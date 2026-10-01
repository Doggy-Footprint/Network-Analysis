# Add analyzers for additional frameworks

## Goal

“아직 안 한것들 handoff 들로 작성해줘” — 재구조화(커밋 `2a340fb`) 이후 남은 작업.

Resumed task: implement the supplied “NestJS 분석기 추가 및 핸드오프 완료 계획”; the user then requested “continue sub agents”. NestJS modules, routes and basic DI are the selected scope.

## Purpose

Extend framework-specific connectivity beyond FastAPI and Android.

## State

- Branch: `polish`; HEAD and workflow base: `c0191a4ecf598a59de8bf49d760f270b1fe0dedc`. Historical handoff base: `2a340fb`. No implementation commit created.
- Implementation changes: `framework_analyzers/nestjs/{__init__,models,analyzer,graph}.py`, `code_analyzer/cli.py`.
- Verification changes: `tests/nestjs_support.py`, `tests/test_nestjs_analyzer.py`, `tests/test_nestjs_cli.py`, `tests/test_nestjs_quality.py`, `tests/nestjs_evidence/`.
- Workflow records: this handoff and `agent-docs/spec-logs/7a2c91e6d80f4b35-nestjs-analyzer.md`. The original index entry remains live; success-only stale movement has not occurred.
- NestJS source extraction, graph/report integration and CLI selection are implemented. The last exact full command `.venv/bin/python -m pytest -q` passed **883 tests and 194 subtests in 24.10 seconds** under a 180-second timeout.
- Three required mutations were detected by their intended assertions and restored byte-identically. Seed status is `none`.
- Final independent audit is `retry`: three required observations remain unverified. This is a verification evidence gap, not an established implementation defect. The approved verifier budget is exhausted; workflow status is `limit`.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| None recorded | — | — |
| Initial integration | 6 failed, 876 passed, 184 subtests; prefix and mixed FastAPI observations failed | verified: AST node identity prevented prefix attachment; test assumed an unsupported FastAPI ID prefix |
| Second integration | 1 failed, 878 passed, 191 subtests; nested class observation failed | verified: test added nested-function class declaration grammar outside the approved exported/plain-class scope; lexical shadow implementation was corrected separately |
| Verifier 1 | `tests/nestjs_evidence/verifier-1.md`: V1–V6, O2/O3/O4/O6/O7/O9 evidence gaps | verified: assertions omitted multiplicity, file-qualified targets, metadata, output ownership and report observations |
| Correction batch 3 reconciliation | 4 failures in strengthened evidence; then source-authored implementation-target oracle missed ValidationPipe | verified: combined graph metrics differ, changed fixture anchor invalidated replacement, no-bootstrap diagnostic was missing, and the fixture oracle omitted an Injectable pipe declaration |
| Verifier 2 | `tests/nestjs_evidence/verifier-2.md`: V7/O5, V8/O6, V9/O7 remain blocking despite green full suite | verified: declared rows do not observe retained relative paths, full explicit-TypeScript output under no-language-graph, or ambiguous route-call source |

## Next Step

The user explicitly chose “기존 2회 제한 유지” after the limit handoff. Stop this run without further source/test corrections or verifier dispatches. Any future recovery requires a new explicit user decision changing that policy; a replacement run must not reset the invocation count.

After an explicitly authorized policy change, strengthen only the declared missing observations:

1. V7: for each absent/multiple/unresolved bootstrap and dynamic/multiple/options prefix row, assert the endpoint retains `/x/y` as `relative_path` while `full_path` remains null.
2. V8: compare the explicit TypeScript + `--no-language-graph` scenario against TypeScript-only source nodes, language edges, enrichment and HTTP calls, while keeping NestJS `IMPLEMENTED_BY` absent.
3. V9: assert the ambiguous GET candidate edge originates from `getOk`, with the existing exact target/candidate policy.

Run the exact full command with a 180-second timeout, record change impact, and obtain independent acceptance under the authorized recovery policy. Only then complete O14: archive the completed spec and move the original index block and handoff to stale while preserving every Failed Attempts row.

## Open Questions

- The framework and analysis-config questions are resolved by the supplied NestJS plan and its builder contract.
- No current policy question is pending: the user chose to retain the two-verifier limit. V7–V9 remain unresolved. No third verifier has been invoked and no post-audit source/test corrections were made.

## Spec

Archived spec: `agent-docs/spec-logs/7a2c91e6d80f4b35-nestjs-analyzer.md`, version 2, status `limit`, run ID `7a2c91e6d80f4b35`. User-approved functional scope and quality thresholds are unchanged.

## Execution Ledger

- Historical finding: only two framework analyzers; user selected NestJS through the supplied plan.
- Current accepted obligations: O1–O4, O8–O13. Open: V7/O5, V8/O6, V9/O7. O14 success closure is deferred.
- V1–V3/V6 closed; V4 narrowed to V8 and V5 narrowed to V9. Main accepted the final three findings as blocking evidence gaps; no spec challenge was raised.
- Baseline: 846 passed, 156 subtests. Current restored full suite: 883 passed, 194 subtests. Eight pre-change standalone JSON/bottlenecks comparisons pass, as do determinism, snapshot isolation and layering checks. Detailed inputs, hashes and obligation mapping: `tests/nestjs_evidence/{coverage.md,run-evidence.json,baselines.json,fixture-oracle.json}`.
- M1 unresolved-reference name guessing: intended O2 assertion detected extra guessed links; 1 failed, 882 passed, 192 subtests. M2 dropped global prefix: intended O10 fixture-route assertion detected missing `/api`; 3 failed, 881 passed, 191 subtests. M3 duplicate TypeScript emission: intended O6 ownership assertion detected duplicate node IDs; 7 failed, 879 passed, 189 subtests. Executions and restores are recorded in `tests/nestjs_evidence/{mutation-results.json,mutations.md}`.
- All mutations restored the original implementation bytes. The later exact weight-profile/implementation-target assertions left the intended mutation assertions and their inputs unchanged; the final full suite reconfirmed the restored state.
- Correction batches: 3. Verifier invocations: **2/2**. Final audit: `tests/nestjs_evidence/verifier-2.md`. No source/test changes after that audit. Spec ledger preserves every attempt and final disposition.
- Limit closure: keep this handoff and its index entry live, archive the limit spec, remove the active workflow marker, and preserve the original Failed Attempts row. The success-only stale-move procedure remains in `tests/nestjs_evidence/closure-evidence.json` with no success after-state claimed.

- User disposition after limit archive: “continue” prompted an explicit policy clarification; the user selected “기존 2회 제한 유지”. The archived spec remains immutable, and the run remains `limit`.
