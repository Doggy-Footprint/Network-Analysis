"""Compare two measured revisions (see measure.py) on independent metrics first, analyzer metrics second."""
import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / 'eval'


def load(repo, label):
    out = EVAL / 'results' / repo / label
    return out, json.loads((out / 'summary.json').read_text()), json.loads((out / 'lizard.json').read_text()), json.loads((out / 'imports.json').read_text())


def touched_lizard(per_file, paths):
    rows = [per_file[p] for p in paths if p in per_file]
    return {'files': len(rows), 'nloc': sum(r['nloc'] for r in rows), 'functions': sum(r['functions'] for r in rows),
            'ccn_max': max((r['ccn_max'] for r in rows), default=0), 'high_ccn': sum(r['high_ccn'] for r in rows),
            'long_functions': sum(r['long_functions'] for r in rows),
            'largest_file_nloc': max((r['nloc'] for r in rows), default=0)}


def touched_imports(imports, paths):
    edges = [tuple(e) for e in imports['edges']]
    paths = set(paths)
    fan_in, fan_out = Counter(b for _, b in edges), Counter(a for a, _ in edges)
    group_in = {a for a, b in edges if b in paths and a not in paths}
    group_out = {b for a, b in edges if a in paths and b not in paths}
    cycle_members = {m for c in imports['cycles'] for m in c}
    return {'max_file_fan_in': max((fan_in[p] for p in paths), default=0), 'max_file_fan_out': max((fan_out[p] for p in paths), default=0),
            'group_external_dependents': len(group_in), 'group_external_dependencies': len(group_out),
            'files_in_cycles': len(paths & cycle_members),
            'largest_cycle_touching': max((len(c) for c in imports['cycles'] if paths & set(c)), default=0)}


def analyzer_view(out, paths):
    path = out / 'bottlenecks.json'
    if not path.exists():
        return None
    bottlenecks = json.loads(path.read_text())
    metrics = bottlenecks['dependency_network']['node_metrics']
    ids = ['file:' + p for p in paths if 'file:' + p in metrics]
    keys = ('pagerank', 'betweenness_centrality', 'fan_in', 'fan_out', 'weighted_fan_in', 'weighted_fan_out', 'hop_2_token_cost')
    targets = {c['target'] for c in bottlenecks['candidates']}
    return {'candidates': dict(Counter(c['kind'] for c in bottlenecks['candidates'])),
            'touched_max': {k: max((metrics[i].get(k, 0) for i in ids), default=0) for k in keys},
            'touched_candidates': sum(1 for i in ids if i in targets)}


def delta(before, after):
    if isinstance(before, dict):
        return {k: delta(before.get(k), after.get(k)) for k in sorted(set(before) | set(after or {}))}
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        return {'before': before, 'after': after, 'delta': round(after - before, 6)}
    return {'before': before, 'after': after}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('repo')
    parser.add_argument('after')
    parser.add_argument('--before', default='before')
    args = parser.parse_args()
    b_out, b_sum, b_liz, b_imp = load(args.repo, args.before)
    a_out, a_sum, a_liz, a_imp = load(args.repo, args.after)
    diff = subprocess.run(['git', '-C', str(EVAL / 'repos' / args.repo), 'diff', '--name-only', b_sum['rev'], a_sum['rev']],
                          check=True, capture_output=True, text=True).stdout.split()
    stat = subprocess.run(['git', '-C', str(EVAL / 'repos' / args.repo), 'diff', '--shortstat', b_sum['rev'], a_sum['rev']],
                          check=True, capture_output=True, text=True).stdout.strip()
    result = {'repo': args.repo, 'before': b_sum['rev'], 'after': a_sum['rev'], 'touched_files': diff, 'diffstat': stat,
              'independent': {
                  'lizard_production': delta(b_sum['lizard']['production'], a_sum['lizard']['production']),
                  'lizard_touched': delta(touched_lizard(b_liz, diff), touched_lizard(a_liz, diff)),
                  'imports_global': delta({k: v for k, v in b_sum['imports'].items() if k != 'method'}, {k: v for k, v in a_sum['imports'].items() if k != 'method'}),
                  'imports_touched': delta(touched_imports(b_imp, diff), touched_imports(a_imp, diff))},
              'analyzer': delta(analyzer_view(b_out, diff), analyzer_view(a_out, diff)) if (b_out / 'bottlenecks.json').exists() and (a_out / 'bottlenecks.json').exists() else None}
    path = EVAL / 'results' / args.repo / f'compare-{args.after}.json'
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
