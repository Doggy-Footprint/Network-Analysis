# Uncaught agent-reported types after the test signals work

## Goal
Raise analyzer recall on agent-reported (weight 3) types that the analyzer still matches in at most one valid injection, measured by the injection eval (608 tasks, `scripts/eval/inject/harness.py`).

## Next Step
Pick one group, run it through `/workflow-approach` on a new branch from `eval`, and re-measure with `tests/rename_comment_evidence/r1_reanalyze.py <repo> --match --workers 4`.

Counts below are summed over the four repos after commit fea60c7 (valid / analyzer located / analyzer matched; "tools" = valid tasks matched by any comparison tool):

| group | types (valid) | located / matched | tools | observation |
| --- | --- | --- | --- | --- |
| dependency declarations | P05 hallucinated package (5), P37 known-vulnerable version (8), P38 dependency declaration smells (8), P52 license issues (8) | 11 / 0 | 1 | Analyzer already emits `DECLARES_DEPENDENCY`; manifest vs import comparison is static. P37 needs advisory data, and the source for it (offline snapshot or other) is undecided. |
| security and authorization | P36 missing authorization (5), P39 hard-coded paths/URLs (8), P33 path traversal (7), P34 injection (7) | 12 / 0 | 4 | Framework analyzers know routes; a route lacking an auth decorator that sibling routes carry is a candidate signal for P36. |
| data layer and performance | P25 ORM misuse (5), P40 N+1 / excessive I/O (6), P41 concurrency (8) | 7 / 0 | 0 | ORM-to-migration edges exist; detection rules are not designed. |
| change structure | P45 tangled change (6), P18 avoidance of refactoring (5) | 8 / 0 | 1 | Needs a judgement over the whole delta; P45 was deferred in the earlier proposal. |
| documentation | P43 docs needing correction (7), P29 excessive comments (8) | 1 / 0 | 0 | Comment-text signals were the cause of the comment-only control false positives fixed in spec 73bd5aa508fa3e88. |

Re-check the counts: aggregate `valid`, `analyzer.located` and `match.verdict` from `~/toy-projects/network-analysis-eval/inject/<repo>/runs/*/result.json` per type (type = task id prefix).

## Related
- tests/test_signals_evidence/r1_comparison.md
- scripts/eval/defects/catalog.json
- agent-docs/progress-logs/b6b52b71cce3df29-agent-problem-injection-eval.md
