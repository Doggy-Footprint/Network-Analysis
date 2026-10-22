"""V02 (graph data: filter, edge merge, color, size, candidate border) and V03 (toolbar search/reset, list tab, tab round trip, physics)."""
import math
import re

import pytest
from playwright.sync_api import expect

from tests.report_redesign_support import (
    SIZE_OPTIONS, build_report, candidate, control, file_id, goto_graph, goto_list, graph_data, make_file,
    row_ids, search_box, set_category, settle_view, tab, tab_active, text_input, SEL, numbers,
)

PROD = ['src/ui/Home.py', 'src/ui/Repo.py', 'src/data/Dao.py', 'src/data/Store.py', 'src/data/Cache.py', 'src/core/Base.py']
TESTS = ['tests/test_home.py', 'tests/test_misc.py']
LAYER = {'src/ui/Home.py': 'ui', 'src/ui/Repo.py': 'ui', 'src/data/Dao.py': 'data', 'src/data/Store.py': 'data', 'src/data/Cache.py': 'data', 'src/core/Base.py': 'core'}
LEGEND = {'ui': 2, 'data': 3, 'core': 1}
PAGERANK = dict(zip(PROD + TESTS, [0, 4, 16, 1, 9, 4, 10000, 0]))
TOKEN = dict(zip(PROD + TESTS, [100, 400, 0, 100, 400, 100, 100, 100]))


def graph_report():
    files = []
    for path in PROD + TESTS:
        files.append(make_file(path, {'pagerank': PAGERANK[path], 'fan_in': 3, 'token_cost': TOKEN[path]}, drop=() if path == 'src/data/Store.py' else ('fan_out',),))
    files[PROD.index('src/data/Store.py')]['metadata']['analysis']['fan_out'] = 7
    relations = [
        ('src/ui/Home.py', 'src/data/Dao.py', 'CALLS', 'static_certain', 'exact', 10),
        ('src/ui/Home.py', 'src/data/Dao.py', 'CALLS', 'static_inferred', 'exact', 11),
        ('src/ui/Home.py', 'src/data/Dao.py', 'IMPORTS', 'static_certain', 'exact', 12),
        ('src/data/Dao.py', 'src/ui/Home.py', 'CALLS', 'static_certain', 'exact', 20),
        ('src/ui/Repo.py', 'src/data/Dao.py', 'CALLS', 'static_certain', 'exact', 21),
        ('src/data/Store.py', 'src/data/Cache.py', 'IMPORTS', 'static_certain', 'exact', 22),
        ('src/core/Base.py', 'src/data/Store.py', 'CALLS', 'static_certain', 'exact', 23),
        ('tests/test_home.py', 'src/ui/Home.py', 'CALLS', 'static_certain', 'exact', 30),
        ('src/ui/Repo.py', 'tests/test_misc.py', 'CALLS', 'static_certain', 'exact', 31),
    ]
    candidates = [candidate(0, 'large_node', 'src/ui/Repo.py'), candidate(1, 'evidence_spread', 'src/data/Cache.py'), candidate(2, 'unresolved_boundary', 'src/core/Base.py')]
    return build_report(files, relations, candidates=candidates, manual_edges=[('src/ui/Home.py', 'src/ui/Home.py', 'CALLS')])


def expected_sizes(values):
    """sqrt, then min-max normalise into [10, 50] among the given (visible) nodes; missing or all-equal -> 10."""
    roots = {k: math.sqrt(v) for k, v in values.items() if v is not None}
    low, high = (min(roots.values()), max(roots.values())) if roots else (0, 0)
    return {k: (10 if k not in roots or high == low else 10 + (roots[k] - low) / (high - low) * 40) for k in values}


def nodes_by_id(page):
    return {n['id']: n for n in graph_data(page)['nodes']}


def choose_size(page, key):
    control_ = page.get_by_label('크기 기준')
    control_.select_option(key)


def assert_sizes(page, expected):
    observed = nodes_by_id(page)
    assert set(observed) == {file_id(p) for p in expected}
    for path, size in expected.items():
        assert observed[file_id(path)]['size'] == pytest.approx(size, abs=0.5), path


def test_V02_filter_default_and_all_node_and_edge_counts(open_report):
    arch, bn = graph_report()
    page = open_report(arch, bn)
    data = graph_data(page)
    assert {n['id'] for n in data['nodes']} == {file_id(p) for p in PROD}
    assert {(e['from'], e['to']) for e in data['edges']} == {
        (file_id('src/ui/Home.py'), file_id('src/data/Dao.py')), (file_id('src/data/Dao.py'), file_id('src/ui/Home.py')),
        (file_id('src/ui/Repo.py'), file_id('src/data/Dao.py')), (file_id('src/data/Store.py'), file_id('src/data/Cache.py')),
        (file_id('src/core/Base.py'), file_id('src/data/Store.py'))}
    assert len(data['edges']) == 5
    set_category(page, 'all')
    data = graph_data(page)
    assert len(data['nodes']) == 8 and len(data['edges']) == 7
    assert {n['id'] for n in data['nodes']} == {file_id(p) for p in PROD + TESTS}
    set_category(page, 'production')
    assert len(graph_data(page)['nodes']) == 6 and len(graph_data(page)['edges']) == 5
    assert page.unhandled_errors == []


def test_V02_edge_merge_per_from_to_pair_relation_counts_and_no_self_loop(open_report):
    arch, bn = graph_report()
    assert any(e['from_id'] == e['to_id'] for e in arch['edges'])
    page = open_report(arch, bn)
    edges = graph_data(page)['edges']
    assert all(e['from'] != e['to'] for e in edges)
    by_pair = {(e['from'], e['to']): e['title'] for e in edges}
    assert len(by_pair) == len(edges), 'one edge per (from,to) pair'
    merged = by_pair[(file_id('src/ui/Home.py'), file_id('src/data/Dao.py'))]
    assert 'CALLS 2 · IMPORTS 1' in merged
    reverse = by_pair[(file_id('src/data/Dao.py'), file_id('src/ui/Home.py'))]
    assert 'CALLS 1' in reverse and 'IMPORTS' not in reverse
    assert 'CALLS 1' in by_pair[(file_id('src/ui/Repo.py'), file_id('src/data/Dao.py'))]
    assert 'IMPORTS 1' in by_pair[(file_id('src/data/Store.py'), file_id('src/data/Cache.py'))]
    assert 'CALLS' not in by_pair[(file_id('src/data/Store.py'), file_id('src/data/Cache.py'))]


def test_V02_layer_colour_consistency_and_legend_counts(open_report):
    arch, bn = graph_report()
    page = open_report(arch, bn)
    nodes = nodes_by_id(page)
    colour_of_layer = {}
    for path in PROD:
        colour_of_layer.setdefault(LAYER[path], set()).add(nodes[file_id(path)]['fill'])
    assert all(len(colours) == 1 and None not in colours for colours in colour_of_layer.values())
    assert len({next(iter(colours)) for colours in colour_of_layer.values()}) == 3
    for layer, count in LEGEND.items():
        entry = page.get_by_text(re.compile(rf'^\s*{re.escape(layer)}\W{{0,6}}{count}\W{{0,3}}\s*$'))
        expect(entry.first).to_be_visible()


def test_V02_size_metric_selector_default_options_and_normalisation(open_report):
    arch, bn = graph_report()
    page = open_report(arch, bn)
    selector = page.get_by_label('크기 기준')
    assert selector.input_value() == 'pagerank'
    assert set(selector.locator('option').evaluate_all('(os) => os.map(o => o.value)')) == SIZE_OPTIONS
    # 0 -> 10, maximum -> 50, interior values via sqrt (linear scaling would give 20 for pagerank 4)
    assert_sizes(page, expected_sizes({p: PAGERANK[p] for p in PROD}))
    assert nodes_by_id(page)[file_id('src/data/Dao.py')]['size'] == pytest.approx(50, abs=0.5)
    assert nodes_by_id(page)[file_id('src/ui/Home.py')]['size'] == pytest.approx(10, abs=0.5)
    # all-equal values
    choose_size(page, 'fan_in')
    assert_sizes(page, {p: 10 for p in PROD})
    # a single node carries a value, the others have none
    choose_size(page, 'fan_out')
    assert_sizes(page, {p: 10 for p in PROD})
    choose_size(page, 'token_cost')
    assert_sizes(page, expected_sizes({p: TOKEN[p] for p in PROD}))
    # normalised among visible nodes only: the hidden test file with a huge value must not change sizes, showing it must
    choose_size(page, 'pagerank')
    set_category(page, 'all')
    assert_sizes(page, expected_sizes({p: PAGERANK[p] for p in PROD + TESTS}))


def test_V02_candidate_border_same_style_for_every_kind_and_distinct_from_plain(open_report):
    arch, bn = graph_report()
    page = open_report(arch, bn)
    nodes = nodes_by_id(page)
    style = lambda path: (nodes[file_id(path)]['borderWidth'], nodes[file_id(path)]['border'])
    flagged = {style(p) for p in ('src/ui/Repo.py', 'src/data/Cache.py', 'src/core/Base.py')}
    plain = {style(p) for p in ('src/ui/Home.py', 'src/data/Dao.py', 'src/data/Store.py')}
    assert len(flagged) == 1 and len(plain) == 1 and flagged != plain
    marker = page.get_by_text('후보', exact=True).evaluate_all("""(els) => els.some(el => {
        let node = el;
        for (let depth = 0; depth < 6 && node; depth++, node = node.parentElement) {
            if (node.innerText.length < 400 && /(^|\\s)ui\\W{0,6}2(\\W|$)/.test(node.innerText)) return true;
        }
        return false; })""")
    assert marker, 'the legend block holding the layer entries must also carry a 후보 marker'

def selected(page):
    return page.evaluate('ReportGraph.getSelectedNodes()')


def view(page):
    return page.evaluate('(() => ({...ReportGraph.getViewPosition(), scale: ReportGraph.getScale()}))()')


def move_away(page):
    page.evaluate('ReportGraph.moveTo({position: {x: 5000, y: 5000}, scale: 0.3, animation: false})')


def test_V03_search_match_focus_select_nomatch_status_and_reset(open_report):
    arch, bn = graph_report()
    page = open_report(arch, bn)
    box = search_box(page)
    datalist = page.evaluate("(el) => [...document.getElementById(el.getAttribute('list')).options].map(o => o.value)", box.element_handle())
    assert all(any(p in value for value in datalist) for p in PROD)
    move_away(page)
    box.fill('Repo')
    box.press('Enter')
    page.wait_for_function('ReportGraph.getSelectedNodes().length === 1')
    assert selected(page) == [file_id('src/ui/Repo.py')]
    settle_view(page)
    position = page.evaluate("ReportGraph.getPositions(['%s'])['%s']" % (file_id('src/ui/Repo.py'), file_id('src/ui/Repo.py')))
    current = view(page)
    assert abs(current['x'] - position['x']) < 2 and abs(current['y'] - position['y']) < 2 and current['scale'] > 0.3
    expect(page.get_by_text('일치하는 파일 없음')).to_have_count(0)
    box.fill('Zzz-no-such-file')
    box.press('Enter')
    expect(page.get_by_text('일치하는 파일 없음')).to_be_visible()
    box.fill('Repo')
    box.press('Enter')
    expect(page.get_by_text('일치하는 파일 없음')).to_have_count(0)
    # reset: fit the view (compared with the library's own fit) and clear the selection
    assert selected(page) == [file_id('src/ui/Repo.py')]
    move_away(page)
    page.get_by_role('button', name='화면 리셋').click()
    settle_view(page)
    assert selected(page) == []
    after = view(page)
    page.evaluate('ReportGraph.fit({animation: false})')
    reference = view(page)
    assert abs(after['x'] - reference['x']) < 1 and abs(after['y'] - reference['y']) < 1 and abs(after['scale'] - reference['scale']) < 0.01


CAPTURE_INITIAL = """(() => { let value = null; Object.defineProperty(window, 'ReportGraph', {configurable: true, get() { return value; },
  set(v) { value = v; try { window.__initialPositions = v.getPositions(); } catch (e) {} } }); })();"""


def test_V03_physics_stabilised_then_disabled(open_report):
    arch, bn = graph_report()
    page = open_report(arch, bn, initial_script=CAPTURE_INITIAL)
    options = page.evaluate("(() => { const o = ReportGraph.physics.options; return {enabled: o.enabled, iterations: Number(o.stabilization && o.stabilization.iterations)}; })()")
    assert options['enabled'] is False
    assert options['iterations'] <= 300
    start = page.evaluate('window.__initialPositions')
    final = page.evaluate('ReportGraph.getPositions()')
    moved = [k for k in final if abs(final[k]['x'] - start[k]['x']) + abs(final[k]['y'] - start[k]['y']) > 1]
    assert len(moved) >= len(final) // 2, 'stabilization must actually have moved nodes (AD1)'


def list_report():
    prod = [f'app/pkg{i:03}/m{i:03}.py' for i in range(105)]
    files = [make_file(path, {'pagerank': i + 1, 'fan_in': 105 - i}) for i, path in enumerate(prod)]
    files.append(make_file('tests/t_one.py', {'pagerank': 1000, 'fan_in': 1000}))
    candidates = [candidate(0, 'large_node', prod[3]), candidate(1, 'evidence_spread', prod[10]), candidate(2, 'unresolved_boundary', prod[20])]
    arch, bn = build_report(files, candidates=candidates)
    return arch, bn, prod


def ids(paths):
    return [file_id(p) for p in paths]


@pytest.mark.parametrize('scenario', ['search', 'sort-metric', 'candidate-kind', 'display-range', 'code-category'])
def test_V03_list_tab_filters(open_report, scenario):
    arch, bn, prod = list_report()
    page = open_report(arch, bn)
    assert tab_active(page, '그래프')
    goto_list(page)
    by_pagerank = list(reversed(prod))
    assert row_ids(page) == ids(by_pagerank[:50])
    if scenario == 'search':
        text_input(page, 'search').fill('pkg007/')
        assert row_ids(page) == ids([prod[7]])
    elif scenario == 'sort-metric':
        control(page, 'sort').select_option('fan_in')
        assert row_ids(page) == ids(prod[:50])
    elif scenario == 'candidate-kind':
        for kind, index in [('large_node', 3), ('evidence_spread', 10), ('unresolved_boundary', 20)]:
            control(page, 'candidate_kind').select_option(kind)
            assert row_ids(page) == ids([prod[index]])
        control(page, 'candidate_kind').select_option('all')
        assert row_ids(page) == ids(by_pagerank[:50])
    elif scenario == 'display-range':
        page.locator(SEL['next']).click()
        assert row_ids(page) == ids(by_pagerank[50:100])
        assert page.locator(SEL['next']).is_disabled()
        control(page, 'limit').select_option('all')
        page.locator(SEL['next']).click()
        page.locator(SEL['next']).click()
        assert row_ids(page) == ids(by_pagerank[100:])
    else:
        control(page, 'category').select_option('test')
        assert row_ids(page) == [file_id('tests/t_one.py')]
        control(page, 'category').select_option('all')
        assert row_ids(page)[0] == file_id('tests/t_one.py') and len(row_ids(page)) == 50


def test_V03_tab_round_trip_keeps_filters_search_sort_and_page(open_report):
    arch, bn, prod = list_report()
    page = open_report(arch, bn)
    goto_list(page)
    control(page, 'category').select_option('all')
    control(page, 'sort').select_option('fan_in')
    control(page, 'limit').select_option('all')
    control(page, 'candidate_kind').select_option('all')
    text_input(page, 'search').fill('app/')
    page.locator(SEL['next']).click()
    expected = ids(prod[50:100])
    assert row_ids(page) == expected
    for _ in range(2):
        goto_graph(page)
        assert tab_active(page, '그래프') and page.evaluate('window.ReportGraph != null')
        goto_list(page)
        assert tab_active(page, '목록')
        assert control(page, 'category').input_value() == 'all'
        assert control(page, 'sort').input_value() == 'fan_in'
        assert control(page, 'limit').input_value() == 'all'
        assert text_input(page, 'search').input_value() == 'app/'
        assert row_ids(page) == expected
    assert page.unhandled_errors == []


def test_V03_list_row_content_target_candidates_metric_and_no_narrative(open_report):
    """E02/F08: a row shows target, one candidate summary per kind and the sort-metric value only."""
    paths = [f'src/rows/r{i}.py' for i in range(4)]
    files = [make_file(p, {'pagerank': 10 + i, 'fan_in': 70 + i}) for i, p in enumerate(paths)]
    candidates = [candidate(0, 'large_node', paths[0]), candidate(1, 'evidence_spread', paths[0]), candidate(2, 'unresolved_boundary', paths[1])]
    arch, bn = build_report(files, candidates=candidates)
    page = open_report(arch, bn)
    goto_list(page)
    names = {k: control(page, 'candidate_kind').locator(f'option[value="{k}"]').text_content().strip().removesuffix(' 후보') for k in ('large_node', 'evidence_spread', 'unresolved_boundary')}
    kinds_of = {paths[0]: {'large_node', 'evidence_spread'}, paths[1]: {'unresolved_boundary'}, paths[2]: set(), paths[3]: set()}
    for sort_key, value in (('pagerank', lambda i: 10 + i), ('fan_in', lambda i: 70 + i)):
        control(page, 'sort').select_option(sort_key)
        for i, path in enumerate(paths):
            row = page.locator(SEL['rows']).nth(row_ids(page).index(file_id(path)))
            text = row.inner_text()
            assert path in text and path.rsplit('/', 1)[1] in text
            for kind, name in names.items():
                assert (name in text) == (kind in kinds_of[path]), (path, kind, text)
            assert row.locator('td').last.inner_text().strip() == str(value(i))
            assert all(len(line) <= 40 for line in text.splitlines()), 'rows carry no narrative text'
            assert row.locator('p').count() == 0
