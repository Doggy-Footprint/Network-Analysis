import json
import re

import pytest

from tests.delta_support import wire
from tests.rename_delta_support import make_repo, write_files
from tests.symbol_changes_support import (AMBIGUOUS, FI, UNRESOLVED, analyze, arch, baseline_then_edit, candidates_of, delta_run, rel, sym,
                                          sym_payload)

KIND = 'unreferenced_symbol'


def api():
    import bottlenecks.symbols as module
    return module


def candidates(nodes, edges=()):
    return api().unreferenced_candidates(arch(nodes, edges))


def evidence_ids(candidate):
    return sorted(e['node_id'] for e in candidate['evidence'])


def assert_common_fields(item):
    assert re.fullmatch(r'b:[0-9a-f]{16}', item['id']) and item['coverage'] == 'static_analyzer_relation'
    assert item['status'] == 'static_candidate'


def only(nodes, edges=()):
    result = candidates(nodes, edges)
    assert len(result) == 1, result
    return result[0]


def test_V06_EP1_functions_and_methods_without_incoming_edges_are_listed_with_the_declared_shape():
    nodes = [sym('py:a#lonely', 'a.py', 'function', line=3), sym('py:a#K', 'a.py', 'class'), sym('py:a#K.m', 'a.py', 'method', line=9),
             sym('py:a#C', 'a.py', 'constant')]
    edges = [rel('py:a#K', 'py:a#K.m', 'CONTAINS')]
    candidate = only(nodes, edges)
    assert {'kind', 'target', 'metrics', 'evidence'} <= set(candidate)
    assert_common_fields(candidate)
    assert candidate['kind'] == KIND and candidate['target'] == 'file:a.py' and candidate['metrics'] == {'unreferenced_count': 2}
    assert sorted(candidate['evidence'], key=lambda e: e['node_id']) == [
        {'node_id': 'py:a#K.m', 'name': 'm', 'kind': 'method', 'start_line': 9},
        {'node_id': 'py:a#lonely', 'name': 'lonely', 'kind': 'function', 'start_line': 3}]


def test_V06_EP1_one_candidate_per_file():
    nodes = [sym('py:a#f', 'a.py'), sym('py:a#g', 'a.py'), sym('py:b#h', 'b.py')]
    result = sorted(candidates(nodes), key=lambda c: c['target'])
    assert [(c['target'], c['metrics']['unreferenced_count']) for c in result] == [('file:a.py', 2), ('file:b.py', 1)]


def test_V06_EP2_a_call_from_the_same_file_is_a_reference():
    nodes = [sym('py:a#helper', 'a.py'), sym('py:a#caller', 'a.py')]
    assert evidence_ids(only(nodes, [rel('py:a#caller', 'py:a#helper')])) == ['py:a#caller']


def test_V06_EP3_a_call_from_another_file_is_a_reference():
    nodes = [sym('py:a#f', 'a.py'), sym('py:b#g', 'b.py')]
    result = candidates(nodes, [rel('py:b#g', 'py:a#f')])
    assert [(c['target'], evidence_ids(c)) for c in result] == [('file:b.py', ['py:b#g'])]


@pytest.mark.parametrize('kwargs', [{'confidence': FI}, {'resolution': AMBIGUOUS}, {'resolution': UNRESOLVED}],
                         ids=['framework-inferred', 'ambiguous', 'unresolved'])
def test_V06_EP4_a_low_confidence_or_unresolved_edge_is_still_a_reference(kwargs):
    nodes = [sym('py:a#f', 'a.py'), sym('py:b#g', 'b.py')]
    result = candidates(nodes, [rel('py:b#g', 'py:a#f', **kwargs)])
    assert all('py:a#f' not in evidence_ids(c) for c in result)


def test_V06_EP4_a_candidate_target_of_an_ambiguous_edge_is_a_reference():
    nodes = [sym('py:a#f', 'a.py'), sym('py:a#other', 'a.py'), sym('py:b#g', 'b.py')]
    edge = rel('py:b#g', 'py:a#other', resolution=AMBIGUOUS, candidates=['py:a#f'])
    result = {c['target']: evidence_ids(c) for c in candidates(nodes, [edge])}
    assert result == {'file:b.py': ['py:b#g']}


def test_V06_EP5_only_self_recursion_is_not_a_reference():
    nodes = [sym('py:a#loop', 'a.py'), sym('py:a#used', 'a.py'), sym('py:b#g', 'b.py')]
    edges = [rel('py:a#loop', 'py:a#loop'), rel('py:b#g', 'py:a#used')]
    result = {c['target']: evidence_ids(c) for c in candidates(nodes, edges)}
    assert result == {'file:a.py': ['py:a#loop'], 'file:b.py': ['py:b#g']}


@pytest.mark.parametrize('name, kind, signature', [
    ('__repr__', 'method', 'def __repr__(self)'),
    ('constructor', 'method', 'constructor(x: number)'),
    ('main', 'function', 'def main()'),
    ('describe', 'method', 'override fun describe(): String'),
    ('describe', 'method', 'public override fun describe(): String'),
], ids=['dunder', 'constructor', 'main', 'override', 'modifier-before-override'])
def test_V06_EP6_excluded_names_and_override_are_never_listed(name, kind, signature):
    nodes = [sym(f'py:a#{name}', 'a.py', kind, name=name, signature=signature)]
    assert candidates(nodes) == []
    nodes.append(sym('py:a#real', 'a.py'))
    assert evidence_ids(only(nodes)) == ['py:a#real']


def test_V06_EP6_names_that_only_resemble_the_exclusions_are_listed():
    nodes = [sym('py:a#_private', 'a.py'), sym('py:a#__x', 'a.py'), sym('py:a#mainly', 'a.py'),
             sym('py:a#d', 'a.py', 'method', signature='fun d(override: Int)')]
    assert evidence_ids(only(nodes)) == ['py:a#__x', 'py:a#_private', 'py:a#d', 'py:a#mainly']


def test_V06_EP7_nodes_in_test_files_are_never_listed():
    nodes = [sym('py:t#test_a', 'tests/test_a.py'), sym('py:t#helper', 'pkg/tests/util.py')]
    assert candidates(nodes) == []
    assert evidence_ids(only(nodes + [sym('py:a#f', 'src/a.py')])) == ['py:a#f']


def test_V06_EP8_an_implemented_by_edge_from_a_framework_declaration_is_a_reference():
    endpoint = sym('nestjs:endpoint:src/c.ts#GET /ok', 'src/c.ts', 'endpoint', name='GET /ok', provenance='nestjs')
    nodes = [sym('ts:src/c.ts#C.ok', 'src/c.ts', 'method', name='ok'), sym('ts:src/c.ts#C.spare', 'src/c.ts', 'method', name='spare'), endpoint]
    edges = [rel(endpoint.id, 'ts:src/c.ts#C.ok', 'IMPLEMENTED_BY')]
    assert evidence_ids(only(nodes, edges)) == ['ts:src/c.ts#C.spare']


def test_V06_EP8_an_implemented_by_edge_from_a_language_node_is_not_a_reference():
    nodes = [sym('py:a#iface', 'a.py', 'class'), sym('py:a#impl', 'a.py', 'method', name='impl')]
    assert evidence_ids(only(nodes, [rel('py:a#iface', 'py:a#impl', 'IMPLEMENTED_BY')])) == ['py:a#impl']


PY = {
    'app/__init__.py': '',
    'app/h.py': 'def helper():\n    return 1\n\n\ndef caller():\n    return helper()\n\n\nclass R:\n    def __repr__(self):\n        return "R"\n\n\n'
                'def unused_py():\n    return 2\n',
}
TS = {
    'src/c.ts': 'function helper(): number { return 1; }\nexport function go(): number { return helper(); }\n'
                'export class Svc {\n  constructor() {}\n}\nexport function unusedTs(): number { return 2; }\n',
}
KT = {
    'src/main/kotlin/k/K.kt': 'package k\n\nopen class Base {\n    open fun describe(): String = "b"\n}\n\nclass Impl : Base() {\n'
                              '    override fun describe(): String = "i"\n}\n\nfun helper(): Int = 1\n\nfun caller(): Int = helper()\n\n'
                              'fun unusedKt(): Int = 2\n',
}
NEST = {
    'src/app.controller.ts': "import { Controller, Get } from '@nestjs/common';\n@Controller('api')\nexport class AppController {\n"
                             "  @Get('ok') ok() { return 1; }\n  unusedHandlerHelper() { return 2; }\n}\n",
    'src/app.module.ts': "import { Module } from '@nestjs/common';\nimport { AppController } from './app.controller';\n"
                         "@Module({ controllers: [AppController] })\nexport class AppModule {}\n",
}


def listed_names(data, path):
    [candidate] = [c for c in candidates_of(data, KIND) if c['target'] == f'file:{path}']
    return candidate, {e['name'] for e in candidate['evidence']}


@pytest.mark.parametrize('files, lang, path, expected_in, expected_out', [
    (PY, ['-l', 'python'], 'app/h.py', {'unused_py', 'caller'}, {'helper', '__repr__'}),
    (TS, ['-l', 'typescript'], 'src/c.ts', {'unusedTs', 'go'}, {'helper', 'constructor'}),
], ids=['python', 'typescript'])
def test_C07_same_file_helper_and_excluded_names_are_not_listed(tmp_path, files, lang, path, expected_in, expected_out):
    root = tmp_path / 'repo'
    make_repo(root, files)
    candidate, names = listed_names(analyze(root, tmp_path / 'o', lang), path)
    assert expected_in <= names and not (expected_out & names)
    assert candidate['metrics']['unreferenced_count'] == len(candidate['evidence'])


def test_C07_kotlin_override_is_not_listed(tmp_path):
    root = tmp_path / 'repo'
    make_repo(root, KT)
    candidate, names = listed_names(analyze(root, tmp_path / 'o', ['-l', 'kotlin']), 'src/main/kotlin/k/K.kt')
    assert {'unusedKt', 'caller'} <= names and 'helper' not in names
    assert not [e for e in candidate['evidence'] if e['name'] == 'describe' and 'Impl' in e['node_id']]


def test_C07_nestjs_route_handler_is_not_listed(tmp_path):
    root = tmp_path / 'repo'
    make_repo(root, NEST)
    _, names = listed_names(analyze(root, tmp_path / 'o', ['-f', 'nestjs', '-l', 'typescript']), 'src/app.controller.ts')
    assert 'unusedHandlerHelper' in names and 'ok' not in names


def test_C06_two_new_unreferenced_methods_raise_the_count_and_the_delta_reports_the_file(tmp_path):
    files = {'app/__init__.py': '', 'app/svc.py': 'class Svc:\n    def run(self):\n        return 1\n',
             'app/use.py': 'from app.svc import Svc\n\n\ndef go():\n    return Svc().run()\n'}
    edit = lambda r: write_files(r, {'app/svc.py': files['app/svc.py'] + '\n    def new_a(self):\n        return 2\n\n    def new_b(self):\n        return 3\n'})
    root, baseline = baseline_then_edit(tmp_path, files, ['-l', 'python'], edit)
    before = [c for c in candidates_of(json.loads(baseline.read_text(encoding='utf-8')), KIND) if c['target'] == 'file:app/svc.py']
    base_count = before[0]['metrics']['unreferenced_count'] if before else 0
    _, data = delta_run(root, baseline, tmp_path, ['-l', 'python'])
    [candidate] = [c for c in candidates_of(data, KIND) if c['target'] == 'file:app/svc.py']
    assert candidate['metrics']['unreferenced_count'] == base_count + 2
    ids = {e['node_id'] for e in candidate['evidence']}
    assert {'py:app.svc#Svc.new_a', 'py:app.svc#Svc.new_b'} <= ids
    reported = [i for i in data['delta']['new_candidates'] + data['delta']['strengthened_candidates']
                if i['kind'] == KIND and i['target'] == 'file:app/svc.py']
    assert len(reported) == 1
    assert reported[0] in (data['delta']['new_candidates'] if not before else data['delta']['strengthened_candidates'])


def candidate(count, node_ids, ident='b:0001', target='file:a.py'):
    return {'id': ident, 'kind': KIND, 'target': target, 'metrics': {'unreferenced_count': count},
            'evidence': [{'node_id': n, 'name': n.split('#')[-1], 'kind': 'function', 'start_line': 1} for n in node_ids],
            'coverage': 'static_analyzer_relation', 'status': 'static_candidate'}


def delta_of(cur, base):
    import bottlenecks.delta as delta
    return wire(delta.compute_delta(sym_payload(None, candidates=cur), sym_payload(None, candidates=base)))


def test_V07_D1_a_larger_count_is_strengthened():
    result = delta_of([candidate(2, ['py:a#x', 'py:a#y'])], [candidate(1, ['py:a#x'], ident='b:0000')])
    assert result['new_candidates'] == []
    [item] = result['strengthened_candidates']
    assert (item['kind'], item['target'], item['candidate_id'], item['baseline_candidate_id']) == (KIND, 'file:a.py', 'b:0001', 'b:0000')
    assert item['increased'] == {'unreferenced_count': {'baseline': 1, 'current': 2}}
    assert result['counts']['strengthened_candidates'] == 1


def test_V07_D2_the_same_count_with_a_replaced_node_is_strengthened_by_evidence():
    result = delta_of([candidate(1, ['py:a#y'])], [candidate(1, ['py:a#x'])])
    [item] = result['strengthened_candidates']
    assert item['increased'] == {}
    assert item['added_evidence'] == [['node', 'py:a#y']]


@pytest.mark.parametrize('cur, base', [
    (candidate(2, ['py:a#x', 'py:a#y']), candidate(2, ['py:a#y', 'py:a#x'])),
    (candidate(1, ['py:a#x']), candidate(2, ['py:a#x', 'py:a#y'])),
], ids=['unchanged', 'fewer-symbols'])
def test_V07_D3_no_change_or_fewer_symbols_report_nothing(cur, base):
    result = delta_of([cur], [base])
    assert result['strengthened_candidates'] == [] and result['new_candidates'] == []


def test_V07_a_file_without_a_baseline_candidate_is_new():
    result = delta_of([candidate(1, ['py:a#x'])], [])
    assert [(i['kind'], i['target'], i['metrics']) for i in result['new_candidates']] == [(KIND, 'file:a.py', {'unreferenced_count': 1})]
