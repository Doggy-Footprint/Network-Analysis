import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import analysis
from repository import RepositorySnapshot
import code_analyzer.cli as cli
from code_analyzer.cli import parse_args


class RemovedCliArgumentsTests(unittest.TestCase):
    def test_removed_arguments_are_rejected_by_argparse(self):
        removed_arguments = [
            ["--diagnostics"],
            ["--diagnostics-output", "diagnostics.json"],
            ["--graph-cost-config", "costs.json"],
            ["--phase-b", "scenarios.json"],
            ["--phase-b-out", "cost.json"],
            ["--exploration-policy", "policy.yaml"],
            ["--cost-weights", "weights.yaml"],
            ["--samples", "12"],
            ["--seed", "7"],
        ]

        for arguments in removed_arguments:
            with self.subTest(arguments=arguments):
                stderr = io.StringIO()
                with patch.object(sys, "argv", ["code-analyzer", ".", *arguments]):
                    with contextlib.redirect_stderr(stderr):
                        with self.assertRaises(SystemExit) as raised:
                            parse_args()
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("unrecognized arguments", stderr.getvalue())
                self.assertIn(arguments[0], stderr.getvalue())


class RemovedDiagnosticsApiTests(unittest.TestCase):
    def test_analysis_only_exports_graph_metrics(self):
        for name in ("GraphAnalyzer", "GraphAnalysisConfig", "pagerank"):
            self.assertIn(name, analysis.__all__)
            self.assertTrue(hasattr(analysis, name))
        for name in ("DiagnosticKind", "FrictionDiagnoser", "ExplorationCostAnalyzer", "TaskDifficultyAnalyzer"):
            self.assertNotIn(name, analysis.__all__)

    def test_removed_analysis_apis_are_not_attributes(self):
        removed_names = [
            "DiagnosticKind",
            "DiagnosticsConfig",
            "DiagnosticsReport",
            "Finding",
            "FrictionDiagnoser",
            "ImprovementCandidate",
            "diagnostics_collection",
            "diagnostics_to_dict",
            "ExplorationCostAnalyzer",
            "TaskDefinition",
            "TaskDifficultyAnalyzer",
            "RepositoryCostDiff",
            "diff_repository_cost",
        ]

        for name in removed_names:
            with self.subTest(name=name):
                with self.assertRaises(AttributeError):
                    getattr(analysis, name)

    def test_removed_analysis_modules_and_git_diff_core_are_unavailable(self):
        removed_modules = [
            "analysis.friction_diagnostics",
            "analysis.exploration_cost",
            "analysis.task_difficulty",
            "analysis.cost_diff",
            "language_analyzers.core.git_diff_core",
        ]
        root = Path(__file__).resolve().parents[1]

        for module_name in removed_modules:
            with self.subTest(module_name=module_name):
                self.assertIsNone(importlib.util.find_spec(module_name))
                self.assertFalse((root / Path(*module_name.split("."))).with_suffix(".py").exists())


class ImmutableStaticSnapshotCliTests(unittest.TestCase):
    @staticmethod
    def _write_fastapi_source(root):
        (root / "main.py").write_text(
            "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef route():\n    return {'ok': True}\n",
            encoding="utf-8",
        )

    def test_C_1_static_fastapi_reuses_one_snapshot_for_analysis_and_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fastapi_source(root)
            output = root / "report.html"
            real_snapshot = cli.build_snapshot
            real_analyzer = cli.FastAPIAnalyzer
            real_builder = cli.ArchitectureGraphBuilder
            snapshots, analyzer_snapshots, builder_snapshots = [], [], []

            def snapshot_spy(*args, **kwargs):
                snapshot = real_snapshot(*args, **kwargs)
                snapshots.append((snapshot, kwargs.get("excluded_paths", ())))
                return snapshot

            class StaticAnalyzerSpy:
                def __init__(self, *args, **kwargs):
                    analyzer_snapshots.append(kwargs.get("snapshot"))
                    self._delegate = real_analyzer(*args, **kwargs)

                def analyze(self):
                    return self._delegate.analyze()

            class GraphBuilderSpy:
                def __init__(self, *args, **kwargs):
                    builder_snapshots.append(kwargs.get("snapshot"))
                    self._delegate = real_builder(*args, **kwargs)

                def build_graph(self, architecture):
                    return self._delegate.build_graph(architecture)

            arguments = ["code-analyzer", str(root), "-f", "fastapi", "-o", str(output)]
            with patch.object(cli, "build_snapshot", side_effect=snapshot_spy), \
                    patch.object(cli, "FastAPIAnalyzer", StaticAnalyzerSpy), \
                    patch.object(cli, "ArchitectureGraphBuilder", GraphBuilderSpy), \
                    patch.object(sys, "argv", arguments), \
                    contextlib.redirect_stdout(io.StringIO()):
                cli.main()

            self.assertEqual(len(snapshots), 1)
            snapshot, excluded_paths = snapshots[0]
            self.assertEqual(analyzer_snapshots, [snapshot])
            self.assertEqual(builder_snapshots, [snapshot])
            self.assertIn(output.name, {Path(path).name for path in excluded_paths})

    def test_C_1_every_static_cli_mode_passes_its_single_snapshot_to_its_analyzer(self):
        class StopAfterAnalyzerConstruction(Exception):
            pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            snapshot = RepositorySnapshot(
                str(root), "snapshot.v1", (("main.py", "value = 1\n"),), ()
            )
            modes = [
                ("python", "PythonGraphAnalyzer", ["-l", "python"]),
                ("typescript", "TypeScriptAnalyzer", ["-l", "typescript"]),
                ("kotlin", "KotlinAnalyzer", ["-l", "kotlin"]),
                ("android", "AndroidAnalyzer", ["-f", "android"]),
                ("fastapi", "FastAPIAnalyzer", ["-f", "fastapi"]),
            ]

            for mode, analyzer_name, mode_arguments in modes:
                with self.subTest(mode=mode):
                    build_calls = []
                    analyzer_snapshots = []

                    def build_snapshot_spy(*args, **kwargs):
                        build_calls.append((args, kwargs))
                        return snapshot

                    class AnalyzerSpy:
                        def __init__(self, *args, **kwargs):
                            analyzer_snapshots.append(kwargs.get("snapshot"))
                            raise StopAfterAnalyzerConstruction

                    arguments = [
                        "code-analyzer", str(root), *mode_arguments,
                        "-o", str(root / f"{mode}.html"),
                    ]
                    with patch.object(cli, "build_snapshot", side_effect=build_snapshot_spy), \
                            patch.object(cli, analyzer_name, AnalyzerSpy), \
                            patch.object(sys, "argv", arguments), \
                            contextlib.redirect_stdout(io.StringIO()), \
                            self.assertRaises(StopAfterAnalyzerConstruction):
                        cli.main(file_lister=lambda *args, **kwargs: [])

                    self.assertEqual(len(build_calls), 1)
                    self.assertEqual(analyzer_snapshots, [snapshot])


if __name__ == "__main__":
    unittest.main()
