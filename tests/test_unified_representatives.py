import pytest
from playwright.sync_api import expect

from tests.unified_support import CORE, architecture, node


@pytest.mark.parametrize('width', [390, 1440])
def test_top10_four_visible_rows_and_scroll_opens_modal(open_report, width):
    nodes = [node(f'n{i:02}', value=20-i) for i in range(11)]
    nodes[0]['span']['file_path'] = 'src/' + 'long-directory/' * 10 + 'example.py'
    page = open_report(architecture(nodes), width=width)
    for metric in CORE:
        group = page.locator(f'[data-metric-group="{metric}"]')
        assert group.locator('[data-node-id]').evaluate_all('(elements)=>elements.map(e=>e.dataset.nodeId)') == [f'n{i:02}' for i in range(10)]
        listing = group.locator('.representative-list')
        sizes = listing.evaluate('(e)=>({viewport:e.clientHeight,total:e.scrollHeight,row:e.firstElementChild.getBoundingClientRect().height})')
        assert sizes['viewport'] == pytest.approx(sizes['row'] * 4, abs=1)
        assert sizes['total'] > sizes['viewport']
        assert listing.locator('[data-node-id="n00"]').get_attribute('title').endswith(nodes[0]['span']['file_path'])
    listing = page.locator('[data-metric-group="pagerank"] .representative-list')
    listing.hover()
    page.mouse.wheel(0, 1000)
    page.wait_for_function('() => {const e=document.querySelector("[data-metric-group=pagerank] .representative-list");return e.scrollTop >= e.scrollHeight-e.clientHeight-1}')
    scroll = page.evaluate('window.scrollY')
    listing.locator('[data-node-id="n09"]').click()
    expect(page.get_by_role('dialog')).to_be_visible()
    assert page.evaluate('window.scrollY') == scroll
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
