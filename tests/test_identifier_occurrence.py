"""V1-V5 for spec d01cf9063bb1e4aa v1: identifier_occurrence and bottlenecks.v3 node_metrics.

Techniques: V1/V3 equivalence partitioning; V2 equivalence partitioning + boundary value
(1 vs many occurrences, single vs multiple contexts); V4 scenario; V5 metamorphic
(contents insertion order). Expected values are written by hand from the spec Cases table,
never derived by calling the implementation.
"""
import json
from pathlib import Path

import pytest

from analysis.edge_weights import default_edge_weights_path, load_edge_weights
from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
from bottlenecks.identifier_occurrence import (
    CONTEXTS,
    file_context_kind,
    identifier_file_counts,
    node_identifier,
)
from language_analyzers.python.graph import PythonGraphAnalyzer
from repository import build_snapshot, default_scan_policy_path, load_scan_policy

COUNT_KEYS = {"total", "code", "comment", "docstring", "doc", "config"}
V3_METRIC_KEYS = {
    "token_cost", "effective_token_cost", "pagerank", "hub_score", "authority_score",
    "degree_centrality", "betweenness_centrality", "weighted_centrality_cost", "fan_in", "fan_out",
    "weighted_fan_in", "weighted_fan_out", "hop_2_node_count", "hop_2_token_cost",
    "hop_3_node_count", "hop_3_token_cost",
}
RANKINGS = {
    "pagerank", "hub_score", "authority_score", "degree_centrality", "betweenness_centrality",
    "weighted_centrality_cost", "fan_in", "fan_out", "hop_2_token_cost", "hop_3_token_cost",
    "weighted_fan_in", "weighted_fan_out",
}
CANDIDATE_KINDS = {"large_node", "evidence_spread", "unresolved_boundary"}


def counts(**kwargs):
    return {key: kwargs.get(key, 0) for key in sorted(COUNT_KEYS)}


def foo_counts(contents):
    return identifier_file_counts(contents, ["Foo"])["Foo"]


def test_contexts_constant_matches_signature():
    assert CONTEXTS == ("code", "comment", "docstring", "doc", "config")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("a.md", "doc"), ("a.rst", "doc"), ("a.txt", "doc"),
        ("a.json", "config"), ("a.yaml", "config"), ("a.yml", "config"),
        ("a.toml", "config"), ("a.properties", "config"), ("a.gradle", "config"),
        ("x.gradle.kts", "config"), (".env", "config"), ("conf/.env", "config"),
        ("README.MD", "doc"),
        ("x.kt", "code"), ("a.py", "code"),
    ],
)
def test_V1_file_context_kind_partitions(path, expected):
    assert file_context_kind(path) == expected


@pytest.mark.parametrize(
    ("case", "contents", "expected"),
    [
        ("C1", {"a.py": "Foo()\n"}, counts(total=1, code=1)),
        (
            "C2",
            {
                "a.py": "# Foo\n",
                "b.py": '"""Foo"""\n',
                "c.md": "Foo\n",
                "d.yaml": "k: Foo\n",
                "e.ts": "// Foo\n",
            },
            counts(total=5, comment=2, docstring=1, doc=1, config=1),
        ),
        ("C3", {"a.py": "Foo\n" * 10}, counts(total=1, code=1)),
        ("C4", {"a.py": "Foo = 1  # Foo\n"}, counts(total=1, code=1, comment=1)),
        ("C5", {"a.py": "FooBar = 1\nfoo = 2\n_Foo = 3\n"}, counts()),
        ("C6", {"a.py": 'x = "# Foo"\n'}, counts(total=1, code=1)),
        ("C7", {"a.py": "x = a // Foo\n"}, counts(total=1, code=1)),
        ("C8", {"a.ts": "/* Foo"}, counts(total=1, comment=1)),
    ],
)
def test_V2_identifier_file_counts_cases(case, contents, expected):
    result = identifier_file_counts(contents, ["Foo"])
    assert result == {"Foo": expected}


def test_V2_result_has_exactly_the_documented_keys_for_every_name():
    result = identifier_file_counts({"a.py": "Foo\n"}, ["Foo", "Absent"])
    assert set(result) == {"Foo", "Absent"}
    assert all(set(value) == COUNT_KEYS for value in result.values())
    assert result["Absent"] == counts()


@pytest.mark.parametrize(
    ("label", "expected"),
    [("pkg.mod.Foo", "Foo"), ("Foo", "Foo"), ("", ""), (None, ""), ("a.b-c", "")],
)
def test_V3_node_identifier_partitions(label, expected):
    assert node_identifier(label) == expected


def test_V3_empty_name_counts_are_all_zero_even_with_matching_text():
    result = identifier_file_counts({"a.py": "Foo\n", "b.md": "Foo\n"}, [""])
    assert result[""] == counts()


def test_V5_contents_insertion_order_does_not_change_result():
    items = [
        ("a.py", "# Foo\n"), ("b.py", '"""Foo"""\n'), ("c.md", "Foo\n"),
        ("d.yaml", "k: Foo\n"), ("e.ts", "// Foo\n"), ("f.py", "Foo()\n"),
    ]
    forward = identifier_file_counts(dict(items), ["Foo", "Bar"])
    reverse = identifier_file_counts(dict(reversed(items)), ["Bar", "Foo"])
    assert forward == reverse
    repeated = [identifier_file_counts(dict(items), ["Foo", "Bar"]) for _ in range(3)]
    assert repeated[0] == repeated[1] == repeated[2] == forward
    assert forward["Foo"] == counts(total=6, code=1, comment=2, docstring=1, doc=1, config=1)


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


def test_V4_node_metrics_carry_identifier_counts_and_v3_contract_is_unchanged():
    files = {
        "a.py": "class Foo:\n    pass\n\n\ndef helper():\n    # helper note\n    return 1\n",
        "b.py": "from a import Foo, helper\n\n\ndef use():\n    return Foo(), helper()\n",
        "README.md": "Foo is documented here.\n",
    }
    snapshot, architecture = subject(files)
    weights = load_edge_weights(default_edge_weights_path())
    payload = json.loads(bottlenecks_to_json(analyze_bottlenecks(snapshot, architecture, weights)))
    network = payload["dependency_network"]
    metrics = network["node_metrics"]

    assert payload["schema"] == "bottlenecks.v3"
    assert metrics
    for node_id, node_metric in metrics.items():
        assert V3_METRIC_KEYS <= set(node_metric), node_id
        assert "identifier_file_count" in node_metric and "identifier_file_count_by_context" in node_metric
        assert set(node_metric["identifier_file_count_by_context"]) == set(CONTEXTS), node_id
        assert type(node_metric["identifier_file_count"]) is int
        assert all(type(value) is int for value in node_metric["identifier_file_count_by_context"].values())

    assert set(network["rankings"]) == RANKINGS
    assert {item["kind"] for item in payload["candidates"]} <= CANDIDATE_KINDS

    def ids_with_name(name):
        found = [node.id for node in architecture.nodes if str(node.label).split(".")[-1] == name]
        assert found, f"PythonGraphAnalyzer produced no node named {name}"
        return found

    def by_context(**kwargs):
        return {key: kwargs.get(key, 0) for key in CONTEXTS}

    expected = [
        ("Foo", 3, by_context(code=2, doc=1)),
        ("helper", 2, by_context(code=2, comment=1)),
        ("use", 1, by_context(code=1)),
        # file nodes labelled "a.py"/"b.py" have last segment "py", which occurs in no file text
        ("py", 0, by_context()),
    ]
    for name, total, contexts in expected:
        for node_id in ids_with_name(name):
            assert metrics[node_id]["identifier_file_count"] == total, name
            assert metrics[node_id]["identifier_file_count_by_context"] == contexts, name
