# Add analyzers for additional frameworks

## Goal

“아직 안 한것들 handoff 들로 작성해줘” — 재구조화(커밋 `2a340fb`) 이후 남은 작업.

## Purpose

Extend framework-specific connectivity beyond FastAPI and Android.

## State

- Branch: `polish`; base commit: `2a340fb`.
- Changed files for this handoff: this file and `agent-docs/handoff/index.md`.
- Framework analyzers exist for FastAPI and Android only (`framework_analyzers/`). Language analyzers exist for Python, TypeScript, Kotlin.
- Both framework analyzers follow the pattern: language graph + framework nodes + named edges with rule_id, evidence span, confidence.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| None recorded | — | — |

## Next Step

Select a target framework with a pinned fixture and list its implicit connections (DI, routing, templates, config binding). Implement following the Android/FastAPI builder pattern, including the analysis-config handling decided in handoff `3a1c71a7afc82a15`.

## Open Questions

- Which framework (e.g. Django, Flask, NestJS, Spring)?
- Should this wait for handoff `3a1c71a7afc82a15` so the new builder does not repeat the duplicated analysis?

## Spec

No workflow spec exists for this handoff. Version, status, and run ID: not applicable.

## Execution Ledger

- Finding: only two framework analyzers; disposition: user selects target.
- Evidence and mutation outcomes: source inspection only; no implementation mutation or verification run.
- Correction count: 0; verifier count: 0.
