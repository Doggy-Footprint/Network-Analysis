"""Spec 485e71fc64c8a984 v1, CLI surface.

VO1 (decision table): -f/-l argv rules observed through parse_args exit codes and through the
  dashboard framework_label captured from the renderer factory (label order == analyzer order).
VO5 (scenario): merged FastAPI + TypeScript + Android run on a scratch git repository.
VO6 (equivalence partitioning): each single-analyzer run has no CALLS_ROUTE and no route_matching.
VO7 (metamorphic): the same merged run twice yields identical JSON and bottlenecks bytes.
Expected values are hand-derived from the spec or built by composing single-analyzer runs.
"""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import code_analyzer.cli as cli
from code_analyzer.cli import parse_args

FASTAPI_SOURCE = """\
from fastapi import FastAPI, APIRouter, Depends
from pydantic import BaseModel

router = APIRouter()
app = FastAPI()


class UserOut(BaseModel):
    id: int


def get_db():
    return {}


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db=Depends(get_db)):
    return {"id": user_id}


@router.post("/users")
def create_user(db=Depends(get_db)):
    return {}


app.include_router(router, prefix="/api")
"""

TS_SOURCE = """\
export async function loadUser(id: string) {
  return fetch(`/api/users/${id}`);
}

export async function createUser() {
  return fetch("/api/users", { method: "POST" });
}

export function ghost() {
  return fetch("/nowhere");
}

export function dynamicUrl(url: string) {
  return fetch(url);
}
"""

RETROFIT_SOURCE = """\
package com.example.core.network

import retrofit2.http.GET
import retrofit2.http.Path

interface UserApi {
    @GET("api/users/{userId}")
    suspend fun getUser(@Path("userId") id: String): String
}
"""

ROOM_SOURCE = """\
package com.example.core.database.model

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "topics")
data class TopicEntity(
    @PrimaryKey
    val id: String,
    val name: String,
)
"""

HILT_SOURCE = """\
package com.example.core.data.di

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides
    fun providesName(): String {
        return "x"
    }
}
"""

COMPOSE_SOURCE = """\
package com.example.feature.topic

import androidx.compose.runtime.Composable

@Composable
fun TopicRoute() {
    TopicScreen()
}

@Composable
fun TopicScreen() {
}
"""

PROJECT_FILES = {
    "main.py": FASTAPI_SOURCE,
    "client.ts": TS_SOURCE,
    "core_network/src/main/kotlin/com/example/core/network/UserApi.kt": RETROFIT_SOURCE,
    "core_database/src/main/kotlin/com/example/core/database/model/TopicEntity.kt": ROOM_SOURCE,
    "core_data/src/main/kotlin/com/example/core/data/di/NetworkModule.kt": HILT_SOURCE,
    "feature_topic/src/main/kotlin/com/example/feature/topic/TopicScreen.kt": COMPOSE_SOURCE,
}


class CliFixture(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        base = Path(self._directory.name).resolve()
        self.root = base / "proj"
        self.out = base / "out"
        self.out.mkdir()
        self.write_project(PROJECT_FILES)

    def write_project(self, files):
        for relative, text in files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "add", *files], cwd=self.root, check=True)

    def run_main(self, *arguments, factory=None):
        """Returns (exit code, stdout, stderr, labels captured from the renderer factory)."""
        labels = []
        real = cli.HTMLRenderer

        def capturing_factory(**kwargs):
            labels.append(kwargs.get("framework_label"))
            return real(**kwargs)

        stdout, stderr = io.StringIO(), io.StringIO()
        code = 0
        with patch.object(sys, "argv", ["code-analyzer", *arguments]):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    cli.main(renderer_factory=factory or capturing_factory)
                except SystemExit as request:
                    code = 0 if request.code is None else request.code
        return code, stdout.getvalue(), stderr.getvalue(), labels

    def run_json(self, *flags, bottlenecks=False, name="architecture"):
        arguments = [str(self.root), *flags, "-o", str(self.out / f"{name}.html"), "--json"]
        if bottlenecks:
            arguments += ["--bottlenecks", str(self.out / f"{name}_b.json")]
        code, _, stderr, labels = self.run_main(*arguments)
        self.assertEqual(code, 0, stderr)
        exported = json.loads((self.out / f"{name}.json").read_text(encoding="utf-8"))
        return exported, labels

    def parse_exit_code(self, *arguments):
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["code-analyzer", str(self.root), *arguments]):
            with contextlib.redirect_stderr(stderr):
                try:
                    parse_args()
                except SystemExit as request:
                    return request.code, stderr.getvalue()
        return None, stderr.getvalue()


def node_ids(exported):
    return [node["id"] for node in exported["nodes"]]


def edge_keys(exported, *, without_route=True):
    return [
        (edge["from_id"], edge["to_id"], edge["relation"])
        for edge in exported["edges"]
        if not (without_route and edge["relation"] == "CALLS_ROUTE")
    ]


def route_edges(exported):
    return [edge for edge in exported["edges"] if edge["relation"] == "CALLS_ROUTE"]


def server_ids(exported):
    """FastAPI endpoint nodes: metadata carries full_path and http_method."""
    found = {}
    for node in exported["nodes"]:
        metadata = node["metadata"]
        if "full_path" in metadata and "http_method" in metadata and node["group"] != "retrofit_endpoint":
            found[(metadata["http_method"], metadata["full_path"])] = node["id"]
    return found


class TestVO1ArgvDecisionTable(CliFixture):
    """Rules: none; -l only; -f only; -f+-l mixed; order preserved; duplicate value;
    mermaid+multi; entrypoint with/without fastapi; mermaid single."""

    def assert_labels(self, argv, expected_label):
        code, _, stderr, labels = self.run_main(str(self.root), *argv, "-o", str(self.out / "a.html"))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(labels, [expected_label], argv)

    def test_rule_none_defaults_to_fastapi_only(self):
        self.assert_labels([], "FastAPI")

    def test_rule_language_only_runs_that_language_only(self):
        self.assert_labels(["-l", "python"], "Python")
        self.assert_labels(["-l", "typescript"], "TypeScript/JavaScript")

    def test_rule_framework_only_runs_that_framework_only(self):
        self.assert_labels(["-f", "android"], "Android")
        self.assert_labels(["-f", "fastapi"], "FastAPI")

    def test_rule_mixed_framework_and_language(self):
        self.assert_labels(["-f", "fastapi", "-l", "typescript"], "FastAPI + TypeScript/JavaScript")

    def test_rule_order_preserved_language_before_framework(self):
        self.assert_labels(["-l", "typescript", "-f", "fastapi"], "TypeScript/JavaScript + FastAPI")

    def test_rule_order_preserved_interleaved_three_analyzers(self):
        self.assert_labels(
            ["-l", "kotlin", "-f", "fastapi", "-l", "typescript"],
            "Kotlin + FastAPI + TypeScript/JavaScript",
        )
        self.assert_labels(
            ["-l", "typescript", "-l", "python", "-f", "android"],
            "TypeScript/JavaScript + Python + Android",
        )

    def test_rule_order_preserved_two_frameworks_and_two_languages(self):
        self.assert_labels(["-f", "android", "-f", "fastapi"], "Android + FastAPI")
        self.assert_labels(["-l", "kotlin", "-l", "typescript"], "Kotlin + TypeScript/JavaScript")

    def test_rule_duplicate_value_is_a_parser_error(self):
        for argv in (
            ["-f", "fastapi", "-f", "fastapi"],
            ["-l", "python", "-l", "python"],
            ["-f", "android", "-f", "fastapi", "-f", "android"],
            ["-l", "typescript", "-f", "fastapi", "-l", "typescript"],
        ):
            with self.subTest(argv=argv):
                code, _ = self.parse_exit_code(*argv)
                self.assertEqual(code, 2)

    def test_rule_duplicate_value_through_main_analyzes_nothing(self):
        code, _, _, labels = self.run_main(
            str(self.root), "-f", "fastapi", "-f", "fastapi", "-o", str(self.out / "a.html")
        )
        self.assertEqual(code, 2)
        self.assertEqual(labels, [])
        self.assertEqual(list(self.out.iterdir()), [])

    def test_rule_mermaid_with_multiple_analyzers_is_a_parser_error(self):
        for argv in (
            ["-f", "fastapi", "-f", "android", "--mermaid"],
            ["-f", "fastapi", "-l", "typescript", "--mermaid"],
            ["-l", "python", "-l", "typescript", "--mermaid"],
        ):
            with self.subTest(argv=argv):
                code, _ = self.parse_exit_code(*argv)
                self.assertEqual(code, 2)

    def test_rule_mermaid_with_multiple_analyzers_analyzes_nothing(self):
        code, _, _, labels = self.run_main(
            str(self.root), "-f", "fastapi", "-f", "android", "--mermaid", "-o", str(self.out / "a.html")
        )
        self.assertEqual(code, 2)
        self.assertEqual(labels, [])
        self.assertEqual(list(self.out.iterdir()), [])

    def test_rule_mermaid_with_single_analyzer_is_accepted(self):
        code, stdout, stderr, labels = self.run_main(
            str(self.root), "-f", "fastapi", "--mermaid", "-o", str(self.out / "a.html")
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(labels, ["FastAPI"])
        self.assertIn("Mermaid Architecture Diagram", stdout)

    def test_rule_entrypoint_with_fastapi_among_frameworks_is_accepted(self):
        for argv in (
            ["-e", "main.py"],
            ["-f", "fastapi", "-e", "main.py"],
            ["-f", "fastapi", "-l", "typescript", "-e", "main.py"],
            ["-l", "typescript", "-f", "fastapi", "-e", "main.py"],
            ["-f", "android", "-f", "fastapi", "-e", "main.py"],
        ):
            with self.subTest(argv=argv):
                code, stderr = self.parse_exit_code(*argv)
                self.assertIsNone(code, stderr)

    def test_rule_entrypoint_without_fastapi_is_a_parser_error(self):
        for argv in (
            ["-l", "typescript", "-e", "main.py"],
            ["-f", "android", "-e", "main.py"],
            ["-l", "python", "-f", "android", "-e", "main.py"],
        ):
            with self.subTest(argv=argv):
                code, stderr = self.parse_exit_code(*argv)
                self.assertEqual(code, 2)
                self.assertIn("--entrypoint", stderr)


class TestVO5MergedRun(CliFixture):
    MERGED = ["-f", "fastapi", "-l", "typescript", "-f", "android"]

    def merged(self, **kwargs):
        return self.run_json(*self.MERGED, **kwargs)

    def test_label_joins_labels_in_argv_order(self):
        _, labels = self.merged()
        self.assertEqual(labels, ["FastAPI + TypeScript/JavaScript + Android"])

    def test_json_contains_calls_route_edges_from_ts_and_retrofit_to_fastapi(self):
        exported, _ = self.merged()
        servers = server_ids(exported)
        get_user, create_user = servers[("GET", "/api/users/{user_id}")], servers[("POST", "/api/users")]
        retrofit = [n["id"] for n in exported["nodes"] if n["group"] == "retrofit_endpoint"]
        self.assertEqual(len(retrofit), 1)
        actual = sorted((e["from_id"], e["to_id"]) for e in route_edges(exported))
        expected = sorted([
            ("ts:client.ts#loadUser", get_user),
            ("ts:client.ts#createUser", create_user),
            (retrofit[0], get_user),
        ])
        self.assertEqual(actual, expected)
        for edge in route_edges(exported):
            self.assertEqual(edge["confidence"], "framework_inferred")
            self.assertEqual(edge["resolution"], "unique_name")
            self.assertEqual(edge["candidates"], [])

    def test_stats_route_matching_counts_every_client_outcome(self):
        exported, _ = self.merged()
        self.assertEqual(
            exported["stats"]["route_matching"],
            {"matched": 3, "ambiguous": 0, "unmatched": 1, "unresolvable": 1},
        )

    def test_nodes_and_edges_are_the_single_runs_concatenated_in_argv_order(self):
        merged, _ = self.merged()
        fastapi, _ = self.run_json("-f", "fastapi", name="s_fastapi")
        typescript, _ = self.run_json("-l", "typescript", name="s_ts")
        android, _ = self.run_json("-f", "android", name="s_android")
        self.assertEqual(node_ids(merged), node_ids(fastapi) + node_ids(typescript) + node_ids(android))
        self.assertEqual(
            edge_keys(merged),
            edge_keys(fastapi) + edge_keys(typescript) + edge_keys(android),
        )
        reordered, _ = self.run_json("-l", "typescript", "-f", "android", "-f", "fastapi", name="reordered")
        self.assertEqual(node_ids(reordered), node_ids(typescript) + node_ids(android) + node_ids(fastapi))

    def test_report_collections_are_concatenated(self):
        merged, _ = self.merged()
        singles = [
            self.run_json("-f", "fastapi", name="c_fastapi")[0],
            self.run_json("-l", "typescript", name="c_ts")[0],
            self.run_json("-f", "android", name="c_android")[0],
        ]
        expected_keys = []
        for single in singles:
            expected_keys += [key for key in single["collections"] if key not in expected_keys]
        self.assertEqual(list(merged["collections"]), expected_keys)
        for single in singles:
            for key, collection in single["collections"].items():
                owners = [s for s in singles if key in s["collections"]]
                if len(owners) == 1:
                    self.assertEqual(merged["collections"][key]["rows"], collection["rows"], key)

    def test_stats_analysis_covers_the_merged_graph_once(self):
        exported, _ = self.merged()
        metrics = exported["stats"]["analysis"]["node_metrics"]
        servers = server_ids(exported)
        for node_id in ("ts:client.ts#loadUser", servers[("GET", "/api/users/{user_id}")]):
            self.assertIn(node_id, metrics)
        retrofit = next(n["id"] for n in exported["nodes"] if n["group"] == "retrofit_endpoint")
        self.assertIn(retrofit, metrics)
        self.assertGreaterEqual(metrics["ts:client.ts#loadUser"]["fan_out"], 1)
        self.assertGreaterEqual(metrics[servers[("POST", "/api/users")]]["fan_in"], 1)

    def test_bottlenecks_node_count_equals_merged_node_count(self):
        exported, _ = self.merged(bottlenecks=True)
        report = json.loads((self.out / "architecture_b.json").read_text(encoding="utf-8"))
        self.assertEqual(report["schema"], "bottlenecks.v3")
        self.assertEqual(report["dependency_network"]["node_count"], len(exported["nodes"]))
        self.assertGreater(len(exported["nodes"]), 0)

    def test_no_flags_apply_to_every_framework_analyzer(self):
        for flag in ("--no-models", "--no-deps", "--no-language-graph"):
            with self.subTest(flag=flag):
                fastapi_plain, _ = self.run_json("-f", "fastapi", name="fp")
                android_plain, _ = self.run_json("-f", "android", name="ap")
                fastapi_flag, _ = self.run_json("-f", "fastapi", flag, name="ff")
                android_flag, _ = self.run_json("-f", "android", flag, name="af")
                self.assertNotEqual(node_ids(fastapi_flag), node_ids(fastapi_plain), "fixture guard: fastapi")
                self.assertNotEqual(node_ids(android_flag), node_ids(android_plain), "fixture guard: android")
                merged, _ = self.run_json("-f", "fastapi", "-f", "android", flag, name="mf")
                self.assertEqual(node_ids(merged), node_ids(fastapi_flag) + node_ids(android_flag))

    def reference_node_ids(self, *flags):
        reference = self.out.parent / "reference"
        reference.mkdir(exist_ok=True)
        code, _, stderr, _ = self.run_main(
            str(self.root), *flags, "-o", str(reference / "r.html"), "--json"
        )
        self.assertEqual(code, 0, stderr)
        return node_ids(json.loads((reference / "r.json").read_text(encoding="utf-8")))

    def test_duplicate_node_id_across_analyzers_fails_without_outputs(self):
        earlier = self.reference_node_ids("-f", "android")
        later = self.reference_node_ids("-l", "kotlin")
        seen = set(earlier)
        first_duplicate = next(node_id for node_id in later if node_id in seen)
        self.assertTrue(first_duplicate.startswith("kotlin:"))
        code, _, stderr, labels = self.run_main(
            str(self.root), "-f", "android", "-l", "kotlin", "-o", str(self.out / "architecture.html"),
            "--json", "--bottlenecks", str(self.out / "b.json"), "--bottlenecks-html", str(self.out / "b.html"),
        )
        self.assertEqual(code, 1)
        self.assertEqual(
            stderr.strip(), f"[!] Error: duplicate node id across analyzers: {first_duplicate}"
        )
        self.assertEqual(list(self.out.iterdir()), [])

    def test_first_duplicate_follows_merge_order_when_argv_order_is_reversed(self):
        earlier = self.reference_node_ids("-l", "kotlin")
        later = self.reference_node_ids("-f", "android")
        seen = set(earlier)
        first_duplicate = next(node_id for node_id in later if node_id in seen)
        code, _, stderr, _ = self.run_main(
            str(self.root), "-l", "kotlin", "-f", "android", "-o", str(self.out / "architecture.html"),
        )
        self.assertEqual(code, 1)
        self.assertEqual(
            stderr.strip(), f"[!] Error: duplicate node id across analyzers: {first_duplicate}"
        )
        self.assertEqual(list(self.out.iterdir()), [])


class TestVO6SingleAnalyzerRuns(CliFixture):
    """Equivalence partitions: fastapi, android, python, kotlin, typescript (plus the default).
    The project contains client calls and Retrofit endpoints, so a leaked matching pass would show."""

    PARTITIONS = {
        "fastapi": ["-f", "fastapi"],
        "android": ["-f", "android"],
        "python": ["-l", "python"],
        "kotlin": ["-l", "kotlin"],
        "typescript": ["-l", "typescript"],
        "default": [],
    }

    def test_single_runs_have_no_calls_route_and_no_route_matching(self):
        for name, flags in self.PARTITIONS.items():
            with self.subTest(partition=name):
                exported, _ = self.run_json(*flags, bottlenecks=True, name=name)
                self.assertEqual(route_edges(exported), [])
                self.assertNotIn("route_matching", exported["stats"])
                report = json.loads((self.out / f"{name}_b.json").read_text(encoding="utf-8"))
                self.assertNotIn("CALLS_ROUTE", json.dumps(report))
                self.assertEqual(report["dependency_network"]["node_count"], len(exported["nodes"]))

    def test_single_runs_label_is_the_plain_analyzer_label(self):
        expected = {"fastapi": "FastAPI", "android": "Android", "python": "Python",
                    "kotlin": "Kotlin", "typescript": "TypeScript/JavaScript", "default": "FastAPI"}
        for name, flags in self.PARTITIONS.items():
            with self.subTest(partition=name):
                _, labels = self.run_json(*flags, name=name)
                self.assertEqual(labels, [expected[name]])


class TestVO7Determinism(CliFixture):
    def test_repeated_merged_runs_write_identical_bytes(self):
        flags = ["-f", "fastapi", "-l", "typescript", "-f", "android"]
        self.run_json(*flags, bottlenecks=True)
        first = ((self.out / "architecture.json").read_bytes(), (self.out / "architecture_b.json").read_bytes())
        for leftover in list(self.out.iterdir()):
            if leftover.is_file():
                leftover.unlink()
        self.run_json(*flags, bottlenecks=True)
        second = ((self.out / "architecture.json").read_bytes(), (self.out / "architecture_b.json").read_bytes())
        self.assertTrue(first[0] and first[1])
        self.assertIn(b"CALLS_ROUTE", first[0])
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
