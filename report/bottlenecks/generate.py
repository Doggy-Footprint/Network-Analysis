import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from report.shared.document import ReportInputError, ReportOutputError

SUPPORTED_SCHEMA = "bottlenecks.v1"


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


def _validate(payload: Any) -> Mapping[str, Any]:
    root = _object(payload, "$")
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


def render_report(payload: Any) -> str:
    data = _validate(payload)
    rows = []
    for candidate in data["candidates"]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(candidate['target'])}</td>"
            f"<td>{html.escape(candidate['kind'])}</td>"
            f"<td><pre>{_visible(candidate['metrics'])}</pre></td>"
            f"<td><pre>{_visible(candidate['evidence'])}</pre></td>"
            f"<td>{html.escape(candidate['status'])}</td>"
            "</tr>"
        )
    embedded = _json(data).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    details = "".join(
        _details(title, data[field])
        for title, field in (
            ("Profile and settings", "profile"),
            ("Versions", "versions"),
            ("Coverage", "coverage"),
            ("Limitations", "limitations"),
            ("Probes", "probes"),
            ("Observation comparison", "observations"),
        )
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Repository bottlenecks</title></head><body>"
        f"<h1>Repository bottlenecks</h1>{_details('Snapshot', data['snapshot'])}{details}"
        "<table><thead><tr><th>Target</th><th>Kind</th><th>Metrics</th><th>Evidence</th><th>Status</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        f"<script id='bottlenecks-data' type='application/json'>{embedded}</script></body></html>"
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
