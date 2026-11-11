"""argv: commit worktree, fixture dir, out golden path. Mirrors tests/build_modules_evidence/base_android-nowinandroid.json fields."""
import json, os, subprocess, sys, tempfile
from pathlib import Path
wt, fx, out = sys.argv[1], sys.argv[2], sys.argv[3]
env = dict(os.environ, PYTHONHASHSEED='0', PYTHONPATH=wt)
def run(args):
    d = Path(tempfile.mkdtemp())
    subprocess.run(['uv', 'run', '-q', '--with-requirements', f'{wt}/requirements-dev.txt', 'python', '-m', 'code_analyzer', fx, *args,
                    '-o', str(d / 'r.html'), '--json', '--bottlenecks', str(d / 'b.json')], cwd=wt, env=env, check=True, capture_output=True)
    return json.loads((d / 'b.json').read_text()), json.loads((d / 'r.json').read_text())
def facts(b, symbol):
    net = b['dependency_network']
    f = {'candidates': [{'id': c['id'], 'kind': c['kind'], 'target': c.get('target')} for c in b['candidates']],
         'edge_count': net['edge_count'], 'node_count': net['node_count'], 'node_metrics': net['node_metrics']}
    if not symbol:
        f.update(file_ids=net['file_ids'], package_dependencies=net['package_dependencies'], package_metrics=net['package_metrics'])
    return f
def arch(a):
    return {'edges': sorted([e['from_id'], e['to_id'], e['relation']] for e in a['edges']), 'nodes': sorted(n['id'] for n in a['nodes'])}
fb, fa = run(['-l', 'kotlin', '--granularity', 'file'])
sb, sa = run(['-l', 'kotlin', '--granularity', 'symbol'])
ab, aa = run(['-f', 'android', '--granularity', 'symbol'])
commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=wt, capture_output=True, text=True).stdout.strip()
g = {'architecture_file': arch(fa), 'base_commit': commit, 'file': facts(fb, False), 'fixture': 'android-nowinandroid',
     'symbol': facts(sb, True), 'symbol_by_flags': {'android': {**facts(ab, True), 'architecture': arch(aa)}, 'kotlin': {**facts(sb, True), 'architecture': arch(sa)}}}
Path(out).write_text(json.dumps(g, sort_keys=True) + '\n')
