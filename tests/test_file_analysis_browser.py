import copy

import pytest
from playwright.sync_api import expect

from tests.unified_support import CORE, HOSTILE, architecture, node, edge, document, rows, select, topology, open_disclosures, bottleneck_fixture
from tests.file_analysis_browser_support import EVIDENCE_DIR, file_node, symbol, file_arch, file_bottlenecks, record_browser, measure_html


@pytest.mark.parametrize('count', [100, 101], ids=['top100', 'top101'])
def test_V09_file_top100_and_full_transition(open_report, count):
    files = [file_node(f'src/n{i:03}.py', value=200-i) for i in range(count)]
    page = open_report(file_arch(files))
    assert page.locator('#list-limit select').input_value() == '100'
    assert rows(page) == [f'file:src/n{i:03}.py' for i in range(50)]
    page.locator('#page-next').click()
    assert rows(page) == [f'file:src/n{i:03}.py' for i in range(50, 100)]
    assert page.locator('#page-next').is_disabled()
    expect(page.locator('#list-count')).to_contain_text(f'100개 표시 / 조건 일치 {count}개')
    page.locator('#list-limit select').select_option('all')
    assert rows(page)[0] == 'file:src/n000.py'
    if count == 101:
        page.locator('#page-next').click()
        page.locator('#page-next').click()
        assert rows(page) == ['file:src/n100.py']
    record_browser(f'V09-top{count}', {'count': count, 'assertions': 'exact IDs, upper limit and full transition'})


@pytest.mark.parametrize('count', [50, 51], ids=['page50', 'page51'])
def test_V09_file_page_boundaries(open_report, count):
    page = open_report(file_arch([file_node(f'src/n{i:03}.py') for i in range(count)]))
    assert rows(page) == [f'file:src/n{i:03}.py' for i in range(50)]
    assert page.locator('#page-next').is_disabled() == (count == 50)
    if count == 51:
        page.locator('#page-next').click()
        assert rows(page) == ['file:src/n050.py']
        page.locator('#page-prev').click()
        assert rows(page)[0] == 'file:src/n000.py'
    record_browser(f'V09-page{count}', {'count': count, 'assertions': 'exact page contents and next/previous enabled state'})


@pytest.mark.parametrize('count', [0, 1, 30, 31], ids=['neighbors0', 'neighbors1', 'neighbors30', 'neighbors31'])
def test_V09_symbol_neighbor_limit_and_full_evidence(open_report, count):
    files = [file_node('src/center.py', 100)] + [file_node(f'src/n{i:02}.py') for i in range(count)]
    symbols = [symbol('center', 'src/center.py')] + [symbol(f'n{i:02}', f'src/n{i:02}.py') for i in range(count)]
    relations = [edge('center', f'n{i:02}', line=i+10) for i in range(count)]
    if count == 31:
        files[-1]['metadata']['analysis']['fan_in'] = 999
        relations[29]['confidence'] = 'static_inferred'
    page = open_report(file_arch(files, symbols, relations))
    assert page.evaluate('window.ReportGraph') is None
    select(page, 'file:src/center.py')
    select(page, 'center')
    assert page.locator('#node-detail').get_attribute('data-selected-file') == 'file:src/center.py'
    assert page.locator('#node-detail').get_attribute('data-detail-kind') == 'symbol'
    observed = topology(page)
    expected_neighbors = list(range(count)) if count <= 30 else [30] + list(range(29))
    assert {n['id'] for n in observed['nodes']} == {'center'} | {f'file:src/n{i:02}.py' for i in expected_neighbors}
    assert len(observed['edges']) == min(count, 30)
    assert page.locator('#graph-status').get_attribute('data-shown') == str(min(count, 30))
    assert page.locator('#graph-status').get_attribute('data-omitted') == str(max(0, count-30))
    relationships = page.locator('#relationship-list')
    assert relationships.locator('[data-relationship-row]').count() == count
    if count:
        open_disclosures(relationships)
        expect(relationships).to_contain_text(f'n{count-1:02}')
        expect(relationships).to_contain_text(f'evidence-{count+9}.py')
        if count == 31:
            expect(relationships).to_contain_text('n29')
            expect(relationships).to_contain_text('evidence-39.py')
    record_browser(f'V09-neighbors{count}', {'shown': min(count,30), 'omitted': max(0,count-30), 'all_original_evidence': count})


def test_V09_external_group_original_targets_and_relationship_paging(open_report):
    files = [file_node('src/a.py', 100), file_node('src/b.py')]
    symbols = [symbol('a', 'src/a.py'), symbol('b1', 'src/b.py'), symbol('b2', 'src/b.py')]
    relations = [edge('a', 'b1' if i%2 == 0 else 'b2', line=100+i) for i in range(51)]
    page = open_report(file_arch(files, symbols, relations))
    select(page, 'file:src/a.py'); select(page, 'a')
    graph = topology(page)
    assert {n['id'] for n in graph['nodes']} == {'a', 'file:src/b.py'}
    assert [(e['source'],e['target']) for e in graph['edges']] == [('a','file:src/b.py')]
    assert page.locator('#graph-status').get_attribute('data-shown') == '1'
    assert page.locator('#graph-status').get_attribute('data-omitted') == '0'
    assert page.locator('#relationship-list [data-relationship-row]').count() == 50
    open_disclosures(page.locator('#relationship-list'))
    expect(page.locator('#relationship-list')).to_contain_text('b1')
    expect(page.locator('#relationship-list')).to_contain_text('b2')
    page.locator('#relationship-next').click()
    assert page.locator('#relationship-list [data-relationship-row]').count() == 1
    open_disclosures(page.locator('#relationship-list'))
    expect(page.locator('#relationship-list')).to_contain_text('evidence-150.py')
    expect(page.locator('#relationship-list')).to_contain_text('b1')
    page.locator('#relationship-prev').click()
    assert page.locator('#relationship-list [data-relationship-row]').count() == 50
    record_browser('V09-external-file-group-all-evidence', {'group_count': 1, 'original_targets': ['b1','b2'], 'relationship_pages': [50,1]})


def mixed_fixture():
    files = [file_node('src/a.py',100), file_node('src/b.py',2), file_node('tests/test_a.py',1,'test')]
    symbols = [symbol('Outer','src/a.py','class'), symbol('Inner','src/a.py','class'),
               symbol('method','src/a.py','method'), symbol('field','src/a.py','field'),
               symbol('top','src/a.py'), symbol('nested','src/a.py'), symbol('ref','src/a.py','reference'),
               symbol('target','src/b.py'), symbol('role','src/a.py','service'),
               symbol('method-role','src/a.py','dependency'),symbol('enum-ref','src/a.py','enum'),
               symbol('config-ref','src/a.py','configuration')]
    for item in symbols:
        if item['id'] in ('role','method-role'):
            item.update(span=None,provenance='fastapi',metadata={'framework':'fastapi'})
        elif item['id']=='enum-ref':
            item.update(language='kotlin',provenance='kotlin-core')
        elif item['id']=='config-ref':
            item.update(provenance='config')
    relations = [edge('role','Outer'), edge('top','target'), edge('method','target'), edge('top','field')]
    relations[0]['relation']='IMPLEMENTED_BY'
    method_role=edge('method-role','method'); method_role['relation']='IMPLEMENTED_BY'
    boundary=node('external-boundary','unknown',value=100000)
    boundary.update(label='EXTERNAL_BOUNDARY_ORACLE',kind='external',group='external',category='external')
    boundary['cost']={'token_estimate':0,'char_count':0,'line_count':0}
    boundary['metadata']['analysis'].update(token_cost=0,effective_token_cost=0)
    boundary['metadata']['analysis'].pop('identifier_file_count')
    boundary['metadata']['analysis'].pop('identifier_file_count_by_context')
    symbols.append(copy.deepcopy(boundary))
    symbols[-1]['metadata'].pop('analysis')
    relations.extend([method_role,edge('top','enum-ref'),edge('top','config-ref'),edge('top','external-boundary',line=777)])
    owners = {'Inner':'Outer','method':'Outer','field':'Outer','nested':'top'}
    mappings = {s['id']:'file:src/a.py' for s in symbols}; mappings['target']='file:src/b.py'; mappings['external-boundary']=None
    result=file_arch(files,symbols,relations,owners,mappings)
    result['nodes'].append(boundary)
    result['stats']['analysis']['node_metrics']['external-boundary']=copy.deepcopy(boundary['metadata']['analysis'])
    return result


def test_V10_file_symbol_external_back_fold_roles_and_filters(open_report):
    arch = mixed_fixture()
    bottlenecks=file_bottlenecks(arch)
    for rankings in [bottlenecks['dependency_network']['rankings'],*bottlenecks['dependency_network']['rankings_by_category'].values()]:
        for metric,ranking in rankings.items():
            rankings[metric]=[row for row in ranking if row['node_id']!='external-boundary']
    page = open_report(arch, bottlenecks)
    assert page.evaluate('window.ReportGraph') is None
    for metric in CORE:
        ids = page.locator(f'[data-metric-group="{metric}"] [data-node-id]').evaluate_all('(els)=>els.map(e=>e.dataset.nodeId)')
        assert ids and all(ident.startswith('file:') for ident in ids)
    assert all(ident.startswith('file:') for ident in rows(page))
    page.locator('#category-filter').select_option('all')
    assert set(rows(page))=={'file:src/a.py','file:src/b.py','file:tests/test_a.py'}
    for metric in CORE:
        ids=page.locator(f'[data-metric-group="{metric}"] [data-node-id]').evaluate_all('(els)=>els.map(e=>e.dataset.nodeId)')
        assert ids and 'external-boundary' not in ids and all(ident.startswith('file:') for ident in ids)
    page.locator('#category-filter').select_option('production')
    select(page,'file:src/a.py')
    detail = page.locator('#node-detail')
    assert detail.get_attribute('data-detail-kind') == 'file'
    listing = page.locator('#file-symbols')
    expect(listing.locator('[data-symbol-id="Outer"] button[data-node-id="Outer"]').first).to_be_visible()
    expect(listing.locator('[data-symbol-id="top"] button[data-node-id="top"]').first).to_be_visible()
    expect(listing.locator('[data-symbol-id="Outer"] .symbol-children [data-symbol-id="Inner"]')).to_have_count(1)
    expect(listing.locator('[data-symbol-id="top"] .symbol-children [data-symbol-id="nested"]')).to_have_count(1)
    folded = listing.locator('[data-symbol-id="Outer"] details').filter(has=page.get_by_text('메서드 · 필드 2개',exact=True)).first
    assert folded.count() == 1 and not folded.evaluate('(e)=>e.open')
    expect(folded.locator('[data-folded-symbol-id="method"]')).not_to_be_visible()
    expect(folded.locator('[data-folded-symbol-id="field"]')).not_to_be_visible()
    folded.locator('summary').click()
    expect(folded.locator('[data-folded-symbol-id="method"]')).to_have_count(1)
    expect(folded.locator('[data-folded-symbol-id="method"]')).to_be_visible()
    expect(folded.locator('[data-folded-symbol-id="field"]')).to_have_count(1)
    expect(folded.locator('[data-folded-symbol-id="field"]')).to_be_visible()
    expect(folded.locator('[data-folded-symbol-id="method"] .framework-role')).to_contain_text('dependency')
    expect(listing.locator('[data-symbol-id="Outer"] .framework-role').filter(has_text='service')).to_have_count(1)
    expect(listing.locator('[data-symbol-id="Outer"] .framework-role').filter(has_text='service')).to_be_visible()
    for hidden in ('role','method-role','enum-ref','config-ref'):
        assert listing.locator(f'button[data-node-id="{hidden}"]').count()==0
    select(page,'Outer')
    assert detail.get_attribute('data-selected-file') == 'file:src/a.py'
    page.locator('#back-to-file').click()
    assert detail.get_attribute('data-selected-node') == 'file:src/a.py'
    select(page,'top')
    graph = topology(page)
    assert {n['id'] for n in graph['nodes']} == {'top','Outer','file:src/a.py','file:src/b.py','external-boundary'}
    open_disclosures(page.locator('#relationship-list'))
    expect(page.locator('#relationship-list')).to_contain_text('enum-ref')
    expect(page.locator('#relationship-list')).to_contain_text('config-ref')
    expect(page.locator('#relationship-list')).to_contain_text('external-boundary')
    expect(page.locator('#relationship-list')).to_contain_text('evidence-777.py')
    page.evaluate("ReportGraph.getElementById('external-boundary').emit('tap')")
    assert detail.get_attribute('data-selected-node')=='external-boundary'
    select(page,'file:src/a.py'); select(page,'top')
    page.evaluate("ReportGraph.getElementById('file:src/a.py').emit('tap')")
    assert detail.get_attribute('data-selected-node')=='file:src/a.py'
    assert detail.get_attribute('data-detail-kind')=='file'
    select(page,'top')
    page.evaluate("ReportGraph.getElementById('file:src/b.py').emit('tap')")
    assert detail.get_attribute('data-selected-node') == 'file:src/b.py'
    assert detail.get_attribute('data-detail-kind') == 'file'
    select(page,'file:src/a.py'); select(page,'top'); page.locator('#back-to-file').click()
    assert detail.get_attribute('data-selected-node') == 'file:src/a.py'
    page.locator('#node-search').fill('SRC/B.PY'); assert rows(page) == ['file:src/b.py']
    page.locator('#node-search').fill(''); page.locator('#category-filter').select_option('test')
    assert rows(page) == ['file:tests/test_a.py']
    page.locator('#category-filter').select_option('production')
    for kind, target in [('large_node','file:src/a.py'),('evidence_spread','file:src/b.py')]:
        page.locator('#candidate-kind-filter').select_option(kind); assert rows(page)==[target]
    record_browser('V10-transitions', {'boundary_observation':{'excluded_from_all_file_list':True,'excluded_from_all_six_representatives':True,'graph_and_original_evidence_retained':True},'items': ['initial-no-graph','file-to-class','file-to-function','symbol-to-external-file','back-to-file','method-fold','field-fold','nested-owner','framework-role','search','category','candidate-filter']})


def test_V10_framework_only_available_information(open_report):
    service = symbol('only-service','src/service.py','service')
    service['provenance']='fastapi'
    arch = file_arch([file_node('src/service.py')],[service])
    page = open_report(arch); select(page,'file:src/service.py')
    expect(page.locator('#file-symbols')).to_contain_text('only-service')
    assert page.locator('#file-symbols [data-symbol-id="only-service"]').count() == 1
    select(page,'only-service')
    assert page.locator('#node-detail').get_attribute('data-selected-file')=='file:src/service.py'
    assert page.external_requests==[] and page.unhandled_errors==[]
    record_browser('V10-framework-only', {'only_available_framework_node': 'only-service'})


@pytest.mark.parametrize('surface',['title','path','docstring','evidence','candidate'],ids=lambda value:value)
def test_V11_source_surfaces_inert_and_offline_navigation(open_report,surface):
    attack = HOSTILE.replace('window.attack=1',f'window.attack_{surface}=1') + f'ORACLE_{surface}'
    files = [file_node('src/a.py',100),file_node('src/b.py')]
    symbols = [symbol('a','src/a.py'),symbol('b','src/b.py')]
    relation=edge('a','b')
    kwargs={}
    if surface=='title': kwargs['title']=attack
    elif surface=='path': files[0]['span']['file_path']=attack; files[0]['metadata']['file_path']=attack
    elif surface=='docstring': symbols[0]['docstring']=attack
    elif surface=='evidence': relation['evidence']['file_path']=attack
    arch=file_arch(files,symbols,[relation]); payload=file_bottlenecks(arch,1)
    if surface=='candidate': payload['candidates'][0]['evidence']['path']=attack
    page=open_report(arch,payload,**kwargs)
    select(page,'file:src/a.py')
    if surface=='candidate': open_disclosures(page.locator('#node-detail')); expect(page.locator('#node-detail')).to_contain_text(attack)
    if surface=='path': expect(page.locator('#node-detail')).to_contain_text(attack)
    select(page,'a'); open_disclosures(page.locator('#node-detail'))
    if surface=='docstring': expect(page.locator('#node-detail')).to_contain_text(attack)
    if surface=='evidence': open_disclosures(page.locator('#relationship-list')); expect(page.locator('#relationship-list')).to_contain_text(attack)
    if surface=='title': expect(page.get_by_text(attack,exact=True).first).to_be_visible()
    page.evaluate("ReportGraph.getElementById('file:src/b.py').emit('tap')")
    assert page.locator('#node-detail').get_attribute('data-selected-node')=='file:src/b.py'
    select(page,'b'); page.locator('#back-to-file').click()
    assert page.locator('#node-detail').get_attribute('data-selected-node')=='file:src/b.py'
    assert page.evaluate(f'window.attack_{surface}') is None
    assert page.external_requests==[] and page.unhandled_errors==[]
    record_browser(f'V11-{surface}', {'surface':surface,'unexpected_script':0,'external_requests':0,'unhandled_errors':0,'offline_navigation':True})


def test_V14_synthetic_five_fresh_contexts(chromium,tmp_path):
    nodes=[node(f'n{i:05}','test' if i%100==99 else 'production',value=10000-i) for i in range(10000)]
    edges=[edge(f'n{i:05}',f'n{(i+delta)%10000:05}',line=delta) for i in range(10000) for delta in (1,2,3)]
    payload=bottleneck_fixture(tmp_path,nodes,edges,candidate_count=1000)
    path=tmp_path/'synthetic.html'; path.write_text(document(architecture(nodes,edges),payload),encoding='utf-8')
    measure_html(chromium,path,'synthetic')
