import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from language_analyzers.core.graph_models import (
    Confidence,
    GraphEdge,
    GraphNode,
    NodeCost,
    Resolution,
    SourceSpan,
)
from language_analyzers.core.report_schema import ColumnSpec, ReportCollection
from language_analyzers.core.serialization import SCHEMA_VERSION, architecture_to_dict
from renderers.html import HTMLRenderer


def sample_architecture():
    node = GraphNode(
        id="py:mod#run",
        label="run",
        group="function",
        category="function",
        kind="function",
        language="python",
        span=SourceSpan("mod.py", 3, 8),
        cost=NodeCost(token_estimate=42, char_count=168, line_count=6),
        signature="def run(value: int) -> int",
        docstring="Runs.",
        exported=True,
        symbol_path="mod.run",
        flags=["dynamic_attr"],
        provenance="python-core",
        metadata={"module": "mod"},
    )
    other = GraphNode(id="py:mod#helper", label="helper", group="function", category="function")
    edge = GraphEdge(
        from_id="py:mod#run",
        to_id="py:mod#helper",
        relation="CALLS",
        confidence=Confidence.STATIC_INFERRED,
        resolution=Resolution.AMBIGUOUS,
        evidence=SourceSpan("mod.py", 5, 5),
        candidates=["py:other#helper"],
        weight=3.0,
    )
    collection = ReportCollection(
        key="symbols",
        label="Symbols",
        columns=[ColumnSpec("symbol_path", "Symbol", "mono")],
        rows=[{"id": node.id, "symbol_path": "mod.run"}],
    )
    return SimpleNamespace(
        project_name="sample",
        project_path="/project",
        stats={"total_symbols": 2},
        nodes=[node, other],
        edges=[edge],
        report_collections=[collection],
    )


class TestSerialization(unittest.TestCase):
    def test_typed_node_fields_reach_the_neutral_schema(self):
        payload = architecture_to_dict(sample_architecture())
        node = payload["nodes"][0]

        self.assertEqual(SCHEMA_VERSION, "5")
        self.assertEqual(payload["schema_version"], "5")
        self.assertEqual(node["display_label"], "")
        self.assertNotIn("evaluation_relations", payload)
        self.assertEqual(node["span"], {
            "file_path": "mod.py", "start_line": 3, "end_line": 8, "start_col": 0, "end_col": 0,
        })
        self.assertEqual(node["cost"]["token_estimate"], 42)
        self.assertEqual(node["signature"], "def run(value: int) -> int")
        self.assertEqual(node["flags"], ["dynamic_attr"])
        self.assertEqual(node["provenance"], "python-core")
        self.assertTrue(node["exported"])

    def test_typed_edge_fields_reach_the_neutral_schema(self):
        edge = architecture_to_dict(sample_architecture())["edges"][0]

        self.assertEqual(edge["from_id"], "py:mod#run")
        self.assertEqual(edge["confidence"], "static_inferred")
        self.assertEqual(edge["resolution"], "ambiguous")
        self.assertEqual(edge["evidence"]["start_line"], 5)
        self.assertEqual(edge["candidates"], ["py:other#helper"])
        self.assertEqual(edge["weight"], 3.0)

    def test_confidence_is_serialized_as_a_plain_string(self):
        payload = json.loads(json.dumps(architecture_to_dict(sample_architecture()), default=str))

        self.assertIsInstance(payload["edges"][0]["confidence"], str)
        self.assertEqual(payload["edges"][0]["confidence"], "static_inferred")

    def test_nodes_without_the_new_fields_still_serialize(self):
        architecture = sample_architecture()
        architecture.nodes = [SimpleNamespace(id="a", label="A", category="thing", metadata={})]

        node = architecture_to_dict(architecture)["nodes"][0]

        self.assertIsNone(node["span"])
        self.assertIsNone(node["cost"])
        self.assertEqual(node["flags"], [])
        self.assertEqual(node["kind"], "thing")

    def test_legacy_evaluation_relations_are_not_serialized(self):
        architecture = sample_architecture()
        architecture.evaluation_relations = [{"cost": 4.0}]

        self.assertNotIn("evaluation_relations", architecture_to_dict(architecture))

    def test_mapping_edges_are_normalized_to_from_id_and_to_id(self):
        architecture = sample_architecture()
        architecture.edges = [{"from": "a", "to": "b", "relation": "CALLS"}]

        edge = architecture_to_dict(architecture)["edges"][0]

        self.assertEqual((edge["from_id"], edge["to_id"]), ("a", "b"))
        self.assertNotIn("from", edge)


class TestRendering(unittest.TestCase):
    def test_inline_report_preserves_neutral_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.html"
            HTMLRenderer(title="Sample").render(sample_architecture(), str(output))
            document = output.read_text(encoding="utf-8")
            match = re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>', document, re.DOTALL)
            self.assertIsNotNone(match)
            payload = json.loads(match.group(1))
            self.assertEqual(payload["architecture"], architecture_to_dict(sample_architecture()))
            self.assertIsNone(payload["bottlenecks"])
            self.assertFalse((output.parent / "report_assets").exists())
            self.assertIn("<style", document)
            self.assertIn('id="report-summary"', document)


if __name__ == "__main__":
    unittest.main()
