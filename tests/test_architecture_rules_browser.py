import copy
import json

import pytest
from playwright.sync_api import expect

from tests.architecture_rules_support import RULE_KIND, to_rules, weights
from tests.report_redesign_support import SEL, close_button, control, dialog, dialog_text, file_id, goto_list

LABEL = '경계 규칙 위반'
HOSTILE = '<img src=x onerror=alert(1)>'
DIALOG_HOOK = 'window.__alerts = []; window.alert = (m) => window.__alerts.push(String(m));'

PATHS = {'a': 'domain/a.py', 'x': 'domain/x.py', 's': 'services/s.py', 'd': 'db/d.py', 'p': 'api/p.py', 'q': 'schemas/q.py'}
SPEC = {'version': 1,
        'layers': {'domain': {'paths': ['domain/**']}, 'services': {'paths': ['services/**']}, 'db': {'paths': ['db/**']},
                   'api': {'paths': ['api/**']}, 'schemas': {'paths': ['schemas/**']}},
        'allow': {'domain': []},
        'forbid': [{'from': 'db', 'to': ['api']}, {'from': 'domain', 'to': ['api']}]}


def build(paths, spec, links):
    from analysis import GraphAnalysisConfig, GraphAnalyzer
    from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
    from tests.edge_weights_support import edge
    from tests.file_analysis_support import converted, node, serialize
    files = {path: 'x = 1\n' for path in paths.values()}
    nodes = [node(key, path) for key, path in paths.items()]
    snap, arch = converted(files, nodes, [edge(a, b) for a, b in links])
    w = weights()
    analysis = GraphAnalyzer(GraphAnalysisConfig(edge_weights=w)).analyze(arch.nodes, arch.edges, project_path=arch.project_path)
    arch.stats['analysis'] = copy.deepcopy(analysis)
    report = json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, w, analysis=analysis, rules=to_rules(spec))))
    return serialize(arch), report


def open_file(page, path):
    goto_list(page)
    control(page, 'limit').select_option('all')
    page.locator(SEL['search']).fill(path)
    row = page.locator(f'{SEL["rows"]}[data-node-row="{file_id(path)}"]')
    row.wait_for(state='attached')
    target = row.locator('[data-node-id]').first if row.locator('[data-node-id]').count() else row
    target.scroll_into_view_if_needed()
    target.click()
    expect(dialog(page)).to_be_visible()
    return dialog_text(page)


def close(page):
    close_button(page).click()
    expect(dialog(page)).to_have_count(0)


@pytest.fixture(scope='module')
def standard():
    arch, report = build(PATHS, SPEC, [('a', 's'), ('d', 'p'), ('x', 'p'), ('s', 'q')])
    assert sorted(c['structure']['rule_type'] for c in report['candidates'] if c['kind'] == RULE_KIND) == ['allow', 'allow', 'forbid', 'forbid']
    return arch, report


def watch_dialogs(page):
    seen = []
    page.on('dialog', lambda d: (seen.append(d.message), d.dismiss()))
    return seen


def test_V10_allow_reason(open_report, standard):
    page = open_report(*standard, initial_script=DIALOG_HOOK)
    text = open_file(page, PATHS['a'])
    assert LABEL in text
    assert f"domain → services · 허용 목록 밖 · {PATHS['s'].rsplit('/', 1)[-1]}" in text
    assert '금지 규칙' not in text


def test_V10_forbid_reason(open_report, standard):
    page = open_report(*standard, initial_script=DIALOG_HOOK)
    text = open_file(page, PATHS['d'])
    assert LABEL in text
    assert 'db → api · 금지 규칙' in text
    assert '허용 목록 밖' not in text


def test_V10_both_reasons_on_one_file_and_target_file_only(open_report, standard):
    page = open_report(*standard, initial_script=DIALOG_HOOK)
    text = open_file(page, PATHS['x'])
    assert 'domain → api · 허용 목록 밖' in text and 'domain → api · 금지 규칙' in text
    close(page)
    for key in ('s', 'p', 'q'):
        other = open_file(page, PATHS[key])
        assert LABEL not in other and ' → ' not in other.replace('경로 → ', '')
        close(page)


def test_V10_layer_name_text_insert_valid_names_and_hostile_path(open_report):
    paths = {'a': 'one/a.py', 'h': f'two/{HOSTILE}.py', 'c': 'three/c.py'}
    spec = {'version': 1, 'layers': {'Core-Layer_2': {'paths': ['one/**']}, 'x9': {'paths': ['two/*.py']}, 'zz': {'paths': ['three/**']}},
            'allow': {'x9': []}}
    arch, report = build(paths, spec, [('h', 'a'), ('a', 'h')])
    page = open_report(arch, report, initial_script=DIALOG_HOOK)
    dialogs = watch_dialogs(page)
    text = open_file(page, paths['h'])
    assert LABEL in text and 'x9 → Core-Layer_2 · 허용 목록 밖' in text and HOSTILE in text
    close(page)
    text = open_file(page, paths['a'])
    assert 'Core-Layer_2 → x9' not in text
    page.wait_for_timeout(300)
    assert dialogs == [] and page.evaluate('window.__alerts') == []
    assert page.locator('img, :not(script)[onerror]').count() == 0
    assert page.unhandled_errors == []


def test_V10_layer_name_text_insert_hostile_payload_layer_names(open_report, standard):
    arch, report = standard
    report = copy.deepcopy(report)
    for item in report['candidates']:
        if item['kind'] == RULE_KIND:
            item['structure']['from_layer'] = HOSTILE
            item['structure']['to_layer'] = '<script>window.__alerts.push("pwned")</script>'
    page = open_report(arch, report, initial_script=DIALOG_HOOK)
    dialogs = watch_dialogs(page)
    text = open_file(page, PATHS['a'])
    assert f'{HOSTILE} → <script>window.__alerts.push("pwned")</script> · 허용 목록 밖' in text
    page.wait_for_timeout(300)
    assert dialogs == [] and page.evaluate('window.__alerts') == []
    assert page.locator('img[src="x"], dialog script, [role=dialog] script').count() == 0
    assert page.unhandled_errors == []
