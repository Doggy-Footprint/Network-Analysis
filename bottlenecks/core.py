import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Tuple

from analysis.edge_weights import EdgeWeights
from analysis.graph_metrics import GraphAnalysisConfig, GraphAnalyzer
from repository.models import RepositorySnapshot


class BottleneckInputError(ValueError): pass


@dataclass(frozen=True)
class BottleneckReport:
    schema: str; snapshot: Mapping[str, Any]; edge_weights: Mapping[str, Any]; versions: Mapping[str, Any]
    coverage: Mapping[str, Any]; dependency_network: Mapping[str, Any]
    candidates: Tuple[Mapping[str, Any], ...]; limitations: Tuple[str, ...]


RANKING_KEYS = (
    "pagerank", "hub_score", "authority_score", "degree_centrality", "betweenness_centrality",
    "weighted_centrality_cost", "fan_in", "fan_out", "weighted_fan_in", "weighted_fan_out",
    "hop_2_token_cost", "hop_3_token_cost",
)


def _lines(text: str) -> list[str]:
    lines = text.split("\n")
    return lines[:-1] if text.endswith("\n") else lines


def _valid_int(value: Any, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _snapshot(snapshot: RepositorySnapshot) -> None:
    if not isinstance(snapshot, RepositorySnapshot) or not isinstance(snapshot.digest, str) or not snapshot.digest or not isinstance(snapshot.contents, tuple):
        raise BottleneckInputError("snapshot is invalid")
    if any(not isinstance(row, tuple) or len(row) != 2 or not isinstance(row[0], str) or not row[0] or not isinstance(row[1], str) for row in snapshot.contents) or len({row[0] for row in snapshot.contents}) != len(snapshot.contents):
        raise BottleneckInputError("snapshot contents are invalid")


def _validate(snapshot: RepositorySnapshot, architecture: Any) -> tuple[list[Any], list[Any], set[tuple[str, str]]]:
    if not hasattr(architecture, "nodes") or not hasattr(architecture, "edges") or (getattr(architecture, "snapshot_digest", None) is not None and architecture.snapshot_digest != snapshot.digest): raise BottleneckInputError("architecture is invalid")
    nodes, edges, paths = list(architecture.nodes), list(architecture.edges), set(snapshot.content_map())
    ids = [getattr(node, "id", None) for node in nodes]
    if not all(isinstance(item, str) and item for item in ids) or len(ids) != len(set(ids)): raise BottleneckInputError("architecture node ids are invalid")
    node_ids = set(ids)
    for node in nodes:
        span, cost = getattr(node, "span", None), getattr(node, "cost", None)
        if span is not None and (getattr(span, "file_path", None) not in paths or not _valid_int(getattr(span, "start_line", None), 1) or not _valid_int(getattr(span, "end_line", None), span.start_line) or span.end_line > len(_lines(snapshot.content_map()[span.file_path])) + int(snapshot.content_map()[span.file_path].endswith("\n"))): raise BottleneckInputError("node span is outside snapshot")
        if cost is not None and not _valid_int(getattr(cost, "token_estimate", None)): raise BottleneckInputError("node cost is invalid")
    pairs = set()
    for edge in edges:
        source, target = getattr(edge, "from_id", None), getattr(edge, "to_id", None)
        if source not in node_ids or target not in node_ids or any(item not in node_ids for item in getattr(edge, "candidates", ())): raise BottleneckInputError("edge reference is outside architecture")
        if source != target: pairs.add((source, target))
    return nodes, edges, pairs


def _candidate(identifier: str, kind: str, target: str, metrics: Mapping[str, Any], evidence: Any, coverage: str) -> Mapping[str, Any]:
    return {"id": "b:" + hashlib.sha256(identifier.encode()).hexdigest()[:16], "kind": kind, "target": target, "metrics": dict(metrics), "evidence": evidence, "coverage": coverage, "status": "static_candidate"}


def _candidates(architecture: Any, threshold: int) -> list[Mapping[str, Any]]:
    candidates = []
    by_target = {}
    for edge in architecture.edges:
        if getattr(edge, "evidence", None) is not None: by_target.setdefault(edge.to_id, []).append(edge)
        if str(getattr(edge, "resolution", "")) == "unresolved" or str(getattr(edge, "confidence", "")) == "dynamic_required": candidates.append(_candidate(f"{edge.from_id}|{edge.to_id}|boundary", "unresolved_boundary", edge.to_id, {}, {"from_id": edge.from_id, "to_id": edge.to_id, "relation": str(getattr(edge, "relation", ""))}, "static_analyzer_relation"))
    for node in architecture.nodes:
        metadata = getattr(node, "metadata", {}) or {}
        unresolved = metadata.get("unresolved_references", [])
        if unresolved or any(str(flag).startswith("dynamic_") for flag in (getattr(node, "flags", ()) or ())):
            candidates.append(_candidate(node.id + "|boundary", "unresolved_boundary", node.id, {"unresolved_count": len(unresolved)}, list(unresolved), "static_analyzer_relation"))
        span = getattr(node, "span", None)
        if span is not None and span.end_line - span.start_line + 1 > threshold:
            candidates.append(_candidate(node.id + "|large_node", "large_node", node.id, {"line_count": span.end_line - span.start_line + 1, "line_threshold": threshold}, {"path": span.file_path, "start_line": span.start_line, "end_line": span.end_line}, "architecture_node_span"))
    for target, edges in sorted(by_target.items()):
        paths = {edge.evidence.file_path for edge in edges}; span = max(edge.evidence.end_line for edge in edges) - min(edge.evidence.start_line for edge in edges) + 1 if len(paths) == 1 else 0
        if len(paths) > 1 or span > threshold: candidates.append(_candidate(target + "|spread", "evidence_spread", target, {"file_count": len(paths), "line_span": span, "line_threshold": threshold}, [{"path": edge.evidence.file_path, "start_line": edge.evidence.start_line, "end_line": edge.evidence.end_line} for edge in edges], "static_analyzer_relation"))
    return sorted({item["id"]: item for item in candidates}.values(), key=lambda item: (item["kind"], item["id"]))


def analyze_bottlenecks(snapshot: RepositorySnapshot, architecture: Any, weights: EdgeWeights) -> BottleneckReport:
    try:
        if not isinstance(weights, EdgeWeights): raise BottleneckInputError("edge weights are invalid")
        _snapshot(snapshot); nodes, edges, pairs = _validate(snapshot, architecture)
        analysis = GraphAnalyzer(GraphAnalysisConfig(edge_weights=weights)).analyze(nodes, edges, getattr(architecture, "project_path", None)); metrics = analysis["node_metrics"]
        rankings = {key: [{"node_id": node_id, "value": metrics[node_id][key]} for node_id in sorted(metrics, key=lambda item: (-metrics[item][key], item))[:10]] for key in RANKING_KEYS}
        candidates = _candidates(architecture, weights.large_node_line_threshold)
        payload = {"id": weights.id, "version": weights.version, "content_hash": weights.content_hash, "confidence": dict(weights.confidence), "resolution": dict(weights.resolution), "large_node_line_threshold": weights.large_node_line_threshold}
        fallback = any(getattr(node, "span", None) is None and getattr(node, "cost", None) is None for node in nodes); limitations = ["Token cost fallback applies to nodes without a source span or explicit cost."] if fallback else []
        return BottleneckReport("bottlenecks.v3", {"digest": snapshot.digest, "file_count": len(snapshot.contents), "ignore_source": snapshot.ignore_source}, payload, {"analysis": "3"}, {"source_file_count": len(snapshot.contents), "limitations": limitations}, {"node_count": len(nodes), "edge_count": len(pairs), "node_metrics": {item: metrics[item] for item in sorted(metrics)}, "rankings": rankings, "betweenness_strategy": analysis["betweenness_strategy"], "betweenness_sample_size": analysis["betweenness_sample_size"]}, tuple(candidates), tuple(limitations))
    except BottleneckInputError: raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc: raise BottleneckInputError("analysis input structure is invalid") from exc


def bottlenecks_to_json(report: BottleneckReport) -> str:
    if not isinstance(report, BottleneckReport): raise BottleneckInputError("report has an invalid type")
    try: return json.dumps(asdict(report), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc: raise BottleneckInputError("report contains non-JSON values") from exc
