import re

import pytest
from playwright.sync_api import expect

from tests.unified_support import CDN_URL, CORE, METRICS, CATEGORIES, architecture, node, edge, rows

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
def test_V5_symbol_report_keyboard_and_modal_without_graph(open_report,width):
    page=open_report(architecture([node('a')],[edge('a','a')]),width=width)
    assert page.evaluate('window.ReportGraph == null')
    assert page.evaluate('document.documentElement.scrollWidth') <= width
    for selector in ['#category-filter select','#node-search','#metric-sort select','#candidate-kind-filter select']:
        page.locator(selector).focus(); assert page.locator(selector).evaluate('(e)=>e===document.activeElement')
    page.locator('[data-node-id="a"]').first.focus(); page.keyboard.press('Enter')
    expect(page.get_by_role('dialog')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.get_by_role('dialog')).to_be_hidden()
    assert set(page.external_requests) <= {CDN_URL} and page.unhandled_errors==[]
