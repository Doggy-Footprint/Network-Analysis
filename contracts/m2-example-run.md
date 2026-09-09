---
version: 2
---

# Signatures
fixtures/harness-evaluation/independent-python-structure-before-run.v1.json: harness_evaluation_run.v1 input
`bottlenecks.evaluation.main(["evaluate", case, run, profile, "-s", support, "-o", result])`: writes harness_run_evaluation.v1 JSON
`report.m2.generate.generate_report(result, html)`: writes one offline HTML report

# Errors
EvaluationRunError — the fixture no longer binds to the structure case or fixed baseline profile.

# Edge Cases
| id | input / state | expected result |
| --- | --- | --- |
| M2R-E01 | Structure case, fixed profile/support, and included declared run fixture | `evaluate` writes an eligible `harness_run_evaluation.v1` with burden `{total_calls: 3, search_calls: 1, read_calls: 0, preparation_calls: 0, failed_calls: 0, returned_items: 2, returned_lines: 1, duplicated_exposure: 0}`; `report.m2.generate` converts those exact bytes to one offline HTML report. |

# Version Log
## v1
- Added a runnable example because no committed M2 run fixture existed.

## v2
- Fixed the run fixture's declared trace, support binding, and independently specified evaluation result so the example can be generated and regression-tested.
