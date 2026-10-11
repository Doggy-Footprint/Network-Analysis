"""V06: page structure and KPI values (F12, F13, F15, C13, C14)."""
import re

import pytest
from playwright.sync_api import expect

from tests.report_redesign_support import SEL, build_report, candidate, coverage_payload, file_id, goto_list, make_file, pill_numbers, row_ids, tab, tab_active
from tests.unified_support import architecture, edge, node

AREAS = {'ui': ['A1', 'A2', 'A3'], 'data': ['B1', 'B2', 'B3'], 'core': ['C1', 'C2', 'C3']}
PATHS = [f'app/{area}/{name}.py' for area, names in AREAS.items() for name in names]
COVERAGE = ['complete'] * 5 + ['partial'] * 3 + ['failed'] * 2 + ['skipped']


def structure_report(coverage=True):
    files = [make_file(p, {'pagerank': i + 1}) for i, p in enumerate(PATHS)]
    relations = [(PATHS[0], PATHS[3], 'CALLS', 'static_certain', 'exact', 10), (PATHS[1], PATHS[4], 'CALLS', 'static_certain', 'exact', 11),
                 (PATHS[2], PATHS[5], 'IMPORTS', 'static_certain', 'exact', 12), (PATHS[6], PATHS[0], 'CALLS', 'static_certain', 'exact', 13)]
    candidates = [candidate(0, 'large_node', PATHS[0]), candidate(1, 'evidence_spread', PATHS[3]), candidate(2, 'evidence_spread', PATHS[4]),
                  candidate(3, 'unresolved_boundary', PATHS[6]), candidate(4, 'unresolved_boundary', PATHS[7]), candidate(5, 'unresolved_boundary', PATHS[8])]
    return build_report(files, relations, candidates=candidates, coverage=coverage_payload(COVERAGE) if coverage else None)


def precedes(page, first, second):
    return page.evaluate('([a, b]) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)', [first.element_handle(), second.element_handle()])


def assert_structure(page):
    assert page.locator('#coverage-details').count() == 0 and page.locator('#node-detail').count() == 0
    kpi = page.get_by_text(re.compile('분석 범위')).first
    one = page.get_by_text(re.compile(r'^\s*01\b')).first
    two = page.get_by_text(re.compile(r'^\s*02\b')).first
    appendix = page.locator('details', has_text='읽는 방법').first
    expect(one).to_be_visible()
    expect(two).to_be_visible()
    assert precedes(page, kpi, one) and precedes(page, one, two) and precedes(page, two, appendix)
    assert page.get_by_text(re.compile(r'^\s*03\b')).count() == 0
    assert page.locator(SEL['card_group']).count() == 6
    narrative = page.evaluate("""() => [...document.querySelectorAll('body *')]
        .filter(el => !el.closest('details, [role=dialog], [role=tooltip], [role=status], output, table, #graph-container, script, style, datalist, select, noscript, #modal-backdrop'))
        .map(el => [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').replace(/\\s+/g, ' ').trim())
        .filter(text => text.length > 40)""")
    assert narrative == [], 'explanatory text blocks must be gone (F12)'
    sections = page.evaluate("""() => [...document.querySelector('main').children].map(el => ({tag: el.tagName, id: el.id, text: el.innerText.trim().slice(0, 40), details: !!el.querySelector('details#report-appendix') || el.id === 'report-appendix'}))""")
    assert len(sections) == 4, sections
    assert '분석 범위' in page.locator('main').evaluate("m => m.children[0].innerText") and page.locator('main > :nth-child(1) #kpi').count() == 1
    assert sections[1]['text'].startswith('01') and sections[2]['text'].startswith('02') and sections[3]['details']
    assert page.unhandled_errors == []


def kind_counts(page):
    """candidate count per kind as the KPI shows it, keyed by the kind's filter value."""
    result = {}
    for kind in ('large_node', 'evidence_spread', 'unresolved_boundary'):
        name = page.locator(f'#candidate-kind-filter option[value="{kind}"]').text_content().strip().removesuffix(' 후보')
        block = page.locator('#kpi').get_by_text(name, exact=True).first.locator('xpath=..')
        result[kind] = int(re.findall(r'\d+', block.inner_text())[0])
    return result


def graph_disabled(page):
    assert tab(page, '그래프').is_disabled()
    assert tab_active(page, '목록')
    assert page.evaluate('window.ReportGraph == null')
    assert page.locator('canvas').count() == 0


def test_V06_combined_report_sections_order_and_kpi_values(open_report):
    arch, bn = structure_report()
    assert len(arch['nodes']) == 9 and len(arch['edges']) == 4
    page = open_report(arch, bn)
    assert_structure(page)
    assert tab_active(page, '그래프')
    assert pill_numbers(page, '파일') == [9]
    assert pill_numbers(page, '연결') == [4]
    assert {1, 2, 3} <= set(pill_numbers(page, '후보'))
    kinds = kind_counts(page)
    assert kinds == {'large_node': 1, 'evidence_spread': 2, 'unresolved_boundary': 3}
    assert pill_numbers(page, '분석 범위') == [5, 3, 2]


def test_V06_architecture_only_candidate_kpi_dash_and_list_works(open_report):
    arch, _ = structure_report()
    page = open_report(arch, None)
    assert_structure(page)
    assert pill_numbers(page, '파일') == [9] and pill_numbers(page, '연결') == [4]
    assert '—' in page.get_by_text('후보', exact=True).first.locator('xpath=..').inner_text()
    goto_list(page)
    assert len(row_ids(page)) == 9


def test_V06_bottlenecks_only_graph_disabled_with_working_list(open_report):
    _, bn = structure_report()
    page = open_report(None, bn)
    assert_structure(page)
    graph_disabled(page)
    expect(page.get_by_text('아키텍처 데이터가 없어 그래프를 그릴 수 없습니다.')).to_be_visible()
    assert len(row_ids(page)) == 9
    assert pill_numbers(page, '분석 범위') == [5, 3, 2]


def test_V06_symbol_granularity_graph_disabled_list_only(open_report):
    page = open_report(architecture([node('a'), node('b', value=2)], [edge('a', 'b')]))
    assert_structure(page)
    graph_disabled(page)
    expect(page.get_by_text('파일 단위 보고서에서만 그래프를 제공합니다.')).to_be_visible()
    assert sorted(row_ids(page)) == ['a', 'b']


def test_V06_without_coverage_reports_unavailable_pill(open_report):
    arch, bn = structure_report(coverage=False)
    page = open_report(arch, bn)
    assert_structure(page)
    expect(page.get_by_text('분석 범위 정보 없음')).to_be_visible()
    assert tab_active(page, '그래프')


@pytest.mark.parametrize('case', ['snapshot-and-edge-count', 'snapshot-absent', 'edge-count-absent'])
def test_V06_bottlenecks_only_kpi_values_follow_A17(open_report, case):
    _, bn = structure_report()
    expected = {'파일': 87, '연결': 4}
    if case == 'snapshot-and-edge-count':
        bn['snapshot']['file_count'] = 87
    elif case == 'snapshot-absent':
        expected['파일'] = None
    else:
        bn['snapshot']['file_count'] = 87
        bn['dependency_network'].pop('edge_count')
        expected['연결'] = None
    page = open_report(None, bn)
    for label, value in expected.items():
        text = page.get_by_text(label, exact=True).first.locator('xpath=..').inner_text()
        assert ('—' in text) if value is None else (pill_numbers(page, label) == [value] and '—' not in text), (label, text)
    assert kind_counts(page) == {'large_node': 1, 'evidence_spread': 2, 'unresolved_boundary': 3}
    assert pill_numbers(page, '분석 범위') == [5, 3, 2]


def test_V06_symbol_report_kpis_without_bottlenecks(open_report):
    page = open_report(architecture([node('a'), node('b', value=2)], [edge('a', 'b')]))
    assert pill_numbers(page, '연결') == [1]
    candidate_pill = page.get_by_text('후보', exact=True).first.locator('xpath=..').inner_text()
    assert '—' in candidate_pill and not re.search(r'\d', candidate_pill)
    expect(page.get_by_text('분석 범위 정보 없음')).to_be_visible()
