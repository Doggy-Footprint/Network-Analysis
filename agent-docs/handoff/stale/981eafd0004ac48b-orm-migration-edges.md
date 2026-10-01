# Add ORM model to migration edges

## Goal

“아직 안 한것들 handoff 들로 작성해줘” — 재구조화(커밋 `2a340fb`) 이후 남은 작업.

## Purpose

Connect ORM model definitions to the migrations that create or alter their tables.

## State

- Branch: `polish`; base commit: `2a340fb`.
- Changed files for this handoff: this file and `agent-docs/handoff/index.md`.
- Android analyzer emits Room DEFINES_ENTITY and QUERIES; Room migrations and schema JSON are not linked.
- No Python ORM (SQLAlchemy/Alembic, Django) analyzer exists.
- Migration files receive a 0.1 cost multiplier in `analysis/graph_metrics.py` (`_cost_multiplier`), which must stay consistent with new edges.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| None recorded | — | — |

## Next Step

Choose one stack (Room Migration classes, or Alembic `op.create_table`/`op.add_column` against SQLAlchemy `__tablename__`). Define table-name matching, confidence for string matching, and handling of renamed tables.

## Open Questions

- Room or a Python ORM first?
- Should migration nodes keep the 0.1 cost multiplier when they become edge endpoints?

## Spec

No workflow spec exists for this handoff. Version, status, and run ID: not applicable.

## Execution Ledger

- Finding: no model↔migration edges exist; disposition: implement after real-repository validation selects it.
- Evidence and mutation outcomes: source inspection only; no implementation mutation or verification run.
- Correction count: 0; verifier count: 0.
