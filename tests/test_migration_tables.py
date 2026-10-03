"""Spec 1620f5318bc5dd4e v1, unit surfaces.

VO1 (syntax testing): sql_table_refs / normalize_table_name, expectations hand-derived from FR6.
  Coverage items: S1 CREATE TABLE, S2 CREATE TEMP TABLE, S3 IF NOT EXISTS, S4 ALTER TABLE,
  S5 ALTER..RENAME TO, S6 DROP TABLE, S7 DROP TABLE IF EXISTS, S8 CREATE INDEX..ON,
  S9 CREATE UNIQUE INDEX, S10 REFERENCES; N1 bare, N2 "q", N3 `q`, N4 [q], N5 schema.q,
  N6 mixed case; X1 non-DDL -> [], X2 empty string.
VO2 (decision table): match_migration_tables, expectations hand-derived from FR8.
  Coverage items: D1 0 candidates, D2 1 candidate, D3 >=2 candidates, D4 unresolvable (None),
  D5 duplicate ref in one migration, E1 relation, E2 confidence, E3 resolution, E4 candidates,
  E5 evidence, E6 framework_rule, E7 metadata.table, K1 stats keys exact, O1 edge ordering.
"""
import pytest

from framework_analyzers.migration_tables import (
    match_migration_tables,
    normalize_table_name,
    sql_table_refs,
)
from language_analyzers.core.graph_models import RelationKind, SourceSpan

# ---------------------------------------------------------------- VO1

SQL_CASES = [
    # id, sql, expected
    ("S1_create_table", "CREATE TABLE users (id INTEGER)", ["users"]),
    ("S2_create_temp_table", "CREATE TEMP TABLE scratch (id INTEGER)", ["scratch"]),
    ("S2_create_temporary_table", "CREATE TEMPORARY TABLE scratch (id INTEGER)", ["scratch"]),
    ("S3_create_if_not_exists", "CREATE TABLE IF NOT EXISTS posts (id INTEGER)", ["posts"]),
    ("S3_temp_if_not_exists", "CREATE TEMP TABLE IF NOT EXISTS t1 (id INTEGER)", ["t1"]),
    ("S4_alter_table", "ALTER TABLE users ADD COLUMN age INTEGER", ["users"]),
    ("S5_alter_rename_to", "ALTER TABLE a RENAME TO b", ["a", "b"]),
    ("S6_drop_table", "DROP TABLE users", ["users"]),
    ("S7_drop_if_exists", "DROP TABLE IF EXISTS users", ["users"]),
    ("S8_create_index_on", "CREATE INDEX ix ON users (x)", ["users"]),
    ("S8_create_index_if_not_exists", "CREATE INDEX IF NOT EXISTS ix ON users (x)", ["users"]),
    ("S9_create_unique_index", "CREATE UNIQUE INDEX ux ON users (x)", ["users"]),
    ("S9_unique_index_if_not_exists", "CREATE UNIQUE INDEX IF NOT EXISTS ux ON users (x)", ["users"]),
    (
        "S10_references_in_create_C21",
        "CREATE TABLE IF NOT EXISTS posts (uid INTEGER REFERENCES users(id))",
        ["posts", "users"],
    ),
    (
        "S10_references_in_alter",
        "ALTER TABLE posts ADD COLUMN uid INTEGER REFERENCES users(id)",
        ["posts", "users"],
    ),
    ("N1_bare", "DROP TABLE plain", ["plain"]),
    ("N2_double_quoted", 'DROP TABLE "quoted"', ["quoted"]),
    ("N3_backtick", "DROP TABLE `ticked`", ["ticked"]),
    ("N4_bracket", "DROP TABLE [bracketed]", ["bracketed"]),
    ("N5_schema_bare", "DROP TABLE main.users", ["users"]),
    ("N5_schema_quoted", 'DROP TABLE "public"."users"', ["users"]),
    ("N5_schema_bracket", "DROP TABLE [dbo].[users]", ["users"]),
    ("N5_schema_backtick", "DROP TABLE `db`.`users`", ["users"]),
    ("N6_mixed_case_name", "DROP TABLE UserAccounts", ["useraccounts"]),
    ("N6_mixed_case_keywords", "dRoP tAbLe If ExIsTs Users", ["users"]),
    ("N6_lowercase_keywords", "create table if not exists users (id integer)", ["users"]),
    ("C7_index_schema_quoted_mixed_case", 'CREATE INDEX ix ON "public"."Users" (x)', ["users"]),
    ("N6_quoted_mixed_case", 'DROP TABLE "Users"', ["users"]),
    ("X1_insert", "INSERT INTO users (id) VALUES (1)", []),
    ("X1_select", "SELECT * FROM users", []),
    ("X1_update", "UPDATE users SET x = 1", []),
    ("X1_delete", "DELETE FROM users", []),
    ("X2_empty", "", []),
    ("order_and_dedup", "CREATE TABLE a (x INT); DROP TABLE b; ALTER TABLE a ADD COLUMN y INT", ["a", "b"]),
    ("order_of_appearance", "DROP TABLE z; DROP TABLE a", ["z", "a"]),
    ("rename_to_dedup_against_earlier", "CREATE TABLE b (x INT); ALTER TABLE a RENAME TO b", ["b", "a"]),
    ("mixed_ddl_and_dml", "INSERT INTO skip VALUES (1); DROP TABLE kept", ["kept"]),
]


@pytest.mark.parametrize("sql,expected", [c[1:] for c in SQL_CASES], ids=[c[0] for c in SQL_CASES])
def test_VO1_sql_table_refs(sql, expected):
    assert sql_table_refs(sql) == expected


NORMALIZE_CASES = [
    ("N1_bare", "users", "users"),
    ("N2_double_quoted", '"users"', "users"),
    ("N3_backtick", "`users`", "users"),
    ("N4_bracket", "[users]", "users"),
    ("N5_schema", "public.users", "users"),
    ("N5_schema_quoted", '"public"."Users"', "users"),
    ("N5_schema_bracket", "[dbo].[Users]", "users"),
    ("N6_mixed_case", "UserAccounts", "useraccounts"),
    ("X2_empty", "", None),
]


@pytest.mark.parametrize("raw,expected", [c[1:] for c in NORMALIZE_CASES], ids=[c[0] for c in NORMALIZE_CASES])
def test_VO1_normalize_table_name(raw, expected):
    assert normalize_table_name(raw) == expected


def test_VO1_normalize_table_name_none_is_none():
    assert normalize_table_name(None) is None


# ---------------------------------------------------------------- VO2

SPAN = SourceSpan("alembic/versions/001.py", 3, 9, 0, 1)
SPAN_B = SourceSpan("alembic/versions/002.py", 1, 4, 0, 1)
STATS_KEYS = {"matched", "ambiguous", "unmatched", "unresolvable"}


def pairs(edges):
    return [(e.from_id, e.to_id) for e in edges]


def test_VO2_D2_single_candidate_edge_has_the_specified_fields():
    edges, stats = match_migration_tables({"users": ["m:User"]}, [("mig:1", ["users"], SPAN)])
    assert len(edges) == 1
    item = edges[0]
    assert (item.from_id, item.to_id) == ("mig:1", "m:User")
    assert item.relation == "MIGRATES" == RelationKind.MIGRATES
    assert item.confidence == "framework_inferred"
    assert item.resolution == "unique_name"
    assert item.candidates == []
    assert item.evidence == SPAN
    assert item.metadata["framework_rule"] == {"id": "orm.migration_touches_table", "specificity": "unique"}
    assert item.metadata["table"] == "users"
    assert stats == {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO2_D1_zero_candidates_counts_unmatched_without_edge_C11():
    edges, stats = match_migration_tables({"users": ["m:User"]}, [("mig:1", ["ghost"], SPAN)])
    assert edges == []
    assert stats == {"matched": 0, "ambiguous": 0, "unmatched": 1, "unresolvable": 0}


def test_VO2_D1_no_models_at_all():
    edges, stats = match_migration_tables({}, [("mig:1", ["a", "b"], SPAN)])
    assert edges == []
    assert stats == {"matched": 0, "ambiguous": 0, "unmatched": 2, "unresolvable": 0}


def test_VO2_D3_two_candidates_pick_first_sorted_id_C12():
    edges, stats = match_migration_tables({"users": ["z:User", "a:User"]}, [("mig:1", ["users"], SPAN)])
    assert len(edges) == 1
    item = edges[0]
    assert (item.from_id, item.to_id, item.relation) == ("mig:1", "a:User", "MIGRATES")
    assert item.resolution == "ambiguous"
    assert item.confidence == "framework_inferred"
    assert item.candidates == ["z:User"]
    assert item.evidence == SPAN
    assert item.metadata["framework_rule"] == {"id": "orm.migration_touches_table", "specificity": "ambiguous"}
    assert item.metadata["table"] == "users"
    assert stats == {"matched": 0, "ambiguous": 1, "unmatched": 0, "unresolvable": 0}


def test_VO2_D3_three_candidates_sorted_remaining_regardless_of_input_order():
    edges, stats = match_migration_tables({"t": ["c", "a", "b"]}, [("mig", ["t"], SPAN)])
    assert [(e.to_id, e.candidates) for e in edges] == [("a", ["b", "c"])]
    assert stats == {"matched": 0, "ambiguous": 1, "unmatched": 0, "unresolvable": 0}


@pytest.mark.parametrize("refs,expected_unresolvable", [([None], 1), ([None, None], 2), ([None, "users", None], 2)], ids=["one", "two_occurrences", "around_resolvable"])
def test_VO2_D4_unresolvable_counts_each_occurrence_and_makes_no_edge_C10(refs, expected_unresolvable):
    edges, stats = match_migration_tables({"users": ["m:User"]}, [("mig:1", refs, SPAN)])
    expected_matched = 1 if "users" in refs else 0
    assert stats == {"matched": expected_matched, "ambiguous": 0, "unmatched": 0, "unresolvable": expected_unresolvable}
    assert pairs(edges) == ([("mig:1", "m:User")] if "users" in refs else [])


def test_VO2_D5_duplicate_ref_in_one_migration_gives_one_edge_and_matched_one_C9():
    edges, stats = match_migration_tables({"users": ["m:User"]}, [("mig:1", ["users", "users", "users"], SPAN)])
    assert pairs(edges) == [("mig:1", "m:User")]
    assert stats == {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO2_D5_duplicate_unmatched_ref_counts_once_per_migration():
    _, stats = match_migration_tables({}, [("mig:1", ["ghost", "ghost"], SPAN)])
    assert stats == {"matched": 0, "ambiguous": 0, "unmatched": 1, "unresolvable": 0}


def test_VO2_same_ref_in_two_migrations_counts_per_migration():
    edges, stats = match_migration_tables(
        {"users": ["m:User"]}, [("mig:1", ["users"], SPAN), ("mig:2", ["users"], SPAN_B)]
    )
    assert pairs(edges) == [("mig:1", "m:User"), ("mig:2", "m:User")]
    assert [e.evidence for e in edges] == [SPAN, SPAN_B]
    assert stats == {"matched": 2, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO2_duplicate_migration_target_pair_from_two_table_names_yields_one_edge():
    edges, stats = match_migration_tables({"a": ["m:Shared"], "b": ["m:Shared"]}, [("mig:1", ["a", "b"], SPAN)])
    assert pairs(edges) == [("mig:1", "m:Shared")]
    assert stats == {"matched": 2, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO2_each_distinct_ref_gets_its_own_edge_with_its_table():
    edges, stats = match_migration_tables(
        {"old_users": ["m:Old"], "users": ["m:User"]}, [("mig:1", ["old_users", "users"], SPAN)]
    )
    assert {(e.to_id, e.metadata["table"]) for e in edges} == {("m:Old", "old_users"), ("m:User", "users")}
    assert stats == {"matched": 2, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO2_mixed_outcomes_in_one_migration():
    edges, stats = match_migration_tables(
        {"a": ["m:A"], "dup": ["m:D2", "m:D1"]}, [("mig:1", ["a", "ghost", None, "dup"], SPAN)]
    )
    assert pairs(edges) == [("mig:1", "m:A"), ("mig:1", "m:D1")]
    assert stats == {"matched": 1, "ambiguous": 1, "unmatched": 1, "unresolvable": 1}


def test_VO2_C8_no_migrations_and_empty_refs_give_empty_result():
    assert match_migration_tables({"users": ["m:User"]}, []) == (
        [], {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}
    )
    edges, stats = match_migration_tables({"users": ["m:User"]}, [("mig:1", [], SPAN)])
    assert edges == []
    assert stats == {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO2_K1_stats_keys_are_exactly_the_four_counters():
    for models, migrations in (
        ({}, []),
        ({"a": ["x"]}, [("m", ["a", "b", None], SPAN)]),
    ):
        _, stats = match_migration_tables(models, migrations)
        assert set(stats) == STATS_KEYS


def test_VO2_O1_edges_sorted_by_from_id_then_to_id_regardless_of_input_order():
    models = {"t1": ["m:1"], "t2": ["m:2"], "t3": ["m:3"]}
    migrations = [
        ("mig:b", ["t3", "t1"], SPAN_B),
        ("mig:a", ["t2", "t1"], SPAN),
    ]
    edges, _ = match_migration_tables(models, migrations)
    assert pairs(edges) == [
        ("mig:a", "m:1"), ("mig:a", "m:2"), ("mig:b", "m:1"), ("mig:b", "m:3"),
    ]
