"""Judge a refactoring point against the metrics its finder predicted before implementation."""
import argparse
import json
from pathlib import Path

EVAL = Path(__file__).resolve().parents[2] / 'eval'
# global guard rails: a point that worsens these is not counted as an improvement
GUARDS = [('imports_global', 'cycle_count'), ('imports_global', 'files_in_cycles'), ('imports_global', 'largest_cycle'),
          ('lizard_production', 'high_ccn_functions'), ('lizard_production', 'long_functions'), ('lizard_production', 'ccn_max')]


ALIASES = {'depcruise': 'imports_global', 'imports': 'imports_global', 'depcruise_touched': 'imports_touched',
           'independent_import_graph': 'imports_touched', 'import_graph': 'imports_touched'}


def file_fan(repo, label, path, key):
    edges = json.loads((EVAL / 'results' / repo / label / 'imports.json').read_text())['edges']
    side = 1 if key.endswith('fan_in') else 0
    return sum(1 for e in edges if e[side] == path)


def lookup(compare, metric, repo, pid):
    metric, _, scoped = metric.partition(' (')
    section, _, key = metric.removeprefix('independent.').partition('.')
    section = ALIASES.get(section, section)
    if scoped and key in ('max_file_fan_in', 'max_file_fan_out'):
        name = scoped.rstrip(')')
        path = next((f for f in compare['touched_files'] if f.endswith('/' + name) or f == name), None)
        if path:
            before, after = file_fan(repo, 'before', path, key), file_fan(repo, pid, path, key)
            return {'before': before, 'after': after, 'delta': after - before, 'file': path}
    if section in ('cycle_count', 'files_in_cycles', 'largest_cycle'):
        section, key = 'imports_global', section
    return compare['independent'].get(section, {}).get(key)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('repo')
    parser.add_argument('pid')
    args = parser.parse_args()
    results = EVAL / 'results' / args.repo
    point = next(p for p in json.loads((results / 'points.json').read_text())['points'] if p['id'] == args.pid)
    compare = json.loads((results / f'compare-{args.pid}.json').read_text())
    gate = json.loads((results / 'gates' / f'{args.pid}-eval.json').read_text())
    predictions = []
    for item in point['predicted']:
        value = lookup(compare, item['metric'], args.repo, args.pid)
        moved = value.get('delta') if value else None
        want = item['direction'].lower()
        hit = moved is not None and ((moved < 0) if want.startswith('dec') else (moved > 0) if want.startswith('inc') else moved == 0)
        predictions.append({**item, 'observed': value, 'hit': hit})
    regressions = [f'{s}.{k}: {compare["independent"][s][k]}' for s, k in GUARDS
                   if (compare['independent'][s].get(k) or {}).get('delta', 0) > 0]
    directional = [p for p in predictions if p['hit'] and p['direction'].lower().startswith(('dec', 'inc'))]
    verdict = ('behaviour_broken' if not gate['ok'] else
               'improved' if directional and not regressions else
               'mixed' if directional else 'not_improved')
    result = {'repo': args.repo, 'pid': args.pid, 'title': point['title'], 'gate_ok': gate['ok'], 'gate': {k: gate.get(k) for k in ('passed', 'failed', 'errors', 'expected_passed', 'returncode')},
              'predictions': predictions, 'hit_rate': f"{sum(p['hit'] for p in predictions)}/{len(predictions)}",
              'regressions': regressions, 'diffstat': compare['diffstat'], 'analyzer_view': compare['analyzer'], 'verdict': verdict}
    (results / f'judge-{args.pid}.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ('repo', 'pid', 'verdict', 'gate_ok', 'hit_rate', 'regressions', 'diffstat')}, indent=1))
    for p in predictions:
        print(' ', p['metric'], p['direction'], p.get('expected'), '->', (p['observed'] or {}).get('before'), '→', (p['observed'] or {}).get('after'), 'HIT' if p['hit'] else 'miss')


if __name__ == '__main__':
    main()
