"""Evidence for spec 74b78d6823637a21 v1 (untested_hub / isolated_node). Expected values come from the spec text and
the reference functions in tests/reach_support.py (full sort, per-file edge scans), never from product output; the
only product values reused are the PageRank scores the spec orders by."""
import collections
import copy
import dataclasses
import html
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

import pytest

from analysis.edge_weights import EdgeWeightsError, default_edge_weights_path, load_edge_weights
from fixtures.registry import fixture_root
from language_analyzers.core.flags import path_flags
from tests.edge_weights_support import load_weights, weights_data, write_weights
from tests.reach_support import (AMBIGUOUS, BASE_COMMIT, CONFIDENCES, DR, E, EXACT, FI, FIXTURES, ISOLATION_EXTENSIONS, NEW_KINDS,
                                 REPO, SC, SI, UNIQUE, UNRESOLVED, Graph, architecture_model, candidate_id, canonical_sha,
                                 fid, graph_model, load_manifest, model_key, of_kind, pagerank_of, record_key, ref_incoming_tests, ref_isolated, ref_untested_hubs, run_report, weights_with, without_reach)

MAIN = 'from code_analyzer.cli import main; main()'
HUB_METRICS = {'pagerank', 'pagerank_rank', 'top_n', 'uncertain_test_edge_count'}
ISO_METRICS = {'line_count', 'framework_edge_count', 'dynamic_edge_count', 'uncertain_static_edge_count'}


def prod(*names, lines=3):
    return {name: ('production', lines) for name in names}


def files_of(**by_category):
    """files_of(production={'src/a.py': 3}, test={...}) -> Graph.files"""
    result = {}
    for category, members in by_category.items():
        for path, lines in members.items():
            result[path] = (category, lines)
    return result


# ------------------------------------------------------------------ shared reference comparison

def assert_candidates_match_reference(report, model, top_n, *, indexed_graph=None, isolation=True):
    """Both kinds against the independent references; rank is asserted wherever pool rank and global rank agree."""
    pagerank = pagerank_of(report)
    candidates = report['candidates']
    hubs = {c['target']: c for c in of_kind(candidates, 'untested_hub')}
    expected_hubs = ref_untested_hubs(model, pagerank, top_n)
    assert set(hubs) == set(expected_hubs), ('hub set', sorted(set(hubs) ^ set(expected_hubs)))
    for ident, (rank, uncertain) in expected_hubs.items():
        item = hubs[ident]
        assert set(item['metrics']) == HUB_METRICS and item['id'] == candidate_id(ident, 'untested_hub')
        assert item['coverage'] == 'static_analyzer_relation'
        assert item['evidence']['path'] == ident[len('file:'):] and set(item['evidence']) == {'path', 'uncertain_test_edges'}
        assert item['metrics']['top_n'] == top_n and item['metrics']['pagerank'] == pytest.approx(pagerank[ident], abs=1e-12, rel=0)
        assert item['metrics']['pagerank_rank'] == rank, ident
        assert item['metrics']['uncertain_test_edge_count'] == len(uncertain)
        assert item['metrics']['uncertain_test_edge_count'] == len(item['evidence']['uncertain_test_edges'])
        if True:
            observed = collections.Counter(record_key(r) for r in item['evidence']['uncertain_test_edges'])
            assert observed == collections.Counter(model_key(model.edges[i]) for i in uncertain)
            if indexed_graph is not None:
                assert sorted(i for r in item['evidence']['uncertain_test_edges'] for i in r['metadata']['detail_edge_indices']) == uncertain
    isolated = {c['target']: c for c in of_kind(candidates, 'isolated_node')}
    if not isolation:
        return hubs, isolated
    expected_isolated = ref_isolated(model)
    assert set(isolated) == set(expected_isolated), ('isolated set', sorted(set(isolated) ^ set(expected_isolated)))
    for ident, (framework, dynamic, uncertain, indices) in expected_isolated.items():
        item = isolated[ident]
        assert item['id'] == candidate_id(ident, 'isolated_node') and item['coverage'] == 'static_analyzer_relation'
        assert item['metrics'] == {'line_count': model.files[ident][1], 'framework_edge_count': framework,
                                   'dynamic_edge_count': dynamic, 'uncertain_static_edge_count': uncertain}
        assert set(item['evidence']) == {'path', 'edges'} and item['evidence']['path'] == ident[len('file:'):]
        assert collections.Counter(record_key(r) for r in item['evidence']['edges']) == collections.Counter(model_key(model.edges[i]) for i in indices)
        if indexed_graph is not None:
            assert sorted(i for r in item['evidence']['edges'] for i in r['metadata']['detail_edge_indices']) == indices
    keys = [(c['kind'], c['id']) for c in candidates]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    return hubs, isolated


def check(graph, tmp_path, top_n=None, isolation=True):
    report = run_report(graph, weights_with(tmp_path, **({} if top_n is None else {'untested_hub_top_n': top_n})))
    hubs, isolated = assert_candidates_match_reference(report, graph_model(graph), 10 if top_n is None else top_n, indexed_graph=graph, isolation=isolation)
    return report, hubs, isolated


def chain(k, **extra_files):
    """p0 -> p1 -> ... -> p(k-1): strictly increasing PageRank along the chain, i.e. descending id order of rank."""
    names = [f'src/p{i}.py' for i in range(k)]
    graph = Graph(files_of(production={n: 3 for n in names}, **extra_files),
                  [E(names[i], names[i + 1]) for i in range(k - 1)])
    return graph, names


def test_graph_builder_categories_agree_with_the_product_path_rules():
    expected = {'src/a.py': set(), 'tests/a.py': {'test'}, 'migrations/a.py': {'generated'}, 'vendor/a.py': {'vendored'}}
    assert {path: set(path_flags(path)) for path in expected} == expected


# =================================================================== V1 boundary value analysis: hub set

@pytest.mark.parametrize('delta', [-1, 0, 1], ids=['pool-1', 'pool', 'pool+1'])
def test_V1_R1_C1_top_n_three_value_boundary(tmp_path, delta):
    graph, names = chain(4)
    top_n = 4 + delta
    report, hubs, _ = check(graph, tmp_path, top_n)
    pagerank = pagerank_of(report)
    assert len({pagerank[fid(n)] for n in names}) == 4, 'the chain must give four distinct scores'
    by_score = sorted((fid(n) for n in names), key=lambda ident: -pagerank[ident])
    assert by_score == [fid(n) for n in reversed(names)]
    assert set(hubs) == set(by_score[:top_n])
    assert len(hubs) == min(top_n, 4)
    assert {t: h['metrics']['pagerank_rank'] for t, h in hubs.items()} == {t: by_score.index(t) + 1 for t in by_score[:top_n]}


def test_V1_R1_pool_is_production_non_boundary_only(tmp_path):
    graph, names = chain(3, test={'tests/t.py': 2}, vendored={'vendor/v.py': 2}, generated={'migrations/g.py': 2})
    graph.boundary = ('ext:lib',)
    graph.edges += [E(n, extra) for n in names for extra in ('vendor/v.py', 'migrations/g.py', 'ext:lib')]
    graph.edges.append(E('tests/t.py', 'vendor/v.py'))
    report, hubs, _ = check(graph, tmp_path, 3)
    assert set(hubs) == {fid(n) for n in names}
    report, hubs, _ = check(graph, tmp_path, 2)
    pagerank = pagerank_of(report)
    assert set(hubs) == set(sorted((fid(n) for n in names), key=lambda i: (-pagerank[i], i))[:2])
    for outsider in ('tests/t.py', 'vendor/v.py', 'migrations/g.py', 'ext:lib'):
        assert all(h['target'] != outsider and h['target'] != fid(outsider) for h in of_kind(report['candidates'], 'untested_hub'))


@pytest.mark.parametrize('order', ['small-id-first', 'large-id-first'])
@pytest.mark.parametrize('names', [('src/a.py', 'src/b.py'), ('src/10.py', 'src/9.py')], ids=['alpha', 'string-not-numeric'])
def test_V1_C3_tie_prefers_smaller_id_at_the_cut(tmp_path, names, order):
    small, large = sorted(names, key=fid)
    graph = Graph(prod(*((small, large) if order == 'small-id-first' else (large, small))))
    report, hubs, _ = check(graph, tmp_path, 1)
    pagerank = pagerank_of(report)
    assert pagerank[fid(small)] == pagerank[fid(large)], 'the two files must tie exactly'
    assert set(hubs) == {fid(small)}
    assert hubs[fid(small)]['metrics']['pagerank_rank'] == 1


@pytest.mark.parametrize('order', ['small-id-first', 'large-id-first'])
def test_V1_C3_tie_below_a_strictly_better_hub(tmp_path, order):
    tied = ['src/b.py', 'src/c.py', 'src/w.py'] if order == 'small-id-first' else ['src/w.py', 'src/c.py', 'src/b.py']
    graph = Graph(files_of(production={'src/z_top.py': 3, **{m: 3 for m in tied}}), [E('src/b.py', 'src/z_top.py')])
    report, hubs, _ = check(graph, tmp_path, 2)
    pagerank = pagerank_of(report)
    assert pagerank[fid('src/c.py')] == pagerank[fid('src/w.py')] < pagerank[fid('src/z_top.py')]
    ordered = sorted((fid(n) for n in tied + ['src/z_top.py']), key=lambda i: (-pagerank[i], i))
    assert set(hubs) == set(ordered[:2])
    assert fid('src/z_top.py') in hubs


def test_V1_C2_pool_smaller_than_n_is_not_an_error(tmp_path):
    graph = Graph(prod('src/only.py'))
    report, hubs, _ = check(graph, tmp_path)
    assert set(hubs) == {fid('src/only.py')} and hubs[fid('src/only.py')]['metrics']['top_n'] == 10
    assert hubs[fid('src/only.py')]['metrics']['pagerank_rank'] == 1


def test_V1_C1_tested_second_ranked_hub_is_the_only_untested_one(tmp_path):
    """C1: three production files, the first-ranked one is tested through an exact TESTS edge, N=2."""
    graph, names = chain(3, test={'tests/test_top.py': 2})
    graph.edges.append(E('tests/test_top.py', names[2], 'TESTS'))
    report, hubs, _ = check(graph, tmp_path, 2)
    pagerank = pagerank_of(report)
    assert pagerank[fid(names[2])] > pagerank[fid(names[1])] > pagerank[fid(names[0])]
    assert set(hubs) == {fid(names[1])}
    assert hubs[fid(names[1])]['metrics']['pagerank_rank'] == 2
    assert hubs[fid(names[1])]['metrics']['uncertain_test_edge_count'] == 0


# =================================================================== V2 decision table: untested hub

HUB = 'src/h.py'
V2_EDGES = {
    'none': lambda origin: [],
    'exact': lambda origin: [E(origin, HUB, 'TESTS', SC, EXACT)],
    'unique_name': lambda origin: [E(origin, HUB, 'TESTS', SC, UNIQUE)],
    'ambiguous-to-id': lambda origin: [E(origin, HUB, 'TESTS', SC, AMBIGUOUS, candidates=('src/o.py',))],
    'ambiguous-candidate': lambda origin: [E(origin, 'src/o.py', 'TESTS', SC, AMBIGUOUS, candidates=(HUB,))],
    'unresolved': lambda origin: [E(origin, HUB, 'TESTS', SC, UNRESOLVED)],
}
# (candidate exists, uncertain_test_edge_count), written from R2/R3 (v3: only test-category origins count)
V2_TABLE = {
    ('none', 'test'): (True, 0), ('none', 'production'): (True, 0),
    ('exact', 'test'): (False, None), ('exact', 'production'): (True, 0),
    ('unique_name', 'test'): (False, None), ('unique_name', 'production'): (True, 0),
    ('ambiguous-to-id', 'test'): (True, 1), ('ambiguous-to-id', 'production'): (True, 0),
    ('ambiguous-candidate', 'test'): (True, 1), ('ambiguous-candidate', 'production'): (True, 0),
    ('unresolved', 'test'): (True, 1), ('unresolved', 'production'): (True, 0),
}


@pytest.mark.parametrize('rule', sorted(V2_TABLE), ids=lambda rule: f'{rule[0]}-from-{rule[1]}')
def test_V2_R2_R3_decision_table(tmp_path, rule):
    kind, origin_category = rule
    origin = 'tests/test_h.py' if origin_category == 'test' else 'src/caller.py'
    graph = Graph(files_of(production={HUB: 3, 'src/o.py': 3, 'src/caller.py': 3}, test={'tests/test_h.py': 2}), V2_EDGES[kind](origin))
    report, hubs, _ = check(graph, tmp_path)
    exists, count = V2_TABLE[rule]
    assert (fid(HUB) in hubs) == exists
    if exists and count is not None:
        item = hubs[fid(HUB)]
        assert item['metrics']['uncertain_test_edge_count'] == count
        assert len(item['evidence']['uncertain_test_edges']) == count
        for record in item['evidence']['uncertain_test_edges']:
            assert record['relation'] == 'TESTS' and record['resolution'] in (AMBIGUOUS, UNRESOLVED)
            assert record['from_id'] == fid(origin)


def test_V2_R3_uncertain_edges_are_counted_not_flagged(tmp_path):
    """Supplementary: a constant 1 or boolean would pass the single-edge rules."""
    graph = Graph(files_of(production={HUB: 3, 'src/o.py': 3}, test={'tests/t1.py': 2, 'tests/t2.py': 2, 'tests/t3.py': 2}),
                  [E('tests/t1.py', HUB, 'TESTS', SC, AMBIGUOUS), E('tests/t2.py', 'src/o.py', 'TESTS', SC, AMBIGUOUS, candidates=(HUB,)),
                   E('tests/t3.py', HUB, 'TESTS', SC, UNRESOLVED)])
    _, hubs, _ = check(graph, tmp_path)
    assert hubs[fid(HUB)]['metrics']['uncertain_test_edge_count'] == 3
    assert hubs[fid('src/o.py')]['metrics']['uncertain_test_edge_count'] == 1   # t2's to_id


def test_V2_R2_confirmed_edge_wins_over_uncertain_edges(tmp_path):
    graph = Graph(files_of(production={HUB: 3}, test={'tests/t1.py': 2, 'tests/t2.py': 2}),
                  [E('tests/t1.py', HUB, 'TESTS', SC, AMBIGUOUS), E('tests/t2.py', HUB, 'TESTS', SC, UNIQUE)])
    _, hubs, _ = check(graph, tmp_path)
    assert fid(HUB) not in hubs


@pytest.mark.parametrize('confidence', [SC, SI, FI, DR])
@pytest.mark.parametrize('resolution', [EXACT, UNIQUE])
def test_V2_R2_v2_confirmed_edge_ignores_confidence(tmp_path, confidence, resolution):
    graph = Graph(files_of(production={HUB: 3}, test={'tests/t.py': 2}), [E('tests/t.py', HUB, 'TESTS', confidence, resolution)])
    _, hubs, _ = check(graph, tmp_path)
    assert fid(HUB) not in hubs


def candidates_rows():
    # (label, edge builder, hub candidate exists, hub uncertain count); candidates are honoured only for `ambiguous`
    return [
        ('exact-with-hub-in-candidates', E('tests/test_h.py', 'src/o.py', 'TESTS', SC, EXACT, candidates=(HUB,)), True, 0),
        ('unique-with-hub-in-candidates', E('tests/test_h.py', 'src/o.py', 'TESTS', SC, UNIQUE, candidates=(HUB,)), True, 0),
        ('unresolved-with-hub-in-candidates', E('tests/test_h.py', 'src/o.py', 'TESTS', SC, UNRESOLVED, candidates=(HUB,)), True, 0),
        ('exact-to-hub-with-other-candidates', E('tests/test_h.py', HUB, 'TESTS', SC, EXACT, candidates=('src/o.py',)), False, None),
        ('unresolved-to-hub-with-other-candidates', E('tests/test_h.py', HUB, 'TESTS', SC, UNRESOLVED, candidates=('src/o.py',)), True, 1),
        ('ambiguous-to-other-hub-in-candidates', E('tests/test_h.py', 'src/o.py', 'TESTS', SC, AMBIGUOUS, candidates=(HUB,)), True, 1),
        ('imports-edge-not-tests', E('tests/test_h.py', HUB, 'IMPORTS', SC, EXACT), True, 0),
        ('tests-edge-reverse-direction', E(HUB, 'tests/test_h.py', 'TESTS', SC, EXACT), True, 0),
    ]


@pytest.mark.parametrize('row', candidates_rows(), ids=lambda r: r[0])
def test_V2_R2_R3_candidates_only_count_for_ambiguous_and_only_tests_edges_into_the_hub(tmp_path, row):
    _, edge, exists, count = row
    graph = Graph(files_of(production={HUB: 3, 'src/o.py': 3}, test={'tests/test_h.py': 2}), [edge])
    _, hubs, _ = check(graph, tmp_path)
    assert (fid(HUB) in hubs) == exists
    if exists:
        assert hubs[fid(HUB)]['metrics']['uncertain_test_edge_count'] == count
        assert len(hubs[fid(HUB)]['evidence']['uncertain_test_edges']) == count


def test_V2_R2_confirmation_is_per_file(tmp_path):
    graph = Graph(files_of(production={HUB: 3, 'src/o.py': 3}, test={'tests/t.py': 2}), [E('tests/t.py', 'src/o.py', 'TESTS', SC, EXACT)])
    _, hubs, _ = check(graph, tmp_path)
    assert set(hubs) == {fid(HUB)}


# =================================================================== V3 decision table: isolated node

A = 'src/a.py'
COUNTERPARTS = {
    'production': ('production', 'src/b.py'), 'test': ('test', 'tests/test_b.py'), 'generated': ('generated', 'migrations/g.py'),
    'vendored': ('vendored', 'vendor/v.py'), 'boundary': (None, 'ext:lib'), 'self': (None, A),
}


def v3_graph(counterpart, confidence, resolution, direction='out'):
    category, path = COUNTERPARTS[counterpart]
    files = {A: ('production', 3)}
    boundary = ()
    if counterpart == 'boundary':
        boundary = (path,)
    elif counterpart != 'self':
        files[path] = (category, 2)
    edge = E(A, path, 'IMPORTS', confidence, resolution) if direction == 'out' else E(path, A, 'IMPORTS', confidence, resolution)
    return Graph(files, [edge], boundary)


def v3_expected(counterpart, confidence, resolution):
    """(isolated, framework, dynamic, uncertain) for one edge between A and the counterpart, from R5/R6."""
    production = counterpart == 'production'
    connected = production and confidence in (SC, SI) and resolution == EXACT
    return (not connected,
            int(production and confidence == FI), int(production and confidence == DR),
            int(production and confidence in (SC, SI) and resolution == AMBIGUOUS))


V3_RULES = [(cp, conf, res, 'out') for cp in COUNTERPARTS for conf in CONFIDENCES for res in (EXACT, AMBIGUOUS)]
V3_RULES += [('production', SC, EXACT, 'in'), ('production', SC, EXACT, 'out')]


@pytest.mark.parametrize('rule', V3_RULES, ids=lambda r: '-'.join(r))
def test_V3_R4_R5_R6_decision_table(tmp_path, rule):
    counterpart, confidence, resolution, direction = rule
    graph = v3_graph(counterpart, confidence, resolution, direction)
    _, _, isolated = check(graph, tmp_path)
    isolated_expected, framework, dynamic, uncertain = v3_expected(counterpart, confidence, resolution)
    assert (fid(A) in isolated) == isolated_expected
    if isolated_expected:
        item = isolated[fid(A)]
        assert item['metrics'] == {'line_count': 3, 'framework_edge_count': framework, 'dynamic_edge_count': dynamic,
                                   'uncertain_static_edge_count': uncertain}
        assert len(item['evidence']['edges']) == framework + dynamic + uncertain


def test_V3_direction_does_not_change_isolation_for_any_confidence_resolution(tmp_path):
    """Supplementary: R5 says direction-independent; the table fixes direction only for one rule."""
    for confidence in CONFIDENCES:
        for resolution in (EXACT, AMBIGUOUS):
            seen = {}
            for direction in ('in', 'out'):
                _, _, isolated = check(v3_graph('production', confidence, resolution, direction), tmp_path)
                seen[direction] = {k: v['metrics'] for k, v in isolated.items() if k == fid(A)}
            assert seen['in'] == seen['out'], (confidence, resolution)


@pytest.mark.parametrize('confidence', [SC, SI])
@pytest.mark.parametrize('resolution,connects', [(UNIQUE, True), (UNRESOLVED, False)])
def test_V3_R5_remaining_resolutions_supplementary(tmp_path, confidence, resolution, connects):
    _, _, isolated = check(v3_graph('production', confidence, resolution), tmp_path)
    assert (fid(A) in isolated) == (not connects)
    if not connects:
        assert isolated[fid(A)]['metrics']['uncertain_static_edge_count'] == 1


B, C = 'src/b.py', 'src/c.py'
TEST_F, VEND, EXT = 'tests/test_t.py', 'vendor/v.py', 'ext:lib'
# (label, edges, expected A: (isolated, framework, dynamic, uncertain)) from R5/R6 + candidate_targets
CANDIDATE_ROWS = [
    ('ambiguous-to-test-candidate-prod', [E(A, TEST_F, 'IMPORTS', SC, AMBIGUOUS, candidates=(B,))], (True, 0, 0, 1)),
    ('ambiguous-to-prod-candidate-test', [E(A, B, 'IMPORTS', SC, AMBIGUOUS, candidates=(TEST_F,))], (True, 0, 0, 1)),
    ('ambiguous-to-boundary-candidate-prod', [E(A, EXT, 'IMPORTS', SC, AMBIGUOUS, candidates=(B,))], (True, 0, 0, 1)),
    ('ambiguous-to-vendored-candidate-prod', [E(A, VEND, 'IMPORTS', SI, AMBIGUOUS, candidates=(B,))], (True, 0, 0, 1)),
    ('ambiguous-to-vendored-candidate-test', [E(A, VEND, 'IMPORTS', SC, AMBIGUOUS, candidates=(TEST_F,))], (True, 0, 0, 0)),
    ('reverse-ambiguous-prod-source-test-to-candidate-A', [E(B, TEST_F, 'IMPORTS', SC, AMBIGUOUS, candidates=(A,))], (True, 0, 0, 1)),
    ('reverse-ambiguous-test-source-candidate-A', [E(TEST_F, B, 'IMPORTS', SC, AMBIGUOUS, candidates=(A,))], (True, 0, 0, 0)),
    ('reverse-ambiguous-boundary-source-candidate-A', [E(EXT, B, 'IMPORTS', SC, AMBIGUOUS, candidates=(A,))], (True, 0, 0, 0)),
    ('exact-to-test-with-prod-candidates', [E(A, TEST_F, 'IMPORTS', SC, EXACT, candidates=(B,))], (True, 0, 0, 0)),
    ('exact-to-prod-with-other-prod-candidates', [E(A, B, 'IMPORTS', SC, EXACT, candidates=(C,))], (False, 0, 0, 0)),
    ('exact-reverse-test-source-prod-candidates', [E(TEST_F, B, 'IMPORTS', SC, EXACT, candidates=(A,))], (True, 0, 0, 0)),
    ('unique-name-to-test-with-prod-candidates', [E(A, TEST_F, 'IMPORTS', SC, UNIQUE, candidates=(B,))], (True, 0, 0, 0)),
    ('unresolved-to-test-with-prod-candidates', [E(A, TEST_F, 'IMPORTS', SC, UNRESOLVED, candidates=(B,))], (True, 0, 0, 0)),
    ('unresolved-to-prod-with-test-candidates', [E(A, B, 'IMPORTS', SC, UNRESOLVED, candidates=(TEST_F,))], (True, 0, 0, 1)),
    ('framework-ambiguous-candidate-prod', [E(A, TEST_F, 'IMPORTS', FI, AMBIGUOUS, candidates=(B,))], (True, 1, 0, 0)),
    ('dynamic-exact-with-prod-candidates-to-test', [E(A, TEST_F, 'IMPORTS', DR, EXACT, candidates=(B,))], (True, 0, 0, 0)),
    ('ambiguous-static-never-connects-even-with-two-prod-candidates', [E(A, B, 'IMPORTS', SC, AMBIGUOUS, candidates=(C,))], (True, 0, 0, 1)),
]


@pytest.mark.parametrize('row', CANDIDATE_ROWS, ids=lambda r: r[0])
def test_V3_R5_R6_candidate_targets_rule(tmp_path, row):
    _, edges, (isolated_expected, framework, dynamic, uncertain) = row
    graph = Graph(files_of(production={A: 3, B: 3, C: 3}, test={TEST_F: 2}, vendored={VEND: 2}), edges, boundary=(EXT,))
    _, _, isolated = check(graph, tmp_path)
    assert (fid(A) in isolated) == isolated_expected
    if isolated_expected:
        item = isolated[fid(A)]['metrics']
        assert (item['framework_edge_count'], item['dynamic_edge_count'], item['uncertain_static_edge_count']) == (framework, dynamic, uncertain)


# ---- V4 / R4: cost.line_count is the source of eligibility and of the metric, independent of span and content
@pytest.mark.parametrize('content,cost,eligible', [(3, 0, False), (3, 5, True), (3, 1, True), (1, 7, True), (1, 0, False)],
                         ids=['cost0-content3', 'cost5-content3', 'cost1-content3', 'cost7-content1', 'cost0-content1'])
def test_V4_R4_cost_line_count_is_the_eligibility_and_metric_source(tmp_path, content, cost, eligible):
    graph = Graph({'src/a.py': ('production', content, cost)})
    _, _, isolated = check(graph, tmp_path)
    assert (fid('src/a.py') in isolated) == eligible
    if eligible:
        assert isolated[fid('src/a.py')]['metrics']['line_count'] == cost


# ---- V14 / Errors 2
def _unknown_endpoint(which):
    graph = Graph(files_of(production={A: 3, B: 3}), [E(A, B, 'IMPORTS', SC, AMBIGUOUS, candidates=(B,))])
    snap, arch = graph.snapshot_and_architecture()
    edge = arch.edges[0]
    if which == 'from_id':
        edge.from_id = 'file:src/ghost.py'
    elif which == 'to_id':
        edge.to_id = 'file:src/ghost.py'
    else:
        edge.candidates = ['file:src/ghost.py']
    return snap, arch


@pytest.mark.parametrize('which', ['from_id', 'to_id', 'candidates'])
def test_V14_unknown_edge_reference_raises_bottleneck_input_error(tmp_path, which):
    from bottlenecks import BottleneckInputError, analyze_bottlenecks
    snap, arch = _unknown_endpoint(which)
    with pytest.raises(BottleneckInputError):
        analyze_bottlenecks(snap, arch, weights_with(tmp_path))


def test_V14_the_same_graph_without_the_unknown_reference_succeeds(tmp_path):
    from bottlenecks import analyze_bottlenecks
    graph = Graph(files_of(production={A: 3, B: 3}), [E(A, B, 'IMPORTS', SC, AMBIGUOUS, candidates=(B,))])
    snap, arch = graph.snapshot_and_architecture()
    assert analyze_bottlenecks(snap, arch, weights_with(tmp_path)) is not None


def test_V3_one_certain_connection_among_noise_removes_the_candidate(tmp_path):
    graph = Graph(files_of(production={A: 3, 'src/b.py': 3, 'src/c.py': 3}, test={'tests/t.py': 2}),
                  [E(A, 'src/b.py', 'IMPORTS', FI, EXACT), E('tests/t.py', A, 'TESTS'), E('src/c.py', A, 'IMPORTS', SC, EXACT)])
    _, _, isolated = check(graph, tmp_path)
    assert fid(A) not in isolated


def test_V3_counts_accumulate_per_edge(tmp_path):
    graph = Graph(files_of(production={A: 3, 'src/b.py': 3, 'src/c.py': 3}),
                  [E(A, 'src/b.py', 'CALLS', FI, EXACT), E('src/c.py', A, 'CALLS', FI, EXACT), E(A, 'src/b.py', 'IMPORTS', DR, EXACT),
                   E('src/b.py', A, 'CALLS', DR, UNRESOLVED), E('src/c.py', A, 'IMPORTS', SI, AMBIGUOUS), E(A, 'src/c.py', 'IMPORTS', SC, UNRESOLVED),
                   E(A, 'src/c.py', 'IMPORTS', SC, AMBIGUOUS)])
    _, _, isolated = check(graph, tmp_path)
    assert isolated[fid(A)]['metrics'] == {'line_count': 3, 'framework_edge_count': 2, 'dynamic_edge_count': 2, 'uncertain_static_edge_count': 3}
    assert len(isolated[fid(A)]['evidence']['edges']) == 7


# =================================================================== V4 equivalence partitioning: eligibility

EXTENSIONS = ['py', 'ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs', 'kt', 'yaml', 'md']
CATEGORY_PATH = {'production': 'src/a', 'test': 'tests/a', 'generated': 'migrations/a', 'vendored': 'vendor/a'}


def v4_case(extension='py', lines=3, category='production'):
    return Graph({f'{CATEGORY_PATH[category]}.{extension}': (category, lines)})


def v4_expected(extension, lines, category):
    return category == 'production' and lines >= 1 and extension in {'py', 'ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs', 'kt'}


V4_CASES = ([('extension', ext, 3, 'production') for ext in EXTENSIONS] + [('line_count', 'py', n, 'production') for n in (0, 1)]
            + [('category', 'py', 3, cat) for cat in CATEGORY_PATH])


@pytest.mark.parametrize('case', V4_CASES, ids=lambda c: f'{c[0]}={c[1] if c[0] == "extension" else c[2] if c[0] == "line_count" else c[3]}')
def test_V4_R4_C10_partitions(tmp_path, case):
    _, extension, lines, category = case
    graph = v4_case(extension, lines, category)
    _, _, isolated = check(graph, tmp_path)
    (path,) = graph.files
    assert (fid(path) in isolated) == v4_expected(extension, lines, category)
    assert set(ISOLATION_EXTENSIONS) == {'py', 'ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs', 'kt'}
    if fid(path) in isolated:
        assert isolated[fid(path)]['metrics']['line_count'] == lines


@pytest.mark.parametrize('lines', [1, 2, 57])
def test_V4_line_count_metric_is_the_file_line_count(tmp_path, lines):
    _, _, isolated = check(v4_case('py', lines), tmp_path)
    assert isolated[fid('src/a.py')]['metrics']['line_count'] == lines


# =================================================================== V5 candidate id and order

def test_V5_R7_id_format_order_and_both_kinds_on_one_file(tmp_path):
    graph = Graph(files_of(production={'src/solo.py': 3, 'src/z.py': 2, 'src/y.py': 4, 'src/x.py': 5},
                           test={'tests/t.py': 2}),
                  [E('src/x.py', 'src/y.py'), E('tests/t.py', 'src/y.py', 'TESTS')])
    report, hubs, isolated = check(graph, tmp_path)
    candidates = [c for c in report['candidates'] if c['kind'] in NEW_KINDS]
    assert fid('src/solo.py') in hubs and fid('src/solo.py') in isolated, 'one file carries both kinds'
    assert len(candidates) == len(hubs) + len(isolated) >= 5
    for item in candidates:
        assert re.fullmatch(r'b:[0-9a-f]{16}', item['id'])
        assert item['id'] == candidate_id(item['target'], item['kind'])
    assert hubs[fid('src/solo.py')]['id'] != isolated[fid('src/solo.py')]['id']
    keys = [(c['kind'], c['id']) for c in report['candidates']]
    assert keys == sorted(keys)
    assert [c['kind'] for c in candidates] == sorted(c['kind'] for c in candidates)
    assert collections.Counter(c['kind'] for c in report['candidates'])['isolated_node'] == len(isolated)


def test_V5_ids_are_stable_across_runs_and_input_order(tmp_path):
    base = Graph(files_of(production={'src/a.py': 3, 'src/b.py': 2, 'src/c.py': 4}), [E('src/a.py', 'src/b.py', 'IMPORTS', FI, EXACT)])
    shuffled = Graph(dict(reversed(list(base.files.items()))), list(base.edges))
    first = [(c['kind'], c['id']) for c in run_report(base, weights_with(tmp_path))['candidates'] if c['kind'] in NEW_KINDS]
    again = [(c['kind'], c['id']) for c in run_report(shuffled, weights_with(tmp_path))['candidates'] if c['kind'] in NEW_KINDS]
    assert first == again and first


# =================================================================== V6 configuration

KEY = 'untested_hub_top_n'


@pytest.mark.parametrize('label,value,error', [
    ('zero', 0, True), ('one', 1, False), ('two', 2, False), ('minus-one', -1, True),
    ('bool-true', True, True), ('string-3', '3', True), ('float-1.0', 1.0, True),
])
def test_V6_R8_C12_values(tmp_path, label, value, error):
    data = weights_data(**{KEY: value})
    if error:
        with pytest.raises(EdgeWeightsError, match=KEY):
            load_weights(tmp_path, data)
    else:
        assert load_weights(tmp_path, data).untested_hub_top_n == value


def test_V6_R8_C13_absent_key_defaults_to_ten_and_is_echoed(tmp_path):
    data = weights_data()
    assert KEY not in data
    weights = load_weights(tmp_path, data)
    assert weights.untested_hub_top_n == 10
    graph = Graph(prod('src/a.py'))
    assert run_report(graph, weights)['edge_weights'][KEY] == 10


def test_V6_R8_present_key_is_echoed_in_output(tmp_path):
    graph = Graph(prod('src/a.py'))
    assert run_report(graph, weights_with(tmp_path, **{KEY: 7}))['edge_weights'][KEY] == 7


def test_V6_R8_default_profile_still_loads_with_default_ten():
    weights = load_edge_weights(default_edge_weights_path())
    assert weights.untested_hub_top_n == 10
    assert weights.large_node_line_threshold == 2000


def test_V6_R8_other_edge_weight_keys_are_still_required_and_extra_keys_rejected(tmp_path):
    for missing in ('id', 'version', 'confidence', 'resolution', 'large_node_line_threshold'):
        data = weights_data()
        del data[missing]
        with pytest.raises(EdgeWeightsError):
            load_weights(tmp_path, data)
    with pytest.raises(EdgeWeightsError):
        load_weights(tmp_path, weights_data(unknown_key=1))


def tiny_project(directory):
    project = directory / 'project'
    project.mkdir()
    (project / 'a.py').write_text('x = 1\n', encoding='utf-8')
    return project


def run_cli(directory, project, weights_path, tag):
    out = directory / tag
    out.mkdir()
    command = [sys.executable, '-c', MAIN, str(project), '-l', 'python', '--edge-weights', str(weights_path),
               '-o', str(out / 'r.html'), '--bottlenecks', str(out / 'b.json')]
    done = subprocess.run(command, cwd=REPO, capture_output=True, text=True)
    return done, out


@pytest.mark.parametrize('value', [0, -1, True, '3', 1.0], ids=['zero', 'minus-one', 'true', 'string', 'float'])
def test_V6_C12_cli_rejects_like_other_config_errors_and_writes_nothing(tmp_path, value):
    project = tiny_project(tmp_path)
    reference_path = write_weights(tmp_path, weights_data(large_node_line_threshold=0), 'existing-error.yaml')
    reference, _ = run_cli(tmp_path, project, reference_path, 'ref')
    assert reference.returncode != 0
    bad_path = write_weights(tmp_path, weights_data(**{KEY: value}), 'bad.yaml')
    done, out = run_cli(tmp_path, project, bad_path, 'bad')
    assert done.returncode == reference.returncode
    assert KEY in done.stderr
    assert list(out.iterdir()) == []


def test_V6_cli_accepts_existing_style_yaml_without_the_key(tmp_path):
    project = tiny_project(tmp_path)
    path = write_weights(tmp_path, weights_data(), 'old.yaml')
    done, out = run_cli(tmp_path, project, path, 'ok')
    assert done.returncode == 0, done.stderr[-1000:]
    assert json.loads((out / 'b.json').read_text(encoding='utf-8'))['edge_weights'][KEY] == 10


# =================================================================== fixtures: shared pipeline

class Pipeline:
    def __init__(self, name, directory):
        self.name, self.directory, self.cache = name, directory, {}

    def output(self, granularity, seed='0', extra=(), tag=None):
        key = (granularity, seed, tuple(extra), tag)
        if key not in self.cache:
            target = self.directory / f'{granularity}-{seed}-{len(self.cache)}'
            target.mkdir()
            command = [sys.executable, '-c', MAIN, str(fixture_root(self.name).resolve()), *load_manifest()['commands'][self.name],
                       '--granularity', granularity, '-o', str(target / 'report.html'), '--bottlenecks', str(target / 'b.json'), *extra]
            done = subprocess.run(command, cwd=REPO, env=dict(os.environ, PYTHONHASHSEED=seed), capture_output=True, text=True)
            assert done.returncode == 0, done.stderr[-2000:]
            self.cache[key] = (target / 'b.json').read_bytes()
        return self.cache[key]

    def payload(self, granularity='file', **kwargs):
        return json.loads(self.output(granularity, **kwargs))


@pytest.fixture(scope='module', params=FIXTURES)
def pipe(request, tmp_path_factory):
    return Pipeline(request.param, tmp_path_factory.mktemp(request.param))


def capture_inputs(name, directory):
    import code_analyzer.cli as cli
    seen = {}
    original = cli.analyze_bottlenecks

    def spy(snapshot, arch, weights, *args, **kwargs):
        seen.update(snapshot=snapshot, arch=copy.deepcopy(arch), weights=weights)
        return original(snapshot, arch, weights, *args, **kwargs)

    argv = ['code-analyzer', str(fixture_root(name).resolve()), *load_manifest()['commands'][name], '--granularity', 'file',
            '-o', str(directory / 'report.html'), '--bottlenecks', str(directory / 'b.json')]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cli, 'analyze_bottlenecks', spy)
        patch.setattr(sys, 'argv', argv)
        cli.main()
    assert seen, 'the CLI must reach analyze_bottlenecks in file mode'
    return seen


@pytest.fixture(scope='module')
def inputs(pipe, tmp_path_factory):
    return capture_inputs(pipe.name, tmp_path_factory.mktemp('inproc-' + pipe.name))


def analyze_again(inputs, tmp_path, top_n, arch=None, snapshot=None):
    """Re-runs the product analysis on (a modified copy of) the captured file architecture, recomputing metrics."""
    from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
    arch = copy.deepcopy(inputs['arch'] if arch is None else arch)
    arch.stats.pop('analysis', None)
    weights = load_weights(tmp_path, weights_data(**{KEY: top_n}))
    return json.loads(bottlenecks_to_json(analyze_bottlenecks(inputs['snapshot'] if snapshot is None else snapshot, arch, weights)))


# =================================================================== V7 compatibility with base_commit

def test_V7_manifest_is_for_the_declared_base_commit():
    manifest = load_manifest()
    assert manifest['base_commit'] == BASE_COMMIT
    assert set(manifest['fixtures']) == set(FIXTURES)


def test_V7_R9_C14_file_output_equals_base_after_dropping_the_new_kinds(pipe):
    payload = pipe.payload('file')
    expected = load_manifest()['fixtures'][pipe.name]['file']
    assert payload['schema'] == 'bottlenecks.v8' == expected['schema']
    assert payload['edge_weights'][KEY] == 10
    assert {c['kind'] for c in payload['candidates']} - set(NEW_KINDS) == set(expected['candidate_kinds'])
    stripped = without_reach(payload)
    assert set(stripped) == set(expected['sections'])
    differing = sorted(key for key, value in stripped.items() if canonical_sha(value) != expected['sections'][key])
    assert differing == [], f'{pipe.name}: sections differ from base_commit: {differing}'
    assert len(stripped['candidates']) == expected['candidate_count']
    assert canonical_sha(stripped) == expected['canonical']


def test_V7_R9_C14_new_kinds_are_only_the_two_declared_ones_and_carry_the_declared_shape(pipe):
    payload = pipe.payload('file')
    kinds = {c['kind'] for c in payload['candidates']}
    assert kinds <= set(load_manifest()['fixtures'][pipe.name]['file']['candidate_kinds']) | set(NEW_KINDS)
    keys = [(c['kind'], c['id']) for c in payload['candidates']]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    for item in payload['candidates']:
        if item['kind'] in NEW_KINDS:
            assert set(item) == {'id', 'kind', 'target', 'metrics', 'evidence', 'coverage', 'status'}
            assert item['coverage'] == 'static_analyzer_relation'


def test_V7_R9_C15_symbol_output_is_byte_identical_to_base(pipe):
    data = pipe.output('symbol')
    expected = load_manifest()['fixtures'][pipe.name]['symbol']
    payload = json.loads(data)
    assert payload['schema'] == expected['schema']
    assert not {c['kind'] for c in payload['candidates']} & set(NEW_KINDS)
    assert len(data) == expected['bytes']
    import hashlib
    assert hashlib.sha256(data).hexdigest() == expected['sha256']


def test_V7_Q3_delta_with_itself_as_baseline_equals_base(tmp_path_factory):
    expected = load_manifest()['delta']
    pipe = Pipeline(expected['fixture'], tmp_path_factory.mktemp('delta'))
    first = pipe.directory / 'baseline.json'
    first.write_bytes(pipe.output('file'))
    payload = json.loads(pipe.output('file', extra=['--baseline', str(first)], tag='delta'))
    assert canonical_sha(payload['delta']) == expected['delta']
    stripped = without_reach(payload)
    assert sorted(k for k, v in stripped.items() if canonical_sha(v) != expected['sections'][k]) == []
    assert payload['delta']['counts'] == {key: 0 for key in payload['delta']['counts']}


def test_V7_base_candidate_kinds_are_unchanged_when_baseline_has_no_new_kinds(tmp_path_factory):
    """Compatibility of older baselines: a baseline produced without the new kinds is still accepted."""
    expected = load_manifest()['delta']
    pipe = Pipeline(expected['fixture'], tmp_path_factory.mktemp('old-baseline'))
    baseline = pipe.payload('file')
    baseline['candidates'] = [c for c in baseline['candidates'] if c['kind'] not in NEW_KINDS]
    baseline['edge_weights'].pop(KEY)
    path = pipe.directory / 'old.json'
    path.write_text(json.dumps(baseline), encoding='utf-8')
    payload = json.loads(pipe.output('file', extra=['--baseline', str(path)], tag='old'))
    assert canonical_sha(payload['delta']) == expected['delta']


# =================================================================== V8 metamorphic relations on the fixtures

N_LADDER = [1, 3, 10, 25, 100000]


def test_V8_reference_agrees_with_product_on_fixture_at_default_n(inputs, tmp_path):
    report = analyze_again(inputs, tmp_path, 10)
    model = architecture_model(inputs['arch'])
    hubs, isolated = assert_candidates_match_reference(report, model, 10)
    assert len(hubs) <= 10


def test_V8_M1_larger_n_never_loses_an_untested_hub(inputs, tmp_path):
    previous = set()
    for top_n in N_LADDER:
        report = analyze_again(inputs, tmp_path, top_n)
        current = {c['target'] for c in of_kind(report['candidates'], 'untested_hub')}
        assert len(current) <= top_n
        assert previous <= current, (top_n, sorted(previous - current))
        previous = current
    assert previous, 'at N=100000 every untested production file is a hub'


def test_V8_M2_removing_test_files_never_shrinks_the_untested_set(pipe, tmp_path_factory):
    """Pool-wide N: with a fixed pool the relation is exact; a top-N cut could reorder the pool (see spec challenge)."""
    huge = write_weights(tmp_path_factory.mktemp('w'), weights_data(**{KEY: 100000}), 'huge.yaml')
    full = pipe.payload('file', extra=['--edge-weights', str(huge)], tag='huge')
    root = fixture_root(pipe.name).resolve()
    copy_full = tmp_path_factory.mktemp('copy-full') / 'fx'
    copy_reduced = tmp_path_factory.mktemp('copy-reduced') / 'fx'
    ignore_git = shutil.ignore_patterns('.git')
    shutil.copytree(root, copy_full, ignore=ignore_git)
    shutil.copytree(root, copy_reduced, ignore=ignore_git)
    removed = 0
    for path in sorted(p for p in copy_reduced.rglob('*') if p.is_file()):
        if 'test' in path_flags(path.relative_to(copy_reduced).as_posix()):
            path.unlink()
            removed += 1
    assert removed > 0, 'the fixture has test files to remove'

    def targets(directory, tag):
        out = tmp_path_factory.mktemp(tag)
        command = [sys.executable, '-c', MAIN, str(directory), *load_manifest()['commands'][pipe.name], '-o', str(out / 'r.html'),
                   '--bottlenecks', str(out / 'b.json'), '--edge-weights', str(huge)]
        done = subprocess.run(command, cwd=REPO, env=dict(os.environ, PYTHONHASHSEED='0'), capture_output=True, text=True)
        assert done.returncode == 0, done.stderr[-1500:]
        payload = json.loads((out / 'b.json').read_text(encoding='utf-8'))
        return {c['evidence']['path'] for c in of_kind(payload['candidates'], 'untested_hub')}

    before, after = targets(copy_full, 'full'), targets(copy_reduced, 'reduced')
    assert before <= after, sorted(before - after)[:5]
    assert {c['evidence']['path'] for c in of_kind(full['candidates'], 'untested_hub')} == before, 'copy without .git must not change the analyzed set'


def with_probe(inputs):
    """Fixture architecture plus one unconnected production file, so the relation never starts from an empty set."""
    from language_analyzers.core.graph_models import GraphNode, NodeCost, SourceSpan
    arch = copy.deepcopy(inputs['arch'])
    path = 'reach_probe_unconnected.py'
    arch.nodes.append(GraphNode(fid(path), path, 'file', 'file', kind='file', language='py', symbol_path=path,
                                span=SourceSpan(path, 1, 2), cost=NodeCost(2, 4, 2), flags=[], provenance='file-aggregation',
                                metadata={'file_path': path, 'granularity': 'file'}))
    snapshot = dataclasses.replace(inputs['snapshot'], contents=tuple(inputs['snapshot'].contents) + ((path, 'x\nx\n'),))
    return arch, snapshot, fid(path)


def test_V8_M3_adding_a_certain_exact_edge_removes_the_isolated_candidate(inputs, tmp_path):
    from language_analyzers.core.graph_models import GraphEdge
    arch, snapshot, probe = with_probe(inputs)
    baseline = analyze_again(inputs, tmp_path, 10, arch=arch, snapshot=snapshot)
    isolated = sorted(c['target'] for c in of_kind(baseline['candidates'], 'isolated_node'))
    assert probe in isolated
    model = architecture_model(arch)
    partners = [ident for ident, (category, _) in sorted(model.files.items()) if category == 'production' and ident not in isolated]
    assert partners, 'a production file outside the isolated set is needed as the partner'
    chosen = [probe] + [i for i in isolated if i != probe][:2]
    for index, target in enumerate(chosen):
        partner = partners[index % len(partners)]
        arch.edges.append(GraphEdge(partner if index % 2 == 0 else target, target if index % 2 == 0 else partner, 'IMPORTS', confidence=SC, resolution=EXACT,
                                    metadata={'detail_edge_indices': [], 'evidence_count': 1, 'candidate_share': 1}))
    changed = analyze_again(inputs, tmp_path, 10, arch=arch, snapshot=snapshot)
    remaining = {c['target'] for c in of_kind(changed['candidates'], 'isolated_node')}
    assert not remaining & set(chosen)
    assert remaining == set(isolated) - set(chosen)


# =================================================================== V9 report rendering

SENTINEL_RANK, SENTINEL_LINES = 4711, 8089


def sentinel_candidates():
    hub = {'id': 'b:00000000000000a1', 'kind': 'untested_hub', 'target': 'file:src/hub.py',
           'metrics': {'pagerank': 0.123456, 'pagerank_rank': SENTINEL_RANK, 'top_n': 10, 'uncertain_test_edge_count': 6203},
           'evidence': {'path': 'src/hub.py', 'uncertain_test_edges': []}, 'coverage': 'static_analyzer_relation', 'status': 'static_candidate'}
    iso = {'id': 'b:00000000000000a2', 'kind': 'isolated_node', 'target': 'file:src/lonely.py',
           'metrics': {'line_count': SENTINEL_LINES, 'framework_edge_count': 7331, 'dynamic_edge_count': 5419, 'uncertain_static_edge_count': 6007},
           'evidence': {'path': 'src/lonely.py', 'edges': []}, 'coverage': 'static_analyzer_relation', 'status': 'static_candidate'}
    return hub, iso


def real_payload(tmp_path):
    graph = Graph(files_of(production={'src/solo.py': 3}))
    return run_report(graph, weights_with(tmp_path))


def payload_with_sentinels(tmp_path):
    payload = real_payload(tmp_path)
    assert {c['kind'] for c in payload['candidates']} == set(NEW_KINDS)
    payload['candidates'] = [c for c in payload['candidates'] if c['kind'] not in NEW_KINDS]
    hub, iso = sentinel_candidates()
    hub['target'], iso['target'] = 'file:src/solo.py', 'file:src/solo.py'
    hub['evidence']['path'] = iso['evidence']['path'] = 'src/solo.py'
    payload['candidates'] += [hub, iso]
    payload['candidates'].sort(key=lambda c: (c['kind'], c['id']))
    return payload


def generate_text(payload):
    from report.bottlenecks.generate import generate
    writes = []
    generate(Path('in.json'), Path('out.html'), read_text=lambda path: json.dumps(payload), write_text=lambda path, text: writes.append(text))
    assert len(writes) == 1
    return writes[0]


HANGUL = re.compile('[가-힣]')


def number_in(text, number):
    pattern = '|'.join(re.escape(form) for form in (str(number), f'{number:,}'))
    return re.search(rf'(?<![\d.,])(?:{pattern})(?![\d])', text) is not None


def dom_without_scripts(page):
    return html.unescape(page.evaluate("(() => { const c = document.body.cloneNode(true); c.querySelectorAll('script').forEach(s => s.remove()); return c.innerHTML; })()"))


KIND_NUMBER = [('untested_hub', SENTINEL_RANK), ('isolated_node', SENTINEL_LINES)]


LABELS = {'untested_hub': '테스트 미도달 허브', 'isolated_node': '고립 파일'}
DESCRIPTIONS = {
    'untested_hub': 'PageRank 상위 production 파일 중 테스트 파일에서 직접 확정 연결(TESTS)이 닿지 않는 사례입니다.',
    'isolated_node': '다른 production 파일과 확정된 정적 연결이 없는 소스 파일 사례입니다. 프레임워크·동적·불확실 연결은 근거로 함께 보입니다.',
}


@pytest.mark.parametrize('kind,number', KIND_NUMBER)
def test_V9_R10_C16_generate_py_label_and_description_strings(kind, number):
    from report.bottlenecks.generate import KIND_DESCRIPTIONS, KIND_LABELS
    assert KIND_LABELS[kind] == LABELS[kind]
    assert KIND_DESCRIPTIONS[kind] == DESCRIPTIONS[kind]


@pytest.mark.parametrize('kind,number', KIND_NUMBER)
def test_V9_R10_C16_generate_py_page_shows_label_and_headline_number(chromium, tmp_path, kind, number):
    payload = payload_with_sentinels(tmp_path)
    target = tmp_path / 'report.html'
    target.write_text(generate_text(payload), encoding='utf-8')
    page = chromium.new_page()
    try:
        page.route('http://**/*', lambda route: route.abort())
        page.route('https://**/*', lambda route: route.abort())
        page.goto(target.as_uri())
        page.wait_for_load_state('load')
        page.wait_for_selector('#node-list [data-node-row]')
        dom = dom_without_scripts(page)
        assert LABELS[kind] in page.inner_text('body')
        page.locator('#node-list [data-node-row]').first.click()
        page.wait_for_timeout(300)
        lines = [line for line in page.inner_text('body').splitlines() if LABELS[kind] in line and number_in(line, number)]
        assert lines, page.inner_text('body')[-800:]
    finally:
        page.close()


def browser_report(tmp_path):
    from tests.report_redesign_support import build_report, make_file
    files = [make_file('src/hub.py'), make_file('src/lonely.py'), make_file('src/plain.py')]
    hub, iso = sentinel_candidates()
    return build_report(files, candidates=[hub, iso])


DASHBOARD_CASES = [('untested_hub', 'src/hub.py', SENTINEL_RANK), ('isolated_node', 'src/lonely.py', SENTINEL_LINES)]


@pytest.mark.parametrize('kind,path,number', DASHBOARD_CASES)
def test_V9_R10_C16_dashboard_modal_label_and_headline_number(open_report, tmp_path, kind, path, number):
    from tests.report_redesign_support import dialog_text
    from tests.test_report_modal import open_modal
    arch, bn = browser_report(tmp_path)
    page = open_report(arch, bn)
    open_modal(page, 'list', path)
    text = dialog_text(page)
    lines = [line for line in text.splitlines() if LABELS[kind] in line]
    assert lines and number_in(lines[0], number), text
    other = 'isolated_node' if kind == 'untested_hub' else 'untested_hub'
    assert not any(LABELS[other] in line for line in text.splitlines())
    assert page.unhandled_errors == []


# =================================================================== V10 performance (benchmark marker)

def median_runtime(command, cwd, env, runs=3):
    samples = []
    for _ in range(runs):
        started = time.perf_counter()
        done = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
        samples.append(time.perf_counter() - started)
        assert done.returncode == 0, done.stderr[-1500:]
    return statistics.median(samples), samples


@pytest.mark.benchmark
@pytest.mark.parametrize('name', ['fastapi-realworld', 'typescript-nestjs-realworld'])
def test_V10_Q2_analysis_time_ratio_against_base_commit(name, tmp_path):
    worktree = tmp_path / 'base'
    subprocess.run(['git', 'worktree', 'add', '--detach', str(worktree), BASE_COMMIT], cwd=REPO, check=True, capture_output=True)
    try:
        env = dict(os.environ, PYTHONHASHSEED='0')
        args = [str(fixture_root(name).resolve()), *load_manifest()['commands'][name], '--granularity', 'file']

        def command(tag):
            out = tmp_path / tag
            out.mkdir(exist_ok=True)
            return [sys.executable, '-c', MAIN, *args, '-o', str(out / 'r.html'), '--bottlenecks', str(out / 'b.json')]

        subprocess.run(command('warm-base'), cwd=worktree, env=env, capture_output=True, check=True)
        subprocess.run(command('warm-new'), cwd=REPO, env=env, capture_output=True, check=True)
        base, base_samples = median_runtime(command('base'), worktree, env)
        new, new_samples = median_runtime(command('new'), REPO, env)
        ratio = new / base
        print(f'BENCHMARK {name} base={base:.3f}s new={new:.3f}s ratio={ratio:.3f} base_samples={base_samples} new_samples={new_samples}')
        assert ratio <= 1.10, f'{name}: {ratio:.3f}x base_commit'
    finally:
        subprocess.run(['git', 'worktree', 'remove', '--force', str(worktree)], cwd=REPO, capture_output=True)
