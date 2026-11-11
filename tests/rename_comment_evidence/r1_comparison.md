# R1 re-measure (spec 73bd5aa508fa3e88 F10, Q06)

Inputs: `~/toy-projects/network-analysis-eval/inject/<repo>/score-full.txt` (full run 2026-11-11 07:55, analyzer at 1bd6ebe) and `score-fp-fix.txt` (2026-11-11 13:48-14:26, `r1_reanalyze.py <repo> --match --workers 4`, two streams, baselines regenerated with `snapshot.git_commit` = clone HEAD for all four repos). Validity of every task is kept from the full run. flask-admin P21-sonnet-0 and P22-sonnet-0 were re-judged with `--only` because the first judge answer was not parseable JSON (verdict null, counted as infra_failed).

## Analyzer false positives on negative controls (valid / analyzer FP)

| control | valid | full run | fp-fix | any tool, both runs |
| --- | --- | --- | --- | --- |
| NC1 rename | 16 | 15 | 2 | 3 |
| NC2 format | 16 | 1 | 1 | 8 |
| NC3 comments | 13 | 4 | 0 | 4 |
| NC4 refactor | 14 | 0 | 0 | 1 |

NC1 remainder: flask-admin NC1-0 and NC1-1, `large_node` `token_count` on `flask_admin/model/base.py` (longer import path, out of scope). NC2 remainder: ghostfolio NC2-0 `large_node` (out of scope).

## Weighted type recall, analyzer (matched / located)

| repo | method | matched full → fp-fix | located full → fp-fix |
| --- | --- | --- | --- |
| CTFd | script | 0.046 → 0.046 | 0.231 → 0.231 |
| CTFd | sonnet | 0.069 → 0.069 | 0.174 → 0.174 |
| flask-admin | script | 0.007 → 0.007 | 0.152 → 0.152 |
| flask-admin | sonnet | 0.054 → 0.054 | 0.250 → 0.250 |
| ghostfolio | script | 0.063 → 0.063 | 0.252 → 0.252 |
| ghostfolio | sonnet | 0.037 → 0.044 | 0.200 → 0.200 |
| nowinandroid | script | 0.032 → 0.032 | 0.354 → 0.354 |
| nowinandroid | sonnet | 0.015 → 0.015 | 0.239 → 0.188 |

Drop above 0.02: nowinandroid sonnet located (-0.051), three tasks whose analyzer item disappeared; none was matched in either run.

| task | type | full-run located item | cause |
| --- | --- | --- | --- |
| G12-sonnet-0 | concrete class injection (w1) | grown dependency cycle | the baseline cycle the new SyncWorker -> StubSyncSubscriber edge joined was held together by comment-only edges (base resolved-tier cycle with SyncWorker: 114 members -> 3) |
| P23-sonnet-0 | encapsulation violation (w3) | 3 strengthened (evidence_spread, unstable_dependency) | added KDoc line naming `[onSearchTriggered]` |
| P29-sonnet-0 | excessive comments (w3) | 4 new package dependencies, 5 new candidates | all 17 added lines are comments |

Check: base 1bd6ebe analyzer on the diff-applied worktree reproduces each full-run item (grown cycles 1; strengthened 3; new package dependencies 4 / new candidates 5); on a copy with only comments blanked (`android_golden/mask_fixture.py`) those counts are 0 (the 39 new candidates and 1 instability change there come from comparing a blanked tree with an unblanked baseline).

Judge spend of the re-measure: 249 calls, about $2.60.
