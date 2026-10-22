"""Spec 64deae051d59caac v5: documentation code references.

Expected rows are written by hand from the spec rules F1-F13. V8 compares against tests/doc_references_evidence/base_views.json,
produced by running this CLI at base commit 7d16983 in a temporary `git worktree` (PYTHONHASHSEED=0, `--granularity <g> --json
--bottlenecks`, flags from K_CONFIGS in doc_references_support) and storing canonical sha256 hashes of each bottleneck top-level
key, each dependency_network key, each details key and the architecture JSON (worktree removed afterwards)."""
import hashlib
import json
import shutil

import pytest

from tests.doc_references_support import (BASE_COMMIT, COLUMNS, EVIDENCE, FIXTURES, K_CONFIGS, NEW_KIND, analyze, candidate_id, comparable,
                                          details_of, gradle, row, rows_of, run_cli, snap, strip_new, sym)

D = 'docs/a.md'
STATUSES = {'resolved', 'ambiguous', 'dangling', 'site_route'}


def one(text, files=None, doc=D, **kwargs):
    return rows_of({doc: text, **(files or {})}, **kwargs)


def lines_of(rows):
    return [(r[1], r[4]) for r in rows]


# ---- V1 -------------------------------------------------------------------------------------------------------------

LINK = '[x](missing.md)'
V1_FENCE_CASES = {
    'P1-backtick-fence': (f'{LINK}\n```\n{LINK}\n`src/none.ts`\n```\n{LINK}\n', [1, 6]),
    'P2-tilde-fence': (f'{LINK}\n~~~\n{LINK}\n~~~\n{LINK}\n', [1, 5]),
    'P3-four-space-indent-is-not-a-fence': (f'    ```\n{LINK}\n', [2]),
    'P3b-three-space-indent-is-a-fence': (f'   ```\n{LINK}\n   ```\n{LINK}\n', [4]),
    'P4-shorter-closing-fence-does-not-close': (f'{LINK}\n````\n{LINK}\n```\n{LINK}\n', [1]),
    'P4b-other-fence-char-does-not-close': (f'```\n~~~\n{LINK}\n', []),
    'P4c-longer-closing-fence-closes': (f'```\n{LINK}\n`````\n{LINK}\n', [4]),
    'P5-unclosed-fence-runs-to-end': (f'{LINK}\n```\n{LINK}\n{LINK}\n', [1]),
}


@pytest.mark.parametrize('text, expected', V1_FENCE_CASES.values(), ids=V1_FENCE_CASES.keys())
def test_V1_fence_partitions(text, expected):
    assert [r[1] for r in one(text)] == expected


def test_V1_P6_P7_document_extensions():
    files = {name: f'{LINK}\n' for name in ('A.MD', 'b.mdx', 'c.markdown', 'd.txt', 'e.rst', 'f.md.bak')}
    table, _candidates, summary = analyze(files)
    assert [(r[0], r[1], r[4]) for r in table['rows']] == [('A.MD', 1, 'dangling'), ('b.mdx', 1, 'dangling'), ('c.markdown', 1, 'dangling')]
    assert summary['document_count'] == 3


# ---- V2 -------------------------------------------------------------------------------------------------------------

M = {'src/m.py': 'x = 1\n'}
V2_IGNORED = ['[x](https://a)', '[x](mailto:a)', '[x](#anchor)', '[x](?q=1)', '[x]()', '[x](#)', '[x](<>)', '[x](C:/a.md)']


@pytest.mark.parametrize('text', V2_IGNORED)
def test_V2_R1_ignored_targets(text):
    assert one(text + '\n') == []


def test_V2_R2_relative_existing_file_node():
    assert one('[x](../src/m.py)\n', M, file_paths=['src/m.py']) == [
        row(D, 1, 'link', '../src/m.py', 'resolved', 'file:src/m.py', 'file')]


def test_V2_R2_relative_existing_non_file_node_is_path():
    assert one('[x](./guide.md)\n', {'docs/guide.md': '#\n'}) == [row(D, 1, 'link', './guide.md', 'resolved', 'docs/guide.md', 'path')]


def test_V2_R3_relative_absent_is_dangling():
    assert one('[x](missing.md)\n') == [row(D, 1, 'link', 'missing.md', 'dangling')]


def test_V2_R4_absolute_link_existing():
    assert one('[x](/src/m.py)\n', M, file_paths=['src/m.py']) == [row(D, 1, 'link', '/src/m.py', 'resolved', 'file:src/m.py', 'file')]


def test_V2_R5_absolute_link_absent_is_site_route():
    assert one('[x](/reference/api)\n', M) == [row(D, 1, 'link', '/reference/api', 'site_route')]


@pytest.mark.parametrize('target', ['/', '/../x.md', '/a/../../x.md'])
def test_V2_R5_root_and_escaping_absolute_links_are_site_routes(target):
    assert one(f'[x]({target})\n', {'x.md': '#\n'}) == [row(D, 1, 'link', target, 'site_route')]


def test_V2_R6_relative_link_outside_repository_is_dangling_even_if_clamped_target_exists():
    assert one('[x](../../outside.md)\n', {'outside.md': '#\n'}) == [row(D, 1, 'link', '../../outside.md', 'dangling')]


def test_V2_R7_fallback_order_direct_before_md():
    files = {'docs/guide': 'x\n', 'docs/guide.md': '#\n'}
    assert one('[x](guide)\n', files) == [row(D, 1, 'link', 'guide', 'resolved', 'docs/guide', 'path')]


def test_V2_R7_fallback_md():
    assert one('[x](guide)\n', {'docs/guide.md': '#\n'}) == [row(D, 1, 'link', 'guide', 'resolved', 'docs/guide.md', 'path')]


def test_V2_R7_fallback_mdx():
    assert one('[x](guide)\n', {'docs/guide.mdx': '#\n'}) == [row(D, 1, 'link', 'guide', 'resolved', 'docs/guide.mdx', 'path')]


def test_V2_R7_fallback_md_before_mdx():
    files = {'docs/guide.mdx': '#\n', 'docs/guide.md': '#\n'}
    assert one('[x](guide)\n', files) == [row(D, 1, 'link', 'guide', 'resolved', 'docs/guide.md', 'path')]


@pytest.mark.parametrize('name', ['README.md', 'index.md', 'index.mdx'])
def test_V2_R7_V11_G4_directory_takes_precedence_over_index_suffixes(name):
    assert one('[x](guide)\n', {f'docs/guide/{name}': '#\n'}) == [row(D, 1, 'link', 'guide', 'resolved', 'docs/guide', 'directory')]


def test_V2_A3_absolute_link_applies_suffix_fallback():
    assert one('[x](/guide)\n', {'guide.md': '#\n'}) == [row(D, 1, 'link', '/guide', 'resolved', 'guide.md', 'path')]


def test_V2_R8_target_only_in_excluded_files():
    assert rows_of({'README.md': '[x](img/logo.png)\n'}, excluded=['img/logo.png']) == [
        row('README.md', 1, 'link', 'img/logo.png', 'resolved', 'img/logo.png', 'path')]


@pytest.mark.parametrize('target', ['../src/', '/src/', '/src'])
def test_V2_R9_directory_link_resolves(target):
    assert one(f'[x]({target})\n', M) == [row(D, 1, 'link', target, 'resolved', 'src', 'directory')]


def test_V2_R10_reference_definitions():
    text = '[home]: ../src/m.py\n[bad]: missing.md\n[web]: https://a\n  not a definition [id]: missing.md\n'
    assert one(text, M, file_paths=['src/m.py']) == [row(D, 1, 'link', '../src/m.py', 'resolved', 'file:src/m.py', 'file'),
                                                    row(D, 2, 'link', 'missing.md', 'dangling')]


def test_V2_R11_images():
    text = '![a](../src/m.py)\n![b](missing.png)\n'
    assert one(text, M, file_paths=['src/m.py']) == [row(D, 1, 'link', '../src/m.py', 'resolved', 'file:src/m.py', 'file'),
                                                    row(D, 2, 'link', 'missing.png', 'dangling')]


def test_V2_C11_fragment_is_removed_before_resolution():
    assert rows_of({'docs/b.md': '[1](a.md#h)\n', 'docs/a.md': '#\n'})[0] == row('docs/b.md', 1, 'link', 'a.md#h', 'resolved', 'docs/a.md', 'path')
    assert one('[1](q.md#h)\n') == [row(D, 1, 'link', 'q.md#h', 'dangling')]


def test_V2_C11_percent_decoding_and_angle_wrapping():
    files = {'docs/a b.md': '#\n', 'docs/c.md': '#\n'}
    assert rows_of({**files, 'docs/z.md': '[2](a%20b.md)\n[3](<c.md>)\n[4](c.md?x=1)\n'}) == [
        row('docs/z.md', 1, 'link', 'a%20b.md', 'resolved', 'docs/a b.md', 'path'),
        row('docs/z.md', 2, 'link', 'c.md', 'resolved', 'docs/c.md', 'path'),
        row('docs/z.md', 3, 'link', 'c.md?x=1', 'resolved', 'docs/c.md', 'path')]


# ---- V3 -------------------------------------------------------------------------------------------------------------

P = {'src/m.py': 'x = 1\n', 'docs/guide.md': '#\n', 'README.md': '#\n', 'docs/x/y.ts': 'a\n'}


def span(text, files=None, **kwargs):
    return rows_of({**(P if files is None else files), D: f'`{text}`\n'}, **kwargs)


def test_V3_a_exists():
    assert span('src/m.py', file_paths=['src/m.py']) == [row(D, 1, 'code_path', 'src/m.py', 'resolved', 'file:src/m.py', 'file')]


def test_V3_a_absent_with_existing_first_segment_and_no_extension():
    assert span('src/none') == [row(D, 1, 'code_path', 'src/none', 'dangling')]
    assert span('./src/none') == [row(D, 1, 'code_path', './src/none', 'dangling')]


def test_V3_b_extension_absent_is_dangling_and_a_absent_no_extension_is_unrecorded():
    assert span('zzz/none.ts') == [row(D, 1, 'code_path', 'zzz/none.ts', 'dangling')]
    assert span('api/users') == []


@pytest.mark.parametrize('text, recorded', [('zzz/x.abcde', True), ('zzz/x.abcdef', False), ('zzz/x.', False)])
def test_V3_b_extension_length_boundary(text, recorded):
    assert span(text) == ([row(D, 1, 'code_path', text, 'dangling')] if recorded else [])


def test_V3_c_exists_in_document_directory_or_root():
    assert span('guide.md') == [row(D, 1, 'code_path', 'guide.md', 'resolved', 'docs/guide.md', 'path')]
    assert span('README.md') == [row(D, 1, 'code_path', 'README.md', 'resolved', 'README.md', 'path')]


def test_V3_c_absent_is_unrecorded():
    assert span('missing.py') == [] and span('master') == []


def test_V3_c_has_no_suffix_fallback():
    assert span('guide') == []


def test_V3_resolution_order_document_directory_before_root():
    files = {**P, 'docs/src/m.py': 'a\n'}
    assert span('src/m.py', files) == [row(D, 1, 'code_path', 'src/m.py', 'resolved', 'docs/src/m.py', 'path')]


def test_V3_document_directory_only_target_resolves():
    assert span('x/y.ts') == [row(D, 1, 'code_path', 'x/y.ts', 'resolved', 'docs/x/y.ts', 'path')]


def test_V3_slash_prefix_uses_root_only():
    assert span('/src/m.py', file_paths=['src/m.py']) == [row(D, 1, 'code_path', '/src/m.py', 'resolved', 'file:src/m.py', 'file')]
    assert span('/x/y.ts') == [row(D, 1, 'code_path', '/x/y.ts', 'dangling')]


def test_V3_dot_slash_prefix():
    assert span('./src/m.py') == [row(D, 1, 'code_path', './src/m.py', 'resolved', 'src/m.py', 'path')]


@pytest.mark.parametrize('text', ['src/*.py', 'src/<name>.ts', 'src/{a}.ts', 'src/[a].ts', 'a b/c.ts', 'src/$x.ts', 'a|b/c.ts', 'src/?.ts',
                                  'src/a>b.ts'])
def test_V3_forbidden_characters_are_unrecorded(text):
    assert span(text) == []


@pytest.mark.parametrize('text', ['https://example.com/a.ts', 'file:///a/b.ts', 'ftp://h/x.ts'])
def test_V3_scheme_is_unrecorded(text):
    assert span(text) == []


@pytest.mark.parametrize('text', ['src/m.py', 'src/none.ts'])
def test_V3_double_backtick_spans_are_excluded(text):
    assert rows_of({D: f'``{text}``\n', **P}) == []


# ---- V4 -------------------------------------------------------------------------------------------------------------

GRADLE_NODES = [gradle(':app'), gradle(':core:data')]


def test_V4_P1_existing_module():
    assert span(':core:data', {}, nodes=GRADLE_NODES) == [
        row(D, 1, 'gradle_module', ':core:data', 'resolved', 'build-module:gradle::core:data', 'build_module')]


def test_V4_P2_missing_module_in_gradle_repository():
    assert span(':core:missing', {}, nodes=GRADLE_NODES) == [row(D, 1, 'gradle_module', ':core:missing', 'dangling')]


@pytest.mark.parametrize('nodes', [[], [sym('build-module:npm:a', 'module', 'a', None, {'build_system': 'npm', 'module_dir': 'a', 'module_path': ':a'})]])
def test_V4_P3_repository_without_gradle_modules_is_unrecorded(nodes):
    assert span(':core:data', {}, nodes=nodes) == []


def test_V4_P4_gradle_nodes_without_module_dir_only():
    assert span(':ghost', {}, nodes=[gradle(':ghost', module_dir=None)]) == []


def test_V4_P4_node_without_module_dir_does_not_resolve_when_a_real_module_exists():
    assert span(':ghost', {}, nodes=[gradle(':app'), gradle(':ghost', module_dir=None)]) == [
        row(D, 1, 'gradle_module', ':ghost', 'dangling')]


@pytest.mark.parametrize('text', [':a b', 'core:data', ':', ':core:', '::a', ':a/b'])
def test_V4_P5_malformed_module_paths_are_unrecorded(text):
    assert span(text, {}, nodes=GRADLE_NODES) == []


# ---- V5 -------------------------------------------------------------------------------------------------------------

def ident(text, nodes):
    return rows_of({D: f'`{text}`\n'}, nodes=nodes)


def test_V5_P1_single_label_match():
    assert ident('UserService', [sym('py:u', 'class', 'UserService', 'app.UserService')]) == [
        row(D, 1, 'identifier', 'UserService', 'resolved', 'py:u', 'symbol')]


@pytest.mark.parametrize('kind', ['class', 'interface', 'enum', 'type_alias', 'function', 'method'])
def test_V5_matched_kinds(kind):
    assert ident('Thing', [sym('n1', kind, 'Thing')]) == [row(D, 1, 'identifier', 'Thing', 'resolved', 'n1', 'symbol')]


def ids12(count):
    order = [f'm{i:02d}' for i in range(count)]
    return [sym(i, 'method', 'id') for i in reversed(order)], order


def test_V5_P2_many_matches_are_ambiguous_with_sorted_capped_candidates():
    nodes, order = ids12(12)
    assert ident('id', nodes) == [row(D, 1, 'identifier', 'id', 'ambiguous', None, None, order[:10], 12)]


@pytest.mark.parametrize('count, total', [(2, 2), (10, 10), (11, 11)])
def test_V5_B1_B2_candidate_cap_boundary(count, total):
    nodes, order = ids12(count)
    assert ident('id', nodes) == [row(D, 1, 'identifier', 'id', 'ambiguous', None, None, order[:10], total)]


def test_V5_P3_no_match_is_unrecorded():
    assert ident('master', [sym('n', 'class', 'Other')]) == []


def test_V5_P4_dotted_full_symbol_path():
    assert ident('pkg.Foo.bar', [sym('n', 'method', 'bar', 'pkg.Foo.bar')]) == [row(D, 1, 'identifier', 'pkg.Foo.bar', 'resolved', 'n', 'symbol')]


def test_V5_P5_P7_dotted_suffix_with_call_parentheses():
    nodes = [sym('n', 'method', 'bar', 'pkg.Foo.bar')]
    assert ident('Foo.bar()', nodes) == [row(D, 1, 'identifier', 'Foo.bar()', 'resolved', 'n', 'symbol')]
    assert ident('Foo.bar', [sym('n', 'method', 'bar', 'pkgFoo.bar')]) == []


def test_V5_P7_call_parentheses_on_plain_label():
    assert ident('run()', [sym('n', 'function', 'run')]) == [row(D, 1, 'identifier', 'run()', 'resolved', 'n', 'symbol')]


@pytest.mark.parametrize('kind', ['field', 'constant', 'module', 'file'])
def test_V5_P6_non_target_kinds_are_unrecorded(kind):
    assert ident('name', [sym('n', kind, 'name', 'a.name')]) == []


def test_V5_plain_identifier_matches_label_only_and_dotted_matches_symbol_path_only():
    assert ident('UserService', [sym('n', 'class', 'Other', 'a.UserService')]) == []
    assert ident('Foo.bar', [sym('n', 'method', 'Foo.bar', None)]) == []


def test_V5_path_span_is_not_also_an_identifier():
    result = rows_of({D: '`guide.md`\n', 'docs/guide.md': '#\n'}, nodes=[sym('n', 'function', 'x', 'guide.md')])
    assert result == [row(D, 1, 'code_path', 'guide.md', 'resolved', 'docs/guide.md', 'path')]


# ---- V6 -------------------------------------------------------------------------------------------------------------

def test_V6_P1_to_P4_row_format():
    text = '[a](../src/m.py)\n[b](guide.md)\n[c](../src/)\n[d](nope.md)\n[e](/site/route)\n'
    assert one(text, {**M, 'docs/guide.md': '#\n'}, file_paths=['src/m.py']) == [
        [D, 1, 'link', '../src/m.py', 'resolved', 'file:src/m.py', 'file', None, None],
        [D, 2, 'link', 'guide.md', 'resolved', 'docs/guide.md', 'path', None, None],
        [D, 3, 'link', '../src/', 'resolved', 'src', 'directory', None, None],
        [D, 4, 'link', 'nope.md', 'dangling', None, None, None, None],
        [D, 5, 'link', '/site/route', 'site_route', None, None, None, None]]
    table, _c, _s = analyze({D: ''})
    assert table['columns'] == COLUMNS == ['doc', 'line', 'notation', 'text', 'status', 'target', 'target_kind', 'candidates', 'candidate_total']


def test_V6_P5_same_line_order_follows_position():
    assert one('`src/m.py` [x](missing.md)\n[y](missing.md) `src/m.py`\n', M) == [
        row(D, 1, 'code_path', 'src/m.py', 'resolved', 'src/m.py', 'path'), row(D, 1, 'link', 'missing.md', 'dangling'),
        row(D, 2, 'link', 'missing.md', 'dangling'), row(D, 2, 'code_path', 'src/m.py', 'resolved', 'src/m.py', 'path')]


def test_V6_P5_rows_sort_by_line_not_by_notation_and_definitions_interleave():
    text = '`src/none`\n[a](missing.md)\n[r]: other.md\n`src/none`\n'
    assert [(r[1], r[2]) for r in one(text, M)] == [(1, 'code_path'), (2, 'link'), (3, 'link'), (4, 'code_path')]


def test_V6_P5_documents_sorted_by_path():
    files = {'docs/z.md': f'{LINK}\n', 'a/x.md': f'{LINK}\n', 'README.md': f'{LINK}\n', 'Zed.md': f'{LINK}\n'}
    assert [r[0] for r in rows_of(files)] == ['README.md', 'Zed.md', 'a/x.md', 'docs/z.md']


# ---- V7 -------------------------------------------------------------------------------------------------------------

def test_V7_P1_document_without_dangling_has_no_candidate():
    _t, candidates, summary = analyze({D: '[x](../src/m.py)\n[y](/site)\n', **M})
    assert candidates == []
    assert summary == {'document_count': 1, 'reference_count': 2, 'by_status': {'resolved': 1, 'site_route': 1}, 'by_notation': {'link': 2}}


def test_V7_P2_one_dangling_candidate_fields():
    _t, candidates, _s = analyze({'README.md': '[x](missing.md)\n'})
    assert candidates == [{'id': 'b:' + hashlib.sha256(b'README.md|dangling_doc').hexdigest()[:16], 'kind': 'dangling_doc_reference',
                           'target': 'file:README.md', 'metrics': {'dangling_count': 1},
                           'evidence': [{'line': 1, 'notation': 'link', 'text': 'missing.md'}], 'coverage': 'doc_reference',
                           'status': 'static_candidate'}]


def test_V7_P3_several_dangling_rows_and_documents():
    files = {'a.md': '[ok](/site)\n[x](m1.md)\n`src/none`\n`:core:zz`\n[y](m2.md)\n', 'b.md': '[x](m3.md)\n', 'c.md': '[ok](a.md)\n',
             'src/m.py': 'x\n'}
    _t, candidates, summary = analyze(files, nodes=[gradle(':app')])
    by_doc = {c['target']: c for c in candidates}
    assert sorted(by_doc) == ['file:a.md', 'file:b.md']
    assert by_doc['file:a.md']['metrics'] == {'dangling_count': 4} and by_doc['file:a.md']['id'] == candidate_id('a.md')
    assert by_doc['file:a.md']['evidence'] == [{'line': 2, 'notation': 'link', 'text': 'm1.md'}, {'line': 3, 'notation': 'code_path', 'text': 'src/none'},
                                              {'line': 4, 'notation': 'gradle_module', 'text': ':core:zz'}, {'line': 5, 'notation': 'link', 'text': 'm2.md'}]
    assert by_doc['file:b.md']['metrics'] == {'dangling_count': 1} and by_doc['file:b.md']['id'] == candidate_id('b.md')
    assert all(c['kind'] == 'dangling_doc_reference' and c['coverage'] == 'doc_reference' and c['status'] == 'static_candidate' for c in candidates)
    assert summary['by_status'] == {'dangling': 5, 'site_route': 1, 'resolved': 1}


def test_V7_P4_no_documents():
    table, candidates, summary = analyze({'src/m.py': 'x\n', 'notes.txt': LINK})
    assert table == {'columns': COLUMNS, 'rows': []} and candidates == []
    assert summary == {'document_count': 0, 'reference_count': 0, 'by_status': {}, 'by_notation': {}}


def test_V7_P5_summary_counts_sum_to_rows():
    files = {D: '[a](x.md)\n[b](/s)\n`src/m.py`\n`UserService`\n`id`\n', **M}
    nodes = [sym('u', 'class', 'UserService')] + ids12(3)[0]
    table, _c, summary = analyze(files, nodes=nodes)
    assert summary['reference_count'] == len(table['rows']) == 5
    assert summary['by_status'] == {'dangling': 1, 'site_route': 1, 'resolved': 2, 'ambiguous': 1}
    assert summary['by_notation'] == {'link': 2, 'code_path': 1, 'identifier': 2}
    assert sum(summary['by_status'].values()) == sum(summary['by_notation'].values()) == 5


def repo(tmp_path, files):
    from tests.build_modules_support import write_repo
    return write_repo(tmp_path / 'repo', files)


PY = {'pkg/a.py': 'class A:\n    pass\n'}
DOCS = {'README.md': '[ok](pkg/a.py)\n[bad](nope.md)\n[api](/ref/api)\n`pkg/zzz.py`\n', 'docs/guide.md': '[r](../README.md)\n'}


def test_V7_integration_details_coverage_and_candidates(tmp_path):
    bottlenecks, details, _report = run_cli(repo(tmp_path, {**PY, **DOCS}), tmp_path / 'o', ['-l', 'python'], 'file')
    assert details['doc_references']['columns'] == COLUMNS
    assert details['doc_references']['rows'] == [
        ['README.md', 1, 'link', 'pkg/a.py', 'resolved', 'file:pkg/a.py', 'file', None, None],
        ['README.md', 2, 'link', 'nope.md', 'dangling', None, None, None, None],
        ['README.md', 3, 'link', '/ref/api', 'site_route', None, None, None, None],
        ['README.md', 4, 'code_path', 'pkg/zzz.py', 'dangling', None, None, None, None],
        ['docs/guide.md', 1, 'link', '../README.md', 'resolved', 'README.md', 'path', None, None]]
    assert bottlenecks['coverage']['doc_references'] == {'document_count': 2, 'reference_count': 5,
                                                         'by_status': {'resolved': 2, 'dangling': 2, 'site_route': 1},
                                                         'by_notation': {'link': 4, 'code_path': 1}}
    new = [c for c in bottlenecks['candidates'] if c['kind'] == NEW_KIND]
    assert new == [{'id': candidate_id('README.md'), 'kind': NEW_KIND, 'target': 'file:README.md', 'metrics': {'dangling_count': 2},
                    'evidence': [{'line': 2, 'notation': 'link', 'text': 'nope.md'}, {'line': 4, 'notation': 'code_path', 'text': 'pkg/zzz.py'}],
                    'coverage': 'doc_reference', 'status': 'static_candidate'}]
    keys = [(c['kind'], c['id']) for c in bottlenecks['candidates']]
    assert keys == sorted(keys)
    assert bottlenecks['versions']['analysis'] == '7' and bottlenecks['schema'] == 'bottlenecks.v9'


def test_V7_P4_integration_without_documents_still_has_empty_table_and_zero_summary(tmp_path):
    bottlenecks, details, _report = run_cli(repo(tmp_path, PY), tmp_path / 'o', ['-l', 'python'], 'file')
    assert details['doc_references'] == {'columns': COLUMNS, 'rows': []}
    assert bottlenecks['coverage']['doc_references'] == {'document_count': 0, 'reference_count': 0, 'by_status': {}, 'by_notation': {}}
    assert not [c for c in bottlenecks['candidates'] if c['kind'] == NEW_KIND]


# ---- V8 -------------------------------------------------------------------------------------------------------------

def golden():
    data = json.loads((EVIDENCE / 'base_views.json').read_text(encoding='utf-8'))
    assert data['base_commit'] == BASE_COMMIT
    return data['configs']


@pytest.mark.parametrize('key', sorted(K_CONFIGS))
def test_V8_base_choice_cli_output_equals_base_after_removing_new_keys(key, tmp_path):
    fixture, flags, granularity = K_CONFIGS[key]
    if not (FIXTURES / fixture).is_dir():
        pytest.skip(f'fixture {fixture} not acquired')
    expected = golden()[key]
    bottlenecks, details, report = run_cli(FIXTURES / fixture, tmp_path, flags, granularity)
    assert bottlenecks['versions']['analysis'] == '7' and expected['analysis_version'] == '6'
    assert bottlenecks['schema'] == expected['schema']
    if granularity == 'file':
        table = details['doc_references']
        assert table['columns'] == COLUMNS
        assert all(len(r) == 9 and r[4] in STATUSES for r in table['rows'])
        summary = bottlenecks['coverage']['doc_references']
        assert summary['reference_count'] == len(table['rows'])
        assert sum(summary['by_status'].values()) == sum(summary['by_notation'].values()) == len(table['rows'])
        dangling_docs = sorted({r[0] for r in table['rows'] if r[4] == 'dangling'})
        new = [c for c in bottlenecks['candidates'] if c['kind'] == NEW_KIND]
        assert sorted(c['target'] for c in new) == [f'file:{d}' for d in dangling_docs]
        keys = [(c['kind'], c['id']) for c in bottlenecks['candidates']]
        assert keys == sorted(keys)
        stripped, details = strip_new(bottlenecks, details)
    else:
        assert 'doc_references' not in bottlenecks['coverage'] and (details is None or 'doc_references' not in details)
        assert NEW_KIND not in {c['kind'] for c in bottlenecks['candidates']}
        stripped = json.loads(json.dumps(bottlenecks))
        stripped['versions']['analysis'] = '6'
    assert comparable(stripped, details, report) == expected['views']


def test_V11_G8_documents_add_no_graph_nodes_or_edges(tmp_path):
    with_docs = run_cli(repo(tmp_path / 'a', {**PY, **DOCS}), tmp_path / 'oa', ['-l', 'python'], 'file')
    without = run_cli(repo(tmp_path / 'b', PY), tmp_path / 'ob', ['-l', 'python'], 'file')
    (b1, d1, r1), (b2, d2, r2) = with_docs, without
    assert r1['nodes'] == r2['nodes'] and r1['edges'] == r2['edges']
    assert b1['dependency_network']['node_metrics'] == b2['dependency_network']['node_metrics']
    assert b1['dependency_network']['rankings'] == b2['dependency_network']['rankings']
    assert {k: v for k, v in d1.items() if k != 'doc_references'} == {k: v for k, v in d2.items() if k != 'doc_references'}


def test_V8_C18_symbol_granularity_has_no_doc_output(tmp_path):
    bottlenecks, details, _r = run_cli(repo(tmp_path, {**PY, **DOCS}), tmp_path / 'o', ['-l', 'python'], 'symbol')
    assert bottlenecks['versions']['analysis'] == '7' and bottlenecks['schema'] == 'bottlenecks.v6'
    assert 'doc_references' not in bottlenecks['coverage'] and NEW_KIND not in {c['kind'] for c in bottlenecks['candidates']}
    assert details is None or 'doc_references' not in details


# ---- V9 -------------------------------------------------------------------------------------------------------------

def handout(candidates):
    from bottlenecks.handout import render_handout
    from tests.report_size_support import fixture_architecture_dict, fixture_payload
    report, arch = fixture_payload(), fixture_architecture_dict()
    report['candidates'] = candidates
    return render_handout(report, arch)


def dangling(n, count):
    return {'id': f'b:{n:016x}', 'kind': NEW_KIND, 'target': f'file:doc{n}.md', 'metrics': {'dangling_count': count},
            'evidence': [{'line': 1, 'notation': 'link', 'text': f'gone{n}.md'}], 'coverage': 'doc_reference', 'status': 'static_candidate'}


def section(text, title):
    lines, body, inside = text.splitlines(), [], False
    for line in lines:
        if inside and line.startswith('#') and len(line) - len(line.lstrip('#')) <= 3:
            break
        if inside:
            body.append(line)
        if line.rstrip() == title:
            inside = True
    assert inside, f'missing heading {title!r}'
    return '\n'.join(body)


def test_V9_P1_sorted_by_dangling_count_descending_then_id_ascending():
    candidates = [dangling(1, 1), dangling(5, 7), dangling(2, 3), dangling(4, 3), dangling(3, 9)]
    body = section(handout(candidates), f'### {NEW_KIND}')
    order = sorted(range(1, 6), key=lambda n: ({1: 1, 5: 7, 2: 3, 4: 3, 3: 9}[n] * -1, n))
    assert order == [3, 5, 2, 4, 1]
    positions = [body.index(f'b:{n:016x}') for n in order]
    assert positions == sorted(positions)


def test_V9_P2_limit_ten_and_more_line():
    candidates = [dangling(100 - rank, 50 - rank) for rank in range(11)]
    text = handout(candidates)
    body = section(text, f'### {NEW_KIND}')
    shown = [c['id'] for c in candidates[:10]]
    assert all(i in body for i in shown) and candidates[10]['id'] not in text
    assert [body.index(i) for i in shown] == sorted(body.index(i) for i in shown)
    assert f'… 1 more {NEW_KIND} candidates in bottlenecks.json' in body.splitlines()


def test_V9_exactly_ten_has_no_more_line():
    body = section(handout([dangling(i, 20 - i) for i in range(1, 11)]), f'### {NEW_KIND}')
    assert 'more' not in body


# ---- V10 ------------------------------------------------------------------------------------------------------------

def test_V10_G1_unmatched_bracket_and_paren_do_not_hide_later_links():
    assert one('[x(missing.md)\n[y](missing.md\n[z](gone.md)\n')[-1] == row(D, 3, 'link', 'gone.md', 'dangling')


def test_V10_G2_unmatched_backtick_keeps_later_line_numbers():
    result = one('`src/none.ts\n[x](missing.md)\n')
    assert row(D, 2, 'link', 'missing.md', 'dangling') in result


def test_V10_G3_invalid_percent_sequence_is_resolved_raw():
    assert one('[x](a%zz.md)\n[y](b%zz.md)\n', {'docs/a%zz.md': '#\n'}) == [
        row(D, 1, 'link', 'a%zz.md', 'resolved', 'docs/a%zz.md', 'path'), row(D, 2, 'link', 'b%zz.md', 'dangling')]


def test_V10_G4_G5_malformed_nodes_are_skipped_and_good_nodes_still_match():
    nodes = [sym('bad2', 'class', 7, 5, {}), sym('bad3', 'class', None, None), {'id': 'bad4', 'kind': 'class'},
             {'id': 'bad5', 'kind': 'module', 'metadata': None, 'label': 'x'}, sym('bad6', 'module', 'g', None, None),
             sym('bad8', 'class', 'Other', 12), gradle(':app'), sym('good', 'class', 'Foo', 'a.Foo'),
             sym('gbad', 'module', 'g', None, {'build_system': 'gradle', 'module_path': 5, 'module_dir': 'q'})]
    text = '`Foo`\n`a.Foo`\n`Foo.x`\n`:app`\n`:zz`\n'
    got = rows_of({D: text}, nodes=nodes)
    assert got == [row(D, 1, 'identifier', 'Foo', 'resolved', 'good', 'symbol'), row(D, 2, 'identifier', 'a.Foo', 'resolved', 'good', 'symbol'),
                   row(D, 4, 'gradle_module', ':app', 'resolved', 'build-module:gradle::app', 'build_module'),
                   row(D, 5, 'gradle_module', ':zz', 'dangling')]


def test_V10_G4_details_without_nodes_key_or_file_nodes():
    from analysis.doc_references import analyze_doc_references
    table, candidates, _s = analyze_doc_references(snap({D: '`Foo` [x](missing.md)\n'}), {})
    assert [r[4] for r in table['rows']] == ['dangling'] and len(candidates) == 1


@pytest.mark.parametrize('text', ['', '\n', '\r\n', '   '])
def test_V10_G6_empty_documents(text):
    table, candidates, summary = analyze({D: text})
    assert table['rows'] == [] and candidates == [] and summary['reference_count'] == 0 and summary['document_count'] == 1


def test_V10_G7_crlf_line_numbers():
    text = 'a\r\n\r\n[x](missing.md)\r\n```\r\n[y](gone.md)\r\n```\r\n[z](gone.md)\r\n'
    assert lines_of(one(text)) == [(3, 'dangling'), (7, 'dangling')]


def test_V10_G7_lf_and_mixed_line_numbers_agree():
    assert lines_of(one('a\n\n[x](m.md)\r\n`src/none.ts`\n')) == [(3, 'dangling'), (4, 'dangling')]


# ---- B2: field-scoped exclusion of malformed nodes --------------------------------------------------------------------

def raw(ident, kind='class', **fields):
    return {'id': ident, 'kind': kind, **fields}


def test_V10_B2_metadata_none_still_matches_simple_identifier():
    node = raw('n1', label='Foo', symbol_path='a.Foo', metadata=None)
    assert ident('Foo', [node]) == [row(D, 1, 'identifier', 'Foo', 'resolved', 'n1', 'symbol')]


def test_V10_B2_non_string_symbol_path_still_matches_simple_identifier():
    for bad in (5, ['a'], None):
        node = raw('n1', label='Foo', symbol_path=bad, metadata={})
        assert ident('Foo', [node]) == [row(D, 1, 'identifier', 'Foo', 'resolved', 'n1', 'symbol')], bad


def test_V10_B2_non_string_label_still_matches_dotted_identifier():
    for bad in (7, None, ['x']):
        node = raw('n1', label=bad, symbol_path='a.Foo.bar', metadata={})
        assert ident('Foo.bar', [node]) == [row(D, 1, 'identifier', 'Foo.bar', 'resolved', 'n1', 'symbol')], bad


def test_V10_B2_field_needed_by_the_match_excludes_the_node():
    assert ident('Foo', [raw('n1', label=7, symbol_path='a.Foo', metadata={})]) == []
    assert ident('Foo.bar', [raw('n1', label='bar', symbol_path=5, metadata={})]) == []


@pytest.mark.parametrize('bad', ['gradle', ['gradle'], 3, None])
def test_V10_B2_non_dict_metadata_is_excluded_only_from_gradle_matching(bad):
    broken = raw('g1', 'module', label='x', symbol_path=None, metadata=bad)
    assert ident(':app', [broken]) == []
    assert ident(':app', [broken, gradle(':other')]) == [row(D, 1, 'gradle_module', ':app', 'dangling')]
    assert ident(':app', [broken, gradle(':app')]) == [row(D, 1, 'gradle_module', ':app', 'resolved', 'build-module:gradle::app', 'build_module')]
    assert ident('Baz', [raw('c1', label='Baz', symbol_path=None, metadata=bad)]) == [row(D, 1, 'identifier', 'Baz', 'resolved', 'c1', 'symbol')]


# ---- B3: handout format and cap-after-sort ----------------------------------------------------------------------------

def skeleton(line):
    import re
    return re.sub(r'`[^`]*`', '`X`', re.sub(r'(metrics|structure): .*', r'\1: M', line))


def block_of(body, ident_):
    lines = body.splitlines()
    start = next(i for i, line in enumerate(lines) if ident_ in line)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('- ')), len(lines))
    return lines[start:end]


def test_V9_F13_block_has_the_generic_renderer_shape_of_other_kinds():
    from tests.test_report_size_handout import make
    text = handout([dangling(4, 5), make('unresolved_boundary', 2)])
    mine = block_of(section(text, f'### {NEW_KIND}'), 'b:0000000000000004')
    other = block_of(section(text, '### unresolved_boundary'), 'b:0000000000000002')
    assert mine == ['- `b:0000000000000004` target `file:doc4.md`', '  - metrics: dangling_count=5', '  - evidence: 1 items',
                    '    - `{"line":1,"notation":"link","text":"gone4.md"}`']
    assert [skeleton(line) for line in mine[:3]] == [skeleton(line) for line in other[:3]]
    assert other[0].startswith('- `b:') and ' target `file:' in other[0] and other[1].startswith('  - metrics: ')


def test_V9_F13_cap_is_applied_after_sorting():
    first_low = dangling(900, 1)
    middle = [dangling(n, 20 - n) for n in range(1, 10)]
    last_high = dangling(950, 99)
    text = handout([first_low, *middle, last_high])
    body = section(text, f'### {NEW_KIND}')
    assert first_low['id'] not in text
    assert body.index(last_high['id']) < body.index(middle[0]['id'])
    assert [i for i in body.splitlines() if i.startswith('- ')][0].startswith(f"- `{last_high['id']}`")
    assert f'… 1 more {NEW_KIND} candidates in bottlenecks.json' in body.splitlines()


# ---- batch 2 (v5) -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('doc, target', [('README.md', '.'), ('README.md', './'), ('docs/a.md', '..')])
def test_V2_R9_relative_link_to_repository_root_is_resolved_directory(doc, target):
    files = {doc: f'[r]({target})\n', 'src/m.py': 'x\n'}
    assert rows_of(files) == [row(doc, 1, 'link', target, 'resolved', '.', 'directory')]


def test_V2_R9_relative_link_above_root_stays_dangling():
    assert one('[r](../..)\n', M) == [row(D, 1, 'link', '../..', 'dangling')]


@pytest.mark.parametrize('order', [('b', 'a'), ('a', 'b')])
def test_V4_duplicate_module_path_resolves_to_smallest_node_id(order):
    nodes = []
    for key in order:
        node = gradle(':core')
        node['id'] = f'build-module:gradle:{key}'
        nodes.append(node)
    assert span(':core', {}, nodes=nodes) == [row(D, 1, 'gradle_module', ':core', 'resolved', 'build-module:gradle:a', 'build_module')]
