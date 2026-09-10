import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_view import read_file
from code_analyzer.cli import main, parse_args


class BottleneckArgumentContractTests(unittest.TestCase):
    def parse(self, arguments):
        with patch.object(sys, "argv", ["code-analyzer", ".", *arguments]):
            return parse_args()

    def test_bottleneck_arguments_are_accepted(self):
        args = self.parse([
            "--language", "python",
            "--bottlenecks", "result.json",
            "--harness-profile", "harness.json",
            "--observation-trace", "first.json",
            "--observation-trace", "second.json",
            "--agent-view-profile", "generation.json",
        ])

        self.assertEqual(args.bottlenecks, "result.json")
        self.assertEqual(args.observation_trace, ["first.json", "second.json"])
        self.assertEqual(args.agent_view_profile, "generation.json")

    def test_invalid_combinations_exit_two(self):
        cases = [
            (["--bottlenecks", "result.json", "--harness-profile", "harness.json"], "--language python"),
            (["--language", "python", "--bottlenecks", "result.json"], "--harness-profile"),
            (["--harness-profile", "harness.json"], "--bottlenecks"),
            (["--observation-trace", "trace.json"], "--bottlenecks"),
            (["--language", "python", "--bottlenecks", "result.json", "--harness-profile", "harness.json", "--agent-view-diff", "a.json", "b.json"], "cannot be combined"),
            (["--language", "python", "--output", "same.json", "--bottlenecks", "same.json", "--harness-profile", "harness.json"], "must be distinct"),
            (["--language", "python", "--agent-view", "same.json", "--bottlenecks", "same.json", "--harness-profile", "harness.json"], "must be distinct"),
        ]

        for arguments, message in cases:
            with self.subTest(arguments=arguments):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                    self.parse(arguments)
                self.assertEqual(raised.exception.code, 2)
                self.assertIn(message, stderr.getvalue())


class BottleneckRunContractTests(unittest.TestCase):
    def run_cli(self, project, arguments, *, files, renderer=None):
        reads = []
        writes = {}

        def reader(path):
            resolved = Path(path).resolve()
            reads.append(resolved)
            if resolved in files:
                return files[resolved]
            return read_file(resolved)

        def lister(root, *, tracked_files_only=True):
            return "injected", [path.relative_to(root).as_posix() for path in files if path.is_relative_to(root)]

        def writer(path, text):
            writes[Path(path).resolve()] = text

        class Renderer:
            def __init__(self, **kwargs):
                pass

            def render(self, architecture, output):
                return Path(output)

        with patch.object(sys, "argv", ["code-analyzer", str(project), *arguments]):
            with contextlib.redirect_stdout(io.StringIO()):
                main(
                    file_lister=lister,
                    file_reader=reader,
                    file_writer=writer,
                    renderer_factory=renderer or Renderer,
                )
        return reads, writes

    def test_one_injected_snapshot_excludes_every_requested_output(self):
        root = Path(__file__).resolve().parents[1]
        harness_path = root / "profiles" / "harness.fixed-baseline.v1.json"
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            source = project / "app.py"
            outputs = [
                project / ".arch.html",
                project / ".arch_assets" / "data.json",
                project / ".bottlenecks.json",
                project / ".agent-view.json",
            ]
            files = {
                source: "def answer():\n    return 42\n",
                harness_path.resolve(): harness_path.read_text(encoding="utf-8"),
                **{path: "stale generated content" for path in outputs},
            }
            arguments = [
                "--language", "python",
                "--output", str(project / ".arch.html"),
                "--agent-view", str(project / ".agent-view.json"),
                "--bottlenecks", str(project / ".bottlenecks.json"),
                "--harness-profile", str(harness_path),
            ]

            with patch("code_analyzer.cli.GraphAnalyzer.analyze", side_effect=AssertionError("filesystem analysis used")):
                reads, writes = self.run_cli(project, arguments, files=files)

            self.assertIn(source, reads)
            for output in outputs:
                self.assertNotIn(output, reads)
            payload = json.loads(writes[(project / ".bottlenecks.json").resolve()])
            self.assertEqual(payload["schema"], "bottlenecks.v1")
            self.assertEqual(payload["snapshot"]["file_count"], 1)
            self.assertIn((project / ".agent-view.json").resolve(), writes)

    def test_invalid_traces_exit_one_before_renderer_or_report_write(self):
        root = Path(__file__).resolve().parents[1]
        harness_path = root / "profiles" / "harness.fixed-baseline.v1.json"
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            class Renderer:
                def __init__(self, **kwargs):
                    raise AssertionError("renderer called before input validation")

            cases = [
                (None, "$ must be an object"),
                ([], "$ must be an object"),
                ({}, "schema"),
                ({"schema": "unknown.v1", "events": []}, "schema"),
                ({"schema": "harness_observation.v1"}, "missing required fields"),
            ]
            for index, (payload, message) in enumerate(cases):
                with self.subTest(payload=payload):
                    trace = project / f"bad-trace-{index}.json"
                    files = {
                        project / "app.py": "value = 1\n",
                        harness_path.resolve(): harness_path.read_text(encoding="utf-8"),
                        trace: json.dumps(payload),
                    }
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                        self.run_cli(project, [
                            "--language", "python",
                            "--bottlenecks", str(project / "result.json"),
                            "--harness-profile", str(harness_path),
                            "--observation-trace", str(trace),
                        ], files=files, renderer=Renderer)

                    self.assertEqual(raised.exception.code, 1)
                    self.assertIn(message, stderr.getvalue())

    def test_output_failure_exits_one_without_traceback(self):
        root = Path(__file__).resolve().parents[1]
        harness_path = root / "profiles" / "harness.fixed-baseline.v1.json"
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            files = {
                project / "app.py": "value = 1\n",
                harness_path.resolve(): harness_path.read_text(encoding="utf-8"),
            }

            def failed_writer(path, text):
                raise OSError("injected write failure")

            stderr = io.StringIO()
            with patch.object(sys, "argv", [
                "code-analyzer", str(project), "--language", "python",
                "--bottlenecks", str(project / "result.json"),
                "--harness-profile", str(harness_path),
            ]), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    main(
                        file_lister=lambda root, **kwargs: ("injected", ["app.py"]),
                        file_reader=lambda path: files.get(Path(path).resolve()),
                        file_writer=failed_writer,
                        renderer_factory=lambda **kwargs: type(
                            "Renderer", (), {"render": lambda self, arch, output: Path(output)}
                        )(),
                    )

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("injected write failure", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
