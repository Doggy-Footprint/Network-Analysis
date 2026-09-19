from __future__ import annotations

import bisect
import json
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from agent_view.models import RepositorySnapshot

from .cost import cost_for_text
from .flags import is_test_path
from .graph_models import (
    Confidence,
    GraphEdge,
    GraphNode,
    NodeKind,
    RelationKind,
    Resolution,
    SourceSpan,
)


_CODE_SUFFIXES = {".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".kt", ".kts"}
_CONFIG_NAMES = {".env"}
_CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".properties"}
STRING_RE = re.compile(r"(?P<quote>['\"])(?P<value>[^'\"\r\n]+)(?P=quote)")


def enrich_repository(
    architecture: Any,
    *,
    file_inventory: Optional[Sequence[str]] = None,
    file_reader: Optional[Callable[[Path], str]] = None,
    snapshot: Optional[RepositorySnapshot] = None,
) -> Any:
    root = Path(architecture.project_path)
    if snapshot is not None:
        snapshot_root = Path(snapshot.root)
        if not root.is_absolute() or not snapshot_root.is_absolute() or root != snapshot_root:
            raise ValueError("project path and snapshot root must be absolute and match")
        snapshot_contents = snapshot.content_map()
        file_inventory = tuple(snapshot_contents)
        file_reader = lambda path: snapshot_contents[path.relative_to(root).as_posix()]
    nodes: List[GraphNode] = architecture.nodes
    edges: List[GraphEdge] = architecture.edges
    inventory = list(file_inventory) if file_inventory is not None else list(_repository_files(root))
    reader = file_reader or (lambda path: path.read_text(encoding="utf-8"))
    contents: Dict[str, str] = {}
    for relative in sorted(set(inventory)):
        if not _enrichment_candidate(relative):
            continue
        try:
            contents[relative] = reader(root / relative)
        except (OSError, UnicodeError, KeyError):
            continue
    _add_test_relations(nodes, edges, contents)
    _add_configuration_relations(nodes, edges, contents)
    return architecture


def _repository_files(root: Path) -> Iterable[str]:
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, ValueError):
        completed = None
    if completed is not None and completed.returncode == 0 and completed.stdout:
        for entry in completed.stdout.decode("utf-8", errors="replace").split("\0"):
            if entry:
                yield Path(entry).as_posix()
        return
    ignored = {".git", ".venv", "venv", "node_modules", "build", "dist", ".gradle", ".idea"}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not any(part in ignored for part in path.relative_to(root).parts):
            yield path.relative_to(root).as_posix()


def _enrichment_candidate(relative: str) -> bool:
    path = Path(relative)
    ignored = {".git", ".venv", "venv", "node_modules", "vendor", "third_party", "build", "dist"}
    if any(part in ignored for part in path.parts):
        return False
    lower_name = path.name.lower()
    return (
        path.suffix.lower() in _CODE_SUFFIXES | _CONFIG_SUFFIXES
        or lower_name in _CONFIG_NAMES
        or lower_name.endswith((".gradle", ".gradle.kts"))
    )


def _path_for(node: GraphNode) -> str:
    if node.span is not None:
        return node.span.file_path
    return str((node.metadata or {}).get("file_path", ""))


def _is_test_node(node: GraphNode) -> bool:
    return "test" in (node.flags or []) or is_test_path(_path_for(node))


def _add_test_relations(
    nodes: Sequence[GraphNode],
    edges: List[GraphEdge],
    contents: Mapping[str, str],
) -> None:
    by_id = {node.id: node for node in nodes}
    existing = {(edge.from_id, edge.to_id, edge.relation) for edge in edges}
    test_nodes = [node for node in nodes if _is_test_node(node)]
    production = [node for node in nodes if not _is_test_node(node)]

    for edge in list(edges):
        source = by_id.get(edge.from_id)
        target = by_id.get(edge.to_id)
        if source is None or target is None or not _is_test_node(source) or _is_test_node(target):
            continue
        _append_edge(edges, existing, source.id, target.id, RelationKind.TESTS,
                     edge.confidence, edge.resolution, edge.evidence, edge.candidates)

    for test in test_nodes:
        path = _path_for(test)
        if not path or Path(path).suffix.lower() not in _CODE_SUFFIXES:
            continue
        file_text = contents.get(path, "")
        if not file_text:
            continue
        lines = file_text.splitlines()
        start = test.span.start_line if test.span is not None else 1
        end = test.span.end_line if test.span is not None else len(lines)
        text = "\n".join(lines[max(0, start - 1):end])
        referenced_names: Dict[str, List[GraphNode]] = {}
        for target in production:
            if target.kind not in (NodeKind.CLASS, NodeKind.FUNCTION, NodeKind.METHOD, NodeKind.FILE, NodeKind.MODULE):
                continue
            if len(target.label) > 2 and re.search(rf"\b{re.escape(target.label)}\b", text):
                referenced_names.setdefault(target.label, []).append(target)
        for name, matches in referenced_names.items():
            target = matches[0]
            line = start + _first_line(text, name) - 1
            resolution = Resolution.UNIQUE_NAME if len(matches) == 1 else Resolution.AMBIGUOUS
            _append_edge(
                edges, existing, test.id, target.id, RelationKind.TESTS,
                Confidence.STATIC_INFERRED, resolution,
                SourceSpan(path, line, line), [item.id for item in matches[1:]],
            )
        if referenced_names:
            continue
        stem = Path(path).stem
        fallback_name = re.sub(r"(^test_|_test$|Test$|\.(test|spec)$)", "", stem, flags=re.I)
        matches = [
            target for target in production
            if target.label.lower() == fallback_name.lower()
            and target.kind in (NodeKind.CLASS, NodeKind.FILE, NodeKind.MODULE)
        ]
        matches.sort(key=lambda target: (target.kind != NodeKind.CLASS, target.id))
        if len(matches) == 1:
            _append_edge(
                edges, existing, test.id, matches[0].id, RelationKind.TESTS,
                Confidence.STATIC_INFERRED, Resolution.UNIQUE_NAME,
                SourceSpan(path, 1, 1), [],
            )


def _add_configuration_relations(
    nodes: List[GraphNode],
    edges: List[GraphEdge],
    contents: Mapping[str, str],
) -> None:
    existing = {(edge.from_id, edge.to_id, edge.relation) for edge in edges}
    existing_node_ids = {node.id for node in nodes}
    code_nodes_by_path: Dict[str, List[GraphNode]] = {}
    for node in nodes:
        path = _path_for(node)
        if path and node.kind != NodeKind.CONFIGURATION and Path(path).suffix.lower() in _CODE_SUFFIXES:
            code_nodes_by_path.setdefault(path, []).append(node)

    code_literals: Dict[str, Dict[str, List[int]]] = {}
    for code_path in sorted(code_nodes_by_path):
        code_text = contents.get(code_path)
        if code_text is None:
            continue
        code_literals[code_path] = _index_code_literals(code_text)

    for relative in sorted(contents):
        path = Path(relative)
        if not _is_config_path(path):
            continue
        text = contents[relative]
        if _is_agent_view_artifact(text):
            continue
        occurrences: Dict[str, List[int]] = {}
        for key, line in config_keys(path, text):
            occurrences.setdefault(key, []).append(line)
        for key in sorted(occurrences):
            lines = sorted(occurrences[key])
            line = lines[0]
            node_id = f"config:{relative}:{key}"
            config_node = GraphNode(
                id=node_id,
                label=key,
                group=NodeKind.CONFIGURATION,
                category=NodeKind.CONFIGURATION,
                kind=NodeKind.CONFIGURATION,
                language="configuration",
                span=SourceSpan(relative, line, line),
                cost=cost_for_text(key),
                symbol_path=f"{relative}:{key}",
                provenance="repository-enrichment",
                metadata={"file_path": relative, "key": key, "occurrence_lines": lines},
            )
            if node_id not in existing_node_ids:
                nodes.append(config_node)
                existing_node_ids.add(node_id)
            for code_path, candidates in code_nodes_by_path.items():
                uses_by_consumer: Dict[str, Tuple[GraphNode, List[int]]] = {}
                for use_line in code_literals.get(code_path, {}).get(key, []):
                    consumer = smallest_node_at_line(candidates, use_line)
                    if consumer is not None:
                        entry = uses_by_consumer.setdefault(
                            consumer.id,
                            (consumer, []),
                        )
                        entry[1].append(use_line)
                for consumer, use_lines in uses_by_consumer.values():
                    ordered_lines = sorted(set(use_lines))
                    _append_edge(
                        edges,
                        existing,
                        node_id,
                        consumer.id,
                        RelationKind.CONFIGURES,
                        Confidence.STATIC_CERTAIN,
                        Resolution.EXACT,
                        SourceSpan(code_path, ordered_lines[0], ordered_lines[0]),
                        [],
                        metadata={"occurrence_lines": ordered_lines},
                    )


def _index_code_literals(text: str) -> Dict[str, List[int]]:
    line_starts = _line_starts(text)
    postings: Dict[str, List[int]] = {}
    for match in STRING_RE.finditer(text):
        postings.setdefault(match.group("value"), []).append(
            _line_number(line_starts, match.start())
        )
    return postings


def _is_agent_view_artifact(text: str) -> bool:
    version = any(marker in text for marker in (
        '"schema_version": "2"', '"schema_version":"2"',
        '"schema_version": "3"', '"schema_version":"3"',
    ))
    return version and ('"occurrence_store"' in text or '"query_nodes"' in text)


def _is_config_path(path: Path) -> bool:
    lower_name = path.name.lower()
    return (
        lower_name in _CONFIG_NAMES
        or path.suffix.lower() in _CONFIG_SUFFIXES
        or lower_name.endswith((".gradle", ".gradle.kts"))
    )


def config_keys(path: Path, text: str) -> List[Tuple[str, int]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            json.loads(text)
        except json.JSONDecodeError:
            return []
        starts = _line_starts(text)
        pattern = re.compile(r'(?P<key>"(?:\\.|[^"\\])*")\s*:')
        return [
            (json.loads(match.group("key")), _line_number(starts, match.start()))
            for match in pattern.finditer(text)
        ]
    results: List[Tuple[str, int]] = []
    separator = r"\s*=\s*" if path.name == ".env" or suffix == ".properties" else r"\s*[:=]\s*"
    pattern = re.compile(rf"^\s*([A-Za-z_][\w.-]*){separator}")
    for line_number, line in enumerate(text.splitlines(), 1):
        match = pattern.match(line)
        if match and not line.lstrip().startswith(("#", "//")):
            results.append((match.group(1), line_number))
        if path.name.lower().endswith((".gradle", ".gradle.kts")):
            call = re.search(r"\b(?:buildConfigField|resValue)\s*\(\s*['\"][^'\"]+['\"]\s*,\s*['\"]([^'\"]+)['\"]", line)
            if call:
                results.append((call.group(1), line_number))
    return results


def _line_starts(text: str) -> List[int]:
    return [0, *(index + 1 for index, character in enumerate(text) if character == "\n")]


def _line_number(starts: Sequence[int], offset: int) -> int:
    return bisect.bisect_right(starts, offset)


def _first_line(text: str, value: str) -> int:
    match = re.search(rf"\b{re.escape(value)}\b", text)
    return text.count("\n", 0, match.start()) + 1 if match else 1


def smallest_node_at_line(nodes: Sequence[GraphNode], line: int) -> Optional[GraphNode]:
    matches = [
        node for node in nodes
        if node.span is not None and node.span.start_line <= line <= node.span.end_line
    ]
    if not matches:
        return None
    return min(matches, key=lambda node: node.span.end_line - node.span.start_line)


def _append_edge(
    edges: List[GraphEdge], existing: set, source: str, target: str, relation: str,
    confidence: str, resolution: str, evidence: Optional[SourceSpan], candidates: List[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    key = (source, target, relation)
    if source == target or key in existing:
        return
    existing.add(key)
    edges.append(GraphEdge(
        from_id=source,
        to_id=target,
        relation=relation,
        confidence=confidence,
        resolution=resolution,
        evidence=evidence,
        candidates=list(candidates),
        metadata=dict(metadata or {}),
    ))
