import argparse
import html
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from report.shared.document import ReportInputError, ReportOutputError
from report.shared.labels import short_labels

SUPPORTED_SCHEMA = "bottlenecks.v6"

_ID_TARGET_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*):([A-Za-z0-9_.]+)(?:#(.+))?$")

KIND_LABELS = {
    "evidence_spread": "근거 분산",
    "large_node": "큰 노드",
    "unresolved_boundary": "정적 분석 미확정 참조",
    "dependency_cycle": "의존 순환",
    "package_cycle": "package 순환",
    "unstable_dependency": "불안정 package 의존",
    "rule_violation": "경계 규칙 위반",
}

KIND_DESCRIPTIONS = {
    "evidence_spread": "근거가 여러 파일에 흩어져 있거나 임계 줄 수를 넘는 범위에 걸친 사례입니다.",
    "large_node": "노드의 소스 범위가 large_node_line_threshold 줄을 넘는 사례입니다.",
    "unresolved_boundary": "분석 경계에서 해결되지 않은 참조가 남은 사례입니다.",
    "dependency_cycle": "파일들이 서로 의존해 순환을 이루는 사례입니다. 같은 순환도 연결 확실성 tier(certain, resolved, all)별로 따로 나옵니다.",
    "package_cycle": "package들이 서로 의존해 순환을 이루는 사례입니다.",
    "unstable_dependency": "package가 자신보다 불안정한(instability가 더 큰) package에 의존하는 사례입니다.",
    "rule_violation": "아키텍처 규칙 file에 선언된 layer 경계(allow 목록 밖 또는 forbid 대상)를 넘는 file 의존 사례입니다.",
}

METRIC_DEFINITIONS = [
    ("token_cost", "코드 조각을 읽는 데 드는 텍스트 양의 근사값입니다."),
    ("effective_token_cost", "token_cost에 배율을 곱한 값입니다. vendored 파일이나 /vendor/, /node_modules/ 경로는 0배, generated·migration 관련 파일이나 /migrations/, /alembic/versions/ 경로는 0.1배, 그 외는 1배입니다."),
    ("pagerank", "다른 node로부터 얼마나 많이 참조되는지를 나타내는 중요도 지표입니다. 확정되지 않은 edge는 edge_weights 설정만큼 할인됩니다."),
    ("weighted_centrality_cost", "pagerank × effective_token_cost로 계산됩니다."),
    ("fan_in", "들어오는 connection 수입니다."),
    ("fan_out", "나가는 connection 수입니다."),
    ("weighted_fan_in", "들어오는 병합 edge 가중치의 합입니다."),
    ("weighted_fan_out", "나가는 병합 edge 가중치의 합입니다."),
    ("hop_2_token_cost", "해당 node에서 2단계 이내로 도달 가능한 node들의 effective_token_cost 합계입니다."),
    ("betweenness_centrality", "다른 node 사이의 최단 경로에 얼마나 자주 놓이는지를 나타냅니다."),
]

CATEGORY_ORDER = ("production", "test", "generated", "vendored", "unknown")

_KIND_SCORE_FIELDS = {
    "large_node": ("line_count", 0),
    "evidence_spread": ("file_count", 0),
    "unresolved_boundary": ("unresolved_count", 1),
    "dependency_cycle": ("member_count", 0),
    "package_cycle": ("member_count", 0),
    "unstable_dependency": ("instability_delta", 0),
}


def _score_candidate(candidate: Mapping[str, Any]) -> float:
    field, default = _KIND_SCORE_FIELDS.get(candidate.get("kind"), (None, 0))
    if field is None:
        return 0.0
    return float((candidate.get("metrics") or {}).get(field, default))


def _parse_id_target(target: str) -> Optional[tuple[str, Optional[str]]]:
    match = _ID_TARGET_RE.match(target)
    if match is None:
        return None
    _lang, module, qual = match.groups()
    return module.replace(".", "/"), qual


def _build_target_labels(candidates: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    id_targets: dict[str, tuple[str, Optional[str]]] = {}
    other_targets: list[str] = []
    for candidate in candidates:
        target = candidate["target"]
        parsed = _parse_id_target(target)
        if parsed is not None:
            id_targets[target] = parsed
        else:
            other_targets.append(target)
    module_labels = short_labels([module for module, _qual in id_targets.values()])
    other_labels = short_labels(other_targets)
    labels: dict[str, str] = {}
    for target, (module, qual) in id_targets.items():
        short = module_labels.get(module, module)
        labels[target] = f"{short}:{qual}" if qual else short
    for target in other_targets:
        labels[target] = other_labels.get(target, target)
    return labels


def _prioritize(data: Mapping[str, Any]) -> list:
    candidates = data["candidates"]
    labels = _build_target_labels(candidates)
    entries = [
        {
            "candidate": candidate,
            "score": _score_candidate(candidate),
            "label": labels.get(candidate["target"], candidate["target"]),
        }
        for candidate in candidates
    ]
    entries.sort(key=lambda entry: (-entry["score"], entry["candidate"]["id"]))
    return entries


def prioritize_candidates(data: Mapping[str, Any]) -> list:
    validated = _validate(data)
    return _prioritize(validated)


def _focus_candidates(prioritized: list) -> list:
    groups: dict = {}
    for entry in prioritized:
        key = (entry["candidate"]["kind"], entry["candidate"]["target"])
        groups.setdefault(key, []).append(entry)
    deduped = []
    for entries in groups.values():
        best = min(entries, key=lambda entry: (-entry["score"], entry["candidate"]["id"]))
        deduped.append({**best, "duplicate_count": len(entries)})
    by_kind: dict = {}
    for entry in deduped:
        by_kind.setdefault(entry["candidate"]["kind"], []).append(entry)
    selected = []
    for entries in by_kind.values():
        entries.sort(key=lambda entry: (-entry["score"], entry["candidate"]["id"]))
        selected.extend(entries[:2])
    selected.sort(key=lambda entry: (-entry["score"], entry["candidate"]["id"]))
    return selected


def focus_candidates(data: Mapping[str, Any]) -> list:
    validated = _validate(data)
    return _focus_candidates(_prioritize(validated))

def _error(path: str, message: str) -> None:
    raise ReportInputError(f"{path}: {message}")


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        _error(path, "must be an object")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _error(path, "must be an array")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        _error(path, "must be a string")
    return value


def _integer(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _error(path, "must be a non-negative integer")
    return value


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _error(path, "must be a finite number")
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _error(path, "must be a boolean")
    return value


def _strings(value: Any, path: str) -> None:
    for index, item in enumerate(_array(value, path)):
        _string(item, f"{path}[{index}]")


def _evidence_rows(value: Any, path: str) -> None:
    for index, item in enumerate(_array(value, path)):
        item_path = f"{path}[{index}]"
        if isinstance(item, str):
            continue
        evidence = _object(item, item_path)
        if "path" in evidence:
            _string(evidence["path"], f"{item_path}.path")
        elif "file_path" in evidence:
            _string(evidence["file_path"], f"{item_path}.file_path")


def _required(value: Mapping[str, Any], path: str, fields: Sequence[str]) -> None:
    for field in fields:
        if field not in value:
            _error(path, f"missing required field {field!r}")


def _finite_values(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        _error(path, "must be finite")
    if isinstance(value, dict):
        for key, item in value.items():
            _finite_values(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _finite_values(item, f"{path}[{index}]")


def _validate(payload: Any) -> Mapping[str, Any]:
    _finite_values(payload)
    root = _object(payload, "$")
    fields = ("schema", "snapshot", "edge_weights", "versions", "coverage", "dependency_network", "candidates", "limitations")
    _required(root, "$", fields)
    schema = _string(root["schema"], "$.schema")
    if schema not in (SUPPORTED_SCHEMA, "bottlenecks.v7", "bottlenecks.v8"):
        _error("$.schema", f"must equal {SUPPORTED_SCHEMA!r}, 'bottlenecks.v7' or 'bottlenecks.v8'")
    if schema != SUPPORTED_SCHEMA:
        _required(root, "$", ("granularity",))
        if _string(root["granularity"], "$.granularity") != "file":
            _error("$.granularity", "must equal 'file'")
        fields = (*fields, "granularity")
    if set(root) != set(fields):
        _error("$", "contains unknown fields")
    for field in ("snapshot", "edge_weights", "versions", "coverage", "dependency_network"):
        _object(root[field], f"$.{field}")
    _strings(root["limitations"], "$.limitations")
    rankings = root["dependency_network"].get("rankings", {})
    for metric, entries in _object(rankings, "$.dependency_network.rankings").items():
        for index, item in enumerate(_array(entries, f"$.dependency_network.rankings.{metric}")):
            ranking_path = f"$.dependency_network.rankings.{metric}[{index}]"
            entry = _object(item, ranking_path)
            _required(entry, ranking_path, ("node_id", "value"))
            _number(entry["value"], f"{ranking_path}.value")
    if "rankings_by_category" in root["dependency_network"]:
        by_category_path = "$.dependency_network.rankings_by_category"
        for category, metrics in _object(root["dependency_network"]["rankings_by_category"], by_category_path).items():
            for metric, entries in _object(metrics, f"{by_category_path}.{category}").items():
                for index, item in enumerate(_array(entries, f"{by_category_path}.{category}.{metric}")):
                    ranking_path = f"{by_category_path}.{category}.{metric}[{index}]"
                    entry = _object(item, ranking_path)
                    _required(entry, ranking_path, ("node_id", "value"))
                    _number(entry["value"], f"{ranking_path}.value")
    candidate_ids: set[str] = set()
    for index, item in enumerate(_array(root["candidates"], "$.candidates")):
        path = f"$.candidates[{index}]"
        entry = _object(item, path)
        _required(entry, path, ("id", "kind", "target", "metrics", "evidence", "coverage", "status"))
        candidate_id = _string(entry["id"], f"{path}.id")
        if candidate_id in candidate_ids:
            _error(f"{path}.id", "must be unique")
        candidate_ids.add(candidate_id)
        if _string(entry["kind"], f"{path}.kind") not in KIND_LABELS:
            _error(f"{path}.kind", "is unsupported")
        _string(entry["target"], f"{path}.target")
        _string(entry["coverage"], f"{path}.coverage")
        if _string(entry["status"], f"{path}.status") != "static_candidate":
            _error(f"{path}.status", "must equal 'static_candidate'")
        for key, value in _object(entry["metrics"], f"{path}.metrics").items():
            _number(value, f"{path}.metrics.{key}")
        evidence = entry["evidence"]
        if isinstance(evidence, list):
            _evidence_rows(evidence, f"{path}.evidence")
        else:
            _evidence_rows([evidence], f"{path}.evidence")
    return root


def render_report(payload: Any) -> str:
    from report.unified import render_unified_report

    return render_unified_report(None, _validate(payload))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, document: str) -> None:
    path.write_text(document, encoding="utf-8")


def generate(
    input_path: Path,
    output_path: Path,
    *,
    read_text: Callable[[Path], str] = _read_text,
    write_text: Callable[[Path, str], None] = _write_text,
) -> Path:
    try:
        source = read_text(input_path)
    except Exception as exc:
        raise ReportInputError(f"cannot read JSON input {input_path}: {exc}") from exc
    try:
        payload = json.loads(source)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ReportInputError(f"invalid JSON input {input_path}: {exc}") from exc
    document = render_report(payload)
    try:
        write_text(output_path, document)
    except Exception as exc:
        raise ReportOutputError(f"cannot write HTML output {output_path}: {exc}") from exc
    return output_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m report.bottlenecks.generate")
    parser.add_argument("input")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args(argv)
    try:
        generate(Path(args.input), Path(args.output))
    except (ReportInputError, ReportOutputError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
