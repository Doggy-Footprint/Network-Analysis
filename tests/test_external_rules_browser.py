import copy
import json

import pytest

from tests.architecture_rules_support import weights
from tests.external_rules_support import ALLOW_EXT, FORBID_EXT, RULE_KIND, rec, to_rules_ext
from tests.test_architecture_rules_browser import DIALOG_HOOK, HOSTILE, LABEL, close, open_file, watch_dialogs

PATHS = {'d': 'db/d.py', 'a': 'domain/a.py', 's': 'services/s.py', 'p': 'api/p.py', 'h': 'hostile/h.py'}
RECORDS = {'d': [rec('fastapi', 1)], 'a': [rec('os', 2), rec('typing', 1)], 's': [rec('fastapi', 1)], 'p': None,
           'h': [rec(HOSTILE, 3)]}
SPEC = {'version': 1,
        'layers': {'db': {'paths': ['db/**']}, 'domain': {'paths': ['domain/**']}, 'services': {'paths': ['services/**']},
                   'api': {'paths': ['api/**']}, 'x9': {'paths': ['hostile/**']}},
        'external': {'web': ['fastapi*']},
        'allow': {'domain': []},
        'forbid': [{'from': 'db', 'to': ['api'], 'to_external': ['group:web']}, {'from': 'x9', 'to_external': ['<img*']}],
        'allow_external': {'domain': ['typing'], 'x9': []}}


def build_ext(paths, records, spec, links):
    from analysis import GraphAnalysisConfig, GraphAnalyzer
    from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
    from tests.edge_weights_support import edge
    from tests.file_analysis_support import converted, node, serialize
    files = {path: 'x = 1\n' for path in paths.values()}
    nodes = [node(key, path, metadata={'external_imports': copy.deepcopy(records[key])} if records.get(key) else None)
             for key, path in paths.items()]
    snap, arch = converted(files, nodes, [edge(a, b) for a, b in links])
    w = weights()
    analysis = GraphAnalyzer(GraphAnalysisConfig(edge_weights=w)).analyze(arch.nodes, arch.edges, project_path=arch.project_path)
    arch.stats['analysis'] = copy.deepcopy(analysis)
    report = json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, w, analysis=analysis, rules=to_rules_ext(spec))))
    return serialize(arch), report


@pytest.fixture(scope='module')
def standard():
    arch, report = build_ext(PATHS, RECORDS, SPEC, [('a', 's'), ('d', 'p')])
    found = sorted((c['structure']['rule_type'], c['structure']['to_external']) for c in report['candidates']
                   if c['kind'] == RULE_KIND and c['structure']['rule_type'] in (FORBID_EXT, ALLOW_EXT))
    assert found == [(ALLOW_EXT, HOSTILE), (ALLOW_EXT, 'os'), (FORBID_EXT, HOSTILE), (FORBID_EXT, 'fastapi')]
    return arch, report


def test_V13_forbid_external_reason(open_report, standard):
    page = open_report(*standard, initial_script=DIALOG_HOOK)
    text = open_file(page, PATHS['d'])
    assert LABEL in text
    assert 'db → fastapi · 외부 금지 규칙' in text
    assert '외부 허용 목록 밖' not in text


def test_V13_allow_external_reason(open_report, standard):
    page = open_report(*standard, initial_script=DIALOG_HOOK)
    text = open_file(page, PATHS['a'])
    assert LABEL in text
    assert 'domain → os · 외부 허용 목록 밖' in text
    assert 'domain → typing' not in text and '외부 금지 규칙' not in text


def test_V13_internal_reason_unchanged_next_to_external_reasons(open_report, standard):
    page = open_report(*standard, initial_script=DIALOG_HOOK)
    text = open_file(page, PATHS['a'])
    assert 'domain → services · 허용 목록 밖 · s.py' in text
    close(page)
    text = open_file(page, PATHS['d'])
    assert 'db → api · 금지 규칙' in text and 'db → api · 외부' not in text


def test_V13_files_without_a_violation_show_no_boundary_reason(open_report, standard):
    page = open_report(*standard, initial_script=DIALOG_HOOK)
    for key in ('s', 'p'):
        text = open_file(page, PATHS[key])
        assert LABEL not in text and ' → fastapi' not in text
        close(page)


def test_V13_hostile_specifier_is_inserted_as_text(open_report, standard):
    page = open_report(*standard, initial_script=DIALOG_HOOK)
    dialogs = watch_dialogs(page)
    text = open_file(page, PATHS['h'])
    assert LABEL in text
    assert f'x9 → {HOSTILE} · 외부 허용 목록 밖' in text and f'x9 → {HOSTILE} · 외부 금지 규칙' in text
    page.wait_for_timeout(300)
    assert dialogs == [] and page.evaluate('window.__alerts') == []
    assert page.locator('img, :not(script)[onerror]').count() == 0
    assert page.unhandled_errors == []


def test_V13_hostile_layer_and_external_names_in_payload_are_text(open_report, standard):
    arch, report = standard
    report = copy.deepcopy(report)
    script = '<script>window.__alerts.push("pwned")</script>'
    for item in report['candidates']:
        if item['kind'] == RULE_KIND and item['structure']['rule_type'] == FORBID_EXT and item['target'] == 'file:db/d.py':
            item['structure']['from_layer'] = HOSTILE
            item['structure']['to_external'] = script
    page = open_report(arch, report, initial_script=DIALOG_HOOK)
    dialogs = watch_dialogs(page)
    text = open_file(page, PATHS['d'])
    assert f'{HOSTILE} → {script} · 외부 금지 규칙' in text
    page.wait_for_timeout(300)
    assert dialogs == [] and page.evaluate('window.__alerts') == []
    assert page.locator('img[src="x"], dialog script, [role=dialog] script').count() == 0
    assert page.unhandled_errors == []
