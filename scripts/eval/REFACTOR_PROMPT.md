You are applying ONE behaviour-preserving refactoring to an open-source repository as part of an evaluation of a static-analysis tool. The refactoring point was chosen earlier from the tool's report; implement it as planned.

Repository clone: {clone} (git; base commit {base}). Point: "{pid}" in {points} — read that entry (title, files, problem, plan, predicted metrics).

Steps:
1. `git -C {clone} switch -c eval/{pid} {base}` (the clone may currently be on another eval/* branch — always start from {base}). Never modify or delete other branches. Do not touch untracked build/env files (node_modules, local.properties, .venv...).
2. Implement the plan. Keep it behaviour-preserving: no public API / route / schema / migration changes, no test assertion changes (tests may only get import-path updates, or be moved alongside moved code). Match the repository's own style and conventions. You may deviate from the plan if the code shows the plan is wrong, but record why.
3. Run the gate: `/Users/hwansu/toy-projects/network-analysis/eval/.venv/bin/python /Users/hwansu/toy-projects/network-analysis/scripts/eval/gate.py {repo} --label {pid}-agent` from any directory. It must print "ok": true (same passed count as baseline, 0 failed/errors, typecheck where applicable). {gate_note} If it fails, fix and re-run; give up after 3 failing gate runs and revert to {base} (leave the branch pointing at {base}).
4. Commit on eval/{pid} with message "eval {pid}: <title>". One commit.
5. Write {out}/{pid}/refactor.json: {{"pid", "status": "done|abandoned", "commit", "deviations_from_plan", "gate_runs": [{{"label", "ok", "passed", "failed"}}], "notes"}}.
Reply in ≤ 6 lines. Do not run the measurement scripts yourself; the evaluator does that.
