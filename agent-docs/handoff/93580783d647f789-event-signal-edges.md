# Add event/signal publish-subscribe edges

## Goal

“아직 안 한것들 handoff 들로 작성해줘” — 재구조화(커밋 `2a340fb`) 이후 남은 작업.

## Purpose

Connect event or signal emitters to their handlers as explicit dependency edges.

## State

- Branch: `polish`; base commit: `2a340fb`.
- Changed files for this handoff: this file and `agent-docs/handoff/index.md`.
- Existing framework edges: FastAPI (ROUTES, INCLUDES, DEPENDS_ON, SUB_DEPENDENCY, REQUEST_BODY, RESPONSE_MODEL, MIDDLEWARE_OF), Android (INJECTS, PROVIDES, BINDS, INSTALLS_IN, USES_VIEWMODEL, HOSTS, DEFINES_ENTITY, QUERIES, CALLS_API).
- No analyzer links an emit/dispatch site to a subscriber; such pairs appear disconnected in the call graph.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| None recorded | — | — |

## Next Step

Pick one concrete mechanism present in a pinned fixture (e.g. Kotlin Flow/SharedFlow collectors, FastAPI startup/shutdown handlers, or a named event bus). Define the matching key (event type or name literal), confidence (`framework_inferred` or `static_inferred`) and resolution (`ambiguous` with `candidates` for multiple subscribers), and the evidence span.

## Open Questions

- Which mechanism and which fixture first?
- New relation kind name, or reuse CALLS with inferred confidence?

## Spec

No workflow spec exists for this handoff. Version, status, and run ID: not applicable.

## Execution Ledger

- Finding: no event/signal edges exist; disposition: implement after real-repository validation selects it.
- Evidence and mutation outcomes: source inspection only; no implementation mutation or verification run.
- Correction count: 0; verifier count: 0.
