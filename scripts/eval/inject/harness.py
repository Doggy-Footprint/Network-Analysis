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


def located_delta(delta, touched):
    hits, total = [], 0
    for key, items in delta.items():
        if key in ('counts', 'resolved') or not isinstance(items, list):
            continue
        for item in items:
            total += 1
            text = json.dumps(item)
            if any(t in text for t in touched):
                hits.append({'list': key, 'kind': item.get('kind'), 'target': item.get('target'), 'id': item.get('id')})
    return hits, total


def tool_findings(root, rels):
    found = []
    py = [r for r in rels if r.endswith('.py') and (root / r).is_file()]
    if not py:
        return found
    proc = run([str(TOOLS / 'ruff'), 'check', '--isolated', '--select', 'ALL', '--no-cache', '--output-format', 'json', *py], cwd=root)
    for row in json.loads(proc.stdout or '[]'):
        found.append(('ruff', row['code'], Path(row['filename']).resolve().relative_to(root.resolve()).as_posix(), row['message']))
    proc = run([str(TOOLS / 'bandit'), '-q', '-f', 'json', *py], cwd=root)
    for row in json.loads(proc.stdout or '{}').get('results', []):
        found.append(('bandit', row['test_id'], row['filename'].removeprefix('./'), row['issue_text']))
    proc = run([str(TOOLS / 'pylint'), '--output-format=json', '--score=n', *py], cwd=root)
    for row in json.loads(proc.stdout or '[]'):
        found.append(('pylint', row['symbol'], row['path'], re.sub(r'\d+', 'N', row['message'])))
    return found


def tool_delta(base_root, worktree, touched):
    before, after = {}, {}
    for key in tool_findings(base_root, touched):
        before[key] = before.get(key, 0) + 1
    for key in tool_findings(worktree, touched):
        after[key] = after.get(key, 0) + 1
    new = [list(k) for k, n in after.items() if n > before.get(k, 0)]
    by_tool = {}
    for tool, *_ in new:
        by_tool[tool] = by_tool.get(tool, 0) + 1
    return {'new': new[:200], 'new_by_tool': by_tool}


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
        delta = report.get('delta') or {}
        (out / 'delta.json').write_text(json.dumps(delta, indent=1))
        hits, total = located_delta(delta, touched)
        result['analyzer'].update(caught=bool(hits), delta_items=total, located=hits[:50])
        result['tools'] = tool_delta(p['clone'], worktree, touched)
        # validity checks run after analysis because the test gate leaves files in the worktree
        if all(checks.values()):
            result['judge'] = judge(task, diff, catalog, texts, out / 'judge')
            checks['judge'] = result['judge'].get('valid') is True
        if all(checks.values()) and not skip_gate:
            result['gate'] = gate(repo, worktree, out)
            checks['tests_green'] = result['gate']['ok']
        result['checks'] = checks
        result['valid'] = all(checks.values())
    except Exception as exc:  # noqa: BLE001 - a broken task must not stop the batch
        result['error'] = f'{type(exc).__name__}: {exc}'[:2000]
        result['valid'] = False
    finally:
        run(['git', 'worktree', 'remove', '--force', str(worktree)], cwd=p['clone'])
        (out / 'result.json').write_text(json.dumps(result, indent=1))
    return result


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


def cmd_score(args):
    catalog = {t['id']: t for t in CATALOG['types']}
    results = [json.loads(p.read_text()) for p in sorted(paths(args.repo)['runs'].glob('*/result.json'))]
    report = {'repo': args.repo, 'tasks': len(results), 'invalid': {}, 'methods': {}, 'negative': {}}
    finders = ['analyzer', 'ruff', 'bandit', 'pylint', 'any_tool']
    for r in results:
        if not r.get('valid'):
            reason = r.get('error') and 'error' or ','.join(k for k, v in (r.get('checks') or {}).items() if not v)
            report['invalid'][r['task']['id']] = reason
    for method in ('script', 'sonnet'):
        per_type = {}
        for r in results:
            if r['task']['method'] != method or not r.get('valid'):
                continue
            by_tool = (r.get('tools') or {}).get('new_by_tool', {})
            hit = {'analyzer': bool(r['analyzer'].get('caught')), 'any_tool': bool(by_tool), **{t: bool(by_tool.get(t)) for t in ('ruff', 'bandit', 'pylint')}}
            row = per_type.setdefault(r['task']['type'], {f: [0, 0] for f in finders})
            for f in finders:
                row[f][0] += hit[f]
                row[f][1] += 1
        summary = {}
        for f in finders:
            num = den = 0.0
            for type_id, row in per_type.items():
                w = catalog[type_id]['weight']
                num += w * row[f][0] / row[f][1]
                den += w
            summary[f] = round(num / den, 4) if den else None
        report['methods'][method] = {'types_with_valid_injection': len(per_type), 'weighted_type_recall': summary,
                                     'per_type': {k: {f: f'{v[f][0]}/{v[f][1]}' for f in finders} for k, v in sorted(per_type.items())}}
    for r in results:
        if r['task']['method'] == 'negative':
            row = report['negative'].setdefault(r['task']['type'], {'valid': 0, 'analyzer_fp': 0, 'tool_fp': 0, 'invalid': 0})
            if not r.get('valid'):
                row['invalid'] += 1
                continue
            row['valid'] += 1
            row['analyzer_fp'] += bool(r['analyzer'].get('caught'))
            row['tool_fp'] += bool((r.get('tools') or {}).get('new_by_tool'))
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
    s = sub.add_parser('score')
    s.add_argument('repo')
    args = parser.parse_args()
    {'baseline': cmd_baseline, 'run': cmd_run, 'score': cmd_score}[args.cmd](args)


if __name__ == '__main__':
    main()
