"""V07: network boundary (F14, F15, C12, Q05, Q07)."""
import re

import pytest
from playwright.sync_api import expect

from tests.report_redesign_support import SEL, build_report, candidate, file_id, goto_list, make_file, open_from_list, render, row_ids, tab, tab_active, dialog
from tests.unified_support import CDN_URL, architecture, edge, node

PATHS = ['app/ui/Home.py', 'app/ui/Repo.py', 'app/data/Dao.py']
NO_ARCH_TEXT = '아키텍처 데이터가 없어 그래프를 그릴 수 없습니다.'
SYMBOL_TEXT = '파일 단위 보고서에서만 그래프를 제공합니다.'
FAILURE_TEXT = '그래프 라이브러리를 불러오지 못했습니다. 목록을 사용하세요.'


def network_report():
    files = [make_file(p, {'pagerank': i + 1}) for i, p in enumerate(PATHS)]
    relations = [(PATHS[0], PATHS[2], 'CALLS', 'static_certain', 'exact', 10), (PATHS[1], PATHS[2], 'CALLS', 'static_certain', 'exact', 11)]
    return build_report(files, relations, candidates=[candidate(0, 'large_node', PATHS[1])])


def script_sources(html):
    return re.findall(r'<script\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', html, re.I)


def test_V07_html_references_only_the_pinned_cdn_script_and_no_cytoscape():
    arch, bn = network_report()
    html = render(arch, bn)
    assert script_sources(html) == [CDN_URL]
    assert 'cytoscape' not in html.lower()
    assert not re.search(r'<link\b[^>]*\bhref\s*=\s*["\']https?:', html, re.I)
    for variant in (render(None, bn), render(arch, None), render(architecture([node('a')], [edge('a', 'a')]))):
        assert set(script_sources(variant)) <= {CDN_URL} and len(script_sources(variant)) <= 1
        assert 'cytoscape' not in variant.lower()


def test_V07_local_route_success_graph_enabled_single_external_request(open_report):
    arch, bn = network_report()
    page = open_report(arch, bn)
    assert not tab(page, '그래프').is_disabled() and tab_active(page, '그래프')
    assert page.evaluate('window.ReportGraph != null')
    assert page.external_requests == [CDN_URL]
    assert page.unhandled_errors == []
    expect(page.get_by_text(FAILURE_TEXT)).to_have_count(0)


@pytest.mark.parametrize('failure', ['abort', 'http-500'])
def test_V07_cdn_failure_degrades_to_list_with_modal_kpi_and_cards(open_report, failure):
    arch, bn = network_report()
    page = open_report(arch, bn, cdn=failure)
    expect(page.get_by_text(FAILURE_TEXT)).to_be_visible()
    assert tab(page, '그래프').is_disabled()
    assert tab_active(page, '목록')
    assert page.evaluate('window.ReportGraph == null')
    assert row_ids(page) == [file_id(p) for p in reversed(PATHS)]
    assert page.locator(SEL['card_group']).count() == 6
    expect(page.get_by_text('파일', exact=True).first).to_be_visible()
    open_from_list(page, file_id(PATHS[1])).click()
    expect(dialog(page)).to_be_visible()
    assert PATHS[1] in dialog(page).inner_text()
    page.keyboard.press('Escape')
    expect(dialog(page)).to_be_hidden()
    assert page.unhandled_errors == []
    assert page.external_requests == [CDN_URL]


def test_V07_symbol_report_requests_nothing_else(open_report):
    page = open_report(architecture([node('a'), node('b')], [edge('a', 'b')]))
    assert set(page.external_requests) <= {CDN_URL}
    assert tab(page, '그래프').is_disabled() and tab_active(page, '목록')
    assert page.unhandled_errors == []


@pytest.mark.parametrize('cdn', ['local', 'abort'])
@pytest.mark.parametrize('case', ['no-architecture', 'symbol'])
def test_V07_disabled_graph_reason_priority(open_report, cdn, case):
    """A13: no architecture > symbol granularity > library failure; the library failure text must not win over the first two."""
    if case == 'symbol':
        page = open_report(architecture([node('a'), node('b')], [edge('a', 'b')]), cdn=cdn)
        shown, hidden = SYMBOL_TEXT, (NO_ARCH_TEXT, FAILURE_TEXT)
    else:
        _, bn = network_report()
        page = open_report(None, bn, cdn=cdn)
        shown, hidden = NO_ARCH_TEXT, (SYMBOL_TEXT, FAILURE_TEXT)
    expect(page.get_by_text(shown)).to_be_visible()
    for text in hidden:
        expect(page.get_by_text(text)).to_have_count(0)
    assert tab(page, '그래프').is_disabled() and tab_active(page, '목록')
    assert page.unhandled_errors == []
