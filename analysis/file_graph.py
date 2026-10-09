from copy import deepcopy
from analysis.candidate_projection import candidate_projection, candidate_targets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from language_analyzers.core.cost import estimate_tokens
from language_analyzers.core.flags import path_flags
from language_analyzers.core.graph_models import GraphNode, GraphEdge, NodeCost, SourceSpan
from language_analyzers.core.serialization import node_to_dict, edge_to_dict
from repository.models import RepositorySnapshot


@dataclass
class FileArchitecture:
    project_name: str
    project_path: str
    nodes: List[Any] = field(default_factory=list)
    edges: List[Any] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    report_collections: List[Any] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    granularity: str = "file"


_DECLARATION_KINDS = {"package", "module", "file", "class", "interface", "enum", "function", "method", "field", "constant", "type_alias"}
_LANGUAGE_PROVENANCE = {"python-core", "typescript-core", "kotlin-core"}


def ownership_edge(edge: Any, nodes: Dict[str, Any]) -> bool:
    if edge.relation == "IMPLEMENTED_BY":
        return True
    source, target = nodes[edge.from_id], nodes[edge.to_id]
    return (edge.relation in {"CONTAINS", "DECLARES", "EXPORTS"}
            and getattr(source, "provenance", "") in _LANGUAGE_PROVENANCE
            and getattr(target, "provenance", "") in _LANGUAGE_PROVENANCE
            and (getattr(source, "kind", "") or getattr(source, "category", "")) in _DECLARATION_KINDS
            and (getattr(target, "kind", "") or getattr(target, "category", "")) in _DECLARATION_KINDS)


def to_file_architecture(architecture: Any, snapshot: RepositorySnapshot) -> FileArchitecture:
    from bottlenecks.core import _snapshot, _validate, BottleneckInputError
    _snapshot(snapshot)
    nodes, edges, _pairs = _validate(snapshot, architecture)
    root = Path(snapshot.root)
    if not root.is_absolute() or Path(architecture.project_path) != root:
        raise BottleneckInputError("project path and snapshot root must be absolute and match")
    contents = snapshot.source_map
    by_id = {node.id: node for node in nodes}
    files = {}
    owners = {node.id: None for node in nodes}

    def valid_path(raw):
        if not isinstance(raw, str) or not raw:
            return None
        path = Path(raw)
        if path.is_absolute():
            try:
                path = path.relative_to(root)
            except ValueError:
                return None
        key = path.as_posix()
        return key if key in contents else None

    for node in nodes:
        span = getattr(node, "span", None)
        path = valid_path(span.file_path) if span is not None else None
        files[node.id] = path or valid_path((getattr(node, "metadata", {}) or {}).get("file_path"))
    direct = {node_id for node_id, path in files.items() if path is not None}
    implementations = {}
    parents = {}
    for edge in edges:
        if not ownership_edge(edge, by_id):
            continue
        if edge.relation == "IMPLEMENTED_BY":
            implementations.setdefault(edge.from_id, []).append(edge.to_id)
            owners[edge.from_id] = edge.to_id
        else:
            parents.setdefault(edge.to_id, []).append(edge.from_id)
            if owners[edge.to_id] is not None and owners[edge.to_id] != edge.from_id:
                raise BottleneckInputError("conflicting declaration owners")
            owners[edge.to_id] = edge.from_id
    # A package has members in many files but no containing source file of its own.
    for _ in range(len(nodes) + 1):
        changed = False
        for node in nodes:
            if node.id in direct:
                continue
            suppliers = implementations.get(node.id) or parents.get(node.id, [])
            choices = {files[item] for item in suppliers if files[item] is not None}
            if len(choices) > 1:
                raise BottleneckInputError("conflicting file ownership")
            if choices:
                path = next(iter(choices))
                if files[node.id] is not None and files[node.id] != path:
                    raise BottleneckInputError("conflicting file ownership")
                if files[node.id] is None:
                    files[node.id] = path
                    changed = True
        if not changed:
            break
    details_nodes = [deepcopy(node_to_dict(node)) for node in nodes]
    for item in details_nodes:
        item["metadata"].pop("analysis", None)
    file_nodes = {}
    output_nodes = []
    for node in nodes:
        path = files[node.id]
        if path is None:
            continue
        file_id = "file:" + path
        if file_id not in file_nodes:
            file_nodes[file_id] = []
            text = contents[path]
            line_count = len(snapshot.source_lines[path])
            output_nodes.append(GraphNode(
                id=file_id, label=path, group="file", category="file", kind="file",
                language=Path(path).suffix.lstrip("."), symbol_path=path,
                span=SourceSpan(path, 1, line_count) if line_count else None,
                cost=NodeCost(estimate_tokens(text), len(text), line_count),
                flags=path_flags(path), provenance="file-aggregation",
                metadata={"file_path": path, "granularity": "file"},
            ))
        file_nodes[file_id].append(node.id)
        file_node = next(item for item in output_nodes if item.id == file_id)
        for flag in getattr(node, "flags", []) or []:
            if flag in {"generated", "migration", "vendored"} and flag not in file_node.flags:
                file_node.flags.append(flag)
    node_files = {node_id: "file:" + path if path is not None else None for node_id, path in files.items()}
    dependency_edges = [(index, edge) for index, edge in enumerate(edges) if not ownership_edge(edge, by_id)]
    boundary_ids = {endpoint for _, edge in dependency_edges for endpoint in (edge.from_id, *candidate_targets(edge)) if node_files[endpoint] is None}
    for node in nodes:
        if node.id in boundary_ids:
            boundary = deepcopy(node)
            boundary.cost = NodeCost(0, 0, 0)
            boundary.metadata.pop("analysis", None)
            boundary.metadata.update(boundary=True, granularity="file")
            output_nodes.append(boundary)
    grouped = {}
    for index, edge in dependency_edges:
        source = node_files[edge.from_id] or edge.from_id
        projection = candidate_projection(edge, by_id)
        target_counts = {}
        for target_id, _share in projection:
            target = node_files[target_id] or target_id
            if source != target:
                target_counts[target] = target_counts.get(target, 0) + 1
        for target, count in target_counts.items():
            share = projection[0][1] if "candidate_share" in (edge.metadata or {}) else count / len(projection)
            key = (source, target, edge.relation, str(edge.confidence), str(edge.resolution))
            if key not in grouped:
                grouped[key] = GraphEdge(source, target, edge.relation, label=edge.label,
                                         confidence=edge.confidence, resolution=edge.resolution,
                                         metadata={"detail_edge_indices": [], "evidence_count": 0, "candidate_share": share})
            item = grouped[key].metadata
            item["candidate_share"] = max(item["candidate_share"], share)
            item["detail_edge_indices"].append(index)
            item["evidence_count"] += 1
    stats = deepcopy(getattr(architecture, "stats", {}) or {})
    stats.pop("analysis", None)
    stats.update(total_files=len(file_nodes), granularity="file")
    return FileArchitecture(architecture.project_name, architecture.project_path, output_nodes,
                            list(grouped.values()), stats, deepcopy(getattr(architecture, "report_collections", []) or []),
                            {"nodes": details_nodes, "edges": [deepcopy(edge_to_dict(edge)) for edge in edges],
                             "node_files": node_files, "node_owners": owners, "file_nodes": file_nodes})
