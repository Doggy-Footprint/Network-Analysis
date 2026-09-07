import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

TRACE_SCHEMA = "agent_trace.v1"
EVENT_KINDS = ("read", "search", "list", "other")
SURFACES = ("content", "path")


class TraceError(ValueError):
    pass


def _mapping(value: Any, path: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise TraceError(f"trace {path} must be an object")
    return value


def _text(value: Any, path: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise TraceError(f"trace {path} must be a non-empty string")
    return value


def _string_list(value: Any, path: str) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TraceError(f"trace {path} must be an array of strings")
    return list(value)


def validate_trace(trace: Any) -> Dict[str, Any]:
    root = _mapping(trace, "root")
    if root.get("schema") != TRACE_SCHEMA:
        raise TraceError(f"trace schema must be {TRACE_SCHEMA}")
    _text(root.get("trace_id"), "trace_id", allow_empty=False)
    _text(root.get("recorded_at"), "recorded_at")
    _text(root.get("task"), "task")
    source = _mapping(root.get("source"), "source")
    for key in ("tool", "transcript_sha256", "session_id"):
        _text(source.get(key), f"source.{key}")
    repository = _mapping(root.get("repository"), "repository")
    for key in ("name", "commit"):
        _text(repository.get(key), f"repository.{key}")
    agent = _mapping(root.get("agent"), "agent")
    for key in ("name", "model"):
        _text(agent.get(key), f"agent.{key}")
    _mapping(agent.get("settings"), "agent.settings")
    _string_list(root.get("targets"), "targets")

    events = root.get("events")
    if not isinstance(events, list):
        raise TraceError("trace events must be an array")
    for position, event in enumerate(events):
        entry = _mapping(event, f"events[{position}]")
        if entry.get("index") != position:
            raise TraceError(f"trace events[{position}].index must equal its position")
        if entry.get("kind") not in EVENT_KINDS:
            raise TraceError(f"trace events[{position}].kind must be one of {list(EVENT_KINDS)}")
        if entry.get("surface") not in SURFACES:
            raise TraceError(f"trace events[{position}].surface must be one of {list(SURFACES)}")
        _string_list(entry.get("paths"), f"events[{position}].paths")
        _text(entry.get("raw_tool"), f"events[{position}].raw_tool")
        _text(entry.get("term"), f"events[{position}].term")
    return root


def load_trace(path: Union[str, Path]) -> Dict[str, Any]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise TraceError(f"cannot read trace {path}: {error}") from error
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise TraceError(f"trace is not valid JSON: {error}") from error
    return validate_trace(document)


def observed_discovery_order(
    trace: Mapping[str, Any],
    targets: Optional[Sequence[str]] = None,
) -> Dict[str, int]:
    wanted = set(trace["targets"] if targets is None else targets)
    order: Dict[str, int] = {}
    for event in trace["events"]:
        if event["kind"] != "read":
            continue
        for file_path in event["paths"]:
            if file_path in wanted and file_path not in order:
                order[file_path] = event["index"]
    return dict(sorted(order.items()))


def _ranks(values: Sequence[float]) -> List[float]:
    order = sorted(range(len(values)), key=lambda position: values[position])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        stop = start
        while stop + 1 < len(order) and values[order[stop + 1]] == values[order[start]]:
            stop += 1
        shared = (start + stop) / 2.0 + 1.0
        for position in order[start : stop + 1]:
            ranks[position] = shared
        start = stop + 1
    return ranks


def spearman(left: Sequence[float], right: Sequence[float]) -> Optional[float]:
    if len(left) != len(right):
        raise TraceError("spearman inputs must have the same length")
    if len(left) < 2:
        return None
    left_ranks = _ranks(left)
    right_ranks = _ranks(right)
    left_mean = sum(left_ranks) / len(left_ranks)
    right_mean = sum(right_ranks) / len(right_ranks)
    covariance = sum(
        (a - left_mean) * (b - right_mean) for a, b in zip(left_ranks, right_ranks)
    )
    left_variance = sum((a - left_mean) ** 2 for a in left_ranks)
    right_variance = sum((b - right_mean) ** 2 for b in right_ranks)
    if left_variance == 0 or right_variance == 0:
        return None
    return covariance / math.sqrt(left_variance * right_variance)


def predicted_discovery_order(view, sample) -> Dict[str, int]:
    order: Dict[str, int] = {}
    for node_id, turn in sample.observations.discovery_turn_index.items():
        file_path = view.readable[node_id].file_path
        if file_path not in order or turn < order[file_path]:
            order[file_path] = turn
    return dict(sorted(order.items()))


def compare_order(
    trace: Mapping[str, Any],
    result,
    view,
    policy,
    *,
    percentile: str = "p50",
) -> Dict[str, Any]:
    sample = result.percentiles[percentile]["sample"]
    predicted = predicted_discovery_order(view, sample)
    observed = observed_discovery_order(trace)
    shared = sorted(set(observed) & set(predicted))
    rho = spearman([observed[key] for key in shared], [predicted[key] for key in shared])
    if rho is None:
        reason = "fewer than 2 shared targets" if len(shared) < 2 else "zero variance in one order"
    else:
        reason = None
    return {
        "trace_id": trace["trace_id"],
        "scenario_id": result.scenario.id,
        "percentile": percentile,
        "policy": {
            "phase_b": policy.phase_b_policy,
            "result_ordering": policy.result_ordering,
        },
        "seed": result.seed,
        "sample_count": result.sample_count,
        "observed": observed,
        "predicted": predicted,
        "compared_targets": shared,
        "observed_only": sorted(set(observed) - set(predicted)),
        "predicted_only": sorted(set(predicted) - set(observed)),
        "n": len(shared),
        "spearman_rho": rho,
        "reason": reason,
    }
