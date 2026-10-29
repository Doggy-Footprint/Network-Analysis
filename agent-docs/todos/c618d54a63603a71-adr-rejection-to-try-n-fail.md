---
commit: c34d6f455add1c78c06f8079030888487daa3425
---

# Migrate ADR and rejection records to try-n-fail

## User Query
Harness 0.29.0 replaced the ADR and rejection record rules with the try-n-fail rule. Review the ADR and rejection records below and move what a later task still needs into `agent-docs/try-n-fail/`. How each record is handled depends on the repository's current state and the user's choices.

## State
Written by `harness.py update` (migration 0.29.0); no code or record was changed. Records to review (`stale/` entries are history):
- `agent-docs/adr/07e12b7114048d41-json-baseline-ratchet.md`
- `agent-docs/adr/31d2dee6912427d5-consolidate-overlapping-metrics.md`
- `agent-docs/adr/58424b9754efe9a2-package-grouping-schemes.md`
- `agent-docs/adr/b8a976686050faf6-evidence-spread-by-directory.md`

## Failed Attempts
| attempt | failure evidence | cause |
| --- | --- | --- |
| none | none | none |

## Next Step
1. Read each record and check its claims against the current code.
2. Per record, propose one of these to the user, with the reason: convert the rejected alternatives or failed approaches a later task could try again into try-n-fail attempts (cause `user rejected: <reason>` or `verified`/`hypothesis`) with a Revisit Condition; otherwise recommend deleting it. A decision the code already shows needs no record.
3. Write and delete only what the user confirms, following the Try-n-Fail Rule in `AGENTS.md`. When no record is left, recommend deleting `agent-docs/adr/` and `agent-docs/rejections/` with their `index.md`, `stale.md`, and `stale/`. The harness does not manage these directories after this step; whatever the user keeps stays as it is.
4. Mark this handoff stale under the Index & Staleness Management rule.

## Open Questions
- Which records the user wants converted or deleted, and whether to delete the emptied directories.

## Spec
none — not a workflow-approach task.

## Execution Ledger
none
