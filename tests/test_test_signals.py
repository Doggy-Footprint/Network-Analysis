from pathlib import Path

import pytest

from tests.delta_support import SYMBOL_COLUMNS, TEST_CASE_COLUMNS
from tests.test_signals_support import (AMBIGUOUS, BASE_COMMIT, DR, EXACT, FI, SC, SI, UNIQUE, UNRESOLVED, analyze, arch, base_worktree,
                                        branch_count, case_row, cases_of, counts_of, decode_symbols, indent, make_repo,
                                        reach_of, rel, remove_worktree, run_cli, run_file_granularity, sym, symbols_api)

# ---------------------------------------------------------------------------------------------------------------------
# V01 branch_count, table B constructs per language. Every expected integer is counted by hand from table B.
# ---------------------------------------------------------------------------------------------------------------------

PY_CASES = {
    'if': ('def f(x):\n    if x:\n        return 1\n    return 0\n', 1),
    'elif-each-counts': ('def f(x):\n    if x == 1:\n        return 1\n    elif x == 2:\n        return 2\n    elif x == 3:\n'
                         '        return 3\n    else:\n        return 0\n', 3),
    'for': ('def f(xs):\n    for x in xs:\n        print(x)\n', 1),
    'async-for': ('async def f(xs):\n    async for x in xs:\n        print(x)\n', 1),
    'while': ('def f(x):\n    while x:\n        x -= 1\n', 1),
    'except-handlers-each': ('def f():\n    try:\n        g()\n    except ValueError:\n        pass\n    except (KeyError, TypeError):\n'
                             '        pass\n    else:\n        pass\n    finally:\n        pass\n', 2),
    'conditional-expression': ('def f(x):\n    return 1 if x else 2\n', 1),
    'comprehension-if-clauses-each': ('def f(xs):\n    return [x for x in xs if x if x > 1]\n', 2),
    'dict-comprehension-if': ('def f(d):\n    return {k: v for k, v in d if v}\n', 1),
    'match-case-each': ('def f(x):\n    match x:\n        case 1:\n            return 1\n        case 2 | 3:\n            return 2\n'
                        '        case _:\n            return 0\n', 3),
    'bool-operands-minus-one': ('def f(a, b, c):\n    return a and b and c\n', 2),
    'bool-mixed-operators': ('def f(a, b, c, d):\n    return a or b and c or d\n', 3),
    'try-with-comparison-not-counted': ('def f():\n    try:\n        pass\n    finally:\n        pass\n    with open("x") as h:\n'
                                        '        pass\n    return 1 == 2\n', 0),
    'no-branches': ('def f():\n    return 1\n', 0),
    'all-together': ('def f(xs, a, b):\n    if a:\n        for x in xs:\n            while x:\n                x -= 1\n    try:\n'
                     '        pass\n    except Exception:\n        pass\n    y = 1 if a else 2\n    z = [i for i in xs if i]\n'
                     '    return a and b\n', 7),
    'lambda-included': ('def f(x):\n    g = lambda y: 1 if y else 2\n    h = lambda a, b: a or b\n    return g(x) + h(x, x)\n', 2),
}


@pytest.mark.parametrize('source, expected', PY_CASES.values(), ids=PY_CASES.keys())
def test_V01_python_branch_constructs(source, expected):
    assert branch_count('a.py', source, 1, 'f') == expected


TS_CASES = {
    'if': ('function f(x: number) {\n  if (x) {\n    return 1;\n  }\n  return 0;\n}\n', 1),
    'else-if-each-counts': ('function f(a: boolean, b: boolean) {\n  if (a) {\n    return 1;\n  } else if (b) {\n    return 2;\n'
                            '  } else {\n    return 3;\n  }\n}\n', 2),
    'for': ('function f(n: number) {\n  for (let i = 0; i < n; i++) {\n    g(i);\n  }\n}\n', 1),
    'for-in': ('function f(o: object) {\n  for (const k in o) {\n    g(k);\n  }\n}\n', 1),
    'for-of': ('function f(xs: number[]) {\n  for (const v of xs) {\n    g(v);\n  }\n}\n', 1),
    'while': ('function f(x: number) {\n  while (x) {\n    x--;\n  }\n}\n', 1),
    'do-while': ('function f(x: number) {\n  do {\n    x--;\n  } while (x);\n}\n', 1),
    'catch': ('function f() {\n  try {\n    g();\n  } catch (e) {\n    h();\n  } finally {\n    k();\n  }\n}\n', 1),
    'ternary': ('function f(x: number) {\n  return x ? 1 : 2;\n}\n', 1),
    'switch-non-default-cases': ('function f(x: number) {\n  switch (x) {\n    case 1:\n      return 1;\n    case 2:\n    case 3:\n'
                                 '      return 2;\n    default:\n      return 0;\n  }\n}\n', 3),
    'and-or': ('function f(a: boolean, b: boolean, c: boolean) {\n  return a && b || c;\n}\n', 2),
    'and-and': ('function f(a: boolean, b: boolean, c: boolean) {\n  return a && b && c;\n}\n', 2),
    'nullish': ('function f(a: number | null, b: number) {\n  return a ?? b;\n}\n', 1),
    'bitwise-and-arithmetic-not-counted': ('function f(a: number, b: number, c: number) {\n  return (a & b) | (c + 1);\n}\n', 0),
    'no-branches': ('function f() {\n  return 1;\n}\n', 0),
    'all-together': ('function f(a: any, b: any, n: number) {\n  if (a) {\n    g();\n  }\n  for (let i = 0; i < n; i++) {\n    g();\n  }\n'
                     '  while (n) {\n    n--;\n  }\n  try {\n    g();\n  } catch (e) {\n    h();\n  }\n  const t = a ? 1 : 2;\n'
                     '  switch (n) {\n    case 1:\n      break;\n    case 2:\n      break;\n    default:\n      break;\n  }\n'
                     '  return a && b;\n}\n', 8),
    'arrow-and-function-expression-included': ('function f(xs: number[]) {\n  const a = xs.map((x) => x ? 1 : 2);\n'
                                               '  const g = function (y: number) {\n    return y ? 1 : 2;\n  };\n'
                                               '  const h = (p: boolean, q: boolean) => p && q;\n  return [a, g, h];\n}\n', 3),
    'exported-declaration': ('export function f(x: number) {\n  if (x) {\n    return 1;\n  }\n  return 0;\n}\n', 1),
}


@pytest.mark.parametrize('source, expected', TS_CASES.values(), ids=TS_CASES.keys())
def test_V01_typescript_branch_constructs(source, expected):
    assert branch_count('a.ts', source, 1, 'f') == expected


@pytest.mark.parametrize('extension', ['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'])
def test_V01_typescript_javascript_extensions_are_all_supported(extension):
    assert branch_count('src/a' + extension, 'function f(x) {\n  if (x) {\n    return 1;\n  }\n  return 0;\n}\n', 1, 'f') == 1


KT_CASES = {
    'if': ('fun f(x: Int): Int {\n    if (x > 0) {\n        return 1\n    }\n    return 0\n}\n', 1),
    'else-if-each-counts': ('fun f(a: Boolean, b: Boolean): Int = if (a) 1 else if (b) 2 else 3\n', 2),
    'for': ('fun f(n: Int) {\n    for (i in 0..n) {\n        g(i)\n    }\n}\n', 1),
    'while': ('fun f(n: Int) {\n    var x = n\n    while (x > 0) {\n        x--\n    }\n}\n', 1),
    'do-while': ('fun f(n: Int) {\n    var x = n\n    do {\n        x--\n    } while (x > 0)\n}\n', 1),
    'catch-each': ('fun f() {\n    try {\n        g()\n    } catch (e: Exception) {\n        h()\n    } catch (e: Error) {\n        h()\n'
                   '    } finally {\n        k()\n    }\n}\n', 2),
    'when-non-else-entries': ('fun f(x: Int) {\n    when (x) {\n        1 -> a()\n        2 -> b()\n        else -> c()\n    }\n}\n', 2),
    'when-without-subject': ('fun f(x: Int) {\n    when {\n        x > 0 -> a()\n        else -> b()\n    }\n}\n', 1),
    'elvis': ('fun f(a: Int?, b: Int): Int {\n    return a ?: b\n}\n', 1),
    'and-or': ('fun f(a: Boolean, b: Boolean, c: Boolean): Boolean {\n    return a && b || c\n}\n', 2),
    'safe-call-not-null-assertion-and-comparison-not-counted': ('fun f(a: String?): Boolean {\n    val n = a?.length\n    return n!! > 1\n}\n', 0),
    'no-branches': ('fun f(): Int {\n    return 1\n}\n', 0),
    'all-together': ('fun f(a: Int?, b: Boolean, xs: List<Int>): Int {\n    if (b) {\n        for (x in xs) {\n            println(x)\n        }\n'
                     '    }\n    var n = 3\n    while (n > 0) {\n        n--\n    }\n    do {\n        n++\n    } while (n < 2)\n'
                     '    try {\n        g()\n    } catch (e: Exception) {\n        h()\n    }\n    when (n) {\n        1 -> g()\n'
                     '        2 -> g()\n        else -> h()\n    }\n    val y = a ?: 0\n'
                     '    return if (b && y > 0 || n > 1) y else 0\n}\n', 11),
    'lambda-included': ('fun f(xs: List<Int?>): List<Int> {\n    return xs.map { if (it != null) 1 else 0 }.map { it ?: 0 }\n}\n', 2),
}


@pytest.mark.parametrize('source, expected', KT_CASES.values(), ids=KT_CASES.keys())
def test_V01_kotlin_branch_constructs(source, expected):
    assert branch_count('A.kt', source, 1, 'f') == expected


PY_NESTED = ('def outer(x):\n    if x:\n        pass\n    def inner(y):\n        if y:\n            pass\n        if y > 1:\n            pass\n'
             '    class K:\n        def m(self):\n            if x:\n                pass\n    return 1\n')
TS_NESTED = ('function outer(x: number) {\n  if (x) {\n    return 1;\n  }\n  function inner(y: number) {\n    if (y) {\n      return 2;\n    }\n'
             '    if (y > 1) {\n      return 3;\n    }\n  }\n  class K {\n    m() {\n      if (x) {\n        return 4;\n      }\n    }\n  }\n'
             '  return 0;\n}\n')
KT_NESTED = ('fun outer(x: Int): Int {\n    if (x > 0) {\n        return 1\n    }\n    fun inner(y: Int): Int {\n        if (y > 0) { return 2 }\n'
             '        return if (y > 1) 3 else 4\n    }\n    class L {\n        fun m(): Int {\n            return if (x > 0) 5 else 6\n'
             '        }\n    }\n    return inner(x)\n}\n')


@pytest.mark.parametrize('path, source, line, name, expected', [
    ('a.py', PY_NESTED, 1, 'outer', 1), ('a.py', PY_NESTED, 4, 'inner', 2), ('a.py', PY_NESTED, 10, 'm', 1), ('a.py', PY_NESTED, 10, 'K.m', 1),
    ('a.py', 'def outer():\n    async def inner(x):\n        if x:\n            pass\n    return 1\n', 1, 'outer', 0),
    ('a.ts', TS_NESTED, 1, 'outer', 1), ('a.ts', TS_NESTED, 5, 'inner', 2), ('a.ts', TS_NESTED, 14, 'm', 1),
    ('A.kt', KT_NESTED, 1, 'outer', 1), ('A.kt', KT_NESTED, 5, 'inner', 2), ('A.kt', KT_NESTED, 10, 'm', 1),
], ids=['py-outer-excludes-nested-def-and-class', 'py-inner', 'py-method-of-nested-class', 'py-dotted-name', 'py-nested-async-def',
        'ts-outer', 'ts-inner', 'ts-method-of-nested-class', 'kt-outer', 'kt-inner', 'kt-method-of-local-class'])
def test_V01_nested_named_declarations_are_excluded_from_the_outer_count(path, source, line, name, expected):
    assert branch_count(path, source, line, name) == expected


@pytest.mark.parametrize('path, source, line, name, expected', [
    ('a.py', 'class K:\n    def m(self, x):\n        if x:\n            return 1\n        return 0\n', 2, 'm', 1),
    ('a.py', 'class K:\n    def m(self, x):\n        if x:\n            return 1\n        return 0\n', 2, 'K.m', 1),
    ('a.ts', 'class K {\n  m(x: number): number {\n    return x > 0 ? 1 : 0;\n  }\n}\n', 2, 'm', 1),
    ('a.ts', 'class K {\n  m(x: number): number {\n    return x > 0 ? 1 : 0;\n  }\n}\n', 2, 'K.m', 1),
    ('A.kt', 'class K {\n    fun m(x: Int): Int {\n        return if (x > 0) 1 else 0\n    }\n}\n', 2, 'm', 1),
    ('A.kt', 'class K {\n    fun m(x: Int): Int {\n        return if (x > 0) 1 else 0\n    }\n}\n', 2, 'K.m', 1),
    ('a.py', 'def a(x):\n    return 1\n\n\ndef b(x):\n    if x:\n        return 1\n    return 0\n', 5, 'b', 1),
    ('a.py', 'def a(x):\n    if x:\n        return 1\n    return 0\n\n\ndef b(x):\n    return 1\n', 1, 'a', 1),
], ids=['py-method', 'py-method-dotted', 'ts-method', 'ts-method-dotted', 'kt-method', 'kt-method-dotted', 'py-second-function',
        'py-first-of-two'])
def test_V01_methods_and_name_with_dots_match_on_the_part_after_the_last_dot(path, source, line, name, expected):
    assert branch_count(path, source, line, name) == expected


MISMATCH_SOURCES = {
    'python': ('a.py', 'def f(x):\n    if x:\n        return 1\n    return 0\n'),
    'typescript': ('a.ts', 'function f(x: number) {\n  if (x) {\n    return 1;\n  }\n  return 0;\n}\n'),
    'kotlin': ('A.kt', 'fun f(x: Int): Int {\n    if (x > 0) {\n        return 1\n    }\n    return 0\n}\n'),
}


@pytest.mark.parametrize('language', MISMATCH_SOURCES)
@pytest.mark.parametrize('line, name', [(1, 'g'), (1, 'f2'), (2, 'f'), (99, 'f'), (0, 'f'), (1, '')],
                         ids=['other-name', 'name-with-extra-suffix', 'line-inside-body', 'line-past-end', 'line-zero', 'empty-name'])
def test_V01_name_or_start_line_mismatch_gives_none(language, line, name):
    path, source = MISMATCH_SOURCES[language]
    assert branch_count(path, source, line, name) is None


@pytest.mark.parametrize('path, source', [
    ('a.py', 'def f(x):\n    if x:\n        return 1\n    return (\n'),
    ('a.py', 'def f(x):\n    if x:\n        return 1\n    return 0\n\n\ndef g(:\n'),
    ('a.ts', 'function f(x: number) {\n  if (x) {\n    return 1;\n  }\n  return 0;\n}\nfunction g( {\n'),
    ('a.ts', 'function f(x: number) {\n  if (x) {\n    return 1;\n  }\n'),
    ('A.kt', 'fun f(x: Int): Int {\n    if (x > 0) { return 1 }\n    return 0\n}\nfun g( {\n'),
    ('A.kt', 'fun f(x: Int): Int {\n    if (x > 0) { return 1 }\n'),
], ids=['py-in-function', 'py-after-function', 'ts-after-function', 'ts-unclosed', 'kt-after-function', 'kt-unclosed'])
def test_V01_syntax_error_gives_none(path, source):
    assert branch_count(path, source, 1, 'f') is None


@pytest.mark.parametrize('path', ['a.rb', 'a.go', 'A.java', 'notes.txt', 'Makefile', 'a.pyc'])
def test_V01_unsupported_extension_gives_none(path):
    assert branch_count(path, 'def f(x)\n  if x\n    1\n  end\nend\n', 1, 'f') is None


TS_DECLARED_VALUES = {
    'const-arrow-block': ('const f = (x: number) => {\n  if (x) {\n    return 1;\n  }\n  return 0;\n};\n', 1, 1),
    'export-const-arrow-expression': ('export const f = (x: number) => x ? 1 : 2;\n', 1, 1),
    'const-function-expression': ('const f = function (x: number) {\n  if (x) {\n    return 1;\n  }\n  return 0;\n};\n', 1, 1),
    'class-field-arrow': ('class K {\n  f = (x: number) => {\n    return x ? 1 : 0;\n  };\n}\n', 2, 1),
    'class-field-function-expression': ('class K {\n  f = function (x: number) {\n    return x && 1;\n  };\n}\n', 2, 1),
    'arrow-without-branches': ('export const f = () => 1;\n', 1, 0),
}


@pytest.mark.parametrize('source, line, expected', TS_DECLARED_VALUES.values(), ids=TS_DECLARED_VALUES.keys())
def test_V01_arrow_or_function_expression_assigned_to_a_variable_or_field_is_the_declaration(source, line, expected):
    assert branch_count('a.ts', source, line, 'f') == expected


def test_V01_declaration_line_and_value_line_both_find_the_assigned_arrow():
    source = 'const f =\n  (x: number) => {\n    if (x) {\n      return 1;\n    }\n    return 0;\n  };\n'
    assert branch_count('a.ts', source, 1, 'f') == 1
    assert branch_count('a.ts', source, 2, 'f') == 1
    assert branch_count('a.ts', source, 3, 'f') is None


# ---------------------------------------------------------------------------------------------------------------------
# V02 symbol table columns (unit with contents) and CLI file granularity (integration)
# ---------------------------------------------------------------------------------------------------------------------

def test_V02_symbol_columns_constant_order():
    assert symbols_api().SYMBOL_COLUMNS == ['id', 'file', 'kind', 'name', 'signature', 'visibility', 'external_refs',
                                            'uncertain_external_refs', 'branches', 'test_reach']
    assert symbols_api().SYMBOL_COLUMNS == SYMBOL_COLUMNS


def table_with(nodes, edges=(), contents=None):
    return {row['id']: row for row in symbols_api().symbol_table(arch(nodes, edges), contents=contents)}


def test_V02_unit_contents_give_branches_for_functions_and_methods_and_null_for_class_and_constant():
    source = 'LIMIT = 1\n\n\ndef f(x):\n    if x:\n        return 1\n    return 0\n\n\nclass K:\n    def m(self, x):\n        return 1 if x else 2\n'
    nodes = [sym('py:a#LIMIT', 'a.py', 'constant', line=1), sym('py:a#f', 'a.py', 'function', line=4), sym('py:a#K', 'a.py', 'class', line=10),
             sym('py:a#K.m', 'a.py', 'method', line=11)]
    rows = table_with(nodes, contents={'a.py': source})
    assert (rows['py:a#f']['branches'], rows['py:a#K.m']['branches']) == (1, 1)
    assert rows['py:a#K']['branches'] is None and rows['py:a#LIMIT']['branches'] is None
    assert all(row['test_reach'] in ('tested', 'uncertain', 'untested') for row in rows.values())
    assert list(next(iter(rows.values()))) == SYMBOL_COLUMNS


def test_V02_unit_without_contents_every_branches_is_null():
    nodes = [sym('py:a#f', 'a.py', 'function', line=1), sym('py:a#K.m', 'a.py', 'method', line=3)]
    assert [row['branches'] for row in table_with(nodes).values()] == [None, None]
    assert [row['branches'] for row in table_with(nodes, contents={}).values()] == [None, None]


def test_V02_unit_file_missing_from_contents_or_syntax_error_or_unsupported_language_is_null_and_others_are_kept():
    nodes = [sym('py:a#f', 'a.py', 'function', line=1), sym('py:b#g', 'b.py', 'function', line=1), sym('py:c#h', 'c.py', 'function', line=1),
             sym('rb:d#i', 'd.rb', 'function', line=1), sym('py:e#k', 'e.py', 'function', line=1)]
    contents = {'a.py': 'def f(x):\n    if x:\n        return 1\n    return 0\n', 'b.py': 'def g(:\n', 'd.rb': 'def i\n  if x\n  end\nend\n',
                'e.py': 'def k(x):\n    return 1\n'}
    rows = table_with(nodes, contents=contents)
    assert {key: row['branches'] for key, row in rows.items()} == {'py:a#f': 1, 'py:b#g': None, 'py:c#h': None, 'rb:d#i': None, 'py:e#k': 0}


def test_V02_unit_line_that_does_not_start_the_named_declaration_is_null():
    nodes = [sym('py:a#f', 'a.py', 'function', line=2)]
    assert table_with(nodes, contents={'a.py': 'def f(x):\n    if x:\n        return 1\n'})['py:a#f']['branches'] is None


PY_PROJECT = {
    'app/__init__.py': '',
    'app/a.py': 'LIMIT = 3\n\n\ndef f(x, y):\n    if x and y:\n        return 1\n    return 0\n\n\ndef lonely():\n    return 2\n\n\n'
                'class K:\n    def m(self, items):\n        return [i for i in items if i]\n',
    'tests/test_a.py': 'from app.a import f\n\n\ndef test_f():\n    assert f(1, 2) == 1\n',
}
TS_PROJECT = {
    'src/a.ts': 'export function f(x: number, y: number): number {\n  if (x > y) {\n    return x;\n  }\n  return y ?? 0;\n}\n\n'
                'export class Box {\n  open(a: number): number {\n    return a > 0 ? 1 : 0;\n  }\n}\n',
    'src/b.ts': "import { f } from './a';\n\nexport function use(): number {\n  return f(1, 2);\n}\n",
}
KT_PROJECT = {
    'src/main/kotlin/a/A.kt': 'package a\n\nfun pub(x: Int): Int = if (x > 0) x else 0\n\nclass Holder {\n    fun get(v: Int?): Int {\n'
                              '        return v ?: 0\n    }\n}\n',
    'src/main/kotlin/b/B.kt': 'package b\n\nimport a.pub\n\nfun use(): Int = pub(1)\n',
}
PROJECTS = {'python': (PY_PROJECT, ['-l', 'python']), 'typescript': (TS_PROJECT, ['-l', 'typescript']), 'kotlin': (KT_PROJECT, ['-l', 'kotlin'])}
EXPECTED_BRANCHES = {
    'python': {('f', 'function'): 2, ('m', 'method'): 1, ('lonely', 'function'): 0, ('K', 'class'): None, ('LIMIT', 'constant'): None},
    'typescript': {('f', 'function'): 2, ('open', 'method'): 1, ('use', 'function'): 0, ('Box', 'class'): None},
    'kotlin': {('pub', 'function'): 1, ('get', 'method'): 1, ('use', 'function'): 0, ('Holder', 'class'): None},
}


@pytest.fixture(scope='module')
def base_tree(tmp_path_factory):
    path = base_worktree(tmp_path_factory.mktemp('base-tree'))
    yield path
    remove_worktree(path)


@pytest.mark.parametrize('language', PROJECTS)
def test_V02_cli_columns_order_branch_values_and_null_for_class_and_constant(language, tmp_path):
    files, lang = PROJECTS[language]
    root = tmp_path / 'repo'
    make_repo(root, files)
    data = analyze(root, tmp_path / 'o', lang)
    network = data['dependency_network']
    assert network['symbol_columns'] == ['id', 'file', 'kind', 'name', 'signature', 'visibility', 'external_refs',
                                         'uncertain_external_refs', 'branches', 'test_reach']
    assert all(len(row) == 10 for row in network['symbols'])
    rows = decode_symbols(data)
    found = {(row['name'], row['kind']): row for row in rows}
    for key, expected in EXPECTED_BRANCHES[language].items():
        assert key in found, (key, sorted(found))
        value = found[key]['branches']
        assert value == expected and (value is None or type(value) is int), (key, value)
    assert all(row['test_reach'] in ('tested', 'uncertain', 'untested') for row in rows)


def test_V02_cli_python_test_reach_values_follow_the_confirmed_call_from_the_test(tmp_path):
    root = tmp_path / 'repo'
    make_repo(root, PY_PROJECT)
    rows = {row['name']: row for row in decode_symbols(analyze(root, tmp_path / 'o', ['-l', 'python']))}
    assert rows['f']['test_reach'] == 'tested'
    assert rows['lonely']['test_reach'] == 'untested' and rows['LIMIT']['test_reach'] == 'untested'


@pytest.mark.parametrize('language', PROJECTS)
def test_V02_cli_output_without_the_new_columns_and_table_equals_the_base_commit(language, base_tree, tmp_path):
    files, lang = PROJECTS[language]
    root = tmp_path / 'repo'
    make_repo(root, files)
    expected = run_file_granularity(root, tmp_path / 'base', base_tree, lang)
    actual = run_file_granularity(root, tmp_path / 'cur', Path(__file__).resolve().parents[1], lang)
    network = actual['dependency_network']
    assert network['test_case_columns'] == TEST_CASE_COLUMNS and isinstance(network['test_cases'], list)
    del network['test_cases'], network['test_case_columns']
    assert network['symbol_columns'][-2:] == ['branches', 'test_reach']
    network['symbol_columns'] = network['symbol_columns'][:-2]
    network['symbols'] = [row[:-2] for row in network['symbols']]
    assert actual == expected


def test_V02_cli_symbol_granularity_has_neither_new_table_nor_columns(tmp_path):
    root = tmp_path / 'repo'
    make_repo(root, PY_PROJECT)
    out = tmp_path / 'o'
    out.mkdir()
    done = run_cli([root, '-l', 'python', '--granularity', 'symbol', '--json', '-o', out / 'r.html', '--bottlenecks', out / 'b.json'])
    assert done.returncode == 0, done.stderr[-1500:]
    text = (out / 'b.json').read_text(encoding='utf-8')
    for word in ('test_cases', 'test_case_columns', 'test_reach', 'symbol_columns'):
        assert word not in text


def test_V01_cli_syntax_error_files_give_null_branches_and_no_test_rows_without_failing(tmp_path):
    files = {'src/a.ts': 'export function ok(x: number): number {\n  if (x) {\n    return 1;\n  }\n  return 0;\n}\n',
             'src/bad.ts': 'export function broken(x: number): number {\n  if (x) {\n    return 1;\n  }\n  return 0;\n}\nfunction g( {\n',
             'src/bad.spec.ts': "it('x', () => {\n  expect(1).toBe(1);\n});\nfunction g( {\n"}
    root = tmp_path / 'repo'
    make_repo(root, files)
    data = analyze(root, tmp_path / 'o', ['-l', 'typescript'])
    rows = decode_symbols(data)
    ok = [r for r in rows if r['name'] == 'ok']
    assert [r['branches'] for r in ok] == [1]
    assert all(r['branches'] is None for r in rows if r['file'] == 'file:src/bad.ts')
    network = data['dependency_network']
    assert not [row for row in network['test_cases'] if network['file_ids'][row[1]] == 'file:src/bad.spec.ts']


# ---------------------------------------------------------------------------------------------------------------------
# V03 test_reach, cause-effect graph
# ---------------------------------------------------------------------------------------------------------------------

def prod(ident, kind='function', path='src/m.py', **kwargs):
    return sym(ident, path, kind, **kwargs)


def tfn(ident='py:t#test_a', path='tests/test_a.py'):
    return sym(ident, path, 'function')


def test_V03_cause_confirmed_chain_gives_tested_and_unreached_nodes_untested_for_all_four_kinds():
    nodes = [tfn(), prod('py:m#A'), prod('py:m#B'), prod('py:m#C'), prod('py:m#D'), prod('py:m#Cls', 'class'), prod('py:m#K', 'constant'),
             prod('py:m#Cls.meth', 'method')]
    edges = [rel('py:t#test_a', 'py:m#A', 'CALLS', SC, EXACT), rel('py:m#A', 'py:m#B', 'CALLS', SI, UNIQUE), rel('py:m#B', 'py:m#C', 'CALLS', SC, UNIQUE)]
    assert reach_of(nodes, edges) == {'py:m#A': 'tested', 'py:m#B': 'tested', 'py:m#C': 'tested', 'py:m#D': 'untested', 'py:m#Cls': 'untested',
                                      'py:m#K': 'untested', 'py:m#Cls.meth': 'untested'}


@pytest.mark.parametrize('confidence, resolution', [(SC, EXACT), (SC, UNIQUE), (SI, EXACT), (SI, UNIQUE)],
                         ids=['certain-exact', 'certain-unique', 'inferred-exact', 'inferred-unique'])
def test_V03_cause_each_confirmed_edge_kind_gives_tested(confidence, resolution):
    nodes = [tfn(), prod('py:m#A')]
    assert reach_of(nodes, [rel('py:t#test_a', 'py:m#A', 'CALLS', confidence, resolution)]) == {'py:m#A': 'tested'}


@pytest.mark.parametrize('confidence, resolution', [(FI, EXACT), (FI, UNIQUE), (DR, EXACT), (SC, AMBIGUOUS), (SI, AMBIGUOUS), (SC, UNRESOLVED),
                                                    (SI, UNRESOLVED)],
                         ids=['framework-exact', 'framework-unique', 'dynamic-exact', 'certain-ambiguous', 'inferred-ambiguous',
                              'certain-unresolved', 'inferred-unresolved'])
def test_V03_cause_a_single_unconfirmed_edge_from_the_test_gives_uncertain(confidence, resolution):
    nodes = [tfn(), prod('py:m#A'), prod('py:m#B')]
    assert reach_of(nodes, [rel('py:t#test_a', 'py:m#A', 'CALLS', confidence, resolution)]) == {'py:m#A': 'uncertain', 'py:m#B': 'untested'}


def test_V03_cause_chain_through_an_unconfirmed_edge_is_uncertain_even_when_later_edges_are_confirmed():
    nodes = [tfn(), prod('py:m#A'), prod('py:m#U'), prod('py:m#V'), prod('py:m#W')]
    edges = [rel('py:t#test_a', 'py:m#A', 'CALLS', SC, EXACT), rel('py:m#A', 'py:m#U', 'CALLS', FI, EXACT),
             rel('py:m#U', 'py:m#V', 'CALLS', SC, EXACT), rel('py:m#V', 'py:m#W', 'CALLS', SC, EXACT)]
    assert reach_of(nodes, edges) == {'py:m#A': 'tested', 'py:m#U': 'uncertain', 'py:m#V': 'uncertain', 'py:m#W': 'uncertain'}


def test_V03_cause_a_confirmed_path_beats_an_uncertain_path_to_the_same_node():
    nodes = [tfn(), prod('py:m#A'), prod('py:m#B')]
    edges = [rel('py:t#test_a', 'py:m#A', 'CALLS', FI, EXACT), rel('py:t#test_a', 'py:m#B', 'CALLS', SC, EXACT),
             rel('py:m#B', 'py:m#A', 'CALLS', SC, EXACT)]
    assert reach_of(nodes, edges) == {'py:m#A': 'tested', 'py:m#B': 'tested'}


def test_V03_cause_ambiguous_edge_makes_every_candidate_target_uncertain():
    nodes = [tfn(), prod('py:m#X'), prod('py:m#X1'), prod('py:m#X2'), prod('py:m#X3')]
    edges = [rel('py:t#test_a', 'py:m#X', 'CALLS', SC, AMBIGUOUS, candidates=['py:m#X1', 'py:m#X2'])]
    assert reach_of(nodes, edges) == {'py:m#X': 'uncertain', 'py:m#X1': 'uncertain', 'py:m#X2': 'uncertain', 'py:m#X3': 'untested'}


def test_V03_cause_candidates_of_a_non_ambiguous_edge_are_not_reached():
    nodes = [tfn(), prod('py:m#Y'), prod('py:m#Z')]
    edges = [rel('py:t#test_a', 'py:m#Y', 'CALLS', SC, EXACT, candidates=['py:m#Z'])]
    assert reach_of(nodes, edges) == {'py:m#Y': 'tested', 'py:m#Z': 'untested'}


@pytest.mark.parametrize('relation', ['IMPORTS', 'TYPE_USES', 'TESTS'])
def test_V03_cause_relations_that_are_not_followed_leave_the_target_untested(relation):
    nodes = [tfn(), prod('py:m#P'), prod('py:m#Q')]
    edges = [rel('py:t#test_a', 'py:m#P', relation, SC, EXACT), rel('py:m#P', 'py:m#Q', 'CALLS', SC, EXACT)]
    assert reach_of(nodes, edges) == {'py:m#P': 'untested', 'py:m#Q': 'untested'}


def test_V03_cause_a_not_followed_relation_in_the_middle_of_a_chain_stops_it():
    nodes = [tfn(), prod('py:m#A'), prod('py:m#B'), prod('py:m#C')]
    edges = [rel('py:t#test_a', 'py:m#A', 'CALLS', SC, EXACT), rel('py:m#A', 'py:m#B', 'TYPE_USES', SC, EXACT),
             rel('py:m#B', 'py:m#C', 'CALLS', SC, EXACT)]
    assert reach_of(nodes, edges) == {'py:m#A': 'tested', 'py:m#B': 'untested', 'py:m#C': 'untested'}


@pytest.mark.parametrize('relation, kind', [('CALLS', 'function'), ('INSTANTIATES', 'class'), ('CALLS_ROUTE', 'function'),
                                            ('IMPLEMENTED_BY', 'method'), ('DECORATES', 'function')])
def test_V03_cause_every_followed_relation_reaches_the_target(relation, kind):
    nodes = [tfn(), prod('py:m#T', kind)]
    assert reach_of(nodes, [rel('py:t#test_a', 'py:m#T', relation, SC, EXACT)]) == {'py:m#T': 'tested'}
    assert reach_of(nodes, [rel('py:t#test_a', 'py:m#T', relation, FI, EXACT)]) == {'py:m#T': 'uncertain'}


def test_V03_cause_framework_node_edge_makes_the_target_and_its_callees_uncertain():
    route = sym('flask:route#r', 'src/routes.py', 'route', provenance='flask')
    nodes = [tfn(), route, prod('py:m#H'), prod('py:m#helper'), prod('py:m#lonely')]
    edges = [rel('flask:route#r', 'py:m#H', 'CALLS_ROUTE', SC, EXACT), rel('py:m#H', 'py:m#helper', 'CALLS', SC, EXACT)]
    assert reach_of(nodes, edges) == {'py:m#H': 'uncertain', 'py:m#helper': 'uncertain', 'py:m#lonely': 'untested'}


def test_V03_cause_chain_from_an_entry_follows_unconfirmed_edges_too():
    route = sym('flask:route#r', 'src/routes.py', 'route', provenance='flask')
    nodes = [route, prod('py:m#H'), prod('py:m#a'), prod('py:m#b')]
    edges = [rel('flask:route#r', 'py:m#H', 'CALLS_ROUTE', FI, AMBIGUOUS, candidates=['py:m#a']), rel('py:m#a', 'py:m#b', 'CALLS', DR, UNRESOLVED)]
    assert reach_of(nodes, edges) == {'py:m#H': 'uncertain', 'py:m#a': 'uncertain', 'py:m#b': 'uncertain'}


def test_V03_cause_entry_that_the_test_also_reaches_confirmed_is_tested():
    route = sym('flask:route#r', 'src/routes.py', 'route', provenance='flask')
    nodes = [tfn(), route, prod('py:m#H'), prod('py:m#helper')]
    edges = [rel('flask:route#r', 'py:m#H', 'CALLS_ROUTE', SC, EXACT), rel('py:t#test_a', 'py:m#H', 'CALLS', SC, EXACT),
             rel('py:m#H', 'py:m#helper', 'CALLS', SC, EXACT)]
    assert reach_of(nodes, edges) == {'py:m#H': 'tested', 'py:m#helper': 'tested'}


def test_V03_cause_an_edge_from_a_language_provenance_production_node_is_not_an_entry():
    nodes = [prod('py:m#P'), prod('py:m#Q'), prod('ts:m#R', path='src/r.ts', provenance='typescript-core'),
             prod('kotlin:m#S', path='src/S.kt', provenance='kotlin-core')]
    edges = [rel('py:m#P', 'py:m#Q', 'CALLS', SC, EXACT), rel('ts:m#R', 'kotlin:m#S', 'CALLS', FI, EXACT)]
    assert reach_of(nodes, edges) == {'py:m#P': 'untested', 'py:m#Q': 'untested', 'ts:m#R': 'untested', 'kotlin:m#S': 'untested'}


CTORS = ('__init__', '__post_init__', 'constructor', 'init')


def test_V03_cause_instantiation_reaches_the_constructor_methods_and_what_they_call():
    nodes = [tfn(), prod('py:m#K', 'class'), prod('py:m#helper')]
    edges = [rel('py:t#test_a', 'py:m#K', 'INSTANTIATES', SC, EXACT), rel('py:m#K.__init__', 'py:m#helper', 'CALLS', SC, EXACT)]
    for index, name in enumerate(CTORS):
        nodes.append(prod(f'py:m#K.{name}', 'method'))
        edges.append(rel('py:m#K', f'py:m#K.{name}', 'CONTAINS' if index % 2 == 0 else 'DECLARES', SC, EXACT))
    nodes.append(prod('py:m#K.other', 'method'))
    edges.append(rel('py:m#K', 'py:m#K.other', 'CONTAINS', SC, EXACT))
    result = reach_of(nodes, edges)
    assert result['py:m#K'] == 'tested' and result['py:m#helper'] == 'tested'
    assert [result[f'py:m#K.{name}'] for name in CTORS] == ['tested'] * 4
    assert result['py:m#K.other'] == 'untested'


def test_V03_cause_uncertain_instantiation_makes_candidates_and_their_constructors_uncertain():
    nodes = [tfn(), prod('py:m#K1', 'class'), prod('py:m#K2', 'class'), prod('py:m#K1.__init__', 'method'),
             prod('py:m#K2.constructor', 'method'), prod('py:m#K3', 'class'), prod('py:m#K3.init', 'method')]
    edges = [rel('py:t#test_a', 'py:m#K1', 'INSTANTIATES', SC, AMBIGUOUS, candidates=['py:m#K2']),
             rel('py:t#test_a', 'py:m#K3', 'INSTANTIATES', FI, EXACT),
             rel('py:m#K1', 'py:m#K1.__init__', 'CONTAINS', SC, EXACT), rel('py:m#K2', 'py:m#K2.constructor', 'DECLARES', SC, EXACT),
             rel('py:m#K3', 'py:m#K3.init', 'CONTAINS', SC, EXACT)]
    assert set(reach_of(nodes, edges).values()) == {'uncertain'}


def test_V03_cause_a_plain_call_to_a_class_does_not_reach_its_constructor():
    nodes = [tfn(), prod('py:m#K', 'class'), prod('py:m#K.__init__', 'method')]
    edges = [rel('py:t#test_a', 'py:m#K', 'CALLS', SC, EXACT), rel('py:m#K', 'py:m#K.__init__', 'CONTAINS', SC, EXACT)]
    assert reach_of(nodes, edges) == {'py:m#K': 'tested', 'py:m#K.__init__': 'untested'}


@pytest.mark.parametrize('relation', ['CONTAINS', 'DECLARES', 'CALLS', 'IMPORTS', 'TYPE_USES'])
def test_V03_cause_an_entry_made_by_any_relation_still_makes_the_target_uncertain(relation):
    module = sym('nestjs:module#M', 'src/m.module.ts', 'module', provenance='nestjs')
    nodes = [module, prod('py:m#H'), prod('py:m#helper'), prod('py:m#lonely')]
    edges = [rel('nestjs:module#M', 'py:m#H', relation, SC, EXACT), rel('py:m#H', 'py:m#helper', 'CALLS', SC, EXACT)]
    assert reach_of(nodes, edges) == {'py:m#H': 'uncertain', 'py:m#helper': 'uncertain', 'py:m#lonely': 'untested'}


def test_V03_cause_every_node_of_a_test_file_is_a_seed_and_is_not_listed():
    nodes = [tfn(), sym('py:t#helper', 'tests/test_a.py', 'function'), sym('py:t#Fixture', 'tests/test_a.py', 'class'),
             prod('py:m#A'), prod('py:m#B')]
    edges = [rel('py:t#helper', 'py:m#A', 'CALLS', SC, EXACT), rel('py:t#Fixture', 'py:m#B', 'CALLS', FI, EXACT)]
    assert reach_of(nodes, edges) == {'py:m#A': 'tested', 'py:m#B': 'uncertain'}


def test_V03_cause_test_directory_and_name_conventions_decide_the_seed_files():
    paths = ['tests/test_x.py', 'pkg/x_test.py', 'src/x.spec.ts', 'src/__tests__/y.ts', 'src/test/kotlin/XTest.kt']
    nodes = [prod('py:m#A')]
    edges = []
    for index, path in enumerate(paths):
        nodes.append(sym(f'py:s{index}#fn', path, 'function'))
        edges.append(rel(f'py:s{index}#fn', 'py:m#A', 'CALLS', FI, EXACT))
    only_test = [sym('py:p#plain', 'src/plain.py', 'function')]
    assert reach_of(nodes + only_test, edges) == {'py:m#A': 'uncertain', 'py:p#plain': 'untested'}


# ---------------------------------------------------------------------------------------------------------------------
# V04 test case table: rows and ids
# ---------------------------------------------------------------------------------------------------------------------

def ids_of(path, source):
    return [row['id'] for row in cases_of(path, source)]


def test_V04_python_module_function_class_method_nested_class_and_non_test_names():
    source = ('def test_a():\n    pass\n\n\ndef helper():\n    pass\n\n\ndef a_test():\n    pass\n\n\ndef Test_x():\n    pass\n\n\n'
              'async def test_async():\n    pass\n\n\nclass TestK:\n    def test_b(self):\n        pass\n\n    def helper(self):\n        pass\n\n'
              '    class Inner:\n        def test_c(self):\n            pass\n\n\ndef test_outer():\n    def test_inner():\n        pass\n')
    assert ids_of('tests/test_a.py', source) == sorted([
        'file:tests/test_a.py#test_a', 'file:tests/test_a.py#test_async', 'file:tests/test_a.py#TestK.test_b',
        'file:tests/test_a.py#TestK.Inner.test_c', 'file:tests/test_a.py#test_outer'])


def test_V04_row_shape_and_file_value():
    [row] = cases_of('tests/test_a.py', 'def test_a():\n    assert 1 == 1\n')
    assert list(row) == TEST_CASE_COLUMNS
    assert row['file'] == 'file:tests/test_a.py' and row['id'] == 'file:tests/test_a.py#test_a' and row['name'] == 'test_a'


def test_V04_rows_are_ordered_by_id_over_several_files_and_only_requested_paths_are_read():
    from tests.test_signals_support import signals_api
    contents = {'tests/b.py': 'def test_z():\n    pass\n', 'tests/a.py': 'def test_y():\n    pass\n\n\ndef test_a():\n    pass\n',
                'tests/c.py': 'def test_unlisted():\n    pass\n'}
    rows = signals_api().test_case_table(contents, ['tests/b.py', 'tests/a.py'])
    assert [r['id'] for r in rows] == ['file:tests/a.py#test_a', 'file:tests/a.py#test_y', 'file:tests/b.py#test_z']


def test_V04_python_duplicate_names_get_numbered_in_source_order():
    source = 'def test_a():\n    pass\n\n\ndef test_a():\n    pass\n\n\ndef test_a():\n    pass\n'
    assert ids_of('tests/test_a.py', source) == ['file:tests/test_a.py#test_a', 'file:tests/test_a.py#test_a [2]', 'file:tests/test_a.py#test_a [3]']


TS_VARIANTS = ("it('plain', () => {});\ntest('tst', () => {});\nit.only('only', () => {});\ntest.only('tonly', () => {});\n"
               "it.skip('skipped', () => {});\ntest.skip('tskipped', () => {});\nit.todo('todo');\ntest.todo('ttodo');\n"
               "it.each([1, 2])('each %s', (n) => {});\ntest.each([1])('teach %s', (n) => {});\nxit('xit', () => {});\nxtest('xtest', () => {});\n"
               "fit('fit', () => {});\n")


def test_V04_typescript_case_call_variants_each_give_a_row_with_the_title_as_name():
    names = ['plain', 'tst', 'only', 'tonly', 'skipped', 'tskipped', 'todo', 'ttodo', 'each %s', 'teach %s', 'xit', 'xtest', 'fit']
    assert ids_of('src/a.test.ts', TS_VARIANTS) == sorted('file:src/a.test.ts#' + n for n in names)


def test_V04_typescript_describe_variants_and_nesting_build_the_name_with_arrows():
    source = ("describe('A', () => {\n  describe('B', () => {\n    it('c', () => {});\n  });\n  it('d', () => {});\n});\n"
              "describe.only('O', () => {\n  it('o1', () => {});\n});\ndescribe.skip('S', () => {\n  it('s1', () => {});\n});\n"
              "describe.each([1, 2])('E %s', () => {\n  it('e1', () => {});\n});\nxdescribe('X', () => {\n  it('x1', () => {});\n});\n"
              "fdescribe('F', () => {\n  it('f1', () => {});\n});\n")
    expected = ['A > B > c', 'A > d', 'O > o1', 'S > s1', 'E %s > e1', 'X > x1', 'F > f1']
    assert ids_of('src/a.test.ts', source) == sorted('file:src/a.test.ts#' + n for n in expected)


def test_V04_typescript_titles_template_literal_quotes_and_dynamic():
    source = ("const name = 'n';\nit(`tpl ${name} end`, () => {});\nit(\"double\", () => {});\nit(name, () => {});\nit('a' + 'b', () => {});\n"
              "describe(name, () => {\n  it('inner', () => {});\n});\n")
    expected = ['tpl ${name} end', 'double', '<dynamic>', '<dynamic> [2]', '<dynamic> > inner']
    assert ids_of('src/a.test.ts', source) == sorted('file:src/a.test.ts#' + n for n in expected)


def test_V04_duplicate_cases_keep_an_unsuffixed_name_column():
    ts = "describe('D', () => {\n  it('t', () => {});\n  it('t', () => {});\n});\n"
    assert [r['name'] for r in cases_of('src/a.test.ts', ts)] == ['D > t', 'D > t']
    py = 'def test_a():\n    pass\n\n\ndef test_a():\n    pass\n'
    assert [r['name'] for r in cases_of('tests/test_a.py', py)] == ['test_a', 'test_a']


def test_V04_typescript_duplicate_titles_in_one_describe_get_numbered():
    source = "describe('D', () => {\n  it('t', () => {});\n  it('t', () => {});\n  it('t', () => {});\n});\n"
    assert ids_of('src/a.test.ts', source) == ['file:src/a.test.ts#D > t', 'file:src/a.test.ts#D > t [2]', 'file:src/a.test.ts#D > t [3]']


@pytest.mark.parametrize('extension', ['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'])
def test_V04_typescript_javascript_extensions_give_rows(extension):
    path = 'src/a.test' + extension
    assert ids_of(path, "it('a', () => {\n  expect(1).toBe(1);\n});\n") == [f'file:{path}#a']


KT_FILE = ('class T {\n    @Test\n    fun a() {\n    }\n\n    @org.junit.Test\n    fun b() {\n    }\n\n    fun c() {\n    }\n\n'
           '    @Before\n    fun d() {\n    }\n}\n\nobject O {\n    @Test\n    fun e() {\n    }\n}\n\n'
           'class Outer {\n    class Inner {\n        @Test\n        fun f() {\n        }\n    }\n}\n\n@Test\nfun top() {\n}\n')


def test_V04_kotlin_annotated_functions_in_classes_objects_and_nested_classes():
    expected = ['T.a', 'T.b', 'O.e', 'Outer.Inner.f', 'top']
    assert ids_of('src/test/kotlin/TTest.kt', KT_FILE) == sorted('file:src/test/kotlin/TTest.kt#' + n for n in expected)


@pytest.mark.parametrize('path, source', [
    ('tests/test_a.py', 'def test_ok():\n    assert 1 == 1\n\n\ndef test_bad(:\n    pass\n'),
    ('src/a.test.ts', "it('ok', () => {\n  expect(1).toBe(1);\n});\nit('bad', () => {\n"),
    ('src/test/kotlin/TTest.kt', 'class T {\n    @Test\n    fun a() {\n    }\n}\nfun g( {\n'),
], ids=['python', 'typescript', 'kotlin'])
def test_V04_syntax_error_file_gives_no_rows_while_other_files_keep_theirs(path, source):
    from tests.test_signals_support import signals_api
    rows = signals_api().test_case_table({path: source, 'tests/test_ok.py': 'def test_fine():\n    pass\n'}, [path, 'tests/test_ok.py'])
    assert [r['id'] for r in rows] == ['file:tests/test_ok.py#test_fine']


@pytest.mark.parametrize('path', ['tests/a.rb', 'tests/a.go', 'tests/a.txt'])
def test_V04_unsupported_extension_gives_no_rows(path):
    assert cases_of(path, "def test_a\nend\n") == []


# ---------------------------------------------------------------------------------------------------------------------
# V05 assertion classification, table A
# ---------------------------------------------------------------------------------------------------------------------

def py_body(body):
    return 'def test_a():\n' + indent(body.rstrip('\n') + '\n', 4)


def py_counts(body):
    row = case_row('tests/test_a.py', py_body(body), 'test_a')
    return row['strong_assertions'], row['weak_assertions']


PY_ASSERT_STATEMENTS = {
    'eq': ('assert x == 1', (1, 0)), 'is': ('assert x is y', (1, 0)), 'is-none': ('assert x is None', (1, 0)),
    'ne': ('assert x != 1', (0, 1)), 'lt': ('assert x < 1', (0, 1)), 'le': ('assert x <= 1', (0, 1)), 'gt': ('assert x > 1', (0, 1)),
    'ge': ('assert x >= 1', (0, 1)), 'in': ('assert x in y', (0, 1)), 'not-in': ('assert x not in y', (0, 1)),
    'is-not': ('assert x is not None', (0, 1)), 'two-operators': ('assert 0 < x < 5', (0, 1)), 'two-equalities': ('assert x == y == z', (0, 1)),
    'truthy': ('assert x', (0, 1)), 'negation': ('assert not x', (0, 1)),
    'boolean-of-comparisons': ('assert x == 1 and y == 2', (0, 1)), 'with-message': ('assert x == 1, "message"', (1, 0)),
    'parenthesised': ('assert (x == 1)', (1, 0)),
    'prefixed-call-inside-assert-counts-only-the-statement': ('assert check(x)', (0, 1)),
    'call-inside-a-strong-comparison': ('assert x == f()', (1, 0)), 'one-strong-one-weak': ('assert x == 1\nassert x != 2', (1, 1)),
}


@pytest.mark.parametrize('body, expected', PY_ASSERT_STATEMENTS.values(), ids=PY_ASSERT_STATEMENTS.keys())
def test_V05_python_assert_statements(body, expected):
    assert py_counts(body) == expected


PY_STRONG_CALLS = ['assertEqual', 'assertEquals', 'assertIs', 'assertIsNone', 'assertDictEqual', 'assertListEqual', 'assertCountEqual',
                   'assertSequenceEqual', 'assertTupleEqual', 'assertSetEqual', 'assertMultiLineEqual', 'assertAlmostEqual', 'assertRaises',
                   'assertRaisesRegex']
PY_WEAK_CALLS = ['assertTrue', 'assertFalse', 'assertIsNotNone', 'assertIn', 'assertNotIn', 'assertGreater', 'assertGreaterEqual', 'assertLess',
                 'assertLessEqual', 'assertNotEqual', 'assertIsInstance', 'assertIsNot', 'assertNotAlmostEqual', 'assertRegex']


@pytest.mark.parametrize('name', PY_STRONG_CALLS)
def test_V05_python_unittest_strong_calls(name):
    assert py_counts(f'self.{name}(a, b)') == (1, 0)


@pytest.mark.parametrize('name', PY_WEAK_CALLS)
def test_V05_python_unittest_weak_calls(name):
    assert py_counts(f'self.{name}(a, b)') == (0, 1)


@pytest.mark.parametrize('name', ['assert_called_once_with', 'assert_called_with', 'assert_any_call', 'assert_has_calls', 'assert_not_called'])
def test_V05_python_mock_strong_assertions(name):
    assert py_counts(f'm.{name}(1)') == (1, 0)


@pytest.mark.parametrize('name', ['assert_called', 'assert_called_once'])
def test_V05_python_mock_weak_assertions_win_over_the_prefix_rule(name):
    assert py_counts(f'm.{name}()') == (0, 1)


def test_V05_python_pytest_raises_and_context_managers():
    assert py_counts('with pytest.raises(ValueError):\n    f()') == (1, 0)
    assert py_counts('with self.assertRaises(ValueError):\n    f()') == (1, 0)


@pytest.mark.parametrize('call', ['check_state(x)', 'verify_all()', 'expect_value(y)', 'self.assertSomethingCustom(x)', 'helpers.assert_ok(x)',
                                  'obj.verify_x()', 'obj.check(x)', 'self.assertNotRegex(a, b)'],
                         ids=['check-bare', 'verify-bare', 'expect-bare', 'assert-prefix-method', 'assert-prefix-attr', 'verify-attr',
                              'check-attr', 'assertNotRegex-unlisted'])
def test_V05_python_prefix_rule_counts_unlisted_calls_as_strong(call):
    assert py_counts(call) == (1, 0)


@pytest.mark.parametrize('call', ['ensure(x)', 'foo.validate(x)', 'result = compute(x)', 'print(x)', 'self.helper_assert_like(x)'],
                         ids=['ensure', 'validate', 'plain-call', 'print', 'prefix-not-at-start'])
def test_V05_python_other_calls_are_not_assertions(call):
    assert py_counts(call) == (0, 0)


def test_V05_python_assertions_inside_nested_function_and_lambda_are_counted_and_other_cases_are_not():
    source = ('def test_a():\n    def inner():\n        assert x == 1\n    cb = lambda: self.assertEqual(1, 1)\n    inner()\n\n\n'
              'def test_b():\n    assert y != 2\n    assert y != 3\n')
    assert counts_of('tests/test_a.py', source, 'test_a')[:2] == (2, 0)
    assert counts_of('tests/test_a.py', source, 'test_b')[:2] == (0, 2)


def test_V05_python_no_assertion_gives_zero_zero():
    assert py_counts('x = 1') == (0, 0)


def ts_counts(body, path='src/a.test.ts'):
    source = "it('a', async () => {\n" + indent(body.rstrip('\n') + '\n', 2) + '});\n'
    row = case_row(path, source, 'a')
    return row['strong_assertions'], row['weak_assertions']


TS_STRONG = ['toBe(1)', 'toEqual({})', 'toStrictEqual({})', 'toBeNull()', 'toBeUndefined()', 'toBeNaN()', 'toBeCloseTo(1.5)', 'toHaveLength(2)',
             'toHaveBeenCalledWith(1)', 'toBeCalledWith(1)', 'toHaveBeenLastCalledWith(1)', 'toHaveBeenNthCalledWith(1, 2)',
             'toHaveBeenCalledTimes(1)', 'toHaveReturnedWith(1)', 'toMatchSnapshot()', 'toMatchInlineSnapshot()',
             'toThrowErrorMatchingSnapshot()', 'toContainEqual(1)', "toThrow('x')", 'toThrowError(Err)', "toHaveProperty('a', 1)",
             'toBeCustomMatcher(1)', 'toHaveBeenCalledOnce()']
TS_WEAK = ['toBeDefined()', 'toBeTruthy()', 'toBeFalsy()', 'toMatchObject({})', 'toHaveBeenCalled()', 'toBeCalled()', 'toHaveReturned()',
           'toContain(1)', 'toBeGreaterThan(1)', 'toBeGreaterThanOrEqual(1)', 'toBeLessThan(1)', 'toBeLessThanOrEqual(1)',
           'toBeInstanceOf(A)', 'toMatch(/a/)', 'toThrow()', 'toThrowError()', "toHaveProperty('a')"]


@pytest.mark.parametrize('matcher', TS_STRONG)
def test_V05_typescript_strong_matchers_including_unlisted_ones(matcher):
    assert ts_counts(f'expect(x).{matcher};') == (1, 0)


@pytest.mark.parametrize('matcher', TS_WEAK)
def test_V05_typescript_weak_matchers(matcher):
    assert ts_counts(f'expect(x).{matcher};') == (0, 1)


TS_CHAINS = {
    'not-makes-it-weak': ('expect(x).not.toBe(1);', (0, 1)),
    'not-null-is-weak': ('expect(x).not.toBeNull();', (0, 1)),
    'not-called-is-strong': ('expect(f).not.toHaveBeenCalled();', (1, 0)),
    'not-called-alias-is-strong': ('expect(f).not.toBeCalled();', (1, 0)),
    'not-called-with-is-weak': ('expect(f).not.toHaveBeenCalledWith(1);', (0, 1)),
    'resolves': ('await expect(p).resolves.toBe(1);', (1, 0)),
    'rejects-with-argument': ("await expect(p).rejects.toThrow('x');", (1, 0)),
    'rejects-without-argument': ('await expect(p).rejects.toThrow();', (0, 1)),
    'resolves-not': ('await expect(p).resolves.not.toBe(1);', (0, 1)),
    'expect-without-matcher': ('expect(x);', (0, 0)),
    'one-per-chain': ('expect(x).toBe(1);\nexpect(y).toBeDefined();\nexpect(z).toEqual(2);', (2, 1)),
    'inside-callback': ('await waitFor(() => {\n  expect(x).toBe(1);\n});', (1, 0)),
    'non-expect-call': ('foo(x);\nbar.baz(y);', (0, 0)),
}


@pytest.mark.parametrize('body, expected', TS_CHAINS.values(), ids=TS_CHAINS.keys())
def test_V05_typescript_chain_rules(body, expected):
    assert ts_counts(body) == expected


@pytest.mark.parametrize('call', ['assert.strictEqual(a, b)', 'assert.deepStrictEqual(a, b)', 'assert.equal(a, b)', 'assert.deepEqual(a, b)',
                                  'assert.throws(() => f())', 'assert.rejects(p)'])
def test_V05_node_assert_strong_calls(call):
    assert ts_counts(call + ';') == (1, 0)


@pytest.mark.parametrize('call', ['assert(x)', 'assert.ok(x)', 'assert.notEqual(a, b)', 'assert.notStrictEqual(a, b)', 'assert.notDeepEqual(a, b)'])
def test_V05_node_assert_weak_calls(call):
    assert ts_counts(call + ';') == (0, 1)


def kt_counts(body):
    source = 'class T {\n    @Test\n    fun a() {\n' + indent(body.rstrip('\n') + '\n', 8) + '    }\n}\n'
    row = case_row('src/test/kotlin/TTest.kt', source, 'T.a')
    return row['strong_assertions'], row['weak_assertions']


KT_STRONG = ['assertEquals(1, x)', 'assertSame(a, b)', 'assertContentEquals(a, b)', 'assertArrayEquals(a, b)', 'assertNull(x)',
             'assertFailsWith<IllegalStateException> { f() }', 'assertThrows<IllegalStateException> { f() }', 'verify { m.f() }',
             'coVerify { m.f() }', 'verifyOrder { m.f() }', 'verifySequence { m.f() }', 'assertCustom(x)', 'verifyThing(x)', 'expectSomething(x)']
KT_WEAK = ['assertTrue(x)', 'assertFalse(x)', 'assertNotNull(x)', 'assertNotEquals(a, b)', 'assertNotSame(a, b)', 'assertIs<String>(x)',
           'assertIsNot<String>(x)', 'assertContains(xs, 1)', 'assertFails { f() }']


@pytest.mark.parametrize('call', KT_STRONG)
def test_V05_kotlin_strong_calls(call):
    assert kt_counts(call) == (1, 0)


@pytest.mark.parametrize('call', KT_WEAK)
def test_V05_kotlin_weak_calls(call):
    assert kt_counts(call) == (0, 1)


@pytest.mark.parametrize('call', ['println(x)', 'foo(x)', 'val y = compute(x)'])
def test_V05_kotlin_other_calls_are_not_assertions(call):
    assert kt_counts(call) == (0, 0)


@pytest.mark.parametrize('matcher', ['isNotNull()', 'isTrue()', 'isFalse()', 'isNotEmpty()', 'contains(1)', 'isNotEqualTo(2)',
                                     'isInstanceOf(String::class.java)', 'isGreaterThan(1)', 'isLessThan(1)', 'isAtLeast(1)', 'isAtMost(1)'])
def test_V05_kotlin_assertThat_chain_weak_matcher_counts_one_weak_assertion(matcher):
    assert kt_counts(f'assertThat(x).{matcher}') == (0, 1)


@pytest.mark.parametrize('matcher', ['isEqualTo(1)', 'isNull()', 'isEmpty()', 'hasSize(2)'])
def test_V05_kotlin_assertThat_chain_unlisted_matcher_counts_one_strong_assertion(matcher):
    assert kt_counts(f'assertThat(x).{matcher}') == (1, 0)


def test_V05_kotlin_assertions_inside_lambda_are_counted_and_other_cases_are_not():
    source = ('class T {\n    @Test\n    fun a() {\n        run {\n            assertEquals(1, x)\n        }\n    }\n\n    @Test\n    fun b() {\n'
              '        assertTrue(y)\n        assertTrue(z)\n    }\n}\n')
    assert counts_of('src/test/kotlin/TTest.kt', source, 'T.a')[:2] == (1, 0)
    assert counts_of('src/test/kotlin/TTest.kt', source, 'T.b')[:2] == (0, 2)


@pytest.mark.parametrize('chain, expected', [
    ('assertThat(x).isNotNull()', (0, 1)), ('assertThat(x).isNotNull().isEqualTo(y)', (1, 0)), ('assertThat(x).isEqualTo(y).isNotNull()', (0, 1)),
    ('assertThat(x)', (0, 0)), ('assertThat(x).isEqualTo(y)\nassertThat(z).isTrue()', (1, 1)),
], ids=['single-weak', 'weak-then-strong', 'strong-then-weak', 'no-matcher', 'two-chains'])
def test_V05_kotlin_assertThat_one_assertion_per_chain_decided_by_the_last_matcher(chain, expected):
    assert kt_counts(chain) == expected


# ---------------------------------------------------------------------------------------------------------------------
# V06 mock counts, table M
# ---------------------------------------------------------------------------------------------------------------------

def py_mocks(body, header='', name='test_a'):
    return counts_of('tests/test_a.py', header + 'def test_a():\n' + indent(body.rstrip('\n') + '\n', 4), name)[2]


PY_MOCK_CALLS = ['patch("a.b")', 'patch.object(X, "y")', 'patch.dict(d, {})', 'patch.multiple(X, a=1)', 'mock.patch("a.b")',
                 'unittest.mock.patch("a.b")', 'mocker.patch("a.b")', 'mocker.patch.object(X, "y")', 'mock.patch.dict(d, {})',
                 'unittest.mock.patch.multiple(X, a=1)', 'Mock()', 'MagicMock()', 'AsyncMock()', 'NonCallableMock()', 'PropertyMock()',
                 'create_autospec(f)', 'mock.Mock()', 'unittest.mock.MagicMock()', 'mocker.AsyncMock()', 'mock.NonCallableMock()',
                 'unittest.mock.PropertyMock()', 'mocker.create_autospec(f)', 'monkeypatch.setattr(a, "b", 1)', 'monkeypatch.setitem(d, "k", 1)']


@pytest.mark.parametrize('call', PY_MOCK_CALLS)
def test_V06_python_each_mock_call_name_counts_one(call):
    assert py_mocks(call) == 1


def test_V06_python_other_calls_and_monkeypatch_setenv_are_not_mocks_and_each_call_counts():
    assert py_mocks('monkeypatch.setenv("A", "1")\nprint(1)\nx = make()') == 0
    assert py_mocks('Mock()\nMagicMock()\nwith patch("a.b"):\n    pass') == 3


def test_V06_python_decorators_on_the_case_count_one_each():
    source = ('@patch("a.b")\n@mock.patch.object(X, "y")\ndef test_a(m1, m2):\n    pass\n\n\n'
              '@pytest.mark.parametrize("v", [1])\ndef test_b(v):\n    pass\n')
    assert counts_of('tests/test_a.py', source, 'test_a')[2] == 2
    assert counts_of('tests/test_a.py', source, 'test_b')[2] == 0


def test_V06_python_class_decorator_module_top_level_case_decorator_and_body_all_count_and_other_scopes_do_not():
    source = ('FAKE = MagicMock()\n\n\ndef helper():\n    Mock()\n    Mock()\n\n\n@patch("c.d")\nclass TestK:\n    @patch("a.b")\n'
              '    def test_a(self, m):\n        Mock()\n\n    def test_b(self):\n        Mock()\n        Mock()\n        Mock()\n')
    assert counts_of('tests/test_a.py', source, 'TestK.test_a')[2] == 4
    assert counts_of('tests/test_a.py', source, 'TestK.test_b')[2] == 5


def test_V06_python_module_top_level_statement_counts_for_every_case_of_the_file():
    source = 'patcher = patch("x.y")\n\n\ndef test_a():\n    pass\n\n\ndef test_b():\n    pass\n'
    assert [counts_of('tests/test_a.py', source, n)[2] for n in ('test_a', 'test_b')] == [1, 1]


def ts_mocks(source, name):
    return counts_of('src/a.test.ts', source, name)[2]


TS_MOCK_CALLS = ["jest.mock('x')", 'jest.fn()', "jest.spyOn(o, 'm')", "jest.doMock('x')", "vi.mock('x')", 'vi.fn()', "vi.spyOn(o, 'm')"]


@pytest.mark.parametrize('call', TS_MOCK_CALLS)
def test_V06_typescript_each_mock_call_name_counts_one(call):
    source = f"it('a', () => {{\n  {call};\n}});\n"
    assert ts_mocks(source, 'a') == 1


def test_V06_typescript_non_mock_calls_do_not_count_and_two_calls_count_two():
    assert ts_mocks("it('a', () => {\n  jest.useFakeTimers();\n  foo.fn();\n  jest.fn();\n  vi.fn();\n});\n", 'a') == 2


def test_V06_typescript_describe_direct_statements_and_hooks_count_for_each_case_inside_and_other_cases_do_not():
    source = ("describe('D', () => {\n  const s = jest.fn();\n  beforeEach(() => {\n    jest.spyOn(x, 'y');\n  });\n  beforeAll(() => {\n"
              "    jest.mock('z');\n  });\n  it('a', () => {\n    jest.fn();\n    jest.fn();\n    jest.fn();\n  });\n  it('b', () => {\n  });\n});\n")
    assert ts_mocks(source, 'D > a') == 6
    assert ts_mocks(source, 'D > b') == 3


def test_V06_typescript_sibling_and_nested_describe_scopes():
    source = ("describe('D1', () => {\n  jest.fn();\n  it('x', () => {});\n});\n"
              "describe('D2', () => {\n  jest.fn();\n  jest.fn();\n  describe('inner', () => {\n    vi.fn();\n    it('c', () => {});\n  });\n"
              "  it('d', () => {});\n});\n")
    assert ts_mocks(source, 'D1 > x') == 1
    assert ts_mocks(source, 'D2 > inner > c') == 3
    assert ts_mocks(source, 'D2 > d') == 2


def test_V06_typescript_file_top_level_statements_count_for_every_case_in_the_file():
    source = ("jest.mock('a');\njest.mock('b');\nconst shared = vi.fn();\nbeforeEach(() => {\n  jest.spyOn(o, 'm');\n});\n"
              "describe('D', () => {\n  it('a', () => {});\n});\nit('b', () => {\n  jest.fn();\n});\n")
    assert ts_mocks(source, 'D > a') == 4
    assert ts_mocks(source, 'b') == 5


KT_MOCK_CALLS = ['mockk<A>()', 'spyk(x)', 'mockkObject(O)', 'mockkStatic(X::class)', 'mockkConstructor(X::class)', 'every { a.f() } returns 1',
                 'coEvery { a.f() } returns 1', 'mock(A::class.java)', 'whenever(a.f()).thenReturn(1)']


@pytest.mark.parametrize('call', KT_MOCK_CALLS)
def test_V06_kotlin_each_mock_call_name_counts_one(call):
    source = 'class T {\n    @Test\n    fun a() {\n        ' + call + '\n    }\n}\n'
    assert counts_of('src/test/kotlin/TTest.kt', source, 'T.a')[2] == 1


def test_V06_kotlin_case_body_property_initialisers_and_before_functions_count_and_other_functions_do_not():
    source = ('class T {\n    private val repo = mockk<Repo>()\n    lateinit var late: Repo\n\n    @Before\n    fun setUp() {\n        mockkObject(O)\n    }\n\n'
              '    @Test\n    fun a() {\n        every { repo.f() } returns 1\n    }\n\n    @Test\n    fun b() {\n        mockk<X>()\n        mockk<Y>()\n    }\n\n'
              '    fun helper() {\n        mockk<Z>()\n    }\n\n    @After\n    fun tearDown() {\n        mockk<W>()\n    }\n}\n')
    assert counts_of('src/test/kotlin/TTest.kt', source, 'T.a')[2] == 3
    assert counts_of('src/test/kotlin/TTest.kt', source, 'T.b')[2] == 4


def test_V06_python_outer_class_decorator_applies_to_a_case_of_a_nested_class():
    source = '@patch("x")\nclass TestOuter:\n    @patch("y")\n    class TestInner:\n        def test_a(self):\n            Mock()\n'
    assert counts_of('tests/test_a.py', source, 'TestOuter.TestInner.test_a')[2] == 3


def test_V06_kotlin_outer_class_properties_and_before_functions_apply_to_a_nested_class_case():
    source = ('class Outer {\n    private val r = mockk<R>()\n\n    @Before\n    fun setUp() {\n        mockkObject(O)\n    }\n\n'
              '    class Inner {\n        private val q = mockk<Q>()\n\n        @Test\n        fun a() {\n            spyk(x)\n        }\n    }\n}\n')
    assert counts_of('src/test/kotlin/TTest.kt', source, 'Outer.Inner.a')[2] == 4


def test_V06_kotlin_before_each_function_counts():
    source = ('class T {\n    @BeforeEach\n    fun setup() {\n        every { x.y() } returns 2\n        whenever(z.w()).thenReturn(1)\n    }\n\n'
              '    @Test\n    fun a() {\n    }\n}\n')
    assert counts_of('src/test/kotlin/TTest.kt', source, 'T.a')[2] == 2


# ---------------------------------------------------------------------------------------------------------------------
# V07 skipped, table S
# ---------------------------------------------------------------------------------------------------------------------

def py_skipped(decorators='', body='pass', class_decorators='', name='test_a'):
    if class_decorators:
        source = class_decorators + 'class TestK:\n' + indent(decorators + 'def test_a(self):\n' + indent(body, 4) + '\n', 4)
        name = 'TestK.test_a'
    else:
        source = decorators + 'def test_a():\n' + indent(body, 4) + '\n'
    return counts_of('tests/test_a.py', source, name)[3]


PY_SKIP_DECORATORS = ['@pytest.mark.skip\n', '@pytest.mark.skip(reason="r")\n', '@pytest.mark.skipif(True, reason="r")\n', '@pytest.mark.xfail\n',
                      '@unittest.skip("r")\n', '@unittest.skipIf(True, "r")\n', '@unittest.skipUnless(False, "r")\n', '@unittest.expectedFailure\n',
                      '@skip("r")\n', '@skipIf(True, "r")\n', '@skipUnless(False, "r")\n', '@expectedFailure\n']
PY_SKIP_MARK_FORMS = ['@mark.skip\n', '@mark.skip(reason="r")\n', '@mark.skipif(True, reason="r")\n', '@mark.xfail\n', '@mark.xfail(reason="r")\n']


@pytest.mark.parametrize('decorator', PY_SKIP_DECORATORS)
def test_V07_python_case_decorators_skip(decorator):
    assert py_skipped(decorators=decorator) is True


@pytest.mark.parametrize('decorator', PY_SKIP_DECORATORS)
def test_V07_python_class_decorators_skip_every_case(decorator):
    assert py_skipped(class_decorators=decorator) is True


@pytest.mark.parametrize('body', ['pytest.skip("r")', 'self.skipTest("r")'])
def test_V07_python_skip_calls_in_the_body(body):
    assert py_skipped(body=body) is True


def test_V07_python_unrelated_decorators_and_skip_in_another_case_do_not_skip():
    assert py_skipped(decorators='@pytest.mark.parametrize("v", [1])\n') is False
    assert py_skipped() is False
    source = 'def test_a():\n    pass\n\n\ndef test_b():\n    pytest.skip("r")\n\n\n@pytest.mark.skip\ndef test_c():\n    pass\n'
    assert [counts_of('tests/test_a.py', source, n)[3] for n in ('test_a', 'test_b', 'test_c')] == [False, True, True]


@pytest.mark.parametrize('call, expected', [("it.skip('a', () => {})", True), ("test.skip('a', () => {})", True), ("xit('a', () => {})", True),
                                            ("xtest('a', () => {})", True), ("it.todo('a')", True), ("test.todo('a')", True),
                                            ("it('a', () => {})", False), ("test('a', () => {})", False), ("it.only('a', () => {})", False),
                                            ("fit('a', () => {})", False), ("it.each([1])('a', () => {})", False)])
def test_V07_typescript_case_forms(call, expected):
    assert counts_of('src/a.test.ts', call + ';\n', 'a')[3] is expected


@pytest.mark.parametrize('wrapper, expected', [('describe.skip', True), ('xdescribe', True), ('describe', False), ('describe.only', False)])
def test_V07_typescript_enclosing_describe_skip_is_inherited_by_every_case(wrapper, expected):
    source = f"{wrapper}('D', () => {{\n  it('a', () => {{}});\n  describe('inner', () => {{\n    it('b', () => {{}});\n  }});\n}});\n"
    assert counts_of('src/a.test.ts', source, 'D > a')[3] is expected
    assert counts_of('src/a.test.ts', source, 'D > inner > b')[3] is expected


@pytest.mark.parametrize('annotation, expected', [('@Ignore', True), ('@Disabled', True), ('@Ignore("r")', True), ('@Disabled("r")', True),
                                                  ('@Before', False)])
def test_V07_kotlin_case_annotations(annotation, expected):
    source = f'class T {{\n    @Test\n    {annotation}\n    fun a() {{\n    }}\n}}\n'
    assert counts_of('src/test/kotlin/TTest.kt', source, 'T.a')[3] is expected


def test_V07_python_outer_class_skip_applies_to_a_case_of_a_nested_class():
    source = '@pytest.mark.skip\nclass TestOuter:\n    class TestInner:\n        def test_a(self):\n            pass\n'
    assert counts_of('tests/test_a.py', source, 'TestOuter.TestInner.test_a')[3] is True


def test_V07_kotlin_outer_class_ignore_applies_to_a_case_of_a_nested_class():
    source = '@Ignore\nclass Outer {\n    class Inner {\n        @Test\n        fun a() {\n        }\n    }\n}\n'
    assert counts_of('src/test/kotlin/TTest.kt', source, 'Outer.Inner.a')[3] is True


def test_V07_typescript_outer_describe_skip_applies_three_levels_down():
    source = "xdescribe('A', () => {\n  describe('B', () => {\n    describe('C', () => {\n      it('d', () => {});\n    });\n  });\n});\n"
    assert counts_of('src/a.test.ts', source, 'A > B > C > d')[3] is True


@pytest.mark.parametrize('annotation, expected', [('@Ignore', True), ('@Disabled', True), ('@RunWith(X::class)', False)])
def test_V07_kotlin_class_annotation_is_inherited_by_every_case(annotation, expected):
    source = f'{annotation}\nclass T {{\n    @Test\n    fun a() {{\n    }}\n\n    @Test\n    fun b() {{\n    }}\n}}\n'
    assert [counts_of('src/test/kotlin/TTest.kt', source, n)[3] for n in ('T.a', 'T.b')] == [expected, expected]


@pytest.mark.parametrize('decorator', PY_SKIP_MARK_FORMS)
def test_V07_python_mark_prefix_omitted_decorator_forms_skip(decorator):
    assert py_skipped(decorators=decorator) is True
    assert py_skipped(class_decorators=decorator) is True
