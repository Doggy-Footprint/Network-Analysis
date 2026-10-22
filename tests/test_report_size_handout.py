"""Spec ee17484a52af182c v1: V04 (handout content) and the F10 CLI file.

Real-pipeline inputs (the fixture project) check F11/F12 structure; hand-built v9 reports (a deep copy of the real
report with replaced candidates, details edges, rankings and packages) give each boundary an exactly known expectation.
Section texts are located by their headings; the wording inside an item is not pinned beyond the tokens F12 names."""
import copy
import json
import re

import pytest

from bottlenecks.handout import render_handout
from language_analyzers.core.serialization import architecture_to_dict
from tests.report_size_support import cli_fixture_run, fixture_architecture_dict, fixture_payload, golden, of_kind, to_payload

V8 = golden('v8_bottlenecks.json')
H2 = ['## How to read', '## Candidate counts', '## Production rankings', '## Packages', '## Candidates']
ARROW = ' → '
MORE = '… {n} more {kind} candidates in bottlenecks.json'


def headings(text, level):
    return [line.rstrip() for line in text.splitlines() if re.match(rf'#{{{level}}} ', line)]


def section(text, title):
    """Body between a heading line and the next heading of the same or a shallower level."""
    level = len(title.split(' ')[0])
    lines, body, inside = text.splitlines(), [], False
    for line in lines:
        if inside and re.match(rf'#{{1,{level}}} ', line):
            break
        if inside:
            body.append(line)
        if line.rstrip() == title:
            inside = True
    assert inside, f'missing heading {title!r}'
    return '\n'.join(body)


def plain(text):
    """Inline-code backticks are presentation; F12 tokens are compared without them."""
    return text.replace('`', '')


def has_token(block, value):
    return re.search(r'(?<![\w.:/])' + re.escape(str(value)) + r'(?![\w])', block) is not None


def candidate_blocks(body, ids):
    """Text of each candidate item: from its id to the next candidate id (or the end of the section)."""
    positions = sorted((body.index(ident), ident) for ident in ids if ident in body)
    blocks = {}
    for i, (start, ident) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(body)
        blocks[ident] = body[start:end]
    return blocks


@pytest.fixture(scope='module')
def real():
    return fixture_payload(), fixture_architecture_dict()


@pytest.fixture(scope='module')
def real_text(real):
    return render_handout(*real)


def test_V04_C03_title_and_sections_in_the_f11_order(real, real_text):
    report, arch = real
    assert real_text.splitlines()[0] == '# Dependency bottleneck handout'
    assert headings(real_text, 1) == ['# Dependency bottleneck handout']
    assert headings(real_text, 2) == H2
    positions = [real_text.index(h + '\n') for h in H2]
    assert positions == sorted(positions)
    header = real_text.split('\n## ')[0]
    assert arch['project_name'] in header
    assert has_token(header, report['snapshot']['file_count']) and has_token(header, report['dependency_network']['edge_count'])


def test_V04_C03_how_to_read_explains_the_terms_and_the_files(real_text):
    body = section(real_text, '## How to read').lower()
    for word in ('relation', 'confidence', 'resolution', 'weight', 'tier', 'bottlenecks.json', 'details', 'evidence'):
        assert word in body, word


def test_V04_C03_candidate_counts_table_lists_each_present_kind_with_its_count(real, real_text):
    body = section(real_text, '## Candidate counts')
    kinds = sorted({item['kind'] for item in V8['candidates']})
    for kind in kinds:
        count = len(of_kind(V8['candidates'], kind))
        line = next((line for line in body.splitlines() if kind in line), None)
        assert line is not None and has_token(line, count), (kind, body)
    for kind in {'large_node', 'unresolved_boundary', 'isolated_node', 'rule_violation'} - set(kinds):
        assert kind not in body


def test_V04_C03_candidates_section_has_one_subsection_per_present_kind_with_all_ids_and_metrics(real, real_text):
    report, _ = real
    body = section(real_text, '## Candidates')
    kinds = sorted({item['kind'] for item in report['candidates']})
    assert set(headings(body, 3)) == {f'### {kind}' for kind in kinds}
    for kind in kinds:
        text = section(real_text, f'### {kind}')
        items = of_kind(report['candidates'], kind)
        assert len(items) <= 10
        for item in items:
            assert item['id'] in text and item['target'] in text
            block = candidate_blocks(text, [i['id'] for i in items])[item['id']]
            for key in item['metrics']:
                assert key in block, (item['id'], key)


def test_V04_C03_evidence_spread_items_show_the_edge_and_its_location(real, real_text):
    text = section(real_text, '### evidence_spread')
    for candidate in of_kind(V8['candidates'], 'evidence_spread'):
        block = candidate_blocks(text, [c['id'] for c in of_kind(V8['candidates'], 'evidence_spread')])[candidate['id']]
        block = plain(block)
        shown = [r for r in candidate['evidence'] if f"{r['from_id']}{ARROW}{r['to_id']}" in block]
        assert 1 <= len(shown) <= 3
        for record in shown:
            assert f"{record['path']}:{record['start_line']}" in block and record['relation'] in block


def test_V04_C03_cycle_and_unstable_items_show_structure_and_the_first_file_pair(real, real_text):
    report, _ = real
    for kind in ('dependency_cycle', 'unstable_dependency'):
        text = section(real_text, f'### {kind}')
        blocks = candidate_blocks(text, [c['id'] for c in of_kind(report['candidates'], kind)])
        for item in of_kind(V8['candidates'], kind):
            block = blocks[item['id']]
            assert item['structure'].get('scheme', '') in block and item['structure']['tier'] in block
            first = item['evidence'][0]
            assert first['from_id'].removeprefix('file:') in block and first['to_id'].removeprefix('file:') in block
            assert has_token(block, len(item['evidence']))


def test_V04_C03_cli_handout_equals_render_handout_of_the_cli_outputs(tmp_path):
    directory = cli_fixture_run(tmp_path)
    report = json.loads((directory / 'bn' / 'b.json').read_text(encoding='utf-8'))
    arch = json.loads((directory / 'report.json').read_text(encoding='utf-8'))
    arch['details'] = json.loads((directory / 'report.details.json').read_text(encoding='utf-8'))
    arch.pop('details_file')
    written = (directory / 'bn' / 'b.handout.md').read_text(encoding='utf-8')
    assert written == render_handout(report, arch)
    assert written.startswith('# Dependency bottleneck handout')


SPREAD_EDGES = 12


def fid_name(i):
    return f'fa{i:02d}.py'


def synthetic_inputs(candidates, *, edges=SPREAD_EDGES, files=30):
    report, arch = copy.deepcopy(fixture_payload()), copy.deepcopy(fixture_architecture_dict())
    ids = [f'file:{fid_name(i)}' for i in range(files)]
    template = next(iter(report['dependency_network']['node_metrics'].values()))
    report['dependency_network']['node_metrics'] = {ident: dict(template) for ident in ids}
    report['dependency_network']['file_ids'] = sorted(ids)
    report['dependency_network']['node_count'] = files
    report['candidates'] = candidates
    sample = arch['details']['edges'][0]
    detail_edges = []
    for k in range(edges):
        edge = copy.deepcopy(sample)
        edge.update(from_id=f'py:sp{k:02d}a', to_id=f'py:sp{k:02d}b', relation='CALLS')
        edge['evidence'] = {'file_path': f'sp/e{k:02d}.py', 'start_line': 1000 + k, 'end_line': 1000 + k, 'start_col': 0, 'end_col': 0}
        detail_edges.append(edge)
    arch['details']['edges'] = detail_edges
    return report, arch


def edge_token(k):
    return f'sp/e{k:02d}.py:{1000 + k}'


def file_row(a, b, count=1):
    return [a, b, ['IMPORTS'], 1.0, count, 'certain']


def make(kind, n, rank=0, tied=False, evidence=None, metrics=None, tier=None):
    item = _make(kind, n, rank, tied, evidence)
    if metrics:
        item['metrics'] = {**item['metrics'], **metrics}
    if tier is not None:
        item['structure']['tier'] = tier
    return item


def _make(kind, n, rank=0, tied=False, evidence=None):
    """Candidate n (id order = n). rank 0 is first by the D09 rule unless tied (all primary keys equal)."""
    r = 0 if tied else rank
    ident = f'b:{n:016x}'
    common = {'id': ident, 'kind': kind, 'target': f'file:{fid_name(n % 30)}', 'coverage': 'static_analyzer_relation', 'status': 'static_candidate'}
    if kind == 'evidence_spread':
        return {**common, 'metrics': {'file_count': 7, 'directory_count': 20 - r, 'line_span': 0, 'line_threshold': 2000},
                'evidence': evidence if evidence is not None else [0, 1]}
    if kind in ('dependency_cycle', 'package_cycle'):
        members = [f'file:{fid_name(i)}' for i in range(2)] if kind == 'dependency_cycle' else ['pkg:python:a', 'pkg:python:b']
        rows = evidence if evidence is not None else ([file_row(0, 1)] if kind == 'dependency_cycle' else
                                                      [['pkg:python:a', 'pkg:python:b', ['IMPORTS'], 1.0, 1, 'certain', [[0, 1]]]])
        return {**common, 'metrics': {'member_count': 30 - r, 'internal_pair_count': 1, 'internal_evidence_count': 1, 'min_pair_weight': 1.0},
                'evidence': rows, 'structure': {'scheme': 'file' if kind == 'dependency_cycle' else 'language', 'tier': 'certain', 'members': members,
                                                'parent_id': None, 'cut_candidates': []}}
    if kind == 'unstable_dependency':
        return {**common, 'metrics': {'instability_from': 0.25, 'instability_to': 0.5, 'instability_delta': 0.25, 'evidence_count': 50 - r,
                                      'file_pair_count': 1},
                'evidence': evidence if evidence is not None else [file_row(0, 1)],
                'structure': {'scheme': 'language', 'tier': 'certain', 'from_package': 'pkg:python:a', 'to_package': 'pkg:python:b'}}
    path = {'path': f'big{n % 100:02d}.py', 'start_line': 1, 'end_line': 3000}
    if kind == 'large_node':
        return {**common, 'metrics': {'line_count': 3000, 'line_threshold': 2000, 'token_count': 5000 - 10 * r, 'token_threshold': 24000}, 'evidence': path}
    if kind == 'unresolved_boundary':
        return {**common, 'metrics': {'unresolved_count': 40 - r}, 'evidence': path}
    if kind == 'isolated_node':
        return {**common, 'metrics': {'line_count': 90 - r, 'framework_edge_count': 0, 'dynamic_edge_count': 0, 'uncertain_static_edge_count': 0},
                'evidence': {'path': path['path'], 'edges': []}}
    if kind == 'untested_hub':
        return {**common, 'metrics': {'pagerank': 0.5, 'pagerank_rank': r + 1, 'top_n': 20, 'uncertain_test_edge_count': 0},
                'evidence': {'path': path['path'], 'uncertain_test_edges': []}}
    assert kind == 'rule_violation'
    return {**common, 'metrics': {'evidence_count': 60 - r, 'max_weight': 1.0},
            'evidence': [{'from_id': 'file:fa00.py', 'to_id': 'file:fa01.py', 'relations': ['IMPORTS'], 'max_weight': 1.0, 'evidence_count': 1,
                          'detail_edge_indices': [0], 'tier': 'all'}],
            'structure': {'rule_type': 'forbid', 'from_layer': 'a', 'to_layer': 'b', 'tier': 'all', 'relations': ['IMPORTS']}}


SORTED_KINDS = ['evidence_spread', 'dependency_cycle', 'package_cycle', 'unstable_dependency', 'large_node', 'unresolved_boundary',
                'isolated_node', 'untested_hub', 'rule_violation']


def descending_id_candidates(kind, count, tied=False):
    """Ids run opposite to the D09 order (id 100 holds rank 0), so ignoring the primary key shows up as a wrong selection."""
    return [make(kind, 100 - rank, rank=rank, tied=tied) for rank in range(count)]


@pytest.mark.parametrize('kind', SORTED_KINDS)
@pytest.mark.parametrize('count', [10, 11])
def test_V04_C04_top_ten_per_kind_and_more_line_at_the_boundary(kind, count):
    candidates = descending_id_candidates(kind, count)
    text = render_handout(*synthetic_inputs(candidates))
    body = section(text, f'### {kind}')
    shown = [c['id'] for c in candidates[:10]]
    assert all(ident in body for ident in shown)
    assert [body.index(ident) for ident in shown] == sorted(body.index(ident) for ident in shown)
    if count == 10:
        assert 'more' not in body
    else:
        assert candidates[10]['id'] not in text
        assert MORE.format(n=1, kind=kind) in body.splitlines()
    assert has_token(section(text, '## Candidate counts'), count)


@pytest.mark.parametrize('kind', SORTED_KINDS)
def test_V04_C04_ties_on_the_primary_key_break_by_id_ascending(kind):
    candidates = [make(kind, 100 - i, tied=True) for i in range(11)]
    text = render_handout(*synthetic_inputs(candidates))
    smallest = sorted(c['id'] for c in candidates)
    assert all(ident in text for ident in smallest[:10]) and smallest[10] not in text
    body = section(text, f'### {kind}')
    assert [body.index(ident) for ident in smallest[:10]] == sorted(body.index(ident) for ident in smallest[:10])


def test_V04_C04_more_line_counts_the_remainder_for_a_larger_overflow():
    candidates = descending_id_candidates('large_node', 14)
    text = render_handout(*synthetic_inputs(candidates))
    assert MORE.format(n=4, kind='large_node') in section(text, '### large_node').splitlines()
    assert all(c['id'] not in text for c in candidates[10:])


def test_V04_C04_other_kinds_keep_their_own_limit():
    candidates = descending_id_candidates('large_node', 11) + descending_id_candidates('untested_hub', 3)
    text = render_handout(*synthetic_inputs(candidates))
    assert 'more' in section(text, '### large_node') and 'more' not in section(text, '### untested_hub')


def spread_candidates(sizes, offset=0):
    """candidate i owns `size` consecutive detail edges; every edge token is unique."""
    result, cursor = [], 0
    for i, size in enumerate(sizes):
        result.append(make('evidence_spread', i + 1, rank=i, evidence=list(range(cursor, cursor + size))))
        cursor += size
    return result


@pytest.mark.parametrize('size,shown', [(1, 1), (3, 3), (4, 3)], ids=['1-evidence', '3-evidence', '4-evidence'])
def test_V04_C05_evidence_spread_representatives_are_at_most_three(size, shown):
    candidate = make('evidence_spread', 1, evidence=list(range(size)))
    text = render_handout(*synthetic_inputs([candidate]))
    body = plain(section(text, '### evidence_spread'))
    assert [k for k in range(SPREAD_EDGES) if edge_token(k) in body] == list(range(shown))
    assert has_token(body, size)
    for k in range(shown):
        assert f'py:sp{k:02d}a{ARROW}py:sp{k:02d}b' in body and 'CALLS' in body


def test_V04_C05_each_candidate_counts_only_its_own_evidence():
    candidates = spread_candidates([1, 3, 4])
    text = render_handout(*synthetic_inputs(candidates))
    blocks = {k: plain(v) for k, v in candidate_blocks(section(text, '### evidence_spread'), [c['id'] for c in candidates]).items()}
    owned = {candidates[0]['id']: range(0, 1), candidates[1]['id']: range(1, 4), candidates[2]['id']: range(4, 8)}
    for ident, indices in owned.items():
        tokens = [k for k in range(SPREAD_EDGES) if edge_token(k) in blocks[ident]]
        assert tokens == list(indices)[:3], ident
        assert has_token(blocks[ident], len(indices))


@pytest.mark.parametrize('kind', ['dependency_cycle', 'unstable_dependency'])
@pytest.mark.parametrize('size,shown', [(1, 1), (3, 3), (4, 3)], ids=['1-evidence', '3-evidence', '4-evidence'])
def test_V04_C05_file_pair_representatives_are_at_most_three(kind, size, shown):
    rows = [file_row(2 * k + 2, 2 * k + 3, count=1) for k in range(size)]
    text = render_handout(*synthetic_inputs([make(kind, 1, evidence=rows)]))
    body = section(text, f'### {kind}')
    present = [k for k in range(size) if fid_name(2 * k + 2) in body and fid_name(2 * k + 3) in body]
    assert present == list(range(shown))
    assert has_token(body, size) and 'IMPORTS' in body
    absent_start = [k for k in range(size, 8) if fid_name(2 * k + 2) in body]
    assert absent_start == []


@pytest.mark.parametrize('size,shown', [(1, 1), (3, 3), (4, 3)], ids=['1-evidence', '3-evidence', '4-evidence'])
def test_V04_C05_D16_package_cycle_representatives_are_the_first_three_package_id_pairs(size, shown):
    rows = [[f'pkg:python:pa{k:02d}', f'pkg:python:pb{k:02d}', ['IMPORTS'], 1.0, 1, 'certain', [[0, 1]]] for k in range(size)]
    text = render_handout(*synthetic_inputs([make('package_cycle', 1, evidence=rows)]))
    body = plain(section(text, '### package_cycle'))
    present = [k for k in range(8) if f'pkg:python:pa{k:02d}' in body and f'pkg:python:pb{k:02d}' in body]
    assert present == list(range(shown))
    assert all(f'pkg:python:pa{k:02d}{ARROW}pkg:python:pb{k:02d}' in body for k in range(shown))
    assert has_token(body, size) and 'IMPORTS' in body


def test_V04_C03_structure_line_shows_scheme_tier_members_and_the_top_five_cut_candidates():
    cuts = [{'from_id': f'file:fa{2 * i + 10:02d}.py', 'to_id': f'file:fa{2 * i + 11:02d}.py', 'relations': ['IMPORTS'], 'max_weight': 0.5 + i / 100,
             'evidence_count': 1} for i in range(7)]
    candidate = make('dependency_cycle', 1)
    candidate['structure'].update(members=[f'file:{fid_name(i)}' for i in range(6)], cut_candidates=cuts)
    candidate['metrics']['member_count'] = 6
    text = render_handout(*synthetic_inputs([candidate]))
    body = section(text, '### dependency_cycle')
    assert 'file' in body and 'certain' in body and has_token(body, 6)
    for i in range(5):
        assert fid_name(2 * i + 10) in body and fid_name(2 * i + 11) in body
    for i in (5, 6):
        assert fid_name(2 * i + 10) not in body and fid_name(2 * i + 11) not in body
    for key in candidate['metrics']:
        assert key in body


def test_V04_C03_production_rankings_show_the_top_ten_per_key():
    report, arch = synthetic_inputs([make('large_node', 1)])
    keys = sorted(report['dependency_network']['rankings_by_category']['production'])
    report['dependency_network']['rankings_by_category']['production'] = {
        key: [{'node_id': f'file:{fid_name(i)}', 'value': 100 - i} for i in range(12)] for key in keys}
    body = section(render_handout(report, arch), '## Production rankings')
    for key in keys:
        assert key in body
    for i in range(10):
        assert fid_name(i) in body
    assert fid_name(10) not in body and fid_name(11) not in body


def test_V04_C03_packages_show_the_ten_most_unstable_per_scheme_with_counts():
    report, arch = synthetic_inputs([make('large_node', 1)])
    metrics = {f'pkg:python:p{i:02d}': {'file_count': 100 + i, 'ca': 200 + i, 'ce': 300 + i, 'instability': round(1 - i / 20, 4),
                                        'weighted_ca': 1.0, 'weighted_ce': 1.0, 'weighted_instability': round(1 - i / 20, 4)} for i in range(12)}
    report['dependency_network']['package_metrics'] = {'language': metrics}
    body = section(render_handout(report, arch), '## Packages')
    assert 'language' in body
    for i in range(10):
        line = next(line for line in body.splitlines() if f'p{i:02d}' in line)
        assert all(has_token(line, value) for value in (100 + i, 200 + i, 300 + i)), line
    assert 'p10' not in body and 'p11' not in body


def empty_graph_report():
    from tests.file_analysis_support import converted
    snap, arch = converted({'README.md': 'document'}, [], [])
    return to_payload(snap, arch), json.loads(json.dumps(architecture_to_dict(arch)))


def test_V04_C07_no_candidates_keeps_v9_and_the_candidates_heading_with_no_candidates_line():
    report, arch = empty_graph_report()
    assert report['schema'] == 'bottlenecks.v9' and report['candidates'] == []
    assert report['dependency_network']['file_ids'] == []
    assert report['dependency_network']['evidence_columns']['file_pair'][0] == 'from'
    text = render_handout(report, arch)
    assert headings(text, 2) == H2
    assert 'No candidates.' in section(text, '## Candidates')
    assert headings(section(text, '## Candidates'), 3) == []


def cycle_free_inputs():
    from tests.edge_weights_support import edge
    from tests.file_analysis_support import converted, node
    files = {'a.py': 'x = 1\n', 'b.py': 'x = 1\n'}
    snap, arch = converted(files, [node('a', 'a.py'), node('b', 'b.py')], [edge('a', 'b')])
    return to_payload(snap, arch), json.loads(json.dumps(architecture_to_dict(arch)))


def test_V04_C08_cycle_free_repository_has_no_cycle_kind_in_the_counts_table():
    report, arch = cycle_free_inputs()
    assert report['schema'] == 'bottlenecks.v9'
    assert not {c['kind'] for c in report['candidates']} & {'dependency_cycle', 'package_cycle'}
    body = section(render_handout(report, arch), '## Candidate counts')
    assert 'dependency_cycle' not in body and 'package_cycle' not in body


def test_V04_C08_zero_count_kinds_are_omitted_from_the_counts_table():
    report, arch = synthetic_inputs([make('large_node', 1), make('untested_hub', 2)])
    body = section(render_handout(report, arch), '## Candidate counts')
    assert 'large_node' in body and 'untested_hub' in body
    for kind in set(SORTED_KINDS) - {'large_node', 'untested_hub'}:
        assert kind not in body
    assert set(headings(section(render_handout(report, arch), '## Candidates'), 3)) == {'### large_node', '### untested_hub'}


def test_V04_D13_header_counts_come_from_snapshot_file_count_and_network_edge_count():
    report, arch = synthetic_inputs([make('large_node', 1)])
    report['snapshot']['file_count'] = 777
    report['dependency_network']['edge_count'] = 888
    header = render_handout(report, arch).split('\n## ')[0]
    assert has_token(header, 777) and has_token(header, 888)
    assert not has_token(header, 30)


def test_V04_D14_evidence_count_of_dict_evidence_is_the_length_of_its_edge_list():
    hub = make('untested_hub', 1)
    hub['evidence']['uncertain_test_edges'] = [{'from_id': f'file:fa0{i}.py', 'to_id': 'file:fa09.py'} for i in range(3)]
    isolated = make('isolated_node', 2)
    isolated['evidence']['edges'] = [{'from_id': f'file:fa1{i}.py', 'to_id': 'file:fa19.py'} for i in range(5)]
    hub_empty = make('untested_hub', 3, rank=1)
    large = make('large_node', 4)
    text = render_handout(*synthetic_inputs([hub, hub_empty, isolated, large]))
    hub_block = candidate_blocks(section(text, '### untested_hub'), [hub['id'], hub_empty['id']])
    assert has_token(hub_block[hub['id']], 3)
    assert has_token(candidate_blocks(section(text, '### isolated_node'), [isolated['id']])[isolated['id']], 5)
    assert has_token(hub_block[hub_empty['id']], 1)
    assert has_token(section(text, '### large_node'), 1)


TIER_ORDER = {'all': 0, 'resolved': 1, 'certain': 2}


def ordered_ids(body, ids):
    return sorted((i for i in ids if i in body), key=body.index)


def assert_selection(kind, candidates, expected_order):
    text = render_handout(*synthetic_inputs(candidates))
    body = section(text, f'### {kind}')
    shown = ordered_ids(body, [c['id'] for c in candidates])
    assert shown == expected_order[:10]
    for c in candidates:
        if c['id'] not in expected_order[:10]:
            assert c['id'] not in text
    assert MORE.format(n=len(candidates) - 10, kind=kind) in body.splitlines()


def test_V04_D09_evidence_spread_ties_on_directory_count_break_by_file_count_desc():
    candidates = [make('evidence_spread', 100 - r, metrics={'directory_count': 9, 'file_count': 50 - r}) for r in range(11)]
    assert_selection('evidence_spread', candidates, [c['id'] for c in candidates])


def test_V04_D09_unstable_dependency_ties_on_evidence_count_break_by_instability_delta_desc():
    candidates = [make('unstable_dependency', 100 - r, metrics={'evidence_count': 7, 'instability_delta': 0.75 - r * 0.0625}) for r in range(11)]
    assert_selection('unstable_dependency', candidates, [c['id'] for c in candidates])


@pytest.mark.parametrize('kind', ['dependency_cycle', 'package_cycle'])
def test_V04_D09_cycle_ties_on_member_count_break_by_tier_all_resolved_certain_then_id(kind):
    tiers = ['certain', 'resolved', 'all'] * 4
    candidates = [make(kind, 90 - 3 * i, metrics={'member_count': 5}, tier=tiers[i]) for i in range(11)]
    expected = [c['id'] for c in sorted(candidates, key=lambda c: (TIER_ORDER[c['structure']['tier']], c['id']))]
    assert_selection(kind, candidates, expected)


@pytest.mark.parametrize('kind', ['dependency_cycle', 'package_cycle'])
def test_V04_D09_member_count_still_outranks_tier(kind):
    candidates = [make(kind, 50 + i, metrics={'member_count': 5 + i}, tier='all' if i < 5 else 'certain') for i in range(11)]
    expected = [c['id'] for c in sorted(candidates, key=lambda c: -c['metrics']['member_count'])]
    assert_selection(kind, candidates, expected)


def unique_metrics(item, n):
    return {key: 1000 * n + index + 1 for index, key in enumerate(item['metrics'])}


@pytest.mark.parametrize('kind', SORTED_KINDS)
def test_V04_F12_every_metric_value_appears_in_its_own_item_only(kind):
    candidates = [make(kind, n, rank=n) for n in range(1, 4)]
    for n, c in enumerate(candidates, 1):
        c['metrics'] = unique_metrics(c, n)
    text = render_handout(*synthetic_inputs(candidates))
    blocks = candidate_blocks(section(text, f'### {kind}'), [c['id'] for c in candidates])
    assert len(blocks) == 3
    for c in candidates:
        block = plain(blocks[c['id']])
        for key, value in c['metrics'].items():
            assert f'{key}={value}' in block, (c['id'], key)
        for other in candidates:
            if other is not c:
                assert not any(f'={value}' in block for value in other['metrics'].values()), (c['id'], other['id'])


@pytest.mark.parametrize('kind', ['dependency_cycle', 'package_cycle'])
def test_V04_F12_structure_scheme_tier_and_member_count_come_from_structure(kind):
    first = make(kind, 1, rank=0, tier='resolved', metrics={'member_count': 41})
    second = make(kind, 2, rank=1, tier='certain', metrics={'member_count': 42})
    first['structure']['members'] = [f'file:{fid_name(i)}' for i in range(6)]
    second['structure']['members'] = [f'file:{fid_name(i)}' for i in range(7)]
    for item in (first, second):
        for row in item['evidence']:
            row[5] = item['structure']['tier']
    text = render_handout(*synthetic_inputs([first, second]))
    blocks = {k: plain(v) for k, v in candidate_blocks(section(text, f'### {kind}'), [first['id'], second['id']]).items()}
    scheme = first['structure']['scheme']
    for item, count, other in ((first, 6, 'certain'), (second, 7, 'resolved')):
        block = blocks[item['id']]
        assert scheme in block and item['structure']['tier'] in block and other not in block
        assert has_token(block, count)
    assert not has_token(blocks[first['id']], 7) and not has_token(blocks[second['id']], 6)


def test_V04_F12_cut_candidates_show_pair_relations_and_weight_for_the_top_five_only():
    cuts = [{'from_id': f'file:{fid_name(10 + 2 * i)}', 'to_id': f'file:{fid_name(11 + 2 * i)}', 'relations': [f'REL_{i}'],
             'max_weight': [0.11, 0.22, 0.33, 0.44, 0.55, 0.66, 0.77][i], 'evidence_count': 1} for i in range(7)]
    candidate = make('dependency_cycle', 1)
    candidate['structure']['cut_candidates'] = cuts
    body = plain(section(render_handout(*synthetic_inputs([candidate])), '### dependency_cycle'))
    lines = body.splitlines()
    for i in range(5):
        line = next(line for line in lines if fid_name(10 + 2 * i) in line)
        assert fid_name(11 + 2 * i) in line and f'REL_{i}' in line and str(cuts[i]['max_weight']) in line, line
    for i in (5, 6):
        assert f'REL_{i}' not in body and fid_name(10 + 2 * i) not in body and str(cuts[i]['max_weight']) not in body


def test_V04_F11_production_rankings_follow_ranking_order_and_cut_at_ten():
    report, arch = synthetic_inputs([make('large_node', 1)])
    keys = sorted(report['dependency_network']['rankings_by_category']['production'])
    orders = {}
    ranking = {}
    for k, key in enumerate(keys):
        order = [(i * 7 + k * 3) % 12 for i in range(12)]
        orders[key] = order
        ranking[key] = [{'node_id': f'file:{fid_name(n)}', 'value': 100 - pos} for pos, n in enumerate(order)]
    report['dependency_network']['rankings_by_category']['production'] = ranking
    text = render_handout(report, arch)
    for key in keys:
        body = section(text, f'### {key}')
        order = orders[key]
        assert [n for n in sorted(range(12), key=lambda n: body.index(fid_name(n)) if fid_name(n) in body else 10**9)
                if fid_name(n) in body] == order[:10], key
        assert all(fid_name(n) not in body for n in order[10:])


def test_V04_F11_packages_are_selected_by_instability_desc_not_by_weighted_instability_or_input_order():
    report, arch = synthetic_inputs([make('large_node', 1)])
    count = 14
    ranks = {'language': [(i * 5) % count for i in range(count)], 'framework': [(i * 3 + 1) % count for i in range(count)]}
    offsets = {'language': 0, 'framework': 1000}

    def rows(scheme):
        rank, offset = ranks[scheme], offsets[scheme]
        assert sorted(rank) == list(range(count))
        return {f'pkg:python:p{i:03d}': {'file_count': offset + 100 + i, 'ca': offset + 200 + i, 'ce': offset + 300 + i,
                                          'instability': round(1 - rank[i] / 20, 4), 'weighted_ca': 1.0, 'weighted_ce': 1.0,
                                          'weighted_instability': round(rank[i] / 20, 4)} for i in range(count)}
    report['dependency_network']['package_metrics'] = {scheme: rows(scheme) for scheme in ranks}
    text = render_handout(report, arch)
    for scheme, rank in ranks.items():
        body = section(text, f'### {scheme}')
        by_rank = sorted(range(count), key=lambda i: rank[i])
        shown = [i for i in sorted(range(count), key=lambda i: body.index(f'p{i:03d}') if f'p{i:03d}' in body else 10**9)
                 if f'p{i:03d}' in body]
        assert shown == by_rank[:10], scheme
        for i in shown:
            line = next(line for line in body.splitlines() if f'p{i:03d}' in line)
            offset = offsets[scheme]
            assert all(has_token(line, offset + base + i) for base in (100, 200, 300)), line
            assert has_token(line, round(1 - rank[i] / 20, 4)) or str(round(1 - rank[i] / 20, 4)) in line, line
        assert all(f'p{i:03d}' not in body for i in by_rank[10:])


def package_rows(values):
    """values: {name: instability or None}; weighted_instability is deliberately different (reversed) from instability."""
    return {f'pkg:python:{name}': {'file_count': 10 + i, 'ca': 20 + i, 'ce': 30 + i, 'instability': value, 'weighted_ca': 1.0,
                                   'weighted_ce': 1.0, 'weighted_instability': (1 - value) if value is not None else 0.5}
            for i, (name, value) in enumerate(values.items())}


def shown_packages(values):
    report, arch = synthetic_inputs([make('large_node', 1)])
    report['dependency_network']['package_metrics'] = {'language': package_rows(values)}
    body = section(render_handout(report, arch), '### language')
    names = [name for name in values if f'pkg:python:{name}`' in body or f'pkg:python:{name} ' in body]
    return sorted(names, key=lambda name: body.index(f'pkg:python:{name}'))


def test_V04_G_M05_zero_instability_is_not_ranked_with_one_and_none_does_not_outrank_it():
    # 'a000' sorts alphabetically before every 1.0 package; if 0 were treated as 1 it would be listed first.
    values = {'a000': 0.0, 'b001': 1.0, 'b002': 1.0, 'b003': 1.0, 'b004': 1.0, 'b005': 1.0, 'c006': 0.5, 'c007': 0.4, 'c008': 0.3,
              'c009': 0.2, 'c010': 0.1, 'a011': None}
    shown = shown_packages(values)
    assert set(shown[:5]) == {'b001', 'b002', 'b003', 'b004', 'b005'}
    assert shown[5:] == ['c006', 'c007', 'c008', 'c009', 'c010']
    assert 'a000' not in shown and 'a011' not in shown


def test_V04_G_M05_zero_instability_is_listed_after_the_nonzero_ones_and_none_is_last():
    values = {'a000': 0.0, 'b001': 1.0, 'b002': 1.0, 'b003': 1.0, 'c004': 0.6, 'c005': 0.5, 'c006': 0.4, 'c007': 0.3, 'c008': 0.2,
              'c009': 0.1, 'a010': None}
    shown = shown_packages(values)
    assert set(shown[:3]) == {'b001', 'b002', 'b003'}
    assert shown[3:] == ['c004', 'c005', 'c006', 'c007', 'c008', 'c009', 'a000']
    assert 'a010' not in shown


def test_V04_G_M05_none_instability_sorts_after_zero_when_both_fit():
    values = {'a000': 0.0, 'b001': 1.0, 'c002': 0.5, 'a003': None}
    assert shown_packages(values) == ['b001', 'c002', 'a000', 'a003']


def edge_record(k, with_path=True):
    record = {'from_id': f'file:fb{k:02d}.py', 'to_id': f'file:tb{k:02d}.py', 'relation': 'CALLS', 'resolution': 'ambiguous',
              'metadata': {'detail_edge_indices': [k]}}
    if with_path:
        record.update(path=f'ev/u{k:02d}.py', start_line=300 + k, end_line=300 + k)
    return record


def assert_location_form(body, k):
    assert f'ev/u{k:02d}.py:{300 + k}' in body, k
    assert f'file:fb{k:02d}.py{ARROW}file:tb{k:02d}.py' not in body and f'fb{k:02d}.py{ARROW}tb{k:02d}.py' not in body, k


def test_V04_G_M10_unresolved_boundary_edge_shaped_records_show_path_and_line_not_an_arrow():
    candidate = make('unresolved_boundary', 1, evidence=None)
    candidate['evidence'] = [edge_record(k) for k in range(4)]
    body = plain(section(render_handout(*synthetic_inputs([candidate])), '### unresolved_boundary'))
    for k in range(3):
        assert_location_form(body, k)
    assert 'ev/u03.py' not in body


def test_V04_G_M10_unresolved_boundary_node_shaped_records_show_path_and_line():
    candidate = make('unresolved_boundary', 1)
    candidate['evidence'] = [{'node_id': f'py:n{k}', 'path': f'ev/n{k:02d}.py', 'start_line': 500 + k, 'end_line': 500 + k} for k in range(4)]
    body = plain(section(render_handout(*synthetic_inputs([candidate])), '### unresolved_boundary'))
    for k in range(3):
        assert f'ev/n{k:02d}.py:{500 + k}' in body
    assert 'ev/n03.py' not in body


def test_V04_G_M10_unresolved_boundary_record_without_a_path_shows_its_to_id():
    candidate = make('unresolved_boundary', 1)
    candidate['evidence'] = [edge_record(0, with_path=False)]
    body = plain(section(render_handout(*synthetic_inputs([candidate])), '### unresolved_boundary'))
    assert 'file:tb00.py' in body


def test_V04_G_M10_large_node_path_mapping_shows_path_and_line():
    candidate = make('large_node', 1)
    candidate['evidence'] = {'path': 'ev/big.py', 'start_line': 777, 'end_line': 3000}
    body = plain(section(render_handout(*synthetic_inputs([candidate])), '### large_node'))
    assert 'ev/big.py:777' in body


@pytest.mark.parametrize('kind,field', [('isolated_node', 'edges'), ('untested_hub', 'uncertain_test_edges')])
def test_V04_G_M10_mapping_evidence_edge_lists_show_the_first_three_as_path_and_line(kind, field):
    candidate = make(kind, 1)
    candidate['evidence'][field] = [edge_record(k) for k in range(4)]
    body = plain(section(render_handout(*synthetic_inputs([candidate])), f'### {kind}'))
    for k in range(3):
        assert_location_form(body, k)
    assert 'ev/u03.py' not in body
    assert has_token(body, 4)
