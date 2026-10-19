import copy
import json
from types import SimpleNamespace

import pytest

from analysis import GraphAnalyzer, GraphAnalysisConfig
from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
from language_analyzers.core.graph_models import Confidence, Resolution, SourceSpan
from tests.edge_weights_support import edge, load_weights, weights_data
from tests.file_analysis_support import architecture, converted, node, serialize, snapshot


def payload(snap, arch, tmp_path, threshold=2000):
    weights = load_weights(tmp_path, weights_data(large_node_line_threshold=threshold))
    return json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, weights)))


@pytest.mark.parametrize('variant', ['internal-only', 'isolated', 'empty-file', 'empty-graph', 'docs-only'])
def test_V03_file_partitions(variant):
    files = {'a.py': '' if variant == 'empty-file' else 'x\n', 'README.md': 'document'}
    nodes = [] if variant in ('empty-graph', 'docs-only') else [node('a', 'a.py')]
    edges = []
    if variant == 'internal-only':
        nodes.append(node('b', 'a.py'))
        edges.append(edge('a', 'b'))
    _, result = converted(files, nodes, edges)
    out = serialize(result)
    assert [n['id'] for n in out['nodes']] == ([] if not nodes else ['file:a.py'])
    assert out['edges'] == []
    assert len(out['details']['edges']) == len(edges)
    if variant == 'empty-file':
        assert out['nodes'][0]['cost'] == {'token_estimate': 1, 'char_count': 0, 'line_count': 0}


def test_V03_mixed_keys_candidate_only_duplicate_weights(tmp_path):
    nodes = [node('a1', 'a.py'), node('a2', 'a.py'), node('b1', 'b.py'), node('candidate', 'c.py')]
    edges = [edge('a1', 'b1', weight=7, candidates=['candidate'], evidence=SourceSpan('a.py', 1, 1)),
             edge('a2', 'b1', evidence=SourceSpan('a.py', 2, 2)),
             edge('a1', 'b1', Confidence.STATIC_INFERRED),
             edge('a1', 'b1', resolution=Resolution.AMBIGUOUS),
             edge('a1', 'b1', relation='IMPORTS')]
    snap, result = converted({'a.py': 'x\ny\n', 'b.py': 'z', 'c.py': 'q'}, nodes, edges)
    out = serialize(result)
    assert len(out['edges']) == 4
    assert {tuple(e['metadata']['detail_edge_indices']) for e in out['edges']} == {(0, 1), (2,), (3,), (4,)}
    assert sorted(e['metadata']['evidence_count'] for e in out['edges']) == [1, 1, 1, 2]
    assert {(e['from_id'], e['to_id']) for e in out['edges']} == {('file:a.py', 'file:b.py')}
    assert {(e['relation'],e['confidence'],e['resolution']) for e in out['edges']}=={('CALLS','static_certain','exact'),('CALLS','static_inferred','exact'),('CALLS','static_certain','ambiguous'),('IMPORTS','static_certain','exact')}
    assert out['details']['edges'][0]['weight'] == 7
    assert out['details']['edges'][0]['candidates'] == ['candidate']
    weights = load_weights(tmp_path, weights_data())
    metrics = GraphAnalyzer(GraphAnalysisConfig(edge_weights=weights)).analyze(result.nodes, result.edges, snap.root)['node_metrics']
    assert metrics['file:b.py']['weighted_fan_in'] == pytest.approx(1.0, abs=1e-9, rel=0)
    assert metrics['file:a.py']['weighted_fan_out'] == pytest.approx(1.0, abs=1e-9, rel=0)
    assert metrics['file:c.py']['fan_in'] == 0


def test_V03_package_boundary_and_incoming(tmp_path):
    nodes = [node('member', 'a.py'), node('package', kind='package'), node('external', kind='external')]
    nodes[1].provenance = 'python-core'
    edges = [edge('package', 'member', relation='CONTAINS'), edge('member', 'external'), edge('external', 'member')]
    snap, result = converted({'a.py': 'x'}, nodes, edges)
    out = serialize(result)
    assert {n['id'] for n in out['nodes']} == {'file:a.py', 'external'}
    assert out['details']['node_files'] == {'member': 'file:a.py', 'package': None, 'external': None}
    assert len(out['details']['edges']) == 3
    assert {(e['from_id'], e['to_id']) for e in out['edges']} == {('file:a.py', 'external'), ('external', 'file:a.py')}
    external = next(n for n in out['nodes'] if n['id'] == 'external')
    assert external['cost']['token_estimate'] == 0
    report = payload(snap, result, tmp_path)
    assert report['dependency_network']['node_metrics']['external']['token_cost'] == 0
    assert all(row['node_id'] != 'external' for rows in report['dependency_network']['rankings'].values() for row in rows)
    assert all(candidate['target'] != 'external' for candidate in report['candidates'])
    assert report['dependency_network']['node_metrics']['external']['fan_in']==1
    assert report['dependency_network']['node_metrics']['external']['fan_out']==1



@pytest.mark.parametrize('variant', ['nested-class', 'nested-function', 'method', 'field', 'top-reference', 'implemented-by', 'configuration', 'framework-same-relation-name'])
def test_V04_owners_roles_configuration(variant):
    parent = node('parent', 'a.py', 'class')
    child = node('child', None, {'nested-class':'class','nested-function':'function','method':'method','field':'field','top-reference':'constant','implemented-by':'provider','configuration':'configuration','framework-same-relation-name':'provider'}[variant])
    if variant == 'implemented-by':
        child.provenance = 'fastapi'
    if variant == 'top-reference':
        parent.kind = 'module'; parent.group = 'module'; parent.category = 'module'
        child.span = SourceSpan('a.py', 1, 1)
    relation = 'IMPLEMENTS' if variant == 'framework-same-relation-name' else 'IMPLEMENTED_BY' if variant == 'implemented-by' else 'CONTAINS'
    if variant == 'top-reference':
        relation = 'DECLARES'
    if variant in ('configuration', 'framework-same-relation-name'):
        child.span = SourceSpan('config.yml', 1, 1)
        child.provenance = 'fastapi'
        relation = 'CONFIGURES' if variant == 'configuration' else 'CONTAINS'
    edges = [edge('child', 'parent', relation=relation)] if variant == 'implemented-by' else [edge('parent', 'child', relation=relation)]
    _, result = converted({'a.py': 'x', 'config.yml': 'q'}, [parent, child], edges)
    out = serialize(result)
    assert len(out['details']['edges']) == 1
    if variant in ('configuration', 'framework-same-relation-name'):
        assert len(out['edges']) == 1
        assert out['details']['node_files']['child'] == 'file:config.yml'
    else:
        assert out['details']['node_files']['child'] == 'file:a.py'
        assert out['edges'] == []
        if variant != 'implemented-by':
            assert out['details']['node_owners']['child'] == 'parent'


def chain():
    files = {'a.py': 'abcd', 'b.py': 'abcde', 'c.py': '1234567', 'd.py': ''}
    nodes = [node(letter, f'{letter}.py', metadata={'analysis': {'pagerank': 1000}}) for letter in 'abcd']
    return converted(files, nodes, [edge('a', 'b'), edge('b', 'c')])


def test_V05_independent_chain_metrics_and_whole_text(tmp_path):
    snap, result = chain()
    report = payload(snap, result, tmp_path)
    metrics = report['dependency_network']['node_metrics']
    base = 1 / (4 + 2 * .85 + .85 ** 2)
    expected_rank = {'a': base, 'b': base * 1.85, 'c': base * (1 + .85 + .85 ** 2), 'd': base}
    tokens = {'a': 1, 'b': 2, 'c': 3, 'd': 1}
    for letter in 'abcd':
        row = metrics[f'file:{letter}.py']
        assert row['pagerank'] == pytest.approx(expected_rank[letter], abs=1e-9, rel=0)
        assert row['token_cost'] == tokens[letter]
        assert row['fan_in'] == int(letter in 'bc')
        assert row['fan_out'] == int(letter in 'ab')
        assert row['weighted_fan_in'] == int(letter in 'bc')
        assert row['weighted_fan_out'] == int(letter in 'ab')
        assert row['betweenness_centrality'] == pytest.approx(1/6 if letter == 'b' else 0,abs=1e-9,rel=0)
        neighbors = set('abc') - {letter} if letter != 'd' else set()
        assert row['hop_2_token_cost'] == sum(tokens[n] for n in neighbors)
    assert report['schema'] == 'bottlenecks.v8' and report['granularity'] == 'file'
    assert all('analysis' not in n['metadata'] for n in serialize(result)['details']['nodes'])
    unicode_snap,unicode_file=converted({'a.py':'value = "a\u2028b"'},[node('value','a.py','constant')])
    unicode_data=serialize(unicode_file)
    assert unicode_data['nodes'][0]['cost']=={'token_estimate':4,'char_count':13,'line_count':1}
    file_span=unicode_data['nodes'][0]['span']
    assert (file_span['file_path'],file_span['start_line'],file_span['end_line'])==('a.py',1,1)
    original_span=unicode_data['details']['nodes'][0]['span']
    assert (original_span['file_path'],original_span['start_line'],original_span['end_line'])==('a.py',1,1)
    unicode_report=payload(unicode_snap,unicode_file,tmp_path)
    assert unicode_report['schema']=='bottlenecks.v8'
    assert unicode_report['granularity']=='file'
    assert unicode_report['dependency_network']['node_metrics']['file:a.py']['token_cost']==4


@pytest.mark.parametrize(('flags', 'discount'), [((), 1), (('generated',), .1), (('vendored',), 0)])
def test_V05_duplicate_symbol_invariance_and_discounts(tmp_path, flags, discount):
    files = {'a.py': 'abcd1234'}
    _, single = converted(files, [node('a', 'a.py', flags=flags)])
    snap, duplicate = converted(files, [node('a', 'a.py', flags=flags), node('b', 'a.py', flags=flags)])
    for result in (single, duplicate):
        metrics = payload(snap, result, tmp_path)['dependency_network']['node_metrics']['file:a.py']
        assert metrics['token_cost'] == 3
        assert metrics['effective_token_cost'] == pytest.approx(3 * discount,abs=1e-9,rel=0)


@pytest.mark.parametrize(('lines', 'expected'), [(2, 0), (3, 0), (4, 1)], ids=['T-1','T','T+1'])
def test_V06_large_three_value_boundary(tmp_path, lines, expected):
    snap, result = converted({'a.py': 'x\n' * lines}, [node('a', 'a.py'), node('b', 'a.py')])
    candidates = [c for c in payload(snap, result, tmp_path, 3)['candidates'] if c['kind'] == 'large_node']
    assert len(candidates) == expected
    if expected:
        assert candidates[0]['target'] == 'file:a.py'
        assert candidates[0]['metrics']['line_count'] == 4
        assert candidates[0]['status'] == 'static_candidate'


@pytest.mark.parametrize(('span', 'expected'), [(2, 0), (3, 0), (4, 1)], ids=['T-1','T','T+1'])
def test_V06_spread_three_value_boundary(tmp_path, span, expected):
    edges = [edge('a', 'b1', evidence=SourceSpan('a.py', 1, 1)), edge('a', 'b2', evidence=SourceSpan('a.py', span, span))]
    owner=node('owner','ownership.py','class')
    role=node('role',kind='provider'); role.provenance='fastapi'
    edges.extend([edge('owner','b1',Confidence.DYNAMIC_REQUIRED,Resolution.UNRESOLVED,relation='CONTAINS',evidence=SourceSpan('ownership.py',1,1)),edge('role','b1',Confidence.DYNAMIC_REQUIRED,Resolution.UNRESOLVED,relation='IMPLEMENTED_BY',evidence=SourceSpan('ownership.py',2,2))])
    snap, result = converted({'a.py': 'x\n'*4, 'b.py': 'y','ownership.py':'owner\nrole'}, [node('a','a.py'),node('b1','b.py'),node('b2','b.py'),owner,role], edges)
    report=payload(snap,result,tmp_path,3)
    assert all(c['kind']!='unresolved_boundary' for c in report['candidates'])
    candidates = [c for c in report['candidates'] if c['kind'] == 'evidence_spread']
    assert len(candidates) == expected
    if expected:
        assert candidates[0]['target'] == 'file:b.py'
        assert candidates[0]['metrics']['line_span'] == 4
        records = candidates[0]['evidence']
        assert {(e['path'],e['start_line']) for e in records} == {('a.py',1),('a.py',4)}


def test_V06_two_files_spread(tmp_path):
    nodes = [node('a','a.py'),node('b','c.py'),node('c','c.py')]
    edges = [edge('a','c',evidence=SourceSpan('a.py',1,1)),edge('b','c',evidence=SourceSpan('c.py',1,1))]
    snap, result = converted({'a.py':'x','c.py':'z'}, nodes, edges)
    candidates = [c for c in payload(snap,result,tmp_path)['candidates'] if c['kind']=='evidence_spread']
    assert len(candidates)==1
    assert candidates[0]['metrics']['file_count']==2
    assert {(item['path'],item['start_line'],item['end_line']) for item in candidates[0]['evidence']}=={('a.py',1,1),('c.py',1,1)}
    assert candidates[0]['status']=='static_candidate'


@pytest.mark.parametrize('variant',['unresolved-many','dynamic-flag','ambiguous-only'])
def test_V06_unresolved_conditions_and_grouping(tmp_path,variant):
    nodes=[node('a','a.py'),node('a2','a.py'),node('b','b.py')]
    if variant=='dynamic-flag':
        nodes[0].flags=['dynamic_attr']; edges=[]
    elif variant=='unresolved-many':
        nodes[1].metadata['unresolved_references']=[{'name':'missing','resolution':'unresolved','confidence':'dynamic_required','evidence':{'file_path':'a.py','start_line':2,'end_line':2}}]
        nodes.append(node('external',kind='external'))
        edges=[edge('a','b',Confidence.DYNAMIC_REQUIRED,Resolution.UNRESOLVED,evidence=SourceSpan('a.py',1,1)),edge('a2','b',Confidence.DYNAMIC_REQUIRED,Resolution.UNRESOLVED,evidence=SourceSpan('a.py',2,2)),edge('a','external',Confidence.DYNAMIC_REQUIRED,Resolution.UNRESOLVED,evidence=SourceSpan('a.py',3,3)),edge('a','a2',Confidence.DYNAMIC_REQUIRED,Resolution.UNRESOLVED,evidence=SourceSpan('a.py',4,4))]
    else:
        edges=[edge('a','b',resolution=Resolution.AMBIGUOUS)]
    snap,result=converted({'a.py':'x\ny\nz\nw','b.py':'z'},nodes,edges)
    candidates=[c for c in payload(snap,result,tmp_path)['candidates'] if c['kind']=='unresolved_boundary']
    assert bool(candidates)==(variant!='ambiguous-only')
    assert len({(c['target'],c['kind']) for c in candidates})==len(candidates)
    if variant=='unresolved-many':
        source_candidate=next(c for c in candidates if c['target']=='file:a.py')
        def positions(value):
            if isinstance(value,dict):
                path=value.get('path',value.get('file_path'))
                found={(path,value['start_line'])} if path and 'start_line' in value else set()
                return found.union(*(positions(child) for child in value.values()))
            if isinstance(value,list):
                return set().union(*(positions(child) for child in value))
            return set()
        assert {('a.py',1),('a.py',2),('a.py',3),('a.py',4)}<=positions(source_candidate['evidence'])
        assert all(c['target']!='external' for c in candidates)
        assert source_candidate['status']=='static_candidate'
        details=serialize(result)['details']
        assert next(n for n in details['nodes'] if n['id']=='a2')['metadata']['unresolved_references'][0]['name']=='missing'


@pytest.mark.parametrize('source',['span','metadata','implementation','declaration'])
def test_V04_ownership_priority_and_normalization(source):
    from analysis.file_graph import to_file_architecture
    child=node('child',None,metadata={'file_path':'b.py'} if source in ('span','metadata') else {})
    parent=node('parent','a.py','class')
    if source=='span': child.span=SourceSpan('a.py',1,1)
    edges=[edge('child','parent',relation='IMPLEMENTED_BY')] if source=='implementation' else [edge('parent','child',relation='CONTAINS')]
    result=to_file_architecture(architecture([parent,child],edges),snapshot({'a.py':'x','b.py':'y'}))
    expected='file:b.py' if source=='metadata' else 'file:a.py'
    assert serialize(result)['details']['node_files']['child']==expected


def test_V03_every_raw_relation_field_and_order_preserved():
    nodes=[node('a','a.py'),node('b','b.py'),node('candidate','c.py')]
    first=edge('a','b',Confidence.STATIC_INFERRED,Resolution.AMBIGUOUS,weight=7,candidates=['candidate'],evidence=SourceSpan('a.py',1,2))
    second=edge('a','b',relation='IMPORTS',evidence=SourceSpan('a.py',2,2))
    original=serialize(architecture(nodes,[first,second]))
    _,result=converted({'a.py':'x\ny','b.py':'z','c.py':'q'},nodes,[first,second])
    details=serialize(result)['details']
    assert details['edges']==original['edges']
    assert details['nodes']==original['nodes']
    assert details['file_nodes']=={'file:a.py':['a'],'file:b.py':['b'],'file:c.py':['candidate']}
