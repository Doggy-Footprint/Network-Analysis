# R1/R2 re-measure (spec fda1b3f71e2390f3 F11, Q01, Q02, Q05)

Inputs: `~/toy-projects/network-analysis-eval/inject/<repo>/score-symbols.txt` (previous, backed up with every run's result.json/delta.json, base and score.json in `backup-symbols/`) and `score-tests.txt`. Baselines regenerated with `harness.py baseline <repo>`; all 608 tasks re-analyzed with `tests/rename_comment_evidence/r1_reanalyze.py <repo> --match --workers 4` (2026-11-12 20:06–20:56, spec v3 implementation, commit fea60c7). Validity of every task is kept from the full run.

## Target types (valid / analyzer located / analyzer matched)

| type | symbols | tests |
| --- | --- | --- |
| P11 error path untested | 8 / 3 / 0 | 8 / 7 / 7 |
| P15 changed code untested | 6 / 3 / 1 | 6 / 5 / 5 |
| P11 + P15 (I1: located ≥ 7, matched ≥ 3) | 14 / 6 / 1 | 14 / 12 / 12 |
| P12 test manipulation (I2: ≥ 3 / ≥ 2) | 8 / 0 / 0 | 8 / 5 / 3 |
| P13 weak or absent oracle (I2: ≥ 5 / ≥ 3) | 7 / 1 / 0 | 7 / 5 / 5 |
| P14 over-mocking (I3: ≥ 5 / ≥ 3) | 7 / 1 / 0 | 7 / 7 / 7 |

Misses:
- P11 CTFd script-0 and P15 ghostfolio script-0: no delta item on the touched file.
- P12:
  - CTFd and flask-admin sonnet-0 special-case test inputs in production code, which is out of scope.
  - nowinandroid script-0 replaces `assertEquals(obj)` with `assertEquals(3, size)`, so its strong-assertion count is unchanged.
  - ghostfolio and nowinandroid sonnet-0 are located through `untested_changes` only and not matched.
- P13 CTFd and flask-admin sonnet-0: no delta item on the touched file.

Delta lists on the target tasks:

| list | P11 | P12 | P13 | P14 | P15 |
| --- | --- | --- | --- | --- | --- |
| `untested_changes` | 7 | — | — | — | 5 |
| `weakened_tests` | — | 3 | 5 | — | — |
| `added_mocks` | — | — | — | 7 | — |

## Analyzer false positives on negative controls (valid / analyzer located)

| control | valid | symbols | tests |
| --- | --- | --- | --- |
| NC1 rename | 16 | 2 | 2 |
| NC2 format | 16 | 1 | 1 |
| NC3 comments | 13 | 0 | 0 |
| NC4 refactor | 14 | 0 | 0 |

The remaining false positives are unchanged from before: flask-admin NC1-0 and NC1-1, and ghostfolio NC2-0, all `strengthened_candidates`. No control has an item from the three new lists.

## Weighted type recall, analyzer (matched / located)

| repo | method | matched symbols → tests | located symbols → tests |
| --- | --- | --- | --- |
| CTFd | script | 0.146 → 0.169 | 0.423 → 0.638 |
| CTFd | sonnet | 0.111 → 0.153 | 0.292 → 0.382 |
| flask-admin | script | 0.069 → 0.193 | 0.331 → 0.703 |
| flask-admin | sonnet | 0.122 → 0.236 | 0.351 → 0.486 |
| ghostfolio | script | 0.108 → 0.216 | 0.351 → 0.577 |
| ghostfolio | sonnet | 0.133 → 0.267 | 0.319 → 0.556 |
| nowinandroid | script | 0.110 → 0.173 | 0.520 → 0.646 |
| nowinandroid | sonnet | 0.036 → 0.130 | 0.254 → 0.384 |

No repo × method cell dropped. Three tasks lost an analyzer match while their located result stayed:
- CTFd P16-script-0 gained an `untested_changes` item.
- nowinandroid G21-script-0 gained an `untested_changes` item.
- flask-admin P02-sonnet-0 kept the same delta item.

In all three, the earlier match rested on an indirect symptom (an unreferenced symbol), which the judge rejected this time. No task lost a located result.

## R2 size and time (base 0f17dd2 vs current, CLI on the clone at `base`)

| repo | bytes base → current | bytes ratio | time base → current (s) | time ratio |
| --- | --- | --- | --- | --- |
| CTFd | 1,693,212 → 1,804,149 | 1.066 | 3.77 → 4.25 | 1.127 |
| flask-admin | 1,474,820 → 1,523,057 | 1.033 | 2.45 → 2.49 | 1.016 |
| ghostfolio | 14,938,201 → 15,158,867 | 1.015 | 14.65 → 14.87 | 1.015 |
| nowinandroid | 2,439,655 → 2,510,692 | 1.029 | 3.85 → 3.99 | 1.036 |

Times are the minimum of 3 runs per side. The exception is CTFd: the first 3-run pass gave 3.80 → 4.43 (1.166), with base runs spread over 3.80–4.69 s. A second pass alternating base and current 5 times each gave 3.77–3.81 → 4.25–4.31, so the CTFd row reports that pass.

Judge spend of the re-measure: $3.34 (match calls saved in result.json).
