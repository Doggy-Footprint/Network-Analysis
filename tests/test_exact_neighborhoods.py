import copy
import math
import random
import sys
from collections import deque

import pytest

from analysis import GraphAnalysisConfig, GraphAnalyzer
from language_analyzers.core.graph_models import GraphEdge, GraphNode, NodeCost


BFS = "single_bfs_to_3_hops"
BITSET = "exact_bitset"
HYBRID = "exact_hybrid"
HOP_KEYS = ("hop_2_node_count", "hop_2_token_cost", "hop_3_node_count", "hop_3_token_cost")


def graph(size, pairs, prefix="n"):
    adjacency = {f"{prefix}{i}": set() for i in range(size)}
    for a, b in pairs:
        if a != b:
            adjacency[f"{prefix}{a}"].add(f"{prefix}{b}")
            adjacency[f"{prefix}{b}"].add(f"{prefix}{a}")
    return adjacency


def chain(size, prefix="n"):
    return graph(size, ((i, i + 1) for i in range(size - 1)), prefix)


def dense(size, prefix="n"):
    return graph(size, ((i, j) for i in range(size) for j in range(i)), prefix)


def circulant(size=64):
    return graph(size, ((i, (i + offset) % size) for i in range(size) for offset in range(1, 5)))


def finite_graph(name):
    if name == "empty":
        return {}, BFS
    if name == "isolated":
        return graph(1, []), BFS
    if name == "chain":
        return chain(7), BFS
    if name == "cycle":
        return graph(9, ((i, (i + 1) % 9) for i in range(9))), BFS
    if name == "hub":
        return graph(72, ((0, i) for i in range(1, 72))), BITSET
    if name == "dense":
        return dense(64), BITSET
    if name == "random":
        rng = random.Random(1729)
        return graph(72, ((rng.randrange(72), rng.randrange(72)) for _ in range(8 * 72))), BITSET
    raise AssertionError(name)


def oracle_sets(adjacency):
    result = {}
    for start in adjacency:
        distances = {start: 0}
        pending = deque([start])
        while pending:
            current = pending.popleft()
            if distances[current] == 3:
                continue
            for target in adjacency[current]:
                if target not in distances:
                    distances[target] = distances[current] + 1
                    pending.append(target)
        result[start] = tuple({node for node, distance in distances.items() if 0 < distance <= limit} for limit in (2, 3))
    return result


def oracle_metrics(adjacency, ticks):
    return {
        node: (len(h2), sum(ticks[target] for target in h2) / 10,
               len(h3), sum(ticks[target] for target in h3) / 10)
        for node, (h2, h3) in oracle_sets(adjacency).items()
    }


def assert_metrics(actual, expected):
    assert actual.keys() == expected.keys()
    for node in expected:
        assert actual[node][0] == expected[node][0], (node, 2)
        assert actual[node][2] == expected[node][2], (node, 3)
        for index in (1, 3):
            assert math.isclose(actual[node][index], expected[node][index], rel_tol=1e-12, abs_tol=1e-9), (node, index)


def node_models(adjacency):
    return [GraphNode(id=name, label=name, group="symbol", category="symbol", cost=NodeCost(index + 1, (index + 1) * 4, 1)) for index, name in enumerate(adjacency)]


def edge_models(adjacency):
    return [GraphEdge(a, b, "CALLS") for a in adjacency for b in sorted(adjacency[a]) if a < b]


@pytest.mark.parametrize("variant", ["empty", "isolated", "chain", "cycle", "hub", "dense", "random"])
def test_V1_all_node_counts_costs_and_marker_membership(variant):
    adjacency, strategy = finite_graph(variant)
    ticks = {name: (i * 37) % 1031 for i, name in enumerate(adjacency)}
    analyzer = GraphAnalyzer()
    actual, chosen = analyzer._neighborhood_metrics(adjacency, ticks)
    assert chosen == strategy
    assert_metrics(actual, oracle_metrics(adjacency, ticks))
    expected = oracle_sets(adjacency)
    recovered = {node: (set(), set()) for node in adjacency}
    for marker in adjacency:
        marker_ticks = {node: int(node == marker) * 10 for node in adjacency}
        observed, chosen = analyzer._neighborhood_metrics(adjacency, marker_ticks)
        assert chosen == strategy
        for start in adjacency:
            for index, hop in ((1, 0), (3, 1)):
                assert observed[start][index] in (0.0, 1.0)
                if observed[start][index] == 1.0:
                    recovered[start][hop].add(marker)
    assert recovered == expected


def test_V1_explicit_distance_boundaries():
    adjacency = chain(5)
    actual, strategy = GraphAnalyzer()._neighborhood_metrics(adjacency, {node: 10 for node in adjacency})
    assert actual["n0"] == (2, 2.0, 3, 3.0)
    assert oracle_sets(adjacency)["n0"] == ({"n1", "n2"}, {"n1", "n2", "n3"})
    assert strategy == BFS


def test_V2_negative_budget_and_default():
    assert GraphAnalysisConfig().neighborhood_memory_budget_bytes == 256 * 1024 * 1024
    with pytest.raises(ValueError):
        GraphAnalysisConfig(neighborhood_memory_budget_bytes=-1)


@pytest.mark.parametrize("variant,expected", [("n63", BFS), ("n64", BITSET), ("work_below", BFS), ("work_equal", BITSET)])
def test_V2_algorithm_boundaries(variant, expected):
    adjacency = dense(63) if variant == "n63" else dense(64) if variant == "n64" else chain(64) if variant == "work_below" else circulant()
    if variant == "work_equal":
        assert sum(len(neighbors) ** 2 for neighbors in adjacency.values()) == 64 * len(adjacency)
    if variant == "work_below":
        assert sum(len(neighbors) ** 2 for neighbors in adjacency.values()) < 64 * len(adjacency)
    ticks = {node: i + 1 for i, node in enumerate(adjacency)}
    actual, strategy = GraphAnalyzer()._neighborhood_metrics(adjacency, ticks)
    assert strategy == expected
    assert_metrics(actual, oracle_metrics(adjacency, ticks))


@pytest.mark.parametrize("boundary,expected", [("zero", BFS), ("below", BFS), ("equal", BITSET), ("above", BITSET)])
def test_V2_budget_boundaries(boundary, expected):
    adjacency = dense(64)
    ticks = {node: (i + 1) * 10 for i, node in enumerate(adjacency)}
    analyzer = GraphAnalyzer()
    estimate = analyzer._estimate_neighborhood_bitset_bytes(64, max(ticks.values()).bit_length())
    budget = {"zero": 0, "below": estimate - 1, "equal": estimate, "above": estimate + 1}[boundary]
    actual, strategy = GraphAnalyzer(GraphAnalysisConfig(neighborhood_memory_budget_bytes=budget))._neighborhood_metrics(adjacency, ticks)
    assert strategy == expected
    assert_metrics(actual, oracle_metrics(adjacency, ticks))


def test_V2_estimator_accounts_for_live_integer_buffers_and_references():
    analyzer = GraphAnalyzer()
    estimates = []
    for count, cost_bits in ((64, 0), (64, 10), (1500, 10)):
        estimate = analyzer._estimate_neighborhood_bitset_bytes(count, cost_bits)
        full_mask = (1 << count) - 1
        minimum = (2 * count + cost_bits) * sys.getsizeof(full_mask) + 2 * sys.getsizeof([None] * count) + sys.getsizeof([None] * cost_bits)
        assert estimate >= minimum
        estimates.append(estimate)
    assert estimates[0] < estimates[1] < estimates[2]


def mixed_cost_nodes():
    return [
        GraphNode(id=name, label=name, group="symbol", category="symbol", cost=NodeCost(raw, raw * 4, 1), flags=flags)
        for name, raw, flags in (("ordinary", 11, []), ("vendor", 29, ["vendored"]),
                                 ("generated", 13, ["generated"]), ("migration", 17, ["migration"]),
                                 ("far", 23, []))
    ]


def test_V3_cost_policy_zero_cost_bridge_normalization_and_reversal():
    nodes = mixed_cost_nodes()
    pairs = [("ordinary", "vendor"), ("vendor", "generated"), ("generated", "migration"), ("migration", "far")]
    edges = [GraphEdge(a, b, "CALLS") for a, b in pairs]
    adjacency = {node.id: set() for node in nodes}
    for a, b in pairs:
        adjacency[a].add(b)
        adjacency[b].add(a)
    ticks = {"ordinary": 110, "vendor": 0, "generated": 13, "migration": 17, "far": 230}
    clean = GraphAnalyzer().analyze(copy.deepcopy(nodes), edges)
    noisy = edges + [GraphEdge("ordinary", "vendor", "CALLS"), GraphEdge("vendor", "vendor", "CALLS"), GraphEdge("unknown", "far", "CALLS"), GraphEdge("ordinary", "unknown", "CALLS")]
    assert GraphAnalyzer().analyze(copy.deepcopy(nodes), noisy) == clean
    reverse = GraphAnalyzer().analyze(copy.deepcopy(nodes), [GraphEdge(b, a, "CALLS") for a, b in pairs])
    for report in (clean, reverse):
        actual = {name: tuple(metrics[key] for key in HOP_KEYS) for name, metrics in report["node_metrics"].items()}
        assert_metrics(actual, oracle_metrics(adjacency, ticks))
        assert actual["ordinary"] == (2, 1.3, 3, 3.0)
        for node in nodes:
            metrics = report["node_metrics"][node.id]
            assert metrics["token_cost"] == node.cost.token_estimate
            assert math.isclose(metrics["effective_token_cost"], ticks[node.id] / 10, rel_tol=1e-12, abs_tol=1e-9)


@pytest.mark.parametrize("variant,expected", [("empty", BFS), ("chain", BFS), ("dense", BITSET), ("mixed", HYBRID)])
def test_V4_report_strategies_compatibility_rankings_and_metadata(variant, expected):
    adjacency = {} if variant == "empty" else chain(7) if variant == "chain" else dense(64)
    if variant == "mixed":
        adjacency.update(chain(5, "c"))
    nodes = node_models(adjacency)
    edges = edge_models(adjacency)
    default_nodes = copy.deepcopy(nodes)
    baseline = GraphAnalyzer(GraphAnalysisConfig(neighborhood_memory_budget_bytes=0)).analyze(copy.deepcopy(nodes), edges)
    report = GraphAnalyzer().analyze(default_nodes, edges)
    assert report["neighborhood_strategy"] == expected
    assert baseline["neighborhood_strategy"] == BFS
    assert report.keys() == baseline.keys()
    for key in report:
        if key not in ("neighborhood_strategy", "node_metrics", "top_hop_2_cost", "top_hop_3_cost"):
            assert report[key] == baseline[key], key
    for node in default_nodes:
        metrics = report["node_metrics"][node.id]
        assert node.metadata["analysis"] == metrics
        assert metrics.keys() == baseline["node_metrics"][node.id].keys()
        for key in metrics:
            assert math.isclose(metrics[key], baseline["node_metrics"][node.id][key], rel_tol=1e-12, abs_tol=1e-9), (node.id, key)
    for hop in (2, 3):
        ranking = report[f"top_hop_{hop}_cost"]
        ids = sorted(adjacency, key=lambda name: report["node_metrics"][name][f"hop_{hop}_token_cost"], reverse=True)[:10]
        assert [item["id"] for item in ranking] == ids


def test_V4_characterization_rank_ties_retain_input_order_and_ten_cap():
    adjacency = {f"node{i}": set() for i in (9, 1, 11, 0, 8, 2, 10, 3, 7, 4, 6, 5)}
    report = GraphAnalyzer().analyze(node_models(adjacency), [])
    for hop in (2, 3):
        assert [item["id"] for item in report[f"top_hop_{hop}_cost"]] == list(adjacency)[:10]


def test_V5_repeated_helper_and_analysis_do_not_retain_component_state():
    analyzer = GraphAnalyzer()
    original_state = copy.deepcopy(vars(analyzer))
    mixed = dense(64)
    mixed.update(chain(7, "c"))
    for adjacency in (dense(64), chain(7), {}, mixed, dense(64)):
        ticks = {node: (i + 1) * 10 for i, node in enumerate(adjacency)}
        expected = oracle_metrics(adjacency, ticks)
        first = analyzer._neighborhood_metrics(adjacency, ticks)
        second = analyzer._neighborhood_metrics(adjacency, ticks)
        assert first == second
        assert_metrics(first[0], expected)
        nodes, edges = node_models(adjacency), edge_models(adjacency)
        assert analyzer.analyze(copy.deepcopy(nodes), edges) == analyzer.analyze(copy.deepcopy(nodes), edges)
        assert vars(analyzer) == original_state
