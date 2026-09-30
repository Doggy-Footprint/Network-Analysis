# Validate bottlenecks.v3 and edge weights on a real repository

## Goal

“아직 안 한것들 handoff 들로 작성해줘” — 재구조화(커밋 `2a340fb`) 이후 남은 작업.

## Purpose

Run bottlenecks.v3 with default edge weights on a pinned real repository and check whether rankings and candidates are usable.

## State

- Branch: `polish`; base commit: `2a340fb`.
- Changed files for this handoff: this file and `agent-docs/handoff/index.md`.
- `fixtures/registry.py` pins `android-nowinandroid` (and other fixtures) for network clone.
- `bottlenecks.v3` and `profiles/edge_weights.v1.yaml` have only been exercised on small in-repo graphs; no real-repository output exists since the refocus.
- Stale handoff `2a5f8873bb660577-nowinandroid-bottlenecks.md` produced a v2 report before the refocus.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| None recorded | — | — |

## Next Step

Clone the pinned fixture, run `code_analyzer.cli` with `-f android --bottlenecks --bottlenecks-html` using default weights, then with all weights 1.0. Compare top-10 rankings (pagerank, hub/authority, weighted_fan_in) and candidate counts per kind. Record which differences come from non-certain edges and whether `large_node` (2000 lines) and `evidence_spread` produce useful or noisy candidates.

## Open Questions

- Which repositories besides Now in Android (e.g. a FastAPI fixture) should be included?
- What observation counts as "usable" (manual review of top-k, or a fixed checklist)?
- Whether to keep the 0.3 default and 2000-line threshold after review.

## Spec

No workflow spec exists for this handoff. Version, status, and run ID: not applicable.

## Execution Ledger

- Finding: no real-repository run of v3; disposition: run before choosing which network expansion to implement first.
- Evidence and mutation outcomes: source inspection only; no implementation mutation or verification run.
- Correction count: 0; verifier count: 0.
