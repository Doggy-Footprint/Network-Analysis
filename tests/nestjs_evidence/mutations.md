# Confirming mutations — spec v2

Each seed ran the exact full test command `.venv/bin/python -m pytest -q` with a 180-second timeout. Main used `.harness/bin/seed.py backup` before each injection and `restore` afterward, checked restored bytes against the pre-injection bytes, and verified the intended assertion rather than counting unrelated failures. The three defect classes were fixed by the approved plan: name guessing violates direct reference resolution; prefix omission violates confirmed full paths; duplicate emission violates explicit TypeScript ownership.

| Seed | Violating behavior | Intended assertion | Observed result | Restore |
| --- | --- | --- | --- | --- |
| M1 | Unresolved imported names incorrectly linked to same-name classes elsewhere | `TestReferences.test_O2_mixed_dynamic_barrel_paths_external_and_shadowed_refs_do_not_guess` | 1 failed, 882 passed, 192 subtests passed in 24.19s; intended assertion detected | byte-identical; seed backup removed |
| M2 | Global prefix omitted from confirmed endpoint full paths | `TestPinnedFixture.test_O10_source_authored_counts_edges_and_routes` | 3 failed, 881 passed, 191 subtests passed in 24.06s; intended assertion detected | byte-identical; seed backup removed |
| M3 | NestJS emits the language graph alongside explicit TypeScript | `TestNestJSCli.test_O6_ownership_in_both_orders_and_standalone` | 7 failed, 879 passed, 189 subtests passed in 24.04s; intended assertion detected | byte-identical; seed backup removed |

M1 observed extra Root→Lost/Alias/External pairs. M2 observed missing `/api` on the independent fixture route table. M3 observed exit 1 with duplicate TypeScript/configuration node IDs in both mixed orders. None was a setup failure. Full sanitized assertion observations and restored SHA256 values are in `mutation-results.json`. No injected diff is exposed to test roles.

Restored full command: 883 passed, 192 subtests passed in 24.06s. Further assertions from the same V4/V6 correction batch are independently reviewed before closure; their intended mutation observations are unchanged.

## Batch 4 confirming mutations (spec v3, after verifier-3)

Seeds via `.harness/bin/seed.py backup/restore`, exact full command, 180-second timeout. All restored byte-identically (sha256 in `mutation-results.json`); seed status none.

| Seed | Violating behavior | Intended assertion | Observed result |
| --- | --- | --- | --- |
| M4 (V7) | endpoint relative_path nulled when full_path is unconfirmed | `TestBootstrap.assert_relative_retained` rows | 11 failed, 882 passed, 191 subtests passed in 26.89s; intended subtests detected (also O4 and O7 relative-path checks) |
| M5 (V8) | explicit TypeScript + --no-language-graph drops TypeScript HTTP calls | `test_O6_mixed_fastapi_and_flags[explicit_language]` | 1 failed, 884 passed, 199 subtests passed in 25.80s |
| M6 (V9) | ambiguous CALLS_ROUTE emitted from the wrong source | `test_O7_duplicate_server_candidates_do_not_pick_arbitrarily` | 1 failed, 883 passed, 200 subtests passed in 25.53s |
| M7 (V10) | union constructor type resolved to first member | `test_O3_each_unsupported_constructor_form_alone_creates_no_dependency[union]` | 1 failed, 884 passed, 199 subtests passed in 25.43s |
| M3 rerun | NestJS emits language graph alongside explicit TypeScript | `test_O6_ownership_in_both_orders_and_standalone` | 8 failed, 880 passed, 194 subtests passed in 25.31s |

Pre-change M7 note: the previous O3 assertion compared a set of target IDs already covered by two plain parameters, so M7 would have passed it; this is why V10 was a real gap. Restored full command: 884 passed, 200 subtests passed in 24.86s.
