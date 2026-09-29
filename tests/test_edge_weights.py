"""V1 (F5, C1, C6, C8) and the weight_for slice of V2 (F6, C4) for spec
8fd668e309160b58 v1.

V1: boundary value (2-value) + equivalence partitioning over
{weight 0, smallest positive, 1.0, above 1.0, negative, bool, str}, {threshold 0, 1},
{key missing, key extra}, enum value missing, missing file, YAML error. F5 states the
weight rule for confidence and resolution "각각", so the weight items run on both groups.
V2 (weight_for): decision table, each choice of confidence (4) and resolution (4)
at least once; expected values are min(confidence, resolution) hand-read from the
tables in the test.
"""
import hashlib

import pytest

from analysis.edge_weights import EdgeWeights, EdgeWeightsError, default_edge_weights_path, load_edge_weights
from language_analyzers.core.graph_models import Confidence, GraphEdge, Resolution
from tests.edge_weights_support import (
    CONFIDENCE_KEYS,
    DEFAULT_WEIGHTS,
    RESOLUTION_KEYS,
    ROOT,
    edge,
    load_weights,
    weights_data,
    write_weights,
)

SMALLEST_POSITIVE = 5e-324


def test_V1_error_type_is_a_value_error():
    assert issubclass(EdgeWeightsError, ValueError)


def test_V1_C1_default_file_loads_the_declared_values():
    path = default_edge_weights_path()
    assert path == ROOT / "profiles" / "edge_weights.v1.yaml"
    weights = load_edge_weights(path)
    assert isinstance(weights, EdgeWeights)
    assert weights.id == "edge_weights"
    assert weights.version == 1
    assert dict(weights.confidence) == DEFAULT_WEIGHTS["confidence"]
    assert dict(weights.resolution) == DEFAULT_WEIGHTS["resolution"]
    assert weights.large_node_line_threshold == 2000
    assert weights.content_hash == hashlib.sha256(path.read_bytes()).hexdigest()


def test_V1_C1_content_hash_is_sha256_of_file_bytes_and_accepts_str_path(tmp_path):
    path = write_weights(tmp_path, weights_data(), "a.yaml")
    path.write_bytes(path.read_bytes() + b"# trailing comment changes the hash\n")
    weights = load_edge_weights(str(path))
    assert weights.content_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(weights.content_hash) == 64


@pytest.mark.parametrize("group", ["confidence", "resolution"])
@pytest.mark.parametrize(
    ("label", "value", "accepted"),
    [
        ("zero", 0.0, False),
        ("smallest-positive", SMALLEST_POSITIVE, True),
        ("one", 1.0, True),
        ("above-one", 1.0000001, False),
        ("negative", -0.5, False),
        ("bool", True, False),
        ("string", "0.5", False),
    ],
)
def test_V1_C6_weight_value_boundaries(tmp_path, group, label, value, accepted):
    key = (CONFIDENCE_KEYS if group == "confidence" else RESOLUTION_KEYS)[1]
    data = weights_data(**{group: {key: value}})
    if accepted:
        weights = load_weights(tmp_path, data)
        assert getattr(weights, group)[key] == value
    else:
        with pytest.raises(EdgeWeightsError):
            load_weights(tmp_path, data)


@pytest.mark.parametrize("group", ["confidence", "resolution"])
def test_V1_A6_integer_weight_one_is_accepted_as_float_and_integer_zero_is_rejected(tmp_path, group):
    key = (CONFIDENCE_KEYS if group == "confidence" else RESOLUTION_KEYS)[1]
    weights = load_weights(tmp_path, weights_data(**{group: {key: 1}}))
    assert getattr(weights, group)[key] == 1.0
    assert isinstance(getattr(weights, group)[key], float)
    with pytest.raises(EdgeWeightsError):
        load_weights(tmp_path, weights_data(**{group: {key: 0}}))


@pytest.mark.parametrize(("threshold", "accepted"), [(0, False), (1, True)])
def test_V1_C6_threshold_boundaries(tmp_path, threshold, accepted):
    data = weights_data(large_node_line_threshold=threshold)
    if accepted:
        assert load_weights(tmp_path, data).large_node_line_threshold == threshold
    else:
        with pytest.raises(EdgeWeightsError):
            load_weights(tmp_path, data)


@pytest.mark.parametrize("missing", ["id", "version", "confidence", "resolution", "large_node_line_threshold"])
def test_V1_C8_missing_top_level_key_is_rejected(tmp_path, missing):
    data = weights_data()
    del data[missing]
    with pytest.raises(EdgeWeightsError):
        load_weights(tmp_path, data)


def test_V1_C8_extra_top_level_key_is_rejected(tmp_path):
    with pytest.raises(EdgeWeightsError):
        load_weights(tmp_path, weights_data(extra_key=1))


@pytest.mark.parametrize(
    ("group", "key"),
    [("confidence", key) for key in CONFIDENCE_KEYS] + [("resolution", key) for key in RESOLUTION_KEYS],
)
def test_V1_C8_missing_enum_value_is_rejected(tmp_path, group, key):
    data = weights_data()
    del data[group][key]
    with pytest.raises(EdgeWeightsError):
        load_weights(tmp_path, data)


def test_V1_C8_missing_file_is_rejected(tmp_path):
    with pytest.raises(EdgeWeightsError):
        load_edge_weights(tmp_path / "absent.yaml")


def test_V1_C8_invalid_yaml_is_rejected(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("id: [unclosed\nconfidence: {a: : :\n", encoding="utf-8")
    with pytest.raises(EdgeWeightsError):
        load_edge_weights(path)


def test_V1_rejection_message_is_not_empty(tmp_path):
    with pytest.raises(EdgeWeightsError) as raised:
        load_edge_weights(tmp_path / "absent.yaml")
    assert str(raised.value).strip()


@pytest.mark.parametrize(
    ("label", "confidence", "resolution", "expected"),
    [
        ("certain-exact", Confidence.STATIC_CERTAIN, Resolution.EXACT, 1.0),
        ("inferred-unique_name", Confidence.STATIC_INFERRED, Resolution.UNIQUE_NAME, 0.3),
        ("framework-ambiguous", Confidence.FRAMEWORK_INFERRED, Resolution.AMBIGUOUS, 0.3),
        ("dynamic-unresolved", Confidence.DYNAMIC_REQUIRED, Resolution.UNRESOLVED, 0.3),
        ("C4-certain-with-ambiguous", Confidence.STATIC_CERTAIN, Resolution.AMBIGUOUS, 0.3),
    ],
)
def test_V2_C4_default_weights_follow_the_declared_table(label, confidence, resolution, expected):
    weights = load_edge_weights(default_edge_weights_path())
    assert weights.weight_for(edge("a", "b", confidence, resolution)) == expected


def test_V2_min_rule_is_taken_over_distinct_values_in_both_directions(tmp_path):
    weights = load_weights(
        tmp_path,
        weights_data(
            confidence={"static_certain": 0.9, "static_inferred": 0.8, "framework_inferred": 0.7, "dynamic_required": 0.6},
            resolution={"exact": 0.95, "unique_name": 0.85, "ambiguous": 0.75, "unresolved": 0.65},
        ),
    )
    cases = [
        (Confidence.STATIC_CERTAIN, Resolution.UNIQUE_NAME, 0.85),
        (Confidence.STATIC_INFERRED, Resolution.UNRESOLVED, 0.65),
        (Confidence.FRAMEWORK_INFERRED, Resolution.EXACT, 0.7),
        (Confidence.DYNAMIC_REQUIRED, Resolution.AMBIGUOUS, 0.6),
    ]
    for confidence, resolution, expected in cases:
        assert weights.weight_for(edge("a", "b", confidence, resolution)) == expected, (confidence, resolution)


@pytest.mark.parametrize("stored_weight", [0.01, 5.0])
def test_V2_F6_graph_edge_weight_field_is_ignored(stored_weight):
    weights = load_edge_weights(default_edge_weights_path())
    assert weights.weight_for(edge("a", "b", weight=stored_weight)) == 1.0
    inferred = edge("a", "b", Confidence.FRAMEWORK_INFERRED, weight=stored_weight)
    assert weights.weight_for(inferred) == 0.3


def test_V2_weight_for_accepts_plain_string_enum_values():
    weights = load_edge_weights(default_edge_weights_path())
    plain = GraphEdge("a", "b", "CALLS", confidence="dynamic_required", resolution="exact")
    assert weights.weight_for(plain) == 0.3


@pytest.mark.parametrize(("label", "version"), [("zero", 0), ("bool", True), ("float", 1.5), ("string", "1")])
def test_V1_F5_invalid_version_is_rejected(tmp_path, label, version):
    with pytest.raises(EdgeWeightsError):
        load_weights(tmp_path, weights_data(version=version))


@pytest.mark.parametrize("version", [1, 2])
def test_V1_F5_version_one_and_two_are_accepted(tmp_path, version):
    assert load_weights(tmp_path, weights_data(version=version)).version == version


@pytest.mark.parametrize(("label", "threshold"), [("bool", True), ("float", 1.5)])
def test_V1_F5_non_integer_threshold_is_rejected(tmp_path, label, threshold):
    with pytest.raises(EdgeWeightsError):
        load_weights(tmp_path, weights_data(large_node_line_threshold=threshold))


@pytest.mark.parametrize(("label", "text"), [("list", "- a\n- b\n"), ("scalar", "5\n")])
def test_V1_F5_root_that_is_not_a_mapping_is_rejected(tmp_path, label, text):
    path = tmp_path / "root.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(EdgeWeightsError):
        load_edge_weights(path)


@pytest.mark.parametrize("group", ["confidence", "resolution"])
@pytest.mark.parametrize("value", [[1.0, 1.0], "x"], ids=["list", "string"])
def test_V1_F5_group_that_is_not_a_mapping_is_rejected(tmp_path, group, value):
    data = weights_data()
    data[group] = value
    with pytest.raises(EdgeWeightsError):
        load_weights(tmp_path, data)


@pytest.mark.parametrize(("label", "identifier"), [("empty", ""), ("integer", 5)])
def test_V1_F5_invalid_id_is_rejected(tmp_path, label, identifier):
    with pytest.raises(EdgeWeightsError):
        load_weights(tmp_path, weights_data(id=identifier))
