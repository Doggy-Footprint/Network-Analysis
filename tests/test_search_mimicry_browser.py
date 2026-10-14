"""V8 and G4 for spec f7564b09cf80bdd9 v1: rendered unified report (playwright) and static metric definitions.

H1/H2: in symbol and file mode no select option, glossary entry or tooltip names a removed metric (Hub, Authority,
Degree, 3-hop, the identifier-occurrence label or any removed key). H3: the six core cards keep the order
[pagerank, betweenness_centrality, hop_2_token_cost, weighted_centrality_cost, fan_in, fan_out]. H4: the static
METRIC_DEFINITIONS table. G4: a wrong core slice in app.js would change the card keys or their labels.
"""
import pytest
from playwright.sync_api import Error as PlaywrightError

from report.bottlenecks.generate import METRIC_DEFINITIONS
from tests.report_redesign_support import CORE_KEYS, CORE_LABELS, build_report, control, goto_graph, goto_list, make_file
from tests.unified_support import CORE, architecture, bottleneck_fixture, node

REMOVED_DISPLAY = ("Hub", "Authority", "Degree", "3-hop", "식별자 출현 파일")
REMOVED_KEYS = ("hub_score", "authority_score", "degree_centrality", "hop_3_token_cost", "identifier_file_count")
EXPECTED_CORE = ["pagerank", "betweenness_centrality", "hop_2_token_cost", "weighted_centrality_cost", "fan_in", "fan_out"]
PATHS = ["app/ui/Home.py", "app/ui/Repo.py", "app/data/Dao.py"]

SELECT_TEXTS_JS = """() => [...document.querySelectorAll('select')].flatMap(s => [...s.options].flatMap(o => [o.textContent, o.value, o.label]))"""
TERM_ELEMENTS_JS = """() => [...document.querySelectorAll('[data-term]')].filter(el => {
  const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && el.checkVisibility({contentVisibilityAuto: true, visibilityProperty: true, opacityProperty: false}); }).map((el, i) => { el.setAttribute('data-v8-probe', String(i)); return i; })"""


def symbol_report(tmp_path):
    nodes = [node("a", value=3), node("b", value=2), node("c", value=1)]
    return architecture(nodes), bottleneck_fixture(tmp_path, nodes)


def file_report():
    files = [make_file(path, {"pagerank": index + 1}) for index, path in enumerate(PATHS)]
    return build_report(files, [(PATHS[0], PATHS[2], "CALLS", "static_certain", "exact", 10)])


def assert_clean(text, where):
    for name in (*REMOVED_DISPLAY, *REMOVED_KEYS):
        assert name not in text, (where, name)


def observe(page):
    texts = page.evaluate(SELECT_TEXTS_JS)
    goto_list(page)
    texts += page.evaluate(SELECT_TEXTS_JS)
    glossary = page.evaluate("window.ReportGlossary || {}")
    texts += list(glossary) + [str(value) for value in glossary.values()]
    tooltips = []
    for index in page.evaluate(TERM_ELEMENTS_JS):
        element = page.locator(f'[data-v8-probe="{index}"]').first
        try:
            element.scroll_into_view_if_needed(timeout=2000)
            element.focus(timeout=2000)
        except PlaywrightError:
            continue
        tip = page.get_by_role("tooltip")
        if tip.count():
            tooltips.append(tip.first.inner_text())
        element.evaluate("(el) => el.blur()")
    return texts, tooltips, glossary


def core_cards(page):
    return page.locator("[data-metric-group]").evaluate_all("(els) => els.map(e => e.dataset.metricGroup)")


@pytest.mark.parametrize("mode", ["symbol", "file"])
def test_V8_H1_H2_selects_glossary_and_tooltips_name_no_removed_metric(open_report, tmp_path, mode):
    arch, bottlenecks = symbol_report(tmp_path) if mode == "symbol" else file_report()
    page = open_report(arch, bottlenecks)
    texts, tooltips, glossary = observe(page)
    options = control(page, "sort").locator("option").evaluate_all("(os) => os.map(o => o.value)")
    assert options
    assert not set(options) & set(REMOVED_KEYS)
    assert glossary, "glossary must be loaded for the term check to be meaningful"
    for text in texts:
        assert_clean(str(text), f"{mode} select/glossary")
    for text in tooltips:
        assert_clean(text, f"{mode} tooltip")
    assert tooltips, "at least one rendered term tooltip must be observed"


@pytest.mark.parametrize("mode", ["symbol", "file"])
def test_V8_H1_H2_size_selector_lists_only_surviving_metrics(open_report, tmp_path, mode):
    arch, bottlenecks = symbol_report(tmp_path) if mode == "symbol" else file_report()
    page = open_report(arch, bottlenecks)
    if mode == "file":
        goto_graph(page)
    size = page.get_by_label("크기 기준")
    values = size.locator("option").evaluate_all("(os) => os.map(o => o.value)")
    allowed = set(CORE_KEYS) | {"token_cost"}
    if mode == "file":
        assert set(values) == allowed
    else:
        assert set(values) <= allowed
    assert_clean(" ".join(size.locator("option").all_text_contents()), f"{mode} size options")


@pytest.mark.parametrize("mode", ["symbol", "file"])
def test_V8_H3_core_cards_are_the_six_core_metrics_in_order(open_report, tmp_path, mode):
    arch, bottlenecks = symbol_report(tmp_path) if mode == "symbol" else file_report()
    page = open_report(arch, bottlenecks)
    assert core_cards(page) == EXPECTED_CORE
    assert list(CORE) == EXPECTED_CORE
    cards = page.locator("[data-metric-group]")
    for index, label in enumerate(CORE_LABELS):
        assert label in cards.nth(index).inner_text(), (mode, index)


def test_V8_H4_metric_definitions_exclude_removed_metrics():
    keys = [key for key, _ in METRIC_DEFINITIONS]
    assert len(keys) == len(set(keys))
    assert not set(keys) & set(REMOVED_KEYS)
    assert {"hop_3_token_cost", "degree_centrality"}.isdisjoint(keys)
    assert set(EXPECTED_CORE) | {"token_cost", "effective_token_cost", "weighted_fan_in", "weighted_fan_out"} == set(keys)
    for _, definition in METRIC_DEFINITIONS:
        assert_clean(definition, "METRIC_DEFINITIONS")
