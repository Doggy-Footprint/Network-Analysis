Goldens for spec ee17484a52af182c (report size for LLM). They are base-commit (5ddd4261850450578d610b2d3d309a5d0b7729cd) outputs, never output of the v9 code.

Command, cwd = a `git worktree` of the base commit, `P` = `tests/report_size_evidence/project`:
`.venv/bin/python -m code_analyzer $P -l python -o out/report.html --json --bottlenecks out/bottlenecks.json` (file granularity, bottlenecks.v8, report.json schema 6)
`... --granularity symbol ...` (symbol granularity, bottlenecks.v6, report.json schema 5)

Files: `v8_bottlenecks.json` (as written), `v8_details.json` (`details` of the v8 report.json), `v8_report_without_details.json` (v8 report.json minus `details`), `v8_symbol_report.json` (symbol report.json). The last three are re-serialised compact with sorted keys.
`project/` holds the fixture: a core<->util file and package cycle, an unstable core->util dependency, two evidence_spread targets, and untested_hub candidates (unchanged kind).
The goldens must be produced with `project/` git-tracked: analysis coverage and the snapshot record the file collection mode (`git-tracked` vs filesystem), so regenerating them from an untracked copy breaks the V02 equality checks.
