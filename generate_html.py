import argparse
import base64
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Union

SUPPORTED_SCHEMA_VERSION = "3"
SIZE_WARNING_BYTES = 10 * 1024 * 1024
TEMPLATE_FILES = (
    "common.css", "header.html", "summary.html", "distributions.html", "graph.html",
    "evidence.html", "glossary.html", "summary_model.js", "graph_model.js",
    "evidence_model.js", "header.js", "summary.js", "distributions.js", "graph.js", "evidence.js",
)

class ReportInputError(ValueError):
    pass

class ReportOutputError(RuntimeError):
    pass

def _fail(path: str, message: str) -> None:
    raise ReportInputError(f"{path}: {message}")

def _object(value: Any, path: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    return value

def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(path, "must be an array")
    return value

def _string(value: Any, path: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        _fail(path, "must be a string" if allow_empty else "must be a non-empty string")
    return value

def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        _fail(path, f"must be an integer >= {minimum}")
    return value

def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail(path, "must be a boolean")
    return value

def _required(value: Mapping[str, Any], path: str, fields: Sequence[str]) -> None:
    for field in fields:
        if field not in value:
            _fail(path, f"missing required field {field!r}")

def _string_array(value: Any, path: str) -> list[str]:
    result = _array(value, path)
    for index, item in enumerate(result):
        _string(item, f"{path}[{index}]")
    return result

def _validate_node_cost(value: Any, path: str) -> None:
    cost = _object(value, path)
    _required(cost, path, ("char_count", "line_count", "token_estimate"))
    for field in ("char_count", "line_count", "token_estimate"):
        _integer(cost[field], f"{path}.{field}")

def _decode_block(block: Mapping[str, Any], path: str) -> list[Any]:
    if block["encoding"] != "gzip+base64":
        _fail(f"{path}.encoding", "must be 'gzip+base64'")
    try:
        compressed = base64.b64decode(block["data"], validate=True)
    except (ValueError, TypeError) as error:
        _fail(f"{path}.data", f"invalid base64: {error}")
    try:
        raw = gzip.decompress(compressed)
    except (OSError, EOFError) as error:
        _fail(f"{path}.data", f"invalid gzip: {error}")
    if hashlib.sha256(raw).hexdigest() != block["sha256"]:
        _fail(f"{path}.sha256", "digest does not match decoded data")
    try:
        rows = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"{path}.data", f"decoded data is not valid JSON: {error}")
    if not isinstance(rows, list):
        _fail(f"{path}.data", "decoded data must be an array")
    for index, item in enumerate(rows):
        row_path = f"{path}.data[{index}]"
        row = _object(item, row_path)
        _required(row, row_path, ("file_path", "line", "col", "matched_text", "context", "enclosing_node_id", "surface"))
        for field in ("file_path", "matched_text", "context", "enclosing_node_id", "surface"):
            _string(row[field], f"{row_path}.{field}", allow_empty=field == "matched_text")
        _integer(row["line"], f"{row_path}.line", minimum=1)
        _integer(row["col"], f"{row_path}.col")
    return rows

def _occurrence_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    text = "\n".join(f"{row['file_path']}|{row['line']}|{row['col']}|{row['matched_text']}|{row['context']}|{row['enclosing_node_id']}|{row['surface']}" for row in rows)
    return hashlib.sha256(text.encode()).hexdigest()

def _validate_payload(value: Any) -> Dict[str, Any]:
    root = _object(value, "root")
    if root.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        _fail("schema_version", f"unsupported version {root.get('schema_version')!r}; expected '3'")
    required = ("project_name", "profile", "scan", "read_units", "readable_nodes", "query_nodes", "connections", "entry_documents", "hint_store", "occurrence_store")
    _required(root, "root", required)
    _string(root["project_name"], "project_name")
    profile = _object(root["profile"], "profile")
    profile_limits = ("min_term_length", "max_file_bytes", "read_unit_token_limit", "read_query_candidate_limit", "search_output_limit", "hint_query_limit", "refinement_threshold", "refinement_query_limit", "refinement_depth_limit", "root_list_depth", "root_list_entry_limit", "occurrence_block_rows", "context_lines", "generated_marker_lines")
    profile_lists = ("vendor_globs", "generated_globs", "generated_markers", "lockfile_names")
    profile_versions = ("split_version", "ordering_version", "output_format_version", "query_equivalence_version", "read_limit_provenance", "search_limit_provenance")
    _required(profile, "profile", ("id", "version", "content_hash", "transforms", "include_agent_docs", "tracked_files_only") + profile_limits + profile_lists + profile_versions)
    _string(profile["id"], "profile.id", allow_empty=False)
    if _integer(profile["version"], "profile.version", minimum=1) != 3:
        _fail("profile.version", "must be 3")
    _string(profile["content_hash"], "profile.content_hash", allow_empty=False)
    for field in profile_limits:
        _integer(profile[field], f"profile.{field}", minimum=0 if field == "context_lines" else 1)
    for field in profile_lists:
        _string_array(profile[field], f"profile.{field}")
    for field in profile_versions:
        _string(profile[field], f"profile.{field}", allow_empty=False)
    _boolean(profile["include_agent_docs"], "profile.include_agent_docs")
    _boolean(profile["tracked_files_only"], "profile.tracked_files_only")
    for index, item in enumerate(_array(profile["transforms"], "profile.transforms")):
        path = f"profile.transforms[{index}]"
        transform = _object(item, path)
        _required(transform, path, ("id", "prefixes", "suffixes"))
        _string(transform["id"], f"{path}.id", allow_empty=False)
        _string_array(transform["prefixes"], f"{path}.prefixes")
        _string_array(transform["suffixes"], f"{path}.suffixes")
    scan = _object(root["scan"], "scan")
    _required(scan, "scan", ("ignore_source", "scanned_file_count", "excluded_files", "exclusion_counts", "snapshot_digest"))
    _string(scan["ignore_source"], "scan.ignore_source")
    _integer(scan["scanned_file_count"], "scan.scanned_file_count")
    _object(scan["exclusion_counts"], "scan.exclusion_counts")
    _string(scan["snapshot_digest"], "scan.snapshot_digest", allow_empty=False)
    for index, item in enumerate(_array(scan["excluded_files"], "scan.excluded_files")):
        path = f"scan.excluded_files[{index}]"
        entry = _object(item, path)
        _required(entry, path, ("file_path", "reason"))
        _string(entry["file_path"], f"{path}.file_path", allow_empty=False)
        _string(entry["reason"], f"{path}.reason", allow_empty=False)
    unit_ids: set[str] = set()
    for index, item in enumerate(_array(root["read_units"], "read_units")):
        path = f"read_units[{index}]"
        unit = _object(item, path)
        _required(unit, path, ("id", "file_path", "start_line", "end_line", "symbol_ids", "read_cost", "oversized_symbol"))
        unit_id = _string(unit["id"], f"{path}.id", allow_empty=False)
        if unit_id in unit_ids:
            _fail(f"{path}.id", "duplicate read unit id")
        unit_ids.add(unit_id)
        _string(unit["file_path"], f"{path}.file_path", allow_empty=False)
        start = _integer(unit["start_line"], f"{path}.start_line", minimum=1)
        end = _integer(unit["end_line"], f"{path}.end_line", minimum=1)
        if end < start:
            _fail(path, "end_line must be >= start_line")
        _string_array(unit["symbol_ids"], f"{path}.symbol_ids")
        _validate_node_cost(unit["read_cost"], f"{path}.read_cost")
        _boolean(unit["oversized_symbol"], f"{path}.oversized_symbol")
    node_ids: set[str] = set()
    for index, item in enumerate(_array(root["readable_nodes"], "readable_nodes")):
        path = f"readable_nodes[{index}]"
        node = _object(item, path)
        _required(node, path, ("id", "file_path", "symbol_id", "label", "kind", "start_line", "end_line", "read_cost", "flags", "read_unit_id"))
        node_id = _string(node["id"], f"{path}.id", allow_empty=False)
        if node_id in node_ids:
            _fail(f"{path}.id", "duplicate readable node id")
        node_ids.add(node_id)
        for field in ("file_path", "label", "kind", "read_unit_id"):
            _string(node[field], f"{path}.{field}", allow_empty=field == "label")
        if node["read_unit_id"] not in unit_ids:
            _fail(f"{path}.read_unit_id", "references an unknown read unit")
        if node["symbol_id"] is not None:
            _string(node["symbol_id"], f"{path}.symbol_id", allow_empty=False)
        if (node["start_line"] is None) != (node["end_line"] is None):
            _fail(path, "start_line and end_line must both be null or integers")
        if node["start_line"] is not None:
            start = _integer(node["start_line"], f"{path}.start_line", minimum=1)
            end = _integer(node["end_line"], f"{path}.end_line", minimum=1)
            if end < start:
                _fail(path, "end_line must be >= start_line")
        _validate_node_cost(node["read_cost"], f"{path}.read_cost")
        _string_array(node["flags"], f"{path}.flags")
    blocks: Dict[str, tuple[Dict[str, Any], list[Any]]] = {}
    expected_start = 0
    for index, item in enumerate(_array(root["occurrence_store"], "occurrence_store")):
        path = f"occurrence_store[{index}]"
        block = _object(item, path)
        _required(block, path, ("id", "start", "end", "count", "sha256", "encoding", "data"))
        block_id = _string(block["id"], f"{path}.id", allow_empty=False)
        if block_id in blocks:
            _fail(f"{path}.id", "duplicate occurrence block id")
        start = _integer(block["start"], f"{path}.start")
        end = _integer(block["end"], f"{path}.end")
        count = _integer(block["count"], f"{path}.count")
        if start != expected_start or end != start + count:
            _fail(path, "start/end/count do not form a contiguous range")
        _string(block["sha256"], f"{path}.sha256", allow_empty=False)
        _string(block["encoding"], f"{path}.encoding", allow_empty=False)
        _string(block["data"], f"{path}.data")
        rows = _decode_block(block, path)
        if len(rows) != count:
            _fail(f"{path}.count", "does not match decoded row count")
        blocks[block_id] = (block, rows)
        expected_start = end
    query_ids: set[str] = set()
    for index, item in enumerate(_array(root["query_nodes"], "query_nodes")):
        path = f"query_nodes[{index}]"
        query = _object(item, path)
        fields = ("id", "term", "kind", "surface", "scope", "clue_kinds", "origin_node_ids", "rule_id", "source_terms", "occurrence_ranges", "occurrence_digest", "arrival_node_ids", "total_count", "visible_count", "truncated", "output_tokens", "duplicate_suppressed_count", "candidate_filtered_count", "candidate_cap_truncated", "refinement_depth")
        _required(query, path, fields)
        query_id = _string(query["id"], f"{path}.id", allow_empty=False)
        if query_id in query_ids:
            _fail(f"{path}.id", "duplicate query id")
        query_ids.add(query_id)
        for field in ("term", "kind", "surface", "scope", "occurrence_digest"):
            _string(query[field], f"{path}.{field}", allow_empty=field == "term")
        if query["rule_id"] is not None:
            _string(query["rule_id"], f"{path}.rule_id", allow_empty=False)
        for field in ("clue_kinds", "origin_node_ids", "source_terms", "arrival_node_ids"):
            _string_array(query[field], f"{path}.{field}")
        total = _integer(query["total_count"], f"{path}.total_count")
        visible = _integer(query["visible_count"], f"{path}.visible_count")
        _boolean(query["truncated"], f"{path}.truncated")
        if visible > total:
            _fail(path, "visible_count must not exceed total_count")
        if query["truncated"] != (visible < total):
            _fail(f"{path}.truncated", "must equal visible_count < total_count")
        _boolean(query["candidate_cap_truncated"], f"{path}.candidate_cap_truncated")
        for field in ("output_tokens", "duplicate_suppressed_count", "candidate_filtered_count", "refinement_depth"):
            _integer(query[field], f"{path}.{field}")
        referenced_rows: list[Any] = []
        for range_index, item_range in enumerate(_array(query["occurrence_ranges"], f"{path}.occurrence_ranges")):
            range_path = f"{path}.occurrence_ranges[{range_index}]"
            ref = _object(item_range, range_path)
            _required(ref, range_path, ("block_id", "start", "count"))
            block_id = _string(ref["block_id"], f"{range_path}.block_id", allow_empty=False)
            if block_id not in blocks:
                _fail(f"{range_path}.block_id", "references an unknown occurrence block")
            start = _integer(ref["start"], f"{range_path}.start")
            count = _integer(ref["count"], f"{range_path}.count")
            rows = blocks[block_id][1]
            if start + count > len(rows):
                _fail(range_path, "range exceeds occurrence block")
            referenced_rows.extend(rows[start:start + count])
        if len(referenced_rows) != total:
            _fail(f"{path}.total_count", "does not match occurrence ranges")
        if query["occurrence_digest"] != _occurrence_digest(referenced_rows):
            _fail(f"{path}.occurrence_digest", "does not match referenced occurrences")
        for field in ("origin_node_ids", "arrival_node_ids"):
            for node_id in query[field]:
                if node_id not in node_ids:
                    _fail(f"{path}.{field}", f"references unknown readable node {node_id!r}")
    all_ids = node_ids | query_ids
    hints = _object(root["hint_store"], "hint_store")
    for hint_id, item in hints.items():
        _string(hint_id, "hint_store key", allow_empty=False)
        path = f"hint_store[{hint_id!r}]"
        hint = _object(item, path)
        _required(hint, path, ("path", "file_name", "symbol_name", "roles", "identifiers"))
        for field in ("path", "file_name", "symbol_name"):
            _string(hint[field], f"{path}.{field}", allow_empty=field == "symbol_name")
        for field in ("roles", "identifiers"):
            _string_array(hint[field], f"{path}.{field}")
    for index, item in enumerate(_array(root["connections"], "connections")):
        path = f"connections[{index}]"
        connection = _object(item, path)
        _required(connection, path, ("id", "from_id", "to_id", "kind", "specificity", "evidence"))
        for field in ("id", "from_id", "to_id", "kind", "specificity"):
            _string(connection[field], f"{path}.{field}", allow_empty=False)
        if connection["from_id"] not in all_ids or connection["to_id"] not in all_ids:
            _fail(path, "connection endpoint is not a readable or query node")
        _object(connection["evidence"], f"{path}.evidence")
        hint_id = connection["evidence"].get("hint_id")
        if hint_id is not None and hint_id not in hints:
            _fail(f"{path}.evidence.hint_id", "references an unknown hint")
    for index, item in enumerate(_array(root["entry_documents"], "entry_documents")):
        path = f"entry_documents[{index}]"
        entry = _object(item, path)
        _required(entry, path, ("node_id", "file_path", "injected"))
        if _string(entry["node_id"], f"{path}.node_id", allow_empty=False) not in node_ids:
            _fail(f"{path}.node_id", "references an unknown readable node")
        _string(entry["file_path"], f"{path}.file_path", allow_empty=False)
        _boolean(entry["injected"], f"{path}.injected")
    return dict(root)

def _default_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def _read_payload(path: Path, read_text: Callable[[Path], str]) -> Dict[str, Any]:
    try:
        text = read_text(path)
    except Exception as error:
        raise ReportOutputError(f"cannot read JSON input {path}: {error}") from error
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError) as error:
        raise ReportInputError(f"invalid JSON input {path}: {error}") from error
    return _validate_payload(value)

def _load_templates(template_dir: Path, read_text: Callable[[Path], str]) -> Dict[str, str]:
    try:
        templates = {name: read_text(template_dir / name) for name in ("base.html",) + TEMPLATE_FILES}
    except Exception as error:
        raise ReportOutputError(f"cannot read report template: {error}") from error
    for marker in ("@@TITLE@@", "@@STYLE@@", "@@COMPONENTS@@", "@@DATA@@", "@@SCRIPTS@@"):
        if templates["base.html"].count(marker) != 1:
            raise ReportOutputError(f"invalid report template: expected exactly one {marker}")
    return templates

def _build_document(payload: Mapping[str, Any], templates: Mapping[str, str], compress: Callable[[bytes], bytes]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    try:
        compressed = compress(raw)
        if not isinstance(compressed, bytes) or gzip.decompress(compressed) != raw:
            raise ValueError("compressor did not return a gzip encoding of the payload")
        encoded = base64.b64encode(compressed).decode("ascii")
    except Exception as error:
        raise ReportOutputError(f"cannot compress report payload: {error}") from error
    components = "\n".join(templates[name] for name in TEMPLATE_FILES if name.endswith(".html"))
    scripts = "\n".join(f"<script>\n{templates[name]}\n</script>" for name in TEMPLATE_FILES if name.endswith(".js"))
    return (templates["base.html"].replace("@@TITLE@@", "Agent-view graph").replace("@@STYLE@@", templates["common.css"]).replace("@@COMPONENTS@@", components).replace("@@DATA@@", encoded).replace("@@SCRIPTS@@", scripts))

def _gzip(raw: bytes) -> bytes:
    return gzip.compress(raw, compresslevel=9, mtime=0)

def generate_report(json_path: Union[str, Path], output_path: Union[str, Path, None] = None, *, read_text: Optional[Callable[[Path], str]] = None, write_text: Optional[Callable[[Path, str], None]] = None, compress: Optional[Callable[[bytes], bytes]] = None, template_dir: Optional[Union[str, Path]] = None, stderr: Any = None) -> Path:
    source = Path(json_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve() if output_path is not None else source.with_suffix(".html")
    if source == output:
        raise ReportOutputError("input and output paths must be different")
    reader = read_text or _default_read_text
    payload = _read_payload(source, reader)
    templates = _load_templates(Path(template_dir) if template_dir is not None else Path(__file__).with_name("html_template"), reader)
    document = _build_document(payload, templates, compress or _gzip)
    try:
        if write_text is None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(document, encoding="utf-8", newline="\n")
        else:
            write_text(output, document)
    except Exception as error:
        raise ReportOutputError(f"cannot write HTML output {output}: {error}") from error
    size = len(document.encode("utf-8"))
    if size > SIZE_WARNING_BYTES:
        print(f"warning: agent-view HTML is {size} bytes (threshold {SIZE_WARNING_BYTES})", file=stderr or sys.stderr)
    return output

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="M1 schema v3 JSON을 단일 오프라인 HTML 보고서로 변환합니다.")
    parser.add_argument("agent_view_json")
    parser.add_argument("-o", "--output")
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
