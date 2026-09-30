"""V2 (merge slice), V3, V4, V5 for spec 8fd668e309160b58 v1: weighted PageRank / HITS /
weighted fan in analysis.graph_metrics.

V3: hand-computed oracles on tiny graphs (derivations are written next to the values).
  PageRank assumes the pre-existing damping 0.85 and uniform teleport with total mass 1;
  the graph has no dangling node so the dangling rule does not enter the oracle.
V4: metamorphic -- an all-1.0 weight file must equal edge_weights=None on every metric.
V5: equivalence -- unweighted metrics do not depend on the weights; weighted fan values are explicit.
V2 merge: duplicate (source, target) pairs collapse to the maximum weight (F7).
"""
import copy
import math

import pytest

from analysis import GraphAnalyzer
from analysis.edge_weights import default_edge_weights_path, load_edge_weights
from analysis.graph_metrics import GraphAnalysisConfig, pagerank
from language_analyzers.core.graph_models import Confidence, Resolution
from language_analyzers.python.graph import PythonGraphAnalyzer
from tests.edge_weights_support import edge, load_weights, symbol_nodes, uniform_weights_data, weights_data

DAMPING = 0.85
TOLERANCE = 1e-9
# The oracle graphs are periodic (A <-> {B, C}); the default max_iterations=100 stops above 1e-9 error.
EXACT_CONFIG = dict(max_iterations=10000)


def analyze(nodes, edges, weights=None, project_path=None, **config_options):
    config = GraphAnalysisConfig(edge_weights=weights, **config_options)
    return GraphAnalyzer(config).analyze(copy.deepcopy(nodes), copy.deepcopy(edges), project_path)


def expected_star_pagerank():
    """A->B (1.0), A->C (0.3), B->A, C->A (1.0 each; single out-edge takes the full share).

    With teleport t = (1-d)/3 and total mass 1:
      pA = t + d*(pB + pC) = t + d*(1 - pA)  =>  pA = (t + d) / (1 + d)
      pB = t + d*pA*(1.0/1.3),  pC = t + d*pA*(0.3/1.3)
    """
    teleport = (1 - DAMPING) / 3
    p_a = (teleport + DAMPING) / (1 + DAMPING)
    p_b = teleport + DAMPING * p_a * (1.0 / 1.3)
    p_c = teleport + DAMPING * p_a * (0.3 / 1.3)
    return {"A": p_a, "B": p_b, "C": p_c}


def test_V3_C2_pagerank_function_splits_by_weight_ratio():
    result = pagerank({"A": {"B": 1.0, "C": 0.3}, "B": {"A": 1.0}, "C": {"A": 1.0}}, GraphAnalysisConfig(**EXACT_CONFIG))
    expected = expected_star_pagerank()
    assert sum(result.values()) == pytest.approx(1.0, abs=TOLERANCE)
    for node_id, value in expected.items():
        assert result[node_id] == pytest.approx(value, abs=TOLERANCE), node_id


def test_V3_C2_pagerank_function_is_consistent_for_any_damping():
    """Damping-free relation: with s = pA, d = (3s - 1) / (2 - 3s) follows from the closed form,
    and pB, pC must then satisfy the weighted split with that d."""
    result = pagerank({"A": {"B": 1.0, "C": 0.3}, "B": {"A": 1.0}, "C": {"A": 1.0}}, GraphAnalysisConfig(**EXACT_CONFIG))
    s = result["A"]
    d = (3 * s - 1) / (2 - 3 * s)
    teleport = (1 - d) / 3
    assert result["B"] == pytest.approx(teleport + d * s / 1.3, abs=TOLERANCE)
    assert result["C"] == pytest.approx(teleport + d * s * 0.3 / 1.3, abs=TOLERANCE)


def test_V3_C2_analyzer_pagerank_uses_default_yaml_weights():
    nodes = symbol_nodes("A", "B", "C")
    edges = [
        edge("A", "B"),
        edge("A", "C", Confidence.FRAMEWORK_INFERRED),
        edge("B", "A"),
        edge("C", "A"),
    ]
    metrics = analyze(nodes, edges, load_edge_weights(default_edge_weights_path()), **EXACT_CONFIG)["node_metrics"]
    for node_id, value in expected_star_pagerank().items():
        assert metrics[node_id]["pagerank"] == pytest.approx(value, abs=TOLERANCE), node_id


def test_V3_hits_branch_weighted_bipartite_graph_matches_closed_form(tmp_path):
    """Weights: H1->X 1.0, H1->Y 0.3, H2->X 0.5, H2->Y 0.15 (each is min of the two axes in the yaml below).
    W = [[1, 0.3], [0.5, 0.15]] = u v^T with u = (1, 0.5), v = (1, 0.3), rank 1, so one power step is exact:
      hub = u / |u|,  authority = v / |v|   (L2 normalization)
      |u| = sqrt(1.25),  |v| = sqrt(1.09).
    An unweighted run would give hub = authority = (0.7071, 0.7071) on both sides.
    """
    weights = load_weights(
        tmp_path,
        weights_data(
            confidence={"static_inferred": 0.5, "framework_inferred": 0.5, "dynamic_required": 0.5},
            resolution={"ambiguous": 0.3, "unresolved": 0.15},
        ),
    )
    nodes = symbol_nodes("H1", "H2", "X", "Y")
    edges = [
        edge("H1", "X", Confidence.STATIC_CERTAIN, Resolution.EXACT),
        edge("H1", "Y", Confidence.STATIC_CERTAIN, Resolution.AMBIGUOUS),
        edge("H2", "X", Confidence.STATIC_INFERRED, Resolution.EXACT),
        edge("H2", "Y", Confidence.STATIC_INFERRED, Resolution.UNRESOLVED),
    ]
    metrics = analyze(nodes, edges, weights)["node_metrics"]
    hub_norm, authority_norm = math.sqrt(1.25), math.sqrt(1.09)
    expected_hub = {"H1": 1 / hub_norm, "H2": 0.5 / hub_norm, "X": 0.0, "Y": 0.0}
    expected_authority = {"H1": 0.0, "H2": 0.0, "X": 1 / authority_norm, "Y": 0.3 / authority_norm}
    for node_id in expected_hub:
        assert metrics[node_id]["hub_score"] == pytest.approx(expected_hub[node_id], abs=TOLERANCE), node_id
        assert metrics[node_id]["authority_score"] == pytest.approx(expected_authority[node_id], abs=TOLERANCE), node_id


def graph_of_python_sources(directory):
    (directory / "plugins").mkdir()
    (directory / "plugins" / "__init__.py").write_text("", encoding="utf-8")
    (directory / "plugins" / "alpha.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    (directory / "loader.py").write_text(
        "import importlib\n\ndef load():\n    return importlib.import_module('plugins.alpha')\n", encoding="utf-8"
    )
    (directory / "main.py").write_text(
        "from loader import load\nfrom plugins.alpha import run\n\ndef main():\n    return load(), run()\n",
        encoding="utf-8",
    )
    architecture = PythonGraphAnalyzer(directory).analyze()
    return architecture.nodes, architecture.edges, architecture.project_path


def graph_of_mixed_confidence():
    nodes = symbol_nodes("a", "b", "c", "d", "e", "f")
    edges = [
        edge("a", "b"),
        edge("a", "c", Confidence.FRAMEWORK_INFERRED),
        edge("b", "c", Confidence.STATIC_INFERRED, Resolution.UNIQUE_NAME),
        edge("c", "d", Confidence.STATIC_CERTAIN, Resolution.AMBIGUOUS),
        edge("d", "b", Confidence.DYNAMIC_REQUIRED, Resolution.UNRESOLVED),
        edge("d", "e"),
        edge("e", "a"),
    ]
    return nodes, edges, None


@pytest.mark.parametrize("builder", ["python_sources", "mixed_confidence"])
def test_V4_C5_all_one_weights_equal_no_weights_on_every_metric(tmp_path, builder):
    nodes, edges, project_path = (
        graph_of_python_sources(tmp_path) if builder == "python_sources" else graph_of_mixed_confidence()
    )
    uniform = load_weights(tmp_path, uniform_weights_data(), "uniform.yaml")
    assert analyze(nodes, edges, uniform, project_path) == analyze(nodes, edges, None, project_path)


@pytest.mark.parametrize("builder", ["python_sources", "mixed_confidence"])
def test_V4_control_default_weights_change_the_weighted_metrics_of_the_same_graphs(tmp_path, builder):
    nodes, edges, project_path = (
        graph_of_python_sources(tmp_path) if builder == "python_sources" else graph_of_mixed_confidence()
    )
    default = load_edge_weights(default_edge_weights_path())
    assert analyze(nodes, edges, default, project_path)["node_metrics"] != analyze(nodes, edges, None, project_path)["node_metrics"]


def test_V4_pagerank_function_set_form_equals_all_one_weight_form():
    as_sets = {"a": {"b", "c"}, "b": {"c"}, "c": {"a"}}
    as_weights = {"a": {"b": 1.0, "c": 1.0}, "b": {"c": 1.0}, "c": {"a": 1.0}}
    assert pagerank(as_sets) == pagerank(as_weights)


def mixed_fan_graph():
    nodes = symbol_nodes("a", "b", "c", "d", "e")
    edges = [
        edge("a", "b"),
        edge("a", "c", Confidence.FRAMEWORK_INFERRED),
        edge("b", "c"),
        edge("b", "c", Confidence.STATIC_INFERRED, relation="IMPORTS"),
        edge("d", "c", Confidence.STATIC_CERTAIN, Resolution.AMBIGUOUS),
        edge("c", "e", Confidence.DYNAMIC_REQUIRED, Resolution.UNRESOLVED),
        edge("c", "c"),
        edge("e", "ghost"),
    ]
    return nodes, edges


UNWEIGHTED_KEYS = [
    "fan_in",
    "fan_out",
    "degree_centrality",
    "betweenness_centrality",
    "hop_2_node_count",
    "hop_3_node_count",
    "hop_2_token_cost",
    "hop_3_token_cost",
    "token_cost",
]


def test_V5_unweighted_metrics_are_identical_for_weights_03_and_10(tmp_path):
    nodes, edges = mixed_fan_graph()
    discounted = analyze(nodes, edges, load_edge_weights(default_edge_weights_path()))["node_metrics"]
    full = analyze(nodes, edges, load_weights(tmp_path, uniform_weights_data()))["node_metrics"]
    for node_id in "abcde":
        for key in UNWEIGHTED_KEYS:
            assert discounted[node_id][key] == full[node_id][key], (node_id, key)
    assert {node_id: discounted[node_id]["fan_in"] for node_id in "abcde"} == {"a": 0, "b": 1, "c": 3, "d": 0, "e": 1}
    assert {node_id: discounted[node_id]["fan_out"] for node_id in "abcde"} == {"a": 2, "b": 1, "c": 1, "d": 1, "e": 0}


def test_V5_weighted_fan_values_use_merged_weights():
    """Merged pairs: a->b 1.0, a->c 0.3, b->c max(1.0, 0.3) = 1.0, d->c 0.3, c->e 0.3.
    Self-loop c->c and the edge to a missing node are excluded."""
    nodes, edges = mixed_fan_graph()
    metrics = analyze(nodes, edges, load_edge_weights(default_edge_weights_path()))["node_metrics"]
    expected_in = {"a": 0.0, "b": 1.0, "c": 0.3 + 1.0 + 0.3, "d": 0.0, "e": 0.3}
    expected_out = {"a": 1.0 + 0.3, "b": 1.0, "c": 0.3, "d": 0.3, "e": 0.0}
    for node_id in "abcde":
        assert metrics[node_id]["weighted_fan_in"] == pytest.approx(expected_in[node_id], abs=1e-12), node_id
        assert metrics[node_id]["weighted_fan_out"] == pytest.approx(expected_out[node_id], abs=1e-12), node_id


def test_V5_weighted_fan_equals_counts_when_weights_are_one(tmp_path):
    nodes, edges = mixed_fan_graph()
    metrics = analyze(nodes, edges, load_weights(tmp_path, uniform_weights_data()))["node_metrics"]
    for node_id in "abcde":
        assert metrics[node_id]["weighted_fan_in"] == pytest.approx(metrics[node_id]["fan_in"], abs=1e-12)
        assert metrics[node_id]["weighted_fan_out"] == pytest.approx(metrics[node_id]["fan_out"], abs=1e-12)


def test_V5_C11_self_loop_only_graph_has_zero_weighted_fan():
    metrics = analyze(symbol_nodes("s"), [edge("s", "s")], load_edge_weights(default_edge_weights_path()))["node_metrics"]["s"]
    assert (metrics["fan_in"], metrics["fan_out"]) == (0, 0)
    assert metrics["weighted_fan_in"] == 0
    assert metrics["weighted_fan_out"] == 0


def test_V2_C3_certain_and_inferred_duplicates_merge_to_full_weight():
    nodes = symbol_nodes("A", "B")
    edges = [edge("A", "B", Confidence.FRAMEWORK_INFERRED), edge("A", "B", Confidence.STATIC_CERTAIN)]
    metrics = analyze(nodes, edges, load_edge_weights(default_edge_weights_path()))["node_metrics"]
    assert metrics["B"]["fan_in"] == 1
    assert metrics["B"]["weighted_fan_in"] == pytest.approx(1.0, abs=1e-12)
    assert metrics["A"]["weighted_fan_out"] == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("order", ["larger-first", "smaller-first"])
def test_V2_F7_merge_takes_the_maximum_regardless_of_order_or_relation(tmp_path, order):
    weights = load_weights(
        tmp_path, weights_data(confidence={"static_inferred": 0.5, "framework_inferred": 0.4})
    )
    larger = edge("A", "B", Confidence.STATIC_INFERRED, relation="CALLS")
    smaller = edge("A", "B", Confidence.FRAMEWORK_INFERRED, relation="IMPORTS")
    edges = [larger, smaller] if order == "larger-first" else [smaller, larger]
    metrics = analyze(symbol_nodes("A", "B"), edges, weights)["node_metrics"]
    assert metrics["B"]["weighted_fan_in"] == pytest.approx(0.5, abs=1e-12)
    assert metrics["A"]["weighted_fan_out"] == pytest.approx(0.5, abs=1e-12)
    assert metrics["B"]["fan_in"] == 1
