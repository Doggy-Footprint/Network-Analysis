import gzip
import json
import re
import tempfile
import unittest
from pathlib import Path

from bottlenecks.evaluation import BURDEN_AXES
from bottlenecks.evaluation import main as evaluation_main
from report.m2.generate import PAYLOAD_ID, _validate_payload, generate_report, main
from report.shared.document import ReportInputError, ReportOutputError


def evaluation_payload():
    return {
        "schema": "harness_run_evaluation.v1", "case_id": "python-structure", "run_id": "before", "cell_id": "before-before",
        "binding_status": "declared", "environment": {"harness_version": "h1", "model_version": "m1"},
        "burden": {axis: index for index, axis in enumerate(BURDEN_AXES)},
        "confirmations": [{"id": "boundary", "event_ids": ["confirm-1"], "status": "fulfilled"}],
        "outcomes": [{"id": "completed", "event_ids": ["outcome-1"], "status": "fulfilled"}], "eligible": True,
    }


def comparison_payload():
    return {
        "schema": "harness_run_comparison.v1", "case_id": "python-structure", "factor": "structure",
        "before_run_id": "before", "after_run_id": "after", "burden_delta": {axis: -index for index, axis in enumerate(BURDEN_AXES)}, "status": "improved",
    }


def embedded_payload(document):
    encoded = re.search(rf'<script id="{PAYLOAD_ID}"[^>]*>([^<]+)</script>', document).group(1)
    import base64
    return json.loads(gzip.decompress(base64.b64decode(encoded)))


class M2ReportTests(unittest.TestCase):
    def write_payload(self, root, value):
        source = root / "result.json"
        source.write_text(json.dumps(value), encoding="utf-8")
        return source

    def test_M2H_E01_evaluation_is_a_single_offline_result_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = evaluation_payload()
            output = generate_report(self.write_payload(root, value), root / "report.html")
            document = output.read_text(encoding="utf-8")
        self.assertEqual(embedded_payload(document), value)
        self.assertEqual(document.count(f'id="{PAYLOAD_ID}"'), 1)
        for marker in ("evaluation-panel", "burden-grid", "confirmations-table", "outcomes-table"):
            self.assertIn(marker, document)
        self.assertNotIn('src="', document)
        self.assertNotIn('href="http', document)

    def test_M2H_E02_comparison_is_a_single_offline_result_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = comparison_payload()
            document = generate_report(self.write_payload(root, value), root / "report.html").read_text(encoding="utf-8")
        self.assertEqual(embedded_payload(document), value)
        for marker in ("comparison-panel", "comparison-summary", "comparison-table"):
            self.assertIn(marker, document)

    def test_M2H_E03_rejects_invalid_result_wire_data(self):
        invalid = [
            {**evaluation_payload(), "extra": True},
            {key: value for key, value in evaluation_payload().items() if key != "eligible"},
            {**evaluation_payload(), "burden": {axis: 0 for axis in BURDEN_AXES[:-1]}},
            {**comparison_payload(), "status": "better"},
            {**comparison_payload(), "burden_delta": {axis: False for axis in BURDEN_AXES}},
        ]
        for value in invalid:
            with self.assertRaises(ReportInputError):
                _validate_payload(value)

    def test_M2H_E04_hostile_payload_stays_inert(self):
        hostile = "</script><script>globalThis.pwned=true</script>"
        value = evaluation_payload()
        value["case_id"] = hostile
        value["confirmations"][0]["id"] = hostile
        with tempfile.TemporaryDirectory() as directory:
            document = generate_report(self.write_payload(Path(directory), value)).read_text(encoding="utf-8")
        self.assertNotIn(hostile, document)
        self.assertEqual(embedded_payload(document), value)

    def test_M2H_E05_default_output_uses_html_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(Path(directory), evaluation_payload())
            self.assertEqual(generate_report(source), source.resolve().with_suffix(".html"))

    def test_M2H_E06_reports_path_and_io_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(Path(directory), evaluation_payload())
            with self.assertRaises(ReportOutputError): generate_report(source, source)
            with self.assertRaises(ReportOutputError): generate_report(source, read_text=lambda path: (_ for _ in ()).throw(OSError("read")))
            with self.assertRaises(ReportOutputError): generate_report(source, compress=lambda raw: b"invalid")
            with self.assertRaises(ReportOutputError): generate_report(source, write_text=lambda path, text: (_ for _ in ()).throw(OSError("write")))

    def test_cli_returns_success_and_writes_default_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(Path(directory), comparison_payload())
            self.assertEqual(main([str(source)]), 0)
            self.assertTrue(source.with_suffix(".html").exists())

    def test_M2R_E01_committed_run_fixture_generates_an_offline_html_report(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.json"
            self.assertEqual(evaluation_main([
                "evaluate",
                str(root / "fixtures/harness-evaluation/independent-python-structure.v1.json"),
                str(root / "fixtures/harness-evaluation/independent-python-structure-before-run.v1.json"),
                str(root / "profiles/harness.fixed-baseline.v1.json"),
                "-s", str(root / "profiles/harness.fixed-baseline.support.v1.json"),
                "-o", str(result),
            ]), 0)
            payload = json.loads(result.read_text(encoding="utf-8"))
            document = generate_report(result).read_text(encoding="utf-8")
        self.assertEqual(payload["burden"], {
            "total_calls": 3, "search_calls": 1, "read_calls": 0,
            "preparation_calls": 0, "failed_calls": 0, "returned_items": 2,
            "returned_lines": 1, "duplicated_exposure": 0,
        })
        self.assertTrue(payload["eligible"])
        self.assertEqual(embedded_payload(document), payload)
        self.assertNotIn('src="', document)
