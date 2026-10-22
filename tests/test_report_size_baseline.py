"""Spec ee17484a52af182c v1/v2: V07 (v8 and v9 baselines give the same delta) and V08 (invalid v9 baselines).

The baseline is the base-commit golden itself (v8, written by the base commit) and its v9 re-encoding by the
F02-F05 rules. The current analysis is the fixture project plus two additions, analysed in-process."""
import copy
import json

import pytest

from bottlenecks.delta import BaselineError, compute_delta, load_baseline
from tests.delta_support import ref_delta, wire
from tests.report_size_support import golden, project_files, snapshot_of, to_payload, to_v8_payload, to_v9_payload
from analysis.file_graph import to_file_architecture
from language_analyzers.core.serialization import architecture_to_dict
from language_analyzers.python.graph import PythonGraphAnalyzer
from pathlib import Path

V8 = golden('v8_bottlenecks.json')

ADDED = {
    # new cycle x <-> y (two packages), and engine <-> more which grows the core/util/registry cycle
    'x/__init__.py': '',
    'x/p.py': 'from y.q import f\n\n\ndef g():\n    return f()\n',
    'y/__init__.py': '',
    'y/q.py': 'from x.p import g\n\n\ndef f():\n    return g()\n',
    'util/more.py': 'from core.engine import shared_tool\n\n\ndef more():\n    return shared_tool(1)\n',
}


@pytest.fixture(scope='module')
def current():
    files = {**project_files(), **ADDED}
    files['core/engine.py'] = 'from util.more import more\n' + files['core/engine.py']
    snap = snapshot_of(files)
    arch = to_file_architecture(PythonGraphAnalyzer(Path('/repo'), snap).analyze(), snap)
    v9 = to_payload(snap, arch)
    details = json.loads(json.dumps(architecture_to_dict(arch)['details']))
    return v9, to_v8_payload(v9, details)


def write(tmp_path, data, name='baseline.json'):
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding='utf-8')
    return path


def test_V07_v8_and_v9_baselines_give_the_same_delta(tmp_path, current):
    cur_v9, cur_v8 = current
    v8_path = write(tmp_path, V8, 'v8.json')
    v9_path = write(tmp_path, to_v9_payload(V8, details_file='x.details.json'), 'v9.json')
    base8, base9 = load_baseline(v8_path), load_baseline(v9_path)
    assert base8['schema'] == 'bottlenecks.v8' and base9['schema'] == 'bottlenecks.v9'
    from_v8 = wire(compute_delta(cur_v9, base8))
    from_v9 = wire(compute_delta(cur_v9, base9))
    assert from_v8 == from_v9
    assert from_v8 == wire(ref_delta(cur_v8, V8))
    assert from_v8['new_cycles'] and from_v8['grown_cycles']
    assert any('file:x/p.py' in item['members'] for item in from_v8['new_cycles'])
    assert any('file:util/more.py' in item['added_members'] for item in from_v8['grown_cycles'])
    assert from_v8['new_package_dependencies']


def test_V07_identical_analysis_has_an_empty_delta_for_both_baseline_schemas(tmp_path):
    from tests.report_size_support import fixture_payload
    cur = fixture_payload()
    for name, data in (('v8', V8), ('v9', to_v9_payload(V8))):
        result = wire(compute_delta(cur, load_baseline(write(tmp_path, data, name + '.json'))))
        assert result['counts'] == {key: 0 for key in result['counts']}, name


# ---------------------------------------------------------------------------------------------------- V08

def good():
    return to_v9_payload(V8, details_file='details.json')


def cycle_row(data):
    return next(c for c in data['candidates'] if c['kind'] == 'dependency_cycle')['evidence'][0]


def drop_file_ids(data):
    del data['dependency_network']['file_ids']


def drop_columns(data):
    del data['dependency_network']['evidence_columns']


def set_index(position, value):
    def mutate(data):
        cycle_row(data)[position] = value
    return mutate


def out_of_range(data):
    cycle_row(data)[1] = len(data['dependency_network']['file_ids'])


def short_row(data):
    next(c for c in data['candidates'] if c['kind'] == 'dependency_cycle')['evidence'][0] = cycle_row(data)[:5]


def schema_v7(data):
    data['schema'] = 'bottlenecks.v7'


def file_ids_not_list(data):
    data['dependency_network']['file_ids'] = 'file:a.py'


def file_ids_non_string(data):
    data['dependency_network']['file_ids'][2] = 7


def row_not_list(data):
    next(c for c in data['candidates'] if c['kind'] == 'dependency_cycle')['evidence'][0] = {'from': 0, 'to': 1}


CASES = {
    'file_ids-not-a-list': (file_ids_not_list, ['file_ids']),
    'file_ids-non-string-element': (file_ids_non_string, ['file_ids']),
    'row-not-a-list': (row_not_list, ['evidence']),
    'index-bool': (set_index(0, True), ['evidence']),
    'index-float': (set_index(1, 1.0), ['evidence']),
    'file_ids-missing': (drop_file_ids, ['file_ids']),
    'evidence_columns-missing': (drop_columns, ['evidence_columns']),
    'row-length-mismatch': (short_row, ['evidence']),
    'index-string': (set_index(0, '3'), ['evidence']),
    'index-minus-one': (set_index(0, -1), ['evidence']),
    'index-equals-len-file_ids': (out_of_range, ['evidence']),
    'schema-v7': (schema_v7, ['bottlenecks.v8', 'bottlenecks.v9']),
}


def test_V08_the_unmutated_v9_baseline_loads(tmp_path):
    assert load_baseline(write(tmp_path, good()))['schema'] == 'bottlenecks.v9'


@pytest.mark.parametrize('case', CASES)
def test_V08_invalid_baseline_raises_baseline_error_with_path_and_location(tmp_path, case):
    mutate, needles = CASES[case]
    data = good()
    mutate(data)
    path = write(tmp_path, data)
    with pytest.raises(BaselineError) as raised:
        load_baseline(path)
    message = str(raised.value)
    assert message.startswith(f'baseline {path}: ')
    for needle in needles:
        assert needle in message, (needle, message)
