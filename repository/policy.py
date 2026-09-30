import hashlib
from pathlib import Path
from typing import Any, Dict, List, Union

import yaml

from .models import ScanPolicy, ScanPolicyRef


class ScanPolicyError(ValueError):
    pass


def default_scan_policy_path() -> Path:
    return Path(__file__).resolve().parents[1] / "profiles" / "snapshot.v1.yaml"


def _positive_int(document: Dict[str, Any], key: str) -> int:
    value = document.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ScanPolicyError(f"scan policy {key} must be an int >= 1")
    return value


def _string_list(raw: Dict[str, Any], key: str) -> List[str]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ScanPolicyError(f"scan policy exclusions.{key} must be an array of strings")
    return list(value)


def load_scan_policy(path: Union[str, Path]) -> ScanPolicy:
    try:
        raw_bytes = Path(path).read_bytes()
    except OSError as error:
        raise ScanPolicyError(f"cannot read scan policy {path}: {error}") from error
    try:
        document = yaml.safe_load(raw_bytes.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise ScanPolicyError(f"scan policy is not valid YAML: {error}") from error
    if not isinstance(document, dict):
        raise ScanPolicyError("scan policy root must be a mapping")
    for key in ("id", "version", "max_file_bytes", "exclusions"):
        if key not in document:
            raise ScanPolicyError(f"scan policy is missing required key: {key}")
    if not isinstance(document["id"], str) or not document["id"]:
        raise ScanPolicyError("scan policy id must be a non-empty string")
    if document["version"] != 1:
        raise ScanPolicyError("scan policy version must be 1")
    for key in ("include_agent_docs", "tracked_files_only"):
        if key in document and not isinstance(document[key], bool):
            raise ScanPolicyError(f"scan policy {key} must be a boolean")
    exclusions = document["exclusions"]
    if not isinstance(exclusions, dict):
        raise ScanPolicyError("scan policy exclusions must be a mapping")

    return ScanPolicy(
        ref=ScanPolicyRef(
            id=document["id"],
            version=1,
            content_hash=hashlib.sha256(raw_bytes).hexdigest(),
        ),
        max_file_bytes=_positive_int(document, "max_file_bytes"),
        generated_marker_lines=(
            _positive_int(document, "generated_marker_lines")
            if "generated_marker_lines" in document else 8
        ),
        include_agent_docs=document.get("include_agent_docs", True),
        tracked_files_only=document.get("tracked_files_only", True),
        vendor_globs=_string_list(exclusions, "vendor_globs"),
        generated_globs=_string_list(exclusions, "generated_globs"),
        generated_markers=_string_list(exclusions, "generated_markers"),
        lockfile_names=_string_list(exclusions, "lockfile_names"),
    )
