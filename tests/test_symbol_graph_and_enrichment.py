import tempfile
import unittest
import importlib.util
import json
import sys
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

from analysis import GraphAnalysisConfig, GraphAnalyzer
from language_analyzers.core import enrichment as enrichment_module
from language_analyzers.core.graph_models import GraphEdge, GraphNode, NodeCost, RelationKind, SourceSpan
from language_analyzers.core.enrichment import enrich_repository
from language_analyzers.core.serialization import architecture_to_dict
from language_analyzers.python.graph import PythonGraphAnalyzer


_HAS_TREE_SITTER = importlib.util.find_spec("tree_sitter_language_pack") is not None


def _node(node_id, cost, flags=None):
    return GraphNode(
        id=node_id,
        label=node_id,
        group="symbol",
        category="symbol",
        cost=NodeCost(cost, cost * 4, 1),
        flags=flags or [],
    )


class TestCostAndScalePolicy(unittest.TestCase):
    def test_raw_and_effective_costs_preserve_nodes(self):
        nodes = [
            _node("ordinary", 10),
            _node("vendor", 20, ["vendored"]),
            _node("generated", 30, ["generated"]),
            _node("migration", 40, ["migration"]),
        ]

        report = GraphAnalyzer().analyze(nodes, [])

        self.assertEqual(report["total_token_cost"], 100)
        self.assertEqual(report["total_effective_token_cost"], 17)
        self.assertEqual(report["node_metrics"]["vendor"]["effective_token_cost"], 0)
        self.assertEqual(report["node_metrics"]["generated"]["effective_token_cost"], 3)
        self.assertEqual(report["node_metrics"]["migration"]["effective_token_cost"], 4)
        self.assertEqual(len(report["node_metrics"]), 4)
        self.assertEqual(report["cost_policy"], {
            "vendored": 0.0, "generated": 0.1, "migration": 0.1, "default": 1.0,
        })

    def test_all_vendored_graph_has_zero_effective_cost(self):
        report = GraphAnalyzer().analyze([_node("a", 8, ["vendored"]), _node("b", 12, ["vendored"])], [])

        self.assertEqual(report["total_token_cost"], 20)
        self.assertEqual(report["total_effective_token_cost"], 0)
        self.assertTrue(all(item["weighted_centrality_cost"] == 0 for item in report["node_metrics"].values()))

    def test_test_flag_has_full_effective_cost(self):
        report = GraphAnalyzer().analyze([_node("test", 13, ["test"])], [])

        self.assertEqual(report["node_metrics"]["test"]["effective_token_cost"], 13)
        self.assertEqual(report["total_effective_token_cost"], 13)

    def test_exact_threshold_boundary_and_sampled_determinism(self):
        nodes = [_node(name, 1) for name in "abcd"]
        edges = [GraphEdge("a", "b", "CALLS"), GraphEdge("b", "c", "CALLS"), GraphEdge("c", "d", "CALLS")]
        exact = GraphAnalyzer(GraphAnalysisConfig(exact_betweenness_threshold=4)).analyze(nodes, edges)
        sampler = lambda ordered, count: ordered[-count:]
        config = GraphAnalysisConfig(
            exact_betweenness_threshold=3,
            betweenness_sample_size=2,
            betweenness_sampler=sampler,
        )

        first = GraphAnalyzer(config).analyze(nodes, edges)
        second = GraphAnalyzer(config).analyze(nodes, edges)

        self.assertEqual(exact["betweenness_strategy"], "exact")
        self.assertEqual(exact["betweenness_sample_size"], 4)
        self.assertEqual(exact["node_metrics"]["b"]["betweenness_centrality"], 1 / 3)
        self.assertEqual(first["betweenness_strategy"], "deterministic_sampled")
        self.assertEqual(first["betweenness_sample_size"], 2)
        self.assertEqual(first["node_metrics"], second["node_metrics"])

    def test_effective_cost_drives_weighted_and_neighborhood_metrics(self):
        nodes = [
            _node("ordinary", 10), _node("generated", 20, ["generated"]),
            _node("migration", 30, ["migration"]), _node("far", 4),
        ]
        edges = [
            GraphEdge("ordinary", "generated", "CALLS"),
            GraphEdge("generated", "migration", "CALLS"),
            GraphEdge("migration", "far", "CALLS"),
        ]

        report = GraphAnalyzer().analyze(nodes, edges)

        metrics = report["node_metrics"]
        self.assertEqual(metrics["generated"]["effective_token_cost"], 2)
        self.assertEqual(metrics["migration"]["effective_token_cost"], 3)
        self.assertEqual(metrics["ordinary"]["hop_2_token_cost"], 5)
        self.assertEqual(metrics["ordinary"]["hop_3_token_cost"], 9)
        self.assertEqual(metrics["ordinary"]["hop_2_node_count"], 2)
        self.assertEqual(metrics["ordinary"]["hop_3_node_count"], 3)
        self.assertEqual(metrics["generated"]["weighted_centrality_cost"], metrics["generated"]["pagerank"] * 2)
        self.assertEqual(report["neighborhood_strategy"], "single_bfs_to_3_hops")

    def test_empty_and_zero_sample_size_metadata(self):
        empty = GraphAnalyzer().analyze([], [])
        nodes = [_node(name, 1) for name in "ab"]
        sampled = GraphAnalyzer(GraphAnalysisConfig(
            exact_betweenness_threshold=1,
            betweenness_sample_size=0,
        )).analyze(nodes, [GraphEdge("a", "b", "CALLS")])

        self.assertEqual(empty["betweenness_strategy"], "exact")
        self.assertEqual(empty["betweenness_sample_size"], 0)
        self.assertEqual(empty["total_effective_token_cost"], 0)
        self.assertEqual(sampled["betweenness_strategy"], "deterministic_sampled")
        self.assertEqual(sampled["betweenness_sample_size"], 1)

    def test_default_sampler_selects_deterministic_evenly_spaced_sources(self):
        nodes = [_node(name, 1) for name in "abcde"]
        edges = [
            GraphEdge("a", "b", "CALLS"), GraphEdge("b", "c", "CALLS"),
            GraphEdge("c", "d", "CALLS"), GraphEdge("d", "e", "CALLS"),
        ]
        config = GraphAnalysisConfig(exact_betweenness_threshold=4, betweenness_sample_size=2)

        reports = [GraphAnalyzer(config).analyze(nodes, edges) for _ in range(5)]
        values = [
            {node_id: report["node_metrics"][node_id]["betweenness_centrality"] for node_id in "abcde"}
            for report in reports
        ]

        self.assertTrue(all(report["betweenness_strategy"] == "deterministic_sampled" for report in reports))
        self.assertTrue(all(report["betweenness_sample_size"] == 2 for report in reports))
        self.assertEqual(values, [values[0]] * 5)
        self.assertEqual(values[0], {"a": 0.0, "b": 0.5, "c": 1 / 3, "d": 1 / 3, "e": 0.0})

    def test_neighborhoods_are_computed_once_per_node(self):
        class SpyGraphAnalyzer(GraphAnalyzer):
            def __init__(self):
                super().__init__()
                self.neighborhood_calls = []

            def _neighborhoods(self, start, adjacency):
                self.neighborhood_calls.append(start)
                return super()._neighborhoods(start, adjacency)

        nodes = [_node(name, 1) for name in "abcd"]
        edges = [GraphEdge("a", "b", "CALLS"), GraphEdge("b", "c", "CALLS"), GraphEdge("c", "d", "CALLS")]
        analyzer = SpyGraphAnalyzer()

        report = analyzer.analyze(nodes, edges)

        self.assertEqual(analyzer.neighborhood_calls, list("abcd"))
        self.assertEqual(report["node_metrics"]["a"]["hop_2_node_count"], 2)
        self.assertEqual(report["node_metrics"]["a"]["hop_3_node_count"], 3)
        self.assertEqual(report["neighborhood_strategy"], "single_bfs_to_3_hops")


class TestRepositoryEnrichment(unittest.TestCase):
    def test_repeated_code_literal_is_indexed_once_and_retains_all_use_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = {
                "config.json": '{\n  "port": 1,\n  "port": 2\n}',
                "consumer.py": (
                    "def consume():\n"
                    "    first = 'port'\n"
                    "    second = 'port'\n"
                    "    return 'port'\n"
                ),
            }
            architecture = SimpleNamespace(
                project_path=str(root),
                nodes=[
                    GraphNode(
                        id="consumer",
                        label="consume",
                        group="symbol",
                        category="symbol",
                        kind="function",
                        span=SourceSpan("consumer.py", 1, 4),
                    )
                ],
                edges=[],
            )
            reads = []

            def reader(path):
                relative = path.relative_to(root).as_posix()
                reads.append(relative)
                return sources[relative]

            with mock.patch.object(
                enrichment_module,
                "_index_code_literals",
                wraps=enrichment_module._index_code_literals,
            ) as index_literals:
                enrich_repository(
                    architecture,
                    file_inventory=["consumer.py", "config.json"],
                    file_reader=reader,
                )

            self.assertEqual(reads, ["config.json", "consumer.py"])
            self.assertEqual(index_literals.call_count, 1)
            self.assertEqual(index_literals.call_args.args, (sources["consumer.py"],))
            config_nodes = [
                node for node in architecture.nodes
                if node.kind == "configuration" and node.label == "port"
            ]
            self.assertEqual(len(config_nodes), 1)
            self.assertEqual(config_nodes[0].metadata["occurrence_lines"], [2, 3])
            config_edges = [
                edge for edge in architecture.edges
                if edge.relation == RelationKind.CONFIGURES
            ]
            self.assertEqual(len(config_edges), 1)
            self.assertEqual(config_edges[0].metadata["occurrence_lines"], [2, 3, 4])
            self.assertEqual(config_edges[0].evidence, SourceSpan("consumer.py", 2, 2))

    def test_injected_inventory_reads_each_code_and_config_file_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = {
                "config.json": '{"port": 1, "nested": {"port": 2}}',
                "consumer.py": 'value = "port"\n',
            }
            calls = []
            architecture = SimpleNamespace(
                project_path=str(root),
                nodes=[
                    GraphNode(
                        id="consumer",
                        label="consumer",
                        group="symbol",
                        category="symbol",
                        kind="function",
                        span=SourceSpan("consumer.py", 1, 1),
                    )
                ],
                edges=[],
            )

            def reader(path):
                relative = path.relative_to(root).as_posix()
                calls.append(relative)
                return sources[relative]

            enrich_repository(
                architecture,
                file_inventory=["consumer.py", "config.json"],
                file_reader=reader,
            )

            self.assertEqual(calls, ["config.json", "consumer.py"])
            config = [node for node in architecture.nodes if node.kind == "configuration"]
            port = next(node for node in config if node.label == "port")
            self.assertEqual(port.metadata["occurrence_lines"], [1, 1])
            self.assertEqual(
                len([edge for edge in architecture.edges if edge.relation == RelationKind.CONFIGURES]),
                1,
            )

    def test_repeated_json_key_has_one_file_key_identity_and_all_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.json").write_text('{"items":[{"port":1},{"port":2}]}', encoding="utf-8")
            (root / "consumer.py").write_text('value = "port"\n', encoding="utf-8")

            architecture = PythonGraphAnalyzer(root).analyze()
            matches = [node for node in architecture.nodes if node.kind == "configuration" and node.label == "port"]

            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].id, "config:config.json:port")
            self.assertEqual(len(matches[0].metadata["occurrence_lines"]), 2)

    def test_test_relations_use_references_and_exclude_test_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "service.py").write_text("def produce():\n    return 1\n", encoding="utf-8")
            (root / "test_service.py").write_text(
                "from service import produce\n\ndef test_produce():\n    assert produce() == 1\n",
                encoding="utf-8",
            )
            (root / "test_helper.py").write_text(
                "def helper():\n    return 1\n",
                encoding="utf-8",
            )

            architecture = PythonGraphAnalyzer(root).analyze()
            nodes = {node.id: node for node in architecture.nodes}
            test_edges = [edge for edge in architecture.edges if edge.relation == RelationKind.TESTS]

            self.assertTrue(test_edges)
            self.assertTrue(any(nodes[edge.to_id].label == "produce" for edge in test_edges))
            self.assertTrue(all("test" not in nodes[edge.to_id].flags for edge in test_edges))
            self.assertTrue(all(edge.evidence is not None for edge in test_edges))

    def test_duplicate_and_unused_config_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("API_URL=one\nUNUSED=value\n", encoding="utf-8")
            (root / "settings.properties").write_text("API_URL=two\n", encoding="utf-8")
            (root / "consumer.py").write_text("value = getenv(\"API_URL\")\n", encoding="utf-8")

            architecture = PythonGraphAnalyzer(root).analyze()
            config_nodes = [node for node in architecture.nodes if node.kind == "configuration"]
            config_edges = [edge for edge in architecture.edges if edge.relation == RelationKind.CONFIGURES]

            self.assertEqual(sum(node.label == "API_URL" for node in config_nodes), 2)
            self.assertEqual(sum(node.label == "UNUSED" for node in config_nodes), 1)
            self.assertEqual(len(config_edges), 2)
            self.assertTrue(all(next(node for node in config_nodes if node.id == edge.from_id).label == "API_URL" for edge in config_edges))

    def test_test_naming_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "widget.py").write_text("class Widget:\n    pass\n", encoding="utf-8")
            (root / "widget_test.py").write_text("def test_behavior():\n    assert True\n", encoding="utf-8")

            architecture = PythonGraphAnalyzer(root).analyze()
            nodes = {node.id: node for node in architecture.nodes}
            targets = [
                nodes[edge.to_id].label for edge in architecture.edges
                if edge.relation == RelationKind.TESTS
            ]

            self.assertIn("Widget", targets)

    def test_reference_priority_with_unrelated_filenames_and_edge_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "domain").mkdir()
            (root / "tests").mkdir()
            (root / "domain" / "engine.py").write_text("def calculate():\n    return 1\n", encoding="utf-8")
            (root / "tests" / "helper.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
            (root / "tests" / "checks.py").write_text(
                "from domain.engine import calculate\n\ndef verify():\n    return calculate()\n",
                encoding="utf-8",
            )

            architecture = PythonGraphAnalyzer(root).analyze()
            nodes = {node.id: node for node in architecture.nodes}
            test_edges = [edge for edge in architecture.edges if edge.relation == RelationKind.TESTS]

            self.assertTrue(any(nodes[edge.from_id].span.file_path == "tests/checks.py" and nodes[edge.to_id].label == "calculate" for edge in test_edges))
            self.assertTrue(all("test" in nodes[edge.from_id].flags for edge in test_edges))
            self.assertTrue(all("test" not in nodes[edge.to_id].flags for edge in test_edges))
            self.assertTrue(all(str(edge.confidence) in {"static_certain", "static_inferred"} for edge in test_edges))
            self.assertTrue(all(str(edge.resolution) in {"exact", "unique_name", "ambiguous"} for edge in test_edges))
            self.assertTrue(all(edge.evidence and edge.evidence.file_path for edge in test_edges))

    def test_all_config_formats_direction_and_value_not_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                ".env": "ENV_KEY=value_only\n",
                "config.json": json.dumps({"JSON_KEY": "JSON_VALUE_ONLY"}),
                "config.yaml": "YAML_KEY: yaml_value_only\n",
                "config.toml": "TOML_KEY = \"toml_value_only\"\n",
                "config.properties": "PROP_KEY=prop_value_only\n",
                "build.gradle.kts": 'buildConfigField("String", "GRADLE_KEY", "gradle_value_only")\n',
            }
            for name, content in files.items():
                (root / name).write_text(content, encoding="utf-8")
            keys = ["ENV_KEY", "JSON_KEY", "YAML_KEY", "TOML_KEY", "PROP_KEY", "GRADLE_KEY"]
            (root / "consumer.py").write_text(
                "def consume():\n    return " + " + ".join(repr(key) for key in keys) + "\n",
                encoding="utf-8",
            )

            architecture = PythonGraphAnalyzer(root).analyze()
            nodes = {node.id: node for node in architecture.nodes}
            config_nodes = [node for node in architecture.nodes if node.kind == "configuration"]
            config_edges = [edge for edge in architecture.edges if edge.relation == RelationKind.CONFIGURES]

            self.assertEqual({node.label for node in config_nodes}, set(keys))
            self.assertFalse({"value_only", "JSON_VALUE_ONLY", "yaml_value_only", "toml_value_only", "prop_value_only", "gradle_value_only"} & {node.label for node in config_nodes})
            self.assertEqual({nodes[edge.from_id].label for edge in config_edges}, set(keys))
            self.assertTrue(all(nodes[edge.from_id].kind == "configuration" and nodes[edge.to_id].label == "consume" for edge in config_edges))
            self.assertTrue(all(str(edge.confidence) == "static_certain" and str(edge.resolution) == "exact" for edge in config_edges))
            self.assertTrue(all(edge.evidence and edge.evidence.file_path == "consumer.py" for edge in config_edges))

    def test_config_key_matching_is_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("API=short\nAPI_URL=full\n", encoding="utf-8")
            (root / "consumer.py").write_text("def consume():\n    return 'API_URL'\n", encoding="utf-8")

            architecture = PythonGraphAnalyzer(root).analyze()
            nodes = {node.id: node for node in architecture.nodes}
            config_edges = [edge for edge in architecture.edges if edge.relation == RelationKind.CONFIGURES]

            self.assertEqual({nodes[edge.from_id].label for edge in config_edges}, {"API_URL"})
            self.assertFalse(any(nodes[edge.from_id].label == "API" for edge in config_edges))

    def test_reference_beats_conflicting_naming_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "widget.py").write_text("class Widget:\n    pass\n", encoding="utf-8")
            (root / "service.py").write_text("class Service:\n    pass\n", encoding="utf-8")
            (root / "widget_test.py").write_text(
                "from service import Service\n\ndef test_service():\n    return Service()\n",
                encoding="utf-8",
            )

            architecture = PythonGraphAnalyzer(root).analyze()
            nodes = {node.id: node for node in architecture.nodes}
            test_edges = [edge for edge in architecture.edges if edge.relation == RelationKind.TESTS]
            targets = {nodes[edge.to_id].label for edge in test_edges}

            self.assertIn("Service", targets)
            self.assertNotIn("Widget", targets)


class TestNeutralContracts(unittest.TestCase):
    def test_python_unresolved_location_and_all_edge_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(
                "def target():\n    return 1\n\ndef caller():\n    target()\n    missing()\n",
                encoding="utf-8",
            )

            architecture = PythonGraphAnalyzer(root).analyze()
            caller = next(node for node in architecture.nodes if node.label == "caller")
            unresolved = caller.metadata["unresolved_references"][0]
            by_id = {node.id: node for node in architecture.nodes}
            call = next(edge for edge in architecture.edges if edge.relation == RelationKind.CALLS)

            self.assertEqual(unresolved["resolution"], "unresolved")
            self.assertEqual(unresolved["confidence"], "dynamic_required")
            self.assertEqual(unresolved["evidence"], {"file_path": "main.py", "start_line": 6, "end_line": 6})
            self.assertEqual((by_id[call.from_id].label, by_id[call.to_id].label), ("caller", "target"))
            self.assertTrue(all(edge.confidence and edge.resolution and edge.evidence for edge in architecture.edges))

    def test_neutral_serialization_preserves_m1_relations_and_evidence(self):
        relations = [
            RelationKind.TYPE_USES, RelationKind.READS, RelationKind.WRITES,
            RelationKind.INSTANTIATES, RelationKind.TESTS, RelationKind.CONFIGURES,
        ]
        nodes = [_node("source", 1), _node("target", 1)]
        edges = [
            GraphEdge(
                "source", "target", relation,
                confidence="static_inferred", resolution="unique_name",
                evidence=SourceSpan("source.py", index + 1, index + 1),
            )
            for index, relation in enumerate(relations)
        ]
        architecture = SimpleNamespace(
            project_name="sample", project_path="/sample", nodes=nodes, edges=edges,
            stats={}, report_collections=[],
        )

        serialized = architecture_to_dict(architecture)

        self.assertEqual([edge["relation"] for edge in serialized["edges"]], relations)
        self.assertTrue(all(edge["evidence"]["file_path"] == "source.py" for edge in serialized["edges"]))
        self.assertTrue(all(edge["confidence"] == "static_inferred" and edge["resolution"] == "unique_name" for edge in serialized["edges"]))

    def test_missing_tree_sitter_uses_typed_import_error(self):
        from language_analyzers.kotlin import ast as kotlin_ast
        from language_analyzers.typescript import ast as typescript_ast

        kotlin_parser = kotlin_ast._PARSER
        typescript_parsers = dict(typescript_ast._PARSERS)
        try:
            kotlin_ast._PARSER = None
            typescript_ast._PARSERS.clear()
            with mock.patch.dict(sys.modules, {"tree_sitter_language_pack": None}):
                with self.assertRaises(ImportError):
                    kotlin_ast.get_kotlin_parser()
                with self.assertRaises(ImportError):
                    typescript_ast.get_parser("typescript")
        finally:
            kotlin_ast._PARSER = kotlin_parser
            typescript_ast._PARSERS.clear()
            typescript_ast._PARSERS.update(typescript_parsers)

    def test_fastapi_builder_enriches_configuration(self):
        from framework_analyzers.fastapi.analyzer import FastAPIAnalyzer
        from framework_analyzers.fastapi.graph import ArchitectureGraphBuilder

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("FEATURE_KEY=enabled\n", encoding="utf-8")
            (root / "main.py").write_text(
                "from fastapi import FastAPI\napp = FastAPI()\n"
                "@app.get('/')\ndef route():\n    return 'FEATURE_KEY'\n",
                encoding="utf-8",
            )

            architecture = ArchitectureGraphBuilder().build_graph(FastAPIAnalyzer(root).analyze())
            nodes = {node.id: node for node in architecture.nodes}
            edges = [edge for edge in architecture.edges if edge.relation == RelationKind.CONFIGURES]

            self.assertTrue(edges)
            self.assertTrue(all(nodes[edge.from_id].kind == "configuration" for edge in edges))
            self.assertTrue(any(nodes[edge.to_id].label == "route" or nodes[edge.to_id].label.startswith("GET /") for edge in edges))
            self.assertTrue(all(str(edge.confidence) == "static_certain" for edge in edges))
            self.assertTrue(all(str(edge.resolution) == "exact" for edge in edges))
            self.assertTrue(all(edge.evidence and edge.evidence.file_path == "main.py" and edge.evidence.start_line == 5 for edge in edges))

    def test_android_builder_enriches_test_and_configuration(self):
        from framework_analyzers.android.graph import AndroidArchitectureGraphBuilder
        from framework_analyzers.android.models import AndroidProjectArchitecture, ComposableInfo

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Prod.kt").write_text('@Composable\nfun Prod() { val key = "ANDROID_KEY" }\n', encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "Checks.kt").write_text("@Composable\nfun Checks() { Prod() }\n", encoding="utf-8")
            (root / ".env").write_text("ANDROID_KEY=value\n", encoding="utf-8")
            architecture = AndroidProjectArchitecture(
                project_name="android", project_path=str(root),
                composables=[
                    ComposableInfo("prod", "Prod", "Prod.kt", "Prod.kt", 2, 2),
                    ComposableInfo("checks", "Checks", "tests/Checks.kt", "tests/Checks.kt", 2, 2, calls=["Prod"]),
                ],
            )

            architecture = AndroidArchitectureGraphBuilder().build_graph(architecture)
            nodes = {node.id: node for node in architecture.nodes}
            tests_edges = [edge for edge in architecture.edges if edge.relation == RelationKind.TESTS]
            config_edges = [edge for edge in architecture.edges if edge.relation == RelationKind.CONFIGURES]

            self.assertTrue(any(nodes[edge.from_id].metadata.get("name") == "Checks" and nodes[edge.to_id].metadata.get("name") == "Prod" for edge in tests_edges))
            self.assertTrue(config_edges)
            self.assertTrue(all(nodes[edge.from_id].kind == "configuration" for edge in config_edges))
            framework_test_edges = [edge for edge in tests_edges if edge.from_id == "checks" and edge.to_id == "prod"]
            self.assertTrue(framework_test_edges)
            self.assertTrue(all(str(edge.confidence) == "framework_inferred" for edge in framework_test_edges))
            self.assertTrue(all(str(edge.resolution) == "unique_name" for edge in framework_test_edges))
            self.assertTrue(all(edge.evidence and edge.evidence.file_path == "tests/Checks.kt" for edge in framework_test_edges))
            self.assertTrue(all(str(edge.confidence) == "static_certain" for edge in config_edges))
            self.assertTrue(all(str(edge.resolution) == "exact" for edge in config_edges))
            self.assertTrue(all(edge.evidence and edge.evidence.file_path == "Prod.kt" and edge.evidence.start_line == 2 for edge in config_edges))


@unittest.skipUnless(_HAS_TREE_SITTER, "tree-sitter-language-pack not installed")
class TestLanguageRelations(unittest.TestCase):
    def test_typescript_reads_and_writes(self):
        from language_analyzers.typescript import TypeScriptAnalyzer

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.ts").write_text(
                "export let counter = 0;\n"
                "export function update(){ counter = counter + 1; return counter; }\n",
                encoding="utf-8",
            )

            architecture = TypeScriptAnalyzer(root).analyze()
            by_id = {node.id: node for node in architecture.nodes}
            relations = {
                edge.relation for edge in architecture.edges
                if by_id[edge.from_id].label == "update" and by_id[edge.to_id].label == "counter"
            }

            self.assertIn(RelationKind.READS, relations)
            self.assertIn(RelationKind.WRITES, relations)
            self.assertTrue(all(edge.confidence and edge.resolution and edge.evidence for edge in architecture.edges))

    def test_typescript_unresolved_reference_location(self):
        from language_analyzers.typescript import TypeScriptAnalyzer

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.ts").write_text(
                "export function target() {}\n"
                "export function caller() {\n"
                "  target();\n"
                "  missing();\n"
                "}\n",
                encoding="utf-8",
            )

            architecture = TypeScriptAnalyzer(root).analyze()
            caller = next(node for node in architecture.nodes if node.label == "caller")
            unresolved = caller.metadata["unresolved_references"][0]

            self.assertEqual(unresolved["name"], "missing")
            self.assertEqual(unresolved["resolution"], "unresolved")
            self.assertEqual(unresolved["confidence"], "dynamic_required")
            self.assertEqual(unresolved["evidence"], {"file_path": "main.ts", "start_line": 4, "end_line": 4})

    def test_kotlin_core_relations_and_unresolved_evidence(self):
        from language_analyzers.kotlin import KotlinAnalyzer

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.kt").write_text(
                "package demo\n"
                "class State\n"
                "open class Base\n"
                "class Service(var state: State): Base() {\n"
                " fun update(next: State): State { state = next; return state }\n"
                "}\n"
                "fun helper(): State = State()\n"
                "fun make(): Service { helper(); external(); return Service(State()) }\n",
                encoding="utf-8",
            )

            architecture = KotlinAnalyzer(root).analyze()
            by_id = {node.id: node for node in architecture.nodes}
            relations = {edge.relation for edge in architecture.edges}
            make = next(node for node in architecture.nodes if node.label == "make")

            self.assertTrue({
                RelationKind.CONTAINS,
                RelationKind.DECLARES,
                RelationKind.CALLS,
                RelationKind.INSTANTIATES,
                RelationKind.INHERITS,
                RelationKind.TYPE_USES,
                RelationKind.READS,
                RelationKind.WRITES,
            }.issubset(relations))
            self.assertTrue(all(edge.evidence is not None for edge in architecture.edges))
            self.assertEqual(make.metadata["unresolved_references"][0]["name"], "external")
            self.assertEqual(make.metadata["unresolved_references"][0]["resolution"], "unresolved")
            self.assertEqual(make.metadata["unresolved_references"][0]["confidence"], "dynamic_required")
            self.assertEqual(make.metadata["unresolved_references"][0]["evidence"], {
                "file_path": "main.kt", "start_line": 8, "end_line": 8,
            })
            self.assertTrue(any(by_id[edge.to_id].label == "helper" and edge.relation == RelationKind.CALLS for edge in architecture.edges))
            endpoints = {(by_id[edge.from_id].label, by_id[edge.to_id].label, edge.relation) for edge in architecture.edges}
            self.assertIn(("make", "helper", RelationKind.CALLS), endpoints)
            self.assertIn(("make", "Service", RelationKind.INSTANTIATES), endpoints)
            self.assertIn(("Service", "Base", RelationKind.INHERITS), endpoints)
            self.assertIn(("Service", "State", RelationKind.TYPE_USES), endpoints)
            self.assertIn(("Service", "update", RelationKind.CONTAINS), endpoints)
            self.assertIn(("main.kt", "make", RelationKind.DECLARES), endpoints)
            self.assertIn(("update", "state", RelationKind.WRITES), endpoints)
            self.assertIn(("update", "state", RelationKind.READS), endpoints)

    def test_kotlin_ambiguous_edge_preserves_candidates(self):
        from language_analyzers.kotlin import KotlinAnalyzer

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.kt").write_text("package one\nclass Duplicate\n", encoding="utf-8")
            (root / "two.kt").write_text("package two\nclass Duplicate\nfun create() = Duplicate()\n", encoding="utf-8")

            architecture = KotlinAnalyzer(root).analyze()
            nodes = {node.id: node for node in architecture.nodes}
            duplicate_ids = {node.id for node in architecture.nodes if node.label == "Duplicate"}
            ambiguous = [
                edge for edge in architecture.edges
                if str(edge.resolution) == "ambiguous"
                and edge.relation == RelationKind.INSTANTIATES
                and nodes[edge.from_id].label == "create"
            ]

            self.assertTrue(ambiguous)
            self.assertEqual(set(ambiguous[0].candidates), duplicate_ids - {ambiguous[0].to_id})
            self.assertTrue(all(edge.evidence is not None for edge in ambiguous))

    def test_kotlin_direct_analyzer_shape_and_cli(self):
        from code_analyzer import cli
        from language_analyzers.kotlin import KotlinAnalyzer, KotlinProjectArchitecture

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.kt").write_text("package demo\nclass Item\nfun create() = Item()\n", encoding="utf-8")
            architecture = KotlinAnalyzer(root).analyze()

            self.assertIsInstance(architecture, KotlinProjectArchitecture)
            self.assertEqual(architecture.project_path, str(root.resolve()))
            self.assertTrue(architecture.nodes)
            self.assertTrue(architecture.edges)
            self.assertIn("nodes_by_kind", architecture.stats)
            self.assertEqual(architecture.report_collections[0].key, "symbols")

            output = root / "kotlin-report.html"
            argv = ["code-analyzer", str(root), "-l", "kotlin", "-o", str(output)]
            with mock.patch.object(sys, "argv", argv):
                args = cli.parse_args()
            self.assertEqual(args.language, "kotlin")
            with mock.patch.object(sys, "argv", argv):
                cli.main()
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
