import copy
import math
import random
import sys
from collections import deque

import pytest

from analysis import GraphAnalysisConfig, GraphAnalyzer
from language_analyzers.core.graph_models import GraphEdge, GraphNode, NodeCost


BFS = "single_bfs_to_2_hops"
BITSET = "exact_bitset"
HYBRID = "exact_hybrid"


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
            if distances[current] == 2:
                continue
            for target in adjacency[current]:
                if target not in distances:
                    distances[target] = distances[current] + 1
                    pending.append(target)
        result[start] = {node for node, distance in distances.items() if 0 < distance <= 2}
    return result


def oracle_costs(adjacency, ticks):
    return {node: sum(ticks[target] for target in members) / 10 for node, members in oracle_sets(adjacency).items()}


def assert_costs(actual, expected):
    assert actual.keys() == expected.keys()
    for node in expected:
        assert math.isclose(actual[node], expected[node], rel_tol=1e-12, abs_tol=1e-9), node


def node_models(adjacency, costs=None, vendored=()):
    return [
        GraphNode(id=name, label=name, group="symbol", category="symbol",
                  cost=NodeCost(costs[name] if costs else index + 1, (index + 1) * 4, 1),
                  flags=["vendored"] if name in vendored else [])
        for index, name in enumerate(adjacency)
    ]


def edge_models(adjacency):
    return [GraphEdge(a, b, "CALLS") for a in adjacency for b in sorted(adjacency[a]) if a < b]


def run(adjacency, costs, config=None, vendored=()):
    report = GraphAnalyzer(config).analyze(node_models(adjacency, costs, vendored), edge_models(adjacency))
    return {name: row["hop_2_token_cost"] for name, row in report["node_metrics"].items()}, report["neighborhood_strategy"]


@pytest.mark.parametrize("variant", ["empty", "isolated", "chain", "cycle", "hub", "dense", "random"])
def test_V1_all_hop_2_costs_and_marker_membership(variant):
    adjacency, strategy = finite_graph(variant)
    costs = {name: (i * 37) % 1031 + 1 for i, name in enumerate(adjacency)}
    actual, chosen = run(adjacency, costs)
    assert chosen == strategy
    assert_costs(actual, oracle_costs(adjacency, {name: 10 * cost for name, cost in costs.items()}))
    expected = oracle_sets(adjacency)
    recovered = {node: set() for node in adjacency}
    for marker in adjacency:
        marker_costs = {node: 10 if node == marker else 1 for node in adjacency}
        observed, chosen = run(adjacency, marker_costs, vendored=[node for node in adjacency if node != marker])
        assert chosen == strategy
        for start in adjacency:
            assert observed[start] in (0.0, 10.0)
            if observed[start] == 10.0:
                recovered[start].add(marker)
    assert recovered == expected


def test_V1_explicit_distance_boundaries():
    adjacency = chain(5)
    actual, strategy = run(adjacency, {node: 1 for node in adjacency})
    assert actual["n0"] == 2.0
    assert oracle_sets(adjacency)["n0"] == {"n1", "n2"}
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
    costs = {node: i + 1 for i, node in enumerate(adjacency)}
    actual, strategy = run(adjacency, costs)
    assert strategy == expected
    assert_costs(actual, oracle_costs(adjacency, {node: 10 * cost for node, cost in costs.items()}))


@pytest.mark.parametrize("boundary,expected", [("zero", BFS), ("below", BFS), ("equal", BITSET), ("above", BITSET)])
def test_V2_budget_boundaries(boundary, expected):
    adjacency = dense(64)
    costs = {node: i + 1 for i, node in enumerate(adjacency)}
    ticks = {node: 10 * cost for node, cost in costs.items()}
    estimate = GraphAnalyzer()._estimate_neighborhood_bitset_bytes(64, max(ticks.values()).bit_length())
    budget = {"zero": 0, "below": estimate - 1, "equal": estimate, "above": estimate + 1}[boundary]
    actual, strategy = run(adjacency, costs, GraphAnalysisConfig(neighborhood_memory_budget_bytes=budget))
    assert strategy == expected
    assert_costs(actual, oracle_costs(adjacency, ticks))


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
        actual = {name: metrics["hop_2_token_cost"] for name, metrics in report["node_metrics"].items()}
        assert_costs(actual, oracle_costs(adjacency, ticks))
        assert actual["ordinary"] == 1.3
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
        if key not in ("neighborhood_strategy", "node_metrics", "top_hop_2_cost"):
            assert report[key] == baseline[key], key
    for node in default_nodes:
        metrics = report["node_metrics"][node.id]
        assert node.metadata["analysis"] == metrics
        assert metrics.keys() == baseline["node_metrics"][node.id].keys()
        for key in metrics:
            assert math.isclose(metrics[key], baseline["node_metrics"][node.id][key], rel_tol=1e-12, abs_tol=1e-9), (node.id, key)
    ranking = report["top_hop_2_cost"]
    ids = sorted(adjacency, key=lambda name: report["node_metrics"][name]["hop_2_token_cost"], reverse=True)[:10]
    assert [item["id"] for item in ranking] == ids


def test_V4_characterization_rank_ties_retain_input_order_and_ten_cap():
    adjacency = {f"node{i}": set() for i in (9, 1, 11, 0, 8, 2, 10, 3, 7, 4, 6, 5)}
    report = GraphAnalyzer().analyze(node_models(adjacency), [])
    assert [item["id"] for item in report["top_hop_2_cost"]] == list(adjacency)[:10]


def test_V5_repeated_analysis_does_not_retain_component_state():
    analyzer = GraphAnalyzer()
    original_state = copy.deepcopy(vars(analyzer))
    mixed = dense(64)
    mixed.update(chain(7, "c"))
    for adjacency in (dense(64), chain(7), {}, mixed, dense(64)):
        costs = {node: i + 1 for i, node in enumerate(adjacency)}
        expected = oracle_costs(adjacency, {node: 10 * cost for node, cost in costs.items()})
        first = run(adjacency, costs)
        second = run(adjacency, costs)
        assert first == second
        assert_costs(first[0], expected)
        nodes, edges = node_models(adjacency), edge_models(adjacency)
        assert analyzer.analyze(copy.deepcopy(nodes), edges) == analyzer.analyze(copy.deepcopy(nodes), edges)
        assert vars(analyzer) == original_state
