import bisect
import re
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

CONTEXTS = ("code", "comment", "docstring", "doc", "config")

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_DOC_SUFFIXES = frozenset({".md", ".rst", ".txt"})
_CONFIG_SUFFIXES = frozenset({".json", ".yaml", ".yml", ".toml", ".properties", ".gradle"})
_PYTHON_SUFFIXES = frozenset({".py", ".pyi"})


def file_context_kind(path: str) -> str:
    pure = PurePosixPath(path)
    name, suffix = pure.name.lower(), pure.suffix.lower()
    if suffix in _DOC_SUFFIXES: return "doc"
    if name.endswith(".gradle.kts") or suffix in _CONFIG_SUFFIXES or name == ".env": return "config"
    return "code"


def node_identifier(label: Any) -> str:
    if not isinstance(label, str) or not label: return ""
    segment = label.rsplit(".", 1)[-1]
    return segment if _WORD_RE.fullmatch(segment) else ""


def _regions(text: str, python: bool) -> list[tuple[int, int, str]]:
    regions, index, length = [], 0, len(text)
    while index < length:
        char = text[index]
        if python and text.startswith(('"""', "'''"), index):
            end = text.find(text[index:index + 3], index + 3)
            end = length if end == -1 else end + 3
            regions.append((index, end, "docstring"))
        elif (python and char == "#") or (not python and text.startswith("//", index)):
            end = text.find("\n", index)
            end = length if end == -1 else end
            regions.append((index, end, "comment"))
        elif not python and text.startswith("/*", index):
            end = text.find("*/", index + 2)
            end = length if end == -1 else end + 2
            regions.append((index, end, "comment"))
        elif char in ("'", '"'):
            # Literal contents stay code: a comment marker inside a string is not a comment.
            end = index + 1
            while end < length and text[end] != char and text[end] != "\n":
                end += 2 if text[end] == "\\" else 1
            index = end + 1
            continue
        else:
            index += 1
            continue
        index = end
    return regions


def identifier_file_counts(contents: Mapping[str, str], names: Iterable[str]) -> dict[str, dict[str, int]]:
    wanted = set(names)
    counts = {name: {"total": 0, **{context: 0 for context in CONTEXTS}} for name in wanted}
    wanted.discard("")
    if not wanted: return counts
    for path in sorted(contents):
        text, base = contents[path], file_context_kind(path)
        found: dict[str, set[str]] = {}
        regions = starts = None
        for match in _WORD_RE.finditer(text):
            token = match.group(0)
            if token not in wanted: continue
            context = base
            if base == "code":
                if regions is None:
                    regions = _regions(text, PurePosixPath(path).suffix.lower() in _PYTHON_SUFFIXES)
                    starts = [region[0] for region in regions]
                position = bisect.bisect_right(starts, match.start()) - 1
                if position >= 0 and match.start() < regions[position][1]: context = regions[position][2]
            found.setdefault(token, set()).add(context)
        for token, seen in found.items():
            counts[token]["total"] += 1
            for context in seen: counts[token][context] += 1
    return counts
