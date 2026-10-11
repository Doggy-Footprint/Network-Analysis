import re

import pytest
from playwright.sync_api import expect

from tests.unified_support import CDN_URL, CORE, CATEGORIES, architecture, node, edge, bottleneck_fixture, rows, tab_to, keyboard_choose


def test_VR1_cards_top10_by_category_and_precedence(open_report, tmp_path):
    assigned = [('p0', 'production', 91), ('p1', 'production', 81), ('t0', 'test', 71), ('t1', 'test', 61), ('g0', 'generated', 51), ('g1', 'generated', 41), ('v0', 'vendored', 31), ('v1', 'vendored', 21), ('u0', 'unknown', 11)]
    nodes = [node(ident, category, value) for ident, category, value in assigned]
    payload = bottleneck_fixture(tmp_path, nodes, candidate_count=3)
    nodes[5]['span']['file_path'] = 'generated/foo_test.py'
    nodes[7]['span']['file_path'] = 'vendor/tests/test_x.py'
    page = open_report(architecture(nodes), payload)
    for category in ('all', *CATEGORIES):
        page.locator('#category-filter').select_option(category)
        members = [(ident, value) for ident, c, value in assigned if category == 'all' or c == category]
        expected = [ident for ident, value in members[:10]]
        for metric in CORE:
            group = page.locator(f'[data-metric-group="{metric}"]')
            assert group.locator('[data-node-id]').evaluate_all('(els)=>els.map(e=>e.dataset.nodeId)') == expected
            for ident, value in members[:10]:
                expect(group.locator(f'[data-node-id="{ident}"]')).to_contain_text(str(value))


def test_VR1_VR6_explicit_empty_list_states(open_report, tmp_path):
    page = open_report(architecture([]), bottleneck_fixture(tmp_path, [], candidate_count=0))
    assert rows(page) == []
    expect(page.locator('#list-count')).to_contain_text('0')
    assert re.search('없|일치.*않', page.locator('#node-list').inner_text())
    page = open_report(architecture([node('a')]), bottleneck_fixture(tmp_path, [node('a')], candidate_count=0))
    page.locator('#node-search').fill('no-such-oracle')
    assert rows(page) == []
    expect(page.locator('#list-count')).to_contain_text('0')
    assert re.search('없|일치.*않', page.locator('#node-list').inner_text())


@pytest.mark.parametrize('width', [390, 1440], ids=['mobile', 'desktop'])
def test_VR5_actual_tab_keyboard_filters_pages_and_modal(open_report, tmp_path, width):
    nodes = [node('center', value=100)] + [node(f'n{i:02}', value=1) for i in range(51)] + [node('test-only', 'test', value=200)]
    edges = [edge('center', f'n{i:02}', line=i + 1) for i in range(51)]
    nodes[1]['metadata']['analysis']['token_cost'] = 999
    page = open_report(architecture(nodes, edges), bottleneck_fixture(tmp_path, nodes, edges), width=width)
    keyboard_choose(page, '#category-filter select', 'test'); assert rows(page) == ['test-only']
    keyboard_choose(page, '#category-filter select', 'production'); assert rows(page)[0] == 'center'
    keyboard_choose(page, '#metric-sort select', 'token_cost'); assert rows(page)[0] == 'n00'
    keyboard_choose(page, '#metric-sort select', 'pagerank'); assert rows(page)[0] == 'center'
    keyboard_choose(page, '#candidate-kind-filter select', 'large_node'); assert rows(page) == ['center']
    keyboard_choose(page, '#candidate-kind-filter select', 'all')
    tab_to(page, '#node-search'); page.keyboard.type('n50'); assert rows(page) == ['n50']
    page.keyboard.press('Backspace'); page.keyboard.press('Backspace'); page.keyboard.press('Backspace'); assert len(rows(page)) == 50
    tab_to(page, '#page-next'); page.keyboard.press('Enter'); assert rows(page) == ['n49', 'n50']
    tab_to(page, '#page-prev'); page.keyboard.press('Enter'); assert rows(page)[0] == 'center'
    row = tab_to(page, '#node-list [data-node-id="center"]'); page.keyboard.press('Enter')
    expect(page.get_by_role('dialog')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.get_by_role('dialog')).to_be_hidden()
    assert row.evaluate('(e)=>e===document.activeElement')
    assert set(page.external_requests) <= {CDN_URL}
