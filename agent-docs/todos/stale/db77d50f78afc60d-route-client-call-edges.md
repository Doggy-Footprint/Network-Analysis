# Add route string to client call edges

## Goal

“아직 안 한것들 handoff 들로 작성해줘” — 재구조화(커밋 `2a340fb`) 이후 남은 작업.

## Purpose

Connect client-side HTTP calls to the server route handlers they target by path string.

## State

- Branch: `polish`; base commit: `2a340fb`.
- Changed files for this handoff: this file and `agent-docs/handoff/index.md`.
- FastAPI analyzer builds ROUTES with full paths including router prefixes (fix in `81db064`).
- Android CALLS_API links to API interface declarations but not to server routes; TypeScript fetch/axios calls are not linked to any route.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| None recorded | — | — |

## Next Step

Define path normalization (prefix, path parameters like `{id}` vs `${id}`, trailing slash, HTTP method) and a cross-language matching pass over the combined node set. Unmatched or multiple matches become `unresolved`/`ambiguous` edges with candidates so recall is kept under the edge-weight policy.

## Open Questions

- Which client side first (TypeScript or Android Retrofit)?
- Does a single run need to analyze two languages together, and how does the CLI accept that?

## Spec

No workflow spec exists for this handoff. Version, status, and run ID: not applicable.

## Execution Ledger

- Finding: no route↔client edges exist and CLI analyzes one language/framework per run; disposition: requires a multi-analyzer run design decision.
- Evidence and mutation outcomes: source inspection only; no implementation mutation or verification run.
- Correction count: 0; verifier count: 0.
