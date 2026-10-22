"""Counts are written out by hand in the tables and cross-checked by the independent oracle in
tests/signal_defects_round4_support.py; nothing derives an expectation from analyzer output."""
import json
import re
from pathlib import Path

import pytest

from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
from language_analyzers.core.graph_models import SourceSpan
from tests.edge_weights_support import edge, load_weights, weights_data
from tests.file_analysis_support import converted, node as file_node
from tests.signal_defects_round4_support import (BASE_COMMIT, base_tree, edge_start_line, expected_spread, framework_dump,
                                                 has_edge, ids_of, kind_of, rel_of, run_cli, shape, span_lines, targets,
                                                 write_project)
from tests.signal_defects_support import (analyze_files, evidence_rows, flags_of, make_subject, meta_of, node_of,
                                          of_kind, pipeline, run_payload, sym, weights_in)

LINE_T = 3
REPO = Path(__file__).resolve().parents[1]


def S(path, a, b=None):
    return SourceSpan(path, a, a if b is None else b)


def assert_candidate_record_unchanged(candidate):
    """R15: fields of an evidence_spread candidate other than metrics keep their 3b768a9 values."""
    assert candidate['kind'] == 'evidence_spread'
    assert candidate['coverage'] == 'static_analyzer_relation'
    assert candidate['status'] == 'static_candidate'
    assert re.fullmatch(r'b:[0-9a-f]{16}', candidate['id'])


def _symbol_spread(tmp_path, target_path, evidence):
    """Target `t` in target_path; one caller node per evidence span. Returns the evidence_spread candidates of `t`."""
    paths = {target_path, 'w.py', *(s.file_path for s in evidence)} - {None}
    files = {p: 'x\n' * 12 for p in paths}
    nodes = [sym('t', target_path, 1, 1)] + [sym(f's{i}', 'w.py', i + 1, i + 1) for i in range(len(evidence))]
    edges = [edge(f's{i}', 't', evidence=span) for i, span in enumerate(evidence)]
    snap, arch = make_subject(files, nodes, edges)
    payload = run_payload(snap, arch, weights_in(tmp_path, large_node_line_threshold=LINE_T))
    return [c for c in of_kind(payload, 'evidence_spread') if c['target'] == 't']


def metrics(files, dirs, span=0):
    return {'file_count': files, 'directory_count': dirs, 'line_span': span, 'line_threshold': LINE_T}


V1_TABLE = {
    'DT1_two_external_directories': ('a/x.py', [S('b/y.py', 1), S('c/z.py', 1)], metrics(2, 2)),
    'DT2_one_external_directory_two_files': ('a/x.py', [S('b/y.py', 1), S('b/z.py', 1)], None),
    'DT3_same_directory_file_plus_one_external': ('a/x.py', [S('a/u.py', 1), S('b/y.py', 1)], None),
    'DT4_one_file_range_equals_threshold': ('a/x.py', [S('b/y.py', 1), S('b/y.py', LINE_T)], None),
    'DT5_one_file_range_threshold_plus_one': ('a/x.py', [S('b/y.py', 1), S('b/y.py', LINE_T + 1)], metrics(1, 1, LINE_T + 1)),
    'DT5_same_directory_single_file_beyond_threshold': ('a/x.py', [S('a/u.py', 1), S('a/u.py', LINE_T + 1)], metrics(1, 0, LINE_T + 1)),
    'DT6_no_evidence': ('a/x.py', [], None),
    'DT7_root_target_root_evidence_and_one_directory': ('t.py', [S('x.py', 1), S('b/y.py', 1)], None),
    'DT7_root_target_two_directories': ('t.py', [S('b/y.py', 1), S('c/z.py', 1)], metrics(2, 2)),
    'DT8_target_without_file_excludes_nothing': (None, [S('x.py', 1), S('b/y.py', 1)], metrics(2, 2)),
    'DT7_root_evidence_counts_as_a_directory_for_a_nested_target': ('a/x.py', [S('x.py', 1), S('b/y.py', 1)], metrics(2, 2)),
}


@pytest.mark.parametrize('case', sorted(V1_TABLE))
def test_V1_oracle_agrees_with_hand_table(case):
    target, evidence, expected = V1_TABLE[case]
    spans = {}
    for s in evidence:
        lo, hi = spans.get(s.file_path, (s.start_line, s.end_line))
        spans[s.file_path] = (min(lo, s.start_line), max(hi, s.end_line))
    assert expected_spread(target, [s.file_path for s in evidence], LINE_T, spans) == expected


@pytest.mark.parametrize('case', sorted(V1_TABLE))
def test_V1_symbol_mode_decision_table(tmp_path, case):
    target, evidence, expected = V1_TABLE[case]
    found = _symbol_spread(tmp_path, target, evidence)
    if expected is None:
        assert found == []
    else:
        assert len(found) == 1
        assert found[0]['metrics'] == expected
        assert_candidate_record_unchanged(found[0])
        assert {(r['path'], r['start_line']) for r in evidence_rows(found[0])} == {(s.file_path, s.start_line) for s in evidence}


def _py_project(tmp_path, name, callers, target='a/t.py', module=None):
    module = module or target[:-3].replace('/', '.')
    files = {target: 'def f():\n    return 1\n'}
    for path in callers:
        files[path] = f'from {module} import f\n\n\ndef use():\n    f()\n'
    return write_project(tmp_path / name, files)


def _f_candidates(payload, module_prefix):
    return [c for c in of_kind(payload, 'evidence_spread') if c['target'] == f'py:{module_prefix}#f']


def test_V1_C1_project_two_external_directories_fire(tmp_path):
    root = _py_project(tmp_path, 'c1', ['b/x.py', 'c/y.py'])
    found = _f_candidates(pipeline(root, tmp_path, 'symbol', 'python', name='c1'), 'a.t')
    assert len(found) == 1
    assert found[0]['metrics'] == {'file_count': 2, 'directory_count': 2, 'line_span': 0, 'line_threshold': 2000}
    assert_candidate_record_unchanged(found[0])


def test_V1_C2_project_one_external_directory_two_files_no_candidate(tmp_path):
    root = _py_project(tmp_path, 'c2', ['b/x.py', 'b/y.py'])
    assert _f_candidates(pipeline(root, tmp_path, 'symbol', 'python', name='c2'), 'a.t') == []


def test_V1_C3_project_same_directory_caller_plus_one_external_no_candidate(tmp_path):
    root = _py_project(tmp_path, 'c3', ['a/u.py', 'b/x.py'])
    assert _f_candidates(pipeline(root, tmp_path, 'symbol', 'python', name='c3'), 'a.t') == []


def test_V1_C6_project_root_target_root_caller_and_one_directory_no_candidate(tmp_path):
    root = _py_project(tmp_path, 'c6', ['x.py', 'b/y.py'], target='t.py', module='t')
    assert _f_candidates(pipeline(root, tmp_path, 'symbol', 'python', name='c6'), 't') == []


def _file_spread(tmp_path, target_path, evidence):
    nodes = [file_node('t', target_path)]
    edges = []
    for i, span in enumerate(evidence):
        nodes.append(file_node(f'u{i}', span.file_path))
        edges.append(edge(f'u{i}', 't', evidence=span))
    paths = {target_path, *(s.file_path for s in evidence)}
    snap, result = converted({p: 'x\n' * 12 for p in paths}, nodes, edges)
    weights = load_weights(tmp_path, weights_data(large_node_line_threshold=LINE_T))
    from tests.report_size_support import with_v8_spread
    payload = with_v8_spread(json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, result, weights))), result)
    return [c for c in of_kind(payload, 'evidence_spread') if c['target'] == f'file:{target_path}']


V2_CASES = ['DT1_two_external_directories', 'DT2_one_external_directory_two_files',
            'DT3_same_directory_file_plus_one_external', 'DT4_one_file_range_equals_threshold',
            'DT5_one_file_range_threshold_plus_one']


@pytest.mark.parametrize('case', V2_CASES)
def test_V2_file_mode_decision_table(tmp_path, case):
    target, evidence, expected = V1_TABLE[case]
    found = _file_spread(tmp_path, target, evidence)
    if expected is None:
        assert found == []
    else:
        assert len(found) == 1 and found[0]['metrics'] == expected
        assert_candidate_record_unchanged(found[0])
        assert {r['path'] for r in evidence_rows(found[0])} == {s.file_path for s in evidence}


def test_V2_C5_file_mode_project_matches_symbol_mode(tmp_path):
    fires = _py_project(tmp_path, 'c5a', ['b/x.py', 'c/y.py'])
    payload = pipeline(fires, tmp_path, 'file', 'python', name='c5a')
    found = [c for c in of_kind(payload, 'evidence_spread') if c['target'] == 'file:a/t.py']
    assert len(found) == 1
    assert found[0]['metrics'] == {'file_count': 2, 'directory_count': 2, 'line_span': 0, 'line_threshold': 2000}
    assert_candidate_record_unchanged(found[0])
    quiet = _py_project(tmp_path, 'c5b', ['b/x.py', 'b/y.py'])
    payload = pipeline(quiet, tmp_path, 'file', 'python', name='c5b')
    assert [c for c in of_kind(payload, 'evidence_spread') if c['target'] == 'file:a/t.py'] == []


APP_JS = (REPO / 'renderers' / 'html' / 'static' / 'app.js').read_text(encoding='utf-8')


def _spread_payload(tmp_path):
    """Three candidates whose file_count order (9, 3, 5) differs from their directory_count order (2, 3, 4)."""
    snap, arch = make_subject({'w.py': 'x\n'}, [sym('t', 'w.py')], [])
    payload = run_payload(snap, arch, weights_in(tmp_path))
    template = {'kind': 'evidence_spread', 'coverage': 'static_analyzer_relation', 'status': 'static_candidate',
                'evidence': [{'path': 'b/x.py', 'start_line': 1, 'end_line': 1}, {'path': 'c/y.py', 'start_line': 1, 'end_line': 1}]}
    rows = [('py:a.t#f', 9, 2), ('py:b.x#g', 3, 3), ('py:c.y#h', 5, 4)]
    payload['candidates'] = [dict(template, id=f'b:{i}', target=t, metrics={'file_count': fc, 'directory_count': dc, 'line_span': 0, 'line_threshold': 2000})
                             for i, (t, fc, dc) in enumerate(rows)]
    return payload


def test_V3_report_description_says_outside_target_directory_two_or_more_directories():
    from report.bottlenecks.generate import KIND_DESCRIPTIONS
    text = KIND_DESCRIPTIONS['evidence_spread']
    assert re.search(r'대상 디렉터리 밖.*둘 이상.*디렉터리', text)
    assert '여러 파일' not in text and '둘 이상의 파일' not in text


def test_V3_report_ranks_evidence_spread_by_directory_count(tmp_path):
    from report.bottlenecks.generate import prioritize_candidates
    ranked = prioritize_candidates(_spread_payload(tmp_path))
    assert [row['candidate']['target'] for row in ranked] == ['py:c.y#h', 'py:b.x#g', 'py:a.t#f']
    assert [row['score'] for row in ranked] == [4.0, 3.0, 2.0]


def test_V3_rendered_report_embeds_the_new_description_and_card_wording(tmp_path):
    from report.bottlenecks import render_report
    document = render_report(_spread_payload(tmp_path))
    assert re.search(r'대상 디렉터리 밖.{0,10}둘 이상.{0,10}디렉터리', document)
    assert '개 디렉터리' in document


def test_V3_app_js_card_value_is_directory_count_in_directories():
    lines = [l for l in APP_JS.splitlines() if "'evidence_spread'" in l and 'return' in l]
    assert len(lines) == 1
    assert 'directory_count' in lines[0] and '개 디렉터리' in lines[0]
    assert 'file_count' not in lines[0] and '개 파일' not in lines[0]


def test_V3_app_js_description_text_is_directory_based():
    match = re.search(r"evidence_spread: \['근거 분산', '([^']*)'\]", APP_JS)
    assert match, 'evidence_spread label/description entry missing'
    assert re.search(r'대상 디렉터리 밖.*둘 이상.*디렉터리', match.group(1))
    assert '여러 파일' not in match.group(1)


def kt(tmp_path, text, name='f.kt'):
    return analyze_files(tmp_path, 'kotlin', {name: text})


F = 'kotlin:f.kt#'
FILE = 'kotlin:f.kt'


def test_V4_B_object_var_C7(tmp_path):
    arch = kt(tmp_path, 'object X { var y = 0 }\n')
    assert kind_of(node_of(arch, F + 'X')) == 'class'
    assert node_of(arch, F + 'X').signature == 'object X'
    assert kind_of(node_of(arch, F + 'X.y')) == 'field'
    assert has_edge(arch, F + 'X', 'CONTAINS', F + 'X.y')
    assert has_edge(arch, FILE, 'DECLARES', F + 'X')
    assert span_lines(node_of(arch, F + 'X')) == (1, 1)


def test_V4_B_object_fun_with_call_C9(tmp_path):
    arch = kt(tmp_path, 'object Q { fun f() = g() }\nfun g() = 1\n')
    assert kind_of(node_of(arch, F + 'Q')) == 'class' and node_of(arch, F + 'Q.f')
    assert node_of(arch, F + 'Q').signature == 'object Q'
    assert has_edge(arch, F + 'Q', 'CONTAINS', F + 'Q.f')
    assert has_edge(arch, FILE, 'DECLARES', F + 'Q')
    assert targets(arch, F + 'Q.f', 'CALLS') == {F + 'g'}
    assert targets(arch, F + 'Q', 'CALLS') == set()


def test_V4_B_object_scans_exclude_member_ranges_R12b(tmp_path):
    arch = kt(tmp_path, 'object Q { var y = 0; fun h() { y = 1 }; fun e() = Class.forName("n"); fun m() = missing() }\n')
    assert has_edge(arch, F + 'Q.h', 'WRITES', F + 'Q.y')
    assert not any(e.from_id == F + 'Q' and rel_of(e) in ('READS', 'WRITES') for e in arch.edges)
    assert 'dynamic_import' in flags_of(arch, F + 'Q.e') and 'dynamic_import' not in flags_of(arch, F + 'Q')
    q_meta = meta_of(arch, F + 'Q')
    assert not any(k.startswith(('external_', 'unresolved_')) for k in q_meta)
    assert meta_of(arch, F + 'Q.m')['external_call_count'] == 1


def test_V4_B_data_object(tmp_path):
    arch = kt(tmp_path, 'data object D { val z = 1 }\n')
    assert kind_of(node_of(arch, F + 'D')) == 'class'
    assert node_of(arch, F + 'D').signature == 'object D'
    assert kind_of(node_of(arch, F + 'D.z')) == 'field'
    assert has_edge(arch, F + 'D', 'CONTAINS', F + 'D.z') and has_edge(arch, FILE, 'DECLARES', F + 'D')


def test_V4_A_class_val_C8(tmp_path):
    arch = kt(tmp_path, 'class K { val v = 1 }\n')
    assert kind_of(node_of(arch, F + 'K.v')) == 'field'
    assert has_edge(arch, F + 'K', 'CONTAINS', F + 'K.v')


def test_V4_A_class_member_scan_excludes_member_range_and_collects_fun(tmp_path):
    arch = kt(tmp_path, 'class K { val v = foo(); fun m() = bar() }\nfun foo() = 1\nfun bar() = 2\n')
    assert targets(arch, F + 'K.v', 'CALLS') == {F + 'foo'}
    assert targets(arch, F + 'K.m', 'CALLS') == {F + 'bar'}
    assert targets(arch, F + 'K', 'CALLS') == set()


def test_V4_A_object_with_supertype_val(tmp_path):
    arch = kt(tmp_path, 'open class B\nobject O : B() { val y = 0 }\n')
    assert kind_of(node_of(arch, F + 'O')) == 'class'
    assert kind_of(node_of(arch, F + 'O.y')) == 'field'
    assert has_edge(arch, F + 'O', 'CONTAINS', F + 'O.y')


def test_V4_A_nested_object(tmp_path):
    arch = kt(tmp_path, 'class A {\n    object B { val c = 1 }\n}\n')
    assert kind_of(node_of(arch, F + 'A.B')) == 'class'
    assert kind_of(node_of(arch, F + 'A.B.c')) == 'field'
    assert has_edge(arch, F + 'A', 'CONTAINS', F + 'A.B') and has_edge(arch, F + 'A.B', 'CONTAINS', F + 'A.B.c')


def test_V4_B_nested_one_line_object_inside_recovered_object(tmp_path):
    arch = analyze_files(tmp_path, 'kotlin', {'f.kt': 'package p\n\nobject T {\n    fun f() = g()\n    object N { val w = 1 }\n}\nfun g() = 1\n'})
    for qual, kind in (('T', 'class'), ('T.f', 'method'), ('T.N', 'class'), ('T.N.w', 'field')):
        assert kind_of(node_of(arch, F + qual)) == kind, qual
    assert node_of(arch, F + 'T').signature == 'object T' and node_of(arch, F + 'T.N').signature == 'object N'
    assert has_edge(arch, F + 'T', 'CONTAINS', F + 'T.N') and has_edge(arch, F + 'T.N', 'CONTAINS', F + 'T.N.w')
    assert targets(arch, F + 'T.f', 'CALLS') == {F + 'g'}
    assert targets(arch, F + 'T', 'CALLS') == set()


def test_V4_C10_ordinary_infix_adds_no_declaration(tmp_path):
    before = ids_of(kt(tmp_path, 'fun g() = 1\n', name='f.kt'))
    arch = kt(tmp_path, 'fun g() = 1\nval p = a to b\nfoo bar { 1 }\na to b\n', name='f.kt')
    added = ids_of(arch) - before
    assert not any(i.endswith(('#a', '#b', '#to', '#bar', '#foo')) for i in added)
    assert all(kind_of(n) != 'class' for n in arch.nodes)


def test_V4_multi_line_contrast_has_the_same_structure(tmp_path):
    one = kt(tmp_path, 'object Q { var y = 0; fun f() = g(); fun h() { y = 1 } }\nfun g() = 1\n', name='f.kt')
    many = kt(tmp_path, 'object Q {\n    var y = 0\n    fun f() = g()\n    fun h() {\n        y = 1\n    }\n}\nfun g() = 1\n', name='f.kt')
    assert shape(one, 'f.kt') == shape(many, 'f.kt')


CTOR_ONE_LINE = ('class C(val a: Int = foo(), val b: Int = bar(), c: Int = baz())\n'
                 'fun foo() = 1\nfun bar() = 2\nfun baz() = 3\n')


def test_V5_val_default_call_belongs_to_that_field_only_C11(tmp_path):
    arch = kt(tmp_path, CTOR_ONE_LINE)
    assert targets(arch, F + 'C.a', 'CALLS') == {F + 'foo'}
    assert targets(arch, F + 'C.b', 'CALLS') == {F + 'bar'}


def test_V5_class_keeps_all_constructor_calls_C11(tmp_path):
    arch = kt(tmp_path, CTOR_ONE_LINE)
    assert targets(arch, F + 'C', 'CALLS') == {F + 'foo', F + 'bar', F + 'baz'}


def test_V5_plain_parameter_default_call_goes_to_class_only(tmp_path):
    arch = kt(tmp_path, CTOR_ONE_LINE)
    assert F + 'C.c' not in ids_of(arch)
    assert F + 'baz' not in targets(arch, F + 'C.a', 'CALLS') | targets(arch, F + 'C.b', 'CALLS')


def test_V5_var_default_call_belongs_to_that_field_only(tmp_path):
    arch = kt(tmp_path, 'class C(var a: Int = foo(), val b: Int = bar())\nfun foo() = 1\nfun bar() = 2\n')
    assert targets(arch, F + 'C.a', 'CALLS') == {F + 'foo'}
    assert targets(arch, F + 'C.b', 'CALLS') == {F + 'bar'}


def test_V5_val_without_default_has_no_calls(tmp_path):
    arch = kt(tmp_path, 'class C(val a: Int, val b: Int = bar())\nfun bar() = 2\n')
    assert targets(arch, F + 'C.a', 'CALLS') == set()
    assert targets(arch, F + 'C.b', 'CALLS') == {F + 'bar'}


def test_V5_reads_writes_scan_is_limited_to_the_parameter(tmp_path):
    arch = kt(tmp_path, 'class C(val a: Int = foo(), val b: Int = bar())\nfun foo() = 1\nfun bar() = 2\n')
    for relation in ('READS', 'WRITES', 'INSTANTIATES'):
        assert F + 'bar' not in targets(arch, F + 'C.a', relation)
        assert F + 'foo' not in targets(arch, F + 'C.b', relation)


MULTI_CTOR = ('class C(\n'
              '    val a: Int = foo(),\n'
              '    val b: Int =\n'
              '        bar(),\n'
              '    c: Int = baz(),\n'
              ') {\n'
              '}\n'
              'fun foo() = 1\nfun bar() = 2\nfun baz() = 3\n')


def test_V5_C12_multi_line_constructor_field_span_is_its_own_parameter(tmp_path):
    arch = kt(tmp_path, MULTI_CTOR)
    assert span_lines(node_of(arch, F + 'C.a')) == (2, 2)
    assert span_lines(node_of(arch, F + 'C.b')) == (3, 4)
    assert node_of(arch, F + 'C.a').cost.line_count == 1 and node_of(arch, F + 'C.b').cost.line_count == 2
    assert span_lines(node_of(arch, F + 'C')) == (1, 7)


def test_V5_C12_signature_and_contains_evidence_use_the_parameter(tmp_path):
    arch = kt(tmp_path, MULTI_CTOR)
    assert 'val a' in node_of(arch, F + 'C.a').signature and 'val b' not in node_of(arch, F + 'C.a').signature
    assert 'val b' in node_of(arch, F + 'C.b').signature and 'val a' not in node_of(arch, F + 'C.b').signature
    assert edge_start_line(arch, F + 'C', 'CONTAINS', F + 'C.a') == [2]
    assert edge_start_line(arch, F + 'C', 'CONTAINS', F + 'C.b') == [3]


def test_V5_C12_multi_line_calls_follow_the_parameter_lines(tmp_path):
    arch = kt(tmp_path, MULTI_CTOR)
    assert targets(arch, F + 'C.a', 'CALLS') == {F + 'foo'}
    assert targets(arch, F + 'C.b', 'CALLS') == {F + 'bar'}
    assert edge_start_line(arch, F + 'C.b', 'CALLS', F + 'bar') == [4]


def test_V5_parameter_type_use_belongs_to_that_field_only(tmp_path):
    arch = kt(tmp_path, 'class Foo\nclass Baz\nclass C(val a: Foo, val b: Int = bar(), val c: Baz)\nfun bar() = 2\n')
    assert targets(arch, F + 'C.a', 'TYPE_USES') == {F + 'Foo'}
    assert targets(arch, F + 'C.b', 'TYPE_USES') == set()
    assert targets(arch, F + 'C.c', 'TYPE_USES') == {F + 'Baz'}
    assert {F + 'Foo', F + 'Baz'} <= targets(arch, F + 'C', 'TYPE_USES')


def test_V5_class_instantiation_in_constructor_keeps_class_attribution(tmp_path):
    arch = kt(tmp_path, 'class Foo\nclass C(val a: Foo = Foo(), val b: Int = 0)\n')
    assert targets(arch, F + 'C.a', 'INSTANTIATES') == {F + 'Foo'}
    assert targets(arch, F + 'C.b', 'INSTANTIATES') == set()
    assert targets(arch, F + 'C', 'INSTANTIATES') == {F + 'Foo'}


def test_V5_external_calls_in_defaults_are_scanned_per_parameter(tmp_path):
    arch = kt(tmp_path, 'class C(val a: Int = ext1(), val b: Int = ext2())\n')
    assert meta_of(arch, F + 'C.a')['external_calls'] == {'ext1': 1}
    assert meta_of(arch, F + 'C.b')['external_calls'] == {'ext2': 1}
    assert meta_of(arch, F + 'C')['external_call_count'] == 2


def test_V5_same_name_body_field_keeps_the_first_collected(tmp_path):
    arch = kt(tmp_path, 'class D(val x: Int = foo()) {\n    val x = bar()\n}\nfun foo() = 1\nfun bar() = 2\n')
    assert [n.id for n in arch.nodes].count(F + 'D.x') == 1
    assert span_lines(node_of(arch, F + 'D.x')) == (1, 1)
    assert targets(arch, F + 'D.x', 'CALLS') == {F + 'foo'}


def test_V6_file_with_only_errors_does_not_raise(tmp_path):
    arch = analyze_files(tmp_path, 'kotlin', {'bad.kt': '}}} ((( class { fun\n@@@ object : : {\n'})
    assert 'kotlin:bad.kt' in ids_of(arch)


def test_V6_error_file_does_not_stop_a_valid_file(tmp_path):
    arch = analyze_files(tmp_path, 'kotlin', {'bad.kt': 'class {{{ val = fun ((\n}}}\n', 'ok.kt': 'class Ok { val v = foo() }\nfun foo() = 1\n'})
    assert 'kotlin:ok.kt#Ok' in ids_of(arch) and 'kotlin:ok.kt#Ok.v' in ids_of(arch)
    assert targets(arch, 'kotlin:ok.kt#Ok.v', 'CALLS') == {'kotlin:ok.kt#foo'}


def test_V6_error_inside_a_valid_declaration_keeps_collectable_members(tmp_path):
    arch = analyze_files(tmp_path, 'kotlin', {'m.kt': 'object Q { fun f() = 1 ))) }\nclass K { val v = 1 }\n'})
    assert 'kotlin:m.kt#K.v' in ids_of(arch)


def test_V7_symbol_bottlenecks_json(tmp_path):
    snap, arch = make_subject({'w.py': 'x\n'}, [sym('t', 'w.py')], [])
    payload = run_payload(snap, arch, weights_in(tmp_path))
    assert payload['versions']['analysis'] == '6' and payload['schema'] == 'bottlenecks.v6'
    assert 'granularity' not in payload


def test_V7_file_bottlenecks_json(tmp_path):
    snap, result = converted({'a.py': 'x\n'}, [file_node('a', 'a.py')], [])
    weights = load_weights(tmp_path, weights_data())
    payload = json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, result, weights)))
    assert payload['versions']['analysis'] == '6' and payload['schema'] == 'bottlenecks.v9'
    assert payload['granularity'] == 'file'


@pytest.mark.parametrize('granularity,schema', [('symbol', 'bottlenecks.v6'), ('file', 'bottlenecks.v9')])
def test_V7_cli_output_declares_version_six(tmp_path, granularity, schema):
    root = _py_project(tmp_path, f'v7{granularity}', ['b/x.py', 'c/y.py'])
    payload = pipeline(root, tmp_path, granularity, 'python', name=f'v7{granularity}')
    assert payload['versions'] == {'analysis': '6'} and payload['schema'] == schema


C7_C11_INPUTS = {
    'c7': {'app/src/main/kotlin/p/X.kt': 'package p\n\nobject X { var y = 0 }\n'},
    'c11': {'app/src/main/kotlin/p/C.kt': ('package p\n\nclass C(val a: Int = foo(), val b: Int = bar(), c: Int = baz())\n'
                                         'fun foo() = 1\nfun bar() = 2\nfun baz() = 3\n')},
    'viewmodel': {'app/src/main/kotlin/p/Vm.kt': ('package p\n\nimport androidx.lifecycle.ViewModel\nimport dagger.hilt.android.lifecycle.HiltViewModel\n'
                                                 'import javax.inject.Inject\n\n@HiltViewModel\n'
                                                 'class Vm @Inject constructor(val repo: Repo = defaultRepo(), val n: Int = size()) : ViewModel()\n'
                                                 'class Repo\nfun defaultRepo() = Repo()\nfun size() = 1\n')},
}


@pytest.fixture(scope='module')
def base_checkout(tmp_path_factory):
    """BASE_COMMIT exported with `git archive` into a scratch directory; the baseline for every V8 comparison."""
    return base_tree(tmp_path_factory)


@pytest.mark.parametrize('case', sorted(C7_C11_INPUTS))
def test_V8_framework_analyzer_output_equals_base_commit(tmp_path, base_checkout, case):
    project = write_project(tmp_path / case, C7_C11_INPUTS[case])
    assert framework_dump(REPO, project) == framework_dump(base_checkout, project)


@pytest.mark.parametrize('case', sorted(C7_C11_INPUTS))
def test_V8_android_graph_without_language_graph_equals_base_commit(tmp_path, base_checkout, case):
    project = write_project(tmp_path / case, C7_C11_INPUTS[case])
    head = run_cli(REPO, project, tmp_path / 'head', '-f', 'android', '--no-language-graph')
    base = run_cli(base_checkout, project, tmp_path / 'base', '-f', 'android', '--no-language-graph')
    assert head == base


def test_V8_android_fixture_framework_output_equals_base_commit(tmp_path, base_checkout):
    from fixtures.registry import fixture_root
    project = fixture_root('android-nowinandroid')
    assert framework_dump(REPO, project) == framework_dump(base_checkout, project)
