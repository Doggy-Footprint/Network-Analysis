# Category rankings: V6 HTML evidence gap after verifier budget

## Goal

"그렇게 해" — handoff ec9d04784407ee5b 권고 2번: 순위를 production/test/generated/vendored로 분리해서 표시.

## State

- Branch: `polish`; base commit: `698402c`; uncommitted.
- Changed files for this run: bottlenecks/core.py, report/bottlenecks/generate.py, tests/test_category_rankings_v3.py.
- Same working tree also holds the separate fixture fix (fixtures/registry.py, tests/test_fixture_registry.py) and handoff ec9d04784407ee5b edits.
- Test command `.venv/bin/python -m pytest -q`: 562 passed, 114 subtests passed.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| V6 v1: node ids after the "분류별 순위" heading | verifier 1 B1/S1: misattributed ids and dropped metrics pass | no per-category marker in spec v1 (verified) |
| V6 v2: per-`data-category` div, `metric in div` substring check | verifier 2 B2; mutation M6 (drop `fan_in`/`fan_out` panels in category divs) → 25 passed | "fan_in" is a substring of "weighted_fan_in" (verified) |

## Next Step

Strengthen the V6 metric check in tests/test_category_rankings_v3.py so each metric panel is matched exactly (e.g. the panel `<h3>metric</h3>` title, which F6 would need to name as the observable), then rerun M6 and M7 (swap two metrics' entry lists). A new workflow run is needed because the verifier budget is spent.

## Open Questions

- Whether F6 should name the panel title element (`<h3>metric</h3>`) as the observable for exact metric matching.

## Spec

agent-docs/spec-logs/3ea9cf8886ee409f-category-rankings.md, version 2, status limit, run ID 3ea9cf8886ee409f.

## Execution Ledger

- Findings: S1 resolved by spec v2 (user approved); B1 resolved by V6 rewrite; B2 open (V6).
- Accepted: V1–V5, V7. Open: V6.
- Mutations: M1 cap-before-filter, M2 precedence flip, M3 reversed ties, M4 first-metric-only, M5 no-data everywhere — detected; M6 fan_in/fan_out dropped — not detected; M7 not run.
- Correction count: 1; verifier count: 2 of 2.
