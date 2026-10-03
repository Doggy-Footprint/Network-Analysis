"""Spec 7a2c91e6d80f4b35 v2: O6–O7 end-to-end CLI scenarios."""
import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import code_analyzer.cli as cli
from analysis.graph_metrics import GraphAnalyzer

from tests.nestjs_support import write_project
from analysis.edge_weights import load_edge_weights
from tests.edge_weights_support import weights_data, write_weights


NEST = """\
import { Module, Controller, Injectable, Get, Post } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
@Injectable() class S {}
@Controller('api') class C {
 constructor(s: S) {}
 @Get('ok') ok() {}
 @Post('ok') post() {}
 @Get(path) unknown() {}
}
@Module({controllers:[C], providers:[S], exports:[S]}) class Root {}
async function bootstrap(){ const app=await NestFactory.create(Root); }
export async function getOk(){return fetch('/api/ok');}
export async function postOk(){return fetch('/api/ok', {method:'POST'});}
export async function wrong(){return fetch('/api/ok', {method:'PUT'});}
"""
FASTAPI = "from fastapi import FastAPI\napp=FastAPI()\n@app.get('/other')\ndef other(): return {}\n"


class TestNestJSCli(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve() / "project"
        self.out = Path(temp.name).resolve() / "out"
        self.out.mkdir()
        write_project(self.root, {"src/main.ts": NEST, "main.py": FASTAPI})
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "src/main.ts", "main.py"], cwd=self.root, check=True)

    def cli(self, *flags, name="arch", output=True):
        labels = []
        original = cli.HTMLRenderer

        def factory(**kwargs):
            labels.append(kwargs.get("framework_label"))
            return original(**kwargs)

        arguments = [str(self.root), *flags, "-o", str(self.out / f"{name}.html")]
        if output:
            arguments.append("--json")
        stderr = io.StringIO()
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["code-analyzer", *arguments]), contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            try:
                cli.main(renderer_factory=factory)
                code = 0
            except SystemExit as error:
                code = error.code if isinstance(error.code, int) else 1
        self.last_stdout = stdout.getvalue()
        report = json.loads((self.out / f"{name}.json").read_text()) if code == 0 and output else None
        return code, stderr.getvalue(), report, labels

    def test_O6_ownership_in_both_orders_and_standalone(self):
        write_project(self.root, {"config.json": '{"api":true}',
                                  "src/main.ts": NEST + "\nexport function configProbe(){return 'api';}\n"})
        subprocess.run(["git", "add", "config.json", "src/main.ts"], cwd=self.root, check=True)
        _, _, ts_only, _ = self.cli("-l", "typescript", name="ts_only")
        expected_nodes = ts_only["nodes"]
        expected_edges = ts_only["edges"]
        self.assertIn("config:config.json:api", {n["id"] for n in expected_nodes})
        self.assertTrue(any(e["relation"] == "CONFIGURES" and e["from_id"] == "config:config.json:api" for e in expected_edges))
        expected_calls = None

        def source_fields(nodes):
            selected = copy.deepcopy(nodes)
            for node in selected:
                node.get("metadata", {}).pop("analysis", None)
            return selected

        for label, flags in [("alone", ("-f", "nestjs")), ("ts_first", ("-l", "typescript", "-f", "nestjs")), ("nest_first", ("-f", "nestjs", "-l", "typescript"))]:
            with self.subTest(label=label):
                code, err, report, labels = self.cli(*flags, name=label)
                self.assertEqual(code, 0, err)
                ids = [n["id"] for n in report["nodes"]]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertTrue(any(i.startswith("nestjs:") for i in ids))
                self.assertTrue(any(i.startswith("ts:") for i in ids))
                self.assertIn("NestJS", str(labels))
                if label != "alone":
                    self.assertEqual(source_fields([n for n in report["nodes"] if not n["id"].startswith("nestjs:")]), source_fields(expected_nodes))
                    self.assertEqual([e for e in report["edges"] if not e["from_id"].startswith("nestjs:")
                                      and not e["to_id"].startswith("nestjs:") and e["relation"] != "CALLS_ROUTE"], expected_edges)
                    for key, collection in ts_only["collections"].items():
                        self.assertEqual(report["collections"][key], collection)
                    calls = [e for e in report["edges"] if e["relation"] == "CALLS_ROUTE"]
                    if expected_calls is None:
                        expected_calls = calls
                    else:
                        self.assertEqual(calls, expected_calls)

    def assert_typescript_outputs_retained(self, report):
        write_project(self.root, {"config.json": '{"api":true}',
                                  "src/main.ts": NEST + "\nexport function configProbe(){return 'api';}\n"})
        subprocess.run(["git", "add", "config.json", "src/main.ts"], cwd=self.root, check=True)
        _, _, ts_only, _ = self.cli("-l", "typescript", name="ts_only_for_explicit")
        _, _, owned, _ = self.cli("-f", "nestjs", "-l", "typescript", name="owned_for_explicit")
        _, err, report_again, _ = self.cli("-f", "nestjs", "-l", "typescript", "--no-language-graph", name="explicit_again")

        def without_analysis(nodes):
            selected = copy.deepcopy([n for n in nodes if not n["id"].startswith("nestjs:")])
            for node in selected:
                node.get("metadata", {}).pop("analysis", None)
            return selected

        def internal_edges(edges):
            return [e for e in edges if not e["from_id"].startswith("nestjs:") and not e["to_id"].startswith("nestjs:")
                    and e["relation"] != "CALLS_ROUTE"]

        self.assertEqual(err, "")
        self.assertEqual(without_analysis(report_again["nodes"]), without_analysis(ts_only["nodes"]))
        self.assertEqual(internal_edges(report_again["edges"]), ts_only["edges"])
        self.assertEqual([e for e in report_again["edges"] if e["relation"] == "CALLS_ROUTE"],
                         [e for e in owned["edges"] if e["relation"] == "CALLS_ROUTE"])
        self.assertTrue(any(e["relation"] == "CONFIGURES" for e in report_again["edges"]))
        for key, collection in ts_only["collections"].items():
            self.assertEqual(report_again["collections"][key], collection)

    def test_O6_mixed_fastapi_and_flags(self):
        for name, flags in [
            ("mixed", ("-f", "fastapi", "-l", "typescript", "-f", "nestjs")),
            ("no_deps", ("-f", "nestjs", "--no-deps")),
            ("no_language", ("-f", "nestjs", "--no-language-graph")),
            ("no_models", ("-f", "nestjs", "--no-models")),
            ("explicit_language", ("-f", "nestjs", "-l", "typescript", "--no-language-graph")),
        ]:
            with self.subTest(name=name):
                code, err, report, _ = self.cli(*flags, name=name)
                self.assertEqual(code, 0, err)
                ids = [n["id"] for n in report["nodes"]]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertTrue(all(e["from_id"] in ids and e["to_id"] in ids for e in report["edges"]))
                if name == "no_deps":
                    self.assertFalse(any(i.startswith("nestjs:provider:") for i in ids))
                    self.assertFalse(any(e["relation"] in {"PROVIDES", "DEPENDS_ON", "EXPORTS"} for e in report["edges"] if e["from_id"].startswith("nestjs:")))
                    self.assertFalse(any(e["relation"] == "IMPLEMENTED_BY" and e["from_id"].startswith("nestjs:provider:") for e in report["edges"]))
                if name == "no_models":
                    _, _, plain, _ = self.cli("-f", "nestjs", name="plain_for_models")
                    self.assertEqual([n for n in report["nodes"] if n["id"].startswith("nestjs:")],
                                     [n for n in plain["nodes"] if n["id"].startswith("nestjs:")])
                    self.assertEqual([e for e in report["edges"] if e["from_id"].startswith("nestjs:")],
                                     [e for e in plain["edges"] if e["from_id"].startswith("nestjs:")])
                if name == "no_language":
                    self.assertFalse(any(i.startswith("ts:") for i in ids))
                    self.assertFalse(any(e["relation"] == "IMPLEMENTED_BY" for e in report["edges"]))
                if name == "explicit_language":
                    self.assertTrue(any(i.startswith("ts:") for i in ids))
                    self.assertFalse(any(e["relation"] == "IMPLEMENTED_BY" for e in report["edges"]))
                    self.assert_typescript_outputs_retained(report)
                if name == "mixed":
                    self.assertTrue(any(n["provenance"] == "fastapi" for n in report["nodes"]))

    def test_O6_mermaid_and_error_rules(self):
        code, err, _, _ = self.cli("-f", "nestjs", "--mermaid", name="mermaid", output=False)
        self.assertEqual(code, 0, err)
        self.assertIn("graph TD", self.last_stdout)
        for name in ("Root", "C", "S", "C.ok"):
            self.assertIn(name, self.last_stdout)
        for label, flags in [
            ("multi", ("-f", "nestjs", "-l", "typescript", "--mermaid")),
            ("entry", ("-f", "nestjs", "--entrypoint", "src/main.ts")),
            ("duplicate", ("-f", "nestjs", "-f", "nestjs")),
        ]:
            with self.subTest(label=label):
                code, _, _, _ = self.cli(*flags, name=label, output=False)
                self.assertNotEqual(code, 0)
        code, err, report, _ = self.cli("-f", "nestjs", "-f", "fastapi", "--entrypoint", "main.py", name="entry_with_fastapi")
        self.assertEqual(code, 0, err)
        self.assertTrue(any(n["provenance"] == "fastapi" for n in report["nodes"]))

    def test_O6_analysis_config_reaches_weighted_graph(self):
        weights = write_weights(self.out, weights_data(confidence={"framework_inferred": 0.5}), "weights.yaml")
        expected = load_edge_weights(weights)
        seen = []
        original = GraphAnalyzer.analyze

        def recording(analyzer, nodes, edges, project_path=None):
            if any(str(n.id).startswith("nestjs:") for n in nodes):
                seen.append(analyzer.config.edge_weights)
            return original(analyzer, nodes, edges, project_path)

        with patch.object(GraphAnalyzer, "analyze", recording):
            code, err, report, _ = self.cli("-f", "nestjs", "--edge-weights", str(weights), name="weighted")
            standalone_seen = list(seen)
            seen.clear()
            mixed_code, mixed_err, mixed_report, _ = self.cli("-f", "nestjs", "-l", "typescript", "--edge-weights", str(weights), name="weighted_mixed")
            mixed_seen = list(seen)
        self.assertEqual(code, 0, err)
        self.assertEqual(mixed_code, 0, mixed_err)
        for label, observed in (("standalone", standalone_seen), ("mixed", mixed_seen)):
            with self.subTest(label=label):
                self.assertTrue(observed)
                self.assertTrue(all(config == expected
                                    for config in observed))
        metrics = report["stats"]["analysis"]["node_metrics"].values()
        self.assertTrue(any(row["weighted_fan_in"] < row["fan_in"] for row in metrics))

    def test_O7_confirmed_method_unknown_and_language_omission(self):
        _, err, report, _ = self.cli("-f", "nestjs", "-l", "typescript", name="routing")
        self.assertEqual(err, "")
        routes = [e for e in report["edges"] if e["relation"] == "CALLS_ROUTE"]
        self.assertEqual(len(routes), 2)
        endpoint_ids = {n["id"] for n in report["nodes"] if n["id"].startswith("nestjs:endpoint:")}
        self.assertTrue(all(e["to_id"] in endpoint_ids for e in routes))
        self.assertTrue(all(e["from_id"] in {n["id"] for n in report["nodes"]} for e in routes))
        by_id = {n["id"]: n for n in report["nodes"]}
        self.assertEqual({(by_id[e["from_id"]]["label"], by_id[e["to_id"]]["metadata"]["http_method"],
                           by_id[e["to_id"]]["metadata"]["full_path"]) for e in routes},
                         {("getOk", "GET", "/api/ok"), ("postOk", "POST", "/api/ok")})
        for edge in routes:
            self.assertEqual(edge["resolution"], "unique_name")
            self.assertEqual(edge["confidence"], "framework_inferred")
            self.assertEqual(edge["candidates"], [])
            self.assertEqual(edge["metadata"]["framework_rule"]["id"], "http.client_calls_route")
        _, _, language_free, _ = self.cli("-f", "nestjs", "--no-language-graph", name="routing_free")
        self.assertFalse(any(e["relation"] == "CALLS_ROUTE" for e in language_free["edges"]))

    def test_O7_relative_route_without_bootstrap_is_not_matched(self):
        source = NEST.replace("async function bootstrap(){ const app=await NestFactory.create(Root); }", "")
        write_project(self.root, {"src/main.ts": source})
        subprocess.run(["git", "add", "src/main.ts"], cwd=self.root, check=True)
        _, _, report, _ = self.cli("-f", "nestjs", "-l", "typescript", name="no_bootstrap")
        self.assertFalse(any(e["relation"] == "CALLS_ROUTE" for e in report["edges"]))
        self.assertTrue(any(n["id"].startswith("nestjs:endpoint:") and n["metadata"]["relative_path"] == "/api/ok"
                            for n in report["nodes"]))

    def test_O7_duplicate_server_candidates_do_not_pick_arbitrarily(self):
        write_project(self.root, {"src/duplicate.ts": "import {Controller,Get,Module} from '@nestjs/common'; @Controller('api') class D {@Get('ok') ok(){}} @Module({controllers:[D]}) export class Extra {}"})
        old = "@Module({controllers:[C], providers:[S], exports:[S]})"
        self.assertIn(old, NEST)
        source = NEST.replace(old, "import {Extra} from './duplicate'; @Module({imports:[Extra],controllers:[C],providers:[S],exports:[S]})")
        write_project(self.root, {"src/main.ts": source})
        subprocess.run(["git", "add", "src/duplicate.ts", "src/main.ts"], cwd=self.root, check=True)
        _, _, report, _ = self.cli("-f", "nestjs", "-l", "typescript", name="duplicates")
        route_edges = [e for e in report["edges"] if e["relation"] == "CALLS_ROUTE"]
        ambiguous = [e for e in route_edges if e["resolution"] == "ambiguous"]
        get_candidates = sorted(n["id"] for n in report["nodes"] if n["id"].startswith("nestjs:endpoint:")
                                and n["metadata"].get("http_method") == "GET" and n["metadata"].get("full_path") == "/api/ok")
        self.assertEqual(len(get_candidates), 2)
        self.assertEqual(len(ambiguous), 1)
        edge = ambiguous[0]
        by_id = {n["id"]: n for n in report["nodes"]}
        self.assertEqual(by_id[edge["from_id"]]["label"], "getOk")
        self.assertEqual(edge["to_id"], get_candidates[0])
        self.assertEqual(edge["candidates"], get_candidates[1:])
        self.assertEqual(edge["confidence"], "framework_inferred")
        self.assertEqual(edge["metadata"]["framework_rule"]["id"], "http.client_calls_route")
