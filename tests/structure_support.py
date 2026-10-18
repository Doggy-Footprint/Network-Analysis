"""Builders and independent oracles for the structure-facts evidence (spec f80bb8ba5e7ac1ef v3).

Everything here is derived from the spec text (F01-F13), never from analysis/structure.py. The reference
functions use different algorithms from the product on purpose (mutual reachability instead of Tarjan,
brute-force pair aggregation) so a shared defect cannot hide.
"""
import hashlib
import json
from collections import deque
from pathlib import Path

from analysis.edge_weights import default_edge_weights_path, load_edge_weights
from analysis.file_graph import FileArchitecture
from language_analyzers.core.graph_models import GraphEdge, GraphNode, SourceSpan

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = Path(__file__).parent / 'structure_evidence'
MANIFEST_PATH = EVIDENCE / 'base_manifest.json'
FIXTURES = ('futuramaapi', 'fastapi-realworld', 'android-nowinandroid', 'typescript-nestjs-realworld')
BASE_KINDS = ('large_node', 'unresolved_boundary', 'evidence_spread')
NEW_KINDS = ('dependency_cycle', 'package_cycle', 'unstable_dependency')
TIERS = ('certain', 'resolved', 'all')
TIER_RANK = {'certain': 0, 'resolved': 1, 'all': 2}
TIER_LABELS = {'certain': '확정 연결', 'resolved': '해석된 연결', 'all': '불확실 포함'}

SC, SI, FI, DR = 'static_certain', 'static_inferred', 'framework_inferred', 'dynamic_required'
EXACT, UNIQUE, AMBIGUOUS, UNRESOLVED = 'exact', 'unique_name', 'ambiguous', 'unresolved'


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))


def canonical_sha(value):
    """Manifest `canonical_json` format."""
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def default_weights():
    return load_edge_weights(default_edge_weights_path())


# ---------------------------------------------------------------- spec-derived identifiers (F04, F12)

def sha16(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def cycle_identifier(scheme, tier, members):
    return f'cycle|{scheme}|{tier}|' + '\n'.join(sorted(members))


def cycle_id(scheme, tier, members):
    return 'b:' + sha16(cycle_identifier(scheme, tier, members))


def cycle_target(scheme, tier, members):
    return f'cycle:{scheme}:{tier}:' + sha16(cycle_identifier(scheme, tier, members))


def unstable_id(scheme, source, target):
    return 'b:' + sha16(f'unstable|{scheme}|{source}|{target}')


# ---------------------------------------------------------------- input builders

def fid(path):
    return 'file:' + path


def file_node(path, boundary=False):
    metadata = {'file_path': path, 'granularity': 'file'}
    if boundary:
        metadata['boundary'] = True
        return GraphNode(path, path, 'module', 'module', kind='module', provenance='python-core', metadata=metadata)
    return GraphNode(fid(path), path, 'file', 'file', kind='file', language=path.rsplit('.', 1)[-1],
                     span=SourceSpan(path, 1, 1), symbol_path=path, provenance='file-aggregation', metadata=metadata)


def _endpoint(value):
    return value if ':' in value else fid(value)


def fedge(source, target, relation='IMPORTS', confidence=SC, resolution=EXACT, share=None, indices=(), evidence=1):
    """File-level edge as to_file_architecture emits it. Plain paths get the 'file:' prefix; ids with ':' are kept."""
    metadata = {'detail_edge_indices': list(indices), 'evidence_count': evidence}
    if share is not None:
        metadata['candidate_share'] = share
    return GraphEdge(_endpoint(source), _endpoint(target), relation, confidence=confidence, resolution=resolution,
                     metadata=metadata)


def dnode(ident, kind='module', provenance='python-core', **extra):
    node = {'id': ident, 'label': ident, 'group': kind, 'category': kind, 'kind': kind, 'language': '', 'span': None,
            'symbol_path': '', 'display_label': '', 'flags': [], 'provenance': provenance, 'metadata': {}}
    node.update(extra)
    return node


def dedge(source, target, relation):
    return {'from_id': source, 'to_id': target, 'relation': relation, 'confidence': FI, 'resolution': EXACT,
            'label': '', 'metadata': {}}


def architecture(paths, edges=(), boundary=(), dnodes=(), dedges=(), node_files=None, details=True):
    """FileArchitecture shaped like analysis.file_graph.to_file_architecture output.
    node_files maps detail node id -> file path (or None); detail nodes absent from it map to None."""
    nodes = [file_node(path) for path in paths] + [file_node(path, boundary=True) for path in boundary]
    mapping = {node['id']: None for node in dnodes}
    for ident, path in (node_files or {}).items():
        mapping[ident] = fid(path) if path else None
    detail = {'nodes': list(dnodes), 'edges': list(dedges), 'node_files': mapping, 'node_owners': {},
              'file_nodes': {}} if details else {}
    return FileArchitecture('oracle', '/oracle', nodes, list(edges), {}, [], detail, 'file')


def python_modules(mapping):
    """{path: dotted symbol_path} -> (dnodes, node_files) of python-core module nodes."""
    dnodes, files = [], {}
    for path, dotted in mapping.items():
        ident = 'py:' + dotted
        dnodes.append(dnode(ident, 'module', 'python-core', symbol_path=dotted))
        files[ident] = path
    return dnodes, files


# ---------------------------------------------------------------- result lookups

def of_kind(candidates, kind):
    return [item for item in candidates if item['kind'] == kind]


def cycles_by_key(candidates, kind='dependency_cycle'):
    """{(scheme, tier, tuple(members)): candidate}"""
    found = {}
    for item in of_kind(candidates, kind):
        key = (item['structure']['scheme'], item['structure']['tier'], tuple(item['structure']['members']))
        assert key not in found, ('duplicate cycle candidate', key)
        found[key] = item
    return found


def cycle_view(candidates, kind='dependency_cycle'):
    return sorted(cycles_by_key(candidates, kind))


# ---------------------------------------------------------------- independent reference implementation

def reference_sccs(nodes, adjacency):
    """SCCs of size >= 2 by mutual reachability (one BFS per node); shares no code idea with Tarjan."""
    nodes = sorted(set(nodes))
    reach = {}
    for start in nodes:
        seen = {start}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for nxt in adjacency.get(current, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        reach[start] = seen
    groups, done = [], set()
    for node in nodes:
        if node in done:
            continue
        group = sorted(other for other in reach[node] if node in reach[other])
        done.update(group)
        if len(group) >= 2:
            groups.append(group)
    return sorted(groups, key=lambda group: group[0])


def ref_tier(edge):
    confidence, resolution = str(edge.confidence), str(edge.resolution)
    if confidence == SC and resolution == EXACT:
        return 'certain'
    return 'resolved' if resolution in (EXACT, UNIQUE) else 'all'


def ref_file_ids(arch):
    return {node.id for node in arch.nodes if not (node.metadata or {}).get('boundary')}


def ref_pairs(arch, weights, tier):
    """F01/F02: file pair records re-aggregated from tier-t edges only."""
    files = ref_file_ids(arch)
    pairs = {}
    for edge in arch.edges:
        if edge.relation == 'TESTS' or edge.from_id not in files or edge.to_id not in files:
            continue
        if TIER_RANK[ref_tier(edge)] > TIER_RANK[tier]:
            continue
        meta = edge.metadata or {}
        record = pairs.setdefault((edge.from_id, edge.to_id), {'relations': set(), 'max_weight': 0.0,
                                                               'evidence_count': 0, 'detail_edge_indices': set(),
                                                               'tiers': []})
        record['relations'].add(edge.relation)
        record['max_weight'] = max(record['max_weight'], weights.weight_for(edge) * meta.get('candidate_share', 1))
        record['evidence_count'] += meta.get('evidence_count', 0)
        record['detail_edge_indices'].update(meta.get('detail_edge_indices', ()))
        record['tiers'].append(ref_tier(edge))
    for record in pairs.values():
        record['relations'] = sorted(record['relations'])
        record['detail_edge_indices'] = sorted(record['detail_edge_indices'])
        record['tier'] = min(record.pop('tiers'), key=TIER_RANK.get)
    return pairs


def ref_language(arch):
    """F07 written from the spec text."""
    detail = arch.details or {}
    node_files = detail.get('node_files', {})
    modules, kotlin_files, kotlin_pkg = {}, {}, {}
    for node in detail.get('nodes', []):
        target = node_files.get(node['id'])
        if node.get('provenance') == 'python-core' and node.get('kind') == 'module' and target:
            modules[target] = node
        if node.get('provenance') == 'kotlin-core' and node.get('kind') == 'file' and target:
            kotlin_files[node['id']] = target
    for edge in detail.get('edges', []):
        if edge['relation'] == 'CONTAINS' and edge['from_id'].startswith('kotlin-package:') and edge['to_id'] in kotlin_files:
            kotlin_pkg[kotlin_files[edge['to_id']]] = edge['from_id'][len('kotlin-package:'):]
    result = {}
    for node in arch.nodes:
        if (node.metadata or {}).get('boundary'):
            continue
        path = node.id[len('file:'):]
        name = path.rsplit('/', 1)[-1]
        if node.id in modules:
            module = modules[node.id]
            dotted = module.get('symbol_path') or module['id'][len('py:'):]
            if name != '__init__.py':
                dotted = dotted.rpartition('.')[0] if '.' in dotted else ''
            result[node.id] = ['pkg:python:' + (dotted or '(root)')]
        elif node.id in kotlin_pkg:
            result[node.id] = ['pkg:kotlin:' + kotlin_pkg[node.id]]
        else:
            directory = path.rpartition('/')[0]
            result[node.id] = ['pkg:dir:' + (directory or '.')]
    return result


def ref_framework(arch):
    detail = arch.details or {}
    node_files = detail.get('node_files', {})
    nodes = {node['id']: node for node in detail.get('nodes', [])}
    modules = [n for n in nodes.values() if n.get('provenance') == 'nestjs' and n.get('kind') == 'module']
    if not modules:
        return None
    members = {}
    for module in modules:
        package = 'pkg:nestjs:' + module['id'][len('nestjs:module:'):]
        files = set()
        if node_files.get(module['id']):
            files.add(node_files[module['id']])
        for edge in detail.get('edges', []):
            if edge['from_id'] == module['id'] and edge['relation'] in ('DECLARES', 'PROVIDES') and node_files.get(edge['to_id']):
                files.add(node_files[edge['to_id']])
        members[package] = files
    result = {}
    for package, files in members.items():
        for path in files:
            result.setdefault(path, []).append(package)
    return {path: sorted(packages) for path, packages in result.items()}


def ref_package_pairs(file_pairs, assignment):
    pairs = {}
    for (source, target), record in file_pairs.items():
        for p in assignment.get(source, ()):
            for q in assignment.get(target, ()):
                if p == q:
                    continue
                item = pairs.setdefault((p, q), {'max_weight': 0.0, 'evidence_count': 0, 'tiers': [], 'file_pairs': []})
                item['max_weight'] = max(item['max_weight'], record['max_weight'])
                item['evidence_count'] += record['evidence_count']
                item['tiers'].append(record['tier'])
                item['file_pairs'].append([source, target])
    for item in pairs.values():
        item['tier'] = min(item.pop('tiers'), key=TIER_RANK.get)
        item['file_pairs'].sort()
    return pairs


def ref_metrics(assignment, all_pairs):
    members = {}
    for path, packages in assignment.items():
        for package in packages:
            members.setdefault(package, set()).add(path)
    out = {}
    for package, files in members.items():
        outs = {q: r for (p, q), r in all_pairs.items() if p == package}
        ins = {p: r for (p, q), r in all_pairs.items() if q == package}
        ce, ca = len(outs), len(ins)
        wce, wca = sum(r['max_weight'] for r in outs.values()), sum(r['max_weight'] for r in ins.values())
        out[package] = {'file_count': len(files), 'ca': ca, 'ce': ce,
                        'instability': ce / (ca + ce) if ca + ce else None,
                        'weighted_ca': wca, 'weighted_ce': wce,
                        'weighted_instability': wce / (wca + wce) if wca + wce else None}
    return out


def ref_structure(arch, weights):
    """Everything the spec lets a test predict: cycle views per scheme/tier and package metrics."""
    schemes = {'language': ref_language(arch)}
    framework = ref_framework(arch)
    if framework is not None:
        schemes['framework'] = framework
    files = sorted(ref_file_ids(arch))
    file_cycles = {}
    pairs_by_tier = {tier: ref_pairs(arch, weights, tier) for tier in TIERS}
    for tier in TIERS:
        adjacency = {}
        for (source, target) in pairs_by_tier[tier]:
            adjacency.setdefault(source, []).append(target)
        file_cycles[tier] = reference_sccs(files, adjacency)
    package_cycles, metrics, unstable = {}, {}, {}
    for scheme, assignment in schemes.items():
        all_pairs = None
        for tier in TIERS:
            package_pairs = ref_package_pairs(pairs_by_tier[tier], assignment)
            if tier == 'all':
                all_pairs = package_pairs
            adjacency = {}
            for (p, q) in package_pairs:
                adjacency.setdefault(p, []).append(q)
            packages = sorted({p for packages in assignment.values() for p in packages})
            package_cycles[(scheme, tier)] = reference_sccs(packages, adjacency)
        metrics[scheme] = ref_metrics(assignment, all_pairs)
        unstable[scheme] = sorted(
            (p, q) for (p, q) in all_pairs
            if (metrics[scheme][q]['instability'] or 0) > (metrics[scheme][p]['instability'] or 0)
        )
    return {'schemes': schemes, 'file_cycles': file_cycles, 'package_cycles': package_cycles, 'metrics': metrics,
            'unstable': unstable, 'pairs': pairs_by_tier}


def file_pair_view(record):
    """Spec F02 fields of an evidence/pair record, comparable across implementations."""
    return {key: record[key] for key in ('from_id', 'to_id', 'relations', 'max_weight', 'evidence_count', 'detail_edge_indices', 'tier')}


# ---------------------------------------------------------------- CLI / bottleneck payload helpers

def without_structure_facts(payload):
    """Drops everything bottlenecks.v8 adds so legacy comparisons keep their original meaning."""
    import copy
    result = copy.deepcopy(payload)
    if 'candidates' in result:
        result['candidates'] = [c for c in result['candidates'] if c.get('kind') not in NEW_KINDS]
    network = result.get('dependency_network')
    if isinstance(network, dict):
        network.pop('package_metrics', None)
        network.pop('structure_policy', None)
    coverage = result.get('coverage')
    if isinstance(coverage, dict):
        coverage.pop('structure', None)
    return result
