"""Expected hashes come from tests/structure_evidence/base_manifest.json, generated at the pre-feature commit.
Size/time checks are deliberately not benchmark-marked so they run in the default selection."""
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time

import pytest

from analysis.structure import analyze_structure, package_assignments
from fixtures.registry import fixture_root
from tests.structure_support import (BASE_KINDS, FIXTURES, NEW_KINDS, REPO, TIERS, canonical_sha, cycle_id, cycle_target, default_weights,
                                     fedge, load_manifest, of_kind, ref_framework, ref_language, ref_pairs, ref_structure, architecture,
                                     unstable_id)

MANIFEST = load_manifest()
MAIN = 'from code_analyzer.cli import main; main()'


def command_args(name):
    return MANIFEST['commands'][name]


class Run:

    def __init__(self, name, directory):
        self.name, self.directory, self.cache = name, directory, {}

    def output(self, granularity, seed='0'):
        key = (granularity, seed)
        if key not in self.cache:
            target = self.directory / f'{granularity}-{seed}'
            target.mkdir()
            command = [sys.executable, '-c', MAIN, str(fixture_root(self.name).resolve()), *command_args(self.name),
                       '--granularity', granularity, '-o', str(target / 'report.html'), '--bottlenecks', str(target / 'b.json')]
            done = subprocess.run(command, cwd=REPO, env=dict(os.environ, PYTHONHASHSEED=seed), capture_output=True, text=True)
            assert done.returncode == 0, done.stderr[-2000:]
            self.cache[key] = (target / 'b.json').read_bytes()
        return self.cache[key]

    def payload(self, granularity='file'):
        return json.loads(self.output(granularity))

    @property
    def manifest(self):
        return MANIFEST['fixtures'][self.name]


@pytest.fixture(scope='module', params=FIXTURES)
def run(request, tmp_path_factory):
    return Run(request.param, tmp_path_factory.mktemp(request.param))


def capture_pipeline(name, directory):
    import code_analyzer.cli as cli
    seen = {}
    original = cli.analyze_bottlenecks

    def spy(snapshot, arch, weights, *args, **kwargs):
        seen.update(snapshot=snapshot, arch=arch, weights=weights)
        return original(snapshot, arch, weights, *args, **kwargs)

    argv = ['code-analyzer', str(fixture_root(name).resolve()), *command_args(name), '--granularity', 'file',
            '-o', str(directory / 'report.html'), '--bottlenecks', str(directory / 'b.json')]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cli, 'analyze_bottlenecks', spy)
        patch.setattr(sys, 'argv', argv)
        cli.main()
    assert seen, 'the CLI must reach analyze_bottlenecks in file mode'
    return seen


@pytest.fixture(scope='module')
def pipeline(run, tmp_path_factory):
    return capture_pipeline(run.name, tmp_path_factory.mktemp('inproc-' + run.name))


def test_V08_file_mode_keeps_base_parts_and_adds_v8_fields(run):
    payload = run.payload('file')
    manifest = run.manifest['file']
    network = payload['dependency_network']
    assert payload['schema'] == 'bottlenecks.v8' and payload['granularity'] == 'file'
    assert payload['versions']['analysis'] == '4'
    assert canonical_sha(network['rankings']) == manifest['rankings']
    assert canonical_sha(network['rankings_by_category']) == manifest['rankings_by_category']
    assert canonical_sha(network['node_metrics']) == manifest['node_metrics']
    assert canonical_sha(network['candidate_groups']) == manifest['candidate_groups']
    base = [c for c in payload['candidates'] if c['kind'] in BASE_KINDS]
    assert len(base) == manifest['candidate_count']
    assert canonical_sha(base) == manifest['candidates']
    assert network['structure_policy'] == 'structure.v1'
    assert 'language' in network['package_metrics']
    assert {c['kind'] for c in payload['candidates']} <= set(BASE_KINDS) | set(NEW_KINDS) | {'untested_hub', 'isolated_node'}


def test_V08_candidates_are_sorted_by_kind_then_id(run):
    keys = [(c['kind'], c['id']) for c in run.payload('file')['candidates']]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)


def test_V08_symbol_mode_is_byte_identical_to_base(run):
    data = run.output('symbol')
    manifest = run.manifest['symbol']
    assert hashlib.sha256(data).hexdigest() == manifest['sha256']
    assert len(data) == manifest['bytes']
    assert json.loads(data)['schema'] == manifest['schema'] == 'bottlenecks.v6'


def test_V08_new_kinds_exist_where_the_input_implies_them(run, pipeline):
    ref = ref_structure(pipeline['arch'], pipeline['weights'])
    payload = run.payload('file')
    expected_dep = sum(len(groups) for groups in ref['file_cycles'].values())
    expected_pkg = sum(len(groups) for groups in ref['package_cycles'].values())
    assert len(of_kind(payload['candidates'], 'dependency_cycle')) == expected_dep
    assert len(of_kind(payload['candidates'], 'package_cycle')) == expected_pkg
    assert len(of_kind(payload['candidates'], 'unstable_dependency')) == sum(len(v) for v in ref['unstable'].values())


def test_V08_futuramaapi_measured_cycle_sizes(tmp_path_factory):
    run = Run('futuramaapi', tmp_path_factory.mktemp('futurama-sizes'))
    cycles = of_kind(run.payload('file')['candidates'], 'dependency_cycle')
    sizes = {tier: sorted((c['metrics']['member_count'] for c in cycles if c['structure']['tier'] == tier), reverse=True) for tier in TIERS}
    assert sizes['all'][0] == 106            # spec ledger attempt 0: all-tier max SCC
    assert sizes['resolved'][0] == 6 and sizes['certain'][0] == 6
    assert all(sizes[tier] for tier in TIERS)


def test_V08_structure_facts_match_independent_reference(run, pipeline):
    arch, weights = pipeline['arch'], pipeline['weights']
    ref = ref_structure(arch, weights)
    payload = run.payload('file')
    candidates = payload['candidates']
    found = {(c['structure']['tier'], tuple(c['structure']['members'])): c for c in of_kind(candidates, 'dependency_cycle')}
    assert set(found) == {(t, tuple(m)) for t in TIERS for m in ref['file_cycles'][t]}
    for (tier, members), item in found.items():
        assert item['id'] == cycle_id('file', tier, members) and item['target'] == cycle_target('file', tier, members)
        assert item['metrics']['member_count'] == len(members)
        internal = {pair: rec for pair, rec in ref_pairs(arch, weights, tier).items() if pair[0] in members and pair[1] in members}
        assert [(r['from_id'], r['to_id']) for r in item['evidence']] == sorted(internal)
        for record in item['evidence']:
            expected = internal[(record['from_id'], record['to_id'])]
            assert record['relations'] == expected['relations'] and record['evidence_count'] == expected['evidence_count']
            assert record['detail_edge_indices'] == expected['detail_edge_indices'] and record['tier'] == expected['tier']
            assert record['max_weight'] == pytest.approx(expected['max_weight'])
        assert item['metrics']['internal_pair_count'] == len(internal)
        assert item['metrics']['internal_evidence_count'] == sum(r['evidence_count'] for r in internal.values())
        assert item['metrics']['min_pair_weight'] == pytest.approx(min(r['max_weight'] for r in internal.values()))
        cuts = item['structure']['cut_candidates']
        order = sorted(internal, key=lambda pair: (internal[pair]['max_weight'], internal[pair]['evidence_count'], pair[0], pair[1]))
        assert [(c['from_id'], c['to_id']) for c in cuts] == order[:10]
        parent = item['structure']['parent_id']
        looser = TIERS[TIERS.index(tier) + 1] if tier != 'all' else None
        if looser is None:
            assert parent is None
        else:
            holder = next(m for m in ref['file_cycles'][looser] if set(members) <= set(m))
            assert parent == cycle_id('file', looser, holder)
    package_found = {(c['structure']['scheme'], c['structure']['tier'], tuple(c['structure']['members'])) for c in of_kind(candidates, 'package_cycle')}
    assert package_found == {(s, t, tuple(m)) for (s, t), groups in ref['package_cycles'].items() for m in groups}
    unstable_found = {(c['structure']['scheme'], c['structure']['from_package'], c['structure']['to_package']): c for c in of_kind(candidates, 'unstable_dependency')}
    assert set(unstable_found) == {(s, p, q) for s, pairs in ref['unstable'].items() for p, q in pairs}
    for (scheme, p, q), item in unstable_found.items():
        assert item['id'] == unstable_id(scheme, p, q) and item['target'] == p
        row_p, row_q = ref['metrics'][scheme][p], ref['metrics'][scheme][q]
        assert item['metrics']['instability_from'] == pytest.approx(row_p['instability'])
        assert item['metrics']['instability_to'] == pytest.approx(row_q['instability'])
        assert item['metrics']['instability_delta'] == pytest.approx(row_q['instability'] - row_p['instability'])
    metrics = payload['dependency_network']['package_metrics']
    assert set(metrics) == set(ref['schemes'])
    for scheme, rows in ref['metrics'].items():
        assert set(metrics[scheme]) == set(rows)
        for package, row in rows.items():
            assert metrics[scheme][package] == pytest.approx(row), (scheme, package)


def test_V08_coverage_structure_matches_f13_from_reference(run, pipeline):
    arch = pipeline['arch']
    files = sorted(n.id for n in arch.nodes if not (n.metadata or {}).get('boundary'))
    ref = {'language': ref_language(arch)}
    if ref_framework(arch) is not None:
        ref['framework'] = ref_framework(arch)
    schemes = {}
    for scheme, assignment in ref.items():
        assigned = [f for f in files if assignment.get(f)]
        schemes[scheme] = {'assigned_file_count': len(assigned), 'unassigned_file_count': len(files) - len(assigned),
                           'unassigned_files': [f for f in files if not assignment.get(f)], 'shared_file_count': sum(len(assignment[f]) > 1 for f in assigned),
                           'shared_files': [f for f in assigned if len(assignment[f]) > 1]}
    expected = {'policy': 'structure.v1', 'schemes': schemes}
    assert run.payload('file')['coverage']['structure'] == expected
    assert analyze_structure(arch, pipeline['weights']).coverage == {'structure': expected}


def test_V08_C24_determinism_across_hash_seeds(tmp_path_factory):
    run = Run('futuramaapi', tmp_path_factory.mktemp('determinism'))
    first = run.output('file', seed='1')
    assert run.output('file', seed='2') == first
    assert run.output('file', seed='0') == first
    assert len(first) > 0


def test_V04_fixture_language_packages_match_reference(run, pipeline):
    arch = pipeline['arch']
    actual = package_assignments(arch)
    assert actual['language'] == ref_language(arch)
    files = {n.id for n in arch.nodes if not (n.metadata or {}).get('boundary')}
    assert set(actual['language']) == files and all(len(v) == 1 for v in actual['language'].values())
    prefixes = {v[0].split(':')[1] for v in actual['language'].values()}
    expected = {'futuramaapi': {'python', 'dir'}, 'fastapi-realworld': {'python', 'dir'},
                'android-nowinandroid': {'kotlin', 'dir'}, 'typescript-nestjs-realworld': {'dir'}}[run.name]
    assert prefixes >= expected - {'dir'} and prefixes <= expected | {'dir'}


def test_V05_fixture_framework_scheme_only_for_nestjs(run, pipeline):
    arch = pipeline['arch']
    assigned = package_assignments(arch)
    if run.name != 'typescript-nestjs-realworld':
        assert 'framework' not in assigned
        return
    expected = ref_framework(arch)
    modules = [n for n in arch.details['nodes'] if n['provenance'] == 'nestjs' and n['kind'] == 'module']
    assert len(modules) >= 2
    assert {f: v for f, v in assigned['framework'].items() if v} == expected
    assert {p for v in expected.values() for p in v} == {'pkg:nestjs:' + m['id'][len('nestjs:module:'):] for m in modules}
    result = analyze_structure(arch, pipeline['weights'])
    files = {n.id for n in arch.nodes if not (n.metadata or {}).get('boundary')}
    schemes = result.coverage['structure']['schemes']['framework']
    assert schemes['assigned_file_count'] == len(expected)
    assert schemes['unassigned_files'] == sorted(files - set(expected))
    assert schemes['shared_files'] == sorted(f for f, v in expected.items() if len(v) > 1)


def test_V08_analyze_structure_is_repeatable_on_real_input(pipeline):
    first = analyze_structure(pipeline['arch'], pipeline['weights'])
    second = analyze_structure(pipeline['arch'], pipeline['weights'])
    assert json.dumps([first.candidates, first.package_metrics, first.coverage], sort_keys=True) == \
        json.dumps([second.candidates, second.package_metrics, second.coverage], sort_keys=True)


SIZE_LIMIT = 1.25
TIME_LIMIT = 1.0
CHAIN_LIMIT = 5.0


def test_V11_size_ratio_per_fixture(run):
    payload = run.payload('file')
    payload['dependency_network'].pop('package_dependencies', None)
    size = len(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')) + 1
    ratio = size / run.manifest['file']['bytes']
    assert ratio <= SIZE_LIMIT, f'{run.name}: v8 is {ratio:.3f}x the base v7 size'
    assert ratio >= 1.0 - 0.05, 'v8 only adds fields; a large shrink means base parts were lost'


def test_V11_analyze_structure_median_time_per_fixture(run, pipeline):
    samples = []
    for _ in range(3):
        started = time.perf_counter()
        analyze_structure(pipeline['arch'], pipeline['weights'])
        samples.append(time.perf_counter() - started)
    assert statistics.median(samples) <= TIME_LIMIT, f'{run.name}: samples {samples}'


def test_V11_chain_of_20000_files_time():
    count = 20000
    paths = [f'f{i:05}.py' for i in range(count)]
    arch = architecture(paths, [fedge(paths[i], paths[(i + 1) % count], indices=[i]) for i in range(count)])
    started = time.perf_counter()
    result = analyze_structure(arch, default_weights())
    elapsed = time.perf_counter() - started
    assert len(of_kind(result.candidates, 'dependency_cycle')) == 3
    assert elapsed <= CHAIN_LIMIT, f'chain took {elapsed:.2f}s'
