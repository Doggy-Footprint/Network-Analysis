# Review evidence (spec e91abc221d7deb2a v4, V12 · V14 · Q1 · Q4)

## Procedure
- Base: `git worktree add --detach <scratch>/basewt cf0cf44`. HEAD: `02aad8f` working tree (code unchanged since).
- Inputs: the base worktree's own sources (`-l python`, so both sides read identical files), `typescript-nestjs-realworld` (`-l typescript`), `android-nowinandroid` (`-l kotlin`), `futuramaapi`, `fastapi-realworld` (`-l python`), each with `--granularity file|symbol --bottlenecks`, `PYTHONHASHSEED=0`.
- Counts: candidate kinds per output; for file mode, the share of non-test, non-vendored, non-generated `file:` nodes that are a candidate target.
- For each kind, up to 10 removed or added targets were opened and attributed to an R id.

## Candidate counts (base → HEAD)
| input | mode | candidate kinds | file share (non-test) |
| --- | --- | --- | --- |
| self | file | dependency_cycle 10→10, evidence_spread 154→133, isolated_node 2→2, large_node 2→2, package_cycle 4→4, unresolved_boundary 196→25, unstable_dependency 147→147, untested_hub 1→0 | unresolved_boundary 72%→11%; evidence_spread 77%→75% |
| self | symbol | evidence_spread 1106→637, unresolved_boundary 2546→39 | |
| nestjs | file | evidence_spread 33→25, unresolved_boundary 21→4, untested_hub 9→8, others equal | unresolved_boundary 51%→10%; evidence_spread 80%→61% |
| nestjs | symbol | evidence_spread 137→94, unresolved_boundary 68→4 | |
| android | file | evidence_spread 47→46, unresolved_boundary 40→0, untested_hub 4→4, others equal | unresolved_boundary 50%→0%; evidence_spread 73%→73% |
| android | symbol | evidence_spread 294→218, unresolved_boundary 195→0 | |
| futuramaapi | file | evidence_spread 91→78, unresolved_boundary 101→5, others equal | unresolved_boundary 52%→3%; evidence_spread 59%→51% |
| futuramaapi | symbol | evidence_spread 352→195, unresolved_boundary 325→5 | |
| fastapi-realworld | file | evidence_spread 44→41, unresolved_boundary 49→0, untested_hub 7→5, others equal | unresolved_boundary 44%→0%; evidence_spread 58%→55% |
| fastapi-realworld | symbol | evidence_spread 191→98, unresolved_boundary 144→0 | |

No kind gained candidates except untested_hub (R7), and large_node, cycle, package and stability kinds are unchanged.

## Attribution of sampled changes
- unresolved_boundary removed (R1): `analysis/architecture_rules.py` (134 references: `any`, `compile`, `field`, …), `analysis/edge_weights.py` (`Path`, `isinstance`, `read_bytes`), nestjs `article.entity.ts` (`Column`, `ManyToOne` from typeorm), `article.module.ts` (`forRoutes` on an external receiver), android `SyncUtilities.kt` (`success`, `versionReader`), android `data/model/NewsResource.kt` (`NewsResource` imported from `core.model.data`; that module is absent from the fixture, so the import is outside the project by the R1 definition). Every sampled reference is a builtin, global, external import or unknown receiver.
- unresolved_boundary remaining (self symbol, 39): 37 come from `dynamic_*` flags (count 0); the 2 call boundaries are `_is_alias` and `_m1_payload`, calls on project-bound receivers whose name the target does not define (R1 ⓐ/ⓒ).
- evidence_spread removed (R5): every sampled removed target (self `archive/agent_view/derived_query.py`, `exact_query.py`, nestjs `app.controller.ts`, `app.module.ts`, android `NewsResourceDaoTest.kt`) had `file_count` 2 in base made of its own file plus one external file.
- untested_hub changed (R7): self `analysis/candidate_projection.py` (rank 7 → outside top 10), nestjs `create-comment.ts`, `follows.entity.ts` out and `user.module.ts`, `user.service.ts` in, android `TopicNavKey.kt` out, `RecentSearchQuery.kt` in; all follow the PageRank order change.
- Kotlin edges (R4): the O11 regeneration shows android/kotlin edges 4510→3747 and 4389→3626 from class scans no longer repeating member bodies (`manifest-regeneration.md`).

Changes not explained by R1–R10: 0.

## Observation (not a contract violation)
File-mode `evidence_spread` still covers 51–75% of files. After R5 the rule is "used from ≥2 other files", which most shared files satisfy; it is close to fan_in ≥ 2 in file mode. Symbol mode drops by 30–50%.

## Schema and keys (Q1)
Schema names are unchanged (`bottlenecks.v8` file, `bottlenecks.v6` symbol). Added keys only: `edge_weights.large_node_token_threshold`, `large_node` metrics `token_count`/`token_threshold`, node metadata `external_call_count`/`external_calls`/`unresolved_reference_total`. `versions.analysis` is "5". The existing byte-equality suites pass against the regenerated manifests.

## Performance (Q4, file mode, 3-run median seconds)
| input | base | HEAD | ratio |
| --- | --- | --- | --- |
| android-nowinandroid | 1.33 | 1.13 | 0.855 |
| typescript-nestjs-realworld | 0.38 | 0.37 | 0.976 |
| self | 16.07 | 12.55 | 0.781 |

All ratios ≤ 1.25.
