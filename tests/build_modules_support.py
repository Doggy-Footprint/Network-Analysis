"""Expected values in the tests are written out by hand from the spec Signatures; nothing here computes an expectation from the product."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from repository import RepositorySnapshot

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = Path(__file__).parent / 'build_modules_evidence'
ROOT = '/bm-oracle'
MAIN = 'from code_analyzer.cli import main; main()'
BASE_COMMIT = 'a8a301272683e61b3e1f669995f969564b9cb907'
PREFIX = 'build-module:'


def gid(path):
    return f'{PREFIX}gradle:{path}'


def nid(name):
    return f'{PREFIX}npm:{name}'


def gpkg(path):
    return f'pkg:gradle:{path}'


def npkg(name):
    return f'pkg:npm:{name}'


def value(item):
    return getattr(item, 'value', item)


def snapshot(files, root=ROOT):
    return RepositorySnapshot(root, 'snapshot.v1', tuple(sorted(files.items())), ())


def blank_architecture(root=ROOT):
    return SimpleNamespace(project_name='bm', project_path=root, nodes=[], edges=[], stats={}, report_collections=[])


def enriched(files, root=ROOT):
    from language_analyzers.core.enrichment import enrich_repository
    arch = blank_architecture(root)
    enrich_repository(arch, snapshot=snapshot(files, root))
    return arch


def module_nodes(arch):
    return [node for node in arch.nodes if node.id.startswith(PREFIX)]


def module_ids(arch, system=None):
    prefix = PREFIX if system is None else f'{PREFIX}{system}:'
    return {node.id for node in arch.nodes if node.id.startswith(prefix)}


def declared_edges(arch):
    return [edge for edge in arch.edges if value(edge.relation) == 'DECLARES_DEPENDENCY']


def edge_view(arch):
    """(from, to, resolution, configuration, evidence file, first line, last line) for every DECLARES_DEPENDENCY edge."""
    return {(e.from_id, e.to_id, value(e.resolution), e.metadata['configuration'], e.evidence.file_path,
             e.evidence.start_line, e.evidence.end_line) for e in declared_edges(arch)}


def node_by_id(arch, ident):
    found = [node for node in arch.nodes if node.id == ident]
    assert len(found) == 1, (ident, len(found))
    return found[0]


def file_architecture(files, source_paths=(), root=ROOT):
    """Enrich, then add one plain source node per path in source_paths so the file exists in the file graph."""
    from analysis.file_graph import to_file_architecture
    from tests.file_analysis_support import node
    arch = enriched(files, root)
    arch.nodes.extend(node('src:' + path, path) for path in source_paths)
    snap = snapshot(files, root)
    return snap, to_file_architecture(arch, snap)


def init_git(root):
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    subprocess.run(['git', 'add', '-A'], cwd=root, check=True)


def write_repo(root, files):
    root = Path(root)
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    init_git(root)
    return root


def run_cli(root, out_dir, *flags, name='r', extra=(), check=True, granularity='file'):
    """Runs the CLI in file granularity; returns (CompletedProcess, bottleneck payload or None, report json or None)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-c', MAIN, str(root), *flags, '--granularity', granularity, '--json',
               '-o', str(out / f'{name}.html'), '--bottlenecks', str(out / f'{name}_b.json'), *extra]
    done = subprocess.run(command, cwd=REPO, env=dict(os.environ, PYTHONHASHSEED='0'), capture_output=True, text=True)
    if check:
        assert done.returncode == 0, done.stderr[-2000:]
    bottlenecks = out / f'{name}_b.json'
    report = out / f'{name}.json'
    return (done, json.loads(bottlenecks.read_text(encoding='utf-8')) if bottlenecks.exists() else None,
            json.loads(report.read_text(encoding='utf-8')) if report.exists() else None)


def pairs_of(payload, scheme):
    return {(item['from_id'], item['to_id']) for item in payload['dependency_network']['package_dependencies'].get(scheme, [])}


def by_kind(payload, kind, scheme=None):
    return [c for c in payload['candidates'] if c['kind'] == kind and (scheme is None or c['structure']['scheme'] == scheme)]
