from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from language_analyzers.core.graph_models import (Confidence, GraphEdge, GraphNode,
                                                  RelationKind, Resolution, SourceSpan)
from language_analyzers.typescript.http_calls import HttpCallSite

RULE_ID = "http.client_calls_route"
_SCHEME_HOST = re.compile(r"^https?://[^/]*", re.IGNORECASE)


def normalize_route_path(path: str) -> Optional[str]:
    if not isinstance(path, str) or path == "":
        return None
    text = re.split(r"[?#]", path.strip(), maxsplit=1)[0]
    text = _SCHEME_HOST.sub("", text, count=1)
    head, slash, rest = text.partition("/")
    if head.startswith("${"):
        text = slash + rest
    segments = []
    for segment in text.split("/"):
        if not segment:
            continue
        if (segment.startswith("{") and segment.endswith("}")) or segment.startswith(":") or "${" in segment:
            segment = "{}"
        segments.append(segment)
    return "/" + "/".join(segments)


def _node_span(node: GraphNode) -> Optional[SourceSpan]:
    if node.span is not None:
        return node.span
    file_path = node.metadata.get("file_path")
    line = node.metadata.get("line_number")
    if not file_path or not isinstance(line, int):
        return None
    return SourceSpan(file_path, line, node.metadata.get("end_line_number") or line)


def _key(method: Any, path: Any) -> Optional[Tuple[str, str]]:
    if not isinstance(method, str) or not method or not isinstance(path, str):
        return None
    normalized = normalize_route_path(path)
    return None if normalized is None else (method.upper(), normalized)


def match_routes(
    nodes: Sequence[GraphNode], http_calls: Sequence[HttpCallSite]
) -> Tuple[List[GraphEdge], Dict[str, int]]:
    servers: Dict[Tuple[str, str], List[str]] = {}
    for node in nodes:
        if node.metadata.get("full_path") and node.metadata.get("http_method"):
            key = _key(node.metadata["http_method"], node.metadata["full_path"])
            if key is not None:
                servers.setdefault(key, []).append(node.id)

    clients: List[Tuple[str, Optional[Tuple[str, str]], Optional[SourceSpan]]] = [
        (call.source_id, _key(call.http_method, call.path), call.evidence) for call in http_calls
    ]
    for node in nodes:
        if node.group == "retrofit_endpoint":
            clients.append((
                node.id,
                _key(node.metadata.get("http_method"), node.metadata.get("path")),
                _node_span(node),
            ))

    stats = {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}
    edges: Dict[Tuple[str, str], GraphEdge] = {}
    for source_id, key, evidence in clients:
        if key is None:
            stats["unresolvable"] += 1
            continue
        candidates = sorted(set(servers.get(key, [])))
        if not candidates:
            stats["unmatched"] += 1
            continue
        ambiguous = len(candidates) > 1
        stats["ambiguous" if ambiguous else "matched"] += 1
        target = candidates[0]
        if (source_id, target) in edges:
            continue
        edges[(source_id, target)] = GraphEdge(
            from_id=source_id,
            to_id=target,
            relation=RelationKind.CALLS_ROUTE,
            confidence=Confidence.FRAMEWORK_INFERRED,
            resolution=Resolution.AMBIGUOUS if ambiguous else Resolution.UNIQUE_NAME,
            evidence=evidence,
            candidates=candidates[1:],
            metadata={"framework_rule": {"id": RULE_ID, "specificity": "ambiguous" if ambiguous else "unique"}},
        )
    return [edges[pair] for pair in sorted(edges)], stats
