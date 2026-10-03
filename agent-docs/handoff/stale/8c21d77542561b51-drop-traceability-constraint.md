# Drop the result traceability constraint

## Goal

“모든 결과는 스냅샷, 소스 근거, 버전이 붙은 profile로 역추적할 수 있다. — 이건 불필요한 제약이야. 삭제하는 걸 handoff로 넣어줘.”

## Purpose

The project definition in `AGENTS.md` no longer requires every result to be traceable to a snapshot digest, source evidence, and versioned profile hashes. Remove code and records that exist only to enforce that requirement.

## State

- Branch: `polish`; base commit: `355feab` plus uncommitted `AGENTS.md`/`README.md` rewrites.
- `AGENTS.md` Project Definition: the traceability sentence is already removed by the user.
- Mechanisms that currently implement traceability:
  - `repository/scan.py` `build_snapshot` computes `RepositorySnapshot.digest`; `repository/policy.py` records `ScanPolicy.content_hash`.
  - `analysis/edge_weights.py` records `EdgeWeights.content_hash`; `bottlenecks/core.py` echoes weights `id`/`version`/`content_hash` and `snapshot.digest` in `bottlenecks.v3`.
  - `bottlenecks/core.py` `_validate` rejects an architecture whose `snapshot_digest` differs from the snapshot; `language_analyzers/python/graph.py` sets `snapshot_digest`.
  - `README.md` Profiles section states every report records profile id, version, and content hash.
- Tests asserting these fields: `tests/test_edge_weights.py`, `tests/test_bottlenecks_v3.py`, `tests/test_cli_bottlenecks_v3.py`, `tests/test_report_bottlenecks_v3.py`, `tests/test_repository_scan.py`, `tests/test_fixture_registry.py`, `tests/test_nestjs_cli.py`, `tests/test_nestjs_quality.py`.
- ADR `77ee4cf0755552e5-versioned-profile-files.md` (versioned profile with hash for traceability) is moved to `adr/stale/` together with this handoff.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| None recorded | — | — |

## Next Step

Decide the removal scope (Open Questions), then remove the selected fields and checks, update the report schema version if output keys change, and update the README Profiles section and affected tests.

## Open Questions

- Which mechanisms to remove: profile `content_hash`/`version` echo, report `snapshot.digest`, the architecture–snapshot digest check, `ScanPolicy.content_hash`, or all?
- Do candidate `evidence` spans stay? They serve the reviewer, not only traceability.
- Does the immutable snapshot itself stay? It also keeps all analyzers reading the same file set within one run.
- Does `fixtures/registry.py` content pinning (`content_sha256`) stay as test reproducibility rather than result traceability?
- If report keys change, is it `bottlenecks.v4` or an in-place v3 change?

## Spec

No workflow spec exists for this handoff. Version, status, and run ID: not applicable.

## Execution Ledger

- Finding: traceability sentence removed from the project definition by the user; disposition: implementation removal deferred to this handoff.
- Evidence and mutation outcomes: source inspection only; no implementation mutation or verification run.
- Correction count: 0; verifier count: 0.
- Decisions (user): remove profile `content_hash`/`id`/`version` echo, report `snapshot.digest`, the architecture–snapshot digest check, and `ScanPolicyRef.content_hash`; keep candidate `evidence`, the immutable snapshot, and `fixtures/registry.py` `content_sha256`; report schema becomes `bottlenecks.v4`.
- Completion: removals applied; `tests/nestjs_evidence/baselines.json` bottlenecks hashes regenerated after confirming all eight cases differ from the previous commit only by the removed keys and schema name; full suite passed (914 passed).
