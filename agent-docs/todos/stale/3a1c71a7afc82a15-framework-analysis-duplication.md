# Framework builder graph analysis duplication

## Goal

“handoff로 넘겨주고” — fastapi·android 경로에서 GraphAnalyzer가 중복 실행되는 문제.

## State

- Branch: `polish`; base commit: `ecb82f8`.
- Changed files for this handoff: this file and `agent-docs/handoff/index.md`.
- `ArchitectureGraphBuilder.build_graph` (`framework_analyzers/fastapi/graph.py`) and `AndroidArchitectureGraphBuilder.build_graph` (`framework_analyzers/android/graph.py`) call `GraphAnalyzer()` without edge weights and store `arch.stats["analysis"]`.
- `code_analyzer/cli.py` recomputes `arch.stats["analysis"]` with `GraphAnalyzer(analysis_config)` after both builders so `--edge-weights` applies; the builder result is discarded.
- With `--bottlenecks`, `analyze_bottlenecks` runs a third analysis. Python skips the CLI stats analysis when `--bottlenecks` is given; typescript and kotlin run CLI and bottlenecks analyses.
- Results are correct; only run time is affected (betweenness is exact up to 500 nodes, sampled beyond).
- The recompute was chosen because `framework_analyzers/android/` was outside spec `agent-docs/spec-logs/8fd668e309160b58-dependency-bottleneck-refocus.md` implementation paths.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| None recorded | — | — |

## Next Step

Choose one approach, then remove the CLI recompute:
1. Add an analysis-config parameter to both builders and pass the CLI's `analysis_config` (recommended).
2. Remove analysis from the builders and run it only in the CLI; check builder callers outside the CLI first.
Optionally let `analyze_bottlenecks` reuse a precomputed analysis; this changes its input validation boundary. Keep `tests/test_cli_bottlenecks_v3.py::test_V7_F14_edge_weights_reach_the_architecture_analysis_export` passing for all five paths.

## Open Questions

- Which approach (1, 2, and whether to include bottlenecks reuse)?

## Spec

No workflow spec exists for this handoff. Version, status, and run ID: not applicable.

## Execution Ledger

- Finding: duplication identified during spec 8fd668e309160b58 implementation; disposition: deferred by user.
- Evidence and mutation outcomes: removing the android CLI recompute is detected by the architecture-analysis export test (mutation M4 in that spec).
- Correction count: 0; verifier count: 0.
