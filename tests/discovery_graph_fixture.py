import dataclasses
import hashlib

from agent_view.models import (
    AgentViewGraph,
    Connection,
    EntryDocument,
    QueryNode,
    ReadableNode,
    ReadUnit,
    ScanReport,
)
from language_analyzers.core.graph_models import NodeCost

NODES = (
    ("n:doc", "docs.md", "Doc", "file", "r:doc"),
    ("n:a1", "a.py", "A1", "function", "r:a"),
    ("n:a2", "a.py", "A2", "function", "r:a"),
    ("n:b", "b.py", "B", "function", "r:b"),
    ("n:c", "pkg/nested/c.py", "C", "function", "r:c"),
    ("n:d", "d.py", "D", "function", "r:d"),
)
UNIT_TOKENS = {"r:doc": 40, "r:a": 100, "r:b": 60, "r:c": 30, "r:d": 20}
QUERIES = (
    ("q:root", ".", "list", "path", "root", ["n:b"], 1, 1, 10),
    ("q:seed", "alpha", "exact", "content", "repository", ["n:a1", "n:c"], 3, 3, 20),
    ("q:empty", "empty", "exact", "content", "repository", [], 0, 0, 0),
    ("q:child", "child", "exact", "content", "repository", ["n:b", "n:c"], 2, 2, 5),
)
HINT_ROLES = {
    ("q:root", "n:b"): ["declaration"],
    ("q:seed", "n:a1"): ["declaration"],
    ("q:seed", "n:c"): ["call"],
    ("q:child", "n:b"): ["reference"],
    ("q:child", "n:c"): ["declaration"],
}
EDGES = (
    ("n:b", "q:child", "generates"),
    ("n:a1", "q:seed", "generates"),
    ("q:child", "q:empty", "hint_query"),
    ("n:a1", "n:b", "static"),
)


def _cost(tokens):
    return NodeCost(token_estimate=tokens, char_count=tokens * 4, line_count=tokens)


def build_graph(
    *,
    entry_injected=True,
    entry_documents=True,
    root_arrivals=("n:b",),
    role_overrides=None,
    extra_queries=(),
    extra_edges=(),
    query_overrides=None,
):
    roles_by_edge = dict(HINT_ROLES)
    roles_by_edge.update(role_overrides or {})
    for node_id in root_arrivals:
        roles_by_edge.setdefault(("q:root", node_id), ["declaration"])
    readable = [
        ReadableNode(
            id=node_id,
            file_path=file_path,
            symbol_id=node_id,
            label=label,
            kind=kind,
            start_line=1,
            end_line=2,
            read_cost=_cost(UNIT_TOKENS[unit_id]),
            read_unit_id=unit_id,
        )
        for node_id, file_path, label, kind, unit_id in NODES
    ]
    units = [
        ReadUnit(
            id=unit_id,
            file_path=next(item[1] for item in NODES if item[4] == unit_id),
            start_line=1,
            end_line=2,
            symbol_ids=[item[0] for item in NODES if item[4] == unit_id],
            read_cost=_cost(tokens),
        )
        for unit_id, tokens in sorted(UNIT_TOKENS.items())
    ]
    queries = [
        QueryNode(
            id=query_id,
            term=term,
            kind=kind,
            surface=surface,
            scope=scope,
            clue_kinds=[],
            origin_node_ids=[],
            rule_id=None,
            source_terms=[],
            occurrence_ranges=[],
            occurrence_digest="",
            arrival_node_ids=list(arrivals),
            total_count=total,
            visible_count=visible,
            truncated=False,
            output_tokens=tokens,
        )
        for query_id, term, kind, surface, scope, arrivals, visible, total, tokens in tuple(QUERIES) + tuple(extra_queries)
    ]
    queries = [
        dataclasses.replace(
            item,
            arrival_node_ids=list(root_arrivals),
            visible_count=len(root_arrivals),
            total_count=len(root_arrivals),
        )
        if item.id == "q:root"
        else item
        for item in queries
    ]

    hint_store = {}
    connections = []
    for (query_id, node_id), roles in sorted(roles_by_edge.items()):
        node = next(item for item in readable if item.id == node_id)
        hint = {
            "path": node.file_path,
            "file_name": node.file_path.rsplit("/", 1)[-1],
            "symbol_name": node.label,
            "roles": list(roles),
            "identifiers": [],
        }
        hint_id = "h:" + hashlib.sha256(f"{query_id}|{node_id}".encode("utf-8")).hexdigest()[:16]
        hint_store[hint_id] = hint
        connections.append(
            Connection(
                id=f"c:result:{query_id}:{node_id}",
                from_id=query_id,
                to_id=node_id,
                kind="result",
                specificity="narrowing",
                evidence={"hint_id": hint_id},
            )
        )
    for identifier, replacements in (query_overrides or {}).items():
        queries = [
            dataclasses.replace(item, **replacements) if item.id == identifier else item
            for item in queries
        ]
    for edge in tuple(EDGES) + tuple(extra_edges):
        source, target, kind = edge[:3]
        specificity = edge[3] if len(edge) == 4 else "narrowing"
        connections.append(
            Connection(
                id=f"c:{kind}:{source}:{target}",
                from_id=source,
                to_id=target,
                kind=kind,
                specificity=specificity,
            )
        )

    documents = []
    if entry_documents:
        documents.append(
            EntryDocument(node_id="n:doc", file_path="docs.md", injected=entry_injected)
        )
    return AgentViewGraph(
        schema_version="3",
        project_name="discovery-fixture",
        project_path="/fixture",
        profile={"characters_per_token": 4, "digit_group_size": 3},
        scan=ScanReport(
            ignore_source="fixture",
            scanned_file_count=len(UNIT_TOKENS),
            excluded_files=[],
            exclusion_counts={},
            snapshot_digest="fixture-digest",
        ),
        read_units=units,
        readable_nodes=readable,
        query_nodes=queries,
        connections=sorted(connections, key=lambda item: item.id),
        entry_documents=documents,
        hint_store=hint_store,
        occurrence_store=[],
    )
