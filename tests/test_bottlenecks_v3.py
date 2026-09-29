"""V6 (F12, F13, C7, C10) for spec 8fd668e309160b58 v1: analyze_bottlenecks -> bottlenecks.v3.

Technique: boundary value + equivalence partitioning. Observations are made on the
bottlenecks_to_json payload, whose top-level shape is fixed by F12. Tests marked
"characterization" keep behavior that predates v3 (the spec says "기존 규칙"); their
expectations come from the retired bottlenecks-contract tests (git history), not from
the current implementation.
Assumption recorded for C7: a span's line count is inclusive (end_line - start_line + 1).
"""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from analysis.edge_weights import default_edge_weights_path, load_edge_weights
from bottlenecks import BottleneckInputError, analyze_bottlenecks, bottlenecks_to_json
from language_analyzers.core.graph_models import Confidence, GraphNode, NodeCost, Resolution, SourceSpan
from language_analyzers.python.graph import PythonGraphAnalyzer
from repository import build_snapshot, default_scan_policy_path, load_scan_policy
from tests.edge_weights_support import edge, load_weights, weights_data

TOP_LEVEL_KEYS = {"schema", "snapshot", "edge_weights", "versions", "coverage", "dependency_network", "candidates", "limitations"}
EDGE_WEIGHT_KEYS = {"id", "version", "content_hash", "confidence", "resolution", "large_node_line_threshold"}
V2_RANKINGS = {
    "pagerank", "hub_score", "authority_score", "degree_centrality", "betweenness_centrality",
    "weighted_centrality_cost", "fan_in", "fan_out", "hop_2_token_cost", "hop_3_token_cost",
}
RANKINGS = V2_RANKINGS | {"weighted_fan_in", "weighted_fan_out"}


def default_weights():
    return load_edge_weights(default_edge_weights_path())


def subject(files):
    root = Path("/repo")
    snapshot = build_snapshot(
        root,
        sorted(files),
        policy=load_scan_policy(default_scan_policy_path()),
        reader=lambda path: files[path.relative_to(root).as_posix()],
        ignore_source="test",
    )
    return snapshot, PythonGraphAnalyzer(root, snapshot).analyze()


def network_subject(ids, edges=(), spans=None, lines=6):
    snapshot, architecture = subject({"a.py": "line\n" * lines})
    spans = spans or {}
    nodes = [
        GraphNode(
            item, item, "g", "c",
            span=spans.get(item, SourceSpan("a.py", 1, 1)),
            cost=NodeCost(10, 10, (spans[item].end_line - spans[item].start_line + 1) if item in spans else 1),
        )
        for item in ids
    ]
    return snapshot, replace(architecture, nodes=nodes, edges=list(edges))


def payload_of(snapshot, architecture, weights=None):
    report = analyze_bottlenecks(snapshot, architecture, weights or default_weights())
    return json.loads(bottlenecks_to_json(report))


def candidates_of(payload, kind):
    return [item for item in payload["candidates"] if item["kind"] == kind]


def test_V6_top_level_schema_and_key_set():
    snapshot, architecture = network_subject(["a", "b"], [edge("a", "b")])
    payload = payload_of(snapshot, architecture)
    assert payload["schema"] == "bottlenecks.v3"
    assert set(payload) == TOP_LEVEL_KEYS


def test_V6_edge_weights_section_echoes_the_loaded_configuration(tmp_path):
    weights = load_weights(tmp_path, weights_data(confidence={"static_inferred": 0.5}, large_node_line_threshold=7))
    snapshot, architecture = network_subject(["a"])
    section = payload_of(snapshot, architecture, weights)["edge_weights"]
    assert set(section) == EDGE_WEIGHT_KEYS
    assert section == {
        "id": weights.id,
        "version": weights.version,
        "content_hash": weights.content_hash,
        "confidence": dict(weights.confidence),
        "resolution": dict(weights.resolution),
        "large_node_line_threshold": 7,
    }
    assert section["confidence"]["static_inferred"] == 0.5


def test_V6_C10_empty_snapshot_has_v3_report_with_empty_rankings():
    snapshot, architecture = subject({})
    payload = payload_of(snapshot, architecture)
    network = payload["dependency_network"]
    assert payload["schema"] == "bottlenecks.v3"
    assert set(payload) == TOP_LEVEL_KEYS
    assert network["node_count"] == 0 and network["edge_count"] == 0
    assert network["node_metrics"] == {}
    assert network["rankings"] == {key: [] for key in RANKINGS}
    assert payload["candidates"] == []


def test_V6_rankings_key_set_adds_weighted_fan_keys():
    snapshot, architecture = network_subject(["a", "b"], [edge("a", "b")])
    assert set(payload_of(snapshot, architecture)["dependency_network"]["rankings"]) == RANKINGS


def test_V6_weighted_fan_rankings_use_merged_weights_and_descending_order():
    """a->b certain (1.0), a->c framework_inferred (0.3), b->c ambiguous (0.3).
    weighted_fan_out: a 1.3, b 0.3, c 0.   weighted_fan_in: b 1.0, c 0.6, a 0."""
    edges = [
        edge("a", "b"),
        edge("a", "c", Confidence.FRAMEWORK_INFERRED),
        edge("b", "c", Confidence.STATIC_CERTAIN, Resolution.AMBIGUOUS),
    ]
    snapshot, architecture = network_subject(["a", "b", "c"], edges)
    rankings = payload_of(snapshot, architecture)["dependency_network"]["rankings"]
    fan_out = [(item["node_id"], item["value"]) for item in rankings["weighted_fan_out"]]
    fan_in = [(item["node_id"], item["value"]) for item in rankings["weighted_fan_in"]]
    assert [name for name, _ in fan_out] == ["a", "b", "c"]
    assert [name for name, _ in fan_in] == ["b", "c", "a"]
    assert [value for _, value in fan_out] == pytest.approx([1.3, 0.3, 0.0], abs=1e-12)
    assert [value for _, value in fan_in] == pytest.approx([1.0, 0.6, 0.0], abs=1e-12)
    metrics = payload_of(snapshot, architecture)["dependency_network"]["node_metrics"]
    assert metrics["c"]["weighted_fan_in"] == pytest.approx(0.6, abs=1e-12)
    assert metrics["a"]["weighted_fan_out"] == pytest.approx(1.3, abs=1e-12)


@pytest.mark.parametrize(
    ("label", "end_line", "expected_count"),
    [("span-equals-threshold", 3, 0), ("span-above-threshold", 4, 1)],
)
def test_V6_C7_large_node_boundary(tmp_path, label, end_line, expected_count):
    weights = load_weights(tmp_path, weights_data(large_node_line_threshold=3))
    snapshot, architecture = network_subject(["big"], spans={"big": SourceSpan("a.py", 1, end_line)})
    found = candidates_of(payload_of(snapshot, architecture, weights), "large_node")
    assert len(found) == expected_count
    if expected_count:
        assert found[0]["metrics"] == {"line_count": 4, "line_threshold": 3}
        assert found[0]["evidence"] == {"path": "a.py", "start_line": 1, "end_line": 4}


def test_V6_F13_large_node_uses_the_configured_threshold_not_a_constant(tmp_path):
    snapshot, architecture = network_subject(["mid"], spans={"mid": SourceSpan("a.py", 1, 5)})
    assert candidates_of(payload_of(snapshot, architecture, default_weights()), "large_node") == []
    weights = load_weights(tmp_path, weights_data(large_node_line_threshold=1))
    found = candidates_of(payload_of(snapshot, architecture, weights), "large_node")
    assert [item["metrics"] for item in found] == [{"line_count": 5, "line_threshold": 1}]


def test_V6_F13_unresolved_boundary_is_emitted_for_dynamic_relations_only():
    """characterization: retired NA_13 -- a dynamic_required relation emits unresolved_boundary."""
    snapshot, architecture = network_subject(["a", "b"], [edge("a", "b", Confidence.DYNAMIC_REQUIRED)])
    assert candidates_of(payload_of(snapshot, architecture), "unresolved_boundary")
    snapshot, architecture = network_subject(["a", "b"], [edge("a", "b")])
    assert candidates_of(payload_of(snapshot, architecture), "unresolved_boundary") == []


def evidence_subject(evidences):
    """Edges n1->n2, n3->n2 (one target n2), each carrying one evidence span."""
    snapshot, architecture = subject({"a.py": "x\n" * 6, "b.py": "x\n" * 6})
    nodes = [
        GraphNode(item, item, "g", "c", span=SourceSpan("a.py", 1, 1), cost=NodeCost(10, 10, 1))
        for item in ("n1", "n2", "n3")
    ]
    edges = [edge(source, "n2", evidence=span) for source, span in zip(("n1", "n3"), evidences)]
    return snapshot, replace(architecture, nodes=nodes, edges=edges)


@pytest.mark.parametrize("threshold", [1, 2000])
def test_V6_F13_evidence_spread_two_files_is_a_candidate_at_any_threshold(tmp_path, threshold):
    weights = load_weights(tmp_path, weights_data(large_node_line_threshold=threshold))
    snapshot, architecture = evidence_subject([SourceSpan("a.py", 1, 1), SourceSpan("b.py", 1, 1)])
    found = candidates_of(payload_of(snapshot, architecture, weights), "evidence_spread")
    assert len(found) == 1
    assert set(found[0]["metrics"]) == {"file_count", "line_span", "line_threshold"}
    assert found[0]["metrics"]["file_count"] == 2
    assert found[0]["metrics"]["line_threshold"] == threshold


@pytest.mark.parametrize(("threshold", "expected_count"), [(4, 0), (3, 1)])
def test_V6_F13_evidence_spread_single_file_boundary(tmp_path, threshold, expected_count):
    """Evidence a.py:2-3 and a.py:4-5 -> line_span = 5 - 2 + 1 = 4; candidate only when 4 > threshold."""
    weights = load_weights(tmp_path, weights_data(large_node_line_threshold=threshold))
    snapshot, architecture = evidence_subject([SourceSpan("a.py", 2, 3), SourceSpan("a.py", 4, 5)])
    found = candidates_of(payload_of(snapshot, architecture, weights), "evidence_spread")
    assert len(found) == expected_count
    if expected_count:
        assert found[0]["metrics"] == {"file_count": 1, "line_span": 4, "line_threshold": 3}


def test_V6_duplicate_and_self_edges_are_ignored():
    """characterization: retired NA_04."""
    snapshot, architecture = network_subject(["a", "b"], [edge("a", "b"), edge("a", "b"), edge("a", "a")])
    network = payload_of(snapshot, architecture)["dependency_network"]
    assert network["edge_count"] == 1
    assert network["node_metrics"]["a"]["fan_out"] == network["node_metrics"]["b"]["fan_in"] == 1


def test_V6_tied_rankings_are_node_sorted_and_capped_at_ten():
    """characterization: retired NA_10 (fan_out ranking), now alongside the weighted keys."""
    ids = [f"n{number:02}" for number in range(12)]
    edges = [
        edge("n00", "n01"), edge("n00", "n02"), edge("n00", "n03"),
        edge("n01", "n02"), edge("n01", "n03"),
        edge("n02", "n04"), edge("n03", "n04"),
    ]
    snapshot, architecture = network_subject(ids, edges)
    rankings = payload_of(snapshot, architecture)["dependency_network"]["rankings"]
    assert rankings["fan_out"] == [
        {"node_id": "n00", "value": 3}, {"node_id": "n01", "value": 2},
        {"node_id": "n02", "value": 1}, {"node_id": "n03", "value": 1},
        {"node_id": "n04", "value": 0}, {"node_id": "n05", "value": 0},
        {"node_id": "n06", "value": 0}, {"node_id": "n07", "value": 0},
        {"node_id": "n08", "value": 0}, {"node_id": "n09", "value": 0},
    ]
    assert all(len(items) <= 10 for items in rankings.values())


def test_V6_outside_span_raises_the_typed_input_error():
    """characterization: retired NA_06."""
    snapshot, architecture = network_subject(["a"])
    outside = replace(architecture.nodes[0], span=SourceSpan("outside.py", 1, 1))
    with pytest.raises(BottleneckInputError):
        analyze_bottlenecks(snapshot, replace(architecture, nodes=[outside]), default_weights())


def test_V6_equivalent_inputs_have_byte_identical_compact_json():
    """characterization: retired NA_19."""
    outputs = []
    for _ in range(2):
        snapshot, architecture = network_subject(["a", "b"], [edge("a", "b", Confidence.FRAMEWORK_INFERRED)])
        outputs.append(bottlenecks_to_json(analyze_bottlenecks(snapshot, architecture, default_weights())))
    assert outputs[0] == outputs[1]
    assert outputs[0].endswith("\n") and "\n" not in outputs[0][:-1]


def custom_subject(nodes, edges, lines=12):
    snapshot, architecture = subject({"a.py": "x\n" * lines, "b.py": "x\n" * lines})
    return snapshot, replace(architecture, nodes=nodes, edges=list(edges))


def plain_node(item, span=None, cost_lines=1):
    return GraphNode(
        item, item, "g", "c",
        span=span or SourceSpan("a.py", 1, 1),
        cost=NodeCost(10, 10, cost_lines),
    )


def three_kind_subject():
    nodes = [plain_node(f"n{number}") for number in range(1, 9)]
    nodes[0] = plain_node("n1", SourceSpan("a.py", 1, 5), 5)
    nodes[1] = plain_node("n2", SourceSpan("a.py", 2, 7), 6)
    edges = [
        edge("n1", "n2", Confidence.DYNAMIC_REQUIRED),
        edge("n3", "n4", Confidence.DYNAMIC_REQUIRED),
        edge("n5", "n6", evidence=SourceSpan("a.py", 1, 1)),
        edge("n7", "n6", evidence=SourceSpan("b.py", 1, 1)),
        edge("n5", "n8", evidence=SourceSpan("a.py", 1, 1)),
        edge("n7", "n8", evidence=SourceSpan("b.py", 1, 1)),
    ]
    return custom_subject(nodes, edges)


def test_V6_E3_candidate_ids_are_unique_stable_and_sorted_by_kind_then_id(tmp_path):
    weights = load_weights(tmp_path, weights_data(large_node_line_threshold=3))
    runs = []
    for _ in range(2):
        snapshot, architecture = three_kind_subject()
        runs.append(payload_of(snapshot, architecture, weights)["candidates"])
    first = runs[0]
    for kind in ("large_node", "unresolved_boundary", "evidence_spread"):
        assert len(candidates_of({"candidates": first}, kind)) >= 2, kind
    ids = [item["id"] for item in first]
    assert len(ids) == len(set(ids))
    assert [item["id"] for item in runs[1]] == ids
    assert first == sorted(first, key=lambda item: (item["kind"], item["id"]))


def test_V6_E3_large_node_follows_span_lines_not_cost_line_count(tmp_path):
    weights = load_weights(tmp_path, weights_data(large_node_line_threshold=5))
    nodes = [
        plain_node("long_span_small_cost", SourceSpan("a.py", 1, 10), cost_lines=1),
        plain_node("short_span_big_cost", SourceSpan("a.py", 1, 5), cost_lines=99),
    ]
    snapshot, architecture = custom_subject(nodes, [])
    found = candidates_of(payload_of(snapshot, architecture, weights), "large_node")
    assert [item["metrics"] for item in found] == [{"line_count": 10, "line_threshold": 5}]
    assert found[0]["evidence"] == {"path": "a.py", "start_line": 1, "end_line": 10}


@pytest.mark.parametrize(("threshold", "expected_count"), [(10, 0), (9, 1)])
def test_V6_E3_evidence_spread_line_span_is_extent_not_sum(tmp_path, threshold, expected_count):
    """Evidence a.py:1-1 and a.py:10-10: extent 10, summed lines 2."""
    weights = load_weights(tmp_path, weights_data(large_node_line_threshold=threshold))
    nodes = [plain_node(item) for item in ("n1", "n2", "n3")]
    edges = [
        edge("n1", "n2", evidence=SourceSpan("a.py", 1, 1)),
        edge("n3", "n2", evidence=SourceSpan("a.py", 10, 10)),
    ]
    snapshot, architecture = custom_subject(nodes, edges)
    found = candidates_of(payload_of(snapshot, architecture, weights), "evidence_spread")
    assert len(found) == expected_count
    if expected_count:
        assert found[0]["metrics"] == {"file_count": 1, "line_span": 10, "line_threshold": 9}
        evidence = found[0]["evidence"]
        rows = evidence if isinstance(evidence, list) else [evidence]
        assert all(set(row) == {"path", "start_line", "end_line"} for row in rows)
        assert {(row["path"], row["start_line"], row["end_line"]) for row in rows} == {("a.py", 1, 1), ("a.py", 10, 10)}
