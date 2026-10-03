"""Spec 1620f5318bc5dd4e v1, Room integration surface.

VO4 (equivalence partitioning) over tmp projects analysed with AndroidAnalyzer + AndroidArchitectureGraphBuilder.
  Migration forms: F1 property initialised with `object : Migration(..)`, F2 class declaration,
                   F3 object declaration, F4 non-migration declarations (ignored).
  SQL argument:    Q1 execSQL string literal, Q2 execSQL non-literal (one unresolvable ref),
                   Q3 several execSQL calls in one body.
  Table name:      E1 @Entity(tableName = "x"), E2 class simple name, E3 normalization (case, backticks).
  Others:          K1 language-node `migration` flag for class/object form, R1 "Room Migrations" collection
                   present when non-empty, R2 absent and no migration_matching stats when no Room migration,
                   N1 include_models=False keeps migration nodes without edges.
VO6 (room part): effective_token_cost == 0.1 * token_cost for room_migration and the flagged Kotlin class node.
Expected values are hand-derived from FR4, FR7, FR10, FR11 and Cases C3, C4, C18, C20.
"""
import unittest

try:
    import tree_sitter_language_pack  # noqa: F401
    _HAS_TREE_SITTER = True
except ImportError:
    _HAS_TREE_SITTER = False

if _HAS_TREE_SITTER:
    from analysis import GraphAnalyzer
    from framework_analyzers.android.analyzer import AndroidAnalyzer
    from framework_analyzers.android.graph import AndroidArchitectureGraphBuilder

import re
import shutil
import tempfile
from pathlib import Path

PKG_DIR = "core_database/src/main/kotlin/com/example/core/database"

USER_ENTITY = """\
package com.example.core.database.model

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "users")
data class User(
    @PrimaryKey val id: Int,
    val age: Int,
)
"""

A_ENTITY = """\
package com.example.core.database.model

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "a")
data class A(@PrimaryKey val id: Int)
"""

B_ENTITY = """\
package com.example.core.database.model

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "b")
data class B(@PrimaryKey val id: Int)
"""

NOTE_ENTITY = """\
package com.example.core.database.model

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity
data class Note(@PrimaryKey val id: Int)
"""

PROPERTY_MIGRATION = """\
package com.example.core.database

import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE `users` ADD COLUMN age INTEGER")
    }
}
"""

CLASS_MIGRATION = """\
package com.example.core.database

import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

class Migration2To3 : Migration(2, 3) {
    override fun migrate(database: SupportSQLiteDatabase) {
        database.execSQL("ALTER TABLE a RENAME TO b")
    }
}
"""

OBJECT_MIGRATION = """\
package com.example.core.database

import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

object Migration3To4 : Migration(3, 4) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("DROP TABLE IF EXISTS Note")
    }
}
"""


def entity_token(node_id, names):
    """Entity node id format is unspecified; the class name must appear as a whole token of the id."""
    tokens = re.findall(r"[A-Za-z0-9]+", node_id)
    found = [name for name in names if name in tokens]
    assert len(found) == 1, (node_id, found)
    return found[0]


def migration_source(name, body, form="class"):
    head = (
        "package com.example.core.database\n\n"
        "import androidx.room.migration.Migration\n"
        "import androidx.sqlite.db.SupportSQLiteDatabase\n\n"
    )
    fn = f"    override fun migrate(db: SupportSQLiteDatabase) {{\n{body}\n    }}\n"
    if form == "class":
        return head + f"class {name} : Migration(1, 2) {{\n{fn}}}\n"
    if form == "object":
        return head + f"object {name} : Migration(1, 2) {{\n{fn}}}\n"
    return head + f"val {name} = object : Migration(1, 2) {{\n{fn}}}\n"


@unittest.skipUnless(_HAS_TREE_SITTER, "tree-sitter-language-pack not installed")
class RoomFixture(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.root = Path(self.dir).resolve()

    def build(self, files, **builder_kwargs):
        for relative, text in files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        architecture = AndroidAnalyzer(str(self.root)).analyze()
        return AndroidArchitectureGraphBuilder(**builder_kwargs).build_graph(architecture)

    @staticmethod
    def migrations(arch):
        return [n for n in arch.nodes if n.group == "room_migration"]

    @staticmethod
    def migrates(arch):
        return [e for e in arch.edges if e.relation == "MIGRATES"]

    def migration(self, arch, name):
        found = [n for n in self.migrations(arch) if n.id.endswith("_" + name)]
        self.assertEqual(len(found), 1, [n.id for n in self.migrations(arch)])
        return found[0]

    def target_ids(self, arch, name):
        node = self.migration(arch, name)
        return sorted(e.to_id for e in self.migrates(arch) if e.from_id == node.id)

    def files(self, *entities, **migrations):
        files = {f"{PKG_DIR}/model/{label}.kt": text for label, text in entities}
        files.update({f"{PKG_DIR}/{label}.kt": text for label, text in migrations.items()})
        return files


class TestVO4RoomMigrations(RoomFixture):
    def test_F1_Q1_E1_property_object_expression_C3(self):
        arch = self.build(self.files(("User", USER_ENTITY), Migrations=PROPERTY_MIGRATION))
        node = self.migration(arch, "MIGRATION_1_2")
        self.assertEqual(node.category, "room_migration")
        self.assertIn("migration", node.flags)
        edges = self.migrates(arch)
        self.assertEqual(len(edges), 1)
        edge = edges[0]
        self.assertEqual(edge.from_id, node.id)
        entity_node = {n.id: n for n in arch.nodes}[edge.to_id]
        self.assertEqual(entity_token(edge.to_id, ("User",)), "User")
        self.assertNotEqual(entity_node.group, "room_migration")
        self.assertEqual(edge.resolution, "unique_name")
        self.assertEqual(edge.confidence, "framework_inferred")
        self.assertEqual(edge.candidates, [])
        self.assertEqual(edge.metadata["table"], "users")
        self.assertEqual(edge.metadata["framework_rule"], {"id": "orm.migration_touches_table", "specificity": "unique"})
        self.assertEqual(arch.stats["migration_matching"], {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 0})

    def test_node_id_is_file_path_and_name(self):
        arch = self.build(self.files(("User", USER_ENTITY), Migrations=PROPERTY_MIGRATION))
        self.assertEqual(
            [n.id for n in self.migrations(arch)],
            [f"room_migration_{PKG_DIR}/Migrations.kt_MIGRATION_1_2"],
        )

    def test_F2_class_declaration_rename_links_both_tables_and_flags_kotlin_node_C4(self):
        arch = self.build(self.files(("A", A_ENTITY), ("B", B_ENTITY), Migration2To3=CLASS_MIGRATION))
        node = self.migration(arch, "Migration2To3")
        self.assertIn("migration", node.flags)
        targets = self.target_ids(arch, "Migration2To3")
        self.assertEqual(len(targets), 2)
        self.assertEqual(sorted(entity_token(t, ("A", "B")) for t in targets), ["A", "B"])
        linked = [e for e in arch.edges if e.relation == "IMPLEMENTED_BY" and e.from_id == node.id]
        self.assertEqual(len(linked), 1)
        kotlin = {n.id: n for n in arch.nodes}[linked[0].to_id]
        self.assertEqual(kotlin.provenance, "kotlin-core")
        self.assertIn("Migration2To3", kotlin.id)
        self.assertIn("migration", kotlin.flags)
        self.assertEqual(arch.stats["migration_matching"], {"matched": 2, "ambiguous": 0, "unmatched": 0, "unresolvable": 0})

    def test_F3_object_declaration_with_create_if_not_exists_and_class_name_table_E2(self):
        arch = self.build(self.files(("Note", NOTE_ENTITY), Migration3To4=OBJECT_MIGRATION))
        node = self.migration(arch, "Migration3To4")
        self.assertIn("migration", node.flags)
        targets = self.target_ids(arch, "Migration3To4")
        self.assertEqual(len(targets), 1)
        self.assertEqual(entity_token(targets[0], ("Note",)), "Note")
        edge = self.migrates(arch)[0]
        self.assertEqual(edge.metadata["table"], "note")
        linked = [e for e in arch.edges if e.relation == "IMPLEMENTED_BY" and e.from_id == node.id]
        self.assertEqual(len(linked), 1)
        self.assertIn("migration", {n.id: n for n in arch.nodes}[linked[0].to_id].flags)

    def test_E1_entity_table_name_overrides_class_name(self):
        arch = self.build(self.files(("User", USER_ENTITY), M=migration_source("M", '        db.execSQL("ALTER TABLE user ADD COLUMN x INTEGER")')))
        self.assertEqual(self.migrates(arch), [])
        self.assertEqual(arch.stats["migration_matching"], {"matched": 0, "ambiguous": 0, "unmatched": 1, "unresolvable": 0})

    def test_E3_case_and_backtick_normalization(self):
        body = '        db.execSQL("DROP TABLE `USERS`")'
        arch = self.build(self.files(("User", USER_ENTITY), M=migration_source("M", body)))
        self.assertEqual(len(self.target_ids(arch, "M")), 1)
        self.assertEqual(arch.stats["migration_matching"], {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 0})

    def test_Q2_non_literal_execSQL_is_unresolvable_C20(self):
        body = "        db.execSQL(sqlVar)"
        arch = self.build(self.files(("User", USER_ENTITY), M=migration_source("M", body)))
        self.assertEqual(self.migrates(arch), [])
        self.assertEqual(arch.stats["migration_matching"], {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 1})

    def test_F5_trimIndent_raw_string_is_unresolvable_even_with_matching_entity(self):
        body = '        db.execSQL("""ALTER TABLE users ADD COLUMN x INTEGER""".trimIndent())'
        arch = self.build(self.files(("User", USER_ENTITY), M=migration_source("M", body)))
        self.assertEqual(self.migrates(arch), [])
        self.assertEqual(arch.stats["migration_matching"], {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 1})

    def test_Q3_several_execSQL_calls_union_literal_and_non_literal(self):
        body = (
            '        db.execSQL("ALTER TABLE users ADD COLUMN x INTEGER")\n'
            '        db.execSQL("CREATE INDEX ix ON users (x)")\n'
            "        db.execSQL(dynamicSql)\n"
            '        db.execSQL("ALTER TABLE ghost ADD COLUMN y INTEGER")'
        )
        arch = self.build(self.files(("User", USER_ENTITY), M=migration_source("M", body)))
        self.assertEqual(len(self.target_ids(arch, "M")), 1)
        self.assertEqual(arch.stats["migration_matching"], {"matched": 1, "ambiguous": 0, "unmatched": 1, "unresolvable": 1})

    def test_F1_F2_F3_together_in_one_project(self):
        files = self.files(
            ("User", USER_ENTITY), ("A", A_ENTITY), ("B", B_ENTITY), ("Note", NOTE_ENTITY),
            Migrations=PROPERTY_MIGRATION, Migration2To3=CLASS_MIGRATION, Migration3To4=OBJECT_MIGRATION,
        )
        arch = self.build(files)
        self.assertEqual(len(self.migrations(arch)), 3)
        for name in ("MIGRATION_1_2", "Migration2To3", "Migration3To4"):
            self.migration(arch, name)
        self.assertEqual(len(self.migrates(arch)), 4)

    def test_F4_other_declarations_are_not_migrations(self):
        source = (
            "package com.example.core.database\n\n"
            "import androidx.room.RoomDatabase\n\n"
            "abstract class AppDatabase : RoomDatabase()\n\n"
            "class Helper {\n    fun run(db: Any) { db.execSQL(\"DROP TABLE users\") }\n}\n\n"
            "val runner = object : Runnable {\n    override fun run() { }\n}\n"
        )
        arch = self.build(self.files(("User", USER_ENTITY), Other=source))
        self.assertEqual(self.migrations(arch), [])
        self.assertEqual(self.migrates(arch), [])

    def test_unparseable_kotlin_file_is_skipped_and_others_analyzed(self):
        files = self.files(("User", USER_ENTITY), Migrations=PROPERTY_MIGRATION, Broken="class Broken : Migration(1, {{{ \n")
        arch = self.build(files)
        self.assertEqual(len(self.target_ids(arch, "MIGRATION_1_2")), 1)
        self.assertEqual(arch.stats["migration_matching"], {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 0})

    def test_R1_room_migrations_collection_present_when_non_empty(self):
        arch = self.build(self.files(("User", USER_ENTITY), Migrations=PROPERTY_MIGRATION))
        self.assertIn("Room Migrations", [c.label for c in arch.report_collections])

    def test_R2_no_room_migration_means_no_nodes_edges_stats_or_collection(self):
        arch = self.build(self.files(("User", USER_ENTITY)))
        self.assertEqual(self.migrations(arch), [])
        self.assertEqual(self.migrates(arch), [])
        self.assertNotIn("migration_matching", arch.stats)
        self.assertNotIn("Room Migrations", [c.label for c in arch.report_collections])
        self.assertFalse([n for n in arch.nodes if "migration" in n.flags])

    def test_N1_no_models_keeps_migration_nodes_without_edges_or_entities(self):
        files = self.files(("User", USER_ENTITY), Migrations=PROPERTY_MIGRATION)
        arch = self.build(files, include_models=False)
        self.assertEqual(len(self.migrations(arch)), 1)
        self.assertEqual(self.migrates(arch), [])
        self.assertIn("Room Migrations", [c.label for c in arch.report_collections])


class TestVO6RoomCost(RoomFixture):
    def metrics(self, arch):
        return GraphAnalyzer().analyze(arch.nodes, arch.edges, str(self.root))["node_metrics"]

    def test_C18_room_migration_and_flagged_kotlin_class_cost_a_tenth(self):
        arch = self.build(self.files(("A", A_ENTITY), ("B", B_ENTITY), Migration2To3=CLASS_MIGRATION))
        metrics = self.metrics(arch)
        node = self.migration(arch, "Migration2To3")
        linked = [e for e in arch.edges if e.relation == "IMPLEMENTED_BY" and e.from_id == node.id]
        kotlin = {n.id: n for n in arch.nodes}[linked[0].to_id]
        self.assertIn("migration", kotlin.flags)
        for target in (node, kotlin):
            cost = metrics[target.id]
            self.assertGreater(cost["token_cost"], 0, target.id)
            self.assertAlmostEqual(cost["effective_token_cost"], 0.1 * cost["token_cost"], places=9, msg=target.id)

    def test_C18_room_migration_property_form_costs_a_tenth_and_entities_do_not(self):
        arch = self.build(self.files(("User", USER_ENTITY), Migrations=PROPERTY_MIGRATION))
        metrics = self.metrics(arch)
        node = self.migration(arch, "MIGRATION_1_2")
        cost = metrics[node.id]
        self.assertGreater(cost["token_cost"], 0)
        self.assertAlmostEqual(cost["effective_token_cost"], 0.1 * cost["token_cost"], places=9)
        entity_id = self.migrates(arch)[0].to_id
        self.assertAlmostEqual(metrics[entity_id]["effective_token_cost"], metrics[entity_id]["token_cost"], places=9)


if __name__ == "__main__":
    unittest.main()
