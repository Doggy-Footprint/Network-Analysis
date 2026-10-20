"""Spec e91abc221d7deb2a v1 support. Expected values in the tests come from rules R1-R9 and the Cases table;
the PageRank references below are independent power-iteration implementations of the R7 formula and of the
pre-change definition (normalise by outgoing weight sum). Nothing here reads analyzer output to derive an expectation."""
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from analysis.edge_weights import load_edge_weights, default_edge_weights_path
from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
from language_analyzers.core.graph_models import GraphNode, NodeCost, SourceSpan
from repository import build_snapshot, default_scan_policy_path, load_scan_policy
from tests.edge_weights_support import edge, load_weights, weights_data, write_weights
from tests.fact_defects_support import kotlin_analyze, python_analyze, ts_analyze, write_tree

DAMPING = 0.85
LANGS = {'python': (python_analyze, '.py'), 'typescript': (ts_analyze, '.ts'), 'kotlin': (kotlin_analyze, '.kt')}


# ---------------------------------------------------------------- analyzer observations

def analyze_files(tmp_path, language, files, name='proj'):
    root = write_tree(Path(tmp_path) / name, files)
    return LANGS[language][0](root)


def node_of(arch, node_id):
    for n in arch.nodes:
        if n.id == node_id:
            return n
    raise AssertionError(f'node {node_id} missing; have {sorted(n.id for n in arch.nodes)}')


def meta_of(arch, node_id):
    return node_of(arch, node_id).metadata or {}


def observed(arch, node_id):
    """Everything R1/R3 talks about, for one node: totals default to 0 when the key is absent."""
    m = meta_of(arch, node_id)
    return {
        'ext_count': m.get('external_call_count', 0),
        'ext_calls': dict(m.get('external_calls') or {}),
        'unres_total': m.get('unresolved_reference_total', 0),
        'unres_calls': dict(m.get('unresolved_calls') or {}),
        'refs': list(m.get('unresolved_references') or []),
        'keys': {k for k in m if k.startswith(('external_', 'unresolved_'))},
    }


def assert_external(arch, node_id, count, calls=None):
    o = observed(arch, node_id)
    assert o['ext_count'] == count, (node_id, o)
    if calls is not None:
        assert o['ext_calls'] == calls, (node_id, o)
    assert o['unres_total'] == 0 and not o['refs'] and not o['unres_calls'], (node_id, o)
    assert not ({'unresolved_calls', 'unresolved_references', 'unresolved_reference_total'} & o['keys']), (node_id, o)


def assert_boundary(arch, node_id, count=1, calls=None, external=0):
    o = observed(arch, node_id)
    assert o['unres_total'] == count, (node_id, o)
    assert len(o['refs']) == min(count, 20), (node_id, o)
    assert sum(o['unres_calls'].values()) == count, (node_id, o)
    if calls is not None:
        assert o['unres_calls'] == calls, (node_id, o)
    assert o['ext_count'] == external, (node_id, o)
    if not external:
        assert 'external_call_count' not in o['keys'] and 'external_calls' not in o['keys'], (node_id, o)


def assert_silent(arch, node_id):
    o = observed(arch, node_id)
    assert not o['keys'] and not o['refs'], (node_id, o)


def edges_between(arch, source, relation):
    return sorted((e.to_id) for e in arch.edges
                  if e.from_id == source and str(getattr(e.relation, 'value', e.relation)) == relation)


def edge_targets_by_label(arch, source, relation, label):
    by_id = {n.id: n for n in arch.nodes}
    return [e.to_id for e in arch.edges
            if e.from_id == source and str(getattr(e.relation, 'value', e.relation)) == relation
            and by_id[e.to_id].label == label]


def flags_of(arch, node_id):
    return list(node_of(arch, node_id).flags or [])


# ---------------------------------------------------------------- CLI pipeline with token threshold

def pipeline(root, tmp_path, granularity, language, name='run', **weight_options):
    import code_analyzer.cli as cli
    out = Path(tmp_path) / name
    out.mkdir(parents=True, exist_ok=True)
    argv = ['code-analyzer', str(Path(root).resolve()), '-l', language, '--granularity', granularity,
            '-o', str(out / 'report.html'), '--bottlenecks', str(out / 'b.json')]
    if weight_options:
        argv += ['--edge-weights', str(write_weights(out, weights_data(**weight_options)))]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, 'argv', argv)
        cli.main()
    return json.loads((out / 'b.json').read_text(encoding='utf-8'))


def of_kind(payload, kind):
    return [c for c in payload['candidates'] if c['kind'] == kind]


def evidence_rows(candidate):
    ev = candidate['evidence']
    return ev if isinstance(ev, list) else [ev]


# ---------------------------------------------------------------- synthetic symbol-mode bottleneck input

def make_subject(files, nodes, edges):
    """files: {path: text}; nodes: GraphNode list; edges: GraphEdge list (all spans must lie in files)."""
    from language_analyzers.python.graph import PythonGraphAnalyzer
    root = Path('/repo')
    snap = build_snapshot(root, sorted(files), policy=load_scan_policy(default_scan_policy_path()),
                          reader=lambda path: files[path.relative_to(root).as_posix()], ignore_source='test')
    arch = PythonGraphAnalyzer(root, snap).analyze()
    return snap, replace(arch, nodes=list(nodes), edges=list(edges))


def sym(ident, path='w.py', start=1, end=1, tokens=10, lines=1, kind=None, provenance=None):
    node = GraphNode(ident, ident, 'g', 'c', span=SourceSpan(path, start, end) if path else None,
                     cost=NodeCost(tokens, tokens, lines))
    if kind:
        node.kind = kind
        node.group = node.category = kind
    if provenance:
        node.provenance = provenance
    return node


def run_payload(snap, arch, weights):
    return json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, weights)))


def default_weights():
    return load_edge_weights(default_edge_weights_path())


def weights_in(tmp_path, **options):
    return load_weights(tmp_path, weights_data(**options))


# ---------------------------------------------------------------- independent PageRank references

def _targets(value):
    return dict(value) if isinstance(value, dict) else {t: 1.0 for t in value}


def _clean(outgoing):
    nodes = sorted(outgoing)
    return nodes, {s: {t: w for t, w in _targets(outgoing[s]).items() if t != s and t in outgoing} for s in nodes}


def ref_pagerank(outgoing, damping=DAMPING):
    """R7: share to t is d*score[s]*w/outdeg(s); what is not delivered, plus dangling mass, is spread uniformly."""
    nodes, out = _clean(outgoing)
    n = len(nodes)
    if n == 0:
        return {}
    score = {x: 1.0 / n for x in nodes}
    for _ in range(200000):
        new = {x: (1 - damping) / n for x in nodes}
        spare = 0.0
        for s in nodes:
            k = len(out[s])
            if k == 0:
                spare += damping * score[s]
                continue
            delivered = 0.0
            for t, w in out[s].items():
                new[t] += damping * score[s] * w / k
                delivered += w / k
            spare += damping * score[s] * (1 - delivered)
        for x in nodes:
            new[x] += spare / n
        if max(abs(new[x] - score[x]) for x in nodes) < 1e-15:
            score = new
            break
        score = new
    return score


def ref_pagerank_before(outgoing, damping=DAMPING):
    """Pre-change definition: normalise by the outgoing weight sum, dangling mass uniform."""
    nodes, out = _clean(outgoing)
    n = len(nodes)
    if n == 0:
        return {}
    score = {x: 1.0 / n for x in nodes}
    for _ in range(200000):
        new = {x: (1 - damping) / n for x in nodes}
        spare = 0.0
        for s in nodes:
            total = sum(out[s].values())
            if not out[s]:
                spare += damping * score[s]
                continue
            for t, w in out[s].items():
                new[t] += damping * score[s] * w / total
        for x in nodes:
            new[x] += spare / n
        if max(abs(new[x] - score[x]) for x in nodes) < 1e-15:
            score = new
            break
        score = new
    return score
