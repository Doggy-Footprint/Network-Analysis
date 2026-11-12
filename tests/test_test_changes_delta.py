import json
import pytest

from tests.delta_support import DELTA_KEYS, LEGACY_SYMBOL_COLUMNS, SYMBOL_COLUMNS, TEST_LISTS, TEST_SUMMARY, TEST_WARNING, cycle, payload
from tests.rename_delta_support import git, make_repo, write_files
from tests.symbol_changes_support import baseline_then_edit, cli_args, delta_run, run_cli
from tests.test_signals_support import (applied, base_worktree, case, compute, counts, delta_api, remove_worktree,
                                        run_file_granularity, signal_payload, summary_lines, symbol)

T1 = 'file:tests/a.test.ts'


def cur_base(current_symbols, base_symbols, renames=None):
    return compute(signal_payload(current_symbols, []), signal_payload(base_symbols, []), renames)


def untested_item(ident, base, cur, reach, kind='function', name=None, file='file:a.py'):
    return {'id': ident, 'file': file, 'kind': kind, 'name': name or ident.split('#')[-1].split('.')[-1], 'baseline_branches': base,
            'current_branches': cur, 'test_reach': reach}


# ---------------------------------------------------------------------------------------------------------------------
# V08 untested_changes decision table
# ---------------------------------------------------------------------------------------------------------------------

def test_V08_D1_new_untested_function_is_listed_with_null_baseline_branches():
    result = cur_base([symbol('py:a#f', branches=2, reach='untested')], [])
    assert result['untested_changes'] == [untested_item('py:a#f', None, 2, 'untested')]
    assert result['counts']['untested_changes'] == 1


def test_V08_D1_new_function_with_no_branches_is_listed_and_a_new_method_too():
    result = cur_base([symbol('py:a#g', branches=0, reach='untested'), symbol('py:a#K.m', kind='method', branches=0, reach='untested')], [])
    assert result['untested_changes'] == [untested_item('py:a#K.m', None, 0, 'untested', kind='method', name='m'),
                                          untested_item('py:a#g', None, 0, 'untested')]


def test_V08_D2_new_uncertain_function_is_listed():
    assert cur_base([symbol('py:a#f', branches=1, reach='uncertain')], [])['untested_changes'] == [untested_item('py:a#f', None, 1, 'uncertain')]


def test_V08_D3_new_tested_function_is_not_listed_and_neither_is_a_tested_increase():
    assert cur_base([symbol('py:a#f', branches=5, reach='tested')], [])['untested_changes'] == []
    assert cur_base([symbol('py:a#f', branches=5, reach='tested')], [symbol('py:a#f', branches=1, reach='untested')])['untested_changes'] == []


def test_V08_D4_branch_increase_untested_or_uncertain_is_listed_with_both_counts():
    base = [symbol('py:a#f', branches=1), symbol('py:a#g', branches=0)]
    cur = [symbol('py:a#f', branches=3, reach='untested'), symbol('py:a#g', branches=1, reach='uncertain')]
    assert cur_base(cur, base)['untested_changes'] == [untested_item('py:a#f', 1, 3, 'untested'), untested_item('py:a#g', 0, 1, 'uncertain')]


def test_V08_D4_the_smallest_increase_counts_and_the_file_and_kind_come_from_the_current_side():
    base = [symbol('py:a#f', 'file:a.py', 'method', branches=4)]
    cur = [symbol('py:a#f', 'file:b.py', 'function', branches=5)]
    assert cur_base(cur, base)['untested_changes'] == [untested_item('py:a#f', 4, 5, 'untested', file='file:b.py')]


@pytest.mark.parametrize('before, now', [(2, 2), (0, 0)], ids=['same', 'both-zero'])
def test_V08_D5_equal_branch_count_is_not_listed(before, now):
    assert cur_base([symbol('py:a#f', branches=now)], [symbol('py:a#f', branches=before)])['untested_changes'] == []


@pytest.mark.parametrize('before, now', [(3, 2), (3, 0)], ids=['by-one', 'to-zero'])
def test_V08_D6_branch_decrease_is_not_listed(before, now):
    assert cur_base([symbol('py:a#f', branches=now)], [symbol('py:a#f', branches=before)])['untested_changes'] == []


@pytest.mark.parametrize('before, now', [(None, 3), (3, None), (None, None)], ids=['baseline-null', 'current-null', 'both-null'])
def test_V08_D7_a_null_branch_count_on_either_side_of_an_existing_symbol_is_not_listed(before, now):
    assert cur_base([symbol('py:a#f', branches=now)], [symbol('py:a#f', branches=before)])['untested_changes'] == []


def test_V08_D7_a_new_symbol_with_null_branches_is_still_listed():
    assert cur_base([symbol('py:a#f', branches=None)], [])['untested_changes'] == [untested_item('py:a#f', None, None, 'untested')]


@pytest.mark.parametrize('kind', ['class', 'constant'])
def test_V08_D8_class_and_constant_symbols_are_never_listed(kind):
    new = cur_base([symbol('py:a#X', kind=kind, branches=None)], [])
    grown = cur_base([symbol('py:a#X', kind=kind, branches=4)], [symbol('py:a#X', kind=kind, branches=1)])
    assert new['untested_changes'] == [] and grown['untested_changes'] == []


def test_V08_D9_baseline_ids_are_mapped_through_the_renames_before_matching():
    base = [symbol('kotlin:src/A.kt#foo', 'file:src/A.kt', branches=1), symbol('kotlin:src/A.kt#same', 'file:src/A.kt', branches=2)]
    cur = [symbol('kotlin:src/B.kt#foo', 'file:src/B.kt', branches=3), symbol('kotlin:src/B.kt#same', 'file:src/B.kt', branches=2)]
    mapped = cur_base(cur, base, applied(('src/A.kt', 'src/B.kt')))
    assert mapped['untested_changes'] == [untested_item('kotlin:src/B.kt#foo', 1, 3, 'untested', file='file:src/B.kt')]
    control = cur_base(cur, base, None)
    assert [i['id'] for i in control['untested_changes']] == ['kotlin:src/B.kt#foo', 'kotlin:src/B.kt#same']
    assert [i['baseline_branches'] for i in control['untested_changes']] == [None, None]


def test_V08_items_are_ordered_by_id_and_have_exactly_the_declared_keys():
    cur = [symbol(i, branches=1) for i in ('py:a#z', 'py:a#B', 'py:a#m')]
    items = cur_base(cur, [])['untested_changes']
    assert [i['id'] for i in items] == ['py:a#B', 'py:a#m', 'py:a#z']
    assert all(set(i) == {'id', 'file', 'kind', 'name', 'baseline_branches', 'current_branches', 'test_reach'} for i in items)


# ---------------------------------------------------------------------------------------------------------------------
# V09 weakened_tests decision table
# ---------------------------------------------------------------------------------------------------------------------

def weak(current_cases, base_cases, renames=None):
    return compute(signal_payload([], current_cases), signal_payload([], base_cases), renames)


def item(row_id, reasons, base, cur, file=T1, name=None):
    return {'id': row_id, 'file': file, 'name': name or row_id.split('#', 1)[1], 'reasons': reasons, 'baseline': base, 'current': cur}


def test_V09_D1_fewer_strong_assertions_is_reported_with_both_count_objects():
    base = case(f'{T1}#t', strong=2, weak=0, mocks=1)
    cur = case(f'{T1}#t', strong=1, weak=3, mocks=1)
    result = weak([cur], [base])
    assert result['weakened_tests'] == [item(f'{T1}#t', ['fewer_strong_assertions'], counts(base), counts(cur))]
    assert counts(base) == {'strong_assertions': 2, 'weak_assertions': 0, 'mocks': 1, 'skipped': False}
    assert result['counts']['weakened_tests'] == 1


def test_V09_D1_strong_dropping_to_zero_counts():
    assert [i['reasons'] for i in weak([case(f'{T1}#t', strong=0)], [case(f'{T1}#t', strong=1)])['weakened_tests']] == [['fewer_strong_assertions']]


@pytest.mark.parametrize('before, now', [((2, 0), (2, 3)), ((2, 1), (3, 1)), ((2, 1), (2, 1))], ids=['weak-increase', 'strong-increase', 'unchanged'])
def test_V09_D2_equal_or_higher_strong_count_is_not_reported_whatever_the_weak_count(before, now):
    base = case(f'{T1}#t', strong=before[0], weak=before[1])
    cur = case(f'{T1}#t', strong=now[0], weak=now[1])
    assert weak([cur], [base])['weakened_tests'] == []


def test_V09_D3_newly_skipped_is_reported():
    base, cur = case(f'{T1}#t', skipped=False), case(f'{T1}#t', skipped=True)
    assert weak([cur], [base])['weakened_tests'] == [item(f'{T1}#t', ['newly_skipped'], counts(base), counts(cur))]


@pytest.mark.parametrize('before, now', [(True, False), (True, True), (False, False)], ids=['unskipped', 'still-skipped', 'never-skipped'])
def test_V09_D4_skipped_that_is_not_newly_set_is_not_reported(before, now):
    assert weak([case(f'{T1}#t', skipped=now)], [case(f'{T1}#t', skipped=before)])['weakened_tests'] == []


def test_V09_D5_removed_case_is_reported_with_baseline_counts_and_null_current():
    base = case(f'{T1}#gone', strong=3, weak=1, mocks=2, skipped=True)
    result = weak([case(f'{T1}#kept')], [base, case(f'{T1}#kept')])
    assert result['weakened_tests'] == [item(f'{T1}#gone', ['removed'], counts(base), None)]


def test_V09_D5_a_deleted_file_reports_every_one_of_its_cases():
    other = 'file:tests/b.test.ts'
    base = [case(f'{T1}#a', T1), case(f'{T1}#b', T1), case(f'{other}#c', other)]
    result = weak([case(f'{other}#c', other)], base)
    assert [(i['id'], i['reasons']) for i in result['weakened_tests']] == [(f'{T1}#a', ['removed']), (f'{T1}#b', ['removed'])]


def test_V09_D6_new_case_without_strong_assertion_is_reported_with_null_baseline():
    cur = case(f'{T1}#new', strong=0, weak=2, mocks=0)
    assert weak([cur], [])['weakened_tests'] == [item(f'{T1}#new', ['new_without_strong_assertions'], None, counts(cur))]


def test_V09_D6_new_case_with_no_assertion_at_all_is_reported():
    assert [i['reasons'] for i in weak([case(f'{T1}#new', strong=0, weak=0)], [])['weakened_tests']] == [['new_without_strong_assertions']]


def test_V09_D7_new_case_with_a_strong_assertion_is_not_reported_even_when_skipped():
    assert weak([case(f'{T1}#new', strong=1), case(f'{T1}#other', strong=4, skipped=True)], [])['weakened_tests'] == []


def test_V09_D8_two_reasons_at_once_are_reported_sorted_in_one_item():
    base = case(f'{T1}#t', strong=2, skipped=False)
    cur = case(f'{T1}#t', strong=0, skipped=True)
    result = weak([cur], [base])
    assert result['weakened_tests'] == [item(f'{T1}#t', ['fewer_strong_assertions', 'newly_skipped'], counts(base), counts(cur))]


def test_V09_items_are_ordered_by_id_and_have_exactly_the_declared_keys():
    base = [case(f'{T1}#z'), case(f'{T1}#m')]
    cur = [case(f'{T1}#k', strong=0), case(f'{T1}#b', strong=0)]
    items = weak(cur, base)['weakened_tests']
    assert [i['id'] for i in items] == [f'{T1}#b', f'{T1}#k', f'{T1}#m', f'{T1}#z']
    assert all(set(i) == {'id', 'file', 'name', 'reasons', 'baseline', 'current'} for i in items)
    assert all(set(i['baseline'] or i['current']) == {'strong_assertions', 'weak_assertions', 'mocks', 'skipped'} for i in items)


# ---------------------------------------------------------------------------------------------------------------------
# V10 added_mocks boundaries
# ---------------------------------------------------------------------------------------------------------------------

def mocks_of(current_cases, base_cases, renames=None):
    return compute(signal_payload([], current_cases), signal_payload([], base_cases), renames)['added_mocks']


def mock_item(row_id, base, cur, file=T1):
    return {'id': row_id, 'file': file, 'name': row_id.split('#', 1)[1], 'baseline_mocks': base, 'current_mocks': cur}


@pytest.mark.parametrize('mocks, listed', [(2, False), (3, True)], ids=['new-case-2-mocks', 'new-case-3-mocks'])
def test_V10_new_case_threshold_is_three_mocks(mocks, listed):
    result = mocks_of([case(f'{T1}#new', mocks=mocks)], [])
    assert result == ([mock_item(f'{T1}#new', None, 3)] if listed else [])


@pytest.mark.parametrize('now, listed', [(2, False), (3, True)], ids=['increase-1', 'increase-2'])
def test_V10_existing_case_threshold_is_an_increase_of_two(now, listed):
    result = mocks_of([case(f'{T1}#t', mocks=now)], [case(f'{T1}#t', mocks=1)])
    assert result == ([mock_item(f'{T1}#t', 1, 3)] if listed else [])


def test_V10_existing_case_with_many_mocks_but_no_increase_or_a_decrease_is_not_listed():
    assert mocks_of([case(f'{T1}#t', mocks=9)], [case(f'{T1}#t', mocks=9)]) == []
    assert mocks_of([case(f'{T1}#t', mocks=1)], [case(f'{T1}#t', mocks=9)]) == []


def test_V10_a_four_mock_increase_on_a_file_level_mock_lists_every_case_of_the_file():
    base = [case(f'{T1}#a', mocks=0), case(f'{T1}#b', mocks=1), case(f'{T1}#c', mocks=2)]
    cur = [case(f'{T1}#a', mocks=4), case(f'{T1}#b', mocks=5), case(f'{T1}#c', mocks=6)]
    assert mocks_of(cur, base) == [mock_item(f'{T1}#a', 0, 4), mock_item(f'{T1}#b', 1, 5), mock_item(f'{T1}#c', 2, 6)]


def test_V10_removed_cases_are_not_listed_and_items_are_ordered_by_id():
    base = [case(f'{T1}#gone', mocks=0)]
    cur = [case(f'{T1}#z', mocks=3), case(f'{T1}#b', mocks=7)]
    assert [i['id'] for i in mocks_of(cur, base)] == [f'{T1}#b', f'{T1}#z']
    assert all(set(i) == {'id', 'file', 'name', 'baseline_mocks', 'current_mocks'} for i in mocks_of(cur, base))


def test_V10_a_case_can_be_in_both_the_weakened_and_the_mock_lists():
    result = compute(signal_payload([], [case(f'{T1}#n', strong=0, mocks=3)]), signal_payload([], []))
    assert [i['id'] for i in result['weakened_tests']] == [f'{T1}#n'] and [i['id'] for i in result['added_mocks']] == [f'{T1}#n']


# ---------------------------------------------------------------------------------------------------------------------
# V11 status, mapping and CLI lines
# ---------------------------------------------------------------------------------------------------------------------

def with_data(*cases_):
    return signal_payload([symbol('py:a#f', branches=1)], list(cases_))


def legacy_columns(data):
    network = data['dependency_network']
    network['symbol_columns'] = list(LEGACY_SYMBOL_COLUMNS)
    network['symbols'] = [row[:8] for row in network['symbols']]
    return data


NO_DATA = {
    'no-test-cases': lambda: signal_payload([symbol('py:a#f', branches=1)], None),
    'no-symbol-columns': lambda: signal_payload(None, [case(f'{T1}#t')]),
    'legacy-symbol-columns': lambda: legacy_columns(signal_payload([symbol('py:a#f', branches=1)], [case(f'{T1}#t')])),
    'nothing': lambda: payload(),
}


def assert_skipped(result, reason):
    assert result['test_changes'] == {'status': 'skipped', 'reason': reason}
    assert result['untested_changes'] == [] and result['weakened_tests'] == [] and result['added_mocks'] == []
    assert [result['counts'][name] for name in TEST_LISTS] == [0, 0, 0]


def test_V11_EP1_both_sides_with_data_is_applied_with_the_declared_object_shape():
    result = compute(with_data(case(f'{T1}#t')), with_data(case(f'{T1}#t')))
    assert result['test_changes'] == {'status': 'applied', 'reason': None}
    assert delta_api().DELTA_POLICY == result['policy'] == 'delta.v5'
    assert set(result) == DELTA_KEYS
    assert set(result['counts']) == {'new_cycles', 'grown_cycles', 'new_violations', 'new_package_dependencies', 'instability_changes',
                                     'new_candidates', 'strengthened_candidates', 'changed_signatures', 'removed_symbols',
                                     'untested_changes', 'weakened_tests', 'added_mocks'}


def test_V11_EP1_empty_tables_count_as_data_and_counts_equal_list_lengths():
    assert compute(signal_payload([], []), signal_payload([], []))['test_changes'] == {'status': 'applied', 'reason': None}
    base = signal_payload([], [case(f'{T1}#a'), case(f'{T1}#b', mocks=0)])
    cur = signal_payload([symbol('py:a#f', branches=1)], [case(f'{T1}#b', strong=0, mocks=5), case(f'{T1}#c', strong=0, mocks=3)])
    result = compute(cur, base)
    assert [result['counts'][n] for n in TEST_LISTS] == [len(result[n]) for n in TEST_LISTS] == [1, 3, 2]


@pytest.mark.parametrize('make', NO_DATA.values(), ids=NO_DATA.keys())
def test_V11_EP2_baseline_without_test_data_is_skipped_with_the_baseline_reason(make):
    assert_skipped(compute(with_data(case(f'{T1}#t', strong=0, mocks=9)), make()), 'baseline_without_test_data')


@pytest.mark.parametrize('make', NO_DATA.values(), ids=NO_DATA.keys())
def test_V11_EP3_current_without_test_data_is_skipped_with_the_current_reason(make):
    assert_skipped(compute(make(), with_data(case(f'{T1}#t'))), 'current_without_test_data')


@pytest.mark.parametrize('make', NO_DATA.values(), ids=NO_DATA.keys())
def test_V11_EP4_both_without_test_data_reports_the_baseline_reason(make):
    assert_skipped(compute(make(), make()), 'baseline_without_test_data')


def test_V11_skipping_changes_nothing_else_in_the_delta():
    base_cycles, cur_cycles = [cycle(['file:a.py', 'file:b.py'])], [cycle(['file:a.py', 'file:b.py', 'file:c.py'])]
    full = compute(signal_payload([], [case(f'{T1}#t')], candidates=cur_cycles), signal_payload([], [case(f'{T1}#t')], candidates=base_cycles))
    skipped = compute(signal_payload([], [case(f'{T1}#t')], candidates=cur_cycles), signal_payload([], None, candidates=base_cycles))
    drop = ('test_changes', 'counts', *TEST_LISTS)
    assert {k: v for k, v in skipped.items() if k not in drop} == {k: v for k, v in full.items() if k not in drop}
    assert {k: v for k, v in skipped['counts'].items() if k not in TEST_LISTS} == {k: v for k, v in full['counts'].items() if k not in TEST_LISTS}
    assert full['counts']['grown_cycles'] == 1


def test_V11_EP5_a_renamed_test_file_with_the_same_content_reports_nothing_and_the_control_does():
    old, new = 'file:tests/old.test.ts', 'file:tests/new.test.ts'
    rows = lambda f: [case(f'{f}#D > a', f, strong=2, mocks=4), case(f'{f}#D > b', f, strong=1, weak=1, skipped=True)]
    base, cur = signal_payload([], rows(old)), signal_payload([], rows(new))
    mapped = compute(cur, base, applied(('tests/old.test.ts', 'tests/new.test.ts')))
    assert mapped['untested_changes'] == [] and mapped['weakened_tests'] == [] and mapped['added_mocks'] == []
    assert mapped['test_changes'] == {'status': 'applied', 'reason': None}
    control = compute(cur, base, None)
    assert sorted(i['id'] for i in control['weakened_tests']) == [f'{old}#D > a', f'{old}#D > b']
    assert [i['id'] for i in control['added_mocks']] == [f'{new}#D > a']


def test_V11_EP5_a_case_removed_from_a_renamed_file_is_reported_at_the_new_path_with_the_baseline_counts():
    old, new = 'file:tests/old.test.ts', 'file:tests/new.test.ts'
    base = signal_payload([], [case(f'{old}#a', old), case(f'{old}#b', old, strong=3, weak=1, mocks=1)])
    cur = signal_payload([], [case(f'{new}#a', new)])
    [removed] = compute(cur, base, applied(('tests/old.test.ts', 'tests/new.test.ts')))['weakened_tests']
    assert removed == item(f'{new}#b', ['removed'], {'strong_assertions': 3, 'weak_assertions': 1, 'mocks': 1, 'skipped': False}, None,
                           file=new, name='b')


def test_V11_EP6_a_renamed_production_file_maps_symbol_ids_so_only_real_changes_are_reported():
    base = signal_payload([symbol('py:app.a#f', 'file:app/a.py', branches=1), symbol('py:app.a#g', 'file:app/a.py', branches=2)], [])
    cur = signal_payload([symbol('py:app.a_impl#f', 'file:app/a_impl.py', branches=3), symbol('py:app.a_impl#g', 'file:app/a_impl.py', branches=2)], [])
    mapped = compute(cur, base, applied(('app/a.py', 'app/a_impl.py')))
    assert mapped['untested_changes'] == [untested_item('py:app.a_impl#f', 1, 3, 'untested', file='file:app/a_impl.py')]
    control = compute(cur, base, None)
    assert [i['baseline_branches'] for i in control['untested_changes']] == [None, None]


def test_V11_EP6_skipped_or_empty_renames_do_not_map_anything():
    base = signal_payload([symbol('py:a#f', 'file:a.py', branches=1)], [])
    cur = signal_payload([symbol('py:b#f', 'file:b.py', branches=1)], [])
    skipped = {'status': 'skipped', 'reason': 'git_unavailable', 'pairs': []}
    assert [i['baseline_branches'] for i in compute(cur, base, skipped)['untested_changes']] == [None]
    assert [i['baseline_branches'] for i in compute(cur, base, applied())['untested_changes']] == [None]


# --- CLI ---------------------------------------------------------------------------------------------------------------

PY_FILES = {
    'app/__init__.py': '',
    'app/a.py': 'def f(x):\n    return x\n',
    'tests/test_a.py': 'from app.a import f\n\n\ndef test_f():\n    assert f(1) == 1\n',
}
LANG = ['-l', 'python']
EDITED = {
    'app/a.py': 'def f(x):\n    return x\n\n\ndef g(x):\n    if x:\n        return 1\n    return 0\n',
    'tests/test_a.py': 'from unittest.mock import Mock\n\nfrom app.a import f\n\n\ndef test_f():\n    assert f(1) >= 1\n\n\n'
                       'def test_new():\n    a = Mock()\n    b = Mock()\n    c = Mock()\n',
}


def test_V11_EP1_cli_applied_prints_one_summary_line_on_stdout_and_no_warning(tmp_path):
    root, baseline = baseline_then_edit(tmp_path, PY_FILES, LANG, lambda r: write_files(r, EDITED))
    done, data = delta_run(root, baseline, tmp_path, LANG)
    assert summary_lines(done) == ([TEST_SUMMARY.format(1, 2, 1)], [])
    assert TEST_SUMMARY.format(1, 2, 1) == '[Δ] Test changes: untested changes 1, weakened tests 2, added mocks 1'
    delta = data['delta']
    assert delta['test_changes'] == {'status': 'applied', 'reason': None}
    assert delta['untested_changes'] == [{'id': 'py:app.a#g', 'file': 'file:app/a.py', 'kind': 'function', 'name': 'g',
                                          'baseline_branches': None, 'current_branches': 1, 'test_reach': 'untested'}]
    tid = 'file:tests/test_a.py'
    assert delta['weakened_tests'] == [
        {'id': f'{tid}#test_f', 'file': tid, 'name': 'test_f', 'reasons': ['fewer_strong_assertions'],
         'baseline': {'strong_assertions': 1, 'weak_assertions': 0, 'mocks': 0, 'skipped': False},
         'current': {'strong_assertions': 0, 'weak_assertions': 1, 'mocks': 0, 'skipped': False}},
        {'id': f'{tid}#test_new', 'file': tid, 'name': 'test_new', 'reasons': ['new_without_strong_assertions'], 'baseline': None,
         'current': {'strong_assertions': 0, 'weak_assertions': 0, 'mocks': 3, 'skipped': False}}]
    assert delta['added_mocks'] == [{'id': f'{tid}#test_new', 'file': tid, 'name': 'test_new', 'baseline_mocks': None, 'current_mocks': 3}]
    assert [delta['counts'][n] for n in TEST_LISTS] == [1, 2, 1]


def test_V11_EP1_cli_unchanged_project_prints_the_zero_line(tmp_path):
    root, baseline = baseline_then_edit(tmp_path, PY_FILES, LANG, lambda r: None)
    done, data = delta_run(root, baseline, tmp_path, LANG)
    assert summary_lines(done) == ([TEST_SUMMARY.format(0, 0, 0)], [])
    assert data['delta']['test_changes'] == {'status': 'applied', 'reason': None}


def test_V11_EP5_cli_test_file_rename_with_the_same_content_reports_nothing(tmp_path):
    def edit(root):
        git(root, 'mv', 'tests/test_a.py', 'tests/test_a2.py')
    root, baseline = baseline_then_edit(tmp_path, PY_FILES, LANG, edit)
    done, data = delta_run(root, baseline, tmp_path, LANG)
    delta = data['delta']
    assert delta['renames']['status'] == 'applied' and [p['to'] for p in delta['renames']['pairs']] == ['tests/test_a2.py']
    assert delta['untested_changes'] == [] and delta['weakened_tests'] == [] and delta['added_mocks'] == []
    assert summary_lines(done) == ([TEST_SUMMARY.format(0, 0, 0)], [])


def test_V11_EP7_cli_without_baseline_prints_no_test_line_and_writes_no_delta(tmp_path):
    root = tmp_path / 'repo'
    make_repo(root, PY_FILES)
    done = run_cli(cli_args(root, tmp_path / 'o', LANG))
    assert done.returncode == 0, done.stderr[-1500:]
    assert summary_lines(done) == ([], [])
    assert 'Test changes' not in done.stdout and 'test changes' not in done.stderr
    assert 'delta' not in json.loads((tmp_path / 'o' / 'b.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def base_tree(tmp_path_factory):
    path = base_worktree(tmp_path_factory.mktemp('base-tree'))
    yield path
    remove_worktree(path)


def strip_test_data(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    network = data['dependency_network']
    del network['test_cases'], network['test_case_columns']
    network['symbol_columns'] = network['symbol_columns'][:8]
    network['symbols'] = [row[:8] for row in network['symbols']]
    path.write_text(json.dumps(data), encoding='utf-8')


def test_V11_EP2_cli_baseline_from_the_base_commit_is_skipped_with_one_warning_and_exit_zero(base_tree, tmp_path):
    root = tmp_path / 'repo'
    make_repo(root, PY_FILES)
    run_file_granularity(root, tmp_path / 'base', base_tree, LANG)
    baseline = tmp_path / 'base' / 'b.json'
    old = json.loads(baseline.read_text(encoding='utf-8'))
    assert 'test_cases' not in old['dependency_network']
    write_files(root, EDITED)
    done, data = delta_run(root, baseline, tmp_path, LANG)
    assert done.returncode == 0
    assert summary_lines(done) == ([], [TEST_WARNING.format('baseline_without_test_data')])
    assert [line for line in done.stderr.splitlines() if line.startswith('[!] Warning: test changes')] == [
        '[!] Warning: test changes not compared (baseline_without_test_data)']
    delta = data['delta']
    assert delta['test_changes'] == {'status': 'skipped', 'reason': 'baseline_without_test_data'}
    assert delta['untested_changes'] == [] and delta['weakened_tests'] == [] and delta['added_mocks'] == []
    assert [delta['counts'][n] for n in TEST_LISTS] == [0, 0, 0]
    assert delta['policy'] == 'delta.v5' and delta['symbol_changes']['status'] == 'applied'


def test_V11_EP2_cli_baseline_with_the_test_data_removed_is_skipped_with_one_warning(tmp_path):
    root, baseline = baseline_then_edit(tmp_path, PY_FILES, LANG, lambda r: write_files(r, EDITED))
    strip_test_data(baseline)
    done, data = delta_run(root, baseline, tmp_path, LANG)
    assert summary_lines(done) == ([], [TEST_WARNING.format('baseline_without_test_data')])
    assert data['delta']['test_changes'] == {'status': 'skipped', 'reason': 'baseline_without_test_data'}


# ---------------------------------------------------------------------------------------------------------------------
# V12 load_baseline validation
# ---------------------------------------------------------------------------------------------------------------------

def write_baseline(tmp_path, data):
    path = tmp_path / 'baseline.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return path


def good():
    return signal_payload([symbol('py:a#f', 'file:a.py', branches=1, reach='tested'), symbol('py:b#g', 'file:b.py', branches=None, reach='uncertain')],
                          [case(f'{T1}#a', strong=2, weak=1, mocks=1), case(f'{T1}#b', skipped=True)])


def assert_rejected(tmp_path, data, needle):
    path = write_baseline(tmp_path, data)
    with pytest.raises(delta_api().BaselineError) as raised:
        delta_api().load_baseline(path)
    message = str(raised.value)
    assert message.startswith(f'baseline {path}: ')
    assert needle in message, message


TC = '$.dependency_network.test_cases'
COLUMNS = ['id', 'file', 'name', 'strong_assertions', 'weak_assertions', 'mocks', 'skipped']


def test_V12_EP1_well_formed_data_loads_and_compares(tmp_path):
    loaded = delta_api().load_baseline(write_baseline(tmp_path, good()))
    assert loaded['dependency_network']['test_cases'] == good()['dependency_network']['test_cases']
    assert loaded['dependency_network']['symbols'] == good()['dependency_network']['symbols']
    assert compute(good(), loaded)['test_changes']['status'] == 'applied'


def test_V12_EP1_baseline_without_the_new_data_and_with_legacy_symbol_columns_still_loads(tmp_path):
    for data in (legacy_columns(signal_payload([symbol('py:a#f')], None)), payload()):
        loaded = delta_api().load_baseline(write_baseline(tmp_path, data))
        assert 'test_cases' not in loaded['dependency_network']


@pytest.mark.parametrize('value', [{}, 'rows', 5], ids=['dict', 'string', 'int'])
def test_V12_EP2_test_cases_that_is_not_a_list(tmp_path, value):
    data = good()
    data['dependency_network']['test_cases'] = value
    assert_rejected(tmp_path, data, TC)


@pytest.mark.parametrize('mutate', [lambda n: n.pop('test_case_columns'), lambda n: n.__setitem__('test_case_columns', COLUMNS[:-1]),
                                    lambda n: n.__setitem__('test_case_columns', 'id'), lambda n: n.__setitem__('test_case_columns', [1] * 7)],
                         ids=['missing', 'a-column-short', 'not-a-list', 'not-strings'])
def test_V12_EP3_test_case_columns_missing_or_incomplete(tmp_path, mutate):
    data = good()
    mutate(data['dependency_network'])
    assert_rejected(tmp_path, data, '$.dependency_network.test_case_columns')


@pytest.mark.parametrize('change', ['short', 'long'])
def test_V12_EP4_row_length_differs_from_column_count(tmp_path, change):
    data = good()
    rows = data['dependency_network']['test_cases']
    rows[1] = rows[1][:-1] if change == 'short' else rows[1] + [0]
    assert_rejected(tmp_path, data, f'{TC}[1]')


def test_V12_EP4_row_that_is_not_a_list(tmp_path):
    data = good()
    data['dependency_network']['test_cases'][0] = {'id': 'x'}
    assert_rejected(tmp_path, data, f'{TC}[0]')


@pytest.mark.parametrize('column, value', [('id', None), ('id', 3), ('name', None), ('name', 7)], ids=['id-null', 'id-int', 'name-null', 'name-int'])
def test_V12_EP4_id_and_name_must_be_strings(tmp_path, column, value):
    data = good()
    data['dependency_network']['test_cases'][1][COLUMNS.index(column)] = value
    assert_rejected(tmp_path, data, f'{TC}[1].{column}')


@pytest.mark.parametrize('column', ['strong_assertions', 'weak_assertions', 'mocks'])
@pytest.mark.parametrize('value', ['1', 1.5, None, True], ids=['string', 'float', 'null', 'bool'])
def test_V12_EP5_count_that_is_not_an_integer(tmp_path, column, value):
    data = good()
    data['dependency_network']['test_cases'][0][COLUMNS.index(column)] = value
    assert_rejected(tmp_path, data, f'{TC}[0].{column}')


@pytest.mark.parametrize('value', [0, 1, 'true', None], ids=['zero', 'one', 'string', 'null'])
def test_V12_EP6_skipped_that_is_not_a_boolean(tmp_path, value):
    data = good()
    data['dependency_network']['test_cases'][1][COLUMNS.index('skipped')] = value
    assert_rejected(tmp_path, data, f'{TC}[1].skipped')


@pytest.mark.parametrize('index', [3, 99, -1, 'a', True], ids=['equal-to-length', 'far-out', 'negative', 'string', 'bool'])
def test_V12_EP7_file_index_outside_file_ids(tmp_path, index):
    data = good()
    assert len(data['dependency_network']['file_ids']) == 3
    data['dependency_network']['test_cases'][0][COLUMNS.index('file')] = index
    assert_rejected(tmp_path, data, f'{TC}[0].file')


@pytest.mark.parametrize('column', ['strong_assertions', 'weak_assertions', 'mocks'])
def test_V12_EP8_negative_count(tmp_path, column):
    data = good()
    data['dependency_network']['test_cases'][1][COLUMNS.index(column)] = -1
    assert_rejected(tmp_path, data, f'{TC}[1].{column}')


SYM = '$.dependency_network.symbols'
BRANCHES = SYMBOL_COLUMNS.index('branches')


@pytest.mark.parametrize('value', [-1, -100], ids=['minus-one', 'minus-hundred'])
def test_V12_EP9_negative_branches(tmp_path, value):
    data = good()
    data['dependency_network']['symbols'][1][BRANCHES] = value
    assert_rejected(tmp_path, data, f'{SYM}[1].branches')


@pytest.mark.parametrize('value', ['3', 1.5, [1], True], ids=['string', 'float', 'list', 'bool'])
def test_V12_EP10_branches_that_is_not_an_integer_or_null(tmp_path, value):
    data = good()
    data['dependency_network']['symbols'][0][BRANCHES] = value
    assert_rejected(tmp_path, data, f'{SYM}[0].branches')


@pytest.mark.parametrize('value', ['maybe', '', 'TESTED', None, 3], ids=['maybe', 'empty', 'upper-case', 'null', 'int'])
def test_V12_EP11_test_reach_outside_the_three_values(tmp_path, value):
    data = good()
    data['dependency_network']['symbols'][1][BRANCHES + 1] = value
    assert_rejected(tmp_path, data, f'{SYM}[1].test_reach')


@pytest.mark.parametrize('value', ['tested', 'uncertain', 'untested'])
def test_V12_EP11_each_declared_test_reach_value_and_null_branches_load(tmp_path, value):
    data = good()
    data['dependency_network']['symbols'][1][BRANCHES + 1] = value
    data['dependency_network']['symbols'][1][BRANCHES] = None
    assert delta_api().load_baseline(write_baseline(tmp_path, data))


def test_V12_C12_cli_rejects_a_string_mock_count_with_the_json_path_exit_one_and_no_output(tmp_path):
    root, baseline = baseline_then_edit(tmp_path, PY_FILES, LANG, lambda r: None)
    old = json.loads(baseline.read_text(encoding='utf-8'))
    old['dependency_network']['test_cases'][0][COLUMNS.index('mocks')] = '1'
    baseline.write_text(json.dumps(old), encoding='utf-8')
    done = run_cli(cli_args(root, tmp_path / 'out', LANG, '--baseline', baseline))
    assert done.returncode == 1
    errors = [line for line in done.stderr.splitlines() if line.startswith('[!]')]
    assert len(errors) == 1 and '$.dependency_network.test_cases[0].mocks' in errors[0]
    assert not (tmp_path / 'out' / 'b.json').exists()
