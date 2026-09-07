import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import analysis
from code_analyzer.cli import main, parse_args


class RemovedCliArgumentsTests(unittest.TestCase):
    def test_removed_arguments_are_rejected_by_argparse(self):
        removed_arguments = [
            ["--diagnostics"],
            ["--diagnostics-output", "diagnostics.json"],
            ["--graph-cost-config", "costs.json"],
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


class PhaseBCliArgumentTests(unittest.TestCase):
    def parse(self, arguments):
        with patch.object(sys, "argv", ["code-analyzer", ".", *arguments]):
            return parse_args()

    def test_phase_b_arguments_are_accepted(self):
        args = self.parse([
            "--phase-b", "scenarios.json", "--phase-b-out", "cost.json",
            "--exploration-policy", "policy.yaml", "--cost-weights", "weights.yaml",
            "--seed-queries", "seeds.json", "--samples", "12", "--seed", "7",
        ])

        self.assertEqual(args.phase_b, "scenarios.json")
        self.assertEqual(args.phase_b_out, "cost.json")
        self.assertEqual(args.exploration_policy, "policy.yaml")
        self.assertEqual(args.cost_weights, "weights.yaml")
        self.assertEqual(args.seed_queries, "seeds.json")
        self.assertEqual(args.samples, 12)
        self.assertEqual(args.seed, 7)

    def test_phase_b_out_defaults(self):
        self.assertEqual(self.parse(["--phase-b", "scenarios.json"]).phase_b_out, "phase_b_cost.json")

    def test_each_companion_flag_without_phase_b_exits_with_code_two(self):
        companions = [
            ["--phase-b-out", "cost.json"],
            ["--exploration-policy", "policy.yaml"],
            ["--cost-weights", "weights.yaml"],
            ["--seed-queries", "seeds.json"],
            ["--samples", "12"],
            ["--seed", "7"],
        ]

        for arguments in companions:
            with self.subTest(arguments=arguments):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        self.parse(arguments)
                self.assertEqual(raised.exception.code, 2)
                self.assertIn(arguments[0], stderr.getvalue())
                self.assertIn("--phase-b", stderr.getvalue())

    def test_non_positive_sample_count_is_rejected(self):
        for value in ("0", "-1"):
            with self.subTest(value=value):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        self.parse(["--phase-b", "scenarios.json", "--samples", value])

                self.assertEqual(raised.exception.code, 2)
                self.assertIn("--samples", stderr.getvalue())


class PhaseBCliRunTests(unittest.TestCase):
    maxDiff = None

    def run_cli(self, directory, extra):
        root = Path(__file__).resolve().parents[1]
        output = Path(directory) / "cost.json"
        arguments = [
            "code-analyzer", str(root / "examples" / "realworld_app"),
            "-o", str(Path(directory) / "arch.html"),
            "--phase-b", str(root / "fixtures" / "scenarios.v1.json"),
            "--phase-b-out", str(output),
            "--seed-queries", str(root / "fixtures" / "seed_queries.v1.json"),
            "--samples", "3",
            *extra,
        ]
        with patch.object(sys, "argv", arguments):
            with contextlib.redirect_stdout(io.StringIO()):
                main()
        return output

    def test_phase_b_writes_the_report_where_told_without_agent_view(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.run_cli(directory, ["--seed", "11"])

            self.assertTrue(output.is_file())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "phase_b_cost.v1")
            self.assertEqual(len(payload["scenarios"]), 3)
            self.assertEqual(payload["scenarios"][0]["sample_count"], 3)
            self.assertIsNone(payload["scenarios"][0]["converged"])
            self.assertFalse((Path(directory) / "view.json").exists())

    def test_phase_b_also_works_alongside_agent_view(self):
        with tempfile.TemporaryDirectory() as directory:
            view = Path(directory) / "view.json"
            output = self.run_cli(directory, ["--seed", "11", "--agent-view", str(view)])

            self.assertTrue(view.is_file())
            self.assertEqual(json.loads(view.read_text(encoding="utf-8"))["schema_version"], "3")
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["schema"], "phase_b_cost.v1"
            )

    def test_seed_reaches_the_run_and_changes_the_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self.run_cli(directory, ["--seed", "11"]).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            same = self.run_cli(directory, ["--seed", "11"]).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            other = self.run_cli(directory, ["--seed", "12"]).read_text(encoding="utf-8")

        self.assertEqual(first, same)
        self.assertNotEqual(first, other)
        self.assertEqual(json.loads(first)["scenarios"][0]["seed"], 11)
        self.assertEqual(json.loads(other)["scenarios"][0]["seed"], 12)

    def test_sample_count_reaches_the_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(__file__).resolve().parents[1]
            output = Path(directory) / "cost.json"
            arguments = [
                "code-analyzer", str(root / "examples" / "realworld_app"),
                "-o", str(Path(directory) / "arch.html"),
                "--phase-b", str(root / "fixtures" / "scenarios.v1.json"),
                "--phase-b-out", str(output),
                "--samples", "5", "--seed", "11",
            ]
            with patch.object(sys, "argv", arguments):
                with contextlib.redirect_stdout(io.StringIO()):
                    main()

            payload = json.loads(output.read_text(encoding="utf-8"))
            for scenario in payload["scenarios"]:
                self.assertEqual(scenario["sample_count"], 5)


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


if __name__ == "__main__":
    unittest.main()
