import hashlib
import json
import random

import pytest

from analysis.architecture_rules import external_entry_matches
from analysis.structure import analyze_structure
from tests.architecture_rules_support import (EXAMPLE_PROFILE, REPO, assert_candidates_equal, edge_counter, framework_imports,
                                              imported_modules, ref_rule_evaluation, violations_of, weights, write_rules)
from tests.external_rules_support import (ALLOW_EXT, EXAMPLE_EXT_SPEC, EXTERNAL_COVERAGE_KEYS, FORBID_EXT, INTERNAL_COVERAGE_KEYS,
                                          RULE_KIND, assert_external_equal, brief, ext_arch, external_violations, internal_spec,
                                          keys_found, ref_coverage, ref_entry_matches, ref_external_evaluation, ref_normalize, rec,
                                          to_rules_ext)
from tests.test_architecture_rules import BASE, load, mentions, rejected, render

LAYERS_D = 'version: 1\nlayers:\n  d:\n    paths: [d/**]\n  x:\n    paths: [x/**]\n  y:\n    paths: [y/**]\n'
EXT_WEB = 'external:\n  webgrp: [fastapi*]\n'

C14_ROWS = {
    'external-list': (BASE + 'external: [libs]\n', ['external']),
    'external-scalar': (BASE + 'external: libs\n', ['external']),
    'external-empty-mapping': (BASE + 'external: {}\n', ['external']),
    'group-name-1a': (BASE + 'external:\n  1a: [x*]\n', ['1a']),
    'group-value-empty-list': (BASE + 'external:\n  webgrp: []\n', ['webgrp']),
    'group-value-not-a-list': (BASE + 'external:\n  webgrp: fastapi*\n', ['webgrp']),
    'group-pattern-non-string': (BASE + 'external:\n  webgrp: [4242]\n', ['webgrp', '4242']),
    'group-pattern-empty-string': (BASE + 'external:\n  webgrp: [""]\n', ['webgrp']),
    'forbid-from-only': (BASE + 'forbid:\n  - from: alpha\n', ['to_external']),
    'forbid-to-external-empty-list': (BASE + 'forbid:\n  - from: alpha\n    to_external: []\n', ['to_external']),
    'forbid-to-external-string': (BASE + 'forbid:\n  - from: alpha\n    to_external: requests\n', ['to_external']),
    'forbid-to-external-non-string': (BASE + 'forbid:\n  - from: alpha\n    to_external: [1]\n', ['to_external']),
    'forbid-extra-key': (BASE + 'forbid:\n  - from: alpha\n    to_external: [requests]\n    zz_extra: [a]\n', ['zz_extra']),
    'forbid-key-set-without-from': (BASE + 'forbid:\n  - to_external: [requests]\n', ['from']),
    'allow-external-list': (BASE + 'allow_external: [alpha]\n', ['allow_external']),
    'allow-external-undefined-layer': (BASE + 'allow_external:\n  zzz_undefined: [requests]\n', ['zzz_undefined']),
    'allow-external-string-value': (BASE + 'allow_external:\n  alpha: requests\n', ['allow_external', 'alpha']),
    'allow-external-empty-string-entry': (BASE + 'allow_external:\n  alpha: [""]\n', ['allow_external']),
    'allow-external-non-string-entry': (BASE + 'allow_external:\n  alpha: [7]\n', ['allow_external', '7']),
    'to-external-undefined-group': (BASE + EXT_WEB + 'forbid:\n  - from: alpha\n    to_external: ["group:missing"]\n', ['missing']),
    'to-external-group-without-external-section': (BASE + 'forbid:\n  - from: alpha\n    to_external: ["group:missing"]\n', ['missing']),
    'to-external-group-empty-name': (BASE + EXT_WEB + 'forbid:\n  - from: alpha\n    to_external: ["group:"]\n', ['group:']),
    'allow-external-undefined-group': (BASE + EXT_WEB + 'allow_external:\n  alpha: ["group:missing"]\n', ['missing']),
    'allow-external-group-empty-name': (BASE + EXT_WEB + 'allow_external:\n  alpha: ["group:"]\n', ['group:']),
}


@pytest.mark.parametrize('row', sorted(C14_ROWS))
def test_V08_C14_table_row(tmp_path, row):
    text, needles = C14_ROWS[row]
    message = rejected(tmp_path, text)
    assert message.strip() and mentions(message, needles), (row, message)
    assert 'not supported' not in message


def test_V08_2a_not_supported_rejection_is_gone(tmp_path):
    text = BASE + EXT_WEB + 'forbid:\n  - from: alpha\n    to_external: ["group:webgrp", requests]\nallow_external:\n  beta: []\n'
    rules = load(write_rules(tmp_path, text))
    assert dict(rules.external) == {'webgrp': ('fastapi*',)}


C15_TEXT = (LAYERS_D + 'external:\n  orm: [sqlalchemy*]\n'
            'forbid:\n'
            '  - from: d\n    to_external: ["group:orm", fastapi]\n'
            '  - from: d\n    to_external: ["group:orm"]\n'
            '  - from: d\n    to: [x]\n    to_external: [y]\n'
            'allow_external:\n  d: ["pydantic*", "pydantic*"]\n')


def test_V08_C15_loads_with_union_sort_dedup_and_to_plus_to_external(tmp_path):
    rules = load(write_rules(tmp_path, C15_TEXT))
    assert dict(rules.external) == {'orm': ('sqlalchemy*',)}
    assert dict(rules.forbid_external) == {'d': ('fastapi', 'group:orm', 'y')}
    assert dict(rules.allow_external) == {'d': ('pydantic*',)}
    assert dict(rules.forbid)['d'] == ('x',)


def test_V08_group_patterns_sorted_and_deduplicated(tmp_path):
    rules = load(write_rules(tmp_path, BASE + 'external:\n  zed: [b*, a*, b*]\n  abc: [q]\n'))
    assert dict(rules.external) == {'abc': ('q',), 'zed': ('a*', 'b*')}


def test_V08_allow_external_entries_sorted_and_deduplicated(tmp_path):
    rules = load(write_rules(tmp_path, BASE + 'allow_external:\n  beta: [z*, a*, z*]\n  alpha: []\n'))
    assert dict(rules.allow_external) == {'alpha': (), 'beta': ('a*', 'z*')}


def test_V08_merge_same_from_is_union_across_items(tmp_path):
    text = (LAYERS_D + 'forbid:\n  - from: d\n    to_external: [b, a]\n  - from: x\n    to_external: [q]\n'
            '  - from: d\n    to_external: [c, a]\n')
    assert dict(load(write_rules(tmp_path, text)).forbid_external) == {'d': ('a', 'b', 'c'), 'x': ('q',)}


def test_V08_unused_group_is_not_an_error(tmp_path):
    rules = load(write_rules(tmp_path, BASE + 'external:\n  unused: [a*]\n'))
    assert dict(rules.external) == {'unused': ('a*',)} and dict(rules.forbid_external) == {}


def test_V08_to_and_to_external_in_one_item_both_apply(tmp_path):
    text = BASE + 'forbid:\n  - from: alpha\n    to: [beta]\n    to_external: [requests]\n'
    rules = load(write_rules(tmp_path, text))
    assert dict(rules.forbid)['alpha'] == ('beta',) and dict(rules.forbid_external) == {'alpha': ('requests',)}


def test_V08_to_external_only_item_creates_no_internal_forbid_entry(tmp_path):
    rules = load(write_rules(tmp_path, BASE + 'forbid:\n  - from: alpha\n    to_external: [requests]\n'))
    assert dict(rules.forbid) == {}


def test_V08_to_external_only_item_with_undefined_from_layer_is_rejected(tmp_path):
    message = rejected(tmp_path, BASE + 'forbid:\n  - from: zzz_undefined\n    to_external: [requests]\n')
    assert 'zzz_undefined' in message


def test_V08_2a_file_unchanged(tmp_path):
    text = BASE + 'allow:\n  alpha: [beta]\nforbid:\n  - from: beta\n    to: [alpha]\n'
    rules = load(write_rules(tmp_path, text))
    assert dict(rules.external) == {} and dict(rules.forbid_external) == {} and dict(rules.allow_external) == {}
    assert dict(rules.allow) == {'alpha': ('beta',)} and dict(rules.forbid) == {'beta': ('alpha',)}
    assert list(rules.layers) == ['alpha', 'beta'] and rules.version == 1


def test_V08_new_fields_default_to_empty_for_2a_constructor_calls():
    from analysis.architecture_rules import ArchitectureRules
    rules = ArchitectureRules(version=1, layers={}, allow={}, forbid={})
    assert dict(rules.external) == {} and dict(rules.forbid_external) == {} and dict(rules.allow_external) == {}


def test_V08_example_profile_has_the_f15_external_content():
    rules = load(EXAMPLE_PROFILE)
    assert dict(rules.external) == {'db_driver': ('aiosql*', 'alembic*', 'asyncpg*', 'pypika*', 'sqlalchemy*'),
                                    'web': ('fastapi*', 'starlette*')}
    assert dict(rules.forbid_external) == {'api': ('group:db_driver',), 'db': ('group:web',)}
    assert dict(rules.allow_external) == {'domain': ('datetime', 'pydantic*', 'typing')}
    assert dict(rules.forbid)['db'] == ('api',)


@pytest.mark.parametrize('where', ['external-value', 'to-external', 'allow-external'])
def test_V08_Q08_python_object_tag_is_rejected_without_side_effect(tmp_path, where):
    sentinel = tmp_path / 'sentinel.txt'
    payload = f'!!python/object/apply:os.system ["touch {sentinel}"]'
    text = {
        'external-value': BASE + f'external:\n  g: [{payload}]\n',
        'to-external': BASE + f'forbid:\n  - from: alpha\n    to_external: [{payload}]\n',
        'allow-external': BASE + f'allow_external:\n  alpha: {payload}\n',
    }[where]
    rejected(tmp_path, text)
    assert not sentinel.exists()


def rules_of(entry, groups=None):
    return to_rules_ext({'layers': {'d': {'paths': ['d/**']}}, 'external': groups or {}, 'forbid': [{'from': 'd', 'to_external': [entry]}]})


@pytest.mark.parametrize('entry,groups,name,expected', [
    ('sqlalchemy*', {}, 'sqlalchemy.orm', True), ('sqlalchemy', {}, 'sqlalchemy.orm', False), ('Fast*', {}, 'fastapi', False),
    ('a?c', {}, 'abc', True), ('[ab]x', {}, 'bx', True), ('@nestjs/*', {}, '@nestjs/common', True),
    ('group:web', {'web': ['fastapi*', 'starlette*']}, 'starlette.requests', True),
    ('group:web', {'web': ['fastapi*', 'starlette*']}, 'fastapi', True),
    ('group:web', {'web': ['fastapi*', 'starlette*']}, 'django', False),
    ('fastapi', {'fastapi': ['starlette*']}, 'fastapi', True), ('fastapi', {'fastapi': ['starlette*']}, 'starlette.x', False),
    ('group:fastapi', {'fastapi': ['starlette*']}, 'starlette.x', True),
    ('group:fastapi', {'fastapi': ['starlette*']}, 'fastapi', False),
    ('web', {'web': ['fastapi*']}, 'fastapi.x', False), ('web', {'web': ['fastapi*']}, 'web', True),
], ids=lambda value: str(value)[:24] if not isinstance(value, dict) else 'g')
def test_V09_F09_entry_matching(entry, groups, name, expected):
    assert external_entry_matches(rules_of(entry, groups), entry, name) is expected
    assert ref_entry_matches(groups, entry, name) is expected


SPEC_D = {'version': 1, 'layers': {'d': {'paths': ['d/**']}, 'o': {'paths': ['o/**']}},
          'external': {'orm': ['sqlalchemy*']},
          'forbid': [{'from': 'd', 'to_external': ['group:orm', 'fastapi']}],
          'allow_external': {'d': ['pydantic*']}}
F = 'file:d/f.py'
C16_FILES = {'d/f.py': [rec('fastapi', 1), rec('os', 2), rec('pydantic', 3), rec('sqlalchemy.orm', 4)]}


def evaluate(spec, files, boundary=None, edges=()):
    arch = ext_arch(files, boundary, edges)
    result = analyze_structure(arch, weights(), to_rules_ext(spec))
    expected, _ = ref_external_evaluation(spec, arch)
    actual = external_violations(result.candidates)
    assert_external_equal(actual, expected)
    return result, actual, arch


def test_V09_C16_decision_table_hand_expected():
    _, actual, _ = evaluate(SPEC_D, C16_FILES)
    assert brief(actual) == [(ALLOW_EXT, 'd', F, 'fastapi'), (ALLOW_EXT, 'd', F, 'os'), (ALLOW_EXT, 'd', F, 'sqlalchemy.orm'),
                             (FORBID_EXT, 'd', F, 'fastapi'), (FORBID_EXT, 'd', F, 'sqlalchemy.orm')]
    matched = {(c['structure']['rule_type'], c['structure']['to_external']): c['structure']['matched'] for c in actual}
    assert matched[(FORBID_EXT, 'sqlalchemy.orm')] == ['group:orm'] and matched[(FORBID_EXT, 'fastapi')] == ['fastapi']
    assert all(matched[key] == [] for key in matched if key[0] == ALLOW_EXT)


def spec_for(forbid=None, allow=None, groups=None):
    spec = {'version': 1, 'layers': {'d': {'paths': ['d/**']}}, 'external': groups or {}, 'forbid': [], 'allow_external': {}}
    if forbid is not None:
        spec['forbid'] = [{'from': 'd', 'to_external': forbid}]
    if allow is not None:
        spec['allow_external'] = {'d': allow}
    return spec


TABLE = [
    ('forbid-match-allow-absent', spec_for(forbid=['fastapi']), 'fastapi', [FORBID_EXT]),
    ('forbid-match-allow-match', spec_for(forbid=['fastapi'], allow=['fastapi*']), 'fastapi', [FORBID_EXT]),
    ('forbid-match-allow-no-match', spec_for(forbid=['fastapi'], allow=['pydantic*']), 'fastapi', [ALLOW_EXT, FORBID_EXT]),
    ('no-forbid-match-allow-no-match', spec_for(forbid=['fastapi'], allow=['pydantic*']), 'os', [ALLOW_EXT]),
    ('no-forbid-match-allow-match', spec_for(forbid=['fastapi'], allow=['pydantic*']), 'pydantic.v1', []),
    ('no-forbid-no-allow-key', spec_for(forbid=['fastapi']), 'os', []),
    ('allow-only-no-forbid', spec_for(allow=['pydantic*']), 'os', [ALLOW_EXT]),
]


@pytest.mark.parametrize('spec,name,rule_types', [row[1:] for row in TABLE], ids=[row[0] for row in TABLE])
def test_V09_F10_decision_table(spec, name, rule_types):
    _, actual, _ = evaluate(spec, {'d/f.py': [rec(name, 1)]})
    assert sorted(c['structure']['rule_type'] for c in actual) == rule_types


def test_V09_C17_group_prefix_versus_literal():
    spec = {'version': 1, 'layers': {'a': {'paths': ['a/**']}, 'b': {'paths': ['b/**']}}, 'external': {'fastapi': ['starlette*']},
            'forbid': [{'from': 'a', 'to_external': ['fastapi']}, {'from': 'b', 'to_external': ['group:fastapi']}]}
    records = [rec('fastapi', 1), rec('starlette.x', 2)]
    _, actual, _ = evaluate(spec, {'a/f.py': records, 'b/f.py': records})
    assert brief(actual) == [(FORBID_EXT, 'a', 'file:a/f.py', 'fastapi'), (FORBID_EXT, 'b', 'file:b/f.py', 'starlette.x')]
    assert [c['structure']['matched'] for c in actual if c['structure']['from_layer'] == 'b'] == [['group:fastapi']]


def test_V09_matched_lists_every_matching_entry_sorted():
    spec = spec_for(forbid=['sqlalchemy.orm', 'group:orm', 'sql*', 'django'], groups={'orm': ['sqlalchemy*']})
    _, actual, _ = evaluate(spec, {'d/f.py': [rec('sqlalchemy.orm', 1)]})
    assert [c['structure']['matched'] for c in actual] == [['group:orm', 'sql*', 'sqlalchemy.orm']]


def test_V09_C18_unassigned_file_has_no_violation():
    spec = {**SPEC_D, 'allow_external': {'d': []}}
    _, actual, _ = evaluate(spec, {'q/f.py': [rec('fastapi', 1), rec('os', 2)], 'd/g.py': None})
    assert actual == []


def test_V09_C18_layer_not_in_allow_external_has_no_allow_violation():
    spec = {**SPEC_D, 'forbid': [], 'allow_external': {'d': ['pydantic*']}}
    _, actual, _ = evaluate(spec, {'o/f.py': [rec('os', 1), rec('fastapi', 2)], 'd/f.py': [rec('pydantic', 1)]})
    assert actual == []


def test_V09_C18_files_without_imports_have_no_violation():
    spec = {**SPEC_D, 'allow_external': {'d': []}}
    _, actual, _ = evaluate(spec, {'d/a.py': None, 'd/b.py': None})
    assert actual == []


def test_V09_C19_static_plus_dynamic_is_one_certain_candidate():
    records = [rec('fastapi', 3), rec('fastapi', 9, dynamic=True)]
    _, actual, _ = evaluate(spec_for(forbid=['fastapi']), {'d/f.py': records})
    assert len(actual) == 1
    item = actual[0]
    assert item['metrics'] == {'evidence_count': 2} and item['evidence'] == records and item['structure']['tier'] == 'certain'


def test_V09_C19_dynamic_only_is_resolved():
    records = [rec('fastapi', 9, dynamic=True)]
    _, actual, _ = evaluate(spec_for(forbid=['fastapi']), {'d/f.py': records})
    assert len(actual) == 1 and actual[0]['structure']['tier'] == 'resolved' and actual[0]['metrics'] == {'evidence_count': 1}


def test_V09_evidence_counts_records_with_the_same_name_not_the_same_specifier():
    records = [rec('typeorm', 1, 'typeorm/a'), rec('typeorm', 2, 'typeorm/b'), rec('typeorm', 3, 'typeorm/b', dynamic=True), rec('zz', 1)]
    _, actual, _ = evaluate(spec_for(forbid=['typeorm']), {'d/f.py': records})
    assert len(actual) == 1 and actual[0]['metrics'] == {'evidence_count': 3} and actual[0]['evidence'] == records[:3]


def test_V09_candidate_fields_hand_expected():
    records = [rec('fastapi', 4), rec('fastapi', 8, dynamic=True)]
    result, actual, _ = evaluate(spec_for(forbid=['fastapi', 'f*']), {'d/f.py': records})
    item = actual[0]
    digest = hashlib.sha256('rule|forbid_external|d|file:d/f.py|fastapi'.encode()).hexdigest()[:16]
    assert item == {'id': 'b:' + digest, 'kind': RULE_KIND, 'target': 'file:d/f.py', 'metrics': {'evidence_count': 2},
                    'evidence': records, 'coverage': 'static_analyzer_relation', 'status': 'static_candidate',
                    'structure': {'rule_type': 'forbid_external', 'from_layer': 'd', 'to_external': 'fastapi',
                                  'matched': ['f*', 'fastapi'], 'tier': 'certain', 'relations': ['IMPORTS']}}
    keys = [(c['kind'], c['id']) for c in result.candidates]
    assert keys == sorted(keys)


def test_V09_allow_candidate_identifier_and_matched_empty():
    result, actual, _ = evaluate(spec_for(allow=['pydantic*']), {'d/f.py': [rec('os', 5)]})
    digest = hashlib.sha256('rule|allow_external|d|file:d/f.py|os'.encode()).hexdigest()[:16]
    assert [c['id'] for c in actual] == ['b:' + digest]
    assert actual[0]['structure']['matched'] == [] and actual[0]['structure']['rule_type'] == 'allow_external'


def test_V09_boundary_nodes_are_not_evaluated():
    spec = spec_for(forbid=['fastapi'], allow=[])
    _, actual, _ = evaluate(spec, {'d/f.py': None}, boundary={'d/ext.py': [rec('fastapi', 1)]})
    assert actual == []


def test_V09_external_rules_leave_internal_candidates_unchanged():
    make = edge_counter()
    spec = {'version': 1, 'layers': {'a': {'paths': ['a/**']}, 'b': {'paths': ['b/**']}}, 'allow': {'a': []},
            'forbid': [{'from': 'b', 'to': ['a'], 'to_external': ['fastapi']}], 'allow_external': {'a': []}}
    edges = [make('a/x.py', 'b/y.py'), make('b/y.py', 'a/x.py')]
    files = {'a/x.py': [rec('fastapi', 1)], 'b/y.py': [rec('fastapi', 2), rec('os', 3)]}
    result, actual, arch = evaluate(spec, files, edges=edges)
    only_internal = analyze_structure(arch, weights(), to_rules_ext(internal_spec(spec)))
    _, expected_internal, _ = ref_rule_evaluation(internal_spec(spec), arch, weights())
    assert_candidates_equal(violations_of([c for c in result.candidates if c['structure'].get('rule_type') in ('allow', 'forbid')]),
                            expected_internal)
    assert [c for c in result.candidates if c['kind'] != RULE_KIND] == [c for c in only_internal.candidates if c['kind'] != RULE_KIND]
    assert brief(actual) == [(ALLOW_EXT, 'a', 'file:a/x.py', 'fastapi'), (FORBID_EXT, 'b', 'file:b/y.py', 'fastapi')]


def random_case(seed):
    rnd = random.Random(seed)
    pool = ['fastapi', 'fastapi.routing', 'starlette.x', 'sqlalchemy.orm', 'os', 'pydantic', 'typing', '@nestjs/common', 'lodash']
    entries = ['fastapi', 'fastapi*', 'group:web', 'group:orm', 'sql*', 'os', 'typing', 'pydantic*', '@nestjs/*', 'lod?sh', 'group:web']
    layers = {name: {'paths': [f'{name}/**']} for name in ('a', 'b', 'c')}
    spec = {'version': 1, 'layers': layers, 'external': {'web': ['fastapi*', 'starlette*'], 'orm': ['sqlalchemy*']},
            'forbid': [{'from': n, 'to_external': rnd.sample(entries, rnd.randint(1, 4))} for n in ('a', 'b') if rnd.random() < .8],
            'allow_external': {n: rnd.sample(entries, rnd.randint(0, 3)) for n in ('b', 'c') if rnd.random() < .7}}
    files = {}
    for index in range(rnd.randint(2, 8)):
        directory = rnd.choice(['a', 'b', 'c', 'zz'])
        records = [rec(rnd.choice(pool), rnd.randint(1, 5), rnd.choice([None, None, 'x/y']), rnd.random() < .3)
                   for _ in range(rnd.randint(0, 6))]
        files[f'{directory}/f{index}.py'] = ref_normalize(records) or None
    return spec, files


@pytest.mark.parametrize('seed', range(40))
def test_V09_random_cases_match_brute_force_reference(seed):
    spec, files = random_case(seed)
    result, actual, arch = evaluate(spec, files)
    assert result.coverage['architecture_rules'] == ref_coverage(spec, arch, weights())


def test_V09_random_family_is_not_vacuous():
    kinds, tiers = set(), set()
    for seed in range(40):
        spec, files = random_case(seed)
        expected, _ = ref_external_evaluation(spec, ext_arch(files))
        kinds |= {c['structure']['rule_type'] for c in expected}
        tiers |= {c['structure']['tier'] for c in expected}
    assert kinds == {FORBID_EXT, ALLOW_EXT} and tiers == {'certain', 'resolved'}


def coverage_of(spec, files, edges=()):
    arch = ext_arch(files, edges=edges)
    return analyze_structure(arch, weights(), to_rules_ext(spec)).coverage['architecture_rules'], arch


def test_V10_with_external_rules_adds_exactly_two_keys():
    coverage, _ = coverage_of(SPEC_D, C16_FILES)
    assert set(coverage) == INTERNAL_COVERAGE_KEYS | EXTERNAL_COVERAGE_KEYS


def test_V10_counts_records_of_non_boundary_files_and_candidates():
    spec = spec_for(forbid=['fastapi'], allow=['pydantic*'])
    files = {'d/a.py': [rec('fastapi', 1), rec('fastapi', 2), rec('os', 3)], 'd/b.py': None, 'q/c.py': [rec('os', 1)]}
    arch = ext_arch(files, boundary={'d/ext.py': [rec('fastapi', 1), rec('os', 2)]})
    coverage = analyze_structure(arch, weights(), to_rules_ext(spec)).coverage['architecture_rules']
    assert coverage['external_import_count'] == 4
    assert coverage['external_violation_count'] == 3
    assert coverage['violation_count'] == 3


def test_V10_total_violation_count_adds_internal_and_external():
    make = edge_counter()
    spec = {'version': 1, 'layers': {'a': {'paths': ['a/**']}, 'b': {'paths': ['b/**']}}, 'allow': {'a': []},
            'forbid': [{'from': 'b', 'to': ['a']}], 'allow_external': {'b': []}}
    files = {'a/x.py': None, 'b/y.py': [rec('os', 1), rec('sys', 2)]}
    coverage, arch = coverage_of(spec, files, edges=[make('a/x.py', 'b/y.py'), make('b/y.py', 'a/x.py')])
    assert coverage['violation_count'] == 4 and coverage['external_violation_count'] == 2 and coverage['external_import_count'] == 2
    assert coverage == ref_coverage(spec, arch, weights())


def test_V10_without_external_rules_same_keys_as_2a_even_when_files_have_imports():
    spec = {'version': 1, 'layers': {'a': {'paths': ['a/**']}}, 'external': {'web': ['fastapi*']}, 'allow': {'a': []}}
    coverage, _ = coverage_of(spec, {'a/x.py': [rec('fastapi', 1)]})
    assert set(coverage) == INTERNAL_COVERAGE_KEYS


def test_V10_empty_allow_external_mapping_declares_no_external_rules(tmp_path):
    rules = load(write_rules(tmp_path, BASE + 'allow_external: {}\n'))
    assert dict(rules.allow_external) == {}
    spec = {'version': 1, 'layers': {'a': {'paths': ['a/**']}}, 'allow_external': {}}
    coverage, _ = coverage_of(spec, {'a/x.py': [rec('os', 1)]})
    assert set(coverage) == INTERNAL_COVERAGE_KEYS


def test_V10_external_rules_are_detected_from_allow_external_alone():
    spec = {'version': 1, 'layers': {'a': {'paths': ['a/**']}}, 'allow_external': {'a': []}}
    coverage, _ = coverage_of(spec, {'a/x.py': [rec('os', 1)]})
    assert set(coverage) == INTERNAL_COVERAGE_KEYS | EXTERNAL_COVERAGE_KEYS and coverage['external_violation_count'] == 1


def test_V10_external_rules_are_detected_from_forbid_external_alone():
    coverage, _ = coverage_of(spec_for(forbid=['zzz']), {'d/x.py': [rec('os', 1)]})
    assert set(coverage) == INTERNAL_COVERAGE_KEYS | EXTERNAL_COVERAGE_KEYS
    assert coverage['external_import_count'] == 1 and coverage['external_violation_count'] == 0


def test_V16_group_name_without_prefix_expanded():
    spec = spec_for(forbid=['web'], groups={'web': ['fastapi*']})
    _, actual, _ = evaluate(spec, {'d/f.py': [rec('fastapi.x', 1), rec('web', 2)]})
    assert brief(actual) == [(FORBID_EXT, 'd', 'file:d/f.py', 'web')]


@pytest.mark.parametrize('field', ['to_external', 'allow_external'])
def test_V16_undefined_group_accepted(tmp_path, field):
    entry = '["group:missing"]'
    body = (f'forbid:\n  - from: alpha\n    to_external: {entry}\n' if field == 'to_external'
            else f'allow_external:\n  alpha: {entry}\n')
    message = rejected(tmp_path, BASE + EXT_WEB + body)
    assert 'missing' in message


def test_V16_empty_allow_external_list_flags_every_name():
    spec = spec_for(allow=[])
    _, actual, _ = evaluate(spec, {'d/f.py': [rec('os', 1), rec('typing', 2), rec('x.y', 3)]})
    assert brief(actual) == [(ALLOW_EXT, 'd', 'file:d/f.py', n) for n in ('os', 'typing', 'x.y')]


def test_V16_coverage_keys_leak_without_external_rules():
    spec = {'version': 1, 'layers': {'a': {'paths': ['a/**']}}, 'allow': {'a': []}, 'forbid': []}
    coverage, _ = coverage_of(spec, {'a/x.py': [rec('os', 1)]})
    assert EXTERNAL_COVERAGE_KEYS.isdisjoint(coverage)


def projection(nodes, edges=(), files=None):
    from tests.file_analysis_support import converted, serialize
    snap, arch = converted(files or {'a.py': 'x = 1\n', 'b.py': 'y = 1\n'}, nodes, list(edges))
    return arch, serialize(arch)


def metadata_of(arch, ident):
    return next(n.metadata for n in arch.nodes if n.id == ident)


def test_V07_C13_union_of_two_nodes_projected_to_one_file():
    from tests.file_analysis_support import node
    first = node('m', 'a.py', kind='module', metadata={'external_imports': [rec('os', 1), rec('fastapi', 2)]})
    second = node('f', 'a.py', metadata={'external_imports': [rec('fastapi', 2), rec('zz', 5), rec('os', 1, 'os/path')]})
    second.provenance = 'fastapi'
    arch, _ = projection([first, second, node('n', 'b.py')])
    expected = ref_normalize([rec('os', 1), rec('fastapi', 2), rec('zz', 5), rec('os', 1, 'os/path')])
    assert metadata_of(arch, 'file:a.py')['external_imports'] == expected


def test_V07_no_records_no_key():
    from tests.file_analysis_support import node
    arch, serialized = projection([node('m', 'a.py', metadata={'external_imports': [rec('os', 1)]}), node('n', 'b.py')])
    assert 'external_imports' in metadata_of(arch, 'file:a.py')
    assert 'external_imports' not in metadata_of(arch, 'file:b.py')
    assert all('external_imports' not in n['metadata'] for n in serialized['nodes'] if n['id'] == 'file:b.py')


def test_V07_details_keep_the_key_boundary_copies_do_not():
    from tests.edge_weights_support import edge
    from tests.file_analysis_support import node
    nodes = [node('m', 'a.py', metadata={'external_imports': [rec('os', 1)]}), node('n', 'b.py'),
             node('ext', None, kind='external', metadata={'external_imports': [rec('boundaryonly', 1)]})]
    arch, serialized = projection(nodes, [edge('m', 'n'), edge('m', 'ext')])
    boundary = [n for n in serialized['nodes'] if n['metadata'].get('boundary')]
    assert boundary, 'the scenario must contain a boundary node'
    assert {n['id'] for n in serialized['details']['nodes']} >= {'m', 'n'}
    index = [n['id'] for n in serialized['nodes']].index('file:a.py')
    detail = [n['id'] for n in serialized['details']['nodes']].index('m')
    assert sorted(keys_found(serialized, 'external_imports')) == sorted([
        ('details', 'nodes', detail, 'metadata', 'external_imports'), ('nodes', index, 'metadata', 'external_imports'),
        ('details', 'nodes', [n['id'] for n in serialized['details']['nodes']].index('ext'), 'metadata', 'external_imports')])
    assert serialized['details']['nodes'][detail]['metadata']['external_imports'] == [rec('os', 1)]


def test_V07_analyzer_nodes_keep_their_own_key_after_projection():
    from tests.file_analysis_support import node
    first = node('m', 'a.py', metadata={'external_imports': [rec('os', 1)]})
    projection([first, node('n', 'b.py')])
    assert first.metadata['external_imports'] == [rec('os', 1)]


def test_V13_validator_accepts_external_violations_and_renders():
    from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
    from tests.file_analysis_support import converted, node
    files = {'db/d.py': 'x = 1\n', 'domain/m.py': 'y = 1\n'}
    nodes = [node('d', 'db/d.py', metadata={'external_imports': [rec('fastapi', 1), rec('typing', 2)]}),
             node('m', 'domain/m.py', metadata={'external_imports': [rec('os', 3)]})]
    snap, arch = converted(files, nodes, [])
    spec = {'version': 1, 'layers': {'db': {'paths': ['db/**']}, 'domain': {'paths': ['domain/**']}}, 'external': {'web': ['fastapi*']},
            'forbid': [{'from': 'db', 'to_external': ['group:web']}], 'allow_external': {'domain': ['typing']}}
    payload = json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, weights(), rules=to_rules_ext(spec))))
    assert payload['schema'] == 'bottlenecks.v8'
    assert brief(external_violations(payload['candidates'])) == [
        (ALLOW_EXT, 'domain', 'file:domain/m.py', 'os'), (FORBID_EXT, 'db', 'file:db/d.py', 'fastapi')]
    coverage = payload['coverage']['architecture_rules']
    assert coverage['external_import_count'] == 3 and coverage['external_violation_count'] == 2 and coverage['violation_count'] == 2
    assert keys_found(payload, 'external_imports') == []
    for text in render(payload):
        assert '<html' in text.lower() and '경계 규칙 위반' in text


ARCH_RULES = REPO / 'analysis' / 'architecture_rules.py'
EXTERNAL_HELPER = REPO / 'language_analyzers' / 'core' / 'external_imports.py'
HELPER_FORBIDDEN_LANGUAGES = ('python', 'typescript', 'kotlin')


def helper_violations(modules):
    bad = []
    for module in modules:
        parts = module.split('.')
        if parts[0] in ('framework_analyzers', 'analysis'):
            bad.append(module)
        elif parts[0] == 'language_analyzers' and len(parts) > 1 and parts[1] in HELPER_FORBIDDEN_LANGUAGES:
            bad.append(module)
    return bad


def rules_violations(modules):
    return [m for m in modules if m.split('.')[0] in ('language_analyzers', 'framework_analyzers')]


@pytest.mark.parametrize('source,rules_bad,helper_bad', [
    ('import language_analyzers.core.graph_models', True, False), ('from language_analyzers.python import X', True, True),
    ('def f():\n    import framework_analyzers.nestjs', True, True), ('from analysis import structure', False, True),
    ('import importlib\nimportlib.import_module("language_analyzers.kotlin")', True, True),
    ('import fnmatch, re, json', False, False),
], ids=['core-import', 'python-import', 'nested-framework-import', 'analysis-import', 'dynamic-kotlin-import', 'clean'])
def test_V15_checker_detects_forbidden_forms(source, rules_bad, helper_bad):
    modules = imported_modules(source, package='language_analyzers.core')
    assert bool(rules_violations(modules)) is rules_bad
    assert bool(helper_violations(modules)) is helper_bad


def test_V15_rules_module_imports():
    modules = imported_modules(ARCH_RULES.read_text(encoding='utf-8'))
    assert modules and rules_violations(modules) == [] and framework_imports(modules) == []


def test_V15_core_helper_imports():
    modules = imported_modules(EXTERNAL_HELPER.read_text(encoding='utf-8'), package='language_analyzers.core')
    assert modules and helper_violations(modules) == []


def test_V09_example_profile_spec_matches_loader_content():
    rules, expected = load(EXAMPLE_PROFILE), to_rules_ext(EXAMPLE_EXT_SPEC)
    assert dict(rules.external) == dict(expected.external)
    assert dict(rules.forbid_external) == dict(expected.forbid_external)
    assert dict(rules.allow_external) == dict(expected.allow_external)
