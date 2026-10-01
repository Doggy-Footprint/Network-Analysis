# Confirming mutations — spec v2

Each seed ran the exact full test command `.venv/bin/python -m pytest -q` with a 180-second timeout. Main used `.harness/bin/seed.py backup` before each injection and `restore` afterward, checked restored bytes against the pre-injection bytes, and verified the intended assertion rather than counting unrelated failures. The three defect classes were fixed by the approved plan: name guessing violates direct reference resolution; prefix omission violates confirmed full paths; duplicate emission violates explicit TypeScript ownership.

| Seed | Violating behavior | Intended assertion | Observed result | Restore |
| --- | --- | --- | --- | --- |
| M1 | Unresolved imported names incorrectly linked to same-name classes elsewhere | `TestReferences.test_O2_mixed_dynamic_barrel_paths_external_and_shadowed_refs_do_not_guess` | 1 failed, 882 passed, 192 subtests passed in 24.19s; intended assertion detected | byte-identical; seed backup removed |
| M2 | Global prefix omitted from confirmed endpoint full paths | `TestPinnedFixture.test_O10_source_authored_counts_edges_and_routes` | 3 failed, 881 passed, 191 subtests passed in 24.06s; intended assertion detected | byte-identical; seed backup removed |
| M3 | NestJS emits the language graph alongside explicit TypeScript | `TestNestJSCli.test_O6_ownership_in_both_orders_and_standalone` | 7 failed, 879 passed, 189 subtests passed in 24.04s; intended assertion detected | byte-identical; seed backup removed |

M1 observed extra Root→Lost/Alias/External pairs. M2 observed missing `/api` on the independent fixture route table. M3 observed exit 1 with duplicate TypeScript/configuration node IDs in both mixed orders. None was a setup failure. Full sanitized assertion observations and restored SHA256 values are in `mutation-results.json`. No injected diff is exposed to test roles.

Restored full command: 883 passed, 192 subtests passed in 24.06s. Further assertions from the same V4/V6 correction batch are independently reviewed before closure; their intended mutation observations are unchanged.
