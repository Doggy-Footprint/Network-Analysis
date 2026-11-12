# android-nowinandroid expected values after the Kotlin comment mask (spec 73bd5aa508fa3e88 F09)

`tests/build_modules_evidence/base_android-nowinandroid.json` and the android `bottleneck_bytes` in `tests/delta_evidence/base_manifest.json` pinned outputs whose Kotlin edges included names found only inside comments.

Equivalence check (`mask_check.py`, result `kotlin_edge_equivalence.json`): `KotlinAnalyzer` edges (from, to, relation, resolution, evidence start line) of the new tree on the original fixture equal those of base commit 1bd6ebe on a copy whose comments are blanked byte-for-byte (`mask_fixture.py`, tree-sitter `line_comment`/`multiline_comment`, newlines kept).

Golden regeneration: `golden_gen.py` reproduces the previous golden byte-identically from a worktree at its `base_commit` a8a3012 (Kotlin analyzer identical to 1bd6ebe). The new golden is the same procedure with only `language_analyzers/kotlin/analyzer.py` replaced by the spec's version; written with `separators=(',', ':')`, `sort_keys=True`, `base_commit` kept. Differences: file edge_count 537 -> 517, symbol 3387 -> 3327, `-f android` symbol 3510 -> 3450, 21 architecture file edges removed and none added, token_cost unchanged, file candidates: two resolved dependency cycles replaced by one and one new untested_hub (pagerank ranking shift).

Size reference: `q04_size.py` (Q04 canonical form, snapshot git keys removed) gives 4994578 bytes at 1bd6ebe and 4903903 with the mask; the android `bottleneck_bytes` (f5ab529, older Kotlin analyzer, not regenerable with the patch) is lowered by the difference, 4969819 - 90675 = 4879144. Its `bottleneck_sha256` is unused for android (the byte-equality test takes the build-only branch) and is left unchanged.
