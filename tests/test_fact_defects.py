"""Evidence for spec 7ab6320d2eb56ccf v1 (analyzer fact defects F11, F7, F8, F9-lines).
Expected values come from the spec text: the reference line counter (R1/R2), the reference relative resolver (R5)
and hand-written edge tables. Product output is never used to derive an expectation.
Tests named *_characterization keep behaviour that the spec says must not change (R12)."""
import random

import pytest

from fixtures.registry import fixture_root
from repository.models import SourceText
from tests.fact_defects_support import (CONTROL_CHARS, TS_EXTENSIONS, arch_edges, arch_node, candidates_of, edge_rows,
                                        kotlin_analyze, kt_file_of, node_rows, python_analyze, ref_line_count, ref_lines,
                                        ref_resolve_relative, run_pipeline, ts_analyze, ts_file_of, write_tree)

NESTJS_ARGS = ('-l', 'typescript', '-f', 'nestjs')


# ---------------------------------------------------------------- V1: SourceText.lines (R1, R2, C1-C4)

V1_CASES = {
    'C1-five-lines-trailing-lf': ('a\nb\nc\nd\ne\n', 5),
    'C2-empty': ('', 0),
    'C2-single-lf': ('\n', 1),
    'C2-one-char-no-lf': ('a', 1),
    'C2-blank-line-after': ('a\n\n', 2),
    'C3-formfeed': ('a\x0cb\n', 1),
    'C3-lone-cr': ('a\rb\n', 1),
    'C3-nbsp-like-space': ('a b', 1),
    'C4-crlf-trailing': ('a\r\nb\r\n', 2),
    'EP-no-trailing-lf': ('a\nb', 2),
    'EP-crlf-no-trailing': ('a\r\nb', 2),
    'EP-lone-cr-at-end': ('a\r', 1),
    'EP-cr-before-lf-only-once': ('a\r\r\nb', 2),
    'BVA-only-crlf': ('\r\n', 1),
    'BVA-only-cr': ('\r', 1),
    'BVA-lf-lf': ('\n\n', 2),
}


@pytest.mark.parametrize('label', sorted(V1_CASES))
def test_V1_lines_length_matches_reference_for_partitions(label):
    text, expected = V1_CASES[label]
    assert ref_line_count(text) == expected  # oracle self-check against the spec table
    lines = SourceText(text).lines
    assert len(lines) == expected
    assert tuple(lines) == ref_lines(text)


@pytest.mark.parametrize('char', CONTROL_CHARS + (' ',), ids=lambda c: 'U+%04X' % ord(c))
def test_V1_C3_non_separator_characters_do_not_split_and_are_preserved(char):
    for template in ('a{c}b\n', 'a{c}b', '{c}', 'a{c}\nb{c}\n'):
        text = template.format(c=char)
        lines = SourceText(text).lines
        assert len(lines) == ref_line_count(text)
        assert tuple(lines) == ref_lines(text)
        assert char in ''.join(lines)


def test_V1_C4_crlf_lines_content():
    assert tuple(SourceText('a\r\nb\r\n').lines) == ('a', 'b')


def test_V1_only_cr_before_lf_is_removed_and_only_once():
    assert tuple(SourceText('a\r\r\nb').lines) == ('a\r', 'b')
    assert tuple(SourceText('x\r').lines) == ('x\r',)


def test_V1_returned_text_is_still_the_original_string():
    text = 'a\r\nb\x0c\n'
    assert str(SourceText(text)) == text


def test_V1_seeded_random_agrees_with_reference():
    rng = random.Random(20261019)
    alphabet = ['a', 'b', '\n', '\r\n', '\r', *CONTROL_CHARS, ' ', '']
    for _ in range(400):
        text = ''.join(rng.choice(alphabet) for _ in range(rng.randint(0, 12)))
        lines = SourceText(text).lines
        assert len(lines) == ref_line_count(text), repr(text)
        assert tuple(lines) == ref_lines(text), repr(text)


# ---------------------------------------------------------------- V2: end_line / line_count (R2, R3, C5, C6)

LANGUAGES = {
    'python': ('.py', python_analyze, lambda stem: f'py:{stem}', '# c\n'),
    'typescript': ('.ts', ts_analyze, lambda stem: f'ts:{stem}.ts', '// c\n'),
    'kotlin': ('.kt', kotlin_analyze, lambda stem: f'kotlin:{stem}.kt', '// c\n'),
}
ENDINGS = {
    'trailing-lf': lambda row, n: row * n,
    'no-trailing-lf': lambda row, n: row * (n - 1) + row.rstrip('\n'),
}


@pytest.mark.parametrize('language', sorted(LANGUAGES))
@pytest.mark.parametrize('ending', sorted(ENDINGS))
def test_V2_module_end_line_follows_reference_line_count(tmp_path, language, ending):
    suffix, analyze, node_id, row = LANGUAGES[language]
    text = ENDINGS[ending](row, 5)
    write_tree(tmp_path, {'m' + suffix: text})
    node = node_rows(analyze(tmp_path))[node_id('m')]
    assert ref_line_count(text) == 5
    assert node['span']['start_line'] == 1
    assert node['span']['end_line'] == max(1, ref_line_count(text))


@pytest.mark.parametrize('language', sorted(LANGUAGES))
def test_V2_empty_file_module_end_line_is_one_and_line_count_zero(tmp_path, language):
    suffix, analyze, node_id, _ = LANGUAGES[language]
    write_tree(tmp_path, {'m' + suffix: ''})
    node = node_rows(analyze(tmp_path))[node_id('m')]
    assert node['span']['end_line'] == max(1, ref_line_count('')) == 1


@pytest.mark.parametrize('language', sorted(LANGUAGES))
def test_V2_one_line_without_lf_is_end_line_one(tmp_path, language):
    suffix, analyze, node_id, row = LANGUAGES[language]
    write_tree(tmp_path, {'m' + suffix: row.rstrip('\n')})
    node = node_rows(analyze(tmp_path))[node_id('m')]
    assert node['span']['end_line'] == 1


FILE_TEXTS = {
    'trailing-lf': lambda row: row * 5,
    'no-trailing-lf': lambda row: row * 4 + row.rstrip('\n'),
    'formfeed-inside-line': lambda row: row * 3 + row.rstrip('\n') + '\x0c\n' + row,
    'crlf': lambda row: (row.rstrip('\n') + '\r\n') * 5,
}


@pytest.mark.parametrize('language', sorted(LANGUAGES))
@pytest.mark.parametrize('shape', sorted(FILE_TEXTS))
def test_V2_file_granularity_node_line_count_and_span(tmp_path, language, shape):
    suffix, _, _, row = LANGUAGES[language]
    text = FILE_TEXTS[shape](row)
    write_tree(tmp_path / 'proj', {'m' + suffix: text})
    args = ('-l', language)
    _, _, arch = run_pipeline(tmp_path / 'proj', tmp_path, 'file', *args)
    node = arch_node(arch, 'file:m' + suffix)
    expected = ref_line_count(text)
    assert node.cost.line_count == expected
    assert node.span.end_line == max(1, expected)


@pytest.mark.parametrize('language', sorted(LANGUAGES))
def test_V2_file_granularity_empty_file_has_line_count_zero(tmp_path, language):
    suffix = LANGUAGES[language][0]
    write_tree(tmp_path / 'proj', {'empty' + suffix: '', 'other' + suffix: LANGUAGES[language][3]})
    _, _, arch = run_pipeline(tmp_path / 'proj', tmp_path, 'file', '-l', language)
    assert arch_node(arch, 'file:empty' + suffix).cost.line_count == ref_line_count('') == 0


@pytest.mark.parametrize('language', sorted(LANGUAGES))
def test_V2_C6_single_168kb_line_counts_one_line(tmp_path, language):
    suffix, _, _, row = LANGUAGES[language]
    marker = '#' if language == 'python' else '//'
    text = marker + ' ' + 'a' * (168 * 1024) + '\n'
    assert ref_line_count(text) == 1 and '\x0c' not in text
    write_tree(tmp_path / 'proj', {'big' + suffix: text, 'small' + suffix: row})
    _, _, arch = run_pipeline(tmp_path / 'proj', tmp_path, 'file', '-l', language)
    node = arch_node(arch, 'file:big' + suffix)
    assert node.cost.line_count == 1
    assert node.span.end_line == 1


# ---------------------------------------------------------------- V3: large_node boundary (R4, C5)

THRESHOLD = 5


def large_nodes(tmp_path, language, line_count, no_trailing_lf=False):
    suffix, _, _, row = LANGUAGES[language]
    text = row * line_count
    if no_trailing_lf:
        text = text.rstrip('\n')
    write_tree(tmp_path / 'proj', {'m' + suffix: text})
    payload, _, _ = run_pipeline(tmp_path / 'proj', tmp_path, 'symbol', '-l', language, threshold=THRESHOLD)
    assert payload['edge_weights']['large_node_line_threshold'] == THRESHOLD
    return candidates_of(payload, 'large_node'), text


@pytest.mark.parametrize('line_count,is_candidate', [(THRESHOLD - 1, False), (THRESHOLD, False), (THRESHOLD + 1, True)])
def test_V3_python_symbol_granularity_large_node_boundary(tmp_path, line_count, is_candidate):
    found, text = large_nodes(tmp_path, 'python', line_count)
    assert ref_line_count(text) == line_count
    if is_candidate:
        assert len(found) == 1
        assert found[0]['target'] == 'py:m'
        assert found[0]['metrics'] == {'line_count': line_count, 'line_threshold': THRESHOLD}
    else:
        assert found == []


def test_V3_python_six_lines_without_trailing_lf_is_candidate_with_six(tmp_path):
    found, text = large_nodes(tmp_path, 'python', 6, no_trailing_lf=True)
    assert ref_line_count(text) == 6
    assert [c['metrics']['line_count'] for c in found] == [6]


@pytest.mark.parametrize('language', ['typescript', 'kotlin'])
def test_V3_threshold_value_file_is_not_a_candidate(tmp_path, language):
    found, text = large_nodes(tmp_path, language, THRESHOLD)
    assert ref_line_count(text) == THRESHOLD
    assert found == []


# ---------------------------------------------------------------- V4: TypeScript relative resolution (R5, R6)

def ts_project(tmp_path, files):
    write_tree(tmp_path / 'proj', files)
    return tmp_path / 'proj'


def module_paths(files):
    return {name for name in files if name.endswith(TS_EXTENSIONS)}


def imports_from(root, importer):
    """Target files of IMPORTS edges leaving `importer` (file node)."""
    source = 'ts:' + importer
    return sorted(ts_file_of(t) for f, r, t, *_ in edge_rows(ts_analyze(root)) if f == source and r == 'IMPORTS')


RULE_CASES = {
    # label: (importer, specifier, files, expected target or None)
    'rule1-explicit-extension': ('a/b.spec.ts', './x.entity.ts',
                                 {'a/x.entity.ts': 'export class X {}\n', 'a/x.ts': 'export class W {}\n'}, 'a/x.entity.ts'),
    'rule2-dotted-name-gets-extension-appended': ('a/b.spec.ts', './x.entity',
                                                  {'a/x.entity.ts': 'export class X {}\n', 'a/x.ts': 'export class W {}\n'},
                                                  'a/x.entity.ts'),
    'rule2-parent-dir-and-two-dots': ('a/sub/b.ts', '../shared/tag.entity.dto',
                                      {'a/shared/tag.entity.dto.ts': 'export class D {}\n', 'a/shared/tag.ts': 'export {}\n'},
                                      'a/shared/tag.entity.dto.ts'),
    'rule2-later-extension-when-ts-absent': ('a/b.ts', './view.model',
                                             {'a/view.model.tsx': 'export const V = 1;\n', 'a/view.ts': 'export {}\n'},
                                             'a/view.model.tsx'),
    'rule3-js-specifier-replaced-by-ts': ('a/b.ts', './foo.js', {'a/foo.ts': 'export const F = 1;\n'}, 'a/foo.ts'),
    'rule3-js-specifier-later-extension': ('a/b.ts', './foo.js', {'a/foo.tsx': 'export const F = 1;\n'}, 'a/foo.tsx'),
    'rule3-dotted-js-specifier': ('a/b.ts', './foo.bar.js', {'a/foo.bar.ts': 'export const F = 1;\n', 'a/foo.ts': 'export {}\n'},
                                  'a/foo.bar.ts'),
    'rule1-js-file-itself-wins-over-ts': ('a/b.ts', './foo.js', {'a/foo.js': 'export const F = 1;\n', 'a/foo.ts': 'export {}\n'},
                                          'a/foo.js'),
    'rule4-directory-index': ('a/b.ts', './dir',
                              {'a/dir/index.ts': 'export class I {}\n'}, 'a/dir/index.ts'),
    'rule4-dotted-directory-index': ('a/b.ts', './my.dir',
                                     {'a/my.dir/index.ts': 'export class I {}\n', 'a/my.ts': 'export {}\n'}, 'a/my.dir/index.ts'),
    'rule5-extension-wins-over-index': ('a/b.ts', './x',
                                        {'a/x.ts': 'export class P {}\n', 'a/x/index.ts': 'export class Q {}\n'}, 'a/x.ts'),
    'rule5-dotted-extension-wins-over-index': ('a/b.ts', './y.entity',
                                               {'a/y.entity.ts': 'export class P {}\n', 'a/y.entity/index.ts': 'export class Q {}\n'},
                                               'a/y.entity.ts'),
    'rule6-missing-dotted': ('a/b.ts', './missing.entity', {'a/other.ts': 'export {}\n'}, None),
    'rule6-missing-plain': ('a/b.ts', './missing', {'a/other.ts': 'export {}\n'}, None),
    'rule7-outside-project': ('a/b.ts', '../../outside', {'a/other.ts': 'export {}\n'}, None),
}


@pytest.mark.parametrize('label', sorted(RULE_CASES))
def test_V4_static_import_rule_decision_table(tmp_path, label):
    importer, specifier, extra, expected = RULE_CASES[label]
    files = {importer: f"import * as target from '{specifier}';\nexport const used = target;\n", **extra}
    root = ts_project(tmp_path, files)
    (tmp_path / 'outside.ts').write_text('export const Q = 1;\n')
    assert ref_resolve_relative(importer, specifier, module_paths(files)) == expected  # oracle self-check
    assert imports_from(root, importer) == ([expected] if expected else [])
    if expected is None:
        edges = [row for row in edge_rows(ts_analyze(root)) if row[0].startswith('ts:' + importer)]
        assert all(row[1] not in ('IMPORTS', 'IMPORTS_SYMBOL') for row in edges)


def test_V4_rule1_to_rule4_edges_are_exact_static_certain(tmp_path):
    files = {'a/b.ts': "import { X } from './x.entity';\n", 'a/x.entity.ts': 'export class X {}\n', 'a/x.ts': 'export {}\n'}
    root = ts_project(tmp_path, files)
    rows = [r for r in edge_rows(ts_analyze(root)) if r[0] == 'ts:a/b.ts' and r[1] == 'IMPORTS']
    assert rows == [('ts:a/b.ts', 'IMPORTS', 'ts:a/x.entity.ts', 'static_certain', 'exact', ())]


def test_V4_failed_specifier_does_not_stop_later_imports(tmp_path):
    files = {'a/b.ts': "import { Q } from './missing.entity';\nimport { X } from './x.entity';\nexport const u = [Q, X];\n",
             'a/x.entity.ts': 'export class X {}\n'}
    root = ts_project(tmp_path, files)
    assert imports_from(root, 'a/b.ts') == ['a/x.entity.ts']


def test_V4_path_static_import_with_symbol_binding(tmp_path):
    files = {'a/use.ts': "import { C } from './c.entity';\nexport function g(x: C) { return x; }\n",
             'a/c.entity.ts': 'export class C {}\n', 'a/c.ts': 'export class Decoy {}\n'}
    root = ts_project(tmp_path, files)
    rows = edge_rows(ts_analyze(root))
    symbol_rows = [r for r in rows if r[0] == 'ts:a/use.ts' and r[1] == 'IMPORTS_SYMBOL']
    assert symbol_rows == [('ts:a/use.ts', 'IMPORTS_SYMBOL', 'ts:a/c.entity.ts#C', 'static_certain', 'exact', ())]
    assert imports_from(root, 'a/use.ts') == ['a/c.entity.ts']


def test_V4_path_import_binding_reference_resolution(tmp_path):
    """R6: reference resolution that goes through the import binding reaches the dotted-name file."""
    files = {'a/use.ts': "import { C } from './c.entity';\nexport function g(x: C) { return x; }\n",
             'a/c.entity.ts': 'export class C {}\n', 'a/other.ts': 'export class C {}\n'}
    root = ts_project(tmp_path, files)
    rows = [r for r in edge_rows(ts_analyze(root)) if r[0] == 'ts:a/use.ts#g' and r[1] == 'TYPE_USES']
    assert rows == [('ts:a/use.ts#g', 'TYPE_USES', 'ts:a/c.entity.ts#C', 'static_certain', 'exact', ())]


def test_V4_C10_path_re_export(tmp_path):
    files = {'a/index.ts': "export * from './a.dto';\n", 'a/a.dto.ts': 'export class A {}\n', 'a/a.ts': 'export class Decoy {}\n'}
    root = ts_project(tmp_path, files)
    rows = edge_rows(ts_analyze(root))
    re_exports = [r for r in rows if r[0] == 'ts:a/index.ts' and r[1] == 'RE_EXPORTS']
    assert re_exports and {ts_file_of(r[2]) for r in re_exports} == {'a/a.dto.ts'}
    assert all(r[4] == 'exact' for r in re_exports)


def test_V4_C10_path_named_re_export(tmp_path):
    files = {'a/index.ts': "export { A } from './a.dto';\n", 'a/a.dto.ts': 'export class A {}\n'}
    rows = edge_rows(ts_analyze(ts_project(tmp_path, files)))
    re_exports = [r for r in rows if r[0] == 'ts:a/index.ts' and r[1] == 'RE_EXPORTS']
    assert re_exports and {ts_file_of(r[2]) for r in re_exports} == {'a/a.dto.ts'}


def test_V4_C10_path_dynamic_import(tmp_path):
    files = {'a/lazy.ts': "export async function load() { return import('./b.service'); }\n",
             'a/b.service.ts': 'export class B {}\n', 'a/b.ts': 'export class Decoy {}\n'}
    root = ts_project(tmp_path, files)
    rows = [r for r in edge_rows(ts_analyze(root)) if r[0] == 'ts:a/lazy.ts' and r[1] == 'IMPORTS']
    assert [ts_file_of(r[2]) for r in rows] == ['a/b.service.ts']
    assert rows[0][3] == 'dynamic_required'  # characterization: dynamic import keeps its confidence


def test_V4_dotted_directory_names_in_the_importer_path(tmp_path):
    files = {'a.b/c.d/user.spec.ts': "import { U } from '../user.entity';\nexport const u = U;\n",
             'a.b/user.entity.ts': 'export class U {}\n', 'a.b/user.ts': 'export {}\n'}
    root = ts_project(tmp_path, files)
    assert imports_from(root, 'a.b/c.d/user.spec.ts') == ['a.b/user.entity.ts']


@pytest.mark.parametrize('dots', [0, 1, 2, 3])
def test_V4_seeded_filename_dot_counts_match_reference_resolver(tmp_path, dots):
    rng = random.Random(20261019 + dots)
    stem = '.'.join(rng.choice(['tag', 'entity', 'dto', 'service']) for _ in range(dots + 1))
    files = {'src/importer.ts': f"import {{ Z }} from './{stem}';\nexport const z = Z;\n",
             f'src/{stem}.ts': 'export const Z = 1;\n'}
    root = ts_project(tmp_path, files)
    expected = ref_resolve_relative('src/importer.ts', './' + stem, module_paths(files))
    assert expected == f'src/{stem}.ts'
    assert imports_from(root, 'src/importer.ts') == [expected]


# ---------------------------------------------------------------- V5: TESTS edge and untested_hub (R7, C7)

def test_V5_C7_synthetic_project_imports_tests_edge_and_no_untested_hub(tmp_path):
    files = {'a/b.spec.ts': "import { X } from './x.entity';\nit('x', () => new X());\n",
             'a/x.entity.ts': 'export class X {}\n',
             'a/orphan.ts': 'export class Orphan {}\n'}
    write_tree(tmp_path / 'proj', files)
    expected_imports = ('file:a/b.spec.ts', 'IMPORTS', 'file:a/x.entity.ts', 'static_certain', 'exact', ())
    language_rows = edge_rows(ts_analyze(tmp_path / 'proj'))
    assert ('ts:a/b.spec.ts', 'IMPORTS', 'ts:a/x.entity.ts', 'static_certain', 'exact', ()) in language_rows
    payload, _, arch = run_pipeline(tmp_path / 'proj', tmp_path, 'file', '-l', 'typescript')
    edges = arch_edges(arch)
    assert expected_imports in edges
    assert ('file:a/b.spec.ts', 'TESTS', 'file:a/x.entity.ts', 'static_certain', 'exact', ()) in edges
    hubs = {c['target'] for c in candidates_of(payload, 'untested_hub')}
    assert 'file:a/x.entity.ts' not in hubs
    assert 'file:a/orphan.ts' in hubs  # negative control: an untested production file is still a hub


def test_V5_C7_synthetic_project_with_nestjs_adapter(tmp_path):
    files = {'a/b.spec.ts': "import { X } from './x.entity';\nit('x', () => new X());\n", 'a/x.entity.ts': 'export class X {}\n'}
    write_tree(tmp_path / 'proj', files)
    payload, _, arch = run_pipeline(tmp_path / 'proj', tmp_path, 'file', *NESTJS_ARGS)
    assert ('file:a/b.spec.ts', 'TESTS', 'file:a/x.entity.ts', 'static_certain', 'exact', ()) in arch_edges(arch)
    assert 'file:a/x.entity.ts' not in {c['target'] for c in candidates_of(payload, 'untested_hub')}


@pytest.fixture(scope='module')
def nestjs_file_run(tmp_path_factory):
    return run_pipeline(fixture_root('typescript-nestjs-realworld'), tmp_path_factory.mktemp('nestjs-file'), 'file', *NESTJS_ARGS)


def test_V5_real_fixture_tag_spec_tests_tag_entity(nestjs_file_run):
    payload, _, arch = nestjs_file_run
    spec, entity = 'file:src/tag/tag.controller.spec.ts', 'file:src/tag/tag.entity.ts'
    tests_edges = [e for e in arch_edges(arch) if e[0] == spec and e[1] == 'TESTS' and e[2] == entity]
    assert len(tests_edges) == 1
    assert {c['target'] for c in candidates_of(payload, 'untested_hub')}.isdisjoint({entity})


def test_V5_real_fixture_imports_edge_exists_for_dotted_specifier(nestjs_file_run):
    _, _, arch = nestjs_file_run
    spec, entity = 'file:src/tag/tag.controller.spec.ts', 'file:src/tag/tag.entity.ts'
    assert any(e[0] == spec and e[1] == 'IMPORTS' and e[2] == entity and e[4] == 'exact' for e in arch_edges(arch))


# ---------------------------------------------------------------- V6/V7: Kotlin import FQN resolution (R8-R11)

USE_TEMPLATE = 'package com.c\n\nimport {imp}\n\nclass Use {{\n    fun make(): {name} = {name}()\n}}\n'
C11_FILES = {
    'com/a/Foo.kt': 'package com.a\n\nclass Foo {\n    fun hi() = 1\n}\n',
    'com/b/Foo.kt': 'package com.b\n\nclass Foo\n',
    'com/c/Use.kt': USE_TEMPLATE.format(imp='com.a.Foo', name='Foo'),
}
USE = 'kotlin:com/c/Use.kt'
IMPORT_RELATIONS = ('IMPORTS', 'IMPORTS_SYMBOL')


def kotlin_rows(tmp_path, files):
    write_tree(tmp_path / 'proj', files)
    return edge_rows(kotlin_analyze(tmp_path / 'proj'))


def import_rows(rows, relation):
    return [r for r in rows if r[0] == USE and r[1] == relation]


def test_V6_C11_single_fqn_match_is_exact_certain_without_candidates(tmp_path):
    rows = kotlin_rows(tmp_path, C11_FILES)
    assert import_rows(rows, 'IMPORTS_SYMBOL') == [(USE, 'IMPORTS_SYMBOL', 'kotlin:com/a/Foo.kt#Foo', 'static_certain', 'exact', ())]
    assert import_rows(rows, 'IMPORTS') == [(USE, 'IMPORTS', 'kotlin:com/a/Foo.kt', 'static_certain', 'exact', ())]


def test_V6_C11_no_edge_leaks_to_the_other_package(tmp_path):
    rows = kotlin_rows(tmp_path, C11_FILES)
    leaked = [r for r in rows if r[0].startswith(USE) and ('com/b/' in r[2] or any('com/b/' in c for c in r[5]))]
    assert leaked == []


def test_V6_C12_two_declarations_of_same_fqn_are_ambiguous_first_symbol_id_is_target(tmp_path):
    files = {'com/a/Foo.kt': 'package com.a\n\nclass Foo\n', 'com/a/Other.kt': 'package com.a\n\nclass Foo\n',
             'com/b/Foo.kt': 'package com.b\n\nclass Foo\n',
             'com/c/Use.kt': USE_TEMPLATE.format(imp='com.a.Foo', name='Foo')}
    rows = kotlin_rows(tmp_path, files)
    assert import_rows(rows, 'IMPORTS_SYMBOL') == [
        (USE, 'IMPORTS_SYMBOL', 'kotlin:com/a/Foo.kt#Foo', 'static_inferred', 'ambiguous', ('kotlin:com/a/Other.kt#Foo',))]
    file_edges = import_rows(rows, 'IMPORTS')
    assert [(r[2], r[3], r[4]) for r in file_edges] == [('kotlin:com/a/Foo.kt', 'static_inferred', 'ambiguous')]
    assert all('com/b/' not in c for r in import_rows(rows, 'IMPORTS_SYMBOL') for c in r[5])


def test_V6_C12_three_declarations_candidates_are_the_remaining_ones_in_order(tmp_path):
    files = {'com/a/Foo.kt': 'package com.a\n\nclass Foo\n', 'com/a/Other.kt': 'package com.a\n\nclass Foo\n',
             'com/a/Zed.kt': 'package com.a\n\nclass Foo\n',
             'com/c/Use.kt': USE_TEMPLATE.format(imp='com.a.Foo', name='Foo')}
    rows = import_rows(kotlin_rows(tmp_path, files), 'IMPORTS_SYMBOL')
    assert len(rows) == 1
    assert rows[0][2] == 'kotlin:com/a/Foo.kt#Foo'
    assert sorted(rows[0][5]) == ['kotlin:com/a/Other.kt#Foo', 'kotlin:com/a/Zed.kt#Foo']
    assert (rows[0][3], rows[0][4]) == ('static_inferred', 'ambiguous')


def test_V6_C12_fqn_zero_matches_external_library_unique_name_fallback_characterization(tmp_path):
    """Characterization (base behaviour, R9 last sentence): an import whose FQN matches nothing keeps simple-name resolution."""
    files = {'com/a/Foo.kt': 'package com.a\n\nclass Foo\n', 'com/c/Use.kt': USE_TEMPLATE.format(imp='org.ext.Foo', name='Foo')}
    rows = kotlin_rows(tmp_path, files)
    assert import_rows(rows, 'IMPORTS_SYMBOL') == [(USE, 'IMPORTS_SYMBOL', 'kotlin:com/a/Foo.kt#Foo', 'static_inferred', 'unique_name', ())]


def test_V6_C12_fqn_zero_matches_external_library_ambiguous_fallback_characterization(tmp_path):
    files = {'com/a/Foo.kt': 'package com.a\n\nclass Foo\n', 'com/b/Foo.kt': 'package com.b\n\nclass Foo\n',
             'com/c/Use.kt': USE_TEMPLATE.format(imp='org.ext.Foo', name='Foo')}
    rows = kotlin_rows(tmp_path, files)
    assert import_rows(rows, 'IMPORTS_SYMBOL') == [
        (USE, 'IMPORTS_SYMBOL', 'kotlin:com/a/Foo.kt#Foo', 'static_inferred', 'ambiguous', ('kotlin:com/b/Foo.kt#Foo',))]


def test_V6_C12_fqn_zero_matches_and_no_simple_name_gives_no_import_edge(tmp_path):
    files = {'com/c/Use.kt': USE_TEMPLATE.format(imp='org.ext.Foo', name='Foo')}
    rows = kotlin_rows(tmp_path, files)
    assert import_rows(rows, 'IMPORTS_SYMBOL') == [] and import_rows(rows, 'IMPORTS') == []


def test_V6_C12_default_package_symbol_matches_by_qualname(tmp_path):
    files = {'Foo.kt': 'class Foo\n', 'com/b/Foo.kt': 'package com.b\n\nclass Foo\n',
             'com/c/Use.kt': USE_TEMPLATE.format(imp='Foo', name='Foo')}
    rows = kotlin_rows(tmp_path, files)
    assert import_rows(rows, 'IMPORTS_SYMBOL') == [(USE, 'IMPORTS_SYMBOL', 'kotlin:Foo.kt#Foo', 'static_certain', 'exact', ())]
    assert import_rows(rows, 'IMPORTS') == [(USE, 'IMPORTS', 'kotlin:Foo.kt', 'static_certain', 'exact', ())]


def test_V6_C13_nested_class_import_resolves_to_inner_symbol(tmp_path):
    files = {'com/a/Outer.kt': 'package com.a\n\nclass Outer {\n    class Inner\n}\n',
             'com/b/Inner.kt': 'package com.b\n\nclass Inner\n',
             'com/c/Use.kt': USE_TEMPLATE.format(imp='com.a.Outer.Inner', name='Inner')}
    rows = kotlin_rows(tmp_path, files)
    assert import_rows(rows, 'IMPORTS_SYMBOL') == [
        (USE, 'IMPORTS_SYMBOL', 'kotlin:com/a/Outer.kt#Outer.Inner', 'static_certain', 'exact', ())]
    assert import_rows(rows, 'IMPORTS') == [(USE, 'IMPORTS', 'kotlin:com/a/Outer.kt', 'static_certain', 'exact', ())]


# ---------------------------------------------------------------- V7: references and package dependencies (R10, R11)

REFERENCE_RELATIONS = ('INSTANTIATES', 'TYPE_USES', 'CALLS', 'READS')


def test_V7_C11_usage_edges_resolve_to_imported_symbol_exactly(tmp_path):
    rows = kotlin_rows(tmp_path, C11_FILES)
    usage = [r for r in rows if r[0].startswith(USE + '#') and r[1] in REFERENCE_RELATIONS and 'Foo' in r[2]]
    assert usage, 'the usage of Foo must produce reference edges'
    assert {r[1] for r in usage} >= {'INSTANTIATES', 'TYPE_USES'}
    for row in usage:
        assert row[2] == 'kotlin:com/a/Foo.kt#Foo', row
        assert (row[3], row[4], row[5]) == ('static_certain', 'exact', ()), row


def test_V7_C11_instantiation_and_type_edges_come_from_the_expected_symbols(tmp_path):
    rows = kotlin_rows(tmp_path, C11_FILES)
    target = 'kotlin:com/a/Foo.kt#Foo'
    assert (f'{USE}#Use.make', 'TYPE_USES', target, 'static_certain', 'exact', ()) in rows
    assert (f'{USE}#Use.make', 'INSTANTIATES', target, 'static_certain', 'exact', ()) in rows


def test_V7_C11_package_dependency_com_c_to_com_a_certain_and_none_to_com_b(tmp_path):
    write_tree(tmp_path / 'proj', C11_FILES)
    payload, _, _ = run_pipeline(tmp_path / 'proj', tmp_path, 'file', '-l', 'kotlin')
    deps = payload['dependency_network']['package_dependencies']['language']
    triples = {(d['from_id'], d['to_id'], d['tier']) for d in deps}
    assert ('pkg:kotlin:com.c', 'pkg:kotlin:com.a', 'certain') in triples
    assert not [t for t in triples if 'pkg:kotlin:com.b' in t[:2]]


def test_V7_reference_in_file_without_the_import_keeps_simple_name_resolution_characterization(tmp_path):
    """R10 is scoped to the importing file: another file using Foo without importing it stays ambiguous (R12)."""
    files = dict(C11_FILES)
    files['com/d/Other.kt'] = 'package com.d\n\nclass Other {\n    fun make(): Foo = Foo()\n}\n'
    rows = kotlin_rows(tmp_path, files)
    other = [r for r in rows if r[0].startswith('kotlin:com/d/Other.kt#') and r[1] == 'INSTANTIATES']
    assert other and all(r[4] == 'ambiguous' and r[3] == 'static_inferred' for r in other)
    assert {r[2] for r in other} | {c for r in other for c in r[5]} == {'kotlin:com/a/Foo.kt#Foo', 'kotlin:com/b/Foo.kt#Foo'}


def test_V7_member_resolution_without_import_is_unchanged_characterization(tmp_path):
    """The existing enclosing-class member resolution (no import involved) must keep its unique_name result."""
    files = {'com/c/Use.kt': 'package com.c\n\nclass Use {\n    fun go() = 3\n    fun run() = this.go()\n}\n'}
    rows = kotlin_rows(tmp_path, files)
    assert (f'{USE}#Use.run', 'CALLS', f'{USE}#Use.go', 'static_inferred', 'unique_name', ()) in rows


# ---------------------------------------------------------------- V8: unchanged output shape (Q2, R12, C14)

# Recorded from the base commit b590d54 analysis of typescript-nestjs-realworld (spec: field names and types unchanged).
EXPECTED_SHAPE = {
    'file': {
        'schema': 'bottlenecks.v8',
        'top': ['candidates', 'coverage', 'dependency_network', 'edge_weights', 'granularity', 'limitations', 'schema',
                'snapshot', 'versions'],
        'dependency_network': ['ambiguity_policy', 'betweenness_sample_size', 'betweenness_strategy', 'candidate_groups',
                               'edge_count', 'node_count', 'node_metrics', 'package_dependencies', 'package_metrics',
                               'rankings', 'rankings_by_category', 'structure_policy'],
        'edge_weights': ['confidence', 'large_node_line_threshold', 'resolution', 'untested_hub_top_n'],
        'coverage': ['analysis_coverage', 'limitations', 'source_file_count', 'structure'],
        'snapshot': ['file_count', 'ignore_source'],
        'versions': ['analysis'],
    },
    'symbol': {
        'schema': 'bottlenecks.v6',
        'top': ['candidates', 'coverage', 'dependency_network', 'edge_weights', 'limitations', 'schema', 'snapshot',
                'versions'],
        'dependency_network': ['ambiguity_policy', 'betweenness_sample_size', 'betweenness_strategy', 'candidate_groups',
                               'edge_count', 'node_count', 'node_metrics', 'rankings', 'rankings_by_category'],
        'edge_weights': ['confidence', 'large_node_line_threshold', 'resolution'],
        'coverage': ['analysis_coverage', 'limitations', 'source_file_count'],
        'snapshot': ['file_count', 'ignore_source'],
        'versions': ['analysis'],
    },
}


@pytest.mark.parametrize('granularity', ['file', 'symbol'])
def test_V8_Q2_json_key_sets_and_schema_version_are_unchanged(tmp_path_factory, granularity):
    payload, _, _ = run_pipeline(fixture_root('typescript-nestjs-realworld'), tmp_path_factory.mktemp('shape-' + granularity),
                                 granularity, *NESTJS_ARGS)
    expected = EXPECTED_SHAPE[granularity]
    assert payload['schema'] == expected['schema']
    assert sorted(payload) == expected['top']
    for section in ('dependency_network', 'edge_weights', 'coverage', 'snapshot', 'versions'):
        assert sorted(payload[section]) == expected[section], section


@pytest.mark.parametrize('granularity', ['file', 'symbol'])
def test_V8_Q2_candidate_key_sets_per_kind_are_stable(tmp_path_factory, granularity):
    payload, _, _ = run_pipeline(fixture_root('typescript-nestjs-realworld'), tmp_path_factory.mktemp('cand-' + granularity),
                                 granularity, *NESTJS_ARGS)
    base = {'coverage', 'evidence', 'id', 'kind', 'metrics', 'status', 'target'}
    allowed = base | ({'structure'} if granularity == 'file' else set())
    for candidate in payload['candidates']:
        assert base <= set(candidate) <= allowed, candidate['kind']


def test_V8_Q2_synthetic_projects_keep_the_same_top_level_keys(tmp_path):
    write_tree(tmp_path / 'proj', {'a/b.spec.ts': "import { X } from './x.entity';\n", 'a/x.entity.ts': 'export class X {}\n'})
    for granularity in ('file', 'symbol'):
        payload, _, _ = run_pipeline(tmp_path / 'proj', tmp_path, granularity, '-l', 'typescript', name=granularity)
        assert sorted(payload) == EXPECTED_SHAPE[granularity]['top']
        assert payload['schema'] == EXPECTED_SHAPE[granularity]['schema']


def test_V8_C14_synthetic_unrelated_edges_unchanged_characterization(tmp_path):
    """R12: an extensionless, non-dotted specifier and a plain package import resolve as before."""
    files = {'a/b.ts': "import { P } from './p';\nimport { Q } from './dir';\nexport const u = [P, Q];\n",
             'a/p.ts': 'export const P = 1;\n', 'a/dir/index.ts': 'export const Q = 2;\n'}
    root = ts_project(tmp_path, files)
    rows = [r for r in edge_rows(ts_analyze(root)) if r[0] == 'ts:a/b.ts' and r[1] == 'IMPORTS']
    assert sorted((r[2], r[3], r[4]) for r in rows) == [('ts:a/dir/index.ts', 'static_certain', 'exact'),
                                                         ('ts:a/p.ts', 'static_certain', 'exact')]


# ---------------------------------------------------------------- V12: configuration attribution (R13, C15)

CONFIG_CASES = {
    'module-span-equals-single-function-span': ("def consume():\n    return 'KEY'\n", 'py:consumer#consume'),
    'function-strictly-smaller-than-module': ("import os\n\n\ndef consume():\n    return 'KEY'\n", 'py:consumer#consume'),
    'line-covered-by-no-symbol': ("print('KEY')\n\n\ndef other():\n    return 1\n", 'py:consumer'),
}


@pytest.mark.parametrize('label', sorted(CONFIG_CASES))
def test_V12_configures_target_by_smallest_covering_node(tmp_path, label):
    source, expected_target = CONFIG_CASES[label]
    write_tree(tmp_path, {'.env': 'KEY=value\n', 'consumer.py': source})
    rows = edge_rows(python_analyze(tmp_path))
    configures = [r for r in rows if r[1] == 'CONFIGURES']
    assert configures == [('config:.env:KEY', 'CONFIGURES', expected_target, 'static_inferred', 'exact', ())]


# ---------------------------------------------------------------- comparator rule for F7 exact originals (spec v4)

def _exact_split(retained_line=1):
    from tests.test_candidate_policy_transition import transition_edge, transition_node
    nodes = [transition_node('s'), transition_node('a'), transition_node('b'), transition_node('c')]
    original = transition_edge('s', 'a', resolution='exact', weight=2, line=1)
    original['confidence'] = 'static_certain'
    kept = dict(original, weight=1, evidence=dict(original['evidence'], start_line=retained_line, end_line=retained_line))
    other = transition_edge('s', 'a', candidates=['b'], resolution='ambiguous', weight=1, line=2)
    import copy as _copy
    return {'nodes': nodes, 'edges': [original]}, {'nodes': _copy.deepcopy(nodes), 'edges': [kept, other]}, transition_edge, original


def test_VO7_F7_exact_original_split_is_accepted():
    from tests.candidate_policy_transition_support import assert_candidate_policy_transition
    before, after, _, _ = _exact_split()
    assert_candidate_policy_transition(before, after, {})


@pytest.mark.parametrize('label', ['retained-evidence-changed', 'retained-confidence-changed', 'other-static-certain',
                                   'other-exact-resolution', 'weight-mismatch', 'no-other-piece', 'retained-missing'])
def test_VO7_F7_exact_original_split_rejections(label):
    from tests.candidate_policy_transition_support import assert_candidate_policy_transition
    before, after, _, _ = _exact_split()
    kept, other = after['edges']
    if label == 'retained-evidence-changed':
        kept['evidence']['start_line'] = kept['evidence']['end_line'] = 2
    elif label == 'retained-confidence-changed':
        kept['confidence'] = 'static_inferred'
    elif label == 'other-static-certain':
        other['confidence'] = 'static_certain'
    elif label == 'other-exact-resolution':
        other['resolution'] = 'exact'
    elif label == 'weight-mismatch':
        other['weight'] = 2
    elif label == 'no-other-piece':
        kept['weight'] = 2
        after['edges'] = [kept]
        after['edges'][0]['evidence']['start_line'] = after['edges'][0]['evidence']['end_line'] = 2
    elif label == 'retained-missing':
        other['candidates'] = ['b']
        kept['to_id'] = 'a'
        kept['candidates'] = ['c']
        kept['resolution'] = 'ambiguous'
    with pytest.raises(AssertionError):
        assert_candidate_policy_transition(before, after, {})
