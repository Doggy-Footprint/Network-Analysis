---
version: 3
run_id: 1620f5318bc5dd4e
status: complete
base_commit: 55088213ae14f2450089db83e7d112e2ec2c26f9
max_verifier_invocations: 2
handoff: agent-docs/handoff/981eafd0004ac48b-orm-migration-edges.md
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| UI1 | repository analyst | Connect ORM model definitions to the migrations that create, alter, drop or rename their tables | Graph contains `MIGRATES` edges migration → model for SQLAlchemy/Alembic (`-f sqlalchemy`) and Room (`-f android`) |
| UI2 | repository analyst | Migration nodes stay cheap in exploration cost | Every migration endpoint node carries the `migration` flag and gets the existing 0.1 cost multiplier |

# Scope
In scope:
- New relation `RelationKind.MIGRATES = "MIGRATES"`, direction migration → model.
- New framework analyzer `-f sqlalchemy` (label `SQLAlchemy`): SQLAlchemy/SQLModel model nodes, Alembic revision nodes, `MIGRATES` edges, `IMPLEMENTED_BY` edges to Python language nodes, Python language graph included per FR9.
- Android analyzer: Room migration nodes, entity table names, `MIGRATES` edges, `migration` flag.
- DDL recognition only (FR5, FR6).

Out of scope:
- DML (INSERT/UPDATE/DELETE, `op.bulk_insert`).
- Room AutoMigration / `@RenameTable` specs, Room exported schema JSON.
- Django ORM, imperative `Table("name", metadata, ...)` models, `__tablename__` computed by `declared_attr` or non-literal expressions.
- Following table names through variables/constants (non-literal names are counted `unresolvable`).
- Changing `_cost_multiplier` rules.
- Mermaid content for `-f sqlalchemy`: `--mermaid` must exit 0 and print a `graph` block; content unspecified.

# Paths
Implementation: code_analyzer/cli.py, language_analyzers/core/graph_models.py, framework_analyzers/sqlalchemy/, framework_analyzers/android/, framework_analyzers/migration_tables.py
Tests: tests/test_migration_tables.py, tests/test_sqlalchemy_migration_edges.py, tests/test_room_migration_edges.py, tests/test_cli_sqlalchemy.py
Test command: .venv/bin/python -m pytest -q
Review evidence: QR1 base-commit comparison (RE1): `git worktree add --detach <scratch>/base 55088213ae14f2450089db83e7d112e2ec2c26f9`; with PYTHONHASHSEED=0 run `python -m code_analyzer.cli <fixture> <variant> -o a.html --json --bottlenecks b.json` from base and from working tree for fastapi-realworld/fastapi-official-template/futuramaapi (-f fastapi), futuramaapi (-l python), android-nowinandroid (-l kotlin, -f android), typescript-nestjs-realworld (-l typescript); `cmp` a.json and b.json; expected 0 differing files. Hash seed fixed because base-commit FastAPI JSON list order already varies across runs (pre-existing, out of scope). Artifact: result lines recorded in Audit state.

# Signatures
language_analyzers.core.graph_models.RelationKind.MIGRATES == "MIGRATES"
framework_analyzers.migration_tables.normalize_table_name(name: str) -> Optional[str]   # strip quotes/backticks/brackets, drop schema prefix "a.b" → "b", lowercase; "" or None → None
framework_analyzers.migration_tables.sql_table_refs(sql: str) -> list[str]   # normalized names referenced by DDL statements in order of appearance, duplicates removed
framework_analyzers.migration_tables.match_migration_tables(models: dict[str, list[str]], migrations: list[tuple[str, list[Optional[str]], SourceSpan]]) -> tuple[list[GraphEdge], dict]
    # models: normalized table name → model node ids; migrations: (migration node id, table refs where None = unresolvable, evidence)
framework_analyzers.sqlalchemy.SQLAlchemyAnalyzer(project_path: str, snapshot: Optional[RepositorySnapshot] = None).analyze() -> SQLAlchemyProjectArchitecture
framework_analyzers.sqlalchemy.SQLAlchemyGraphBuilder(include_models: bool = True, include_language_graph: bool = True, emit_language_graph: bool = True, snapshot=None, analysis_config=None).build_graph(arch) -> SQLAlchemyProjectArchitecture
    # architecture has nodes, edges, stats, report_collections, project_name, project_path like other framework architectures
CLI: `code-analyzer PATH -f sqlalchemy [other existing flags]`

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| FR1 | `-f sqlalchemy` is a valid framework choice (label `SQLAlchemy`), repeatable/mixable with other `-f/-l` per existing rules. | must | user decision |
| FR2 | SQLAlchemy model = Python class whose body assigns `__tablename__` a string literal → table = that literal. SQLModel class with class keyword `table=True` and no `__tablename__` → table = class name lowercased. Each model becomes a framework node (group/category `sqlalchemy_model`, id `sqlalchemy_model_<dotted module>_<qualname>`, e.g. `sqlalchemy_model_app.models_User`). | must | user decision |
| FR3 | Alembic revision = `.py` file under a directory path containing `alembic/versions/` or `migrations/versions/` that defines top-level `upgrade`. Each becomes a framework node (group/category `alembic_migration`, id `alembic_migration_<repo-relative posix file path>`) with flags containing `migration`. Its table refs are collected from `upgrade` and `downgrade` bodies. | must | user decision |
| FR4 | Room migration = (a) top-level class/object declaration whose supertype list contains `Migration(...)`, or (b) property declaration initialized with `object : Migration(...)`. Each becomes a framework node (group/category `room_migration`, id `room_migration_<file path>_<name>`), flags containing `migration`. Table refs from string-literal first arguments of `execSQL(...)` calls in its body via `sql_table_refs`; non-literal argument (including `"""...""".trimIndent()`) → one unresolvable ref. For (a), the Kotlin language node linked by `IMPLEMENTED_BY` also receives the `migration` flag. | must | user decision |
| FR5 | Alembic op table refs (receiver `op` only): `create_table(name)`, `drop_table(name)`, `rename_table(old, new)` → both, `add_column(table)`, `drop_column(table)`, `alter_column(table)`, `create_index(name, table)`, `drop_index(name, table_name=...)` when table given, `create_foreign_key(name, source, referent)` → both, `create_unique_constraint(name, table)`, `drop_constraint(name, table)`, `batch_alter_table(table)`, `execute("<sql literal>")` → `sql_table_refs`. Table args may be positional or keyword (`table_name`, `source_table`, `referent_table`, `old_table_name`, `new_table_name`). Calls on the batch alias add nothing (only receiver `op` is scanned). `execute` with a non-literal argument (including `sa.text(...)`) adds nothing and is not counted. `drop_index` without a table argument adds nothing. A required table arg that is not a string literal → one unresolvable ref. | must | user decision |
| FR6 | `sql_table_refs` recognizes, case-insensitively: `CREATE [TEMP|TEMPORARY] TABLE [IF NOT EXISTS] t`, `ALTER TABLE t` (+ `RENAME TO u` → t and u), `DROP TABLE [IF EXISTS] t`, `CREATE [UNIQUE] INDEX [IF NOT EXISTS] i ON t`, `REFERENCES t` inside CREATE/ALTER TABLE. Names may be quoted with `"`, `` ` ``, `[]`, and schema-qualified. Other statements yield nothing. | must | user decision |
| FR7 | Room entity table name = `@Entity(tableName = "x")` literal, otherwise the class simple name; normalized. | must | Room semantics |
| FR8 | `match_migration_tables`: per migration, each distinct resolvable ref → 0 candidates: counted `unmatched`, no edge; 1 → edge `MIGRATES` migration→model, confidence `framework_inferred`, resolution `unique_name`, candidates []; ≥2 → edge to the lexicographically first id, resolution `ambiguous`, candidates = remaining sorted ids. Each edge has evidence = the migration span and `metadata.framework_rule = {"id": "orm.migration_touches_table", "specificity": "unique"|"ambiguous"}`, `metadata.table = <normalized name>`. Duplicate (migration, target) pairs yield one edge. Stats keys exactly `matched`, `ambiguous`, `unmatched`, `unresolvable`, mutually exclusive (an ambiguous ref is not counted in `matched`), counting refs (distinct per migration for resolvable, each occurrence for unresolvable). Edges sorted by (from_id, to_id). | must | user decision |
| FR9 | Language graph in `-f sqlalchemy`: included by default (python-core nodes/edges as FastAPI does), omitted with `--no-language-graph`. In a merged run where `-f fastapi` (without `--no-language-graph`) or `-l python` is also selected, sqlalchemy does not emit python-core nodes/edges (`emit_language_graph=False`) but still emits `IMPLEMENTED_BY` edges from its model/migration nodes to the existing python-core ids (model → class node, migration → module node). No duplicate-id error results. | must | user decision |
| FR10 | `--no-models`: sqlalchemy emits no model nodes; android emits no entity nodes (existing); consequently no `MIGRATES` edges; migration nodes are still emitted. | must | consistency with android |
| FR11 | Stats: sqlalchemy and android architectures expose `stats["migration_matching"]` with the FR8 dict (android only when ≥1 Room migration found). In merged runs the first analyzer's `migration_matching` is kept (existing per-key merge rule). `-f sqlalchemy` skips config/test enrichment whenever it does not emit the language graph. Report collections: `SQLAlchemy Models`, `Alembic Migrations` (sqlalchemy); `Room Migrations` (android, only when non-empty). | should | observability |
| FR12 | Output is deterministic: identical input → byte-identical JSON/bottlenecks. | must | determinism |

# Errors
Unparseable Python/Kotlin file — skipped exactly as the existing analyzers skip it; no exception; other files still analyzed.
Non-literal table name — counted `unresolvable`; no edge; run succeeds.
Migration referencing unknown table — counted `unmatched`; no edge; run succeeds.
`-f sqlalchemy` with `--entrypoint` — existing parser error (exit 2).

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | model `User.__tablename__="users"`; revision `op.create_table("users", ...)` | one MIGRATES revision→User, unique_name |
| C2 | normal | revision `op.rename_table("old_users","users")`, models for both | two edges (to both models) |
| C3 | normal | Room `val MIGRATION_1_2 = object : Migration(1, 2) { override fun migrate(db) { db.execSQL("ALTER TABLE `users` ADD COLUMN age INTEGER") } }`, `@Entity(tableName="users") class User` | one MIGRATES room_migration→User entity; room_migration flags contain `migration` |
| C4 | normal | Room `class Migration2To3 : Migration(2, 3)` with `execSQL("ALTER TABLE a RENAME TO b")`, entities A (table a) and B (table b) | two edges; Kotlin language node `Migration2To3` flags contain `migration` |
| C5 | normal | SQLModel `class Hero(SQLModel, table=True)` no tablename; `op.add_column("hero", ...)` | edge to Hero |
| C6 | normal | `with op.batch_alter_table("users") as b: b.add_column(...)` | edge to users model; batch call adds nothing more |
| C7 | normal | `op.execute("CREATE INDEX ix ON \"public\".\"Users\" (x)")` | ref `users` |
| C8 | boundary | revision with no op calls; model with no migration | no edges; stats all 0 |
| C9 | boundary | same table touched 3× in one revision | one edge; matched = 1 |
| C10 | error | `op.create_table(TABLE_NAME)` (variable) | unresolvable 1; no edge |
| C11 | error | `op.drop_table("ghost")` no model | unmatched 1; no edge |
| C12 | error | two models with `__tablename__="users"` in different modules | one edge to first sorted id, ambiguous, candidates = [other] |
| C13 | edge | `-f fastapi -f sqlalchemy --json` on project with models+revisions | exit 0; no duplicate error; python-core nodes appear once; IMPLEMENTED_BY from sqlalchemy nodes to python-core ids present; MIGRATES edges present |
| C14 | edge | `-f sqlalchemy --no-language-graph` | no python-core nodes; no IMPLEMENTED_BY; MIGRATES present |
| C15 | edge | `-f sqlalchemy --no-models` | no model nodes; no MIGRATES; migration nodes present |
| C16 | edge | `op.create_foreign_key("fk", "posts", "users", ...)` | edges to posts and users models |
| C17 | edge | revision file outside versions dirs (e.g. `app/upgrade.py` with `def upgrade`) | not a migration node |
| C18 | edge | GraphAnalyzer on graph with MIGRATES edge | migration node effective_token_cost = 0.1 × token_cost |
| C19 | normal | `-f fastapi` / `-l python` / `-l kotlin` / `-l typescript` single runs; `-f android` on fixture without Room migrations | output identical to base commit |
| C20 | edge | Room `execSQL(sqlVar)` | unresolvable 1 |
| C21 | edge | SQL `CREATE TABLE IF NOT EXISTS posts (uid INTEGER REFERENCES users(id))` | refs [posts, users] |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | core behavior |
| Performance efficiency | no | per-file AST pass reusing existing parsers; no user target |
| Compatibility | yes | existing single-analyzer outputs must not change (C19) |
| Interaction capability | no | one CLI choice; covered by FR1 |
| Reliability | yes | determinism (FR12) |
| Security | no | no new input channels beyond repository files |
| Maintainability | no | no user target set |
| Flexibility | no | no user target set |
| Safety | no | no safety function |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| QR1 | Compatibility / co-existence | single runs `-f fastapi`, `-l python`, `-l kotlin`, `-l typescript`, and `-f android` on existing fixtures without Room migrations | existing suite + equality of JSON/bottlenecks against base-commit behavior; count of differing outputs | = 0 | automated; mutation | C19 |
| QR2 | Reliability / faultlessness | `-f sqlalchemy --json --bottlenecks` and `-f fastapi -f sqlalchemy --json` run twice on the same fixture | byte comparison; differing bytes | = 0 | automated | FR12 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VO1 | FR6, C7, C21 | `sql_table_refs`, `normalize_table_name` | unit | syntax testing | statements: CREATE TABLE, CREATE TEMP TABLE, IF NOT EXISTS, ALTER TABLE, ALTER…RENAME TO, DROP TABLE, DROP TABLE IF EXISTS, CREATE INDEX…ON, CREATE UNIQUE INDEX, REFERENCES; name forms: bare, "q", `q`, [q], schema.q, mixed case; non-DDL (INSERT/SELECT) → []; empty string | 100% | returned list equals expected | Test command |
| VO2 | FR8, C8, C9, C11, C12 | `match_migration_tables` | unit | decision table | 0/1/≥2 candidates; unresolvable (None) ref; duplicate ref in one migration; edge fields (relation, confidence, resolution, candidates, evidence, framework_rule, metadata.table); stats keys exact; edge ordering | 100% | edges + stats | Test command |
| VO3 | FR2, FR3, FR5, C1, C2, C5, C6, C10, C16, C17 | `SQLAlchemyAnalyzer` + `SQLAlchemyGraphBuilder` on tmp project | integration | equivalence partitioning | model forms: __tablename__ literal, SQLModel table=True, non-literal __tablename__ (not a model), plain class; migration location: alembic/versions, migrations/versions, other dir; op kinds: each FR5 op (create_table, drop_table, rename_table, add_column, drop_column, alter_column, create_index, drop_index with/without table_name, create_foreign_key, create_unique_constraint, drop_constraint, batch_alter_table, execute); positional vs keyword table arg; literal vs non-literal; refs in downgrade | 100% | node ids/groups/flags; MIGRATES edges; stats | Test command |
| VO4 | FR4, FR7, C3, C4, C20 | `AndroidAnalyzer` + `AndroidArchitectureGraphBuilder` on tmp project | integration | equivalence partitioning | migration forms: property object expression, class, object declaration; execSQL literal vs non-literal; entity tableName vs class name; language-node migration flag for class form; report collection presence/absence | 100% | nodes, flags, edges, stats | Test command |
| VO5 | FR1, FR9, FR10, C13, C14, C15 | CLI `main` on tmp project | integration | decision table | rules: `-f sqlalchemy` alone; + `--no-language-graph`; + `--no-models`; `-f fastapi -f sqlalchemy`; `-f sqlalchemy -f fastapi`; `-l python -f sqlalchemy`; `-f fastapi --no-language-graph -f sqlalchemy` (global flag → both omit, no python-core); `--entrypoint` with sqlalchemy only → exit 2; `-f sqlalchemy --mermaid` → exit 0 and stdout contains `graph`; D10 `-f android -f sqlalchemy` → merged `stats.migration_matching` equals the android-only run value; D11 project with a `.yaml` file + `-f fastapi -f sqlalchemy` → exit 0, `config:` ids unique; D12 `-f sqlalchemy --no-language-graph` on project with tests and yaml → no CONFIGURES/TESTS edges | 100% | exit code, node id uniqueness, python-core presence, IMPLEMENTED_BY targets exist, MIGRATES present/absent | Test command |
| VO6 | UI2, C18 | `GraphAnalyzer.analyze` on nodes from VO3/VO4 builders | integration | equivalence partitioning | alembic_migration node, room_migration node, flagged Kotlin class node | 100% | effective_token_cost = 0.1 × token_cost | Test command |
| VO7 | QR1, C19 | existing suite + base-commit equality | integration | equivalence partitioning | the five single-run variants in QR1 | 100% | no differing outputs | Test command + RE1 |
| VO8 | QR2, FR12 | two identical runs | integration | equivalence partitioning | the two run variants in QR2 | 100% | byte-identical | Test command |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
| --- | --- | --- | --- |
| A1 | Both stacks; migration multiplier stays 0.1; renames connect both names | user answers | user decision |
| A2 | `-f sqlalchemy` standalone; MIGRATES migration→model; new framework nodes for Alembic; DDL only | user answers | user decision |
| A3 | Language graph included but not re-emitted when fastapi/-l python already emits it (FR9) instead of relaxing the duplicate-id error | existing FR4 of spec 485e71fc64c8a984 is preserved | user decision |
| A4 | Table name match is case-insensitive and schema prefix is dropped | Unquoted SQL identifiers are case-insensitive in SQLite/Postgres; quoted names differing only by case merge. Same table name in two schemas maps to one key → `ambiguous` when two models share it | user approval (v1 whole-spec) |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| FR1 | C13 | VO5 | Test command |
| FR2 | C1, C5 | VO3 | Test command |
| FR3 | C1, C17 | VO3 | Test command |
| FR4 | C3, C4, C20 | VO4 | Test command |
| FR5 | C1, C2, C6, C10, C16 | VO3 | Test command |
| FR6 | C7, C21 | VO1 | Test command |
| FR7 | C3 | VO4 | Test command |
| FR8 | C8, C9, C11, C12 | VO2 | Test command |
| FR9 | C13, C14 | VO5 | Test command |
| FR10 | C15 | VO5 | Test command |
| FR11 | C3, C8 | VO3, VO4 | Test command |
| FR12 | — | VO8 | Test command |
| QR1 | C19 | VO7 | Test command |
| QR2 | — | VO8 | Test command |
| UI2 | C18 | VO6 | Test command |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 1 |
| verifier invocations | 2 |
| open finding ids | none (advisory A1 D12 positive control, A2 RE1 lines — A2 addressed below) |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| VO1, VO5(D1–D9), VO6, VO8 | 2 | verifier 1 accepted | accepted | — | reopen on change to listed tests |
| VO7 | 3 | RE1 lines: SAME fastapi_realworld a.json;SAME fastapi_realworld b.json;SAME fastapi_template a.json;SAME fastapi_template b.json;SAME fastapi_futurama a.json;SAME fastapi_futurama b.json;SAME python_futurama a.json;SAME python_futurama b.json;SAME kotlin_nia a.json;SAME kotlin_nia b.json;SAME ts_nest a.json;SAME ts_nest b.json;SAME android_nia a.json;SAME android_nia b.json; — 14/14 files SAME (7 runs × a.json, b.json) with PYTHONHASHSEED=0; existing suite | accepted (verifier 2) | F3 closed | — |
| VO2, VO3, VO4, VO5(D10–D12) | 3 | strengthened tests; 846 passed | accepted (verifier 2) | F1, F2, F4, F5 closed; M1–M3 detected | — |
| (superseded) VO1–VO8 | 2 | tests/test_migration_tables.py, tests/test_sqlalchemy_migration_edges.py, tests/test_room_migration_edges.py, tests/test_cli_sqlalchemy.py @ working tree after first implement/test; Test command 840 passed | pending | v2 clarifications change no tested expectation | — |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 1 | verifier 1: F1 matched not asserted for ambiguous; F2 model id exact form + zero-stats for add-nothing cases; F3 no base-commit evidence; F4 FR11 clauses unverified; F5 trimIndent unresolvable untested | test evidence gaps (F1,F2,F5); evidence procedure gap (F3); spec gap (F4) | tests strengthened; RE1 run; v3 adds D10–D12 | Test command 846 passed |
| 2 | D10 failed: duplicate node id config:config.yaml:debug in `-f android -f sqlalchemy` | test defect: fixture had config files; two enriching framework analyzers collide on config: ids — pre-existing (reproduced at base with `-f android -f fastapi`), out of scope | D10 fixture made config-free | 846 passed, 156 subtests |
| 3 | mutations M1 ambiguous also counted matched; M2 non-literal op.execute counted unresolvable; M3 sqlalchemy re-emits language graph in merged run | strongest classes: FR8 stats exclusivity (F1), FR5 add-nothing (F2), FR9 dedupe (core merge risk) | seed.py backup/inject/restore | M1 detected by test_VO2_D3_two_candidates_pick_first_sorted_id_C12; M2 by op_kinds[execute_non_literal_variable_adds_nothing]; M3 by test_D4_fastapi_then_sqlalchemy; restore ok |

# Version Log
## v1
- Initial draft from handoff 981eafd0004ac48b and user decisions (both stacks, 0.1 multiplier kept with Room flag, rename both names, `-f sqlalchemy`, MIGRATES migration→model, framework nodes, DDL only, language graph dedupe via non-emission).

## v2
- Clarified from implementer/test-implementer challenges (user approved 2026-10-01): exclusive stats keys; model id = dotted module + qualname; batch alias adds nothing (resolved FR5 contradiction); non-literal/`sa.text` execute ignored; `drop_index` without table adds nothing; trimIndent SQL unresolvable; Room class form top-level only; merged migration_matching first-wins; enrichment skipped when language graph not emitted. No behavior change to implementation; tests unaffected.

## v3
- Verifier 1 findings: VO7 evidence procedure RE1 added (F3); VO5 coverage items D10–D12 added for FR11 merged stats and enrichment skip (F4). User approved 2026-10-01.

## v3 closure
- Verifier 2 pass; complete. Advisory A1 (D12 positive control) left open as non-blocking.
