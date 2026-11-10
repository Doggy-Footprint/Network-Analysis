"""Reference for the general-candidate comparison, written from the spec tables with a different algorithm from the
product on purpose: pairing, membership and de-duplication are nested scans over plain lists; no dict or set indexes
keys, signatures or ids."""
import json

CYCLE_AND_RULE_KINDS = ('dependency_cycle', 'package_cycle', 'rule_violation')
STRENGTH = {
    'large_node': ('line_count', 'token_count'),
    'unresolved_boundary': ('unresolved_count',),
    'evidence_spread': ('file_count', 'directory_count'),
    'dangling_doc_reference': ('dangling_count',),
    'unstable_dependency': ('file_pair_count',),
}
SEVEN_PAIRS = [(kind, metric) for kind, metrics in STRENGTH.items() for metric in metrics]


def gen(kind, target, ident, metrics=None, structure=None, evidence=None):
    item = {'id': ident, 'kind': kind, 'target': target, 'metrics': {} if metrics is None else dict(metrics)}
    if structure is not None:
        item['structure'] = structure
    if evidence is not None:
        item['evidence'] = evidence
    return item


def boundary_evidence(node, names=(), flags=(), line=1):
    return [{'node_id': node, 'unresolved_references': [{'name': n, 'line': line} for n in names], 'flags': list(flags)}]


def doc_evidence(*pairs, line=1):
    return [{'notation': notation, 'text': text, 'line': line} for notation, text in pairs]


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _base_key(item):
    structure = item.get('structure')
    text = '' if structure is None else json.dumps({k: v for k, v in structure.items() if k != 'tier'}, sort_keys=True)
    return (item['kind'], item.get('target'), text)


def _keyed(report):
    items = [c for c in report['candidates'] if c['kind'] not in CYCLE_AND_RULE_KINDS]
    keyed = []
    for item in items:
        same = sum(1 for other in items if _base_key(other) == _base_key(item))
        keyed.append((_base_key(item) + ((item['id'],) if same > 1 else ()), item))
    return keyed


def _find(keyed, key):
    for candidate_key, item in keyed:
        if candidate_key == key:
            return item
    return None


def signatures(item):
    found = []
    evidence = item.get('evidence')
    if item['kind'] == 'unresolved_boundary' and isinstance(evidence, list):
        for element in evidence:
            if not isinstance(element, dict):
                continue
            node = element['node_id'] if isinstance(element.get('node_id'), str) else item['target']
            if isinstance(element.get('unresolved_references'), list):
                for ref in element['unresolved_references']:
                    if isinstance(ref, dict) and isinstance(ref.get('name'), str):
                        found.append(['reference', node, ref['name']])
            if isinstance(element.get('flags'), list):
                found.extend(['flag', node, f] for f in element['flags'] if isinstance(f, str))
            if isinstance(element.get('from_id'), str) and isinstance(element.get('to_id'), str):
                relation = element.get('relation')
                found.append(['edge', element['from_id'], element['to_id'], relation if isinstance(relation, str) else ''])
    if item['kind'] == 'dangling_doc_reference' and isinstance(evidence, list):
        for element in evidence:
            if isinstance(element, dict) and isinstance(element.get('notation'), str) and isinstance(element.get('text'), str):
                found.append(['doc', element['notation'], element['text']])
    unique = []
    for signature in found:
        if signature not in unique:
            unique.append(signature)
    return unique


def ref_general(current, baseline):
    cur, base = _keyed(current), _keyed(baseline)
    new, strengthened = [], []
    for key, item in cur:
        old = _find(base, key)
        if old is None:
            new.append({'candidate_id': item['id'], 'kind': item['kind'], 'target': item.get('target'), 'metrics': item.get('metrics')})
            continue
        increased = {}
        for metric in STRENGTH.get(item['kind'], ()):
            before, now = old.get('metrics', {}).get(metric), item.get('metrics', {}).get(metric)
            if _is_number(before) and _is_number(now) and now > before:
                increased[metric] = {'baseline': before, 'current': now}
        old_signatures = signatures(old)
        added = sorted(s for s in signatures(item) if s not in old_signatures)
        if increased or added:
            strengthened.append({'candidate_id': item['id'], 'baseline_candidate_id': old['id'], 'kind': item['kind'],
                                 'target': item.get('target'), 'increased': increased, 'added_evidence': added})
    order = lambda i: (i['kind'], str(i['target']), i['candidate_id'])
    new.sort(key=order)
    strengthened.sort(key=order)
    resolved = sum(1 for key, _ in base if _find(cur, key) is None)
    return {'new_candidates': new, 'strengthened_candidates': strengthened, 'resolved_candidates': resolved}
