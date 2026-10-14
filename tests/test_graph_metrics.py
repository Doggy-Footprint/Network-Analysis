import tempfile
import unittest
from pathlib import Path

from analysis import GraphAnalyzer
from analysis.graph_metrics import GraphAnalysisConfig
from framework_analyzers.fastapi.models import GraphEdge, GraphNode


class TestGraphAnalyzer(unittest.TestCase):
    def test_centrality_and_hop_costs(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.py"
            source.write_text(
                "def first():\n    return 1\n\ndef second():\n    return first()\n\ndef third():\n    return second()\n",
                encoding="utf-8",
            )
            nodes = [
                GraphNode(
                    id=node_id,
                    label=node_id,
                    group="symbol",
                    category="symbol",
                    metadata={"file_path": str(source), "line_number": line},
                )
                for node_id, line in (("first", 1), ("second", 4), ("third", 7))
            ]
            edges = [
                GraphEdge(from_id="first", to_id="second", relation="CALLS"),
                GraphEdge(from_id="second", to_id="third", relation="CALLS"),
            ]

            report = GraphAnalyzer().analyze(nodes, edges, directory)
            metrics = report["node_metrics"]

            self.assertGreater(metrics["third"]["pagerank"], metrics["second"]["pagerank"])
            self.assertGreater(metrics["second"]["betweenness_centrality"], 0)
            self.assertAlmostEqual(
                metrics["first"]["hop_2_token_cost"],
                metrics["second"]["effective_token_cost"] + metrics["third"]["effective_token_cost"],
            )
            self.assertGreater(metrics["first"]["token_cost"], 0)
            self.assertEqual(nodes[0].metadata["analysis"], metrics["first"])

    def test_empty_graph(self):
        report = GraphAnalyzer().analyze([], [])

        self.assertEqual(report["node_metrics"], {})
        self.assertEqual(report["total_token_cost"], 0)

    def test_single_isolated_node_has_stable_zero_connectivity_metrics(self):
        node = GraphNode(id="only", label="only", group="symbol", category="symbol")

        report = GraphAnalyzer().analyze([node], [])

        metrics = report["node_metrics"]["only"]
        self.assertEqual(metrics["pagerank"], 1.0)
        self.assertEqual(metrics["betweenness_centrality"], 0.0)
        self.assertEqual(metrics["fan_in"], 0)
        self.assertEqual(metrics["fan_out"], 0)
        self.assertEqual(metrics["hop_2_token_cost"], 0)

    def test_ignores_self_duplicate_and_unknown_edges_without_reversing_direction(self):
        nodes = [
            GraphNode(id=node_id, label=node_id, group="symbol", category="symbol")
            for node_id in ("source", "target", "isolated")
        ]
        edges = [
            {"from": "source", "to": "target"},
            {"from": "source", "to": "target"},
            {"from": "source", "to": "source"},
            {"from": "unknown", "to": "target"},
            {"from": "source", "to": "unknown"},
        ]

        report = GraphAnalyzer().analyze(nodes, edges)

        source = report["node_metrics"]["source"]
        target = report["node_metrics"]["target"]
        isolated = report["node_metrics"]["isolated"]
        self.assertEqual((source["fan_in"], source["fan_out"]), (0, 1))
        self.assertEqual((target["fan_in"], target["fan_out"]), (1, 0))
        self.assertEqual((isolated["fan_in"], isolated["fan_out"]), (0, 0))
        self.assertEqual(source["hop_2_token_cost"], target["effective_token_cost"])

    def test_hop_limits_include_exact_boundary_and_exclude_next_node(self):
        nodes = [
            GraphNode(id=str(index), label=str(index), group="symbol", category="symbol")
            for index in range(5)
        ]
        edges = [GraphEdge(from_id=str(index), to_id=str(index + 1), relation="CALLS") for index in range(4)]

        metrics = GraphAnalyzer().analyze(nodes, edges)["node_metrics"]

        self.assertAlmostEqual(
            metrics["0"]["hop_2_token_cost"],
            metrics["1"]["effective_token_cost"] + metrics["2"]["effective_token_cost"],
        )

    def test_token_estimation_rounds_up_at_ascii_and_unicode_boundaries(self):
        analyzer = GraphAnalyzer(GraphAnalysisConfig(characters_per_token=4))

        self.assertEqual(analyzer._estimate_tokens(""), 1)
        self.assertEqual(analyzer._estimate_tokens("abcd"), 1)
        self.assertEqual(analyzer._estimate_tokens("abcde"), 2)
        self.assertEqual(analyzer._estimate_tokens("한글테스"), 1)
        self.assertEqual(analyzer._estimate_tokens("한글테스트"), 2)
        self.assertEqual(analyzer._estimate_tokens("x" * 401), 101)

    def test_rankings_are_capped_at_ten_nodes_and_preserve_input_order_for_ties(self):
        node_ids = ["node-9", "node-1", "node-11", "node-0", "node-8", "node-2", "node-10", "node-3", "node-7", "node-4", "node-6", "node-5"]
        nodes = [
            GraphNode(id=node_id, label=node_id, group="symbol", category="symbol")
            for node_id in node_ids
        ]

        report = GraphAnalyzer().analyze(nodes, [])

        for ranking_name in (
            "top_pagerank",
            "top_betweenness",
            "top_weighted_cost",
            "top_hop_2_cost",
        ):
            self.assertEqual(len(report[ranking_name]), 10)

        for ranking_name in ("top_pagerank", "top_betweenness", "top_hop_2_cost"):
            self.assertEqual([item["id"] for item in report[ranking_name]], node_ids[:10])


if __name__ == "__main__":
    unittest.main()
