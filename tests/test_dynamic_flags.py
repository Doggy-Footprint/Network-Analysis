"""Evidence for spec f3972ebd2386454f v1 (dynamic_* flags, rules R1-R9; R10/Q1 automated part).
Every expected flag set is written literally from the spec rule or Case table; no analyzer helper is called to compute it.
Tests named *_characterization keep behaviour the spec says must not change."""
import itertools

import pytest

from fixtures.registry import fixture_root
from language_analyzers.core.serialization import architecture_to_dict
from tests.dynamic_flags_support import (FLAG_ATTR, FLAG_EVAL, FLAG_IMPORT, build_kotlin, build_python, build_ts, dyn_flags,
                                         dyn_of, dynamic_edges, dynamic_external_names, imports_edges)
from tests.fact_defects_support import run_pipeline

IMP, ATT, EVA = [FLAG_IMPORT], [FLAG_ATTR], [FLAG_EVAL]
TS_MOD = 'ts:a.ts'


def ts_flags(tmp_path, source, extra=None):
    files = {'a.ts': source, 'b.ts': 'export const b = 1;\n'}
    files.update(extra or {})
    return build_ts(tmp_path, files)


# ------------------------------------------------------------------ V1: TS import/require (R1, C1, C2, C15)

V1_ARGS = {  # label -> (argument text, internal IMPORTS edge expected, dynamic external record names)
    'identifier': ('name', False, []),
    'internal-literal': ("'./b'", True, []),
    'external-literal': ("'fs'", False, ['fs']),
    'empty-string': ("''", False, []),
    'no-argument': ('', False, []),
    'substituted-template': ('`./${x}`', False, []),
}


@pytest.mark.parametrize('call', ['import', 'require'])
@pytest.mark.parametrize('label', sorted(V1_ARGS))
def test_V1_call_and_argument_partitions(tmp_path, call, label):
    arg, internal_edge, external = V1_ARGS[label]
    arch = ts_flags(tmp_path, f'const m = {call}({arg});\n')
    assert dyn_of(arch, TS_MOD) == IMP
    assert dyn_of(arch, 'ts:b.ts') == []
    assert dynamic_edges(arch) == ([(TS_MOD, 'ts:b.ts')] if internal_edge else [])
    assert imports_edges(arch) == ([(TS_MOD, 'ts:b.ts', 'dynamic_required')] if internal_edge else [])
    assert dynamic_external_names(arch, TS_MOD) == external


@pytest.mark.parametrize('source', ['const r = require.resolve(x);\n', 'const r = x.require(y);\n'],
                         ids=['require.resolve', 'member.require'])
def test_V1_negative_partitions_do_not_flag(tmp_path, source):
    arch = ts_flags(tmp_path, source)
    assert dyn_of(arch, TS_MOD) == []
    assert dynamic_edges(arch) == []


def test_V1_C15_require_without_arguments_does_not_raise_and_flags_module_only_once(tmp_path):
    arch = ts_flags(tmp_path, 'export function f() {}\nrequire();\n')
    assert dyn_of(arch, TS_MOD) == IMP
    assert dyn_of(arch, 'ts:a.ts#f') == []


def test_V1_flag_lands_on_module_node_even_when_call_is_inside_a_function(tmp_path):
    arch = ts_flags(tmp_path, 'export function f(n) {\n  return require(n);\n}\nexport function g() {}\n')
    assert dyn_of(arch, TS_MOD) == IMP
    assert dyn_of(arch, 'ts:a.ts#f') == []
    assert dyn_of(arch, 'ts:a.ts#g') == []


# ------------------------------------------------------------------ V2: TS eval/Function (R2, C3, C4)

V2_CASES = {
    'eval-call': ('eval(x);', EVA),
    'Function-call': ('Function(x);', EVA),
    'new-Function': ('new Function(x);', EVA),
    'window.eval': ('window.eval(x);', []),
    'member-Function-call': ('o.Function();', []),
    'new-member-Function': ('new o.Function();', []),
    'evaluate': ('evaluate(x);', []),
}


@pytest.mark.parametrize('label', sorted(V2_CASES))
def test_V2_eval_partitions(tmp_path, label):
    source, expected = V2_CASES[label]
    arch = ts_flags(tmp_path, source + '\n')
    assert dyn_of(arch, TS_MOD) == expected


def test_V2_C3_Function_with_several_arguments(tmp_path):
    assert dyn_of(ts_flags(tmp_path, "const f = Function('a', body);\n"), TS_MOD) == EVA


# ------------------------------------------------------------------ V3: TS Reflect/defineProperty (R3, C5, C6)

V3_FUNCS = ['Reflect.get', 'Reflect.set', 'Reflect.has', 'Reflect.defineProperty', 'Reflect.deleteProperty',
            'Object.defineProperty']
V3_SECOND = {  # label -> (second-argument text or None for absent, flagged)
    'identifier': ('k', True),
    'string': ("'a'", False),
    'number': ('0', False),
    'plain-template': ('`a`', False),
    'substituted-template': ('`a${x}`', True),
    'absent': (None, True),
}
V3_CASES = [(f, label) for f in V3_FUNCS for label in ('identifier', 'string')]
V3_CASES += [('Reflect.get', label) for label in V3_SECOND if label not in ('identifier', 'string')]


@pytest.mark.parametrize('func,label', V3_CASES, ids=[f'{f}-{l}' for f, l in V3_CASES])
def test_V3_second_argument_decision_table(tmp_path, func, label):
    second, flagged = V3_SECOND[label]
    args = 'o' if second is None else f'o, {second}'
    arch = ts_flags(tmp_path, f'{func}({args});\n')
    assert dyn_of(arch, TS_MOD) == (ATT if flagged else [])


@pytest.mark.parametrize('args', ['f, t, a', "f, 'a', []", 'f, null, 1'], ids=['identifiers', 'string-arg', 'literal-args'])
def test_V3_Reflect_apply_is_always_flagged(tmp_path, args):
    assert dyn_of(ts_flags(tmp_path, f'Reflect.apply({args});\n'), TS_MOD) == ATT


@pytest.mark.parametrize('source', ['const v = obj[name];', 'Reflect.ownKeys(o);', 'Object.keys(o);'],
                         ids=['computed-access', 'Reflect.ownKeys', 'Object.keys'])
def test_V3_negative_partitions(tmp_path, source):
    assert dyn_of(ts_flags(tmp_path, source + '\n'), TS_MOD) == []


def test_V3_first_argument_literal_does_not_suppress_the_flag(tmp_path):
    assert dyn_of(ts_flags(tmp_path, "Reflect.get('lit', k);\n"), TS_MOD) == ATT


def test_V3_independent_triggers_in_one_file_combine(tmp_path):
    arch = ts_flags(tmp_path, "require(n);\neval(x);\nReflect.get(o, k);\n")
    assert dyn_of(arch, TS_MOD) == sorted([FLAG_IMPORT, FLAG_EVAL, FLAG_ATTR])


# ------------------------------------------------------------------ Kotlin helpers

KT_FILE = 'a/X.kt'
KT_TOP = 'kotlin:a/X.kt#run'


def kt_top(tmp_path, statement):
    source = f'package a\n\nfun run(cls: Class<*>, n: String) {{\n    {statement}\n}}\n\nfun other() {{}}\n'
    return build_kotlin(tmp_path, {KT_FILE: source})


# ------------------------------------------------------------------ V4: Kotlin class loading (R4, C7, C9, C15)

V4_CASES = {
    'Class.forName': ('Class.forName(n)', IMP),
    'qualified-Class.forName-literal': ('java.lang.Class.forName("a.B")', IMP),
    'ServiceLoader.load': ('ServiceLoader.load(Svc::class.java)', IMP),
    'loader.loadClass': ('loader.loadClass(n)', IMP),
    'receiverless-forName': ('forName(n)', []),
    'receiverless-loadClass': ('loadClass(n)', []),
    'Foo.forName': ('Foo.forName(n)', []),
    'x.load': ('x.load()', []),
}


@pytest.mark.parametrize('label', sorted(V4_CASES))
def test_V4_class_loading_decision_table(tmp_path, label):
    statement, expected = V4_CASES[label]
    arch = kt_top(tmp_path, statement)
    assert dyn_of(arch, KT_TOP) == expected
    assert dyn_of(arch, 'kotlin:a/X.kt#other') == []
    assert dynamic_edges(arch) == []


def test_V4_attribution_method_and_enclosing_class_both_flagged(tmp_path):
    source = ('package a\n\nclass X {\n    fun m(n: String) {\n        Class.forName(n)\n    }\n\n    fun quiet() {}\n}\n\n'
              'class Y {\n    fun idle() {}\n}\n\nfun top(n: String) {\n    Class.forName(n)\n}\n\nfun calm() {}\n')
    arch = build_kotlin(tmp_path, {KT_FILE: source})
    assert dyn_of(arch, 'kotlin:a/X.kt#X.m') == IMP
    assert dyn_of(arch, 'kotlin:a/X.kt#X') == IMP
    assert dyn_of(arch, 'kotlin:a/X.kt#top') == IMP
    for quiet in ('kotlin:a/X.kt#X.quiet', 'kotlin:a/X.kt#Y', 'kotlin:a/X.kt#Y.idle', 'kotlin:a/X.kt#calm'):
        assert dyn_of(arch, quiet) == []
    assert dynamic_edges(arch) == []


def test_V4_C15_syntax_error_file_does_not_raise_and_other_files_still_analyzed(tmp_path):
    files = {
        'a/X.kt': 'package a\n\nfun ok(n: String) {\n    Class.forName(n)\n}\n\nfun = = ;\n',
        'a/Y.kt': 'package a\n\nfun y(n: String) {\n    Class.forName(n)\n}\n',
    }
    arch = build_kotlin(tmp_path, files)
    assert dyn_of(arch, 'kotlin:a/X.kt#ok') == IMP
    assert dyn_of(arch, 'kotlin:a/Y.kt#y') == IMP


# ------------------------------------------------------------------ V5: Kotlin reflective member lookup (R5, C8, C9)

V5_CASES = [('getMethod', 'identifier', 'n', True), ('getMethod', 'literal', '"run"', False),
            ('getMethod', 'interpolated', '"$n"', True), ('getMethod', 'no-argument', '', True),
            ('getMethod', 'literal-plus-extra', '"run", Int::class.java', False)]
for _name in ('getDeclaredMethod', 'getField', 'getDeclaredField'):
    V5_CASES += [(_name, 'identifier', 'n', True), (_name, 'literal', '"run"', False)]


@pytest.mark.parametrize('method,label,args,flagged', V5_CASES, ids=[f'{m}-{l}' for m, l, _, _ in V5_CASES])
def test_V5_member_lookup_argument_partitions(tmp_path, method, label, args, flagged):
    arch = kt_top(tmp_path, f'cls.{method}({args})')
    assert dyn_of(arch, KT_TOP) == (ATT if flagged else [])
    assert dyn_of(arch, 'kotlin:a/X.kt#other') == []


def test_V5_receiverless_getMethod_is_not_flagged(tmp_path):
    assert dyn_of(kt_top(tmp_path, 'getMethod(n)'), KT_TOP) == []


def test_V5_attribution_includes_enclosing_class(tmp_path):
    source = 'package a\n\nclass X {\n    fun m(c: Class<*>, n: String) {\n        c.getMethod(n)\n    }\n}\n'
    arch = build_kotlin(tmp_path, {KT_FILE: source})
    assert dyn_of(arch, 'kotlin:a/X.kt#X.m') == ATT
    assert dyn_of(arch, 'kotlin:a/X.kt#X') == ATT


# ------------------------------------------------------------------ Python helpers

PY_MOD = 'py:mod'
PY_RUN = 'py:mod#run'


def py_arch(tmp_path, source, extra=None):
    files = {'mod.py': source}
    files.update(extra or {})
    return build_python(tmp_path, files)


# ------------------------------------------------------------------ V6: Python aliases (R6, C10, C14)

V6_FORMS = {  # label -> (alias statement, call on a computed arg, call on literal "pkg.mod", flag, literal edge)
    'from-importlib-as': ('from importlib import import_module as im', 'im(n)', 'im("pkg.mod")', IMP, True),
    'import-importlib-as': ('import importlib as il', 'il.import_module(n)', 'il.import_module("pkg.mod")', IMP, True),
    'from-builtins-as': ('from builtins import eval as e', 'e(n)', 'e("pkg.mod")', EVA, False),
    'import-builtins-as': ('import builtins as b', 'b.eval(n)', 'b.eval("pkg.mod")', EVA, False),
}
PKG = {'pkg/__init__.py': '', 'pkg/mod.py': 'X = 1\n'}


def v6_source(position, alias, call):
    if position == 'top':
        return f'{alias}\n\ndef run(n):\n    return {call}\n'
    if position == 'if':
        return f'if True:\n    {alias}\n\ndef run(n):\n    return {call}\n'
    if position == 'try':
        return f'try:\n    {alias}\nexcept ImportError:\n    pass\n\ndef run(n):\n    return {call}\n'
    assert position == 'body'
    return f'def run(n):\n    {alias}\n    return {call}\n'


V6_POSITIONS = ['top', 'if', 'try', 'body']


@pytest.mark.parametrize('position', V6_POSITIONS)
@pytest.mark.parametrize('form', sorted(V6_FORMS))
def test_V6_alias_form_by_position_flags_scanning_symbol(tmp_path, form, position):
    alias, computed, _, flag, _ = V6_FORMS[form]
    arch = py_arch(tmp_path, v6_source(position, alias, computed), PKG)
    assert dyn_of(arch, PY_RUN) == flag
    assert dynamic_edges(arch) == []


@pytest.mark.parametrize('position', V6_POSITIONS)
@pytest.mark.parametrize('form', sorted(V6_FORMS))
def test_V6_literal_alias_argument_also_creates_dynamic_required_edge(tmp_path, form, position):
    alias, _, literal, flag, edge = V6_FORMS[form]
    arch = py_arch(tmp_path, v6_source(position, alias, literal), PKG)
    assert dyn_of(arch, PY_RUN) == flag
    assert dynamic_edges(arch) == ([(PY_RUN, 'py:pkg.mod')] if edge else [])


# A receiver call named import_module is already flagged by name before this spec, so that form cannot be a negative.
@pytest.mark.parametrize('form', sorted(set(V6_FORMS) - {'import-importlib-as'}))
def test_V6_negative_alias_defined_in_another_function_body(tmp_path, form):
    alias, computed, _, _, _ = V6_FORMS[form]
    source = f'def other():\n    {alias}\n\ndef run(n):\n    return {computed}\n'
    arch = py_arch(tmp_path, source, PKG)
    assert dyn_of(arch, PY_RUN) == []
    assert dyn_of(arch, 'py:mod#other') == []


@pytest.mark.parametrize('statement,call', [('from m import im', 'im(n)'), ('from m import eval as e', 'e(n)'),
                                            ('import m as b', 'b.eval(n)')],
                         ids=['from-other-module', 'from-other-module-eval', 'import-other-module'])
def test_V6_C14_alias_from_another_module_is_not_an_alias(tmp_path, statement, call):
    extra = {'m.py': 'def im(x):\n    return x\n\neval = None\nimport_module = None\n'}
    arch = py_arch(tmp_path, f'{statement}\n\ndef run(n):\n    return {call}\n', extra)
    assert dyn_of(arch, PY_RUN) == []


@pytest.mark.parametrize('alias,name,call', [('from importlib import import_module as im', 'im', 'im(n)'),
                                             ('from builtins import eval as e', 'e', 'e(n)')],
                         ids=['import-alias', 'eval-alias'])
def test_V6_C14_alias_name_reassigned_locally_is_not_an_alias(tmp_path, alias, name, call):
    source = f'{alias}\n\ndef run(n, f):\n    {name} = f\n    return {call}\n'
    assert dyn_of(py_arch(tmp_path, source), PY_RUN) == []


def test_V6_D9_alias_resolution_only_adds_flags_characterization(tmp_path):
    # eval(c) was flagged by its own name before alias handling; aliasing the name to another builtin must keep it.
    source = 'from builtins import len as eval\n\ndef run(c):\n    return eval(c)\n'
    assert dyn_of(py_arch(tmp_path, source), PY_RUN) == EVA


def test_V6_unaliased_direct_calls_are_unchanged_characterization(tmp_path):
    source = 'import importlib\n\ndef run(n):\n    eval(n)\n    return importlib.import_module(n)\n'
    assert dyn_of(py_arch(tmp_path, source), PY_RUN) == sorted([FLAG_EVAL, FLAG_IMPORT])


# ------------------------------------------------------------------ V7: Python builtins receiver (R7, C11)

V7_CASES = {
    'builtins.eval': ('builtins.eval(c)', EVA),
    'builtins.exec': ('builtins.exec(c)', EVA),
    'builtins.getattr-nonconstant': ('builtins.getattr(o, n)', ATT),
    'builtins.getattr-constant': ('builtins.getattr(o, "x")', []),
}


@pytest.mark.parametrize('label', sorted(V7_CASES))
def test_V7_builtins_receiver_partitions(tmp_path, label):
    call, expected = V7_CASES[label]
    source = f'import builtins\n\ndef run(o, n, c):\n    return {call}\n'
    assert dyn_of(py_arch(tmp_path, source), PY_RUN) == expected


def test_V7_aliased_builtins_receiver(tmp_path):
    source = 'import builtins as b\n\ndef run(o, n):\n    return b.getattr(o, n)\n'
    assert dyn_of(py_arch(tmp_path, source), PY_RUN) == ATT


def test_V7_C11_from_builtins_alias_eval_and_receiver_alias_getattr_in_one_module(tmp_path):
    source = ('from builtins import eval as e\nimport builtins as b\n\n'
              'def one(c):\n    return e(c)\n\ndef two(o, n):\n    return b.getattr(o, n)\n\ndef three(o):\n    return b.getattr(o, "x")\n')
    arch = py_arch(tmp_path, source)
    assert dyn_of(arch, 'py:mod#one') == EVA
    assert dyn_of(arch, 'py:mod#two') == ATT
    assert dyn_of(arch, 'py:mod#three') == []


# ------------------------------------------------------------------ V8: Python __dict__[k] (R8, C12)

V8_CASES = {
    'load-name': ('return o.__dict__[n]', ATT),
    'load-str-constant': ('return o.__dict__["x"]', []),
    'load-int-constant': ('return o.__dict__[1]', ATT),
    'load-fstring': ('return o.__dict__[f"a{n}"]', ATT),
    'store-name': ('o.__dict__[n] = v', ATT),
    'del-name': ('del o.__dict__[n]', ATT),
    'store-int-constant': ('o.__dict__[2] = v', ATT),
    'del-fstring': ('del o.__dict__[f"a{n}"]', ATT),
    'store-str-constant': ('o.__dict__["x"] = v', []),
    'del-str-constant': ('del o.__dict__["x"]', []),
    'other-mapping-name': ('return o.mapping[n]', []),
    'other-mapping-store': ('o.mapping[n] = v', []),
}


@pytest.mark.parametrize('label', sorted(V8_CASES))
def test_V8_dunder_dict_subscript_partitions(tmp_path, label):
    body, expected = V8_CASES[label]
    source = f'def run(o, n, v):\n    {body}\n'
    assert dyn_of(py_arch(tmp_path, source), PY_RUN) == expected


# ------------------------------------------------------------------ V9: Python attribute hooks (R9, C13)

HOOK_RAISE = '        raise AttributeError(n)\n'


@pytest.mark.parametrize('hook', ['__getattr__', '__getattribute__', '__setattr__', '__delattr__'])
def test_V9_hook_method_flags_class_node_only(tmp_path, hook):
    source = f'class A:\n    def {hook}(self, n):\n{HOOK_RAISE}\nclass Plain:\n    def f(self):\n        pass\n'
    arch = py_arch(tmp_path, source)
    assert dyn_of(arch, 'py:mod#A') == ATT
    assert dyn_of(arch, f'py:mod#A.{hook}') == []
    assert dyn_of(arch, 'py:mod#Plain') == []
    assert dyn_of(arch, 'py:mod#Plain.f') == []
    assert dyn_of(arch, PY_MOD) == []


def test_V9_async_def_hook(tmp_path):
    source = f'class B:\n    async def __setattr__(self, n, v):\n{HOOK_RAISE}'
    arch = py_arch(tmp_path, source)
    assert dyn_of(arch, 'py:mod#B') == ATT
    assert dyn_of(arch, PY_MOD) == []


def test_V9_hook_in_nested_class_flags_inner_only(tmp_path):
    source = f'class Outer:\n    class Inner:\n        def __getattr__(self, n):\n    {HOOK_RAISE}\n    def f(self):\n        pass\n'
    arch = py_arch(tmp_path, source)
    assert dyn_of(arch, 'py:mod#Outer.Inner') == ATT
    assert dyn_of(arch, 'py:mod#Outer') == []
    assert dyn_of(arch, 'py:mod#Outer.f') == []


def test_V9_C13_module_level_getattr_flags_module_node(tmp_path):
    source = 'def __getattr__(name):\n    raise AttributeError(name)\n\ndef helper():\n    pass\n'
    arch = py_arch(tmp_path, source)
    assert dyn_of(arch, PY_MOD) == ATT
    assert dyn_of(arch, 'py:mod#helper') == []


@pytest.mark.parametrize('name', ['__setattr__', '__dir__'])
def test_V9_module_level_setattr_and_dir_do_not_flag(tmp_path, name):
    source = f'def {name}(*args):\n    return None\n'
    assert dyn_of(py_arch(tmp_path, source), PY_MOD) == []


def test_V9_C13_class_and_module_hooks_together(tmp_path):
    source = ('def __getattr__(name):\n    raise AttributeError(name)\n\n'
              'class A:\n    def __getattr__(self, n):\n        raise AttributeError(n)\n\n'
              'class B:\n    async def __setattr__(self, n, v):\n        pass\n')
    flags = dyn_flags(py_arch(tmp_path, source))
    assert flags[PY_MOD] == ATT and flags['py:mod#A'] == ATT and flags['py:mod#B'] == ATT
    assert flags['py:mod#A.__getattr__'] == [] and flags['py:mod#B.__setattr__'] == []


# ------------------------------------------------------------------ V10 (automated part): output shape unchanged (Q1)

# Independent source: language_analyzers/core/serialization.py field lists and the bottlenecks.v8/v6 shape recorded by
# tests/test_fact_defects.py::EXPECTED_SHAPE; the schema must not change (spec Scope, Signatures).
NODE_KEYS = ['category', 'color', 'cost', 'display_label', 'docstring', 'exported', 'flags', 'group', 'id', 'kind', 'label',
             'language', 'metadata', 'provenance', 'shape', 'signature', 'size', 'span', 'symbol_path', 'title']
EDGE_KEYS = ['arrows', 'candidates', 'color', 'confidence', 'dashes', 'evidence', 'from_id', 'label', 'metadata', 'relation',
             'resolution', 'title', 'to_id', 'weight']
CANDIDATE_BASE = {'coverage', 'evidence', 'id', 'kind', 'metrics', 'status', 'target'}
SHAPE = {
    'file': ('bottlenecks.v8', '6', ['candidates', 'coverage', 'dependency_network', 'edge_weights', 'granularity',
                                     'limitations', 'schema', 'snapshot', 'versions']),
    'symbol': ('bottlenecks.v6', '5', ['candidates', 'coverage', 'dependency_network', 'edge_weights', 'limitations',
                                       'schema', 'snapshot', 'versions']),
}
KNOWN_FLAGS = {'dynamic_import', 'dynamic_attr', 'dynamic_eval', 'reexport', 'ambiguous_name', 'generated', 'vendored', 'test'}
FIXTURES = [('typescript-nestjs-realworld', ('-l', 'typescript', '-f', 'nestjs')), ('futuramaapi', ('-l', 'python'))]


@pytest.mark.parametrize('granularity', ['file', 'symbol'])
@pytest.mark.parametrize('fixture,args', FIXTURES, ids=[f for f, _ in FIXTURES])
def test_V10_Q1_json_key_sets_and_schema_version_unchanged(tmp_path_factory, fixture, args, granularity):
    payload, _, arch = run_pipeline(fixture_root(fixture), tmp_path_factory.mktemp(f'{fixture}-{granularity}'), granularity, *args)
    schema, arch_version, top = SHAPE[granularity]
    assert payload['schema'] == schema
    assert sorted(payload) == top
    data = architecture_to_dict(arch)
    assert data['schema_version'] == arch_version
    assert data['nodes'] and data['edges']
    for node in data['nodes']:
        assert sorted(node) == NODE_KEYS
        assert set(node['flags']) <= KNOWN_FLAGS
    for edge in data['edges']:
        assert sorted(edge) == EDGE_KEYS
    allowed = CANDIDATE_BASE | ({'structure'} if granularity == 'file' else set())
    for candidate in payload['candidates']:
        assert CANDIDATE_BASE <= set(candidate) <= allowed, candidate['kind']
