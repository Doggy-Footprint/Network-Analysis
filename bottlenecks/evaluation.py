from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from .core import (
    HarnessProfile,
    ObservationTrace,
    ObservationTraceError,
    convert_legacy_trace,
    parse_harness_profile,
    parse_observation_trace,
)


class HarnessSupportError(ValueError):
    pass


class EvaluationCaseError(ValueError):
    pass


class EvaluationRunError(ValueError):
    pass


class EvaluationComparisonError(ValueError):
    pass


BURDEN_AXES = (
    "total_calls", "search_calls", "read_calls", "preparation_calls", "failed_calls",
    "returned_items", "returned_lines", "duplicated_exposure",
)


@dataclass(frozen=True)
class HarnessSupport:
    schema: str
    profile: Mapping[str, Any]
    language_scope: tuple[str, ...]
    settings: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class EvaluationCell:
    id: str
    repository_variant: str
    harness_variant: str
    snapshot_digest: str
    profile: Mapping[str, Any]


@dataclass(frozen=True)
class EvaluationCase:
    schema: str
    id: str
    language: str
    task: str
    confirmations: tuple[Mapping[str, str], ...]
    outcomes: tuple[Mapping[str, str], ...]
    factor: str
    cells: tuple[EvaluationCell, ...]


@dataclass(frozen=True)
class EvaluationRun:
    schema: str
    id: str
    case_id: str
    cell: EvaluationCell
    environment: Mapping[str, str]
    trace: ObservationTrace


@dataclass(frozen=True)
class RunEvaluation:
    schema: str
    case_id: str
    run_id: str
    cell_id: str
    binding_status: str
    environment: Mapping[str, str]
    burden: Mapping[str, int]
    confirmations: tuple[Mapping[str, Any], ...]
    outcomes: tuple[Mapping[str, Any], ...]
    eligible: bool
    _cell: EvaluationCell


@dataclass(frozen=True)
class RunComparison:
    schema: str
    case_id: str
    factor: str
    before_run_id: str
    after_run_id: str
    burden_delta: Mapping[str, int]
    status: str


def _mapping(value: Any, path: str, error: type[ValueError]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise error(f"{path} must be an object")
    return value


def _string(value: Any, path: str, error: type[ValueError]) -> str:
    if not isinstance(value, str) or not value:
        raise error(f"{path} must be a non-empty string")
    return value


def _profile_hash(profile: HarnessProfile) -> str:
    return hashlib.sha256(json.dumps(asdict(profile), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _profile_binding(value: Any, path: str, error: type[ValueError]) -> Mapping[str, Any]:
    obj = _mapping(value, path, error)
    if set(obj) != {"id", "version", "content_hash"}:
        raise error(f"{path} must contain id, version, and content_hash")
    _string(obj["id"], f"{path}.id", error)
    if not isinstance(obj["version"], int) or isinstance(obj["version"], bool) or obj["version"] < 1:
        raise error(f"{path}.version must be a positive integer")
    hash_value = _string(obj["content_hash"], f"{path}.content_hash", error)
    if len(hash_value) != 64 or any(char not in "0123456789abcdef" for char in hash_value):
        raise error(f"{path}.content_hash must be a lowercase SHA-256 digest")
    return dict(obj)


def _binding_for(profile: HarnessProfile) -> Mapping[str, Any]:
    return {"id": profile.id, "version": profile.version, "content_hash": _profile_hash(profile)}


def _scalar_pointers(value: Any, pointer: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key in sorted(value):
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            output.update(_scalar_pointers(value[key], f"{pointer}/{escaped}"))
        return output
    if isinstance(value, (list, tuple)):
        output = {}
        for index, item in enumerate(value):
            output.update(_scalar_pointers(item, f"{pointer}/{index}"))
        return output
    return {pointer: value}


def _is_evidence_reference(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        return bool(parsed.netloc)
    if parsed.scheme or value.startswith("/"):
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


def parse_harness_support(data: Mapping[str, object], profile: HarnessProfile) -> HarnessSupport:
    try:
        profile = parse_harness_profile(asdict(profile))
    except (TypeError, ValueError) as exc:
        raise HarnessSupportError("profile is invalid") from exc
    obj = _mapping(data, "$", HarnessSupportError)
    if set(obj) != {"schema", "profile", "language_scope", "settings"} or obj.get("schema") != "harness_support.v1":
        raise HarnessSupportError("support manifest has invalid schema or fields")
    if _profile_binding(obj["profile"], "$.profile", HarnessSupportError) != _binding_for(profile):
        raise HarnessSupportError("support profile does not bind to the parsed profile")
    languages = obj["language_scope"]
    if not isinstance(languages, list) or not languages or any(not isinstance(item, str) or not item for item in languages) or len(set(languages)) != len(languages):
        raise HarnessSupportError("$.language_scope must be a non-empty unique array of language ids")
    if not isinstance(obj["settings"], list):
        raise HarnessSupportError("$.settings must be an array")
    profile_data = asdict(profile)
    expected = _scalar_pointers({key: profile_data[key] for key in ("provenance_status", "content_search", "path_search", "read", "features", "assumptions")})
    found: dict[str, Any] = {}
    settings = []
    for index, raw in enumerate(obj["settings"]):
        item = _mapping(raw, f"$.settings[{index}]", HarnessSupportError)
        if set(item) != {"pointer", "value", "support", "provenance"}:
            raise HarnessSupportError("support setting has invalid fields")
        pointer = _string(item["pointer"], f"$.settings[{index}].pointer", HarnessSupportError)
        if pointer not in expected or pointer in found or item["value"] != expected[pointer]:
            raise HarnessSupportError("support settings must bind every profile scalar exactly once")
        if item["support"] not in {"replayed", "observation_only", "unsupported"}:
            raise HarnessSupportError("support setting has invalid support status")
        provenance = _mapping(item["provenance"], f"$.settings[{index}].provenance", HarnessSupportError)
        if set(provenance) != {"status", "evidence"} or provenance.get("status") not in {"sourced", "unverified"} or not isinstance(provenance.get("evidence"), list) or any(not _is_evidence_reference(entry) for entry in provenance["evidence"]):
            raise HarnessSupportError("support setting has invalid provenance")
        if provenance["status"] == "sourced" and not provenance["evidence"]:
            raise HarnessSupportError("sourced provenance requires evidence")
        found[pointer] = item["value"]
        settings.append({"pointer": pointer, "value": item["value"], "support": item["support"], "provenance": dict(provenance)})
    if set(found) != set(expected):
        raise HarnessSupportError("support settings omit or add a profile pointer")
    return HarnessSupport("harness_support.v1", dict(_binding_for(profile)), tuple(sorted(languages)), tuple(sorted(settings, key=lambda item: item["pointer"])))


def _declared_rows(value: Any, path: str, error: type[ValueError]) -> tuple[Mapping[str, str], ...]:
    if not isinstance(value, list) or not value:
        raise error(f"{path} must be a non-empty array")
    rows = []
    ids = set()
    for index, raw in enumerate(value):
        item = _mapping(raw, f"{path}[{index}]", error)
        if set(item) != {"id", "description"}:
            raise error(f"{path}[{index}] must contain id and description")
        identifier = _string(item["id"], f"{path}[{index}].id", error)
        if identifier in ids:
            raise error(f"{path} ids must be unique")
        ids.add(identifier)
        rows.append({"id": identifier, "description": _string(item["description"], f"{path}[{index}].description", error)})
    return tuple(sorted(rows, key=lambda item: item["id"]))


def parse_evaluation_case(data: Mapping[str, object]) -> EvaluationCase:
    obj = _mapping(data, "$", EvaluationCaseError)
    required = {"schema", "id", "language", "task", "confirmations", "outcomes", "comparison"}
    if set(obj) != required or obj.get("schema") != "harness_evaluation_case.v1":
        raise EvaluationCaseError("evaluation case has invalid schema or fields")
    identity = [_string(obj[key], f"$.{key}", EvaluationCaseError) for key in ("id", "language", "task")]
    confirmations = _declared_rows(obj["confirmations"], "$.confirmations", EvaluationCaseError)
    outcomes = _declared_rows(obj["outcomes"], "$.outcomes", EvaluationCaseError)
    comparison = _mapping(obj["comparison"], "$.comparison", EvaluationCaseError)
    if set(comparison) != {"factor", "cells"} or comparison.get("factor") not in {"structure", "harness", "interaction"} or not isinstance(comparison.get("cells"), list):
        raise EvaluationCaseError("comparison has invalid factor or cells")
    cells = []
    cell_ids = set()
    for index, raw in enumerate(comparison["cells"]):
        item = _mapping(raw, f"$.comparison.cells[{index}]", EvaluationCaseError)
        if set(item) != {"id", "repository_variant", "harness_variant", "snapshot_digest", "profile"}:
            raise EvaluationCaseError("comparison cell has invalid fields")
        cell_id = _string(item["id"], f"$.comparison.cells[{index}].id", EvaluationCaseError)
        if cell_id in cell_ids or item.get("repository_variant") not in {"before", "after"} or item.get("harness_variant") not in {"before", "after"}:
            raise EvaluationCaseError("comparison cell id or variants are invalid")
        cell_ids.add(cell_id)
        cells.append(EvaluationCell(cell_id, item["repository_variant"], item["harness_variant"], _string(item["snapshot_digest"], f"$.comparison.cells[{index}].snapshot_digest", EvaluationCaseError), _profile_binding(item["profile"], f"$.comparison.cells[{index}].profile", EvaluationCaseError)))
    factor = comparison["factor"]
    pairs = {(cell.repository_variant, cell.harness_variant) for cell in cells}
    expected_pairs = {("before", "before"), ("after", "before")} if factor == "structure" else ({("before", "before"), ("before", "after")} if factor == "harness" else {("before", "before"), ("before", "after"), ("after", "before"), ("after", "after")})
    if len(cells) != len(expected_pairs) or pairs != expected_pairs:
        raise EvaluationCaseError("comparison cells do not match the factor design")
    by_pair = {(cell.repository_variant, cell.harness_variant): cell for cell in cells}
    if factor == "structure":
        before, after = by_pair[("before", "before")], by_pair[("after", "before")]
        valid = before.profile == after.profile and before.snapshot_digest != after.snapshot_digest
    elif factor == "harness":
        before, after = by_pair[("before", "before")], by_pair[("before", "after")]
        valid = before.snapshot_digest == after.snapshot_digest and before.profile != after.profile
    else:
        valid = all(len({cell.snapshot_digest for cell in cells if cell.repository_variant == variant}) == 1 for variant in ("before", "after")) and all(len({json.dumps(cell.profile, sort_keys=True) for cell in cells if cell.harness_variant == variant}) == 1 for variant in ("before", "after"))
    if not valid:
        raise EvaluationCaseError("comparison cells have invalid bindings")
    return EvaluationCase("harness_evaluation_case.v1", identity[0], identity[1], identity[2], confirmations, outcomes, factor, tuple(sorted(cells, key=lambda cell: cell.id)))


def parse_evaluation_run(data: Mapping[str, object], case: EvaluationCase, profile: HarnessProfile) -> EvaluationRun:
    if not isinstance(case, EvaluationCase):
        raise EvaluationRunError("case is invalid")
    try:
        profile = parse_harness_profile(asdict(profile))
    except (TypeError, ValueError) as exc:
        raise EvaluationRunError("profile is invalid") from exc
    obj = _mapping(data, "$", EvaluationRunError)
    if set(obj) != {"schema", "id", "case_id", "cell_id", "environment", "trace"} or obj.get("schema") != "harness_evaluation_run.v1":
        raise EvaluationRunError("evaluation run has invalid schema or fields")
    run_id, case_id, cell_id = (_string(obj[key], f"$.{key}", EvaluationRunError) for key in ("id", "case_id", "cell_id"))
    if case_id != case.id:
        raise EvaluationRunError("run case id does not match")
    cell = next((item for item in case.cells if item.id == cell_id), None)
    if cell is None or cell.profile != _binding_for(profile):
        raise EvaluationRunError("run cell does not bind to the supplied profile")
    environment = _mapping(obj["environment"], "$.environment", EvaluationRunError)
    if set(environment) != {"model_version", "harness_version"}:
        raise EvaluationRunError("run environment has invalid fields")
    normalized_environment = {key: _string(environment[key], f"$.environment.{key}", EvaluationRunError) for key in sorted(environment)}
    trace_payload = _mapping(obj["trace"], "$.trace", EvaluationRunError)
    try:
        if trace_payload.get("schema") == "harness_observation.v1":
            trace = parse_observation_trace(trace_payload)
            if trace.snapshot_digest != cell.snapshot_digest or (trace.profile_id, trace.profile_version, trace.profile_content_hash) != (profile.id, profile.version, _profile_hash(profile)):
                raise EvaluationRunError("observation trace does not bind to the run cell")
        elif trace_payload.get("schema") == "agent_trace.v1":
            trace = convert_legacy_trace(trace_payload, snapshot_digest=cell.snapshot_digest, profile=profile)
        else:
            raise EvaluationRunError("run trace schema is unsupported")
    except ObservationTraceError as exc:
        raise EvaluationRunError("run trace is invalid") from exc
    confirmation_ids = {item["id"] for item in case.confirmations}
    outcome_ids = {item["id"] for item in case.outcomes}
    for event in trace.events:
        if event.get("kind") in {"confirm", "outcome"}:
            input_name = "confirmation_id" if event["kind"] == "confirm" else "outcome_id"
            inputs = event.get("inputs")
            returned = event.get("returned")
            expected_ids = confirmation_ids if event["kind"] == "confirm" else outcome_ids
            if not isinstance(inputs, Mapping) or not isinstance(returned, Mapping) or not isinstance(inputs.get(input_name), str) or inputs[input_name] not in expected_ids:
                raise EvaluationRunError("confirmation or outcome event has invalid evidence")
    return EvaluationRun("harness_evaluation_run.v1", run_id, case_id, cell, normalized_environment, trace)


def _event_volume(returned: Mapping[str, Any]) -> tuple[int, int]:
    visible = returned.get("visible_count")
    if isinstance(visible, int) and not isinstance(visible, bool) and visible >= 0:
        items = visible
    elif isinstance(returned.get("rows"), list):
        items = len(returned["rows"])
    elif isinstance(returned.get("paths"), list):
        items = len(returned["paths"])
    else:
        items = 0
    ranges = returned.get("ranges") if isinstance(returned.get("ranges"), list) else ([] if returned.get("range") is None else [returned.get("range")])
    lines = sum(item["end_line"] - item["start_line"] + 1 for item in ranges if isinstance(item, Mapping) and isinstance(item.get("start_line"), int) and not isinstance(item.get("start_line"), bool) and isinstance(item.get("end_line"), int) and not isinstance(item.get("end_line"), bool) and item["start_line"] >= 1 and item["end_line"] >= item["start_line"])
    if not lines and not ranges and isinstance(returned.get("rows"), list):
        lines = sum(row["end_line"] - row["start_line"] + 1 for row in returned["rows"] if isinstance(row, Mapping) and isinstance(row.get("start_line"), int) and not isinstance(row.get("start_line"), bool) and isinstance(row.get("end_line"), int) and not isinstance(row.get("end_line"), bool) and row["start_line"] >= 1 and row["end_line"] >= row["start_line"])
    return items, lines


def _fulfillment(declared: Sequence[Mapping[str, str]], events: Sequence[Mapping[str, Any]], kind: str) -> tuple[Mapping[str, Any], ...]:
    field = "confirmation_id" if kind == "confirm" else "outcome_id"
    rows = []
    for requirement in declared:
        relevant = [event for event in events if event.get("kind") == kind and isinstance(event.get("inputs"), Mapping) and event["inputs"].get(field) == requirement["id"]]
        event_ids = sorted(str(event["id"]) for event in relevant)
        if not relevant:
            status = "missing"
        elif len(relevant) != 1:
            status = "duplicate"
        else:
            event, returned = relevant[0], relevant[0].get("returned")
            if event.get("status") != "completed" or not isinstance(returned, Mapping) or returned.get("status") != "passed":
                status = "failed"
            elif not returned.get("evidence"):
                status = "evidence_missing"
            else:
                status = "fulfilled"
        rows.append({"id": requirement["id"], "event_ids": event_ids, "status": status})
    return tuple(rows)


def evaluate_run(case: EvaluationCase, run: EvaluationRun) -> RunEvaluation:
    if not isinstance(case, EvaluationCase) or not isinstance(run, EvaluationRun) or run.case_id != case.id or not any(cell.id == run.cell.id for cell in case.cells):
        raise EvaluationRunError("case and run are not compatible")
    burden = {axis: 0 for axis in BURDEN_AXES}
    exposures: set[str] = set()
    for event in run.trace.events:
        burden["total_calls"] += 1
        kind = event.get("kind")
        if kind == "search": burden["search_calls"] += 1
        elif kind == "read": burden["read_calls"] += 1
        elif kind == "preparation": burden["preparation_calls"] += 1
        if event.get("status") in {"failed", "unknown"}: burden["failed_calls"] += 1
        returned = event.get("returned")
        if not isinstance(returned, Mapping):
            continue
        items, lines = _event_volume(returned)
        burden["returned_items"] += items
        burden["returned_lines"] += lines
        identity = {
            key: returned[key]
            for key in ("rows", "paths", "ranges", "range", "text")
            if key in returned and returned[key] not in (None, [], "")
        }
        if identity:
            rendered = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            if rendered in exposures:
                burden["duplicated_exposure"] += items if items else lines
            exposures.add(rendered)
    confirmations = _fulfillment(case.confirmations, run.trace.events, "confirm")
    outcomes = _fulfillment(case.outcomes, run.trace.events, "outcome")
    eligible = all(row["status"] == "fulfilled" for row in (*confirmations, *outcomes))
    return RunEvaluation("harness_run_evaluation.v1", case.id, run.id, run.cell.id, run.trace.binding_status, dict(run.environment), burden, confirmations, outcomes, eligible, run.cell)


def compare_runs(case: EvaluationCase, before: RunEvaluation, after: RunEvaluation) -> RunComparison:
    if not isinstance(case, EvaluationCase) or not isinstance(before, RunEvaluation) or not isinstance(after, RunEvaluation) or before.case_id != case.id or after.case_id != case.id:
        raise EvaluationComparisonError("evaluations are not comparable")
    repository_changed = before._cell.repository_variant != after._cell.repository_variant
    harness_changed = before._cell.harness_variant != after._cell.harness_variant
    if repository_changed == harness_changed:
        raise EvaluationComparisonError("comparison must change exactly one factor")
    expected_factor = "structure" if repository_changed else "harness"
    if case.factor != "interaction" and case.factor != expected_factor:
        raise EvaluationComparisonError("comparison does not match the declared factor")
    if repository_changed and before._cell.harness_variant != after._cell.harness_variant or harness_changed and before._cell.repository_variant != after._cell.repository_variant:
        raise EvaluationComparisonError("comparison changes more than one factor")
    delta = {axis: after.burden[axis] - before.burden[axis] for axis in BURDEN_AXES}
    if not before.eligible or not after.eligible:
        status = "ineligible"
    elif all(value == 0 for value in delta.values()): status = "unchanged"
    elif all(value <= 0 for value in delta.values()): status = "improved"
    elif all(value >= 0 for value in delta.values()): status = "regressed"
    else: status = "mixed"
    return RunComparison("harness_run_comparison.v1", case.id, expected_factor, before.run_id, after.run_id, delta, status)


def evaluation_to_json(value: RunEvaluation | RunComparison) -> str:
    if isinstance(value, RunEvaluation):
        data = {key: getattr(value, key) for key in ("schema", "case_id", "run_id", "cell_id", "binding_status", "environment", "burden", "confirmations", "outcomes", "eligible")}
    elif isinstance(value, RunComparison):
        data = {key: getattr(value, key) for key in ("schema", "case_id", "factor", "before_run_id", "after_run_id", "burden_delta", "status")}
    else:
        raise EvaluationRunError("evaluation has an invalid type")
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"


def _load_json(path: str) -> Mapping[str, object]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(value, Mapping):
        raise ValueError("JSON root must be an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bottlenecks.evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("case")
    evaluate.add_argument("run")
    evaluate.add_argument("profile")
    evaluate.add_argument("-s", "--support")
    evaluate.add_argument("-o", "--output", required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("case")
    compare.add_argument("before_run")
    compare.add_argument("before_profile")
    compare.add_argument("after_run")
    compare.add_argument("after_profile")
    compare.add_argument("-o", "--output", required=True)
    args = parser.parse_args(argv)
    try:
        case = parse_evaluation_case(_load_json(args.case))
        if args.command == "evaluate":
            profile = parse_harness_profile(_load_json(args.profile))
            if args.support:
                parse_harness_support(_load_json(args.support), profile)
            result = evaluate_run(case, parse_evaluation_run(_load_json(args.run), case, profile))
        else:
            before_profile = parse_harness_profile(_load_json(args.before_profile))
            after_profile = parse_harness_profile(_load_json(args.after_profile))
            before = evaluate_run(case, parse_evaluation_run(_load_json(args.before_run), case, before_profile))
            after = evaluate_run(case, parse_evaluation_run(_load_json(args.after_run), case, after_profile))
            result = compare_runs(case, before, after)
        Path(args.output).write_text(evaluation_to_json(result), encoding="utf-8")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")
    return 0


if __name__ == "__main__":
    main()
