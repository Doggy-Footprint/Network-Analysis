"""Expected values come from spec F03, F05-F12, F14 and F15, from hand calculation, and from the nested-scan reference in
tests/delta_support.py; none comes from product output."""
import copy
import dataclasses
import hashlib
import itertools
import json

import pytest

from tests.delta_support import (DELTA_KEYS, LISTS, canonical, cid, cycle, external_violation, independent_digest, internal_violation,
                                 make_delta, payload, pdep, pmetrics, ref_delta, ref_regressions, wire)

A, B, C, D, E = ('file:%s.py' % n for n in 'abcde')


def delta_api():
    import bottlenecks.delta as module
    return module


def run(current, baseline):
    result = wire(delta_api().compute_delta(current, baseline))
    assert result == wire(ref_delta(current, baseline))
    return result


def empty_lists(result):
    return all(result[name] == [] for name in LISTS)


def baseline_of(*cycles, **kwargs):
    return payload(candidates=list(cycles), **kwargs)


def pairs_of(*pairs):
    return [list(p) for p in pairs]


def test_policy_constant():
    assert delta_api().DELTA_POLICY == 'delta.v1'


def test_F12_delta_object_shape_and_counts():
    base = payload(candidates=[cycle([A, B])], file_count=7, rules_sha='h1')
    cur = payload(candidates=[cycle([A, B, C]), cycle([D, E])], file_count=9, rules_sha='h1')
    result = run(cur, base)
    assert set(result) == DELTA_KEYS
    assert result['policy'] == 'delta.v1'
    assert result['baseline'] == {'file_count': 7, 'rules_sha256': 'h1'}
    assert result['rules_changed'] is False
    assert result['resolved'] == {'cycles': 0, 'violations': 0, 'package_dependencies': 0}
    assert result['counts'] == {'new_cycles': 1, 'grown_cycles': 1, 'new_violations': 0, 'new_package_dependencies': 0,
                                'instability_changes': 0}


def test_F12_same_input_same_bytes_and_inputs_untouched():
    base = payload(candidates=[cycle([A, B]), internal_violation('b:v1', A, B)], package_dependencies={'language': [pdep('p', 'q')]})
    cur = payload(candidates=[cycle([A, B, C]), internal_violation('b:v2', A, C)], package_dependencies={'language': [pdep('p', 'r')]})
    frozen = (copy.deepcopy(cur), copy.deepcopy(base))
    first = delta_api().compute_delta(cur, base)
    second = delta_api().compute_delta(copy.deepcopy(cur), copy.deepcopy(base))
    assert canonical(wire(first)) == canonical(wire(second))
    assert (cur, base) == frozen


# V01 decision table ---------------------------------------------------------------------------------------------------

def test_V01_C_new_cycle_when_no_overlap():
    cur = payload(candidates=[cycle([A, B])])
    result = run(cur, baseline_of(cycle([D, E])))
    assert result['grown_cycles'] == []
    assert result['new_cycles'] == [{
        'candidate_id': cid('dependency_cycle', 'file', 'all', [A, B]), 'kind': 'dependency_cycle', 'scheme': 'file',
        'tier': 'all', 'members': [A, B], 'baseline_candidate_ids': [], 'added_members': [A, B],
        'new_internal_pairs': pairs_of((A, B), (B, A))}]
    assert result['resolved']['cycles'] == 1


def test_V01_C05_grown_by_added_member():
    result = run(payload(candidates=[cycle([A, B, C])]), baseline_of(cycle([A, B])))
    assert result['new_cycles'] == []
    assert result['grown_cycles'] == [{
        'candidate_id': cid('dependency_cycle', 'file', 'all', [A, B, C]), 'kind': 'dependency_cycle', 'scheme': 'file',
        'tier': 'all', 'members': [A, B, C], 'baseline_candidate_ids': [cid('dependency_cycle', 'file', 'all', [A, B])],
        'added_members': [C], 'new_internal_pairs': pairs_of((B, C), (C, A))}]
    assert result['resolved']['cycles'] == 0


def test_V01_C07_shrunk_cycle_is_not_reported():
    result = run(payload(candidates=[cycle([A, B])]), baseline_of(cycle([A, B, C])))
    assert empty_lists(result)
    assert result['resolved']['cycles'] == 0


def test_V01_C06_merged_cycles_grow_without_added_members():
    base = baseline_of(cycle([A, B]), cycle([C, D]))
    cur = payload(candidates=[cycle([A, B, C, D], pairs=[(A, B), (B, A), (C, D), (D, C), (B, C)])])
    result = run(cur, base)
    assert result['new_cycles'] == []
    [item] = result['grown_cycles']
    assert item['added_members'] == []
    assert item['baseline_candidate_ids'] == sorted([cid('dependency_cycle', 'file', 'all', [A, B]),
                                                      cid('dependency_cycle', 'file', 'all', [C, D])])
    assert item['new_internal_pairs'] == pairs_of((B, C))
    assert result['resolved']['cycles'] == 0


def test_V01_merged_cycles_with_added_member():
    base = baseline_of(cycle([A, B]), cycle([C, D]))
    result = run(payload(candidates=[cycle([A, B, C, D, E])]), base)
    [item] = result['grown_cycles']
    assert item['added_members'] == [E] and len(item['baseline_candidate_ids']) == 2
    assert result['new_cycles'] == []


def test_V01_C08_extra_internal_edge_is_not_reported():
    base = baseline_of(cycle([A, B], pairs=[(A, B)]))
    cur = payload(candidates=[cycle([A, B], pairs=[(A, B), (B, A)])])
    result = run(cur, base)
    assert empty_lists(result) and result['resolved']['cycles'] == 0


def test_V01_C09_overlap_of_one_member_grows():
    result = run(payload(candidates=[cycle([B, C])]), baseline_of(cycle([A, B])))
    [item] = result['grown_cycles']
    assert result['new_cycles'] == []
    assert item['added_members'] == [C]
    assert item['baseline_candidate_ids'] == [cid('dependency_cycle', 'file', 'all', [A, B])]
    assert result['resolved']['cycles'] == 0


def test_V01_C10_tier_is_part_of_the_key():
    base = baseline_of(cycle([A, B], tier='all'))
    cur = payload(candidates=[cycle([A, B], tier='all'), cycle([A, B], tier='certain')])
    result = run(cur, base)
    assert [(i['tier'], i['candidate_id']) for i in result['new_cycles']] == [('certain', cid('dependency_cycle', 'file', 'certain', [A, B]))]
    assert result['grown_cycles'] == []


def test_V01_kind_is_part_of_the_key():
    base = baseline_of(cycle([A, B], kind='dependency_cycle', scheme='language'))
    cur = payload(candidates=[cycle([A, B], kind='package_cycle', scheme='language')])
    result = run(cur, base)
    assert [i['kind'] for i in result['new_cycles']] == ['package_cycle']
    assert result['grown_cycles'] == []
    assert result['resolved']['cycles'] == 1


def test_V01_scheme_is_part_of_the_key():
    base = baseline_of(cycle(['p', 'q'], kind='package_cycle', scheme='language'))
    cur = payload(candidates=[cycle(['p', 'q'], kind='package_cycle', scheme='framework')])
    result = run(cur, base)
    assert [(i['scheme'], i['baseline_candidate_ids']) for i in result['new_cycles']] == [('framework', [])]
    assert result['resolved']['cycles'] == 1


def test_V01_new_cycles_sorted_by_kind_scheme_tier_id():
    cur = payload(candidates=[
        cycle(['p', 'q'], kind='package_cycle', scheme='language', tier='certain'),
        cycle([D, E], tier='resolved'), cycle([A, B], tier='certain'), cycle([C, D]),
        cycle(['x', 'y'], kind='package_cycle', scheme='framework', tier='all'),
        cycle(['u', 'v'], kind='package_cycle', scheme='language', tier='all')])
    result = run(cur, payload())
    keys = [(i['kind'], i['scheme'], i['tier'], i['candidate_id']) for i in result['new_cycles']]
    assert keys == sorted(keys) and len(keys) == 6
    assert [k[:3] for k in keys] == [('dependency_cycle', 'file', 'all'), ('dependency_cycle', 'file', 'certain'),
                                    ('dependency_cycle', 'file', 'resolved'), ('package_cycle', 'framework', 'all'),
                                    ('package_cycle', 'language', 'all'), ('package_cycle', 'language', 'certain')]


def test_V01_new_internal_pairs_sorted_by_from_then_to():
    base = baseline_of(cycle([A, B], pairs=[(A, B), (B, A)]))
    cur = payload(candidates=[cycle([A, B, C], pairs=[(C, A), (B, C), (A, B), (B, A), (A, C)])])
    [item] = run(cur, base)['grown_cycles']
    assert item['new_internal_pairs'] == pairs_of((A, C), (B, C), (C, A))


# V02 ------------------------------------------------------------------------------------------------------------------

def test_V02_new_internal_violation():
    cur = payload(candidates=[internal_violation('b:v9', A, B, rule_type='allow', from_layer='domain', to_layer='services')])
    result = run(cur, payload())
    assert result['new_violations'] == [{'candidate_id': 'b:v9', 'rule_type': 'allow', 'from_layer': 'domain', 'target': A,
                                         'to_layer': 'services', 'to_id': B}]
    assert result['counts']['new_violations'] == 1


def test_V02_new_external_violation():
    cur = payload(candidates=[external_violation('b:e1', A, 'fastapi')])
    result = run(cur, payload())
    assert result['new_violations'] == [{'candidate_id': 'b:e1', 'rule_type': 'forbid_external', 'from_layer': 'db', 'target': A,
                                         'to_external': 'fastapi'}]
    assert 'to_layer' not in result['new_violations'][0] and 'to_id' not in result['new_violations'][0]


def test_V02_existing_violation_is_kept_even_when_other_fields_change():
    base = payload(candidates=[internal_violation('b:v1', A, B, tier='certain')])
    cur = payload(candidates=[internal_violation('b:v1', A, B, tier='all')])
    result = run(cur, base)
    assert empty_lists(result) and result['resolved']['violations'] == 0


def test_V02_vanished_violation_is_counted_as_resolved():
    base = payload(candidates=[internal_violation('b:v1', A, B), external_violation('b:v2', A, 'os'), internal_violation('b:v3', C, D)])
    cur = payload(candidates=[internal_violation('b:v3', C, D)])
    result = run(cur, base)
    assert empty_lists(result) and result['resolved']['violations'] == 2


def test_V02_violation_identity_is_the_candidate_id_not_the_file_pair():
    base = payload(candidates=[internal_violation('b:v1', A, B, rule_type='allow')])
    cur = payload(candidates=[internal_violation('b:v1', A, B, rule_type='allow'), internal_violation('b:v2', A, B, rule_type='forbid')])
    result = run(cur, base)
    assert [(i['candidate_id'], i['rule_type']) for i in result['new_violations']] == [('b:v2', 'forbid')]
    assert result['resolved']['violations'] == 0


def test_V02_new_violations_sorted_by_candidate_id():
    cur = payload(candidates=[internal_violation('b:c', A, B), external_violation('b:a', A, 'os'), internal_violation('b:b', C, D)])
    assert [i['candidate_id'] for i in run(cur, payload())['new_violations']] == ['b:a', 'b:b', 'b:c']


def test_V02_new_package_dependency():
    cur = payload(package_dependencies={'language': [pdep('p', 'q', 'resolved')]})
    result = run(cur, payload())
    assert result['new_package_dependencies'] == [{'scheme': 'language', 'from_id': 'p', 'to_id': 'q', 'tier': 'resolved'}]
    assert result['counts']['new_package_dependencies'] == 1 and result['resolved']['package_dependencies'] == 0


def test_V02_kept_package_dependency():
    both = {'language': [pdep('p', 'q')]}
    result = run(payload(package_dependencies=both), payload(package_dependencies=both))
    assert empty_lists(result) and result['resolved']['package_dependencies'] == 0


def test_V02_vanished_package_dependency():
    base = payload(package_dependencies={'language': [pdep('p', 'q'), pdep('q', 'r')], 'framework': [pdep('m', 'n')]})
    cur = payload(package_dependencies={'language': [pdep('q', 'r')], 'framework': []})
    result = run(cur, base)
    assert empty_lists(result) and result['resolved']['package_dependencies'] == 2


def test_V02_C12_scheme_missing_from_baseline_makes_every_pair_new():
    base = payload(package_dependencies={'language': [pdep('p', 'q')]})
    cur = payload(package_dependencies={'language': [pdep('p', 'q')], 'framework': [pdep('n2', 'n1'), pdep('n1', 'n2', 'all')]})
    result = run(cur, base)
    assert result['new_package_dependencies'] == [{'scheme': 'framework', 'from_id': 'n1', 'to_id': 'n2', 'tier': 'all'},
                                                  {'scheme': 'framework', 'from_id': 'n2', 'to_id': 'n1', 'tier': 'certain'}]


def test_V02_tier_only_change_is_not_reported():
    base = payload(package_dependencies={'language': [pdep('p', 'q', 'all')]})
    cur = payload(package_dependencies={'language': [pdep('p', 'q', 'certain')]})
    result = run(cur, base)
    assert empty_lists(result) and result['resolved']['package_dependencies'] == 0


def test_V02_same_pair_in_two_schemes_is_independent():
    base = payload(package_dependencies={'language': [pdep('p', 'q')], 'framework': []})
    cur = payload(package_dependencies={'language': [pdep('p', 'q')], 'framework': [pdep('p', 'q')]})
    assert [i['scheme'] for i in run(cur, base)['new_package_dependencies']] == ['framework']


def test_V02_new_package_dependencies_sorted_by_scheme_from_to():
    cur = payload(package_dependencies={'language': [pdep('b', 'a'), pdep('a', 'c'), pdep('a', 'b')], 'framework': [pdep('z', 'y')]})
    keys = [(i['scheme'], i['from_id'], i['to_id']) for i in run(cur, payload(package_dependencies={}))['new_package_dependencies']]
    assert keys == [('framework', 'z', 'y'), ('language', 'a', 'b'), ('language', 'a', 'c'), ('language', 'b', 'a')]


# V03 ------------------------------------------------------------------------------------------------------------------

def instability(before, after, scheme='language'):
    base = payload(package_metrics={scheme: pmetrics({'pkg:x': before})})
    cur = payload(package_metrics={scheme: pmetrics({'pkg:x': after})})
    return run(cur, base)['instability_changes']


@pytest.mark.parametrize('before, after', [
    pytest.param(0.5, 0.7, id='plus-0.19999999999999996'),
    pytest.param(0.0, 0.2, id='plus-0.2'),
    pytest.param(0.0, 0.2000001, id='plus-0.2000001'),
    pytest.param(0.7, 0.5, id='minus-0.19999999999999996'),
    pytest.param(0.2, 0.0, id='minus-0.2'),
    pytest.param(0.2000001, 0.0, id='minus-0.2000001'),
])
def test_V03_reported_boundaries(before, after):
    assert instability(before, after) == [{'scheme': 'language', 'package': 'pkg:x', 'baseline': before, 'current': after,
                                           'delta': after - before}]


@pytest.mark.parametrize('before, after', [(0.0, 0.1999), (0.1999, 0.0), (0.0, 0.0), (0.4, 0.4)])
def test_V03_C11_below_threshold_is_not_reported(before, after):
    assert instability(before, after) == []


@pytest.mark.parametrize('before, after', [(None, 0.9), (0.9, None), (None, None)])
def test_V03_null_on_either_side_is_not_reported(before, after):
    assert instability(before, after) == []


def test_V03_package_on_one_side_only_is_not_reported():
    base = payload(package_metrics={'language': pmetrics({'pkg:old': 0.0, 'pkg:x': 0.5})})
    cur = payload(package_metrics={'language': pmetrics({'pkg:new': 1.0, 'pkg:x': 0.5})})
    assert run(cur, base)['instability_changes'] == []


def test_V03_C11_combined_order_is_largest_magnitude_first():
    names = {'pkg:a': (0.5, 0.7), 'pkg:b': (0.0, 0.1999), 'pkg:c': (0.5, 0.25), 'pkg:d': (0.0, 0.2)}
    base = payload(package_metrics={'language': pmetrics({k: v[0] for k, v in names.items()})})
    cur = payload(package_metrics={'language': pmetrics({k: v[1] for k, v in names.items()})})
    result = run(cur, base)['instability_changes']
    assert [i['package'] for i in result] == ['pkg:c', 'pkg:d', 'pkg:a']
    assert result[0]['delta'] == 0.25 - 0.5 and result[0]['baseline'] == 0.5 and result[0]['current'] == 0.25


def test_V03_ties_sort_by_scheme_then_package():
    base = payload(package_metrics={'language': pmetrics({'pkg:b': 0.0, 'pkg:a': 0.0}), 'framework': pmetrics({'pkg:z': 0.0})})
    cur = payload(package_metrics={'language': pmetrics({'pkg:b': 0.5, 'pkg:a': 0.5}), 'framework': pmetrics({'pkg:z': 0.5})})
    keys = [(i['scheme'], i['package']) for i in run(cur, base)['instability_changes']]
    assert keys == [('framework', 'pkg:z'), ('language', 'pkg:a'), ('language', 'pkg:b')]


def test_V03_scheme_mismatch_is_not_compared():
    base = payload(package_metrics={'language': pmetrics({'pkg:x': 0.0})})
    cur = payload(package_metrics={'framework': pmetrics({'pkg:x': 1.0})})
    assert run(cur, base)['instability_changes'] == []


# V14 error guessing ---------------------------------------------------------------------------------------------------

def test_V14_overlap_is_compared_by_member_not_by_candidate_id():
    base = baseline_of(cycle([A, B], ident='b:same'))
    cur = payload(candidates=[cycle([C, D], ident='b:same')])
    result = run(cur, base)
    assert [i['candidate_id'] for i in result['new_cycles']] == ['b:same'] and result['grown_cycles'] == []
    assert result['resolved']['cycles'] == 1
    cur = payload(candidates=[cycle([A, B, C], ident='b:other')])
    assert [i['candidate_id'] for i in run(cur, base)['grown_cycles']] == ['b:other']


def test_V14_grown_cycle_is_not_classified_as_new():
    result = run(payload(candidates=[cycle([A, B, C])]), baseline_of(cycle([A, B])))
    assert result['counts']['new_cycles'] == 0 and result['counts']['grown_cycles'] == 1


def test_V14_added_members_exclude_every_overlapping_baseline_member():
    base = baseline_of(cycle([A, B]), cycle([C, D]), cycle([E, 'file:f.py']))
    cur = payload(candidates=[cycle([A, B, C, D, 'file:g.py'])])
    [item] = run(cur, base)['grown_cycles']
    assert item['added_members'] == ['file:g.py']
    assert E not in item['added_members'] and len(item['baseline_candidate_ids']) == 2


def test_V14_violation_identity_ignores_tier_and_layers():
    base = payload(candidates=[internal_violation('b:v1', A, B, tier='certain', from_layer='x', to_layer='y')])
    cur = payload(candidates=[internal_violation('b:v1', A, B, tier='all', from_layer='x', to_layer='y')])
    assert empty_lists(run(cur, base))


def test_V14_schemes_are_not_mixed_for_cycles_dependencies_and_metrics():
    base = payload(candidates=[cycle(['p', 'q'], kind='package_cycle', scheme='language')],
                   package_dependencies={'language': [pdep('p', 'q')]}, package_metrics={'language': pmetrics({'pkg:x': 0.0})})
    cur = payload(candidates=[cycle(['p', 'q'], kind='package_cycle', scheme='framework')],
                  package_dependencies={'framework': [pdep('p', 'q')]}, package_metrics={'framework': pmetrics({'pkg:x': 1.0})})
    result = run(cur, base)
    assert result['counts'] == {'new_cycles': 1, 'grown_cycles': 0, 'new_violations': 0, 'new_package_dependencies': 1,
                                'instability_changes': 0}
    assert result['resolved'] == {'cycles': 1, 'violations': 0, 'package_dependencies': 1}


def test_V14_resolved_cycles_exclude_baseline_cycles_that_overlap_current():
    base = baseline_of(cycle([A, B]), cycle([C, D]), cycle([E, 'file:f.py']))
    cur = payload(candidates=[cycle([A, B, C, D])])
    assert run(cur, base)['resolved']['cycles'] == 1
    cur = payload(candidates=[cycle([B, 'file:z.py'])])
    assert run(cur, base)['resolved']['cycles'] == 2


def test_V14_resolved_cycles_respect_the_key():
    base = baseline_of(cycle([A, B], tier='certain'))
    cur = payload(candidates=[cycle([A, B], tier='all')])
    assert run(cur, base)['resolved']['cycles'] == 1


def test_V14_internal_pairs_compare_direction():
    base = baseline_of(cycle([A, B], pairs=[(A, B)]))
    [item] = run(payload(candidates=[cycle([A, B, C], pairs=[(B, A), (A, B), (B, C)])]), base)['grown_cycles']
    assert item['new_internal_pairs'] == pairs_of((B, A), (B, C))


# F06 / rules_changed --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('cur_sha, base_sha, expected', [
    ('h1', 'h1', False), ('h1', 'h2', True), (None, 'h1', True), ('h1', None, True), ('absent', 'absent', False),
])
def test_F06_rules_changed(cur_sha, base_sha, expected):
    result = run(payload(rules_sha=cur_sha), payload(rules_sha=base_sha))
    assert result['rules_changed'] is expected
    assert result['baseline']['rules_sha256'] == (base_sha if base_sha not in ('absent', None) else None)


def test_F06_rules_differences_do_not_stop_the_comparison():
    base = payload(candidates=[cycle([A, B])], rules_sha='h1')
    cur = payload(candidates=[cycle([A, B, C])], rules_sha='h2')
    result = run(cur, base)
    assert result['rules_changed'] is True and len(result['grown_cycles']) == 1


@pytest.mark.parametrize('cur_sha, base_sha', [('h1', 'absent'), ('absent', 'h1'), (None, 'absent'), ('absent', None)])
def test_V04_F06_rules_on_one_side_only_is_an_error(cur_sha, base_sha):
    with pytest.raises(delta_api().BaselineError) as raised:
        delta_api().compute_delta(payload(rules_sha=cur_sha), payload(rules_sha=base_sha))
    assert str(raised.value).startswith('baseline: ')


def test_V04_F06_structure_policy_mismatch_is_an_error():
    with pytest.raises(delta_api().BaselineError) as raised:
        delta_api().compute_delta(payload(policy='structure.v2'), payload(policy='structure.v1'))
    assert str(raised.value).startswith('baseline: ') and 'structure_policy' in str(raised.value)


def test_V04_error_type_is_a_value_error():
    assert issubclass(delta_api().BaselineError, ValueError)


# V04 load_baseline ----------------------------------------------------------------------------------------------------

def good():
    return payload(
        candidates=[cycle([A, B]), cycle(['p', 'q'], kind='package_cycle', scheme='language'),
                    internal_violation('b:v1', A, B), external_violation('b:v2', A, 'os'),
                    {'id': 'b:l', 'kind': 'large_node'}],
        package_dependencies={'language': [pdep('p', 'q')]}, package_metrics={'language': pmetrics({'pkg:x': 0.5, 'pkg:n': None})},
        rules_sha='abc')


def write(tmp_path, data, name='baseline.json'):
    target = tmp_path / name
    if isinstance(data, bytes):
        target.write_bytes(data)
    else:
        target.write_text(data if isinstance(data, str) else json.dumps(data), encoding='utf-8')
    return target


def cand(data, kind):
    return next(c for c in data['candidates'] if c['kind'] == kind)


def violation(data, rule_type):
    return next(c for c in data['candidates'] if c['kind'] == 'rule_violation' and c['structure']['rule_type'] == rule_type)


def setter(path, value):
    def apply(data):
        target = data
        for part in path[:-1]:
            target = target[part]
        if value is DELETE:
            del target[path[-1]]
        else:
            target[path[-1]] = value
    return apply


DELETE = object()


def on(finder, *path, value):
    def apply(data):
        target = finder(data)
        for part in path[:-1]:
            target = target[part]
        if value is DELETE:
            del target[path[-1]]
        else:
            target[path[-1]] = value
    return apply


def dep_cycle(data):
    return cand(data, 'dependency_cycle')


def pkg_cycle(data):
    return cand(data, 'package_cycle')


def internal_v(data):
    return violation(data, 'forbid')


def external_v(data):
    return violation(data, 'forbid_external')


def pdeps(data):
    return data['dependency_network']['package_dependencies']


MUTATIONS = {
    'schema-v7': (setter(['schema'], 'bottlenecks.v7'), ['schema', 'bottlenecks.v8']),
    'schema-v6': (setter(['schema'], 'bottlenecks.v6'), ['schema', 'bottlenecks.v8']),
    'schema-missing': (setter(['schema'], DELETE), ['schema']),
    'granularity-missing': (setter(['granularity'], DELETE), ['granularity', 'file']),
    'granularity-symbol': (setter(['granularity'], 'symbol'), ['granularity', 'file']),
    'snapshot-missing': (setter(['snapshot'], DELETE), ['snapshot']),
    'file_count-string': (setter(['snapshot', 'file_count'], '3'), ['file_count']),
    'file_count-float': (setter(['snapshot', 'file_count'], 1.5), ['file_count']),
    'structure_policy-number': (setter(['dependency_network', 'structure_policy'], 5), ['structure_policy']),
    'structure_policy-missing': (setter(['dependency_network', 'structure_policy'], DELETE), ['structure_policy']),
    'package_dependencies-missing': (setter(['dependency_network', 'package_dependencies'], DELETE), ['package_dependencies']),
    'package_dependencies-list': (setter(['dependency_network', 'package_dependencies'], []), ['package_dependencies']),
    'package_dependencies-scheme-not-list': (lambda d: pdeps(d).update(language={}), ['package_dependencies']),
    'package_dependencies-item-not-object': (lambda d: pdeps(d)['language'].append('p'), ['package_dependencies']),
    'package_dependencies-from_id-int': (lambda d: pdeps(d)['language'][0].update(from_id=3), ['from_id']),
    'package_dependencies-to_id-missing': (lambda d: pdeps(d)['language'][0].pop('to_id'), ['to_id']),
    'package_dependencies-tier-unknown': (lambda d: pdeps(d)['language'][0].update(tier='maybe'), ['tier']),
    'package_dependencies-tier-int': (lambda d: pdeps(d)['language'][0].update(tier=1), ['tier']),
    'package_metrics-missing': (setter(['dependency_network', 'package_metrics'], DELETE), ['package_metrics']),
    'package_metrics-scheme-not-object': (lambda d: d['dependency_network']['package_metrics'].update(language=[]), ['package_metrics']),
    'package_metrics-package-not-object': (lambda d: d['dependency_network']['package_metrics']['language'].update({'pkg:x': 1}),
                                           ['package_metrics']),
    'instability-string': (lambda d: d['dependency_network']['package_metrics']['language']['pkg:x'].update(instability='0.5'),
                           ['instability']),
    'candidates-not-list': (setter(['candidates'], {}), ['candidates']),
    'candidates-missing': (setter(['candidates'], DELETE), ['candidates']),
    'candidate-not-object': (lambda d: d['candidates'].append(5), ['candidates']),
    'candidate-id-int': (lambda d: d['candidates'][0].update(id=7), ['id']),
    'candidate-kind-missing': (lambda d: d['candidates'][0].pop('kind'), ['kind']),
    'cycle-structure-missing': (on(dep_cycle, 'structure', value=DELETE), ['structure']),
    'cycle-scheme-int': (on(dep_cycle, 'structure', 'scheme', value=4), ['scheme']),
    'cycle-tier-unknown': (on(dep_cycle, 'structure', 'tier', value='some'), ['tier']),
    'cycle-members-string': (on(dep_cycle, 'structure', 'members', value='file:a.py'), ['members']),
    'cycle-members-item-int': (on(dep_cycle, 'structure', 'members', value=[A, 3]), ['members']),
    'cycle-members-missing': (on(dep_cycle, 'structure', 'members', value=DELETE), ['members']),
    'cycle-evidence-not-list': (on(dep_cycle, 'evidence', value={}), ['evidence']),
    'cycle-evidence-item-not-object': (lambda d: dep_cycle(d)['evidence'].append([A, B]), ['evidence']),
    'cycle-evidence-from_id-int': (lambda d: dep_cycle(d)['evidence'][0].update(from_id=1), ['from_id']),
    'cycle-evidence-to_id-missing': (lambda d: dep_cycle(d)['evidence'][0].pop('to_id'), ['to_id']),
    'package_cycle-members-int': (on(pkg_cycle, 'structure', 'members', value=[1, 2]), ['members']),
    'package_cycle-tier-unknown': (on(pkg_cycle, 'structure', 'tier', value='x'), ['tier']),
    'package_cycle-evidence-from_id-missing': (lambda d: pkg_cycle(d)['evidence'][0].pop('from_id'), ['from_id']),
    'violation-rule_type-int': (on(internal_v, 'structure', 'rule_type', value=1), ['rule_type']),
    'violation-from_layer-missing': (on(internal_v, 'structure', 'from_layer', value=DELETE), ['from_layer']),
    'violation-no-target-kind': (on(internal_v, 'structure', 'to_layer', value=DELETE), [('to_layer', 'to_external')]),
    'violation-to_layer-int': (on(internal_v, 'structure', 'to_layer', value=3), ['to_layer']),
    'violation-to_external-int': (on(external_v, 'structure', 'to_external', value=3), ['to_external']),
    'violation-structure-missing': (on(external_v, 'structure', value=DELETE), [('structure', 'rule_type')]),
    'architecture_rules-not-object': (setter(['coverage', 'architecture_rules'], []), ['architecture_rules']),
    'rules_sha256-int': (setter(['coverage', 'architecture_rules', 'rules_sha256'], 5), ['rules_sha256']),
}


def test_V04_the_good_baseline_loads(tmp_path):
    path = write(tmp_path, good())
    assert delta_api().load_baseline(path)['schema'] == 'bottlenecks.v8'
    assert delta_api().load_baseline(str(path))['candidates'][0]['kind'] == 'dependency_cycle'


@pytest.mark.parametrize('name', list(MUTATIONS))
def test_V04_F05_format_violation(tmp_path, name):
    mutate, needles = MUTATIONS[name]
    data = good()
    mutate(data)
    path = write(tmp_path, data)
    with pytest.raises(delta_api().BaselineError) as raised:
        delta_api().load_baseline(path)
    message = str(raised.value)
    assert message.startswith(f'baseline {path}: ')
    for needle in needles:
        assert any(option in message for option in (needle if isinstance(needle, tuple) else (needle,)))


@pytest.mark.parametrize('content', ['[]', '"text"', '5', 'null'])
def test_V04_F05_root_must_be_an_object(tmp_path, content):
    path = write(tmp_path, content)
    with pytest.raises(delta_api().BaselineError) as raised:
        delta_api().load_baseline(path)
    assert str(raised.value).startswith(f'baseline {path}: ')


def test_V04_C16_missing_file(tmp_path):
    path = tmp_path / 'nope.json'
    with pytest.raises(delta_api().BaselineError) as raised:
        delta_api().load_baseline(path)
    assert str(raised.value).startswith(f'baseline {path}: ')


def test_V04_C16_directory(tmp_path):
    with pytest.raises(delta_api().BaselineError) as raised:
        delta_api().load_baseline(tmp_path)
    assert str(raised.value).startswith(f'baseline {tmp_path}: ')


def test_V04_C16_invalid_utf8(tmp_path):
    path = write(tmp_path, b'{"schema": "\xff\xfe"}')
    with pytest.raises(delta_api().BaselineError) as raised:
        delta_api().load_baseline(path)
    assert str(raised.value).startswith(f'baseline {path}: ')


@pytest.mark.parametrize('content', ['', '{"schema": "bottlenecks.v8"', '{"a": tru}', '{} {}'])
def test_V04_C16_invalid_json(tmp_path, content):
    path = write(tmp_path, content)
    with pytest.raises(delta_api().BaselineError) as raised:
        delta_api().load_baseline(path)
    assert str(raised.value).startswith(f'baseline {path}: ')


def test_V04_C16_truncated_real_shape(tmp_path):
    text = json.dumps(good())
    path = write(tmp_path, text[:len(text) // 2])
    with pytest.raises(delta_api().BaselineError):
        delta_api().load_baseline(path)


def test_V04_C16_nesting_depth(tmp_path):
    path = write(tmp_path, '[' * 100000 + ']' * 100000)
    with pytest.raises(delta_api().BaselineError) as raised:
        delta_api().load_baseline(path)
    assert str(raised.value).startswith(f'baseline {path}: ')


def test_V04_C20_previous_delta_is_ignored(tmp_path):
    data = good()
    data['delta'] = {'policy': 'delta.v1', 'new_cycles': 'garbage', 'counts': 5}
    loaded = delta_api().load_baseline(write(tmp_path, data))
    cur = payload(candidates=[cycle([A, B, C])], rules_sha='abc')
    with_delta = run(cur, loaded)
    without = run(cur, good())
    assert with_delta == without


def test_V04_C20_unread_extra_fields_are_ignored(tmp_path):
    data = good()
    data['unrelated'] = [1, {'x': None}]
    data['dependency_network']['whatever'] = 'v'
    data['candidates'][0]['metrics'] = 'not read'
    data['candidates'][-1]['evidence'] = 'not a list'
    data['candidates'][-1]['structure'] = 'not an object'
    data['coverage']['other'] = 1
    data['dependency_network']['package_dependencies']['language'][0]['extra'] = 1
    delta_api().load_baseline(write(tmp_path, data))


def test_V04_C21_candidate_group_id_records_load_and_compare(tmp_path):
    data = good()
    for record in dep_cycle(data)['evidence']:
        record['candidate_group_id'] = 'g:0001'
        record['resolution'] = 'ambiguous'
    loaded = delta_api().load_baseline(write(tmp_path, data))
    cur = payload(candidates=[cycle([A, B, C])], rules_sha='abc')
    result = run(cur, loaded)
    assert [i['added_members'] for i in result['grown_cycles']] == [[C]]


def test_V04_architecture_rules_section_without_digest_loads(tmp_path):
    data = good()
    del data['coverage']['architecture_rules']['rules_sha256']
    delta_api().load_baseline(write(tmp_path, data))


def test_V04_null_instability_loads(tmp_path):
    data = good()
    assert data['dependency_network']['package_metrics']['language']['pkg:n']['instability'] is None
    delta_api().load_baseline(write(tmp_path, data))


# V09 -------------------------------------------------------------------------------------------------------------------

STATES = {
    'new-only': ({'new_cycles': [{'x': 1}]}, True, False),
    'grown-only': ({'grown_cycles': [{'x': 1}]}, True, False),
    'violation-only': ({'new_violations': [{'x': 1}]}, False, True),
    'all-empty': ({}, False, False),
    'package-and-instability-only': ({'new_package_dependencies': [{'x': 1}], 'instability_changes': [{'x': 1}]}, False, False),
}
SUBSETS = [c for n in (1, 2, 3) for c in itertools.combinations(('cycle', 'violation', 'any'), n)]


@pytest.mark.parametrize('state', list(STATES))
@pytest.mark.parametrize('fail_on', SUBSETS, ids=['+'.join(s) for s in SUBSETS])
def test_V09_regressions(fail_on, state):
    lists, hits_cycle, hits_violation = STATES[state]
    delta = make_delta(**lists)
    wanted = set(fail_on)
    if 'any' in wanted:
        wanted |= {'cycle', 'violation'}
    expected = [n for n, hit in (('cycle', hits_cycle), ('violation', hits_violation)) if hit and n in wanted]
    assert delta_api().regressions(delta, fail_on) == expected
    assert ref_regressions(delta, fail_on) == expected


def test_V09_accepts_any_iterable_and_repeats():
    delta = make_delta(new_cycles=[{}], new_violations=[{}])
    assert delta_api().regressions(delta, iter(['violation', 'cycle', 'cycle'])) == ['cycle', 'violation']
    assert delta_api().regressions(delta, []) == []


# V10 -------------------------------------------------------------------------------------------------------------------

def build_report(delta=None):
    from analysis import GraphAnalysisConfig, GraphAnalyzer
    from bottlenecks import analyze_bottlenecks
    from tests.architecture_rules_support import to_rules, weights
    from tests.edge_weights_support import edge
    from tests.file_analysis_support import converted, node
    paths = {'a': 'domain/a.py', 's': 'services/s.py'}
    spec = {'version': 1, 'layers': {'domain': {'paths': ['domain/**']}, 'services': {'paths': ['services/**']}}, 'allow': {'domain': []}}
    files = {path: 'x = 1\n' for path in paths.values()}
    snap, arch = converted(files, [node(k, p) for k, p in paths.items()], [edge('a', 's')])
    w = weights()
    analysis = GraphAnalyzer(GraphAnalysisConfig(edge_weights=w)).analyze(arch.nodes, arch.edges, project_path=arch.project_path)
    arch.stats['analysis'] = copy.deepcopy(analysis)
    report = analyze_bottlenecks(snap, arch, w, analysis=analysis, rules=to_rules(spec))
    return dataclasses.replace(report, delta=delta) if delta is not None else report


def test_V10_F04_delta_key_is_absent_without_baseline_and_present_with_it():
    from bottlenecks import bottlenecks_to_json
    plain = json.loads(bottlenecks_to_json(build_report()))
    assert 'delta' not in plain and plain['schema'] == 'bottlenecks.v8'
    delta = delta_api().compute_delta(plain, plain)
    with_delta = json.loads(bottlenecks_to_json(build_report(delta)))
    assert with_delta['delta'] == wire(delta)
    assert {k: v for k, v in with_delta.items() if k != 'delta'} == plain


def test_V10_F15_validator_accepts_delta_on_v8():
    from bottlenecks import bottlenecks_to_json
    from report.bottlenecks import render_report
    plain = json.loads(bottlenecks_to_json(build_report()))
    with_delta = copy.deepcopy(plain)
    with_delta['delta'] = wire(delta_api().compute_delta(plain, plain))
    assert render_report(plain) and render_report(with_delta)


def test_V10_F15_delta_must_be_an_object_on_v8():
    from bottlenecks import bottlenecks_to_json
    from report.bottlenecks import render_report
    from report.shared.document import ReportInputError
    broken = json.loads(bottlenecks_to_json(build_report()))
    broken['delta'] = []
    with pytest.raises(ReportInputError):
        render_report(broken)


def test_V10_F15_delta_is_still_unknown_on_v6(tmp_path):
    from report.bottlenecks import render_report
    from report.shared.document import ReportInputError
    from tests.test_report_bottlenecks_v3 import v3_payload
    v6 = v3_payload(tmp_path)
    assert v6['schema'] == 'bottlenecks.v6' and render_report(v6)
    v6['delta'] = {}
    with pytest.raises(ReportInputError):
        render_report(v6)


# V05 rules_digest -----------------------------------------------------------------------------------------------------

BASE_RULES = """\
version: 1
layers:
  api:
    paths: ["app/api/**"]
  services:
    paths: ["app/services/**"]
  db:
    paths: ["app/db/**"]
  domain:
    packages: ["pkg:python:app.models.domain"]
external:
  web: ["fastapi*", "starlette*"]
  driver: ["asyncpg*"]
allow:
  domain: ["services"]
forbid:
  - from: db
    to: [api, services]
    to_external: ["group:web"]
  - from: api
    to_external: ["group:driver"]
allow_external:
  domain: ["pydantic*"]
"""


def digest_of(tmp_path, text, name='r.yaml'):
    from analysis.architecture_rules import load_architecture_rules, rules_digest
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return rules_digest(load_architecture_rules(path)), load_architecture_rules(path)


def test_V05_digest_matches_the_independent_definition(tmp_path):
    digest, rules = digest_of(tmp_path, BASE_RULES)
    assert digest == independent_digest(rules)
    assert len(digest) == 64 and digest == digest.lower()


def test_V05_digest_of_hand_built_rules_matches_literal_form():
    from analysis.architecture_rules import ArchitectureRules, LayerSelector, rules_digest
    rules = ArchitectureRules(version=1, layers={'a': LayerSelector(paths=('x/**',), packages=())}, allow={'a': ()}, forbid={},
                              external={'g': ('os*',)}, forbid_external={'a': ('group:g',)}, allow_external={})
    text = ('{"allow":{"a":[]},"allow_external":{},"external":{"g":["os*"]},"forbid":{},"forbid_external":{"a":["group:g"]},'
            '"layers":{"a":{"packages":[],"paths":["x/**"]}},"version":1}')
    assert rules_digest(rules) == hashlib.sha256(text.encode('utf-8')).hexdigest()


def test_V05_C13_key_order_is_irrelevant(tmp_path):
    base, _ = digest_of(tmp_path, BASE_RULES)
    spec = {
        'allow_external': {'domain': ['pydantic*']},
        'forbid': [{'from': 'api', 'to_external': ['group:driver']}, {'from': 'db', 'to_external': ['group:web'], 'to': ['api', 'services']}],
        'allow': {'domain': ['services']},
        'external': {'driver': ['asyncpg*'], 'web': ['fastapi*', 'starlette*']},
        'layers': {'domain': {'packages': ['pkg:python:app.models.domain']}, 'db': {'paths': ['app/db/**']},
                   'services': {'paths': ['app/services/**']}, 'api': {'paths': ['app/api/**']}},
        'version': 1}
    shuffled, _ = digest_of(tmp_path, json.dumps(spec), 'shuffled.yaml')
    assert shuffled == base


def test_V05_C13_comments_are_irrelevant(tmp_path):
    base, _ = digest_of(tmp_path, BASE_RULES)
    commented = '# leading\n' + BASE_RULES.replace('  api:\n', '  api:  # the api layer\n').replace('forbid:\n', '# forbid section\nforbid:\n')
    assert digest_of(tmp_path, commented, 'c.yaml')[0] == base


def test_V05_C13_list_duplicates_are_irrelevant(tmp_path):
    base, _ = digest_of(tmp_path, BASE_RULES)
    duplicated = BASE_RULES.replace('["app/api/**"]', '["app/api/**", "app/api/**"]').replace('[api, services]', '[api, services, api]')
    duplicated = duplicated.replace('["fastapi*", "starlette*"]', '["fastapi*", "starlette*", "fastapi*"]')
    assert digest_of(tmp_path, duplicated, 'd.yaml')[0] == base


def test_V05_C13_forbid_split_by_from_is_irrelevant(tmp_path):
    base, _ = digest_of(tmp_path, BASE_RULES)
    split = BASE_RULES.replace("""  - from: db
    to: [api, services]
    to_external: ["group:web"]
""", """  - from: db
    to: [api]
  - from: db
    to: [services]
  - from: db
    to_external: ["group:web"]
""")
    assert split != BASE_RULES
    assert digest_of(tmp_path, split, 's.yaml')[0] == base


CHANGES = {
    'layers': ('["app/db/**"]', '["app/db/**", "app/extra/**"]'),
    'allow': ('domain: ["services"]', 'domain: ["services", "db"]'),
    'forbid': ('to: [api, services]', 'to: [api]'),
    'external': ('driver: ["asyncpg*"]', 'driver: ["asyncpg*", "psycopg*"]'),
    'forbid_external': ('to_external: ["group:driver"]', 'to_external: ["group:driver", "group:web"]'),
    'allow_external': ('domain: ["pydantic*"]', 'domain: ["pydantic*", "typing"]'),
}


@pytest.mark.parametrize('section', list(CHANGES))
def test_V05_C14_one_semantic_change_per_section_changes_the_digest(tmp_path, section):
    old, new = CHANGES[section]
    assert BASE_RULES.count(old) == 1
    base, _ = digest_of(tmp_path, BASE_RULES)
    changed, rules = digest_of(tmp_path, BASE_RULES.replace(old, new), 'x.yaml')
    assert changed != base
    assert changed == independent_digest(rules)


def test_V05_C14_new_layer_changes_the_digest(tmp_path):
    base, _ = digest_of(tmp_path, BASE_RULES)
    more = BASE_RULES.replace('external:\n', '  cache:\n    paths: ["app/cache/**"]\nexternal:\n', 1)
    assert digest_of(tmp_path, more, 'm.yaml')[0] != base


LAYER_RULES = """\
version: 1
layers:
  api:
    paths: ["app/b/**", "app/a/**", "app/c/**"]
    packages: ["pkg:python:z", "pkg:python:m", "pkg:python:a"]
  db:
    paths: ["app/db/**"]
"""


def test_V05_F03_layer_paths_and_packages_order_and_duplicates_are_irrelevant(tmp_path):
    base, rules = digest_of(tmp_path, LAYER_RULES)
    assert base == independent_digest(rules)
    reordered = LAYER_RULES.replace('["app/b/**", "app/a/**", "app/c/**"]', '["app/c/**", "app/a/**", "app/b/**", "app/a/**"]')
    reordered = reordered.replace('["pkg:python:z", "pkg:python:m", "pkg:python:a"]', '["pkg:python:a", "pkg:python:z", "pkg:python:m", "pkg:python:z"]')
    assert reordered != LAYER_RULES
    changed, rules2 = digest_of(tmp_path, reordered, 'o.yaml')
    assert changed == base == independent_digest(rules2)


@pytest.mark.parametrize('old, new', [('"app/c/**"]', '"app/d/**"]'), ('"pkg:python:a"]', '"pkg:python:b"]')], ids=['paths', 'packages'])
def test_V05_F03_a_changed_layer_element_changes_the_digest(tmp_path, old, new):
    base, _ = digest_of(tmp_path, LAYER_RULES)
    changed, rules = digest_of(tmp_path, LAYER_RULES.replace(old, new), 'c.yaml')
    assert changed != base and changed == independent_digest(rules)
