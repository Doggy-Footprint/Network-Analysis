"""R1 re-measure driver (spec 73bd5aa508fa3e88 F10). `harness.py rescore` reuses each run's saved delta.json, so this reruns the
analyzer on every cached task: fresh worktree at `base`, `git apply --index diff.patch`, analyze against the regenerated
base/bottlenecks.json, then the harness's own assess / assess_match. Validity (judge, gate) is kept from the original run.
usage: python r1_reanalyze.py <repo> [--only-negative] [--only ID,ID] [--match] [--workers N]"""
import argparse
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('harness', ROOT / 'scripts/eval/inject/harness.py')
h = importlib.util.module_from_spec(spec)
sys.modules['harness'] = h
spec.loader.exec_module(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('repo')
    ap.add_argument('--only-negative', action='store_true')
    ap.add_argument('--match', action='store_true')
    ap.add_argument('--only', default='')
    ap.add_argument('--workers', type=int, default=4)
    args = ap.parse_args()
    catalog = {t['id']: t for t in h.CATALOG['types']}
    texts = h.type_text()
    p = h.paths(args.repo)

    def one(path):
        result = json.loads(path.read_text())
        out, task = path.parent, result['task']
        if result.get('error') or 'analyzer' not in result:
            return task['id'], 'skipped'
        if (args.only_negative and task['method'] != 'negative') or (args.only and task['id'] not in args.only.split(',')):
            return task['id'], 'not_selected'
        worktree = h.WORK / args.repo / 'wt' / ('r1-' + task['id'])
        if worktree.exists():
            h.run(['git', 'worktree', 'remove', '--force', str(worktree)], cwd=p['clone'])
        h.run(['git', 'worktree', 'add', '-q', '--detach', str(worktree), 'base'], cwd=p['clone'], check=True)
        try:
            diff = (out / 'diff.patch').read_text()
            if diff:
                h.run(['git', 'apply', '--index', str(out / 'diff.patch')], cwd=worktree, check=True)
            h.wait_memory(args.repo, h.LIGHT_LEVEL, 'analyze')
            result['analyzer'] = h.analyze(args.repo, worktree, out, p['base'] / 'bottlenecks.json')
            report = json.loads((out / 'bottlenecks.json').read_text()) if result['analyzer']['returncode'] == 0 else {}
            (out / 'delta.json').write_text(json.dumps(report.get('delta') or {}, indent=1))
            h.assess(args.repo, out, worktree, result['touched'], diff, result)
            if args.match:
                h.assess_match(task, out, diff, result, catalog, texts)
        finally:
            h.run(['git', 'worktree', 'remove', '--force', str(worktree)], cwd=p['clone'])
        result['infra_failed'] = h.infra_failed(result)
        result['r1'] = {'renames': (json.loads((out / 'delta.json').read_text()).get('renames') or {}).get('status')}
        path.write_text(json.dumps(result, indent=1))
        return task['id'], result['analyzer']['returncode'], result['analyzer'].get('caught')

    with ThreadPoolExecutor(args.workers) as pool:
        for row in pool.map(one, sorted(p['runs'].glob('*/result.json'))):
            if row[1] != 'not_selected':
                print(json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
