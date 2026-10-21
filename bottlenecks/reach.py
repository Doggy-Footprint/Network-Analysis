from typing import Any, Mapping

from analysis.candidate_projection import candidate_targets
from language_analyzers.core.serialization import edge_to_dict

_SOURCE_LANGUAGES = frozenset({"py", "ts", "tsx", "js", "jsx", "mjs", "cjs", "kt"})
_CONFIRMED = frozenset({"exact", "unique_name"})
_STATIC = frozenset({"static_certain", "static_inferred"})


def reach_candidates(architecture: Any, metrics: Mapping[str, Mapping[str, Any]], top_n: int) -> list[Mapping[str, Any]]:
    # Imported lazily: bottlenecks.core imports this module.
    from bottlenecks.core import _candidate, _category

    production = {}
    categories = {}
    for node in architecture.nodes:
        if (getattr(node, "metadata", {}) or {}).get("boundary"):
            continue
        category = _category(node)
        categories[node.id] = category
        if category == "production":
            production[node.id] = node

    ranked = sorted(production, key=lambda item: (-metrics[item]["pagerank"], item))
    ranks = {node_id: index for index, node_id in enumerate(ranked, 1)}
    hubs = set(ranked[:top_n])
    isolation_targets = {node_id for node_id, node in production.items()
                         if getattr(node, "language", None) in _SOURCE_LANGUAGES and node.cost.line_count >= 1}

    tested = set()
    uncertain_tests = {}
    linked = set()
    related = {}
    records = {}

    def record(edge):
        key = id(edge)
        if key not in records:
            records[key] = edge_to_dict(edge)
        return records[key]

    for edge in architecture.edges:
        confidence, resolution = str(edge.confidence), str(edge.resolution)
        source = edge.from_id
        targets = candidate_targets(edge)
        if str(edge.relation) == "TESTS" and categories.get(source) == "test":
            for target in targets:
                if target not in hubs:
                    continue
                if resolution in _CONFIRMED:
                    tested.add(target)
                elif resolution in {"ambiguous", "unresolved"}:
                    uncertain_tests.setdefault(target, []).append(record(edge))
        if source in production:
            others = [target for target in targets if target in production and target != source]
            if others:
                endpoints = [source, *others]
                for endpoint in endpoints:
                    if endpoint not in isolation_targets:
                        continue
                    if confidence in _STATIC and resolution in _CONFIRMED:
                        linked.add(endpoint)
                    else:
                        related.setdefault(endpoint, []).append(edge)

    candidates = []
    for node_id in ranked[:top_n]:
        if node_id in tested:
            continue
        edges = uncertain_tests.get(node_id, [])
        candidates.append(_candidate(node_id + "|untested_hub", "untested_hub", node_id,
            {"pagerank": metrics[node_id]["pagerank"], "pagerank_rank": ranks[node_id], "top_n": top_n,
             "uncertain_test_edge_count": len(edges)},
            {"path": production[node_id].metadata["file_path"], "uncertain_test_edges": edges}, "static_analyzer_relation"))

    for node_id in sorted(isolation_targets - linked):
        edges = related.get(node_id, [])
        counts = {"framework_inferred": 0, "dynamic_required": 0}
        uncertain = 0
        for edge in edges:
            confidence = str(edge.confidence)
            if confidence in counts:
                counts[confidence] += 1
            elif confidence in _STATIC:
                uncertain += 1
        node = production[node_id]
        candidates.append(_candidate(node_id + "|isolated_node", "isolated_node", node_id,
            {"line_count": node.cost.line_count, "framework_edge_count": counts["framework_inferred"],
             "dynamic_edge_count": counts["dynamic_required"], "uncertain_static_edge_count": uncertain},
            {"path": node.metadata["file_path"], "edges": [record(edge) for edge in edges]}, "static_analyzer_relation"))
    return candidates
