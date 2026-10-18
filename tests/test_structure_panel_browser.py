"""Selectors the spec leaves open are declared once in PANEL; they follow the interface the implementer was told to expose
(#structure-* ids, button[data-structure-kind], window.ReportGraph.getSelectedNodes). Texts and counts come from spec
F16 and F17 and from existing candidate reason strings."""
import json
import re

import pytest
from playwright.sync_api import expect

from tests.delta_support import EXAMPLE_PROFILE, append_file, copy_fixture, retrack, run_bottlenecks
from tests.report_redesign_support import build_report, control, goto_list, dialog, dialog_text, file_id, make_file, tab_active
from tests.structure_support import cycle_id, cycle_target
from tests.test_delta_cli import CYCLE_FILES, VIOLATION_EDIT

PANEL = {
    'section': '#structure-section', 'delta': '#structure-delta', 'cycles': '#structure-cycles',
    'violations': '#structure-violations', 'tier': '#structure-tier', 'rules_changed': '#structure-rules-changed',
}
P = {n: f'src/{n}.py' for n in 'abcde'}
TEST_FILE = 'tests/test_a.py'
HOSTILE = '<img src=x onerror=window.__xss=1>'
HOSTILE_PATH = f'src/{HOSTILE}.py'
RELATIONS = [(P['a'], P['b'], 'IMPORTS', 'static_certain', 'exact', 1), (P['b'], P['a'], 'IMPORTS', 'static_certain', 'exact', 2),
             (P['b'], P['e'], 'IMPORTS', 'static_certain', 'exact', 3), (TEST_FILE, P['a'], 'CALLS', 'static_certain', 'exact', 4)]


def button(page, area, kind=None):
    selector = f'{PANEL[area]} button[data-structure-kind]' + (f'[data-structure-kind="{kind}"]' if kind else '')
    return page.locator(selector)


def area_text(page, area):
    return page.locator(PANEL[area]).inner_text()


def cycle_candidate(kind, scheme, tier, members, file_pairs=None):
    members = sorted(members)
    ring = [(members[i], members[(i + 1) % len(members)]) for i in range(len(members))]
    evidence = [{'from_id': a, 'to_id': b, 'relations': ['IMPORTS'], 'max_weight': 1.0, 'evidence_count': 1, 'detail_edge_indices': [i],
                 'tier': 'certain'} for i, (a, b) in enumerate(sorted(ring))]
    if file_pairs is not None:
        for record, pair in zip(evidence, file_pairs):
            record['file_pairs'] = [list(pair)]
        evidence = evidence[:len(file_pairs)]
    return {'id': cycle_id(scheme, tier, members), 'kind': kind, 'target': cycle_target(scheme, tier, members),
            'metrics': {'member_count': len(members), 'internal_pair_count': len(ring), 'internal_evidence_count': len(ring),
                        'min_pair_weight': 1.0},
            'evidence': evidence, 'coverage': 'static_analyzer_relation', 'status': 'static_candidate',
            'structure': {'scheme': scheme, 'tier': tier, 'members': members, 'parent_id': None, 'cut_candidates': []}}


def dep_cycle(tier, *paths):
    return cycle_candidate('dependency_cycle', 'file', tier, [file_id(p) for p in paths])


def pkg_cycle(packages, pairs, tier='all'):
    return cycle_candidate('package_cycle', 'language', tier, packages, [(file_id(a), file_id(b)) for a, b in pairs])


def internal_violation(index, source, target, rule='forbid', from_layer='db', to_layer='api'):
    return {'id': f'b:{index:016x}', 'kind': 'rule_violation', 'target': file_id(source),
            'metrics': {'evidence_count': 1, 'max_weight': 1.0},
            'evidence': [{'from_id': file_id(source), 'to_id': file_id(target), 'relations': ['IMPORTS'], 'max_weight': 1.0,
                          'evidence_count': 1, 'detail_edge_indices': [0], 'tier': 'all'}],
            'coverage': 'static_analyzer_relation', 'status': 'static_candidate',
            'structure': {'rule_type': rule, 'from_layer': from_layer, 'to_layer': to_layer, 'tier': 'all', 'relations': ['IMPORTS']}}


def external_violation(index, source, name='fastapi', from_layer='db'):
    return {'id': f'b:{index:016x}', 'kind': 'rule_violation', 'target': file_id(source), 'metrics': {'evidence_count': 1},
            'evidence': [{'line': 3, 'name': name}], 'coverage': 'static_analyzer_relation', 'status': 'static_candidate',
            'structure': {'rule_type': 'forbid_external', 'from_layer': from_layer, 'matched': ['group:web'], 'relations': ['IMPORTS'],
                          'tier': 'certain', 'to_external': name}}


def cycle_item(candidate, baseline_ids=()):
    structure = candidate['structure']
    return {'candidate_id': candidate['id'], 'kind': candidate['kind'], 'scheme': structure['scheme'], 'tier': structure['tier'],
            'members': structure['members'], 'baseline_candidate_ids': list(baseline_ids), 'added_members': structure['members'][:1],
            'new_internal_pairs': []}


def violation_item(candidate):
    structure = candidate['structure']
    item = {'candidate_id': candidate['id'], 'rule_type': structure['rule_type'], 'from_layer': structure['from_layer'],
            'target': candidate['target']}
    if 'to_layer' in structure:
        item.update(to_layer=structure['to_layer'], to_id=candidate['evidence'][0]['to_id'])
    else:
        item['to_external'] = structure['to_external']
    return item


def delta_of(new_cycles=(), grown_cycles=(), new_violations=(), packages=(), instability=(), rules_changed=False):
    lists = {'new_cycles': list(new_cycles), 'grown_cycles': list(grown_cycles), 'new_violations': list(new_violations),
             'new_package_dependencies': list(packages), 'instability_changes': list(instability)}
    return {'policy': 'delta.v1', 'baseline': {'file_count': 5, 'rules_sha256': 'a' * 64}, 'rules_changed': rules_changed, **lists,
            'resolved': {'cycles': 0, 'violations': 0, 'package_dependencies': 0},
            'counts': {name: len(items) for name, items in lists.items()}}


def report(candidates, delta=None, paths=None, relations=RELATIONS):
    names = list(paths if paths is not None else [*P.values(), TEST_FILE])
    arch, bn = build_report([make_file(p) for p in names], relations, candidates=candidates)
    if delta is not None:
        bn['delta'] = delta
    return arch, bn


C_CERTAIN = dep_cycle('certain', P['a'], P['b'])
C_RESOLVED = dep_cycle('resolved', P['a'], P['b'], P['c'])
C_ALL = dep_cycle('all', P['a'], P['b'], P['c'], P['d'])
C_TEST = dep_cycle('all', P['a'], P['e'], TEST_FILE)
PKG = pkg_cycle(['pkg:dir:src/a', 'pkg:dir:src/b'], [(P['a'], P['b']), (P['b'], P['e'])])
V_INTERNAL = internal_violation(1, P['a'], P['b'])
V_EXTERNAL = external_violation(2, P['c'])


def standard_candidates():
    return [C_CERTAIN, C_RESOLVED, C_ALL, C_TEST, PKG, V_INTERNAL, V_EXTERNAL]


def standard_delta(rules_changed=True):
    return delta_of(
        new_cycles=[cycle_item(C_ALL)], grown_cycles=[cycle_item(PKG, ['b:0000000000000099'])],
        new_violations=[violation_item(V_INTERNAL), violation_item(V_EXTERNAL)],
        packages=[{'scheme': 'language', 'from_id': 'pkg:python:app.zz', 'to_id': 'pkg:python:app.fresh', 'tier': 'certain'}],
        instability=[{'scheme': 'language', 'package': 'pkg:python:app.shifted', 'baseline': 0.1, 'current': 0.5, 'delta': 0.4}],
        rules_changed=rules_changed)


@pytest.fixture
def standard(open_report):
    arch, bn = report(standard_candidates(), standard_delta())
    return open_report(arch, bn)


def selected(page):
    return page.evaluate('ReportGraph.getSelectedNodes()')


def body(page):
    return page.locator('body').inner_text()


STATUS = re.compile(r'(\d+)개 파일 강조(?: · (\d+)개는 현재 코드 분류 밖)?')


def clicked(page, locator):
    results = []
    for index in range(locator.count()):
        page.evaluate('ReportGraph.unselectAll()')
        locator.nth(index).click()
        page.wait_for_function('ReportGraph.getSelectedNodes().length > 0')
        match = STATUS.search(body(page))
        results.append((sorted(selected(page)), match.group(0) if match else None))
    return results


def ids(*names):
    return sorted(file_id(P[n]) if n in P else file_id(n) for n in names)


def sets_of(results):
    return sorted(r[0] for r in results)


# display ---------------------------------------------------------------------------------------------------------------

def test_V11_section_shown_for_file_granularity_after_the_review_section(standard):
    page = standard
    expect(page.locator(PANEL['section'])).to_be_visible()
    assert '03 / 구조' in page.locator(PANEL['section']).inner_text()
    numbers = page.evaluate("""() => [...document.querySelectorAll('section')]
      .map(s => (s.textContent.match(/(\\d\\d) \\/ /) || [])[1]).filter(Boolean)""")
    assert numbers[-2:] == ['02', '03'] and numbers.count('03') == 1


def test_V11_section_hidden_for_symbol_granularity(open_report, tmp_path):
    from tests.unified_support import architecture, bottleneck_fixture, node
    arch = architecture([node('a')])
    bn = bottleneck_fixture(tmp_path, arch['nodes'], candidate_count=0)
    page = open_report(arch, bn)
    expect(page.locator(PANEL['section'])).to_be_hidden()
    assert '03 / 구조' not in body(page)


def test_V11_delta_block_lists_each_delta_family(standard):
    page = standard
    expect(page.locator(PANEL['delta'])).to_be_visible()
    assert button(page, 'delta', 'new_cycles').count() == 1
    assert button(page, 'delta', 'grown_cycles').count() == 1
    assert button(page, 'delta', 'new_violations').count() == 2
    text = area_text(page, 'delta')
    for name in ('pkg:python:app.zz', 'pkg:python:app.fresh', 'pkg:python:app.shifted'):
        assert name in text
    for kind in ('new_package_dependencies', 'instability_changes'):
        assert button(page, 'delta', kind).count() == 0
    assert page.locator(f'{PANEL["delta"]} button:has-text("pkg:python:app.zz"), {PANEL["delta"]} button:has-text("pkg:python:app.shifted")').count() == 0


def test_V11_delta_block_absent_without_baseline(open_report):
    arch, bn = report(standard_candidates())
    page = open_report(arch, bn)
    expect(page.locator(PANEL['delta'])).to_be_hidden()
    expect(page.locator(PANEL['section'])).to_be_visible()
    assert button(page, 'cycles').count() > 0 and button(page, 'violations').count() == 2


def test_V11_rules_changed_warning_follows_the_flag(open_report):
    arch, bn = report(standard_candidates(), standard_delta(rules_changed=True))
    expect(open_report(arch, bn).locator(PANEL['rules_changed'])).to_be_visible()
    arch, bn = report(standard_candidates(), standard_delta(rules_changed=False))
    expect(open_report(arch, bn).locator(PANEL['rules_changed'])).to_be_hidden()


def test_V11_counts_summary_line_pairs_each_count_in_order(open_report):
    arch, bn = report(standard_candidates(), delta_of(
        new_cycles=[cycle_item(C_ALL)] * 3, grown_cycles=[cycle_item(PKG)] * 4, new_violations=[violation_item(V_EXTERNAL)] * 5,
        packages=[{'scheme': 'language', 'from_id': f'pkg:p{i}', 'to_id': 'pkg:q', 'tier': 'certain'} for i in range(6)],
        instability=[{'scheme': 'language', 'package': f'pkg:i{i}', 'baseline': 0.0, 'current': 0.5, 'delta': 0.5} for i in range(7)]))
    text = area_text(open_report(arch, bn), 'delta')
    lines = [line for line in text.splitlines() if re.findall(r'\d+', line) == ['3', '4', '5', '6', '7']]
    assert lines, text


def test_V11_cycles_follow_tier_selection_by_equality(standard):
    page = standard
    select = page.locator(PANEL['tier'])
    assert select.input_value() == 'all'
    assert set(select.locator('option').evaluate_all('(o) => o.map(x => x.value)')) == {'certain', 'resolved', 'all'}
    expected = {'certain': [ids('a', 'b')], 'resolved': [ids('a', 'b', 'c')],
                'all': sorted([ids('a', 'b', 'c', 'd'), ids('a', 'e'), ids('a', 'b', 'e')])}
    assert sets_of(clicked(page, button(page, 'cycles'))) == expected['all']
    for tier in ('certain', 'resolved', 'all'):
        select.select_option(tier)
        assert button(page, 'cycles').count() == len(expected[tier]), tier
        assert sets_of(clicked(page, button(page, 'cycles'))) == expected[tier], tier


def test_V11_C24_click_from_the_list_tab_switches_to_the_graph(standard):
    page = standard
    goto_list(page)
    assert tab_active(page, '목록') and not tab_active(page, '그래프')
    button(page, 'cycles', 'package_cycle').first.click()
    page.wait_for_function('window.ReportGraph != null && ReportGraph.getSelectedNodes().length === 3')
    assert tab_active(page, '그래프')
    assert sorted(selected(page)) == ids('a', 'b', 'e')


def test_V11_violation_reasons_use_the_existing_candidate_wording(standard):
    text = area_text(standard, 'violations')
    assert 'db → api · 금지 규칙' in text
    assert 'db → fastapi · 외부 금지 규칙' in text
    assert P['a'] in text and P['c'] in text


def test_V11_C28_lists_cap_at_fifty_and_report_the_rest(open_report):
    many = [internal_violation(100 + i, P['a'], P['b'], to_layer=f'api{i:02d}') for i in range(51)]
    arch, bn = report(many, delta_of(new_violations=[violation_item(v) for v in many]))
    page = open_report(arch, bn)
    assert button(page, 'violations').count() == 50
    assert '외 1개' in area_text(page, 'violations')
    assert button(page, 'delta', 'new_violations').count() == 50
    assert '외 1개' in area_text(page, 'delta')
    arch, bn = report(many[:50])
    page = open_report(arch, bn)
    assert button(page, 'violations').count() == 50 and '외 ' not in area_text(page, 'violations')


def test_V11_empty_lists_say_none(open_report):
    arch, bn = report([], delta_of())
    page = open_report(arch, bn)
    assert '없음' in area_text(page, 'cycles') and '없음' in area_text(page, 'violations') and '없음' in area_text(page, 'delta')
    assert button(page, 'cycles').count() == 0 and button(page, 'violations').count() == 0


# selection -------------------------------------------------------------------------------------------------------------

def test_V11_C24_cycle_click_selects_members_on_the_graph(standard):
    page = standard
    results = clicked(page, button(page, 'cycles', 'dependency_cycle'))
    assert tab_active(page, '그래프')
    by_set = {tuple(r[0]): r[1] for r in results}
    assert by_set[tuple(ids('a', 'b', 'c', 'd'))] == '4개 파일 강조'


def test_V11_package_cycle_click_selects_the_files_of_its_evidence_pairs(standard):
    results = clicked(standard, button(standard, 'cycles', 'package_cycle'))
    assert results == [(ids('a', 'b', 'e'), '3개 파일 강조')]


def test_V11_violation_clicks_select_target_and_destination_or_target_only(standard):
    page = standard
    internal = page.locator(f'{PANEL["violations"]} button[data-structure-kind]:has-text("db → api")')
    external = page.locator(f'{PANEL["violations"]} button[data-structure-kind]:has-text("fastapi")')
    assert clicked(page, internal) == [(ids('a', 'b'), '2개 파일 강조')]
    assert clicked(page, external) == [(ids('c'), '1개 파일 강조')]


def test_V11_delta_items_resolve_their_file_sets(standard):
    page = standard
    assert clicked(page, button(page, 'delta', 'grown_cycles')) == [(ids('a', 'b', 'e'), '3개 파일 강조')]
    assert clicked(page, button(page, 'delta', 'new_cycles')) == [(ids('a', 'b', 'c', 'd'), '4개 파일 강조')]
    assert sets_of(clicked(page, button(page, 'delta', 'new_violations'))) == sorted([ids('a', 'b'), ids('c')])


def test_V11_C25_files_outside_the_code_filter_are_counted_not_selected(standard):
    page = standard
    by_set = {tuple(r[0]): r[1] for r in clicked(page, button(page, 'cycles', 'dependency_cycle'))}
    assert by_set[tuple(ids('a', 'e'))] == '2개 파일 강조 · 1개는 현재 코드 분류 밖'
    assert file_id(TEST_FILE) not in {f for key in by_set for f in key}


def test_V11_C25_widening_the_filter_selects_the_test_file_too(open_report):
    arch, bn = report(standard_candidates(), standard_delta())
    page = open_report(arch, bn)
    control(page, 'category').select_option('all')
    by_set = {tuple(r[0]): r[1] for r in clicked(page, button(page, 'cycles', 'dependency_cycle'))}
    assert by_set[tuple(ids('a', 'e', TEST_FILE))] == '3개 파일 강조'


def test_V11_C26_without_the_graph_library_the_first_file_modal_opens(open_report):
    candidate = dep_cycle('all', P['e'], P['d'], P['c'])
    arch, bn = report([candidate], paths=[P['c'], P['d'], P['e']], relations=[])
    page = open_report(arch, bn, cdn='abort')
    button(page, 'cycles', 'dependency_cycle').first.click()
    expect(dialog(page)).to_be_visible()
    text = dialog_text(page)
    assert P['c'] in text and P['d'] not in text and P['e'] not in text


def test_V11_C23_hostile_file_names_stay_text(open_report):
    names = [P['a'], HOSTILE_PATH]
    cyc = dep_cycle('all', *names)
    violation = internal_violation(7, HOSTILE_PATH, P['a'], from_layer=HOSTILE, to_layer='api')
    external = external_violation(8, HOSTILE_PATH, name=HOSTILE)
    pkg = {'scheme': 'language', 'from_id': HOSTILE, 'to_id': 'pkg:python:x', 'tier': 'certain'}
    delta = delta_of(new_cycles=[cycle_item(cyc)], new_violations=[violation_item(violation), violation_item(external)], packages=[pkg],
                     instability=[{'scheme': 'language', 'package': HOSTILE, 'baseline': 0.0, 'current': 0.9, 'delta': 0.9}])
    arch, bn = report([cyc, violation, external], delta, paths=names, relations=[(P['a'], HOSTILE_PATH, 'IMPORTS', 'static_certain', 'exact', 1)])
    page = open_report(arch, bn)
    dialogs = []
    page.on('dialog', lambda d: (dialogs.append(d.message), d.dismiss()))
    page.wait_for_timeout(300)
    section = page.locator(PANEL['section'])
    assert page.evaluate('window.__xss') is None
    assert HOSTILE in section.inner_text() and HOSTILE_PATH in area_text(page, 'cycles')
    assert section.locator('img, [onerror]').count() == 0
    button(page, 'cycles', 'dependency_cycle').first.click()
    page.wait_for_timeout(300)
    assert page.evaluate('window.__xss') is None and dialogs == []
    assert page.unhandled_errors == []


# end to end ------------------------------------------------------------------------------------------------------------

@pytest.fixture(scope='module')
def cli_html(tmp_path_factory):
    from fixtures.registry import fixture_root
    directory = tmp_path_factory.mktemp('panel-html')
    run_bottlenecks(fixture_root('fastapi-realworld').resolve(), directory / 'base', rules=EXAMPLE_PROFILE)
    root = copy_fixture('fastapi-realworld', directory / 'copy')
    for relative, text in [*CYCLE_FILES, *VIOLATION_EDIT]:
        append_file(root, relative, text)
    retrack(root)
    done = run_bottlenecks(root, directory / 'out', rules=EXAMPLE_PROFILE, extra=['--baseline', directory / 'base' / 'b.json'], check=False)
    assert done.returncode == 0, done.stderr[-1500:]
    return (directory / 'out' / 'r.html').read_text(encoding='utf-8'), json.loads((directory / 'out' / 'b.json').read_text(encoding='utf-8'))


def test_V11_F04_cli_html_carries_the_delta_and_clicking_selects_the_item_files(open_report, cli_html):
    html, payload = cli_html
    delta = payload['delta']
    assert delta['new_cycles'] and delta['new_violations'] and len(delta['new_cycles']) <= 50
    assert {item['kind'] for item in delta['new_cycles']} == {'dependency_cycle'}
    page = open_report(None, None, html=html, graph=True)
    expect(page.locator(PANEL['section'])).to_be_visible()
    expect(page.locator(PANEL['rules_changed'])).to_be_hidden()
    assert button(page, 'delta', 'new_cycles').count() == len(delta['new_cycles'])
    assert button(page, 'delta', 'new_violations').count() == len(delta['new_violations'])
    assert sets_of(clicked(page, button(page, 'delta', 'new_cycles'))) == sorted(sorted(i['members']) for i in delta['new_cycles'])
    wanted = sorted(sorted({i['target'], i['to_id']}) for i in delta['new_violations'])
    assert sets_of(clicked(page, button(page, 'delta', 'new_violations'))) == wanted
