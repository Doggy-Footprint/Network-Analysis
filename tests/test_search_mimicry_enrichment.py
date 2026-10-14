"""V2, V3 and the enrichment slice of V10 for spec f7564b09cf80bdd9 v1.

V2 (decision table, one case per rule R1..R6): enrich_repository adds TESTS edges only as copies of existing
edges that leave a test node and have at least one production node among their candidate targets (F2).
V3 (equivalence partitioning K1..K5): CONFIGURES edges keep their base conditions, evidence and metadata, carry
confidence static_inferred / resolution exact (F3), and that confidence drives the default-weight fan-out.
V10 (error guessing): G1 fixed confidence on clones, G2 CONFIGURES change leaking into other edges.
Expected values are stated from the spec; node and edge inputs are built by hand.
"""
import copy
from types import SimpleNamespace

import pytest

from analysis import GraphAnalysisConfig, GraphAnalyzer
from analysis.edge_weights import default_edge_weights_path, load_edge_weights
from language_analyzers.core.enrichment import enrich_repository
from language_analyzers.core.graph_models import (
    Confidence, GraphEdge, GraphNode, NodeCost, RelationKind, Resolution, SourceSpan,
)
from repository import RepositorySnapshot
from tests.edge_weights_support import load_weights, weights_data

ROOT = "/enrich-oracle"
PROD_PATH = "src/foo.py"
TEST_PATH = "tests/test_foo.py"


def snapshot(files):
    return RepositorySnapshot(ROOT, "snapshot.v1", tuple(sorted(files.items())), ())


def prod(ident, path=PROD_PATH, kind="function", lines=(1, 2)):
    return GraphNode(ident, ident, "symbol", "symbol", kind=kind, span=SourceSpan(path, *lines),
                     cost=NodeCost(5, 20, 2))


def make_test_node(ident, path=TEST_PATH, lines=(1, 3)):
    return GraphNode(ident, ident, "symbol", "symbol", kind="function", span=SourceSpan(path, *lines),
                     flags=["test"], cost=NodeCost(5, 20, 2))


def call(source, target, confidence=Confidence.STATIC_CERTAIN, resolution=Resolution.EXACT, line=2,
         candidates=(), path=TEST_PATH, relation=RelationKind.CALLS):
    return GraphEdge(source, target, relation, confidence=confidence, resolution=resolution,
                     evidence=SourceSpan(path, line, line), candidates=list(candidates))


def enriched(nodes, edges, files):
    architecture = SimpleNamespace(project_path=ROOT, nodes=list(nodes), edges=list(edges))
    enrich_repository(architecture, snapshot=snapshot(files))
    return architecture


def relation_edges_of_tests(architecture):
    return [edge for edge in architecture.edges if edge.relation == RelationKind.TESTS]


def config_edges(architecture):
    return [edge for edge in architecture.edges if edge.relation == RelationKind.CONFIGURES]


def view(edge):
    return (edge.from_id, edge.to_id, str(edge.confidence), str(edge.resolution), edge.evidence, list(edge.candidates))


FOO_FILES = {
    PROD_PATH: "class Foo:\n    pass\n",
    TEST_PATH: "from src.foo import Foo\ndef test_foo():\n    return Foo()\n",
}


# ---- V2: decision table -----------------------------------------------------------------------------------------


def test_V2_R1_test_to_production_edge_is_copied_with_original_attributes():
    original = call("t", "p", Confidence.FRAMEWORK_INFERRED, Resolution.UNIQUE_NAME, line=3)
    architecture = enriched([prod("p"), make_test_node("t")], [original], FOO_FILES)
    assert [view(edge) for edge in relation_edges_of_tests(architecture)] == [
        ("t", "p", "framework_inferred", "unique_name", SourceSpan(TEST_PATH, 3, 3), []),
    ]
    assert original in architecture.edges and original.relation == RelationKind.CALLS


@pytest.mark.parametrize("variant", ["string", "comment"])
def test_V2_R2_name_occurrence_without_edge_creates_no_tests_edge(variant):
    body = {"string": 'def test_foo():\n    return "Foo"\n', "comment": "def test_foo():\n    # Foo\n    return 1\n"}[variant]
    files = {PROD_PATH: "class Foo:\n    pass\n", TEST_PATH: body}
    architecture = enriched([prod("Foo", kind="class"), make_test_node("test_foo")], [], files)
    assert relation_edges_of_tests(architecture) == []
    assert architecture.edges == []


@pytest.mark.parametrize("test_path", ["tests/test_foo.py", "tests/foo_test.py", "tests/Foo.test.py"])
def test_V2_R3_test_file_stem_alone_creates_no_tests_edge(test_path):
    files = {PROD_PATH: "class Foo:\n    pass\n", test_path: "def test_behavior():\n    assert True\n"}
    architecture = enriched([prod("Foo", kind="class"), make_test_node("test_behavior", test_path)], [], files)
    assert relation_edges_of_tests(architecture) == []


@pytest.mark.parametrize("resolution,candidates", [(Resolution.EXACT, []), (Resolution.AMBIGUOUS, ["t2"])])
def test_V2_R4_test_to_test_edge_creates_no_tests_edge(resolution, candidates):
    files = {**FOO_FILES, "tests/test_helper.py": "def helper():\n    return 1\n"}
    nodes = [make_test_node("t"), make_test_node("t2", "tests/test_helper.py", (1, 2)), make_test_node("t3", "tests/test_helper.py", (1, 2))]
    edges = [call("t", "t3", resolution=resolution, candidates=candidates)]
    architecture = enriched(nodes, edges, files)
    assert relation_edges_of_tests(architecture) == []


def test_V2_R5_production_to_production_edge_creates_no_tests_edge():
    files = {PROD_PATH: "def a():\n    return b()\ndef b():\n    return 1\n"}
    architecture = enriched([prod("a", lines=(1, 2)), prod("b", lines=(3, 4))], [call("a", "b", path=PROD_PATH)], files)
    assert relation_edges_of_tests(architecture) == []


@pytest.mark.parametrize(
    "representative,candidates,variant",
    [("p1", ["p2"], "operational-representative"), ("helper", ["p1", "p2"], "test-representative-with-operational-candidates")],
)
def test_V2_R6_ambiguous_edge_with_operational_candidate_is_copied_with_same_candidates(representative, candidates, variant):
    files = {**FOO_FILES, "tests/test_helper.py": "def helper():\n    return 1\n"}
    nodes = [prod("p1"), prod("p2", lines=(3, 4)), make_test_node("t"), make_test_node("helper", "tests/test_helper.py", (1, 2))]
    original = call("t", representative, Confidence.STATIC_INFERRED, Resolution.AMBIGUOUS, line=2, candidates=candidates)
    architecture = enriched(nodes, [original], files)
    assert [view(edge) for edge in relation_edges_of_tests(architecture)] == [
        ("t", representative, "static_inferred", "ambiguous", SourceSpan(TEST_PATH, 2, 2), candidates),
    ], variant


def flag_only_test_node(ident, path=PROD_PATH, lines=(1, 2)):
    return GraphNode(ident, ident, "symbol", "symbol", kind="function", span=SourceSpan(path, *lines),
                     flags=["test"], cost=NodeCost(5, 20, 2))


def path_only_test_node(ident, path="tests/test_x.py", lines=(1, 2)):
    return GraphNode(ident, ident, "symbol", "symbol", kind="function", span=SourceSpan(path, *lines),
                     cost=NodeCost(5, 20, 2))


def test_V2_R7_flagged_source_on_non_test_path_is_cloned():
    files = {PROD_PATH: "def t():\n    return p()\n", "src/bar.py": "def p():\n    return 1\n"}
    nodes = [flag_only_test_node("t"), prod("p", "src/bar.py")]
    architecture = enriched(nodes, [call("t", "p", Confidence.STATIC_INFERRED, Resolution.UNIQUE_NAME, path=PROD_PATH)], files)
    assert [view(e) for e in relation_edges_of_tests(architecture)] == [
        ("t", "p", "static_inferred", "unique_name", SourceSpan(PROD_PATH, 2, 2), []),
    ]


def test_V2_R8_unflagged_source_on_test_path_is_cloned():
    files = {PROD_PATH: "def p():\n    return 1\n", "tests/test_x.py": "def t():\n    return p()\n"}
    nodes = [prod("p"), path_only_test_node("t")]
    architecture = enriched(nodes, [call("t", "p", Confidence.FRAMEWORK_INFERRED, Resolution.EXACT, path="tests/test_x.py")], files)
    assert [view(e) for e in relation_edges_of_tests(architecture)] == [
        ("t", "p", "framework_inferred", "exact", SourceSpan("tests/test_x.py", 2, 2), []),
    ]


@pytest.mark.parametrize("relation", [RelationKind.IMPORTS, RelationKind.READS])
def test_V2_R9_non_call_relations_are_cloned_with_original_attributes(relation):
    original = call("t", "p", Confidence.DYNAMIC_REQUIRED, Resolution.UNIQUE_NAME, line=3, relation=relation)
    architecture = enriched([prod("p"), make_test_node("t")], [original], FOO_FILES)
    assert [view(e) for e in relation_edges_of_tests(architecture)] == [
        ("t", "p", "dynamic_required", "unique_name", SourceSpan(TEST_PATH, 3, 3), []),
    ]
    assert original.relation == relation


@pytest.mark.parametrize("variant", ["relation", "evidence"])
@pytest.mark.parametrize("first_is_certain", [True, False])
def test_V2_R10_originals_sharing_source_target_resolution_candidates_yield_one_tests_edge(variant, first_is_certain):
    certain = (Confidence.STATIC_CERTAIN, 2)
    inferred = (Confidence.FRAMEWORK_INFERRED, 3)
    (first_confidence, first_line), (second_confidence, second_line) = (certain, inferred) if first_is_certain else (inferred, certain)
    first = call("t", "p", first_confidence, Resolution.UNIQUE_NAME, line=first_line)
    second_relation = RelationKind.IMPORTS if variant == "relation" else RelationKind.CALLS
    second_line = first_line if variant == "relation" else second_line
    second = call("t", "p", second_confidence, Resolution.UNIQUE_NAME, line=second_line, relation=second_relation)
    architecture = enriched([prod("p"), make_test_node("t")], [first, second], FOO_FILES)
    assert [view(e) for e in relation_edges_of_tests(architecture)] == [
        ("t", "p", str(first_confidence), "unique_name", SourceSpan(TEST_PATH, first_line, first_line), []),
    ]


def test_V2_R11_flagged_target_on_non_test_path_is_a_test_target():
    files = {**FOO_FILES, "src/helper.py": "def h():\n    return 1\n"}
    nodes = [make_test_node("t"), flag_only_test_node("h", "src/helper.py")]
    architecture = enriched(nodes, [call("t", "h")], files)
    assert relation_edges_of_tests(architecture) == []


# ---- V3: configuration edges -----------------------------------------------------------------------------------

CONSUMER_PATH = "src/app.py"
CONSUMER_TEXT = 'def consume():\n    first = "{key}"\n    second = "{key}"\n    return first, second\n'
CONFIG_CASES = {
    "K1-env": (".env", "API_KEY=value\nOTHER=1\n", "API_KEY", 1),
    "K2-json": ("settings.json", '{\n  "API_KEY": "value"\n}\n', "API_KEY", 2),
    "K3-yaml": ("settings.yaml", "api:\n  API_KEY: value\n", "API_KEY", 2),
    "K4-gradle": ("build.gradle.kts", 'android {\n  buildConfigField("String", "API_KEY", "\\"value\\"")\n}\n', "API_KEY", 2),
}


def configured(path, text, key):
    files = {CONSUMER_PATH: CONSUMER_TEXT.format(key=key), path: text}
    consumer = GraphNode("consumer", "consume", "symbol", "symbol", kind="function", span=SourceSpan(CONSUMER_PATH, 1, 4))
    return enriched([consumer], [], files)


@pytest.mark.parametrize("case", list(CONFIG_CASES))
def test_V3_K1_to_K4_configures_edge_attributes_evidence_and_metadata(case):
    path, text, key, config_line = CONFIG_CASES[case]
    architecture = configured(path, text, key)
    configuration = [node for node in architecture.nodes if node.kind == "configuration"]
    node = next(item for item in configuration if item.label == key)
    assert node.metadata["occurrence_lines"] == [config_line]
    edges = config_edges(architecture)
    assert len(edges) == 1
    edge = edges[0]
    assert (edge.from_id, edge.to_id) == (node.id, "consumer")
    assert str(edge.confidence) == "static_inferred"
    assert str(edge.resolution) == "exact"
    assert edge.evidence == SourceSpan(CONSUMER_PATH, 2, 2)
    assert edge.metadata["occurrence_lines"] == [2, 3]
    assert list(edge.candidates) == []


def test_V3_K1_key_without_code_literal_creates_no_configures_edge():
    path, text, key, _ = CONFIG_CASES["K1-env"]
    files = {CONSUMER_PATH: "def consume():\n    return 1\n", path: text}
    consumer = GraphNode("consumer", "consume", "symbol", "symbol", kind="function", span=SourceSpan(CONSUMER_PATH, 1, 2))
    assert config_edges(enriched([consumer], [], files)) == []


def weighted_fan_out_of_config(architecture, weights):
    nodes = copy.deepcopy(architecture.nodes)
    for item in nodes:
        item.cost = NodeCost(5, 20, 1)
    report = GraphAnalyzer(GraphAnalysisConfig(edge_weights=weights)).analyze(nodes, copy.deepcopy(architecture.edges))
    config_id = next(item.id for item in architecture.nodes if item.kind == "configuration")
    return report["node_metrics"][config_id]


def test_V3_K5_default_weights_apply_the_static_inferred_confidence_weight():
    weights = load_edge_weights(default_edge_weights_path())
    architecture = configured(*CONFIG_CASES["K1-env"][:3])
    row = weighted_fan_out_of_config(architecture, weights)
    assert weights.confidence["static_inferred"] == pytest.approx(0.3)
    assert weights.confidence["static_certain"] == pytest.approx(1.0)
    assert row["fan_out"] == 1
    assert row["weighted_fan_out"] == pytest.approx(0.3, abs=1e-12, rel=0)


def test_V3_K5_custom_confidence_weight_is_the_one_that_scales_the_edge(tmp_path):
    weights = load_weights(tmp_path, weights_data(confidence={"static_inferred": 0.55, "static_certain": 0.9}))
    architecture = configured(*CONFIG_CASES["K3-yaml"][:3])
    row = weighted_fan_out_of_config(architecture, weights)
    assert row["weighted_fan_out"] == pytest.approx(0.55, abs=1e-12, rel=0)


# ---- V10: error guessing ---------------------------------------------------------------------------------------


def test_V10_G1_clones_keep_each_original_confidence_and_resolution():
    files = {**FOO_FILES, "src/bar.py": "def bar():\n    return 1\n"}
    nodes = [prod("p"), prod("q", "src/bar.py"), make_test_node("t")]
    originals = [
        call("t", "p", Confidence.STATIC_CERTAIN, Resolution.EXACT, line=2),
        call("t", "q", Confidence.DYNAMIC_REQUIRED, Resolution.UNIQUE_NAME, line=3),
    ]
    architecture = enriched(nodes, originals, files)
    assert sorted(view(edge) for edge in relation_edges_of_tests(architecture)) == sorted([
        ("t", "p", "static_certain", "exact", SourceSpan(TEST_PATH, 2, 2), []),
        ("t", "q", "dynamic_required", "unique_name", SourceSpan(TEST_PATH, 3, 3), []),
    ])


def test_V10_G2_configures_confidence_does_not_leak_into_tests_or_other_relations():
    files = {
        **FOO_FILES,
        ".env": "API_KEY=1\n",
        "src/app.py": 'def consume():\n    return "API_KEY"\n',
    }
    nodes = [
        prod("p"), make_test_node("t"),
        GraphNode("consumer", "consume", "symbol", "symbol", kind="function", span=SourceSpan("src/app.py", 1, 2)),
    ]
    other = [
        call("t", "p", Confidence.STATIC_CERTAIN, Resolution.EXACT),
        call("consumer", "p", Confidence.STATIC_CERTAIN, Resolution.EXACT, path="src/app.py", relation=RelationKind.IMPORTS),
    ]
    before = copy.deepcopy(other)
    architecture = enriched(nodes, other, files)
    assert architecture.edges[:2] == before
    assert [str(e.confidence) for e in relation_edges_of_tests(architecture)] == ["static_certain"]
    assert [str(e.confidence) for e in config_edges(architecture)] == ["static_inferred"]
    others = [e for e in architecture.edges if e.relation not in (RelationKind.TESTS, RelationKind.CONFIGURES)]
    assert {str(e.confidence) for e in others} == {"static_certain"}
