import copy
import re

import pytest
from playwright.sync_api import expect

from tests.unified_support import CORE, METRICS, CATEGORIES, HOSTILE, architecture, node, edge, rows, select, topology, open_disclosures


def test_V1_six_representatives_category_values_and_sort(open_report):
    nodes = [node('b', value=9), node('a', value=9), node('c', value=3), node('d', value=1)] + [node(c, c, value=20) for c in CATEGORIES[1:]]
    expected_groups={'pagerank':['a','b','c','d'],'betweenness_centrality':['d','c','b','a'],'hop_2_token_cost':['b','d','a','c'],'weighted_centrality_cost':['c','a','d','b'],'fan_in':['d','b','c','a'],'fan_out':['b','c','d','a']}
    for metric,order in expected_groups.items():
        if metric=='pagerank': continue
        for n in nodes[:4]: n['metadata']['analysis'][metric]=[8,6,4,2][(order+[ident for ident in ['a','b','c','d'] if ident not in order]).index(n['id'])]
    page = open_report(architecture(nodes))
    assert page.locator('#category-filter').input_value() == 'production'
    assert page.locator('[data-metric-group]').count() == 6
    for metric in CORE:
        group = page.locator(f'[data-metric-group="{metric}"]')
        assert group.locator('[data-node-id]').evaluate_all('(els)=>els.map(e=>e.dataset.nodeId)') == expected_groups[metric]
        assert str(9 if metric=='pagerank' else 8) in group.inner_text()
    assert rows(page) == ['a','b','c','d']
    for category in ('all', *CATEGORIES):
        page.locator('#category-filter').select_option(category)
        expected = ['generated','test','unknown','vendored','a','b','c','d'] if category == 'all' else ['a','b','c','d'] if category == 'production' else [category]
        assert rows(page) == expected
        if category == 'production':
            assert '9' in page.locator('[data-metric-group="pagerank"]').inner_text()
    page.locator('#category-filter').select_option('all')
    page.locator('#node-search').fill('  SRC/APP.PY  ')
    assert rows(page) == ['a','b','c','d']
    page.locator('#node-search').fill('unknown')
    assert rows(page) == ['unknown']
    page.locator('#node-search').fill('SAME')
    assert len(rows(page)) == 8
    page.locator('#node-search').fill('no-match')
    assert rows(page) == []
    assert page.locator('#list-count').inner_text()
    page.locator('#node-search').fill('')
    options = page.locator('#metric-sort option').evaluate_all('(els)=>els.map(e=>e.value)')
    assert set(METRICS) | {'token_cost','effective_token_cost','identifier_file_count'} <= set(options)
    page.locator('#metric-sort').select_option('token_cost')
    assert rows(page) == sorted(n['id'] for n in nodes)


@pytest.mark.parametrize('count',[0,1,50,51],ids=['empty','one','full-page','next-page'])
def test_V3_list_boundaries_and_reset(open_report,count):
    page = open_report(architecture([node(f'n{i:03}',value=1) for i in range(count)]))
    assert len(rows(page)) == min(count,50)
    assert page.locator('#page-prev').is_disabled()
    assert page.locator('#page-next').is_disabled() == (count <= 50)
    if count == 51:
        page.locator('#page-next').click()
        assert rows(page) == ['n050']
        page.locator('#page-prev').click()
        assert rows(page)[0] == 'n000'
        for control,value in [('#node-search','same'),('#metric-sort','fan_in'),('#category-filter','all'),('#candidate-kind-filter','all')]:
            page.locator('#page-next').click()
            if control == '#node-search': page.locator(control).fill(value)
            else: page.locator(control).select_option(value)
            assert rows(page)[0] == 'n000'


@pytest.mark.parametrize('count',[0,1,30,31],ids=['isolated','single','limit','omitted'])
def test_V2_neighbor_boundaries_and_omitted_evidence(open_report,count):
    nodes = [node('center',value=100)] + [node(f'n{i:02}', 'test' if i==0 else 'production',value=1) for i in range(count)]
    edges = [edge('center',f'n{i:02}',line=i+10) for i in range(count)]
    page = open_report(architecture(nodes,edges))
    assert page.evaluate('window.ReportGraph') is None
    select(page,'center')
    graph = topology(page)
    assert {n['id'] for n in graph['nodes']} == {'center'} | {f'n{i:02}' for i in range(min(count,30))}
    assert len(graph['edges']) == min(count,30)
    assert all(e['source']=='center' for e in graph['edges'])
    assert page.locator('#graph-status').get_attribute('data-shown') == str(min(count,30))
    assert page.locator('#graph-status').get_attribute('data-omitted') == str(max(0,count-30))
    assert page.locator('[data-relationship-row]').count() == count
    if count:
        assert f'evidence-{count+9}.py' in page.locator('#relationship-list').inner_text()
        open_disclosures(page.locator('#relationship-list'))
        expect(page.locator('#relationship-list')).to_contain_text(f'n{count-1:02}')
        page.locator('#graph-zoom-in').click()
        zoom = page.evaluate('ReportGraph.zoom()')
        page.locator('#graph-zoom-out').click()
        assert page.evaluate('ReportGraph.zoom()') < zoom
        page.locator('#graph-fit').click()
        page.evaluate("ReportGraph.getElementById('n00').emit('tap')")
        assert page.locator('#node-detail').get_attribute('data-selected-node') == 'n00'


def test_V2_weight_fanin_id_grouping_layout_relationship_paging(open_report):
    nodes = [node('center',value=100)] + [node(f'n{i:02}',value=1) for i in range(32)]
    nodes[-1]['metadata']['analysis']['fan_in']=999
    edges = [edge('center',f'n{i:02}',confidence='static_inferred',line=i+10) for i in range(32)]
    edges += [edge('n30','center',line=90),edge('center','n31',line=91)]
    edges += [edge('center','n00',confidence='static_inferred',line=100+i) for i in range(20)]
    edges += [edge('center','center',line=200),edge('n00','n01',line=201)]
    page = open_report(architecture(nodes,edges)); select(page,'center')
    graph = topology(page)
    assert {n['id'] for n in graph['nodes']} == {'center','n30','n31'} | {f'n{i:02}' for i in range(28)}
    assert len(graph['edges']) == 31
    center = next(n['pos'] for n in graph['nodes'] if n['id']=='center')
    both = next(n['pos'] for n in graph['nodes'] if n['id']=='n30')
    out = next(n['pos'] for n in graph['nodes'] if n['id']=='n31')
    assert both['y'] > center['y'] and out['x'] > center['x']
    assert page.locator('[data-relationship-row]').count() == 50
    page.locator('#relationship-next').click()
    assert page.locator('[data-relationship-row]').count() == 5
    page.locator('#relationship-prev').click()
    page.evaluate("ReportGraph.edges().filter(e => e.source().id()==='center' && e.target().id()==='n00').emit('tap')")
    assert 'evidence-119.py' in page.locator('#node-detail').inner_text()


def test_V3_detail_secondary_fields_and_source_paths(open_report):
    n=node('a'); b=node('b'); b['span']['file_path']='other/same.py'
    page=open_report(architecture([n,b],collection_count=51)); select(page,'a')
    detail=page.locator('#node-detail')
    open_disclosures(detail)
    expect(detail).to_contain_text('DOC_ORACLE')
    expect(detail).to_contain_text('def same(value: int) -> int')
    text=detail.inner_text()
    for literal in ['a','src/app.py','def same(value: int) -> int','DOC_ORACLE','FLAG_ORACLE','META_ORACLE','42','21','7','3','2','4']:
        assert literal in text
    assert 'other/same.py' in page.locator('#node-list').inner_text()
    appendix=page.locator('#report-appendix')
    assert appendix.locator('[data-collection-row]').count() == 0
    appendix.locator(':scope > summary').click()
    appendix.locator('details > summary').first.wait_for(state='visible', timeout=5000)
    open_disclosures(appendix)
    expect(appendix).to_contain_text('37')
    assert 'sampled' in appendix.inner_text()
    collection=appendix.locator('[data-collection-key="oracle"]')
    expect(collection.locator('[data-collection-row]')).to_have_count(50)
    collection.locator('[data-collection-next]').click()
    expect(collection.locator('[data-collection-row]')).to_have_count(1)
    assert 'collection-050' in collection.inner_text()
    collection.locator('[data-collection-prev]').click()
    expect(collection.locator('[data-collection-row]')).to_have_count(50)


def test_V1_V6_missing_zero_no_production(open_report):
    n=node('missing',value=0); n['metadata']['analysis'].pop('pagerank')
    page=open_report(architecture([n,node('zero',value=0)]))
    assert rows(page)==['zero','missing']
    assert '—' in page.locator('[data-node-row="missing"]').inner_text()
    assert re.search('(모두|모든|전부).*0',page.locator('[data-metric-group="fan_in"]').inner_text())
    page=open_report(architecture([node('test','test')]))
    assert rows(page)==[]
    assert page.locator('#category-filter').input_value()=='production'
    assert re.search('분류|운영',page.locator('#node-list').inner_text())
    page.locator('#category-filter').select_option('test'); assert rows(page)==['test']


@pytest.mark.parametrize('width',[390,1440],ids=['mobile','desktop'])
def test_V5_offline_keyboard_hierarchy(open_report,width):
    page=open_report(architecture([node('a')],[edge('a','a')]),width=width)
    assert page.evaluate('window.ReportGraph') is None
    assert page.evaluate('document.documentElement.scrollWidth') <= width
    assert page.locator('#report-summary').evaluate('(e)=>e.compareDocumentPosition(document.querySelector("#node-detail")) & Node.DOCUMENT_POSITION_FOLLOWING')
    for selector in ['#category-filter select','#node-search','#metric-sort select','#candidate-kind-filter select']:
        page.locator(selector).focus(); assert page.locator(selector).evaluate('(e)=>e===document.activeElement')
    page.locator('[data-node-id="a"]').first.focus(); page.keyboard.press('Enter')
    assert page.locator('#node-detail').get_attribute('data-selected-node')=='a'
    for selector in ['#graph-fit','#graph-zoom-in','#graph-zoom-out']:
        page.locator(selector).focus(); page.keyboard.press('Enter')
    assert page.external_requests==[] and page.unhandled_errors==[]


def test_V6_hostile_source_text_and_graph_failure(open_report):
    n=node('a'); n.update(label=HOSTILE,docstring=HOSTILE); n['metadata']['custom']=HOSTILE
    e=edge('a','a'); e['evidence']['file_path']=HOSTILE
    page=open_report(architecture([n],[e]), title=HOSTILE)
    select(page,'a')
    open_disclosures(page.locator('#node-detail'))
    assert page.evaluate('window.attack') is None
    expect(page.locator('#node-detail')).to_contain_text(HOSTILE)
    assert page.external_requests==[]
    fault="Object.defineProperty(window,'cytoscape',{configurable:true,get(){return ()=>{throw new Error('ORACLE_GRAPH_FAILURE')}},set(){}})"
    page=open_report(architecture([node('a'),node('b')],[edge('a','b')]),initial_script=fault)
    select(page,'a')
    assert re.search('오류|실패|불가|ORACLE_GRAPH_FAILURE',page.locator('#graph-status').inner_text())
    assert page.locator('[data-relationship-row]').count()==1
    select(page,'b'); assert 'src/app.py' in page.locator('#node-detail').inner_text()
    page.locator('#node-search').fill('b'); assert rows(page)==['b']
    assert page.unhandled_errors==[]


def test_V2_sixty_arrows_incoming_layout_and_configured_weights(open_report,tmp_path):
    from tests.unified_support import bottleneck_fixture
    nodes=[node('center',value=100)]+[node(f'n{i:02}',value=1) for i in range(31)]
    edges=[e for i in range(30) for e in (edge('center',f'n{i:02}',line=i+10),edge(f'n{i:02}','center',line=i+50))]
    edges += [edge('n30','center',confidence='static_inferred',line=90)]
    payload=bottleneck_fixture(tmp_path,nodes,edges,candidate_count=0)
    payload['edge_weights']['confidence']['static_certain']=0.1
    payload['edge_weights']['confidence']['static_inferred']=0.9
    arch=architecture(nodes,edges)
    arch['stats']['analysis']['edge_weights']=copy.deepcopy(payload['edge_weights'])
    page=open_report(arch,payload);select(page,'center')
    graph=topology(page)
    assert len(graph['edges'])==59
    assert {n['id'] for n in graph['nodes']}=={'center','n30'}|{f'n{i:02}' for i in range(29)}
    center=next(n['pos'] for n in graph['nodes'] if n['id']=='center')
    incoming=next(n['pos'] for n in graph['nodes'] if n['id']=='n30')
    assert incoming['x']<center['x']
    page=open_report(architecture(nodes[:-1],edges[:-1]));select(page,'center')
    assert len(topology(page)['edges'])==60
