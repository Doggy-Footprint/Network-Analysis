import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Set

from language_analyzers.core.enrichment import STRING_RE, config_keys
from language_analyzers.core.graph_models import GraphNode

from .models import ReadableNode
from .occurrence import enclosing_node_id, file_context_kind
from .profile import Profile

_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_RAISE_RE = re.compile(r"\b(raise|throw)\b")


@dataclass
class Clue:
    term: str
    clue_kinds: Set[str] = field(default_factory=set)
    origin_node_ids: Set[str] = field(default_factory=set)


def _add(clues: Dict[str, Clue], term: str, kind: str, origin: str, profile: Profile) -> None:
    term = term.strip()
    if not term or "\n" in term or "\r" in term or len(term) < profile.min_term_length:
        return
    clue = clues.get(term)
    if clue is None:
        clue = Clue(term=term)
        clues[term] = clue
    clue.clue_kinds.add(kind)
    if origin:
        clue.origin_node_ids.add(origin)


def extract_clues(
    nodes: Sequence[GraphNode],
    readable: Sequence[ReadableNode],
    contents: Mapping[str, str],
    profile: Profile,
) -> Dict[str, Clue]:
    clues: Dict[str, Clue] = {}
    readable_ids = {
        node.symbol_id: node.id
        for node in readable
        if node.symbol_id is not None
    }
    nodes_by_file: Dict[str, List[ReadableNode]] = {}
    for node in readable:
        nodes_by_file.setdefault(node.file_path, []).append(node)

    for node in sorted(nodes, key=lambda item: item.id):
        origin = readable_ids.get(node.id, "")
        _add(clues, node.label, "identifier", origin, profile)
        if node.symbol_path and node.symbol_path != node.label:
            _add(clues, node.symbol_path, "qualified_name", origin, profile)

    for path in sorted(contents):
        text = contents[path]
        origin_for_file = enclosing_node_id(nodes_by_file.get(path, []), path, 1)
        _add(clues, path, "path", origin_for_file, profile)
        without_suffix = str(Path(path).with_suffix("").as_posix())
        if without_suffix != path:
            _add(clues, without_suffix, "path", origin_for_file, profile)

        kind = file_context_kind(path)
        if kind == "config":
            for key, line in config_keys(Path(path), text):
                _add(clues, key, "config_key", enclosing_node_id(nodes_by_file.get(path, []), path, line), profile)
            continue
        if kind == "doc":
            if Path(path).suffix.lower() == ".md":
                for match in _BACKTICK_RE.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    origin = enclosing_node_id(nodes_by_file.get(path, []), path, line)
                    _add(clues, match.group(1), "doc_mention", origin, profile)
            continue

        lines = text.splitlines()
        for match in STRING_RE.finditer(text):
            value = match.group("value")
            line = text.count("\n", 0, match.start()) + 1
            origin = enclosing_node_id(nodes_by_file.get(path, []), path, line)
            _add(clues, value, "literal", origin, profile)
            if value.strip().startswith("/"):
                _add(clues, value, "route", origin, profile)
            if 1 <= line <= len(lines) and _RAISE_RE.search(lines[line - 1]):
                _add(clues, value, "error_message", origin, profile)

    return clues
