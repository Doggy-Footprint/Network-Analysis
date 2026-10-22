"""Spec ee17484a52af182c v1: V01 (bottlenecks.v9 evidence encoding), V02 (output files per CLI flags), V03 (handout path),
V05 (determinism), V09 (write failure).

V01 oracle: tests/report_size_evidence/v8_*.json were written by the base commit (see README there) and are decoded
against the v9 output field by field; cycle rows are also recomputed from the architecture with tests.structure_support."""
import copy
import json
import os
from pathlib import Path

import pytest

from tests.structure_support import with_base_policy

from tests.report_size_support import (CHANGED_KINDS, EVIDENCE_COLUMNS, PROJECT, cli_fixture_run, decode_evidence, fixture_architecture_dict,
                                       fixture_payload, fixture_pipeline, golden, inline_data, is_compact, of_kind, run_cli, run_cli_ok,
                                       weights)
from tests.structure_support import ref_package_pairs, ref_pairs, ref_structure

V8 = golden('v8_bottlenecks.json')
V8_DETAILS = golden('v8_details.json')


@pytest.fixture(scope='module')
def v9():
    return fixture_payload()


@pytest.fixture(scope='module')
def file_ids(v9):
    return v9['dependency_network']['file_ids']


def by_id(candidates):
    return {item['id']: item for item in candidates}


def test_V01_precondition_golden_has_all_four_changed_kinds_and_an_unchanged_kind():
    kinds = {item['kind'] for item in V8['candidates']}
    assert set(CHANGED_KINDS) <= kinds and kinds - set(CHANGED_KINDS)
    assert V8['schema'] == 'bottlenecks.v8'


def test_V01_fixture_details_equal_base_details():
    assert fixture_architecture_dict()['details'] == V8_DETAILS


def test_V01_F01_schema_and_candidate_set_and_order(v9):
    assert v9['schema'] == 'bottlenecks.v9' and v9['granularity'] == 'file'
    assert [item['id'] for item in v9['candidates']] == [item['id'] for item in V8['candidates']]
    assert [item['kind'] for item in v9['candidates']] == [item['kind'] for item in V8['candidates']]


def test_V01_EP6_F02_file_ids_and_evidence_columns(v9):
    network = v9['dependency_network']
    assert network['file_ids'] == sorted(V8['dependency_network']['node_metrics'])
    assert all(isinstance(item, str) for item in network['file_ids'])
    assert network['evidence_columns'] == EVIDENCE_COLUMNS
    assert network['evidence_columns'] == {'file_pair': ['from', 'to', 'relations', 'max_weight', 'evidence_count', 'tier'],
                                           'package_pair': ['from_id', 'to_id', 'relations', 'max_weight', 'evidence_count', 'tier', 'file_pairs']}


def test_V01_EP1_F03_evidence_spread_is_the_sorted_unique_index_list_of_the_v8_records(v9):
    base = by_id(of_kind(V8['candidates'], 'evidence_spread'))
    found = by_id(of_kind(v9['candidates'], 'evidence_spread'))
    assert base and set(found) == set(base)
    for ident, candidate in found.items():
        indices = candidate['evidence']
        assert all(type(i) is int for i in indices)
        assert indices == sorted(set(indices))
        assert set(indices) == {record['detail_edge_index'] for record in base[ident]['evidence']}
        assert len(indices) == len(base[ident]['evidence'])


def test_V01_EP1_F03_each_index_points_at_the_v8_detail_edge(v9):
    details = fixture_architecture_dict()['details']
    for candidate in of_kind(v9['candidates'], 'evidence_spread'):
        base = {record['detail_edge_index']: record for record in by_id(V8['candidates'])[candidate['id']]['evidence']}
        for index in candidate['evidence']:
            edge, record = details['edges'][index], base[index]
            assert (edge['from_id'], edge['to_id'], edge['relation']) == (record['from_id'], record['to_id'], record['relation'])
            assert edge['evidence']['file_path'] == record['path'] and edge['evidence']['start_line'] == record['start_line']


@pytest.mark.parametrize('kind', ['dependency_cycle', 'unstable_dependency'])
def test_V01_EP2_EP4_F04_file_pair_rows_decode_to_the_v8_records(v9, file_ids, kind):
    base = by_id(of_kind(V8['candidates'], kind))
    found = by_id(of_kind(v9['candidates'], kind))
    assert base and set(found) == set(base)
    for ident, candidate in found.items():
        for row in candidate['evidence']:
            assert isinstance(row, list) and len(row) == 6
            assert type(row[0]) is int and type(row[1]) is int and isinstance(row[2], list) and row[2] == sorted(row[2])
        expected = [{k: v for k, v in record.items() if k != 'detail_edge_indices'} for record in base[ident]['evidence']]
        assert decode_evidence(candidate, file_ids) == expected


def test_V01_EP3_F05_package_pair_rows_decode_to_the_v8_records(v9, file_ids):
    base = by_id(of_kind(V8['candidates'], 'package_cycle'))
    found = by_id(of_kind(v9['candidates'], 'package_cycle'))
    assert base and set(found) == set(base)
    for ident, candidate in found.items():
        for row in candidate['evidence']:
            assert isinstance(row, list) and len(row) == 7 and isinstance(row[0], str) and isinstance(row[1], str)
            assert all(type(a) is int and type(b) is int for a, b in row[6])
        assert decode_evidence(candidate, file_ids) == base[ident]['evidence']


def test_V01_EP2_F04_cycle_rows_match_the_independent_architecture_reference(v9, file_ids):
    arch = fixture_pipeline()[1]
    for item in of_kind(v9['candidates'], 'dependency_cycle'):
        tier, members = item['structure']['tier'], set(item['structure']['members'])
        internal = {pair: rec for pair, rec in ref_pairs(arch, weights(), tier).items() if pair[0] in members and pair[1] in members}
        rows = decode_evidence(item, file_ids)
        assert [(r['from_id'], r['to_id']) for r in rows] == sorted(internal)
        for row in rows:
            expected = internal[(row['from_id'], row['to_id'])]
            assert row['relations'] == expected['relations'] and row['evidence_count'] == expected['evidence_count']
            assert row['tier'] == expected['tier'] and row['max_weight'] == pytest.approx(expected['max_weight'])


def test_V01_EP3_F05_package_rows_match_the_independent_architecture_reference(v9, file_ids):
    arch = fixture_pipeline()[1]
    ref = ref_structure(arch, weights())
    for item in of_kind(v9['candidates'], 'package_cycle'):
        structure = item['structure']
        members = set(structure['members'])
        package_pairs = ref_package_pairs(ref['pairs'][structure['tier']], ref['schemes'][structure['scheme']])
        internal = {pair: rec for pair, rec in package_pairs.items() if pair[0] in members and pair[1] in members}
        rows = decode_evidence(item, file_ids)
        assert [(r['from_id'], r['to_id']) for r in rows] == sorted(internal)
        for row in rows:
            expected = internal[(row['from_id'], row['to_id'])]
            assert row['file_pairs'] == expected['file_pairs'] and row['evidence_count'] == expected['evidence_count']
            assert row['tier'] == expected['tier'] and row['max_weight'] == pytest.approx(expected['max_weight'])


def test_V01_F06_everything_except_the_evidence_field_is_unchanged(v9):
    base = by_id(V8['candidates'])
    assert len(v9['candidates']) == len(base)
    for candidate in v9['candidates']:
        old = base[candidate['id']]
        assert {k: v for k, v in candidate.items() if k != 'evidence'} == {k: v for k, v in old.items() if k != 'evidence'}


def test_V01_EP5_F06_unchanged_kinds_are_identical_to_v8(v9):
    unchanged = [item for item in V8['candidates'] if item['kind'] not in CHANGED_KINDS]
    assert unchanged
    assert [item for item in v9['candidates'] if item['kind'] not in CHANGED_KINDS] == unchanged


def test_V01_EP6_F06_dependency_network_and_top_level_keys_are_unchanged(v9):
    v9 = with_base_policy(v9)
    network = {k: v for k, v in v9['dependency_network'].items() if k not in ('file_ids', 'evidence_columns')}
    assert network == V8['dependency_network']
    assert set(v9) - set(V8) <= {'details_file'}
    assert set(V8) <= set(v9)
    for key in V8:
        if key not in ('schema', 'candidates', 'dependency_network', 'snapshot', 'coverage'):
            assert v9[key] == V8[key], key
    assert v9['coverage']['structure'] == V8['coverage']['structure']


def test_V01_v9_json_round_trip_has_no_v8_leftovers(v9):
    for item in v9['candidates']:
        if item['kind'] in ('dependency_cycle', 'unstable_dependency', 'package_cycle'):
            assert all(isinstance(row, list) for row in item['evidence'])
    assert 'detail_edge_indices' not in json.dumps(v9['candidates'])


@pytest.fixture(scope='module')
def r1(tmp_path_factory):
    return cli_fixture_run(tmp_path_factory.mktemp('r1'))


def names(directory):
    return {path.relative_to(directory).as_posix() for path in Path(directory).rglob('*') if path.is_file()}


RULES = {
    # rule: (granularity, --json, --bottlenecks) -> files that must exist beyond report.html
    'R1-file-json-bottlenecks': ('file', True, True, {'report.json', 'report.details.json', 'bn/b.json', 'bn/b.handout.md'}),
    'R2-file-json': ('file', True, False, {'report.json', 'report.details.json'}),
    'R3-file-bottlenecks': ('file', False, True, {'report.details.json', 'bn/b.json', 'bn/b.handout.md'}),
    'R4-file-neither': ('file', False, False, set()),
    'R5-symbol-json-bottlenecks': ('symbol', True, True, {'report.json', 'bn/b.json'}),
}


@pytest.mark.parametrize('rule', RULES)
def test_V02_decision_table_files_present_and_absent(tmp_path, rule):
    granularity, json_flag, bottlenecks, expected = RULES[rule]
    directory = cli_fixture_run(tmp_path, json_flag=json_flag, bottlenecks='bn/b.json' if bottlenecks else None, granularity=granularity)
    assert names(directory) - {'report.html'} == expected


def test_V02_R1_report_json_is_compact_schema_7_without_details(r1):
    text = (r1 / 'report.json').read_text(encoding='utf-8')
    assert is_compact(text)
    report = json.loads(text)
    assert report['schema_version'] == '7' and 'details' not in report
    assert report['details_file'] == 'report.details.json'
    assert report['granularity'] == 'file'


def test_V02_R1_report_json_keeps_every_other_v8_value(r1):
    report = json.loads((r1 / 'report.json').read_text(encoding='utf-8'))
    base = golden('v8_report_without_details.json')
    assert set(report) == set(base) | {'details_file'}
    for key in base:
        if key not in ('schema_version', 'project_path'):
            assert report[key] == base[key], key
    assert Path(report['project_path']).resolve() == PROJECT.resolve()


def test_V02_R1_details_file_is_the_full_compact_architecture_details(r1):
    text = (r1 / 'report.details.json').read_text(encoding='utf-8')
    assert is_compact(text)
    details = json.loads(text)
    assert set(details) == {'nodes', 'edges', 'node_files', 'node_owners', 'file_nodes'}
    assert details == V8_DETAILS == fixture_architecture_dict()['details']


def test_V02_R1_bottlenecks_details_file_is_relative_to_the_bottlenecks_directory(r1):
    payload = json.loads((r1 / 'bn' / 'b.json').read_text(encoding='utf-8'))
    reference = payload['details_file']
    assert not os.path.isabs(reference) and reference != 'report.details.json'
    assert (r1 / 'bn' / reference).resolve() == (r1 / 'report.details.json').resolve()
    assert payload['schema'] == 'bottlenecks.v9'


def test_V02_R1_cli_bottlenecks_decode_to_the_v8_golden(r1):
    payload = json.loads((r1 / 'bn' / 'b.json').read_text(encoding='utf-8'))
    details = json.loads((r1 / 'report.details.json').read_text(encoding='utf-8'))
    from tests.report_size_support import to_v8_payload
    restored = with_base_policy(to_v8_payload(payload, details))
    expected = copy.deepcopy(V8['candidates'])
    for item in expected:
        for record in item['evidence'] if isinstance(item['evidence'], list) else ():
            if item['kind'] != 'evidence_spread':
                record.pop('detail_edge_indices', None)
    assert restored['candidates'] == expected
    assert restored['dependency_network'] == V8['dependency_network']


def test_V02_R1_v8_detail_edge_indices_are_recoverable_from_report_json_file_edges(r1):
    report = json.loads((r1 / 'report.json').read_text(encoding='utf-8'))
    payload = json.loads((r1 / 'bn' / 'b.json').read_text(encoding='utf-8'))
    file_ids = payload['dependency_network']['file_ids']
    recovered = {}
    for edge in report['edges']:
        recovered.setdefault((edge['from_id'], edge['to_id']), set()).update(edge['metadata']['detail_edge_indices'])
    for candidate in of_kind(V8['candidates'], 'dependency_cycle') + of_kind(V8['candidates'], 'unstable_dependency'):
        for record in candidate['evidence']:
            assert set(record['detail_edge_indices']) <= recovered[(record['from_id'], record['to_id'])]
    assert all(0 <= i < len(V8_DETAILS['edges']) for found in recovered.values() for i in found) and file_ids


def test_V02_R1_html_embeds_the_compact_report_without_details(r1):
    data = inline_data(r1 / 'report.html')
    assert 'details' not in data['architecture']
    assert data['architecture']['schema_version'] == '6' and 'details_file' not in data['architecture']
    assert 'details_file' not in data['bottlenecks']


def test_V02_R5_symbol_granularity_keeps_v6_and_schema_5(tmp_path):
    directory = cli_fixture_run(tmp_path, granularity='symbol')
    text = (directory / 'report.json').read_text(encoding='utf-8')
    assert is_compact(text)
    report = json.loads(text)
    base = golden('v8_symbol_report.json')
    assert report['schema_version'] == '5' and 'details' not in report and 'details_file' not in report
    assert set(report) == set(base)
    for key in base:
        if key != 'project_path':
            assert report[key] == base[key], key
    assert json.loads((directory / 'bn' / 'b.json').read_text(encoding='utf-8'))['schema'] == 'bottlenecks.v6'
    assert 'details_file' not in json.loads((directory / 'bn' / 'b.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('name,handout', [('b.json', 'b.handout.md'), ('b', 'b.handout.md'), ('b.JSON', 'b.JSON.handout.md')],
                         ids=['json-suffix', 'no-suffix', 'upper-JSON-suffix'])
def test_V03_handout_path_follows_the_bottlenecks_path(tmp_path, name, handout):
    (tmp_path / 'bn').mkdir()
    run_cli_ok(PROJECT, '-l', 'python', '-o', tmp_path / 'report.html', '--bottlenecks', tmp_path / 'bn' / name)
    assert names(tmp_path / 'bn') == {name, handout}
    assert (tmp_path / 'bn' / handout).read_text(encoding='utf-8').startswith('# Dependency bottleneck handout')


HASH_SEEDS = ['0', '1', '31337']


def test_V05_four_outputs_are_byte_identical_across_runs_and_hash_seeds(tmp_path):
    """PYTHONHASHSEED is varied so set/dict iteration order cannot leak into any of the four files (F13)."""
    targets = ('report.json', 'report.details.json', 'bn/b.json', 'bn/b.handout.md')
    outputs = {}
    for seed in HASH_SEEDS + ['0']:
        for target in targets:
            (tmp_path / target).unlink(missing_ok=True)
        cli_fixture_run(tmp_path, seed=seed)
        outputs.setdefault(seed, []).append({target: (tmp_path / target).read_bytes() for target in targets})
    first = outputs['0'][0]
    assert all(first.values())
    assert outputs['0'][1] == first
    for seed in HASH_SEEDS[1:]:
        assert outputs[seed][0] == first, seed


def test_V09_details_path_that_is_a_directory_fails_with_exit_code_1(tmp_path):
    (tmp_path / 'report.details.json').mkdir()
    done = run_cli(PROJECT, '-l', 'python', '-o', tmp_path / 'report.html', '--json')
    assert done.returncode == 1
    assert '[!] Error:' in done.stderr
    assert 'Traceback' not in done.stderr


def test_V09_handout_path_that_is_a_directory_fails_with_exit_code_1(tmp_path):
    (tmp_path / 'b.handout.md').mkdir()
    done = run_cli(PROJECT, '-l', 'python', '-o', tmp_path / 'report.html', '--bottlenecks', tmp_path / 'b.json')
    assert done.returncode == 1
    assert '[!] Error:' in done.stderr
    assert 'Traceback' not in done.stderr
