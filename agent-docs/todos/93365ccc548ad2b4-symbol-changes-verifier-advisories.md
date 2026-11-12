# Symbol changes and NestJS visibility: verifier advisories

## Goal
Cover partitions that spec 338f748639b68776 left without evidence (reported as non-blocking by its verifiers) and one report-generator gap found during it.

## Next Step
- NestJS analyzer: a `@Module(x)` whose argument is not an object literal is specified to record `unsupported_fields = ["imports", "providers"]`; no test pins that value. Proposed mutation: record `[]` for that case in `framework_analyzers/nestjs/analyzer.py` `_modules`.
- C04 CLI trailing-comma case (`tests/test_symbol_changes.py`): check whether the TypeScript analyzer keeps the trailing comma in `signature`; if it does not, the case passes without exercising the delta comparison.
- V04 D5c covers quote style in one direction only; add the reverse.
- Signature comparison mutations not run: closer set without `>` or `]`, single-pass separator removal, `;` removed everywhere, quote replacement only at token start (`_squeeze` in `bottlenecks/delta.py`). Running `tests/symbol_changes_evidence/fuzz/fuzz_symbols.py` against M16–M18 was also not done.
- `report/bottlenecks/generate.py` `KIND_LABELS` lacks `dangling_doc_reference` and `duplicate_code` (also at 075881f); the generator rejects a v9 JSON containing either kind with `$.candidates[i].kind: is unsupported`. Re-check: generate a report from a bottleneck JSON with a dangling doc reference.
- TypeScript method signatures carry no access modifier (`name(params)`), so TS `private`/`protected` members are reported as public in `dependency_network.symbols`.

## Related
- agent-docs/spec-logs/338f748639b68776-breaking-changes-and-unused-symbols.md (execution ledger VR2, VR3; assumption A06)
- tests/test_symbol_changes.py, tests/test_unprovided_injection.py, tests/symbol_changes_evidence/mutations/run_mutations.py
