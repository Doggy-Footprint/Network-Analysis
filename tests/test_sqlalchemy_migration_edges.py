"""Spec 1620f5318bc5dd4e v1, SQLAlchemy/Alembic integration surface.

VO3 (equivalence partitioning) over tmp projects analysed with SQLAlchemyAnalyzer + SQLAlchemyGraphBuilder.
  Model forms:   M1 __tablename__ literal, M2 SQLModel table=True (class name lowercased), M3 non-literal
                 __tablename__ (not a model), M4 plain class (not a model), M5 SQLModel without table=True
                 (not a model), M6 SQLModel table=True with literal __tablename__ (literal wins).
  Locations:     L1 alembic/versions, L2 migrations/versions, L3 other directory (not a migration),
                 L4 file in versions dir without top-level upgrade (not a migration).
  Op kinds:      O1 create_table, O2 drop_table, O3 rename_table, O4 add_column, O5 drop_column,
                 O6 alter_column, O7 create_index, O8 drop_index with table_name, O9 drop_index without,
                 O10 create_foreign_key, O11 create_unique_constraint, O12 drop_constraint,
                 O13 batch_alter_table, O14 execute(sql literal).
  Argument form: P1 positional, P2 keyword; T1 literal, T2 non-literal; R1 refs in upgrade, R2 refs in downgrade.
VO6 (alembic part): effective_token_cost == 0.1 * token_cost for an alembic_migration node.
Expected values are hand-derived from FR2, FR3, FR5, FR8, FR11 and Cases C1, C2, C5, C6, C8, C10, C12, C16, C17, C18.
"""
import pytest

from analysis import GraphAnalyzer
from framework_analyzers.sqlalchemy import SQLAlchemyAnalyzer, SQLAlchemyGraphBuilder

MODELS = """\
from sqlalchemy import Column, Integer
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Alpha(Base):
    __tablename__ = "alpha"
    id = Column(Integer, primary_key=True)


class Beta(Base):
    __tablename__ = "beta"
    id = Column(Integer, primary_key=True)
"""

ZERO = {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def write(root, files):
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def build(tmp_path, files, **builder_kwargs):
    root = tmp_path / "proj"
    write(root, files)
    architecture = SQLAlchemyAnalyzer(str(root)).analyze()
    return SQLAlchemyGraphBuilder(**builder_kwargs).build_graph(architecture), root


def revision(upgrade_body, downgrade_body="pass"):
    def indent(body):
        return "\n".join("    " + line for line in body.splitlines())

    return (
        "from alembic import op\nimport sqlalchemy as sa\n\n"
        "revision = 'r1'\ndown_revision = None\n\n\n"
        f"def upgrade():\n{indent(upgrade_body)}\n\n\n"
        f"def downgrade():\n{indent(downgrade_body)}\n"
    )


def nodes_in(arch, group):
    return [n for n in arch.nodes if n.group == group]


def model_name(node_id):
    return node_id.rsplit("_", 1)[1]


def migration_node(arch, tail):
    found = [n for n in nodes_in(arch, "alembic_migration") if n.id.endswith(tail)]
    assert len(found) == 1, [n.id for n in nodes_in(arch, "alembic_migration")]
    return found[0]


def migrates(arch):
    return [e for e in arch.edges if e.relation == "MIGRATES"]


def targets_of(arch, tail):
    node = migration_node(arch, tail)
    return sorted(model_name(e.to_id) for e in migrates(arch) if e.from_id == node.id)


def project(revision_source, rel="alembic/versions/0001_x.py", models=MODELS):
    return {"app/models.py": models, rel: revision_source}


# ---------------------------------------------------------------- op kinds, O1-O14 / P1-P2 / R1

OP_CASES = [
    ("O1_create_table_positional", 'op.create_table("alpha", sa.Column("id", sa.Integer()))', ["Alpha"]),
    ("O1_create_table_keyword", 'op.create_table(table_name="alpha")', ["Alpha"]),
    ("O2_drop_table_positional", 'op.drop_table("alpha")', ["Alpha"]),
    ("O2_drop_table_keyword", 'op.drop_table(table_name="alpha")', ["Alpha"]),
    ("O3_rename_table_positional_C2", 'op.rename_table("alpha", "beta")', ["Alpha", "Beta"]),
    ("O3_rename_table_keyword", 'op.rename_table(old_table_name="alpha", new_table_name="beta")', ["Alpha", "Beta"]),
    ("O4_add_column_positional", 'op.add_column("alpha", sa.Column("x", sa.Integer()))', ["Alpha"]),
    ("O4_add_column_keyword", 'op.add_column(table_name="alpha", column=sa.Column("x", sa.Integer()))', ["Alpha"]),
    ("O5_drop_column_positional", 'op.drop_column("alpha", "x")', ["Alpha"]),
    ("O5_drop_column_keyword", 'op.drop_column(table_name="alpha", column_name="beta")', ["Alpha"]),
    ("O6_alter_column_positional", 'op.alter_column("alpha", "x", nullable=False)', ["Alpha"]),
    ("O6_alter_column_keyword", 'op.alter_column(table_name="alpha", column_name="x", nullable=False)', ["Alpha"]),
    ("O7_create_index_positional", 'op.create_index("ix_a", "alpha", ["x"])', ["Alpha"]),
    ("O7_create_index_keyword", 'op.create_index("ix_a", table_name="alpha", columns=["x"])', ["Alpha"]),
    ("O8_drop_index_with_table_name", 'op.drop_index("ix_a", table_name="alpha")', ["Alpha"]),
    ("O9_drop_index_without_table_name", 'op.drop_index("ix_a")', []),
    ("O10_create_foreign_key_positional_C16", 'op.create_foreign_key("fk", "alpha", "beta", ["b_id"], ["id"])', ["Alpha", "Beta"]),
    ("O10_create_foreign_key_keyword", 'op.create_foreign_key("fk", source_table="alpha", referent_table="beta", local_cols=["b_id"], remote_cols=["id"])', ["Alpha", "Beta"]),
    ("O11_create_unique_constraint_positional", 'op.create_unique_constraint("uq", "alpha", ["x"])', ["Alpha"]),
    ("O11_create_unique_constraint_keyword", 'op.create_unique_constraint("uq", table_name="alpha", columns=["x"])', ["Alpha"]),
    ("O12_drop_constraint_positional", 'op.drop_constraint("c", "alpha")', ["Alpha"]),
    ("O12_drop_constraint_keyword", 'op.drop_constraint("c", table_name="alpha", type_="unique")', ["Alpha"]),
    ("O13_batch_alter_table_positional", 'with op.batch_alter_table("alpha"):\n    pass', ["Alpha"]),
    ("O13_batch_alter_table_keyword", 'with op.batch_alter_table(table_name="alpha"):\n    pass', ["Alpha"]),
    ("O14_execute_sql_literal_C7", 'op.execute("CREATE INDEX ix ON \\"public\\".\\"Alpha\\" (x)")', ["Alpha"]),
    ("O14_execute_rename_sql_both", 'op.execute("ALTER TABLE alpha RENAME TO beta")', ["Alpha", "Beta"]),
    ("O14_execute_dml_yields_nothing", 'op.execute("INSERT INTO alpha (id) VALUES (1)")', []),
    ("C6_batch_alias_adds_nothing_more", 'with op.batch_alter_table("alpha") as b:\n    b.add_column(sa.Column("x", sa.Integer()))\n    b.drop_column("beta")\n    b.create_index("ix_beta", ["beta"])', ["Alpha"]),
    ("execute_non_literal_variable_adds_nothing", 'op.execute(sql_var)', []),
    ("execute_sa_text_adds_nothing", 'op.execute(sa.text("CREATE TABLE alpha (id INTEGER)"))', []),
    ("receiver_other_than_op_is_ignored", 'helper.create_table("alpha")\nself.op.drop_table("beta")', []),
    ("several_ops_union", 'op.create_table("alpha")\nop.add_column("beta", sa.Column("x", sa.Integer()))', ["Alpha", "Beta"]),
]


@pytest.mark.parametrize("body,expected", [c[1:] for c in OP_CASES], ids=[c[0] for c in OP_CASES])
def test_VO3_upgrade_op_kinds_produce_edges_to_the_named_models(tmp_path, body, expected):
    arch, _ = build(tmp_path, project(revision(body)))
    assert targets_of(arch, "0001_x.py") == expected
    assert arch.stats["migration_matching"] == {"matched": len(expected), "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO3_R2_refs_in_downgrade_are_collected_with_upgrade(tmp_path):
    arch, _ = build(tmp_path, project(revision('op.create_table("alpha")', 'op.drop_table("beta")')))
    assert targets_of(arch, "0001_x.py") == ["Alpha", "Beta"]
    assert arch.stats["migration_matching"] == {"matched": 2, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO3_R2_downgrade_only_reference(tmp_path):
    arch, _ = build(tmp_path, project(revision("pass", 'op.drop_table("beta")')))
    assert targets_of(arch, "0001_x.py") == ["Beta"]
    assert arch.stats["migration_matching"] == {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


# ---------------------------------------------------------------- T1/T2 literal vs non-literal, stats

def test_VO3_C1_unique_edge_fields_and_stats(tmp_path):
    arch, _ = build(tmp_path, project(revision('op.create_table("alpha")')))
    node = migration_node(arch, "0001_x.py")
    edges = migrates(arch)
    assert len(edges) == 1
    edge = edges[0]
    assert edge.from_id == node.id
    assert model_name(edge.to_id) == "Alpha"
    assert edge.to_id in {n.id for n in nodes_in(arch, "sqlalchemy_model")}
    assert edge.resolution == "unique_name"
    assert edge.confidence == "framework_inferred"
    assert edge.candidates == []
    assert edge.metadata["table"] == "alpha"
    assert arch.stats["migration_matching"] == {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO3_T2_non_literal_table_name_is_unresolvable_C10(tmp_path):
    arch, _ = build(tmp_path, project(revision("op.create_table(TABLE_NAME)")))
    assert migrates(arch) == []
    assert arch.stats["migration_matching"] == {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 1}


def test_VO3_T2_fstring_and_keyword_non_literals_are_unresolvable(tmp_path):
    body = 'op.drop_table(f"t_{n}")\nop.add_column(table_name=name, column=sa.Column("x", sa.Integer()))'
    arch, _ = build(tmp_path, project(revision(body)))
    assert migrates(arch) == []
    assert arch.stats["migration_matching"] == {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 2}


def test_VO3_T1_T2_literal_and_non_literal_args_of_one_call(tmp_path):
    arch, _ = build(tmp_path, project(revision('op.rename_table("alpha", NEW_NAME)')))
    assert targets_of(arch, "0001_x.py") == ["Alpha"]
    assert arch.stats["migration_matching"] == {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 1}


def test_VO3_unknown_table_is_unmatched_C11(tmp_path):
    arch, _ = build(tmp_path, project(revision('op.drop_table("ghost")')))
    assert migrates(arch) == []
    assert arch.stats["migration_matching"] == {"matched": 0, "ambiguous": 0, "unmatched": 1, "unresolvable": 0}


def test_VO3_C9_same_table_three_times_one_edge(tmp_path):
    body = 'op.add_column("alpha", sa.Column("x", sa.Integer()))\nop.add_column("alpha", sa.Column("y", sa.Integer()))\nop.drop_column("alpha", "z")'
    arch, _ = build(tmp_path, project(revision(body)))
    assert len(migrates(arch)) == 1
    assert arch.stats["migration_matching"] == {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO3_C8_revision_without_ops_and_model_without_migration(tmp_path):
    arch, _ = build(tmp_path, project(revision("pass")))
    assert len(nodes_in(arch, "alembic_migration")) == 1
    assert len(nodes_in(arch, "sqlalchemy_model")) == 2
    assert migrates(arch) == []
    assert arch.stats["migration_matching"] == ZERO


def test_VO3_C12_two_models_same_table_are_ambiguous_to_first_sorted_id(tmp_path):
    files = {
        "app/a_models.py": 'from sqlalchemy.orm import declarative_base\nBase = declarative_base()\n\n\nclass User(Base):\n    __tablename__ = "users"\n',
        "app/b_models.py": 'from sqlalchemy.orm import declarative_base\nBase = declarative_base()\n\n\nclass User(Base):\n    __tablename__ = "users"\n',
        "alembic/versions/0001_x.py": revision('op.create_table("users")'),
    }
    arch, _ = build(tmp_path, files)
    ids = sorted(n.id for n in nodes_in(arch, "sqlalchemy_model"))
    assert len(ids) == 2 and ids[0] != ids[1]
    edges = migrates(arch)
    assert len(edges) == 1
    assert edges[0].to_id == ids[0]
    assert edges[0].resolution == "ambiguous"
    assert edges[0].candidates == [ids[1]]
    assert edges[0].metadata["framework_rule"]["specificity"] == "ambiguous"
    assert arch.stats["migration_matching"] == {"matched": 0, "ambiguous": 1, "unmatched": 0, "unresolvable": 0}


def test_VO3_table_match_is_case_insensitive(tmp_path):
    models = 'from sqlalchemy.orm import declarative_base\nBase = declarative_base()\n\n\nclass Account(Base):\n    __tablename__ = "Accounts"\n'
    arch, _ = build(tmp_path, project(revision('op.create_table("accounts")'), models=models))
    assert targets_of(arch, "0001_x.py") == ["Account"]
    assert arch.stats["migration_matching"] == {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


# ---------------------------------------------------------------- model forms M1-M6

MODEL_FORMS = """\
from sqlalchemy import Column, Integer
from sqlalchemy.orm import declarative_base
from sqlmodel import SQLModel

Base = declarative_base()
NAME = "computed"


class Literal(Base):
    __tablename__ = "literal_tbl"


class Hero(SQLModel, table=True):
    id: int


class NonLiteral(Base):
    __tablename__ = NAME


class Plain:
    x = 1


class NotATable(SQLModel):
    id: int


class Team(SQLModel, table=True):
    __tablename__ = "squads"
"""


def test_VO3_M1_to_M6_model_forms_become_model_nodes_only_when_specified(tmp_path):
    arch, _ = build(tmp_path, {"app/forms.py": MODEL_FORMS})
    names = sorted(model_name(n.id) for n in nodes_in(arch, "sqlalchemy_model"))
    assert names == ["Hero", "Literal", "Team"]
    for node in nodes_in(arch, "sqlalchemy_model"):
        assert node.category == "sqlalchemy_model"
        assert node.id.startswith("sqlalchemy_model_")


def test_VO3_F2_model_node_id_is_dotted_module_and_class(tmp_path):
    hero = 'from sqlmodel import SQLModel\n\n\nclass Hero(SQLModel, table=True):\n    id: int\n'
    arch, _ = build(tmp_path, {"app/models.py": MODELS, "app/db/forms.py": hero})
    assert sorted(n.id for n in nodes_in(arch, "sqlalchemy_model")) == [
        "sqlalchemy_model_app.db.forms_Hero",
        "sqlalchemy_model_app.models_Alpha",
        "sqlalchemy_model_app.models_Beta",
    ]


@pytest.mark.parametrize(
    "table,expected",
    [
        ("literal_tbl", ["Literal"]),
        ("hero", ["Hero"]),
        ("squads", ["Team"]),
        ("team", []),
        ("computed", []),
        ("nonliteral", []),
        ("plain", []),
        ("notatable", []),
    ],
    ids=["M1_literal", "M2_sqlmodel_lowercased_C5", "M6_literal_wins", "M6_class_name_not_used", "M3_value_of_constant", "M3_class_name", "M4_plain", "M5_sqlmodel_without_table"],
)
def test_VO3_model_table_names_drive_matching(tmp_path, table, expected):
    files = {"app/forms.py": MODEL_FORMS, "alembic/versions/0001_x.py": revision(f'op.add_column("{table}", sa.Column("x", sa.Integer()))')}
    arch, _ = build(tmp_path, files)
    assert targets_of(arch, "0001_x.py") == expected
    assert arch.stats["migration_matching"] == {
        "matched": len(expected), "ambiguous": 0, "unmatched": 1 - len(expected), "unresolvable": 0,
    }


# ---------------------------------------------------------------- locations L1-L4

def test_VO3_L1_L2_both_versions_dirs_and_nested_path_are_migrations(tmp_path):
    files = {
        "app/models.py": MODELS,
        "alembic/versions/0001_a.py": revision('op.create_table("alpha")'),
        "migrations/versions/0002_b.py": revision('op.create_table("beta")'),
        "backend/alembic/versions/0003_c.py": revision("pass"),
    }
    arch, _ = build(tmp_path, files)
    migrations = nodes_in(arch, "alembic_migration")
    assert len(migrations) == 3
    for node in migrations:
        assert node.category == "alembic_migration"
        assert "migration" in node.flags
        assert node.id.startswith("alembic_migration_")
    assert targets_of(arch, "0001_a.py") == ["Alpha"]
    assert targets_of(arch, "0002_b.py") == ["Beta"]
    assert targets_of(arch, "0003_c.py") == []


def test_VO3_node_id_is_migration_file_path(tmp_path):
    arch, _ = build(tmp_path, project(revision("pass")))
    assert [n.id for n in nodes_in(arch, "alembic_migration")] == ["alembic_migration_alembic/versions/0001_x.py"]


def test_VO3_L3_L4_outside_versions_or_without_upgrade_is_not_a_migration_C17(tmp_path):
    files = {
        "app/models.py": MODELS,
        "app/upgrade.py": "def upgrade():\n    pass\n",
        "db/versions/0001_y.py": revision('op.create_table("alpha")'),
        "alembic/versions/0002_only_downgrade.py": "def downgrade():\n    pass\n",
        "alembic/versions/0003_nested.py": "def helper():\n    def upgrade():\n        pass\n",
        "alembic/versions/0004_real.py": revision("pass"),
    }
    arch, _ = build(tmp_path, files)
    assert [n.id.rsplit("/", 1)[1] for n in nodes_in(arch, "alembic_migration")] == ["0004_real.py"]
    assert migrates(arch) == []


def test_VO3_unparseable_python_file_is_skipped_and_others_analyzed(tmp_path):
    files = {
        "app/models.py": MODELS,
        "app/broken.py": "class Broken(:\n",
        "alembic/versions/0001_x.py": revision('op.create_table("alpha")'),
        "alembic/versions/0002_broken.py": "def upgrade(:\n",
    }
    arch, _ = build(tmp_path, files)
    assert targets_of(arch, "0001_x.py") == ["Alpha"]
    assert arch.stats["migration_matching"] == {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


# ---------------------------------------------------------------- FR11 collections / FR10 builder flag

def test_VO3_FR11_report_collection_labels(tmp_path):
    arch, _ = build(tmp_path, project(revision('op.create_table("alpha")')))
    labels = {c.label for c in arch.report_collections}
    assert {"SQLAlchemy Models", "Alembic Migrations"} <= labels


def test_VO3_FR10_no_models_keeps_migration_nodes_without_edges(tmp_path):
    arch, _ = build(tmp_path, project(revision('op.create_table("alpha")')), include_models=False)
    assert nodes_in(arch, "sqlalchemy_model") == []
    assert migrates(arch) == []
    assert len(nodes_in(arch, "alembic_migration")) == 1


def test_VO3_C2_rename_edges_carry_each_table_name(tmp_path):
    arch, _ = build(tmp_path, project(revision('op.rename_table("alpha", "beta")')))
    assert {(model_name(e.to_id), e.metadata["table"]) for e in migrates(arch)} == {("Alpha", "alpha"), ("Beta", "beta")}
    assert arch.stats["migration_matching"] == {"matched": 2, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


# ---------------------------------------------------------------- VO6 alembic part

def test_VO6_C18_alembic_migration_effective_cost_is_a_tenth_of_token_cost(tmp_path):
    arch, root = build(tmp_path, project(revision('op.create_table("alpha")')))
    metrics = GraphAnalyzer().analyze(arch.nodes, arch.edges, str(root))["node_metrics"]
    node = migration_node(arch, "0001_x.py")
    assert "migration" in node.flags
    assert metrics[node.id]["token_cost"] > 0
    assert metrics[node.id]["effective_token_cost"] == pytest.approx(0.1 * metrics[node.id]["token_cost"])
    model = nodes_in(arch, "sqlalchemy_model")[0]
    assert metrics[model.id]["effective_token_cost"] == pytest.approx(metrics[model.id]["token_cost"])
