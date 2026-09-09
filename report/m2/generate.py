import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Union

from bottlenecks.evaluation import BURDEN_AXES
from report.shared.document import (
    ReportInputError,
    ReportOutputError,
    array as _array,
    boolean as _boolean,
    fail as _fail,
    generate,
    integer as _integer,
    object_ as _object,
    string as _string,
)

EVALUATION_SCHEMA = "harness_run_evaluation.v1"
COMPARISON_SCHEMA = "harness_run_comparison.v1"
PAYLOAD_ID = "m2-harness-result-payload"
READY_EVENT = "m2-harness-result-ready"
READY_LABEL = '"M2 harness 결과 로드 완료"'
TEMPLATE_FILES = ("header.html", "evaluation.html", "comparison.html", "header.js", "result.js")
FULFILLMENT_STATUSES = {"missing", "duplicate", "failed", "evidence_missing", "fulfilled"}
COMPARISON_STATUSES = {"ineligible", "unchanged", "improved", "regressed", "mixed"}


def _template_dir() -> Path:
    return Path(__file__).resolve().parent / "templates"


def _exact(value: Dict[str, Any], path: str, fields: Sequence[str]) -> None:
    if set(value) != set(fields):
        _fail(path, "must contain exactly " + ", ".join(repr(field) for field in fields))


def _burden(value: Any, path: str, *, signed: bool) -> None:
    burden = _object(value, path)
    _exact(burden, path, BURDEN_AXES)
    for axis in BURDEN_AXES:
        _integer(burden[axis], f"{path}.{axis}", minimum=-sys.maxsize if signed else 0)


def _requirements(value: Any, path: str) -> None:
    rows = _array(value, path)
    seen = set()
    for index, raw in enumerate(rows):
        item_path = f"{path}[{index}]"
        item = _object(raw, item_path)
        _exact(item, item_path, ("id", "event_ids", "status"))
        identifier = _string(item["id"], f"{item_path}.id", allow_empty=False)
        if identifier in seen:
            _fail(path, "requirement ids must be unique")
        seen.add(identifier)
        if item["status"] not in FULFILLMENT_STATUSES:
            _fail(f"{item_path}.status", "has an invalid fulfillment status")
        for event_index, event_id in enumerate(_array(item["event_ids"], f"{item_path}.event_ids")):
            _string(event_id, f"{item_path}.event_ids[{event_index}]", allow_empty=False)


def _evaluation(root: Dict[str, Any]) -> Dict[str, Any]:
    _exact(root, "root", ("schema", "case_id", "run_id", "cell_id", "binding_status", "environment", "burden", "confirmations", "outcomes", "eligible"))
    for field in ("case_id", "run_id", "cell_id", "binding_status"):
        _string(root[field], f"root.{field}", allow_empty=False)
    environment = _object(root["environment"], "root.environment")
    _exact(environment, "root.environment", ("harness_version", "model_version"))
    for field in ("harness_version", "model_version"):
        _string(environment[field], f"root.environment.{field}", allow_empty=False)
    _burden(root["burden"], "root.burden", signed=False)
    _requirements(root["confirmations"], "root.confirmations")
    _requirements(root["outcomes"], "root.outcomes")
    _boolean(root["eligible"], "root.eligible")
    return root


def _comparison(root: Dict[str, Any]) -> Dict[str, Any]:
    _exact(root, "root", ("schema", "case_id", "factor", "before_run_id", "after_run_id", "burden_delta", "status"))
    for field in ("case_id", "before_run_id", "after_run_id"):
        _string(root[field], f"root.{field}", allow_empty=False)
    if root["factor"] not in {"structure", "harness"}:
        _fail("root.factor", "must be 'structure' or 'harness'")
    if root["status"] not in COMPARISON_STATUSES:
        _fail("root.status", "has an invalid comparison status")
    _burden(root["burden_delta"], "root.burden_delta", signed=True)
    return root


def _validate_payload(value: Any) -> Dict[str, Any]:
    root = _object(value, "root")
    if root.get("schema") == EVALUATION_SCHEMA:
        return _evaluation(root)
    if root.get("schema") == COMPARISON_SCHEMA:
        return _comparison(root)
    _fail("root.schema", f"must be {EVALUATION_SCHEMA!r} or {COMPARISON_SCHEMA!r}")


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
        json_path, output_path, validate=_validate_payload,
        template_dir=Path(template_dir) if template_dir is not None else _template_dir(),
        names=TEMPLATE_FILES, title="M2 Harness evaluation", payload_id=PAYLOAD_ID,
        ready_event=READY_EVENT, ready_label=READY_LABEL, label="m2-harness-result",
        read_text=read_text, write_text=write_text, compress=compress, stderr=stderr,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="M2 harness 결과 JSON을 단일 오프라인 HTML 보고서로 변환합니다.")
    parser.add_argument("result_json")
    parser.add_argument("-o", "--output")
    args = parser.parse_args(argv)
    try:
        output = generate_report(args.result_json, args.output)
    except (ReportInputError, ReportOutputError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
