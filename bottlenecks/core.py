import hashlib
import json
import math
from pathlib import Path
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Tuple, Optional
from types import SimpleNamespace

from analysis.architecture_rules import ArchitectureRulesError
from analysis.edge_weights import EdgeWeights
from analysis.candidate_projection import AMBIGUITY_POLICY, candidate_projection, candidate_targets
from language_analyzers.core.serialization import edge_to_dict
from analysis.graph_metrics import GraphAnalysisConfig, GraphAnalyzer
from language_analyzers.core.flags import GENERATED, TEST, VENDORED, path_flags
from repository.models import RepositorySnapshot


class BottleneckInputError(ValueError): pass


@dataclass(frozen=True)
class BottleneckReport:
    schema: str; snapshot: Mapping[str, Any]; edge_weights: Mapping[str, Any]; versions: Mapping[str, Any]
    coverage: Mapping[str, Any]; dependency_network: Mapping[str, Any]
    candidates: Tuple[Mapping[str, Any], ...]; limitations: Tuple[str, ...]
    granularity: Optional[str] = None
    delta: Optional[Mapping[str, Any]] = None


RANKING_KEYS = (
    "pagerank", "betweenness_centrality", "weighted_centrality_cost", "fan_in", "fan_out",
    "weighted_fan_in", "weighted_fan_out", "hop_2_token_cost",
)

CATEGORY_KEYS = ("production", "test", "generated", "vendored", "unknown")


def _category(node: Any) -> str:
    span = getattr(node, "span", None)
    if span is None and not (getattr(node, "metadata", {}) or {}).get("granularity") == "file": return "unknown"
    flags = path_flags(span.file_path if span is not None else node.metadata.get("file_path", ""))
    return "vendored" if VENDORED in flags else "generated" if GENERATED in flags else "test" if TEST in flags else "production"


def _lines(text: str) -> list[str]:
    lines = text.split("\n")
    return lines[:-1] if text.endswith("\n") else lines


def _valid_int(value: Any, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _snapshot(snapshot: RepositorySnapshot) -> None:
    if not isinstance(snapshot, RepositorySnapshot) or not isinstance(snapshot.contents, tuple) or not isinstance(snapshot.root, str) or not Path(snapshot.root).is_absolute() or not isinstance(snapshot.ignore_source, str):
        raise BottleneckInputError("snapshot is invalid")
    if any(not isinstance(row, tuple) or len(row) != 2 or not isinstance(row[0], str) or not row[0] or not isinstance(row[1], str) for row in snapshot.contents) or len({row[0] for row in snapshot.contents}) != len(snapshot.contents):
        raise BottleneckInputError("snapshot contents are invalid")
    if any(Path(path).is_absolute() or ".." in Path(path).parts or Path(path).as_posix() != path or path == "." for path, _ in snapshot.contents):
        raise BottleneckInputError("snapshot paths must be repository-relative POSIX paths")


def _validate_structure(snapshot: RepositorySnapshot, architecture: Any) -> tuple[list[Any], list[Any], set[tuple[str, str]]]:
    if not hasattr(architecture, "nodes") or not hasattr(architecture, "edges"): raise BottleneckInputError("architecture is invalid")
    nodes, edges, contents = list(architecture.nodes), list(architecture.edges), snapshot.source_map
    paths = set(contents)
    if getattr(architecture, "granularity", None) == "file":
        line_bounds = {path: len(snapshot.source_lines[path]) for path in contents}
    else:
        line_bounds = {path: len(_lines(text)) + int(text.endswith("\n")) for path, text in contents.items()}
    ids = [getattr(node, "id", None) for node in nodes]
    if not all(isinstance(item, str) and item for item in ids) or len(ids) != len(set(ids)): raise BottleneckInputError("architecture node ids are invalid")
    node_ids = set(ids)
    for node in nodes:
        span, cost = getattr(node, "span", None), getattr(node, "cost", None)
        if span is not None and (getattr(span, "file_path", None) not in paths or not _valid_int(getattr(span, "start_line", None), 1) or not _valid_int(getattr(span, "end_line", None), span.start_line) or span.end_line > line_bounds[span.file_path]): raise BottleneckInputError("node span is outside snapshot")
        if cost is not None and not _valid_int(getattr(cost, "token_estimate", None)): raise BottleneckInputError("node cost is invalid")
    pairs = set()
    for edge in edges:
        source, target = getattr(edge, "from_id", None), getattr(edge, "to_id", None)
        if source not in node_ids or target not in node_ids or any(item not in node_ids for item in getattr(edge, "candidates", ())): raise BottleneckInputError("edge reference is outside architecture")
        for target, _share in candidate_projection(edge, node_ids):
            if source != target: pairs.add((source, target))
    return nodes, edges, pairs


def _validate(snapshot: RepositorySnapshot, architecture: Any):
    try:
        return _validate_structure(snapshot, architecture)
    except BottleneckInputError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise BottleneckInputError("architecture input structure is invalid") from exc


def _weights(weights):
    from language_analyzers.core.graph_models import Confidence, Resolution
    if not isinstance(weights, EdgeWeights):
        raise BottleneckInputError("edge weights are invalid")
    for table, members in ((weights.confidence, Confidence), (weights.resolution, Resolution)):
        if not isinstance(table, Mapping) or set(table) != {item.value for item in members}:
            raise BottleneckInputError("edge weight table is invalid")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 1 for value in table.values()):
            raise BottleneckInputError("edge weight value is invalid")
    if not _valid_int(weights.large_node_line_threshold, 1):
        raise BottleneckInputError("edge weight threshold is invalid")
    if not _valid_int(getattr(weights, "untested_hub_top_n", None), 1):
        raise BottleneckInputError("edge weight untested_hub_top_n is invalid")
    if not _valid_int(getattr(weights, "large_node_token_threshold", None), 1):
        raise BottleneckInputError("edge weight token threshold is invalid")


def _candidate(identifier: str, kind: str, target: str, metrics: Mapping[str, Any], evidence: Any, coverage: str) -> Mapping[str, Any]:
    return {"id": "b:" + hashlib.sha256(identifier.encode()).hexdigest()[:16], "kind": kind, "target": target, "metrics": dict(metrics), "evidence": evidence, "coverage": coverage, "status": "static_candidate"}


def _unresolved_count(metadata: Mapping[str, Any]) -> int:
    total = metadata.get("unresolved_reference_total")
    return total if _valid_int(total) else len(metadata.get("unresolved_references", []))


def _candidates(architecture: Any, threshold: int, token_threshold: int, metrics: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    from analysis.file_graph import ownership_edge
    candidates = []
    by_target = {}
    evidence_records = {}
    nodes_by_id = {node.id: node for node in architecture.nodes}
    for edge in architecture.edges:
        if getattr(edge, "evidence", None) is not None and not ownership_edge(edge, nodes_by_id):
            for target in candidate_targets(edge):
                by_target.setdefault(target, []).append(edge)
        if str(getattr(edge, "resolution", "")) == "unresolved" or str(getattr(edge, "confidence", "")) == "dynamic_required": candidates.append(_candidate(f"{edge.from_id}|{edge.to_id}|boundary", "unresolved_boundary", edge.to_id, {}, {"from_id": edge.from_id, "to_id": edge.to_id, "relation": str(getattr(edge, "relation", ""))}, "static_analyzer_relation"))
    for node in architecture.nodes:
        metadata = getattr(node, "metadata", {}) or {}
        unresolved = metadata.get("unresolved_references", [])
        if unresolved or any(str(flag).startswith("dynamic_") for flag in (getattr(node, "flags", ()) or ())):
            candidates.append(_candidate(node.id + "|boundary", "unresolved_boundary", node.id, {"unresolved_count": _unresolved_count(metadata)}, list(unresolved), "static_analyzer_relation"))
        span = getattr(node, "span", None)
        tokens = metrics[node.id]["token_cost"]
        if span is not None and (span.end_line - span.start_line + 1 > threshold or tokens > token_threshold):
            candidates.append(_candidate(node.id + "|large_node", "large_node", node.id, {"line_count": span.end_line - span.start_line + 1, "line_threshold": threshold, "token_count": tokens, "token_threshold": token_threshold}, {"path": span.file_path, "start_line": span.start_line, "end_line": span.end_line}, "architecture_node_span"))
    def evidence_record(edge):
        key = id(edge)
        if key not in evidence_records:
            evidence_records[key] = dict(edge_to_dict(edge) if str(edge.resolution) == "ambiguous" else {},
                path=edge.evidence.file_path, start_line=edge.evidence.start_line, end_line=edge.evidence.end_line)
        return evidence_records[key]

    for target, edges in sorted(by_target.items()):
        own = getattr(getattr(nodes_by_id[target], "span", None), "file_path", None)
        edges = [edge for edge in edges if edge.evidence.file_path != own]
        if not edges:
            continue
        paths = {edge.evidence.file_path for edge in edges}; span = max(edge.evidence.end_line for edge in edges) - min(edge.evidence.start_line for edge in edges) + 1 if len(paths) == 1 else 0
        if len(paths) > 1 or span > threshold: candidates.append(_candidate(target + "|spread", "evidence_spread", target, {"file_count": len(paths), "line_span": span, "line_threshold": threshold}, [evidence_record(edge) for edge in edges], "static_analyzer_relation"))
    return sorted({item["id"]: item for item in candidates}.values(), key=lambda item: (item["kind"], item["id"]))


def _file_candidates(architecture: Any, threshold: int, token_threshold: int, metrics: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    from analysis.file_graph import ownership_edge
    details = architecture.details
    node_files = details["node_files"]
    original_nodes = {node["id"]: SimpleNamespace(**node) for node in details["nodes"]}
    incoming = {}
    boundaries = {}
    for index, edge in enumerate(details["edges"]):
        if ownership_edge(SimpleNamespace(**edge), original_nodes):
            continue
        targets = set(node_files[target] or target for target in candidate_targets(edge))
        target = node_files[edge["to_id"]]
        evidence = edge.get("evidence")
        record = dict(edge, detail_edge_index=index)
        if evidence is not None:
            record.update(path=evidence["file_path"], start_line=evidence["start_line"], end_line=evidence["end_line"])
        if evidence is not None:
            for possible_target in targets:
                incoming.setdefault(possible_target, []).append(record)
        if edge.get("resolution") == "unresolved" or edge.get("confidence") == "dynamic_required":
            affected = target or node_files[edge["from_id"]]
            if affected is not None:
                boundaries.setdefault(affected, []).append(record)
    for node in details["nodes"]:
        target = node_files[node["id"]]
        if target is None:
            continue
        node_metadata = node.get("metadata", {})
        unresolved = node_metadata.get("unresolved_references", [])
        dynamic = [flag for flag in node.get("flags", []) if str(flag).startswith("dynamic_")]
        if unresolved or dynamic:
            record = {"node_id": node["id"], "unresolved_references": unresolved, "flags": dynamic}
            if "unresolved_reference_total" in node_metadata:
                record["unresolved_reference_total"] = node_metadata["unresolved_reference_total"]
            if node.get("span"):
                record.update(path=node["span"]["file_path"], start_line=node["span"]["start_line"], end_line=node["span"]["end_line"])
            boundaries.setdefault(target, []).append(record)
    candidates = []
    for node in architecture.nodes:
        if node.id not in details["file_nodes"]:
            continue
        count = node.cost.line_count
        tokens = metrics[node.id]["token_cost"]
        if count > threshold or tokens > token_threshold:
            candidates.append(_candidate(node.id + "|large_node", "large_node", node.id,
                {"line_count": count, "line_threshold": threshold, "token_count": tokens, "token_threshold": token_threshold},
                {"path": node.metadata["file_path"], "start_line": 1, "end_line": count}, "architecture_node_span"))
        if node.id in boundaries:
            records = boundaries[node.id]
            candidates.append(_candidate(node.id + "|boundary", "unresolved_boundary", node.id,
                {"unresolved_count": sum(_unresolved_count(record) for record in records)}, records, "static_analyzer_relation"))
        own = node.metadata["file_path"]
        records = [record for record in incoming.get(node.id, []) if record["evidence"]["file_path"] != own]
        if records:
            paths = {record["evidence"]["file_path"] for record in records}
            span = max(record["evidence"]["end_line"] for record in records) - min(record["evidence"]["start_line"] for record in records) + 1 if len(paths) == 1 else 0
            if len(paths) > 1 or span > threshold:
                candidates.append(_candidate(node.id + "|spread", "evidence_spread", node.id,
                    {"file_count": len(paths), "line_span": span, "line_threshold": threshold}, records, "static_analyzer_relation"))
    return sorted(candidates, key=lambda item: (item["kind"], item["id"]))


def _intern_candidate_groups(candidates):
    groups = {}
    group_ids = {}
    visited = set()
    for candidate in candidates:
        evidence = candidate["evidence"]
        for record in evidence if isinstance(evidence, list) else [evidence]:
            if not isinstance(record, dict) or id(record) in visited:
                continue
            visited.add(id(record))
            if record.get("resolution") != "ambiguous" or "candidates" not in record:
                continue
            key = (record["to_id"], tuple(record["candidates"]))
            group_id = group_ids.get(key)
            if group_id is None:
                group = {"to_id": record["to_id"], "candidates": record["candidates"]}
                encoded = json.dumps(group, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                group_id = "cg:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                group_ids[key] = group_id
                groups[group_id] = group
            record.pop("candidates")
            record["candidate_group_id"] = group_id
    return groups


def analyze_bottlenecks(snapshot: RepositorySnapshot, architecture: Any, weights: EdgeWeights, *, analysis: Optional[Mapping[str, Any]] = None, rules: Any = None) -> BottleneckReport:
    try:
        _weights(weights)
        _snapshot(snapshot); nodes, edges, pairs = _validate(snapshot, architecture)
        is_file = getattr(architecture, "granularity", None) == "file"
        if analysis is None:
            analysis = GraphAnalyzer(GraphAnalysisConfig(edge_weights=weights)).analyze(nodes, edges, getattr(architecture, "project_path", None))
        if analysis.get("ambiguity_policy") != AMBIGUITY_POLICY:
            raise BottleneckInputError("missing or unsupported analysis ambiguity_policy")
        metrics = analysis["node_metrics"]
        ranked_ids = [node.id for node in nodes if not is_file or not (getattr(node, "metadata", {}) or {}).get("boundary")]
        rankings = {key: [{"node_id": node_id, "value": metrics[node_id][key]} for node_id in sorted(ranked_ids, key=lambda item: (-metrics[item][key], item))[:10]] for key in RANKING_KEYS}
        categories = {node.id: _category(node) for node in nodes}
        rankings_by_category = {category: {key: [{"node_id": node_id, "value": metrics[node_id][key]} for node_id in sorted((item for item in ranked_ids if categories[item] == category), key=lambda item: (-metrics[item][key], item))[:10]] for key in RANKING_KEYS} for category in CATEGORY_KEYS}
        candidates = _file_candidates(architecture, weights.large_node_line_threshold, weights.large_node_token_threshold, metrics) if is_file else _candidates(architecture, weights.large_node_line_threshold, weights.large_node_token_threshold, metrics)
        structure = None
        if is_file:
            from analysis.structure import analyze_structure
            structure = analyze_structure(architecture, weights, rules)
            from bottlenecks.reach import reach_candidates
            reach = reach_candidates(architecture, metrics, weights.untested_hub_top_n)
            candidates = sorted(candidates + list(structure.candidates) + reach, key=lambda item: (item["kind"], item["id"]))
        candidate_groups = _intern_candidate_groups(candidates)
        payload = {"confidence": dict(weights.confidence), "resolution": dict(weights.resolution), "large_node_line_threshold": weights.large_node_line_threshold, "large_node_token_threshold": weights.large_node_token_threshold}
        if is_file:
            payload["untested_hub_top_n"] = weights.untested_hub_top_n
        fallback = any(getattr(node, "span", None) is None and getattr(node, "cost", None) is None for node in nodes); limitations = ["Token cost fallback applies to nodes without a source span or explicit cost."] if fallback else []
        coverage = {"source_file_count": len(snapshot.contents), "limitations": limitations}
        if (getattr(architecture, "stats", {}) or {}).get("analysis_coverage") is not None:
            coverage["analysis_coverage"] = architecture.stats["analysis_coverage"]
        network = {"ambiguity_policy": AMBIGUITY_POLICY, "node_count": len(nodes), "edge_count": len(pairs),
            "node_metrics": {item: metrics[item] for item in sorted(metrics)}, "rankings": rankings,
            "rankings_by_category": rankings_by_category, "betweenness_strategy": analysis["betweenness_strategy"],
            "betweenness_sample_size": analysis["betweenness_sample_size"]}
        if candidate_groups:
            network["candidate_groups"] = candidate_groups
        if structure is not None:
            from analysis.structure import STRUCTURE_POLICY
            network.update(package_metrics=structure.package_metrics, package_dependencies=structure.package_dependencies, structure_policy=STRUCTURE_POLICY); coverage.update(structure.coverage)
        return BottleneckReport("bottlenecks.v8" if is_file else "bottlenecks.v6", {"file_count": len(snapshot.contents), "ignore_source": snapshot.ignore_source}, payload, {"analysis": "5"}, coverage, network, tuple(candidates), tuple(limitations), "file" if is_file else None)
    except (BottleneckInputError, ArchitectureRulesError): raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc: raise BottleneckInputError("analysis input structure is invalid") from exc


def bottlenecks_to_json(report: BottleneckReport) -> str:
    if not isinstance(report, BottleneckReport): raise BottleneckInputError("report has an invalid type")
    try:
        payload = asdict(report)
        if report.granularity is None:
            payload.pop("granularity")
        if report.delta is None:
            payload.pop("delta")
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc: raise BottleneckInputError("report contains non-JSON values") from exc
