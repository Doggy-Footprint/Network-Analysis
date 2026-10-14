"""Archived tests for the disk and ast token-cost fallback moved out of analysis/graph_metrics.py (spec f7564b09cf80bdd9, V7/T4).

Not collected by pytest (testpaths = tests). The fallback module is loaded by file path because
archive/ is not an importable package; the cases below are the original tests/test_graph_metrics.py
cases that depended on metadata file_path/line_number/end_line_number reads.
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

from framework_analyzers.fastapi.models import GraphNode

_FALLBACK = Path(__file__).resolve().parents[1] / "token_cost_disk_fallback" / "graph_metrics_fallback.py"
_spec = importlib.util.spec_from_file_location("graph_metrics_fallback", _FALLBACK)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
GraphAnalyzer = _module.GraphAnalyzer
GraphAnalysisConfig = _module.GraphAnalysisConfig


class TestGraphAnalyzerDiskFallback(unittest.TestCase):
    def test_source_ranges_are_inclusive_and_relative_to_project_path(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.txt"
            source.write_text("first\nsecond\nthird\n", encoding="utf-8")
            node = GraphNode(
                id="range",
                label="range",
                group="symbol",
                category="symbol",
                metadata={"file_path": "sample.txt", "line_number": 2, "end_line_number": 3},
            )

            metrics = GraphAnalyzer(GraphAnalysisConfig(characters_per_token=4)).analyze([node], [], directory)["node_metrics"]

            self.assertEqual(metrics["range"]["token_cost"], 3)

    def test_end_line_number_takes_precedence_over_ast_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.py"
            source.write_text(
                "def first():\n    return 1\n\ndef second():\n    return first()\n\ndef third():\n    return second()\n",
                encoding="utf-8",
            )
            explicit_range_node = GraphNode(
                id="third_line_only",
                label="third_line_only",
                group="symbol",
                category="symbol",
                metadata={"file_path": str(source), "line_number": 8, "end_line_number": 8},
            )
            ast_fallback_node = GraphNode(
                id="third_whole_function",
                label="third_whole_function",
                group="symbol",
                category="symbol",
                metadata={"file_path": str(source), "line_number": 8},
            )

            report = GraphAnalyzer().analyze([explicit_range_node, ast_fallback_node], [], directory)
            metrics = report["node_metrics"]

            # Line 8 alone ("    return second()", 19 chars) -> ceil(19/4) = 5 tokens.
            self.assertEqual(metrics["third_line_only"]["token_cost"], 5)
            # Without end_line_number, line 8 falls inside the enclosing "third" FunctionDef
            # (lines 7-8, "def third():\n    return second()", 32 chars) -> ceil(32/4) = 8 tokens.
            self.assertEqual(metrics["third_whole_function"]["token_cost"], 8)
            self.assertNotEqual(
                metrics["third_line_only"]["token_cost"],
                metrics["third_whole_function"]["token_cost"],
            )


if __name__ == "__main__":
    unittest.main()
