"""V9 evidence (spec 3f70cc03aeae9c1a): synthetic base/head JSON pairs for each RV rule. Expected explained / unexplained
outcomes come from the RV1-RV9 text; the pairs are hand-built and never produced by the product."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

EVIDENCE = Path(__file__).parent / 'signal_defects_evidence'
_spec = importlib.util.spec_from_file_location('review_diff_under_test', EVIDENCE / 'review_diff.py')
rd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rd)

METRIC_KEYS = ('fan_in', 'fan_out', 'token_cost', 'betweenness_centrality', 'hop_2_token_cost', 'pagerank')


def node(ident, kind='function', path='a.kt', start=1, end=1, flags=(), meta=None, signature=None):
    return {'id': ident, 'label': ident, 'kind': kind, 'span': {'file_path': path, 'start_line': start, 'end_line': end},
            'cost': {'token_estimate': 1}, 'signature': signature, 'flags': list(flags), 'metadata': dict(meta or {}),
            'size': 25, 'provenance': 'kotlin-core'}


def edge(source, target, relation='CALLS', line=1, path='a.kt', resolution='exact', confidence='static_certain', candidates=()):
    return {'from_id': source, 'to_id': target, 'relation': relation, 'resolution': resolution,
            'confidence': confidence, 'candidates': list(candidates),
            'evidence': {'file_path': path, 'start_line': line, 'end_line': line}}


def arch(nodes, edges, details=None):
    data = {'schema_version': '5', 'nodes': list(nodes), 'edges': list(edges)}
    if details is not None:
        data['details'] = details
    return data


def bott(nodes, candidates=(), analysis='5', threshold=2000, metrics=None):
    node_metrics = {n['id']: {k: 0 for k in METRIC_KEYS} for n in nodes}
    for ident, values in (metrics or {}).items():
        node_metrics[ident].update(values)
    return {'schema': 'bottlenecks.v6', 'versions': {'analysis': analysis}, 'candidates': list(candidates),
            'edge_weights': {'large_node_line_threshold': threshold},
            'dependency_network': {'node_metrics': node_metrics}}


def pair(nodes, edges, candidates=(), analysis='5', details=None, metrics=None, threshold=2000):
    return arch(nodes, edges, details), bott(nodes, candidates, analysis, threshold, metrics)


def candidate(ident, kind, target, metrics=None, evidence=None):
    return {'id': ident, 'kind': kind, 'target': target, 'metrics': metrics or {}, 'evidence': evidence or [],
            'coverage': 'static_analyzer_relation', 'status': 'static_candidate'}


def review(base, head, stage='a', mode='symbol', name='x', symbol=None):
    return rd.review(base, head, name=name, mode=mode, stage=stage, symbol_pairs=symbol)


def file_details(nodes=(), edges=()):
    return {'nodes': list(nodes), 'edges': list(edges), 'node_files': {}, 'node_owners': {}, 'file_nodes': {}}


CLS = 'kotlin:a.kt#C'
MEM = 'kotlin:a.kt#C.m'
TGT = 'kotlin:b.kt#T'


def class_nodes(extra=()):
    return [node(CLS, 'class', start=1, end=9), node(MEM, 'method', start=2, end=2), node(TGT, 'class', 'b.kt', 1, 3), *extra]


def contains(owner=CLS, member=MEM, line=2):
    return edge(owner, member, 'CONTAINS', line)


def test_sanity_identical_pairs_have_no_unexplained():
    nodes = class_nodes()
    p = pair(nodes, [contains(), edge(MEM, TGT)])
    assert review(p, p)['unexplained'] == []
    p6 = pair(nodes, [contains(), edge(MEM, TGT)], analysis='6')
    assert review(pair(nodes, [contains(), edge(MEM, TGT)], analysis='5'), p6, stage='b')['unexplained'] == []


# ---------------------------------------------------------------- RV2

IMP_SRC, IMP_DST = 'kotlin:u.kt', 'kotlin:b.kt#B'


@pytest.mark.parametrize('relation', ['IMPORTS', 'IMPORTS_SYMBOL'])
def test_V9_RV2_start_line_only_difference_is_explained(relation):
    nodes = [node(IMP_SRC, 'file', 'u.kt'), node(IMP_DST, 'class', 'b.kt')]
    base = pair(nodes, [edge(IMP_SRC, IMP_DST, relation, 3, 'u.kt')])
    head = pair(nodes, [edge(IMP_SRC, IMP_DST, relation, 2, 'u.kt')])
    assert review(base, head)['unexplained'] == []


def test_V9_RV2_resolution_also_different_is_unexplained():
    nodes = [node(IMP_SRC, 'file', 'u.kt'), node(IMP_DST, 'class', 'b.kt')]
    base = pair(nodes, [edge(IMP_SRC, IMP_DST, 'IMPORTS', 3, 'u.kt')])
    head = pair(nodes, [edge(IMP_SRC, IMP_DST, 'IMPORTS', 2, 'u.kt', resolution='unique_name')])
    found = review(base, head)['unexplained']
    assert any(u.startswith('edge removed') for u in found) and any(u.startswith('edge added') for u in found)


@pytest.mark.parametrize('field,value', [('confidence', 'static_inferred'), ('candidates', ['kotlin:b.kt#B2'])])
def test_V9_RV2_confidence_or_candidates_difference_is_unexplained(field, value):
    nodes = [node(IMP_SRC, 'file', 'u.kt'), node(IMP_DST, 'class', 'b.kt')]
    base = pair(nodes, [edge(IMP_SRC, IMP_DST, 'IMPORTS', 3, 'u.kt')])
    changed = edge(IMP_SRC, IMP_DST, 'IMPORTS', 2, 'u.kt')
    changed[field] = value
    assert review(base, pair(nodes, [changed]))['unexplained']


def test_V9_RV2_non_kotlin_pair_is_unexplained():
    nodes = [node('py:u', 'module', 'u.py'), node('py:b#B', 'class', 'b.py')]
    base = pair(nodes, [edge('py:u', 'py:b#B', 'IMPORTS', 3, 'u.py')])
    head = pair(nodes, [edge('py:u', 'py:b#B', 'IMPORTS', 2, 'u.py')])
    assert review(base, head)['unexplained']


def test_V9_RV2_pairs_are_consumed_one_to_one():
    nodes = [node(IMP_SRC, 'file', 'u.kt'), node(IMP_DST, 'class', 'b.kt')]
    base = pair(nodes, [edge(IMP_SRC, IMP_DST, 'IMPORTS', 3, 'u.kt'), edge(IMP_SRC, IMP_DST, 'IMPORTS', 4, 'u.kt')])
    head = pair(nodes, [edge(IMP_SRC, IMP_DST, 'IMPORTS', 2, 'u.kt')])
    found = review(base, head)['unexplained']
    assert len(found) == 1 and found[0].startswith('edge removed')


# ---------------------------------------------------------------- RV3

@pytest.mark.parametrize('relation', ['CALLS', 'INSTANTIATES', 'READS', 'WRITES'])
def test_V9_RV3_class_edge_removed_with_member_holding_same_edge_is_explained(relation):
    nodes = class_nodes()
    base = pair(nodes, [contains(), edge(CLS, TGT, relation), edge(MEM, TGT, relation)])
    head = pair(nodes, [contains(), edge(MEM, TGT, relation)])
    assert review(base, head)['unexplained'] == []


def test_V9_RV3_class_edge_removed_without_member_edge_is_unexplained():
    nodes = class_nodes()
    base = pair(nodes, [contains(), edge(CLS, TGT, 'CALLS')])
    head = pair(nodes, [contains()])
    assert review(base, head)['unexplained']


def test_V9_RV3_member_edge_with_different_relation_does_not_explain():
    nodes = class_nodes()
    base = pair(nodes, [contains(), edge(CLS, TGT, 'CALLS')])
    head = pair(nodes, [contains(), edge(MEM, TGT, 'READS')])
    assert any(u.startswith('edge removed') for u in review(base, head)['unexplained'])


def test_V9_RV3_edge_to_own_member_is_explained():
    nodes = class_nodes()
    base = pair(nodes, [contains(), edge(CLS, MEM, 'READS')])
    head = pair(nodes, [contains()])
    assert review(base, head)['unexplained'] == []


def test_V9_RV3_tests_edge_to_member_or_with_vanished_sibling_relations():
    nodes = class_nodes()
    to_member = (pair(nodes, [contains(), edge(CLS, MEM, 'TESTS')]), pair(nodes, [contains()]))
    assert review(*to_member)['unexplained'] == []
    vanished = (pair(nodes, [contains(), edge(CLS, TGT, 'CALLS'), edge(CLS, TGT, 'TESTS'), edge(MEM, TGT, 'CALLS')]),
                pair(nodes, [contains(), edge(MEM, TGT, 'CALLS')]))
    assert review(*vanished)['unexplained'] == []
    # a non-TESTS relation survives at class level, so the TESTS edge is not explained
    survives = (pair(nodes, [contains(), edge(CLS, TGT, 'CALLS'), edge(CLS, TGT, 'TESTS')]),
                pair(nodes, [contains(), edge(CLS, TGT, 'CALLS')]))
    assert review(*survives)['unexplained']
    # TESTS with no sibling relation in base at all
    alone = (pair(nodes, [contains(), edge(CLS, TGT, 'TESTS')]), pair(nodes, [contains()]))
    assert review(*alone)['unexplained']


def test_V9_RV3_non_class_source_is_unexplained():
    nodes = class_nodes()
    base = pair(nodes, [contains(), edge(MEM, TGT, 'CALLS')])
    head = pair(nodes, [contains()])
    assert review(base, head)['unexplained']


def test_V9_RV3_rekey_requires_same_relation_and_both_ends():
    nodes = class_nodes()
    same = (pair(nodes, [contains(), edge(CLS, TGT, 'TESTS', 4)]), pair(nodes, [contains(), edge(CLS, TGT, 'TESTS', 6)]))
    assert review(*same)['unexplained'] == []
    other_end = (pair(nodes, [contains(), edge(CLS, TGT, 'TESTS', 4)]),
                 pair(nodes, [contains(), edge(CLS, MEM, 'TESTS', 6)]))
    assert review(*other_end)['unexplained']
    other_relation = (pair(nodes, [contains(), edge(CLS, TGT, 'TESTS', 4)]),
                      pair(nodes, [contains(), edge(CLS, TGT, 'READS', 6)]))
    assert review(*other_relation)['unexplained']


def test_V9_RV3_added_edge_without_pair_is_unexplained():
    nodes = class_nodes()
    assert review(pair(nodes, [contains()]), pair(nodes, [contains(), edge(MEM, TGT)]))['unexplained']


def _file_mode(sym_edges_base, sym_edges_head, file_edge_base, file_edge_head):
    nodes = class_nodes()
    files = [node('file:a.kt', 'file', 'a.kt'), node('file:b.kt', 'file', 'b.kt')]
    base = pair(files, file_edge_base, details=file_details(nodes, sym_edges_base))
    head = pair(files, file_edge_head, details=file_details(nodes, sym_edges_head))
    sym = (pair(nodes, sym_edges_base), pair(nodes, sym_edges_head))
    return base, head, sym


def test_V9_RV3_file_mode_removal_needs_same_relation_symbol_removal():
    f = lambda rel: edge('file:a.kt', 'file:b.kt', rel, 1)
    sym_base = [contains(), edge(CLS, TGT, 'CALLS'), edge(MEM, TGT, 'CALLS')]
    sym_head = [contains(), edge(MEM, TGT, 'CALLS')]
    base, head, sym = _file_mode(sym_base, sym_head, [f('CALLS')], [])
    assert review(base, head, mode='file', symbol=sym)['unexplained'] == []
    # same file pair, different relation: no wildcard relation mapping
    base, head, sym = _file_mode(sym_base, sym_head, [f('READS')], [])
    assert any(u.startswith('edge removed') for u in review(base, head, mode='file', symbol=sym)['unexplained'])


def test_V9_RV3_file_mode_removal_needs_same_file_pair():
    sym_base = [contains(), edge(CLS, TGT, 'CALLS'), edge(MEM, TGT, 'CALLS')]
    sym_head = [contains(), edge(MEM, TGT, 'CALLS')]
    other = edge('file:a.kt', 'file:z.kt', 'CALLS', 1)
    base, head, sym = _file_mode(sym_base, sym_head, [other], [])
    assert any(u.startswith('edge removed') for u in review(base, head, mode='file', symbol=sym)['unexplained'])


# ---------------------------------------------------------------- RV4

def _structure(kind, base_files, head_files, ident='s1'):
    nodes = class_nodes()
    edges_b = [contains(), edge(CLS, TGT, 'CALLS'), edge(MEM, TGT, 'CALLS')]
    edges_h = [contains(), edge(MEM, TGT, 'CALLS')]
    cb = [candidate(ident, kind, 'cycle:1', {'size': 2}, [{'from_id': f, 'to_id': base_files[-1]} for f in base_files])] if base_files else []
    ch = [candidate(ident, kind, 'cycle:1', {'size': 3}, [{'from_id': f, 'to_id': head_files[-1]} for f in head_files])] if head_files else []
    return pair(nodes, edges_b, cb), pair(nodes, edges_h, ch)


@pytest.mark.parametrize('kind', sorted(rd.STRUCTURE_KINDS))
def test_V9_RV4_overlapping_change_is_explained(kind):
    base, head = _structure(kind, ['kotlin:a.kt', 'kotlin:q.kt'], ['kotlin:a.kt#C', 'kotlin:q.kt'])
    assert review(base, head)['unexplained'] == []


@pytest.mark.parametrize('kind', sorted(rd.STRUCTURE_KINDS))
def test_V9_RV4_non_overlapping_change_is_unexplained(kind):
    base, head = _structure(kind, ['kotlin:y.kt', 'kotlin:q.kt'], ['kotlin:y.kt', 'kotlin:q.kt'])
    assert review(base, head)['unexplained']


@pytest.mark.parametrize('kind', sorted(rd.STRUCTURE_KINDS))
def test_V9_RV4_added_or_removed_candidate_is_unexplained(kind):
    base, head = _structure(kind, [], ['kotlin:a.kt', 'kotlin:q.kt'])
    assert any(kind in u for u in review(base, head)['unexplained'])
    base, head = _structure(kind, ['kotlin:a.kt', 'kotlin:q.kt'], [])
    assert any(kind in u for u in review(base, head)['unexplained'])


def test_V9_RV4_package_overlap_is_explained():
    pkg = node('kotlin-package:p', 'module', 'a.kt')
    nodes = class_nodes([pkg])
    link = edge('kotlin-package:p', 'kotlin:a.kt#C', 'CONTAINS', 1)
    cb = [candidate('s1', 'package_cycle', 'c', {'n': 2}, [{'pkg': 'pkg:kotlin:p'}])]
    ch = [candidate('s1', 'package_cycle', 'c', {'n': 3}, [{'pkg': 'pkg:kotlin:p'}])]
    base = pair(nodes, [link, contains(), edge(CLS, TGT, 'CALLS'), edge(MEM, TGT, 'CALLS')], cb)
    head = pair(nodes, [link, contains(), edge(MEM, TGT, 'CALLS')], ch)
    assert review(base, head)['unexplained'] == []


def test_V9_RV4_other_kind_change_is_unexplained():
    nodes = class_nodes()
    cb = [candidate('i1', 'isolated_node', MEM, {'n': 1})]
    ch = [candidate('i1', 'isolated_node', MEM, {'n': 2})]
    assert review(pair(nodes, [contains()], cb), pair(nodes, [contains()], ch))['unexplained']


# ---------------------------------------------------------------- RV5

def test_V9_RV5_large_node_removal_is_unexplained_in_stage_a():
    nodes = class_nodes()
    cand = [candidate('l1', 'large_node', MEM, {'line_count': 3000, 'line_threshold': 2000})]
    assert review(pair(nodes, [contains()], cand), pair(nodes, [contains()]))['unexplained']


def test_V9_RV5_large_node_metric_key_addition_and_token_addition_are_explained():
    nodes = class_nodes()
    before = [candidate('l1', 'large_node', MEM, {'line_count': 3000, 'line_threshold': 2000})]
    after = [candidate('l1', 'large_node', MEM, {'line_count': 3000, 'line_threshold': 2000, 'token_count': 5, 'token_threshold': 24000})]
    assert review(pair(nodes, [contains()], before), pair(nodes, [contains()], after))['unexplained'] == []
    token_only = [candidate('l2', 'large_node', MEM, {'line_count': 10, 'line_threshold': 2000, 'token_count': 30000, 'token_threshold': 24000})]
    assert review(pair(nodes, [contains()]), pair(nodes, [contains()], token_only))['unexplained'] == []
    not_token = [candidate('l3', 'large_node', MEM, {'line_count': 10, 'line_threshold': 2000, 'token_count': 5, 'token_threshold': 24000})]
    assert review(pair(nodes, [contains()]), pair(nodes, [contains()], not_token))['unexplained']


def test_V9_RV5_large_node_value_change_is_unexplained():
    nodes = class_nodes()
    before = [candidate('l1', 'large_node', MEM, {'line_count': 3000, 'line_threshold': 2000})]
    after = [candidate('l1', 'large_node', MEM, {'line_count': 3001, 'line_threshold': 2000, 'token_count': 5, 'token_threshold': 24000})]
    assert review(pair(nodes, [contains()], before), pair(nodes, [contains()], after))['unexplained']


def _boundary(head_meta, base_meta=None):
    base_meta = base_meta or {'unresolved_calls': {'foo': 1}, 'unresolved_references': [{'name': 'foo'}], 'unresolved_reference_total': 1}
    base_nodes = [node(MEM, 'method', meta=base_meta), node(CLS, 'class', start=1, end=9), node(TGT, 'class', 'b.kt', 1, 3)]
    head_nodes = [node(MEM, 'method', meta=head_meta), node(CLS, 'class', start=1, end=9), node(TGT, 'class', 'b.kt', 1, 3)]
    cand = [candidate('u1', 'unresolved_boundary', MEM, {'unresolved_count': 1}, {'path': 'a.kt'})]
    return pair(base_nodes, [contains()], cand), pair(head_nodes, [contains()])


def test_V9_RV5_unresolved_name_moved_to_external_is_explained():
    base, head = _boundary({'external_calls': {'foo': 1}, 'external_call_count': 1})
    assert review(base, head)['unexplained'] == []


def test_V9_RV5_unresolved_name_not_moved_is_unexplained():
    base, head = _boundary({'external_calls': {'other': 1}, 'external_call_count': 1})
    assert any(u.startswith('unresolved_boundary removed') for u in review(base, head)['unexplained'])
    base, head = _boundary({})
    assert any(u.startswith('unresolved_boundary removed') for u in review(base, head)['unexplained'])


def test_V9_RV5_unresolved_removal_with_partial_names_is_unexplained():
    base, head = _boundary({'external_calls': {'foo': 1}, 'external_call_count': 1},
                           {'unresolved_calls': {'foo': 1, 'bar': 1}, 'unresolved_reference_total': 2})
    assert any(u.startswith('unresolved_boundary removed') for u in review(base, head)['unexplained'])


def _spread_pair(base_sources, head_sources, base_cand, head_cand, stage):
    """Target t in a/t.py; each source (path) calls it once at line 1."""
    t = node('py:a.t#f', 'function', 'a/t.py', 1, 2)
    nodes = [t, node('py:s', 'function', 'w.py', 1, 1)]
    mk = lambda paths: [edge('py:s', 'py:a.t#f', 'CALLS', 1, p) for p in paths]
    analysis_b = '5' if stage == 'a' else '5'
    return (pair(nodes, mk(base_sources), base_cand, analysis_b),
            pair(nodes, mk(head_sources), head_cand, '5' if stage == 'a' else '6'))


def _spread_cand(files, directory_count=None, span=0):
    metrics = {'file_count': files, 'line_span': span, 'line_threshold': 2000}
    if directory_count is not None:
        metrics['directory_count'] = directory_count
    return candidate('e1', 'evidence_spread', 'py:a.t#f', metrics)


def test_V9_RV5_spread_matching_recomputation_is_explained_stage_b():
    base, head = _spread_pair(['b/x.py', 'c/y.py'], ['b/x.py', 'c/y.py'], [_spread_cand(2)], [_spread_cand(2, 2)], 'b')
    assert review(base, head, stage='b')['unexplained'] == []


def test_V9_RV5_spread_same_directory_candidate_removal_is_explained_stage_b():
    base, head = _spread_pair(['b/x.py', 'b/y.py'], ['b/x.py', 'b/y.py'], [_spread_cand(2)], [], 'b')
    assert review(base, head, stage='b')['unexplained'] == []


@pytest.mark.parametrize('wrong', [_spread_cand(2, 3), _spread_cand(3, 2), _spread_cand(2, 1)])
def test_V9_RV5_spread_recomputation_mismatch_is_unexplained_stage_b(wrong):
    base, head = _spread_pair(['b/x.py', 'c/y.py'], ['b/x.py', 'c/y.py'], [_spread_cand(2)], [wrong], 'b')
    assert any('evidence_spread head' in u for u in review(base, head, stage='b')['unexplained'])


def test_V9_RV5_spread_missing_expected_candidate_is_unexplained_stage_b():
    base, head = _spread_pair(['b/x.py', 'c/y.py'], ['b/x.py', 'c/y.py'], [_spread_cand(2)], [], 'b')
    assert any('evidence_spread head' in u for u in review(base, head, stage='b')['unexplained'])


def test_V9_RV5_spread_stage_a_uses_the_pre_round3_and_r5_definitions():
    # base counted the target's own file (a/t.py) as evidence; head (R5) drops it, leaving one external file
    base, head = _spread_pair(['a/t.py', 'b/x.py'], ['a/t.py', 'b/x.py'], [_spread_cand(2)], [], 'a')
    assert review(base, head, stage='a')['unexplained'] == []
    wrong_base, head = _spread_pair(['a/t.py', 'b/x.py'], ['a/t.py', 'b/x.py'], [], [], 'a')
    assert any('evidence_spread base' in u for u in review(wrong_base, head, stage='a')['unexplained'])


def test_V9_RV5_untested_hub_change_needs_pagerank_change_in_stage_a_only():
    nodes = class_nodes()
    cb = [candidate('h1', 'untested_hub', MEM, {'pagerank': 0.1})]
    ch = [candidate('h1', 'untested_hub', MEM, {'pagerank': 0.2})]
    moved = review(pair(nodes, [contains()], cb, metrics={MEM: {'pagerank': 0.1}}),
                   pair(nodes, [contains()], ch, metrics={MEM: {'pagerank': 0.2}}))
    assert moved['unexplained'] == []
    same = review(pair(nodes, [contains()], cb, metrics={MEM: {'pagerank': 0.1}}),
                  pair(nodes, [contains()], ch, metrics={MEM: {'pagerank': 0.1}}))
    assert same['unexplained']
    stage_b = review(pair(nodes, [contains()], cb, metrics={MEM: {'pagerank': 0.1}}),
                     pair(nodes, [contains()], ch, analysis='6', metrics={MEM: {'pagerank': 0.2}}), stage='b')
    assert any(u.startswith('untested_hub') for u in stage_b['unexplained'])


# ---------------------------------------------------------------- RV6

def test_V9_RV6_external_call_count_in_node_metrics_is_unexplained_but_node_metadata_is_not():
    nodes = class_nodes()
    base = pair(nodes, [contains()])
    head = pair(nodes, [contains()])
    head[1]['dependency_network']['node_metrics'][MEM]['external_call_count'] = 2
    found = review(base, head)['unexplained']
    assert any('external_call_count' in u for u in found)
    meta_nodes = [node(MEM, 'method', start=2, end=2, meta={'external_call_count': 2, 'external_calls': {'x': 2}, 'unresolved_reference_total': 0}),
                  node(CLS, 'class', start=1, end=9), node(TGT, 'class', 'b.kt', 1, 3)]
    head2 = pair(meta_nodes, [contains()])
    assert review(base, head2)['unexplained'] == []


def test_V9_RV6_token_count_on_a_non_large_node_candidate_is_unexplained():
    nodes = class_nodes()
    before = [candidate('u1', 'unresolved_boundary', MEM, {'unresolved_count': 1})]
    after = [candidate('u1', 'unresolved_boundary', MEM, {'unresolved_count': 1, 'token_count': 3})]
    found = review(pair(nodes, [contains()], before), pair(nodes, [contains()], after))['unexplained']
    assert any('token_count' in u for u in found)


def test_V9_RV6_allowed_paths_are_position_fixed():
    nodes = class_nodes()
    base = pair(nodes, [contains()])
    head = pair(nodes, [contains()])
    head[1]['edge_weights']['large_node_token_threshold'] = 24000
    assert review(base, head)['unexplained'] == []
    head[1]['coverage'] = {'external_call_count': 3}
    assert any('coverage' in u for u in review(base, head)['unexplained'])


def test_V9_RV6_stage_b_allows_only_directory_count_on_spread_candidates():
    base, head = _spread_pair(['b/x.py', 'c/y.py'], ['b/x.py', 'c/y.py'], [_spread_cand(2)], [_spread_cand(2, 2)], 'b')
    head[1]['edge_weights']['large_node_token_threshold'] = 24000
    assert any('large_node_token_threshold' in u for u in review(base, head, stage='b')['unexplained'])


# ---------------------------------------------------------------- RV7

CTOR_CLASS = 'kotlin:a.kt#K'
F1, F2 = 'kotlin:a.kt#K.a', 'kotlin:a.kt#K.b'
SIG = '(\n    val a: Int,\n    val b: Int\n)'


def ctor_side(head, extra_edges=(), f2_span=None, analysis=None):
    f1_span = (2, 2) if head else (1, 4)
    f2_span = f2_span or ((3, 3) if head else (1, 4))
    nodes = [node(CTOR_CLASS, 'class', start=1, end=9),
             node(F1, 'field', start=f1_span[0], end=f1_span[1], signature='val a: Int' if head else SIG),
             node(F2, 'field', start=f2_span[0], end=f2_span[1], signature='val b: Int' if head else SIG)]
    edges = [edge(CTOR_CLASS, F1, 'CONTAINS', 2 if head else 1), edge(CTOR_CLASS, F2, 'CONTAINS', 3 if head else 1)]
    return nodes, edges + list(extra_edges), analysis or ('6' if head else '5')


def ctor_pair(head, extra_edges=(), **kw):
    nodes, edges, analysis = ctor_side(head, extra_edges, **kw)
    return pair(nodes, edges, analysis=analysis)


def test_V9_RV7_constructor_field_span_signature_change_is_explained_stage_b():
    assert review(ctor_pair(False), ctor_pair(True), stage='b')['unexplained'] == []


def test_V9_RV7_span_change_on_a_non_constructor_node_is_unexplained_stage_b():
    nodes = class_nodes()
    moved = [node(CLS, 'class', start=1, end=9), node(MEM, 'method', start=3, end=3), node(TGT, 'class', 'b.kt', 1, 3)]
    found = review(pair(nodes, [contains()]), pair(moved, [contains()], analysis='6'), stage='b')['unexplained']
    assert any(u.startswith('span changed') for u in found)


def test_V9_RV7_span_change_in_stage_a_is_unexplained_even_for_constructor_fields():
    found = review(ctor_pair(False), ctor_pair(True, analysis='5'), stage='a')['unexplained']
    assert any(u.startswith('span changed') for u in found)


def test_V9_RV7_node_id_set_rules():
    nodes = class_nodes()
    extra = nodes + [node('kotlin:n.kt#N', 'class', 'n.kt')]
    assert review(pair(nodes, [contains()]), pair(extra, [contains()]))['unexplained']
    assert review(pair(nodes, [contains()]), pair(extra, [contains()], analysis='6'), stage='b')['unexplained'] == []
    py_extra = nodes + [node('py:n#N', 'class', 'n.py')]
    assert review(pair(nodes, [contains()]), pair(py_extra, [contains()], analysis='6'), stage='b')['unexplained']
    assert review(pair(extra, [contains()]), pair(nodes, [contains()], analysis='6'), stage='b')['unexplained']


def test_V9_RV7_flag_rules():
    nodes_b = [node(CLS, 'class', start=1, end=9, flags=['dynamic_import']), node(MEM, 'method', flags=['dynamic_import'])]
    nodes_h = [node(CLS, 'class', start=1, end=9), node(MEM, 'method', flags=['dynamic_import'])]
    assert review(pair(nodes_b, [contains()]), pair(nodes_h, [contains()]))['unexplained'] == []
    lost_member = [node(CLS, 'class', start=1, end=9), node(MEM, 'method')]
    assert review(pair(nodes_b, [contains()]), pair(lost_member, [contains()]))['unexplained']
    gained = [node(CLS, 'class', start=1, end=9, flags=['dynamic_import']), node(MEM, 'method', flags=['dynamic_import', 'dynamic_eval'])]
    assert review(pair(nodes_b, [contains()]), pair(gained, [contains()]))['unexplained']


def test_V9_RV7_metadata_value_change_rules():
    plain = class_nodes()
    changed = [node(CLS, 'class', start=1, end=9, meta={'custom': 1}), node(MEM, 'method', start=2, end=2), node(TGT, 'class', 'b.kt', 1, 3)]
    assert review(pair(plain, [contains()]), pair(changed, [contains()]))['unexplained']


# ---------------------------------------------------------------- RV8

@pytest.mark.parametrize('path,expected', [
    ('src/main/Foo.kt', True), ('src/test/Foo.kt', False), ('tests/a.py', False), ('spec/a.rb', False),
    ('src/FooTest.kt', False), ('src/FooTests.kt', False), ('pkg/test_x.py', False), ('pkg/x_test.py', False),
    ('src/a.spec.ts', False), ('src/a.test.ts', False), ('src/contest/a.kt', True), ('src/latest.py', True)])
def test_V9_RV8_nontest_predicate(path, expected):
    assert rd.is_nontest(path) is expected


def test_V9_RV8_ratios_are_recorded_in_the_output():
    files = [node('file:src/a.kt', 'file', 'src/a.kt'), node('file:src/b.kt', 'file', 'src/b.kt'),
             node('file:tests/c.kt', 'file', 'tests/c.kt'), node('file:src/FooTest.kt', 'file', 'src/FooTest.kt')]
    cands = [candidate('u1', 'unresolved_boundary', 'file:src/a.kt'), candidate('u2', 'unresolved_boundary', 'file:tests/c.kt'),
             candidate('e1', 'evidence_spread', 'file:src/a.kt'), candidate('e2', 'evidence_spread', 'file:src/b.kt')]
    p = pair(files, [], cands, details=file_details())
    report = review(p, p, mode='file', symbol=(pair([], []), pair([], [])))
    share = report['nontest_share']['head']
    assert share['nontest_files'] == 2
    assert share['unresolved_boundary'] == {'files': 1, 'share': 0.5}
    assert share['evidence_spread'] == {'files': 2, 'share': 1.0}
    assert report['nontest_share']['base'] == share


def test_V9_RV8_structural_metric_change_needs_attributed_neighbourhood():
    nodes = class_nodes([node('kotlin:far.kt#Z', 'class', 'far.kt')])
    base = pair(nodes, [contains(), edge(CLS, TGT, 'CALLS'), edge(MEM, TGT, 'CALLS')], metrics={'kotlin:far.kt#Z': {'fan_in': 1}})
    head_near = pair(nodes, [contains(), edge(MEM, TGT, 'CALLS')], metrics={'kotlin:far.kt#Z': {'fan_in': 1}, TGT: {'fan_in': 2}})
    base_near = pair(nodes, [contains(), edge(CLS, TGT, 'CALLS'), edge(MEM, TGT, 'CALLS')], metrics={'kotlin:far.kt#Z': {'fan_in': 1}})
    assert review(base_near, head_near, name='android')['unexplained'] == []
    assert review(base_near, head_near, name='other')['unexplained']
    head_far = pair(nodes, [contains(), edge(MEM, TGT, 'CALLS')], metrics={'kotlin:far.kt#Z': {'fan_in': 5}})
    assert review(base, head_far, name='android')['unexplained']


def test_V9_RV8_stage_b_token_cost_only_on_constructor_fields():
    base = ctor_pair(False)
    head = ctor_pair(True)
    head[1]['dependency_network']['node_metrics'][F1]['token_cost'] = 7
    assert review(base, head, stage='b')['unexplained'] == []
    head[1]['dependency_network']['node_metrics'][CTOR_CLASS]['token_cost'] = 7
    assert any('token_cost changed' in u for u in review(base, head, stage='b')['unexplained'])


# ---------------------------------------------------------------- RV9

CFG = 'kotlin:a.kt#Cfg'
OTHER_CLASS, OF1 = 'kotlin:a.kt#D', 'kotlin:a.kt#D.z'


def retarget(to_head, line=3, extra_head_nodes=False):
    nodes_b, edges_b, _ = ctor_side(False, [edge(CFG, F1, 'CONFIGURES', line)])
    nodes_h, edges_h, _ = ctor_side(True, [edge(CFG, to_head, 'CONFIGURES', line)])
    cfg = node(CFG, 'class', start=20, end=22)
    other = [node(OTHER_CLASS, 'class', start=30, end=40), node(OF1, 'field', start=31, end=31, signature='val z: Int')]
    other_b = [node(OTHER_CLASS, 'class', start=30, end=40), node(OF1, 'field', start=30, end=32, signature='(val z: Int)')]
    own = [edge(OTHER_CLASS, OF1, 'CONTAINS', 31)]
    own_b = [edge(OTHER_CLASS, OF1, 'CONTAINS', 30)]
    base = pair(nodes_b + [cfg] + other_b, edges_b + own_b, analysis='5')
    head = pair(nodes_h + [cfg] + other, edges_h + own, analysis='6')
    return base, head


def test_V9_RV9_same_class_field_retarget_with_span_containing_evidence_is_explained():
    base, head = retarget(F2, line=3)
    assert review(base, head, stage='b')['unexplained'] == []


def test_V9_RV9_retarget_to_another_class_field_is_unexplained():
    base, head = retarget(OF1, line=31)
    assert any('CONFIGURES' in u for u in review(base, head, stage='b')['unexplained'])


def test_V9_RV9_head_span_not_containing_evidence_line_is_unexplained():
    base, head = retarget(F2, line=2)
    assert any('CONFIGURES' in u for u in review(base, head, stage='b')['unexplained'])


def test_V9_RV9_non_enrichment_relation_is_unexplained():
    nodes_b, edges_b, _ = ctor_side(False, [edge(CFG, F1, 'READS', 3)])
    nodes_h, edges_h, _ = ctor_side(True, [edge(CFG, F2, 'READS', 3)])
    cfg = node(CFG, 'class', start=20, end=22)
    base, head = pair(nodes_b + [cfg], edges_b), pair(nodes_h + [cfg], edges_h, analysis='6')
    assert review(base, head, stage='b')['unexplained']


def test_V9_RV9_pairs_are_consumed_one_to_one():
    nodes_b, edges_b, _ = ctor_side(False, [edge(CFG, F1, 'CONFIGURES', 3), edge(CFG, F1, 'CONFIGURES', 3)])
    nodes_h, edges_h, _ = ctor_side(True, [edge(CFG, F2, 'CONFIGURES', 3)])
    cfg = node(CFG, 'class', start=20, end=22)
    base, head = pair(nodes_b + [cfg], edges_b), pair(nodes_h + [cfg], edges_h, analysis='6')
    # two identical base edges collapse to one multiset key with count 2; only one is paired
    assert review(base, head, stage='b')['unexplained']


# ---------------------------------------------------------------- CLI and error handling

def _write(directory, name, mode, payload):
    directory.mkdir(exist_ok=True)
    (directory / f'{name}-{mode}.json').write_text(json.dumps(payload[0]))
    (directory / f'{name}-{mode}.b.json').write_text(json.dumps(payload[1]))


def _run(base, head, out, stage='a', mode='symbol', name='x'):
    return subprocess.run([sys.executable, str(EVIDENCE / 'review_diff.py'), str(base), str(head), name, mode, str(out), '--stage', stage],
                          capture_output=True, text=True)


def test_V9_cli_writes_report_with_stage_and_sorted_content(tmp_path):
    p = pair(class_nodes(), [contains(), edge(MEM, TGT)])
    _write(tmp_path / 'b', 'x', 'symbol', p)
    _write(tmp_path / 'h', 'x', 'symbol', p)
    result = _run(tmp_path / 'b', tmp_path / 'h', tmp_path / 'out.json')
    assert result.returncode == 0, result.stderr
    out = json.loads((tmp_path / 'out.json').read_text())
    assert out['stage'] == 'a' and out['unexplained'] == [] and 'nontest_share' in out


def test_V9_cli_missing_input_exits_non_zero_without_output(tmp_path):
    p = pair(class_nodes(), [contains()])
    _write(tmp_path / 'b', 'x', 'symbol', p)
    (tmp_path / 'h').mkdir()
    (tmp_path / 'h' / 'x-symbol.json').write_text(json.dumps(p[0]))
    result = _run(tmp_path / 'b', tmp_path / 'h', tmp_path / 'out.json')
    assert result.returncode != 0 and not (tmp_path / 'out.json').exists()


def test_V9_cli_requires_stage(tmp_path):
    result = subprocess.run([sys.executable, str(EVIDENCE / 'review_diff.py'), 'a', 'b', 'x', 'symbol', str(tmp_path / 'o.json')],
                            capture_output=True, text=True)
    assert result.returncode != 0 and not (tmp_path / 'o.json').exists()
