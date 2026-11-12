# R1/R2 re-measure (spec 338f748639b68776 F09, Q01, Q02, Q05)

Inputs: `~/toy-projects/network-analysis-eval/inject/<repo>/score-fp-fix.txt` (previous, backed up with result.json/delta.json and base in `backup-fp-fix/`) and `score-symbols.txt`. Baselines regenerated with `harness.py baseline <repo>`; all 608 tasks re-analyzed with `tests/rename_comment_evidence/r1_reanalyze.py <repo> --match --workers 4` (2026-11-12, spec v5 implementation); after the v6 signature comparison the 41 tasks whose delta had `changed_signatures` were re-run with `--only`. Validity of every task is kept from the full run.

## Target types (valid / analyzer located / analyzer matched)

| type | fp-fix | symbols |
| --- | --- | --- |
| P50 breaking change | 7 / 0 / 0 | 7 / 6 / 6 |
| P20 unnecessary method | 8 / 3 / 0 | 8 / 8 / 8 |

P50 miss: ghostfolio P50-script-0 (no delta item on the touched file).

## Analyzer false positives on negative controls (valid / analyzer FP)

| control | valid | fp-fix | symbols, v5 | symbols, v6 |
| --- | --- | --- | --- | --- |
| NC1 rename | 16 | 2 | 2 | 2 |
| NC2 format | 16 | 1 | 4 | 1 |
| NC3 comments | 13 | 0 | 0 | 0 |
| NC4 refactor | 14 | 0 | 0 | 0 |

v5 NC2 additions (ghostfolio NC2-1, NC2-3, nowinandroid NC2-1) were `changed_signatures` from formatter-only differences: `deleteMany({ dataSource, symbol }: AssetProfileIdentifier)` vs `deleteMany({ dataSource, symbol, }: AssetProfileIdentifier)`, `UserWithSettings['createdAt']` vs `UserWithSettings["createdAt"]`, `configureAndroidCompose( commonExtension: CommonExtension, )` vs `configureAndroidCompose(commonExtension: CommonExtension)`. Remaining NC2: ghostfolio NC2-0 (`strengthened_candidates`, as before).

## Weighted type recall, analyzer (matched / located)

| repo | method | matched fp-fix → symbols | located fp-fix → symbols |
| --- | --- | --- | --- |
| CTFd | script | 0.046 → 0.146 | 0.231 → 0.423 |
| CTFd | sonnet | 0.069 → 0.111 | 0.174 → 0.292 |
| flask-admin | script | 0.007 → 0.069 | 0.152 → 0.331 |
| flask-admin | sonnet | 0.054 → 0.122 | 0.250 → 0.351 |
| ghostfolio | script | 0.063 → 0.108 | 0.252 → 0.351 |
| ghostfolio | sonnet | 0.044 → 0.133 | 0.200 → 0.319 |
| nowinandroid | script | 0.032 → 0.110 | 0.354 → 0.520 |
| nowinandroid | sonnet | 0.015 → 0.036 | 0.188 → 0.254 |

No task lost an analyzer located or matched result. Newly matched tasks by type (v5 run): P20 8, P50 6, G12 3, G05 2, G04 2, and one each for P15, P16, G18, P02, G08, G13, P24, G21, P27. Delta lists on newly located tasks: new_candidates 28, changed_signatures 17, strengthened_candidates 12, removed_symbols 4. The match judge reran for every task, so tool-only matched values moved by judge variance (any tool: ghostfolio script 0.108 → 0.081, CTFd sonnet 0.278 → 0.299).

## R2 size and time (base 075881f vs current, CLI on the clone at `base`, 3 runs, minimum)

| repo | bytes ratio | time base → current (s) | time ratio |
| --- | --- | --- | --- |
| CTFd | 1.121 | 3.64 → 3.67 | 1.008 |
| flask-admin | 1.266 | 2.15 → 2.18 | 1.014 |
| ghostfolio | 1.052 | 13.14 → 13.69 | 1.042 |
| nowinandroid | 1.104 | 3.62 → 3.69 | 1.019 |

Judge spend of the re-measure: about $2.7 (match calls saved in result.json $2.64 plus the replaced first-pass calls of the 41 re-run tasks).
