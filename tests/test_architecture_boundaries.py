import ast
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from analysis import GraphAnalyzer
from renderers.html import HTMLRenderer


@dataclass
class GenericNode:
    id: str
    label: str
    group: str = "symbol"
    category: str = "symbol"
    title: str = ""
    shape: str = "box"
    size: int = 25
    color: dict | None = None
    metadata: dict = field(default_factory=dict)


class TestArchitectureBoundaries(unittest.TestCase):
    def test_old_framework_package_directory_is_gone(self):
        root = Path(__file__).resolve().parents[1]
        self.assertFalse((root / "fastapi_visualizer").exists())

    def test_generic_layers_do_not_import_framework_analyzers(self):
        root = Path(__file__).resolve().parents[1]
        for package in (root / "analysis", root / "renderers"):
            for source_path in package.rglob("*.py"):
                tree = ast.parse(source_path.read_text(encoding="utf-8"))
                imported = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imported.append(node.module)
                self.assertFalse(
                    any(name == "framework_analyzers" or name.startswith("framework_analyzers.") for name in imported),
                    source_path,
                )

    def test_language_analyzers_do_not_import_framework_analyzers(self):
        root = Path(__file__).resolve().parents[1]
        for source_path in (root / "language_analyzers").rglob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
            self.assertFalse(
                any(name == "framework_analyzers" or name.startswith("framework_analyzers.") for name in imported),
                source_path,
            )

    def test_agent_view_does_not_import_framework_analyzers(self):
        root = Path(__file__).resolve().parents[1]
        for source_path in (root / "agent_view").rglob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
            self.assertFalse(
                any(name == "framework_analyzers" or name.startswith("framework_analyzers.") for name in imported),
                source_path,
            )

    def test_framework_analyzers_do_not_cross_import(self):
        root = Path(__file__).resolve().parents[1]
        pairs = (
            (root / "framework_analyzers" / "android", "framework_analyzers.fastapi"),
            (root / "framework_analyzers" / "fastapi", "framework_analyzers.android"),
        )
        for package, forbidden in pairs:
            for source_path in package.rglob("*.py"):
                tree = ast.parse(source_path.read_text(encoding="utf-8"))
                imported = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imported.append(node.module)
                self.assertFalse(
                    any(name == forbidden or name.startswith(forbidden + ".") for name in imported),
                    source_path,
                )

    def test_analysis_accepts_framework_neutral_nodes_and_mapping_edges(self):
        nodes = [GenericNode("a", "A"), GenericNode("b", "B"), GenericNode("c", "C")]
        edges = [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]

        metrics = GraphAnalyzer().analyze(nodes, edges)["node_metrics"]

        expected = {
            "pagerank",
            "hub_score",
            "authority_score",
            "degree_centrality",
            "betweenness_centrality",
            "token_cost",
            "weighted_centrality_cost",
            "hop_2_token_cost",
            "hop_3_token_cost",
        }
        self.assertTrue(expected.issubset(metrics["a"]))
        self.assertGreater(metrics["a"]["hub_score"], metrics["c"]["hub_score"])
        self.assertGreater(metrics["c"]["authority_score"], metrics["a"]["authority_score"])
        self.assertGreater(metrics["b"]["degree_centrality"], metrics["a"]["degree_centrality"])
        self.assertEqual(
            metrics["a"]["weighted_centrality_cost"],
            metrics["a"]["pagerank"] * metrics["a"]["token_cost"],
        )
        self.assertEqual(metrics["a"]["hop_2_token_cost"], metrics["b"]["token_cost"] + metrics["c"]["token_cost"])
        self.assertEqual(metrics["a"]["hop_3_token_cost"], metrics["a"]["hop_2_token_cost"])

    def test_renderer_writes_and_references_sibling_assets(self):
        node = GenericNode("a", "A")
        arch = SimpleNamespace(
            project_name="generic",
            project_path="/project",
            stats={},
            nodes=[node],
            edges=[],
            report_collections=[],
        )
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.html"
            HTMLRenderer(title="Generic report").render(arch, str(report))

            document = report.read_text(encoding="utf-8")
            for asset in ("styles.css", "tailwind-config.js", "app.js"):
                self.assertTrue((report.parent / "report_assets" / asset).is_file())
                self.assertIn(f'report_assets/{asset}', document)
            self.assertNotIn("<style", document)
            self.assertNotIn("function initNetwork", document)
            self.assertIn(
                "function initNetwork",
                (report.parent / "report_assets" / "app.js").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
