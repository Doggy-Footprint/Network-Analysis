import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from agent_view.models import AgentViewGraph, RepositorySnapshot
from agent_view.occurrence import enclosing_node_id
from analysis.graph_metrics import GraphAnalysisConfig, pagerank
from language_analyzers.python.graph import PythonProjectArchitecture
from language_analyzers.core.graph_models import NodeKind


class HarnessProfileError(ValueError):
    pass


class ObservationTraceError(ValueError):
    pass


class BottleneckInputError(ValueError):
    pass


@dataclass(frozen=True)
class HarnessProfile:
    schema: str
    id: str
    version: int
    provenance_status: str
    content_search: Mapping[str, Any]
    path_search: Mapping[str, Any]
    read: Mapping[str, Any]
    features: Mapping[str, str]
    assumptions: Mapping[str, Any]


@dataclass(frozen=True)
class Probe:
    id: str
    kind: str
    surface: str
    term: str
    scope: str = "repository"
    path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None


@dataclass(frozen=True)
class ProbeOutput:
    probe_id: str
    rows: Tuple[Mapping[str, Any], ...]
    total_count: int
    visible_count: int
    truncated: bool
    omitted_count: int = 0


@dataclass(frozen=True)
class ObservationTrace:
    schema: str
    id: str
    snapshot_digest: str
    profile_id: str
    profile_version: int
    events: Tuple[Mapping[str, Any], ...]
    profile_content_hash: Optional[str] = None
    binding_status: str = "declared"


@dataclass(frozen=True)
class BottleneckReport:
    schema: str
    snapshot: Mapping[str, Any]
    profile: Mapping[str, Any]
    versions: Mapping[str, Any]
    coverage: Mapping[str, Any]
    probes: Tuple[Mapping[str, Any], ...]
    candidates: Tuple[Mapping[str, Any], ...]
    observations: Tuple[Mapping[str, Any], ...]
    limitations: Tuple[str, ...]


def _mapping(value: Any, path: str, error: type[ValueError]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise error(f"{path} must be an object")
    return value


def _text_lines(text: str) -> list[str]:
    if not text:
        return []
    lines = text.split("\n")
    return lines[:-1] if text.endswith("\n") else lines


def _validate_snapshot(snapshot: RepositorySnapshot) -> None:
    if not isinstance(snapshot.digest, str) or not snapshot.digest or not isinstance(snapshot.contents, tuple) or any(not isinstance(row, tuple) or len(row) != 2 or not isinstance(row[0], str) or not isinstance(row[1], str) for row in snapshot.contents):
        raise BottleneckInputError("snapshot is invalid")
    if len({path for path, _ in snapshot.contents}) != len(snapshot.contents):
        raise BottleneckInputError("snapshot paths must be unique")


def parse_harness_profile(data: Mapping[str, object]) -> HarnessProfile:
    obj = _mapping(data, "$", HarnessProfileError)
    required = ("schema", "id", "version", "provenance_status", "content_search", "path_search", "read", "features", "assumptions")
    missing = [key for key in required if key not in obj]
    if missing:
        raise HarnessProfileError(f"$ missing required fields: {', '.join(missing)}")
    if set(obj) != set(required):
        raise HarnessProfileError("$ contains unknown fields")
    if obj["schema"] != "harness_profile.v1":
        raise HarnessProfileError("$.schema must be harness_profile.v1")
    if not isinstance(obj["id"], str) or not obj["id"]:
        raise HarnessProfileError("$.id must be a non-empty string")
    if not isinstance(obj["version"], int) or isinstance(obj["version"], bool) or obj["version"] < 1:
        raise HarnessProfileError("$.version must be a positive integer")
    if obj["provenance_status"] != "unverified_baseline":
        raise HarnessProfileError("$.provenance_status must be unverified_baseline")
    content = _mapping(obj["content_search"], "$.content_search", HarnessProfileError)
    path = _mapping(obj["path_search"], "$.path_search", HarnessProfileError)
    read = _mapping(obj["read"], "$.read", HarnessProfileError)
    features = _mapping(obj["features"], "$.features", HarnessProfileError)
    assumptions = _mapping(obj["assumptions"], "$.assumptions", HarnessProfileError)
    for name, search in (("content_search", content), ("path_search", path)):
        if search.get("matching") != "fixed_string_case_sensitive" or search.get("order") != "path_lexical_then_numeric_line":
            raise HarnessProfileError(f"$.{name} has unsupported matching or order")
        visible = search.get("visible_lines")
        if not isinstance(visible, int) or isinstance(visible, bool) or visible < 1:
            raise HarnessProfileError(f"$.{name}.visible_lines must be a positive integer")
    if content.get("cap_unit") != "matching_lines" or content.get("same_line_occurrences") != "preserved" or set(content) != {"matching", "order", "visible_lines", "cap_unit", "same_line_occurrences"}:
        raise HarnessProfileError("$.content_search has unsupported fields")
    if path.get("cap_unit") != "matching_paths" or set(path) != {"matching", "order", "visible_lines", "cap_unit"}:
        raise HarnessProfileError("$.path_search has unsupported fields")
    maximum = read.get("max_lines")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
        raise HarnessProfileError("$.read.max_lines must be a positive integer")
    if read.get("bounds") != "one_based_inclusive" or read.get("eof") != "clamp" or read.get("truncation") != "actual_omitted_lines":
        raise HarnessProfileError("$.read has unsupported bounds, eof, or truncation rules")
    if set(read) != {"bounds", "max_lines", "eof", "truncation"}:
        raise HarnessProfileError("$.read contains unknown fields")
    required_features = {"fixed_string_search": "supported", "line_range_read": "supported", "semantic_search": "unsupported", "index": "unsupported", "context_compaction": "observation_only", "parallelism": "observation_only", "subagents": "observation_only"}
    if dict(features) != required_features:
        raise HarnessProfileError("$.features does not match the fixed capability contract")
    if assumptions.get("automatic_injection") != "unverified_baseline" or not isinstance(assumptions.get("list_depth"), int) or isinstance(assumptions.get("list_depth"), bool) or assumptions["list_depth"] < 0:
        raise HarnessProfileError("$.assumptions must declare automatic injection and non-negative list depth")
    if set(assumptions) != {"automatic_injection", "list_depth"}:
        raise HarnessProfileError("$.assumptions contains unknown fields")
    return HarnessProfile(obj["schema"], obj["id"], obj["version"], obj["provenance_status"], dict(content), dict(path), dict(read), dict(features), dict(assumptions))


def parse_observation_trace(data: Mapping[str, object]) -> ObservationTrace:
    obj = _mapping(data, "$", ObservationTraceError)
    required = ("schema", "id", "snapshot_digest", "profile", "events")
    missing = [key for key in required if key not in obj]
    if missing:
        raise ObservationTraceError(f"$ missing required fields: {', '.join(missing)}")
    if obj["schema"] != "harness_observation.v1":
        raise ObservationTraceError("$.schema must be harness_observation.v1")
    if set(obj) != set(required):
        raise ObservationTraceError("$ contains unknown fields")
    profile = _mapping(obj["profile"], "$.profile", ObservationTraceError)
    if set(profile) != {"id", "version", "content_hash"}:
        raise ObservationTraceError("$.profile must contain id, version, and content_hash")
    events = obj["events"]
    if not isinstance(events, list):
        raise ObservationTraceError("$.events must be an array")
    seen = set()
    normalized = []
    for index, event in enumerate(events):
        item = _mapping(event, f"$.events[{index}]", ObservationTraceError)
        if not isinstance(item.get("id"), str) or not item.get("id") or item["id"] in seen or not isinstance(item.get("kind"), str) or not item.get("kind"):
            raise ObservationTraceError("event ids must be unique strings and kind is required")
        if "inputs" not in item or "returned" not in item or "status" not in item:
            raise ObservationTraceError("each event requires explicit inputs, returned data, and status")
        inputs = _mapping(item["inputs"], f"$.events[{index}].inputs", ObservationTraceError)
        returned = _mapping(item["returned"], f"$.events[{index}].returned", ObservationTraceError)
        if "probe_id" in inputs and inputs["probe_id"] is not None and (not isinstance(inputs["probe_id"], str) or not inputs["probe_id"]):
            raise ObservationTraceError(f"$.events[{index}].inputs.probe_id must be a string or null")
        if "path" in inputs and inputs["path"] is not None and not isinstance(inputs["path"], str):
            raise ObservationTraceError(f"$.events[{index}].inputs.path must be a string or null")
        for key in ("start_line", "end_line"):
            if key in inputs and inputs[key] is not None and (not isinstance(inputs[key], int) or isinstance(inputs[key], bool)):
                raise ObservationTraceError(f"$.events[{index}].inputs.{key} must be an integer or null")
        if inputs.get("start_line") is not None and inputs.get("end_line") is not None and (inputs["start_line"] < 1 or inputs["end_line"] < inputs["start_line"]):
            raise ObservationTraceError(f"$.events[{index}] has invalid read bounds")
        for key in ("surface", "term"):
            if key in inputs and inputs[key] is not None and not isinstance(inputs[key], str):
                raise ObservationTraceError(f"$.events[{index}].inputs.{key} must be a string or null")
        for key in ("total_count", "visible_count", "omitted_count"):
            if key in returned and returned[key] is not None and (not isinstance(returned[key], int) or isinstance(returned[key], bool) or returned[key] < 0):
                raise ObservationTraceError(f"$.events[{index}].returned.{key} must be a non-negative integer or null")
        if "truncated" in returned and returned["truncated"] is not None and not isinstance(returned["truncated"], bool):
            raise ObservationTraceError(f"$.events[{index}].returned.truncated must be a boolean or null")
        if "rows" in returned and returned["rows"] is not None and not isinstance(returned["rows"], list):
            raise ObservationTraceError(f"$.events[{index}].returned.rows must be an array or null")
        if "paths" in returned and returned["paths"] is not None and (not isinstance(returned["paths"], list) or any(not isinstance(path, str) for path in returned["paths"])):
            raise ObservationTraceError(f"$.events[{index}].returned.paths must be an array of strings or null")
        if "ranges" in returned and returned["ranges"] is not None and not isinstance(returned["ranges"], list):
            raise ObservationTraceError(f"$.events[{index}].returned.ranges must be an array or null")
        ranges = returned.get("ranges") if isinstance(returned.get("ranges"), list) else []
        if isinstance(returned.get("range"), Mapping):
            ranges = [*ranges, returned["range"]]
        elif returned.get("range") is not None:
            raise ObservationTraceError(f"$.events[{index}].returned.range must be an object or null")
        for range_index, item_range in enumerate(ranges):
            range_obj = _mapping(item_range, f"$.events[{index}].returned.ranges[{range_index}]", ObservationTraceError)
            start = range_obj.get("start_line")
            end = range_obj.get("end_line")
            if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool) or start < 1 or end < start:
                raise ObservationTraceError(f"$.events[{index}] has an invalid returned range")
            if "path" in range_obj and not isinstance(range_obj["path"], str):
                raise ObservationTraceError(f"$.events[{index}] returned range path must be a string")
        if not isinstance(item["status"], str) or item["status"] not in {"completed", "truncated", "failed", "unknown"}:
            raise ObservationTraceError(f"$.events[{index}].status is invalid")
        seen.add(item["id"])
        normalized.append(dict(item))
    try:
        version = profile["version"]
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise KeyError
        for key in ("id",):
            if not isinstance(obj[key], str) or not obj[key]:
                raise KeyError
        if not isinstance(obj["snapshot_digest"], str) or not obj["snapshot_digest"]:
            raise KeyError
        content_hash = profile["content_hash"]
        if not isinstance(profile.get("id"), str) or not profile["id"] or not isinstance(content_hash, str) or not content_hash:
            raise KeyError
        return ObservationTrace(str(obj["schema"]), obj["id"], obj["snapshot_digest"], str(profile["id"]), version, tuple(normalized), content_hash)
    except KeyError as exc:
        raise ObservationTraceError("$.profile requires non-empty id, positive integer version, and content_hash") from exc


def convert_legacy_trace(data: Mapping[str, object], *, snapshot_digest: str, profile: HarnessProfile) -> ObservationTrace:
    obj = _mapping(data, "$", ObservationTraceError)
    if not isinstance(snapshot_digest, str) or not snapshot_digest or not isinstance(profile, HarnessProfile):
        raise ObservationTraceError("legacy conversion requires a snapshot digest and harness profile")
    try:
        profile = parse_harness_profile(asdict(profile))
    except (HarnessProfileError, TypeError) as exc:
        raise ObservationTraceError("legacy conversion profile is invalid") from exc
    events = obj.get("events")
    if not isinstance(events, list):
        raise ObservationTraceError("legacy trace events must be an array")
    converted = []
    for index, event in enumerate(events):
        item = _mapping(event, f"$.events[{index}]", ObservationTraceError)
        kind = item.get("kind", "other")
        paths = item.get("paths", [])
        if not isinstance(kind, str) or not kind or not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
            raise ObservationTraceError(f"$.events[{index}] has invalid kind or paths")
        converted.append({"id": f"legacy:{index:06d}", "kind": kind, "inputs": {"surface": item.get("surface"), "term": item.get("term"), "paths": paths, "raw_tool": item.get("raw_tool")}, "returned": {"paths": paths, "text": None, "ranges": None, "exposure_known": False}, "binding": "caller_supplied_unverified"})
    try:
        identity = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ObservationTraceError("legacy trace must contain JSON values") from exc
    trace_id = "legacy:" + hashlib.sha256(identity.encode()).hexdigest()[:16]
    profile_hash = hashlib.sha256(json.dumps(asdict(profile), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ObservationTrace("harness_observation.v1", trace_id, snapshot_digest, profile.id, profile.version, tuple(converted), profile_hash, "caller_supplied_unverified")


def replay_probe(snapshot: RepositorySnapshot, probe: Probe, profile: HarnessProfile) -> ProbeOutput:
    if not isinstance(snapshot, RepositorySnapshot) or not isinstance(probe, Probe) or not isinstance(profile, HarnessProfile):
        raise BottleneckInputError("snapshot, probe, and profile have invalid types")
    try:
        profile = parse_harness_profile(asdict(profile))
    except (HarnessProfileError, TypeError) as exc:
        raise BottleneckInputError("profile is invalid") from exc
    _validate_snapshot(snapshot)
    if not isinstance(probe.id, str) or not probe.id or not isinstance(probe.kind, str) or not isinstance(probe.surface, str) or not isinstance(probe.term, str) or not isinstance(probe.scope, str):
        raise BottleneckInputError("probe string fields must be strings and id must be non-empty")
    contents = snapshot.content_map()
    if probe.surface == "read":
        if not isinstance(probe.path, str) or not probe.path or probe.path not in contents:
            raise BottleneckInputError("read path is outside the snapshot")
        if not isinstance(probe.start_line, int) or isinstance(probe.start_line, bool) or not isinstance(probe.end_line, int) or isinstance(probe.end_line, bool) or probe.start_line < 1 or probe.end_line < probe.start_line:
            raise BottleneckInputError("read bounds must be 1-based inclusive and ordered")
        limit = profile.read["max_lines"]
        lines = _text_lines(contents[probe.path])
        requested_available_end = min(probe.end_line, len(lines))
        end = min(requested_available_end, probe.start_line + limit - 1)
        if probe.start_line > len(lines):
            rows = ()
        else:
            selected_text = "\n".join(lines[probe.start_line - 1:end])
            if end < len(lines) or contents[probe.path].endswith("\n"):
                selected_text += "\n"
            rows = ({"path": probe.path, "start_line": probe.start_line, "end_line": end, "text": selected_text},)
        omitted = max(0, requested_available_end - end)
        visible_lines = end - probe.start_line + 1 if rows else 0
        return ProbeOutput(probe.id, rows, visible_lines + omitted, visible_lines, omitted > 0, omitted)
    if probe.surface not in {"content", "path"} or probe.kind not in {"exact", "derived", "refinement", "list"}:
        raise BottleneckInputError("unsupported probe")
    if probe.kind != "list" and not probe.term:
        raise BottleneckInputError("search term must be non-empty")
    if probe.kind == "list" and probe.surface != "path":
        raise BottleneckInputError("list probes use the path surface")
    scope_parts = probe.scope.split("|")
    if not scope_parts or any(part != "repository" and part != "root" and not part.startswith("path_prefix:") and not part.startswith("extension:") for part in scope_parts):
        raise BottleneckInputError("unsupported scope")
    if any(part.startswith(("path_prefix:", "extension:")) and not part.split(":", 1)[1] for part in scope_parts):
        raise BottleneckInputError("scope values must be non-empty")
    if probe.kind != "list" and "root" in scope_parts:
        raise BottleneckInputError("root scope is supported only for list probes")
    if probe.kind == "list":
        rows = [{"path": path, "line": 1, "text": path, "occurrences": 1} for path, _ in snapshot.contents]
        depth = profile.assumptions["list_depth"]
        if "root" in scope_parts:
            rows = [row for row in rows if len(row["path"].split("/")) <= depth]
        for part in scope_parts:
            if part.startswith("path_prefix:"):
                prefix = part.split(":", 1)[1].rstrip("/")
                rows = [row for row in rows if row["path"] == prefix or row["path"].startswith(prefix + "/")]
            elif part.startswith("extension:"):
                extension = part.split(":", 1)[1]
                rows = [row for row in rows if row["path"].endswith(extension)]
    else:
        rows = []
    for path, text in snapshot.contents if probe.kind != "list" else ():
        if any(item.startswith("path_prefix:") and not (path == item.split(":", 1)[1].rstrip("/") or path.startswith(item.split(":", 1)[1].rstrip("/") + "/")) for item in scope_parts):
            continue
        if any(item.startswith("extension:") and not path.endswith(item.split(":", 1)[1]) for item in scope_parts):
            continue
        if probe.surface == "path":
            if probe.term in path:
                rows.append({"path": path, "line": 1, "text": path, "occurrences": path.count(probe.term)})
        else:
            for line_number, line in enumerate(_text_lines(text), 1):
                count = line.count(probe.term)
                if count:
                    rows.append({"path": path, "line": line_number, "text": line, "occurrences": count})
    rows.sort(key=lambda row: (row["path"], row["line"]))
    limit = profile.content_search["visible_lines"] if probe.surface == "content" else profile.path_search["visible_lines"]
    omitted = max(0, len(rows) - limit)
    return ProbeOutput(probe.id, tuple(rows[:limit]), len(rows), min(len(rows), limit), omitted > 0, omitted)


def _probe_id(kind: str, surface: str, term: str, scope: str) -> str:
    return "p:" + hashlib.sha256(f"{kind}|{surface}|{term}|{scope}".encode()).hexdigest()[:16]


def _analyze_bottlenecks(snapshot: RepositorySnapshot, architecture: PythonProjectArchitecture, graph: AgentViewGraph, profile: HarnessProfile, *, traces: Sequence[ObservationTrace] = ()) -> BottleneckReport:
    if not isinstance(snapshot, RepositorySnapshot) or not isinstance(architecture, PythonProjectArchitecture) or not isinstance(graph, AgentViewGraph) or not isinstance(profile, HarnessProfile):
        raise BottleneckInputError("analysis inputs have invalid types")
    try:
        profile = parse_harness_profile(asdict(profile))
    except (HarnessProfileError, TypeError) as exc:
        raise BottleneckInputError("profile is invalid") from exc
    _validate_snapshot(snapshot)
    if not isinstance(traces, Sequence) or isinstance(traces, (str, bytes)) or any(not isinstance(trace, ObservationTrace) for trace in traces):
        raise BottleneckInputError("traces must contain observation traces")
    if graph.scan.snapshot_digest != snapshot.digest:
        raise BottleneckInputError("agent-view graph and snapshot do not match")
    if architecture.snapshot_digest != snapshot.digest:
        raise BottleneckInputError("architecture and snapshot do not match")
    architecture_ids = {node.id for node in architecture.nodes}
    architecture_by_id = {node.id: node for node in architecture.nodes}
    snapshot_paths = set(snapshot.content_map())
    if len(architecture_ids) != len(architecture.nodes):
        raise BottleneckInputError("architecture contains duplicate node ids")
    if any(node.span is not None and node.span.file_path not in snapshot_paths for node in architecture.nodes):
        raise BottleneckInputError("architecture contains a path outside the snapshot")
    for edge in architecture.edges:
        if edge.from_id not in architecture_ids or edge.to_id not in architecture_ids or any(candidate not in architecture_ids for candidate in edge.candidates):
            raise BottleneckInputError("architecture contains an invalid reference")
    readable_ids = {node.id for node in graph.readable_nodes}
    query_ids = {query.id for query in graph.query_nodes}
    read_unit_ids = {unit.id for unit in graph.read_units}
    occurrence_block_ids = {block.id for block in graph.occurrence_store}
    occurrence_blocks = {block.id: block for block in graph.occurrence_store}
    if len(readable_ids) != len(graph.readable_nodes) or len(query_ids) != len(graph.query_nodes) or len(read_unit_ids) != len(graph.read_units) or len(occurrence_block_ids) != len(graph.occurrence_store):
        raise BottleneckInputError("agent-view graph contains duplicate ids")
    for unit in graph.read_units:
        if unit.file_path not in snapshot_paths or any(symbol_id not in readable_ids for symbol_id in unit.symbol_ids):
            raise BottleneckInputError("read unit references an unknown path or symbol")
    for node in graph.readable_nodes:
        if node.file_path not in snapshot_paths or (node.symbol_id is not None and node.symbol_id not in architecture_ids) or (node.read_unit_id and node.read_unit_id not in read_unit_ids):
            raise BottleneckInputError("readable node references an unknown path, symbol, or read unit")
    for query in graph.query_nodes:
        if any(node_id not in readable_ids for node_id in query.arrival_node_ids + query.origin_node_ids):
            raise BottleneckInputError("query references an unknown readable node")
        if any(item.block_id not in occurrence_block_ids for item in query.occurrence_ranges):
            raise BottleneckInputError("query references an unknown occurrence block")
        if any(item.start < 0 or item.count < 0 or item.start + item.count > occurrence_blocks[item.block_id].count for item in query.occurrence_ranges):
            raise BottleneckInputError("query contains an invalid occurrence range")
    for connection in graph.connections:
        if connection.from_id not in readable_ids | query_ids or connection.to_id not in readable_ids | query_ids:
            raise BottleneckInputError("connection contains an invalid endpoint")
    for document in graph.entry_documents:
        if document.node_id not in readable_ids or document.file_path not in snapshot_paths:
            raise BottleneckInputError("entry document contains an invalid reference")
    for trace in traces:
        expected_profile_hash = hashlib.sha256(json.dumps(asdict(profile), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if trace.snapshot_digest != snapshot.digest or (trace.profile_id, trace.profile_version) != (profile.id, profile.version) or trace.profile_content_hash != expected_profile_hash:
            raise BottleneckInputError("observation trace does not match snapshot/profile")
    readable = sorted(graph.readable_nodes, key=lambda item: item.id)
    def arrivals(rows: Sequence[Mapping[str, Any]], surface: str) -> set[str]:
        result = set()
        for row in rows:
            path = row.get("path")
            nodes = [node for node in readable if node.file_path == path]
            if surface == "path":
                file_nodes = [node for node in nodes if node.symbol_id is None or (node.symbol_id in architecture_by_id and architecture_by_id[node.symbol_id].kind == NodeKind.MODULE)]
                if file_nodes:
                    result.add(min(file_nodes, key=lambda node: node.id).id)
            elif nodes:
                result.add(enclosing_node_id(nodes, path, row.get("line", 1)))
        return result
    profile_payload = asdict(profile)
    profile_hash = hashlib.sha256(json.dumps(profile_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    probe_outputs = []
    candidates = []
    for query in sorted(graph.query_nodes, key=lambda item: item.id):
        if query.kind == "framework":
            continue
        if query.kind not in {"exact", "derived", "refinement", "list"} or query.surface not in {"content", "path"}:
            continue
        probe = Probe(_probe_id(query.kind, query.surface, query.term, query.scope), query.kind, query.surface, query.term, query.scope)
        output = replay_probe(snapshot, probe, profile)
        unlimited = replace(profile, content_search={**profile.content_search, "visible_lines": 2 ** 31}, path_search={**profile.path_search, "visible_lines": 2 ** 31})
        complete = replay_probe(snapshot, probe, unlimited)
        visible_arrivals, all_arrivals = arrivals(output.rows, probe.surface), arrivals(complete.rows, probe.surface)
        probe_outputs.append({"probe": asdict(probe), "source_query": {"id": query.id, "origin_node_ids": sorted(query.origin_node_ids), "rule_id": query.rule_id, "source_terms": sorted(query.source_terms), "candidate_filtered_count": query.candidate_filtered_count, "candidate_cap_truncated": query.candidate_cap_truncated, "refinement_depth": query.refinement_depth}, "output": asdict(output), "visible_arrival_ids": sorted(visible_arrivals), "hidden_arrival_ids": sorted(all_arrivals - visible_arrivals)})
        reasons = []
        if len(all_arrivals) > 1:
            reasons.append("multiple_results")
        if output.truncated:
            reasons.append("output_truncated")
        if reasons:
            identity = f"{probe.id}|{'|'.join(reasons)}"
            candidates.append({"id": "b:" + hashlib.sha256(identity.encode()).hexdigest()[:16], "kind": reasons[0], "target": query.term, "probe_ids": [probe.id], "reasons": reasons, "metrics": {"total_rows": output.total_count, "visible_rows": output.visible_count, "hidden_rows": output.omitted_count, "distinct_arrivals": len(all_arrivals)}, "evidence": {"visible": list(output.rows), "hidden": list(complete.rows[output.visible_count:]), "visible_arrival_ids": sorted(visible_arrivals), "hidden_arrival_ids": sorted(all_arrivals - visible_arrivals)}, "coverage": "generated_probe", "status": "static_candidate"})
    evidence_by_target: Dict[str, list] = {}
    for edge in architecture.edges:
        if edge.evidence:
            evidence_by_target.setdefault(edge.to_id, []).append(edge)
        if str(edge.resolution) == "unresolved" or str(edge.confidence) == "dynamic_required":
            candidates.append({"id": "b:" + hashlib.sha256(f"boundary|{edge.from_id}|{edge.to_id}|{edge.relation}".encode()).hexdigest()[:16], "kind": "unresolved_boundary", "target": edge.to_id, "probe_ids": [], "reasons": ["unresolved_or_dynamic_relation"], "metrics": {}, "evidence": {"edge": {"from_id": edge.from_id, "to_id": edge.to_id, "relation": str(edge.relation)}, "span": asdict(edge.evidence) if edge.evidence else None}, "coverage": "original_python_relations", "status": "static_candidate"})
    for node in architecture.nodes:
        unresolved = (node.metadata or {}).get("unresolved_references", [])
        if unresolved or any(flag.startswith("dynamic_") for flag in node.flags):
            total = (node.metadata or {}).get("unresolved_reference_total", len(unresolved))
            candidates.append({"id": "b:" + hashlib.sha256(f"node-boundary|{node.id}".encode()).hexdigest()[:16], "kind": "unresolved_boundary", "target": node.id, "probe_ids": [], "reasons": ["unresolved_reference_or_dynamic_marker"], "metrics": {"unresolved_total": total, "evidence_limit": (node.metadata or {}).get("unresolved_reference_limit", len(unresolved)), "evidence_truncated": (node.metadata or {}).get("unresolved_reference_truncated", False)}, "evidence": unresolved, "coverage": "original_python_relations", "status": "static_candidate"})
    for target, related in sorted(evidence_by_target.items()):
        paths = {edge.evidence.file_path for edge in related}
        starts = [edge.evidence.start_line for edge in related]
        ends = [edge.evidence.end_line for edge in related]
        spread = max(ends) - min(starts) + 1 if len(paths) == 1 and starts else 0
        reasons = []
        if len(paths) > 1:
            reasons.append("evidence_in_multiple_files")
        if spread > profile.read["max_lines"]:
            reasons.append("same_file_span_exceeds_read_limit")
        if reasons:
            candidates.append({"id": "b:" + hashlib.sha256(f"spread|{target}".encode()).hexdigest()[:16], "kind": "evidence_spread", "target": target, "probe_ids": [], "reasons": reasons, "metrics": {"file_count": len(paths), "line_span": spread, "max_lines": profile.read["max_lines"]}, "evidence": [{"edge": {"from_id": edge.from_id, "to_id": edge.to_id, "relation": str(edge.relation)}, "span": asdict(edge.evidence)} for edge in related], "coverage": "original_python_relations", "status": "static_candidate"})
    exposure_terms: Dict[str, set] = {}
    for entry in probe_outputs:
        probe_data = entry["probe"]
        if probe_data["kind"] not in {"exact", "derived", "refinement"}:
            continue
        for node_id in set(entry["visible_arrival_ids"]):
            exposure_terms.setdefault(node_id, set()).add(probe_data["term"])
    for node in sorted(graph.readable_nodes, key=lambda item: item.id):
        count = len(exposure_terms.get(node.id, set()))
        if count <= 1:
            supporting = sorted(entry["probe"]["id"] for entry in probe_outputs if node.id in entry["visible_arrival_ids"] and entry["probe"]["kind"] in {"exact", "derived", "refinement"})
            candidates.append({"id": "b:" + hashlib.sha256(f"connection|{node.id}".encode()).hexdigest()[:16], "kind": "connection_constraint", "target": node.id, "probe_ids": supporting, "reasons": ["no_independent_visible_search_clue" if count == 0 else "one_independent_visible_search_clue"], "metrics": {"independent_visible_clue_count": count}, "evidence": {"path": node.file_path, "terms": sorted(exposure_terms.get(node.id, set()))}, "coverage": "replayed_generated_probes", "status": "static_candidate"})
        if node.start_line and node.end_line and node.end_line - node.start_line + 1 > int(profile.read["max_lines"]):
            candidates.append({"id": "b:" + hashlib.sha256(f"read|{node.id}".encode()).hexdigest()[:16], "kind": "read_limit", "target": node.id, "probe_ids": [], "reasons": ["node_exceeds_single_read"], "metrics": {"line_count": node.end_line - node.start_line + 1, "max_lines": profile.read["max_lines"]}, "evidence": {"path": node.file_path, "start_line": node.start_line, "end_line": node.end_line}, "coverage": "readable_nodes", "status": "static_candidate"})
    output_by_id = {entry["probe"]["id"]: entry["output"] for entry in probe_outputs}
    observations_list = []
    for trace in sorted(traces, key=lambda item: item.id):
        comparisons = []
        returned_volume = 0
        confirmations = []
        exposures: Dict[str, int] = {}
        duplicated_exposure = 0
        for event in trace.events:
            returned = event.get("returned")
            inputs = event.get("inputs") if isinstance(event.get("inputs"), Mapping) else {}
            if isinstance(returned, Mapping):
                visible_count = returned.get("visible_count")
                if isinstance(visible_count, int) and not isinstance(visible_count, bool):
                    event_volume = visible_count
                else:
                    ranges = returned.get("ranges")
                    one_range = returned.get("range")
                    range_rows = ranges if isinstance(ranges, list) else ([one_range] if isinstance(one_range, Mapping) else [])
                    event_volume = sum(item["end_line"] - item["start_line"] + 1 for item in range_rows if isinstance(item, Mapping) and isinstance(item.get("start_line"), int) and isinstance(item.get("end_line"), int) and item["end_line"] >= item["start_line"])
                    if not event_volume and isinstance(returned.get("rows"), list):
                        event_volume = sum(row.get("end_line", 0) - row.get("start_line", 1) + 1 if isinstance(row, Mapping) and isinstance(row.get("start_line"), int) and isinstance(row.get("end_line"), int) else 1 for row in returned["rows"])
                returned_volume += event_volume
                key_payload = {key: returned.get(key) for key in ("paths", "ranges", "range", "rows", "text") if key in returned and returned.get(key) is not None}
                if key_payload:
                    exposure_key = json.dumps(key_payload, sort_keys=True, separators=(",", ":"))
                    if exposure_key in exposures:
                        duplicated_exposure += event_volume
                    exposures[exposure_key] = exposures.get(exposure_key, 0) + 1
            if event.get("kind") in {"confirm", "test", "verification"} and isinstance(returned, Mapping) and any(returned.get(key) is not None for key in ("rows", "paths", "ranges", "range", "text", "status")):
                confirmations.append(event["id"])
            probe_id = inputs.get("probe_id")
            if trace.binding_status != "declared":
                continue
            if probe_id is not None and probe_id not in output_by_id:
                raise BottleneckInputError("observation event references an unknown probe")
            expected = output_by_id.get(probe_id)
            comparison_id = probe_id
            if expected is None and event.get("kind") == "read" and {"path", "start_line", "end_line"}.issubset(inputs):
                read_probe = Probe(f"trace-read:{event['id']}", "exact", "read", "", path=inputs["path"], start_line=inputs["start_line"], end_line=inputs["end_line"])
                expected = asdict(replay_probe(snapshot, read_probe, profile))
                comparison_id = read_probe.id
            if expected is not None:
                output_fields = {"rows", "total_count", "visible_count", "truncated", "omitted_count"}
                observed_returned = dict(returned) if isinstance(returned, Mapping) else {}
                if "rows" not in observed_returned and observed_returned.get("text") is not None and isinstance(observed_returned.get("range"), Mapping):
                    returned_range = observed_returned["range"]
                    observed_returned["rows"] = [{"path": returned_range.get("path", inputs.get("path")), "start_line": returned_range.get("start_line"), "end_line": returned_range.get("end_line"), "text": observed_returned["text"]}]
                comparable = {key: observed_returned.get(key) for key in output_fields if key in observed_returned and observed_returned.get(key) is not None}
                canonical_expected = json.loads(json.dumps(expected))
                agrees = comparable and all(canonical_expected[key] == value for key, value in comparable.items())
                if trace.binding_status != "declared":
                    status = "unverified"
                elif not comparable:
                    status = "unknown"
                elif not agrees:
                    status = "mismatch"
                elif set(comparable) == output_fields:
                    status = "match"
                else:
                    status = "partial"
                comparisons.append({"event_id": event["id"], "probe_id": comparison_id, "status": status, "compared_fields": sorted(comparable)})
        observations_list.append({"trace_id": trace.id, "binding_status": trace.binding_status, "events": list(trace.events), "event_count": len(trace.events), "comparisons": comparisons, "returned_visible_count": returned_volume, "duplicated_exposure_count": duplicated_exposure, "confirmation_event_ids": confirmations, "confirmation_status": "observed" if confirmations else "unobserved", "status": "observed_only"})
    observations = tuple(observations_list)
    graph_metric_config = GraphAnalysisConfig()
    outgoing = {node_id: set() for node_id in sorted(architecture_ids)}
    incoming = {node_id: set() for node_id in sorted(architecture_ids)}
    for edge in sorted(architecture.edges, key=lambda item: (item.from_id, item.to_id, str(item.relation))):
        if edge.from_id != edge.to_id:
            outgoing[edge.from_id].add(edge.to_id)
            incoming[edge.to_id].add(edge.from_id)
    rank = pagerank(outgoing, graph_metric_config)
    readable_symbols = {node.id: node.symbol_id for node in graph.readable_nodes if node.symbol_id}
    for candidate in candidates:
        target_ids = set()
        if candidate["target"] in architecture_ids:
            target_ids.add(candidate["target"])
        if candidate["target"] in readable_symbols:
            target_ids.add(readable_symbols[candidate["target"]])
        evidence = candidate.get("evidence")
        if isinstance(evidence, Mapping):
            for arrival_id in evidence.get("visible_arrival_ids", []) + evidence.get("hidden_arrival_ids", []):
                if arrival_id in readable_symbols:
                    target_ids.add(readable_symbols[arrival_id])
        candidate["metrics"]["repository_graph"] = [
            {"target_id": node_id, "pagerank": rank[node_id], "in_degree": len(incoming[node_id]), "out_degree": len(outgoing[node_id])}
            for node_id in sorted(target_ids)
        ]
    unique_candidates = {item["id"]: item for item in candidates}
    graph_profile = graph.profile
    graph_ref = graph_profile.get("ref", graph_profile) if isinstance(graph_profile, Mapping) else {}
    versions = {"analysis": "1", "agent_view_schema": graph.schema_version, "agent_view_profile": graph.profile, "agent_view_profile_id": graph_ref.get("id", "unknown"), "agent_view_profile_version": graph_ref.get("version", "unknown"), "agent_view_profile_content_hash": graph_ref.get("content_hash"), "query_rule_ids": sorted({query.rule_id for query in graph.query_nodes if query.rule_id}), "repository_graph_metrics": {"implementation": "analysis.graph_metrics.pagerank", "version": "1", "scope": "directed_original_python_architecture_nodes_and_edges", "config": {"damping": graph_metric_config.damping, "tolerance": graph_metric_config.tolerance, "max_iterations": graph_metric_config.max_iterations}}}
    skipped = {}
    for query in sorted(graph.query_nodes, key=lambda item: item.id):
        if query.kind == "framework":
            skipped[query.id] = "framework_surface_unsupported"
        elif query.kind not in {"exact", "derived", "refinement", "list"}:
            skipped[query.id] = "query_kind_unsupported"
        elif query.surface not in {"content", "path"}:
            skipped[query.id] = "query_surface_unsupported"
    coverage = {"generated_probe_count": len(probe_outputs), "query_node_count": len(graph.query_nodes), "skipped_query_ids": skipped, "query_candidate_filtered_count": sum(query.candidate_filtered_count for query in graph.query_nodes), "candidate_cap_truncated_query_ids": sorted(query.id for query in graph.query_nodes if query.candidate_cap_truncated), "source_file_count": len(snapshot.contents), "python_file_count": architecture.snapshot_coverage.get("python_file_count"), "parsed_python_file_count": architecture.snapshot_coverage.get("parsed_python_file_count"), "invalid_python_files": architecture.snapshot_coverage.get("invalid_python_files", []), "non_python_files_searchable_only": sum(not path.endswith(".py") for path, _ in snapshot.contents), "excluded_files": [asdict(item) for item in snapshot.excluded_files], "unresolved_boundaries_included": True, "unsupported_query_kinds": {"framework": "framework surface replay is unsupported by the fixed harness profile"}}
    ordered_candidates = sorted(unique_candidates.values(), key=lambda item: (item["kind"], item["id"]))
    return BottleneckReport("bottlenecks.v1", {"digest": snapshot.digest, "file_count": len(snapshot.contents), "ignore_source": snapshot.ignore_source}, {**profile_payload, "content_hash": profile_hash}, versions, coverage, tuple(probe_outputs), tuple(ordered_candidates), observations, ("Generated probes do not establish discoverability outside their covered terms.", "Static candidates do not demonstrate reduced agent effort or safer changes."))


def analyze_bottlenecks(snapshot: RepositorySnapshot, architecture: PythonProjectArchitecture, graph: AgentViewGraph, profile: HarnessProfile, *, traces: Sequence[ObservationTrace] = ()) -> BottleneckReport:
    try:
        return _analyze_bottlenecks(snapshot, architecture, graph, profile, traces=traces)
    except BottleneckInputError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise BottleneckInputError("analysis input structure is invalid") from exc


def bottlenecks_to_json(report: BottleneckReport) -> str:
    if not isinstance(report, BottleneckReport):
        raise BottleneckInputError("report has an invalid type")
    try:
        return json.dumps(asdict(report), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise BottleneckInputError("report contains non-JSON values") from exc
