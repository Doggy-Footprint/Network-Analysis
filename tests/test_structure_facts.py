import ast
import dataclasses
import json
import random
import sys
from pathlib import Path

import pytest

from analysis.edge_weights import EdgeWeights
from analysis.structure import (STRUCTURE_POLICY, TIERS, StructureResult, analyze_structure, edge_tier,
                                strongly_connected_components)
from tests.structure_support import (AMBIGUOUS, DR, EXACT, FI, REPO, SC, SI, UNIQUE, UNRESOLVED, architecture, cycle_id,
                                     cycle_target, cycles_by_key, cycle_view, default_weights, fedge, fid, of_kind,
                                     reference_sccs)


def run(paths, edges, **kwargs):
    return analyze_structure(architecture(paths, edges, **kwargs), default_weights())


def deps(result):
    return cycles_by_key(result.candidates)


def view(result, kind='dependency_cycle'):
    return cycle_view(result.candidates, kind)


def key(tier, *paths, scheme='file'):
    return (scheme, tier, tuple(sorted(fid(p) for p in paths)))


def test_V01_policy_constants():
    assert STRUCTURE_POLICY == 'structure.v2'
    assert TIERS == ('certain', 'resolved', 'all')


EDGE_TIER_TABLE = {
    # (confidence, resolution) -> tier, written out from the Signature text (not computed)
    (SC, EXACT): 'certain', (SC, UNIQUE): 'resolved', (SC, AMBIGUOUS): 'all', (SC, UNRESOLVED): 'all',
    (SI, EXACT): 'resolved', (SI, UNIQUE): 'resolved', (SI, AMBIGUOUS): 'all', (SI, UNRESOLVED): 'all',
    (FI, EXACT): 'resolved', (FI, UNIQUE): 'resolved', (FI, AMBIGUOUS): 'all', (FI, UNRESOLVED): 'all',
    (DR, EXACT): 'resolved', (DR, UNIQUE): 'resolved', (DR, AMBIGUOUS): 'all', (DR, UNRESOLVED): 'all',
}


@pytest.mark.parametrize('confidence,resolution', sorted(EDGE_TIER_TABLE))
def test_V01_edge_tier_partitions(confidence, resolution):
    assert edge_tier(fedge('a.py', 'b.py', confidence=confidence, resolution=resolution)) == EDGE_TIER_TABLE[(confidence, resolution)]


def test_V01_edge_tier_accepts_enum_members():
    from language_analyzers.core.graph_models import Confidence, Resolution
    assert edge_tier(fedge('a.py', 'b.py', confidence=Confidence.STATIC_CERTAIN, resolution=Resolution.EXACT)) == 'certain'
    assert edge_tier(fedge('a.py', 'b.py', confidence=Confidence.DYNAMIC_REQUIRED, resolution=Resolution.EXACT)) == 'resolved'
    assert edge_tier(fedge('a.py', 'b.py', confidence=Confidence.STATIC_CERTAIN, resolution=Resolution.UNRESOLVED)) == 'all'


def test_V01_C03_tests_relation_never_closes_a_cycle():
    result = run(['a.py', 'b.py'], [fedge('a.py', 'b.py', 'TESTS'), fedge('b.py', 'a.py', 'IMPORTS')])
    assert view(result) == []
    assert result.candidates == () or not of_kind(result.candidates, 'dependency_cycle')


def test_V01_C04_boundary_endpoint_never_closes_a_cycle():
    edges = [fedge('a.py', 'ext:lib'), fedge('ext:lib', 'a.py'), fedge('b.py', 'c.py')]
    result = run(['a.py', 'b.py', 'c.py'], edges, boundary=['ext:lib'])
    assert view(result) == []


def test_V01_C04_boundary_free_cycle_beside_boundary_edges_is_kept():
    edges = [fedge('a.py', 'b.py'), fedge('b.py', 'a.py'), fedge('a.py', 'ext:lib'), fedge('ext:lib', 'c.py'),
             fedge('c.py', 'a.py')]
    result = run(['a.py', 'b.py', 'c.py'], edges, boundary=['ext:lib'])
    assert {k for k in deps(result)} == {key(t, 'a.py', 'b.py') for t in TIERS}


def pair_scenario():
    """A<->B with two relations on A->B, C joined only through ambiguous edges; a TESTS edge and boundary edges are noise."""
    edges = [
        fedge('a.py', 'b.py', 'IMPORTS', SC, EXACT, share=1, indices=[0, 1], evidence=2),
        fedge('a.py', 'b.py', 'CALLS', SI, AMBIGUOUS, share=.5, indices=[1, 2, 3], evidence=3),
        fedge('b.py', 'a.py', 'IMPORTS', SC, EXACT, indices=[4], evidence=1),
        fedge('c.py', 'a.py', 'CALLS', SI, AMBIGUOUS, share=.5, indices=[5], evidence=1),
        fedge('a.py', 'c.py', 'CALLS', SI, AMBIGUOUS, share=.25, indices=[6], evidence=1),
        fedge('a.py', 'b.py', 'TESTS', SC, EXACT, indices=[7], evidence=1),
        fedge('a.py', 'ext:lib', 'IMPORTS', SC, EXACT, indices=[8], evidence=1),
        fedge('ext:lib', 'b.py', 'IMPORTS', SC, EXACT, indices=[9], evidence=1),
    ]
    return run(['a.py', 'b.py', 'c.py'], edges, boundary=['ext:lib'])


def test_V01_C07_pair_aggregation_in_all_tier():
    candidate = deps(pair_scenario())[key('all', 'a.py', 'b.py', 'c.py')]
    records = [{k: r[k] for k in ('from_id', 'to_id', 'relations', 'evidence_count', 'detail_edge_indices', 'tier')} for r in candidate['evidence']]
    assert records == [
        {'from_id': fid('a.py'), 'to_id': fid('b.py'), 'relations': ['CALLS', 'IMPORTS'], 'evidence_count': 5, 'detail_edge_indices': [0, 1, 2, 3], 'tier': 'certain'},
        {'from_id': fid('a.py'), 'to_id': fid('c.py'), 'relations': ['CALLS'], 'evidence_count': 1, 'detail_edge_indices': [6], 'tier': 'all'},
        {'from_id': fid('b.py'), 'to_id': fid('a.py'), 'relations': ['IMPORTS'], 'evidence_count': 1, 'detail_edge_indices': [4], 'tier': 'certain'},
        {'from_id': fid('c.py'), 'to_id': fid('a.py'), 'relations': ['CALLS'], 'evidence_count': 1, 'detail_edge_indices': [5], 'tier': 'all'},
    ]
    # max(1.0, 0.3 * 0.5) = 1.0 for A->B; share multiplies the weight: 0.3 * 0.5, 0.3 * 0.25; absent share counts as 1
    assert [r['max_weight'] for r in candidate['evidence']] == pytest.approx([1.0, 0.075, 1.0, 0.15])
    assert candidate['metrics']['internal_evidence_count'] == 8
    assert candidate['metrics']['min_pair_weight'] == pytest.approx(0.075)


@pytest.mark.parametrize('tier', ['certain', 'resolved'])
def test_V01_pairs_are_reaggregated_from_stricter_edges_only(tier):
    candidate = deps(pair_scenario())[key(tier, 'a.py', 'b.py')]
    records = {(r['from_id'], r['to_id']): r for r in candidate['evidence']}
    forward = records[(fid('a.py'), fid('b.py'))]
    assert forward['relations'] == ['IMPORTS']
    assert forward['evidence_count'] == 2
    assert forward['detail_edge_indices'] == [0, 1]
    assert forward['max_weight'] == pytest.approx(1.0)
    assert forward['tier'] == 'certain'
    assert candidate['metrics'] == {'member_count': 2, 'internal_pair_count': 2, 'internal_evidence_count': 3, 'min_pair_weight': pytest.approx(1.0)}


def test_V01_share_weight_defaults_and_multiplies():
    edges = [fedge('a.py', 'b.py', 'CALLS', SI, UNIQUE, share=.5, indices=[0]), fedge('b.py', 'a.py', 'CALLS', SI, UNIQUE, indices=[1])]
    candidate = deps(run(['a.py', 'b.py'], edges))[key('all', 'a.py', 'b.py')]
    # static_inferred 0.3, unique_name 1.0 -> 0.3; times share 0.5 and times the absent share (1)
    assert [r['max_weight'] for r in candidate['evidence']] == pytest.approx([0.15, 0.3])
    assert candidate['evidence'][0]['tier'] == 'resolved'


def test_V01_tier_of_pair_is_strictest_edge_tier():
    edges = [fedge('a.py', 'b.py', 'CALLS', SI, UNRESOLVED), fedge('a.py', 'b.py', 'IMPORTS', SC, UNIQUE),
             fedge('b.py', 'a.py', 'IMPORTS', DR, EXACT)]
    candidate = deps(run(['a.py', 'b.py'], edges))[key('all', 'a.py', 'b.py')]
    assert [r['tier'] for r in candidate['evidence']] == ['resolved', 'resolved']


def sccs(nodes, adjacency):
    return strongly_connected_components(nodes, adjacency)


def test_V02_fixed_two_cycle():
    assert sccs(['b', 'a', 'c'], {'a': ['b'], 'b': ['a'], 'c': []}) == [['a', 'b']]


def test_V02_fixed_nested_cycles_and_bridge():
    adjacency = {'a': ['b'], 'b': ['c', 'a'], 'c': ['a', 'd'], 'd': ['e'], 'e': ['f'], 'f': ['d'], 'g': ['a']}
    assert sccs('abcdefg', adjacency) == [['a', 'b', 'c'], ['d', 'e', 'f']]


def test_V02_fixed_dag():
    assert sccs('abcd', {'a': ['b', 'c'], 'b': ['d'], 'c': ['d']}) == []


def test_V02_fixed_selfloop_and_disjoint():
    adjacency = {'s': ['s'], 'x': ['y'], 'y': ['x'], 'p': ['q'], 'q': ['p', 'q'], 'iso': []}
    assert sccs(['iso', 's', 'y', 'x', 'q', 'p'], adjacency) == [['p', 'q'], ['x', 'y']]


def test_V02_missing_adjacency_keys_and_generator_input():
    assert sccs((n for n in 'ab'), {'a': iter(['b']), 'b': ['a']}) == [['a', 'b']]
    assert sccs(['a', 'b'], {}) == []


def random_graph(seed):
    rng = random.Random(seed)
    count = rng.randint(1, 60)
    density = rng.uniform(0.02, 0.3)
    nodes = [f'n{i:02}' for i in range(count)]
    adjacency = {n: [m for m in nodes if rng.random() < density] for n in nodes}
    return nodes, adjacency


@pytest.mark.parametrize('seed', range(50))
def test_V02_random_graphs_match_mutual_reachability_oracle(seed):
    nodes, adjacency = random_graph(seed)
    expected = reference_sccs(nodes, adjacency)
    actual = sccs(nodes, adjacency)
    assert actual == expected
    assert all(group == sorted(group) for group in actual)
    assert [g[0] for g in actual] == sorted(g[0] for g in actual)
    shuffled = list(nodes)
    random.Random(seed + 1000).shuffle(shuffled)
    reordered = {n: random.Random(seed).sample(adjacency[n], len(adjacency[n])) for n in reversed(shuffled)}
    assert sccs(shuffled, reordered) == expected


def test_V02_oracle_sanity_has_nontrivial_cases():
    sizes = [len(group) for seed in range(50) for group in reference_sccs(*random_graph(seed))]
    assert max(sizes) >= 5 and len(sizes) >= 20


def test_V02_chain_20000_cycle_has_no_recursion_error():
    names = [f'n{i:05}' for i in range(20000)]
    adjacency = {names[i]: [names[(i + 1) % 20000]] for i in range(20000)}
    assert sys.getrecursionlimit() < 20000
    assert sccs(names, adjacency) == [names]


def test_V02_chain_20000_acyclic():
    names = [f'n{i:05}' for i in range(20000)]
    assert sccs(names, {names[i]: [names[i + 1]] for i in range(19999)}) == []


def cyc_pair(ab, ba):
    return run(['a.py', 'b.py'], [fedge('a.py', 'b.py', confidence=ab[0], resolution=ab[1], indices=[0]),
                                  fedge('b.py', 'a.py', confidence=ba[0], resolution=ba[1], indices=[1])])


@pytest.mark.parametrize('name,ab,ba,tiers', [
    ('tiers-all-three', (SC, EXACT), (SC, EXACT), {'certain', 'resolved', 'all'}),
    ('resolved-only', (SC, EXACT), (SC, UNIQUE), {'resolved', 'all'}),
    ('resolved-only-dynamic-exact', (SC, EXACT), (DR, EXACT), {'resolved', 'all'}),
    ('all-only', (SC, EXACT), (SC, AMBIGUOUS), {'all'}),
    ('all-only-unresolved', (SI, UNRESOLVED), (SC, EXACT), {'all'}),
])
def test_V03_rule_tier_presence(name, ab, ba, tiers):
    assert set(deps(cyc_pair(ab, ba))) == {key(t, 'a.py', 'b.py') for t in tiers}


def test_V03_C01_parent_chain_and_derived_fields():
    result = run(['a.py', 'b.py', 'c.py'], [fedge('a.py', 'b.py', indices=[0]), fedge('b.py', 'a.py', indices=[1])])
    found = deps(result)
    members = [fid('a.py'), fid('b.py')]
    assert set(found) == {key(t, 'a.py', 'b.py') for t in TIERS}
    ids = {t: cycle_id('file', t, members) for t in TIERS}
    for tier in TIERS:
        item = found[key(tier, 'a.py', 'b.py')]
        assert set(item) == {'id', 'kind', 'target', 'metrics', 'evidence', 'coverage', 'status', 'structure'}
        assert item['id'] == ids[tier]
        assert item['target'] == cycle_target('file', tier, members)
        assert item['kind'] == 'dependency_cycle'
        assert item['coverage'] == 'static_analyzer_relation' and item['status'] == 'static_candidate'
        assert set(item['structure']) == {'scheme', 'tier', 'members', 'parent_id', 'cut_candidates'}
        assert item['structure']['scheme'] == 'file' and item['structure']['tier'] == tier
        assert item['structure']['members'] == members
        assert set(item['metrics']) == {'member_count', 'internal_pair_count', 'internal_evidence_count', 'min_pair_weight'}
        assert item['metrics'] == {'member_count': 2, 'internal_pair_count': 2, 'internal_evidence_count': 2, 'min_pair_weight': pytest.approx(1.0)}
        assert [(r['from_id'], r['to_id']) for r in item['evidence']] == [(members[0], members[1]), (members[1], members[0])]
    assert found[key('certain', 'a.py', 'b.py')]['structure']['parent_id'] == ids['resolved']
    assert found[key('resolved', 'a.py', 'b.py')]['structure']['parent_id'] == ids['all']
    assert found[key('all', 'a.py', 'b.py')]['structure']['parent_id'] is None
    assert len(set(ids.values())) == 3 and len({found[k]['target'] for k in found}) == 3  # rule-same-members-across-tiers


def test_V03_member_order_in_identifier_is_sorted():
    result = run(['z.py', 'a.py', 'm.py'], [fedge('z.py', 'a.py'), fedge('a.py', 'm.py'), fedge('m.py', 'z.py')])
    item = deps(result)[key('all', 'z.py', 'a.py', 'm.py')]
    sorted_members = sorted(fid(p) for p in ('z.py', 'a.py', 'm.py'))
    assert item['structure']['members'] == sorted_members
    assert item['id'] == cycle_id('file', 'all', sorted_members)


def test_V03_C02_ambiguous_edge_widens_only_the_all_tier():
    edges = [fedge('a.py', 'b.py', 'IMPORTS', SC, EXACT), fedge('b.py', 'c.py', 'CALLS', SC, AMBIGUOUS),
             fedge('c.py', 'a.py', 'IMPORTS', SC, EXACT), fedge('a.py', 'c.py', 'CALLS', SC, UNIQUE)]
    result = run(['a.py', 'b.py', 'c.py'], edges)
    assert view(result) == sorted([key('all', 'a.py', 'b.py', 'c.py'), key('resolved', 'a.py', 'c.py')])
    found = deps(result)
    assert found[key('resolved', 'a.py', 'c.py')]['structure']['parent_id'] == cycle_id('file', 'all', [fid(p) for p in ('a.py', 'b.py', 'c.py')])


def test_V03_parent_is_the_containing_scc_not_the_first_one():
    # certain {A,B}; resolved {A,B} and {X,Y}; all {A,B,C}, {X,Y,Z} (C and Z join through ambiguous edges only)
    edges = [fedge('a.py', 'b.py'), fedge('b.py', 'a.py'), fedge('a.py', 'c.py', resolution=AMBIGUOUS), fedge('c.py', 'a.py', resolution=AMBIGUOUS),
             fedge('x.py', 'y.py', resolution=UNIQUE), fedge('y.py', 'x.py', resolution=UNIQUE),
             fedge('x.py', 'z.py', resolution=AMBIGUOUS), fedge('z.py', 'x.py', resolution=AMBIGUOUS)]
    result = run(['a.py', 'b.py', 'c.py', 'x.py', 'y.py', 'z.py'], edges)
    found = deps(result)
    assert set(found) == {key('certain', 'a.py', 'b.py'), key('resolved', 'a.py', 'b.py'), key('all', 'a.py', 'b.py', 'c.py'),
                          key('resolved', 'x.py', 'y.py'), key('all', 'x.py', 'y.py', 'z.py')}
    abc = [fid(p) for p in ('a.py', 'b.py', 'c.py')]
    xyz = [fid(p) for p in ('x.py', 'y.py', 'z.py')]
    ab = [fid('a.py'), fid('b.py')]
    assert found[key('certain', 'a.py', 'b.py')]['structure']['parent_id'] == cycle_id('file', 'resolved', ab)
    assert found[key('resolved', 'a.py', 'b.py')]['structure']['parent_id'] == cycle_id('file', 'all', abc)
    assert found[key('resolved', 'x.py', 'y.py')]['structure']['parent_id'] == cycle_id('file', 'all', xyz)
    assert found[key('all', 'x.py', 'y.py', 'z.py')]['structure']['parent_id'] is None


def test_V03_resolved_parent_may_have_different_members():
    edges = [fedge('a.py', 'b.py'), fedge('b.py', 'a.py'), fedge('b.py', 'c.py', resolution=UNIQUE), fedge('c.py', 'b.py', resolution=UNIQUE)]
    found = deps(run(['a.py', 'b.py', 'c.py'], edges))
    assert found[key('certain', 'a.py', 'b.py')]['structure']['parent_id'] == cycle_id('file', 'resolved', [fid(p) for p in ('a.py', 'b.py', 'c.py')])


RING_SHARES = [1, 1, .5, .5, .5, 1, .25, 1, .5, 1, .25]
RING_EVIDENCE = [3, 1, 2, 2, 1, 1, 5, 2, 1, 1, 1]
# Order by (max_weight, evidence_count, from_id, to_id), worked out by hand for the 11-ring:
# .25: i10(ev1), i6(ev5); .5: ev1 i4, i8; ev2 i2, i3; 1.0: ev1 i1, i5, i9; ev2 i7; ev3 i0
RING_ORDER = [10, 6, 4, 8, 2, 3, 1, 5, 9, 7, 0]


def ring(count):
    paths = [f'n{i:02}.py' for i in range(count)]
    edges = [fedge(paths[i], paths[(i + 1) % count], share=RING_SHARES[i], indices=[i], evidence=RING_EVIDENCE[i]) for i in range(count)]
    return paths, edges


@pytest.mark.parametrize('count,expected_len', [(9, 9), (10, 10), (11, 10)])
@pytest.mark.parametrize('tier', ['certain', 'all'])
def test_V03_C05_cut_candidates_length_and_order(count, expected_len, tier):
    paths, edges = ring(count)
    item = deps(run(paths, edges))[key(tier, *paths)]
    cuts = item['structure']['cut_candidates']
    assert len(cuts) == expected_len
    order = sorted(range(count), key=lambda i: (RING_SHARES[i], RING_EVIDENCE[i], fid(paths[i]), fid(paths[(i + 1) % count])))
    assert [(c['from_id'], c['to_id']) for c in cuts] == [(fid(paths[i]), fid(paths[(i + 1) % count])) for i in order[:10]]
    for cut, i in zip(cuts, order):
        assert cut == {'from_id': fid(paths[i]), 'to_id': fid(paths[(i + 1) % count]), 'relations': ['IMPORTS'],
                       'max_weight': pytest.approx(RING_SHARES[i]), 'evidence_count': RING_EVIDENCE[i]}
    assert item['metrics'] == {'member_count': count, 'internal_pair_count': count,
                               'internal_evidence_count': sum(RING_EVIDENCE[:count]), 'min_pair_weight': pytest.approx(min(RING_SHARES[:count]))}
    assert len(item['evidence']) == count  # evidence keeps every internal pair; only cut_candidates is capped


def test_V03_cut_order_hand_worked_for_eleven_ring():
    paths, edges = ring(11)
    cuts = deps(run(paths, edges))[key('all', *paths)]['structure']['cut_candidates']
    assert [c['from_id'] for c in cuts] == [fid(paths[i]) for i in RING_ORDER[:10]]
    assert fid(paths[0]) not in [c['from_id'] for c in cuts]  # heaviest (1.0, evidence 3) pair is the one dropped


def test_V03_cut_order_ties_break_on_endpoint_ids():
    paths = ['m.py', 'a.py', 'z.py', 'b.py']
    edges = [fedge('m.py', 'a.py'), fedge('a.py', 'z.py'), fedge('z.py', 'b.py'), fedge('b.py', 'm.py')]
    cuts = deps(run(paths, edges))[key('all', *paths)]['structure']['cut_candidates']
    assert [(c['from_id'], c['to_id']) for c in cuts] == [(fid('a.py'), fid('z.py')), (fid('b.py'), fid('m.py')),
                                                          (fid('m.py'), fid('a.py')), (fid('z.py'), fid('b.py'))]


def test_V03_C06_chain_of_20000_files_is_one_cycle():
    count = 20000
    paths = [f'f{i:05}.py' for i in range(count)]
    edges = [fedge(paths[i], paths[(i + 1) % count], indices=[i]) for i in range(count)]
    result = run(paths, edges)
    found = deps(result)
    assert set(found) == {key(t, *paths) for t in TIERS}
    top = found[key('all', *paths)]
    assert top['metrics']['member_count'] == count and top['metrics']['internal_pair_count'] == count
    assert len(top['structure']['cut_candidates']) == 10


def test_V03_candidates_are_sorted_by_kind_then_id():
    edges = [fedge('a/x.py', 'b/y.py'), fedge('b/y.py', 'a/x.py'), fedge('b/y.py', 'c/z.py')]
    result = run(['a/x.py', 'b/y.py', 'c/z.py'], edges)
    keys = [(c['kind'], c['id']) for c in result.candidates]
    assert len({k[0] for k in keys}) >= 2 and keys == sorted(keys)


def test_V03_result_coverage_is_exactly_the_structure_object():
    result = run(['a/x.py', 'b/y.py'], [])
    empty = {'assigned_file_count': 2, 'unassigned_file_count': 0, 'unassigned_files': [], 'shared_file_count': 0, 'shared_files': []}
    assert result.coverage == {'structure': {'policy': 'structure.v2', 'schemes': {'language': empty}}}


def test_V03_result_is_frozen_dataclass_with_declared_fields():
    result = run(['a.py'], [])
    assert isinstance(result, StructureResult) and dataclasses.is_dataclass(result)
    assert [f.name for f in dataclasses.fields(StructureResult)] == ['candidates', 'package_metrics', 'coverage', 'package_dependencies']
    assert isinstance(result.candidates, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.candidates = ()


def test_V03_F17_repeat_and_input_order_independence():
    paths, edges = ring(8)
    first = analyze_structure(architecture(paths, edges), default_weights())
    again = analyze_structure(architecture(list(reversed(paths)), list(reversed(edges))), default_weights())
    assert json.dumps(first.candidates, sort_keys=True) == json.dumps(again.candidates, sort_keys=True)
    assert first == analyze_structure(architecture(paths, edges), default_weights())


def v8_payload(tmp_path, with_arch=False):
    """A bottlenecks.v8 payload with all three new kinds, produced by the product pipeline on a hand-made graph."""
    from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
    from tests.edge_weights_support import edge, load_weights, weights_data
    from tests.file_analysis_support import converted, node
    files = {'p/a.py': 'x = 1\n', 'q/b.py': 'x = 1\n', 'r/c.py': 'x = 1\n'}
    nodes = [node('a', 'p/a.py'), node('b', 'q/b.py'), node('c', 'r/c.py')]
    edges = [edge('a', 'b'), edge('b', 'a'), edge('c', 'a')]
    snap, arch = converted(files, nodes, edges)
    payload = json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, load_weights(tmp_path, weights_data()))))
    return (payload, arch) if with_arch else payload


def test_V09_pipeline_payload_is_v8_with_all_new_kinds(tmp_path):
    payload = v8_payload(tmp_path)
    assert payload['schema'] == 'bottlenecks.v9' and payload['granularity'] == 'file'
    assert {c['kind'] for c in payload['candidates']} >= {'dependency_cycle', 'package_cycle', 'unstable_dependency'}
    assert payload['dependency_network']['structure_policy'] == 'structure.v2'
    assert set(payload['dependency_network']['package_metrics']) == {'language'}


def generate_to_text(payload):
    from report.bottlenecks.generate import generate
    writes = []
    generate(Path('in.json'), Path('out.html'), read_text=lambda path: json.dumps(payload),
             write_text=lambda path, text: writes.append(text))
    assert len(writes) == 1
    return writes[0]


def test_V09_bottleneck_json_coverage_structure_is_the_f13_object(tmp_path):
    payload = v8_payload(tmp_path)
    language = {'assigned_file_count': 3, 'unassigned_file_count': 0, 'unassigned_files': [], 'shared_file_count': 0, 'shared_files': []}
    assert payload['coverage']['structure'] == {'policy': 'structure.v2', 'schemes': {'language': language}}


def test_V09_v8_ok_and_new_kind_labels_render(tmp_path):
    from report.bottlenecks import render_report
    from report.bottlenecks.generate import KIND_DESCRIPTIONS, KIND_LABELS
    from tests.report_size_support import legacy_v8
    payload, arch = v8_payload(tmp_path, with_arch=True)
    payload = legacy_v8(payload, arch)
    for kind in ('dependency_cycle', 'package_cycle', 'unstable_dependency', 'untested_hub', 'isolated_node'):
        assert isinstance(KIND_LABELS[kind], str) and KIND_LABELS[kind].strip()
        assert isinstance(KIND_DESCRIPTIONS[kind], str) and KIND_DESCRIPTIONS[kind].strip()
    for kind in ('large_node', 'unresolved_boundary', 'evidence_spread'):
        assert kind in KIND_LABELS and kind in KIND_DESCRIPTIONS
    for text in (render_report(payload), generate_to_text(payload)):
        assert '<html' in text.lower()


def test_V09_v7_and_v6_still_render(tmp_path):
    from tests.test_search_mimicry_schema_and_structure import v6, v7
    for payload in (v6(tmp_path), v7(tmp_path)):
        assert '<html' in generate_to_text(payload).lower()
    assert v7(tmp_path)['schema'] == 'bottlenecks.v7'


def test_V09_v8_without_granularity_is_rejected(tmp_path):
    from tests.test_search_mimicry_schema_and_structure import rejected_by_generate, rejected_by_render
    payload = v8_payload(tmp_path)
    del payload['granularity']
    assert '$' in rejected_by_render(payload)
    assert '$' in rejected_by_generate(payload, tmp_path)


@pytest.mark.parametrize('granularity', ['symbol', '', None, 'FILE'])
def test_V09_v8_with_other_granularity_is_rejected(tmp_path, granularity):
    from tests.test_search_mimicry_schema_and_structure import rejected_by_generate
    payload = v8_payload(tmp_path)
    payload['granularity'] = granularity
    assert '$' in rejected_by_generate(payload, tmp_path)


def test_V09_unknown_kind_is_rejected(tmp_path):
    from tests.test_search_mimicry_schema_and_structure import rejected_by_generate, rejected_by_render
    payload = v8_payload(tmp_path)
    payload['candidates'][0]['kind'] = 'not_a_kind'
    assert '$' in rejected_by_render(payload)
    assert '$' in rejected_by_generate(payload, tmp_path)


def test_V09_unknown_schema_version_is_rejected(tmp_path):
    from tests.test_search_mimicry_schema_and_structure import rejected_by_render
    payload = v8_payload(tmp_path)
    payload['schema'] = 'bottlenecks.v10'
    assert '$.schema' in rejected_by_render(payload)


STRUCTURE_SOURCE = REPO / 'analysis' / 'structure.py'
FORBIDDEN_LANGUAGES = ('python', 'kotlin', 'typescript')


def imported_modules(source, package='analysis'):
    """Absolute dotted names of every import, including function-level ones, relative imports resolved against
    `package`, plus literal arguments of importlib.import_module/__import__."""
    modules = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:
                parts = package.split('.')[:len(package.split('.')) - node.level + 1]
                base = '.'.join(parts + ([base] if base else []))
            modules.append(base)
            modules += [f'{base}.{alias.name}' for alias in node.names]
        elif isinstance(node, ast.Call):
            name = getattr(node.func, 'attr', getattr(node.func, 'id', ''))
            if name in {'import_module', '__import__'} and node.args and isinstance(node.args[0], ast.Constant):
                modules.append(str(node.args[0].value))
    return modules


def violations(modules):
    bad = []
    for name in modules:
        parts = name.split('.')
        if parts[0] == 'framework_analyzers':
            bad.append(name)
        if parts[0] == 'language_analyzers' and len(parts) > 1 and parts[1] in FORBIDDEN_LANGUAGES:
            bad.append(name)
    return bad


@pytest.mark.parametrize('source,expected', [
    ('import framework_analyzers.nestjs', ['framework_analyzers.nestjs']),
    ('from framework_analyzers import fastapi', ['framework_analyzers', 'framework_analyzers.fastapi']),
    ('from language_analyzers.python.graph import X', ['language_analyzers.python.graph', 'language_analyzers.python.graph.X']),
    ('def f():\n    from language_analyzers.kotlin import K', ['language_analyzers.kotlin', 'language_analyzers.kotlin.K']),
    ('import importlib\nimportlib.import_module("language_analyzers.typescript")', ['language_analyzers.typescript']),
    ('from ..framework_analyzers.android import A', ['framework_analyzers.android', 'framework_analyzers.android.A']),
    ('from language_analyzers.core.graph_models import GraphEdge', []),
    ('from .edge_weights import EdgeWeights', []),
    ('import hashlib, dataclasses', []),
])
def test_V12_checker_detects_and_allows_expected_forms(source, expected):
    assert violations(imported_modules(source)) == expected


def test_V12_no_framework_import_in_structure_module():
    assert STRUCTURE_SOURCE.exists()
    modules = imported_modules(STRUCTURE_SOURCE.read_text(encoding='utf-8'))
    assert modules, 'analysis/structure.py must have imports (checker would pass vacuously otherwise)'
    assert [m for m in violations(modules) if m.split('.')[0] == 'framework_analyzers'] == []


def test_V12_no_language_specific_import_in_structure_module():
    modules = imported_modules(STRUCTURE_SOURCE.read_text(encoding='utf-8'))
    assert [m for m in violations(modules) if m.split('.')[0] == 'language_analyzers'] == []


def test_V13_empty_graph():
    result = analyze_structure(architecture([], [], details=False), default_weights())
    assert result.candidates == ()
    assert result.package_metrics == {'language': {}}
    assert 'framework' not in result.package_metrics and 'framework' not in result.coverage['structure']['schemes']


def test_V13_empty_graph_with_empty_details_mapping():
    result = analyze_structure(architecture([], []), default_weights())
    assert result.candidates == () and result.package_metrics == {'language': {}}


def test_V13_no_edges_gives_isolated_language_packages():
    result = run(['a/x.py', 'b/y.py', 'z.py'], [])
    assert result.candidates == ()
    assert set(result.package_metrics['language']) == {'pkg:dir:a', 'pkg:dir:b', 'pkg:dir:.'}
    for row in result.package_metrics['language'].values():
        assert row['ca'] == 0 and row['ce'] == 0 and row['instability'] is None and row['file_count'] == 1


def converted_pair():
    from tests.edge_weights_support import edge
    from tests.file_analysis_support import converted, node
    return converted({'a.py': 'x = 1\n', 'b.py': 'y = 2\n'}, [node('a', 'a.py'), node('b', 'b.py')], [edge('a', 'b'), edge('b', 'a')])


def test_V13_unknown_confidence_raises_bottleneck_input_error():
    from bottlenecks import BottleneckInputError, analyze_bottlenecks
    snap, arch = converted_pair()
    arch.edges[0].confidence = 'bogus_confidence'
    with pytest.raises(BottleneckInputError):
        analyze_bottlenecks(snap, arch, default_weights())


def test_V13_confidence_missing_from_edge_weights_raises_bottleneck_input_error():
    from bottlenecks import BottleneckInputError, analyze_bottlenecks
    snap, arch = converted_pair()
    base = default_weights()
    partial = EdgeWeights(base.id, base.version, {SC: 1.0}, dict(base.resolution), base.large_node_line_threshold)
    arch.edges[0].confidence = SI
    with pytest.raises(BottleneckInputError):
        analyze_bottlenecks(snap, arch, partial)


def test_V13_valid_converted_graph_still_succeeds():
    from bottlenecks import analyze_bottlenecks
    snap, arch = converted_pair()
    report = analyze_bottlenecks(snap, arch, default_weights())
    assert report is not None


def test_V13_unmapped_nest_module_keeps_other_members():
    from tests.structure_support import dedge, dnode
    module = dnode('nestjs:module:src/m.ts#M', 'module', 'nestjs')
    controller = dnode('nestjs:controller:src/c.ts#C', 'controller', 'nestjs')
    arch = architecture(['src/c.ts', 'src/s.ts'], [], dnodes=[module, controller, dnode('nestjs:provider:src/s.ts#S', 'provider', 'nestjs')],
                        dedges=[dedge(module['id'], controller['id'], 'DECLARES'), dedge(module['id'], 'nestjs:provider:src/s.ts#S', 'PROVIDES')],
                        node_files={controller['id']: 'src/c.ts', 'nestjs:provider:src/s.ts#S': 'src/s.ts'})
    result = analyze_structure(arch, default_weights())
    assert result.package_metrics['framework']['pkg:nestjs:src/m.ts#M']['file_count'] == 2
    assert result.coverage['structure']['schemes']['framework']['unassigned_file_count'] == 0
