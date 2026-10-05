import pytest
from playwright.sync_api import expect

from tests.unified_support import architecture, node, rows


@pytest.mark.parametrize('count', [99, 100, 101])
def test_default_top100_boundary_and_full_list(open_report, count):
    nodes = [node(f'n{i:03}', value=200-i) for i in range(count)]
    page = open_report(architecture(nodes))
    assert page.locator('#list-limit select').input_value() == '100'
    assert rows(page) == [f'n{i:03}' for i in range(50)]
    page.locator('#page-next').click()
    assert rows(page) == [f'n{i:03}' for i in range(50, min(count, 100))]
    assert page.locator('#page-next').is_disabled()
    expect(page.locator('#list-count')).to_contain_text(f'{min(count, 100)}개 표시 / 조건 일치 {count}개')
    page.locator('#list-limit select').select_option('all')
    assert rows(page)[0] == 'n000'
    if count == 101:
        page.locator('#page-next').click()
        page.locator('#page-next').click()
        assert rows(page) == ['n100']
        page.locator('#list-limit select').select_option('100')
        assert rows(page)[0] == 'n000'
        expect(page.locator('#page-label')).to_have_text('1 / 2 페이지')


def test_filter_and_current_metric_precede_top100(open_report):
    nodes = [node(f'n{i:03}', value=200-i) for i in range(101)]
    nodes[-1]['metadata']['analysis']['fan_in'] = 999
    page = open_report(architecture(nodes))
    page.locator('#node-search').fill('n100')
    assert rows(page) == ['n100']
    page.locator('#node-search').fill('')
    page.locator('#metric-sort select').select_option('fan_in')
    assert rows(page)[0] == 'n100'
    assert page.locator('#list-limit select').input_value() == '100'
