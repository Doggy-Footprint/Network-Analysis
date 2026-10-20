# Review evidence (spec e91abc221d7deb2a v5, V12 · V14 · Q1 · Q4)

## Procedure (repeatable)
1. Base tree: `git worktree add --detach <scratch>/basewt cf0cf4446106f44026dc40d00ba09df977d61ecc` and `ln -s <repo>/.fixtures <scratch>/basewt/.fixtures`.
2. Outputs: `SELF=<scratch>/basewt review_run.sh <scratch>/basewt <scratch>/review/base`, then `SELF=<scratch>/basewt review_run.sh <repo> <scratch>/review/head`. For each of self (`-l python` on the base worktree's own sources, so both sides read identical input), `typescript-nestjs-realworld` (`-l typescript`), `android-nowinandroid` (`-l kotlin`), `futuramaapi`, `fastapi-realworld` (`-l python`), and each `--granularity file|symbol`, it writes the architecture JSON (`--json`, `<name>-<mode>.json`) and the bottleneck JSON (`<name>-<mode>.b.json`), with `PYTHONHASHSEED=0`.
3. Diff: `review_diff.py <scratch>/review/base <scratch>/review/head <name> <mode> review-output/<name>-<mode>.json` for all 10 pairs. The script compares the node id set, per-node flags, per-node metadata keys and values, the edge multiset keyed by (from, to, relation, resolution, confidence, evidence line, candidates), JSON key paths of records present on both sides, every candidate kind (removed, added and changed counts, up to 10 samples per change type with metrics before and after), and the structural metrics fan_in, fan_out, token_cost, betweenness and hop_2. Each difference gets an R id from fixed rules (in the script). Anything without a rule is listed under `unexplained`.
4. Wall time: `perf.py <scratch>` runs file-mode `--bottlenecks` on android, nestjs and self, alternating base and HEAD three times each, and reports the median.

Attribution rules worth stating:
- R4 edge removal: a Kotlin class edge is attributed only when a member of that class has the same (target, relation) in HEAD, or the target is the class's own member (the class used to read the member at its declaration site). A TESTS edge is attributed when the class-level relations it was derived from are gone, or its target is the class's own member. A file-mode edge is attributed when the symbol-mode diff of the same input removed an R4 edge between those two files.
- Structure kinds (dependency_cycle, package_cycle, unstable_dependency) may only change in place, never appear or disappear, and only in an input with R4 edge removals.
- Record keys removed under `$.evidence[]` are accepted only for unresolved_boundary and evidence_spread, whose evidence lists R1 and R5 filter.

## Result (`review-output/*.json`)
| input | mode | nodes | flag changes | edges base→head: changes | metadata changes (nodes) | candidate kinds that changed (base→head) | unexplained |
| --- | --- | --- | --- | --- | --- | --- | --- |
| self | file | 450→450 | none | 16791→16791: none | analysis (R7) 450, external_call_count (R1) 193 | evidence_spread 154→133, large_node 2→2 (R8 metric keys), unresolved_boundary 196→25, untested_hub 1→0 | 0 |
| self | symbol | 10596→10596 | -ambiguous_name (R6) 1210 | 67602→67602: none | analysis 10596; external_call_count/external_calls/unresolved_calls/unresolved_references 2537 (R1); unresolved_reference_total 81 (R3) | evidence_spread 1106→637, unresolved_boundary 2546→39 | 0 |
| nestjs | file | 42→42 | none | 407→407: none | analysis 42, external_call_count 20 | evidence_spread 33→25, unresolved_boundary 21→4, untested_hub 9→8 | 0 |
| nestjs | symbol | 268→268 | -ambiguous_name (R6) 82 | 669→669: none | analysis 268, R1 keys 64 | evidence_spread 137→94, unresolved_boundary 68→4 | 0 |
| android | file | 78→78 | none | 1620→1616: -READS (R4) 4 | analysis 78, external_call_count 40 | dependency_cycle 4 changed, package_cycle 4 changed, unstable_dependency 13 changed (R4), evidence_spread 47→46, unresolved_boundary 40→0, untested_hub 4→4 | 0 |
| android | symbol | 885→885 | -ambiguous_name (R6) 194 | 4157→3310: -CALLS 116, -INSTANTIATES 25, -READS 399, -WRITES 108, -TESTS 200 (R4); IMPORTS/IMPORTS_SYMBOL 21 each and TESTS 19 re-keyed by evidence line (R9/R4) | analysis 885, R1/R4 keys 167–195 | evidence_spread 294→218, unresolved_boundary 195→0 | 0 |
| futuramaapi | file | 188→188 | none | 1384→1384: none | analysis 188, external_call_count 101 | evidence_spread 91→78, unresolved_boundary 101→5, untested_hub 3→3 | 0 |
| futuramaapi | symbol | 1449→1449 | -ambiguous_name (R6) 559 | 3175→3175: none | analysis 1449, R1 keys 325, unresolved_reference_total 3 | evidence_spread 352→195, unresolved_boundary 325→5 | 0 |
| fastapi-realworld | file | 98→98 | none | 726→726: none | analysis 98, external_call_count 49 | evidence_spread 44→41, large_node 1→1 (R8 metric keys), unresolved_boundary 49→0, untested_hub 7→5 | 0 |
| fastapi-realworld | symbol | 601→601 | -ambiguous_name (R6) 124 | 1787→1787: none | analysis 601, R1 keys 144 | evidence_spread 191→98, unresolved_boundary 144→0 | 0 |

Observations:
- No node is added or removed, and no flag other than `ambiguous_name` changes. Python and TypeScript edges are identical, and structural metrics are unchanged everywhere except android, where they follow the R4 edge removals.
- The android file-mode READS removals (for example `OfflineFirstUserDataRepository.kt → TopicViewModel.kt`) came from the class reading its own member `setNewsResourceViewed` at the member's declaration, where that read was ambiguous with `TopicViewModel.setNewsResourceViewed`. The member's own CALLS edge, and so the file-level CALLS edge, remains.
- Sampled unresolved_boundary removals are builtins, globals, external imports or unknown receivers (for example `any`, `compile`, `Path`, typeorm `Column`, `forRoutes`). android `data/model/NewsResource.kt` imports `NewsResource` from `core.model.data`, a module absent from the fixture, so the import is outside the project by the R1 definition. The 39 remaining self-symbol candidates are 37 `dynamic_*` flag nodes and 2 boundary calls (`_is_alias`, `_m1_payload`).
- Sampled evidence_spread removals had `file_count` 2 in base made of the target's own file plus one external file (R5).
- untested_hub changes all coincide with a PageRank change of the target (R7).

Changes not explained by R1–R10: 0 in all 10 outputs.

## Non-test file share (file mode)
| input | unresolved_boundary | evidence_spread |
| --- | --- | --- |
| self | 72% → 11% | 77% → 75% |
| nestjs | 51% → 10% | 80% → 61% |
| android | 50% → 0% | 73% → 73% |
| futuramaapi | 52% → 3% | 59% → 51% |
| fastapi-realworld | 44% → 0% | 58% → 55% |

File-mode evidence_spread stays high: after R5 the rule is "used from at least 2 other files", which is close to fan_in ≥ 2 at file granularity. Symbol mode drops by 30–50%. This is a property of the approved R5 definition, not a defect.

## Schema and keys (Q1)
Schema names are unchanged: `bottlenecks.v8` (file) and `bottlenecks.v6` (symbol). `versions.analysis` is "5". The only added key paths are `edge_weights.large_node_token_threshold`, `large_node` metrics `token_count`/`token_threshold`, and node metadata `external_call_count`/`external_calls`/`unresolved_reference_total`. Removed key paths occur only inside R1-filtered metadata and R1/R5-filtered evidence records.

## Performance (Q4, file mode, 3-run median seconds, `perf.py`)
| input | base | HEAD | ratio |
| --- | --- | --- | --- |
| android-nowinandroid | 1.33 | 1.13 | 0.855 |
| typescript-nestjs-realworld | 0.38 | 0.37 | 0.976 |
| self | 16.07 | 12.55 | 0.781 |

All ratios ≤ 1.25.


# Round 4 (spec 3f70cc03aeae9c1a, V9 · Q1 · Q3 · Q4)

The round-3 sections above were produced with the loose round-3 `review_diff.py`; their counts are kept as the
round-3 record. The rules now in `review_diff.py` (spec RV1–RV12, `--stage a|b`) supersede them.

## Procedure (repeatable)
1. Worktrees: `git worktree add --detach <scratch>/wt_a cf0cf4446106f44026dc40d00ba09df977d61ecc`,
   `git worktree add --detach <scratch>/wt_b 3b768a9b5e9b79c519bfe667b12b8e980cfa636b`, and
   `ln -s <repo>/.fixtures <scratch>/wt_{a,b}/.fixtures`. Put `.venv/bin` first on `PATH` (tree-sitter).
2. Outputs, always with `SELF=<scratch>/wt_a` so the self input is identical everywhere:
   `review_run.sh <scratch>/wt_a <scratch>/review/a_base`, `review_run.sh <scratch>/wt_b <scratch>/review/a_head`,
   `review_run.sh <repo> <scratch>/review/b_head`.
3. Stage a (cf0cf44 → 3b768a9, rules for R1–R10):
   `review_diff.py <scratch>/review/a_base <scratch>/review/a_head <name> <mode> review-output/<name>-<mode>.json --stage a`.
   Stage b (3b768a9 → this run, rules for R11–R14):
   `review_diff.py <scratch>/review/a_head <scratch>/review/b_head <name> <mode> review-output-round4/<name>-<mode>.json --stage b`.
   File-mode runs read the symbol-mode pair from the same directories. Each output records `unexplained`,
   the attributed edge changes, the independent evidence_spread recomputation, and `nontest_share`.
4. Wall time: `perf.py <dir>` where `<dir>/basewt` is the 3b768a9 worktree.

## Result
All 20 outputs (5 inputs × 2 modes × 2 stages) have `unexplained` 0.

| input | mode | stage a edges (base→head): attributed | stage b edges: attributed | evidence_spread a | evidence_spread b |
| --- | --- | --- | --- | --- | --- |
| self | file | 16791→16791 | 16791→16791 | 154→133 | 133→108 |
| self | symbol | 67602→67602 | 67602→67602 | 1106→637 | 637→360 |
| nestjs | file | 407→407 | 407→407 | 33→25 | 25→16 |
| nestjs | symbol | 669→669 | 669→669 | 137→94 | 94→41 |
| android | file | 1620→1616: -READS 4 (R4) | 1616→1616 | 47→46 | 46→41 |
| android | symbol | 4157→3310: -CALLS 116, -INSTANTIATES 25, -READS 398, -TESTS 200, -WRITES 108 (R4); IMPORTS re-key 42 (R9); other re-key 20 (R4) | 3310→3208: -READS 62, -TYPE_USES 35, -WRITES 5, CONFIGURES retarget 14, constructor-field re-key 74 (R13) | 294→218 | 218→175 |
| futuramaapi | file | 1384→1384 | 1384→1384 | 91→78 | 78→59 |
| futuramaapi | symbol | 3175→3175 | 3175→3175 | 352→195 | 195→125 |
| fastapi-realworld | file | 726→726 | 726→726 | 44→41 | 41→32 |
| fastapi-realworld | symbol | 1787→1787 | 1787→1787 | 191→98 | 98→66 |

Observations:
- Stage b changes edges only in android, all from R13: constructor fields no longer scan the whole constructor. The
  14 CONFIGURES retargets move a Room column-name config key from the first constructor field of the entity to the
  field annotated with that name (for example `TopicFtsEntity.topicId` → `TopicFtsEntity.name` for `name`).
- No fixture contains a one-line body misparse (R12): node id sets are unchanged in every stage b output.
- The independent evidence_spread recomputation (pre-round-3, R5, R11 definitions) equals the actual candidates in
  all 20 outputs.

## Non-test file share, file mode (computed by `review_diff.py`)
| input | unresolved_boundary (round 3) | evidence_spread round 3 (R5) | evidence_spread round 4 (R11) |
| --- | --- | --- | --- |
| self | 72% → 11% | 77% → 75% | 75% → 72% |
| nestjs | 51% → 10% | 80% → 61% | 61% → 39% |
| android | 39% → 0% | 56% → 56% | 56% → 52% |
| futuramaapi | 54% → 3% | 54% → 46% | 46% → 35% |
| fastapi-realworld | 45% → 0% | 56% → 53% | 53% → 41% |

The script counts non-test files from file nodes, so the round-3 numbers differ slightly from the hand-computed
table above. In this repository most source files are used from two or more other directories, so R11 lowers the
share only from 75% to 72% here.

## Schema and keys (Q1)
Schema names are unchanged (`bottlenecks.v8` file, `bottlenecks.v6` symbol). `versions.analysis` is "6". The only
added key path in stage b is evidence_spread `$.metrics.directory_count`.

## Performance (Q3, file mode, 3-run median seconds, `perf.py`, base = 3b768a9)
| input | base | HEAD | ratio |
| --- | --- | --- | --- |
| android-nowinandroid | 1.35 | 1.52 | 1.133 |
| typescript-nestjs-realworld | 0.50 | 0.43 | 0.848 |
| self | 18.31 | 18.62 | 1.017 |

All ratios ≤ 1.25.
