You are evaluating a static-analysis tool ("the analyzer") that builds a repository's dependency network and reports structural bottleneck candidates. Your job: use ONLY the analyzer's report as your guide to choose refactoring points in an open-source repository. You may read the repository's code to confirm and scope each point, but every point must originate from a specific report entry (candidate, ranking row, cycle, or package metric). Do not edit any file.

Repository: {repo} ({cell}), pristine snapshot at {snap} (read-only; same content as the git clone at {clone}).
Analyzer outputs: {out}/bottlenecks.json (candidates, dependency_network.rankings_by_category.production, package_metrics, candidate_groups) and {out}/report.json (file graph). The HTML report {out}/report.html is the same data.
Test gate: {out}/../test-baseline.json describes the ONLY test command that will verify behaviour. A point is admissible only if the code it changes is exercised by that gate's scope (e.g. a module/package whose tests are in the gate). Read subset_note.

Choose exactly 3 behaviour-preserving refactoring points. Constraints:
- Each point must be implementable independently from the same base commit, in roughly ≤ 400 changed lines, without changing public behaviour, HTTP/GraphQL APIs, DB schema/migrations, or test assertions (tests may only get import-path updates).
- Prefer points where the structural problem is real when you read the code; reject report entries that are artefacts (generated code, config files, framework boilerplate) and record them as rejected with the reason — this is evaluation evidence about the report.
- For each point declare, BEFORE any implementation, the independent metric(s) expected to improve. Available independent metrics (computed by tools unrelated to the analyzer) on the touched files:
  lizard: ccn_max, high_ccn (functions with CCN>15), long_functions (NLOC>60), largest_file_nloc;
  independent import graph ({imports_tool}): max_file_fan_in, max_file_fan_out, group_external_dependents, group_external_dependencies, files_in_cycles, largest_cycle_touching; global cycle_count / files_in_cycles.
  Pick only metrics your change should actually move; say the expected direction and rough size.

Write {out}/../points.json:
{{"repo": "{repo}", "points": [{{"id": "p1", "title": "...", "report_evidence": [{{"source": "candidate|ranking|cycle|package_metric", "ref": "candidate id or ranking key + rank", "detail": "metric values quoted from the report"}}], "files": ["paths"], "problem": "what is structurally wrong, confirmed in code (cite file:line)", "plan": "concrete steps", "in_gate_scope": "why the gate covers it", "predicted": [{{"metric": "lizard_touched.high_ccn", "direction": "decrease", "expected": "3 -> 0"}}], "risk": "..."}}], "rejected_report_entries": [{{"ref": "...", "reason": "..."}}], "report_observations": ["anything the report got wrong or missed that you noticed, with evidence"]}}
Reply with a short summary (≤ 8 lines).
