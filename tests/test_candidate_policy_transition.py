import copy

import pytest

from tests.candidate_policy_transition_support import assert_candidate_policy_transition


def transition_node(ident, name=None, path='prod.py', kind='function'):
    return {'id': ident, 'label': name or ident, 'kind': kind, 'flags': ['test'] if path.startswith('tests/') else [], 'span': {'file_path': path, 'start_line': 1, 'end_line': 1 if path.startswith('tests/') else 3}}


def transition_edge(source, target, *, candidates=(), resolution='unique_name', relation='CALLS', weight=1, line=1, path='prod.py'):
    return {'from_id': source, 'to_id': target, 'relation': relation, 'confidence': 'static_inferred', 'resolution': resolution, 'candidates': list(candidates), 'weight': weight, 'evidence': {'file_path': path, 'start_line': line, 'end_line': line}, 'arrows': 'to', 'color': None, 'dashes': False, 'label': '', 'metadata': {}, 'title': None}


def transition_fixture(case):
    if case == 'split':
        nodes = [transition_node('s'), transition_node('a'), transition_node('b'), transition_node('c')]
        old = transition_edge('s', 'a', candidates=['b'], resolution='ambiguous', weight=3)
        before = {'nodes': nodes, 'edges': [old]}
        first = copy.deepcopy(old)
        first['weight'] = 1
        second = transition_edge('s', 'a', candidates=['c'], resolution='ambiguous', weight=2, line=2)
        return before, {'nodes': copy.deepcopy(nodes), 'edges': [first, second]}, {}
    if case == 'self':
        nodes = [transition_node('s', 'same'), transition_node('a', 'same')]
        before = {'nodes': nodes, 'edges': []}
        after = {'nodes': copy.deepcopy(nodes), 'edges': [transition_edge('s', 's', candidates=['a'], resolution='ambiguous')]}
        return before, after, {'prod.py': 'same()\n'}
    nodes = [transition_node('t', 'test_call', 'tests/test_prod.py'), transition_node('a', 'shared'), transition_node('b', 'shared')]
    raw = transition_edge('t', 'a', candidates=['b'], resolution='ambiguous', path='tests/test_prod.py')
    before = {'nodes': nodes, 'edges': [raw] if case == 'propagated-tests' else []}
    tests = transition_edge('t', 'a', candidates=['b'], resolution='ambiguous', relation='TESTS', path='tests/test_prod.py')
    after = {'nodes': copy.deepcopy(nodes), 'edges': copy.deepcopy(before['edges']) + [tests]}
    return before, after, {'tests/test_prod.py': 'shared()\n'}


@pytest.mark.parametrize('case', ['split', 'self', 'propagated-tests', 'textual-tests'])
def test_VO7_transition_accepts_only_explicit_approved_classes(case):
    before, after, contents = transition_fixture(case)
    assert_candidate_policy_transition(before, after, contents)


def test_VO7_textual_singleton_not_misclassified_as_propagated():
    nodes = [transition_node('t', 'test_call', 'tests/test_prod.py'), transition_node('a', 'shared')]
    raw = transition_edge('t', 'a', resolution='ambiguous', path='tests/test_prod.py')
    before = {'nodes': nodes, 'edges': [raw]}
    tests = transition_edge('t', 'a', relation='TESTS', path='tests/test_prod.py')
    after = {'nodes': copy.deepcopy(nodes), 'edges': [copy.deepcopy(raw), tests]}
    assert_candidate_policy_transition(before, after, {'tests/test_prod.py': 'shared()\n'})


def test_VO7_split_preserves_unchanged_same_pair_sibling():
    before, after, contents = transition_fixture('split')
    sibling = transition_edge('s', 'a', resolution='exact', line=3)
    before['edges'].append(copy.deepcopy(sibling))
    after['edges'].append(copy.deepcopy(sibling))
    assert_candidate_policy_transition(before, after, contents)


def test_VO7_split_rejects_removed_same_pair_exact_sibling():
    before, after, contents = transition_fixture('split')
    before['edges'].append(transition_edge('s', 'a', resolution='exact', line=3))
    with pytest.raises(AssertionError):
        assert_candidate_policy_transition(before, after, contents)


def test_VO7_split_restores_ambiguous_group_hidden_by_unique_first_discovery():
    before, after, contents = transition_fixture('split')
    before['edges'][0].update(candidates=[], resolution='unique_name')
    after['edges'][0].update(candidates=[], resolution='unique_name')
    assert_candidate_policy_transition(before, after, contents)


def test_VO7_split_requires_named_frozen_source_alternative():
    before, after, _ = transition_fixture('split')
    contents = {'prod.py': 'b()\nc()\n'}
    assert_candidate_policy_transition(before, after, contents)
    before['nodes'][-1]['label'] = after['nodes'][-1]['label'] = 'unrelated'
    with pytest.raises(AssertionError):
        assert_candidate_policy_transition(before, after, contents)


def test_VO7_self_file_import_retains_same_lookup_name_external_alternatives():
    nodes = [transition_node('s', 'source.kt', kind='file'), transition_node('a', 'imported'), transition_node('b', 'imported')]
    before = {'nodes': nodes, 'edges': []}
    after = {'nodes': copy.deepcopy(nodes), 'edges': [transition_edge('s', 's', candidates=['a', 'b'], resolution='ambiguous', relation='IMPORTS')]}
    contents = {'prod.py': 'import imported\n'}
    assert_candidate_policy_transition(before, after, contents)
    before['nodes'][-1]['label'] = after['nodes'][-1]['label'] = 'unrelated'
    with pytest.raises(AssertionError):
        assert_candidate_policy_transition(before, after, contents)


def test_VO7_self_file_import_still_requires_named_source_evidence():
    nodes = [transition_node('s', 'source.kt', kind='file'), transition_node('a', 'imported')]
    before = {'nodes': nodes, 'edges': []}
    after = {'nodes': copy.deepcopy(nodes), 'edges': [transition_edge('s', 's', candidates=['a'], resolution='ambiguous', relation='IMPORTS')]}
    with pytest.raises(AssertionError):
        assert_candidate_policy_transition(before, after, {'prod.py': 'import wrong_name\n'})


def unique_file_import_fixture():
    nodes = [transition_node('t', 'test_source.kt', 'tests/test_source.kt', kind='file'), transition_node('a', 'production.kt', kind='file')]
    raw = transition_edge('t', 'a', relation='IMPORTS', path='tests/test_source.kt')
    before = {'nodes': nodes, 'edges': [raw]}
    tests = transition_edge('t', 'a', relation='TESTS', path='tests/test_source.kt')
    after = {'nodes': copy.deepcopy(nodes), 'edges': [copy.deepcopy(raw), tests]}
    return before, after


def test_VO7_unique_file_import_propagates_TESTS_with_exact_provenance():
    before, after = unique_file_import_fixture()
    assert_candidate_policy_transition(before, after)


@pytest.mark.parametrize('mismatch', ['resolution', 'confidence'])
def test_VO7_file_import_propagation_rejects_mismatched_resolution_or_confidence(mismatch):
    before, after = unique_file_import_fixture()
    if mismatch == 'resolution':
        after['edges'][-1]['resolution'] = 'exact'
    else:
        before['edges'][0]['confidence'] = after['edges'][0]['confidence'] = 'static_certain'
    with pytest.raises(AssertionError):
        assert_candidate_policy_transition(before, after)


def test_VO7_nonambiguous_propagation_cannot_use_ignored_production_alternative():
    before, after = unique_file_import_fixture()
    source = 't'
    for e in [before['edges'][0], *after['edges']]:
        e['to_id'], e['candidates'] = source, ['a']
    with pytest.raises(AssertionError):
        assert_candidate_policy_transition(before, after)


def test_VO7_file_level_textual_reference_uses_whole_frozen_source_scope():
    before, after, contents = transition_fixture('textual-tests')
    before['nodes'][0]['kind'] = after['nodes'][0]['kind'] = 'file'
    assert_candidate_policy_transition(before, after, contents)


@pytest.mark.parametrize('defect', ['no-name', 'invalid-source-span', 'non-test-source', 'non-code-source'])
def test_VO7_file_level_textual_reference_rejects_invalid_source_evidence(defect):
    before, after, contents = transition_fixture('textual-tests')
    before['nodes'][0]['kind'] = after['nodes'][0]['kind'] = 'file'
    if defect == 'no-name':
        contents['tests/test_prod.py'] = 'unrelated()\n'
    elif defect == 'invalid-source-span':
        before['nodes'][0]['span']['end_line'] = after['nodes'][0]['span']['end_line'] = 10
    elif defect == 'non-test-source':
        before['nodes'][0]['flags'] = after['nodes'][0]['flags'] = []
        before['nodes'][0]['span']['file_path'] = after['nodes'][0]['span']['file_path'] = 'prod.py'
    else:
        before['nodes'][0]['span']['file_path'] = after['nodes'][0]['span']['file_path'] = 'tests/test_prod.json'
        after['edges'][-1]['evidence']['file_path'] = 'tests/test_prod.json'
        contents['tests/test_prod.json'] = contents.pop('tests/test_prod.py')
    with pytest.raises(AssertionError):
        assert_candidate_policy_transition(before, after, contents)


def test_VO7_textual_fallback_still_requires_first_source_occurrence():
    nodes = [transition_node('t', 'test_call', 'tests/test_prod.py'), transition_node('a', 'shared')]
    raw = transition_edge('t', 'a', resolution='ambiguous', path='tests/test_prod.py', line=2)
    before = {'nodes': nodes, 'edges': [raw]}
    tests = transition_edge('t', 'a', relation='TESTS', path='tests/test_prod.py', line=2)
    after = {'nodes': copy.deepcopy(nodes), 'edges': [copy.deepcopy(raw), tests]}
    with pytest.raises(AssertionError):
        assert_candidate_policy_transition(before, after, {'tests/test_prod.py': 'shared()\nshared()\n'})


@pytest.mark.parametrize('defect', ['node-change', 'unrelated-removal', 'unrelated-addition', 'multiplicity', 'split-field-change', 'lost-original-group', 'duplicate-split-group', 'self-unrelated-target', 'self-style-change', 'self-wrong-evidence', 'tests-nontest-source', 'tests-incomplete-group', 'tests-wrong-evidence', 'tests-fabricated-name'])
def test_VO7_transition_rejects_unapproved_changes(defect):
    case = 'self' if defect.startswith('self-') else 'textual-tests' if defect.startswith('tests-') else 'split'
    before, after, contents = transition_fixture(case)
    if defect == 'node-change':
        after['nodes'][0]['label'] = 'mutated'
    elif defect == 'unrelated-removal':
        old = transition_edge('b', 'c')
        before['edges'].append(old)
    elif defect == 'unrelated-addition':
        after['edges'].append(transition_edge('b', 'c'))
    elif defect == 'multiplicity':
        after['edges'][1]['weight'] += 1
    elif defect == 'split-field-change':
        after['edges'][1]['metadata'] = {'invented': True}
    elif defect == 'lost-original-group':
        after['edges'][0]['candidates'] = ['c']
    elif defect == 'duplicate-split-group':
        after['edges'][1]['candidates'] = ['b']
    elif defect == 'self-unrelated-target':
        before['nodes'][1]['label'] = after['nodes'][1]['label'] = 'different'
    elif defect == 'self-style-change':
        after['edges'][0]['color'] = 'red'
    elif defect == 'self-wrong-evidence':
        after['edges'][0]['evidence']['start_line'] = after['edges'][0]['evidence']['end_line'] = 2
    elif defect == 'tests-nontest-source':
        before['nodes'][0]['flags'] = after['nodes'][0]['flags'] = []
        before['nodes'][0]['span']['file_path'] = after['nodes'][0]['span']['file_path'] = 'prod.py'
    elif defect == 'tests-incomplete-group':
        after['edges'][0]['candidates'] = []
        after['edges'][0]['resolution'] = 'unique_name'
    elif defect == 'tests-wrong-evidence':
        after['edges'][0]['evidence']['start_line'] = after['edges'][0]['evidence']['end_line'] = 2
    elif defect == 'tests-fabricated-name':
        contents['tests/test_prod.py'] = 'unrelated()\n'
    with pytest.raises(AssertionError):
        assert_candidate_policy_transition(before, after, contents)
