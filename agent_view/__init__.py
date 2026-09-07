import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from language_analyzers.core.cost import estimate_tokens

from .derived_query import derive_terms
from .exact_query import extract_clues
from .models import (
    SCHEMA_VERSION,
    AgentViewGraph,
    Connection,
    EntryDocument,
    Occurrence,
    QueryNode,
    ReadableNode,
    RepositorySnapshot,
    ScanReport,
)
from .occurrence import (
    OccurrenceIndex,
    OccurrenceStoreError,
    decode_occurrence_block,
    decode_occurrence_ranges,
    encode_occurrence_blocks,
)
from .profile import Profile, ProfileError, Transform, default_profile_path, load_profile
from .readable import build_readable_graph, build_readable_nodes
from .scan import build_snapshot, list_repository_files, read_file, scan_files
from .serialize import graph_to_dict, graph_to_json

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DECLARATION = re.compile(r"\b(?:class|def|fun|function|interface|type|const|let|var)\s+")
_IMPORT = re.compile(r"^\s*(?:from\s+\S+\s+import|import\s+|require\s*\(|use\s+)")

QueryKey = Tuple[str, str, str, str, str]


class AgentViewInputError(ValueError):
    pass


@dataclass
class _QuerySpec:
    kind: str
    term: str
    surface: str
    scope: str
    occurrences: List[Occurrence]
    origins: Set[str] = field(default_factory=set)
    clue_kinds: Set[str] = field(default_factory=set)
    rule_id: Optional[str] = None
    source_terms: Set[str] = field(default_factory=set)
    refinement_depth: int = 0
    parent_key: Optional[QueryKey] = None
    generation_evidence: Dict[str, Any] = field(default_factory=dict)
    duplicate_count: int = 0
    filtered_count: int = 0
    cap_truncated: bool = False


def _query_key(
    kind: str,
    term: str,
    surface: str,
    scope: str,
    equivalence_version: str,
) -> QueryKey:
    normalized = term if kind == "exact" else term.casefold()
    return kind, normalized, surface, scope, equivalence_version


def _query_id(key: QueryKey) -> str:
    return "q:" + hashlib.sha256("|".join(key).encode("utf-8")).hexdigest()[:16]


def _occurrence_digest(occurrences: Sequence[Occurrence]) -> str:
    rows = (
        f"{item.file_path}|{item.line}|{item.col}|{item.matched_text}|"
        f"{item.context}|{item.enclosing_node_id}|{item.surface}"
        for item in occurrences
    )
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _visible_line(item: Occurrence, contents: Mapping[str, str]) -> str:
    if item.surface == "path":
        return item.file_path
    lines = contents.get(item.file_path, "").splitlines()
    if 0 < item.line <= len(lines):
        return lines[item.line - 1]
    return item.matched_text


def _syntax_role(item: Occurrence, line: str, node: Optional[ReadableNode]) -> str:
    if node is not None and "test" in node.flags:
        return "test"
    if item.surface == "path":
        return "path"
    if item.context in {"comment", "docstring"}:
        return "comment"
    if item.context == "doc":
        return "doc"
    if _IMPORT.search(line):
        return "import"
    if _DECLARATION.search(line):
        return "declaration"
    if re.search(rf"['\"]{re.escape(item.matched_text)}['\"]", line):
        return "literal"
    if re.search(rf"\b{re.escape(item.matched_text)}\s*\(", line):
        return "call"
    return "reference"


def _project_hints(
    visible: Sequence[Occurrence],
    contents: Mapping[str, str],
    readable_by_id: Mapping[str, ReadableNode],
) -> Dict[str, Dict[str, Any]]:
    hints: Dict[str, Dict[str, Any]] = {}
    for item in visible:
        node = readable_by_id.get(item.enclosing_node_id)
        line = _visible_line(item, contents)
        hint = hints.setdefault(
            item.enclosing_node_id,
            {
                "path": item.file_path,
                "file_name": Path(item.file_path).name,
                "symbol_name": node.label if node is not None else "",
                "roles": set(),
                "identifiers": set(),
            },
        )
        hint["roles"].add(_syntax_role(item, line, node))
        hint["identifiers"].update(_IDENTIFIER.findall(line))
    result = {}
    for node_id, value in sorted(hints.items()):
        result[node_id] = {
            "path": value["path"],
            "file_name": value["file_name"],
            "symbol_name": value["symbol_name"],
            "roles": sorted(value["roles"]),
            "identifiers": sorted(value["identifiers"]),
        }
    return result


def _render_visible(occurrences: Sequence[Occurrence], contents: Mapping[str, str]) -> str:
    return "\n".join(
        f"{item.file_path}:{item.line}:{_visible_line(item, contents)}"
        for item in occurrences
    )


def _edge_evidence(edge: Any) -> Dict[str, Any]:
    span = getattr(edge, "evidence", None)
    result: Dict[str, Any] = {"relation": str(getattr(edge, "relation", ""))}
    if span is not None:
        result.update({"file_path": span.file_path, "line": span.start_line})
    rule = (getattr(edge, "metadata", None) or {}).get("framework_rule")
    if isinstance(rule, dict) and isinstance(rule.get("id"), str):
        result["rule_id"] = rule["id"]
    return result


def _candidate_proxy_terms(
    architecture: Any,
    read_units: Sequence[Any],
    readable: Sequence[ReadableNode],
    contents: Mapping[str, str],
) -> Dict[str, Dict[str, int]]:
    readable_by_symbol = {
        node.symbol_id: node.id
        for node in readable
        if node.symbol_id is not None
    }
    unit_by_node = {node.id: node.read_unit_id for node in readable}
    labels = {node.id: node.label for node in readable}
    repository_labels = set(labels.values())
    proxy: Dict[str, Dict[str, int]] = defaultdict(dict)

    for edge in getattr(architecture, "edges", []):
        source_id = readable_by_symbol.get(edge.from_id)
        unit_id = unit_by_node.get(source_id)
        target_ids = [edge.to_id, *(getattr(edge, "candidates", None) or [])]
        if unit_id is None:
            continue
        for target_id in target_ids:
            readable_id = readable_by_symbol.get(target_id)
            if readable_id in labels:
                proxy[unit_id][labels[readable_id]] = 0

    for unit in read_units:
        source = "\n".join(
            contents[unit.file_path].splitlines()[unit.start_line - 1:unit.end_line]
        )
        counts = Counter(_IDENTIFIER.findall(source))
        for term, count in counts.items():
            if count >= 2:
                proxy[unit.id].setdefault(term, 1)
        declarations = {labels[node_id] for node_id in unit.symbol_ids if node_id in labels}
        for term in counts:
            if term in repository_labels and term not in declarations:
                proxy[unit.id].setdefault(term, 2)
    return proxy


def _add_spec(specs: Dict[QueryKey, _QuerySpec], spec: _QuerySpec, profile: Profile) -> QueryKey:
    key = _query_key(
        spec.kind,
        spec.term,
        spec.surface,
        spec.scope,
        profile.query_equivalence_version,
    )
    existing = specs.get(key)
    if existing is None:
        specs[key] = spec
        return key
    existing.origins.update(spec.origins)
    existing.clue_kinds.update(spec.clue_kinds)
    existing.source_terms.update(spec.source_terms)
    existing.duplicate_count += 1
    return key


def _query_actions(
    term: str,
    clue_kind: str,
    origins: Set[str],
    profile: Profile,
) -> List[Tuple[str, str, str, Set[str], Set[str], Optional[str], Set[str]]]:
    actions = []
    surfaces = ("path",) if clue_kind == "path" else ("content", "path")
    for surface in surfaces:
        actions.append(("exact", term, surface, origins, {clue_kind}, None, set()))
    if clue_kind != "path":
        for derived, rule_id in derive_terms(term, profile):
            for surface in ("content", "path"):
                actions.append(
                    ("derived", derived, surface, origins, {"identifier"}, rule_id, {term})
                )
    return actions


def _build_search_specs(
    architecture: Any,
    profile: Profile,
    readable: Sequence[ReadableNode],
    read_units: Sequence[Any],
    contents: Mapping[str, str],
    index: OccurrenceIndex,
) -> Dict[QueryKey, _QuerySpec]:
    specs: Dict[QueryKey, _QuerySpec] = {}
    unit_by_node = {node.id: node.read_unit_id for node in readable}
    proxy = _candidate_proxy_terms(architecture, read_units, readable, contents)
    candidates: Dict[str, Dict[str, Tuple[str, Set[str], int]]] = defaultdict(dict)

    for term, clue in sorted(extract_clues(architecture.nodes, readable, contents, profile).items()):
        for origin in sorted(clue.origin_node_ids):
            unit_id = unit_by_node.get(origin)
            if unit_id is None:
                continue
            kinds = sorted(clue.clue_kinds)
            identifier_only = all(kind in {"identifier", "qualified_name"} for kind in kinds)
            proxy_rank = min(
                proxy[unit_id].get(term, 99),
                proxy[unit_id].get(term.rsplit(".", 1)[-1], 99),
            )
            if identifier_only and proxy_rank == 99:
                continue
            if identifier_only:
                rank = proxy_rank
            elif kinds[0] == "path":
                rank = 9
            else:
                rank = 0
            current = candidates[unit_id].setdefault(term, (kinds[0], set(), rank))
            current[1].add(origin)

    for unit in read_units:
        for term, rank in proxy[unit.id].items():
            if len(term) < profile.min_term_length:
                continue
            candidates[unit.id].setdefault(
                term,
                ("identifier", set(unit.symbol_ids), rank),
            )

    for unit in read_units:
        candidates[unit.id].setdefault(unit.file_path, ("path", set(unit.symbol_ids), 9))

    for unit_id in sorted(candidates):
        entries = sorted(
            candidates[unit_id].items(),
            key=lambda item: (item[1][2], item[0].casefold(), item[0]),
        )
        actions = []
        for term, (clue_kind, origins, _rank) in entries:
            actions.extend(_query_actions(term, clue_kind, origins, profile))
        cap_truncated = len(actions) > profile.read_query_candidate_limit
        filtered_count = max(0, len(actions) - profile.read_query_candidate_limit)
        for kind, term, surface, origins, clue_kinds, rule_id, source_terms in actions[:profile.read_query_candidate_limit]:
            occurrences = index.find_path(term) if surface == "path" else index.find(term)
            _add_spec(
                specs,
                _QuerySpec(
                    kind=kind,
                    term=term,
                    surface=surface,
                    scope="repository",
                    occurrences=occurrences,
                    origins=set(origins),
                    clue_kinds=set(clue_kinds),
                    rule_id=rule_id,
                    source_terms=set(source_terms),
                    filtered_count=filtered_count,
                    cap_truncated=cap_truncated,
                ),
                profile,
            )
    return specs


def _build_connection_specs(
    architecture: Any,
    profile: Profile,
    readable_by_id: Mapping[str, ReadableNode],
    specs: Dict[QueryKey, _QuerySpec],
) -> List[Connection]:
    direct = []
    narrowing: Dict[Tuple[str, str], Dict[str, Any]] = {}
    readable_by_symbol = {
        node.symbol_id: node.id
        for node in readable_by_id.values()
        if node.symbol_id is not None
    }
    for edge in sorted(
        getattr(architecture, "edges", []),
        key=lambda item: (item.from_id, item.to_id, str(item.relation)),
    ):
        source_id = readable_by_symbol.get(edge.from_id)
        if source_id is None:
            continue
        targets = {
            readable_by_symbol[identifier]
            for identifier in [edge.to_id, *(getattr(edge, "candidates", None) or [])]
            if identifier in readable_by_symbol
        }
        if not targets:
            continue
        rule = (getattr(edge, "metadata", None) or {}).get("framework_rule")
        declared_specificity = rule.get("specificity") if isinstance(rule, dict) else None
        resolution = str(getattr(edge, "resolution", ""))
        unique = declared_specificity == "unique" or (
            declared_specificity is None
            and len(targets) == 1
            and resolution in {"exact", "unique_name"}
        )
        if unique:
            target = min(targets)
            direct.append(
                _connection(
                    source_id,
                    target,
                    "static",
                    "unique",
                    _edge_evidence(edge),
                )
            )
            continue

        rule_id = (
            str(rule.get("id"))
            if isinstance(rule, dict) and rule.get("id")
            else f"relation:{edge.relation}"
        )
        group = narrowing.setdefault(
            (source_id, rule_id),
            {"targets": set(), "evidence": _edge_evidence(edge)},
        )
        group["targets"].update(targets)

    for (source, rule_id), group in sorted(narrowing.items()):
        occurrences = []
        for target in sorted(group["targets"]):
            node = readable_by_id[target]
            occurrences.append(
                Occurrence(
                    file_path=node.file_path,
                    line=node.start_line or 1,
                    col=0,
                    matched_text=rule_id,
                    context="framework",
                    enclosing_node_id=target,
                    surface="framework",
                )
            )
        _add_spec(
            specs,
            _QuerySpec(
                kind="framework",
                term=rule_id,
                surface="framework",
                scope=f"source:{source}",
                occurrences=occurrences,
                origins={source},
                clue_kinds={"framework"},
                rule_id=rule_id,
                generation_evidence=group["evidence"],
            ),
            profile,
        )
    return direct


def _refinement_candidates(occurrences: Sequence[Occurrence]) -> List[Tuple[str, str]]:
    candidates = set()
    for occurrence in occurrences:
        parts = Path(occurrence.file_path).parts[:-1]
        for length in range(1, len(parts) + 1):
            candidates.add(("path_prefix", Path(*parts[:length]).as_posix()))
        suffix = Path(occurrence.file_path).suffix
        if suffix:
            candidates.add(("extension", suffix))
    return sorted(candidates)


def _refined_subset(
    occurrences: Sequence[Occurrence],
    refinement_kind: str,
    value: str,
) -> List[Occurrence]:
    if refinement_kind == "path_prefix":
        return [item for item in occurrences if item.file_path.startswith(value + "/")]
    return [item for item in occurrences if Path(item.file_path).suffix == value]


def _add_refinements(specs: Dict[QueryKey, _QuerySpec], profile: Profile) -> None:
    queue = sorted(specs)
    position = 0
    while position < len(queue):
        parent_key = queue[position]
        position += 1
        parent = specs[parent_key]
        if parent.refinement_depth >= profile.refinement_depth_limit:
            continue
        if len(parent.occurrences) <= profile.refinement_threshold:
            continue
        produced = 0
        visible_occurrences = parent.occurrences[: profile.search_output_limit]
        for kind, value in _refinement_candidates(visible_occurrences):
            subset = _refined_subset(parent.occurrences, kind, value)
            if not subset or len(subset) >= len(parent.occurrences):
                continue
            child = _QuerySpec(
                kind="refinement",
                term=parent.term,
                surface=parent.surface,
                scope=f"{parent.scope}|{kind}:{value}",
                occurrences=subset,
                clue_kinds={"refinement"},
                rule_id="refinement-v1",
                source_terms={parent.term},
                refinement_depth=parent.refinement_depth + 1,
                parent_key=parent_key,
                generation_evidence={"kind": kind, "value": value},
            )
            child_key = _add_spec(specs, child, profile)
            if child_key not in queue:
                queue.append(child_key)
            produced += 1
            if produced == profile.refinement_query_limit:
                break


def _connection(
    source: str,
    target: str,
    kind: str,
    specificity: str,
    evidence: Dict[str, Any],
) -> Connection:
    evidence_identity = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    identity = f"{source}|{target}|{kind}|{specificity}|{evidence_identity}"
    identifier = "c:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:14]
    return Connection(identifier, source, target, kind, specificity, evidence)


def build_agent_view(
    architecture: Any,
    *,
    profile: Optional[Profile] = None,
    snapshot: Optional[RepositorySnapshot] = None,
    excluded_paths: Sequence[str] = (),
    file_reader: Optional[Callable[[Path], Optional[str]]] = None,
    file_lister: Optional[Callable[[Path], Tuple[str, List[str]]]] = None,
) -> AgentViewGraph:
    active = profile or load_profile(default_profile_path())
    root = Path(architecture.project_path)
    if snapshot is None:
        lister = file_lister or (
            lambda path: list_repository_files(path, tracked_files_only=active.tracked_files_only)
        )
        ignore_source, paths = lister(root)
        snapshot = build_snapshot(
            root,
            paths,
            profile=active,
            reader=file_reader or read_file,
            ignore_source=ignore_source,
            excluded_paths=excluded_paths,
        )

    contents = snapshot.content_map()
    readable, read_units, _ = build_readable_graph(
        architecture.nodes,
        list(contents),
        contents,
        active.read_unit_token_limit,
    )
    readable_by_id = {node.id: node for node in readable}
    nodes_by_file: Dict[str, List[ReadableNode]] = defaultdict(list)
    for node in readable:
        nodes_by_file[node.file_path].append(node)
    index = OccurrenceIndex(contents, nodes_by_file)

    specs = _build_search_specs(
        architecture,
        active,
        readable,
        read_units,
        contents,
        index,
    )
    root_paths = [
        path
        for path in sorted(contents)
        if len(Path(path).parts) <= active.root_list_depth
    ][:active.root_list_entry_limit]
    _add_spec(
        specs,
        _QuerySpec(
            kind="list",
            term=".",
            surface="path",
            scope="root",
            occurrences=index.list_paths(root_paths),
            clue_kinds={"entry"},
        ),
        active,
    )
    connections = _build_connection_specs(architecture, active, readable_by_id, specs)
    _add_refinements(specs, active)

    ordered_keys = sorted(specs, key=_query_id)
    occurrence_blocks, occurrence_ranges = encode_occurrence_blocks(
        [specs[key].occurrences for key in ordered_keys],
        active.occurrence_block_rows,
    )
    queries = []
    hints_by_query: Dict[str, Dict[str, Dict[str, Any]]] = {}
    hint_store: Dict[str, Dict[str, Any]] = {}
    for key, ranges in zip(ordered_keys, occurrence_ranges):
        spec = specs[key]
        visible = spec.occurrences[:active.search_output_limit]
        arrivals = sorted({item.enclosing_node_id for item in visible})
        query_id = _query_id(key)
        hints = _project_hints(visible, contents, readable_by_id)
        hints_by_query[query_id] = hints
        queries.append(
            QueryNode(
                id=query_id,
                term=spec.term,
                kind=spec.kind,
                surface=spec.surface,
                scope=spec.scope,
                clue_kinds=sorted(spec.clue_kinds),
                origin_node_ids=sorted(spec.origins),
                rule_id=spec.rule_id,
                source_terms=sorted(spec.source_terms),
                occurrence_ranges=ranges,
                occurrence_digest=_occurrence_digest(spec.occurrences),
                arrival_node_ids=arrivals,
                total_count=len(spec.occurrences),
                visible_count=len(visible),
                truncated=len(visible) < len(spec.occurrences),
                output_tokens=estimate_tokens(_render_visible(visible, contents)) if visible else 0,
                duplicate_suppressed_count=spec.duplicate_count,
                candidate_filtered_count=spec.filtered_count,
                candidate_cap_truncated=spec.cap_truncated,
                refinement_depth=spec.refinement_depth,
            )
        )
        for origin in sorted(spec.origins):
            connections.append(
                _connection(
                    origin,
                    query_id,
                    "generates",
                    "narrowing",
                    spec.generation_evidence,
                )
            )
        for arrival in arrivals:
            hint = hints[arrival]
            serialized_hint = repr(sorted(hint.items()))
            hint_id = "h:" + hashlib.sha256(serialized_hint.encode("utf-8")).hexdigest()[:16]
            hint_store.setdefault(hint_id, hint)
            connections.append(
                _connection(
                    query_id,
                    arrival,
                    "result",
                    "narrowing",
                    {"hint_id": hint_id},
                )
            )
        if spec.parent_key is not None:
            connections.append(
                _connection(
                    _query_id(spec.parent_key),
                    query_id,
                    "refines",
                    "narrowing",
                    spec.generation_evidence,
                )
            )

    query_lookup = {(query.term, query.surface): query.id for query in queries}
    for query in queries:
        terms = {
            identifier
            for hint in hints_by_query[query.id].values()
            for identifier in hint["identifiers"]
            if identifier != query.term
        }
        linked = 0
        for term in sorted(terms):
            target = query_lookup.get((term, query.surface))
            if target is None or target == query.id:
                continue
            connections.append(
                _connection(
                    query.id,
                    target,
                    "hint_query",
                    "narrowing",
                    {"term": term},
                )
            )
            linked += 1
            if linked == active.hint_query_limit:
                break

    unique_connections = {}
    for connection in connections:
        existing = unique_connections.get(connection.id)
        if existing is not None and existing != connection:
            raise AgentViewInputError(f"connection id collision: {connection.id}")
        unique_connections[connection.id] = connection
    entry_documents = []
    for name in ("AGENTS.md", "CLAUDE.md", "README.md"):
        node = next((item for item in readable if item.file_path == name), None)
        if node is not None:
            entry_documents.append(
                EntryDocument(node_id=node.id, file_path=name, injected=name != "README.md")
            )

    exclusion_counts = Counter(item.reason for item in snapshot.excluded_files)
    scan = ScanReport(
        ignore_source=snapshot.ignore_source,
        scanned_file_count=len(contents),
        excluded_files=list(snapshot.excluded_files),
        exclusion_counts=dict(sorted(exclusion_counts.items())),
        snapshot_digest=snapshot.digest,
    )
    return AgentViewGraph(
        schema_version=SCHEMA_VERSION,
        project_name=getattr(architecture, "project_name", ""),
        project_path=str(root),
        profile=active.output(),
        scan=scan,
        read_units=read_units,
        readable_nodes=readable,
        query_nodes=sorted(queries, key=lambda query: query.id),
        connections=sorted(unique_connections.values(), key=lambda connection: connection.id),
        entry_documents=entry_documents,
        hint_store=dict(sorted(hint_store.items())),
        occurrence_store=occurrence_blocks,
    )


def diff_agent_view(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    for name, payload in (("before", before), ("after", after)):
        if not isinstance(payload, dict):
            raise AgentViewInputError(f"{name}: must be an object")
        if payload.get("schema_version") != "3":
            raise AgentViewInputError(f"{name}.schema_version: expected '3'")

    def section(name: str) -> Dict[str, Any]:
        left = {item["id"]: item for item in before.get(name, [])}
        right = {item["id"]: item for item in after.get(name, [])}
        shared = left.keys() & right.keys()
        return {
            "added": sorted(right.keys() - left.keys()),
            "removed": sorted(left.keys() - right.keys()),
            "changed": sorted(identifier for identifier in shared if left[identifier] != right[identifier]),
        }

    return {
        "schema_version": "3",
        "readable_nodes": section("readable_nodes"),
        "query_nodes": section("query_nodes"),
        "connections": section("connections"),
        "profile": {"before": before.get("profile", {}), "after": after.get("profile", {})},
    }


__all__ = [
    "SCHEMA_VERSION",
    "AgentViewGraph",
    "AgentViewInputError",
    "Occurrence",
    "OccurrenceIndex",
    "OccurrenceStoreError",
    "Profile",
    "ProfileError",
    "RepositorySnapshot",
    "Transform",
    "build_agent_view",
    "build_readable_graph",
    "build_readable_nodes",
    "build_snapshot",
    "decode_occurrence_block",
    "decode_occurrence_ranges",
    "default_profile_path",
    "derive_terms",
    "diff_agent_view",
    "encode_occurrence_blocks",
    "extract_clues",
    "graph_to_dict",
    "graph_to_json",
    "list_repository_files",
    "load_profile",
    "read_file",
    "scan_files",
]
