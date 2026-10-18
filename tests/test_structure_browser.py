"""Playwright evidence for the dependency_cycle display and its XSS safety (V10; C21, C22; Q05, Q07).

Spec f80bb8ba5e7ac1ef v3 F16: dependency_cycle is attached to every member file with the kind label and the reason
"<member_count>개 파일 순환 · <tier label>"; package_cycle and unstable_dependency are not shown. The exact kind label is
the implementer's choice, so it is read from report.bottlenecks.generate.KIND_LABELS at runtime (or from the dashboard's
own kind filter option when it offers one); the reason string is fixed by the spec.
"""
import copy
import json
import os
import re
import subprocess
import sys

import pytest
from playwright.sync_api import expect

from fixtures.registry import fixture_root
from tests.report_redesign_support import SEL, build_report, close_button, control, dialog, dialog_text, file_id, goto_list, make_file
from tests.structure_support import REPO, TIER_LABELS, TIERS, cycle_id, cycle_target, default_weights

REASON = re.compile(r'\d+개 파일 순환 ·')


def reason(count, tier):
    return f'{count}개 파일 순환 · {TIER_LABELS[tier]}'


def kind_labels(kind):
    from report.bottlenecks.generate import KIND_LABELS
    return KIND_LABELS[kind]


def dashboard_labels(page, kind):
    """Labels a reader can see for `kind`: the report-page label, plus the dashboard filter option text when present."""
    labels = {kind_labels(kind)}
    option = control(page, 'candidate_kind').locator(f'option[value="{kind}"]')
    if option.count():
        labels.add(re.sub(r'\s*후보$', '', option.first.text_content().strip()))
    return {label for label in labels if label}


def cycle_candidate(tier, paths, scheme='file', kind='dependency_cycle'):
    members = sorted(file_id(p) for p in paths) if scheme == 'file' else sorted(paths)
    ring = [(members[i], members[(i + 1) % len(members)]) for i in range(len(members))]
    return {'id': cycle_id(scheme, tier, members), 'kind': kind, 'target': cycle_target(scheme, tier, members),
            'metrics': {'member_count': len(members), 'internal_pair_count': len(ring), 'internal_evidence_count': len(ring), 'min_pair_weight': 1.0},
            'evidence': [{'from_id': a, 'to_id': b, 'relations': ['IMPORTS'], 'max_weight': 1.0, 'evidence_count': 1, 'detail_edge_indices': [i], 'tier': 'certain'}
                         for i, (a, b) in enumerate(sorted(ring))],
            'coverage': 'static_analyzer_relation', 'status': 'static_candidate',
            'structure': {'scheme': scheme, 'tier': tier, 'members': members, 'parent_id': None, 'cut_candidates': []}}


def unstable_candidate():
    return {'id': 'b:0000000000000abc', 'kind': 'unstable_dependency', 'target': 'pkg:dir:src/a',
            'metrics': {'instability_from': .5, 'instability_to': .75, 'instability_delta': .25, 'evidence_count': 2, 'file_pair_count': 1},
            'evidence': [], 'coverage': 'static_analyzer_relation', 'status': 'static_candidate',
            'structure': {'scheme': 'language', 'tier': 'certain', 'from_package': 'pkg:dir:src/a', 'to_package': 'pkg:dir:src/b'}}


PATHS = {name: f'src/{name}.py' for name in 'abcde'}


def synthetic_report():
    files = [make_file(p) for p in PATHS.values()]
    candidates = [
        cycle_candidate('certain', [PATHS['a'], PATHS['b']]),
        cycle_candidate('resolved', [PATHS['a'], PATHS['b'], PATHS['c']]),
        cycle_candidate('all', [PATHS['a'], PATHS['b'], PATHS['c'], PATHS['d']]),
        cycle_candidate('all', ['pkg:dir:src/a', 'pkg:dir:src/b'], scheme='language', kind='package_cycle'),
        unstable_candidate(),
    ]
    return build_report(files, candidates=candidates)


def open_file(page, path, search=False):
    goto_list(page)
    if search:
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


EXPECTED = {
    'a': [reason(2, 'certain'), reason(3, 'resolved'), reason(4, 'all')],
    'b': [reason(2, 'certain'), reason(3, 'resolved'), reason(4, 'all')],
    'c': [reason(3, 'resolved'), reason(4, 'all')],
    'd': [reason(4, 'all')],
    'e': [],
}


@pytest.mark.parametrize('member', sorted(EXPECTED))
def test_V10_cycle_shown_on_each_member_with_tier_labels(open_report, member):
    arch, bn = synthetic_report()
    page = open_report(arch, bn)
    text = open_file(page, PATHS[member])
    reasons = [line.strip() for line in text.splitlines() if REASON.search(line)]
    assert len(reasons) == len(EXPECTED[member]), (member, reasons)
    for expected in EXPECTED[member]:
        assert any(expected in line for line in reasons), (member, expected)
    labels = dashboard_labels(page, 'dependency_cycle')
    if EXPECTED[member]:
        assert any(label in text for label in labels), (member, labels)
    else:
        assert not any(label in text for label in labels) and not REASON.search(text)


def test_V10_tier_label_text_is_exact_for_all_three_tiers(open_report):
    arch, bn = synthetic_report()
    text = open_file(open_report(arch, bn), PATHS['a'])
    for count, tier, label in ((2, 'certain', '확정 연결'), (3, 'resolved', '해석된 연결'), (4, 'all', '불확실 포함')):
        assert f'{count}개 파일 순환 · {label}' in text


def test_V10_package_kinds_are_hidden_everywhere_in_the_dashboard(open_report):
    arch, bn = synthetic_report()
    page = open_report(arch, bn)
    for member in 'ab':
        text = open_file(page, PATHS[member])
        for kind in ('package_cycle', 'unstable_dependency'):
            assert not any(label in text for label in dashboard_labels(page, kind)), (member, kind)
        assert 'pkg:dir:' not in text
        close(page)
    goto_list(page)
    listing = page.locator('#node-list').inner_text()
    for kind in ('package_cycle', 'unstable_dependency'):
        assert not any(label in listing for label in dashboard_labels(page, kind))
    assert 'pkg:dir:' not in listing


def test_V10_cycle_member_with_only_base_candidates_keeps_them(open_report):
    arch, bn = synthetic_report()
    bn['candidates'].append({'id': 'b:00000000000000aa', 'kind': 'large_node', 'target': file_id(PATHS['e']),
                             'metrics': {'line_count': 2417, 'line_threshold': 2000},
                             'evidence': {'path': PATHS['e'], 'start_line': 1, 'end_line': 2}, 'coverage': 'static_analyzer_relation', 'status': 'static_candidate'})
    page = open_report(arch, bn)
    text = open_file(page, PATHS['e'])
    assert '2417' in text.replace(',', '') and not REASON.search(text)


# ---------------------------------------------------------------- real pipeline, futuramaapi (C21)

@pytest.fixture(scope='module')
def futurama_html(tmp_path_factory):
    directory = tmp_path_factory.mktemp('futurama-html')
    command = [sys.executable, '-c', 'from code_analyzer.cli import main; main()', str(fixture_root('futuramaapi').resolve()), '-l', 'python',
               '--granularity', 'file', '-o', str(directory / 'report.html'), '--bottlenecks', str(directory / 'b.json')]
    done = subprocess.run(command, cwd=REPO, env=dict(os.environ, PYTHONHASHSEED='0'), capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-2000:]
    return (directory / 'report.html').read_text(encoding='utf-8'), json.loads((directory / 'b.json').read_text(encoding='utf-8'))


def cycles_of(payload, member):
    return [c for c in payload['candidates'] if c['kind'] == 'dependency_cycle' and member in c['structure']['members']]


def test_V10_C21_futuramaapi_cycle_members_show_reason_and_label(open_report, futurama_html):
    html, payload = futurama_html
    certain = sorted((c for c in payload['candidates'] if c['kind'] == 'dependency_cycle' and c['structure']['tier'] == 'certain'),
                     key=lambda c: (-c['metrics']['member_count'], c['id']))
    big = max((c for c in payload['candidates'] if c['kind'] == 'dependency_cycle' and c['structure']['tier'] == 'all'),
              key=lambda c: c['metrics']['member_count'])
    assert certain and big['metrics']['member_count'] == 106
    members = list(certain[0]['structure']['members']) + [big['structure']['members'][0], big['structure']['members'][-1]]
    page = open_report(None, None, html=html, graph=False)
    labels = dashboard_labels(page, 'dependency_cycle')
    for member in members:
        path = member[len('file:'):]
        text = open_file(page, path, search=True)
        expected = {reason(c['metrics']['member_count'], c['structure']['tier']) for c in cycles_of(payload, member)}
        lines = [line for line in text.splitlines() if REASON.search(line)]
        assert len(lines) == len(expected) >= 1, (member, lines)
        for item in expected:
            assert any(item in line for line in lines), (member, item)
        assert any(label in text for label in labels)
        close(page)


def test_V10_C21_futuramaapi_file_outside_any_cycle_shows_no_cycle(open_report, futurama_html):
    html, payload = futurama_html
    in_cycle = {m for c in payload['candidates'] if c['kind'] == 'dependency_cycle' for m in c['structure']['members']}
    outside = sorted(i for i in payload['dependency_network']['node_metrics'] if i not in in_cycle and i.startswith('file:'))
    assert outside
    page = open_report(None, None, html=html, graph=False)
    text = open_file(page, outside[0][len('file:'):], search=True)
    assert not REASON.search(text)


# ---------------------------------------------------------------- XSS (C22, Q07)

HOSTILE = '<img src=x onerror=alert(1)>'


def hostile_report():
    from analysis import GraphAnalyzer, GraphAnalysisConfig
    from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
    from tests.edge_weights_support import edge
    from tests.file_analysis_support import converted, node, serialize
    paths = {'a': 'src/a.py', 'h': f'src/{HOSTILE}.py', 'c': 'src/c.py'}
    files = {path: 'x = 1\n' for path in paths.values()}
    nodes = [node(key, path) for key, path in paths.items()]
    snap, arch = converted(files, nodes, [edge('a', 'h'), edge('h', 'a')])
    weights = default_weights()
    analysis = GraphAnalyzer(GraphAnalysisConfig(edge_weights=weights)).analyze(arch.nodes, arch.edges, project_path=arch.project_path)
    arch.stats['analysis'] = copy.deepcopy(analysis)
    report = json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, weights, analysis=analysis)))
    return serialize(arch), report, paths


def test_V10_C22_hostile_cycle_member_path_is_text_and_inert(open_report):
    arch, bn, paths = hostile_report()
    cycles = [c for c in bn['candidates'] if c['kind'] == 'dependency_cycle']
    assert {c['structure']['tier'] for c in cycles} == set(TIERS) and all(file_id(paths['h']) in c['structure']['members'] for c in cycles)
    page = open_report(arch, bn, initial_script='window.__alerts = []; window.alert = (m) => window.__alerts.push(String(m));')
    dialogs = []
    page.on('dialog', lambda d: (dialogs.append(d.message), d.dismiss()))
    for key in ('h', 'a'):
        text = open_file(page, paths[key])
        assert reason(2, 'certain') in text and reason(2, 'all') in text
        if key == 'h':
            assert HOSTILE in text, 'hostile path must be displayed literally'
        close(page)
    goto_list(page)
    assert HOSTILE in page.locator('#node-list').inner_text()
    page.wait_for_timeout(300)
    assert dialogs == [] and page.evaluate('window.__alerts') == []
    assert page.locator('img, :not(script)[onerror]').count() == 0
    assert page.unhandled_errors == []
