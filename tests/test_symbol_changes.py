import json
import re
from pathlib import Path

import pytest

from fixtures.registry import fixture_root
from tests.delta_support import DELTA_KEYS, SYMBOL_COLUMNS, SYMBOL_SUMMARY, SYMBOL_WARNING, ref_delta, wire
from tests.rename_delta_support import git, make_repo, write_files
from tests.symbol_changes_support import (AMBIGUOUS, FI, SC, SI, UNIQUE, UNRESOLVED, arch, assert_symbol_additions, base_worktree,
                                          baseline_then_edit, by_id, cli_args, delta_lines, delta_run, entry, find,
                                          rel, remove_worktree, run_cli, sym, sym_payload, table_of, analyze)


def delta_api():
    import bottlenecks.delta as module
    return module


def symbols_api():
    import bottlenecks.symbols as module
    return module


def table(nodes, edges=()):
    return symbols_api().symbol_table(arch(nodes, edges))


def applied(*pairs):
    return {'status': 'applied', 'reason': None, 'pairs': [{'from': a, 'to': b, 'similarity': 100} for a, b in pairs]}


def compute(current, baseline, renames=None):
    result = wire(delta_api().compute_delta(current, baseline, renames))
    assert result == wire(ref_delta(current, baseline, renames))
    return result


def full(ident, file, kind, name, signature, visibility, refs=0, uncertain=0):
    return {'id': ident, 'file': file, 'kind': kind, 'name': name, 'signature': signature, 'visibility': visibility,
            'external_refs': refs, 'uncertain_external_refs': uncertain}


def test_V01_EP1_four_kinds_each_give_one_entry_sorted_by_id():
    nodes = [sym('py:a#f', 'a.py', 'function', signature='def f(x)'), sym('py:a#K.m', 'a.py', 'method', signature='def m(self)'),
             sym('py:a#K', 'a.py', 'class', signature='class K'), sym('py:a#C', 'a.py', 'constant')]
    assert table(nodes) == [
        full('py:a#C', 'file:a.py', 'constant', 'C', None, 'public'),
        full('py:a#K', 'file:a.py', 'class', 'K', 'class K', 'public'),
        full('py:a#K.m', 'file:a.py', 'method', 'm', 'def m(self)', 'public'),
        full('py:a#f', 'file:a.py', 'function', 'f', 'def f(x)', 'public')]


def test_V01_EP2_field_and_module_nodes_have_no_entry():
    nodes = [sym('py:a#f', 'a.py'), sym('py:a#K.x', 'a.py', 'field'), sym('py:a', 'a.py', 'module', name='a.py')]
    assert [e['id'] for e in table(nodes)] == ['py:a#f']


def test_V01_EP3_test_file_nodes_have_no_entry():
    nodes = [sym('py:a#f', 'src/a.py'), sym('py:t#test_f', 'tests/test_a.py'), sym('py:t2#helper', 'pkg/test_b.py')]
    assert [e['id'] for e in table(nodes)] == ['py:a#f']


@pytest.mark.parametrize('name, signature, expected', [
    ('_x', 'def _x()', 'private'),
    ('#x', '#x()', 'private'),
    ('h', 'private fun h()', 'private'),
    ('h', 'protected fun h()', 'private'),
    ('h', 'internal fun h()', 'private'),
    ('h', 'override internal fun h()', 'private'),
    ('h', 'fun h(private: Int)', 'public'),
    ('privateKey', 'fun privateKey()', 'public'),
    ('h', 'def h()', 'public'),
    ('h', None, 'public'),
], ids=['underscore', 'hash', 'private-word', 'protected-word', 'internal-word', 'internal-after-override', 'modifier-word-after-name',
        'name-contains-private', 'plain-signature', 'no-signature'])
def test_V01_EP4_visibility(name, signature, expected):
    [row] = table([sym(f'py:a#{name}', 'a.py', 'method', name=name, signature=signature)])
    assert row['visibility'] == expected


def test_V01_EP4_whitespace_runs_in_signature_collapse_and_edges_are_stripped():
    nodes = [sym('py:a#f', 'a.py', signature='  def  f(x,\n        y)\t'), sym('py:a#g', 'a.py', signature=None)]
    assert [e['signature'] for e in table(nodes)] == ['def f(x, y)', None]


def target_with(*sources):
    nodes = [sym('py:a#f', 'a.py'), sym('py:a#other', 'a.py')]
    edges = []
    seen = {n.id for n in nodes}
    for ident, path, edge in sources:
        if ident not in seen:
            nodes.append(sym(ident, path, 'module' if ident.startswith('mod:') else 'function'))
            seen.add(ident)
        if edge is not None:
            edges.append(rel(ident, edge.pop('to', 'py:a#f'), **edge))
    return nodes, edges


REF_CASES = {
    'confirmed-other-file': ([('py:b#g', 'b.py', {})], (1, 0)),
    'inferred-unique-name': ([('py:b#g', 'b.py', {'confidence': SI, 'resolution': UNIQUE})], (1, 0)),
    'same-file': ([('py:a#h', 'a.py', {})], (0, 0)),
    'uncertain-confidence': ([('py:b#g', 'b.py', {'confidence': FI})], (0, 1)),
    'uncertain-ambiguous': ([('py:b#g', 'b.py', {'resolution': AMBIGUOUS})], (0, 1)),
    'uncertain-unresolved': ([('py:b#g', 'b.py', {'resolution': UNRESOLVED})], (0, 1)),
    'ownership-edge': ([('mod:b', 'b.py', {'relation': 'EXPORTS'})], (0, 0)),
    'candidate-target': ([('py:b#g', 'b.py', {'to': 'py:a#other', 'resolution': AMBIGUOUS, 'candidates': ['py:a#f']})], (0, 1)),
    'distinct-source-files-counted-once': ([('py:b#g', 'b.py', {}), ('py:b#g2', 'b.py', {}), ('py:c#g', 'c.py', {})], (2, 0)),
    'file-with-confirmed-and-uncertain-counts-as-confirmed': ([('py:b#g', 'b.py', {}), ('py:b#g2', 'b.py', {'confidence': FI})], (1, 0)),
    'two-uncertain-files': ([('py:b#g', 'b.py', {'confidence': FI}), ('py:c#g', 'c.py', {'resolution': AMBIGUOUS})], (0, 2)),
}


@pytest.mark.parametrize('sources, expected', REF_CASES.values(), ids=REF_CASES.keys())
def test_V01_EP5_external_reference_counts(sources, expected):
    nodes, edges = target_with(*[(i, p, None if e is None else dict(e)) for i, p, e in sources])
    row = by_id(table(nodes, edges))['py:a#f']
    assert (row['external_refs'], row['uncertain_external_refs']) == expected


PY_FILES = {
    'app/__init__.py': '',
    'app/a.py': 'ALLOWED = 1\n\n\ndef f(x, y):\n    return x + y\n\n\ndef _g(x):\n    return x\n\n\nclass K:\n    def m(self):\n        return 1\n',
    'app/b.py': 'from app.a import f\n\n\ndef use():\n    return f(1, 2)\n',
}
TS_FILES = {
    'src/a.ts': 'export function f(x: number, y: number): number { return x + y; }\n'
                'export class Box {\n  _hidden(): number { return 1; }\n  open(): number { return this._hidden(); }\n}\n',
    'src/b.ts': "import { f } from './a';\nexport function use(): number { return f(1, 2); }\n",
}
KT_FILES = {
    'src/main/kotlin/a/A.kt': 'package a\n\nfun pub(x: Int): Int = x + 1\n\nprivate fun hidden(): Int = 2\n\ninternal fun inner(): Int = 3\n',
    'src/main/kotlin/b/B.kt': 'package b\n\nimport a.pub\n\nfun use(): Int = pub(1)\n',
}


def project(tmp_path, files):
    root = tmp_path / 'repo'
    make_repo(root, files)
    return root


def test_V01_python_cli_symbol_table_values(tmp_path):
    data = analyze(project(tmp_path, PY_FILES), tmp_path / 'o', ['-l', 'python'])
    assert_symbol_additions(data)
    rows = table_of(data)
    f = find(rows, 'f', 'file:app/a.py')
    assert f == full('py:app.a#f', 'file:app/a.py', 'function', 'f', 'def f(x, y)', 'public', 1, 0)
    assert find(rows, '_g')['visibility'] == 'private' and find(rows, '_g')['signature'] == 'def _g(x)'
    assert find(rows, 'ALLOWED') == full('py:app.a#ALLOWED', 'file:app/a.py', 'constant', 'ALLOWED', None, 'public')
    assert find(rows, 'K')['kind'] == 'class' and find(rows, 'm')['kind'] == 'method'
    assert find(rows, 'use')['external_refs'] == 0


def test_V01_typescript_cli_symbol_table_values(tmp_path):
    rows = table_of(analyze(project(tmp_path, TS_FILES), tmp_path / 'o', ['-l', 'typescript']))
    f = find(rows, 'f', 'file:src/a.ts')
    assert f['kind'] == 'function' and f['visibility'] == 'public' and f['signature'].startswith('function f(x: number, y: number)')
    assert f['external_refs'] + f['uncertain_external_refs'] == 1
    assert find(rows, '_hidden')['visibility'] == 'private'
    assert find(rows, 'open')['visibility'] == 'public'


def test_V01_kotlin_cli_symbol_table_values(tmp_path):
    rows = table_of(analyze(project(tmp_path, KT_FILES), tmp_path / 'o', ['-l', 'kotlin']))
    pub = find(rows, 'pub')
    assert pub['kind'] == 'function' and pub['visibility'] == 'public' and pub['signature'] == 'fun pub(x: Int): Int'
    assert pub['external_refs'] + pub['uncertain_external_refs'] == 1
    assert find(rows, 'hidden')['visibility'] == 'private' and find(rows, 'inner')['visibility'] == 'private'


def test_V01_EP6_cli_json_serialisation_uses_columns_rows_and_file_id_indexes(tmp_path):
    data = analyze(project(tmp_path, PY_FILES), tmp_path / 'o', ['-l', 'python'])
    network = data['dependency_network']
    assert network['symbol_columns'] == SYMBOL_COLUMNS
    ids = [row[0] for row in network['symbols']]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    for row in network['symbols']:
        assert len(row) == 8 and type(row[1]) is int and 0 <= row[1] < len(network['file_ids'])
        assert network['file_ids'][row[1]].startswith('file:app/')
    f_row = next(row for row in network['symbols'] if row[0] == 'py:app.a#f')
    assert f_row == ['py:app.a#f', network['file_ids'].index('file:app/a.py'), 'function', 'f', 'def f(x, y)', 'public', 1, 0]


@pytest.fixture(scope='module')
def base_tree(tmp_path_factory):
    path = base_worktree(tmp_path_factory.mktemp('base-tree'))
    yield path
    remove_worktree(path)


def symbol_run(root, directory, cwd, lang):
    directory.mkdir(parents=True)
    args = [root, *lang, '--granularity', 'symbol', '--json', '-o', directory / 'r.html', '--bottlenecks', directory / 'b.json']
    done = run_cli(args, cwd=cwd)
    assert done.returncode == 0, done.stderr[-1500:]
    return {name: (directory / name).read_bytes().replace(str(directory).encode(), b'<out>') for name in ('r.json', 'b.json')}


@pytest.mark.parametrize('name, lang', [('futuramaapi', ['-l', 'python']), ('fastapi-realworld', ['-l', 'python']),
                                        ('typescript-nestjs-realworld', ['-l', 'typescript', '-f', 'nestjs'])])
def test_V02_M1_symbol_granularity_output_equals_base_commit(name, lang, base_tree, tmp_path):
    root = fixture_root(name).resolve()
    expected = symbol_run(root, tmp_path / 'base', base_tree, lang)
    actual = symbol_run(root, tmp_path / 'cur', Path(__file__).resolve().parents[1], lang)
    assert actual['b.json'] == expected['b.json']
    assert actual['r.json'] == expected['r.json']
    assert b'symbol_columns' not in actual['b.json']


def generate(source, output):
    import subprocess
    import sys
    return subprocess.run([sys.executable, '-m', 'report.bottlenecks.generate', str(source), '-o', str(output)],
                          cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)


V14_UNREFERENCED = {'app/__init__.py': '', 'app/a.py': 'def lonely():\n    return 1\n'}
V14_PROVIDER = "import { Injectable } from '@nestjs/common';\n@Injectable()\nexport class S {}\n"
V14_FILES = {
    'src/s.service.ts': V14_PROVIDER,
    'src/a.module.ts': "import { Module } from '@nestjs/common';\nimport { S } from './s.service';\n@Module({ providers: [S] })\nexport class AModule {}\n",
    'src/b.controller.ts': "import { Controller } from '@nestjs/common';\nimport { S } from './s.service';\n@Controller('b')\n"
                           "export class BController {\n  constructor(private readonly s: S) {}\n}\n",
    'src/b.module.ts': "import { Module } from '@nestjs/common';\nimport { AModule } from './a.module';\n"
                       "import { BController } from './b.controller';\n@Module({ imports: [AModule], controllers: [BController] })\nexport class BModule {}\n",
}


@pytest.mark.parametrize('files, lang, kind', [
    (V14_UNREFERENCED, ['-l', 'python'], 'unreferenced_symbol'),
    (V14_FILES, ['-f', 'nestjs', '-l', 'typescript'], 'unprovided_injection'),
    ({'app/__init__.py': '', 'app/a.py': 'X = 1\n'}, ['-l', 'python'], None),
], ids=['EP1-unreferenced_symbol', 'EP2-unprovided_injection', 'EP3-neither'])
def test_V14_report_generator_accepts_symbol_tables_and_new_kinds(tmp_path, files, lang, kind):
    root = project(tmp_path, files)
    data = analyze(root, tmp_path / 'o', lang)
    kinds = {c['kind'] for c in data['candidates']}
    assert data['schema'] == 'bottlenecks.v9' and data['dependency_network']['symbols'] is not None
    assert (kind in kinds) if kind else not ({'unreferenced_symbol', 'unprovided_injection'} & kinds)
    done = generate(tmp_path / 'o' / 'b.json', tmp_path / 'report.html')
    assert done.returncode == 0, done.stderr[-1500:]
    html = (tmp_path / 'report.html').read_text(encoding='utf-8')
    assert '<html' in html.lower()


def test_V14_kind_labels_and_descriptions_exist_for_both_new_kinds():
    from report.bottlenecks import generate as module
    assert module.KIND_LABELS['unreferenced_symbol'] == '참조 없는 함수·메서드'
    assert module.KIND_LABELS['unprovided_injection'] == '보이지 않는 주입 provider'
    for kind in ('unreferenced_symbol', 'unprovided_injection'):
        assert isinstance(module.KIND_DESCRIPTIONS[kind], str) and module.KIND_DESCRIPTIONS[kind].strip()


SRC_A = 'file:src/A.kt'
SRC_B = 'file:src/B.kt'


def test_V03_EP1_file_path_ids_are_mapped_before_matching():
    base = sym_payload([entry('kotlin:src/A.kt#foo', SRC_A, name='foo', signature='fun foo()')])
    cur = sym_payload([entry('kotlin:src/B.kt#foo', SRC_B, name='foo', signature='fun foo()')])
    renamed = compute(cur, base, applied(('src/A.kt', 'src/B.kt')))
    assert renamed['symbol_changes'] == {'status': 'applied', 'reason': None}
    assert renamed['changed_signatures'] == [] and renamed['removed_symbols'] == []
    control = compute(cur, base, None)
    assert [r['id'] for r in control['removed_symbols']] == ['kotlin:src/A.kt#foo'] and control['removed_symbols'][0]['file'] == SRC_A


def test_V03_EP1_mapped_symbol_with_new_signature_is_reported_at_the_new_path():
    base = sym_payload([entry('kotlin:src/A.kt#foo', SRC_A, name='foo', signature='fun foo()')])
    cur = sym_payload([entry('kotlin:src/B.kt#foo', SRC_B, name='foo', signature='fun foo(x: Int)')])
    result = compute(cur, base, applied(('src/A.kt', 'src/B.kt')))
    assert result['removed_symbols'] == []
    assert result['changed_signatures'] == [{
        'id': 'kotlin:src/B.kt#foo', 'file': SRC_B, 'kind': 'function', 'name': 'foo', 'baseline_signature': 'fun foo()',
        'current_signature': 'fun foo(x: Int)', 'visibility': 'public', 'external_refs': 0, 'uncertain_external_refs': 0}]


@pytest.mark.parametrize('old, new, module_old, module_new', [
    ('app/a.py', 'app/a_impl.py', 'app.a', 'app.a_impl'),
    ('app/pkg/__init__.py', 'app/pkg2/__init__.py', 'app.pkg', 'app.pkg2'),
], ids=['module-file', 'package-init'])
def test_V03_EP2_python_module_ids_are_mapped_before_matching(old, new, module_old, module_new):
    base = sym_payload([entry(f'py:{module_old}#f', f'file:{old}', signature='def f(x)')])
    cur = sym_payload([entry(f'py:{module_new}#f', f'file:{new}', signature='def f(x)')])
    result = compute(cur, base, applied((old, new)))
    assert result['changed_signatures'] == [] and result['removed_symbols'] == []
    assert len(compute(cur, base, None)['removed_symbols']) == 1


def test_V03_EP2_module_name_that_only_shares_a_prefix_is_not_mapped():
    base = sym_payload([entry('py:app.a_x#f', 'file:app/a_x.py')])
    cur = sym_payload([entry('py:app.a_impl_x#f', 'file:app/a_x.py')])
    result = compute(cur, base, applied(('app/a.py', 'app/a_impl.py')))
    assert [r['id'] for r in result['removed_symbols']] == ['py:app.a_x#f']


STATE_BASE = [entry('py:a#f', 'file:a.py', signature='def f(x)')]
STATE_CUR = [entry('py:a#f', 'file:a.py', signature='def f(x, y)')]


def test_V03_EP3_baseline_without_symbols_is_skipped_with_empty_lists():
    result = compute(sym_payload(STATE_CUR), sym_payload(None))
    assert result['symbol_changes'] == {'status': 'skipped', 'reason': 'baseline_without_symbols'}
    assert result['changed_signatures'] == [] and result['removed_symbols'] == []
    assert result['counts']['changed_signatures'] == 0 and result['counts']['removed_symbols'] == 0


def test_V03_EP4_current_without_symbols_is_skipped_and_the_rest_of_the_delta_is_unchanged():
    cur, base = sym_payload(None), sym_payload(STATE_BASE)
    result = compute(cur, base)
    assert result['symbol_changes'] == {'status': 'skipped', 'reason': 'current_without_symbols'}
    assert result['changed_signatures'] == [] and result['removed_symbols'] == []
    plain = compute(sym_payload(None), sym_payload(None))
    assert {k: v for k, v in result.items() if k != 'symbol_changes'} == {k: v for k, v in plain.items() if k != 'symbol_changes'}


def test_V03_EP3_EP4_both_without_symbols_reports_the_baseline_reason():
    result = compute(sym_payload(None), sym_payload(None))
    assert result['symbol_changes'] == {'status': 'skipped', 'reason': 'baseline_without_symbols'}


def test_V03_EP5_both_with_symbols_is_applied():
    result = compute(sym_payload(STATE_CUR), sym_payload(STATE_BASE))
    assert result['symbol_changes'] == {'status': 'applied', 'reason': None}
    assert [c['id'] for c in result['changed_signatures']] == ['py:a#f']
    assert set(result) == DELTA_KEYS


def test_V03_EP5_empty_symbol_tables_count_as_present():
    assert compute(sym_payload([]), sym_payload([]))['symbol_changes'] == {'status': 'applied', 'reason': None}
    result = compute(sym_payload([]), sym_payload(STATE_BASE))
    assert result['symbol_changes']['status'] == 'applied' and [r['id'] for r in result['removed_symbols']] == ['py:a#f']


def changed(base_entries, cur_entries, renames=None):
    return compute(sym_payload(cur_entries), sym_payload(base_entries), renames)


def f_entry(signature, visibility='public', refs=0, uncertain=0, file='file:a.py'):
    return entry('py:a#f', file, signature=signature, visibility=visibility, refs=refs, uncertain=uncertain)


def test_V04_D1_public_without_references_is_reported_with_current_values_and_baseline_refs():
    result = changed([f_entry('def f(x)')], [f_entry('def f(x, y)')])
    assert result['changed_signatures'] == [{
        'id': 'py:a#f', 'file': 'file:a.py', 'kind': 'function', 'name': 'f', 'baseline_signature': 'def f(x)',
        'current_signature': 'def f(x, y)', 'visibility': 'public', 'external_refs': 0, 'uncertain_external_refs': 0}]
    assert result['counts']['changed_signatures'] == 1 and result['removed_symbols'] == []


def test_V04_D1_reported_fields_come_from_the_current_entry_and_refs_from_the_baseline():
    base = [entry('py:a#f', 'file:a.py', kind='method', name='f', signature='def f(x)', refs=3, uncertain=1)]
    cur = [entry('py:a#f', 'file:b.py', kind='function', name='f', signature='def f(x, y)', refs=9, uncertain=9)]
    [item] = changed(base, cur)['changed_signatures']
    assert (item['file'], item['kind'], item['external_refs'], item['uncertain_external_refs']) == ('file:b.py', 'function', 3, 1)


@pytest.mark.parametrize('current', [f_entry('def f(x, y)', 'private', refs=5, uncertain=5), f_entry('def f(x, y)', 'private')],
                         ids=['private-with-current-refs', 'public-turned-private'])
def test_V04_D2_private_without_baseline_references_is_not_reported(current):
    assert changed([f_entry('def f(x)', 'private')], [current])['changed_signatures'] == []
    assert changed([f_entry('def f(x)')], [current])['changed_signatures'] == []


def test_V04_D3_private_with_confirmed_references_is_reported():
    [item] = changed([f_entry('def f(x)', 'private', refs=2)], [f_entry('def f(x, y)', 'private')])['changed_signatures']
    assert (item['visibility'], item['external_refs'], item['uncertain_external_refs']) == ('private', 2, 0)


def test_V04_D4_private_with_only_uncertain_references_is_reported():
    [item] = changed([f_entry('def f(x)', 'private', uncertain=3)], [f_entry('def f(x, y)', 'private')])['changed_signatures']
    assert (item['external_refs'], item['uncertain_external_refs']) == (0, 3)


def test_V04_D5_signature_that_differs_only_in_whitespace_is_not_reported():
    old = [sym('py:a#f', 'a.py', signature='def f(x,  y)')]
    new = [sym('py:a#f', 'a.py', signature='def f(x,\n      y)  ')]
    base, cur = sym_payload(table(old)), sym_payload(table(new))
    assert compute(cur, base)['changed_signatures'] == []
    really = sym_payload(table([sym('py:a#f', 'a.py', signature='def f(y, x)')]))
    assert len(compute(really, base)['changed_signatures']) == 1


def test_V04_D7_private_turned_public_without_references_is_reported():
    [item] = changed([f_entry('def f(x)', 'private')], [f_entry('def f(x, y)', 'public')])['changed_signatures']
    assert (item['visibility'], item['external_refs'], item['uncertain_external_refs']) == ('public', 0, 0)


@pytest.mark.parametrize('before, now', [(None, 'def f(x)'), ('def f(x)', None), (None, None)], ids=['baseline-null', 'current-null', 'both-null'])
def test_V04_D6_a_null_signature_on_either_side_is_not_reported(before, now):
    assert changed([f_entry(before)], [f_entry(now)])['changed_signatures'] == []


def test_V04_result_is_ordered_by_id_and_unchanged_signatures_are_ignored():
    names = ['py:a#z', 'py:a#B', 'py:a#m', 'py:a#keep']
    base = [entry(i, signature='def x(a)') for i in names]
    cur = [entry(i, signature='def x(a)' if i.endswith('keep') else 'def x(a, b)') for i in reversed(names)]
    assert [c['id'] for c in changed(base, cur)['changed_signatures']] == ['py:a#B', 'py:a#m', 'py:a#z']


def test_V05_D1_removed_public_symbol_is_reported_with_baseline_values():
    base = [entry('py:a#ALLOWED', kind='constant', signature=None, name='ALLOWED'), entry('py:a#keep')]
    cur = [entry('py:a#PERMITTED', kind='constant', signature=None, name='PERMITTED'), entry('py:a#keep')]
    result = changed(base, cur)
    assert result['removed_symbols'] == [{
        'id': 'py:a#ALLOWED', 'file': 'file:a.py', 'kind': 'constant', 'name': 'ALLOWED', 'baseline_signature': None,
        'visibility': 'public', 'external_refs': 0, 'uncertain_external_refs': 0}]
    assert result['counts']['removed_symbols'] == 1 and result['changed_signatures'] == []


def test_V05_D2_removed_private_symbol_without_references_is_not_reported():
    assert changed([entry('py:a#_h', visibility='private')], [])['removed_symbols'] == []


@pytest.mark.parametrize('refs, uncertain', [(1, 0), (0, 2)], ids=['confirmed', 'uncertain'])
def test_V05_D3_removed_private_symbol_with_references_is_reported(refs, uncertain):
    [item] = changed([entry('py:a#_h', visibility='private', refs=refs, uncertain=uncertain)], [])['removed_symbols']
    assert (item['visibility'], item['external_refs'], item['uncertain_external_refs']) == ('private', refs, uncertain)


def test_V05_D4_symbol_whose_id_maps_to_a_current_symbol_is_not_removed():
    base = sym_payload([entry('py:app.a#f', 'file:app/a.py')])
    cur = sym_payload([entry('py:app.a_impl#f', 'file:app/a_impl.py')])
    assert compute(cur, base, applied(('app/a.py', 'app/a_impl.py')))['removed_symbols'] == []


def test_V05_result_is_ordered_by_id():
    base = [entry(i) for i in ('py:a#z', 'py:a#B', 'py:a#m')]
    assert [r['id'] for r in changed(base, [])['removed_symbols']] == ['py:a#B', 'py:a#m', 'py:a#z']


def test_V09_EP1_applied_policy_counts_and_object_shape():
    result = compute(sym_payload(STATE_CUR), sym_payload(STATE_BASE + [entry('py:a#gone')]))
    assert delta_api().DELTA_POLICY == result['policy'] == 'delta.v4'
    assert set(result) == DELTA_KEYS
    assert set(result['counts']) == {'new_cycles', 'grown_cycles', 'new_violations', 'new_package_dependencies', 'instability_changes',
                                     'new_candidates', 'strengthened_candidates', 'changed_signatures', 'removed_symbols'}
    assert result['counts']['changed_signatures'] == 1 and result['counts']['removed_symbols'] == 1
    assert set(result['symbol_changes']) == {'status', 'reason'}


def test_V09_EP2_skipped_policy_and_zero_counts():
    result = compute(sym_payload(None), sym_payload(STATE_BASE))
    assert result['policy'] == 'delta.v4' and result['counts']['changed_signatures'] == result['counts']['removed_symbols'] == 0


def test_V09_EP1_cli_prints_one_symbol_line_on_stdout_and_no_warning(tmp_path):
    root, baseline = baseline_then_edit(tmp_path, PY_FILES, ['-l', 'python'], lambda r: write_files(r, {
        'app/a.py': PY_FILES['app/a.py'].replace('def f(x, y)', 'def f(y, x)').replace('ALLOWED', 'PERMITTED')}))
    done, data = delta_run(root, baseline, tmp_path, ['-l', 'python'])
    out, err = delta_lines(done)
    assert out == [SYMBOL_SUMMARY.format(1, 1)] and err == []
    assert data['delta']['counts']['changed_signatures'] == 1 and data['delta']['counts']['removed_symbols'] == 1


def test_V09_EP2_cli_skipped_prints_one_stderr_warning_and_no_stdout_line(tmp_path):
    root, baseline = baseline_then_edit(tmp_path, PY_FILES, ['-l', 'python'], lambda r: None)
    old = json.loads(baseline.read_text(encoding='utf-8'))
    del old['dependency_network']['symbols'], old['dependency_network']['symbol_columns']
    baseline.write_text(json.dumps(old), encoding='utf-8')
    done, data = delta_run(root, baseline, tmp_path, ['-l', 'python'])
    out, err = delta_lines(done)
    assert out == [] and err == [SYMBOL_WARNING.format('baseline_without_symbols')]
    assert data['delta']['symbol_changes'] == {'status': 'skipped', 'reason': 'baseline_without_symbols'}


def test_V09_EP3_cli_without_baseline_prints_no_symbol_line_and_no_delta(tmp_path):
    root = project(tmp_path, PY_FILES)
    done = run_cli(cli_args(root, tmp_path / 'o', ['-l', 'python']))
    assert done.returncode == 0, done.stderr[-1500:]
    assert delta_lines(done) == ([], [])
    assert 'delta' not in json.loads((tmp_path / 'o' / 'b.json').read_text(encoding='utf-8'))


def edit_a(old, new):
    return lambda root: write_files(root, {'app/a.py': PY_FILES['app/a.py'].replace(old, new)})


def test_C01_changed_parameter_order_is_reported_with_its_caller_count(tmp_path):
    root, baseline = baseline_then_edit(tmp_path, PY_FILES, ['-l', 'python'], edit_a('def f(x, y)', 'def f(y, x)'))
    _, data = delta_run(root, baseline, tmp_path, ['-l', 'python'])
    delta = data['delta']
    assert delta['symbol_changes'] == {'status': 'applied', 'reason': None}
    assert delta['changed_signatures'] == [{
        'id': 'py:app.a#f', 'file': 'file:app/a.py', 'kind': 'function', 'name': 'f', 'baseline_signature': 'def f(x, y)',
        'current_signature': 'def f(y, x)', 'visibility': 'public', 'external_refs': 1, 'uncertain_external_refs': 0}]
    assert delta['removed_symbols'] == []


def test_C02_renamed_public_constant_is_reported_as_removed(tmp_path):
    root, baseline = baseline_then_edit(tmp_path, PY_FILES, ['-l', 'python'], edit_a('ALLOWED', 'PERMITTED'))
    _, data = delta_run(root, baseline, tmp_path, ['-l', 'python'])
    delta = data['delta']
    assert delta['removed_symbols'] == [{
        'id': 'py:app.a#ALLOWED', 'file': 'file:app/a.py', 'kind': 'constant', 'name': 'ALLOWED', 'baseline_signature': None,
        'visibility': 'public', 'external_refs': 0, 'uncertain_external_refs': 0}]
    assert delta['changed_signatures'] == []


PRIVATE_USED = {**PY_FILES, 'app/b.py': 'from app.a import f, _g\n\n\ndef use():\n    return f(1, 2) + _g(3)\n'}


@pytest.mark.parametrize('files, listed', [(PY_FILES, False), (PRIVATE_USED, True)], ids=['no-reference', 'referenced-from-another-file'])
def test_C03_private_function_signature_change_depends_on_outside_references(tmp_path, files, listed):
    root, baseline = baseline_then_edit(tmp_path, files, ['-l', 'python'], lambda r: write_files(
        r, {'app/a.py': files['app/a.py'].replace('def _g(x)', 'def _g(x, z)')}))
    _, data = delta_run(root, baseline, tmp_path, ['-l', 'python'])
    ids = [c['id'] for c in data['delta']['changed_signatures']]
    assert ids == (['py:app.a#_g'] if listed else [])


def test_C04_typescript_signature_that_differs_only_in_whitespace_is_not_reported(tmp_path):
    def edit(root):
        text = TS_FILES['src/a.ts'].replace('function f(x: number, y: number)', 'function f(x: number,\n    y:   number)')
        write_files(root, {'src/a.ts': text})
    root, baseline = baseline_then_edit(tmp_path, TS_FILES, ['-l', 'typescript'], edit)
    _, data = delta_run(root, baseline, tmp_path, ['-l', 'typescript'])
    assert data['delta']['changed_signatures'] == [] and data['delta']['removed_symbols'] == []


def test_C05_file_rename_without_other_change_reports_nothing(tmp_path):
    def edit(root):
        git(root, 'mv', 'app/a.py', 'app/a2.py')
        write_files(root, {'app/b.py': PY_FILES['app/b.py'].replace('app.a import', 'app.a2 import')})
    root, baseline = baseline_then_edit(tmp_path, PY_FILES, ['-l', 'python'], edit)
    done, data = delta_run(root, baseline, tmp_path, ['-l', 'python'])
    delta = data['delta']
    assert delta['renames']['status'] == 'applied' and [p['to'] for p in delta['renames']['pairs']] == ['app/a2.py']
    assert delta['changed_signatures'] == [] and delta['removed_symbols'] == []
    assert delta['counts']['changed_signatures'] == delta['counts']['removed_symbols'] == 0
    assert delta_lines(done)[0] == [SYMBOL_SUMMARY.format(0, 0)]


def test_C12_baseline_without_symbols_skips_only_the_symbol_comparison(tmp_path):
    root, baseline = baseline_then_edit(tmp_path, PY_FILES, ['-l', 'python'], edit_a('def f(x, y)', 'def f(y, x)'))
    full_done, with_symbols = delta_run(root, baseline, tmp_path / 'full', ['-l', 'python'])
    old = json.loads(baseline.read_text(encoding='utf-8'))
    del old['dependency_network']['symbols'], old['dependency_network']['symbol_columns']
    stripped = tmp_path / 'stripped.json'
    stripped.write_text(json.dumps(old), encoding='utf-8')
    done, data = delta_run(root, stripped, tmp_path / 'skip', ['-l', 'python'])
    assert delta_lines(done) == ([], [SYMBOL_WARNING.format('baseline_without_symbols')])
    assert data['delta']['symbol_changes'] == {'status': 'skipped', 'reason': 'baseline_without_symbols'}
    assert data['delta']['changed_signatures'] == [] and data['delta']['removed_symbols'] == []
    same = ('policy', 'baseline', 'rules_changed', 'new_cycles', 'grown_cycles', 'new_violations', 'new_package_dependencies',
            'instability_changes', 'resolved')
    assert {k: data['delta'][k] for k in same} == {k: with_symbols['delta'][k] for k in same}


def test_C13_string_reference_count_in_baseline_is_a_baseline_error_with_the_json_path(tmp_path):
    root, baseline = baseline_then_edit(tmp_path, PY_FILES, ['-l', 'python'], lambda r: None)
    old = json.loads(baseline.read_text(encoding='utf-8'))
    old['dependency_network']['symbols'][0][SYMBOL_COLUMNS.index('external_refs')] = '1'
    baseline.write_text(json.dumps(old), encoding='utf-8')
    done = run_cli(cli_args(root, tmp_path / 'out', ['-l', 'python'], '--baseline', baseline))
    assert done.returncode == 1
    errors = [line for line in done.stderr.splitlines() if line.startswith('[!]')]
    assert len(errors) == 1 and '$.dependency_network.symbols[0].external_refs' in errors[0]
    assert not (tmp_path / 'out' / 'b.json').exists()


def write_baseline(tmp_path, data):
    path = tmp_path / 'baseline.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return path


def good_payload():
    return sym_payload([entry('py:a#f', 'file:a.py'), entry('py:b#g', 'file:b.py')])


def assert_rejected(tmp_path, data, needle, exact=False):
    path = write_baseline(tmp_path, data)
    with pytest.raises(delta_api().BaselineError) as raised:
        delta_api().load_baseline(path)
    message = str(raised.value)
    assert message.startswith(f'baseline {path}: ')
    assert (re.search(re.escape(needle) + r'(?![.\[\w])', message) if exact else needle in message), message


def test_V10_EP1_well_formed_symbol_table_loads_and_compares(tmp_path):
    loaded = delta_api().load_baseline(write_baseline(tmp_path, good_payload()))
    assert loaded['dependency_network']['symbols'] == good_payload()['dependency_network']['symbols']
    assert compute(good_payload(), loaded)['symbol_changes']['status'] == 'applied'


def test_V10_EP1_baseline_without_symbols_still_loads(tmp_path):
    loaded = delta_api().load_baseline(write_baseline(tmp_path, sym_payload(None)))
    assert 'symbols' not in loaded['dependency_network']


@pytest.mark.parametrize('value', [{}, 'rows', 5], ids=['dict', 'string', 'int'])
def test_V10_EP2_symbols_that_is_not_a_list(tmp_path, value):
    data = good_payload()
    data['dependency_network']['symbols'] = value
    assert_rejected(tmp_path, data, '$.dependency_network.symbols')


@pytest.mark.parametrize('column, value', [('id', None), ('id', 3), ('kind', 3), ('name', None)], ids=['id-null', 'id-int', 'kind-int', 'name-null'])
def test_V10_EP3_row_field_that_is_not_a_string(tmp_path, column, value):
    data = good_payload()
    data['dependency_network']['symbols'][0][SYMBOL_COLUMNS.index(column)] = value
    assert_rejected(tmp_path, data, f'$.dependency_network.symbols[0].{column}')


def test_V10_EP3_row_that_is_not_a_list(tmp_path):
    data = good_payload()
    data['dependency_network']['symbols'][1] = {'id': 'x'}
    assert_rejected(tmp_path, data, '$.dependency_network.symbols[1]', exact=True)


@pytest.mark.parametrize('column', ['external_refs', 'uncertain_external_refs'])
def test_V10_EP4_reference_count_that_is_a_string(tmp_path, column):
    data = good_payload()
    data['dependency_network']['symbols'][1][SYMBOL_COLUMNS.index(column)] = '1'
    assert_rejected(tmp_path, data, f'$.dependency_network.symbols[1].{column}')


def test_V10_EP5_signature_that_is_an_integer(tmp_path):
    data = good_payload()
    data['dependency_network']['symbols'][0][SYMBOL_COLUMNS.index('signature')] = 7
    assert_rejected(tmp_path, data, '$.dependency_network.symbols[0].signature')


@pytest.mark.parametrize('mutate', [lambda n: n.pop('symbol_columns'), lambda n: n.__setitem__('symbol_columns', SYMBOL_COLUMNS[:-1]),
                                    lambda n: n.__setitem__('symbol_columns', 'id'), lambda n: n.__setitem__('symbol_columns', [1] * 8)],
                         ids=['missing', 'a-column-short', 'not-a-list', 'not-strings'])
def test_V10_EP6_symbol_columns_missing_or_incomplete(tmp_path, mutate):
    data = good_payload()
    mutate(data['dependency_network'])
    assert_rejected(tmp_path, data, '$.dependency_network.symbol_columns')


@pytest.mark.parametrize('index', [2, 99, -1, 'a'], ids=['equal-to-length', 'far-out', 'negative', 'string'])
def test_V10_EP7_file_index_outside_file_ids(tmp_path, index):
    data = good_payload()
    data['dependency_network']['symbols'][0][SYMBOL_COLUMNS.index('file')] = index
    assert_rejected(tmp_path, data, '$.dependency_network.symbols[0].file')


@pytest.mark.parametrize('change', ['short', 'long'])
def test_V10_EP8_row_length_differs_from_column_count(tmp_path, change):
    data = good_payload()
    row = data['dependency_network']['symbols'][1]
    data['dependency_network']['symbols'][1] = row[:-1] if change == 'short' else row + [0]
    assert_rejected(tmp_path, data, '$.dependency_network.symbols[1]', exact=True)
