"""Fault-injection eval: Sonnet injects one catalog problem per task, the analyzer is judged on its baseline delta.

The workspace lives outside this repository and headless agents run with --restricted in a per-task worktree, so the
injector never sees the analyzer or this project's instructions.
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
WORK = Path.home() / 'toy-projects' / 'network-analysis-eval' / 'inject'
MANIFEST = json.loads((ROOT / 'scripts/eval/repos.json').read_text())
CATALOG = json.loads((ROOT / 'scripts/eval/defects/catalog.json').read_text())
TOOLS = WORK / 'tools' / 'bin'
JAVA = '/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin/java'
NODE_BIN = WORK / 'node' / 'node-v22.23.4-darwin-arm64' / 'bin'
JS_TOOLS = WORK / 'tools' / 'eslint'
NOTE = 'INJECTION_NOTE.json'
CLAUDE = ['claude', '-p', '--model', 'sonnet', '--effort', 'medium', '--restricted', '--strict-mcp-config',
          '--no-session-persistence', '--output-format', 'json']
LANGS = {
    'python': {'exts': ('.py',), 'test': r'(^|/)tests?/|(^|/)test_[^/]*\.py$', 'manifests': ('pyproject.toml', 'requirements.txt', 'setup.cfg'),
               'tools': ('ruff', 'bandit', 'pylint', 'semgrep')},
    'typescript': {'exts': ('.ts', '.tsx'), 'test': r'\.(spec|test)\.tsx?$|(^|/)test/', 'manifests': ('package.json',),
                   'tools': ('eslint', 'semgrep')},
    'kotlin': {'exts': ('.kt',), 'test': r'/src/test[A-Za-z]*/', 'manifests': ('gradle/libs.versions.toml', 'app/build.gradle.kts'),
               'tools': ('detekt', 'semgrep')},
}
SKIP_PARTS = {'.git', 'node_modules', 'build', 'migrations', 'dist', '.gradle'}
REPOS = {
    # AWS values are the dummies upstream CI uses
    'CTFd': {'count': 'pytest', 'test': "env AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY "
             "TESTING_DATABASE_URL='sqlite://' {py} -m pytest -c setup.cfg --rootdir=. -p no:randomly -p no:sugar -p no:cacheprovider "
             "-q -rfE --ignore-glob='**/node_modules/' -W ignore::sqlalchemy.exc.SADeprecationWarning -W ignore::sqlalchemy.exc.SAWarning -n 8 tests"},
    'flask-admin': {'count': 'pytest', 'test': '{py} -m pytest -p no:cacheprovider -q -rsx --ignore=flask_admin/tests/geoa '
                    '--ignore=flask_admin/tests/mongoengine --ignore=flask_admin/tests/pymongo --ignore=flask_admin/tests/sqla/test_postgres.py '
                    '--ignore=flask_admin/tests/fileadmin/test_fileadmin_azure.py'},
    'ghostfolio': {'count': 'jest', 'node': True, 'scope': ['apps/api', 'libs/common'],
                   'test': 'NX_DAEMON=false NX_NO_CLOUD=true CI=true npx dotenv-cli -e .env.example -- npx nx run-many --target=test '
                           '--projects=api,common --parallel=1 --skip-nx-cache --outputStyle=stream',
                   'extra': ['npx tsc --noEmit -p apps/api/tsconfig.app.json', 'npx tsc --noEmit -p apps/api/tsconfig.spec.json']},
    # deleting test-results and --no-build-cache make Gradle rerun the tests instead of reporting them up to date
    'nowinandroid': {'count': 'junit', 'exclude': r'/src/androidTest/', 'test': 'find . -path "*/build/test-results" -type d -prune -exec rm -rf {{}} + ; '
                     f'JAVA_HOME="{Path(JAVA).parents[1]}" ./gradlew --no-build-cache testDemoDebugUnitTest :core:common:test :lint:test '
                     '-Proborazzi.test.verify=false --continue'},
}
TEST_TYPES = {'P12', 'P13', 'P14'}
MANIFEST_TYPES = {'P37', 'P38'}
NEGATIVE = {
    'NC1': ('rename', None),
    'NC2': ('format', None),
    'NC3': ('comments', 'Add or improve docstrings and comments in {file} only. Do not change any executable code.'),
    'NC4': ('refactor', 'Make a small behavior-preserving readability refactor in {file} (for example rename local variables or extract a '
                        'private helper used once). Do not change behavior, public names, or other files, and do not introduce any problem.'),
}
GATE = threading.Lock()


def run(cmd, cwd=None, timeout=None, input=None, env=None, check=False):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, input=input, env=env, shell=isinstance(cmd, str))
    if check and proc.returncode:
        raise RuntimeError(f'{cmd}: {proc.stderr[-2000:]}')
    return proc


def node_env():
    return {**os.environ, 'PATH': f'{NODE_BIN}:{TOOLS}:{os.environ["PATH"]}'}


def paths(repo):
    base = WORK / repo
    return {'clone': base / 'clone', 'venv': base / 'env' / 'venv', 'base': base / 'base', 'runs': base / 'runs', 'gate': base / 'gate'}


def lang(repo):
    return LANGS[MANIFEST[repo]['language']]


def type_text():
    rows = {}
    for line in (ROOT / 'scripts/eval/defects/agent-reported.md').read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if re.fullmatch(r'P\d\d', cells[0]) and len(cells) >= 4:
            rows[cells[0]] = f'{cells[2]} Typical form: {cells[3]}'
    return rows


def files_of(repo, kind):
    clone, spec = paths(repo)['clone'], lang(repo)
    if kind == 'manifest':
        return [p for p in spec['manifests'] if (clone / p).is_file()]
    roots = REPOS[repo].get('scope') or MANIFEST[repo].get('packages') or MANIFEST[repo].get('roots') or ['']
    exclude = REPOS[repo].get('exclude')
    out = []
    for path in sorted(clone.rglob('*')):
        rel = path.relative_to(clone).as_posix()
        if path.suffix not in spec['exts'] or rel.endswith('.d.ts') or SKIP_PARTS & set(path.relative_to(clone).parts[:-1]):
            continue
        if (kind == 'test') != bool(re.search(spec['test'], rel)) or (exclude and re.search(exclude, rel)):
            continue
        if (kind == 'source' or REPOS[repo].get('scope')) and not any(not r or rel.startswith(r + '/') for r in roots):
            continue
        if path.is_file() and len(path.read_text(errors='replace').splitlines()) >= 20:
            out.append(rel)
    return out


def plan(repo, types, replicates, negatives):
    tasks = []
    for type_id in types:
        kind = 'test' if type_id in TEST_TYPES else 'manifest' if type_id in MANIFEST_TYPES else 'source'
        pool = files_of(repo, kind)
        for rep in range(replicates):
            rnd = random.Random(f'{repo}:{type_id}:{rep}')
            tasks.append({'id': f'{type_id}-script-{rep}', 'type': type_id, 'method': 'script', 'file': rnd.choice(pool)})
            tasks.append({'id': f'{type_id}-sonnet-{rep}', 'type': type_id, 'method': 'sonnet', 'file': None})
    pool = files_of(repo, 'source')
    for nc in sorted(NEGATIVE):
        for rep in range(negatives):
            tasks.append({'id': f'{nc}-{rep}', 'type': nc, 'method': 'negative', 'file': random.Random(f'{repo}:{nc}:{rep}').choice(pool)})
    return tasks


def scope_text(repo):
    parts = []
    if REPOS[repo].get('scope'):
        parts.append('Keep every change inside ' + ', '.join(f'`{d}/`' for d in REPOS[repo]['scope']) + ' (only these are built and tested).')
    if REPOS[repo].get('exclude'):
        parts.append(f'Do not change files matching `{REPOS[repo]["exclude"]}` (they are not built by the test run).')
    return ' '.join(parts)


def injection_prompt(repo, task, catalog, texts):
    entry = catalog[task['type']]
    detail = texts.get(task['type'], '')
    where = (f'The change must modify `{task["file"]}` and put the problem there; touch other files only if the problem cannot exist without it.'
             if task['file'] else 'Choose the location yourself, where such a change would plausibly be made in this project.')
    where = f'{where} {scope_text(repo)}'.strip()
    return (HERE / 'INJECT_PROMPT.md').read_text().format(name=entry['name'], detail=detail, where=where, note=NOTE)


def wait_online(limit=4 * 3600):
    # an offline Claude call would be recorded as an invalid injection, so calls wait for the API to be reachable
    start = time.time()
    while time.time() - start < limit:
        if run(['curl', '-s', '-o', '/dev/null', '-m', '10', 'https://api.anthropic.com']).returncode == 0:
            return
        time.sleep(60)


def call(args, cwd, timeout, prompt):
    wait_online()
    return run(args, cwd=cwd, timeout=timeout, input=prompt)


def infra_failed(result):
    inject, judged, matched = result.get('inject') or {}, result.get('judge'), result.get('match')
    return bool(inject.get('is_error') or (judged is not None and judged.get('valid') is None)
                or (matched is not None and matched.get('verdict') is None) or result.get('error'))


def claude(prompt, cwd, timeout):
    start = time.perf_counter()
    proc = call(CLAUDE + ['--permission-mode', 'acceptEdits', '--allowedTools', 'Read', 'Edit', 'Write', 'Glob', 'Grep'],
                cwd, timeout, prompt)
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        out = {'is_error': True, 'result': (proc.stdout + proc.stderr)[-2000:]}
    return {'seconds': round(time.perf_counter() - start, 1), 'is_error': out.get('is_error'), 'cost_usd': out.get('total_cost_usd'),
            'turns': out.get('num_turns'), 'result': (out.get('result') or '')[-3000:]}


def negative_meaning(task):
    if task['type'] == 'NC1':
        return f'Rename the file {task["file"]} and update references to it only.'
    if task['type'] == 'NC2':
        return f'Reformat {task["file"]} only.'
    return NEGATIVE[task['type']][1].format(file=task['file'])


def judge(task, diff, catalog, texts, scratch):
    if task['method'] == 'negative':
        question = (f'The diff was meant to be only this: "{negative_meaning(task)}" '
                    'Is the diff limited to that, and free of any new bug, smell, or security problem?')
    else:
        entry = catalog[task['type']]
        question = (f'Problem type: {entry["name"]}. {texts.get(task["type"], "")}\n'
                    'Does the diff introduce at least one concrete instance of this problem type?')
    prompt = (f'{question}\nAnswer with one JSON object only: {{"valid": true|false, "reason": "<one sentence>"}}.\n\n'
              f'```diff\n{diff[:60000]}\n```\n')
    scratch.mkdir(exist_ok=True)
    proc = call(CLAUDE + ['--tools', ''], scratch, 600, prompt)
    try:
        text = json.loads(proc.stdout).get('result', '')
        return json.loads(re.search(r'\{.*\}', text, re.S).group(0))
    except (json.JSONDecodeError, AttributeError):
        return {'valid': None, 'reason': (proc.stdout + proc.stderr)[-500:]}


def changed(worktree):
    run(['git', 'add', '-A'], cwd=worktree, check=True)
    names = run(['git', 'diff', '--cached', '-M', '--name-status', 'HEAD'], cwd=worktree, check=True).stdout.splitlines()
    touched = set()
    for line in names:
        touched.update(line.split('\t')[1:])
    diff = run(['git', 'diff', '--cached', '-M', '--binary', 'HEAD'], cwd=worktree, check=True).stdout
    return sorted(touched), diff


def count_tests(repo, output, gate_dir):
    method = REPOS[repo]['count']
    if method == 'pytest':
        return {k.rstrip('s') if k.startswith('error') else k: int(v) for v, k in re.findall(r'(\d+) (passed|failed|errors?)\b', output[-4000:])}
    if method == 'jest':
        clean = re.sub(r'\x1b\[[0-9;]*m', '', output)
        rows = re.findall(r'^(?:[\w-]+:\s+)?Tests:\s+(.*)$', clean, re.M)
        return {'passed': sum(int(n) for r in rows for n in re.findall(r'(\d+) passed', r)),
                'failed': sum(int(n) for r in rows for n in re.findall(r'(\d+) failed', r))}
    totals = {'passed': 0, 'failed': 0, 'error': 0}
    for xml in gate_dir.glob('**/build/test-results/**/TEST-*.xml'):
        for case in ET.parse(xml).getroot().iter('testcase'):
            tags = {child.tag for child in case}
            key = 'failed' if 'failure' in tags else 'error' if 'error' in tags else 'skipped' if 'skipped' in tags else 'passed'
            totals[key] = totals.get(key, 0) + 1
    return totals


def gate(repo, out):
    """Tests run in one persistent checkout per repository so installed dependencies and build outputs are reused."""
    gate_dir, cfg = paths(repo)['gate'], REPOS[repo]
    env = node_env() if cfg.get('node') else None
    command = cfg['test'].format(py=paths(repo)['venv'] / 'bin' / 'python')
    with GATE:
        run(['git', 'reset', '-q', '--hard', 'base'], cwd=gate_dir, check=True)
        run(['git', 'clean', '-qfd'], cwd=gate_dir, check=True)
        try:
            if (out / 'diff.patch').read_text():
                run(['git', 'apply', '--index', str(out / 'diff.patch')], cwd=gate_dir, check=True)
            start = time.perf_counter()
            proc = run(command, cwd=gate_dir, timeout=3600, env=env)
            output = proc.stdout + proc.stderr
            counts = count_tests(repo, output, gate_dir)
            extras = [run(c, cwd=gate_dir, timeout=1800, env=env) for c in cfg.get('extra', [])]
            seconds = round(time.perf_counter() - start, 1)
        finally:
            run(['git', 'reset', '-q', '--hard', 'base'], cwd=gate_dir)
            run(['git', 'clean', '-qfd'], cwd=gate_dir)
    (out / 'gate.log').write_text(output + ''.join(e.stdout + e.stderr for e in extras))
    ok = proc.returncode == 0 and not counts.get('failed') and not counts.get('error') and counts.get('passed', 0) > 0
    return {'returncode': proc.returncode, 'seconds': seconds, **counts, 'extra_ok': [e.returncode == 0 for e in extras],
            'ok': ok and all(e.returncode == 0 for e in extras), 'tail': output[-800:]}


def analyze(repo, worktree, out, baseline):
    cmd = [str(ROOT / '.venv/bin/python'), '-m', 'code_analyzer', str(worktree), *MANIFEST[repo]['analyzers'], '-o', str(out / 'report.html'),
           '--bottlenecks', str(out / 'bottlenecks.json'), '--title', repo]
    if baseline:
        cmd += ['--baseline', str(baseline)]
    start = time.perf_counter()
    proc = run(cmd, cwd=ROOT, timeout=1800)
    (out / 'analyzer.log').write_text(proc.stdout + proc.stderr)
    return {'returncode': proc.returncode, 'seconds': round(time.perf_counter() - start, 1)}


def location_tokens(touched, roots):
    """Strings that tie a delta item to a touched file: its path, its directory package, and its language package."""
    tokens = set(touched)
    for rel in touched:
        path = Path(rel)
        parent = path.parent.as_posix()
        tokens.add(f'"pkg:dir:{parent}"')
        if path.suffix == '.py':
            parts = path.with_suffix('').parts
            module = parts if parts[-1] != '__init__' else parts[:-1]
            tokens.update(f'"pkg:python:{d}"' for d in {'.'.join(parts[:-1]), '.'.join(module)} - {''})
        elif path.suffix in ('.ts', '.tsx'):
            tokens.add(f'"pkg:nestjs:{parent}/')
        elif path.suffix == '.kt':
            root = next((r for r in roots if (r / rel).is_file()), None)
            if root is None:
                continue
            match = re.search(r'^\s*package\s+([\w.]+)', (root / rel).read_text(errors='replace'), re.M)
            tokens.add(f'"pkg:kotlin:{match.group(1) if match else "<default>"}"')
            module = next((d for d in [path.parent, *path.parent.parents] if (root / d / 'build.gradle.kts').is_file()), None)
            if module is not None and module.as_posix() != '.':
                tokens.add(f'"pkg:gradle::{module.as_posix().replace("/", ":")}"')
    return tokens


def mentions(item, tokens):
    text = json.dumps(item)
    return any(t in text for t in tokens)


def located_delta(delta, tokens):
    hits, total = [], 0
    for key, items in delta.items():
        if key in ('counts', 'resolved') or not isinstance(items, list):
            continue
        for item in items:
            total += 1
            if mentions(item, tokens):
                hits.append({'list': key, 'kind': item.get('kind'), 'target': item.get('target'), 'id': item.get('id')})
    return hits, total


def relpath(name, root):
    path = Path(name)
    return (path.resolve().relative_to(root.resolve()) if path.is_absolute() else path).as_posix().removeprefix('./')


def tool_findings(root, rels, tools, exts):
    found = []
    files = [r for r in rels if r.endswith(exts) and (root / r).is_file()]
    if not files:
        return found
    if 'ruff' in tools:
        proc = run([str(TOOLS / 'ruff'), 'check', '--isolated', '--select', 'ALL', '--no-cache', '--output-format', 'json', *files], cwd=root)
        found += [('ruff', r['code'], relpath(r['filename'], root), r['message'], r['location']['row']) for r in json.loads(proc.stdout or '[]')]
    if 'bandit' in tools:
        proc = run([str(TOOLS / 'bandit'), '-q', '-f', 'json', *files], cwd=root)
        found += [('bandit', r['test_id'], relpath(r['filename'], root), r['issue_text'], r['line_number'])
                  for r in json.loads(proc.stdout or '{}').get('results', [])]
    if 'pylint' in tools:
        proc = run([str(TOOLS / 'pylint'), '--output-format=json', '--score=n', *files], cwd=root)
        found += [('pylint', r['symbol'], r['path'], r['message'], r['line']) for r in json.loads(proc.stdout or '[]')]
    if 'semgrep' in tools:
        proc = run([str(TOOLS / 'semgrep'), 'scan', '--config', str(WORK / 'tools' / 'semgrep-default.yml'), '--metrics=off', '--json', '--quiet',
                    *files], cwd=root, env=node_env())
        found += [('semgrep', r['check_id'].rsplit('.', 1)[-1], relpath(r['path'], root), r['extra']['message'][:300], r['start']['line'])
                  for r in json.loads(proc.stdout or '{}').get('results', [])]
    if 'eslint' in tools:
        proc = run([str(JS_TOOLS / 'node_modules/.bin/eslint'), '-c', str(JS_TOOLS / 'eslint.config.mjs'), '-f', 'json', '--no-warn-ignored', *files],
                   cwd=root, env=node_env())
        found += [('eslint', m.get('ruleId') or 'parse', relpath(r['filePath'], root), m['message'], m.get('line', 0))
                  for r in json.loads(proc.stdout or '[]') for m in r['messages']]
    if 'detekt' in tools:
        report = root / '.detekt-report.xml'
        run([JAVA, '-jar', str(WORK / 'tools/detekt/detekt-cli.jar'), '--input', ','.join(files), '--report', f'xml:{report}'], cwd=root)
        if report.exists():
            for file in ET.parse(report).getroot().iter('file'):
                found += [('detekt', e.get('source', '').removeprefix('detekt.'), relpath(file.get('name'), root), e.get('message', ''),
                           int(e.get('line', 0))) for e in file.iter('error')]
            report.unlink()
    return found


def changed_lines(diff):
    lines, path, number = {}, None, 0
    for line in diff.splitlines():
        if line.startswith('+++ '):
            path = line[6:] if line.startswith('+++ b/') else None
        elif line.startswith('@@'):
            number = int(re.search(r'\+(\d+)', line).group(1))
        elif path and not line.startswith(('---', '\\')):
            if line.startswith('+'):
                lines.setdefault(path, set()).add(number)
            if not line.startswith('-'):
                number += 1
    return lines


def renames(diff):
    return dict(zip(re.findall(r'^rename to (.+)$', diff, re.M), re.findall(r'^rename from (.+)$', diff, re.M)))


def tool_delta(repo, base_root, worktree, touched, diff):
    tools, exts = lang(repo)['tools'], lang(repo)['exts']
    moved = renames(diff)
    back = {old: new for new, old in moved.items()}

    def key(f):
        return f[0], f[1], f[2], re.sub(r'\d+', 'N', f[3])
    before = {}
    for f in tool_findings(base_root, [moved.get(t, t) for t in touched], tools, exts):
        f = (f[0], f[1], back.get(f[2], f[2]), *f[3:])
        before[key(f)] = before.get(key(f), 0) + 1
    after = tool_findings(worktree, touched, tools, exts)
    counts = {}
    for f in after:
        counts[key(f)] = counts.get(key(f), 0) + 1
    lines = changed_lines(diff)
    new = [{'tool': f[0], 'rule': f[1], 'path': f[2], 'message': f[3], 'line': f[4], 'on_changed_line': f[4] in lines.get(f[2], ())}
           for f in after if counts[key(f)] > before.get(key(f), 0)]
    by_tool, on_lines = {}, {}
    for f in new:
        by_tool[f['tool']] = by_tool.get(f['tool'], 0) + 1
        on_lines[f['tool']] = on_lines.get(f['tool'], 0) + f['on_changed_line']
    return {'new': new[:300], 'new_by_tool': by_tool, 'on_changed_lines_by_tool': {k: v for k, v in on_lines.items() if v}}


def rewrite_relative(text, file_rel, source, target):
    package = list(file_rel.parent.parts)
    old_module = list(source.with_suffix('').parts)

    def resolve(dots, module):
        base = package[:len(package) - (len(dots) - 1)] if len(dots) > 1 else package
        return base + (module.split('.') if module else [])

    def fix(match):
        dots, module, names = match.group(1), match.group(2), match.group(3)
        absolute = resolve(dots, module)
        if absolute == old_module:
            return f'from {dots}{module[:len(module) - len(source.stem)]}{target.stem} import{names}'
        if absolute == old_module[:-1]:
            names = re.sub(rf'\b{source.stem}\b(?!\s+as\b)', f'{target.stem} as {source.stem}', names)
        return f'from {dots}{module} import{names}'
    return re.sub(r'from\s+(\.+)([\w.]*)\s+import(\s*\([^)]*\)|[^\n]*)', fix, text)


def rename_file(worktree, rel):
    source = Path(rel)
    if source.suffix == '.kt':
        target = source.with_name(source.stem + 'Impl.kt')
    elif source.suffix in ('.ts', '.tsx'):
        head, _, tail = source.name.partition('.')
        target = source.with_name(f'{head}-impl.{tail}')
    else:
        target = source.with_name(source.stem + '_impl.py')
    run(['git', 'mv', rel, target.as_posix()], cwd=worktree, check=True)
    if source.suffix == '.kt':
        return {'renamed_to': target.as_posix(), 'rewritten': []}
    if source.suffix == '.py':
        old_dotted, new_dotted = '.'.join(source.with_suffix('').parts), '.'.join(target.with_suffix('').parts)
        package = '.'.join(source.parent.parts)
        patterns = [(re.compile(rf'\b{re.escape(old_dotted)}\b'), new_dotted),
                    (re.compile(rf'(from\s+{re.escape(package)}\s+import\s+(?:\([^)]*?)?)\b{source.stem}\b(?!\s+as\b)'),
                     rf'\g<1>{target.stem} as {source.stem}')]
        exts = ('.py',)
    else:
        old_spec, new_spec = source.with_suffix('').name, target.with_suffix('').name
        patterns = [(re.compile(r'''(['"][^'"]*/)''' + re.escape(old_spec) + r'''(['"])'''), rf'\g<1>{new_spec}\g<2>')]
        exts = ('.ts', '.tsx')
    rewritten = []
    for path in sorted(worktree.rglob('*')):
        if path.suffix not in exts or SKIP_PARTS & set(path.relative_to(worktree).parts) or not path.is_file():
            continue
        text = path.read_text(errors='replace')
        new = text
        for pattern, replacement in patterns:
            new = pattern.sub(replacement, new)
        if source.suffix == '.py':
            new = rewrite_relative(new, path.relative_to(worktree), source, target)
        if new != text:
            path.write_text(new)
            rewritten.append(path.relative_to(worktree).as_posix())
    return {'renamed_to': target.as_posix(), 'rewritten': rewritten}


def format_only(worktree, rel):
    if rel.endswith('.py'):
        cmd = [str(TOOLS / 'ruff'), 'format', '--isolated', '--line-length', '60', rel]
    elif rel.endswith(('.ts', '.tsx')):
        cmd = [str(JS_TOOLS / 'node_modules/.bin/prettier'), '--no-config', '--print-width', '60', '--write', rel]
    else:
        cmd = [JAVA, '-jar', str(WORK / 'tools/ktfmt/ktfmt.jar'), '--google-style', rel]
    return {'returncode': run(cmd, cwd=worktree, env=node_env()).returncode}


def match(task, out, diff, catalog, texts, analyzer_items, tool_new, finders):
    findings = {'analyzer': [json.dumps(i)[:2500] for i in analyzer_items[:20]]}
    for tool in finders[1:]:
        findings[tool] = [f'{f["path"]}:{f["line"]} {f["rule"]} {f["message"]}' for f in tool_new if f['tool'] == tool][:40]
    present = [f for f in finders if findings[f]]
    verdict = {f: False for f in finders}
    if not present:
        return {'verdict': verdict, 'reason': 'no findings'}
    order = sorted(present, key=lambda f: random.Random(f'{task["id"]}:{f}').random())
    letters = {f: chr(ord('A') + i) for i, f in enumerate(order)}
    note = (out / NOTE).read_text()[:2000] if (out / NOTE).exists() else ''
    entry = catalog[task['type']]
    blocks = '\n\n'.join(f'Reviewer {letters[f]}:\n' + '\n'.join(f'- {x}' for x in findings[f]) for f in order)
    prompt = (f'A diff was made to contain one instance of this problem: {entry["name"]}. {texts.get(task["type"], "")}\n'
              f'Author\'s note on where it is: {note}\n\n```diff\n{diff[:40000]}\n```\n\n'
              'Several automated reviewers reported the findings below. For each reviewer, decide whether at least one of its findings '
              'identifies this injected problem: it must point at the code that carries the problem and describe the problem or its direct '
              'symptom. Findings that only flag style, naming, or unrelated issues do not count.\n\n'
              f'{blocks}\n\nAnswer with one JSON object only: {{"<letter>": true|false, ..., "reason": "<one sentence>"}}.')
    (out / 'match_prompt.md').write_text(prompt)
    scratch = out / 'judge'
    scratch.mkdir(exist_ok=True)
    proc = call(CLAUDE + ['--tools', ''], scratch, 600, prompt)
    try:
        answer = json.loads(re.search(r'\{.*\}', json.loads(proc.stdout).get('result', ''), re.S).group(0))
    except (json.JSONDecodeError, AttributeError):
        return {'verdict': None, 'reason': (proc.stdout + proc.stderr)[-500:]}
    for f in present:
        verdict[f] = answer.get(letters[f]) is True
    return {'verdict': verdict, 'letters': letters, 'reason': answer.get('reason')}


def assess(repo, out, worktree, touched, diff, result):
    delta = json.loads((out / 'delta.json').read_text())
    tokens = location_tokens(touched, [worktree, paths(repo)['clone']])
    hits, total = located_delta(delta, tokens)
    result['analyzer'].update(caught=bool(hits), delta_items=total, located=hits[:50])
    result['tools'] = tool_delta(repo, paths(repo)['clone'], worktree, touched, diff)
    result['finders'] = ['analyzer', *lang(repo)['tools']]
    result['tokens'] = sorted(tokens)


def assess_match(task, out, diff, result, catalog, texts):
    if result.get('valid') and task['method'] != 'negative':
        delta = json.loads((out / 'delta.json').read_text())
        tokens = set(result['tokens'])
        items = [i for v in delta.values() if isinstance(v, list) for i in v if mentions(i, tokens)]
        result['match'] = match(task, out, diff, catalog, texts, items, result['tools']['new'], result['finders'])


def compiles(repo, worktree, touched):
    if MANIFEST[repo]['language'] != 'python':
        return True
    return all(run([sys.executable, '-m', 'py_compile', rel], cwd=worktree).returncode == 0
               for rel in touched if rel.endswith('.py') and (worktree / rel).is_file())


def execute(repo, task, catalog, texts, skip_gate):
    p = paths(repo)
    out = p['runs'] / task['id']
    if (out / 'result.json').exists():
        cached = json.loads((out / 'result.json').read_text())
        if not cached.get('infra_failed'):
            return cached
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    worktree = WORK / repo / 'wt' / task['id']
    if worktree.exists():
        run(['git', 'worktree', 'remove', '--force', str(worktree)], cwd=p['clone'])
    run(['git', 'worktree', 'add', '-q', '--detach', str(worktree), 'base'], cwd=p['clone'], check=True)
    result = {'task': task}
    try:
        if task['type'] == 'NC2':
            result['inject'] = format_only(worktree, task['file'])
        elif task['type'] == 'NC1':
            result['inject'] = rename_file(worktree, task['file'])
        else:
            if task['method'] == 'negative':
                prompt = (HERE / 'NEGATIVE_PROMPT.md').read_text().format(instruction=negative_meaning(task))
            else:
                prompt = injection_prompt(repo, task, catalog, texts)
            (out / 'prompt.md').write_text(prompt)
            result['inject'] = claude(prompt, worktree, timeout=1800)
        note = worktree / NOTE
        if note.exists():
            (out / NOTE).write_text(note.read_text())
            note.unlink()
        touched, diff = changed(worktree)
        (out / 'diff.patch').write_text(diff)
        result['touched'] = touched
        checks = {'nonempty': bool(touched)}
        if task['method'] == 'script':
            checks['primary_touched'] = task['file'] in touched
        checks['compiles'] = compiles(repo, worktree, touched)
        result['analyzer'] = analyze(repo, worktree, out, p['base'] / 'bottlenecks.json')
        report = json.loads((out / 'bottlenecks.json').read_text()) if result['analyzer']['returncode'] == 0 else {}
        (out / 'delta.json').write_text(json.dumps(report.get('delta') or {}, indent=1))
        assess(repo, out, worktree, touched, diff, result)
        if all(checks.values()) and task['type'] not in ('NC1', 'NC2'):
            result['judge'] = judge(task, diff, catalog, texts, out / 'judge')
            checks['judge'] = result['judge'].get('valid') is True
        if all(checks.values()) and not skip_gate:
            result['gate'] = gate(repo, out)
            checks['tests_green'] = result['gate']['ok']
        result['checks'] = checks
        result['valid'] = all(checks.values())
        assess_match(task, out, diff, result, catalog, texts)
    except Exception as exc:  # noqa: BLE001 - a broken task must not stop the batch
        result['error'] = f'{type(exc).__name__}: {exc}'[:2000]
        result['valid'] = False
    finally:
        run(['git', 'worktree', 'remove', '--force', str(worktree)], cwd=p['clone'])
        result['infra_failed'] = infra_failed(result)
        (out / 'result.json').write_text(json.dumps(result, indent=1))
    return result


def cmd_rescore(args):
    catalog = {t['id']: t for t in CATALOG['types']}
    texts = type_text()
    p = paths(args.repo)

    def one(path):
        result = json.loads(path.read_text())
        out, task = path.parent, result['task']
        if result.get('error') or 'analyzer' not in result:
            return task['id'], 'skipped'
        worktree = WORK / args.repo / 'wt' / ('rescore-' + task['id'])
        if worktree.exists():
            run(['git', 'worktree', 'remove', '--force', str(worktree)], cwd=p['clone'])
        run(['git', 'worktree', 'add', '-q', '--detach', str(worktree), 'base'], cwd=p['clone'], check=True)
        try:
            diff = (out / 'diff.patch').read_text()
            if diff:
                run(['git', 'apply', '--index', str(out / 'diff.patch')], cwd=worktree, check=True)
            assess(args.repo, out, worktree, result['touched'], diff, result)
            assess_match(task, out, diff, result, catalog, texts)
        finally:
            run(['git', 'worktree', 'remove', '--force', str(worktree)], cwd=p['clone'])
        result['infra_failed'] = infra_failed(result)
        path.write_text(json.dumps(result, indent=1))
        return task['id'], (result.get('match') or {}).get('verdict')

    with ThreadPoolExecutor(args.workers) as pool:
        for row in pool.map(one, sorted(p['runs'].glob('*/result.json'))):
            print(json.dumps(row), flush=True)


def cmd_clone(args):
    clone = paths(args.repo)['clone']
    spec = MANIFEST[args.repo]
    if clone.exists():
        shutil.rmtree(clone)
    clone.mkdir(parents=True)

    def git(*a):
        return run(['git', *a], cwd=clone, check=True).stdout.strip()
    git('init', '-q')
    # fetch by URL without registering a remote, so the injector's worktree has no upstream to look up
    git('fetch', '-q', '--depth', '1', f'https://github.com/{spec["github"]}.git', spec['commit'])
    git('checkout', '-q', '-b', 'base', 'FETCH_HEAD')
    (clone / '.git' / 'FETCH_HEAD').unlink()
    shutil.rmtree(clone / '.git' / 'logs', ignore_errors=True)
    git('config', 'user.name', 'eval')
    git('config', 'user.email', 'eval@localhost')
    assert git('rev-parse', 'HEAD') == spec['commit']
    print(clone)


def cmd_baseline(args):
    p = paths(args.repo)
    p['base'].mkdir(parents=True, exist_ok=True)
    print(json.dumps(analyze(args.repo, p['clone'], p['base'], None)))


def cmd_gate(args):
    out = WORK / args.repo / 'gate-check'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'diff.patch').write_text('')
    result = gate(args.repo, out)
    print(json.dumps({k: v for k, v in result.items() if k != 'tail'}))


def cmd_run(args):
    catalog = {t['id']: t for t in CATALOG['types']}
    texts = type_text()
    types = args.types.split(',') if args.types else [t['id'] for t in CATALOG['types'] if t['injectable']]
    tasks = plan(args.repo, types, args.replicates, args.negatives)
    if args.only_negative:
        tasks = [t for t in tasks if t['method'] == 'negative']
    paths(args.repo)['runs'].mkdir(parents=True, exist_ok=True)
    print(f'{len(tasks)} tasks', flush=True)
    with ThreadPoolExecutor(args.workers) as pool:
        for result in pool.map(lambda t: execute(args.repo, t, catalog, texts, args.skip_gate), tasks):
            a = result.get('analyzer') or {}
            print(json.dumps({'id': result['task']['id'], 'valid': result.get('valid'), 'checks': result.get('checks'),
                              'caught': a.get('caught'), 'tools': (result.get('tools') or {}).get('new_by_tool'),
                              'error': result.get('error')}), flush=True)


def hits(r, tools):
    on_lines = (r.get('tools') or {}).get('on_changed_lines_by_tool', {})
    located = {'analyzer': bool(r['analyzer'].get('caught')), **{t: bool(on_lines.get(t)) for t in tools}}
    verdict = (r.get('match') or {}).get('verdict') or {}
    matched = {f: bool(verdict.get(f)) for f in ('analyzer', *tools)}
    for h in (located, matched):
        h['any_tool'] = any(h[t] for t in tools)
    return {'matched': matched, 'located': located}


def cmd_score(args):
    catalog = {t['id']: t for t in CATALOG['types']}
    tools = list(lang(args.repo)['tools'])
    finders = ['analyzer', *tools, 'any_tool']
    results = [json.loads(p.read_text()) for p in sorted(paths(args.repo)['runs'].glob('*/result.json'))]
    report = {'repo': args.repo, 'tasks': len(results), 'infra_failed': [], 'invalid': {}, 'methods': {}, 'negative': {},
              'definitions': {'matched': 'a Sonnet judge, seeing the diff, the type, and anonymized findings, says a finding identifies the injected problem',
                              'located': 'analyzer: a delta item names a touched file or its package; tools: a new finding on an added line'}}
    for r in results:
        if r.get('infra_failed'):
            report['infra_failed'].append(r['task']['id'])
        elif not r.get('valid'):
            report['invalid'][r['task']['id']] = r.get('error') and 'error' or ','.join(k for k, v in (r.get('checks') or {}).items() if not v)
    usable = [r for r in results if r.get('valid') and not r.get('infra_failed')]
    for method in ('script', 'sonnet'):
        per_type = {}
        for r in usable:
            if r['task']['method'] != method:
                continue
            h = hits(r, tools)
            row = per_type.setdefault(r['task']['type'], {m: {f: [0, 0] for f in finders} for m in h})
            for m in h:
                for f in finders:
                    row[m][f][0] += h[m][f]
                    row[m][f][1] += 1
        summary = {}
        for m in ('matched', 'located'):
            summary[m] = {}
            for f in finders:
                num = den = 0.0
                for type_id, row in per_type.items():
                    w = catalog[type_id]['weight']
                    num += w * row[m][f][0] / row[m][f][1]
                    den += w
                summary[m][f] = round(num / den, 4) if den else None
        report['methods'][method] = {'types_with_valid_injection': len(per_type), 'weighted_type_recall': summary,
                                     'per_type_matched': {k: {f: f'{v["matched"][f][0]}/{v["matched"][f][1]}' for f in finders}
                                                          for k, v in sorted(per_type.items())}}
    for r in results:
        if r['task']['method'] != 'negative' or r.get('infra_failed'):
            continue
        row = report['negative'].setdefault(r['task']['type'], {'valid': 0, 'invalid': 0, **{f'{f}_fp': 0 for f in finders}})
        if not r.get('valid'):
            row['invalid'] += 1
            continue
        row['valid'] += 1
        for f, v in hits(r, tools)['located'].items():
            row[f'{f}_fp'] += v
    text = json.dumps(report, indent=1)
    (WORK / args.repo / 'score.json').write_text(text)
    print(text)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd', required=True)
    for name in ('clone', 'baseline', 'gate', 'score'):
        sub.add_parser(name).add_argument('repo')
    r = sub.add_parser('run')
    r.add_argument('repo')
    r.add_argument('--types', help='comma-separated catalog ids (default: every injectable type)')
    r.add_argument('--replicates', type=int, default=1)
    r.add_argument('--negatives', type=int, default=2)
    r.add_argument('--workers', type=int, default=3)
    r.add_argument('--skip-gate', action='store_true')
    r.add_argument('--only-negative', action='store_true')
    rs = sub.add_parser('rescore')
    rs.add_argument('repo')
    rs.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    {'clone': cmd_clone, 'baseline': cmd_baseline, 'gate': cmd_gate, 'run': cmd_run, 'rescore': cmd_rescore, 'score': cmd_score}[args.cmd](args)


if __name__ == '__main__':
    main()
