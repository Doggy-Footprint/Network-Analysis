import ast
import importlib
import shutil
import tempfile
import unittest
from pathlib import Path

from fixtures.registry import fixture_root
from renderers.html import HTMLRenderer

try:
    import tree_sitter_language_pack  # noqa: F401
    _HAS_TREE_SITTER = True
except ImportError:
    _HAS_TREE_SITTER = False


@unittest.skipUnless(_HAS_TREE_SITTER, "tree-sitter and tree-sitter-language-pack are not installed")
class TestTypeScriptAnalyzer(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def _write(self, relative_path, source):
        path = self.directory / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def _analyze(self):
        module = importlib.import_module("language_analyzers.typescript")
        return module.TypeScriptAnalyzer(str(self.directory)).analyze()

    @staticmethod
    def _node_labels(architecture):
        return {str(node.label) for node in architecture.nodes}

    @staticmethod
    def _edge_relations(architecture):
        return {str(edge.relation).upper() for edge in architecture.edges}

    def test_analyze_discovers_typescript_and_javascript_symbols_and_links(self):
        self._write(
            "src/lib.ts",
            """
export function formatName(name: string): string {
  return name.toUpperCase();
}

export class Greeter {
  greet(name: string): string {
    return formatName(name);
  }
}
""",
        )
        self._write(
            "src/main.ts",
            """
import { formatName, Greeter } from "./lib";

export { formatName };

export function run(name: string): string {
  const greeter = new Greeter();
  return formatName(greeter.greet(name));
}
""",
        )
        self._write(
            "scripts/entry.js",
            """
import { run } from "../src/main";

export function execute() {
  return run("Ada");
}
""",
        )
        self._write("ignored.py", "def not_javascript(): pass\n")

        architecture = self._analyze()

        self.assertTrue(hasattr(architecture, "nodes"))
        self.assertTrue(hasattr(architecture, "edges"))
        self.assertTrue(hasattr(architecture, "report_collections"))
        self.assertTrue(hasattr(architecture, "stats"))
        self.assertGreater(len(architecture.nodes), 0)

        labels = self._node_labels(architecture)
        self.assertTrue(
            {"formatName", "Greeter", "greet", "run", "execute"}.issubset(labels),
            labels,
        )

        relations = self._edge_relations(architecture)
        self.assertTrue(any("IMPORT" in relation for relation in relations), relations)
        self.assertTrue(any("EXPORT" in relation for relation in relations), relations)
        self.assertTrue(any("CALL" in relation for relation in relations), relations)

        node_by_id = {node.id: node for node in architecture.nodes}
        call_pairs = {
            (node_by_id[edge.from_id].label, node_by_id[edge.to_id].label)
            for edge in architecture.edges
            if "CALL" in str(edge.relation).upper()
            and edge.from_id in node_by_id
            and edge.to_id in node_by_id
        }
        self.assertIn(("run", "formatName"), call_pairs)
        self.assertIn(("execute", "run"), call_pairs)

        report_path = self.directory / "architecture.html"
        self.assertTrue(HTMLRenderer().render(architecture, str(report_path)).exists())

    def test_empty_project_produces_an_empty_deterministic_architecture(self):
        architecture = self._analyze()

        self.assertEqual(architecture.nodes, [])
        self.assertEqual(architecture.edges, [])
        self.assertEqual(architecture.stats, {
            "total_files": 0,
            "total_symbols": 0,
            "symbols_by_kind": {},
            "nodes_by_kind": {},
            "edges_by_relation": {},
            "edges_by_confidence": {},
        })
        self.assertEqual(architecture.report_collections[0].rows, [])

    def test_discovery_excludes_generated_and_hidden_files_but_keeps_unicode_source(self):
        self._write("src/한국어.ts", "export const greeting = () => '안녕';\n")
        self._write("node_modules/dependency.ts", "export function excluded() {}\n")
        self._write("build/output.js", "export function generated() {}\n")
        self._write(".cache/private.ts", "export function hidden() {}\n")

        architecture = self._analyze()

        self.assertEqual(architecture.stats["total_files"], 1)
        self.assertEqual(architecture.stats["total_symbols"], 1)
        self.assertEqual(self._node_labels(architecture), {"src/한국어.ts", "greeting"})
        greeting = next(node for node in architecture.nodes if node.label == "greeting")
        self.assertEqual(greeting.metadata["file_path"], "src/한국어.ts")
        self.assertEqual(greeting.metadata["line_number"], 1)

    def test_language_analyzer_package_does_not_depend_on_framework_analyzers(self):
        module = importlib.import_module("language_analyzers.typescript")
        package_dir = Path(module.__file__).parent

        for source_path in package_dir.rglob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            self.assertFalse(
                any(name == "framework_analyzers" or name.startswith("framework_analyzers.") for name in imports),
                source_path,
            )


@unittest.skipUnless(_HAS_TREE_SITTER, "tree-sitter and tree-sitter-language-pack are not installed")
class TestTypeScriptRealFixtureSmoke(unittest.TestCase):
    """Acceptance-level smoke coverage against a real, network-fetched NestJS app
    (fixtures.registry), in addition to (not replacing) TestTypeScriptAnalyzer's
    precise hand-written-snippet assertions above -- see contracts/fixture-unification.md
    Phase 2 dispatch report for why the precise assertions were not ported onto it.
    """

    def test_full_pipeline_against_real_nestjs_realworld_repository(self):
        root = fixture_root("typescript-nestjs-realworld")
        module = importlib.import_module("language_analyzers.typescript")
        architecture = module.TypeScriptAnalyzer(str(root / "src")).analyze()

        self.assertGreater(len(architecture.nodes), 0)
        self.assertGreater(len(architecture.edges), 0)
        node_ids = {node.id for node in architecture.nodes}
        for edge in architecture.edges:
            self.assertIn(edge.from_id, node_ids)
            self.assertIn(edge.to_id, node_ids)

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "architecture.html"
            self.assertTrue(HTMLRenderer().render(architecture, str(report_path)).exists())


if __name__ == "__main__":
    unittest.main()
