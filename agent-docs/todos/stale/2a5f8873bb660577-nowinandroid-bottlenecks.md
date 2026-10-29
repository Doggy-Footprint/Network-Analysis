# Now in Android bottleneck report

## Goal

“렉은 확실하게 개선됐어. 여기서 병목이 어딘지는 어떻게 하면 볼 수 있어?”

## State

- Branch: `refact/report`; commit: `fbf10d3` (`Limit dashboard startup graph and defer collection rendering`).
- Depth-1 target clone: `/private/tmp/nowinandroid-depth1`, upstream commit `12f80da`.
- Existing untracked dashboard: `nowinandroid-analysis.html` (39 MB) and `nowinandroid-analysis_assets/`; it was generated successfully and excludes the clone and report from the commit.
- No bottleneck JSON or HTML was produced. No tracked files changed during this task.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| Generate bottleneck JSON and HTML with `--bottlenecks`, `--bottlenecks-html`, and `profiles/harness.fixed-baseline.v1.json` | Process interrupted while rebuilding the Android graph; exit 130, no bottleneck output files | verified: user requested handoff before completion |

## Next Step

Run the analyzer again against the existing clone. Use `/private/tmp/refact-report-test-venv/bin/python -m code_analyzer /private/tmp/nowinandroid-depth1 -f android -o /private/tmp/nowinandroid-bottleneck-architecture.html --bottlenecks nowinandroid-bottlenecks.json --bottlenecks-html nowinandroid-bottlenecks.html --harness-profile profiles/harness.fixed-baseline.v1.json`. Then verify output files and explain that the HTML candidate table shows static candidates while `Dependency network` contains metric top-10 rankings. The harness profile declares `unverified_baseline`; interpret probe-based results accordingly.

## Open Questions

- Whether the user wants the generated bottleneck report only, or also a short interpretation of the highest-ranked targets.

## Contract Snapshot

none
