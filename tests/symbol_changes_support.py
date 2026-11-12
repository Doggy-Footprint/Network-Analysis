"""Builders for the symbol table, symbol candidates and symbol delta tests. Architectures are built by hand in the shape
analysis.file_graph.to_file_architecture produces (details.nodes/edges/node_files/node_owners/file_nodes plus one file node
per path), so expectations never depend on product code."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from analysis.file_graph import FileArchitecture, ownership_edge
from language_analyzers.core.flags import path_flags
from language_analyzers.core.graph_models import GraphEdge, GraphNode, NodeCost, SourceSpan
from language_analyzers.core.serialization import edge_to_dict, node_to_dict
from tests.delta_support import MAIN, REPO, SYMBOL_COLUMNS, SYMBOL_ENTRY_KEYS, payload
from tests.rename_delta_support import git, make_repo

BASE_COMMIT = '075881f86abf2cd8733e74ae8c4df1d79922c05a'
EVIDENCE = Path(__file__).parent / 'symbol_changes_evidence'
SC, SI, FI, DR = 'static_certain', 'static_inferred', 'framework_inferred', 'dynamic_required'
EXACT, UNIQUE, AMBIGUOUS, UNRESOLVED = 'exact', 'unique_name', 'ambiguous', 'unresolved'
CANDIDATE_KEYS = {'kind', 'target', 'metrics', 'evidence'}


def file_node(path):
    return GraphNode(id='file:' + path, label=path, group='file', category='file', kind='file', language=Path(path).suffix.lstrip('.'),
                     symbol_path=path, span=SourceSpan(path, 1, 50), cost=NodeCost(1, 1, 50), flags=path_flags(path),
                     provenance='file-aggregation', metadata={'file_path': path, 'granularity': 'file'})


def sym(ident, path, kind='function', name=None, signature=None, line=1, provenance='python-core', metadata=None):
    name = name or ident.split('#')[-1].split('.')[-1]
    return GraphNode(id=ident, label=name, group=kind, category=kind, kind=kind, language='python', span=SourceSpan(path, line, line + 1),
                     cost=NodeCost(1, 1, 2), signature=signature, symbol_path=ident, flags=path_flags(path), provenance=provenance,
                     metadata=dict(metadata or {}))


def rel(source, target, relation='CALLS', confidence=SC, resolution=EXACT, candidates=(), path=None, line=1):
    return GraphEdge(source, target, relation, confidence=confidence, resolution=resolution, candidates=list(candidates),
                     evidence=SourceSpan(path, line, line) if path else None)


def arch(nodes, edges=()):
    by_id = {n.id: n for n in nodes}
    paths = []
    for n in nodes:
        if n.span.file_path not in paths:
            paths.append(n.span.file_path)
    owners = {n.id: None for n in nodes}
    for e in edges:
        if ownership_edge(e, by_id) and e.relation != 'IMPLEMENTED_BY':
            owners[e.to_id] = e.from_id
        elif e.relation == 'IMPLEMENTED_BY':
            owners[e.from_id] = e.to_id
    node_files = {n.id: 'file:' + n.span.file_path for n in nodes}
    file_nodes = {'file:' + p: [n.id for n in nodes if n.span.file_path == p] for p in paths}
    details = {'nodes': [node_to_dict(n) for n in nodes], 'edges': [edge_to_dict(e) for e in edges], 'node_files': node_files,
               'node_owners': owners, 'file_nodes': file_nodes}
    return FileArchitecture('t', '/t', [file_node(p) for p in paths], [], {}, [], details, 'file')


def by_id(entries):
    return {e['id']: e for e in entries}


def nest(kind, name, path, line=1, global_=None, unsupported=None, provenance='nestjs'):
    metadata = {}
    if kind == 'module':
        metadata = {'global': bool(global_), 'unsupported_fields': list(unsupported or [])}
    return sym(f'nestjs:{kind}:{path}#{name}', path, kind=kind, name=name, line=line, provenance=provenance, metadata=metadata)


def nest_id(kind, name, path):
    return f'nestjs:{kind}:{path}#{name}'


def row_of(entry, file_ids):
    values = dict(entry)
    values['file'] = file_ids.index(entry['file'])
    return [values[c] for c in SYMBOL_COLUMNS]


def entry(ident, file='file:a.py', kind='function', name=None, signature='def f(x)', visibility='public', refs=0, uncertain=0):
    return {'id': ident, 'file': file, 'kind': kind, 'name': name or ident.split('#')[-1], 'signature': signature,
            'visibility': visibility, 'external_refs': refs, 'uncertain_external_refs': uncertain}


def sym_payload(entries=None, candidates=(), extra_files=(), **kwargs):
    data = payload(candidates=candidates, **kwargs)
    if entries is not None:
        file_ids = sorted({e['file'] for e in entries} | set(extra_files))
        data['dependency_network']['file_ids'] = file_ids
        data['dependency_network']['symbol_columns'] = list(SYMBOL_COLUMNS)
        data['dependency_network']['symbols'] = [row_of(e, file_ids) for e in entries]
    return data


def decode_rows(data):
    network = data['dependency_network']
    out = []
    for row in network['symbols']:
        item = dict(zip(network['symbol_columns'], row))
        item['file'] = network['file_ids'][item['file']]
        out.append(item)
    return out


def assert_symbol_additions(data):
    network = data['dependency_network']
    assert network['symbol_columns'] == SYMBOL_COLUMNS
    assert network['symbols'], 'symbol table is empty'
    assert all(len(row) == len(SYMBOL_COLUMNS) for row in network['symbols'])
    assert {k for k in decode_rows(data)[0]} == SYMBOL_ENTRY_KEYS


def cli_args(root, out, lang, *extra, bottlenecks='b.json', json_output=False):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    args = [root, *lang, '--granularity', 'file', '-o', out / 'r.html', '--bottlenecks', out / bottlenecks]
    if json_output:
        args.append('--json')
    return [*args, *extra]


def run_cli(args, cwd=REPO, seed='0'):
    return subprocess.run([sys.executable, '-c', MAIN, *map(str, args)], cwd=cwd, env=dict(os.environ, PYTHONHASHSEED=seed),
                          capture_output=True, text=True)


def analyze(root, out, lang, *extra):
    done = run_cli(cli_args(root, out, lang, *extra))
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads((Path(out) / 'b.json').read_text(encoding='utf-8'))


def table_of(bottlenecks):
    return decode_rows(bottlenecks)


def find(entries, name, file=None, kind=None):
    found = [e for e in entries if e['name'] == name and (file is None or e['file'] == file) and (kind is None or e['kind'] == kind)]
    assert len(found) == 1, (name, file, [e['id'] for e in found])
    return found[0]


def candidates_of(bottlenecks, kind):
    return [c for c in bottlenecks['candidates'] if c['kind'] == kind]


def delta_lines(done):
    out = [line for line in done.stdout.splitlines() if line.startswith('[Δ] Symbol changes')]
    err = [line for line in done.stderr.splitlines() if 'symbol changes not compared' in line]
    return out, err


def baseline_then_edit(tmp_path, files, lang, edit):
    root = tmp_path / 'repo'
    make_repo(root, files)
    analyze(root, tmp_path / 'base', lang)
    edit(root)
    return root, tmp_path / 'base' / 'b.json'


def delta_run(root, baseline, tmp_path, lang, *extra):
    done = run_cli(cli_args(root, tmp_path / 'out', lang, '--baseline', baseline, *extra))
    assert done.returncode == 0, done.stderr[-2000:]
    return done, json.loads((tmp_path / 'out' / 'b.json').read_text(encoding='utf-8'))


def base_worktree(tmp_dir):
    target = Path(tmp_dir) / 'base-worktree'
    git(REPO, 'worktree', 'add', '--detach', target, BASE_COMMIT)
    return target


def remove_worktree(path):
    git(REPO, 'worktree', 'remove', '--force', path, check=False)
    shutil.rmtree(path, ignore_errors=True)
    git(REPO, 'worktree', 'prune', check=False)

