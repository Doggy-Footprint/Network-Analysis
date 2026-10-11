import copy

import pytest
from playwright.sync_api import expect

from tests.unified_support import CORE, architecture, node, edge, document, rows, bottleneck_fixture
from tests.file_analysis_browser_support import EVIDENCE_DIR, file_node, symbol, file_arch, file_bottlenecks, record_browser, measure_html
from tests.report_redesign_support import dialog, goto_list


@pytest.mark.parametrize('count', [100, 101], ids=['top100', 'top101'])
def test_V09_file_top100_and_full_transition(open_report, count):
    files = [file_node(f'src/n{i:03}.py', value=200-i) for i in range(count)]
    page = open_report(file_arch(files))
    goto_list(page)
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
    goto_list(page)
    assert rows(page) == [f'file:src/n{i:03}.py' for i in range(50)]
    assert page.locator('#page-next').is_disabled() == (count == 50)
    if count == 51:
        page.locator('#page-next').click()
        assert rows(page) == ['file:src/n050.py']
        page.locator('#page-prev').click()
        assert rows(page)[0] == 'file:src/n000.py'
    record_browser(f'V09-page{count}', {'count': count, 'assertions': 'exact page contents and next/previous enabled state'})


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


def test_V10_file_granularity_lists_and_cards_hold_files_only_and_filters(open_report):
    arch = mixed_fixture()
    bottlenecks=file_bottlenecks(arch)
    for rankings in [bottlenecks['dependency_network']['rankings'],*bottlenecks['dependency_network']['rankings_by_category'].values()]:
        for metric,ranking in rankings.items():
            rankings[metric]=[row for row in ranking if row['node_id']!='external-boundary']
    page = open_report(arch, bottlenecks)
    for metric in CORE:
        ids = page.locator(f'[data-metric-group="{metric}"] [data-node-id]').evaluate_all('(els)=>els.map(e=>e.dataset.nodeId)')
        assert ids and all(ident.startswith('file:') for ident in ids)
    goto_list(page)
    assert all(ident.startswith('file:') for ident in rows(page))
    page.locator('#category-filter').select_option('all')
    assert set(rows(page))=={'file:src/a.py','file:src/b.py','file:tests/test_a.py'}
    for metric in CORE:
        ids=page.locator(f'[data-metric-group="{metric}"] [data-node-id]').evaluate_all('(els)=>els.map(e=>e.dataset.nodeId)')
        assert ids and 'external-boundary' not in ids and all(ident.startswith('file:') for ident in ids)
    page.locator('#category-filter').select_option('production')
    page.locator('#node-search').fill('SRC/B.PY'); assert rows(page) == ['file:src/b.py']
    page.locator('#node-search').fill(''); page.locator('#category-filter').select_option('test')
    assert rows(page) == ['file:tests/test_a.py']
    page.locator('#category-filter').select_option('production')
    for kind, target in [('large_node','file:src/a.py'),('evidence_spread','file:src/b.py')]:
        page.locator('#candidate-kind-filter').select_option(kind); assert rows(page)==[target]
    page.locator('#candidate-kind-filter').select_option('all')
    page.locator(f'{"#node-list"} [data-node-row="file:src/a.py"] [data-node-id]').first.click()
    expect(dialog(page)).to_be_visible()
    assert 'src/a.py' in dialog(page).inner_text()
    record_browser('V10-transitions', {'boundary_observation':{'excluded_from_all_file_list':True,'excluded_from_all_six_representatives':True},'items': ['file-only-lists','search','category','candidate-filter','modal-opens-for-file']})


def test_V14_synthetic_five_fresh_contexts(chromium,tmp_path):
    nodes=[node(f'n{i:05}','test' if i%100==99 else 'production',value=10000-i) for i in range(10000)]
    edges=[edge(f'n{i:05}',f'n{(i+delta)%10000:05}',line=delta) for i in range(10000) for delta in (1,2,3)]
    payload=bottleneck_fixture(tmp_path,nodes,edges,candidate_count=1000)
    path=tmp_path/'synthetic.html'; path.write_text(document(architecture(nodes,edges),payload),encoding='utf-8')
    measure_html(chromium,path,'synthetic')
