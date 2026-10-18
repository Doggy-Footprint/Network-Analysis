"""V1, V4, V6 and the metric slice of V10 for spec f7564b09cf80bdd9 v1 (search-mimicry and metric cleanup).

V1 (equivalence partitioning): P1..P8 pin the exact node-metric, top_*, ranking key sets of GraphAnalyzer.analyze
and the bottlenecks payloads. V4 (random testing): S1..S4 compare hop_2_token_cost, fan values and
neighborhood_strategy with a brute-force oracle written here (undirected adjacency, 2-hop set, ticks sum / 10) over
fixed-seed random graphs. V6 (decision table): D1..D6 token_cost provenance with file-read spying.
V10 (error guessing): G3, G5, G6.
Expected values come from the spec text and the oracles below, never from the implementation output.
"""
import builtins
import copy
import io
import json
import math
import os
import random
import subprocess
import sys
from collections import deque
from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest

from analysis import GraphAnalysisConfig, GraphAnalyzer
from language_analyzers.core.cost import estimate_tokens
from language_analyzers.core.graph_models import GraphEdge, GraphNode, NodeCost
from tests.edge_weights_support import edge
from tests.file_analysis_support import converted, node as file_node
from tests.test_bottlenecks_v3 import network_subject, payload_of
from tests.test_category_rankings_v3 import CATEGORIES, mixed_graph, payload_for
from tests.test_file_analysis_core import payload as file_payload

NODE_METRIC_KEYS = {
    "token_cost", "effective_token_cost", "pagerank", "betweenness_centrality", "weighted_centrality_cost",
    "fan_in", "fan_out", "weighted_fan_in", "weighted_fan_out", "hop_2_token_cost",
}
RANKING_KEYS = {
    "pagerank", "betweenness_centrality", "weighted_centrality_cost", "fan_in", "fan_out",
    "weighted_fan_in", "weighted_fan_out", "hop_2_token_cost",
}
TOP_KEYS = {"top_pagerank", "top_betweenness", "top_weighted_cost", "top_hop_2_cost"}
ANALYZE_KEYS = TOP_KEYS | {
    "ambiguity_policy", "edge_weights", "node_metrics", "total_token_cost", "total_effective_token_cost",
    "cost_policy", "betweenness_strategy", "betweenness_sample_size", "neighborhood_strategy",
}
REMOVED_NAMES = (
    "hub_score", "authority_score", "degree_centrality", "hop_3", "hop_2_node_count", "top_hubs",
    "identifier_file_count",
)
BFS, BITSET, HYBRID = "single_bfs_to_2_hops", "exact_bitset", "exact_hybrid"


def plain_nodes(ids, costs=None):
    return [
        GraphNode(item, item, "symbol", "symbol", cost=NodeCost(costs[item] if costs else 3, 12, 1))
        for item in ids
    ]


def assert_no_removed_names(value, where):
    text = json.dumps(value, default=str)
    for name in REMOVED_NAMES:
        assert name not in text, (where, name)


def chain_architecture_payloads(tmp_path):
    symbol_snapshot, symbol_architecture = network_subject(["a", "b", "c"], [edge("a", "b"), edge("b", "c")])
    symbol = payload_of(symbol_snapshot, symbol_architecture)
    files = {"a.py": "abcd", "b.py": "abcde", "c.py": "1234567"}
    nodes = [file_node(letter, f"{letter}.py") for letter in "abc"]
    snap, result = converted(files, nodes, [edge("a", "b"), edge("b", "c")])
    return symbol, file_payload(snap, result, tmp_path), result


# ---- V1: equivalence partitioning ------------------------------------------------------------------------------


def test_V1_P1_analyze_node_metrics_key_set_is_exactly_ten():
    nodes = plain_nodes("abc")
    report = GraphAnalyzer().analyze(nodes, [GraphEdge("a", "b", "CALLS"), GraphEdge("b", "c", "CALLS")])
    assert set(report["node_metrics"]) == {"a", "b", "c"}
    for node_id, row in report["node_metrics"].items():
        assert set(row) == NODE_METRIC_KEYS, node_id
        assert len(row) == 10


def test_V1_P2_analyze_top_and_retained_keys():
    report = GraphAnalyzer().analyze(plain_nodes("abc"), [GraphEdge("a", "b", "CALLS")])
    assert {key for key in report if key.startswith("top_")} == TOP_KEYS
    assert "top_hubs" not in report and "top_hop_3_cost" not in report
    assert set(report) == ANALYZE_KEYS
    for key in TOP_KEYS:
        assert all(set(item) == {"id", "label", "value"} for item in report[key]), key
    assert_no_removed_names({k: v for k, v in report.items() if k != "node_metrics"}, "analyze")


def test_V1_P3_node_metadata_analysis_equals_row_and_key_set():
    nodes = plain_nodes("abc")
    report = GraphAnalyzer().analyze(nodes, [GraphEdge("a", "b", "CALLS")])
    for item in nodes:
        assert set(item.metadata["analysis"]) == NODE_METRIC_KEYS
        assert item.metadata["analysis"] == report["node_metrics"][item.id]


def test_V1_P4_symbol_bottlenecks_node_metrics_keys(tmp_path):
    symbol, _, _ = chain_architecture_payloads(tmp_path)
    metrics = symbol["dependency_network"]["node_metrics"]
    assert set(metrics) == {"a", "b", "c"}
    for node_id, row in metrics.items():
        assert set(row) == NODE_METRIC_KEYS, node_id
        assert "identifier_file_count" not in row and "identifier_file_count_by_context" not in row
    assert_no_removed_names(symbol["dependency_network"], "symbol bottlenecks")


def test_V1_P5_file_bottlenecks_node_metrics_keys(tmp_path):
    _, file_mode, _ = chain_architecture_payloads(tmp_path)
    metrics = file_mode["dependency_network"]["node_metrics"]
    assert set(metrics) == {"file:a.py", "file:b.py", "file:c.py"}
    for node_id, row in metrics.items():
        assert set(row) == NODE_METRIC_KEYS, node_id
    assert_no_removed_names(file_mode["dependency_network"], "file bottlenecks")


@pytest.mark.parametrize("mode", ["symbol", "file"])
def test_V1_P6_rankings_key_set(tmp_path, mode):
    symbol, file_mode, _ = chain_architecture_payloads(tmp_path)
    rankings = (symbol if mode == "symbol" else file_mode)["dependency_network"]["rankings"]
    assert set(rankings) == RANKING_KEYS
    assert len(rankings) == 8


def test_V1_P7_rankings_by_category_every_category_symbol_mode():
    assigned, edges, _ = mixed_graph()
    categories = payload_for(assigned, edges)["dependency_network"]["rankings_by_category"]
    assert set(categories) == set(CATEGORIES)
    for name in CATEGORIES:
        assert set(categories[name]) == RANKING_KEYS, name


def test_V1_P7_rankings_by_category_every_category_file_mode(tmp_path):
    _, file_mode, _ = chain_architecture_payloads(tmp_path)
    categories = file_mode["dependency_network"]["rankings_by_category"]
    assert set(categories) == set(CATEGORIES)
    for name in CATEGORIES:
        assert set(categories[name]) == RANKING_KEYS, name


def test_V1_P8_empty_graph_and_single_node():
    empty = GraphAnalyzer().analyze([], [])
    assert empty["node_metrics"] == {}
    assert empty["total_token_cost"] == 0
    assert set(empty) == ANALYZE_KEYS
    single = GraphAnalyzer().analyze(plain_nodes(["only"]), [])
    row = single["node_metrics"]["only"]
    assert set(row) == NODE_METRIC_KEYS
    assert row["hop_2_token_cost"] == 0
    assert (row["fan_in"], row["fan_out"]) == (0, 0)


def test_V1_P8_empty_snapshot_bottlenecks_has_eight_empty_rankings():
    payload = payload_for([])
    network = payload["dependency_network"]
    assert network["node_metrics"] == {}
    assert network["rankings"] == {key: [] for key in RANKING_KEYS}
    for name in CATEGORIES:
        assert network["rankings_by_category"][name] == {key: [] for key in RANKING_KEYS}


# ---- V1 integration: CLI --bottlenecks JSON (C1, C2) -------------------------------------------------------------

PROJECT = {
    "loader.py": "import importlib\n\ndef load():\n    return importlib.import_module('plugins.alpha')\n",
    "plugins/__init__.py": "",
    "plugins/alpha.py": "def run():\n    return 1\n",
    "main.py": "from loader import load\nfrom plugins.alpha import run\n\ndef main():\n    return load(), run()\n",
}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    for relative, text in PROJECT.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    return root


def run_cli(monkeypatch, project, out, granularity):
    import code_analyzer.cli as cli

    monkeypatch.setattr(sys, "argv", [
        "code-analyzer", str(project), "-l", "python", "--granularity", granularity,
        "-o", str(out / "report.html"), "--json", "--bottlenecks", str(out / "b.json"),
    ])
    try:
        cli.main()
    except SystemExit as exit_request:
        return exit_request.code
    return 0


@pytest.mark.parametrize("granularity,schema", [("symbol", "bottlenecks.v6"), ("file", "bottlenecks.v8")])
def test_V1_C1_C2_cli_bottlenecks_and_architecture_json(monkeypatch, project, tmp_path, granularity, schema):
    out = tmp_path / "out"
    out.mkdir()
    assert run_cli(monkeypatch, project, out, granularity) in (0, None)
    bottlenecks = json.loads((out / "b.json").read_text(encoding="utf-8"))
    architecture = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert bottlenecks["schema"] == schema
    assert ("granularity" in bottlenecks) == (granularity == "file")
    if granularity == "file":
        assert bottlenecks["granularity"] == "file"
    assert bottlenecks["versions"]["analysis"] == "4"
    network = bottlenecks["dependency_network"]
    assert network["node_metrics"]
    for node_id, row in network["node_metrics"].items():
        assert set(row) == NODE_METRIC_KEYS, node_id
    assert set(network["rankings"]) == RANKING_KEYS
    for name in CATEGORIES:
        assert set(network["rankings_by_category"][name]) == RANKING_KEYS
    assert_no_removed_names(bottlenecks, "cli bottlenecks")
    analysis = architecture["stats"]["analysis"]
    present = {key for key in analysis if key.startswith("top_")}
    assert present <= TOP_KEYS
    if granularity == "file":
        assert present == TOP_KEYS
    assert analysis.get("neighborhood_strategy", BFS) in {BFS, BITSET, HYBRID}
    for row in analysis.get("node_metrics", {}).values():
        assert set(row) == NODE_METRIC_KEYS
    assert_no_removed_names(analysis, "cli architecture stats")
    analysed = [item["metadata"]["analysis"] for item in architecture["nodes"] if "analysis" in item["metadata"]]
    assert analysed
    for row in analysed:
        assert set(row) == NODE_METRIC_KEYS


# ---- V4: random testing with an independent brute-force oracle -------------------------------------------------------


def random_graph(seed, size, probability, spanning=False, prefix="n", noise=True):
    rng = random.Random(seed)
    ids = [f"{prefix}{i:03d}" for i in range(size)]
    costs = {item: rng.randint(1, 200) for item in ids}
    pairs = []
    if spanning:
        pairs.extend((ids[i], ids[i + 1]) for i in range(size - 1))
    for i in range(size):
        for j in range(i):
            if rng.random() < probability:
                pairs.append((ids[i], ids[j]) if rng.random() < 0.5 else (ids[j], ids[i]))
    if noise and ids:
        pairs.append(pairs[0] if pairs else (ids[0], ids[0]))
        pairs.append((ids[0], ids[0]))
        pairs.append((ids[-1], f"{prefix}_missing"))
        pairs.append((f"{prefix}_missing", ids[0]))
    rng.shuffle(pairs)
    return ids, costs, pairs


def combine(*parts):
    ids, costs, pairs = [], {}, []
    for part_ids, part_costs, part_pairs in parts:
        ids.extend(part_ids)
        costs.update(part_costs)
        pairs.extend(part_pairs)
    return ids, costs, pairs


def brute_force(ids, costs, pairs):
    known = set(ids)
    undirected = {item: set() for item in ids}
    incoming = {item: set() for item in ids}
    outgoing = {item: set() for item in ids}
    for source, target in pairs:
        if source in known and target in known and source != target:
            undirected[source].add(target)
            undirected[target].add(source)
            outgoing[source].add(target)
            incoming[target].add(source)
    result = {}
    for start in ids:
        reach = {start: 0}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            if reach[current] == 2:
                continue
            for other in undirected[current]:
                if other not in reach:
                    reach[other] = reach[current] + 1
                    queue.append(other)
        members = [item for item in reach if item != start]
        ticks = sum(costs[item] * round(10 * 1.0) for item in members)
        result[start] = (ticks / 10, len(incoming[start]), len(outgoing[start]))
    return result, undirected


def expected_strategy(undirected):
    seen, dense_flags = set(), []
    for start in undirected:
        if start in seen:
            continue
        component, stack = {start}, [start]
        seen.add(start)
        while stack:
            for other in undirected[stack.pop()]:
                if other not in seen:
                    seen.add(other)
                    component.add(other)
                    stack.append(other)
        degree_squares = sum(len(undirected[item]) ** 2 for item in component)
        dense_flags.append(len(component) >= 64 and degree_squares >= 64 * len(component))
    if dense_flags and all(dense_flags):
        return BITSET
    return HYBRID if any(dense_flags) else BFS


def analyze_random(ids, costs, pairs, config=None):
    nodes = plain_nodes(ids, costs)
    edges = [GraphEdge(source, target, "CALLS") for source, target in pairs]
    return GraphAnalyzer(config).analyze(nodes, edges)


def check_against_oracle(ids, costs, pairs, strategy, config=None):
    oracle, undirected = brute_force(ids, costs, pairs)
    if config is None:
        assert expected_strategy(undirected) == strategy, "test generator does not produce the intended partition"
    report = analyze_random(ids, costs, pairs, config)
    assert report["neighborhood_strategy"] == strategy
    assert set(report["node_metrics"]) == set(ids)
    for item in ids:
        row = report["node_metrics"][item]
        expected_cost, fan_in, fan_out = oracle[item]
        assert math.isclose(row["hop_2_token_cost"], expected_cost, rel_tol=1e-12, abs_tol=1e-9), item
        assert (row["fan_in"], row["fan_out"]) == (fan_in, fan_out), item
    return report


@pytest.mark.parametrize("seed,size,probability", [(11, 10, 0.2), (12, 37, 0.06), (13, 63, 0.05), (14, 120, 0.02)])
def test_V4_S1_bfs_only_path_matches_brute_force(seed, size, probability):
    ids, costs, pairs = random_graph(seed, size, probability)
    check_against_oracle(ids, costs, pairs, BFS)


def test_V4_S1_zero_memory_budget_forces_bfs_on_dense_graph():
    ids, costs, pairs = random_graph(21, 70, 0.3, spanning=True)
    _, undirected = brute_force(ids, costs, pairs)
    assert expected_strategy(undirected) == BITSET
    config = GraphAnalysisConfig(neighborhood_memory_budget_bytes=0)
    forced = check_against_oracle(ids, costs, pairs, BFS, config)
    default = analyze_random(ids, costs, pairs)
    assert default["neighborhood_strategy"] == BITSET
    for item in ids:
        for key, value in default["node_metrics"][item].items():
            assert math.isclose(value, forced["node_metrics"][item][key], rel_tol=1e-12, abs_tol=1e-9), (item, key)


@pytest.mark.parametrize("seed,size,probability", [(31, 64, 0.3), (32, 80, 0.2), (33, 100, 0.15)])
def test_V4_S2_exact_bitset_matches_brute_force(seed, size, probability):
    ids, costs, pairs = random_graph(seed, size, probability, spanning=True)
    check_against_oracle(ids, costs, pairs, BITSET)


@pytest.mark.parametrize("seed", [41, 42])
def test_V4_S3_exact_hybrid_dense_component_plus_sparse_component(seed):
    dense = random_graph(seed, 70, 0.3, spanning=True, prefix="d", noise=False)
    sparse = random_graph(seed + 100, 8, 0.0, spanning=True, prefix="s", noise=False)
    lone = (["x000"], {"x000": 9}, [])
    ids, costs, pairs = combine(dense, sparse, lone)
    check_against_oracle(ids, costs, pairs, HYBRID)


def complete_graph(size, seed):
    ids = [f"n{i:03d}" for i in range(size)]
    rng = random.Random(seed)
    costs = {item: rng.randint(1, 200) for item in ids}
    pairs = [(ids[i], ids[j]) for i in range(size) for j in range(i)]
    return ids, costs, pairs


@pytest.mark.parametrize("size,strategy", [(63, BFS), (64, BITSET)])
def test_V4_S4_boundary_complete_graph_node_counts(size, strategy):
    ids, costs, pairs = complete_graph(size, 7)
    check_against_oracle(ids, costs, pairs, strategy)


@pytest.mark.parametrize("size,strategy", [(63, BFS), (64, BITSET)])
def test_V4_S4_boundary_random_dense_node_counts(size, strategy):
    ids, costs, pairs = random_graph(51, size, 0.4, spanning=True)
    check_against_oracle(ids, costs, pairs, strategy)


def test_V4_hop_2_excludes_start_and_counts_each_member_once():
    ids = ["s", "a", "b", "c", "d"]
    costs = {"s": 1000, "a": 1, "b": 2, "c": 4, "d": 8}
    pairs = [("s", "a"), ("a", "b"), ("s", "b"), ("b", "c"), ("c", "d")]
    report = check_against_oracle(ids, costs, pairs, BFS)
    assert report["node_metrics"]["s"]["hop_2_token_cost"] == 1 + 2 + 4
    assert report["node_metrics"]["a"]["hop_2_token_cost"] == 1000 + 2 + 4


# ---- V6: decision table for token_cost ---------------------------------------------------------------------------


def json_estimate(snapshot_node):
    text = json.dumps(
        {
            "label": getattr(snapshot_node, "display_label", "") or snapshot_node.label or "",
            "title": getattr(snapshot_node, "title", ""),
            "metadata": snapshot_node.metadata,
        },
        ensure_ascii=False,
        default=str,
    )
    return estimate_tokens(text)


class ReadSpy:
    def __init__(self, root):
        self.root = str(root)
        self.hits = []

    def record(self, target):
        try:
            text = os.fspath(target)
        except TypeError:
            return
        text = text.decode(errors="ignore") if isinstance(text, bytes) else text
        if self.root in text or text.endswith((".py", ".txt")):
            self.hits.append(text)


def analyze_with_spy(nodes, root, project_path=None):
    spy = ReadSpy(root)
    real_open, real_io_open, real_os_open = builtins.open, io.open, os.open
    real_read_text, real_read_bytes, real_path_open = Path.read_text, Path.read_bytes, Path.open

    def wrap(real):
        def spied(file, *args, **kwargs):
            spy.record(file)
            return real(file, *args, **kwargs)
        return spied

    def wrap_method(real):
        def spied(self, *args, **kwargs):
            spy.record(self)
            return real(self, *args, **kwargs)
        return spied

    with mock.patch.object(builtins, "open", wrap(real_open)), mock.patch.object(io, "open", wrap(real_io_open)), \
            mock.patch.object(os, "open", wrap(real_os_open)), \
            mock.patch.object(Path, "read_text", wrap_method(real_read_text)), \
            mock.patch.object(Path, "read_bytes", wrap_method(real_read_bytes)), \
            mock.patch.object(Path, "open", wrap_method(real_path_open)):
        report = GraphAnalyzer().analyze(nodes, [], project_path)
    return report, spy


SOURCE_LINES = [f"line {index:03d} " + "payload " * 8 for index in range(1, 41)]
SOURCE_TEXT = "\n".join(SOURCE_LINES) + "\n"


@pytest.fixture
def source_file(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text(SOURCE_TEXT, encoding="utf-8")
    return path


def content_estimate(first, last):
    return estimate_tokens("\n".join(SOURCE_LINES[first - 1:last]))


def test_V6_D1_positive_cost_is_used_without_file_access(source_file, tmp_path):
    item = GraphNode("n", "n", "symbol", "symbol", cost=NodeCost(7, 28, 1),
                     metadata={"file_path": str(source_file), "line_number": 1, "end_line_number": 40})
    report, spy = analyze_with_spy([item], tmp_path, str(tmp_path))
    assert report["node_metrics"]["n"]["token_cost"] == 7
    assert spy.hits == []


@pytest.mark.parametrize("positive", [1, 7, 12345])
def test_V6_D1_positive_cost_values_pass_through(positive):
    item = GraphNode("n", "n", "symbol", "symbol", cost=NodeCost(positive, 4, 1))
    assert GraphAnalyzer().analyze([item], [])["node_metrics"]["n"]["token_cost"] == positive


def test_V6_D2_zero_cost_boundary_node_is_zero(source_file, tmp_path):
    item = GraphNode("n", "n", "symbol", "symbol", cost=NodeCost(0, 0, 0),
                     metadata={"boundary": True, "file_path": str(source_file)})
    report, spy = analyze_with_spy([item], tmp_path, str(tmp_path))
    assert report["node_metrics"]["n"]["token_cost"] == 0
    assert report["node_metrics"]["n"]["effective_token_cost"] == 0
    assert spy.hits == []


@pytest.mark.parametrize("placement", ["absolute", "relative-with-project-path"])
def test_V6_D3_zero_cost_non_boundary_uses_json_estimate(source_file, tmp_path, placement):
    file_path = str(source_file) if placement == "absolute" else "sample.py"
    item = GraphNode("n", "n", "symbol", "symbol", cost=NodeCost(0, 0, 0), metadata={"file_path": file_path})
    expected = json_estimate(copy.deepcopy(item))
    assert expected != content_estimate(1, 40)
    report, spy = analyze_with_spy([item], tmp_path, str(tmp_path) if placement != "absolute" else None)
    assert report["node_metrics"]["n"]["token_cost"] == expected
    assert spy.hits == []


@pytest.mark.parametrize("placement", ["absolute", "relative-with-project-path"])
@pytest.mark.parametrize("lines", [(5, 9), (3, None)])
def test_V6_D4_no_cost_with_file_path_and_line_range_uses_json_estimate(source_file, tmp_path, placement, lines):
    file_path = str(source_file) if placement == "absolute" else "sample.py"
    metadata = {"file_path": file_path, "line_number": lines[0]}
    if lines[1] is not None:
        metadata["end_line_number"] = lines[1]
    item = GraphNode("n", "n", "symbol", "symbol", metadata=metadata)
    expected = json_estimate(copy.deepcopy(item))
    assert expected not in {content_estimate(lines[0], lines[1] or lines[0]), content_estimate(1, 40)}
    report, spy = analyze_with_spy([item], tmp_path, str(tmp_path) if placement != "absolute" else None)
    assert report["node_metrics"]["n"]["token_cost"] == expected
    assert spy.hits == []


@pytest.mark.parametrize("variant", ["missing", "outside-project", "unreadable"])
def test_V6_D5_no_cost_with_unusable_file_path_uses_json_estimate_without_error(tmp_path, variant):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text(SOURCE_TEXT, encoding="utf-8")
    locked = project / "locked.py"
    locked.write_text(SOURCE_TEXT, encoding="utf-8")
    file_path = {"missing": "does/not/exist.py", "outside-project": "../outside.py", "unreadable": "locked.py"}[variant]
    if variant == "unreadable":
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("permission bits are not enforced for root")
        locked.chmod(0)
    item = GraphNode("n", "n", "symbol", "symbol", metadata={"file_path": file_path, "line_number": 1, "end_line_number": 40})
    expected = json_estimate(copy.deepcopy(item))
    try:
        report, spy = analyze_with_spy([item], tmp_path, str(project))
    finally:
        locked.chmod(0o644)
    assert report["node_metrics"]["n"]["token_cost"] == expected
    assert spy.hits == []


def test_V6_D6_no_cost_without_file_path_uses_json_estimate():
    item = GraphNode("n", "label", "symbol", "symbol", title="a title", display_label="shown", metadata={"k": "v"})
    expected = json_estimate(copy.deepcopy(item))
    assert GraphAnalyzer().analyze([item], [])["node_metrics"]["n"]["token_cost"] == expected


def test_V6_D6_empty_label_and_title_fall_back_to_empty_strings():
    item = GraphNode("n", "", "symbol", "symbol")
    expected = estimate_tokens(json.dumps({"label": "", "title": "", "metadata": {}}, ensure_ascii=False, default=str))
    assert GraphAnalyzer().analyze([item], [])["node_metrics"]["n"]["token_cost"] == expected


def test_V6_D7_no_cost_with_boundary_flag_uses_json_estimate(source_file, tmp_path):
    item = GraphNode("n", "n", "symbol", "symbol", metadata={"boundary": True, "file_path": str(source_file)})
    expected = json_estimate(copy.deepcopy(item))
    report, spy = analyze_with_spy([item], tmp_path, str(tmp_path))
    assert report["node_metrics"]["n"]["token_cost"] == expected
    assert expected > 0
    assert spy.hits == []


def test_V6_D8_positive_cost_with_boundary_flag_keeps_the_cost(source_file, tmp_path):
    item = GraphNode("n", "n", "symbol", "symbol", cost=NodeCost(13, 52, 1),
                     metadata={"boundary": True, "file_path": str(source_file)})
    report, spy = analyze_with_spy([item], tmp_path, str(tmp_path))
    assert report["node_metrics"]["n"]["token_cost"] == 13
    assert spy.hits == []


def test_V6_json_estimate_depends_on_each_input_field():
    base = GraphNode("n", "label", "symbol", "symbol", title="t", metadata={"k": "v"})
    variants = [
        GraphNode("n", "much longer label " * 5, "symbol", "symbol", title="t", metadata={"k": "v"}),
        GraphNode("n", "label", "symbol", "symbol", title="long title " * 5, metadata={"k": "v"}),
        GraphNode("n", "label", "symbol", "symbol", title="t", metadata={"k": "long value " * 5}),
    ]
    baseline = GraphAnalyzer().analyze([copy.deepcopy(base)], [])["node_metrics"]["n"]["token_cost"]
    for variant in variants:
        expected = json_estimate(copy.deepcopy(variant))
        assert GraphAnalyzer().analyze([variant], [])["node_metrics"]["n"]["token_cost"] == expected
        assert expected > baseline


# ---- V10: error guessing -----------------------------------------------------------------------------------------


def test_V10_G3_removed_keys_do_not_survive_in_any_category_ranking(tmp_path):
    assigned, edges, _ = mixed_graph()
    symbol = payload_for(assigned, edges)
    _, file_mode, _ = chain_architecture_payloads(tmp_path)
    for label, payload in (("symbol", symbol), ("file", file_mode)):
        assert_no_removed_names(payload["dependency_network"]["rankings"], label)
        assert_no_removed_names(payload["dependency_network"]["rankings_by_category"], label)


@pytest.mark.parametrize("variant,expect_limitation", [("no-span-no-cost", True), ("span-only", False), ("cost-only", False)])
def test_V10_G5_fallback_limitation_condition_and_wording(variant, expect_limitation):
    phrase = "Token cost fallback applies to nodes without a source span or explicit cost."
    snapshot, architecture = network_subject(["a", "b"], [edge("a", "b")])
    nodes = list(architecture.nodes)
    nodes[0] = {
        "no-span-no-cost": replace(nodes[0], span=None, cost=None),
        "span-only": replace(nodes[0], cost=None),
        "cost-only": replace(nodes[0], span=None),
    }[variant]
    payload = payload_of(snapshot, replace(architecture, nodes=nodes))
    assert payload["limitations"] == ([phrase] if expect_limitation else [])
    assert payload["coverage"]["limitations"] == ([phrase] if expect_limitation else [])


def test_V10_G6_hop_2_value_is_a_cost_sum_not_a_node_count():
    ids = ["c", "x", "y", "z"]
    costs = {"c": 5, "x": 100, "y": 200, "z": 300}
    pairs = [("c", "x"), ("c", "y"), ("c", "z")]
    report = analyze_random(ids, costs, pairs)
    assert report["node_metrics"]["x"]["hop_2_token_cost"] == 5 + 200 + 300
    assert report["node_metrics"]["c"]["hop_2_token_cost"] == 100 + 200 + 300
    assert report["node_metrics"]["z"]["hop_2_token_cost"] == 5 + 100 + 200
    assert [(item["id"], item["value"]) for item in report["top_hop_2_cost"]] == [
        ("c", 600), ("x", 505), ("y", 405), ("z", 305),
    ]
