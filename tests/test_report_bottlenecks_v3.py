"""V8 (F15) for spec 8fd668e309160b58 v1: report/bottlenecks renders bottlenecks.v3 only.

Technique: equivalence partitioning over {valid v3, v2 input, absence of probes/exploration
sections}. Payloads come from the real analyze_bottlenecks -> JSON path so the renderer sees
the F12 shape; the v2 payloads are hand-written.
"""
import copy
import json
import re

import pytest

from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
from language_analyzers.core.graph_models import Confidence, SourceSpan
from report.bottlenecks import render_report
from report.shared.document import ReportInputError
from tests.edge_weights_support import edge, load_weights, weights_data
from tests.test_bottlenecks_v3 import network_subject


def v3_payload(directory, large_threshold=1):
    weights = load_weights(directory, weights_data(large_node_line_threshold=large_threshold))
    snapshot, architecture = network_subject(
        ["wide", "callee"],
        [edge("wide", "callee", Confidence.DYNAMIC_REQUIRED)],
        spans={"wide": SourceSpan("a.py", 1, 5)},
    )
    return json.loads(bottlenecks_to_json(analyze_bottlenecks(snapshot, architecture, weights)))


def test_V8_valid_v3_payload_renders_a_document(tmp_path):
    payload = v3_payload(tmp_path)
    assert {item["kind"] for item in payload["candidates"]} >= {"large_node", "unresolved_boundary"}
    document = render_report(payload)
    assert isinstance(document, str) and "<html" in document.lower()


def test_V8_rendering_depends_on_the_payload(tmp_path):
    with_candidates = v3_payload(tmp_path)
    without_candidates = copy.deepcopy(with_candidates)
    without_candidates["candidates"] = []
    assert render_report(with_candidates) != render_report(without_candidates)


def test_V8_empty_candidates_still_render(tmp_path):
    payload = v3_payload(tmp_path)
    payload["candidates"] = []
    assert render_report(payload)


@pytest.mark.parametrize("label", ["schema-only", "full-v2-shape", "v3-body-with-v2-schema"])
def test_V8_v2_input_is_a_validation_error(tmp_path, label):
    if label == "schema-only":
        payload = {"schema": "bottlenecks.v2"}
    elif label == "full-v2-shape":
        payload = {
            "schema": "bottlenecks.v2", "snapshot": {}, "profile": {}, "versions": {}, "coverage": {},
            "dependency_network": {}, "exploration_network": {}, "probes": [], "candidates": [], "limitations": [],
        }
    else:
        payload = v3_payload(tmp_path)
        payload["schema"] = "bottlenecks.v2"
    with pytest.raises(ReportInputError):
        render_report(payload)


def test_V8_rendered_document_has_no_probe_or_exploration_sections(tmp_path):
    document = render_report(v3_payload(tmp_path)).lower()
    assert "probe" not in document
    assert "exploration" not in document
    assert re.search(r"""id=['"](probes?|exploration[^'"]*)['"]""", document) is None


def _drop(payload, key):
    del payload[key]


def _add_extra(payload):
    payload["probes"] = []


def _candidates_not_list(payload):
    payload["candidates"] = {}


def _candidate_metric_non_numeric(payload):
    next(item for item in payload["candidates"] if item["kind"] == "large_node")["metrics"]["line_count"] = "many"


def _ranking_value_non_numeric(payload):
    payload["dependency_network"]["rankings"]["fan_in"][0]["value"] = "many"


MALFORMED = {
    "missing-top-level-key": lambda payload: _drop(payload, "versions"),
    "extra-top-level-key": _add_extra,
    "missing-edge-weights": lambda payload: _drop(payload, "edge_weights"),
    "candidates-not-a-list": _candidates_not_list,
    "candidate-metric-non-numeric": _candidate_metric_non_numeric,
    "ranking-value-non-numeric": _ranking_value_non_numeric,
}


@pytest.mark.parametrize("case", list(MALFORMED))
def test_V8_F15_malformed_v3_payload_is_a_validation_error(tmp_path, case):
    """render_report returns text and writes no file, so the observable is the typed error."""
    payload = v3_payload(tmp_path)
    MALFORMED[case](payload)
    before = sorted(path.name for path in tmp_path.iterdir())
    with pytest.raises(ReportInputError):
        render_report(payload)
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_V8_advisory_rendered_document_contains_v3_values(tmp_path):
    payload = v3_payload(tmp_path)
    document = render_report(payload)
    assert "wide" in document
    assert payload["edge_weights"]["content_hash"] in document
