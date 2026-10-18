import json
import posixpath
from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple


def normalize_external_imports(records: Iterable[Mapping[str, Any]]) -> List[dict]:
    unique: Dict[Tuple[Tuple[str, str], ...], dict] = {}
    for record in records:
        unique.setdefault(tuple(sorted((key, repr(value)) for key, value in record.items())), dict(record))
    return [unique[key] for key in sorted(unique, key=lambda key: _order(unique[key], key))]


def _order(record: Mapping[str, Any], key: Tuple[Tuple[str, str], ...]) -> tuple:
    return (record.get("name", ""), record.get("line", 0), record.get("specifier", ""), bool(record.get("dynamic", False)), key)


def typescript_package_name(specifier: str) -> str:
    if specifier.startswith("@"):
        return "/".join(specifier.split("/")[:2])
    return specifier.split("/", 1)[0]


@dataclass(frozen=True)
class TsconfigAliases:
    path_keys: Tuple[str, ...] = ()
    base_url: Optional[str] = None


def _strip_jsonc(text: str) -> str:
    out: List[str] = []
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        if char == '"':
            end = index + 1
            while end < length and text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            out.append(text[index:end + 1])
            index = end + 1
        elif text.startswith("//", index):
            newline = text.find("\n", index)
            index = length if newline < 0 else newline
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            out.append(" ")
            index = length if end < 0 else end + 2
        else:
            if char in "}]":
                cursor = len(out) - 1
                while cursor >= 0 and out[cursor].isspace():
                    cursor -= 1
                if cursor >= 0 and out[cursor] == ",":
                    del out[cursor]
            out.append(char)
            index += 1
    return "".join(out)


def parse_tsconfig_aliases(text: str) -> TsconfigAliases:
    try:
        document = json.loads(_strip_jsonc(text.lstrip("﻿")))
    except (RecursionError, ValueError) as error:
        raise ValueError(f"tsconfig is not valid JSON: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("tsconfig top-level value must be an object")
    options = document.get("compilerOptions", {})
    if not isinstance(options, dict):
        raise ValueError("tsconfig compilerOptions must be an object")
    paths = options.get("paths", {})
    if not isinstance(paths, dict) or not all(isinstance(key, str) for key in paths):
        raise ValueError("tsconfig compilerOptions.paths must be an object with string keys")
    base_url = options.get("baseUrl")
    if base_url is not None and not isinstance(base_url, str):
        raise ValueError("tsconfig compilerOptions.baseUrl must be a string")
    if base_url is not None:
        base_url = posixpath.normpath(base_url)
        base_url = "" if base_url == "." else base_url
    return TsconfigAliases(tuple(paths), base_url)


def _base_url_roots(aliases: TsconfigAliases, source_files: Iterable[str]) -> FrozenSet[str]:
    base = aliases.base_url
    if base is None:
        return frozenset()
    prefix = base + "/" if base else ""
    roots = set()
    for path in source_files:
        if not path.startswith(prefix):
            continue
        relative = path[len(prefix):]
        roots.add(relative.split("/", 1)[0] if "/" in relative else posixpath.splitext(relative)[0])
    return frozenset(roots)


def typescript_alias_matcher(aliases: TsconfigAliases, source_files: Iterable[str]) -> Callable[[str], bool]:
    prefixes = tuple(key[:-1] for key in aliases.path_keys if key.endswith("*") and key != "*")
    exact = frozenset(key for key in aliases.path_keys if not key.endswith("*"))
    roots = _base_url_roots(aliases, source_files)

    def matches(specifier: str) -> bool:
        return (specifier in exact or any(specifier.startswith(prefix) for prefix in prefixes)
                or (bool(roots) and specifier.split("/", 1)[0] in roots))
    return matches


def is_typescript_alias(specifier: str, aliases: TsconfigAliases, source_files: Iterable[str]) -> bool:
    return typescript_alias_matcher(aliases, source_files)(specifier)


class PythonModuleIndex:
    def __init__(self, modules: Iterable[str], packages: Iterable[str]):
        package_set = frozenset(packages)
        names = set()
        for module in modules:
            segments = module.split(".")
            for start in range(len(segments)):
                if start and ".".join(segments[:start]) in package_set:
                    continue
                for end in range(start + 1, len(segments) + 1):
                    names.add(".".join(segments[start:end]))
        self._names = frozenset(names)

    def is_internal(self, name: str) -> bool:
        return name in self._names


def kotlin_is_internal(name: str, packages: Iterable[str]) -> bool:
    return any(name == package or name.startswith(package + ".") or package.startswith(name + ".") for package in packages)
