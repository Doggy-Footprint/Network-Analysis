"""V1-V6 for spec 3ea9cf8886ee409f v1: dependency_network.rankings_by_category in bottlenecks.v3.

Techniques: equivalence partitioning (V1, V4, V5, V6), decision table (V2), 3-value boundary
value analysis (V3). Expected categories are assigned by hand from the F2 rule; expected
lists are computed in the test from the payload's own node_metrics (F3 says the values are
the whole-graph metrics), never by calling path_flags or the implementation's ranking code.
"""
import copy
import json
import re
from pathlib import Path
from dataclasses import replace
from pathlib import Path

import pytest

from analysis.edge_weights import default_edge_weights_path, load_edge_weights
from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
from language_analyzers.core.graph_models import GraphNode, NodeCost, SourceSpan
from language_analyzers.python.graph import PythonGraphAnalyzer
from repository import build_snapshot, default_scan_policy_path, load_scan_policy
from report.bottlenecks import render_report
from report.shared.document import ReportInputError
from tests.edge_weights_support import edge

CATEGORIES = ("production", "test", "generated", "vendored", "unknown")
RANKINGS = (
    "pagerank", "hub_score", "authority_score", "degree_centrality", "betweenness_centrality",
    "weighted_centrality_cost", "fan_in", "fan_out", "hop_2_token_cost", "hop_3_token_cost",
    "weighted_fan_in", "weighted_fan_out",
)
ERROR_PATH = "$.dependency_network.rankings_by_category"
HEADING = "분류별 순위"
NO_DATA = "순위 데이터가 없습니다."

PATH_OF = {
    "production": "src/app.py",
    "test": "tests/test_app.py",
    "generated": "migrations/0001.py",
    "vendored": "vendor/lib.py",
}
FILES = {
    "src/app.py": "x\n" * 6,
    "tests/test_app.py": "x\n" * 6,
    "migrations/0001.py": "x\n" * 6,
    "vendor/lib.py": "x\n" * 6,
    "vendor/tests/test_x.py": "x\n" * 6,
    "generated/foo_test.py": "x\n" * 6,
}


def subject(files):
    """Scan exclusions for vendor/generated paths are disabled so those paths reach the snapshot."""
    root = Path("/repo")
    policy = replace(load_scan_policy(default_scan_policy_path()), vendor_globs=[], generated_globs=[], generated_markers=[])
    snapshot = build_snapshot(
        root, sorted(files), policy=policy,
        reader=lambda path: files[path.relative_to(root).as_posix()], ignore_source="test",
    )
    return snapshot, PythonGraphAnalyzer(root, snapshot).analyze()


def weights():
    return load_edge_weights(default_edge_weights_path())


def make_node(node_id, path):
    span = None if path is None else SourceSpan(path, 1, 1)
    return GraphNode(node_id, node_id, "g", "c", span=span, cost=NodeCost(10, 10, 1))


def payload_for(assigned, edges=(), files=FILES):
    """assigned: list of (node_id, path or None)."""
    snapshot, architecture = subject(files)
    architecture = replace(architecture, nodes=[make_node(*item) for item in assigned], edges=list(edges))
    return json.loads(bottlenecks_to_json(analyze_bottlenecks(snapshot, architecture, weights())))


def by_category(payload):
    return payload["dependency_network"]["rankings_by_category"]


def ids_in(category_lists):
    return {entry["node_id"] for entries in category_lists.values() for entry in entries}


def expected_list(payload, members, metric, cap=10):
    metrics = payload["dependency_network"]["node_metrics"]
    rows = sorted(((-metrics[item][metric], item) for item in members))
    return [{"node_id": item, "value": metrics[item][metric]} for _, item in rows[:cap]]


def mixed_graph():
    """Hand-assigned: p* production, t* test, g* generated, v* vendored, u* unknown."""
    assigned = (
        [(f"p{n:02}", "src/app.py") for n in range(12)]
        + [("t0", "tests/test_app.py"), ("t1", "tests/test_app.py")]
        + [("g0", "migrations/0001.py"), ("v0", "vendor/lib.py"), ("u0", None)]
    )
    expected = {
        "production": [f"p{n:02}" for n in range(12)],
        "test": ["t0", "t1"],
        "generated": ["g0"],
        "vendored": ["v0"],
        "unknown": ["u0"],
    }
    edges = [
        edge("p00", "p01"), edge("p00", "p02"), edge("p00", "t0"), edge("p01", "p02"),
        edge("t0", "p03"), edge("t1", "p03"), edge("g0", "v0"), edge("u0", "p00"),
        edge("p05", "p06"), edge("p06", "u0"), edge("v0", "t1"),
    ]
    return assigned, edges, expected


def test_V1_each_node_appears_only_in_its_own_category():
    assigned, edges, expected = mixed_graph()
    payload = payload_for(assigned, edges)
    categories = by_category(payload)
    assert set(categories) == set(CATEGORIES)
    for category, members in expected.items():
        assert set(categories[category]) == set(RANKINGS)
        listed = ids_in(categories[category])
        assert listed <= set(members), category
        if len(members) <= 10:
            assert listed == set(members), category
    for node_id in payload["dependency_network"]["node_metrics"]:
        owners = [name for name in CATEGORIES if node_id in ids_in(categories[name])]
        assert len(owners) <= 1, node_id
        if not node_id.startswith("p"):
            assert len(owners) == 1, node_id


@pytest.mark.parametrize("category", CATEGORIES)
def test_V1_single_node_lands_in_exactly_its_category(category):
    path = None if category == "unknown" else PATH_OF[category]
    payload = payload_for([("solo", path)])
    categories = by_category(payload)
    for name in CATEGORIES:
        expected_ids = {"solo"} if name == category else set()
        assert ids_in(categories[name]) == expected_ids, (category, name)


@pytest.mark.parametrize(
    ("label", "path", "expected"),
    [
        ("vendored-plus-test", "vendor/tests/test_x.py", "vendored"),
        ("generated-plus-test", "generated/foo_test.py", "generated"),
    ],
)
def test_V2_precedence_rules(label, path, expected):
    categories = by_category(payload_for([("n", path)]))
    for name in CATEGORIES:
        assert ids_in(categories[name]) == ({"n"} if name == expected else set()), (label, name)


def test_V3_F1_empty_snapshot_has_all_categories_and_metrics_with_empty_lists():
    snapshot, architecture = subject({})
    payload = json.loads(bottlenecks_to_json(analyze_bottlenecks(snapshot, architecture, weights())))
    categories = by_category(payload)
    assert set(categories) == set(CATEGORIES) and len(categories) == 5
    for name in CATEGORIES:
        assert set(categories[name]) == set(RANKINGS) and len(categories[name]) == 12
        assert all(entries == [] for entries in categories[name].values()), name


@pytest.mark.parametrize(("count", "expected_len"), [(9, 9), (10, 10), (11, 10)])
def test_V3_category_list_is_capped_at_ten(count, expected_len):
    assigned = [(f"p{n:02}", "src/app.py") for n in range(count)]
    edges = [edge(f"p{n:02}", f"p{n + 1:02}") for n in range(count - 1)]
    categories = by_category(payload_for(assigned, edges))
    for metric in RANKINGS:
        assert len(categories["production"][metric]) == expected_len, metric
    for name in CATEGORIES[1:]:
        assert all(entries == [] for entries in categories[name].values()), name


def test_V3_cap_applies_after_filtering_not_before():
    """12 test nodes with high fan-out crowd the global top 10; production nodes still appear."""
    tests = [(f"t{n:02}", "tests/test_app.py") for n in range(12)]
    prods = [("p0", "src/app.py"), ("p1", "src/app.py")]
    edges = [edge(f"t{n:02}", f"t{m:02}") for n in range(6) for m in range(6, 12)]
    categories = by_category(payload_for(tests + prods, edges))
    assert {entry["node_id"] for entry in categories["production"]["fan_out"]} == {"p0", "p1"}
    assert len(categories["test"]["fan_out"]) == 10


def test_V4_values_order_and_category_membership_match_node_metrics():
    assigned, edges, expected = mixed_graph()
    payload = payload_for(assigned, edges)
    metrics = payload["dependency_network"]["node_metrics"]
    categories = by_category(payload)
    for category, members in expected.items():
        for metric in RANKINGS:
            actual = categories[category][metric]
            for entry in actual:
                assert entry["value"] == metrics[entry["node_id"]][metric]
            assert actual == expected_list(payload, members, metric), (category, metric)
    assert len(categories["production"]["fan_in"]) == 10 and len(expected["production"]) == 12


def test_V4_ties_are_ordered_by_node_id():
    """Identical isolated nodes: every metric ties, so order is purely node_id."""
    ids = ["p_c", "p_a", "p_b", "p_e", "p_d"]
    assigned = [(item, "src/app.py") for item in ids]
    categories = by_category(payload_for(assigned))
    for metric in RANKINGS:
        entries = categories["production"][metric]
        assert [entry["node_id"] for entry in entries] == sorted(ids), metric
        assert len({entry["value"] for entry in entries}) == 1, metric


def test_V4_rankings_equal_top_ten_over_all_nodes():
    assigned, edges, _ = mixed_graph()
    payload = payload_for(assigned, edges)
    network = payload["dependency_network"]
    everyone = list(network["node_metrics"])
    assert len(everyone) == 17
    for metric in RANKINGS:
        assert network["rankings"][metric] == expected_list(payload, everyone, metric), metric


def test_V4_json_is_byte_identical_for_equal_inputs_and_keeps_schema():
    assigned, edges, _ = mixed_graph()
    outputs = []
    for _ in range(2):
        snapshot, architecture = subject(FILES)
        architecture = replace(architecture, nodes=[make_node(*item) for item in assigned], edges=list(edges))
        outputs.append(bottlenecks_to_json(analyze_bottlenecks(snapshot, architecture, weights())))
    assert outputs[0] == outputs[1]
    assert json.loads(outputs[0])["schema"] == "bottlenecks.v4"


def report_payload():
    assigned, edges, _ = mixed_graph()
    return payload_for(assigned, edges)


def _not_object(payload):
    payload["dependency_network"]["rankings_by_category"] = []


def _category_not_object(payload):
    payload["dependency_network"]["rankings_by_category"]["production"] = []


def _metric_not_array(payload):
    payload["dependency_network"]["rankings_by_category"]["production"]["fan_in"] = {}


def _entry_missing_node_id(payload):
    del payload["dependency_network"]["rankings_by_category"]["production"]["fan_in"][0]["node_id"]


def _entry_value_non_numeric(payload):
    payload["dependency_network"]["rankings_by_category"]["production"]["fan_in"][0]["value"] = "many"


MALFORMED = {
    "not-an-object": _not_object,
    "category-not-an-object": _category_not_object,
    "metric-not-an-array": _metric_not_array,
    "entry-missing-node-id": _entry_missing_node_id,
    "entry-value-non-numeric": _entry_value_non_numeric,
}


@pytest.mark.parametrize("case", list(MALFORMED))
def test_V5_malformed_rankings_by_category_is_a_validation_error_naming_the_path(case):
    payload = report_payload()
    assert payload["dependency_network"]["rankings_by_category"]["production"]["fan_in"]
    MALFORMED[case](payload)
    with pytest.raises(ReportInputError) as raised:
        render_report(payload)
    assert str(raised.value).startswith(ERROR_PATH)


def test_V5_valid_payload_renders_and_absent_field_is_accepted():
    payload = report_payload()
    assert render_report(payload)
    del payload["dependency_network"]["rankings_by_category"]
    assert "<html" in render_report(payload).lower()


def v6_graph(with_vendored=True):
    prods = [(f"prod_{n:02}", "src/app.py") for n in range(12)]
    others = [("tst_a", "tests/test_app.py"), ("tst_b", "tests/test_app.py"), ("gen_a", "migrations/0001.py"), ("unk_a", None)]
    if with_vendored:
        others.append(("vnd_a", "vendor/lib.py"))
    edges = [
        edge("prod_00", "prod_10"), edge("prod_00", "prod_11"), edge("prod_01", "prod_11"),
        edge("prod_02", "prod_00"), edge("prod_03", "prod_00"), edge("prod_04", "prod_01"),
        edge("prod_05", "prod_02"), edge("prod_06", "prod_07"), edge("prod_08", "prod_09"),
        edge("tst_a", "prod_00"), edge("tst_b", "tst_a"), edge("gen_a", "prod_01"), edge("unk_a", "prod_02"),
    ]
    if with_vendored:
        edges.append(edge("vnd_a", "prod_03"))
    return prods + others, edges


def category_divs(document):
    assert document.count(HEADING) >= 1
    section = document[document.rindex(HEADING):]
    end = section.find("</section>")
    if end != -1:
        section = section[:end]
    marks = list(re.finditer(r'<div data-category="([^"]*)"\s*>', section))
    divs = {}
    for index, mark in enumerate(marks):
        stop = marks[index + 1].start() if index + 1 < len(marks) else len(section)
        assert mark.group(1) not in divs, "duplicate data-category div"
        divs[mark.group(1)] = section[mark.end():stop]
    return divs, len(marks)


def _render_v6(with_vendored):
    assigned, edges = v6_graph(with_vendored)
    payload = payload_for(assigned, edges)
    return payload, *category_divs(render_report(payload))


def test_V6_one_div_per_category_with_metrics_and_only_own_ids():
    payload, divs, count = _render_v6(True)
    categories = by_category(payload)
    assert count == 5 and set(divs) == set(CATEGORIES)
    partial_seen = False
    for name in CATEGORIES:
        own = ids_in(categories[name])
        assert own, name
        assert NO_DATA not in divs[name], name
        for metric in RANKINGS:
            assert metric in divs[name], (name, metric)
        for node_id in own:
            assert node_id in divs[name], (name, node_id)
        for other in CATEGORIES:
            if other != name:
                for node_id in ids_in(categories[other]):
                    assert node_id not in divs[name], (name, node_id)
        listed_per_metric = [{e["node_id"] for e in categories[name][m]} for m in RANKINGS]
        partial_seen = partial_seen or any(ids not in ({*own}, set()) for ids in listed_per_metric)
    assert partial_seen, "graph must rank some id in only some metrics"
    production_ids = {e["node_id"] for entries in categories["production"].values() for e in entries}
    assert any(
        any(node_id not in {e["node_id"] for e in categories["production"][m]} for m in RANKINGS)
        for node_id in production_ids
    ), "production must contain an id ranked in only some metrics"


def test_V6_empty_category_div_has_no_data_message_and_no_metric_panels():
    payload, divs, count = _render_v6(False)
    categories = by_category(payload)
    assert count == 5 and set(divs) == set(CATEGORIES)
    assert ids_in(categories["vendored"]) == set()
    assert NO_DATA in divs["vendored"]
    for metric in RANKINGS:
        assert metric not in divs["vendored"], metric
    assert "vnd_a" not in "".join(divs.values())
    for name in CATEGORIES:
        if name != "vendored":
            assert NO_DATA not in divs[name], name
            assert all(metric in divs[name] for metric in RANKINGS), name
