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

SUPPORTED_SCHEMA = "bottlenecks.v2"

_ID_TARGET_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*):([A-Za-z0-9_.]+)(?:#(.+))?$")

KIND_LABELS = {
    "output_truncation": "출력 잘림",
    "multiple_results": "다중 결과",
    "evidence_spread": "근거 분산",
    "read_limit": "읽기 한계",
    "connection_constraint": "연결 제약",
    "unresolved_boundary": "미해결 경계",
}

KIND_DESCRIPTIONS = {
    "output_truncation": "query 결과가 노출 한도를 넘어 생략된 사례입니다.",
    "multiple_results": "하나의 target에 결과가 여러 개 도달하는 사례입니다.",
    "evidence_spread": "근거가 여러 파일에 흩어져 있는 사례입니다.",
    "read_limit": "읽기 단위가 read_line_limit을 넘는 사례입니다.",
    "connection_constraint": "현재 생성되지 않음",
    "unresolved_boundary": "분석 경계에서 해결되지 않은 참조가 남은 사례입니다.",
}

METRIC_DEFINITIONS = [
    ("token_cost", "코드 조각을 읽는 데 드는 텍스트 양의 근사값입니다."),
    ("effective_token_cost", "token_cost에 배율을 곱한 값입니다. vendored 파일이나 /vendor/, /node_modules/ 경로는 0배, generated·migration 관련 파일이나 /migrations/, /alembic/versions/ 경로는 0.1배, 그 외는 1배입니다."),
    ("pagerank", "다른 node로부터 얼마나 많이 참조되는지를 나타내는 중요도 지표입니다."),
    ("weighted_centrality_cost", "pagerank × effective_token_cost로 계산됩니다."),
    ("fan_in", "들어오는 connection 수입니다."),
    ("fan_out", "나가는 connection 수입니다."),
    ("hop_2_token_cost", "해당 node에서 2단계 이내로 도달 가능한 node들의 effective_token_cost 합계입니다."),
    ("hop_3_token_cost", "해당 node에서 3단계 이내로 도달 가능한 node들의 effective_token_cost 합계입니다."),
    ("betweenness_centrality", "다른 node 사이의 최단 경로에 얼마나 자주 놓이는지를 나타냅니다."),
    ("degree_centrality", "해당 node에 연결된 edge 수를 전체 node 수 기준 최대 연결 수로 나눈 값입니다."),
]

_KIND_SCORE_FIELDS = {
    "output_truncation": ("omitted_count", 0),
    "multiple_results": ("total_count", 0),
    "evidence_spread": ("file_count", 0),
    "unresolved_boundary": ("unresolved_count", 1),
}


def _score_candidate(candidate: Mapping[str, Any]) -> float:
    kind = candidate.get("kind")
    metrics = candidate.get("metrics") or {}
    if kind == "read_limit":
        return float(metrics.get("line_count", 0)) - float(metrics.get("read_line_limit", 0))
    field, default = _KIND_SCORE_FIELDS.get(kind, (None, 0))
    if field is None:
        return 0.0
    return float(metrics.get(field, default))


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

def _templates_dir() -> Path:
    return Path(__file__).resolve().parent / "templates"


def _inline_css() -> str:
    return (_templates_dir() / "styles.css").read_text(encoding="utf-8").strip()


def _inline_js() -> str:
    return (_templates_dir() / "script.js").read_text(encoding="utf-8").strip()


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
    if root.get("schema") == SUPPORTED_SCHEMA:
        _required(root, "$", ("schema", "snapshot", "profile", "versions", "coverage", "dependency_network", "exploration_network", "probes", "candidates", "limitations"))
        if set(root) != {"schema", "snapshot", "profile", "versions", "coverage", "dependency_network", "exploration_network", "probes", "candidates", "limitations"}:
            _error("$", "contains unknown fields")
        for field in ("snapshot", "profile", "versions", "coverage", "dependency_network", "exploration_network"):
            _object(root[field], f"$.{field}")
        _strings(root["limitations"], "$.limitations")
        probe_ids: set[str] = set()
        for index, item in enumerate(_array(root["probes"], "$.probes")):
            entry = _object(item, f"$.probes[{index}]")
            _required(entry, f"$.probes[{index}]", ("probe", "output"))
            probe = _object(entry["probe"], f"$.probes[{index}].probe")
            probe_id = _string(probe.get("id"), f"$.probes[{index}].probe.id")
            if probe_id in probe_ids:
                _error(f"$.probes[{index}].probe.id", "must be unique")
            probe_ids.add(probe_id)
            output = _object(entry["output"], f"$.probes[{index}].output")
            for key in ("total_count", "visible_count", "omitted_count"):
                _integer(output.get(key), f"$.probes[{index}].output.{key}")
            if output["visible_count"] > output["total_count"] or output["omitted_count"] != output["total_count"] - output["visible_count"]:
                _error(f"$.probes[{index}].output", "has inconsistent counts")
        candidate_ids: set[str] = set()
        for index, item in enumerate(_array(root["candidates"], "$.candidates")):
            entry = _object(item, f"$.candidates[{index}]")
            _required(entry, f"$.candidates[{index}]", ("id", "kind", "target", "probe_ids", "metrics", "evidence", "coverage", "status"))
            candidate_id = _string(entry["id"], f"$.candidates[{index}].id")
            if candidate_id in candidate_ids:
                _error(f"$.candidates[{index}].id", "must be unique")
            candidate_ids.add(candidate_id)
            if _string(entry["kind"], f"$.candidates[{index}].kind") not in {"output_truncation", "multiple_results", "evidence_spread", "read_limit", "connection_constraint", "unresolved_boundary"}:
                _error(f"$.candidates[{index}].kind", "is unsupported")
            if _string(entry["status"], f"$.candidates[{index}].status") != "static_candidate":
                _error(f"$.candidates[{index}].status", "must equal 'static_candidate'")
        return root
    fields = ("schema", "snapshot", "profile", "versions", "coverage", "probes", "candidates", "observations", "limitations")
    _required(root, "$", fields)
    if _string(root["schema"], "$.schema") != SUPPORTED_SCHEMA:
        _error("$.schema", f"must equal {SUPPORTED_SCHEMA!r}")
    for field in ("snapshot", "profile", "versions", "coverage"):
        _object(root[field], f"$.{field}")
    _strings(root["limitations"], "$.limitations")

    probe_ids: set[str] = set()
    for index, item in enumerate(_array(root["probes"], "$.probes")):
        path = f"$.probes[{index}]"
        entry = _object(item, path)
        _required(entry, path, ("probe", "output", "visible_arrival_ids", "hidden_arrival_ids"))
        probe = _object(entry["probe"], f"{path}.probe")
        output = _object(entry["output"], f"{path}.output")
        _required(probe, f"{path}.probe", ("id", "kind", "scope", "surface", "term"))
        _required(output, f"{path}.output", ("probe_id", "rows", "total_count", "visible_count", "omitted_count", "truncated"))
        probe_id = _string(probe["id"], f"{path}.probe.id")
        if probe_id in probe_ids:
            _error(f"{path}.probe.id", "must be unique")
        probe_ids.add(probe_id)
        for field in ("kind", "scope", "surface", "term"):
            _string(probe[field], f"{path}.probe.{field}")
        if _string(output["probe_id"], f"{path}.output.probe_id") != probe_id:
            _error(f"{path}.output.probe_id", "must match probe.id")
        total = _integer(output["total_count"], f"{path}.output.total_count")
        visible = _integer(output["visible_count"], f"{path}.output.visible_count")
        omitted = _integer(output["omitted_count"], f"{path}.output.omitted_count")
        _boolean(output["truncated"], f"{path}.output.truncated")
        if visible > total:
            _error(f"{path}.output.visible_count", "must not exceed total_count")
        if omitted != total - visible:
            _error(f"{path}.output.omitted_count", "must equal total_count minus visible_count")
        _strings(entry["visible_arrival_ids"], f"{path}.visible_arrival_ids")
        _strings(entry["hidden_arrival_ids"], f"{path}.hidden_arrival_ids")
        for row_index, row_value in enumerate(_array(output["rows"], f"{path}.output.rows")):
            row_path = f"{path}.output.rows[{row_index}]"
            row = _object(row_value, row_path)
            _required(row, row_path, ("path",))
            _string(row["path"], f"{row_path}.path")

    for index, item in enumerate(_array(root["candidates"], "$.candidates")):
        path = f"$.candidates[{index}]"
        candidate = _object(item, path)
        required = ("id", "target", "kind", "metrics", "evidence", "status", "probe_ids", "reasons", "coverage")
        _required(candidate, path, required)
        for field in ("id", "target", "kind", "status", "coverage"):
            _string(candidate[field], f"{path}.{field}")
        if "validation_status" in candidate:
            if _string(candidate["validation_status"], f"{path}.validation_status") != "unverified":
                _error(f"{path}.validation_status", "must equal 'unverified'")
        if "affected_profile_ids" in candidate:
            _strings(candidate["affected_profile_ids"], f"{path}.affected_profile_ids")
        if "obstacle" in candidate:
            obstacle = _object(candidate["obstacle"], f"{path}.obstacle")
            _required(obstacle, f"{path}.obstacle", ("axis", "explanation"))
            _string(obstacle["axis"], f"{path}.obstacle.axis")
            _string(obstacle["explanation"], f"{path}.obstacle.explanation")
        _object(candidate["metrics"], f"{path}.metrics")
        _strings(candidate["reasons"], f"{path}.reasons")
        evidence = candidate["evidence"]
        if isinstance(evidence, list):
            _evidence_rows(evidence, f"{path}.evidence")
        else:
            evidence_object = _object(evidence, f"{path}.evidence")
            if "visible" in evidence_object:
                required_evidence = ("visible", "hidden", "visible_arrival_ids", "hidden_arrival_ids")
                _required(evidence_object, f"{path}.evidence", required_evidence)
                _evidence_rows(evidence_object["visible"], f"{path}.evidence.visible")
                _evidence_rows(evidence_object["hidden"], f"{path}.evidence.hidden")
                _strings(evidence_object["visible_arrival_ids"], f"{path}.evidence.visible_arrival_ids")
                _strings(evidence_object["hidden_arrival_ids"], f"{path}.evidence.hidden_arrival_ids")
            elif "path" in evidence_object:
                _string(evidence_object["path"], f"{path}.evidence.path")
            elif "edge" in evidence_object:
                _object(evidence_object["edge"], f"{path}.evidence.edge")
                if evidence_object.get("span") is not None:
                    _object(evidence_object["span"], f"{path}.evidence.span")
            else:
                _error(f"{path}.evidence", "has an unsupported object shape")
        references = _array(candidate["probe_ids"], f"{path}.probe_ids")
        for reference_index, reference_value in enumerate(references):
            reference_path = f"{path}.probe_ids[{reference_index}]"
            reference = _string(reference_value, reference_path)
            if reference not in probe_ids:
                _error(reference_path, "does not reference a probe")

    for index, item in enumerate(_array(root["observations"], "$.observations")):
        _object(item, f"$.observations[{index}]")
    return root


def _json(value: Any, *, indent: Optional[int] = None) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=indent)


def _visible(value: Any) -> str:
    return html.escape(_json(value, indent=2))


def _details(title: str, value: Any) -> str:
    return f"<details><summary>{html.escape(title)}</summary><pre>{_visible(value)}</pre></details>"


def _numeric_metrics(metrics: Mapping[str, Any]) -> list[tuple[str, float]]:
    return [
        (key, float(value))
        for key, value in sorted(metrics.items())
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    ]


def _bar_rows(values: Sequence[tuple[str, float]]) -> str:
    maximum = max((value for _, value in values), default=0)
    return "".join(
        "<div class='bar-row'>"
        f"<span class='bar-label'>{html.escape(label)}</span>"
        f"<div class='bar-track'><div class='bar' style='width: {value / maximum * 100 if maximum else 0:.2f}%'></div></div>"
        f"<output class='bar-value'>{value:g}</output></div>"
        for label, value in values
    )


def _candidate_metrics(candidate: Mapping[str, Any]) -> str:
    metrics = _numeric_metrics(candidate["metrics"])
    chart = f"<div class='metric-chart'>{_bar_rows(metrics)}</div>" if metrics else "<span>None</span>"
    return f"{chart}{_details('Raw metrics', candidate['metrics'])}"


def _kind_counts(candidates: Sequence[Mapping[str, Any]]) -> dict:
    counts: dict[str, int] = {kind: 0 for kind in KIND_LABELS}
    for candidate in candidates:
        kind = candidate["kind"]
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _evidence_lines(evidence: Any) -> list:
    lines: list = []

    def add(path: Any, line: Any) -> None:
        if not isinstance(path, str) or not path:
            return
        lines.append(f"{path}:{line}" if line is not None else path)

    def visit(value: Any) -> None:
        if isinstance(value, str):
            add(value, None)
        elif isinstance(value, dict):
            if "path" in value or "file_path" in value:
                add(value.get("path", value.get("file_path")), value.get("line"))
            for nested in value.values():
                if isinstance(nested, (list, dict)):
                    visit(nested)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(evidence)
    return lines


def _focus_reason(candidate: Mapping[str, Any], score: float) -> str:
    kind = candidate["kind"]
    metrics = candidate.get("metrics") or {}
    if kind == "output_truncation":
        return f"결과 {metrics.get('total_count', '?')}건 중 {metrics.get('omitted_count', score)}건이 생략되었습니다."
    if kind == "multiple_results":
        return f"결과가 {metrics.get('total_count', score)}건 도달합니다."
    if kind == "read_limit":
        return f"읽기 단위가 {metrics.get('line_count', '?')}줄로 한계 {metrics.get('read_line_limit', '?')}줄을 넘습니다."
    if kind == "evidence_spread":
        return f"근거가 {metrics.get('file_count', score)}개 파일에 분산되어 있습니다."
    if kind == "unresolved_boundary":
        return f"미해결 참조가 {metrics.get('unresolved_count', score)}건 남아 있습니다."
    return KIND_DESCRIPTIONS.get(kind, "")


def _ranking_entries(value: Any) -> list:
    entries: list = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                node_id = item.get("id") or item.get("target") or item.get("node_id") or ""
                metric_value = item.get("value")
                if metric_value is None:
                    metric_value = item.get("score", 0)
                entries.append((str(node_id), metric_value))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                entries.append((str(item[0]), item[1]))
    return entries


def render_report(payload: Any) -> str:
    data = _validate(payload)
    candidates = data["candidates"]
    priorities = _prioritize(data)
    target_labels = _build_target_labels(candidates)

    rows = []
    for candidate in candidates:
        search_text = " ".join(
            [
                candidate["target"],
                target_labels.get(candidate["target"], candidate["target"]),
                KIND_LABELS.get(candidate["kind"], candidate["kind"]),
                candidate["status"],
                *_evidence_lines(candidate["evidence"]),
            ]
        )
        rows.append(
            f"<tr data-candidate-row data-kind=\"{html.escape(candidate['kind'])}\" "
            f"data-search=\"{html.escape(search_text)}\">"
            f"<td title=\"{html.escape(candidate['target'])}\">{html.escape(target_labels.get(candidate['target'], candidate['target']))}</td>"
            f"<td>{html.escape(KIND_LABELS.get(candidate['kind'], candidate['kind']))}</td>"
            f"<td>{_candidate_metrics(candidate)}</td>"
            f"<td>{''.join(f'<div>{html.escape(line)}</div>' for line in _evidence_lines(candidate['evidence'])) or '<span class=\"muted\">근거 없음</span>'}</td>"
            f"<td>{_details('원본 JSON', candidate)}</td>"
            f"<td>{html.escape(candidate['status'])}</td>"
            "</tr>"
        )

    embedded = _json(data).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")

    focus_items = _focus_candidates(priorities)
    if focus_items:
        focus_html = "<ol class='focus-list'>" + "".join(
            f"<li title=\"{html.escape(item['candidate']['target'])}\"><strong>{html.escape(item['label'])}</strong> ({html.escape(KIND_LABELS.get(item['candidate']['kind'], item['candidate']['kind']))}, "
            f"score {item['score']:g}) — {html.escape(_focus_reason(item['candidate'], item['score']))}"
            + (f" <span class='muted'>같은 대상 {item['duplicate_count']}건</span>" if item["duplicate_count"] > 1 else "")
            + "</li>"
            for item in focus_items
        ) + "</ol>"
    else:
        focus_html = "<p>발견된 후보 없음</p>"

    kind_counts = _kind_counts(candidates)
    kinds_html = "<div class='kind-grid'>" + "".join(
        f"<div class='panel'><h3>{html.escape(KIND_LABELS[kind])}</h3><p>{html.escape(KIND_DESCRIPTIONS[kind])}</p><p><strong>{count}</strong>건</p></div>"
        for kind, count in sorted(kind_counts.items())
    ) + "</div>"

    kind_options = "".join(f"<option value='{html.escape(kind)}'>{html.escape(label)}</option>" for kind, label in sorted(KIND_LABELS.items()))

    rankings = (data.get("dependency_network") or {}).get("rankings") or {}
    if rankings:
        rankings_html = "".join(
            f"<div class='panel'><h3>{html.escape(str(metric))}</h3>{_bar_rows([(node_id, float(value)) for node_id, value in _ranking_entries(entries) if isinstance(value, (int, float)) and not isinstance(value, bool)][:10])}</div>"
            for metric, entries in sorted(rankings.items())
        )
    else:
        rankings_html = "<p>순위 데이터가 없습니다.</p>"

    profile_exposure = (data.get("exploration_network") or {}).get("profile_exposure") or {}
    limits_html = ""
    if "search_output_limit" in profile_exposure or "read_line_limit" in profile_exposure:
        limits_html = (
            "<div class='summary-grid'>"
            + (
                f"<div class='panel'><h2>search_output_limit</h2><strong>{html.escape(str(profile_exposure['search_output_limit']))}</strong>"
                "<p>검색 결과 한 번에 노출되는 최대 줄 수입니다.</p></div>"
                if "search_output_limit" in profile_exposure else ""
            )
            + (
                f"<div class='panel'><h2>read_line_limit</h2><strong>{html.escape(str(profile_exposure['read_line_limit']))}</strong>"
                "<p>읽기 단위 하나가 넘지 않아야 하는 최대 줄 수입니다.</p></div>"
                if "read_line_limit" in profile_exposure else ""
            )
            + "</div>"
        )

    appendix_details = "".join(
        _details(title, data[field])
        for title, field in (
            ("Coverage", "coverage"),
            ("Limitations", "limitations"),
            ("Probes", "probes"),
        )
    )

    glossary_html = (
        "<dl class='glossary-grid'>"
        + "".join(f"<div><dt>{html.escape(KIND_LABELS[kind])}</dt><dd>{html.escape(KIND_DESCRIPTIONS[kind])}</dd></div>" for kind in sorted(KIND_LABELS))
        + "<div><dt>score</dt><dd>후보를 정렬하는 데 쓰이는 측정값입니다. kind별로 다른 필드에서 계산됩니다.</dd></div>"
        + "<div><dt>probe</dt><dd>후보를 찾기 위해 실행한 개별 탐색입니다.</dd></div>"
        + "<div><dt>duplicate_count</dt><dd>같은 (kind, target) 조합에서 중복으로 발견되어 하나로 묶인 후보 건수입니다.</dd></div>"
        + "".join(f"<div><dt>{html.escape(term)}</dt><dd>{html.escape(desc)}</dd></div>" for term, desc in METRIC_DEFINITIONS if term in rankings)
        + "</dl>"
    )

    return (
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>저장소 병목 후보</title><style>{_inline_css()}</style></head><body>"
        "<h1>저장소 병목 후보</h1>"
        "<section id='overview'>"
        f"{_details('Snapshot', data['snapshot'])}"
        "<div class='summary-grid'>"
        f"<div class='panel'><h2>candidate 수</h2><strong>{len(candidates)}</strong></div>"
        f"<div class='panel'><h2>probe 수</h2><strong>{len(data['probes'])}</strong></div>"
        "</div>"
        f"{limits_html}"
        f"{_details('profile', data['profile'])}{_details('versions', data['versions'])}"
        "</section>"
        f"<section id='focus'><h2>먼저 볼 곳</h2>{focus_html}</section>"
        f"<section id='kinds'><h2>후보 종류</h2>{kinds_html}</section>"
        "<section id='candidates'><h2>후보 목록</h2>"
        "<div class='filter-bar'>"
        "<label for='candidate-filter'>후보 검색"
        "<input id='candidate-filter' type='search' placeholder='target, evidence, status'></label>"
        f"<label for='candidate-kind-filter'>종류<select id='candidate-kind-filter'><option value='all'>전체</option>{kind_options}</select></label>"
        f"<output id='candidate-count' for='candidate-filter'>{len(rows)} / {len(rows)} candidates</output>"
        "</div>"
        "<div class='table-wrap'>"
        "<table><thead><tr><th>target</th><th>종류</th><th>지표</th><th>근거</th><th>원본</th><th>상태</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        "</section>"
        f"<section id='rankings'><h2>지표별 순위</h2>{rankings_html}</section>"
        f"<section id='appendix'><h2>부록</h2>{appendix_details}</section>"
        f"<section id='glossary'><h2>용어 안내</h2>{glossary_html}</section>"
        f"<script id='bottlenecks-data' type='application/json'>{embedded}</script><script>{_inline_js()}</script></body></html>"
    )


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
