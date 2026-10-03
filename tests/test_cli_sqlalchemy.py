"""Spec 1620f5318bc5dd4e v1, CLI surface.

VO5 (decision table) rules over `cli.main` on a tmp git project with models, revisions and a FastAPI app:
  D1 `-f sqlalchemy` alone, D2 + --no-language-graph, D3 + --no-models, D4 `-f fastapi -f sqlalchemy`,
  D5 `-f sqlalchemy -f fastapi`, D6 `-l python -f sqlalchemy`, D7 `-f fastapi --no-language-graph -f sqlalchemy`,
  D8 `--entrypoint` with sqlalchemy only -> exit 2, D9 `-f sqlalchemy --mermaid` -> exit 0 and `graph`.
  Observations: exit code, node id uniqueness, python-core presence, IMPLEMENTED_BY targets exist,
  MIGRATES present/absent.
VO7 (equivalence partitioning, the parts not covered by the existing suite): `-f android` on a Room project
  without migrations has no room_migration nodes, no MIGRATES edges, no migration_matching stats key and no
  "Room Migrations" collection; single `-f fastapi` / `-l python` runs on a project containing models and
  revisions emit no sqlalchemy nodes and no MIGRATES.
VO8 (metamorphic): the two QR2 run variants written twice are byte-identical.
Expected values are hand-derived from FR1, FR9, FR10, FR12, C13, C14, C15 and QR2.
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

MODELS = """\
from sqlalchemy import Column, Integer
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)


class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
"""

REVISION_1 = """\
from alembic import op
import sqlalchemy as sa

revision = "r1"
down_revision = None


def upgrade():
    op.create_table("users", sa.Column("id", sa.Integer()))
    op.create_foreign_key("fk", "posts", "users", ["uid"], ["id"])


def downgrade():
    op.drop_table("users")
"""

REVISION_2 = """\
from alembic import op
import sqlalchemy as sa

revision = "r2"
down_revision = "r1"


def upgrade():
    op.add_column("posts", sa.Column("title", sa.String()))
"""

MAIN = """\
from fastapi import FastAPI

app = FastAPI()


@app.get("/users")
def list_users():
    return []
"""

ROOM_ENTITY = """\
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

PROJECT_FILES = {
    "main.py": MAIN,
    "app/models.py": MODELS,
    "alembic/versions/0001_init.py": REVISION_1,
    "alembic/versions/0002_title.py": REVISION_2,
}

ANDROID_FILES = {
    "core_database/src/main/kotlin/com/example/core/database/model/TopicEntity.kt": ROOM_ENTITY,
}

SQLA_GROUPS = ("sqlalchemy_model", "alembic_migration")


class CliFixture(unittest.TestCase):
    files = PROJECT_FILES

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        base = Path(self._directory.name).resolve()
        self.root = base / "proj"
        self.out = base / "out"
        self.out.mkdir()
        for relative, text in self.files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "add", *self.files], cwd=self.root, check=True)

    def run_main(self, *arguments):
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
                    cli.main(renderer_factory=capturing_factory)
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


def by_id(exported):
    return {node["id"]: node for node in exported["nodes"]}


def python_core(exported):
    return [node for node in exported["nodes"] if node["provenance"] == "python-core"]


def relation(exported, name):
    return [edge for edge in exported["edges"] if edge["relation"] == name]


def sqla_nodes(exported):
    return [node for node in exported["nodes"] if node["group"] in SQLA_GROUPS]


class TestVO5DecisionTable(CliFixture):
    def assert_unique_ids(self, exported):
        ids = [node["id"] for node in exported["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))

    def assert_implemented_by_reach_python_core(self, exported):
        nodes = by_id(exported)
        mine = sqla_nodes(exported)
        self.assertEqual(len([n for n in mine if n["group"] == "sqlalchemy_model"]), 2)
        self.assertEqual(len([n for n in mine if n["group"] == "alembic_migration"]), 2)
        links = {}
        for edge in relation(exported, "IMPLEMENTED_BY"):
            if edge["from_id"] in {n["id"] for n in mine}:
                links.setdefault(edge["from_id"], []).append(edge["to_id"])
        for node in mine:
            self.assertEqual(len(links.get(node["id"], [])), 1, node["id"])
            target = nodes[links[node["id"]][0]]
            self.assertEqual(target["provenance"], "python-core", node["id"])
            if node["group"] == "sqlalchemy_model":
                self.assertEqual(target["kind"], "class")
                self.assertEqual(target["span"]["file_path"], "app/models.py")
                self.assertEqual(target["id"].rsplit("#", 1)[-1], node["id"].rsplit("_", 1)[-1])
            else:
                self.assertEqual(target["kind"], "module")
                self.assertEqual(target["span"]["file_path"], node["span"]["file_path"])

    def assert_migrates(self, exported):
        nodes = by_id(exported)
        edges = relation(exported, "MIGRATES")
        self.assertGreaterEqual(len(edges), 3)
        for edge in edges:
            self.assertEqual(nodes[edge["from_id"]]["group"], "alembic_migration")
            self.assertEqual(nodes[edge["to_id"]]["group"], "sqlalchemy_model")
        self.assertEqual(
            sorted({(nodes[e["from_id"]]["span"]["file_path"], e["to_id"].rsplit("_", 1)[-1]) for e in edges}),
            [
                ("alembic/versions/0001_init.py", "Post"),
                ("alembic/versions/0001_init.py", "User"),
                ("alembic/versions/0002_title.py", "Post"),
            ],
        )

    def test_D1_sqlalchemy_alone_includes_language_graph(self):
        exported, labels = self.run_json("-f", "sqlalchemy")
        self.assertEqual(labels, ["SQLAlchemy"])
        self.assert_unique_ids(exported)
        self.assertTrue(python_core(exported))
        self.assert_implemented_by_reach_python_core(exported)
        self.assert_migrates(exported)
        self.assertFalse([n for n in exported["nodes"] if n["provenance"] == "fastapi"])
        self.assertEqual(
            exported["stats"]["migration_matching"],
            {"matched": 3, "ambiguous": 0, "unmatched": 0, "unresolvable": 0},
        )

    def test_D2_no_language_graph_drops_python_core_and_implemented_by(self):
        exported, _ = self.run_json("-f", "sqlalchemy", "--no-language-graph")
        self.assertEqual(python_core(exported), [])
        self.assertEqual(relation(exported, "IMPLEMENTED_BY"), [])
        self.assert_unique_ids(exported)
        self.assert_migrates(exported)

    def test_D3_no_models_keeps_migrations_without_edges(self):
        exported, _ = self.run_json("-f", "sqlalchemy", "--no-models")
        groups = {n["group"] for n in exported["nodes"]}
        self.assertNotIn("sqlalchemy_model", groups)
        self.assertEqual(len([n for n in exported["nodes"] if n["group"] == "alembic_migration"]), 2)
        self.assertEqual(relation(exported, "MIGRATES"), [])

    def merged(self, *flags):
        exported, labels = self.run_json(*flags)
        single, _ = self.run_json("-l", "python", name="python_only")
        self.assert_unique_ids(exported)
        core_ids = [n["id"] for n in python_core(exported)]
        self.assertEqual(sorted(core_ids), sorted(n["id"] for n in python_core(single)))
        self.assertEqual(len(core_ids), len(set(core_ids)))
        self.assert_implemented_by_reach_python_core(exported)
        self.assert_migrates(exported)
        return exported, labels

    def test_D4_fastapi_then_sqlalchemy(self):
        exported, labels = self.merged("-f", "fastapi", "-f", "sqlalchemy")
        self.assertEqual(labels, ["FastAPI + SQLAlchemy"])
        self.assertTrue([n for n in exported["nodes"] if n["provenance"] == "fastapi"])

    def test_D5_sqlalchemy_then_fastapi(self):
        exported, labels = self.merged("-f", "sqlalchemy", "-f", "fastapi")
        self.assertEqual(labels, ["SQLAlchemy + FastAPI"])
        self.assertTrue([n for n in exported["nodes"] if n["provenance"] == "fastapi"])

    def test_D6_python_language_then_sqlalchemy(self):
        _, labels = self.merged("-l", "python", "-f", "sqlalchemy")
        self.assertEqual(labels, ["Python + SQLAlchemy"])

    def test_D7_global_no_language_graph_with_fastapi_and_sqlalchemy(self):
        exported, _ = self.run_json("-f", "fastapi", "--no-language-graph", "-f", "sqlalchemy")
        self.assert_unique_ids(exported)
        self.assertEqual(python_core(exported), [])
        self.assertEqual(relation(exported, "IMPLEMENTED_BY"), [])
        self.assert_migrates(exported)
        self.assertTrue([n for n in exported["nodes"] if n["provenance"] == "fastapi"])

    def test_D8_entrypoint_with_sqlalchemy_only_is_a_parser_error(self):
        code, stderr = self.parse_exit_code("-f", "sqlalchemy", "-e", "main.py")
        self.assertEqual(code, 2)
        self.assertIn("--entrypoint", stderr)
        code, _, _, labels = self.run_main(
            str(self.root), "-f", "sqlalchemy", "--entrypoint", "main.py", "-o", str(self.out / "a.html")
        )
        self.assertEqual(code, 2)
        self.assertEqual(labels, [])
        self.assertEqual(list(self.out.iterdir()), [])

    def test_D8_entrypoint_is_accepted_when_fastapi_is_also_selected(self):
        code, stderr = self.parse_exit_code("-f", "fastapi", "-f", "sqlalchemy", "-e", "main.py")
        self.assertIsNone(code, stderr)

    def test_D9_mermaid_exits_zero_and_prints_a_graph_block(self):
        code, stdout, stderr, labels = self.run_main(
            str(self.root), "-f", "sqlalchemy", "--mermaid", "-o", str(self.out / "a.html")
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(labels, ["SQLAlchemy"])
        self.assertIn("graph", stdout)

    def test_FR1_sqlalchemy_is_a_valid_repeatable_framework_choice(self):
        for argv in (["-f", "sqlalchemy"], ["-f", "sqlalchemy", "-l", "python"], ["-f", "sqlalchemy", "-f", "android"]):
            with self.subTest(argv=argv):
                code, stderr = self.parse_exit_code(*argv)
                self.assertIsNone(code, stderr)
        code, _ = self.parse_exit_code("-f", "sqlalchemy", "-f", "sqlalchemy")
        self.assertEqual(code, 2)


KOTLIN_MIGRATION = """\
package com.example.core.database

import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE topics ADD COLUMN x INTEGER")
    }
}
"""

EXTRA_FILES = {
    "config.yaml": "debug: true\nname: demo\n",
    "settings.toml": "[app]\nname = \"demo\"\n",
    "data.json": "{\"name\": \"demo\"}\n",
    "tests/test_models.py": "from app.models import User\n\n\ndef test_user():\n    assert User\n",
    "core_database/src/main/kotlin/com/example/core/database/Migrations.kt": KOTLIN_MIGRATION,
    **ANDROID_FILES,
}
ZERO = {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


class TestVO5D10MergedStats(CliFixture):
    """No config or test files: two framework analyzers that both run config enrichment collide on
    config: ids (pre-existing behavior outside this spec), which would mask the merge rule under test."""

    files = {
        **PROJECT_FILES,
        "core_database/src/main/kotlin/com/example/core/database/Migrations.kt": KOTLIN_MIGRATION,
        **ANDROID_FILES,
    }

    def test_D10_android_then_sqlalchemy_keeps_first_migration_matching(self):
        single_android, _ = self.run_json("-f", "android", name="android_only")
        single_sqla, _ = self.run_json("-f", "sqlalchemy", name="sqla_only")
        expected = {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}
        self.assertEqual(single_android["stats"]["migration_matching"], expected)
        self.assertNotEqual(single_sqla["stats"]["migration_matching"], expected)
        merged, _ = self.run_json("-f", "android", "-f", "sqlalchemy", name="merged")
        self.assertEqual(merged["stats"]["migration_matching"], single_android["stats"]["migration_matching"])
        self.assertEqual(len({n["id"] for n in merged["nodes"]}), len(merged["nodes"]))
        self.assertTrue(relation(merged, "MIGRATES"))


class TestVO5Enrichment(CliFixture):
    files = {**PROJECT_FILES, **EXTRA_FILES}

    def test_D11_config_files_with_fastapi_and_sqlalchemy_keep_ids_unique(self):
        merged, _ = self.run_json("-f", "fastapi", "-f", "sqlalchemy", name="merged")
        ids = [n["id"] for n in merged["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        config_ids = [i for i in ids if i.startswith("config:")]
        self.assertEqual(len(config_ids), len(set(config_ids)))
        single, _ = self.run_json("-f", "fastapi", name="fastapi_only")
        self.assertLessEqual({n["id"] for n in single["nodes"] if n["id"].startswith("config:")}, set(config_ids))

    def test_D12_no_language_graph_skips_configures_and_tests_edges(self):
        exported, _ = self.run_json("-f", "sqlalchemy", "--no-language-graph", name="nolang")
        self.assertEqual(relation(exported, "CONFIGURES"), [])
        self.assertEqual(relation(exported, "TESTS"), [])
        self.assertEqual(python_core(exported), [])
        self.assertTrue(relation(exported, "MIGRATES"))


class TestVO7SingleRunsWithoutSqlalchemy(CliFixture):
    def test_fastapi_and_python_single_runs_do_not_leak_sqlalchemy_output(self):
        for name, flags in (("fastapi", ["-f", "fastapi"]), ("python", ["-l", "python"])):
            with self.subTest(partition=name):
                exported, _ = self.run_json(*flags, name=name)
                self.assertEqual(sqla_nodes(exported), [])
                self.assertEqual(relation(exported, "MIGRATES"), [])
                self.assertNotIn("migration_matching", exported["stats"])
                labels = [c.get("label") for c in exported["collections"].values()]
                self.assertNotIn("SQLAlchemy Models", labels)
                self.assertNotIn("Alembic Migrations", labels)


class TestVO7AndroidWithoutMigrations(CliFixture):
    files = ANDROID_FILES

    def test_android_on_room_project_without_migrations_has_no_migration_output(self):
        exported, labels = self.run_json("-f", "android")
        self.assertEqual(labels, ["Android"])
        self.assertTrue([n for n in exported["nodes"] if n["group"] != "room_migration"])
        self.assertEqual([n for n in exported["nodes"] if n["group"] == "room_migration"], [])
        self.assertEqual(relation(exported, "MIGRATES"), [])
        self.assertNotIn("migration_matching", exported["stats"])
        labels = [c.get("label") for c in exported["collections"].values()]
        self.assertNotIn("Room Migrations", labels)
        self.assertFalse([n for n in exported["nodes"] if "migration" in (n.get("flags") or [])])


class TestVO8Determinism(CliFixture):
    def collect(self, flags, bottlenecks):
        self.run_json(*flags, bottlenecks=bottlenecks)
        result = [(self.out / "architecture.json").read_bytes()]
        if bottlenecks:
            result.append((self.out / "architecture_b.json").read_bytes())
        for leftover in list(self.out.iterdir()):
            if leftover.is_file():
                leftover.unlink()
        return result

    def test_sqlalchemy_json_and_bottlenecks_are_byte_identical_across_runs(self):
        first = self.collect(["-f", "sqlalchemy"], True)
        second = self.collect(["-f", "sqlalchemy"], True)
        self.assertTrue(all(first))
        self.assertIn(b"MIGRATES", first[0])
        self.assertEqual(first, second)

    def test_fastapi_plus_sqlalchemy_json_is_byte_identical_across_runs(self):
        first = self.collect(["-f", "fastapi", "-f", "sqlalchemy"], False)
        second = self.collect(["-f", "fastapi", "-f", "sqlalchemy"], False)
        self.assertTrue(all(first))
        self.assertIn(b"MIGRATES", first[0])
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
