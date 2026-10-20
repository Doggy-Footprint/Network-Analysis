"""Spec f3972ebd2386454f v1 support. Expected values in the tests are written literally from rules R1-R9;
nothing here derives an expectation from analyzer output."""
from pathlib import Path

from tests.fact_defects_support import kotlin_analyze, python_analyze, ts_analyze, write_tree

DYNAMIC_PREFIX = 'dynamic_'
FLAG_IMPORT, FLAG_ATTR, FLAG_EVAL = 'dynamic_import', 'dynamic_attr', 'dynamic_eval'


def _build(analyze, tmp_path, files):
    root = write_tree(Path(tmp_path) / 'proj', files)
    return analyze(root)


def build_ts(tmp_path, files):
    return _build(ts_analyze, tmp_path, files)


def build_kotlin(tmp_path, files):
    return _build(kotlin_analyze, tmp_path, files)


def build_python(tmp_path, files):
    return _build(python_analyze, tmp_path, files)


def dyn_flags(arch):
    """node id -> sorted dynamic_* flags (every node, including those without)."""
    return {n.id: sorted(f for f in (n.flags or []) if str(f).startswith(DYNAMIC_PREFIX)) for n in arch.nodes}


def dyn_of(arch, node_id):
    flags = dyn_flags(arch)
    assert node_id in flags, f'node {node_id} missing; have {sorted(flags)}'
    return flags[node_id]


def dynamic_edges(arch, relation='IMPORTS'):
    return sorted((e.from_id, e.to_id) for e in arch.edges
                  if str(getattr(e.relation, 'value', e.relation)) == relation
                  and str(getattr(e.confidence, 'value', e.confidence)) == 'dynamic_required')


def imports_edges(arch):
    return sorted((e.from_id, e.to_id, str(getattr(e.confidence, 'value', e.confidence))) for e in arch.edges
                  if str(getattr(e.relation, 'value', e.relation)) == 'IMPORTS')


def dynamic_external_names(arch, node_id):
    for n in arch.nodes:
        if n.id == node_id:
            return sorted(r['name'] for r in (n.metadata or {}).get('external_imports') or [] if r.get('dynamic'))
    raise AssertionError(f'node {node_id} missing')
