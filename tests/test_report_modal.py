"""V04: modal state transitions (F09, F10, F11, C08, C09, C10, Q04). Expected content is derived from the fixture, not from rendered output."""
import re

import pytest
from playwright.sync_api import expect

from tests.report_redesign_support import (
    tab_active,
    CORE_KEYS, CORE_LABELS, SEL, WEIGHT_TABLE, build_report, candidate, click_graph_node, close_button, control,
    dialog, dialog_text, file_id, goto_graph, goto_list, has_number, install_pointer_trace, make_file, numbers, open_from_list,
    prepare_canvas, settle_view,
)
from tests.unified_support import tab_to

HUB = 'src/core/RepoCache.py'
PLAIN = 'src/core/Plain.py'
SPREAD = 'src/core/Spread.py'
SUFFIX = [f'A{chr(97 + i)}' for i in range(15)]
INBOUND = [f'src/in/In{s}.py' for s in SUFFIX]
OUT_SUFFIX = [f'B{chr(97 + i)}' for i in range(12)]
OUTBOUND = [f'src/out/Out{s}.py' for s in OUT_SUFFIX]
# (confidence, resolution) tiers; effective weight = min of the two table values (WEIGHT_TABLE).
# Tiers 0-8 are clear winners (1.0 / 0.8), tier 9 is 0.6 by min but 0.36 as a product, tier 10 is 0.5 (product 0.5),
# tiers 11-14 are below. The top-10 cut therefore falls between tier 9 and tier 10.
TIERS = [('static_certain', 'exact'), ('static_inferred', 'exact')] * 4 + [('static_certain', 'exact')] + [
    ('framework_inferred', 'unique_name'), ('static_certain', 'ambiguous'),
    ('dynamic_required', 'exact'), ('static_certain', 'unresolved'), ('dynamic_required', 'unique_name'), ('static_inferred', 'unresolved')]
IN_TIER = [3, 14, 0, 7, 12, 5, 9, 1, 11, 6, 13, 2, 8, 4, 10]
# 12 outgoing neighbours (3 fewer than incoming): tiers 0-9 are inside the cut, 10 and 12 outside
OUT_TIER = [10, 2, 6, 0, 9, 4, 12, 1, 5, 3, 8, 7]
CORE_VALUES = dict(zip(CORE_KEYS, range(101, 107)))
LINES, TOKENS = 311, 457


def top_ten(paths, tiers):
    shown = {p for p, t in zip(paths, tiers) if t <= 9}
    return shown, set(paths) - shown


def modal_report():
    files = [make_file(HUB, {**CORE_VALUES, 'token_cost': TOKENS}, cost={'line_count': LINES, 'token_estimate': TOKENS}), make_file(PLAIN), make_file(SPREAD)]
    files += [make_file(p) for p in INBOUND + OUTBOUND]
    relations = []
    for i, path in enumerate(INBOUND):
        relations.append((path, HUB, 'CALLS', *TIERS[IN_TIER[i]], 100 + i))
    for i, path in enumerate(OUTBOUND):
        relations.append((HUB, path, 'CALLS', *TIERS[OUT_TIER[i]], 200 + i))
    candidates = [candidate(0, 'large_node', HUB, {'line_count': 2417, 'line_threshold': 2000}), candidate(1, 'unresolved_boundary', HUB, {'unresolved_count': 7}),
                  candidate(2, 'evidence_spread', SPREAD, {'file_count': 6, 'line_span': 1234, 'line_threshold': 2000})]
    return build_report(files, relations, weights=WEIGHT_TABLE, candidates=candidates)


def kind_label(page, kind):
    """Kind name as the product labels it; the filter option reads '<name> 후보'."""
    text = control(page, 'candidate_kind').locator(f'option[value="{kind}"]').text_content().strip()
    return re.sub(r'\s*후보$', '', text)


def open_modal(page, route, node=HUB):
    """Opens the modal through one of the four routes; returns window.scrollY right before the click."""
    ident = file_id(node)
    if route == 'graph':
        prepare_canvas(page)
        scroll = page.evaluate('window.scrollY')
        page.evaluate('window.__before = null')
        click_graph_node(page, ident)
    elif route == 'list':
        target = open_from_list(page, ident)
        scroll = page.evaluate('window.scrollY')
        page.evaluate('window.__before = null')
        target.click()
    elif route == 'card':
        target = page.locator(f'{SEL["card_group"]}[data-metric-group="pagerank"] [data-node-id="{ident}"]').first
        target.scroll_into_view_if_needed()
        scroll = page.evaluate('window.scrollY')
        page.evaluate('window.__before = null')
        target.click()
    else:
        open_modal(page, 'list', INBOUND[0])
        scroll = click_connection(page, node)
    expect(dialog(page)).to_be_visible()
    return scroll


def click_connection(page, node=HUB):
    expect(dialog(page)).to_be_visible()
    stem = node.rsplit('/', 1)[1][:-3]
    link = dialog(page).locator(f'[data-node-id="{file_id(node)}"]').or_(dialog(page).get_by_text(stem)).first
    scroll = page.evaluate('window.scrollY')
    link.click()
    return scroll


def test_V04_modal_contents_hub_node(open_report):
    arch, bn = modal_report()
    page = open_report(arch, bn)
    open_modal(page, 'list')
    box = dialog(page)
    assert box.get_attribute('aria-modal') == 'true'
    text = dialog_text(page)
    assert HUB in text
    assert any('RepoCache' in h for h in box.get_by_role('heading').all_inner_texts())
    assert any(l.strip() == 'core' or l.startswith('core') for l in text.splitlines()), 'layer badge'
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    ties = list(zip(CORE_LABELS, CORE_VALUES.values())) + [('줄 수', LINES), ('토큰 수', TOKENS)]
    for label, value in ties:
        assert lines.index(label) >= 0 and has_number(lines[lines.index(label) + 1], value) and lines[lines.index(label) + 1].replace(',', '') == str(value), label
    heading = box.get_by_role('heading', level=2).inner_text().strip()
    assert heading != HUB and heading in HUB and HUB in lines, 'short label and full path are separate'
    assert lines.index(HUB) > lines.index(heading) and any(l.startswith('core') and '/' not in l for l in lines)
    large = [l for l in lines if kind_label(page, 'large_node') in l and has_number(l, 2417)]
    unresolved = [l for l in lines if kind_label(page, 'unresolved_boundary') in l and has_number(l, 7)]
    assert large and unresolved and large[0] != unresolved[0]
    assert kind_label(page, 'evidence_spread') not in text and '후보 없음' not in text
    incoming_at = next(i for i, l in enumerate(lines) if l.startswith('들어오는 연결 ·'))
    outgoing_at = next(i for i, l in enumerate(lines) if l.startswith('나가는 연결 ·'))
    assert incoming_at < outgoing_at
    sections = {'in': (lines[incoming_at], lines[incoming_at + 1:outgoing_at]), 'out': (lines[outgoing_at], lines[outgoing_at + 1:])}
    assert has_number(sections['in'][0], 15) and has_number(sections['out'][0], 12)
    for direction, paths, tiers, prefix in (('in', INBOUND, IN_TIER, 'In'), ('out', OUTBOUND, OUT_TIER, 'Out')):
        shown, hidden = top_ten(paths, tiers)
        body = '\n'.join(sections[direction][1])
        for path in shown:
            assert path.rsplit('/', 1)[1][:-3] in body, (direction, path)
        for path in hidden:
            assert path.rsplit('/', 1)[1][:-3] not in body, (direction, path)
        other = 'Out' if prefix == 'In' else 'In'
        assert other not in body, 'neighbours listed under the wrong direction'
    for forbidden in ('candidate-0.py', 'ORACLE_COVERAGE', 'evidence-1', 'evidence-2'):
        assert forbidden not in text, 'detail evidence must not be shown (F10/A06)'


def test_V04_modal_contents_node_without_candidates_or_connections(open_report):
    arch, bn = modal_report()
    page = open_report(arch, bn)
    open_modal(page, 'list', PLAIN)
    text = dialog_text(page)
    assert PLAIN in text and '후보 없음' in text
    assert 'RepoCache' not in text and not any(f'In{s}' in text or f'Out{s}' in text for s in SUFFIX)
    assert has_number(text, 0)


def test_V04_same_modal_from_all_four_open_paths_without_scrolling(open_report):
    arch, bn = modal_report()
    page = open_report(arch, bn)
    texts = {}
    for route in ('graph', 'list', 'card', 'connection'):
        before = open_modal(page, route)
        assert page.evaluate('window.scrollY') == before, route
        texts[route] = dialog_text(page)
        page.keyboard.press('Escape')
        expect(dialog(page)).to_be_hidden()
        goto_graph(page)
    assert len(set(texts.values())) == 1, {k: v[:80] for k, v in texts.items()}
    assert dialog(page).count() == 0


@pytest.mark.parametrize('close', ['button', 'escape', 'backdrop'])
@pytest.mark.parametrize('route', ['graph', 'list', 'card', 'connection'])
def test_V04_open_close_transitions_focus_and_scroll(open_report, route, close):
    arch, bn = modal_report()
    page = open_report(arch, bn)
    install_pointer_trace(page)
    before = open_modal(page, route)
    box = dialog(page)
    assert box.get_attribute('aria-modal') == 'true' and page.evaluate('window.scrollY') == before
    assert close_button(page).evaluate('(el) => el === document.activeElement'), 'focus must start on the close button'
    opener = page.evaluate('window.__before !== undefined && window.__before !== null')
    assert dialog(page).count() == 1
    previous = page.evaluate_handle('window.__before')
    if close == 'button':
        close_button(page).click()
    elif close == 'escape':
        page.keyboard.press('Escape')
    else:
        page.mouse.click(3, 3)
    expect(dialog(page)).to_be_hidden()
    assert page.evaluate('window.scrollY') == before
    inside = page.evaluate("!!document.activeElement && !!document.activeElement.closest('[role=dialog]')")
    assert not inside
    assert opener
    assert page.evaluate('(prev) => document.activeElement === prev', previous), 'focus must return to the element that first opened the modal (A14)'


def test_V04_focus_trap_tab_cycle(open_report):
    arch, bn = modal_report()
    page = open_report(arch, bn)
    open_modal(page, 'list')
    focusable = dialog(page).locator('button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])').count()
    assert focusable >= 2
    visited = set()
    for key in ['Tab'] * (focusable * 2 + 3) + ['Shift+Tab'] * (focusable * 2 + 3):
        page.keyboard.press(key)
        assert page.evaluate("!!document.activeElement.closest('[role=dialog]')"), key
        visited.add(page.evaluate("[...document.querySelectorAll('[role=dialog] *')].indexOf(document.activeElement)"))
    assert len(visited) >= 2


def test_V04_keyboard_only_open_escape_and_restore(open_report):
    arch, bn = modal_report()
    page = open_report(arch, bn)
    goto_list(page)
    row = f'{SEL["rows"]}[data-node-row="{file_id(HUB)}"]'
    target = tab_to(page, f'{row} [data-node-id]' if page.locator(f'{row} [data-node-id]').count() else row)
    page.keyboard.press('Enter')
    expect(dialog(page)).to_be_visible()
    assert close_button(page).evaluate('(el) => el === document.activeElement')
    page.keyboard.press('Escape')
    expect(dialog(page)).to_be_hidden()
    assert target.evaluate('(el) => el === document.activeElement')
    assert page.unhandled_errors == []


def test_V04_connection_click_switches_modal_target(open_report):
    arch, bn = modal_report()
    page = open_report(arch, bn)
    open_modal(page, 'list', INBOUND[0])
    assert INBOUND[0] in dialog_text(page)
    assert any('InAa' in h for h in dialog(page).get_by_role('heading').all_inner_texts())
    click_connection(page)
    assert dialog(page).count() == 1
    assert HUB in dialog_text(page)
    assert any('RepoCache' in h for h in dialog(page).get_by_role('heading').all_inner_texts())
    assert not any('InAa' in h for h in dialog(page).get_by_role('heading').all_inner_texts())


def test_V04_candidate_headline_numbers_per_kind(open_report):
    """A12: unresolved_count / file_count / line_count."""
    arch, bn = modal_report()
    page = open_report(arch, bn)
    open_modal(page, 'list', SPREAD)
    lines = [l for l in dialog_text(page).splitlines() if kind_label(page, 'evidence_spread') in l]
    assert lines and has_number(lines[0], 6)
    assert kind_label(page, 'large_node') not in dialog_text(page)


def test_V04_total_counts_distinct_neighbour_files(open_report):
    files = [make_file('src/a/X.py'), make_file('src/a/Y.py')]
    relations = [('src/a/X.py', 'src/a/Y.py', 'CALLS', 'static_certain', 'exact', 5), ('src/a/X.py', 'src/a/Y.py', 'IMPORTS', 'static_certain', 'exact', 6),
                 ('src/a/X.py', 'src/a/Y.py', 'CALLS', 'static_inferred', 'exact', 7)]
    arch, bn = build_report(files, relations)
    page = open_report(arch, bn)
    open_modal(page, 'list', 'src/a/X.py')
    text = dialog_text(page)
    assert re.search(r'나가는 연결\D*총\s*1\D', text) and re.search(r'들어오는 연결\D*총\s*0\D', text)


def assert_graph_focused_on(page, node):
    ident = file_id(node)
    page.wait_for_function('(id) => ReportGraph.getSelectedNodes().length === 1 && ReportGraph.getSelectedNodes()[0] === id', arg=ident)
    page.wait_for_function("(id) => { const p = ReportGraph.getPositions([id])[id], v = ReportGraph.getViewPosition(); return Math.abs(p.x - v.x) < 2 && Math.abs(p.y - v.y) < 2; }", arg=ident, timeout=4000)
    assert page.evaluate('ReportGraph.getSelectedNodes()') == [ident]
    position = page.evaluate('(id) => ReportGraph.getPositions([id])[id]', ident)
    view = page.evaluate('ReportGraph.getViewPosition()')
    assert abs(view['x'] - position['x']) < 2 and abs(view['y'] - position['y']) < 2


@pytest.mark.parametrize('route', ['card', 'connection', 'graph'])
def test_V04_graph_tab_active_modal_selects_and_centres_node(open_report, route):
    """E03/F09: with the graph tab active, every graph-visible open path also selects and focuses the node."""
    arch, bn = modal_report()
    page = open_report(arch, bn)
    away = "ReportGraph.moveTo({position: {x: 4000, y: 4000}, scale: 0.4, animation: false})"
    if route == 'connection':
        page.evaluate(away)
        open_modal(page, 'card', INBOUND[0])
        assert_graph_focused_on(page, INBOUND[0])
        page.evaluate(away)
        click_connection(page, HUB)
    elif route == 'card':
        page.evaluate(away)
        open_modal(page, 'card')
    else:
        open_modal(page, 'graph')
    assert_graph_focused_on(page, HUB)
    assert tab_active(page, '그래프')


def test_V04_keyboard_only_tab_switching(open_report):
    """E05/Q04: reach the tab list with Tab, switch with arrows/Enter/Space, panels follow."""
    arch, bn = modal_report()
    page = open_report(arch, bn)
    active = tab_to(page, '[role=tab][aria-selected="true"]')
    assert 'graph' in (active.get_attribute('id') or '') or active.inner_text().strip() == '그래프'

    def panel_state():
        return page.evaluate("[...document.querySelectorAll('[role=tabpanel]')].map(p => [p.id, !p.hidden && p.getBoundingClientRect().height > 0])")

    assert dict(panel_state())['panel-graph'] and not dict(panel_state())['panel-list']
    page.keyboard.press('ArrowRight')
    if dict(panel_state())['panel-graph']:
        page.keyboard.press('Enter')
    assert tab_active(page, '목록') and dict(panel_state())['panel-list'] and not dict(panel_state())['panel-graph']
    page.keyboard.press('ArrowLeft')
    if not dict(panel_state())['panel-graph']:
        page.keyboard.press('Space')
    page.wait_for_function('document.body.dataset.graphReady === "true"')
    assert tab_active(page, '그래프') and dict(panel_state())['panel-graph'] and not dict(panel_state())['panel-list']
    assert page.unhandled_errors == []
