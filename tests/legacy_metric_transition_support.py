"""Maps archived characterization goldens to the output contract of spec f7564b09cf80bdd9 v1.

The allowed differences between a golden recorded before the change and current output are exactly:
the removed metric keys, the removed top_* keys, the bottlenecks schema/versions.analysis strings and the
neighborhood_strategy rename (applied at any depth). Edge lists and every other value are left untouched, so a changed TESTS or
CONFIGURES edge, or a changed remaining metric, still fails the comparison it is used in.
Archived evidence files are never edited; only the in-memory copy is mapped.
"""
import copy

REMOVED_METRICS = frozenset({
    "hub_score", "authority_score", "degree_centrality", "hop_2_node_count", "hop_3_node_count", "hop_3_token_cost",
    "identifier_file_count", "identifier_file_count_by_context",
})
REMOVED_TOPS = frozenset({"top_hubs", "top_hop_3_cost"})
SCHEMA_RENAMES = {"bottlenecks.v4": "bottlenecks.v6", "bottlenecks.v5": "bottlenecks.v7"}
STRATEGY_RENAMES = {"single_bfs_to_3_hops": "single_bfs_to_2_hops"}
REMOVED = REMOVED_METRICS | REMOVED_TOPS


def _strip(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in REMOVED:
                continue
            if key == "neighborhood_strategy" and item in STRATEGY_RENAMES:
                item = STRATEGY_RENAMES[item]
            result[key] = _strip(item)
        if result.get("schema") in SCHEMA_RENAMES:
            result["schema"] = SCHEMA_RENAMES[result["schema"]]
            versions = result.get("versions")
            if isinstance(versions, dict) and versions.get("analysis") == "3":
                versions["analysis"] = "4"
        return result
    if isinstance(value, list):
        return [_strip(item) for item in value]
    return value


def legacy_to_current(value):
    """Maps a golden architecture, bottlenecks or case-keyed collection of them to the current contract."""
    return _strip(copy.deepcopy(value))


COST_DRIVEN = frozenset({"token_cost", "effective_token_cost", "weighted_centrality_cost", "hop_2_token_cost"})
COST_DRIVEN_RANKINGS = frozenset({"weighted_centrality_cost", "hop_2_token_cost"})


def _json_estimate(node):
    from language_analyzers.core.cost import estimate_tokens
    import json

    text = json.dumps(
        {"label": node.get("display_label") or node.get("label") or "", "title": node.get("title") or "",
         "metadata": node.get("metadata", {})},
        ensure_ascii=False, default=str,
    )
    return estimate_tokens(text)


def _neighbors(edges, ids):
    adjacency = {ident: set() for ident in ids}
    for edge in edges:
        group = {edge["to_id"], *edge.get("candidates", [])} if edge["resolution"] == "ambiguous" else {edge["to_id"]}
        for target in group:
            if edge["from_id"] in ids and target in ids and edge["from_id"] != target:
                adjacency[edge["from_id"]].add(target)
                adjacency[target].add(edge["from_id"])
    return adjacency


def _two_hop(adjacency, start):
    first = adjacency[start]
    second = set().union(*(adjacency[other] for other in first)) if first else set()
    return (first | second) - {start}


def expected_cost_rows(builder_arch, golden_rows, current_rows):
    """Cost-driven node metrics after the disk fallback removal, from the pre-bottlenecks node data (F11, F13).

    Nodes without a positive cost estimate (and without metadata.boundary) are costed from their label/title/metadata
    JSON; every other node keeps the golden token_cost. Effective cost keeps each node's golden multiplier.
    """
    nodes = {item["id"]: item for item in builder_arch["nodes"]}
    tokens, ticks = {}, {}
    for ident, row in golden_rows.items():
        node = nodes[ident]
        cost = node.get("cost") or {}
        fallback = not (cost.get("token_estimate") or 0) > 0 and not node.get("metadata", {}).get("boundary")
        tokens[ident] = _json_estimate(node) if fallback else row["token_cost"]
        ticks[ident] = round(10 * row["effective_token_cost"] / row["token_cost"]) if row["token_cost"] else 0
    adjacency = _neighbors(builder_arch["edges"], set(golden_rows))
    effective = {ident: tokens[ident] * ticks[ident] / 10 for ident in golden_rows}
    expected = {}
    for ident in golden_rows:
        expected[ident] = {
            "token_cost": tokens[ident],
            "effective_token_cost": effective[ident],
            "weighted_centrality_cost": current_rows[ident]["pagerank"] * effective[ident],
            "hop_2_token_cost": sum(tokens[other] * ticks[other] for other in _two_hop(adjacency, ident)) / 10,
        }
    return expected


def _without_cost_driven(rows):
    return {ident: {k: v for k, v in row.items() if k not in COST_DRIVEN} for ident, row in rows.items()}


def assert_bottlenecks_match_legacy_modulo_fallback_costs(builder_arch, current, golden):
    """current/golden: bottlenecks payloads (golden already mapped by legacy_to_current).

    Everything except the cost-driven node metrics and their two rankings must be equal to the golden; the
    cost-driven values must equal the independent recomputation in expected_cost_rows.
    """
    import math

    network, old_network = current["dependency_network"], golden["dependency_network"]
    expected = expected_cost_rows(builder_arch, old_network["node_metrics"], network["node_metrics"])
    assert network["node_metrics"].keys() == expected.keys()
    for ident, row in network["node_metrics"].items():
        for key, value in expected[ident].items():
            assert math.isclose(row[key], value, rel_tol=1e-12, abs_tol=1e-9), (ident, key)

    def strip(payload):
        result = copy.deepcopy(payload)
        net = result["dependency_network"]
        net["node_metrics"] = _without_cost_driven(net["node_metrics"])
        for key in COST_DRIVEN_RANKINGS:
            net["rankings"].pop(key)
            for lists in net["rankings_by_category"].values():
                lists.pop(key)
        return result

    assert strip(current) == strip(golden)
    values = network["node_metrics"]
    for key in COST_DRIVEN_RANKINGS:
        assert network["rankings"][key] == [
            {"node_id": ident, "value": values[ident][key]}
            for ident in sorted(values, key=lambda ident: (-values[ident][key], ident))[:10]
        ], key
        for category, lists in network["rankings_by_category"].items():
            entries = lists[key]
            assert entries == sorted(entries, key=lambda item: (-item["value"], item["node_id"])), (category, key)
            assert all(item["value"] == values[item["node_id"]][key] for item in entries), (category, key)
            assert len({item["node_id"] for item in entries}) == len(entries) <= 10
    return expected


def assert_architecture_match_legacy_modulo_fallback_costs(expected_rows, current, golden):
    """After-bottlenecks architecture: node metadata.analysis rows carry the same recomputed cost-driven values."""
    import math

    current_nodes = {item["id"]: item for item in current["nodes"]}
    for ident, values in expected_rows.items():
        analysis = current_nodes[ident]["metadata"]["analysis"]
        for key, value in values.items():
            assert math.isclose(analysis[key], value, rel_tol=1e-12, abs_tol=1e-9), (ident, key)

    def strip(payload):
        result = copy.deepcopy(payload)
        for item in result["nodes"]:
            analysis = item.get("metadata", {}).get("analysis")
            if analysis is not None:
                item["metadata"]["analysis"] = {k: v for k, v in analysis.items() if k not in COST_DRIVEN}
        return result

    assert strip(current) == strip(golden)
