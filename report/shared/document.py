import base64
import gzip
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Union

SIZE_WARNING_BYTES = 10 * 1024 * 1024
SINGLE_MARKERS = (
    "@@TITLE@@",
    "@@STYLE@@",
    "@@COMPONENTS@@",
    "@@DATA@@",
    "@@SCRIPTS@@",
    "@@READY_EVENT@@",
    "@@READY_LABEL@@",
)


class ReportInputError(ValueError):
    pass


class ReportOutputError(RuntimeError):
    pass


def fail(path: str, message: str) -> None:
    raise ReportInputError(f"{path}: {message}")


def object_(value: Any, path: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        fail(path, "must be an object")
    return value


def array(value: Any, path: str) -> list:
    if not isinstance(value, list):
        fail(path, "must be an array")
    return value


def string(value: Any, path: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        fail(path, "must be a string" if allow_empty else "must be a non-empty string")
    return value


def integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        fail(path, f"must be an integer >= {minimum}")
    return value


def boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        fail(path, "must be a boolean")
    return value


def required(value: Mapping[str, Any], path: str, fields: Sequence[str]) -> None:
    for field in fields:
        if field not in value:
            fail(path, f"missing required field {field!r}")


def string_array(value: Any, path: str) -> list:
    result = array(value, path)
    for index, item in enumerate(result):
        string(item, f"{path}[{index}]")
    return result


def shared_dir() -> Path:
    return Path(__file__).resolve().parent


def _default_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_payload(
    path: Path,
    read_text: Callable[[Path], str],
    validate: Callable[[Any], Dict[str, Any]],
) -> Dict[str, Any]:
    try:
        text = read_text(path)
    except Exception as error:
        raise ReportOutputError(f"cannot read JSON input {path}: {error}") from error
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError) as error:
        raise ReportInputError(f"invalid JSON input {path}: {error}") from error
    return validate(value)


def _load_templates(
    template_dir: Path,
    names: Sequence[str],
    read_text: Callable[[Path], str],
) -> Dict[str, str]:
    base = shared_dir()
    try:
        templates = {name: read_text(template_dir / name) for name in names}
        for name in ("base.html", "common.css"):
            templates[name] = read_text(base / name)
    except Exception as error:
        raise ReportOutputError(f"cannot read report template: {error}") from error
    for marker in SINGLE_MARKERS:
        if templates["base.html"].count(marker) != 1:
            raise ReportOutputError(f"invalid report template: expected exactly one {marker}")
    if "@@PAYLOAD_ID@@" not in templates["base.html"]:
        raise ReportOutputError("invalid report template: expected @@PAYLOAD_ID@@")
    return templates


def _build_document(
    payload: Mapping[str, Any],
    templates: Mapping[str, str],
    names: Sequence[str],
    compress: Callable[[bytes], bytes],
    *,
    title: str,
    payload_id: str,
    ready_event: str,
    ready_label: str,
) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    try:
        compressed = compress(raw)
        if not isinstance(compressed, bytes) or gzip.decompress(compressed) != raw:
            raise ValueError("compressor did not return a gzip encoding of the payload")
        encoded = base64.b64encode(compressed).decode("ascii")
    except Exception as error:
        raise ReportOutputError(f"cannot compress report payload: {error}") from error
    components = "\n".join(templates[name] for name in names if name.endswith(".html"))
    scripts = "\n".join(
        f"<script>\n{templates[name]}\n</script>" for name in names if name.endswith(".js")
    )
    return (
        templates["base.html"]
        .replace("@@TITLE@@", title)
        .replace("@@STYLE@@", templates["common.css"])
        .replace("@@COMPONENTS@@", components)
        .replace("@@PAYLOAD_ID@@", payload_id)
        .replace("@@READY_EVENT@@", ready_event)
        .replace("@@READY_LABEL@@", ready_label)
        .replace("@@DATA@@", encoded)
        .replace("@@SCRIPTS@@", scripts)
    )


def _gzip(raw: bytes) -> bytes:
    return gzip.compress(raw, compresslevel=9, mtime=0)


def generate(
    json_path: Union[str, Path],
    output_path: Union[str, Path, None] = None,
    *,
    validate: Callable[[Any], Dict[str, Any]],
    template_dir: Union[str, Path],
    names: Sequence[str],
    title: str,
    payload_id: str,
    ready_event: str,
    ready_label: str,
    label: str,
    read_text: Optional[Callable[[Path], str]] = None,
    write_text: Optional[Callable[[Path, str], None]] = None,
    compress: Optional[Callable[[bytes], bytes]] = None,
    stderr: Any = None,
) -> Path:
    source = Path(json_path).expanduser().resolve()
    output = (
        Path(output_path).expanduser().resolve()
        if output_path is not None
        else source.with_suffix(".html")
    )
    if source == output:
        raise ReportOutputError("input and output paths must be different")
    reader = read_text or _default_read_text
    payload = _read_payload(source, reader, validate)
    templates = _load_templates(Path(template_dir), names, reader)
    document = _build_document(
        payload,
        templates,
        names,
        compress or _gzip,
        title=title,
        payload_id=payload_id,
        ready_event=ready_event,
        ready_label=ready_label,
    )
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
        print(
            f"warning: {label} HTML is {size} bytes (threshold {SIZE_WARNING_BYTES})",
            file=stderr or sys.stderr,
        )
    return output
