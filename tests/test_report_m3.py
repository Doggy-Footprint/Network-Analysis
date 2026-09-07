import base64
import copy
import gzip
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from discovery.graph_view import GraphView
from discovery.models import Scenario, SeedQuerySet, SeedTerm
from discovery.montecarlo import run_scenario
from discovery.policy import default_policy_path, load_exploration_policy
from discovery.report import build_report, report_to_json
from discovery.weights import default_weights_path, load_cost_weights
from agent_view.profile import default_profile_path, load_profile
from report.m3.generate import generate_report
from report.shared.document import ReportInputError, ReportOutputError
from tests.discovery_graph_fixture import build_graph

import dataclasses

PAYLOAD_ID = "phase-b-cost-payload"


def _embedded_payload(html):
    matches = re.findall(rf'<script id="{PAYLOAD_ID}"[^>]*>([^<]+)</script>', html)
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one payload, got {len(matches)}")
    return json.loads(gzip.decompress(base64.b64decode(matches[0])))


def _assert_offline(test_case, html):
    executable = re.sub(rf'(<script id="{PAYLOAD_ID}"[^>]*>)[^<]+(</script>)', r"\1\2", html)
    for api in ("fetch", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon", "importScripts"):
        test_case.assertIsNone(re.search(rf"\b{api}\b", executable), api)
    test_case.assertIsNone(re.search(r"\bimport\s*\(", executable), "dynamic import")
    test_case.assertIsNone(
        re.search(r"(?:https?|wss?|ftp)://|(?<!:)//[^/\s]", executable, re.IGNORECASE), "network scheme"
    )
    test_case.assertIsNone(
        re.search(r"<(?:script|link|img|iframe|audio|video|source)\b[^>]*\b(?:src|href)\s*=", executable, re.IGNORECASE),
        "external resource attribute",
    )


def _payload():
    graph = build_graph()
    view = GraphView(graph)
    policy = dataclasses.replace(
        load_exploration_policy(default_policy_path()),
        repo_map_enabled=False,
        bootstrap_resamples=20,
    )
    weights = load_cost_weights(default_weights_path())
    scenario = Scenario("s", "t", ("n:a1", "n:a2"), (SeedTerm("alpha", "content"),))
    result = run_scenario(view, scenario, policy, weights, samples=8, seed=5)
    seed_set = SeedQuerySet(
        source="cache",
        terms=(SeedTerm("alpha", "content"),),
        generator={
            "model_id": "hand-written", "revision": "1", "backend": "none",
            "prompt_id": "p", "prompt": "prompt", "decoding": {},
            "fixture_sha256": "b" * 64, "raw_output": "content:alpha",
        },
    )
    return build_report(
        graph, view, [result], load_profile(default_profile_path()), policy, weights, {"s": seed_set}
    )


class ReportContractTests(unittest.TestCase):
    def setUp(self):
        self.value = _payload()

    def write_payload(self, root, value=None):
        source = root / "phase_b_cost.json"
        source.write_text(report_to_json(value if value is not None else self.value), encoding="utf-8")
        return source

    def test_report_is_a_single_offline_file_carrying_the_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.write_payload(root)
            stderr = io.StringIO()

            output = generate_report(source, root / "report.html", stderr=stderr)

            html = output.read_text(encoding="utf-8")
            self.assertEqual(_embedded_payload(html), self.value)
            self.assertEqual(html.count(f'id="{PAYLOAD_ID}"'), 1)
            _assert_offline(self, html)
            self.assertNotIn("warning:", stderr.getvalue())

    def test_report_renders_the_required_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = generate_report(self.write_payload(root), root / "report.html")

            html = output.read_text(encoding="utf-8")
            for marker in (
                "시나리오별 비용", "이 실행이 소비한 버전 스탬프", "축별 분포",
                "discovery timeline", "closure", "invariants", "versions-table",
            ):
                self.assertIn(marker, html)

    def test_output_defaults_to_the_input_name_and_rejects_overwriting_the_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.write_payload(root)

            output = generate_report(source)

            self.assertEqual(output, source.resolve().with_suffix(".html"))
            with self.assertRaises(ReportOutputError):
                generate_report(source, source)

    def test_wrong_schema_and_malformed_json_are_typed_input_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrong = copy.deepcopy(self.value)
            wrong["schema"] = "phase_b_cost.v2"
            with self.assertRaises(ReportInputError):
                generate_report(self.write_payload(root, wrong), root / "a.html")

            malformed = root / "malformed.json"
            malformed.write_text("{", encoding="utf-8")
            with self.assertRaises(ReportInputError):
                generate_report(malformed, root / "b.html")

    def test_structurally_invalid_payloads_are_rejected(self):
        mutations = []

        missing_axis = copy.deepcopy(self.value)
        del missing_axis["scenarios"][0]["percentiles"]["p50"]["axes"]["revisits"]
        mutations.append(missing_axis)

        unsorted_versions = copy.deepcopy(self.value)
        unsorted_versions["versions"] = list(reversed(unsorted_versions["versions"]))
        mutations.append(unsorted_versions)

        nested_version = copy.deepcopy(self.value)
        nested_version["versions"][0] = {"id": "cost_weights", "version": "1", "scope": "profile"}
        mutations.append(nested_version)

        bad_phase = copy.deepcopy(self.value)
        bad_phase["scenarios"][0]["percentiles"]["p5"]["execution_sequence"][0]["phase"] = "C"
        mutations.append(bad_phase)

        unknown_axis = copy.deepcopy(self.value)
        unknown_axis["scenarios"][0]["percentiles"]["p5"]["execution_sequence"][0]["cost_delta"]["nope"] = 1
        mutations.append(unknown_axis)

        no_scenarios = copy.deepcopy(self.value)
        no_scenarios["scenarios"] = []
        mutations.append(no_scenarios)

        missing_percentile = copy.deepcopy(self.value)
        del missing_percentile["scenarios"][0]["percentiles"]["p95"]
        mutations.append(missing_percentile)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, mutation in enumerate(mutations):
                with self.subTest(index=index):
                    with self.assertRaises(ReportInputError):
                        generate_report(self.write_payload(root, mutation), root / f"bad-{index}.html")

    def test_template_write_and_compression_failures_are_typed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.write_payload(root)
            source_text = source.read_text(encoding="utf-8")

            def fail_template(path):
                if path.name == source.name:
                    return source_text
                raise OSError("template")

            with self.assertRaises(ReportOutputError):
                generate_report(source, root / "a.html", read_text=lambda path: (_ for _ in ()).throw(OSError("read")))
            with self.assertRaises(ReportOutputError):
                generate_report(source, root / "b.html", read_text=fail_template)
            with self.assertRaises(ReportOutputError):
                generate_report(source, root / "c.html", compress=lambda raw: b"not-gzip")
            with self.assertRaises(ReportOutputError):
                generate_report(source, root / "d.html", write_text=lambda path, text: (_ for _ in ()).throw(OSError("write")))

    def test_bootstrap_ci_may_be_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = copy.deepcopy(self.value)
            for name in ("p5", "p50", "p95"):
                value["scenarios"][0]["percentiles"][name]["bootstrap_ci"] = None

            output = generate_report(self.write_payload(root, value), root / "report.html")

            self.assertEqual(_embedded_payload(output.read_text(encoding="utf-8")), value)

    @unittest.skipUnless(shutil.which("node"), "node is required to run the browser bootstrap")
    def test_browser_bootstrap_resolves_phase_b_payload_and_sets_schema_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = generate_report(self.write_payload(root)).read_text(encoding="utf-8")
            encoded = re.search(rf'<script id="{PAYLOAD_ID}"[^>]*>([^<]+)</script>', html).group(1)
            bootstrap = re.search(
                r'</script>\s*<script>\s*((?:.|\n)*?)</script>', html[html.index(f'id="{PAYLOAD_ID}"'):]
            ).group(1)
            driver = (
                "globalThis.window=globalThis;"
                'const status={textContent:"",className:""};'
                "globalThis.CustomEvent=class {constructor(name, options){this.name=name;this.detail=options.detail;}};"
                f"globalThis.document={{getElementById:(id)=>id==={json.dumps(PAYLOAD_ID)}?{{textContent:{json.dumps(encoded)}}}:status,dispatchEvent:()=>{{}}}};"
                f"eval({json.dumps(bootstrap)});"
                "ReportReady.then(graph=>console.log(JSON.stringify({payload:graph,schema:graph.schema,status:status.textContent})))"
                ".catch(error=>{console.error(error);process.exit(1);});"
            )
            result = subprocess.run(["node", "-"], input=driver, text=True, capture_output=True, check=True)
            state = json.loads(result.stdout)

            self.assertEqual(state["payload"], self.value)
            self.assertEqual(state["schema"], "phase_b_cost.v1")
            self.assertIn("phase_b_cost.v1", state["status"])


class CostModelTests(unittest.TestCase):
    def test_cost_model_builds_timelines_axes_and_closure_bars(self):
        value = _payload()
        model_path = Path(__file__).resolve().parents[1] / "report" / "m3" / "templates" / "cost_model.js"
        driver = (
            f"const model=require({json.dumps(str(model_path))});"
            f"const data={json.dumps(value)};"
            "const built=model.build(data);"
            "const scenario=built.scenarios[0];"
            "console.log(JSON.stringify({"
            "axes:scenario.axes.map(a=>a.axis),"
            "timelines:scenario.timelines.map(t=>t.percentile),"
            "steps:scenario.timelines[1].steps.length,"
            "bars:scenario.weightedBars.map(b=>b.label),"
            "closureShareWithinOne:scenario.axes.every(a=>a.closureShare<=1),"
            "meanKeys:scenario.axes.every(a=>typeof a.mean===\"number\"&&typeof a.stdev===\"number\"),"
            "versions:built.versions.length"
            "}));"
        )
        result = subprocess.run(["node", "-"], input=driver, text=True, capture_output=True, check=True)
        payload = json.loads(result.stdout)

        self.assertEqual(payload["axes"], list(model_axes()))
        self.assertEqual(payload["timelines"], ["p5", "p50", "p95"])
        self.assertEqual(payload["bars"], ["p5", "p50", "p95", "closure"])
        self.assertEqual(
            payload["steps"],
            len(value["scenarios"][0]["percentiles"]["p50"]["execution_sequence"]),
        )
        self.assertTrue(payload["closureShareWithinOne"])
        self.assertTrue(payload["meanKeys"])
        self.assertEqual(payload["versions"], 12)


def model_axes():
    from report.m3.generate import AXES

    return AXES


if __name__ == "__main__":
    unittest.main()
