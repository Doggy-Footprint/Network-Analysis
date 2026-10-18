"""Base hashes and byte counts come from tests/delta_evidence/base_manifest.json, produced at the pre-feature commit.
Expected package pairs are rebuilt from the file graph with the Phase 1 reference in tests/structure_support.py.
Time checks are not benchmark-marked so they run in the default selection."""
import copy
import hashlib
import json
import sys
import time

import pytest

from fixtures.registry import fixture_root
from tests.delta_support import (EXAMPLE_PROFILE, FIXTURE_ARGS, cid, cli, cycle, independent_digest, internal_violation,
                                 load_manifest, payload, pdep, ref_delta, run_bottlenecks, wire)
from tests.structure_support import default_weights, ref_framework, ref_language, ref_package_pairs, ref_pairs

MANIFEST = load_manifest()
RUNS = MANIFEST['runs']
RUN_IDS = [f"{r['fixture']}{'-rules' if r['rules'] else ''}" for r in RUNS]
PLAIN = [r for r in RUNS if not r['rules']]
CANON = dict(sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def run_args(entry):
    return entry['args']


@pytest.fixture(scope='module')
def outputs_by_id(tmp_path_factory):
    cache = {}

    def get(entry):
        key = f"{entry['fixture']}{'-rules' if entry['rules'] else ''}"
        if key not in cache:
            directory = tmp_path_factory.mktemp(key)
            assert run_args(entry) == FIXTURE_ARGS[entry['fixture']]
            rules = EXAMPLE_PROFILE if entry['rules'] else None
            run_bottlenecks(fixture_root(entry['fixture']).resolve(), directory, name=entry['fixture'], rules=rules, extra=[])
            cache[key] = (directory / 'b.json').read_bytes()
        return cache[key]
    return get


@pytest.fixture(scope='module')
def arch_of(tmp_path_factory):
    cache = {}

    def get(name):
        if name not in cache:
            import code_analyzer.cli as cli_module
            seen = {}
            original = cli_module.analyze_bottlenecks

            def spy(snapshot, arch, weights, *args, **kwargs):
                seen['arch'] = arch
                return original(snapshot, arch, weights, *args, **kwargs)

            directory = tmp_path_factory.mktemp('inproc-' + name)
            argv = ['code-analyzer', str(fixture_root(name).resolve()), *FIXTURE_ARGS[name], '--granularity', 'file',
                    '-o', str(directory / 'r.html'), '--bottlenecks', str(directory / 'b.json')]
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(cli_module, 'analyze_bottlenecks', spy)
                patch.setattr(sys, 'argv', argv)
                cli_module.main()
            assert seen
            cache[name] = seen['arch']
        return cache[name]
    return get


@pytest.fixture(params=RUNS, ids=RUN_IDS)
def entry(request):
    return request.param


@pytest.fixture(params=PLAIN, ids=[r['fixture'] for r in PLAIN])
def plain_entry(request):
    return request.param


def test_V06_C27_output_minus_added_keys_is_byte_equal_to_base(entry, outputs_by_id):
    data = outputs_by_id(entry)
    obj = json.loads(data)
    del obj['dependency_network']['package_dependencies']
    if entry['rules']:
        del obj['coverage']['architecture_rules']['rules_sha256']
    text = json.dumps(obj, **CANON) + '\n'
    assert len(text.encode('utf-8')) == entry['bottleneck_bytes']
    assert hashlib.sha256(text.encode('utf-8')).hexdigest() == entry['bottleneck_sha256']
    assert obj['schema'] == 'bottlenecks.v8'


def test_V06_F02_without_rules_no_rules_section_is_added(plain_entry, outputs_by_id):
    assert 'architecture_rules' not in json.loads(outputs_by_id(plain_entry))['coverage']


def expected_package_dependencies(arch):
    files = {'language': ref_language(arch)}
    framework = ref_framework(arch)
    if framework is not None:
        files['framework'] = framework
    pairs = ref_pairs(arch, default_weights(), 'all')
    result = {}
    for scheme, assignment in files.items():
        found = ref_package_pairs(pairs, assignment)
        result[scheme] = [{'from_id': p, 'to_id': q, 'tier': record['tier']} for (p, q), record in sorted(found.items())]
    return result


def test_V06_F01_package_dependencies_match_the_file_graph_reference(plain_entry, outputs_by_id, arch_of):
    data = json.loads(outputs_by_id(plain_entry))
    actual = data['dependency_network']['package_dependencies']
    assert set(actual) == set(data['dependency_network']['package_metrics'])
    assert actual == expected_package_dependencies(arch_of(plain_entry['fixture']))
    assert any(actual.values())


def test_V06_F01_pair_counts_agree_with_package_metrics(plain_entry, outputs_by_id):
    network = json.loads(outputs_by_id(plain_entry))['dependency_network']
    for scheme, pairs in network['package_dependencies'].items():
        metrics = network['package_metrics'][scheme]
        assert all(a['from_id'] != a['to_id'] for a in pairs)
        assert sorted((p['from_id'], p['to_id']) for p in pairs) == [(p['from_id'], p['to_id']) for p in pairs]
        assert len({(p['from_id'], p['to_id']) for p in pairs}) == len(pairs)
        for package, record in metrics.items():
            assert record['ce'] == sum(1 for p in pairs if p['from_id'] == package)
            assert record['ca'] == sum(1 for p in pairs if p['to_id'] == package)


def test_V06_F03_rules_run_pairs_equal_plain_pairs_and_digest_is_the_independent_one(outputs_by_id):
    ruled = [r for r in RUNS if r['rules']][0]
    plain = [r for r in PLAIN if r['fixture'] == ruled['fixture']][0]
    with_rules = json.loads(outputs_by_id(ruled))
    assert with_rules['dependency_network']['package_dependencies'] == json.loads(outputs_by_id(plain))['dependency_network']['package_dependencies']
    from analysis.architecture_rules import load_architecture_rules
    expected = independent_digest(load_architecture_rules(EXAMPLE_PROFILE))
    assert with_rules['coverage']['architecture_rules']['rules_sha256'] == expected


def test_V06_F01_symbol_granularity_has_no_package_dependencies(tmp_path):
    done = cli([fixture_root('fastapi-realworld').resolve(), '-l', 'python', '--granularity', 'symbol', '--bottlenecks',
                tmp_path / 'b.json', '-o', tmp_path / 'r.html'])
    assert done.returncode == 0, done.stderr[-1500:]
    text = (tmp_path / 'b.json').read_text(encoding='utf-8')
    assert 'package_dependencies' not in text and 'rules_sha256' not in text


def test_V13_Q04_size_ratio(plain_entry, outputs_by_id):
    ratio = len(outputs_by_id(plain_entry)) / plain_entry['bottleneck_bytes']
    assert 1.0 <= ratio <= 1.03, ratio


def fastest(call, repeats=3):
    best = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = call()
        elapsed = time.perf_counter() - start
        best = elapsed if best is None else min(best, elapsed)
    return best, result


def shrink(data):
    base = copy.deepcopy(data)
    kept = []
    cycles = 0
    for item in base['candidates']:
        if item['kind'] in ('dependency_cycle', 'package_cycle'):
            cycles += 1
            if cycles % 2 == 0:
                continue
            item['structure']['members'] = item['structure']['members'][:-1]
        kept.append(item)
    base['candidates'] = kept
    for scheme, pairs in base['dependency_network']['package_dependencies'].items():
        base['dependency_network']['package_dependencies'][scheme] = pairs[::2]
    for scheme in base['dependency_network']['package_metrics'].values():
        for index, record in enumerate(scheme.values()):
            if isinstance(record['instability'], float) and index % 2:
                record['instability'] = round(1 - record['instability'], 3)
    return base


def test_V12_Q02_compute_delta_on_real_futuramaapi_json(outputs_by_id):
    from bottlenecks.delta import compute_delta
    current = json.loads(outputs_by_id([r for r in PLAIN if r['fixture'] == 'futuramaapi'][0]))
    baseline = shrink(current)
    seconds, result = fastest(lambda: compute_delta(current, baseline))
    assert seconds <= 1.0, seconds
    result = wire(result)
    assert result == wire(ref_delta(current, baseline))
    assert result['counts']['grown_cycles'] + result['counts']['new_cycles'] > 0
    assert result['counts']['new_package_dependencies'] > 0


def test_V12_Q02_identical_real_json_pair(outputs_by_id):
    from bottlenecks.delta import compute_delta
    current = json.loads(outputs_by_id([r for r in PLAIN if r['fixture'] == 'futuramaapi'][0]))
    seconds, result = fastest(lambda: compute_delta(current, copy.deepcopy(current)))
    assert seconds <= 1.0, seconds
    assert wire(result)['counts'] == {'new_cycles': 0, 'grown_cycles': 0, 'new_violations': 0, 'new_package_dependencies': 0,
                                      'instability_changes': 0}


def large_pair():
    def members(prefix, i, count=20):
        return [f'file:{prefix}{i:04d}/m{j:02d}.py' for j in range(count)]
    current_cycles = [cycle(members('c', i)) for i in range(1000)]
    base_cycles = [cycle(members('c', i)) for i in range(500)]
    base_cycles += [cycle(members('c', i)[:-1]) for i in range(500, 750)]
    base_cycles += [cycle(members('old', i)) for i in range(100)]
    current_violations = [internal_violation(f'b:v{i:05d}', f'file:s{i}.py', f'file:t{i}.py') for i in range(20000)]
    base_violations = current_violations[:15000] + [internal_violation(f'b:x{i:04d}', 'file:s.py', 'file:t.py') for i in range(1000)]
    current_pairs = [pdep(f'pkg:{i:05d}', f'pkg:{i + 1:05d}') for i in range(20000)]
    base_pairs = current_pairs[:15000] + [pdep(f'pkg:o{i:04d}', 'pkg:z') for i in range(500)]
    current = payload(candidates=current_cycles + current_violations, package_dependencies={'language': current_pairs})
    baseline = payload(candidates=base_cycles + base_violations, package_dependencies={'language': base_pairs})
    return current, baseline


def test_V12_Q03_compute_delta_on_large_synthetic_input():
    from bottlenecks.delta import compute_delta
    current, baseline = large_pair()
    seconds, result = fastest(lambda: compute_delta(current, baseline), repeats=1)
    assert seconds <= 3.0, seconds
    result = wire(result)
    assert result['counts'] == {'new_cycles': 250, 'grown_cycles': 250, 'new_violations': 5000, 'new_package_dependencies': 5000,
                                'instability_changes': 0}
    assert result['resolved'] == {'cycles': 100, 'violations': 1000, 'package_dependencies': 500}
    assert [i['candidate_id'] for i in result['new_cycles']] == sorted(cid('dependency_cycle', 'file', 'all', [
        f'file:c{i:04d}/m{j:02d}.py' for j in range(20)]) for i in range(750, 1000))
    assert all(len(i['added_members']) == 1 for i in result['grown_cycles'])
