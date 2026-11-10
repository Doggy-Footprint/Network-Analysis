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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
WORK = Path.home() / 'toy-projects' / 'network-analysis-eval' / 'inject'
MANIFEST = json.loads((ROOT / 'scripts/eval/repos.json').read_text())
CATALOG = json.loads((ROOT / 'scripts/eval/defects/catalog.json').read_text())
TOOLS = WORK / 'tools' / 'bin'
NOTE = 'INJECTION_NOTE.json'
CLAUDE = ['claude', '-p', '--model', 'sonnet', '--effort', 'medium', '--restricted', '--strict-mcp-config',
          '--no-session-persistence', '--output-format', 'json']
TEST_ENV = {
    # AWS values are the dummies upstream CI uses
    'CTFd': {'python': '3.11', 'command': "env AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY "
             "TESTING_DATABASE_URL='sqlite://' {py} -m pytest -c setup.cfg --rootdir=. -p no:randomly -p no:sugar -p no:cacheprovider "
             "-q -rfE --ignore-glob='**/node_modules/' -W ignore::sqlalchemy.exc.SADeprecationWarning -W ignore::sqlalchemy.exc.SAWarning "
             "-n 8 tests --junitxml={junit}"},
}
TEST_TYPES = {'P12', 'P13', 'P14'}
MANIFEST_TYPES = {'P37', 'P38'}
NEGATIVE = {
    'NC1': ('rename', 'Rename the module {file} to a new, sensible name in the same package and update every reference to it. Make no other change.'),
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


def paths(repo):
    base = WORK / repo
    return {'clone': base / 'clone', 'venv': base / 'env' / 'venv', 'base': base / 'base', 'runs': base / 'runs'}


def type_text():
    rows = {}
    for line in (ROOT / 'scripts/eval/defects/agent-reported.md').read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if re.fullmatch(r'P\d\d', cells[0]) and len(cells) >= 4:
            rows[cells[0]] = f'{cells[2]} Typical form: {cells[3]}'
    return rows


def files_of(repo, kind):
    clone = paths(repo)['clone']
    if kind == 'manifest':
        return [p for p in ('pyproject.toml', 'requirements.txt', 'package.json') if (clone / p).is_file()]
    out = []
    for path in sorted(clone.rglob('*.py')):
        rel = path.relative_to(clone).as_posix()
        is_test = rel.startswith('tests/') or '/tests/' in rel
        if '.git/' in rel or 'migrations/' in rel or (kind == 'test') != is_test:
            continue
        if kind == 'source' and not any(rel.startswith(p + '/') for p in MANIFEST[repo].get('packages', [''])):
            continue
        if len(path.read_text(errors='replace').splitlines()) >= 20:
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


def injection_prompt(task, catalog, texts):
    entry = catalog[task['type']]
    detail = texts.get(task['type'], '')
    where = (f'The change must modify `{task["file"]}` and put the problem there; touch other files only if the problem cannot exist without it.'
             if task['file'] else 'Choose the location yourself, where such a change would plausibly be made in this project.')
    return (HERE / 'INJECT_PROMPT.md').read_text().format(name=entry['name'], detail=detail, where=where, note=NOTE)


def claude(prompt, cwd, timeout):
    start = time.perf_counter()
    proc = run(CLAUDE + ['--permission-mode', 'acceptEdits', '--allowedTools', 'Read', 'Edit', 'Write', 'Glob', 'Grep'],
               cwd=cwd, timeout=timeout, input=prompt)
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        out = {'is_error': True, 'result': (proc.stdout + proc.stderr)[-2000:]}
    return {'seconds': round(time.perf_counter() - start, 1), 'is_error': out.get('is_error'), 'cost_usd': out.get('total_cost_usd'),
            'turns': out.get('num_turns'), 'result': (out.get('result') or '')[-3000:]}


def judge(task, diff, catalog, texts, scratch):
    if task['method'] == 'negative':
        meant = (NEGATIVE[task['type']][1] or 'Reformat {file} only.').format(file=task['file'])
        question = (f'The diff was meant to be only this: "{meant}" '
                    'Is the diff limited to that, and free of any new bug, smell, or security problem?')
    else:
        entry = catalog[task['type']]
        question = (f'Problem type: {entry["name"]}. {texts.get(task["type"], "")}\n'
                    'Does the diff introduce at least one concrete instance of this problem type?')
    prompt = (f'{question}\nAnswer with one JSON object only: {{"valid": true|false, "reason": "<one sentence>"}}.\n\n'
              f'```diff\n{diff[:60000]}\n```\n')
    scratch.mkdir(exist_ok=True)
    proc = run(CLAUDE + ['--tools', ''], cwd=scratch, timeout=600, input=prompt)
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
    diff = run(['git', 'diff', '--cached', '-M', 'HEAD'], cwd=worktree, check=True).stdout
    return sorted(touched), diff


def gate(repo, worktree, out):
    py = paths(repo)['venv'] / 'bin' / 'python'
    command = TEST_ENV[repo]['command'].format(py=py, junit=out / 'junit.xml')
    with GATE:
        start = time.perf_counter()
        proc = run(command, cwd=worktree, timeout=1800)
    tail = (proc.stdout + proc.stderr)[-3000:]
    counts = {k: int(v) for v, k in re.findall(r'(\d+) (passed|failed|errors?)', tail)}
    return {'returncode': proc.returncode, 'seconds': round(time.perf_counter() - start, 1), **counts,
            'ok': proc.returncode == 0 and not counts.get('failed') and not counts.get('error') and not counts.get('errors'),
            'tail': tail[-800:]}


def analyze(repo, worktree, out, baseline):
    cmd = [str(ROOT / '.venv/bin/python'), '-m', 'code_analyzer', str(worktree), *MANIFEST[repo]['analyzers'], '-o', str(out / 'report.html'),
           '--bottlenecks', str(out / 'bottlenecks.json'), '--title', repo]
    if baseline:
        cmd += ['--baseline', str(baseline)]
    start = time.perf_counter()
    proc = run(cmd, cwd=ROOT, timeout=1800)
    (out / 'analyzer.log').write_text(proc.stdout + proc.stderr)
    return {'returncode': proc.returncode, 'seconds': round(time.perf_counter() - start, 1)}


def location_tokens(touched):
    tokens = set(touched)
    for rel in touched:
        if rel.endswith('.py'):
            parts = Path(rel).with_suffix('').parts
            package = parts[:-1] if parts[-1] != '__init__' else parts[:-1]
            module = parts if parts[-1] != '__init__' else parts[:-1]
            for dotted in {'.'.join(package), '.'.join(module)} - {''}:
                tokens.add(f'"pkg:python:{dotted}"')
    return tokens


def mentions(item, touched):
    text = json.dumps(item)
    return any(t in text for t in location_tokens(touched))


def located_delta(delta, touched):
    hits, total = [], 0
    for key, items in delta.items():
        if key in ('counts', 'resolved') or not isinstance(items, list):
            continue
        for item in items:
            total += 1
            if mentions(item, touched):
                hits.append({'list': key, 'kind': item.get('kind'), 'target': item.get('target'), 'id': item.get('id')})
    return hits, total


def tool_findings(root, rels):
    found = []
    py = [r for r in rels if r.endswith('.py') and (root / r).is_file()]
    if not py:
        return found
    proc = run([str(TOOLS / 'ruff'), 'check', '--isolated', '--select', 'ALL', '--no-cache', '--output-format', 'json', *py], cwd=root)
    for row in json.loads(proc.stdout or '[]'):
        rel = Path(row['filename']).resolve().relative_to(root.resolve()).as_posix()
        found.append(('ruff', row['code'], rel, row['message'], row['location']['row']))
    proc = run([str(TOOLS / 'bandit'), '-q', '-f', 'json', *py], cwd=root)
    for row in json.loads(proc.stdout or '{}').get('results', []):
        found.append(('bandit', row['test_id'], row['filename'].removeprefix('./'), row['issue_text'], row['line_number']))
    proc = run([str(TOOLS / 'pylint'), '--output-format=json', '--score=n', *py], cwd=root)
    for row in json.loads(proc.stdout or '[]'):
        found.append(('pylint', row['symbol'], row['path'], row['message'], row['line']))
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


def tool_delta(base_root, worktree, touched, diff):
    def key(f):
        return f[0], f[1], f[2], re.sub(r'\d+', 'N', f[3])
    before = {}
    for f in tool_findings(base_root, touched):
        before[key(f)] = before.get(key(f), 0) + 1
    after = tool_findings(worktree, touched)
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


def rename_module(worktree, rel):
    source = Path(rel)
    target = source.with_name(source.stem + '_impl.py')
    old_dotted, new_dotted = '.'.join(source.with_suffix('').parts), '.'.join(target.with_suffix('').parts)
    run(['git', 'mv', rel, target.as_posix()], cwd=worktree, check=True)
    package = '.'.join(source.parent.parts)
    patterns = [(re.compile(rf'\b{re.escape(old_dotted)}\b'), new_dotted),
                (re.compile(rf'(from\s+{re.escape(package)}\s+import\s+(?:\([^)]*?)?)\b{source.stem}\b'), rf'\g<1>{target.stem}'),
                (re.compile(rf'(from\s+\.)({source.stem})(\s+import)'), rf'\g<1>{target.stem}\g<3>')]
    rewritten = []
    for path in sorted(worktree.rglob('*.py')):
        if '.git' in path.parts:
            continue
        text = path.read_text(errors='replace')
        new = text
        for pattern, replacement in patterns[:2]:
            new = pattern.sub(replacement, new)
        if path.parent == worktree / source.parent:
            new = patterns[2][0].sub(patterns[2][1], new)
        if new != text:
            path.write_text(new)
            rewritten.append(path.relative_to(worktree).as_posix())
    return {'renamed_to': target.as_posix(), 'rewritten': rewritten}


FINDERS = ('analyzer', 'ruff', 'bandit', 'pylint')


def match(task, out, diff, catalog, texts, analyzer_items, tool_new):
    findings = {'analyzer': [json.dumps(i)[:2500] for i in analyzer_items[:20]]}
    for tool in FINDERS[1:]:
        findings[tool] = [f'{f["path"]}:{f["line"]} {f["rule"]} {f["message"]}' for f in tool_new if f['tool'] == tool][:40]
    present = [f for f in FINDERS if findings[f]]
    verdict = {f: False for f in FINDERS}
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
    proc = run(CLAUDE + ['--tools', ''], cwd=scratch, timeout=600, input=prompt)
    try:
        answer = json.loads(re.search(r'\{.*\}', json.loads(proc.stdout).get('result', ''), re.S).group(0))
    except (json.JSONDecodeError, AttributeError):
        return {'verdict': None, 'reason': (proc.stdout + proc.stderr)[-500:]}
    for f in present:
        verdict[f] = answer.get(letters[f]) is True
    return {'verdict': verdict, 'letters': letters, 'reason': answer.get('reason')}


def assess(repo, task, out, worktree, touched, diff, result):
    delta = json.loads((out / 'delta.json').read_text())
    hits, total = located_delta(delta, touched)
    result['analyzer'].update(caught=bool(hits), delta_items=total, located=hits[:50])
    result['tools'] = tool_delta(paths(repo)['clone'], worktree, touched, diff)


def assess_match(task, out, diff, touched, result, catalog, texts):
    delta = json.loads((out / 'delta.json').read_text())
    if result.get('valid') and task['method'] != 'negative':
        items = [i for k, v in delta.items() if isinstance(v, list) for i in v if mentions(i, touched)]
        result['match'] = match(task, out, diff, catalog, texts, items, result['tools']['new'])


def format_only(worktree, rel):
    proc = run([str(TOOLS / 'ruff'), 'format', '--isolated', '--line-length', '60', rel], cwd=worktree)
    return {'returncode': proc.returncode}


def execute(repo, task, catalog, texts, skip_gate):
    p = paths(repo)
    out = p['runs'] / task['id']
    if (out / 'result.json').exists():
        return json.loads((out / 'result.json').read_text())
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
            result['inject'] = rename_module(worktree, task['file'])
        else:
            if task['method'] == 'negative':
                prompt = (HERE / 'NEGATIVE_PROMPT.md').read_text().format(instruction=NEGATIVE[task['type']][1].format(file=task['file']))
            else:
                prompt = injection_prompt(task, catalog, texts)
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
        compile_errors = []
        for rel in touched:
            if rel.endswith('.py') and (worktree / rel).is_file():
                proc = run([sys.executable, '-m', 'py_compile', rel], cwd=worktree)
                if proc.returncode:
                    compile_errors.append(rel)
        checks['compiles'] = not compile_errors
        result['analyzer'] = analyze(repo, worktree, out, p['base'] / 'bottlenecks.json')
        report = json.loads((out / 'bottlenecks.json').read_text()) if result['analyzer']['returncode'] == 0 else {}
        (out / 'delta.json').write_text(json.dumps(report.get('delta') or {}, indent=1))
        assess(repo, task, out, worktree, touched, diff, result)
        # validity checks run after analysis because the test gate leaves files in the worktree
        if all(checks.values()):
            result['judge'] = judge(task, diff, catalog, texts, out / 'judge')
            checks['judge'] = result['judge'].get('valid') is True
        if all(checks.values()) and not skip_gate:
            result['gate'] = gate(repo, worktree, out)
            checks['tests_green'] = result['gate']['ok']
        result['checks'] = checks
        result['valid'] = all(checks.values())
        assess_match(task, out, diff, touched, result, catalog, texts)
    except Exception as exc:  # noqa: BLE001 - a broken task must not stop the batch
        result['error'] = f'{type(exc).__name__}: {exc}'[:2000]
        result['valid'] = False
    finally:
        run(['git', 'worktree', 'remove', '--force', str(worktree)], cwd=p['clone'])
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
            assess(args.repo, task, out, worktree, result['touched'], diff, result)
            assess_match(task, out, diff, result['touched'], result, catalog, texts)
        finally:
            run(['git', 'worktree', 'remove', '--force', str(worktree)], cwd=p['clone'])
        path.write_text(json.dumps(result, indent=1))
        return task['id'], (result.get('match') or {}).get('verdict')

    with ThreadPoolExecutor(args.workers) as pool:
        for row in pool.map(one, sorted(p['runs'].glob('*/result.json'))):
            print(json.dumps(row), flush=True)


def cmd_baseline(args):
    p = paths(args.repo)
    p['base'].mkdir(parents=True, exist_ok=True)
    print(json.dumps(analyze(args.repo, p['clone'], p['base'], None)))


def cmd_run(args):
    catalog = {t['id']: t for t in CATALOG['types']}
    texts = type_text()
    types = args.types.split(',') if args.types else [t['id'] for t in CATALOG['types'] if t['injectable']]
    tasks = plan(args.repo, types, args.replicates, args.negatives)
    if args.only_negative:
        tasks = [t for t in tasks if t['method'] == 'negative']
    (paths(args.repo)['runs']).mkdir(parents=True, exist_ok=True)
    print(f'{len(tasks)} tasks', flush=True)
    with ThreadPoolExecutor(args.workers) as pool:
        for result in pool.map(lambda t: execute(args.repo, t, catalog, texts, args.skip_gate), tasks):
            a = result.get('analyzer') or {}
            print(json.dumps({'id': result['task']['id'], 'valid': result.get('valid'), 'checks': result.get('checks'),
                              'caught': a.get('caught'), 'tools': (result.get('tools') or {}).get('new_by_tool'),
                              'error': result.get('error')}), flush=True)


def hits(r):
    on_lines = (r.get('tools') or {}).get('on_changed_lines_by_tool', {})
    located = {'analyzer': bool(r['analyzer'].get('caught')), **{t: bool(on_lines.get(t)) for t in FINDERS[1:]}}
    verdict = (r.get('match') or {}).get('verdict') or {}
    matched = {f: bool(verdict.get(f)) for f in FINDERS}
    for h in (located, matched):
        h['any_tool'] = any(h[t] for t in FINDERS[1:])
    return {'matched': matched, 'located': located}


def cmd_score(args):
    catalog = {t['id']: t for t in CATALOG['types']}
    results = [json.loads(p.read_text()) for p in sorted(paths(args.repo)['runs'].glob('*/result.json'))]
    report = {'repo': args.repo, 'tasks': len(results), 'invalid': {}, 'methods': {}, 'negative': {},
              'definitions': {'matched': 'a Sonnet judge, seeing the diff, the type, and anonymized findings, says a finding identifies the injected problem',
                              'located': 'analyzer: a delta item names a touched file; tools: a new finding on an added line'}}
    finders = [*FINDERS, 'any_tool']
    for r in results:
        if not r.get('valid'):
            reason = r.get('error') and 'error' or ','.join(k for k, v in (r.get('checks') or {}).items() if not v)
            report['invalid'][r['task']['id']] = reason
    for method in ('script', 'sonnet'):
        per_type = {}
        for r in results:
            if r['task']['method'] != method or not r.get('valid'):
                continue
            h = hits(r)
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
                                     'per_type_matched': {k: {f: f'{v["matched"][f][0]}/{v["matched"][f][1]}' for f in finders} for k, v in sorted(per_type.items())}}
    for r in results:
        if r['task']['method'] == 'negative':
            row = report['negative'].setdefault(r['task']['type'], {'valid': 0, 'invalid': 0, **{f'{f}_fp': 0 for f in finders}})
            if not r.get('valid'):
                row['invalid'] += 1
                continue
            row['valid'] += 1
            for f, v in hits(r)['located'].items():
                row[f'{f}_fp'] += v
    text = json.dumps(report, indent=1)
    (WORK / args.repo / 'score.json').write_text(text)
    print(text)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('baseline')
    b.add_argument('repo')
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
    s = sub.add_parser('score')
    s.add_argument('repo')
    args = parser.parse_args()
    {'baseline': cmd_baseline, 'run': cmd_run, 'rescore': cmd_rescore, 'score': cmd_score}[args.cmd](args)


if __name__ == '__main__':
    main()
