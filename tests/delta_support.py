"""Reference implementation written from spec F07-F12 and F14 with a different algorithm from the product's on
purpose: every overlap and membership test is a nested scan over plain lists, never an index or set intersection of
whole cycles. Payload builders emit only the fields F05 lists."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests.architecture_rules_support import init_git
from tests.doc_references_support import without_doc_references

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = Path(__file__).parent / 'delta_evidence'
MANIFEST_PATH = EVIDENCE / 'base_manifest.json'
EXAMPLE_PROFILE = REPO / 'profiles' / 'architecture_rules.example.yaml'
MAIN = 'from code_analyzer.cli import main; main()'
CYCLE_KINDS = ('dependency_cycle', 'package_cycle')
TIERS = ('certain', 'resolved', 'all')
LISTS = ('new_cycles', 'grown_cycles', 'new_violations', 'new_package_dependencies', 'instability_changes')
DELTA_KEYS = {'policy', 'baseline', 'rules_changed', *LISTS, 'resolved', 'counts'}
FIXTURES = ('futuramaapi', 'fastapi-realworld', 'fastapi-official-template', 'android-nowinandroid', 'typescript-nestjs-realworld')
FIXTURE_ARGS = {'futuramaapi': ['-l', 'python'], 'fastapi-realworld': ['-l', 'python'], 'fastapi-official-template': ['-l', 'python'],
                'android-nowinandroid': ['-l', 'kotlin'], 'typescript-nestjs-realworld': ['-l', 'typescript']}
SUMMARY = '[Δ] Delta vs baseline: new cycles {}, grown cycles {}, new violations {}, new package dependencies {}, instability changes {}'
RULES_WARNING = '[!] Warning: architecture rules differ from the baseline'


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))


def sha16(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def cid(kind, scheme, tier, members):
    return 'b:' + sha16(f'{kind}|{scheme}|{tier}|' + '\n'.join(sorted(members)))


def ring(members):
    members = sorted(members)
    return [[members[i], members[(i + 1) % len(members)]] for i in range(len(members))]


def cycle(members, kind='dependency_cycle', scheme='file', tier='all', pairs=None, ident=None):
    members = sorted(members)
    pairs = ring(members) if pairs is None else pairs
    return {'id': ident or cid(kind, scheme, tier, members), 'kind': kind,
            'structure': {'scheme': scheme, 'tier': tier, 'members': members},
            'evidence': [{'from_id': a, 'to_id': b, 'tier': tier} for a, b in pairs]}


def internal_violation(ident, target, to_id, rule_type='forbid', from_layer='db', to_layer='api', tier='all'):
    return {'id': ident, 'kind': 'rule_violation', 'target': target,
            'structure': {'rule_type': rule_type, 'from_layer': from_layer, 'to_layer': to_layer, 'tier': tier},
            'evidence': [{'from_id': target, 'to_id': to_id, 'tier': tier}]}


def external_violation(ident, target, name, rule_type='forbid_external', from_layer='db'):
    return {'id': ident, 'kind': 'rule_violation', 'target': target,
            'structure': {'rule_type': rule_type, 'from_layer': from_layer, 'to_external': name},
            'evidence': [{'name': name, 'line': 1}]}


def pdep(a, b, tier='certain'):
    return {'from_id': a, 'to_id': b, 'tier': tier}


def pmetrics(instabilities):
    return {name: {'instability': value} for name, value in instabilities.items()}


def payload(candidates=(), package_dependencies=None, package_metrics=None, rules_sha='absent', file_count=3,
            policy='structure.v2'):
    """rules_sha: 'absent' omits coverage.architecture_rules; None keeps the section without a digest."""
    result = {
        'schema': 'bottlenecks.v8', 'granularity': 'file', 'snapshot': {'file_count': file_count},
        'dependency_network': {
            'structure_policy': policy,
            'package_dependencies': {'language': []} if package_dependencies is None else package_dependencies,
            'package_metrics': {'language': {}} if package_metrics is None else package_metrics},
        'candidates': list(candidates), 'coverage': {},
    }
    if rules_sha != 'absent':
        result['coverage']['architecture_rules'] = {} if rules_sha is None else {'rules_sha256': rules_sha}
    return result


def _pair(item, evidence, file_ids):
    """(from, to) of one cycle evidence entry: a v8 record, or a bottlenecks.v9 row (file indexes for file pairs)."""
    if isinstance(evidence, dict):
        return [evidence['from_id'], evidence['to_id']]
    if item['kind'] == 'dependency_cycle':
        return [file_ids[evidence[0]], file_ids[evidence[1]]]
    return [evidence[0], evidence[1]]


def _cycles(data):
    found = []
    file_ids = data['dependency_network'].get('file_ids')
    for item in data['candidates']:
        if item['kind'] in CYCLE_KINDS:
            structure = item['structure']
            found.append({'id': item['id'], 'kind': item['kind'], 'scheme': structure['scheme'], 'tier': structure['tier'],
                          'members': list(structure['members']),
                          'pairs': [_pair(item, e, file_ids) for e in item['evidence']]})
    return found


def _same_key(a, b):
    return (a['kind'], a['scheme'], a['tier']) == (b['kind'], b['scheme'], b['tier'])


def _overlaps(a, b):
    return _same_key(a, b) and any(m == n for m in a['members'] for n in b['members'])


def ref_delta(current, baseline):
    cur, base = _cycles(current), _cycles(baseline)
    new_cycles, grown_cycles = [], []
    for c in cur:
        overlapping = [b for b in base if _overlaps(c, b)]
        covered = [m for m in c['members'] if any(m in b['members'] for b in overlapping)]
        added = sorted(m for m in c['members'] if m not in covered)
        if overlapping and not added and len(overlapping) < 2:
            continue
        old_pairs = [p for b in overlapping for p in b['pairs']]
        item = {'candidate_id': c['id'], 'kind': c['kind'], 'scheme': c['scheme'], 'tier': c['tier'], 'members': c['members'],
                'baseline_candidate_ids': sorted(b['id'] for b in overlapping), 'added_members': added,
                'new_internal_pairs': sorted(p for p in c['pairs'] if p not in old_pairs)}
        (grown_cycles if overlapping else new_cycles).append(item)
    order = lambda i: (i['kind'], i['scheme'], i['tier'], i['candidate_id'])
    new_cycles.sort(key=order)
    grown_cycles.sort(key=order)
    resolved_cycles = sum(1 for b in base if not any(_overlaps(b, c) for c in cur))

    def violations(data):
        return [c for c in data['candidates'] if c['kind'] == 'rule_violation']
    base_ids = [v['id'] for v in violations(baseline)]
    cur_ids = [v['id'] for v in violations(current)]
    new_violations = []
    for v in violations(current):
        if v['id'] in base_ids:
            continue
        s = v['structure']
        item = {'candidate_id': v['id'], 'rule_type': s['rule_type'], 'from_layer': s['from_layer'], 'target': v['target']}
        if 'to_layer' in s:
            item['to_layer'] = s['to_layer']
            item['to_id'] = v['evidence'][0]['to_id']
        else:
            item['to_external'] = s['to_external']
        new_violations.append(item)
    new_violations.sort(key=lambda i: i['candidate_id'])

    cur_pd = current['dependency_network']['package_dependencies']
    base_pd = baseline['dependency_network']['package_dependencies']
    new_pd, resolved_pd = [], 0
    for scheme, pairs in cur_pd.items():
        known = [(p['from_id'], p['to_id']) for p in base_pd.get(scheme, [])]
        for p in pairs:
            if (p['from_id'], p['to_id']) not in known:
                new_pd.append({'scheme': scheme, 'from_id': p['from_id'], 'to_id': p['to_id'], 'tier': p['tier']})
    new_pd.sort(key=lambda i: (i['scheme'], i['from_id'], i['to_id']))
    for scheme, pairs in base_pd.items():
        now = [(p['from_id'], p['to_id']) for p in cur_pd.get(scheme, [])]
        resolved_pd += sum(1 for p in pairs if (p['from_id'], p['to_id']) not in now)

    changes = []
    cur_m = current['dependency_network']['package_metrics']
    base_m = baseline['dependency_network']['package_metrics']
    for scheme in cur_m:
        for package in cur_m[scheme]:
            if scheme not in base_m or package not in base_m[scheme]:
                continue
            a, b = base_m[scheme][package]['instability'], cur_m[scheme][package]['instability']
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(b - a) >= 0.2 - 1e-12:
                changes.append({'scheme': scheme, 'package': package, 'baseline': a, 'current': b, 'delta': b - a})
    changes.sort(key=lambda i: (-abs(i['delta']), i['scheme'], i['package']))

    cur_rules = current['coverage'].get('architecture_rules')
    base_rules = baseline['coverage'].get('architecture_rules')
    changed = False
    if cur_rules is not None and base_rules is not None:
        changed = 'rules_sha256' not in cur_rules or 'rules_sha256' not in base_rules or cur_rules['rules_sha256'] != base_rules['rules_sha256']
    lists = {'new_cycles': new_cycles, 'grown_cycles': grown_cycles, 'new_violations': new_violations,
             'new_package_dependencies': new_pd, 'instability_changes': changes}
    return {'policy': 'delta.v1',
            'baseline': {'file_count': baseline['snapshot']['file_count'],
                         'rules_sha256': (base_rules or {}).get('rules_sha256')},
            'rules_changed': changed, **lists,
            'resolved': {'cycles': resolved_cycles,
                         'violations': sum(1 for i in base_ids if i not in cur_ids),
                         'package_dependencies': resolved_pd},
            'counts': {name: len(items) for name, items in lists.items()}}


def ref_regressions(delta, fail_on):
    names = set()
    for name in fail_on:
        names.update(('cycle', 'violation') if name == 'any' else (name,))
    hit = {'cycle': bool(delta['new_cycles'] or delta['grown_cycles']), 'violation': bool(delta['new_violations'])}
    return [name for name in ('cycle', 'violation') if name in names and hit[name]]


def make_delta(**lists):
    return {name: lists.get(name, []) for name in LISTS}


def wire(value):
    return json.loads(json.dumps(value))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def cli(args, cwd=REPO, seed='0'):
    return subprocess.run([sys.executable, '-c', MAIN, *map(str, args)], cwd=cwd, env=dict(os.environ, PYTHONHASHSEED=seed),
                          capture_output=True, text=True)


def copy_fixture(name, destination):
    from fixtures.registry import fixture_root
    shutil.copytree(fixture_root(name), destination, symlinks=True)
    return Path(destination)


def outputs(directory):
    return {name: (Path(directory) / name).exists() for name in ('r.html', 'r.json', 'r_assets', 'b.json')}


def run_bottlenecks(root, directory, name='fastapi-realworld', rules=None, extra=(), check=True, bottlenecks='b.json'):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    args = [root, *FIXTURE_ARGS[name], '--granularity', 'file', '--json', '-o', directory / 'r.html',
            '--bottlenecks', directory / bottlenecks, *extra]
    if rules is not None:
        args += ['--architecture-rules', rules]
    done = cli(args)
    if check:
        assert done.returncode == 0, done.stderr[-2000:]
    return done


def append_file(root, relative, text):
    target = Path(root) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding='utf-8') if target.exists() else ''
    target.write_text(existing + text, encoding='utf-8')


def retrack(root):
    init_git(root)


def independent_digest(rules):
    form = {'version': rules.version,
            'layers': {name: {'paths': sorted(set(sel.paths)), 'packages': sorted(set(sel.packages))} for name, sel in rules.layers.items()},
            'allow': {k: list(v) for k, v in rules.allow.items()}, 'forbid': {k: list(v) for k, v in rules.forbid.items()},
            'external': {k: list(v) for k, v in rules.external.items()},
            'forbid_external': {k: list(v) for k, v in rules.forbid_external.items()},
            'allow_external': {k: list(v) for k, v in rules.allow_external.items()}}
    return hashlib.sha256(json.dumps(form, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()


def without_digest(coverage):
    return {k: v for k, v in coverage.items() if k != 'rules_sha256'}


def base_form_bytes(data):
    obj = without_doc_references(json.loads(data))
    obj['dependency_network'].pop('package_dependencies', None)
    obj['dependency_network']['structure_policy'] = 'structure.v1'   # base hashes predate the structure.v2 bump (build scheme)
    obj.get('coverage', {}).get('structure', {})['policy'] = 'structure.v1'
    obj['candidates'] = [c for c in obj['candidates'] if c['kind'] not in ('untested_hub', 'isolated_node')]
    obj.get('edge_weights', {}).pop('untested_hub_top_n', None)
    obj.get('edge_weights', {}).pop('large_node_token_threshold', None)
    rules = obj.get('coverage', {}).get('architecture_rules')
    if isinstance(rules, dict):
        rules.pop('rules_sha256', None)
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
