"""Expected values come from the spec's rule tables, hand calculation, and the nested-scan reference in
tests/delta_candidates_support.py; none comes from product output."""
import copy
import json
import random
import time

import pytest

from fixtures.registry import fixture_root
from tests.delta_candidates_support import SEVEN_PAIRS, STRENGTH, boundary_evidence, doc_evidence, gen, ref_general
from tests.delta_support import (DELTA_KEYS, TEST_LISTS, TEST_SUMMARY, SUMMARY, SYMBOL_SUMMARY, append_file, copy_fixture, cycle, internal_violation, payload,
                                 pdep, pmetrics, ref_delta, retrack, run_bottlenecks, wire)

A, B, C = ('file:%s.py' % n for n in 'abc')
NAME = 'fastapi-realworld'


def api():
    import bottlenecks.delta as module
    return module


def run(current, baseline):
    result = wire(api().compute_delta(current, baseline))
    assert result == wire(ref_delta(current, baseline))
    return result


def run_lists(cur, base):
    return run(payload(candidates=cur), payload(candidates=base))


def empty_general(result):
    return result['new_candidates'] == [] and result['strengthened_candidates'] == []


def new_item(item):
    return {'candidate_id': item['id'], 'kind': item['kind'], 'target': item['target'], 'metrics': item['metrics']}


def strengthened_item(cur, base, increased, added=()):
    return {'candidate_id': cur['id'], 'baseline_candidate_id': base['id'], 'kind': cur['kind'], 'target': cur['target'],
            'increased': increased, 'added_evidence': list(added)}


# ---------------------------------------------------------------- V01 decision table

# kind, target, baseline metrics, increased metrics, decreased metrics, metrics differing only in non-strength fields,
# the {metric: {baseline, current}} that the increase must report
KINDS_WITH_STRENGTH = {
    'large_node': ('file:big.py', {'line_count': 2100, 'token_count': 9000, 'pagerank': 0.1},
                   {'line_count': 2300, 'token_count': 9000, 'pagerank': 0.1},
                   {'line_count': 2000, 'token_count': 9000, 'pagerank': 0.1},
                   {'line_count': 2100, 'token_count': 9000, 'pagerank': 0.5},
                   {'line_count': {'baseline': 2100, 'current': 2300}}),
    'unresolved_boundary': ('file:ub.py', {'unresolved_count': 5, 'pagerank': 0.1},
                            {'unresolved_count': 9, 'pagerank': 0.1},
                            {'unresolved_count': 2, 'pagerank': 0.1},
                            {'unresolved_count': 5, 'pagerank': 0.9},
                            {'unresolved_count': {'baseline': 5, 'current': 9}}),
    'evidence_spread': ('file:es.py', {'file_count': 4, 'directory_count': 2, 'line_span': 50},
                        {'file_count': 7, 'directory_count': 2, 'line_span': 50},
                        {'file_count': 3, 'directory_count': 2, 'line_span': 50},
                        {'file_count': 4, 'directory_count': 2, 'line_span': 90},
                        {'file_count': {'baseline': 4, 'current': 7}}),
    'dangling_doc_reference': ('file:dd.md', {'dangling_count': 3, 'pagerank_rank': 1},
                               {'dangling_count': 6, 'pagerank_rank': 1},
                               {'dangling_count': 1, 'pagerank_rank': 1},
                               {'dangling_count': 3, 'pagerank_rank': 4},
                               {'dangling_count': {'baseline': 3, 'current': 6}}),
    'unstable_dependency': ('pkg:p->pkg:q', {'file_pair_count': 6, 'instability_to': 0.5},
                            {'file_pair_count': 8, 'instability_to': 0.5},
                            {'file_pair_count': 4, 'instability_to': 0.5},
                            {'file_pair_count': 6, 'instability_to': 0.9},
                            {'file_pair_count': {'baseline': 6, 'current': 8}}),
}
RULES = ['R1', 'R2', 'R3', 'R4', 'R5', 'R8']
STRENGTH_CELLS = [(kind, rule) for kind in KINDS_WITH_STRENGTH for rule in RULES]


@pytest.mark.parametrize('kind, rule', STRENGTH_CELLS, ids=[f'{k}-{r}' for k, r in STRENGTH_CELLS])
def test_V01_strength_kind_cell(kind, rule):
    target, base_m, up_m, down_m, f07_m, increase = KINDS_WITH_STRENGTH[kind]
    base = gen(kind, target, 'b1', base_m)
    if rule == 'R1':
        cur = gen(kind, target, 'c1', base_m)
        result = run_lists([cur], [])
        assert result['new_candidates'] == [new_item(cur)] and result['strengthened_candidates'] == []
        assert result['resolved']['candidates'] == 0
        return
    if rule == 'R2':
        result = run_lists([], [base])
        assert empty_general(result) and result['resolved']['candidates'] == 1
        return
    cur = gen(kind, target, 'c1', {'R3': up_m, 'R4': base_m, 'R5': down_m, 'R8': f07_m}[rule])
    result = run_lists([cur], [base])
    assert result['new_candidates'] == [] and result['resolved']['candidates'] == 0
    if rule == 'R3':
        assert result['strengthened_candidates'] == [strengthened_item(cur, base, increase)]
    else:
        assert result['strengthened_candidates'] == []
    assert result['counts']['new_candidates'] == 0
    assert result['counts']['strengthened_candidates'] == (1 if rule == 'R3' else 0)


def test_V01_signature_kind_R6_unresolved_boundary_added_reference():
    base = gen('unresolved_boundary', A, 'b1', {'unresolved_count': 2}, evidence=boundary_evidence(A, ['foo']))
    cur = gen('unresolved_boundary', A, 'c1', {'unresolved_count': 2}, evidence=boundary_evidence(A, ['bar']))
    result = run_lists([cur], [base])
    assert result['strengthened_candidates'] == [strengthened_item(cur, base, {}, [['reference', A, 'bar']])]
    assert result['new_candidates'] == [] and result['resolved']['candidates'] == 0


def test_V01_signature_kind_R6_dangling_doc_added_text():
    base = gen('dangling_doc_reference', 'file:d.md', 'b1', {'dangling_count': 1}, evidence=doc_evidence(('path', 'a.md')))
    cur = gen('dangling_doc_reference', 'file:d.md', 'c1', {'dangling_count': 1},
              evidence=doc_evidence(('path', 'a.md'), ('path', 'b.md')))
    result = run_lists([cur], [base])
    assert result['strengthened_candidates'] == [strengthened_item(cur, base, {}, [['doc', 'path', 'b.md']])]


def test_V01_signature_kind_R7_unresolved_boundary_removed_reference():
    base = gen('unresolved_boundary', A, 'b1', {'unresolved_count': 2}, evidence=boundary_evidence(A, ['foo', 'bar']))
    cur = gen('unresolved_boundary', A, 'c1', {'unresolved_count': 2}, evidence=boundary_evidence(A, ['foo']))
    result = run_lists([cur], [base])
    assert empty_general(result) and result['resolved']['candidates'] == 0


def test_V01_signature_kind_R7_dangling_doc_removed_text():
    base = gen('dangling_doc_reference', 'file:d.md', 'b1', {'dangling_count': 2},
               evidence=doc_evidence(('path', 'a.md'), ('path', 'b.md')))
    cur = gen('dangling_doc_reference', 'file:d.md', 'c1', {'dangling_count': 2}, evidence=doc_evidence(('path', 'a.md')))
    result = run_lists([cur], [base])
    assert empty_general(result) and result['resolved']['candidates'] == 0


@pytest.mark.parametrize('kind', ['untested_hub', 'isolated_node'])
@pytest.mark.parametrize('rule', ['R1', 'R2', 'R3'])
def test_V01_no_strength_kind_cell(kind, rule):
    base = gen(kind, B, 'b1', {'pagerank': 0.2, 'degree': 1})
    cur = gen(kind, B, 'c1', {'pagerank': 0.9, 'degree': 7})
    result = run_lists([cur] if rule != 'R2' else [], [base] if rule != 'R1' else [])
    if rule == 'R1':
        assert result['new_candidates'] == [new_item(cur)] and result['strengthened_candidates'] == []
        assert result['resolved']['candidates'] == 0
    elif rule == 'R2':
        assert empty_general(result) and result['resolved']['candidates'] == 1
    else:
        assert empty_general(result) and result['resolved']['candidates'] == 0


def test_V01_unstable_dependency_R9_tier_only_change():
    base = gen('unstable_dependency', 'pkg:p->pkg:q', 'b1', {'file_pair_count': 3}, structure={'scheme': 'language', 'tier': 'certain'})
    cur = gen('unstable_dependency', 'pkg:p->pkg:q', 'c1', {'file_pair_count': 3}, structure={'scheme': 'language', 'tier': 'all'})
    result = run_lists([cur], [base])
    assert empty_general(result) and result['resolved']['candidates'] == 0


def test_V01_unknown_kind_R1_new():
    cur = gen('duplicate_code', A, 'c1', {'copies': 3, 'line_count': 40})
    result = run_lists([cur], [])
    assert result['new_candidates'] == [new_item(cur)] and result['resolved']['candidates'] == 0
    assert result['counts']['new_candidates'] == 1


def test_V01_unknown_kind_R10_metric_increase_is_not_reported():
    base = gen('duplicate_code', A, 'b1', {'copies': 3, 'line_count': 40})
    cur = gen('duplicate_code', A, 'c1', {'copies': 9, 'line_count': 400})
    result = run_lists([cur], [base])
    assert empty_general(result) and result['resolved']['candidates'] == 0


def test_V01_unknown_kind_R11_duplicate_key_pairs_by_id():
    base = [gen('duplicate_code', A, 'x1', {'copies': 1}), gen('duplicate_code', A, 'x2', {'copies': 1})]
    swapped = [gen('duplicate_code', A, 'x2', {'copies': 1}), gen('duplicate_code', A, 'x1', {'copies': 1})]
    result = run_lists(swapped, base)
    assert empty_general(result) and result['resolved']['candidates'] == 0
    third = [gen('duplicate_code', A, 'x1', {'copies': 1}), gen('duplicate_code', A, 'x3', {'copies': 2})]
    result = run_lists(third, base)
    assert result['new_candidates'] == [new_item(third[1])] and result['strengthened_candidates'] == []
    assert result['resolved']['candidates'] == 1


def test_V01_unknown_kind_R11_single_baseline_against_duplicated_current_pairs_nothing():
    base = [gen('duplicate_code', A, 'x1', {'copies': 1})]
    cur = [gen('duplicate_code', A, 'x1', {'copies': 1}), gen('duplicate_code', A, 'x2', {'copies': 1})]
    result = run_lists(cur, base)
    assert [i['candidate_id'] for i in result['new_candidates']] == ['x1', 'x2']
    assert result['resolved']['candidates'] == 1


# ---------------------------------------------------------------- V02 boundaries

BOUNDARY_CASES = [(kind, metric, step) for kind, metric in SEVEN_PAIRS for step in (0, 1)]


@pytest.mark.parametrize('kind, metric, step', BOUNDARY_CASES, ids=[f'{k}-{m}-{"equal" if s == 0 else "plus-one"}' for k, m, s in BOUNDARY_CASES])
def test_V02_strength_metric_boundary(kind, metric, step):
    target = KINDS_WITH_STRENGTH[kind][0]
    metrics = {name: 10 for name in STRENGTH[kind]}
    base = gen(kind, target, 'b1', metrics)
    cur = gen(kind, target, 'c1', {**metrics, metric: 10 + step})
    result = run_lists([cur], [base])
    assert result['new_candidates'] == []
    if step == 0:
        assert result['strengthened_candidates'] == []
    else:
        assert result['strengthened_candidates'] == [strengthened_item(cur, base, {metric: {'baseline': 10, 'current': 11}})]


# ---------------------------------------------------------------- V03 F11 syntax

def write(tmp_path, data, name='baseline.json'):
    target = tmp_path / name
    target.write_text(json.dumps(data), encoding='utf-8')
    return target


def assert_rejected(tmp_path, bad, location):
    data = payload(candidates=[cycle([A, B]), bad])
    path = write(tmp_path, data)
    with pytest.raises(api().BaselineError) as raised:
        api().load_baseline(path)
    message = str(raised.value)
    assert message.startswith(f'baseline {path}: {location} must be ')


def test_V03_target_not_string(tmp_path):
    assert_rejected(tmp_path, gen('large_node', 5, 'b1', {'line_count': 1}), '$.candidates[1].target')


def test_V03_metrics_not_object(tmp_path):
    bad = gen('large_node', A, 'b1')
    bad['metrics'] = [1, 2]
    assert_rejected(tmp_path, bad, '$.candidates[1].metrics')


@pytest.mark.parametrize('kind, metric', [('large_node', 'line_count'), ('unresolved_boundary', 'unresolved_count'),
                                          ('unstable_dependency', 'file_pair_count')])
@pytest.mark.parametrize('value', ['2100', True, None], ids=['string', 'bool', 'null'])
def test_V03_strength_metric_not_number(tmp_path, kind, metric, value):
    assert_rejected(tmp_path, gen(kind, A, 'b1', {metric: value}), f'$.candidates[1].metrics.{metric}')


@pytest.mark.parametrize('kind', ['unresolved_boundary', 'dangling_doc_reference'])
def test_V03_evidence_not_list(tmp_path, kind):
    assert_rejected(tmp_path, gen(kind, A, 'b1', {}, evidence={'a': 1}), '$.candidates[1].evidence')


@pytest.mark.parametrize('kind', ['unresolved_boundary', 'dangling_doc_reference'])
def test_V03_evidence_element_not_object(tmp_path, kind):
    assert_rejected(tmp_path, gen(kind, A, 'b1', {}, evidence=[{}, 'text']), '$.candidates[1].evidence[1]')


def test_V03_unknown_kind_target_not_string(tmp_path):
    assert_rejected(tmp_path, gen('duplicate_code', 5, 'b1', {}), '$.candidates[1].target')


def test_V03_unknown_kind_metrics_not_object(tmp_path):
    bad = gen('duplicate_code', A, 'b1')
    bad['metrics'] = 'text'
    assert_rejected(tmp_path, bad, '$.candidates[1].metrics')


def test_V03_cycle_candidate_with_odd_target_and_metrics_loads(tmp_path):
    odd = cycle([A, B])
    odd['target'] = 5
    odd['metrics'] = 'text'
    loaded = api().load_baseline(write(tmp_path, payload(candidates=[odd])))
    assert loaded['candidates'][0]['kind'] == 'dependency_cycle'


def test_V03_violation_candidate_with_odd_target_and_metrics_loads(tmp_path):
    odd = internal_violation('b:v1', A, B)
    odd['target'] = 5
    odd['metrics'] = 'text'
    loaded = api().load_baseline(write(tmp_path, payload(candidates=[odd])))
    assert loaded['candidates'][0]['kind'] == 'rule_violation'


def test_V03_unknown_kind_is_not_subject_to_strength_metric_and_evidence_checks(tmp_path):
    unknown = gen('duplicate_code', A, 'b1', {'line_count': '2100', 'unresolved_count': None}, evidence={'a': 1})
    loaded = api().load_baseline(write(tmp_path, payload(candidates=[unknown])))
    assert loaded['candidates'][0]['kind'] == 'duplicate_code'


# ---------------------------------------------------------------- V04 equivalence classes

def mixed_pair():
    base = payload(
        candidates=[cycle([A, B]), internal_violation('b:v1', A, B),
                    gen('large_node', 'file:big.py', 'b1', {'line_count': 10, 'token_count': 5}),
                    gen('isolated_node', 'file:old.py', 'b2', {})],
        package_dependencies={'language': [pdep('p', 'q')]}, package_metrics={'language': pmetrics({'pkg:x': 0.1})})
    cur = payload(
        candidates=[cycle([A, B, C]), internal_violation('b:v2', A, C),
                    gen('large_node', 'file:big.py', 'c1', {'line_count': 20, 'token_count': 5}),
                    gen('isolated_node', 'file:new.py', 'c2', {})],
        package_dependencies={'language': [pdep('p', 'r')]}, package_metrics={'language': pmetrics({'pkg:x': 0.9})})
    return cur, base


def test_V04_policy_value_and_key_sets():
    assert api().DELTA_POLICY == 'delta.v5'
    cur, base = mixed_pair()
    result = run(cur, base)
    assert result['policy'] == 'delta.v5'
    assert set(result) == DELTA_KEYS
    assert set(result['counts']) == {'new_cycles', 'grown_cycles', 'new_violations', 'new_package_dependencies', 'instability_changes',
                                     'new_candidates', 'strengthened_candidates', 'changed_signatures', 'removed_symbols',
                                     'untested_changes', 'weakened_tests', 'added_mocks'}
    assert set(result['resolved']) == {'cycles', 'violations', 'package_dependencies', 'candidates'}
    assert result['counts']['new_candidates'] == len(result['new_candidates']) == 1
    assert result['counts']['strengthened_candidates'] == len(result['strengthened_candidates']) == 1


def test_V04_existing_lists_and_resolved_values_ignore_general_candidates():
    cur, base = mixed_pair()
    with_general = run(cur, base)
    without = run({**cur, 'candidates': [c for c in cur['candidates'] if c['kind'] in ('dependency_cycle', 'rule_violation')]},
                   {**base, 'candidates': [c for c in base['candidates'] if c['kind'] in ('dependency_cycle', 'rule_violation')]})
    for name in ('baseline', 'rules_changed', 'new_cycles', 'grown_cycles', 'new_violations', 'new_package_dependencies',
                 'instability_changes'):
        assert with_general[name] == without[name], name
    for name in ('cycles', 'violations', 'package_dependencies'):
        assert with_general['resolved'][name] == without['resolved'][name], name
    assert len(without['new_violations']) == 1 and len(without['grown_cycles']) == 1 and len(without['instability_changes']) == 1


def test_V04_cycle_and_violation_changes_only_leave_general_lists_empty():
    cur = payload(candidates=[cycle([A, B, C]), internal_violation('b:v2', A, C)])
    base = payload(candidates=[cycle([A, B]), internal_violation('b:v1', A, B)])
    result = run(cur, base)
    assert empty_general(result) and result['resolved']['candidates'] == 0
    assert len(result['grown_cycles']) == 1 and len(result['new_violations']) == 1 and result['resolved']['violations'] == 1


@pytest.mark.parametrize('fail_on', [['any'], ['cycle'], ['violation'], ['cycle', 'violation']])
def test_V04_regressions_ignore_general_only_delta(fail_on):
    cur = payload(candidates=[gen('isolated_node', A, 'c1', {}), gen('large_node', B, 'c2', {'line_count': 9})])
    base = payload(candidates=[gen('large_node', B, 'b2', {'line_count': 1})])
    result = run(cur, base)
    assert result['new_candidates'] and result['strengthened_candidates']
    assert api().regressions(result, fail_on) == []


def test_V04_v8_baseline_file_applies_general_comparison_and_checks(tmp_path):
    base = payload(candidates=[gen('large_node', B, 'b1', {'line_count': 1}), gen('duplicate_code', C, 'b2', {})])
    assert base['schema'] == 'bottlenecks.v8'
    loaded = api().load_baseline(write(tmp_path, base))
    cur = payload(candidates=[gen('large_node', B, 'c1', {'line_count': 2}), gen('isolated_node', A, 'c3', {})])
    result = run(cur, loaded)
    assert [i['candidate_id'] for i in result['new_candidates']] == ['c3']
    assert [i['increased'] for i in result['strengthened_candidates']] == [{'line_count': {'baseline': 1, 'current': 2}}]
    assert result['resolved']['candidates'] == 1
    broken = payload(candidates=[gen('large_node', 5, 'b1', {})])
    with pytest.raises(api().BaselineError, match=r'\$\.candidates\[0\]\.target'):
        api().load_baseline(write(tmp_path, broken, 'broken.json'))


# ---------------------------------------------------------------- V05 CLI scenario

UNRESOLVED_CALLS = ('\nfrom app.services import jwt as zz_jwt_module\n\n\ndef zz_calls_missing_attributes():\n'
                    + ''.join(f'    zz_jwt_module.zz_missing_name_{i}()\n' for i in range(3)))


def test_V05_cli_baseline_rerun_reports_new_unresolved_boundary_and_isolated_node(tmp_path):
    pristine = fixture_root(NAME).resolve()
    run_bottlenecks(pristine, tmp_path / 'base')
    baseline = tmp_path / 'base' / 'b.json'
    root = copy_fixture(NAME, tmp_path / 'copy')
    append_file(root, 'app/services/security.py', UNRESOLVED_CALLS)
    append_file(root, 'app/zz_orphan.py', 'def orphan():\n    return 1\n')
    retrack(root)
    done = run_bottlenecks(root, tmp_path / 'out', extra=['--baseline', baseline], check=False)
    assert done.returncode == 0, done.stderr[-1500:]
    delta = json.loads((tmp_path / 'out' / 'b.json').read_text(encoding='utf-8'))['delta']
    reported = delta['new_candidates'] + delta['strengthened_candidates']
    assert any(i['kind'] == 'unresolved_boundary' and i['target'] == 'file:app/services/security.py' for i in reported)
    assert any(i['kind'] == 'isolated_node' and i['target'] == 'file:app/zz_orphan.py' for i in delta['new_candidates'])
    assert all(i['kind'] not in ('dependency_cycle', 'package_cycle', 'rule_violation') for i in reported)
    lines = [line for line in done.stdout.splitlines() if line.startswith('[Δ]')]
    symbol_lines = [line for line in lines if line.startswith('[Δ] Symbol changes')]
    assert symbol_lines == [SYMBOL_SUMMARY.format(delta['counts']['changed_signatures'], delta['counts']['removed_symbols'])]
    test_lines = [line for line in lines if line.startswith('[Δ] Test changes')]
    assert test_lines == [TEST_SUMMARY.format(*(delta['counts'][n] for n in TEST_LISTS))]
    lines = [line for line in lines if line not in symbol_lines and line not in test_lines]
    expected = SUMMARY.format(*(len(delta[n]) for n in ('new_cycles', 'grown_cycles', 'new_violations', 'new_package_dependencies',
                                                        'instability_changes')),
                              len(delta['new_candidates']), len(delta['strengthened_candidates']))
    assert lines == [expected]
    assert lines[0].endswith(f", new candidates {delta['counts']['new_candidates']}, "
                             f"strengthened candidates {delta['counts']['strengthened_candidates']}")
    assert delta['counts']['new_candidates'] == len(delta['new_candidates']) >= 1


# ---------------------------------------------------------------- V06 metamorphic

def varied_pair():
    base = payload(candidates=[
        gen('large_node', A, 'b1', {'line_count': 10, 'token_count': 20}),
        gen('unresolved_boundary', B, 'b2', {'unresolved_count': 2}, evidence=boundary_evidence(B, ['foo'])),
        gen('dangling_doc_reference', C, 'b3', {'dangling_count': 1}, evidence=doc_evidence(('path', 'a.md'))),
        gen('duplicate_code', A, 'b4', {}), gen('duplicate_code', A, 'b5', {}), gen('isolated_node', 'file:gone.py', 'b6', {}),
        cycle([A, B])])
    cur = payload(candidates=[
        gen('large_node', A, 'c1', {'line_count': 30, 'token_count': 20}),
        gen('unresolved_boundary', B, 'c2', {'unresolved_count': 3}, evidence=boundary_evidence(B, ['foo', 'bar'])),
        gen('dangling_doc_reference', C, 'c3', {'dangling_count': 1}, evidence=doc_evidence(('path', 'a.md'))),
        gen('duplicate_code', A, 'b4', {}), gen('duplicate_code', A, 'c9', {}), gen('isolated_node', 'file:fresh.py', 'c6', {}),
        cycle([A, B])])
    return cur, base


def test_V06_M1_identity():
    cur, _ = varied_pair()
    result = run(cur, copy.deepcopy(cur))
    assert empty_general(result) and result['resolved']['candidates'] == 0


def test_V06_M2_swap_symmetry_of_new_and_resolved():
    cur, base = varied_pair()
    forward, backward = run(cur, base), run(base, cur)
    assert forward['counts']['new_candidates'] == backward['resolved']['candidates']
    assert backward['counts']['new_candidates'] == forward['resolved']['candidates']
    assert forward['counts']['new_candidates'] == 2 and forward['resolved']['candidates'] == 2


def test_V06_M3_candidate_order_does_not_change_the_result():
    cur, base = varied_pair()
    expected = run(cur, base)
    rng = random.Random(20261110)
    for _ in range(5):
        shuffled_cur, shuffled_base = copy.deepcopy(cur), copy.deepcopy(base)
        rng.shuffle(shuffled_cur['candidates'])
        rng.shuffle(shuffled_base['candidates'])
        assert run(shuffled_cur, shuffled_base) == expected


def test_V06_M4_rename_is_resolved_plus_new_known_false_positive():
    base = payload(candidates=[gen('isolated_node', 'file:old_name.py', 'b1', {})])
    cur = payload(candidates=[gen('isolated_node', 'file:new_name.py', 'c1', {})])
    result = run(cur, base)
    assert result['resolved']['candidates'] == 1
    assert [i['target'] for i in result['new_candidates']] == ['file:new_name.py']
    assert result['strengthened_candidates'] == []


# ---------------------------------------------------------------- V07 performance

def large_general_pair():
    kinds = ['large_node', 'unresolved_boundary', 'evidence_spread', 'dangling_doc_reference', 'unstable_dependency', 'untested_hub']
    main = {'large_node': 'line_count', 'unresolved_boundary': 'unresolved_count', 'evidence_spread': 'file_count',
            'dangling_doc_reference': 'dangling_count', 'unstable_dependency': 'file_pair_count'}

    def item(i, ident, bump):
        kind = kinds[i % 6]
        metrics = {main[kind]: 10 + bump} if kind in main else {'pagerank': 0.1}
        return gen(kind, f'file:m{i}.py', ident, metrics, evidence=[] if kind in ('unresolved_boundary', 'dangling_doc_reference') else None)
    common = 25000
    base = [item(i, f'b{i}', 0) for i in range(common)] + [item(i, f'b{i}', 0) for i in range(common, 2 * common)]
    cur = [item(i, f'c{i}', 1 if i % 5 == 0 else 0) for i in range(common)] + [item(i, f'c{i}', 0) for i in range(2 * common, 3 * common)]
    cycles = [cycle([f'file:cy{i}/a.py', f'file:cy{i}/b.py']) for i in range(20)]
    return payload(candidates=cur + cycles), payload(candidates=base + cycles[:10])


def test_V07_fifty_thousand_candidates_per_side_in_three_seconds():
    cur, base = large_general_pair()
    best = None
    for _ in range(3):
        start = time.perf_counter()
        result = api().compute_delta(cur, base)
        elapsed = time.perf_counter() - start
        best = elapsed if best is None else min(best, elapsed)
    assert best <= 3.0, best
    result = wire(result)
    assert result['counts']['new_candidates'] == 25000
    assert result['resolved']['candidates'] == 25000
    assert result['counts']['strengthened_candidates'] == 4166


# ---------------------------------------------------------------- V08 error guessing

def test_V08_pairing_uses_key_not_id():
    base = gen('large_node', A, 'same-id', {'line_count': 1})
    moved = gen('large_node', B, 'same-id', {'line_count': 1})
    result = run_lists([moved], [base])
    assert [i['target'] for i in result['new_candidates']] == [B] and result['resolved']['candidates'] == 1
    paired = gen('large_node', A, 'other-id', {'line_count': 5})
    result = run_lists([paired], [base])
    assert result['new_candidates'] == [] and result['resolved']['candidates'] == 0
    assert result['strengthened_candidates'][0]['baseline_candidate_id'] == 'same-id'


def test_V08_tier_is_not_part_of_the_key_but_other_structure_is():
    base = gen('unstable_dependency', 'pkg:p->pkg:q', 'b1', {'file_pair_count': 3}, structure={'scheme': 'language', 'tier': 'certain'})
    other_tier = gen('unstable_dependency', 'pkg:p->pkg:q', 'c1', {'file_pair_count': 3}, structure={'scheme': 'language', 'tier': 'all'})
    assert empty_general(run_lists([other_tier], [base]))
    other_scheme = gen('unstable_dependency', 'pkg:p->pkg:q', 'c1', {'file_pair_count': 3}, structure={'scheme': 'framework', 'tier': 'certain'})
    result = run_lists([other_scheme], [base])
    assert [i['candidate_id'] for i in result['new_candidates']] == ['c1'] and result['resolved']['candidates'] == 1
    no_structure = gen('unstable_dependency', 'pkg:p->pkg:q', 'c2', {'file_pair_count': 3})
    result = run_lists([no_structure], [base])
    assert len(result['new_candidates']) == 1 and result['resolved']['candidates'] == 1


@pytest.mark.parametrize('kind, metric', SEVEN_PAIRS, ids=[f'{k}-{m}' for k, m in SEVEN_PAIRS])
def test_V08_decrease_is_not_reported_in_any_list(kind, metric):
    target = KINDS_WITH_STRENGTH[kind][0]
    base = gen(kind, target, 'b1', {name: 10 for name in STRENGTH[kind]})
    cur = gen(kind, target, 'c1', {**base['metrics'], metric: 9})
    result = run_lists([cur], [base])
    assert empty_general(result) and result['resolved']['candidates'] == 0


def test_V08_increased_lists_only_metrics_that_grew():
    base = gen('large_node', A, 'b1', {'line_count': 100, 'token_count': 900})
    cur = gen('large_node', A, 'c1', {'line_count': 120, 'token_count': 900})
    assert run_lists([cur], [base])['strengthened_candidates'][0]['increased'] == {'line_count': {'baseline': 100, 'current': 120}}
    cur = gen('large_node', A, 'c1', {'line_count': 80, 'token_count': 901})
    assert run_lists([cur], [base])['strengthened_candidates'][0]['increased'] == {'token_count': {'baseline': 900, 'current': 901}}
    spread = gen('evidence_spread', A, 'b2', {'file_count': 4, 'directory_count': 2})
    grown = gen('evidence_spread', A, 'c2', {'file_count': 4, 'directory_count': 3})
    assert run_lists([grown], [spread])['strengthened_candidates'][0]['increased'] == {'directory_count': {'baseline': 2, 'current': 3}}


def test_V08_signatures_ignore_line_numbers_and_other_evidence_fields():
    base = gen('unresolved_boundary', A, 'b1', {'unresolved_count': 1}, evidence=boundary_evidence(A, ['foo'], line=3))
    cur = gen('unresolved_boundary', A, 'c1', {'unresolved_count': 1}, evidence=boundary_evidence(A, ['foo'], line=40))
    cur['evidence'][0]['path'] = 'elsewhere.py'
    cur['evidence'][0]['detail_edge_index'] = 7
    assert empty_general(run_lists([cur], [base]))
    doc_base = gen('dangling_doc_reference', 'file:d.md', 'b1', {'dangling_count': 1}, evidence=doc_evidence(('path', 'a.md'), line=2))
    doc_cur = gen('dangling_doc_reference', 'file:d.md', 'c1', {'dangling_count': 1}, evidence=doc_evidence(('path', 'a.md'), line=90))
    assert empty_general(run_lists([doc_cur], [doc_base]))


def test_V08_signature_forms_flag_and_edge_and_default_node():
    base = gen('unresolved_boundary', A, 'b1', {'unresolved_count': 1}, evidence=[{}])
    cur = gen('unresolved_boundary', A, 'c1', {'unresolved_count': 1}, evidence=[
        {'flags': ['dynamic_import'], 'from_id': 'file:x.py', 'to_id': 'file:y.py', 'relation': 'IMPORTS'},
        {'node_id': B, 'unresolved_references': [{'name': 'zed', 'line': 1}]}])
    result = run_lists([cur], [base])
    assert result['strengthened_candidates'][0]['added_evidence'] == [
        ['edge', 'file:x.py', 'file:y.py', 'IMPORTS'], ['flag', A, 'dynamic_import'], ['reference', B, 'zed']]


def test_V08_cycles_and_violations_never_enter_general_lists():
    cur = payload(candidates=[cycle([A, B, C]), cycle(['p', 'q'], kind='package_cycle', scheme='language'),
                              internal_violation('b:v2', A, C)])
    result = run(cur, payload())
    assert empty_general(result) and result['resolved']['candidates'] == 0
    assert len(result['new_cycles']) == 2 and len(result['new_violations']) == 1
    result = run(payload(), cur)
    assert result['resolved']['candidates'] == 0 and result['resolved']['cycles'] == 2


def test_V08_unknown_kind_is_not_dropped_and_current_non_number_metric_does_not_raise():
    cur = [gen('future_kind', A, 'c1', {'x': 1}), gen('large_node', B, 'c2', {'line_count': 'many'})]
    base = [gen('large_node', B, 'b2', {'line_count': 5})]
    result = run_lists(cur, base)
    assert [i['kind'] for i in result['new_candidates']] == ['future_kind']
    assert result['strengthened_candidates'] == [] and result['resolved']['candidates'] == 0


def test_V08_output_order_is_kind_target_candidate_id():
    cur = [gen('isolated_node', B, 'z', {}), gen('isolated_node', A, 'y', {}), gen('duplicate_code', C, 'x', {}),
           gen('duplicate_code', C, 'w', {}, structure={'k': 1}), gen('isolated_node', A, 'a', {}, structure={'k': 1})]
    result = run_lists(cur, [])
    assert [(i['kind'], i['target'], i['candidate_id']) for i in result['new_candidates']] == [
        ('duplicate_code', C, 'w'), ('duplicate_code', C, 'x'), ('isolated_node', A, 'a'), ('isolated_node', A, 'y'),
        ('isolated_node', B, 'z')]
    base = gen('unresolved_boundary', A, 'b', {'unresolved_count': 1}, evidence=boundary_evidence(A, ['q']))
    cur = gen('unresolved_boundary', A, 'c', {'unresolved_count': 1}, evidence=boundary_evidence(A, ['q', 'b', 'a']))
    assert run_lists([cur], [base])['strengthened_candidates'][0]['added_evidence'] == [['reference', A, 'a'], ['reference', A, 'b']]


def test_V01_edge_signature_without_or_with_non_string_relation_uses_empty_relation():
    base = gen('unresolved_boundary', A, 'b1', {'unresolved_count': 1}, evidence=[{}])
    cur = gen('unresolved_boundary', A, 'c1', {'unresolved_count': 1}, evidence=[
        {'from_id': 'file:p.py', 'to_id': 'file:q.py'},
        {'from_id': 'file:r.py', 'to_id': 'file:s.py', 'relation': 5},
        {'from_id': 'file:t.py', 'to_id': 'file:u.py', 'relation': None}])
    result = run_lists([cur], [base])
    assert result['strengthened_candidates'][0]['added_evidence'] == [
        ['edge', 'file:p.py', 'file:q.py', ''], ['edge', 'file:r.py', 'file:s.py', ''], ['edge', 'file:t.py', 'file:u.py', '']]
    assert result['strengthened_candidates'][0]['increased'] == {}


def test_V01_flag_and_reference_signatures_use_the_element_node_id_not_the_target():
    base = gen('unresolved_boundary', A, 'b1', {'unresolved_count': 1}, evidence=[{}])
    cur = gen('unresolved_boundary', A, 'c1', {'unresolved_count': 1}, evidence=[
        {'node_id': 'file:other.py', 'flags': ['dynamic_import'], 'unresolved_references': [{'name': 'ghost', 'line': 2}]}])
    result = run_lists([cur], [base])
    assert result['strengthened_candidates'][0]['added_evidence'] == [
        ['flag', 'file:other.py', 'dynamic_import'], ['reference', 'file:other.py', 'ghost']]


def test_V01_same_signature_under_a_different_node_id_is_an_added_signature():
    base = gen('unresolved_boundary', A, 'b1', {'unresolved_count': 1},
               evidence=[{'node_id': 'file:one.py', 'flags': ['dynamic_import']}])
    cur = gen('unresolved_boundary', A, 'c1', {'unresolved_count': 1},
              evidence=[{'node_id': 'file:two.py', 'flags': ['dynamic_import']}])
    result = run_lists([cur], [base])
    assert result['strengthened_candidates'][0]['added_evidence'] == [['flag', 'file:two.py', 'dynamic_import']]


def ordered(pairs):
    return dict(pairs)


FORWARD = [('scheme', 'language'), ('from_layer', 'db'), ('zeta', 1), ('alpha', 2)]


def test_V01_structure_key_insertion_order_does_not_affect_pairing():
    for kind, target in (('unstable_dependency', 'pkg:p->pkg:q'), ('duplicate_code', A)):
        base = gen(kind, target, 'b1', {'file_pair_count': 3}, structure={**ordered(FORWARD), 'tier': 'certain'})
        cur = gen(kind, target, 'c1', {'file_pair_count': 3}, structure={'tier': 'all', **ordered(reversed(FORWARD))})
        assert list(base['structure']) != list(cur['structure'])
        result = run_lists([cur], [base])
        assert empty_general(result) and result['resolved']['candidates'] == 0, kind
        cur['metrics']['file_pair_count'] = 4
        result = run_lists([cur], [base])
        if kind == 'unstable_dependency':
            assert result['strengthened_candidates'] == [strengthened_item(cur, base, {'file_pair_count': {'baseline': 3, 'current': 4}})]
        else:
            assert empty_general(result)
        assert result['new_candidates'] == [] and result['resolved']['candidates'] == 0


def test_V06_M5_structure_key_order_permutation_leaves_the_result_unchanged():
    cur, base = varied_pair()
    cur['candidates'].append(gen('unstable_dependency', 'pkg:a->pkg:b', 'c20', {'file_pair_count': 5}, structure=ordered(FORWARD)))
    base['candidates'].append(gen('unstable_dependency', 'pkg:a->pkg:b', 'b20', {'file_pair_count': 4}, structure=ordered(FORWARD)))
    expected = run(cur, base)
    assert len(expected['strengthened_candidates']) == 3
    permuted = copy.deepcopy(base)
    for item in permuted['candidates']:
        if 'structure' in item:
            item['structure'] = ordered(reversed(list(item['structure'].items())))
    assert list(permuted['candidates'][-1]['structure']) != list(base['candidates'][-1]['structure'])
    assert run(cur, permuted) == expected
    permuted_cur = copy.deepcopy(cur)
    for item in permuted_cur['candidates']:
        if 'structure' in item:
            item['structure'] = ordered(reversed(list(item['structure'].items())))
    assert run(permuted_cur, base) == expected
