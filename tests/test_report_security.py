"""V08 (error guessing): hostile repository paths/labels must render as literal text on every new surface (C15, Q06)."""
import pytest
from playwright.sync_api import expect

from tests.report_redesign_support import SEL, build_report, candidate, dialog, file_id, goto_graph, goto_list, make_file, open_from_list, prepare_canvas
from tests.unified_support import CDN_URL

DIR_HOSTILE = '<img src=x onerror="window.attack_layer=1">&"'
NAME_HOSTILE = 'Q"&amp;<b>x</b>.py'
LABEL_HOSTILE = '</script><img src="https://invalid.example/x" onerror="window.attack_label=1"><script>window.attack_label=1</script>'
TITLE_HOSTILE = '</script><img src="https://invalid.example/t" onerror="window.attack_title=1"><script>window.attack_title=1</script>'
EVIL = f'src/{DIR_HOSTILE}/Evil.py'
NAMED = f'src/ui/{NAME_HOSTILE}'
LABELLED = 'src/ui/Repo.py'
HOME = 'src/ui/Home.py'
FLAGS = ('attack_layer', 'attack_label', 'attack_title', 'attack')


def hostile_report():
    files = [make_file(EVIL, {'pagerank': 9}), make_file(NAMED, {'pagerank': 5}), make_file(LABELLED, {'pagerank': 3}, label=LABEL_HOSTILE), make_file(HOME, {'pagerank': 1})]
    relations = [(EVIL, HOME, 'CALLS', 'static_certain', 'exact', 10), (NAMED, LABELLED, 'IMPORTS', 'static_certain', 'exact', 11), (HOME, EVIL, 'CALLS', 'static_inferred', 'exact', 12)]
    return build_report(files, relations, candidates=[candidate(0, 'large_node', EVIL)])


def assert_inert(page):
    for flag in FLAGS:
        assert page.evaluate(f'window.{flag}') is None, flag
    assert page.locator('img, :not(script)[onerror], iframe, object, embed').count() == 0
    assert set(page.external_requests) <= {CDN_URL}
    assert page.unhandled_errors == []


def test_V08_list_legend_and_graph_surfaces_are_literal(open_report):
    arch, bn = hostile_report()
    page = open_report(arch, bn, title=TITLE_HOSTILE)
    expect(page.get_by_text(DIR_HOSTILE).first).to_be_visible()  # legend entry carries the layer name verbatim
    multi = page.evaluate("Object.values(ReportGraph.body.nodes).map(n => n.options.font.multi)")
    assert all(m in (False, None, 'false') for m in multi), 'rich-text label parsing must stay off'
    goto_list(page)
    listing = page.locator('#node-list').inner_text()
    assert DIR_HOSTILE in listing and NAME_HOSTILE in listing
    expect(page.get_by_text(TITLE_HOSTILE, exact=True).first).to_be_visible()
    assert_inert(page)


def test_V08_modal_is_literal(open_report):
    arch, bn = hostile_report()
    page = open_report(arch, bn, title=TITLE_HOSTILE)
    open_from_list(page, file_id(EVIL)).click()
    expect(dialog(page)).to_be_visible()
    text = dialog(page).inner_text()
    assert DIR_HOSTILE in text
    assert dialog(page).locator('img, script, [onerror]').count() == 0
    page.keyboard.press('Escape')
    open_from_list(page, file_id(NAMED)).click()
    assert NAME_HOSTILE in dialog(page).inner_text()
    page.keyboard.press('Escape')
    open_from_list(page, file_id(LABELLED)).click()
    expect(dialog(page)).to_be_visible()
    assert dialog(page).locator('img, script, [onerror]').count() == 0
    assert_inert(page)


POINT_JS = """([a, b]) => { const p = ReportGraph.getPositions(b ? [a, b] : [a]);
    const q = b ? {x: (p[a].x + p[b].x) / 2, y: (p[a].y + p[b].y) / 2} : p[a];
    const d = ReportGraph.canvasToDOM(q); const r = document.querySelector('canvas').getBoundingClientRect(); return {x: r.left + d.x, y: r.top + d.y}; }"""


def hover_tooltip(page, ids, expected):
    """Hover the node (one id) or the edge midpoint (two ids) until the vis tooltip shows `expected`; re-hover on each attempt."""
    tip = page.locator('.vis-tooltip')
    last = ''
    for _ in range(5):
        page.mouse.move(1, 1)
        prepare_canvas(page)
        point = page.evaluate(POINT_JS, ids)
        page.mouse.move(point['x'] - 5, point['y'] - 5)
        page.mouse.move(point['x'], point['y'], steps=6)
        try:
            page.wait_for_function("(text) => { const t = document.querySelector('.vis-tooltip'); return !!t && getComputedStyle(t).visibility === 'visible' && t.innerText.includes(text); }", arg=expected, timeout=2500)
            return tip
        except Exception as error:
            last = str(error)
    raise AssertionError(f'tooltip containing {expected!r} never appeared: {last[:200]}')


def test_V08_edge_and_node_hover_tooltips_are_literal(open_report):
    arch, bn = hostile_report()
    page = open_report(arch, bn)
    # random layout can stack nodes on the hover point; pin well-separated positions (physics is already off)
    page.evaluate("""([evil, home, named, labelled]) => { ReportGraph.moveNode(evil, -300, 0); ReportGraph.moveNode(home, 300, 0);
        ReportGraph.moveNode(named, -300, 300); ReportGraph.moveNode(labelled, 300, 300); ReportGraph.fit({animation: false}); }""",
        [file_id(EVIL), file_id(HOME), file_id(NAMED), file_id(LABELLED)])
    tip = hover_tooltip(page, [file_id(NAMED), file_id(LABELLED)], 'IMPORTS 1')
    assert tip.locator(':not(br)').count() == 0
    tip = hover_tooltip(page, [file_id(EVIL), None], DIR_HOSTILE)
    assert tip.locator(':not(br)').count() == 0
    assert DIR_HOSTILE in tip.inner_text()
    assert_inert(page)


def test_V08_glossary_tooltip_with_hostile_data_present(open_report):
    arch, bn = hostile_report()
    page = open_report(arch, bn, title=TITLE_HOSTILE)
    term = page.locator('[data-term]:visible').first
    glossary = page.evaluate('window.ReportGlossary')
    term.hover()
    tip = page.get_by_role('tooltip')
    expect(tip).to_have_count(1)
    assert tip.first.inner_text().strip() == glossary[term.get_attribute('data-term')].strip()
    assert tip.first.locator('*').count() == 0
    assert_inert(page)
