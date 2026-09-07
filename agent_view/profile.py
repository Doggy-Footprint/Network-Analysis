import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Union

import yaml

from .models import ProfileRef

ALLOWED_TRANSFORM_IDS = (
    "split-case",
    "token-adjacent-pairs",
    "normalize-case",
    "plural-singular",
    "strip-affix",
)
_LIMIT_KEYS = (
    "min_term_length",
    "max_file_bytes",
    "read_unit_token_limit",
    "read_query_candidate_limit",
    "search_output_limit",
    "hint_query_limit",
    "refinement_threshold",
    "refinement_query_limit",
    "refinement_depth_limit",
    "root_list_depth",
    "root_list_entry_limit",
    "occurrence_block_rows",
    "context_lines",
    "generated_marker_lines",
)


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class Transform:
    id: str
    prefixes: List[str] = field(default_factory=list)
    suffixes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Profile:
    ref: ProfileRef
    min_term_length: int
    max_file_bytes: int
    transforms: List[Transform]
    include_agent_docs: bool = True
    tracked_files_only: bool = True
    read_unit_token_limit: int = 8000
    read_query_candidate_limit: int = 8
    search_output_limit: int = 100
    hint_query_limit: int = 4
    refinement_threshold: int = 50
    refinement_query_limit: int = 4
    refinement_depth_limit: int = 2
    root_list_depth: int = 2
    root_list_entry_limit: int = 200
    occurrence_block_rows: int = 4096
    context_lines: int = 0
    generated_marker_lines: int = 8
    vendor_globs: List[str] = field(
        default_factory=lambda: ["vendor/**", "node_modules/**", "third_party/**"]
    )
    generated_globs: List[str] = field(
        default_factory=lambda: ["build/**", "dist/**", "*.min.js"]
    )
    generated_markers: List[str] = field(
        default_factory=lambda: [r"generated file", r"do not edit"]
    )
    lockfile_names: List[str] = field(
        default_factory=lambda: [
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "poetry.lock",
            "Pipfile.lock",
        ]
    )
    split_version: str = "symbol-greedy-v1"
    ordering_version: str = "path-line-byte-v1"
    output_format_version: str = "match-line-v1"
    query_equivalence_version: str = "kind-term-surface-scope-rules-v1"
    read_limit_provenance: str = ""
    search_limit_provenance: str = ""
    query_candidate_limit_provenance: str = ""

    @property
    def version(self) -> int:
        return self.ref.version

    def output(self) -> Dict[str, Any]:
        result = asdict(self)
        result.update(asdict(self.ref))
        del result["ref"]
        return result


def default_profile_path() -> Path:
    return Path(__file__).resolve().parents[1] / "profiles" / "agent_view.v3.yaml"


def _required_mapping(document: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ProfileError(f"profile {key} must be a mapping")
    return value


def _positive_limits(raw: Dict[str, Any]) -> Dict[str, int]:
    values = {}
    for key in _LIMIT_KEYS:
        value = raw.get(key)
        minimum = 0 if key == "context_lines" else 1
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise ProfileError(f"profile limit {key} must be an int >= {minimum}")
        values[key] = value
    return values


def _string_list(raw: Dict[str, Any], key: str) -> List[str]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProfileError(f"profile exclusions.{key} must be an array of strings")
    return list(value)


def load_profile(path: Union[str, Path]) -> Profile:
    try:
        raw_bytes = Path(path).read_bytes()
    except OSError as error:
        raise ProfileError(f"cannot read profile {path}: {error}") from error
    try:
        document = yaml.safe_load(raw_bytes.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise ProfileError(f"profile is not valid YAML: {error}") from error
    if not isinstance(document, dict):
        raise ProfileError("profile root must be a mapping")
    for key in ("id", "version", "limits", "transforms", "versions", "provenance", "exclusions"):
        if key not in document:
            raise ProfileError(f"profile is missing required key: {key}")
    if not isinstance(document["id"], str) or not document["id"]:
        raise ProfileError("profile id must be a non-empty string")
    if document["version"] != 3:
        raise ProfileError("profile version must be 3")
    for key in ("include_agent_docs", "tracked_files_only"):
        if key in document and not isinstance(document[key], bool):
            raise ProfileError(f"profile {key} must be a boolean")

    limits = _positive_limits(_required_mapping(document, "limits"))
    versions = _required_mapping(document, "versions")
    provenance = _required_mapping(document, "provenance")
    exclusions = _required_mapping(document, "exclusions")
    for key in ("split", "ordering", "output_format", "query_equivalence"):
        if not isinstance(versions.get(key), str) or not versions[key]:
            raise ProfileError(f"profile versions.{key} must be a non-empty string")
    for key in ("read_limit", "search_limit", "query_candidate_limit"):
        if not isinstance(provenance.get(key), str) or not provenance[key]:
            raise ProfileError(f"profile provenance.{key} must be a non-empty string")

    return Profile(
        ref=ProfileRef(
            id=document["id"],
            version=3,
            content_hash=hashlib.sha256(raw_bytes).hexdigest(),
        ),
        transforms=_load_transforms(document["transforms"]),
        include_agent_docs=bool(document.get("include_agent_docs", True)),
        tracked_files_only=bool(document.get("tracked_files_only", True)),
        vendor_globs=_string_list(exclusions, "vendor_globs"),
        generated_globs=_string_list(exclusions, "generated_globs"),
        generated_markers=_string_list(exclusions, "generated_markers"),
        lockfile_names=_string_list(exclusions, "lockfile_names"),
        split_version=versions["split"],
        ordering_version=versions["ordering"],
        output_format_version=versions["output_format"],
        query_equivalence_version=versions["query_equivalence"],
        read_limit_provenance=provenance["read_limit"],
        search_limit_provenance=provenance["search_limit"],
        query_candidate_limit_provenance=provenance["query_candidate_limit"],
        **limits,
    )


def _load_transforms(raw: Any) -> List[Transform]:
    if not isinstance(raw, list) or not raw:
        raise ProfileError("profile transforms must be a non-empty list")
    transforms = []
    seen = set()
    for entry in raw:
        if not isinstance(entry, dict) or entry.get("id") not in ALLOWED_TRANSFORM_IDS:
            identifier = entry.get("id") if isinstance(entry, dict) else entry
            raise ProfileError(f"unknown transform id: {identifier}")
        identifier = entry["id"]
        if identifier in seen:
            raise ProfileError(f"duplicate transform id: {identifier}")
        seen.add(identifier)
        prefixes = entry.get("prefixes", [])
        suffixes = entry.get("suffixes", [])
        if not all(isinstance(item, str) for item in prefixes + suffixes):
            raise ProfileError("transform prefixes/suffixes must be strings")
        if identifier == "strip-affix" and not (prefixes or suffixes):
            raise ProfileError("strip-affix requires prefixes or suffixes")
        if identifier != "strip-affix" and ("prefixes" in entry or "suffixes" in entry):
            raise ProfileError("prefixes/suffixes are only allowed on strip-affix")
        transforms.append(Transform(identifier, list(prefixes), list(suffixes)))
    return transforms
