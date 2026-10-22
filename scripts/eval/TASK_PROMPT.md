You are refactoring an open-source repository to remove structural bottlenecks. Work end to end on your own: find the bottlenecks, choose refactoring points, implement them, verify them, and commit them. Nobody will answer questions.

Repository: {repo} ({cell}), a git checkout at `{clone}` on branch `base` (commit {base}). It is the only checkout; there is no remote and no network access. Do not try to look up the upstream project, its history, issues, or other versions.
Your working files: `{run}/points.json` (write once, see step 2) and `{run}/result.json` (step 4). Do not create files anywhere else outside the checkout.
{report_section}
## Behaviour gate

`{run}/gate` runs the repository's test suite on whatever is checked out in `{clone}` and is the only way the suite can be run here: it is the only command with the network and caches the tests need. Run it exactly as `{run}/gate` (no arguments, any working directory) with a Bash timeout of 3600000 ms — it may first wait for a shared test slot. It prints the log tail and exits non-zero on failure. On the untouched base it passes with {expected} tests passed and 0 failed{extra_note}. A point passes the gate only with the same passed count, 0 failed/errors{extra_pass}.
Other tool commands (e.g. single test files, type checkers) may fail inside the sandbox; that is expected — use the gate.

## Steps

1. Run the gate once on `base` before changing anything. If it does not pass, stop: write `{run}/result.json` as `{{"status": "gate_unusable", "notes": "..."}}` and finish.
2. Find the repository's structural bottlenecks (dependency hubs, cycles, overly coupled or oversized modules, ...) and choose exactly 3 behaviour-preserving refactoring points, each implementable independently from `base` in roughly 400 changed lines or fewer. Then, BEFORE implementing anything, write `{run}/points.json` with the Write tool. It can be written only once.
   ```json
   {{"repo": "{repo}", "points": [{{"id": "p1", "title": "...", "evidence": [{evidence_shape}], "files": ["paths"], "problem": "what is structurally wrong, confirmed in code (file:line)", "plan": "concrete steps", "predicted": [{{"metric": "<one of the metric keys below>", "direction": "decrease|increase", "expected": "rough before -> after"}}], "risk": "..."}}]{rejected_shape}}}
   ```
   `predicted` must use these exact metric keys. They are computed after you finish by independent tools on the files your point changes ("touched" = files that differ between `base` and the point's branch); you cannot run these tools. Only list metrics your change should actually move.
   - `lizard_touched.ccn_max`, `lizard_touched.high_ccn` (functions with cyclomatic complexity > 15), `lizard_touched.long_functions` (functions > 60 NLOC), `lizard_touched.largest_file_nloc`
   - `imports_touched.max_file_fan_in`, `imports_touched.max_file_fan_out` — the maximum over all touched files; to target one file write `imports_touched.max_file_fan_out (path/to/file.ext)`
   - `imports_touched.group_external_dependents`, `imports_touched.group_external_dependencies` (files outside the touched set that import into / are imported from it), `imports_touched.files_in_cycles`, `imports_touched.largest_cycle_touching`
   - `imports_global.cycle_count`, `imports_global.files_in_cycles`, `imports_global.largest_cycle`
   The import graph is built by {imports_tool}.
3. For each point in order: `git switch -c eval/pN base`, implement the plan, run the gate, and on success commit once on `eval/pN` with the message `eval pN: <title>`. Always start each point from `base`, never from another point's branch. Rules:
   - Behaviour-preserving only: no public API, route, CLI, schema, or migration changes; do not change test assertions (tests may only get import-path updates or move together with moved code).
   - Match the repository's own style. Do not touch untracked environment files (node_modules, local.properties, virtualenvs, build output).
   - If the gate fails, fix and rerun. After 3 failing gate runs for a point, abandon it: leave `eval/pN` pointing at `base` (`git switch eval/pN && git reset --hard base`) and continue with the next point.
   - You may deviate from the plan when the code shows it is wrong; record why.
4. Write `{run}/result.json`: `{{"points": [{{"id": "p1", "status": "done|abandoned", "commit": "<sha or null>", "gate_runs": [{{"ok": true, "passed": 0, "failed": 0}}], "deviations_from_plan": "...", "notes": "..."}}]}}`, then finish with a summary of at most 8 lines.
