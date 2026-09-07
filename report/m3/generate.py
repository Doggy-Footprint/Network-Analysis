import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Union

from report.shared.document import (
    ReportInputError,
    ReportOutputError,
    array as _array,
    boolean as _boolean,
    fail as _fail,
    generate,
    integer as _integer,
    object_ as _object,
    required as _required,
    string as _string,
    string_array as _string_array,
)

SUPPORTED_SCHEMA = "phase_b_cost.v1"
AXES = (
    "exploration_turns", "search_tool_calls", "read_tool_calls",
    "query_result_tokens", "readable_node_tokens", "zero_result_queries",
    "revisits", "exposed_non_target_candidates", "duplicate_occurrences",
)
PERCENTILES = ("p5", "p50", "p95")
TEMPLATE_FILES = (
    "header.html", "scenarios.html", "glossary.html",
    "cost_model.js", "header.js", "scenarios.js",
)
PAYLOAD_ID = "phase-b-cost-payload"
READY_EVENT = "phase-b-cost-ready"
READY_LABEL = '"phase-b " + graph.schema + " 로드 완료"'


def _template_dir() -> Path:
    return Path(__file__).resolve().parent / "templates"


def _number(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        _fail(path, "must be a number")
    return float(value)


def _axes(value: Any, path: str) -> Dict[str, int]:
    axes = _object(value, path)
    _required(axes, path, AXES)
    for axis in AXES:
        _integer(axes[axis], f"{path}.{axis}", minimum=0)
    return axes


def _bootstrap(value: Any, path: str) -> None:
    if value is None:
        return
    interval = _object(value, path)
    _required(interval, path, ("low", "high", "resamples", "interval"))
    _number(interval["low"], f"{path}.low")
    _number(interval["high"], f"{path}.high")
    _integer(interval["resamples"], f"{path}.resamples", minimum=1)
    _number(interval["interval"], f"{path}.interval")


def _percentile(value: Any, path: str) -> None:
    entry = _object(value, path)
    _required(entry, path, (
        "rank", "weighted_cost", "axes", "observations", "execution_sequence", "bootstrap_ci",
    ))
    _integer(entry["rank"], f"{path}.rank", minimum=0)
    _number(entry["weighted_cost"], f"{path}.weighted_cost")
    _axes(entry["axes"], f"{path}.axes")
    _bootstrap(entry["bootstrap_ci"], f"{path}.bootstrap_ci")

    observations = _object(entry["observations"], f"{path}.observations")
    _required(observations, f"{path}.observations", (
        "discovery_turn_index", "unread_targets", "hinted_unread_nodes",
        "duplicate_suppressed_queries",
    ))
    turns = _object(observations["discovery_turn_index"], f"{path}.observations.discovery_turn_index")
    for key, turn in turns.items():
        _integer(turn, f"{path}.observations.discovery_turn_index[{key}]", minimum=0)
    _string_array(observations["unread_targets"], f"{path}.observations.unread_targets")
    _integer(observations["hinted_unread_nodes"], f"{path}.observations.hinted_unread_nodes", minimum=0)
    _integer(
        observations["duplicate_suppressed_queries"],
        f"{path}.observations.duplicate_suppressed_queries",
        minimum=0,
    )

    for index, step in enumerate(_array(entry["execution_sequence"], f"{path}.execution_sequence")):
        step_path = f"{path}.execution_sequence[{index}]"
        item = _object(step, step_path)
        _required(item, step_path, ("step", "phase", "action", "id", "turn", "cost_delta"))
        _integer(item["step"], f"{step_path}.step", minimum=0)
        _integer(item["turn"], f"{step_path}.turn", minimum=0)
        _string(item["id"], f"{step_path}.id")
        if item["phase"] not in ("A", "B"):
            _fail(f"{step_path}.phase", "must be 'A' or 'B'")
        if item["action"] not in ("search", "read", "inject"):
            _fail(f"{step_path}.action", "must be 'search', 'read' or 'inject'")
        deltas = _object(item["cost_delta"], f"{step_path}.cost_delta")
        for axis, delta in deltas.items():
            if axis not in AXES:
                _fail(f"{step_path}.cost_delta", f"unknown cost axis {axis!r}")
            _integer(delta, f"{step_path}.cost_delta.{axis}", minimum=0)


def _scenario(value: Any, path: str) -> None:
    scenario = _object(value, path)
    _required(scenario, path, (
        "id", "task", "targets", "seed_queries", "phase_a", "sample_count", "converged",
        "seed", "percentile_method", "percentiles", "axis_statistics", "closure",
        "invariants", "reachability",
    ))
    _string(scenario["id"], f"{path}.id", allow_empty=False)
    _string(scenario["task"], f"{path}.task")
    _integer(scenario["sample_count"], f"{path}.sample_count", minimum=1)
    _integer(scenario["seed"], f"{path}.seed", minimum=0)
    _string(scenario["percentile_method"], f"{path}.percentile_method", allow_empty=False)
    if scenario["converged"] is not None:
        _boolean(scenario["converged"], f"{path}.converged")

    for index, target in enumerate(_array(scenario["targets"], f"{path}.targets")):
        target_path = f"{path}.targets[{index}]"
        entry = _object(target, target_path)
        _required(entry, target_path, ("node_id", "file_path", "label", "read_unit_id"))
        for field in ("node_id", "file_path", "label", "read_unit_id"):
            _string(entry[field], f"{target_path}.{field}")

    seeds = _object(scenario["seed_queries"], f"{path}.seed_queries")
    _required(seeds, f"{path}.seed_queries", ("source", "terms", "resolved_query_ids", "unmatched_terms"))
    _string(seeds["source"], f"{path}.seed_queries.source", allow_empty=False)
    _string_array(seeds["resolved_query_ids"], f"{path}.seed_queries.resolved_query_ids")
    for field in ("terms", "unmatched_terms"):
        for index, term in enumerate(_array(seeds[field], f"{path}.seed_queries.{field}")):
            term_path = f"{path}.seed_queries.{field}[{index}]"
            item = _object(term, term_path)
            _required(item, term_path, ("term", "surface"))
            _string(item["term"], f"{term_path}.term")
            _string(item["surface"], f"{term_path}.surface")

    phase_a = _object(scenario["phase_a"], f"{path}.phase_a")
    _required(phase_a, f"{path}.phase_a", (
        "entry_documents", "root_list_query_id", "repo_map_entry_count", "repo_map_tokens", "axes",
    ))
    _axes(phase_a["axes"], f"{path}.phase_a.axes")
    _integer(phase_a["repo_map_entry_count"], f"{path}.phase_a.repo_map_entry_count", minimum=0)
    _integer(phase_a["repo_map_tokens"], f"{path}.phase_a.repo_map_tokens", minimum=0)
    if phase_a["root_list_query_id"] is not None:
        _string(phase_a["root_list_query_id"], f"{path}.phase_a.root_list_query_id")
    for index, document in enumerate(_array(phase_a["entry_documents"], f"{path}.phase_a.entry_documents")):
        document_path = f"{path}.phase_a.entry_documents[{index}]"
        entry = _object(document, document_path)
        _required(entry, document_path, ("node_id", "file_path", "injected"))
        _boolean(entry["injected"], f"{document_path}.injected")

    percentiles = _object(scenario["percentiles"], f"{path}.percentiles")
    _required(percentiles, f"{path}.percentiles", PERCENTILES)
    for name in PERCENTILES:
        _percentile(percentiles[name], f"{path}.percentiles.{name}")

    statistics = _object(scenario["axis_statistics"], f"{path}.axis_statistics")
    _required(statistics, f"{path}.axis_statistics", AXES)
    for axis in AXES:
        entry = _object(statistics[axis], f"{path}.axis_statistics.{axis}")
        _required(entry, f"{path}.axis_statistics.{axis}", ("mean", "stdev"))
        _number(entry["mean"], f"{path}.axis_statistics.{axis}.mean")
        _number(entry["stdev"], f"{path}.axis_statistics.{axis}.stdev")

    closure = _object(scenario["closure"], f"{path}.closure")
    _required(closure, f"{path}.closure", ("axes", "weighted_cost", "query_count", "read_unit_count"))
    _axes(closure["axes"], f"{path}.closure.axes")
    _number(closure["weighted_cost"], f"{path}.closure.weighted_cost")
    _integer(closure["query_count"], f"{path}.closure.query_count", minimum=0)
    _integer(closure["read_unit_count"], f"{path}.closure.read_unit_count", minimum=0)

    invariants = _object(scenario["invariants"], f"{path}.invariants")
    _required(invariants, f"{path}.invariants", ("weighted_monotone", "axis_within_closure", "violations"))
    _boolean(invariants["weighted_monotone"], f"{path}.invariants.weighted_monotone")
    _boolean(invariants["axis_within_closure"], f"{path}.invariants.axis_within_closure")
    _array(invariants["violations"], f"{path}.invariants.violations")

    reachability = _object(scenario["reachability"], f"{path}.reachability")
    _required(reachability, f"{path}.reachability", ("status", "unreached_targets", "incomplete_sample_count"))
    _string(reachability["status"], f"{path}.reachability.status", allow_empty=False)
    _string_array(reachability["unreached_targets"], f"{path}.reachability.unreached_targets")
    _integer(reachability["incomplete_sample_count"], f"{path}.reachability.incomplete_sample_count", minimum=0)


def _validate_payload(value: Any) -> Dict[str, Any]:
    root = _object(value, "root")
    if root.get("schema") != SUPPORTED_SCHEMA:
        _fail("root.schema", f"must be {SUPPORTED_SCHEMA!r}")
    _required(root, "root", (
        "project_name", "snapshot_digest", "profiles", "seed_query_generator", "versions", "scenarios",
    ))
    _string(root["project_name"], "root.project_name")
    _string(root["snapshot_digest"], "root.snapshot_digest")

    profiles = _object(root["profiles"], "root.profiles")
    _required(profiles, "root.profiles", ("agent_view", "exploration_policy", "cost_weights"))
    for name in ("agent_view", "exploration_policy", "cost_weights"):
        entry = _object(profiles[name], f"root.profiles.{name}")
        _required(entry, f"root.profiles.{name}", ("id", "version", "content_hash"))
        _string(entry["id"], f"root.profiles.{name}.id", allow_empty=False)
        _integer(entry["version"], f"root.profiles.{name}.version", minimum=1)
        _string(entry["content_hash"], f"root.profiles.{name}.content_hash", allow_empty=False)

    _object(root["seed_query_generator"], "root.seed_query_generator")

    seen = []
    for index, stamp in enumerate(_array(root["versions"], "root.versions")):
        stamp_path = f"root.versions[{index}]"
        entry = _object(stamp, stamp_path)
        if sorted(entry) != ["id", "version"]:
            _fail(stamp_path, "must have exactly the fields 'id' and 'version'")
        _string(entry["id"], f"{stamp_path}.id", allow_empty=False)
        _string(entry["version"], f"{stamp_path}.version", allow_empty=False)
        seen.append(entry["id"])
    if seen != sorted(seen):
        _fail("root.versions", "must be sorted by id")

    scenarios = _array(root["scenarios"], "root.scenarios")
    if not scenarios:
        _fail("root.scenarios", "must not be empty")
    for index, scenario in enumerate(scenarios):
        _scenario(scenario, f"root.scenarios[{index}]")
    return dict(root)


def generate_report(
    json_path: Union[str, Path],
    output_path: Union[str, Path, None] = None,
    *,
    read_text: Optional[Callable[[Path], str]] = None,
    write_text: Optional[Callable[[Path, str], None]] = None,
    compress: Optional[Callable[[bytes], bytes]] = None,
    template_dir: Optional[Union[str, Path]] = None,
    stderr: Any = None,
) -> Path:
    return generate(
        json_path,
        output_path,
        validate=_validate_payload,
        template_dir=Path(template_dir) if template_dir is not None else _template_dir(),
        names=TEMPLATE_FILES,
        title="Phase-B discovery cost",
        payload_id=PAYLOAD_ID,
        ready_event=READY_EVENT,
        ready_label=READY_LABEL,
        label="phase-b-cost",
        read_text=read_text,
        write_text=write_text,
        compress=compress,
        stderr=stderr,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="M3 phase_b_cost.v1 JSON을 단일 오프라인 HTML 보고서로 변환합니다."
    )
    parser.add_argument("phase_b_cost_json")
    parser.add_argument("-o", "--output")
    args = parser.parse_args(argv)
    try:
        output = generate_report(args.phase_b_cost_json, args.output)
    except (ReportInputError, ReportOutputError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
