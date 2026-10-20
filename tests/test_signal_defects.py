"""Evidence for spec e91abc221d7deb2a v1 (signal defects round 3, rules R1-R9).
Expected values are written from the rule text and the Cases table; PageRank expectations come from closed forms
and from an independent power iteration in tests/signal_defects_support.py."""
import dataclasses
import copy
import random

import pytest

from analysis import GraphAnalyzer
from analysis.edge_weights import (DEFAULT_LARGE_NODE_TOKEN_THRESHOLD, EdgeWeightsError, default_edge_weights_path,
                                   load_edge_weights)
from analysis.graph_metrics import GraphAnalysisConfig, pagerank
from bottlenecks import BottleneckInputError, analyze_bottlenecks
from language_analyzers.core.graph_models import Confidence, SourceSpan
from tests.edge_weights_support import edge, load_weights, symbol_nodes, weights_data
from tests.fact_defects_support import run_pipeline, write_tree
from tests.file_analysis_support import converted, node as file_node
from tests.signal_defects_support import (analyze_files, assert_boundary, assert_external, assert_silent,
                                          default_weights, edge_targets_by_label, edges_between, evidence_rows,
                                          flags_of, make_subject, meta_of, node_of, observed, of_kind, pipeline,
                                          ref_pagerank, ref_pagerank_before, run_payload, sym, weights_in)

EXACT = GraphAnalysisConfig(max_iterations=10000)
TOL = 1e-9


# =============================================================== V1: Python classification (R1; C1-C4, C20)

PKG_A = ('import unittest\n\nclass Closed:\n    pass\n\nclass Open(unittest.TestCase):\n    pass\n\n'
         'def real():\n    return 1\n')
PY_MAIN = '''import requests
import unittest
import pkg.a as m
import pkg.broken as bm
from os.path import join
from pkg.a import Closed, Open, gone


def f_builtin(x):
    return len(x)


def f_ext_bare(a):
    return join(a, 'b')


def f_ext_module():
    requests.get('u')


def f_local_param(o):
    o.append(1)


def f_local_var():
    items = []
    items.append(1)


def f_mod_missing_parsed():
    m.missing()


def f_mod_missing_unparsed():
    bm.thing()


def f_from_import_gone():
    gone()


def f_closed_class_name():
    Closed.nope()


def f_open_class_name():
    Open.nope()


def f_mixed(x):
    len(x)
    m.missing()


class Lone:
    def lone_self(self):
        self.nope()

    @classmethod
    def lone_cls(cls):
        cls.nope()


class Mixed(Closed):
    def mixed_self(self):
        self.nope()


class Ext(unittest.TestCase):
    def ext_self(self):
        self.assertEqual(1, 1)

    @classmethod
    def ext_cls(cls):
        cls.nope()


class Deep(Open):
    def deep_self(self):
        self.nope()


class Obj(object):
    def obj_self(self):
        self.nope()


class CycA(CycB):
    def cyc_a(self):
        self.x()


class CycB(CycA):
    def cyc_b(self):
        self.x()
'''
PY_FILES = {'pkg/__init__.py': '', 'pkg/a.py': PKG_A, 'pkg/broken.py': 'def broken(:\n', 'main.py': PY_MAIN}
M = 'py:main#'
# label -> (node id, 'ext'|'bnd', exact name->count dict or None)
PY_CASES = {
    'builtin-bare': (M + 'f_builtin', 'ext', {'len': 1}),
    'external-import-bare': (M + 'f_ext_bare', 'ext', {'join': 1}),
    'external-module-receiver': (M + 'f_ext_module', 'ext', {'get': 1}),
    'param-receiver': (M + 'f_local_param', 'ext', {'append': 1}),
    'local-var-receiver': (M + 'f_local_var', 'ext', {'append': 1}),
    'project-module-receiver-parsed': (M + 'f_mod_missing_parsed', 'bnd', {'missing': 1}),
    'project-module-receiver-unparsed': (M + 'f_mod_missing_unparsed', 'bnd', {'thing': 1}),
    'project-from-import-missing': (M + 'f_from_import_gone', 'bnd', {'gone': 1}),
    'self-no-base': (M + 'Lone.lone_self', 'bnd', {'nope': 1}),
    'cls-no-base': (M + 'Lone.lone_cls', 'bnd', {'nope': 1}),
    'self-project-base': (M + 'Mixed.mixed_self', 'bnd', {'nope': 1}),
    'self-external-base': (M + 'Ext.ext_self', 'ext', {'assertEqual': 1}),
    'cls-external-base': (M + 'Ext.ext_cls', 'ext', {'nope': 1}),
    'self-project-base-of-external-base': (M + 'Deep.deep_self', 'ext', {'nope': 1}),
    'self-object-base': (M + 'Obj.obj_self', 'bnd', {'nope': 1}),
    'self-cycle-a': (M + 'CycA.cyc_a', 'bnd', {'x': 1}),
    'self-cycle-b': (M + 'CycB.cyc_b', 'bnd', {'x': 1}),
    'project-class-name-closed': (M + 'f_closed_class_name', 'bnd', {'nope': 1}),
    'project-class-name-open': (M + 'f_open_class_name', 'ext', {'nope': 1}),
}


@pytest.fixture(scope='module')
def py_arch(tmp_path_factory):
    return analyze_files(tmp_path_factory.mktemp('v1'), 'python', PY_FILES)


@pytest.mark.parametrize('label', sorted(PY_CASES))
def test_V1_python_classification_tree(py_arch, label):
    node_id, kind, calls = PY_CASES[label]
    if kind == 'ext':
        assert_external(py_arch, node_id, 1, calls)
    else:
        assert_boundary(py_arch, node_id, 1, calls)


def test_V1_C1_print_len_counts_two_external_and_no_unresolved_keys(tmp_path):
    arch = analyze_files(tmp_path, 'python', {'x.py': 'def run(x):\n    print(len(x))\n'})
    assert_external(arch, 'py:x#run', 2, {'print': 1, 'len': 1})


def test_V1_boundary_and_external_in_one_node_are_recorded_separately(py_arch):
    o = observed(py_arch, M + 'f_mixed')
    assert o['ext_count'] == 1 and o['ext_calls'] == {'len': 1}
    assert o['unres_total'] == 1 and o['unres_calls'] == {'missing': 1} and len(o['refs']) == 1


def test_V1_C4_external_base_class_never_leaks_into_sibling_classes(py_arch):
    # Lone (no base) must stay boundary even though Ext (external base) lives in the same module.
    assert_boundary(py_arch, M + 'Lone.lone_self', 1)
    assert_external(py_arch, M + 'Ext.ext_self', 1)


def test_V1_positions_method_and_module_top_level(tmp_path):
    files = {'pkg/__init__.py': '', 'pkg/a.py': PKG_A,
             'top.py': 'import pkg.a as m\n\nTOTAL = len([1])\nm.top_missing()\n',
             'meths.py': 'import pkg.a as m\n\n\nclass K:\n    def build(self, x):\n        return len(x)\n\n'
                         '    def link(self):\n        m.missing()\n'}
    arch = analyze_files(tmp_path, 'python', files)
    o = observed(arch, 'py:top')
    assert o['ext_count'] == 1 and o['ext_calls'] == {'len': 1}
    assert o['unres_total'] == 1 and o['unres_calls'] == {'top_missing': 1}
    assert_external(arch, 'py:meths#K.build', 1, {'len': 1})
    assert_boundary(arch, 'py:meths#K.link', 1, {'missing': 1})


def test_V1_C3_boundary_functions_have_candidates_and_external_ones_do_not(tmp_path):
    files = {'pkg/__init__.py': '', 'pkg/a.py': PKG_A,
             'main.py': 'import pkg.a as m\nfrom pkg.a import gone\n\n\ndef via_module():\n    m.missing()\n\n\n'
                        'def via_import():\n    gone()\n\n\ndef run(x):\n    print(len(x))\n'}
    root = write_tree(tmp_path / 'proj', files)
    payload, _, _ = run_pipeline(root, tmp_path, 'symbol', '-l', 'python')
    targets = {c['target'] for c in of_kind(payload, 'unresolved_boundary')}
    assert {'py:main#via_module', 'py:main#via_import'} <= targets
    assert 'py:main#run' not in targets


# =============================================================== V2: TypeScript classification (R1; C5)

TS_M = 'export function real() { return 1; }\nexport class Proj { base() { return 1; } }\n'
TS_MAIN = '''import axios from 'axios';
import * as lib from 'external-lib';
import * as ns from './m';
import { gone } from './m';
import dflt from './m';
import { Repository } from 'typeorm';

export function f_global(x: number) { console.log(x); }
export function f_parse(s: string) { return parseInt(s, 10); }
export function f_axios() { axios.get('u'); }
export function f_ns_ext() { lib.go(); }
export function f_local(o: number[]) { o.push(1); }
export function f_ns_proj() { ns.nope(); }
export function f_named_gone() { gone(); }
export function f_default_fail() { dflt(); }
export function f_new_ext() { return new Map(); }
export function f_mixed() { parseInt('1'); ns.nope(); }
export class NoBase { run() { this.nope(); } }
export class ProjChild extends NoBase { run2() { this.nope(); } }
export class Repo extends Repository<number> { run3() { return this.find(); } }
'''
T = 'ts:main.ts#'
TS_CASES = {
    'global-bare-console': (T + 'f_global', 'ext', None),
    'global-bare-parseInt': (T + 'f_parse', 'ext', {'parseInt': 1}),
    'external-named-default-import': (T + 'f_axios', 'ext', None),
    'external-namespace-receiver': (T + 'f_ns_ext', 'ext', None),
    'local-receiver': (T + 'f_local', 'ext', None),
    'project-namespace-receiver-missing': (T + 'f_ns_proj', 'bnd', {'nope': 1}),
    'project-named-import-missing': (T + 'f_named_gone', 'bnd', {'gone': 1}),
    'project-default-import-unresolved': (T + 'f_default_fail', 'bnd', {'dflt': 1}),
    'new-external-class': (T + 'f_new_ext', 'ext', {'Map': 1}),
    'this-no-heritage': (T + 'NoBase.run', 'bnd', {'nope': 1}),
    'this-project-heritage': (T + 'ProjChild.run2', 'bnd', {'nope': 1}),
    'this-external-heritage': (T + 'Repo.run3', 'ext', None),
}


@pytest.fixture(scope='module')
def ts_arch(tmp_path_factory):
    return analyze_files(tmp_path_factory.mktemp('v2'), 'typescript', {'m.ts': TS_M, 'main.ts': TS_MAIN})


@pytest.mark.parametrize('label', sorted(TS_CASES))
def test_V2_typescript_classification_tree(ts_arch, label):
    node_id, kind, calls = TS_CASES[label]
    if kind == 'ext':
        assert_external(ts_arch, node_id, 1, calls)
    else:
        assert_boundary(ts_arch, node_id, 1, calls)


def test_V2_boundary_and_external_in_one_node(ts_arch):
    o = observed(ts_arch, T + 'f_mixed')
    assert o['ext_count'] == 1 and o['ext_calls'] == {'parseInt': 1}
    assert o['unres_total'] == 1 and o['unres_calls'] == {'nope': 1}


def test_V2_syntax_error_file_does_not_stop_analysis(tmp_path):
    arch = analyze_files(tmp_path, 'typescript', {'m.ts': TS_M, 'main.ts': TS_MAIN, 'bad.ts': 'export function = = ;\n'})
    assert_boundary(arch, T + 'f_named_gone', 1, {'gone': 1})


# =============================================================== V3: Kotlin classification (R1; C6)

KT_UTIL = 'package com.proj.util\n\nfun other() = 1\n'
KT_MAIN = '''package com.proj.app

import com.proj.util.helper
import org.other.ext_thing

fun f_stdlib(x: Int) { println(x) }
fun f_listof() { listOf(1) }
fun f_receiver(s: String) { s.trim() }
fun f_ext_import() { ext_thing() }
fun f_proj_import() { helper() }
fun f_mixed(x: Int) { println(x); helper() }
'''
KT_WILD = 'package com.proj.app2\n\nimport com.proj.util.*\n\nfun f_wild() { missing_name() }\n'
K = 'kotlin:com/proj/app/Main.kt#'
KT_FILES = {'com/proj/util/Util.kt': KT_UTIL, 'com/proj/app/Main.kt': KT_MAIN, 'com/proj/app2/Wild.kt': KT_WILD}
KT_CASES = {
    'stdlib-bare-println': (K + 'f_stdlib', 'ext', {'println': 1}),
    'stdlib-bare-listOf': (K + 'f_listof', 'ext', {'listOf': 1}),
    'receiver-method': (K + 'f_receiver', 'ext', None),
    'external-import-name': (K + 'f_ext_import', 'ext', {'ext_thing': 1}),
    'project-package-import-name-uncollected': (K + 'f_proj_import', 'bnd', {'helper': 1}),
    # literal reading of R1 (b): a wildcard import has no last piece that binds the name, so the call is external
    'wildcard-project-import-missing-name': ('kotlin:com/proj/app2/Wild.kt#f_wild', 'ext', {'missing_name': 1}),
}


@pytest.fixture(scope='module')
def kt_arch(tmp_path_factory):
    return analyze_files(tmp_path_factory.mktemp('v3'), 'kotlin', KT_FILES)


@pytest.mark.parametrize('label', sorted(KT_CASES))
def test_V3_kotlin_equivalence_partitions(kt_arch, label):
    node_id, kind, calls = KT_CASES[label]
    if kind == 'ext':
        assert_external(kt_arch, node_id, 1, calls)
    else:
        assert_boundary(kt_arch, node_id, 1, calls)


def test_V3_boundary_and_external_in_one_node(kt_arch):
    o = observed(kt_arch, K + 'f_mixed')
    assert o['ext_count'] == 1 and o['ext_calls'] == {'println': 1}
    assert o['unres_total'] == 1 and o['unres_calls'] == {'helper': 1}


def test_V3_syntax_error_file_does_not_stop_analysis(tmp_path):
    files = dict(KT_FILES, **{'com/proj/app3/Bad.kt': 'package com.proj.app3\n\nfun = = ;\n'})
    arch = analyze_files(tmp_path, 'kotlin', files)
    assert_boundary(arch, K + 'f_proj_import', 1, {'helper': 1})


# =============================================================== V4: file-node external_call_count (R2; C1)

def test_V4_file_node_sums_constituent_external_counts_and_creates_no_candidate(tmp_path):
    files = {'a.py': 'def a(x):\n    len(x)\n    print(x)\n\n\ndef b(x):\n    str(x)\n    int(x)\n    abs(x)\n\n\n'
                     'class K:\n    def c(self, x):\n        return max(x)\n',
             'b.py': 'def z():\n    return 1\n'}
    root = write_tree(tmp_path / 'proj', files)
    payload, _, arch = run_pipeline(root, tmp_path, 'file', '-l', 'python')
    a = {n.id: n for n in arch.nodes}['file:a.py'].metadata
    b = {n.id: n for n in arch.nodes}['file:b.py'].metadata
    assert a['external_call_count'] == 6
    assert 'external_call_count' not in b
    assert not any(c['target'] in ('file:a.py', 'file:b.py') for c in of_kind(payload, 'unresolved_boundary'))
    assert 'unresolved_reference_total' not in a and 'unresolved_references' not in a


def test_V4_single_external_call_file_has_count_one(tmp_path):
    root = write_tree(tmp_path / 'proj', {'only.py': 'def f(x):\n    return len(x)\n'})
    _, _, arch = run_pipeline(root, tmp_path, 'file', '-l', 'python')
    assert {n.id: n for n in arch.nodes}['file:only.py'].metadata['external_call_count'] == 1


# =============================================================== V5: unresolved_reference_total (R3; C7, C8)

def _many_files(language, n):
    names = [f'n{i:02d}' for i in range(n)]
    if language == 'python':
        text = 'from pkg.a import ' + ', '.join(names) + '\n\n\ndef many():\n' + ''.join(f'    {x}()\n' for x in names)
        return {'pkg/__init__.py': '', 'pkg/a.py': PKG_A, 'main.py': text}, 'py:main#many', 'main.py'
    if language == 'typescript':
        text = 'import { ' + ', '.join(names) + " } from './m';\n\nexport function many() {\n" + \
               ''.join(f'  {x}();\n' for x in names) + '}\n'
        return {'m.ts': TS_M, 'main.ts': text}, 'ts:main.ts#many', 'main.ts'
    text = 'package com.proj.app\n\n' + ''.join(f'import com.proj.util.{x}\n' for x in names) + \
           '\nfun many() {\n' + ''.join(f'    {x}()\n' for x in names) + '}\n'
    return {'com/proj/util/Util.kt': KT_UTIL, 'com/proj/app/Main.kt': text}, 'kotlin:com/proj/app/Main.kt#many', \
        'com/proj/app/Main.kt'


@pytest.mark.parametrize('n', [19, 20, 21, 30])
@pytest.mark.parametrize('language', ['python', 'typescript', 'kotlin'])
def test_V5_list_is_capped_at_twenty_and_total_is_the_uncapped_count(tmp_path, language, n):
    files, node_id, _ = _many_files(language, n)
    arch = analyze_files(tmp_path, language, files)
    m = meta_of(arch, node_id)
    refs = m['unresolved_references']
    assert m['unresolved_reference_total'] == n
    assert len(refs) == min(n, 20)
    assert [r['name'] for r in refs] == [f'n{i:02d}' for i in range(min(n, 20))]
    assert 'external_call_count' not in m


@pytest.mark.parametrize('n', [19, 20, 21])
@pytest.mark.parametrize('language', ['python', 'typescript', 'kotlin'])
def test_V5_symbol_mode_unresolved_count_equals_total(tmp_path, language, n):
    files, node_id, _ = _many_files(language, n)
    root = write_tree(tmp_path / 'proj', files)
    payload, _, _ = run_pipeline(root, tmp_path, 'symbol', '-l', language)
    found = [c for c in of_kind(payload, 'unresolved_boundary') if c['target'] == node_id]
    assert len(found) == 1 and found[0]['metrics']['unresolved_count'] == n


@pytest.mark.parametrize('mode', ['symbol', 'file'])
@pytest.mark.parametrize('language', ['python', 'typescript', 'kotlin'])
def test_V5_C7_thirty_boundary_calls_count_thirty_in_both_modes(tmp_path, language, mode):
    files, node_id, path = _many_files(language, 30)
    root = write_tree(tmp_path / 'proj', files)
    payload, _, _ = run_pipeline(root, tmp_path, mode, '-l', language)
    target = node_id if mode == 'symbol' else 'file:' + path
    found = [c for c in of_kind(payload, 'unresolved_boundary') if c['target'] == target]
    assert len(found) == 1 and found[0]['metrics']['unresolved_count'] == 30


def test_V5_file_mode_count_sums_per_node_totals_not_list_lengths(tmp_path):
    names = [f'n{i:02d}' for i in range(25)]
    more = [f'p{i:02d}' for i in range(25)]
    text = 'from pkg.a import ' + ', '.join(names + more) + '\n\n\ndef one():\n' + ''.join(f'    {x}()\n' for x in names) + \
           '\n\ndef two():\n' + ''.join(f'    {x}()\n' for x in more)
    root = write_tree(tmp_path / 'proj', {'pkg/__init__.py': '', 'pkg/a.py': PKG_A, 'main.py': text})
    payload, _, _ = run_pipeline(root, tmp_path, 'file', '-l', 'python')
    found = [c for c in of_kind(payload, 'unresolved_boundary') if c['target'] == 'file:main.py']
    assert len(found) == 1 and found[0]['metrics']['unresolved_count'] == 50
    arch = analyze_files(tmp_path, 'python', {'pkg/__init__.py': '', 'pkg/a.py': PKG_A, 'main.py': text}, name='sym')
    assert meta_of(arch, 'py:main#one')['unresolved_reference_total'] == 25
    assert len(meta_of(arch, 'py:main#two')['unresolved_references']) == 20


def test_V5_node_without_total_key_falls_back_to_list_length(tmp_path):
    nodes = [sym('a', 'a.py', tokens=5), sym('b', 'b.py', tokens=5)]
    nodes[0].metadata['unresolved_references'] = [
        {'name': f'u{i}', 'resolution': 'unresolved', 'confidence': 'dynamic_required',
         'evidence': {'file_path': 'a.py', 'start_line': 1, 'end_line': 1}} for i in range(3)]
    snap, arch = make_subject({'a.py': 'x\n', 'b.py': 'y\n', 'w.py': 'w\n'}, nodes, [edge('a', 'b')])
    found = of_kind(run_payload(snap, arch, default_weights()), 'unresolved_boundary')
    assert [(c['target'], c['metrics']['unresolved_count']) for c in found] == [('a', 3)]


# =============================================================== V6: Kotlin class scan excludes members (R4; C9)

KT_SVC = '''package com.proj.app

import com.proj.util.h1
import com.proj.util.h2
import com.proj.util.h3
import com.proj.util.h4

fun helper() = 1

class Svc {
    fun m() {
        h1()
        h2()
        helper()
        h3()
        h4()
    }
}
'''
SVC = 'kotlin:com/proj/app/Svc.kt#'


def test_V6_C9_four_unresolved_calls_belong_to_the_method_only(tmp_path):
    arch = analyze_files(tmp_path, 'kotlin', {'com/proj/util/Util.kt': KT_UTIL, 'com/proj/app/Svc.kt': KT_SVC})
    assert meta_of(arch, SVC + 'Svc.m')['unresolved_reference_total'] == 4
    assert_silent(arch, SVC + 'Svc')
    assert edges_between(arch, SVC + 'Svc.m', 'CALLS') == [SVC + 'helper']
    assert edges_between(arch, SVC + 'Svc', 'CALLS') == []


def test_V6_C9_file_mode_unresolved_count_is_four(tmp_path):
    root = write_tree(tmp_path / 'proj', {'com/proj/util/Util.kt': KT_UTIL, 'com/proj/app/Svc.kt': KT_SVC})
    payload, _, _ = run_pipeline(root, tmp_path, 'file', '-l', 'kotlin')
    found = [c for c in of_kind(payload, 'unresolved_boundary') if c['target'] == 'file:com/proj/app/Svc.kt']
    assert len(found) == 1 and found[0]['metrics']['unresolved_count'] == 4


KT_MATRIX = '''package com.proj.app

import com.proj.util.u1
import com.proj.util.u2
import com.proj.util.u3
import com.proj.util.u4

object Store {
    var counter = 0
}

class Svc(var state: Int) {
    fun fm(n: String) {
        u1()
        Class.forName(n)
        state = state + 1
        Store.counter = Store.counter + 1
    }

    class Inner {
        init {
            u2()
            Class.forName(n)
            Store.counter = Store.counter + 1
        }
    }

    object Obj {
        init {
            u3()
            Class.forName(n)
            Store.counter = Store.counter + 1
        }
    }

    val p1 = u4()
    val p2 = Class.forName(n)
    val p3 = Store.counter
}
'''
MX = 'kotlin:com/proj/app/Mat.kt#'
MEMBER_CALLS = {'Svc.fm': 1, 'Svc.Inner': 1, 'Svc.Obj': 1, 'Svc.p1': 1}
MEMBER_DYNAMIC = {'Svc.fm': True, 'Svc.Inner': True, 'Svc.Obj': True, 'Svc.p2': True, 'Svc.p1': False, 'Svc.p3': False}
MEMBER_RW = {'Svc.fm': ('READS', 'WRITES'), 'Svc.Inner': ('READS', 'WRITES'), 'Svc.Obj': ('READS', 'WRITES'),
             'Svc.p3': ('READS',)}


@pytest.fixture(scope='module')
def kt_matrix(tmp_path_factory):
    return analyze_files(tmp_path_factory.mktemp('v6'), 'kotlin',
                         {'com/proj/util/Util.kt': KT_UTIL, 'com/proj/app/Mat.kt': KT_MATRIX})


@pytest.mark.parametrize('member', sorted(MEMBER_CALLS))
def test_V6_call_scan_member_kind_attributed_to_member_not_class(kt_matrix, member):
    assert meta_of(kt_matrix, MX + member)['unresolved_reference_total'] == MEMBER_CALLS[member]
    assert 'unresolved_reference_total' not in meta_of(kt_matrix, MX + 'Svc')
    assert 'unresolved_references' not in meta_of(kt_matrix, MX + 'Svc')


@pytest.mark.parametrize('member', sorted(MEMBER_DYNAMIC))
def test_V6_dynamic_flag_scan_member_kind_attributed_to_member_not_class(kt_matrix, member):
    assert ('dynamic_import' in flags_of(kt_matrix, MX + member)) is MEMBER_DYNAMIC[member]
    assert 'dynamic_import' not in flags_of(kt_matrix, MX + 'Svc')


@pytest.mark.parametrize('member', sorted(MEMBER_RW))
def test_V6_reads_writes_scan_member_kind_attributed_to_member_not_class(kt_matrix, member):
    for relation in MEMBER_RW[member]:
        assert edge_targets_by_label(kt_matrix, MX + member, relation, 'counter'), (member, relation)
    for relation in ('READS', 'WRITES'):
        assert edge_targets_by_label(kt_matrix, MX + 'Svc', relation, 'counter') == []


def test_V6_method_state_access_is_not_duplicated_on_the_class(kt_matrix):
    for relation in ('READS', 'WRITES'):
        assert edge_targets_by_label(kt_matrix, MX + 'Svc.fm', relation, 'state')
        assert edge_targets_by_label(kt_matrix, MX + 'Svc', relation, 'state') == []


KT_CONTROL = '''package com.proj.app

import com.proj.util.u5
import com.proj.util.u6
import com.proj.util.u7

class Ctl(a: Int = u5()) {
    init {
        u6()
    }

    fun x() {
        u7()
    }
}
'''


def test_V6_control_init_block_and_primary_constructor_calls_stay_on_the_class(tmp_path):
    arch = analyze_files(tmp_path, 'kotlin', {'com/proj/util/Util.kt': KT_UTIL, 'com/proj/app/Ctl.kt': KT_CONTROL})
    base = 'kotlin:com/proj/app/Ctl.kt#'
    assert meta_of(arch, base + 'Ctl')['unresolved_reference_total'] == 2
    assert [r['name'] for r in meta_of(arch, base + 'Ctl')['unresolved_references']] == ['u5', 'u6']
    assert meta_of(arch, base + 'Ctl.x')['unresolved_reference_total'] == 1


def test_V6_control_file_mode_counts_class_plus_method(tmp_path):
    root = write_tree(tmp_path / 'proj', {'com/proj/util/Util.kt': KT_UTIL, 'com/proj/app/Ctl.kt': KT_CONTROL})
    payload, _, _ = run_pipeline(root, tmp_path, 'file', '-l', 'kotlin')
    found = [c for c in of_kind(payload, 'unresolved_boundary') if c['target'] == 'file:com/proj/app/Ctl.kt']
    assert len(found) == 1 and found[0]['metrics']['unresolved_count'] == 3


# =============================================================== V7: evidence_spread (R5; C10-C12)

FILES7 = {name: 'x\n' * 12 for name in ('x.py', 'y.py', 'z.py', 'w.py')}
LINE_T = 3


def _spread(tmp_path, evidences, *, target_path='x.py', extra_edges=(), nodes_extra=(), threshold=LINE_T):
    """Target t (in target_path); one source per evidence span; returns the evidence_spread candidates for t."""
    nodes = [sym('t', target_path, 1, 1)]
    edges = []
    for i, span in enumerate(evidences):
        nodes.append(sym(f's{i}', 'w.py', i + 1, i + 1))
        edges.append(edge(f's{i}', 't', evidence=span))
    nodes.extend(nodes_extra)
    edges.extend(extra_edges)
    snap, arch = make_subject(FILES7, nodes, edges)
    payload = run_payload(snap, arch, weights_in(tmp_path, large_node_line_threshold=threshold))
    return [c for c in of_kind(payload, 'evidence_spread') if c['target'] == 't']


def S(path, a, b=None):
    return SourceSpan(path, a, a if b is None else b)


def test_V7_C10_only_own_file_evidence_never_fires_even_with_wide_range(tmp_path):
    assert _spread(tmp_path, [S('x.py', 1), S('x.py', 10)]) == []


def test_V7_zero_evidence_files(tmp_path):
    assert _spread(tmp_path, []) == []


def test_V7_C11_two_external_files_fire_with_zero_line_span(tmp_path):
    found = _spread(tmp_path, [S('y.py', 1), S('z.py', 1)])
    assert len(found) == 1
    assert found[0]['metrics'] == {'file_count': 2, 'line_span': 0, 'line_threshold': LINE_T}
    assert {(r['path'], r['start_line'], r['end_line']) for r in evidence_rows(found[0])} == {('y.py', 1, 1), ('z.py', 1, 1)}


@pytest.mark.parametrize('end,fires', [(LINE_T - 1, False), (LINE_T, False), (LINE_T + 1, True)])
def test_V7_C11_one_external_file_line_range_boundary(tmp_path, end, fires):
    found = _spread(tmp_path, [S('y.py', 1), S('y.py', end)])
    assert len(found) == int(fires)
    if fires:
        assert found[0]['metrics'] == {'file_count': 1, 'line_span': end, 'line_threshold': LINE_T}
        assert {(r['path'], r['start_line']) for r in evidence_rows(found[0])} == {('y.py', 1), ('y.py', end)}


def test_V7_one_external_file_single_short_evidence_does_not_fire(tmp_path):
    assert _spread(tmp_path, [S('y.py', 5)]) == []


def test_V7_own_file_evidence_is_dropped_from_count_range_and_evidence_list(tmp_path):
    found = _spread(tmp_path, [S('x.py', 1), S('y.py', 1), S('z.py', 1)])
    assert len(found) == 1 and found[0]['metrics']['file_count'] == 2
    assert {r['path'] for r in evidence_rows(found[0])} == {'y.py', 'z.py'}
    # own-file evidence far from the external evidence must not stretch the single-file range either
    assert _spread(tmp_path, [S('x.py', 12), S('y.py', 1), S('y.py', 3)]) == []
    wide = _spread(tmp_path, [S('x.py', 12), S('y.py', 1), S('y.py', 4)])
    assert len(wide) == 1 and wide[0]['metrics']['line_span'] == 4
    assert {r['path'] for r in evidence_rows(wide[0])} == {'y.py'}


@pytest.mark.parametrize('relation', ['CONTAINS', 'DECLARES'])
def test_V7_C12_ownership_edge_evidence_is_dropped(tmp_path, relation):
    owner = sym('K', 'x.py', 1, 1, kind='class', provenance='python-core')
    child = sym('t', 'x.py', 2, 2, kind='function', provenance='python-core')
    use = sym('s0', 'w.py', 1, 1)
    edges = [edge('K', 't', relation=relation, evidence=S('z.py', 1)), edge('s0', 't', evidence=S('y.py', 1))]
    snap, arch = make_subject(FILES7, [owner, child, use], edges)
    payload = run_payload(snap, arch, weights_in(tmp_path, large_node_line_threshold=LINE_T))
    assert [c for c in of_kind(payload, 'evidence_spread') if c['target'] == 't'] == []


def test_V7_non_ownership_edge_with_same_shape_still_counts(tmp_path):
    owner = sym('K', 'x.py', 1, 1, kind='class', provenance='python-core')
    child = sym('t', 'x.py', 2, 2, kind='function', provenance='python-core')
    use = sym('s0', 'w.py', 1, 1)
    edges = [edge('K', 't', relation='CALLS', evidence=S('z.py', 1)), edge('s0', 't', evidence=S('y.py', 1))]
    snap, arch = make_subject(FILES7, [owner, child, use], edges)
    payload = run_payload(snap, arch, weights_in(tmp_path, large_node_line_threshold=LINE_T))
    found = [c for c in of_kind(payload, 'evidence_spread') if c['target'] == 't']
    assert len(found) == 1 and found[0]['metrics']['file_count'] == 2


def test_V7_target_without_file_excludes_nothing(tmp_path):
    found = _spread(tmp_path, [S('x.py', 1), S('y.py', 1)], target_path=None)
    assert len(found) == 1 and found[0]['metrics']['file_count'] == 2
    assert {r['path'] for r in evidence_rows(found[0])} == {'x.py', 'y.py'}


# ---- file mode

def _file_spread(tmp_path, evidences, owner_edges=(), threshold=LINE_T):
    nodes = [file_node('t', 'x.py')]
    edges = []
    for i, (path, span) in enumerate(evidences):
        nodes.append(file_node(f'u{i}', path))
        edges.append(edge(f'u{i}', 't', evidence=span))
    files = {'x.py': 'x\n' * 12, 'y.py': 'x\n' * 12, 'z.py': 'x\n' * 12}
    nodes.extend(n for n, _ in owner_edges)
    edges.extend(e for _, e in owner_edges)
    snap, result = converted(files, nodes, edges)
    import json
    from bottlenecks import bottlenecks_to_json
    weights = load_weights(tmp_path, weights_data(large_node_line_threshold=threshold))
    payload = json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, result, weights)))
    return [c for c in of_kind(payload, 'evidence_spread') if c['target'] == 'file:x.py']


def test_V7_file_mode_evidence_in_target_file_is_dropped(tmp_path):
    assert _file_spread(tmp_path, [('y.py', S('x.py', 1)), ('z.py', S('x.py', 10))]) == []


def test_V7_file_mode_two_external_files_fire(tmp_path):
    found = _file_spread(tmp_path, [('y.py', S('y.py', 1)), ('z.py', S('z.py', 1)), ('y.py', S('x.py', 5))])
    assert len(found) == 1 and found[0]['metrics'] == {'file_count': 2, 'line_span': 0, 'line_threshold': LINE_T}
    assert {r['path'] for r in evidence_rows(found[0])} == {'y.py', 'z.py'}


@pytest.mark.parametrize('end,fires', [(LINE_T, False), (LINE_T + 1, True)])
def test_V7_file_mode_one_external_file_boundary(tmp_path, end, fires):
    found = _file_spread(tmp_path, [('y.py', S('y.py', 1)), ('y.py', S('y.py', end))])
    assert len(found) == int(fires)
    if fires:
        assert found[0]['metrics'] == {'file_count': 1, 'line_span': end, 'line_threshold': LINE_T}


@pytest.mark.parametrize('relation', ['CONTAINS', 'DECLARES'])
def test_V7_file_mode_ownership_evidence_is_dropped(tmp_path, relation):
    owner = file_node('K', 'z.py', 'class')
    owned = edge('K', 't', relation=relation, evidence=S('z.py', 1))
    found = _file_spread(tmp_path, [('y.py', S('y.py', 1))], owner_edges=[(owner, owned)])
    assert found == []


# =============================================================== V8: ambiguous_name flag removed (R6; C13)

AMBIGUOUS_CROSS = {
    'python': ({'a.py': 'def shared():\n    return 1\n', 'b.py': 'def shared():\n    return 2\n',
                'main.py': 'def caller():\n    return shared()\n'}, 'shared', 'CALLS'),
    'typescript': ({'a.ts': 'export function shared() { return 1; }', 'b.ts': 'export function shared() { return 2; }',
                    'main.ts': 'export function caller() { return shared(); }'}, 'shared', 'CALLS'),
    'kotlin': ({'a.kt': 'package a\nclass Duplicate\n', 'b.kt': 'package b\nclass Duplicate\n',
                'main.kt': 'package main\nfun caller() = Duplicate()\n'}, 'Duplicate', 'INSTANTIATES'),
}
AMBIGUOUS_SAME_MODULE = {
    'python': {'c.py': 'class A:\n    def save(self):\n        return 1\n\n\nclass B:\n    def save(self):\n        return 2\n'},
    'typescript': {'c.ts': 'export class A { save() { return 1; } }\nexport class B { save() { return 2; } }\n'},
    'kotlin': {'c.kt': 'package c\nclass A { fun save() = 1 }\nclass B { fun save() = 2 }\n'},
}


@pytest.mark.parametrize('language', ['python', 'typescript', 'kotlin'])
def test_V8_cross_module_same_name_has_no_flag_and_keeps_ambiguous_edge(tmp_path, language):
    files, label, relation = AMBIGUOUS_CROSS[language]
    arch = analyze_files(tmp_path, language, files)
    assert [n.id for n in arch.nodes if 'ambiguous_name' in (n.flags or [])] == []
    expected = {n.id for n in arch.nodes if n.label == label}
    assert len(expected) == 2
    caller = next(n for n in arch.nodes if n.label == 'caller')
    ambiguous = [e for e in arch.edges if e.from_id == caller.id and str(e.resolution) == 'ambiguous']
    assert sum(str(getattr(e.relation, 'value', e.relation)) == relation for e in ambiguous) == 1
    for e in ambiguous:
        assert {e.to_id, *e.candidates} == expected


@pytest.mark.parametrize('language', ['python', 'typescript', 'kotlin'])
def test_V8_same_module_method_names_have_no_flag(tmp_path, language):
    arch = analyze_files(tmp_path, language, AMBIGUOUS_SAME_MODULE[language])
    saves = [n for n in arch.nodes if n.label == 'save']
    assert len(saves) == 2
    assert [n.id for n in arch.nodes if 'ambiguous_name' in (n.flags or [])] == []


def test_V8_flags_module_has_no_ambiguous_name_constant():
    import language_analyzers.core.flags as flags
    assert not hasattr(flags, 'AMBIGUOUS_NAME')
    assert 'ambiguous_name' not in {v for v in vars(flags).values() if isinstance(v, str)}


# =============================================================== V9: PageRank R7 (C14, C15)

def test_V9_C14_closed_form_single_edge_for_both_weights():
    # n=2, d=0.85: sa = 0.5 / (1 + 0.425 w), sb = 1 - sa  (derivation in the module docstring of the support helpers)
    results = {}
    for w in (1.0, 0.3):
        r = pagerank({'a': {'b': w}, 'b': {}}, EXACT)
        sa = 0.5 / (1 + 0.425 * w)
        assert r['a'] == pytest.approx(sa, abs=TOL, rel=0)
        assert r['b'] == pytest.approx(1 - sa, abs=TOL, rel=0)
        assert sum(r.values()) == pytest.approx(1.0, abs=TOL, rel=0)
        results[w] = r
    assert results[1.0]['b'] > results[0.3]['b']
    assert results[1.0]['b'] != results[0.3]['b']


def test_V9_mixed_weights_multi_edge_closed_form():
    # a->b 1.0, a->c 0.3, b->a, c->a (all single out-edge weight 1.0): outdeg(a)=2, undelivered u = d*pa*0.35.
    # pa = t + d(pb+pc) + u/3 with pb+pc = 1-pa  =>  pa = (t + d) / (1 + d - 0.85*0.35/3)
    d, t = 0.85, 0.05
    pa = (t + d) / (1 + d - d * 0.35 / 3)
    u = d * pa * 0.35
    pb = t + d * pa * 0.5 + u / 3
    pc = t + d * pa * 0.15 + u / 3
    r = pagerank({'a': {'b': 1.0, 'c': 0.3}, 'b': {'a': 1.0}, 'c': {'a': 1.0}}, EXACT)
    for k, v in {'a': pa, 'b': pb, 'c': pc}.items():
        assert r[k] == pytest.approx(v, abs=TOL, rel=0), k
    assert sum(r.values()) == pytest.approx(1.0, abs=TOL, rel=0)


def test_V9_discount_does_not_vanish_with_out_degree():
    # four 0.3 edges (sum 1.2 > 1) must still be discounted relative to four 1.0 edges
    heavy = pagerank({'a': {x: 1.0 for x in 'bcde'}, **{x: {} for x in 'bcde'}}, EXACT)
    light = pagerank({'a': {x: 0.3 for x in 'bcde'}, **{x: {} for x in 'bcde'}}, EXACT)
    assert all(light[x] < heavy[x] for x in 'bcde')
    ref = ref_pagerank({'a': {x: 0.3 for x in 'bcde'}, **{x: {} for x in 'bcde'}})
    for k in light:
        assert light[k] == pytest.approx(ref[k], abs=TOL, rel=0)


def test_V9_dangling_node_mass_is_spread_uniformly():
    # three nodes, a->b only: closed form via reference iteration of the R7 recurrence
    graph = {'a': {'b': 1.0}, 'b': {}, 'c': {}}
    r = pagerank(graph, EXACT)
    ref = ref_pagerank(graph)
    for k in graph:
        assert r[k] == pytest.approx(ref[k], abs=TOL, rel=0)
    assert r['a'] == pytest.approx(r['c'], abs=TOL, rel=0)
    assert sum(r.values()) == pytest.approx(1.0, abs=TOL, rel=0)


def test_V9_empty_graph_and_single_node():
    assert pagerank({}, EXACT) == {}
    assert pagerank({'only': {}}, EXACT)['only'] == pytest.approx(1.0, abs=TOL, rel=0)


GRAPHS_ALL_ONE = {
    'cycle': {'a': {'b'}, 'b': {'c'}, 'c': {'a'}},
    'star': {'a': {'b', 'c', 'd'}, 'b': {'a'}, 'c': {'a'}, 'd': set()},
    'mixed': {'a': {'b', 'c'}, 'b': {'c'}, 'c': {'a'}, 'd': {'a'}},
}


@pytest.mark.parametrize('name', sorted(GRAPHS_ALL_ONE))
def test_V9_C15_set_input_equals_all_one_map_equals_pre_change_definition(name):
    sets = GRAPHS_ALL_ONE[name]
    maps = {k: {t: 1.0 for t in v} for k, v in sets.items()}
    from_sets = pagerank(sets, EXACT)
    from_maps = pagerank(maps, EXACT)
    before = ref_pagerank_before(sets)
    for k in sets:
        assert from_sets[k] == pytest.approx(from_maps[k], abs=1e-12, rel=0)
        assert from_sets[k] == pytest.approx(before[k], abs=1e-9, rel=0)
        assert from_maps[k] == pytest.approx(ref_pagerank(maps)[k], abs=1e-9, rel=0)


def test_V9_C15_graph_analyzer_uniform_weights_equal_no_weights(tmp_path):
    nodes = symbol_nodes('A', 'B', 'C')
    edges = [edge('A', 'B'), edge('A', 'C'), edge('B', 'A'), edge('C', 'A')]
    uniform = load_weights(tmp_path, weights_data(confidence={k: 1.0 for k in weights_data()['confidence']},
                                                  resolution={k: 1.0 for k in weights_data()['resolution']}))
    def run(weights):
        return GraphAnalyzer(GraphAnalysisConfig(edge_weights=weights, max_iterations=10000)).analyze(
            copy.deepcopy(nodes), list(edges))['node_metrics']
    a, b = run(uniform), run(None)
    for k in a:
        assert a[k]['pagerank'] == pytest.approx(b[k]['pagerank'], abs=1e-12, rel=0)


def test_V9_graph_analyzer_applies_default_profile_weights_to_pagerank():
    nodes = symbol_nodes('A', 'B', 'C')
    edges = [edge('A', 'B'), edge('A', 'C', Confidence.FRAMEWORK_INFERRED), edge('B', 'A'), edge('C', 'A')]
    metrics = GraphAnalyzer(GraphAnalysisConfig(edge_weights=default_weights(), max_iterations=10000)).analyze(
        nodes, edges)['node_metrics']
    ref = ref_pagerank({'A': {'B': 1.0, 'C': 0.3}, 'B': {'A': 1.0}, 'C': {'A': 1.0}})
    for k in ref:
        assert metrics[k]['pagerank'] == pytest.approx(ref[k], abs=TOL, rel=0), k


def _random_graph(rng):
    n = rng.randint(2, 8)
    ids = [f'n{i}' for i in range(n)]
    graph = {i: {} for i in ids}
    for s in ids:
        for t in ids:
            if s != t and rng.random() < 0.35:
                graph[s][t] = rng.choice([1.0, 0.3, 0.6, 0.05])
    return graph


@pytest.mark.parametrize('seed', range(40))
def test_V9_metamorphic_lowering_one_weight_never_raises_its_target_and_sums_stay_one(seed):
    rng = random.Random(20261020 + seed)
    graph = _random_graph(rng)
    pairs = [(s, t) for s, targets in graph.items() for t in targets]
    base = pagerank(graph, EXACT)
    assert sum(base.values()) == pytest.approx(1.0, abs=TOL, rel=0)
    assert all(v > 0 for v in base.values())
    ref = ref_pagerank(graph)
    for k in graph:
        assert base[k] == pytest.approx(ref[k], abs=TOL, rel=0)
    for s, t in pairs:
        lowered = {k: dict(v) for k, v in graph.items()}
        lowered[s][t] = lowered[s][t] * 0.5
        after = pagerank(lowered, EXACT)
        assert sum(after.values()) == pytest.approx(1.0, abs=TOL, rel=0)
        assert after[t] <= base[t] + TOL, (s, t)


# =============================================================== V10: token threshold (R8; C16-C18, Q2, Q6)

BAD_VALUES = [0, -1, True, 1.5, 'x']


@pytest.mark.parametrize('value', BAD_VALUES, ids=['zero', 'minus-one', 'true', 'float', 'string'])
def test_V10_C18_yaml_invalid_token_threshold_is_rejected(tmp_path, value):
    with pytest.raises(EdgeWeightsError):
        load_weights(tmp_path, weights_data(large_node_token_threshold=value))


def test_V10_C18_yaml_valid_values_and_default(tmp_path):
    assert load_weights(tmp_path, weights_data(large_node_token_threshold=1)).large_node_token_threshold == 1
    assert load_weights(tmp_path, weights_data(large_node_token_threshold=777)).large_node_token_threshold == 777
    absent = weights_data()
    assert 'large_node_token_threshold' not in absent
    assert load_weights(tmp_path, absent).large_node_token_threshold == 24000 == DEFAULT_LARGE_NODE_TOKEN_THRESHOLD
    assert load_edge_weights(default_edge_weights_path()).large_node_token_threshold == 24000


def test_V10_Q2_profile_states_24000_explicitly():
    text = default_edge_weights_path().read_text(encoding='utf-8')
    assert 'large_node_token_threshold: 24000' in text


@pytest.mark.parametrize('value', BAD_VALUES, ids=['zero', 'minus-one', 'true', 'float', 'string'])
def test_V10_direct_edge_weights_with_invalid_token_threshold_raises_input_error(value):
    snap, arch = make_subject({'a.py': 'x\n'}, [sym('a', 'a.py')], [])
    bad = dataclasses.replace(default_weights(), large_node_token_threshold=value)
    with pytest.raises(BottleneckInputError, match='edge weight token threshold is invalid'):
        analyze_bottlenecks(snap, arch, bad)


def _symbol_costs(tmp_path, tokens, **options):
    nodes = [sym('big', 'a.py', 1, 2, tokens=tokens, lines=2)]
    snap, arch = make_subject({'a.py': 'x\n' * 12, 'w.py': 'w\n'}, nodes, [])
    return run_payload(snap, arch, weights_in(tmp_path, **options))


def test_V10_C17_symbol_mode_token_boundary_from_observed_cost_three_values(tmp_path):
    cost = _symbol_costs(tmp_path, 120)['dependency_network']['node_metrics']['big']['token_cost']
    assert cost >= 2
    for threshold, fires in ((cost - 1, True), (cost, False), (cost + 1, False)):
        payload = _symbol_costs(tmp_path, 120, large_node_token_threshold=threshold)
        found = of_kind(payload, 'large_node')
        assert bool(found) is fires, threshold
        if fires:
            assert found[0]['metrics']['token_count'] == cost and found[0]['metrics']['token_threshold'] == threshold


def test_V10_line_only_trigger_keeps_four_metrics(tmp_path):
    nodes = [sym('longer', 'a.py', 1, 10, tokens=10, lines=10)]
    snap, arch = make_subject({'a.py': 'x\n' * 12, 'w.py': 'w\n'}, nodes, [])
    payload = run_payload(snap, arch, weights_in(tmp_path, large_node_line_threshold=5))
    found = of_kind(payload, 'large_node')
    cost = payload['dependency_network']['node_metrics']['longer']['token_cost']
    assert len(found) == 1 and cost <= 24000
    assert found[0]['metrics'] == {'line_count': 10, 'line_threshold': 5, 'token_count': cost, 'token_threshold': 24000}


def test_V10_neither_line_nor_token_over_threshold_gives_no_candidate(tmp_path):
    nodes = [sym('small', 'a.py', 1, 5, tokens=10, lines=5)]
    snap, arch = make_subject({'a.py': 'x\n' * 12, 'w.py': 'w\n'}, nodes, [])
    payload = run_payload(snap, arch, weights_in(tmp_path, large_node_line_threshold=5))
    assert of_kind(payload, 'large_node') == []


def _file_payload(tmp_path, name, **options):
    root = write_tree(tmp_path / 'fproj', {'a.py': 'value = 1\n' * 30})
    return pipeline(root, tmp_path, 'file', 'python', name=name, **options)


def test_V10_C17_file_mode_token_boundary_from_observed_cost_three_values(tmp_path):
    cost = _file_payload(tmp_path, 'base')['dependency_network']['node_metrics']['file:a.py']['token_cost']
    assert cost >= 2
    for threshold, fires in ((cost - 1, True), (cost, False), (cost + 1, False)):
        payload = _file_payload(tmp_path, f't{threshold}', large_node_token_threshold=threshold)
        assert payload['edge_weights']['large_node_token_threshold'] == threshold
        assert payload['dependency_network']['node_metrics']['file:a.py']['token_cost'] == cost
        found = [c for c in of_kind(payload, 'large_node') if c['target'] == 'file:a.py']
        assert bool(found) is fires, threshold
        if fires:
            assert found[0]['metrics'] == {'line_count': 30, 'line_threshold': 2000, 'token_count': cost,
                                           'token_threshold': threshold}


def test_V10_Q6_threshold_change_flips_the_result_on_the_same_input(tmp_path):
    base = _file_payload(tmp_path, 'base')
    cost = base['dependency_network']['node_metrics']['file:a.py']['token_cost']
    assert cost > 1
    assert [c for c in of_kind(base, 'large_node') if c['target'] == 'file:a.py'] == []
    low = _file_payload(tmp_path, 'low', large_node_token_threshold=1)
    assert len([c for c in of_kind(low, 'large_node') if c['target'] == 'file:a.py']) == 1


@pytest.mark.parametrize('mode', ['symbol', 'file'])
def test_V10_C16_real_one_line_168kb_python_file(tmp_path, mode):
    text = '# ' + 'a' * (168 * 1024) + '\n'
    root = write_tree(tmp_path / 'proj', {'big.py': text, 'small.py': 'def f():\n    return 1\n'})
    payload, _, _ = run_pipeline(root, tmp_path, mode, '-l', 'python', threshold=2000)
    # run_pipeline writes a weights file only for threshold, so the token threshold is the profile default
    target = 'py:big' if mode == 'symbol' else 'file:big.py'
    found = [c for c in of_kind(payload, 'large_node') if c['target'] == target]
    assert len(found) == 1
    cost = payload['dependency_network']['node_metrics'][target]['token_cost']
    assert cost > 24000
    assert found[0]['metrics'] == {'line_count': 1, 'line_threshold': 2000, 'token_count': cost, 'token_threshold': 24000}
    assert payload['edge_weights']['large_node_token_threshold'] == 24000
    assert not [c for c in of_kind(payload, 'large_node') if 'small' in c['target']]


# =============================================================== V11: Kotlin import line numbers (R9; C19)

def _import_lines(tmp_path, use_text, extra=None):
    files = {'com/a/Foo.kt': 'package com.a\n\nclass Foo\n', 'com/a/Bar.kt': 'package com.a\n\nclass Bar\n',
             'Use.kt': use_text}
    files.update(extra or {})
    arch = analyze_files(tmp_path, 'kotlin', files)
    rows = {}
    for e in arch.edges:
        rel = str(getattr(e.relation, 'value', e.relation))
        if e.from_id == 'kotlin:Use.kt' and rel in ('IMPORTS', 'IMPORTS_SYMBOL'):
            rows.setdefault(e.to_id, set()).add((rel, e.evidence.start_line, e.evidence.end_line))
    return rows


FOO_FILE, FOO_SYMBOL = 'kotlin:com/a/Foo.kt', 'kotlin:com/a/Foo.kt#Foo'
V11_CASES = {
    'first-line': ('import com.a.Foo\n\nclass U\n', 1),
    'one-blank-line': ('package com.c\n\nimport com.a.Foo\n\nclass U\n', 3),
    'two-blank-lines': ('package com.c\n\n\nimport com.a.Foo\n\nclass U\n', 4),
    'blank-lines-to-line-19': ('package com.c\n' + '\n' * 17 + 'import com.a.Foo\n\nclass U\n', 19),
    'indented': ('package com.c\n\n    import com.a.Foo\n\nclass U\n', 3),
    'after-comments': ('package com.c\n// note one\n/* note\n two */\nimport com.a.Foo\n\nclass U\n', 5),
}


@pytest.mark.parametrize('label', sorted(V11_CASES))
def test_V11_import_evidence_is_the_import_keyword_line(tmp_path, label):
    text, line = V11_CASES[label]
    if label == 'blank-lines-to-line-19':
        assert text.splitlines().index('import com.a.Foo') + 1 == 19
    rows = _import_lines(tmp_path, text)
    assert rows[FOO_FILE] == {('IMPORTS', line, line)}
    assert rows[FOO_SYMBOL] == {('IMPORTS_SYMBOL', line, line)}


def test_V11_each_import_in_a_list_gets_its_own_line(tmp_path):
    text = 'package com.c\n\nimport com.a.Foo\n\n\nimport com.a.Bar\n\nclass U\n'
    rows = _import_lines(tmp_path, text)
    assert rows[FOO_SYMBOL] == {('IMPORTS_SYMBOL', 3, 3)}
    assert rows['kotlin:com/a/Bar.kt#Bar'] == {('IMPORTS_SYMBOL', 6, 6)}
