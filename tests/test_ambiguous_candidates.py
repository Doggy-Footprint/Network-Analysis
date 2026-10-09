import copy
import math

import pytest

from analysis import GraphAnalyzer, GraphAnalysisConfig
from analysis.edge_weights import default_edge_weights_path, load_edge_weights
from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
from language_analyzers.core.graph_models import NodeCost, Resolution, SourceSpan
from tests.edge_weights_support import edge, load_weights, symbol_nodes, weights_data
from tests.file_analysis_support import architecture, converted, node, serialize, snapshot
from tests.candidate_group_storage_support import recovered_candidate_evidence

POLICY = 'equal-symbol-share.v1'
TOL = 1e-9


def metrics(nodes, edges, weights=None):
    return GraphAnalyzer(GraphAnalysisConfig(edge_weights=weights, max_iterations=10000)).analyze(copy.deepcopy(nodes), copy.deepcopy(edges))


@pytest.mark.parametrize('case,count,alternatives,profile,total', [
    ('two', 2, ['B'], 'no-profile', 1),
    ('three', 3, ['B', 'C'], 'no-profile', 1),
    ('duplicates', 2, ['A', 'B', 'B'], 'no-profile', 1),
    ('no-alternatives', 1, [], 'no-profile', 1),
    ('default-profile', 2, ['B'], 'default-profile', .3),
    ('custom-profile', 2, ['B'], 'custom-profile', .6),
])
def test_VO1_independent_closed_form_star(tmp_path, case, count, alternatives, profile, total):
    targets = list('ABC'[:count])
    nodes = symbol_nodes('S', *targets)
    for i, n in enumerate(nodes):
        n.cost = NodeCost(i + 1, 4 * (i + 1), 1)
    edges = [edge('S', 'A', resolution=Resolution.AMBIGUOUS, candidates=alternatives, weight=87)]
    edges += [edge(t, 'S') for t in targets]
    weights = None if profile == 'no-profile' else load_edge_weights(default_edge_weights_path()) if profile == 'default-profile' else load_weights(tmp_path, weights_data(resolution={'ambiguous': .6}))
    result = metrics(nodes, edges, weights)
    assert result['ambiguity_policy'] == POLICY
    n = count + 1
    teleport = (1 - .85) / n
    source_rank = (teleport + .85) / 1.85
    target_rank = teleport + .85 * source_rank / count
    for ident in ['S', *targets]:
        m = result['node_metrics'][ident]
        is_source = ident == 'S'
        assert m['fan_in'] == (count if is_source else 1)
        assert m['fan_out'] == (count if is_source else 1)
        assert m['weighted_fan_out'] == pytest.approx(total if is_source else 1, abs=TOL, rel=0)
        assert m['weighted_fan_in'] == pytest.approx(count if is_source else total / count, abs=TOL, rel=0)
        assert m['pagerank'] == pytest.approx(source_rank if is_source else target_rank, abs=TOL, rel=0)
        # W W^T has leading source eigenvalue total^2/count, versus count for targets.
        if count > 1 or total < 1:
            assert m['hub_score'] == pytest.approx(0 if is_source else 1 / math.sqrt(count), abs=TOL, rel=0)
            assert m['authority_score'] == pytest.approx(1 if is_source else 0, abs=TOL, rel=0)
        else:
            assert m['hub_score'] == pytest.approx(1 / math.sqrt(2), abs=TOL, rel=0)
            assert m['authority_score'] == pytest.approx(1 / math.sqrt(2), abs=TOL, rel=0)
        assert m['degree_centrality'] == pytest.approx(1 if is_source else 1 / count, abs=TOL, rel=0)
        assert m['betweenness_centrality'] == pytest.approx(1 if is_source and count > 1 else 0, abs=TOL, rel=0)
        for hop in (2, 3):
            assert m[f'hop_{hop}_node_count'] == count
            assert m[f'hop_{hop}_token_cost'] == sum(x.cost.token_estimate for x in nodes if x.id != ident)


@pytest.mark.parametrize('transformation', ['representative-swap', 'bijective-rename'])
def test_VO1_all_metrics_metamorphic(transformation):
    ids = ['S', 'A', 'B', 'C']
    nodes = symbol_nodes(*ids)
    for i, n in enumerate(nodes):
        n.cost = NodeCost(i + 2, 4 * (i + 2), 1)
    edges = [edge('S', 'A', resolution=Resolution.AMBIGUOUS, candidates=['B', 'C']), edge('B', 'C'), edge('C', 'S')]
    baseline = metrics(nodes, edges)['node_metrics']
    if transformation == 'representative-swap':
        edges[0].to_id, edges[0].candidates = 'C', ['B', 'A', 'A']
        mapping = {i: i for i in ids}
    else:
        mapping = dict(zip(ids, ['z', 'y', 'x', 'w']))
        for n in nodes:
            n.id = mapping[n.id]
        for e in edges:
            e.from_id, e.to_id = mapping[e.from_id], mapping[e.to_id]
            e.candidates = [mapping[t] for t in e.candidates]
    changed = metrics(nodes, edges)['node_metrics']
    for ident, expected in baseline.items():
        assert changed[mapping[ident]] == pytest.approx(expected, abs=TOL, rel=0)


@pytest.mark.parametrize('profile,total', [('no-profile', 1), ('default-profile', .3), ('custom-profile', .6)])
def test_VO1_pagerank_competing_exact_edge_independent_allocation(tmp_path, profile, total):
    nodes = symbol_nodes('S', 'A', 'B', 'C')
    edges = [edge('S', 'A', resolution=Resolution.AMBIGUOUS, candidates=['B'], weight=87), edge('S', 'C')]
    edges += [edge(target, 'S') for target in 'ABC']
    weights = None if profile == 'no-profile' else load_edge_weights(default_edge_weights_path()) if profile == 'default-profile' else load_weights(tmp_path, weights_data(resolution={'ambiguous': .6}))
    observed = metrics(nodes, edges, weights)['node_metrics']
    damping = .85
    teleport = .15 / 4
    source = (teleport + damping) / (1 + damping)
    candidate = teleport + damping * source * (total / 2) / (1 + total)
    exact = teleport + damping * source / (1 + total)
    for ident, expected in {'S': source, 'A': candidate, 'B': candidate, 'C': exact}.items():
        assert observed[ident]['pagerank'] == pytest.approx(expected, abs=TOL, rel=0)
    assert observed['S']['weighted_fan_out'] == pytest.approx(1 + total, abs=TOL, rel=0)
    assert observed['A']['weighted_fan_in'] == pytest.approx(total / 2, abs=TOL, rel=0)
    assert observed['B']['weighted_fan_in'] == pytest.approx(total / 2, abs=TOL, rel=0)
    assert observed['C']['weighted_fan_in'] == 1


def test_VO1_declared_absolute_comparison_bound_rejects_relative_slack():
    assert 1 + 5e-10 == pytest.approx(1, abs=TOL, rel=0)
    assert not 1 + 5e-8 == pytest.approx(1, abs=TOL, rel=0)


FILE_CASES = [
    ('same-file-2-of-3', ['b1', 'b2', 'c'], {'file:b.py': 2/3, 'file:c.py': 1/3}),
    ('all-one-target-file', ['b1', 'b2'], {'file:b.py': 1}),
    ('internal+external', ['inside', 'b1'], {'file:b.py': .5}),
    ('all-internal', ['s', 'inside'], {}),
    ('self+external', ['s', 'b1'], {'file:b.py': .5}),
    ('boundary-alternative', ['b1', 'outside'], {'file:b.py': .5, 'outside': .5}),
]


@pytest.mark.parametrize('case,targets,expected', FILE_CASES)
def test_VO2_file_decision_table(case, targets, expected):
    nodes = [node('s', 'a.py'), node('inside', 'a.py'), node('b1', 'b.py'), node('b2', 'b.py'), node('c', 'c.py'), node('outside', kind='external')]
    original = edge('s', targets[0], resolution=Resolution.AMBIGUOUS, candidates=targets[1:] + targets[1:], weight=91, evidence=SourceSpan('a.py', 1, 1))
    snap, result = converted({'a.py': 'aa', 'b.py': 'bb', 'c.py': 'cc'}, nodes, [original])
    payload = serialize(result)
    assert {(e['from_id'], e['to_id']) for e in payload['edges']} == {('file:a.py', t) for t in expected}
    for e in payload['edges']:
        assert e['metadata']['candidate_share'] == pytest.approx(expected[e['to_id']], abs=TOL, rel=0)
        assert e['metadata']['detail_edge_indices'] == [0]
        assert e['metadata']['evidence_count'] == 1
    assert payload['details']['edges'] == serialize(architecture(nodes, [original]))['edges']
    measured = metrics(result.nodes, result.edges)['node_metrics']
    assert measured['file:a.py']['weighted_fan_out'] == pytest.approx(sum(expected.values()), abs=TOL, rel=0)
    for t, contribution in expected.items():
        assert measured[t]['weighted_fan_in'] == pytest.approx(contribution, abs=TOL, rel=0)


@pytest.mark.parametrize('variant', ['overlap-max', 'exact-overlap'])
def test_VO2_overlap_provenance_and_no_double_split(variant):
    nodes = [node('s', 'a.py'), node('b1', 'b.py'), node('b2', 'b.py'), node('c', 'c.py')]
    first = edge('s', 'b1', resolution=Resolution.AMBIGUOUS, candidates=['b2', 'c'], evidence=SourceSpan('a.py', 1, 1))
    second = edge('s', 'b1', resolution=Resolution.AMBIGUOUS, candidates=['c'], evidence=SourceSpan('a.py', 2, 2))
    edges = [first, second]
    if variant == 'exact-overlap':
        edges.append(edge('s', 'b1', evidence=SourceSpan('a.py', 3, 3)))
    _, result = converted({'a.py': 'x\ny\nz', 'b.py': 'b', 'c.py': 'c'}, nodes, edges)
    out = serialize(result)
    measured = metrics(result.nodes, result.edges)['node_metrics']
    assert measured['file:b.py']['weighted_fan_in'] == pytest.approx(1 if variant == 'exact-overlap' else 2/3, abs=TOL, rel=0)
    assert measured['file:c.py']['weighted_fan_in'] == pytest.approx(.5, abs=TOL, rel=0)
    for e in out['edges']:
        indices = e['metadata']['detail_edge_indices']
        assert len(indices) == len(set(indices))
        assert e['metadata']['evidence_count'] == len(indices)
    b_ambiguous = next(e for e in out['edges'] if e['to_id'] == 'file:b.py' and e['resolution'] == 'ambiguous')
    assert b_ambiguous['metadata']['detail_edge_indices'] == [0, 1]
    assert out['details']['edges'] == serialize(architecture(nodes, edges))['edges']


@pytest.mark.parametrize('boundary,share', [
    pytest.param('analyzer', 'bad', id='nonnumeric'),
    pytest.param('analyzer', True, id='bool'),
    pytest.param('analyzer', float('nan'), id='nan'),
    pytest.param('analyzer', float('inf'), id='infinite'),
    pytest.param('analyzer', 0, id='zero'),
    pytest.param('analyzer', -.1, id='negative'),
    pytest.param('analyzer', 1.1, id='over-one'),
    pytest.param('file', 'bad', id='file-invalid'),
    pytest.param('bottleneck', True, id='bottleneck-invalid'),
])
def test_VO6_invalid_share_rejected(tmp_path, share, boundary):
    from bottlenecks import BottleneckInputError
    nodes = [node('s', 'a.py'), node('t', 'b.py')]
    edges = [edge('s', 't', metadata={'candidate_share': share})]
    snap = snapshot({'a.py': 'a', 'b.py': 'b'})
    with pytest.raises(ValueError if boundary == 'analyzer' else BottleneckInputError):
        if boundary == 'analyzer':
            metrics(nodes, edges)
        elif boundary == 'file':
            from analysis.file_graph import to_file_architecture
            to_file_architecture(architecture(nodes, edges), snap)
        else:
            analyze_bottlenecks(snap, architecture(nodes, edges), load_weights(tmp_path, weights_data()))


@pytest.mark.parametrize('boundary', ['analyzer', 'file', 'bottleneck'])
def test_VO6_unknown_candidate_rejected(tmp_path, boundary):
    from bottlenecks import BottleneckInputError
    nodes = [node('s', 'a.py'), node('t', 'b.py')]
    edges = [edge('s', 't', resolution=Resolution.AMBIGUOUS, candidates=['ghost'])]
    snap = snapshot({'a.py': 'x', 'b.py': 'y'})
    with pytest.raises(ValueError if boundary == 'analyzer' else BottleneckInputError):
        if boundary == 'analyzer':
            metrics(nodes, edges)
        elif boundary == 'file':
            from analysis.file_graph import to_file_architecture
            to_file_architecture(architecture(nodes, edges), snap)
        else:
            analyze_bottlenecks(snap, architecture(nodes, edges), load_weights(tmp_path, weights_data()))


@pytest.mark.parametrize('granularity', ['symbol', 'file', 'collapsed-target-file', 'internal-file-evidence'])
def test_VO4_symmetric_evidence_and_unique_projected_pairs(tmp_path, granularity):
    import json
    nodes = [node('s', 'a.py'), node('u', 'u.py'), node('b', 'b.py'), node('c', 'b.py' if granularity == 'collapsed-target-file' else 'c.py')]
    if granularity == 'internal-file-evidence':
        nodes[0].span = SourceSpan('b.py', 1, 1)
    edges = [edge('s', 'b', resolution=Resolution.AMBIGUOUS, candidates=['c', 'c'], evidence=SourceSpan(nodes[0].span.file_path, 1, 1)), edge('u', 'c', resolution=Resolution.AMBIGUOUS, candidates=['b'], evidence=SourceSpan('u.py', 1, 1))]
    files = {'a.py': 'x', 'u.py': 'u', 'b.py': 'b', 'c.py': 'c'}
    snap = snapshot(files)
    arch = architecture(nodes, edges)
    if granularity != 'symbol':
        from analysis.file_graph import to_file_architecture
        arch = to_file_architecture(arch, snap)
    weights = load_weights(tmp_path, weights_data())
    report = json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, weights)))
    report = recovered_candidate_evidence(report)
    assert report['dependency_network']['ambiguity_policy'] == POLICY
    assert report['dependency_network']['edge_count'] == {'symbol': 4, 'file': 4, 'collapsed-target-file': 2, 'internal-file-evidence': 3}[granularity]
    spread = {c['target']: c for c in report['candidates'] if c['kind'] == 'evidence_spread'}
    expected_targets = {'b', 'c'} if granularity == 'symbol' else {'file:b.py'} if granularity == 'collapsed-target-file' else {'file:b.py', 'file:c.py'}
    assert set(spread) == expected_targets
    for c in spread.values():
        assert c['metrics']['file_count'] == 2
        assert len(c['evidence']) == 2
        assert {r['start_line'] for r in c['evidence']} == {1}
        assert 'ambiguous' in json.dumps(c['evidence'])
        assert 'candidates' in json.dumps(c['evidence'])
    assert all(c['kind'] != 'unresolved_boundary' for c in report['candidates'])
    assert bottlenecks_to_json(analyze_bottlenecks(snap, arch, weights)) == bottlenecks_to_json(analyze_bottlenecks(snap, arch, weights))


def test_VO2_nine_symbols_same_file_has_exact_full_share():
    nodes = [node('s', 'a.py')] + [node(f'b{i}', 'b.py') for i in range(9)]
    _, result = converted({'a.py': 'a', 'b.py': 'b'}, nodes, [edge('s', 'b0', resolution=Resolution.AMBIGUOUS, candidates=[f'b{i}' for i in range(1, 9)])])
    out = serialize(result)
    assert len(out['edges']) == 1
    assert out['edges'][0]['metadata']['candidate_share'] == 1
    assert metrics(result.nodes, result.edges)['node_metrics']['file:b.py']['weighted_fan_in'] == 1


@pytest.mark.parametrize('language', ['Python', 'TypeScript', 'Kotlin'])
def test_VO3_language_candidate_group_reaches_public_policy(tmp_path, language):
    from language_analyzers.python.graph import PythonGraphAnalyzer
    from language_analyzers.typescript import TypeScriptAnalyzer
    from language_analyzers.kotlin import KotlinAnalyzer
    builders = {'Python': PythonGraphAnalyzer, 'TypeScript': TypeScriptAnalyzer, 'Kotlin': KotlinAnalyzer}
    sources = {
        'Python': {'a.py': 'def shared():\n    return 1\n', 'b.py': 'def shared():\n    return 2\n', 'main.py': 'def caller():\n    return shared()\n'},
        'TypeScript': {'a.ts': 'export function shared() { return 1; }', 'b.ts': 'export function shared() { return 2; }', 'main.ts': 'export function caller() { return shared(); }'},
        'Kotlin': {'a.kt': 'package a\nclass Duplicate\n', 'b.kt': 'package b\nclass Duplicate\n', 'main.kt': 'package main\nfun caller() = Duplicate()\n'},
    }
    for path, text in sources[language].items():
        (tmp_path / path).write_text(text)
    arch = builders[language](tmp_path).analyze()
    expected = {n.id for n in arch.nodes if n.label == ('Duplicate' if language == 'Kotlin' else 'shared')}
    caller = next(n for n in arch.nodes if n.label == 'caller')
    relations = [e for e in arch.edges if e.from_id == caller.id and str(e.resolution) == 'ambiguous']
    observed_kind = 'INSTANTIATES' if language == 'Kotlin' else 'CALLS'
    assert sum(str(e.relation) == observed_kind for e in relations) == 1
    for relation in relations:
        assert {relation.to_id, *relation.candidates} == expected
        assert relation.evidence is not None
    result = metrics(arch.nodes, relations)
    assert result['node_metrics'][caller.id]['fan_out'] == 2
    for target in expected:
        assert result['node_metrics'][target]['weighted_fan_in'] == .5


@pytest.mark.parametrize('client', ['HTTP-TS', 'Retrofit'])
def test_VO3_route_producer_feeds_complete_candidates(client):
    from framework_analyzers.route_matching import match_routes
    from tests.test_route_client_call_edges import server, retrofit, call
    servers = [server('a', 'GET', '/x'), server('b', 'GET', '/x')]
    nodes = symbol_nodes('caller') + servers
    if client == 'Retrofit':
        nodes = [retrofit('caller', 'GET', '/x')] + servers
    edges, stats = match_routes(nodes, [call('caller', 'GET', '/x')] if client == 'HTTP-TS' else [])
    assert len(edges) == 1
    assert {edges[0].to_id, *edges[0].candidates} == {'a', 'b'}
    assert edges[0].evidence is not None
    assert stats == {'matched': 0, 'ambiguous': 1, 'unmatched': 0, 'unresolvable': 0}
    result = metrics(nodes, edges)
    assert result['node_metrics']['a']['weighted_fan_in'] == .5
    assert result['node_metrics']['b']['weighted_fan_in'] == .5


def test_VO3_migration_distinct_candidate_sets_not_deduped():
    from framework_analyzers.migration_tables import match_migration_tables
    edges, stats = match_migration_tables({'one': ['a', 'b'], 'two': ['a', 'c']}, [('m', ['one', 'two'], SourceSpan('migration.py', 1, 1))])
    assert len(edges) == 2
    assert {frozenset([e.to_id, *e.candidates]) for e in edges} == {frozenset(['a', 'b']), frozenset(['a', 'c'])}
    assert stats == {'matched': 0, 'ambiguous': 2, 'unmatched': 0, 'unresolvable': 0}
    result = metrics(symbol_nodes('m', 'a', 'b', 'c'), edges)['node_metrics']
    assert result['m']['fan_out'] == 3
    assert result['m']['weighted_fan_out'] == 1.5


@pytest.mark.parametrize('policy', [None, 'legacy'])
def test_VO6_supplied_analysis_policy_cannot_relabel_stale_metrics(tmp_path, policy):
    from bottlenecks import BottleneckInputError
    nodes = [node('s', 'a.py'), node('t', 'b.py')]
    edges = [edge('s', 't')]
    analysis = metrics(nodes, edges)
    if policy is None:
        analysis.pop('ambiguity_policy')
    else:
        analysis['ambiguity_policy'] = policy
    with pytest.raises(BottleneckInputError):
        analyze_bottlenecks(snapshot({'a.py': 'a', 'b.py': 'b'}), architecture(nodes, edges), load_weights(tmp_path, weights_data()), analysis=analysis)


def assert_producer_group(arch, relations, expected):
    assert len(relations) == 1
    relation = relations[0]
    assert str(relation.resolution) == 'ambiguous'
    assert {relation.to_id, *relation.candidates} == expected
    assert relation.evidence is not None
    assert isinstance(relation.metadata['framework_rule']['id'], str)
    observed = metrics(arch.nodes, relations)['node_metrics']
    for ident in expected:
        assert observed[ident]['weighted_fan_in'] == pytest.approx(.5, abs=TOL, rel=0)


@pytest.mark.parametrize('surface', ['named', 'field-types'])
def test_VO3_fastapi_producer_group_and_evidence(tmp_path, surface):
    from framework_analyzers.fastapi.graph import ArchitectureGraphBuilder
    from framework_analyzers.fastapi.models import DependencyInfo, EndpointInfo, ProjectArchitecture, SchemaFieldInfo, SchemaInfo
    if surface == 'field-types':
        schemas = [SchemaInfo(id='owner-a', name='Owner', module='a', file_path='a.py', line_number=1, end_line_number=1),
                   SchemaInfo(id='owner-b', name='Owner', module='b', file_path='b.py', line_number=1, end_line_number=1),
                   SchemaInfo(id='model', name='Model', module='main', file_path='main.py', line_number=5, end_line_number=5,
                              fields=[SchemaFieldInfo(name='owner', type_annotation='Owner')])]
        (tmp_path / 'main.py').write_text('x = 1\n')
        arch = ArchitectureGraphBuilder(include_language_graph=False).build_graph(ProjectArchitecture(project_name='oracle', project_path=str(tmp_path), schemas=schemas))
        relations = [e for e in arch.edges if e.from_id == 'model' and str(e.relation) == 'TYPE_USES']
        assert_producer_group(arch, relations, {'owner-a', 'owner-b'})
        assert relations[0].evidence == SourceSpan('main.py', 5, 5)
        assert relations[0].metadata['framework_rule']['id'] == 'fastapi.model_field_type_uses'
    else:
        (tmp_path / 'main.py').write_text('def route():\n    return 1\n')
        providers_input = [DependencyInfo(id='dep-a', name='shared', kind='function', module='a', file_path='a.py', line_number=1, end_line_number=2),
                           DependencyInfo(id='dep-b', name='shared', kind='function', module='b', file_path='b.py', line_number=1, end_line_number=2)]
        endpoint = EndpointInfo(id='route', http_method='GET', path='/x', full_path='/x', function_name='route', module='main', file_path='main.py', line_number=1, end_line_number=2, dependencies=['shared'])
        arch = ArchitectureGraphBuilder(include_language_graph=False).build_graph(ProjectArchitecture(project_name='oracle', project_path=str(tmp_path), dependencies=providers_input, endpoints=[endpoint]))
        providers = {n.id for n in arch.nodes if n.label == 'shared'}
        assert len(providers) == 2
        relations = [e for e in arch.edges if str(e.relation) == 'DEPENDS_ON' and {e.to_id, *e.candidates} == providers]
        assert_producer_group(arch, relations, providers)


def test_VO3_android_named_candidate_policy():
    from tests.test_android_graph_contract import AndroidNameCollisionTests
    relations = [e for e in AndroidNameCollisionTests().build() if e.from_id == 'composable_Caller']
    expected = {'composable_overload_a', 'composable_overload_b'}
    arch = architecture(symbol_nodes('composable_Caller', *expected))
    assert_producer_group(arch, relations, expected)
    assert relations[0].metadata['framework_rule']['specificity'] == 'ambiguous'


@pytest.mark.parametrize('orm', ['SQLAlchemy', 'Room'])
def test_VO3_orm_migration_complete_group_stats_and_policy(tmp_path, orm):
    if orm == 'SQLAlchemy':
        from tests.test_sqlalchemy_migration_edges import build, project, revision
        source = 'from sqlalchemy.orm import declarative_base\nBase = declarative_base()\nclass Alpha(Base):\n    __tablename__ = "users"\nclass Beta(Base):\n    __tablename__ = "users"\n'
        arch, _ = build(tmp_path, project(revision('op.add_column("users", sa.Column("age", sa.Integer()))'), models=source))
        expected = {n.id for n in arch.nodes if n.group == 'sqlalchemy_model'}
    else:
        from framework_analyzers.android.analyzer import AndroidAnalyzer
        from framework_analyzers.android.graph import AndroidArchitectureGraphBuilder
        from tests.test_room_migration_edges import PKG_DIR, PROPERTY_MIGRATION, USER_ENTITY
        files = {f'{PKG_DIR}/model/User.kt': USER_ENTITY, f'{PKG_DIR}/model/Second.kt': USER_ENTITY.replace('User(', 'Second('), f'{PKG_DIR}/Migrations.kt': PROPERTY_MIGRATION}
        for relative, text in files.items():
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        arch = AndroidArchitectureGraphBuilder().build_graph(AndroidAnalyzer(str(tmp_path)).analyze())
        relations = [e for e in arch.edges if str(e.relation) == 'MIGRATES']
        expected = {n.id for n in arch.nodes if n.label in {'User', 'Second'} and n.provenance != 'kotlin-core'}
    relations = [e for e in arch.edges if str(e.relation) == 'MIGRATES']
    assert len(expected) == 2
    assert_producer_group(arch, relations, expected)
    assert relations[0].metadata['table'] == 'users'
    assert relations[0].metadata['framework_rule'] == {'id': 'orm.migration_touches_table', 'specificity': 'ambiguous'}
    assert arch.stats['migration_matching'] == {'matched': 0, 'ambiguous': 1, 'unmatched': 0, 'unresolvable': 0}


def test_VO3_enrichment_TESTS_each_candidate(tmp_path):
    from language_analyzers.python.graph import PythonGraphAnalyzer
    for path in ['a.py', 'b.py']:
        (tmp_path / path).write_text('def shared():\n    return 1\n')
    (tmp_path / 'test_main.py').write_text('def test_call():\n    assert shared() == 1\n')
    arch = PythonGraphAnalyzer(tmp_path).analyze()
    expected = {n.id for n in arch.nodes if n.label == 'shared'}
    test_node = next(n for n in arch.nodes if n.label == 'test_call')
    relations = [e for e in arch.edges if e.from_id == test_node.id and str(e.relation) == 'TESTS']
    assert len(relations) == 1
    assert {relations[0].to_id, *relations[0].candidates} == expected
    assert relations[0].evidence == SourceSpan('test_main.py', 2, 2)
    assert str(relations[0].resolution) == 'ambiguous'
    result = metrics(arch.nodes, relations)['node_metrics']
    assert result[test_node.id]['fan_out'] == 2
    for ident in expected:
        assert result[ident]['weighted_fan_in'] == .5


def test_VO4_overlapping_original_evidence_count_once_per_target(tmp_path):
    import json
    nodes = [node('s', 'a.py'), node('u', 'u.py'), node('b1', 'b.py'), node('b2', 'b.py'), node('c', 'c.py')]
    edges = [edge('s', 'b1', resolution=Resolution.AMBIGUOUS, candidates=['b2', 'c'], evidence=SourceSpan('a.py', 1, 2)),
             edge('u', 'b2', resolution=Resolution.AMBIGUOUS, candidates=['b1', 'c'], evidence=SourceSpan('u.py', 3, 4))]
    snap, arch = converted({'a.py': 'a\na', 'u.py': 'u\nu\nu\nu', 'b.py': 'b', 'c.py': 'c'}, nodes, edges)
    report = json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, load_weights(tmp_path, weights_data()))))
    report = recovered_candidate_evidence(report)
    candidates = {c['target']: c for c in report['candidates'] if c['kind'] == 'evidence_spread'}
    assert set(candidates) == {'file:b.py', 'file:c.py'}
    for c in candidates.values():
        assert c['metrics']['file_count'] == 2
        assert len(c['evidence']) == 2
        assert {(e['path'], e['start_line'], e['end_line']) for e in c['evidence']} == {('a.py', 1, 2), ('u.py', 3, 4)}


def test_VO7_characterization_exact_unique_unresolved_targets_and_repeat():
    nodes = symbol_nodes('s', 'a', 'b', 'c')
    edges = [edge('s', 'a', candidates=['c']), edge('s', 'b', resolution=Resolution.UNIQUE_NAME, candidates=['c']), edge('a', 'b', resolution=Resolution.UNRESOLVED, candidates=['c'])]
    first = metrics(nodes, edges)
    assert first == metrics(nodes, edges)
    assert first['node_metrics']['s']['fan_out'] == 2
    assert first['node_metrics']['s']['weighted_fan_out'] == 2
    assert first['node_metrics']['b']['weighted_fan_in'] == 2
    assert first['node_metrics']['c']['fan_in'] == 0
    assert first['node_metrics']['c']['weighted_fan_in'] == 0


@pytest.mark.parametrize('emitter', ['Python', 'TypeScript', 'Kotlin', 'enrichment'])
def test_VO3_controlled_self_representative_and_distinct_groups(tmp_path, emitter):
    from language_analyzers.core.enrichment import _append_edge
    from language_analyzers.python.graph import PythonGraphAnalyzer
    from language_analyzers.typescript import TypeScriptAnalyzer
    from language_analyzers.kotlin import KotlinAnalyzer
    span = SourceSpan('input.py', 2, 2)
    if emitter == 'enrichment':
        nodes = symbol_nodes('src', 'a', 'b')
        output, existing = [], set()
        for external in ['a', 'b']:
            _append_edge(output, existing, 'src', 'src', 'TESTS', 'static_inferred', 'ambiguous', span, [external])
        source, alternatives = 'src', {'a', 'b'}
    else:
        builders = {'Python': PythonGraphAnalyzer, 'TypeScript': TypeScriptAnalyzer, 'Kotlin': KotlinAnalyzer}
        path, text = {'Python': ('input.py', 'def src():\n    return 1\ndef a():\n    return 1\ndef b():\n    return 1\n'),
                      'TypeScript': ('input.ts', 'function src() { return 1; }\nfunction a() { return 1; }\nfunction b() { return 1; }'),
                      'Kotlin': ('input.kt', 'fun src() = 1\nfun a() = 1\nfun b() = 1\n')}[emitter]
        (tmp_path / path).write_text(text)
        builder = builders[emitter](tmp_path)
        arch = builder.analyze()
        nodes = arch.nodes
        source = next(n.id for n in nodes if n.label == 'src')
        alternatives = {n.id for n in nodes if n.label in {'a', 'b'}}
        assert len(alternatives) == 2
        for external in sorted(alternatives):
            builder._add_edge(source, source, 'TESTS', confidence='static_inferred', resolution='ambiguous', evidence=span, candidates=[external])
        output = [e for e in builder._edges.values() if str(e.relation) == 'TESTS']
    assert len(output) == 2
    assert {frozenset([e.to_id, *e.candidates]) for e in output} == {frozenset([source, external]) for external in alternatives}
    assert all(e.evidence == span for e in output)
    observed = metrics(nodes, output)['node_metrics']
    assert observed[source]['fan_out'] == 2
    assert observed[source]['weighted_fan_out'] == 1
    for external in alternatives:
        assert observed[external]['weighted_fan_in'] == .5


@pytest.mark.parametrize('granularity', ['symbol', 'file'])
def test_VO4_registry_losslessly_interns_original_order_duplicates_and_representative(tmp_path, granularity):
    import json
    from collections import Counter
    groups = [('b', ['c', 'd', 'c']), ('b', ['c', 'd', 'c']), ('b', ['d', 'c', 'c']), ('c', ['b', 'd', 'c']), ('b', ['c', 'd'])]
    nodes = [node(f's{i}', f's{i}.py') for i in range(len(groups))] + [node(ident, 'target.py') for ident in 'bcd']
    edges = [edge(f's{i}', target, resolution=Resolution.AMBIGUOUS, candidates=alternatives, weight=i + 7, evidence=SourceSpan(f's{i}.py', 1, 1), metadata={'original_marker': i}) for i, (target, alternatives) in enumerate(groups)]
    files = {f's{i}.py': f's{i}()\n' for i in range(len(groups))}
    files['target.py'] = 'target\n'
    snap = snapshot(files)
    arch = architecture(nodes, edges)
    raw = serialize(arch)['edges']
    if granularity == 'file':
        from analysis.file_graph import to_file_architecture
        arch = to_file_architecture(arch, snap)
    before = copy.deepcopy(serialize(arch))
    weights = load_weights(tmp_path, weights_data())
    report = json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, weights)))
    registry = report['dependency_network']['candidate_groups']
    fingerprint = lambda group: json.dumps(group, sort_keys=True)
    expected_groups = {fingerprint({'to_id': target, 'candidates': alternatives}) for target, alternatives in groups}
    assert len(registry) == 4
    assert {fingerprint(group) for group in registry.values()} == expected_groups
    recovered = recovered_candidate_evidence(report)
    expected_records = [dict(copy.deepcopy(relation), path=relation['evidence']['file_path'], start_line=1, end_line=1) for relation in raw]
    if granularity == 'file':
        for ordinal, record in enumerate(expected_records):
            record['detail_edge_index'] = ordinal
    candidates = [c for c in recovered['candidates'] if c['kind'] == 'evidence_spread']
    assert {c['target'] for c in candidates} == ({'b', 'c', 'd'} if granularity == 'symbol' else {'file:target.py'})
    for candidate in candidates:
        assert Counter(fingerprint(record) for record in candidate['evidence']) == Counter(fingerprint(record) for record in expected_records)
    references = {i: set() for i in range(len(groups))}
    for candidate in report['candidates']:
        if candidate['kind'] == 'evidence_spread':
            for record in candidate['evidence']:
                assert 'candidates' not in record
                references[record['metadata']['original_marker']].add(record['candidate_group_id'])
    assert all(len(ids) == 1 for ids in references.values())
    assert references[0] == references[1]
    assert len({next(iter(ids)) for ids in references.values()}) == 4
    after = serialize(arch)
    assert after['edges'] == before['edges']
    if granularity == 'file':
        assert after['details']['edges'] == before['details']['edges'] == raw
    repeated = json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, weights)))
    assert repeated == report
    reversed_arch = architecture(nodes, list(reversed(edges)))
    if granularity == 'file':
        reversed_arch = to_file_architecture(reversed_arch, snap)
    reordered = json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, reversed_arch, weights)))
    assert reordered['dependency_network']['candidate_groups'] == registry


def test_VO4_registry_omitted_for_unchanged_nonambiguous_evidence(tmp_path):
    import json
    nodes = [node('s', 'a.py'), node('u', 'u.py'), node('t', 'target.py')]
    edges = [edge('s', 't', evidence=SourceSpan('a.py', 1, 1)), edge('u', 't', evidence=SourceSpan('u.py', 2, 2))]
    report = json.loads(bottlenecks_to_json(analyze_bottlenecks(snapshot({'a.py': 'a', 'u.py': 'u\nu', 'target.py': 't'}), architecture(nodes, edges), load_weights(tmp_path, weights_data()))))
    assert 'candidate_groups' not in report['dependency_network']
    assert recovered_candidate_evidence(report) == report
    candidate = next(c for c in report['candidates'] if c['kind'] == 'evidence_spread')
    assert candidate['evidence'] == [{'path': 'a.py', 'start_line': 1, 'end_line': 1}, {'path': 'u.py', 'start_line': 2, 'end_line': 2}]
