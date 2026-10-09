import copy
import json
import re

import pytest
from playwright.sync_api import expect

from report.shared.document import ReportInputError
from bottlenecks import BottleneckInputError
from tests.candidate_policy_metadata_support import DEFAULT_TABLES
from tests.unified_support import HOSTILE, architecture, bottleneck_fixture, document, edge, node, open_disclosures, select, topology
from tests.file_analysis_browser_support import file_arch, file_node, symbol
from tests.unified_support import visible_records


def ambiguous(source='s', target='a', others=('b',), line=5):
    e = edge(source, target, resolution='ambiguous', line=line)
    e['candidates'] = list(others)
    e['weight'] = 87
    return e


def assert_visible_symbol_allocations(page, labels, contribution):
    for label in labels:
        line = page.locator('[data-relationship-row] > div').filter(has_text=re.compile(r'^' + re.escape(label) + r' · 배분 몫 0\.5 ·'))
        expect(line).to_be_visible()
        expect(line).to_have_text(f'{label} · 배분 몫 0.5 · 가중 기여도 {contribution}')


@pytest.mark.parametrize('mode', ['architecture-only', 'report-only', 'combined'])
def test_VO6_supported_payload_shapes(tmp_path, mode):
    arch = architecture([node('a')])
    report = bottleneck_fixture(tmp_path, arch['nodes'], candidate_count=0)
    html = document(None if mode == 'report-only' else arch, None if mode == 'architecture-only' else report)
    decoded = json.loads(re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert decoded['architecture'] == (None if mode == 'report-only' else arch)
    assert decoded['bottlenecks'] == (None if mode == 'architecture-only' else report)


@pytest.mark.parametrize('component,policy,combined', [
    ('architecture', None, False), ('architecture', 'old', False),
    ('report', None, False), ('report', 'old', False),
    ('architecture', None, True), ('architecture', 'old', True),
    ('report', None, True), ('report', 'old', True),
])
def test_VO6_generation_policy_rejections(tmp_path, component, policy, combined):
    arch = architecture([node('a')])
    report = bottleneck_fixture(tmp_path, arch['nodes'], candidate_count=0)
    section = arch['stats']['analysis'] if component == 'architecture' else report['dependency_network']
    if policy is None:
        section.pop('ambiguity_policy')
    else:
        section['ambiguity_policy'] = policy
    with pytest.raises(ReportInputError):
        document(arch if combined or component == 'architecture' else None, report if combined or component == 'report' else None)


def test_VO6_unknown_candidate_generation_rejected():
    arch = architecture([node('s'), node('a')], [ambiguous(others=('ghost',))])
    with pytest.raises(BottleneckInputError):
        document(arch)


@pytest.mark.parametrize('component,policy', [('architecture', None), ('architecture', 'old'), ('bottlenecks', None), ('bottlenecks', 'old')])
def test_VO6_injected_policy_loader_error(open_report, tmp_path, component, policy):
    arch = architecture([node('a')])
    report = bottleneck_fixture(tmp_path, arch['nodes'], candidate_count=0)
    html = document(arch, report)
    match = re.search(r'(<script[^>]*id="report-data"[^>]*>)(.*?)(</script>)', html, re.S)
    data = json.loads(match.group(2))
    section = data[component]['stats']['analysis'] if component == 'architecture' else data[component]['dependency_network']
    if policy is None:
        section.pop('ambiguity_policy')
    else:
        section['ambiguity_policy'] = policy
    html = html[:match.start(2)] + json.dumps(data) + html[match.end(2):]
    page = open_report(None, html=html)
    expect(page.locator('#report-status')).to_be_visible()
    assert page.locator('#report-status').inner_text().strip()
    assert page.locator('[data-node-row]').count() == 0
    assert page.evaluate('window.ReportGraph == null')


@pytest.mark.parametrize('selected', ['s', 'a', 'b'])
def test_VO5_symbol_source_and_every_alternative(open_report, selected):
    nodes = [node(i) for i in ['s', 'a', 'b']]
    nodes[1]['label'] = 'TARGET_ALPHA'
    nodes[2]['label'] = 'TARGET_BETA'
    arch = architecture(nodes, [ambiguous()])
    arch['stats']['analysis']['edge_weights'] = copy.deepcopy(DEFAULT_TABLES)
    page = open_report(arch)
    select(page, selected)
    edges = {(e['source'], e['target']) for e in topology(page)['edges']}
    assert edges == ({('s', 'a'), ('s', 'b')} if selected == 's' else {('s', selected)})
    assert_visible_symbol_allocations(page, ['TARGET_ALPHA', 'TARGET_BETA'], '0.15')
    open_disclosures(page.locator('#node-detail'))
    text = page.locator('#node-detail').inner_text()
    for literal in ['ambiguous', '87', 'TARGET_ALPHA', 'TARGET_BETA']:
        assert literal in text
    assert re.search(r'0\.5(?:0*)?\b', text)
    assert page.external_requests == [] and page.unhandled_errors == []


@pytest.mark.parametrize('selected', ['file:a.py', 'file:b.py', 'file:c.py'])
def test_VO5_file_source_every_alternative_original_group(open_report, selected):
    originals = [symbol('s', 'a.py'), symbol('a', 'b.py'), symbol('b', 'b.py'), symbol('c', 'c.py')]
    raw = ambiguous(others=('b', 'c'))
    arch = file_arch([file_node(p) for p in ['a.py', 'b.py', 'c.py']], originals, [raw])
    arch['edges'] = []
    arch['stats']['analysis']['edge_weights'] = copy.deepcopy(DEFAULT_TABLES)
    for target, share in [('file:b.py', 2/3), ('file:c.py', 1/3)]:
        e = copy.deepcopy(raw)
        e.update(from_id='file:a.py', to_id=target, candidates=[], metadata={'candidate_share': share, 'detail_edge_indices': [0], 'evidence_count': 1})
        arch['edges'].append(e)
    page = open_report(arch)
    select(page, selected)
    edges = {(e['source'], e['target']) for e in topology(page)['edges']}
    assert edges == ({('file:a.py', 'file:b.py'), ('file:a.py', 'file:c.py')} if selected == 'file:a.py' else {('file:a.py', selected)})
    expected_allocations = {'file:b.py': ('b.py', '0.66667', '0.2'), 'file:c.py': ('c.py', '0.33333', '0.1')}
    required_targets = expected_allocations if selected == 'file:a.py' else [selected]
    for target in required_targets:
        label, share, contribution = expected_allocations[target]
        line = page.locator('[data-relationship-row] > div').filter(has_text=re.compile(r'^' + re.escape(label) + r' · 파일 배분 몫'))
        expect(line).to_be_visible()
        expect(line).to_have_text(f'{label} · 파일 배분 몫 {share} · 가중 기여도 {contribution}')
    open_disclosures(page.locator('#node-detail'))
    text = page.locator('#node-detail').inner_text()
    for literal in ['ambiguous', '87', 'b', 'c']:
        assert literal in text
    assert page.external_requests == [] and page.unhandled_errors == []


def test_VO5_ambiguous_neighbor_limit_relation_pagination_and_hostile_text(open_report):
    nodes = [node('s', value=100)] + [node(f'n{i:02}') for i in range(51)]
    nodes[-1]['label'] = HOSTILE
    nodes[-1]['span']['file_path'] = HOSTILE
    edges = [ambiguous(target=f'n{i:02}', others=(f'n{(i+1)%51:02}',), line=i+5) for i in range(51)]
    page = open_report(architecture(nodes, edges))
    select(page, 's')
    assert len(topology(page)['nodes']) == 31
    assert page.locator('#graph-status').get_attribute('data-omitted') == '21'
    assert page.locator('[data-relationship-row]').count() == 50
    page.locator('#relationship-next').click()
    assert page.locator('[data-relationship-row]').count() == 1
    open_disclosures(page.locator('#node-detail'))
    expect(page.locator('#node-detail')).to_contain_text(HOSTILE)
    assert page.evaluate('window.attack') is None
    assert page.external_requests == [] and page.unhandled_errors == []


def test_VO5_architecture_only_custom_profile_share_and_max_neighbor_order(open_report):
    nodes = [node('s', value=100), node('a'), node('b'), node('z-low')] + [node(f'high{i:02}') for i in range(28)]
    nodes[1]['label'] = 'TARGET_ALPHA'
    nodes[2]['label'] = 'TARGET_BETA'
    relations = [ambiguous(), edge('s', 'a', confidence='static_inferred'), edge('s', 'z-low', confidence='static_inferred')]
    relations += [edge('s', f'high{i:02}') for i in range(28)]
    arch = architecture(nodes, relations)
    arch['stats']['analysis']['edge_weights'] = {'confidence': {'static_certain': 1, 'static_inferred': .2, 'framework_inferred': .3, 'dynamic_required': .3}, 'resolution': {'exact': 1, 'unique_name': 1, 'ambiguous': .6, 'unresolved': .3}}
    page = open_report(arch)
    select(page, 's')
    assert {n['id'] for n in topology(page)['nodes']} == {'s', 'a', 'b'} | {f'high{i:02}' for i in range(28)}
    assert page.locator('#graph-status').get_attribute('data-omitted') == '1'
    assert_visible_symbol_allocations(page, ['TARGET_ALPHA', 'TARGET_BETA'], '0.3')
    open_disclosures(page.locator('#relationship-list'))
    text = page.locator('#relationship-list').inner_text()
    assert re.search(r'0\.3(?:0*)?\b', text)
    assert '87' in text


@pytest.mark.parametrize('selected', ['s', 'a', 'b', 'outside'])
def test_VO5_file_original_same_file_symbols_and_boundary(open_report, selected):
    originals = [symbol('s', 'a.py'), symbol('a', 'b.py'), symbol('b', 'b.py')]
    boundary = node('outside', 'unknown')
    boundary.update(label='BOUNDARY_TARGET', kind='external', group='external', category='external', span=None)
    originals.append(copy.deepcopy(boundary))
    relation = ambiguous(others=('b', 'outside'))
    arch = file_arch([file_node('a.py'), file_node('b.py')], originals, [relation])
    arch['nodes'].append(boundary)
    arch['stats']['analysis']['node_metrics']['outside'] = copy.deepcopy(boundary['metadata']['analysis'])
    arch['edges'] = []
    for target, share in [('file:b.py', 2/3), ('outside', 1/3)]:
        e = copy.deepcopy(relation)
        e.update(from_id='file:a.py', to_id=target, candidates=[], metadata={'candidate_share': share, 'detail_edge_indices': [0], 'evidence_count': 1})
        arch['edges'].append(e)
    page = open_report(arch)
    select(page, 'file:a.py' if selected == 's' else 'file:b.py' if selected in {'a', 'b'} else 'file:a.py')
    if selected == 'outside':
        page.evaluate("ReportGraph.getElementById('outside').emit('tap')")
    else:
        select(page, selected)
    assert page.locator('#node-detail').get_attribute('data-selected-node') == selected
    observed = {(e['source'], e['target']) for e in topology(page)['edges']}
    if selected == 's':
        assert observed == {('s', 'file:b.py'), ('s', 'outside')}
    elif selected in {'a', 'b'}:
        assert ('file:a.py', selected) in observed
    else:
        assert ('file:a.py', 'outside') in observed
    open_disclosures(page.locator('#relationship-list'))
    text = page.locator('#relationship-list').inner_text()
    assert 'ambiguous' in text and '87' in text and 'BOUNDARY_TARGET' in text
    assert 'a' in text and 'b' in text
    assert page.external_requests == [] and page.unhandled_errors == []


def test_VO5_report_only_HTML_resolves_original_group_order_duplicates_safely(open_report, tmp_path):
    nodes = [node(ident) for ident in ['s', 'a', 'b']]
    original = ambiguous(others=('b', 'a', 'b'))
    original['evidence']['file_path'] = HOSTILE
    original['metadata'] = {'original_marker': 'RAW_EVIDENCE_ORACLE'}
    expected = dict(copy.deepcopy(original), path=HOSTILE, start_line=5, end_line=7)
    stored = copy.deepcopy(expected)
    stored.pop('candidates')
    stored['candidate_group_id'] = 'group:original-order'
    report = bottleneck_fixture(tmp_path, nodes, [original], candidate_count=0)
    report['dependency_network']['edge_count'] = 2
    report['dependency_network']['candidate_groups'] = {'group:original-order': {'to_id': 'a', 'candidates': ['b', 'a', 'b']}}
    report['candidates'] = [{'id': 'b:0000000000000001', 'kind': 'evidence_spread', 'target': 'a', 'metrics': {'file_count': 2, 'line_span': 0, 'line_threshold': 2000}, 'evidence': [stored, {'path': 'second.py', 'start_line': 1, 'end_line': 1}], 'coverage': 'static_analyzer_relation', 'status': 'static_candidate'}]
    page = open_report(None, report)
    select(page, 'a')
    detail = page.locator('#node-detail')
    records = visible_records(detail, '후보의 전체 기록')
    assert len(records) == 1
    recovered = records[0]['evidence'][0]
    for field, value in expected.items():
        assert recovered[field] == value
    assert recovered['candidates'] == ['b', 'a', 'b']
    assert records[0]['evidence'][1] == {'path': 'second.py', 'start_line': 1, 'end_line': 1}
    expect(detail).to_contain_text('RAW_EVIDENCE_ORACLE')
    expect(detail).to_contain_text(HOSTILE)
    assert page.evaluate('window.ReportGraph') is None
    assert page.evaluate('window.attack') is None
    assert page.external_requests == [] and page.unhandled_errors == []


@pytest.mark.parametrize('view', ['file-source', 'symbol-source'])
def test_VO5_same_original_file_sum_selects_target_at_neighbor_cutoff(open_report, view):
    high_paths = [f'high{i:02}.py' for i in range(28)]
    paths = ['a.py', 'b.py', 'c.py', 'middle0.py', 'middle1.py', *high_paths]
    originals = [symbol('s', 'a.py'), symbol('a', 'b.py'), symbol('b', 'b.py'), symbol('c', 'c.py')]
    originals += [symbol(f'middle{i}', f'middle{i}.py') for i in range(2)]
    originals += [symbol(f'high{i:02}', path) for i, path in enumerate(high_paths)]
    relations = [ambiguous(others=('b', 'c'))]
    relations += [edge('s', f'high{i:02}') for i in range(28)]
    relations += [edge('s', f'middle{i}', confidence='framework_inferred') for i in range(2)]
    arch = file_arch([file_node(path) for path in paths], originals, relations)
    arch['stats']['analysis']['edge_weights'] = copy.deepcopy(DEFAULT_TABLES)
    arch['stats']['analysis']['edge_weights']['confidence']['framework_inferred'] = .15
    arch['edges'] = []
    for target, share in [('file:b.py', 2/3), ('file:c.py', 1/3)]:
        relation = copy.deepcopy(relations[0])
        relation.update(from_id='file:a.py', to_id=target, candidates=[], metadata={'candidate_share': share, 'detail_edge_indices': [0], 'evidence_count': 1})
        arch['edges'].append(relation)
    for ordinal, relation in enumerate(relations[1:], 1):
        aggregate = copy.deepcopy(relation)
        aggregate.update(from_id='file:a.py', to_id=arch['details']['node_files'][relation['to_id']], candidates=[], metadata={'candidate_share': 1, 'detail_edge_indices': [ordinal], 'evidence_count': 1})
        arch['edges'].append(aggregate)
    page = open_report(arch)
    select(page, 'file:a.py')
    if view == 'symbol-source':
        select(page, 's')
    neighbors = {entry['id'] for entry in topology(page)['nodes']}
    assert 'file:b.py' in neighbors
    assert 'file:c.py' not in neighbors
    assert {f'file:{path}' for path in high_paths} <= neighbors
    assert page.locator('#graph-status').get_attribute('data-shown') == '30'
    if view == 'file-source':
        assert neighbors == {'file:a.py', 'file:b.py', 'file:middle0.py'} | {f'file:{path}' for path in high_paths}
    for label, share, contribution in [('b.py', '0.66667', '0.2'), ('c.py', '0.33333', '0.1')]:
        line = page.locator('[data-relationship-row] > div').filter(has_text=re.compile(r'^' + re.escape(label) + r' · 파일 배분 몫'))
        expect(line).to_be_visible()
        expect(line).to_have_text(f'{label} · 파일 배분 몫 {share} · 가중 기여도 {contribution}')
    assert page.external_requests == [] and page.unhandled_errors == []
