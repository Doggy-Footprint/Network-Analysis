import importlib
import json
from pathlib import Path

from fixtures.registry import fixture_root


ORACLE_PATH = Path(__file__).parent / "nestjs_evidence" / "fixture-oracle.json"


def oracle():
    return json.loads(ORACLE_PATH.read_text(encoding="utf-8"))


def analyze(root, *, snapshot=None, dependencies=True, language=False):
    package = importlib.import_module("framework_analyzers.nestjs")
    arch = package.NestJSAnalyzer(str(root), snapshot=snapshot).analyze()
    return package.NestJSGraphBuilder(
        include_dependencies=dependencies,
        include_language_graph=language,
        emit_language_graph=language,
        snapshot=snapshot,
    ).build_graph(arch)


def fixture():
    return fixture_root("typescript-nestjs-realworld")


def framework_nodes(arch, kind=None):
    result = [n for n in arch.nodes if str(n.id).startswith("nestjs:")]
    return [n for n in result if str(n.id).startswith(f"nestjs:{kind}:")] if kind else result


def node_name(node):
    return str(node.label)


def framework_edges(arch, relation=None):
    result = [e for e in arch.edges if str(e.from_id).startswith("nestjs:")]
    return [e for e in result if str(e.relation) == relation] if relation else result


def edge_names(arch, relation):
    by_id = {n.id: n for n in arch.nodes}
    missing = [(e.from_id, e.to_id) for e in framework_edges(arch, relation)
               if e.from_id not in by_id or e.to_id not in by_id]
    if missing:
        raise AssertionError(f"dangling {relation} edges: {missing}")
    return {(node_name(by_id[e.from_id]), node_name(by_id[e.to_id]))
            for e in framework_edges(arch, relation)
            }


def diagnostics(arch):
    return arch.stats["nestjs"]["diagnostics"]


def endpoint_data(arch):
    return {(n.metadata.get("http_method"), n.metadata.get("full_path"))
            for n in framework_nodes(arch, "endpoint")}


def write_project(root, files):
    for name, source in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
