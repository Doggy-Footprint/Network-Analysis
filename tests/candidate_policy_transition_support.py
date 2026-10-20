import json
import math
import re
from collections import Counter, defaultdict


def _record(edge):
    return json.dumps(edge, sort_keys=True, ensure_ascii=False)


def _group(edge):
    return frozenset([edge['to_id'], *edge.get('candidates', [])])


def _exact_piece(edge):
    return edge['resolution'] == 'exact' and edge['confidence'] == 'static_certain' and not edge.get('candidates')


def _test_node(node):
    path = (node.get('span') or {}).get('file_path', '').replace('\\', '/')
    pieces = path.lower().split('/')
    filename = pieces[-1]
    return 'test' in node.get('flags', []) or any(p in {'test', 'tests', 'androidtest'} for p in pieces[:-1]) or filename.startswith('test_') or filename.endswith(('_test.py', '_test.kt', '_test.ts', 'test.kt', 'test.java'))


def _first_name_line(node, name, contents):
    span = node.get('span') or {}
    path = span.get('file_path')
    assert path in contents and path.endswith(('.py', '.pyi', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.kt', '.kts')), 'textual TESTS needs frozen code-source span'
    expression = re.compile(r'(?<!\w)' + re.escape(name) + r'(?!\w)')
    lines = contents[path].split('\n')
    assert type(span.get('start_line')) is int and type(span.get('end_line')) is int
    assert 1 <= span['start_line'] <= span['end_line'] <= len(lines), 'textual TESTS source span outside frozen input'
    for line in range(span['start_line'], span['end_line'] + 1):
        if expression.search(lines[line - 1]):
            return line
    return None


def assert_candidate_policy_transition(baseline, optimized, snapshot_contents=None):
    assert baseline['nodes'] == optimized['nodes'], 'candidate policy changed raw nodes'
    assert set(baseline) == set(optimized), 'candidate policy changed raw top-level fields'
    for key in baseline.keys() - {'nodes', 'edges'}:
        assert baseline[key] == optimized[key]
    nodes = {n['id']: n for n in baseline['nodes']}
    contents = dict(snapshot_contents or ())
    old = Counter(map(_record, baseline['edges']))
    new = Counter(map(_record, optimized['edges']))
    removed = [json.loads(record) for record, count in (old - new).items() for _ in range(count)]
    added = [json.loads(record) for record, count in (new - old).items() for _ in range(count)]
    split_keys = {(e['from_id'], e['to_id'], e['relation']) for e in removed}
    for key in split_keys:
        before = [e for e in removed if (e['from_id'], e['to_id'], e['relation']) == key]
        after = [e for e in added if (e['from_id'], e['to_id'], e['relation']) == key]
        assert len(before) == 1, 'unrelated edge removed'
        original = before[0]
        exact_original = original['resolution'] == 'exact' and original['confidence'] == 'static_certain' and not original.get('candidates')
        assert original['resolution'] in {'ambiguous', 'unique_name'} or exact_original, 'unrelated edge removed'
        assert len(after) > 1, 'removed relation has no distinct-group split'
        if not exact_original:
            assert any(e['resolution'] == 'ambiguous' for e in after), 'split has no ambiguous candidate group'
        exact_pieces = [e for e in after if _exact_piece(e)]
        assert len(exact_pieces) <= 1, 'split has several exact pieces'
        assert len({_group(e) for e in after}) == len(after), 'split duplicated a candidate group'
        assert math.fsum(e['weight'] for e in after) == original['weight'], 'split changed discovery multiplicity'
        ignored = {'weight', 'candidates', 'resolution', 'evidence'}
        stable = {k: v for k, v in original.items() if k not in ignored}
        retained_exact = [e for e in after if exact_original and _group(e) == _group(original)]
        if exact_original:
            assert len(retained_exact) == 1, 'split lost original group/evidence'
            kept = retained_exact[0]
            assert {k: v for k, v in kept.items() if k != 'weight'} == {k: v for k, v in original.items() if k != 'weight'}, 'split changed unrelated edge fields'
        for e in after:
            is_exact_piece = bool(exact_pieces) and e is exact_pieces[0]
            relaxed = ignored | ({'confidence'} if exact_original or is_exact_piece else set())
            assert {k: v for k, v in e.items() if k not in relaxed} == {k: v for k, v in original.items() if k not in relaxed}, 'split changed unrelated edge fields'
            assert type(e['weight']) in {int, float} and e['weight'] >= 1 and float(e['weight']).is_integer()
            assert _group(e) <= nodes.keys()
            if exact_original and e is retained_exact[0]:
                continue
            if exact_original:
                assert e['confidence'] == 'static_inferred', 'split changed unrelated edge fields'
            if is_exact_piece and not exact_original:
                assert _group(e) != _group(original), 'exact piece replaced the retained group'
                assert e['evidence']['file_path'] == original['evidence']['file_path']
                assert e['evidence']['start_line'] >= original['evidence']['start_line']
                assert e['evidence']['end_line'] >= e['evidence']['start_line']
                continue
            assert e['resolution'] == ('ambiguous' if len(_group(e)) > 1 else 'unique_name')
            assert e['evidence']['file_path'] == original['evidence']['file_path']
            assert e['evidence']['start_line'] >= original['evidence']['start_line']
            assert e['evidence']['end_line'] >= e['evidence']['start_line']
            if contents and len(_group(e)) > 1:
                path = e['evidence']['file_path']
                text = '\n'.join(contents[path].splitlines()[e['evidence']['start_line'] - 1:e['evidence']['end_line']])
                assert any(re.search(r'(?<!\w)' + re.escape(nodes[target]['label']) + r'(?!\w)', text) for target in _group(e) - {e['to_id']}), 'split alternative lacks named frozen source evidence'
        retained = [e for e in after if _group(e) == _group(original)]
        assert len(retained) == 1 and retained[0]['evidence'] == original['evidence'], 'split lost original group/evidence'
    raw_groups = defaultdict(list)
    for e in optimized['edges']:
        if e['relation'] != 'TESTS':
            raw_groups[(e['from_id'], _group(e), _record(e['evidence']), e['resolution'], e['confidence'])].append(e)
    eligible = defaultdict(set)
    for n in nodes.values():
        if not _test_node(n) and n.get('kind') in {'class', 'function', 'method', 'file', 'module'} and len(n['label']) > 2:
            eligible[n['label']].add(n['id'])
    for e in added:
        if (e['from_id'], e['to_id'], e['relation']) in split_keys:
            continue
        assert _group(e) <= nodes.keys(), 'added relation references unknown candidate'
        source = nodes[e['from_id']]
        default_fields = {k: v for k, v in e.items() if k not in {'from_id', 'to_id', 'relation', 'confidence', 'resolution', 'weight', 'evidence', 'candidates'}}
        assert default_fields == {'arrows': 'to', 'color': None, 'dashes': False, 'label': '', 'metadata': {}, 'title': None}, 'added language/enrichment relation changed default fields'
        if e['from_id'] == e['to_id'] and e['resolution'] == 'ambiguous' and e['relation'] != 'TESTS':
            assert len(_group(e)) > 1
            assert e['relation'] in {'CALLS', 'READS', 'WRITES', 'TYPE_USES', 'INSTANTIATES', 'IMPORTS', 'INHERITS', 'IMPLEMENTS'}
            assert e['confidence'] == 'static_inferred'
            if e['relation'] == 'IMPORTS' and source.get('kind') == 'file':
                assert contents, 'self file-import additions require independent frozen source evidence'
                names = {nodes[t]['label'] for t in _group(e) - {e['from_id']}}
                assert len(names) == 1, 'self import group has unrelated external lookup names'
                lookup_name = next(iter(names))
            else:
                assert all(nodes[t]['label'] == source['label'] for t in _group(e)), 'self group has unrelated candidate'
                lookup_name = source['label']
            assert e['weight'] >= 1 and float(e['weight']).is_integer()
            span = source['span']
            assert e['evidence']['file_path'] == span['file_path']
            assert span['start_line'] <= e['evidence']['start_line'] <= e['evidence']['end_line'] <= span['end_line']
            if contents:
                lines = contents[span['file_path']].splitlines()
                observed = '\n'.join(lines[e['evidence']['start_line'] - 1:e['evidence']['end_line']])
                assert re.search(r'(?<!\w)' + re.escape(lookup_name) + r'(?!\w)', observed), 'self group has no named source evidence'
            continue
        assert e['relation'] == 'TESTS' and _test_node(source), 'unapproved added relation'
        assert e['weight'] == 1 and e['confidence'] == 'static_inferred' and e.get('metadata', {}) == {}
        propagated = raw_groups.get((e['from_id'], _group(e), _record(e['evidence']), e['resolution'], e['confidence']), [])
        if propagated:
            logical_targets = _group(e) if e['resolution'] == 'ambiguous' else {e['to_id']}
            assert any(not _test_node(nodes[t]) for t in logical_targets)
            continue
        assert contents, 'textual TESTS additions require independent frozen source contents'
        labels = {nodes[t]['label'] for t in _group(e)}
        assert len(labels) == 1
        name = next(iter(labels))
        assert _group(e) == eligible[name], 'textual TESTS group omits/adds production candidates'
        assert e['resolution'] == ('ambiguous' if len(_group(e)) > 1 else 'unique_name')
        span = source['span']
        line = _first_name_line(source, name, contents)
        assert line is not None and e['evidence']['file_path'] == span['file_path']
        assert e['evidence']['start_line'] == line == e['evidence']['end_line'], 'textual TESTS evidence not first identifier occurrence'
