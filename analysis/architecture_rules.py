import re
from dataclasses import dataclass
from fnmatch import translate
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple, Union

import yaml

RULES_POLICY = "architecture_rules.v1"
_TOP_KEYS = {"version", "layers", "allow", "forbid"}
_SELECTOR_KEYS = ("paths", "packages")
_LAYER_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_REPORT_LIMIT = 10
_EXTERNAL_MESSAGE = "architecture rules {where}: external library rules are not supported in this version"


class ArchitectureRulesError(ValueError):
    pass


@dataclass(frozen=True)
class LayerSelector:
    paths: Tuple[str, ...]
    packages: Tuple[str, ...]


@dataclass(frozen=True)
class ArchitectureRules:
    version: int
    layers: Mapping[str, LayerSelector]
    allow: Mapping[str, Tuple[str, ...]]
    forbid: Mapping[str, Tuple[str, ...]]


def _fail(message: str) -> None:
    raise ArchitectureRulesError("architecture rules " + message)


@lru_cache(maxsize=None)
def _compile_path(pattern: str) -> "re.Pattern[str]":
    segments = pattern.split("/")
    parts: List[str] = []
    previous_globstar = False
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            if previous_globstar and not last:
                continue
            parts.append(".*" if last else "(?:[^/]*/)*")
            previous_globstar = True
            continue
        previous_globstar = False
        body = "".join("[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char) for char in segment)
        parts.append(body if last else body + "/")
    return re.compile("".join(parts), re.DOTALL)


def match_path(pattern: str, path: str) -> bool:
    return _compile_path(pattern).fullmatch(path) is not None


@lru_cache(maxsize=None)
def _compile_package(pattern: str) -> "re.Pattern[str]":
    return re.compile(translate(pattern))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _string_list(value: Any, where: str) -> List[str]:
    if not isinstance(value, list) or not value:
        _fail(f"{where} must be a non-empty list, got {value!r}")
    for item in value:
        if not isinstance(item, str) or not item:
            _fail(f"{where} entries must be non-empty strings, got {item!r}")
    return value


def _check_path_pattern(pattern: str, where: str) -> None:
    if pattern.startswith("/"):
        _fail(f"{where} path pattern {pattern!r} must not start with '/'")
    for segment in pattern.split("/"):
        if "**" in segment and segment != "**":
            _fail(f"{where} path pattern {pattern!r} may use '**' only as a whole segment")


def _parse_layers(layers: Any) -> Dict[str, LayerSelector]:
    if not isinstance(layers, dict) or not layers:
        _fail(f"layers must be a non-empty mapping, got {layers!r}")
    result = {}
    for name in sorted(layers, key=str):
        selector = layers[name]
        if not isinstance(name, str) or not _LAYER_NAME.fullmatch(name):
            _fail(f"layer name {name!r} must match [A-Za-z][A-Za-z0-9_-]*")
        if not isinstance(selector, dict) or not selector or not set(selector) <= set(_SELECTOR_KEYS):
            _fail(f"layer {name!r} must be a non-empty mapping with keys from {list(_SELECTOR_KEYS)}, got {selector!r}")
        paths = _string_list(selector["paths"], f"layer {name!r} paths") if "paths" in selector else []
        for pattern in paths:
            _check_path_pattern(pattern, f"layer {name!r}")
        packages = _string_list(selector["packages"], f"layer {name!r} packages") if "packages" in selector else []
        result[name] = LayerSelector(tuple(paths), tuple(packages))
    return result


def _layer_list(value: Any, owner: str, where: str, layers: Mapping[str, Any], allow_empty: bool) -> Tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        _fail(f"{where} must be a{'' if allow_empty else ' non-empty'} list of layer names, got {value!r}")
    for item in value:
        if not isinstance(item, str) or item not in layers:
            _fail(f"{where} references undefined layer {item!r}")
        if item == owner:
            _fail(f"{where} must not contain its own layer {item!r}")
    return tuple(sorted(set(value)))


def _parse_allow(allow: Any, layers: Mapping[str, Any]) -> Dict[str, Tuple[str, ...]]:
    if not isinstance(allow, dict):
        _fail(f"allow must be a mapping, got {allow!r}")
    result = {}
    for name in sorted(allow, key=str):
        if not isinstance(name, str) or name not in layers:
            _fail(f"allow references undefined layer {name!r}")
        result[name] = _layer_list(allow[name], name, f"allow.{name}", layers, True)
    return result


def _parse_forbid(forbid: Any, layers: Mapping[str, Any]) -> Dict[str, Tuple[str, ...]]:
    if not isinstance(forbid, list):
        _fail(f"forbid must be a list, got {forbid!r}")
    merged: Dict[str, set] = {}
    for index, item in enumerate(forbid):
        where = f"forbid[{index}]"
        if isinstance(item, dict) and "to_external" in item:
            raise ArchitectureRulesError(_EXTERNAL_MESSAGE.format(where=f"{where} key 'to_external'"))
        if not isinstance(item, dict) or set(item) != {"from", "to"}:
            _fail(f"{where} must be a mapping with exactly the keys ['from', 'to'], got {item!r}")
        source = item["from"]
        if not isinstance(source, str) or source not in layers:
            _fail(f"{where}.from references undefined layer {source!r}")
        merged.setdefault(source, set()).update(_layer_list(item["to"], source, f"{where}.to", layers, False))
    return {name: tuple(sorted(merged[name])) for name in sorted(merged)}


def load_architecture_rules(path: Union[str, Path]) -> ArchitectureRules:
    try:
        raw_bytes = Path(path).read_bytes()
    except OSError as error:
        raise ArchitectureRulesError(f"cannot read architecture rules {path}: {error}") from error
    try:
        document = yaml.safe_load(raw_bytes.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError, RecursionError) as error:
        raise ArchitectureRulesError(f"architecture rules {path} is not valid YAML: {error}") from error
    if not isinstance(document, dict):
        _fail(f"must be a YAML mapping, got {type(document).__name__}")
    if "external" in document:
        raise ArchitectureRulesError(_EXTERNAL_MESSAGE.format(where="key 'external'"))
    unknown = sorted(repr(key) for key in document if key not in _TOP_KEYS)
    if unknown:
        _fail(f"has unknown keys {', '.join(unknown)}; allowed keys are {sorted(_TOP_KEYS)}")
    for required in ("version", "layers"):
        if required not in document:
            _fail(f"is missing required key {required!r}")
    if not _is_int(document["version"]) or document["version"] != 1:
        _fail(f"version must be the integer 1, got {document['version']!r}")
    layers = _parse_layers(document["layers"])
    allow = _parse_allow(document["allow"], layers) if "allow" in document else {}
    forbid = _parse_forbid(document["forbid"], layers) if "forbid" in document else {}
    return ArchitectureRules(1, layers, allow, forbid)


def layer_assignments(rules: ArchitectureRules, files: Iterable[str], packages: Mapping[str, Mapping[str, List[str]]]) -> Dict[str, str]:
    package_layers: Dict[str, frozenset] = {}

    def layers_of_package(package: str) -> frozenset:
        found = package_layers.get(package)
        if found is None:
            found = package_layers[package] = frozenset(
                name for name, selector in rules.layers.items()
                if any(_compile_package(pattern).fullmatch(package) for pattern in selector.packages))
        return found

    assigned, conflicts = {}, {}
    for file_id in sorted(set(files)):
        path = file_id[5:] if file_id.startswith("file:") else file_id
        matched = {name for name, selector in rules.layers.items() if any(match_path(pattern, path) for pattern in selector.paths)}
        for scheme in sorted(packages):
            for package in packages[scheme].get(file_id, ()):
                matched |= layers_of_package(package)
        if len(matched) == 1:
            assigned[file_id] = next(iter(matched))
        elif matched:
            conflicts[file_id] = sorted(matched)
    if conflicts:
        shown = "; ".join(f"{file_id[5:] if file_id.startswith('file:') else file_id} -> {', '.join(names)}" for file_id, names in list(conflicts.items())[:_REPORT_LIMIT])
        _fail(f"layers overlap: {len(conflicts)} file(s) match more than one layer (first {min(len(conflicts), _REPORT_LIMIT)}): {shown}")
    return assigned
