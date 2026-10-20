"""Directory and file counts are computed here with posixpath on the generated paths, never read from the analyzer
under test."""
import json
import os
import posixpath
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fact_defects_support import write_tree

REPO = Path(__file__).resolve().parents[1]
BASE_COMMIT = '3b768a9b5e9b79c519bfe667b12b8e980cfa636b'


def expected_spread(target_file, evidence_files, threshold, line_spans=None):
    """R11 from the rule text. evidence_files: file_path of every remaining (non-ownership) evidence row; the rows in
    the target's own file are dropped first (R5). line_spans: {file: (min_start, max_end)} for the single-file extent.
    Returns None when the candidate does not fire, else the metrics dict."""
    kept = [p for p in evidence_files if p != target_file]
    files = set(kept)
    own_dir = posixpath.dirname(target_file) if target_file else None
    dirs = {posixpath.dirname(p) for p in files} - {own_dir}
    extent = 0
    if len(files) == 1:
        lo, hi = line_spans[next(iter(files))]
        extent = hi - lo + 1
    fires = len(dirs) >= 2 or (len(files) == 1 and extent > threshold)
    if not fires:
        return None
    return {'file_count': len(files), 'directory_count': len(dirs), 'line_span': extent, 'line_threshold': threshold}


def kind_of(node):
    return getattr(node.kind, 'value', node.kind)


def rel_of(edge):
    return str(getattr(edge.relation, 'value', edge.relation))


def ids_of(arch):
    return {n.id for n in arch.nodes}


def targets(arch, source, relation):
    return {e.to_id for e in arch.edges if e.from_id == source and rel_of(e) == relation}


def has_edge(arch, source, relation, target):
    return any(e.from_id == source and e.to_id == target and rel_of(e) == relation for e in arch.edges)


def edge_start_line(arch, source, relation, target):
    lines = [e.evidence.start_line for e in arch.edges
             if e.from_id == source and e.to_id == target and rel_of(e) == relation and e.evidence]
    assert lines, (source, relation, target)
    return lines


def span_lines(node):
    return (node.span.start_line, node.span.end_line)


def shape(arch, file_id, skip_prefixes=('kotlin-package:',)):
    """Relative structure of one file: (qualname, kind, signature) and (from, relation, to) triples, so a one-line and a
    multi-line spelling of the same declarations can be compared."""
    prefix = f'kotlin:{file_id}#'
    own = {n.id for n in arch.nodes if n.id.startswith(prefix)}
    nodes = {(n.id[len(prefix):], kind_of(n), n.signature) for n in arch.nodes if n.id in own}
    edges = {(e.from_id[len(prefix):] if e.from_id in own else e.from_id, rel_of(e), e.to_id[len(prefix):] if e.to_id in own else e.to_id)
             for e in arch.edges if (e.from_id in own or e.to_id in own)}
    return nodes, edges


def base_tree(tmp_path_factory):
    """Export BASE_COMMIT into a scratch directory with `git archive` (no worktree is registered in the repository)."""
    probe = subprocess.run(['git', '-C', str(REPO), 'cat-file', '-e', f'{BASE_COMMIT}^{{commit}}'], capture_output=True)
    if probe.returncode != 0:
        pytest.skip(f'{BASE_COMMIT} is not available in this clone; V8 compares against it')
    target = Path(tmp_path_factory.mktemp('base-tree'))
    archive = subprocess.run(['git', '-C', str(REPO), 'archive', BASE_COMMIT], capture_output=True, check=True)
    subprocess.run(['tar', '-x', '-C', str(target)], input=archive.stdout, check=True)
    return target


def run_cli(tree, project, out_dir, *args):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONHASHSEED='0', PYTHONPATH=str(tree))
    result = subprocess.run([sys.executable, '-m', 'code_analyzer', str(project), *args, '-o', str(out_dir / 'r.html'),
                             '--json'], cwd=str(tree), env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads((out_dir / 'r.json').read_text(encoding='utf-8'))


FRAMEWORK_DUMP = '''
import dataclasses, json, sys
from framework_analyzers.android.analyzer import AndroidAnalyzer

def plain(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [plain(v) for v in value]
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True)) if isinstance(value, (set, frozenset)) else items
    if hasattr(value, '__dict__') and not isinstance(value, type):
        return {k: plain(v) for k, v in vars(value).items() if not k.startswith('_')}
    if hasattr(value, 'value'):
        return plain(value.value)
    return value if isinstance(value, (str, int, float, bool, type(None))) else repr(value)

print(json.dumps(plain(AndroidAnalyzer(sys.argv[1]).analyze()), sort_keys=True))
'''


def framework_dump(tree, project):
    env = dict(os.environ, PYTHONHASHSEED='0', PYTHONPATH=str(tree))
    result = subprocess.run([sys.executable, '-c', FRAMEWORK_DUMP, str(project)], cwd=str(tree), env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout)


def write_project(root, files):
    return write_tree(root, files)


def rmtree(path):
    shutil.rmtree(path, ignore_errors=True)
