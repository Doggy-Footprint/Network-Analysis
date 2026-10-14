"""V05: glossary tooltips (F01, C11, Q04). Terms come from A05; the tooltip text oracle is window.ReportGlossary, whose
completeness is checked against the independently listed term set (the wording itself is a review item: glossary.json)."""
import json
import re

import pytest
from playwright.sync_api import Error as PlaywrightError, expect

from tests.report_redesign_support import (
    CORE_LABELS, EVIDENCE_DIR, FIXED_TERMS, STATE_TERMS, build_report, candidate, control, dialog, file_id, goto_graph, goto_list,
    make_file, open_from_list,
)
from tests.unified_support import architecture, node, tab_to
from tests.report_redesign_support import coverage_payload

PATHS = ['app/ui/Home.py', 'app/ui/Repo.py', 'app/data/Dao.py']


def tooltip_report():
    files = [make_file(p, {'pagerank': i + 1}) for i, p in enumerate(PATHS)]
    relations = [(PATHS[0], PATHS[2], 'CALLS', 'static_certain', 'exact', 10), (PATHS[1], PATHS[2], 'IMPORTS', 'static_inferred', 'exact', 11)]
    candidates = [candidate(0, 'large_node', PATHS[1]), candidate(1, 'evidence_spread', PATHS[2]), candidate(2, 'unresolved_boundary', PATHS[0])]
    return build_report(files, relations, candidates=candidates, coverage=coverage_payload(['complete'] * 5 + ['partial'] * 3 + ['failed'] * 2 + ['skipped', 'not_targeted', 'excluded']))


def glossary_terms(page):
    sort_labels = [t.split(' · ')[0].strip() for t in control(page, 'sort').locator('option').all_text_contents()]
    class_labels = [t.strip() for t in control(page, 'category').locator('option').all_text_contents()]
    kind_labels = [o.text_content().strip().removesuffix(' 후보') for o in control(page, 'candidate_kind').locator('option:not([value="all"])').all()]
    assert len(class_labels) == 6 and len(kind_labels) == 3
    return {'metrics': sort_labels, 'classes': class_labels, 'kinds': kind_labels}


def all_glossary_terms(open_report, page):
    """A05 term set: file and symbol reports list the same 10 sort metrics (8 ranking keys plus the two token costs)."""
    groups = glossary_terms(page)
    symbol_page = open_report(architecture([node('a')]))
    symbol_groups = glossary_terms(symbol_page)
    metrics = set(groups['metrics']) | set(symbol_groups['metrics'])
    assert len(metrics) == 10
    return set(CORE_LABELS) | metrics | set(groups['classes']) | set(groups['kinds']) | set(STATE_TERMS) | set(FIXED_TERMS), groups


def test_V05_glossary_completeness_and_review_artifact(open_report):
    arch, bn = tooltip_report()
    page = open_report(arch, bn)
    expected, groups = all_glossary_terms(open_report, page)
    glossary = page.evaluate('window.ReportGlossary')
    assert isinstance(glossary, dict)
    assert expected - set(glossary) == set()
    for term in expected:
        definition = glossary[term]
        assert isinstance(definition, str) and len(definition.strip()) > len(term) + 3 and definition.strip() != term
    for term in ('할인', '가중', '배분 몫', '가중 기여도', 'hop'):
        assert len({glossary[term]} | {glossary[other] for other in ('할인', '가중', '배분 몫', '가중 기여도', 'hop') if other != term}) == 5
    EVIDENCE_DIR.mkdir(exist_ok=True)
    (EVIDENCE_DIR / 'glossary.json').write_text(json.dumps({'spec_version': 1, 'terms': {t: glossary[t] for t in sorted(expected)}}, ensure_ascii=False, indent=2) + '\n')


COLLECT_JS = """(allTerms) => {
  const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && el.checkVisibility({contentVisibilityAuto: true, visibilityProperty: true, opacityProperty: false}); };
  const region = (el) => el.closest('[role=dialog]') ? 'modal' : el.closest('[data-metric-group]') ? 'card' : el.closest('details') ? 'appendix' : el.closest('#node-list, table') ? 'list' : 'page';
  const modal = document.querySelector('[role=dialog]');
  const scope = modal && modal.getBoundingClientRect().height > 0 ? modal : document;
  const marked = [...scope.querySelectorAll('[data-term]')].filter(visible).map((el, i) => { el.setAttribute('data-probe', String(i)); return {probe: i, term: el.dataset.term, region: region(el), focusable: el.tabIndex >= 0}; });
  const unwrapped = [...document.querySelectorAll('body *')].filter(el => el.children.length === 0 && visible(el) && !el.closest('option, select, datalist, script, style, [role=tooltip], [data-term]')
      && allTerms.includes(el.textContent.trim())).map(el => ({text: el.textContent.trim(), region: region(el)}));
  return {marked, unwrapped};
}"""


def collect(page, all_terms):
    page.evaluate("document.querySelectorAll('[data-probe]').forEach(e => e.removeAttribute('data-probe'))")
    return page.evaluate(COLLECT_JS, sorted(all_terms))


def norm(text):
    return re.sub(r'\s+', ' ', text).strip()


def exercise(page, element, term, glossary):
    """hover/leave and focus/blur/Escape for one element; returns a list of failure strings."""
    failures = []
    tip = page.get_by_role('tooltip')
    try:
        element.scroll_into_view_if_needed(timeout=2000)
        element.hover(timeout=2000)
        expect(tip).to_have_count(1)
        if norm(tip.first.inner_text()) != norm(glossary[term]):
            failures.append(f'{term}: hover text {tip.first.inner_text()!r}')
        tip_id = tip.first.get_attribute('id')
        if not tip_id or tip_id not in (element.get_attribute('aria-describedby') or '').split():
            failures.append(f'{term}: aria-describedby does not reference the tooltip')
        page.mouse.move(1, 1)
        expect(tip).to_have_count(0)
        element.focus(timeout=2000)
        expect(tip).to_have_count(1)
        if norm(tip.first.inner_text()) != norm(glossary[term]):
            failures.append(f'{term}: focus text {tip.first.inner_text()!r}')
        if tip.first.get_attribute('id') not in (element.get_attribute('aria-describedby') or '').split():
            failures.append(f'{term}: focus aria-describedby')
        element.evaluate('(el) => el.blur()')
        expect(tip).to_have_count(0)
        element.focus(timeout=2000)
        expect(tip).to_have_count(1)
        page.keyboard.press('Escape')
        expect(tip).to_have_count(0)
    except (AssertionError, PlaywrightError) as error:
        failures.append(f'{term}: {str(error)[:200]}')
    return failures


def test_V05_every_term_location_class_hover_and_focus_tooltip(open_report):
    arch, bn = tooltip_report()
    page = open_report(arch, bn)
    all_terms, groups = all_glossary_terms(open_report, page)
    glossary = page.evaluate('window.ReportGlossary')
    seen, failures, unwrapped, matrix, escape_closes_modal = {}, [], [], [], []

    def visit(state):
        found = collect(page, all_terms)
        unwrapped.extend((state, u['region'], u['text']) for u in found['unwrapped'])
        for item in found['marked']:
            key = (item['term'], state, item['region'])
            if key in seen:
                continue
            seen[key] = item
            if item['term'] not in glossary:
                failures.append(f'{item["term"]}: data-term has no glossary entry')
                continue
            if not item['focusable']:
                failures.append(f'{item["term"]}: not keyboard focusable')
            element = dialog(page).locator(f'[data-term="{item["term"]}"]').first if item['region'] == 'modal' else page.locator(f'[data-probe="{item["probe"]}"]').first
            failures.extend(f'[{state}/{item["region"]}] {msg}' for msg in exercise(page, element, item['term'], glossary))
            if item['region'] == 'modal':
                if dialog(page).is_visible():
                    failures.append(f'{item["term"]}: one Escape must close tooltip and modal together (A14)')
                else:
                    escape_closes_modal.append(item['term'])
                    open_from_list(page, file_id(PATHS[1])).click()
                    expect(dialog(page)).to_be_visible()
            matrix.append(list(key))

    goto_list(page)
    visit('list-tab')
    goto_graph(page)
    visit('graph-tab')
    page.locator('details', has_text='읽는 방법').first.locator('summary').first.click()
    visit('appendix-open')
    goto_list(page)
    open_from_list(page, file_id(PATHS[1])).click()
    expect(dialog(page)).to_be_visible()
    visit('modal-open')
    EVIDENCE_DIR.mkdir(exist_ok=True)
    (EVIDENCE_DIR / 'tooltip-matrix.json').write_text(json.dumps({'spec_version': 1, 'term_state_region': sorted(matrix), 'escape_with_tooltip_also_closed_modal_for': sorted(set(escape_closes_modal))}, ensure_ascii=False, indent=1) + '\n')
    assert not failures, '\n'.join(failures)
    assert unwrapped == [], 'glossary terms shown as plain text without data-term'
    terms_in = lambda region: {t for (t, s, r) in seen if r == region}
    assert set(CORE_LABELS) <= terms_in('card'), 'representative cards must carry the six core labels'
    assert set(CORE_LABELS) <= terms_in('modal'), 'modal must carry the six core metric labels'
    assert set(groups['kinds']) <= {t for (t, s, r) in seen if r != 'modal'}, 'candidate kinds must appear in KPI/cards/list'
    all_seen = {t for (t, s, r) in seen}
    assert {'layer', '할인', '가중'} <= all_seen



def test_V05_keyboard_tab_reaches_term_and_escape_hides(open_report):
    arch, bn = tooltip_report()
    page = open_report(arch, bn)
    glossary = page.evaluate('window.ReportGlossary')
    first = tab_to(page, '[data-term]:visible')
    term = first.get_attribute('data-term')
    tip = page.get_by_role('tooltip')
    expect(tip).to_have_count(1)
    assert norm(tip.first.inner_text()) == norm(glossary[term])
    assert tip.first.get_attribute('id') in first.get_attribute('aria-describedby').split()
    page.keyboard.press('Escape')
    expect(tip).to_have_count(0)
    page.keyboard.press('Tab')
    page.keyboard.press('Shift+Tab')
    expect(tip).to_have_count(1)
