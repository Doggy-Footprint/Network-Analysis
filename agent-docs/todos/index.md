File: c618d54a63603a71-adr-rejection-to-try-n-fail.md
Summary: Move ADR and rejection records to try-n-fail as the user chooses after the 0.29.0 update.
Related Files: agent-docs/adr/07e12b7114048d41-json-baseline-ratchet.md, agent-docs/adr/31d2dee6912427d5-consolidate-overlapping-metrics.md, agent-docs/adr/58424b9754efe9a2-package-grouping-schemes.md, agent-docs/adr/b8a976686050faf6-evidence-spread-by-directory.md
Related Symbols: none
---
File: 5e2b9c41d7a08f36-rename-and-comment-verifier-advisories.md
Summary: Test extension-changing renames, Python id mapping outside evidence node_id, and Kotlin comment-span boundaries.
Related Files: bottlenecks/delta.py, language_analyzers/kotlin/analyzer.py, tests/test_rename_delta.py, tests/test_kotlin_comment_scan.py
Related Symbols: compute_delta, KotlinAnalyzer
---
File: 93365ccc548ad2b4-symbol-changes-verifier-advisories.md
Summary: Pin NestJS non-object module metadata, check the C04 CLI case, add signature-comparison mutations, add missing report kind labels.
Related Files: framework_analyzers/nestjs/analyzer.py, bottlenecks/delta.py, report/bottlenecks/generate.py, tests/test_symbol_changes.py, tests/test_unprovided_injection.py
Related Symbols: compute_delta, unprovided_candidates, KIND_LABELS
---
File: 01572c68cd525023-test-signals-verifier-advisories.md
Summary: Separate the Kotlin object scope-walk mutation, add a reach-only fuzz case, re-check CTFd time with alternating runs, cover out-of-table assertion forms.
Related Files: bottlenecks/test_signals.py, tests/test_signals_evidence/fuzz/fuzz_test_changes.py, tests/test_signals_evidence/r1_comparison.md
Related Symbols: test_case_table, compute_delta
---
File: 6cddcdd2e2ebc085-uncaught-agent-type-groups.md
Summary: Five groups of weight-3 types the analyzer still misses (dependency declarations, security, data layer, change structure, documentation) with per-group eval counts.
Related Files: scripts/eval/inject/harness.py, scripts/eval/defects/catalog.json, tests/test_signals_evidence/r1_comparison.md
Related Symbols: compute_delta
