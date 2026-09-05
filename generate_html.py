import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Union


TEMPLATE_DIR = Path(__file__).resolve().parent / "html_template"
COMPONENTS = ("header", "summary", "distributions", "graph", "evidence", "glossary")
SCRIPTS = (
    "summary_model", "graph_model", "evidence_model", "header",
    "summary", "distributions", "graph", "evidence",
)
SUPPORTED_SCHEMA_VERSION = "2"


class ReportInputError(ValueError):
    pass


class ReportOutputError(RuntimeError):
    pass


def _fail(path: str, message: str) -> None:
    raise ReportInputError(f"{path}: {message}")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    return value


def _required(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        _fail(path, f"missing required field {key!r}")
    return mapping[key]


def _string(value: Any, path: str, *, nullable: bool = False) -> Optional[str]:
    if nullable and value is None:
        return None
    if not isinstance(value, str):
        _fail(path, "must be a string" + (" or null" if nullable else ""))
    return value


def _integer(value: Any, path: str, *, nullable: bool = False, minimum: int = 0) -> Optional[int]:
    if nullable and value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        _fail(path, f"must be an integer >= {minimum}" + (" or null" if nullable else ""))
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail(path, "must be a boolean")
    return value


def _list(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, list):
        _fail(path, "must be an array")
    return value


def _string_list(value: Any, path: str) -> Sequence[str]:
    result = _list(value, path)
    for index, item in enumerate(result):
        _string(item, f"{path}[{index}]")
    return result


def _validate_profile(value: Any) -> None:
    profile = _mapping(value, "profile")
    _string(_required(profile, "id", "profile"), "profile.id")
    _integer(_required(profile, "version", "profile"), "profile.version")
    _string(_required(profile, "content_hash", "profile"), "profile.content_hash")


def _validate_cost(value: Any, path: str) -> None:
    cost = _mapping(value, path)
    for field in ("token_estimate", "char_count", "line_count"):
        _integer(_required(cost, field, path), f"{path}.{field}")


def _validate_readable(value: Any, index: int) -> str:
    path = f"readable_nodes[{index}]"
    node = _mapping(value, path)
    identifier = _string(_required(node, "id", path), f"{path}.id")
    _string(_required(node, "file_path", path), f"{path}.file_path")
    _string(_required(node, "symbol_id", path), f"{path}.symbol_id", nullable=True)
    _string(_required(node, "label", path), f"{path}.label")
    _string(_required(node, "kind", path), f"{path}.kind")
    _integer(_required(node, "start_line", path), f"{path}.start_line", nullable=True)
    _integer(_required(node, "end_line", path), f"{path}.end_line", nullable=True)
    _validate_cost(_required(node, "read_cost", path), f"{path}.read_cost")
    _string_list(_required(node, "flags", path), f"{path}.flags")
    return identifier or ""


def _validate_occurrence(value: Any, path: str) -> str:
    occurrence = _mapping(value, path)
    _string(_required(occurrence, "file_path", path), f"{path}.file_path")
    _integer(_required(occurrence, "line", path), f"{path}.line", minimum=1)
    _integer(_required(occurrence, "col", path), f"{path}.col")
    _string(_required(occurrence, "matched_text", path), f"{path}.matched_text")
    _string(_required(occurrence, "context", path), f"{path}.context")
    return _string(
        _required(occurrence, "enclosing_node_id", path),
        f"{path}.enclosing_node_id",
    ) or ""


def _validate_query(value: Any, index: int) -> tuple[str, Sequence[str]]:
    path = f"query_nodes[{index}]"
    node = _mapping(value, path)
    identifier = _string(_required(node, "id", path), f"{path}.id") or ""
    _string(_required(node, "term", path), f"{path}.term")
    _string(_required(node, "kind", path), f"{path}.kind")
    _string_list(_required(node, "clue_kinds", path), f"{path}.clue_kinds")
    origins = _string_list(_required(node, "origin_node_ids", path), f"{path}.origin_node_ids")
    _string(_required(node, "rule_id", path), f"{path}.rule_id", nullable=True)
    _string_list(_required(node, "source_terms", path), f"{path}.source_terms")
    occurrences = _list(_required(node, "occurrences", path), f"{path}.occurrences")
    occurrence_refs = [
        _validate_occurrence(item, f"{path}.occurrences[{occurrence_index}]")
        for occurrence_index, item in enumerate(occurrences)
    ]
    _string(_required(node, "occurrence_digest", path), f"{path}.occurrence_digest")
    arrivals = _string_list(_required(node, "arrival_node_ids", path), f"{path}.arrival_node_ids")
    _integer(_required(node, "output_tokens", path), f"{path}.output_tokens")
    _boolean(_required(node, "excluded", path), f"{path}.excluded")
    _string(_required(node, "exclusion_reason", path), f"{path}.exclusion_reason", nullable=True)
    return identifier, tuple(origins) + tuple(arrivals) + tuple(occurrence_refs)


def _validate_framework_link(value: Any, index: int) -> tuple[str, Sequence[str], Optional[str]]:
    path = f"framework_links[{index}]"
    link = _mapping(value, path)
    identifier = _string(_required(link, "id", path), f"{path}.id") or ""
    from_id = _string(_required(link, "from_node_id", path), f"{path}.from_node_id") or ""
    _string(_required(link, "rule_id", path), f"{path}.rule_id")
    _string(_required(link, "specificity", path), f"{path}.specificity")
    _string(_required(link, "resolution", path), f"{path}.resolution")
    targets = _string_list(_required(link, "to_node_ids", path), f"{path}.to_node_ids")
    candidates = _string_list(_required(link, "candidate_node_ids", path), f"{path}.candidate_node_ids")
    query_id = _string(_required(link, "query_id", path), f"{path}.query_id", nullable=True)
    _string(_required(link, "evidence_file", path), f"{path}.evidence_file")
    _integer(_required(link, "evidence_line", path), f"{path}.evidence_line", minimum=1)
    return identifier, (from_id, *targets, *candidates), query_id


def _validate_scan(value: Any) -> None:
    scan = _mapping(value, "scan")
    _string(_required(scan, "ignore_source", "scan"), "scan.ignore_source")
    for field in ("scanned_file_count", "generated_file_count", "generated_node_count"):
        _integer(_required(scan, field, "scan"), f"scan.{field}")
    excluded = _list(_required(scan, "excluded_files", "scan"), "scan.excluded_files")
    for index, value in enumerate(excluded):
        path = f"scan.excluded_files[{index}]"
        entry = _mapping(value, path)
        _string(_required(entry, "file_path", path), f"{path}.file_path")
        _string(_required(entry, "reason", path), f"{path}.reason")
    _string_list(_required(scan, "unknown_framework_edges", "scan"), "scan.unknown_framework_edges")


def _unique(ids: Iterable[str], collection: str) -> set[str]:
    seen: set[str] = set()
    for identifier in ids:
        if identifier in seen:
            _fail(collection, f"duplicate id {identifier!r}")
        seen.add(identifier)
    return seen


def _references_exist(references: Iterable[str], valid: set[str], path: str) -> None:
    for identifier in references:
        if identifier not in valid:
            _fail(path, f"dangling reference {identifier!r}")


def _validate_payload(value: Any) -> Dict[str, Any]:
    payload = _mapping(value, "root")
    version = _string(_required(payload, "schema_version", "root"), "schema_version")
    if version != SUPPORTED_SCHEMA_VERSION:
        _fail("schema_version", f"unsupported version {version!r}; expected {SUPPORTED_SCHEMA_VERSION!r}")
    _string(_required(payload, "project_name", "root"), "project_name")
    _validate_profile(_required(payload, "profile", "root"))

    readable_values = _list(_required(payload, "readable_nodes", "root"), "readable_nodes")
    readable_ids = _unique(
        (_validate_readable(value, index) for index, value in enumerate(readable_values)),
        "readable_nodes",
    )

    query_values = _list(_required(payload, "query_nodes", "root"), "query_nodes")
    query_results = [_validate_query(value, index) for index, value in enumerate(query_values)]
    query_ids = _unique((result[0] for result in query_results), "query_nodes")
    shared_ids = readable_ids & query_ids
    if shared_ids:
        _fail("graph nodes", f"duplicate id {sorted(shared_ids)[0]!r}")
    for index, result in enumerate(query_results):
        _references_exist(result[1], readable_ids, f"query_nodes[{index}]")

    link_values = _list(_required(payload, "framework_links", "root"), "framework_links")
    link_results = [_validate_framework_link(value, index) for index, value in enumerate(link_values)]
    _unique((result[0] for result in link_results), "framework_links")
    for index, result in enumerate(link_results):
        _references_exist(result[1], readable_ids, f"framework_links[{index}]")
        if result[2] is not None:
            _references_exist((result[2],), query_ids, f"framework_links[{index}].query_id")

    unreachable = _string_list(
        _required(payload, "unreachable_node_ids", "root"),
        "unreachable_node_ids",
    )
    _references_exist(unreachable, readable_ids, "unreachable_node_ids")
    _validate_scan(_required(payload, "scan", "root"))
    return dict(payload)


def _read_payload(path: Path) -> Dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ReportInputError(f"cannot read JSON input {path}: {error}") from error
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ReportInputError(f"invalid JSON input {path}: {error}") from error
    return _validate_payload(value)


def _read_template(name: str) -> str:
    path = TEMPLATE_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ReportOutputError(f"cannot read template {path}: {error}") from error


def _safe_json(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _build_document(payload: Mapping[str, Any]) -> str:
    base = _read_template("base.html")
    components = "\n".join(_read_template(f"{name}.html").rstrip() for name in COMPONENTS)
    scripts = "\n".join(f"<script>\n{_read_template(f'{name}.js').rstrip()}\n</script>" for name in SCRIPTS)
    replacements = {
        "@@TITLE@@": html.escape(f"{payload['project_name']} · Agent-view graph"),
        "@@STYLE@@": _read_template("common.css").rstrip(),
        "@@COMPONENTS@@": components,
        "@@DATA@@": _safe_json(payload),
        "@@SCRIPTS@@": scripts,
    }
    for marker in replacements:
        if base.count(marker) != 1:
            raise ReportOutputError(f"base template must contain exactly one {marker} marker")
    document = "".join(replacements.get(part, part) for part in re.split("(@@[A-Z]+@@)", base))
    return document.rstrip() + "\n"


def generate_report(
    json_path: Union[str, Path],
    output_path: Union[str, Path, None] = None,
) -> Path:
    source = Path(json_path).expanduser().resolve()
    output = (
        Path(output_path).expanduser().resolve()
        if output_path is not None
        else source.with_suffix(".html")
    )
    if source == output:
        raise ReportOutputError("input and output paths must be different")
    payload = _read_payload(source)
    document = _build_document(payload)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document, encoding="utf-8", newline="\n")
    except (OSError, UnicodeError) as error:
        raise ReportOutputError(f"cannot write HTML output {output}: {error}") from error
    return output


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="M1 agent-view JSON을 단일 HTML 보고서로 변환합니다.")
    parser.add_argument("agent_view_json", help="schema_version 2 agent-view JSON 경로")
    parser.add_argument("-o", "--output", help="출력 HTML 경로")
    args = parser.parse_args(argv)
    try:
        output = generate_report(args.agent_view_json, args.output)
    except (ReportInputError, ReportOutputError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
