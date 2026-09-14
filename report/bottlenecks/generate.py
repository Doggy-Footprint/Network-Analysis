import argparse
import html
import json
import math
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from report.shared.document import ReportInputError, ReportOutputError

SUPPORTED_SCHEMA = "bottlenecks.v2"

INLINE_CSS = """
:root {
  color-scheme: light dark;
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.5;
}
body {
  max-width: 96rem;
  margin: 0 auto;
  padding: 2rem;
  background: Canvas;
  color: CanvasText;
}
h1 { margin-top: 0; }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 1rem;
  margin: 1.5rem 0;
}
.panel {
  padding: 1rem;
  border: 1px solid color-mix(in srgb, CanvasText 20%, Canvas);
  border-radius: 0.5rem;
  background: color-mix(in srgb, CanvasText 4%, Canvas);
}
.panel h2 { margin: 0 0 0.75rem; font-size: 1rem; }
.bar-row { display: grid; grid-template-columns: minmax(7rem, 1fr) 3fr auto; gap: 0.5rem; align-items: center; margin: 0.35rem 0; }
.bar-track { height: 0.7rem; overflow: hidden; border-radius: 999px; background: color-mix(in srgb, CanvasText 12%, Canvas); }
.bar { height: 100%; min-width: 2px; border-radius: inherit; background: #4f46e5; }
.metric-chart { min-width: 16rem; }
.metric-chart .bar { background: #0891b2; }
.bar-label, .bar-value { overflow-wrap: anywhere; }
.bar-value { font-variant-numeric: tabular-nums; }
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.75rem 1rem;
  margin: 1.5rem 0 1rem;
}
.filter-bar label { font-weight: 600; }
.filter-bar input {
  display: block;
  box-sizing: border-box;
  width: min(32rem, 80vw);
  margin-top: 0.25rem;
  padding: 0.55rem 0.7rem;
  border: 1px solid GrayText;
  border-radius: 0.35rem;
  background: Field;
  color: FieldText;
  font: inherit;
}
.table-wrap { overflow-x: auto; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
th, td {
  padding: 0.65rem;
  border: 1px solid color-mix(in srgb, CanvasText 25%, Canvas);
  text-align: left;
  vertical-align: top;
}
th { background: color-mix(in srgb, CanvasText 8%, Canvas); }
tbody tr:nth-child(even) { background: color-mix(in srgb, CanvasText 4%, Canvas); }
pre {
  max-width: 42rem;
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
details {
  margin: 0.6rem 0;
  padding: 0.5rem 0.7rem;
  border: 1px solid color-mix(in srgb, CanvasText 20%, Canvas);
  border-radius: 0.35rem;
}
summary { cursor: pointer; font-weight: 600; }
[hidden] { display: none !important; }
""".strip()

INLINE_JS = """
(() => {
  const input = document.getElementById('candidate-filter');
  const count = document.getElementById('candidate-count');
  const rows = Array.from(document.querySelectorAll('[data-candidate-row]'));
  const applyFilter = () => {
    const query = input.value.trim().toLocaleLowerCase();
    let visible = 0;
    rows.forEach((row) => {
      const matches = row.textContent.toLocaleLowerCase().includes(query);
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    count.textContent = `${visible} of ${rows.length} candidates`;
  };
  input.addEventListener('input', applyFilter);
  applyFilter();
})();
""".strip()


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


def _kind_summary(candidates: Sequence[Mapping[str, Any]]) -> str:
    counts: dict[str, float] = {}
    for candidate in candidates:
        kind = candidate["kind"]
        counts[kind] = counts.get(kind, 0) + 1
    values = [(kind, count) for kind, count in sorted(counts.items())]
    return _bar_rows(values) if values else "<span>No candidates.</span>"


def render_report(payload: Any) -> str:
    data = _validate(payload)
    rows = []
    for candidate in data["candidates"]:
        rows.append(
            "<tr data-candidate-row>"
            f"<td>{html.escape(candidate['target'])}</td>"
            f"<td>{html.escape(candidate['kind'])}</td>"
            f"<td>{_candidate_metrics(candidate)}</td>"
            f"<td><pre>{_visible(candidate['evidence'])}</pre></td>"
            f"<td><pre>{_visible(candidate.get('obstacle'))}</pre></td>"
            f"<td>{html.escape(candidate['status'])}</td>"
            f"<td>{html.escape(candidate.get('validation_status', ''))}</td>"
            "</tr>"
        )
    embedded = _json(data).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    details = "".join(
        _details(title, data[field])
        for title, field in (
            ("Profile and settings", "profile"),
            ("Versions", "versions"),
            ("Coverage", "coverage"),
            ("Dependency network", "dependency_network"),
            ("Exploration network", "exploration_network"),
            ("Limitations", "limitations"),
            ("Probes", "probes"),
        )
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Repository bottlenecks</title><style>{INLINE_CSS}</style></head><body>"
        f"<h1>Repository bottlenecks</h1>{_details('Snapshot', data['snapshot'])}{details}"
        "<section class='summary-grid' aria-label='Candidate summary'>"
        f"<div class='panel'><h2>Candidates ({len(rows)})</h2>{_kind_summary(data['candidates'])}</div>"
        f"<div class='panel'><h2>Probes</h2><strong>{len(data['probes'])}</strong></div>"
        "</section>"
        "<div class='filter-bar'><label for='candidate-filter'>Filter candidates"
        "<input id='candidate-filter' type='search' placeholder='Target, kind, evidence, or status'></label>"
        f"<output id='candidate-count' for='candidate-filter'>{len(rows)} of {len(rows)} candidates</output></div>"
        "<div class='table-wrap'>"
        "<table><thead><tr><th>Target</th><th>Kind</th><th>Metrics</th><th>Evidence</th><th>Obstacle</th><th>Status</th><th>Validation</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        f"<script id='bottlenecks-data' type='application/json'>{embedded}</script><script>{INLINE_JS}</script></body></html>"
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
