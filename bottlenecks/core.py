import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Tuple

from agent_view.models import AgentViewGraph, RepositorySnapshot
from analysis.graph_metrics import GraphAnalysisConfig, GraphAnalyzer


class HarnessProfileError(ValueError): pass
class BottleneckInputError(ValueError): pass


@dataclass(frozen=True)
class HarnessProfile:
    schema: str; id: str; version: int; provenance_status: str
    content_search: Mapping[str, Any]; path_search: Mapping[str, Any]
    read: Mapping[str, Any]; features: Mapping[str, str]; assumptions: Mapping[str, Any]


@dataclass(frozen=True)
class Probe:
    id: str; kind: str; surface: str; term: str; scope: str = "repository"
    path: Optional[str] = None; start_line: Optional[int] = None; end_line: Optional[int] = None


@dataclass(frozen=True)
class ProbeOutput:
    probe_id: str; rows: Tuple[Mapping[str, Any], ...]; total_count: int; visible_count: int
    truncated: bool; omitted_count: int = 0


@dataclass(frozen=True)
class BottleneckReport:
    schema: str; snapshot: Mapping[str, Any]; profile: Mapping[str, Any]; versions: Mapping[str, Any]
    coverage: Mapping[str, Any]; dependency_network: Mapping[str, Any]; exploration_network: Mapping[str, Any]
    probes: Tuple[Mapping[str, Any], ...]; candidates: Tuple[Mapping[str, Any], ...]; limitations: Tuple[str, ...]


def _lines(text: str) -> list[str]:
    lines = text.split("\n")
    return lines[:-1] if text.endswith("\n") else lines


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping): raise HarnessProfileError(f"{path} must be an object")
    return value


def _valid_int(value: Any, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _snapshot(snapshot: RepositorySnapshot) -> None:
    if not isinstance(snapshot, RepositorySnapshot) or not isinstance(snapshot.digest, str) or not snapshot.digest or not isinstance(snapshot.contents, tuple):
        raise BottleneckInputError("snapshot is invalid")
    if any(not isinstance(row, tuple) or len(row) != 2 or not isinstance(row[0], str) or not row[0] or not isinstance(row[1], str) for row in snapshot.contents) or len({row[0] for row in snapshot.contents}) != len(snapshot.contents):
        raise BottleneckInputError("snapshot contents are invalid")


def parse_harness_profile(data: Mapping[str, object]) -> HarnessProfile:
    obj = _mapping(data, "$")
    required = {"schema", "id", "version", "provenance_status", "content_search", "path_search", "read", "features", "assumptions"}
    if set(obj) != required or obj["schema"] != "harness_profile.v1" or not isinstance(obj["id"], str) or not obj["id"] or not _valid_int(obj["version"], 1) or obj["provenance_status"] != "unverified_baseline":
        raise HarnessProfileError("profile identity is invalid")
    content, path, read = _mapping(obj["content_search"], "$.content_search"), _mapping(obj["path_search"], "$.path_search"), _mapping(obj["read"], "$.read")
    for item, cap in ((content, "matching_lines"), (path, "matching_paths")):
        if item.get("matching") != "fixed_string_case_sensitive" or item.get("order") != "path_lexical_then_numeric_line" or item.get("cap_unit") != cap or not _valid_int(item.get("visible_lines"), 1):
            raise HarnessProfileError("search profile is unsupported")
    if set(content) != {"matching", "order", "visible_lines", "cap_unit", "same_line_occurrences"} or content.get("same_line_occurrences") != "preserved" or set(path) != {"matching", "order", "visible_lines", "cap_unit"}:
        raise HarnessProfileError("search profile fields are invalid")
    if set(read) != {"bounds", "max_lines", "eof", "truncation"} or read.get("bounds") != "one_based_inclusive" or read.get("eof") != "clamp" or read.get("truncation") != "actual_omitted_lines" or not _valid_int(read.get("max_lines"), 1):
        raise HarnessProfileError("read profile is unsupported")
    features, assumptions = _mapping(obj["features"], "$.features"), _mapping(obj["assumptions"], "$.assumptions")
    expected = {"fixed_string_search": "supported", "line_range_read": "supported", "semantic_search": "unsupported", "index": "unsupported", "context_compaction": "observation_only", "parallelism": "observation_only", "subagents": "observation_only"}
    if dict(features) != expected or set(assumptions) != {"automatic_injection", "list_depth"} or assumptions.get("automatic_injection") != "unverified_baseline" or not _valid_int(assumptions.get("list_depth")):
        raise HarnessProfileError("profile features or assumptions are unsupported")
    return HarnessProfile(obj["schema"], obj["id"], obj["version"], obj["provenance_status"], dict(content), dict(path), dict(read), dict(features), dict(assumptions))


def replay_probe(snapshot: RepositorySnapshot, probe: Probe, profile: HarnessProfile) -> ProbeOutput:
    _snapshot(snapshot)
    if not isinstance(probe, Probe) or not isinstance(profile, HarnessProfile): raise BottleneckInputError("probe or profile is invalid")
    try: profile = parse_harness_profile(asdict(profile))
    except (HarnessProfileError, TypeError) as exc: raise BottleneckInputError("profile is invalid") from exc
    if not isinstance(probe.id, str) or not probe.id: raise BottleneckInputError("probe id is invalid")
    contents = snapshot.content_map()
    if probe.surface == "read":
        if not isinstance(probe.path, str) or probe.path not in contents or not _valid_int(probe.start_line, 1) or not _valid_int(probe.end_line, probe.start_line): raise BottleneckInputError("read probe is invalid")
        available = min(probe.end_line, len(_lines(contents[probe.path])))
        end = min(available, probe.start_line + profile.read["max_lines"] - 1)
        visible, total = max(0, end - probe.start_line + 1), max(0, available - probe.start_line + 1)
        rows = () if not visible else ({"path": probe.path, "start_line": probe.start_line, "end_line": end, "text": "\n".join(_lines(contents[probe.path])[probe.start_line - 1:end])},)
        return ProbeOutput(probe.id, rows, total, visible, total > visible, total - visible)
    if probe.kind not in {"exact", "derived", "refinement", "list"} or probe.surface not in {"content", "path"} or not isinstance(probe.term, str) or not isinstance(probe.scope, str) or (probe.kind != "list" and not probe.term): raise BottleneckInputError("search probe is invalid")
    rows = []
    for path, text in snapshot.contents:
        if probe.surface == "path" and probe.term in path: rows.append({"path": path, "line": 1, "text": path, "occurrences": path.count(probe.term)})
        if probe.surface == "content":
            rows.extend({"path": path, "line": line, "text": value, "occurrences": value.count(probe.term)} for line, value in enumerate(_lines(text), 1) if probe.term in value)
    rows.sort(key=lambda row: (row["path"], row["line"]))
    limit = profile.content_search["visible_lines"] if probe.surface == "content" else profile.path_search["visible_lines"]
    return ProbeOutput(probe.id, tuple(rows[:limit]), len(rows), min(len(rows), limit), len(rows) > limit, max(0, len(rows) - limit))


def _probe_id(query: Any) -> str:
    return "p:" + hashlib.sha256(f"{query.kind}|{query.surface}|{query.term}|{query.scope}".encode()).hexdigest()[:16]


def _validate(snapshot: RepositorySnapshot, architecture: Any, graph: AgentViewGraph) -> tuple[list[Any], list[Any], set[tuple[str, str]]]:
    if not isinstance(graph, AgentViewGraph) or not hasattr(architecture, "nodes") or not hasattr(architecture, "edges") or graph.scan.snapshot_digest != snapshot.digest or (getattr(architecture, "snapshot_digest", None) is not None and architecture.snapshot_digest != snapshot.digest): raise BottleneckInputError("architecture or agent-view graph is invalid")
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
    readable, queries = {item.id for item in graph.readable_nodes}, {item.id for item in graph.query_nodes}
    if len(readable) != len(graph.readable_nodes) or len(queries) != len(graph.query_nodes): raise BottleneckInputError("agent-view ids are invalid")
    if any(item.file_path not in paths or (item.symbol_id is not None and item.symbol_id not in node_ids) for item in graph.readable_nodes): raise BottleneckInputError("readable node reference is invalid")
    blocks = {item.id: item for item in graph.occurrence_store}
    if any(any(value not in readable for value in item.origin_node_ids + item.arrival_node_ids) or any(span.block_id not in blocks or not _valid_int(span.start) or not _valid_int(span.count) or span.start + span.count > blocks[span.block_id].count for span in item.occurrence_ranges) for item in graph.query_nodes) or any(item.from_id not in readable | queries or item.to_id not in readable | queries for item in graph.connections): raise BottleneckInputError("agent-view reference is invalid")
    return nodes, edges, pairs


def _candidate(identifier: str, kind: str, target: str, probe_ids: list[str], metrics: Mapping[str, Any], evidence: Any, coverage: str) -> Mapping[str, Any]:
    return {"id": "b:" + hashlib.sha256(identifier.encode()).hexdigest()[:16], "kind": kind, "target": target, "probe_ids": probe_ids, "metrics": dict(metrics), "evidence": evidence, "coverage": coverage, "status": "static_candidate"}


def _probes_and_candidates(snapshot: RepositorySnapshot, architecture: Any, graph: AgentViewGraph, profile: HarnessProfile) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    probes, candidates = [], []
    for query in sorted(graph.query_nodes, key=lambda item: item.id):
        if query.kind not in {"exact", "derived", "refinement", "list"} or query.surface not in {"content", "path"}: continue
        probe = Probe(_probe_id(query), query.kind, query.surface, query.term, query.scope); output = replay_probe(snapshot, probe, profile)
        probes.append({"probe": asdict(probe), "output": asdict(output)})
        base = {"total_count": output.total_count, "visible_count": output.visible_count, "omitted_count": output.omitted_count}
        if output.truncated: candidates.append(_candidate(probe.id + "|truncation", "output_truncation", query.term, [probe.id], base, list(output.rows), "static_profile_probe"))
        if output.total_count > 1: candidates.append(_candidate(probe.id + "|multiple", "multiple_results", query.term, [probe.id], base, list(output.rows), "static_profile_probe"))
    for node in sorted(graph.readable_nodes, key=lambda item: item.id):
        if node.start_line is not None and node.end_line is not None and node.end_line - node.start_line + 1 > profile.read["max_lines"]:
            candidates.append(_candidate(node.id + "|read", "read_limit", node.id, [], {"line_count": node.end_line - node.start_line + 1, "read_line_limit": profile.read["max_lines"]}, {"path": node.file_path, "start_line": node.start_line, "end_line": node.end_line}, "readable_nodes"))
    by_target = {}
    for edge in architecture.edges:
        if getattr(edge, "evidence", None) is not None: by_target.setdefault(edge.to_id, []).append(edge)
        if str(getattr(edge, "resolution", "")) == "unresolved" or str(getattr(edge, "confidence", "")) == "dynamic_required": candidates.append(_candidate(f"{edge.from_id}|{edge.to_id}|boundary", "unresolved_boundary", edge.to_id, [], {}, {"from_id": edge.from_id, "to_id": edge.to_id, "relation": str(getattr(edge, "relation", ""))}, "static_analyzer_relation"))
    for node in architecture.nodes:
        metadata = getattr(node, "metadata", {}) or {}
        unresolved = metadata.get("unresolved_references", [])
        if unresolved or any(str(flag).startswith("dynamic_") for flag in (getattr(node, "flags", ()) or ())):
            candidates.append(_candidate(node.id + "|boundary", "unresolved_boundary", node.id, [], {"unresolved_count": len(unresolved)}, list(unresolved), "static_analyzer_relation"))
    for target, edges in sorted(by_target.items()):
        paths = {edge.evidence.file_path for edge in edges}; span = max(edge.evidence.end_line for edge in edges) - min(edge.evidence.start_line for edge in edges) + 1 if len(paths) == 1 else 0
        if len(paths) > 1 or span > profile.read["max_lines"]: candidates.append(_candidate(target + "|spread", "evidence_spread", target, [], {"file_count": len(paths), "line_span": span, "read_line_limit": profile.read["max_lines"]}, [{"path": edge.evidence.file_path, "start_line": edge.evidence.start_line, "end_line": edge.evidence.end_line} for edge in edges], "static_analyzer_relation"))
    return probes, sorted({item["id"]: item for item in candidates}.values(), key=lambda item: (item["kind"], item["id"]))


def analyze_bottlenecks(snapshot: RepositorySnapshot, architecture: Any, graph: AgentViewGraph, profile: HarnessProfile) -> BottleneckReport:
    try:
        profile = parse_harness_profile(asdict(profile)); _snapshot(snapshot); nodes, edges, pairs = _validate(snapshot, architecture, graph)
        analysis = GraphAnalyzer(GraphAnalysisConfig()).analyze(nodes, edges, getattr(architecture, "project_path", None)); metrics = analysis["node_metrics"]
        keys = ("pagerank", "hub_score", "authority_score", "degree_centrality", "betweenness_centrality", "weighted_centrality_cost", "fan_in", "fan_out", "hop_2_token_cost", "hop_3_token_cost")
        rankings = {key: [{"node_id": node_id, "value": metrics[node_id][key]} for node_id in sorted(metrics, key=lambda item: (-metrics[item][key], item))[:10]] for key in keys}
        probes, candidates = _probes_and_candidates(snapshot, architecture, graph, profile)
        payload = asdict(profile); payload["content_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        fallback = any(getattr(node, "span", None) is None and getattr(node, "cost", None) is None for node in nodes); limitations = ["Token cost fallback applies to nodes without a source span or explicit cost."] if fallback else []
        return BottleneckReport("bottlenecks.v2", {"digest": snapshot.digest, "file_count": len(snapshot.contents), "ignore_source": snapshot.ignore_source}, payload, {"analysis": "2", "agent_view_schema": graph.schema_version}, {"source_file_count": len(snapshot.contents), "generated_probe_count": len(probes), "limitations": limitations}, {"node_count": len(nodes), "edge_count": len(pairs), "node_metrics": {item: metrics[item] for item in sorted(metrics)}, "rankings": rankings, "betweenness_strategy": analysis["betweenness_strategy"], "betweenness_sample_size": analysis["betweenness_sample_size"]}, {"readable_node_count": len(graph.readable_nodes), "query_node_count": len(graph.query_nodes), "connection_count": len(graph.connections), "profile_exposure": {"search_output_limit": profile.content_search["visible_lines"], "read_line_limit": profile.read["max_lines"]}}, tuple(sorted(probes, key=lambda item: item["probe"]["id"])), tuple(candidates), tuple(limitations))
    except BottleneckInputError: raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc: raise BottleneckInputError("analysis input structure is invalid") from exc


def bottlenecks_to_json(report: BottleneckReport) -> str:
    if not isinstance(report, BottleneckReport): raise BottleneckInputError("report has an invalid type")
    try: return json.dumps(asdict(report), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc: raise BottleneckInputError("report contains non-JSON values") from exc
