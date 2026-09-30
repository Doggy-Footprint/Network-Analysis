# Repository-grounded exploration candidate rules

## Goal

“ROADMAP / ANALYSIS_APPROACH에서 이 남은 업무를 각각 handoff로 넘기자.” “탐색 후보 규칙에 관한 작업으로 재정의해줘.”

## State

- Branch: `master`; base commit: `ad8431b`.
- Changed files for this handoff: this file and `agent-docs/handoff/index.md`; source planning document `ROADMAP.md` is removed.
- The exploration graph already derives search candidates from repository identifiers, paths, literals, configuration keys, and documents. Profile transforms produce additional terms; framework edges and visible results can produce further candidates. The former relation-coverage wording referred to dependency edges and is superseded by this handoff. No new exploration rule has been selected.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| None recorded | — | — |

## Next Step

Select one reproducible repository case where a useful next search or read target is suggested by a repository clue but existing exact matches, derived terms, framework connections, and dependency edges do not expose it. Specify the clue, the fixed rule that maps it to a candidate, the candidate's repository evidence, and cases where the rule must yield no candidate. Record the rule and its version or identifier in the profile or output, then verify deterministic candidate generation and ordering on a fixed local case. Describe the output as a possible exploration path, not an observed agent action.

## Open Questions

- Which repository clue and intended destination should the first rule connect?
- What repository evidence is sufficient to emit that candidate, and what evidence should suppress it?

## Spec

No workflow spec exists for this handoff. Version, status, and run ID: not applicable.

## Execution Ledger

- Finding: `agent_view/exact_query.py`, `agent_view/derived_query.py`, and `agent_view/__init__.py` already generate bounded candidates with origins and rule identifiers; disposition: extend this exploration surface only for a selected repository-grounded case.
- Finding: dependency relation expansion and inferred agent behavior are outside this handoff; disposition: no analyzer edge or behavioral claim is requested.
- Evidence and mutation outcomes: source and roadmap inspection only; no implementation mutation or verification run.
- Correction count: 0; verifier count: 0.
