import hashlib
from dataclasses import replace
from typing import Dict, List, Mapping, Sequence, Tuple

from language_analyzers.core.cost import cost_for_text
from language_analyzers.core.flags import path_flags
from language_analyzers.core.graph_models import GraphNode

from .models import ReadableNode, ReadUnit


def _line_count(text: str) -> int:
    return max(1, len(text.splitlines()))


def _slice(text: str, start_line: int, end_line: int) -> str:
    return "\n".join(text.splitlines()[start_line - 1:end_line])


def _unit_id(path: str, start_line: int, end_line: int) -> str:
    value = f"{path}|{start_line}|{end_line}"
    return "r:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _readable_id(identity: str, path: str, start_line: int, end_line: int) -> str:
    value = f"{identity}|{path}|{start_line}|{end_line}"
    return "n:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _candidate_nodes(
    nodes: Sequence[GraphNode],
    scanned_paths: Sequence[str],
    contents: Mapping[str, str],
) -> List[ReadableNode]:
    scanned = set(scanned_paths)
    by_id: Dict[str, ReadableNode] = {}
    ordered = sorted(
        nodes,
        key=lambda node: (
            node.id,
            node.span.file_path if node.span else "",
            node.span.start_line if node.span else 0,
        ),
    )
    for node in ordered:
        if node.id in by_id or node.span is None or node.span.file_path not in scanned:
            continue
        span_text = _slice(contents[node.span.file_path], node.span.start_line, node.span.end_line)
        readable_id = _readable_id(
            node.id,
            node.span.file_path,
            node.span.start_line,
            node.span.end_line,
        )
        by_id[node.id] = ReadableNode(
            id=readable_id,
            file_path=node.span.file_path,
            symbol_id=node.id,
            label=node.label,
            kind=node.kind,
            start_line=node.span.start_line,
            end_line=node.span.end_line,
            read_cost=cost_for_text(span_text),
            flags=sorted(path_flags(node.span.file_path)),
        )

    covered_paths = {node.file_path for node in by_id.values()}
    for path in sorted(scanned - covered_paths):
        file_id = _readable_id("file", path, 1, _line_count(contents[path]))
        by_id[f"file:{path}"] = ReadableNode(
            id=file_id,
            file_path=path,
            symbol_id=None,
            label=path,
            kind="file",
            start_line=1,
            end_line=_line_count(contents[path]),
            read_cost=cost_for_text(contents[path]),
            flags=sorted(path_flags(path)),
        )
    return sorted(by_id.values(), key=lambda node: node.id)


def _split_file(
    path: str,
    text: str,
    symbols: Sequence[ReadableNode],
    token_limit: int,
) -> List[ReadUnit]:
    last_line = _line_count(text)
    whole_cost = cost_for_text(text)
    if whole_cost.token_estimate <= token_limit or not symbols:
        return [
            ReadUnit(
                id=_unit_id(path, 1, last_line),
                file_path=path,
                start_line=1,
                end_line=last_line,
                symbol_ids=sorted(node.id for node in symbols),
                read_cost=whole_cost,
            )
        ]

    ordered = sorted(
        symbols,
        key=lambda node: (node.start_line or 1, -(node.end_line or 1), node.id),
    )
    groups: List[Tuple[int, int, List[ReadableNode], bool]] = []
    start_line = 1
    members: List[ReadableNode] = []
    covered_end = 0
    assigned_ids = set()

    for symbol in ordered:
        if symbol.id in assigned_ids:
            continue
        symbol_start = symbol.start_line or 1
        symbol_end = symbol.end_line or symbol_start
        if members and symbol_end <= covered_end:
            members.append(symbol)
            continue

        candidate_end = max(covered_end, symbol_end)
        candidate_tokens = cost_for_text(_slice(text, start_line, candidate_end)).token_estimate
        if members and candidate_tokens > token_limit:
            groups.append((start_line, covered_end, members, False))
            start_line = covered_end + 1
            members = []

        symbol_tokens = cost_for_text(_slice(text, symbol_start, symbol_end)).token_estimate
        if not members and symbol_tokens > token_limit:
            if start_line < symbol_start:
                groups.append((start_line, symbol_start - 1, [], False))
            oversized_members = [
                item
                for item in ordered
                if (item.start_line or 1) >= symbol_start and (item.end_line or 1) <= symbol_end
            ]
            assigned_ids.update(item.id for item in oversized_members)
            groups.append((symbol_start, symbol_end, oversized_members, True))
            start_line = symbol_end + 1
            covered_end = symbol_end
            members = []
            continue

        members.append(symbol)
        assigned_ids.add(symbol.id)
        covered_end = max(covered_end, symbol_end)

    if members:
        groups.append((start_line, last_line, members, False))
    elif start_line <= last_line:
        groups.append((start_line, last_line, [], False))

    units = []
    for start_line, end_line, members, oversized in groups:
        if start_line > end_line:
            continue
        units.append(
            ReadUnit(
                id=_unit_id(path, start_line, end_line),
                file_path=path,
                start_line=start_line,
                end_line=end_line,
                symbol_ids=sorted({node.id for node in members}),
                read_cost=cost_for_text(_slice(text, start_line, end_line)),
                oversized_symbol=oversized,
            )
        )
    return units


def build_readable_graph(
    nodes: Sequence[GraphNode],
    scanned_paths: Sequence[str],
    contents: Mapping[str, str],
    token_limit: int,
) -> Tuple[List[ReadableNode], List[ReadUnit], Dict[str, List[str]]]:
    readable = _candidate_nodes(nodes, scanned_paths, contents)
    by_path: Dict[str, List[ReadableNode]] = {}
    for node in readable:
        by_path.setdefault(node.file_path, []).append(node)

    units: List[ReadUnit] = []
    for path in sorted(scanned_paths):
        units.extend(_split_file(path, contents[path], by_path.get(path, []), token_limit))

    unit_by_node = {
        node_id: unit
        for unit in units
        for node_id in unit.symbol_ids
    }
    adjusted = []
    for node in readable:
        unit = unit_by_node.get(node.id)
        if unit is None:
            unit = next(item for item in units if item.file_path == node.file_path)
        adjusted.append(replace(node, read_unit_id=unit.id, read_cost=unit.read_cost))

    units_by_path: Dict[str, List[str]] = {}
    for unit in sorted(units, key=lambda item: (item.file_path, item.start_line, item.id)):
        units_by_path.setdefault(unit.file_path, []).append(unit.id)
    return sorted(adjusted, key=lambda node: node.id), sorted(units, key=lambda unit: unit.id), units_by_path


def build_readable_nodes(
    nodes: Sequence[GraphNode],
    scanned_paths: Sequence[str],
    contents: Mapping[str, str],
):
    readable, _, _ = build_readable_graph(nodes, scanned_paths, contents, 10**12)
    by_path: Dict[str, List[str]] = {}
    for node in readable:
        by_path.setdefault(node.file_path, []).append(node.id)
    return readable, by_path
