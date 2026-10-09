import copy
import json


def recovered_candidate_evidence(report):
    result = copy.deepcopy(report)
    registry = result['dependency_network'].pop('candidate_groups', None)
    if registry is not None:
        assert isinstance(registry, dict) and registry, 'empty registry must be omitted'
        fingerprints = []
        for ident, group in registry.items():
            assert isinstance(ident, str) and ident
            assert isinstance(group, dict) and set(group) == {'to_id', 'candidates'}
            assert isinstance(group['to_id'], str)
            assert isinstance(group['candidates'], list) and all(isinstance(value, str) for value in group['candidates'])
            fingerprints.append(json.dumps(group, sort_keys=True))
        assert len(fingerprints) == len(set(fingerprints)), 'identical original group was interned multiple times'
    ambiguous_count = 0
    for candidate in result['candidates']:
        evidence = candidate.get('evidence')
        records = evidence if isinstance(evidence, list) else [evidence]
        for record in records:
            if not isinstance(record, dict):
                continue
            if record.get('resolution') == 'ambiguous':
                ambiguous_count += 1
                assert 'candidates' not in record, 'ambiguous evidence repeated candidate list'
                ident = record.pop('candidate_group_id')
                assert registry is not None and ident in registry, 'ambiguous evidence has no registry entry'
                group = registry[ident]
                assert record['to_id'] == group['to_id'], 'reference changed original representative'
                record['candidates'] = copy.deepcopy(group['candidates'])
            else:
                assert 'candidate_group_id' not in record, 'nonambiguous evidence wire shape changed'
    assert ambiguous_count or registry is None, 'registry present without ambiguous evidence'
    return result
