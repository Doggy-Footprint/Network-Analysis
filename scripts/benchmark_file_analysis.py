import argparse
import copy
import hashlib
import json
import math
import os
import pickle
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STAGES = ('snapshot', 'extraction', 'integration', 'conversion', 'metrics_candidates', 'output')


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def raw_relations(payload):
    result = copy.deepcopy({key: payload[key] for key in ('nodes', 'edges')})
    for node in result['nodes']:
        node.get('metadata', {}).pop('analysis', None)
    return result


def digest(snapshot):
    return hashlib.sha256(json.dumps(list(snapshot.contents), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def worker(args):
    import code_analyzer.cli as cli
    from renderers.html import HTMLRenderer
    from analysis import GraphAnalyzer
    from language_analyzers.core.serialization import architecture_to_dict
    directory = Path(args.evidence_dir)
    frozen = directory / 'baseline-snapshot.pickle'
    observed = {'pid': os.getpid(), 'mode': args.mode, 'spec_version': 2 if args.mode=='baseline' else 2}
    stages = dict.fromkeys(STAGES, 0.0)
    first = [None]
    raw = [None]
    original_render = HTMLRenderer.render
    overhead = [0.0]
    stack = []

    def timed_call(stage, function, *positional, **keywords):
        start = time.perf_counter()
        frame = [start, 0.0, overhead[0]]
        stack.append(frame)
        try:
            return function(*positional, **keywords)
        finally:
            elapsed = time.perf_counter() - start
            stack.pop()
            stages[stage] += elapsed - frame[1] - (overhead[0] - frame[2])
            if stack:
                stack[-1][1] += elapsed - (overhead[0] - frame[2])

    original_metrics = GraphAnalyzer.analyze
    def metrics(self, *positional, **keywords):
        return timed_call('metrics_candidates', original_metrics, self, *positional, **keywords)
    GraphAnalyzer.analyze = metrics

    def render(self, architecture, *positional, **keywords):
        start = time.perf_counter()
        raw[0] = raw_relations(architecture_to_dict(architecture))
        overhead[0] += time.perf_counter() - start
        result = timed_call('output', original_render, self, architecture, *positional, **keywords)
        observed['end'] = time.perf_counter()
        return result
    HTMLRenderer.render = render

    for name, function in list(vars(cli).items()):
        if not callable(function) or isinstance(function, type):
            continue
        if name == 'build_snapshot':
            def snapshot_wrapper(*positional, _function=function, **keywords):
                first[0] = time.perf_counter()
                actual = timed_call('snapshot', _function, *positional, **keywords)
                start = time.perf_counter()
                observed['snapshot_hash'] = digest(actual)
                if args.mode == 'baseline':
                    if frozen.exists():
                        raise ValueError('Refusing to replace immutable baseline snapshot')
                    frozen.write_bytes(pickle.dumps(actual))
                    dump(directory / 'baseline-snapshot-contents.json', list(actual.contents))
                else:
                    saved = pickle.loads(frozen.read_bytes())
                    if digest(saved) != digest(actual):
                        raise ValueError('Snapshot hash mismatch')
                    actual = saved
                overhead[0] += time.perf_counter() - start
                return actual
            setattr(cli, name, snapshot_wrapper)
        elif name in ('_run_analyzer', 'analyze_bottlenecks', 'to_file_architecture', 'merge_architectures'):
            stage = {'_run_analyzer': 'extraction', 'analyze_bottlenecks': 'metrics_candidates', 'to_file_architecture': 'conversion', 'merge_architectures': 'integration'}[name]
            def timed(*positional, _function=function, _stage=stage, **keywords):
                return timed_call(_stage, _function, *positional, **keywords)
            setattr(cli, name, timed)
    output = directory / ('baseline.html' if args.mode == 'baseline' else f'{args.mode}.html')
    sys.argv = ['code-analyzer', args.project, '-f', 'android', '-o', str(output)]
    if args.mode != 'baseline':
        sys.argv += ['--granularity', 'symbol' if args.mode == 'optimized-symbol' else 'file']
    cli.main()
    if first[0] is None or 'end' not in observed or raw[0] is None:
        raise AssertionError('Missing public snapshot/render observations')
    total = observed['end'] - first[0] - overhead[0]
    stages['extraction'] += total - sum(stages.values())
    if stages['extraction'] < 0:
        raise AssertionError('Overlapping benchmark stages')
    observed.update(stages=stages, total_seconds=total, observer_overhead_seconds=overhead[0], html=str(output))
    dump(directory / f'{args.mode}-timing.json', observed)
    if args.mode in ('baseline', 'optimized-symbol'):
        dump(directory / f'{args.mode}-relations.json', raw[0])
    if args.mode == 'baseline':
        dump(directory / 'baseline-manifest.json', {'project': str(Path(args.project).resolve()), 'snapshot_hash': observed['snapshot_hash'], 'spec_version': 1, 'snapshot': str(frozen), 'measurement': 'snapshot start through HTML save; preparation excluded'})


def invoke(args, mode, timeout):
    command = [sys.executable, str(Path(__file__).resolve()), '--worker', mode, '--project', args.project, '--evidence-dir', args.evidence_dir]
    subprocess.run(command, check=True, timeout=timeout, cwd=ROOT)


def verify_artifacts(directory):
    dump(directory/'benchmark.json',{'spec_version':2,'passed':False,'status':'verification in progress'})
    from tests.file_analysis_support import characterization, CHARACTERIZATION_FILES
    from tests.candidate_policy_transition_support import assert_candidate_policy_transition
    frozen = pickle.loads((directory / 'baseline-snapshot.pickle').read_bytes())
    if json.loads((directory / 'baseline-small-inputs.json').read_text()) != CHARACTERIZATION_FILES:
        raise AssertionError('Small characterization inputs changed')
    small = characterization()
    dump(directory / 'optimized-small-relations.json', small)
    small_baseline = json.loads((directory / 'baseline-small-relations.json').read_text())
    if set(small) != set(small_baseline):
        raise AssertionError('Small characterization analyzer set changed')
    for flavor in small_baseline:
        assert_candidate_policy_transition(small_baseline[flavor], small[flavor], CHARACTERIZATION_FILES)
    baseline = json.loads((directory / 'baseline-relations.json').read_text())
    optimized = json.loads((directory / 'optimized-symbol-relations.json').read_text())
    equal = baseline == optimized
    assert_candidate_policy_transition(baseline, optimized, frozen.contents)
    dump(directory / 'symbol-equivalence.json', {'equal': equal, 'candidate_policy_transition': True, 'comparison': 'approved-candidate-policy-transition', 'excluded_fields': ['nodes[*].metadata.analysis'], 'spec_version': 2})
    manifest = json.loads((directory / 'baseline-manifest.json').read_text())
    if digest(frozen)!=manifest['snapshot_hash']:
        raise AssertionError('Immutable baseline snapshot hash mismatch')
    optimized_timing=json.loads((directory/'optimized-symbol-timing.json').read_text())
    if optimized_timing['snapshot_hash']!=manifest['snapshot_hash']:
        raise AssertionError('Optimized symbol snapshot hash mismatch')
    timings = [json.loads((directory / f'file-run{i}-timing.json').read_text()) for i in range(1, 4)]
    if len({timing['pid'] for timing in timings})!=3:
        raise AssertionError('File measurements are not three independent processes')
    for index,timing in enumerate(timings,1):
        if timing['mode']!=f'file-run{index}':
            raise AssertionError('Wrong file measurement mode')
        if timing['snapshot_hash'] != manifest['snapshot_hash']:
            raise AssertionError('Snapshot hash mismatch')
        if set(timing['stages']) != set(STAGES) or any(not math.isfinite(value) or value < 0 for value in timing['stages'].values()):
            raise AssertionError('Missing or invalid six-stage timing')
        total=timing['total_seconds']
        if not math.isfinite(total) or total<0 or total>600:
            raise AssertionError('Invalid or timed-out file total')
        if not math.isclose(sum(timing['stages'].values()),total,abs_tol=1e-9,rel_tol=1e-8):
            raise AssertionError('Six-stage timing total mismatch')
    file_values = [row['total_seconds'] for row in timings]
    median = statistics.median(file_values)
    if median > 180:
        raise AssertionError(f'Tag-Manager median {median} exceeds 180 seconds')
    browser = json.loads((directory / 'browser.json').read_text())
    for dataset in ('synthetic', 'Tag-Manager'):
        result = browser.get('datasets', {}).get(dataset)
        if not result or result.get('fresh_context_count')!=5:
            raise AssertionError('Missing mandatory browser dataset: ' + dataset)
        for metric, threshold in {'summary_ms': 5000, 'filter_page_ms': 300, 'detail_graph_ms': 1000}.items():
            browser_values = result.get('raw_ms', {}).get(metric, [])
            if len(browser_values) != 5 or any(not math.isfinite(value) or value<0 for value in browser_values) or statistics.median(browser_values) > threshold:
                raise AssertionError('Failed browser threshold or fresh-context count: ' + dataset + '/' + metric)
    dump(directory / 'benchmark.json', {'spec_version': 2, 'runs': timings, 'raw_seconds': file_values, 'median_seconds': median, 'threshold_seconds': 180, 'passed': True})


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--baseline', action='store_true')
    modes.add_argument('--verify', action='store_true')
    modes.add_argument('--worker', dest='mode')
    parser.add_argument('--project', required=True)
    parser.add_argument('--evidence-dir', required=True)
    args = parser.parse_args()
    directory = Path(args.evidence_dir)
    directory.mkdir(parents=True, exist_ok=True)
    if args.mode:
        worker(args)
    elif args.baseline:
        if any(directory.glob('baseline*')):
            raise ValueError('Refusing to replace immutable baseline artifacts')
        from tests.file_analysis_support import characterization, CHARACTERIZATION_FILES
        dump(directory / 'baseline-small-inputs.json', CHARACTERIZATION_FILES)
        dump(directory / 'baseline-small-relations.json', characterization())
        invoke(args, 'baseline', 3600)
    else:
        dump(directory/'benchmark.json',{'spec_version':2,'passed':False,'status':'verification in progress'})
        try:
            invoke(args, 'optimized-symbol', 3600)
            for index in range(1, 4):
                invoke(args, f'file-run{index}', 600)
            from playwright.sync_api import sync_playwright
            from tests.file_analysis_browser_support import measure_all
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel='chrome')
                try:
                    measure_all(browser, directory / 'file-run1.html', directory)
                finally:
                    browser.close()
            verify_artifacts(directory)
        except Exception as exc:
            dump(directory/'benchmark.json',{'spec_version':2,'passed':False,'error_type':type(exc).__name__,'cause':str(exc)})
            raise


if __name__ == '__main__':
    main()
