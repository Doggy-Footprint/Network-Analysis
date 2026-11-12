# Rename mapping and Kotlin comment filter: verifier advisories

## Goal
Cover two partitions that spec 73bd5aa508fa3e88 did not declare, reported as non-blocking by its third verifier.

## Next Step
- Rename pairs whose extension changes (`x.py -> x.txt`, `x.py -> x.pyi`, `.py` on one side only): add a case showing `py:<module>` ids are not mapped, so a removed module stays visible. Proposed mutation: drop the both-sides-`.py` condition in the module mapping of `bottlenecks/delta.py`.
- Python id mapping at locations other than evidence `node_id` (candidate `target`, cycle members): add a case per location.
- Kotlin comment-span filter boundaries in `language_analyzers/kotlin/analyzer.py`: names directly after `*/`, directly before `//` or `/*`, `//` ending at the line end, unterminated nested block comments. Proposed mutations: inclusive span end, exclusive span start, `//` masked to end of file.

## Related
- agent-docs/spec-logs/73bd5aa508fa3e88-rename-and-comment-false-positives.md (execution ledger attempt 8)
- tests/test_rename_delta.py, tests/test_kotlin_comment_scan.py
