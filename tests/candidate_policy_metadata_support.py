import copy

from tests.edge_weights_support import DEFAULT_WEIGHTS

POLICY = 'equal-symbol-share.v1'
DEFAULT_TABLES = {key: copy.deepcopy(DEFAULT_WEIGHTS[key]) for key in ('confidence', 'resolution')}
IDENTITY_TABLES = {key: {name: 1.0 for name in table} for key, table in DEFAULT_TABLES.items()}


def without_candidate_policy_metadata(payload, surface, expected_tables=DEFAULT_TABLES):
    result = copy.deepcopy(payload)
    if surface == 'architecture':
        analysis = result['stats']['analysis']
        assert analysis.pop('ambiguity_policy') == POLICY
        assert analysis.pop('edge_weights') == expected_tables
        if result.get('granularity') == 'file':
            for edge in result['edges']:
                assert edge['resolution'] != 'ambiguous', 'ambiguous golden file share requires an explicit independent expectation'
                assert type(edge['metadata']['candidate_share']) in {int, float}
                assert edge['metadata'].pop('candidate_share') == 1
    elif surface == 'bottlenecks':
        assert result['dependency_network'].pop('ambiguity_policy') == POLICY
    else:
        raise AssertionError('unknown characterization surface: ' + surface)
    return result
