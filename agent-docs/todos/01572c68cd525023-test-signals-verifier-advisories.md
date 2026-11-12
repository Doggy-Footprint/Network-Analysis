# Test change signals: verifier advisories

## Goal
Cover partitions and measurement choices that spec fda1b3f71e2390f3 left without evidence (reported as non-blocking by its second verifier).

## Next Step
- Kotlin `object_declaration` has two code paths in `bottlenecks/test_signals.py`: case discovery and the mock/skip scope walk. Mutations M14 and M16 cover the skip-inheritance line and case discovery only; a mutation that drops `object_declaration` from the scope walk alone was not run.
- `tests/test_signals_evidence/fuzz/fuzz_test_changes.py` never generates a pair where only `test_reach` changes on an existing symbol with equal branches (unit test V08 D5 covers it).
- R2 time for CTFd: a sequential 3-run pass gave 1.166 (base runs 3.80–4.69 s); an alternating 5-run pass gave 1.127 and is the one recorded in `tests/test_signals_evidence/r1_comparison.md`. Re-check with alternating runs before treating a single pass above 1.15 as a regression.
- Kotlin `assertThat(x, matcher)` (Hamcrest form) and Python `self.assertRaises(E, f)` as a plain call are outside table A and untested.

## Related
- agent-docs/spec-logs/fda1b3f71e2390f3-test-change-signals.md (execution ledger 2, 3; verifier round 2 advisories A-5–A-7)
- tests/test_signals_evidence/mutations/run_mutations.py, tests/test_signals_evidence/fuzz/fuzz_test_changes.py
