# Validate bottlenecks.v3 and edge weights on a real repository

## Goal

“아직 안 한것들 handoff 들로 작성해줘” — 재구조화(커밋 `2a340fb`) 이후 남은 작업.

## Purpose

Run bottlenecks.v3 with default edge weights on a pinned real repository and check whether rankings and candidates are usable.

## State

- Branch: `polish`; base commit: `2a340fb`.
- Changed files for this handoff: this file and `agent-docs/handoff/index.md`.
- `fixtures/registry.py` pins `android-nowinandroid` (and other fixtures) for network clone.
- `bottlenecks.v3` and `profiles/edge_weights.v1.yaml` have only been exercised on small in-repo graphs; no real-repository output exists since the refocus.
- Stale handoff `2a5f8873bb660577-nowinandroid-bottlenecks.md` produced a v2 report before the refocus.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| Run CLI on `fixture_root('android-nowinandroid')` directly | `snapshot.file_count: 0`, `node_count: 0`, `ignore_source: git-tracked` | `_prune_subpaths` renames `core/data` → `core_data` etc., so no working-tree file matches `git ls-files`; snapshot scan admits nothing (verified) |

## Observations (2026-09-30, commit `698402c`)

Workaround: copied the three pruned subpaths into a directory without `.git` (`ignore_source: static_fallback`). 90 source files, 950 nodes, 2867 edges. Runs: default `edge_weights.v1.yaml` vs. all 0.3 → 1.0.

- Top-10 overlap (default vs. 1.0): pagerank 9/10, weighted_fan_in 7/10, authority 7/10, hub **0/10**.
- Hub (default): all top-10 are `config:core_database/schemas/...NiaDatabase/<n>.json:name` (Room schema JSON). Hub (1.0): test classes and `OfflineFirstNewsRepository`. Default weighting lets schema-JSON config nodes dominate hub ranking — noise.
- Authority / weighted_fan_in (default): test-only symbols (`TestNewsResourceDao.asPopulatedNewsResource`, `PopulatedNewsResourceKtTest...`) in top-5; with 1.0 they drop out.
- Candidates identical for both weightings: `evidence_spread` 218, `unresolved_boundary` 195, `large_node` 0 (no file ≥ 2000 lines in the subset). `evidence_spread` fires on 2-file spans such as `NetworkMonitor` ← `DataModule` — likely noisy at this count.
- Android summary counts (Composables, ViewModels, DI Bindings, Room Entities, Retrofit APIs) all print 0 despite `TopicViewModel`, `TopicDao`, `NiaDatabase` being present (not investigated).

## Decisions (2026-09-30, user approved recommendations)

1. Fixture mismatch: fixed in `fixtures/registry.py` — `subpaths` is now a tuple of upstream paths pruned in place (no rename). `content_sha256` unchanged because `compute_content_sha256` hashes contents only in sorted path order. Direct fixture run: `ignore_source: git-tracked`, 90 files, 950 nodes, 2867 edges; Android summary counts now non-zero (Composables 7, ViewModels 1, DI Bindings 22, Room Entities 6), so the zero counts had the same cause.
2. Noise: rankings split by source category (`rankings_by_category`) instead of exclusion or down-weighting. JSON part accepted; HTML metric-panel evidence gap recorded as issue `d784aad47a3ab51b-category-rankings-metric-panel-substring.md`.
3. Defaults (0.3, 2000 lines): kept unchanged pending more evidence.
4. Next validation: add one FastAPI fixture and judge with a fixed checklist — production share of top-10, top-10 overlap across weightings, candidate counts per kind, usable ratio of 10 sampled candidates.

## Next Step

Run decision 4 on Now in Android and one FastAPI fixture; re-run `code_analyzer.cli` with `-f android --bottlenecks --bottlenecks-html` using default weights, then with all weights 1.0. Compare top-10 rankings (pagerank, hub/authority, weighted_fan_in) and candidate counts per kind. Record which differences come from non-certain edges and whether `large_node` (2000 lines) and `evidence_spread` produce useful or noisy candidates.

## Open Questions

- Which repositories besides Now in Android (e.g. a FastAPI fixture) should be included?
- What observation counts as "usable" (manual review of top-k, or a fixed checklist)?
- Whether to keep the 0.3 default and 2000-line threshold after review (0 `large_node` candidates observed).
- Whether config/schema JSON nodes and test sources should be excluded or down-weighted in hub/authority rankings.
- Whether the pruned-fixture snapshot mismatch is fixed in `fixtures/registry.py` (keep original paths) or in the snapshot scan (fall back when git-tracked set is empty).
- Why Android framework summary counts are all 0.

## Spec

No workflow spec exists for this handoff. Version, status, and run ID: not applicable.

## Execution Ledger

- Finding: no real-repository run of v3; disposition: run before choosing which network expansion to implement first.
- Evidence and mutation outcomes: two CLI runs on a `.git`-less copy of the fixture (see Observations); no implementation mutation.
- Correction count: 0; verifier count: 0.
