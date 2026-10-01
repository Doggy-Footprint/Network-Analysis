"""Spec 7a2c91e6d80f4b35 v2: O8–O9, O11–O12 boundaries and quality."""
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from language_analyzers.core.serialization import architecture_to_dict
from language_analyzers.typescript.analyzer import IGNORED_DIRECTORIES, SOURCE_EXTENSIONS
from repository import RepositorySnapshot
from renderers.html import HTMLRenderer

from tests.nestjs_support import analyze, diagnostics, fixture, framework_edges, framework_nodes, write_project


REPO = Path(__file__).resolve().parents[1]
BASELINES = Path(__file__).parent / "nestjs_evidence" / "baselines.json"


def cli_bytes(root, *flags, seed="0"):
    with tempfile.TemporaryDirectory() as temp:
        output = Path(temp) / "report.html"
        bottle = Path(temp) / "bottlenecks.json"
        environment = dict(os.environ, PYTHONHASHSEED=seed)
        command = [sys.executable, "-c", "from code_analyzer.cli import main; main()", str(root), *flags,
                   "-o", str(output), "--json", "--bottlenecks", str(bottle)]
        result = subprocess.run(command, cwd=REPO, env=environment, capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(f"CLI exit {result.returncode}: {result.stderr}")
        return output.with_suffix(".json").read_bytes(), bottle.read_bytes()


class TestSnapshotAndErrors(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def snapshot(self, files):
        return RepositorySnapshot(str(self.root), "snapshot.v1", tuple(sorted(files.items())), (), "0" * 64)

    def test_O8_snapshot_survives_changed_deleted_files_without_source_access(self):
        files = {
            "src/a.ts": "import {Module} from '@nestjs/common'; import {B} from './b'; @Module({imports:[B]}) export class A {}",
            "src/b.ts": "import {Module} from '@nestjs/common'; @Module({}) export class B {}",
        }
        write_project(self.root, files)
        captured = self.snapshot(files)
        expected = architecture_to_dict(analyze(self.root, snapshot=captured, language=True))
        (self.root / "src/a.ts").write_text("invalid changed text", encoding="utf-8")
        (self.root / "src/b.ts").unlink()
        with mock.patch.object(Path, "rglob", side_effect=AssertionError("source discovery")), \
                mock.patch.object(Path, "glob", side_effect=AssertionError("source discovery")), \
                mock.patch.object(Path, "iterdir", side_effect=AssertionError("source discovery")), \
                mock.patch.object(Path, "exists", side_effect=AssertionError("source path existence")), \
                mock.patch.object(Path, "is_file", side_effect=AssertionError("source path existence")), \
                mock.patch.object(Path, "read_text", side_effect=AssertionError("source read")), \
                mock.patch.object(Path, "read_bytes", side_effect=AssertionError("source read")), \
                mock.patch.object(os, "walk", side_effect=AssertionError("source discovery")):
            actual = architecture_to_dict(analyze(self.root, snapshot=captured, language=True))
        self.assertEqual(actual, expected)

    def test_O8_relative_and_mismatched_snapshot_roots_raise_valueerror(self):
        snapshot = self.snapshot({})
        for root in [Path("relative"), self.root / "other"]:
            with self.subTest(root=root), self.assertRaises(ValueError):
                analyze(root, snapshot=snapshot)

    def test_O8_source_suffix_and_excluded_directory_parity_with_typescript(self):
        files = {f"src/broken{suffix}": "function (" for suffix in SOURCE_EXTENSIONS}
        files.update({f"{directory}/ignored.ts": "function (" for directory in IGNORED_DIRECTORIES})
        files[".hidden/ignored.ts"] = "function ("
        files["src/ignored.py"] = "function ("
        write_project(self.root, files)
        arch = analyze(self.root, language=False)
        syntax_paths = {d["span"]["file_path"] for d in diagnostics(arch) if d["code"] == "syntax_error"}
        self.assertEqual(syntax_paths, {f"src/broken{suffix}" for suffix in SOURCE_EXTENSIONS})

    def test_O8_invalid_file_is_skipped_and_valid_file_survives(self):
        write_project(self.root, {
            "good.ts": "import {Module} from '@nestjs/common'; @Module({}) class Good {}",
            "bad.ts": "import {Module} from '@nestjs/common'; @Module({ class Broken {",
        })
        arch = analyze(self.root, language=False)
        self.assertEqual({n.label for n in framework_nodes(arch, "module")}, {"Good"})
        self.assertIn("syntax_error", {d["code"] for d in diagnostics(arch)})

    def test_O8_empty_project_and_no_repository_execution(self):
        write_project(self.root, {"main.ts": "import {Module} from '@nestjs/common'; @Module({}) class Root {}"})
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("repository execution")), \
                mock.patch.object(subprocess, "Popen", side_effect=AssertionError("repository execution")), \
                mock.patch("os.system", side_effect=AssertionError("repository execution")):
            arch = analyze(self.root, language=False)
        self.assertEqual({n.label for n in framework_nodes(arch, "module")}, {"Root"})
        (self.root / "main.ts").unlink()
        empty = analyze(self.root, language=False)
        self.assertFalse(framework_nodes(empty))
        self.assertFalse(framework_edges(empty))


class TestOutput(unittest.TestCase):
    def test_O9_schema_provenance_evidence_reports_and_integrity(self):
        arch = analyze(fixture(), language=True)
        data = architecture_to_dict(arch)
        self.assertEqual(data["schema_version"], "5")
        ids = {n["id"] for n in data["nodes"]}
        self.assertEqual(len(ids), len(data["nodes"]))
        for node in data["nodes"]:
            if node["id"].startswith("nestjs:"):
                self.assertRegex(node["id"], r"^nestjs:(application|module|controller|provider|endpoint):[^#]+#.+$")
                self.assertFalse(node["id"].split(":", 2)[2].startswith("/"))
        for node in data["nodes"]:
            if node["id"].startswith("nestjs:"):
                self.assertEqual(node["provenance"], "nestjs")
                self.assertIsNotNone(node["span"])
                self.assertGreater(node["cost"]["token_estimate"], 0)
        for edge in data["edges"]:
            self.assertIn(edge["from_id"], ids)
            self.assertIn(edge["to_id"], ids)
            if edge["from_id"].startswith("nestjs:"):
                self.assertIsNotNone(edge["evidence"])
                self.assertEqual(edge["confidence"], "framework_inferred")
                self.assertEqual(edge["resolution"], "exact")
                self.assertTrue(edge["metadata"]["framework_rule"]["id"].startswith("nestjs."))
        by_id = {n["id"]: n for n in data["nodes"]}
        self.assertIn(("ApplicationModule", "INCLUDES"),
                      {(by_id[e["to_id"]]["label"], e["relation"]) for e in data["edges"]
                       if e["from_id"].startswith("nestjs:application:")})
        implementation_edges = [e for e in data["edges"] if e["relation"] == "IMPLEMENTED_BY"]
        source_symbols = {
            "src/app.module.ts": {"module": ["ApplicationModule"]},
            "src/app.controller.ts": {"controller": ["AppController"], "endpoint": ["AppController.root"]},
            "src/article/article.module.ts": {"module": ["ArticleModule"]},
            "src/article/article.controller.ts": {
                "controller": ["ArticleController"],
                "endpoint": ["ArticleController.findAll", "ArticleController.getFeed", "ArticleController.findOne",
                             "ArticleController.findComments", "ArticleController.create", "ArticleController.update",
                             "ArticleController.delete", "ArticleController.createComment", "ArticleController.deleteComment",
                             "ArticleController.favorite", "ArticleController.unFavorite"],
            },
            "src/article/article.service.ts": {"provider": ["ArticleService"]},
            "src/profile/profile.module.ts": {"module": ["ProfileModule"]},
            "src/profile/profile.controller.ts": {
                "controller": ["ProfileController"],
                "endpoint": ["ProfileController.getProfile", "ProfileController.follow", "ProfileController.unFollow"],
            },
            "src/profile/profile.service.ts": {"provider": ["ProfileService"]},
            "src/tag/tag.module.ts": {"module": ["TagModule"]},
            "src/tag/tag.controller.ts": {"controller": ["TagController"], "endpoint": ["TagController.findAll"]},
            "src/tag/tag.service.ts": {"provider": ["TagService"]},
            "src/shared/pipes/validation.pipe.ts": {"provider": ["ValidationPipe"]},
            "src/user/user.module.ts": {"module": ["UserModule"]},
            "src/user/user.controller.ts": {
                "controller": ["UserController"],
                "endpoint": ["UserController.findMe", "UserController.update", "UserController.create",
                             "UserController.delete", "UserController.login"],
            },
            "src/user/user.service.ts": {"provider": ["UserService"]},
            "src/user/auth.middleware.ts": {"provider": ["AuthMiddleware"]},
        }
        expected_targets = {
            f"nestjs:{kind}:{path}#{name}": f"ts:{path}#{name}"
            for path, kinds in source_symbols.items()
            for kind, names in kinds.items()
            for name in names
        }
        observed_targets = {}
        application_edges = []
        for edge in implementation_edges:
            source_id = edge["from_id"]
            self.assertIn(source_id, by_id)
            self.assertIn(edge["to_id"], by_id)
            self.assertTrue(edge["to_id"].startswith("ts:"))
            if source_id.startswith("nestjs:application:"):
                application_edges.append(edge)
                continue
            source_identifier = source_id.split("@", 1)[0]
            self.assertNotIn(source_identifier, observed_targets)
            observed_targets[source_identifier] = edge["to_id"]
        self.assertEqual(observed_targets, expected_targets)
        self.assertEqual(len(application_edges), 1)
        self.assertEqual(application_edges[0]["to_id"], "ts:src/main.ts#bootstrap")
        self.assertEqual(len(implementation_edges), len([n for n in data["nodes"] if n["id"].startswith("nestjs:")]))
        self.assertEqual({c.key for c in arch.report_collections if c.key.startswith("nestjs_")},
                         {"nestjs_modules", "nestjs_controllers", "nestjs_providers", "nestjs_endpoints", "nestjs_diagnostics"})
        self.assertEqual(len(framework_nodes(arch, "endpoint")), 21)
        for diagnosis in diagnostics(arch):
            self.assertTrue({"code", "span", "expression", "reason"} <= diagnosis.keys())
        for kind in ["application", "module", "controller", "provider", "endpoint"]:
            self.assertEqual(arch.stats["nestjs"][kind], len(framework_nodes(arch, kind)))

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.html"
            HTMLRenderer().render(arch, str(path))
            html = path.read_text(encoding="utf-8")
            for title in ("Modules", "Controllers", "Providers", "Endpoints", "Diagnostics"):
                self.assertIn(title, html)
            for source_text in ("ApplicationModule", "ArticleController", "UserService", "/api/articles/:slug", "TypeOrmModule.forRoot"):
                self.assertIn(source_text, html)

    def test_O9_call_and_decorator_locations_make_ids_unique(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            write_project(root, {"main.ts": """\
import {Module, Controller, Get, Post} from '@nestjs/common';
import {NestFactory} from '@nestjs/core';
@Controller('x') class C { @Get('a') @Post('b') route() {} }
@Module({controllers:[C]}) class Root {}
async function first(){const app=await NestFactory.create(Root);}
async function second(){const app=await NestFactory.create(Root);}
"""})
            arch = analyze(root, language=False)
            for kind, count in [("application", 2), ("endpoint", 2)]:
                nodes = framework_nodes(arch, kind)
                self.assertEqual(len(nodes), count)
                self.assertEqual(len({n.id for n in nodes}), count)
                self.assertEqual(len({(n.span.start_line, n.span.start_col) for n in nodes}), count)

    def test_O9_missing_bootstrap_has_classified_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            write_project(root, {"main.ts": "import {Module,Controller,Get} from '@nestjs/common'; @Controller() class C {@Get() route(){}} @Module({controllers:[C]}) class Root {}"})
            arch = analyze(root, language=False)
            self.assertIn("bootstrap_unresolved", {d["code"] for d in diagnostics(arch)})


class TestRegression(unittest.TestCase):
    def test_O11_characterization_existing_standalone_outputs_are_byte_identical(self):
        """Characterization of pre-existing standalone adapters at base commit."""
        baseline = json.loads(BASELINES.read_text(encoding="utf-8"))
        self.assertEqual(baseline["hash_seed"], "0")
        self.assertEqual(len(baseline["cases"]), 8)
        for case in baseline["cases"]:
            with self.subTest(case=case["name"]):
                project = REPO / case["relative_project"]
                outputs = cli_bytes(project, *case["flags"], seed="0")
                for name, content in zip(("json", "bottlenecks"), outputs):
                    portable = content.replace(str(REPO).encode(), b"<REPO_ROOT>")
                    self.assertEqual(hashlib.sha256(portable).hexdigest(), case["hashes"][name])
                    if str(REPO) == baseline["captured_root"]:
                        self.assertEqual(hashlib.sha256(content).hexdigest(), case["raw_hashes"][name])

    def test_O12_repeated_and_hash_seeded_json_and_bottlenecks(self):
        first = cli_bytes(fixture(), "-f", "nestjs", seed="0")
        self.assertEqual(first, cli_bytes(fixture(), "-f", "nestjs", seed="0"))
        for seed in ("1", "42"):
            with self.subTest(seed=seed):
                self.assertEqual(first, cli_bytes(fixture(), "-f", "nestjs", seed=seed))

    def test_O12_reversed_snapshot_inventory_and_graph_integrity(self):
        root = fixture().resolve()
        sources = tuple(sorted((str(p.relative_to(root)), p.read_text(encoding="utf-8"))
                               for p in root.rglob("*.ts") if "node_modules" not in p.parts))
        one = RepositorySnapshot(str(root), "snapshot.v1", sources, (), "0" * 64)
        two = RepositorySnapshot(str(root), "snapshot.v1", tuple(reversed(sources)), (), "0" * 64)
        left = architecture_to_dict(analyze(root, snapshot=one, language=False))
        right = architecture_to_dict(analyze(root, snapshot=two, language=False))
        self.assertEqual(left, right)
        ids = {n["id"] for n in left["nodes"]}
        self.assertTrue(all(e["from_id"] in ids and e["to_id"] in ids for e in left["edges"]))

    def test_O12_no_reverse_imports_in_language_common_or_renderers(self):
        roots = [REPO / "language_analyzers", REPO / "analysis", REPO / "renderers"]
        violations = []
        for root in roots:
            for path in root.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        violations.extend(str(path) for alias in node.names if alias.name.startswith("framework_analyzers.nestjs"))
                    elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("framework_analyzers.nestjs"):
                        violations.append(str(path))
        self.assertEqual(violations, [])
