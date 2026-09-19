import contextlib
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import analysis
from agent_view import RepositorySnapshot
import code_analyzer.cli as cli
from code_analyzer.cli import main, parse_args


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


class AgentViewCliArgumentTests(unittest.TestCase):
    def parse(self, arguments):
        with patch.object(sys, "argv", ["code-analyzer", ".", *arguments]):
            return parse_args()

    def test_agent_view_arguments_are_accepted(self):
        args = self.parse(["--agent-view", "view.json", "--agent-view-profile", "rules.yaml"])

        self.assertEqual(args.agent_view, "view.json")
        self.assertEqual(args.agent_view_profile, "rules.yaml")
        self.assertIsNone(args.agent_view_diff)

    def test_agent_view_diff_takes_two_paths(self):
        args = self.parse(["--agent-view-diff", "before.json", "after.json"])

        self.assertEqual(args.agent_view_diff, ["before.json", "after.json"])

    def test_agent_view_profile_without_agent_view_exits_with_code_two(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                self.parse(["--agent-view-profile", "rules.yaml"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--agent-view-profile", stderr.getvalue())


class RemovedDiagnosticsApiTests(unittest.TestCase):
    def test_analysis_only_exports_graph_metrics(self):
        self.assertEqual(analysis.__all__, ["GraphAnalyzer", "GraphAnalysisConfig", "pagerank"])

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


class AgentViewCliBehaviourTests(unittest.TestCase):
    def test_agent_view_writes_the_serialized_graph_to_the_given_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("handler = 1\n", encoding="utf-8")
            output = root / "graph.json"

            argv = ["code-analyzer", str(root), "-l", "python",
                    "-o", str(root / "report.html"), "--agent-view", str(output)]
            with patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(io.StringIO()):
                    main()

            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(
            sorted(payload),
            ["connections", "entry_documents", "hint_store", "occurrence_store", "profile", "project_name",
             "query_nodes", "read_units", "readable_nodes", "scan", "schema_version"],
        )
        self.assertEqual(payload["schema_version"], "3")

    def test_agent_view_diff_prints_a_diff_and_ignores_a_missing_project_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = root / "before.json"
            after = root / "after.json"
            before.write_text(json.dumps({
                "schema_version": "3",
                "readable_nodes": [{"id": "gone", "flags": [], "read_cost": {"token_estimate": 1}}],
                "query_nodes": [], "connections": [], "profile": {"version": 3},
            }), encoding="utf-8")
            after.write_text(json.dumps({
                "schema_version": "3",
                "readable_nodes": [{"id": "fresh", "flags": [], "read_cost": {"token_estimate": 1}}],
                "query_nodes": [], "connections": [], "profile": {"version": 3},
            }), encoding="utf-8")

            argv = ["code-analyzer", str(root / "does-not-exist"),
                    "--agent-view-diff", str(before), str(after)]
            stdout = io.StringIO()
            with patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(stdout):
                    main()

        result = json.loads(stdout.getvalue())

        self.assertEqual(result["readable_nodes"]["added"], ["fresh"])
        self.assertEqual(result["readable_nodes"]["removed"], ["gone"])


class ImmutableStaticSnapshotCliTests(unittest.TestCase):
    def _arguments(self, root, output, agent_view, app=None):
        arguments = ["code-analyzer", str(root), "-f", "fastapi", "-o", str(output), "--agent-view", str(agent_view)]
        if app is not None:
            arguments.extend(["--app", app])
        return arguments

    @staticmethod
    def _write_fastapi_source(root):
        (root / "main.py").write_text(
            "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef route():\n    return {'ok': True}\n",
            encoding="utf-8",
        )

    def test_C_1_static_fastapi_reuses_one_snapshot_for_analysis_graph_and_agent_view(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fastapi_source(root)
            output = root / "report.html"
            agent_view = root / "view.json"
            real_snapshot = cli.build_snapshot
            real_analyzer = cli.FastAPIAnalyzer
            real_builder = cli.ArchitectureGraphBuilder
            real_agent_view = cli.build_agent_view
            snapshots, analyzer_snapshots, builder_snapshots, agent_view_snapshots = [], [], [], []

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

            def agent_view_spy(*args, **kwargs):
                agent_view_snapshots.append(kwargs["snapshot"])
                return real_agent_view(*args, **kwargs)

            with patch.object(cli, "build_snapshot", side_effect=snapshot_spy), \
                    patch.object(cli, "FastAPIAnalyzer", StaticAnalyzerSpy), \
                    patch.object(cli, "ArchitectureGraphBuilder", GraphBuilderSpy), \
                    patch.object(cli, "build_agent_view", side_effect=agent_view_spy), \
                    patch.object(sys, "argv", self._arguments(root, output, agent_view)), \
                    contextlib.redirect_stdout(io.StringIO()):
                cli.main()

            self.assertEqual(len(snapshots), 1)
            snapshot, excluded_paths = snapshots[0]
            self.assertEqual(analyzer_snapshots, [snapshot])
            self.assertEqual(builder_snapshots, [snapshot])
            self.assertEqual(agent_view_snapshots, [snapshot])
            self.assertTrue({output.name, agent_view.name}.issubset({Path(path).name for path in excluded_paths}))

    def test_C_1_every_static_cli_mode_passes_its_single_snapshot_to_its_analyzer(self):
        class StopAfterAnalyzerConstruction(Exception):
            pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            snapshot = RepositorySnapshot(
                str(root), "agent_view.v3", (("main.py", "value = 1\n"),), (), "0" * 64,
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

    def test_C_1_selected_agent_view_profile_is_passed_to_snapshot_capture(self):
        class StopAfterAnalyzerConstruction(Exception):
            pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            profile_path = root / "profile.yaml"
            shutil.copyfile(cli.default_profile_path(), profile_path)
            profile_path.write_text(
                re.sub(r"(?m)^id:.*$", "id: custom-snapshot-profile", profile_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            selected_profile = cli.load_profile(profile_path)
            snapshot = RepositorySnapshot(
                str(root), "agent_view.v3", (("main.py", "value = 1\n"),), (), "0" * 64,
            )
            captured_profiles = []

            def build_snapshot_spy(*args, **kwargs):
                captured_profiles.append(kwargs["profile"])
                return snapshot

            class PythonAnalyzerSpy:
                def __init__(self, *args, **kwargs):
                    raise StopAfterAnalyzerConstruction

            arguments = [
                "code-analyzer", str(root), "-l", "python", "-o", str(root / "report.html"),
                "--agent-view", str(root / "view.json"), "--agent-view-profile", str(profile_path),
            ]
            with patch.object(cli, "build_snapshot", side_effect=build_snapshot_spy), \
                    patch.object(cli, "PythonGraphAnalyzer", PythonAnalyzerSpy), \
                    patch.object(sys, "argv", arguments), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    self.assertRaises(StopAfterAnalyzerConstruction):
                cli.main(file_lister=lambda *args, **kwargs: [])

            self.assertEqual(len(captured_profiles), 1)
            self.assertEqual(captured_profiles[0], selected_profile)

    def test_C_5_dynamic_fastapi_success_does_not_construct_a_static_analyzer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fastapi_source(root)
            dynamic_result = cli.FastAPIAnalyzer(str(root)).analyze()
            static_constructions = []
            rendered = []

            class DynamicSuccess:
                def __init__(self, project_path, app_import):
                    self.project_path = project_path
                    self.app_import = app_import

                def analyze(self):
                    return dynamic_result

            class StaticAnalyzerMustNotRun:
                def __init__(self, *args, **kwargs):
                    static_constructions.append((args, kwargs))
                    raise AssertionError("static fallback ran after dynamic success")

            class Renderer:
                def __init__(self, *args, **kwargs):
                    pass

                def render(self, architecture, output_path):
                    rendered.append(architecture)
                    return Path(output_path)

            with patch.object(cli, "DynamicFastAPIAnalyzer", DynamicSuccess), \
                    patch.object(cli, "FastAPIAnalyzer", StaticAnalyzerMustNotRun), \
                    patch.object(sys, "argv", self._arguments(root, root / "report.html", root / "view.json", "main:app")), \
                    contextlib.redirect_stdout(io.StringIO()):
                cli.main(renderer_factory=Renderer)

            self.assertEqual(static_constructions, [])
            self.assertEqual(rendered, [dynamic_result])

    def test_C_6_dynamic_fastapi_failure_uses_the_cli_snapshot_for_static_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fastapi_source(root)
            output = root / "report.html"
            agent_view = root / "view.json"
            real_snapshot = cli.build_snapshot
            real_static = cli.FastAPIAnalyzer
            real_builder = cli.ArchitectureGraphBuilder
            snapshots, static_snapshots, builder_snapshots = [], [], []

            def snapshot_spy(*args, **kwargs):
                snapshot = real_snapshot(*args, **kwargs)
                snapshots.append(snapshot)
                return snapshot

            class DynamicFailure:
                def __init__(self, project_path, app_import):
                    pass

                def analyze(self):
                    return None

            class StaticAnalyzerSpy:
                def __init__(self, *args, **kwargs):
                    static_snapshots.append(kwargs.get("snapshot"))
                    self._delegate = real_static(*args, **kwargs)

                def analyze(self):
                    return self._delegate.analyze()

            class GraphBuilderSpy:
                def __init__(self, *args, **kwargs):
                    builder_snapshots.append(kwargs.get("snapshot"))
                    self._delegate = real_builder(*args, **kwargs)

                def build_graph(self, architecture):
                    return self._delegate.build_graph(architecture)

            with patch.object(cli, "build_snapshot", side_effect=snapshot_spy), \
                    patch.object(cli, "DynamicFastAPIAnalyzer", DynamicFailure), \
                    patch.object(cli, "FastAPIAnalyzer", StaticAnalyzerSpy), \
                    patch.object(cli, "ArchitectureGraphBuilder", GraphBuilderSpy), \
                    patch.object(sys, "argv", self._arguments(root, output, agent_view, "main:app")), \
                    contextlib.redirect_stdout(io.StringIO()):
                cli.main()

            self.assertEqual(len(snapshots), 1)
            self.assertEqual(static_snapshots, snapshots)
            self.assertEqual(builder_snapshots, snapshots)


if __name__ == "__main__":
    unittest.main()
