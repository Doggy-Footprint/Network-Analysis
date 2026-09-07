import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_view import build_agent_view  # noqa: E402
from agent_view.profile import default_profile_path, load_profile  # noqa: E402
from discovery import (  # noqa: E402
    CachedSeedQueryGenerator,
    GraphView,
    compare_order,
    default_policy_path,
    default_weights_path,
    load_cost_weights,
    load_exploration_policy,
    load_scenarios,
    resolve_seed_queries,
    run_scenario,
)
from discovery.trace import load_trace  # noqa: E402
from language_analyzers.python.graph import PythonGraphAnalyzer  # noqa: E402

SCHEMA = "trace_fit.v1"
POLICIES = ("bfs-exhaust", "best-first-pivot")
ORDERINGS = ("hint-prior", "uniform")
NOTE = (
    "No pass threshold is set. The gate requires that the measurement is recorded and becomes "
    "the stated basis for the defaults, not that it exceeds a level."
)
TARGET_PROVENANCE = (
    "Targets are the files the recorded session actually changed, taken from the commits it "
    "produced (d4040c1, 7c36875, 7c0b9de, fd2f45e, 921fa8f) and intersected with paths that "
    "still carry a readable node in the analysed snapshot. Deriving them from what the session "
    "read early would make the discovery-order comparison circular."
)
EXCLUDED_TARGETS = {
    "agent_view/__init__.py": "analyzer_artifact",
    "agent_view/scan.py": "analyzer_artifact",
}
SNAPSHOT_NOTE = (
    "The trace was recorded against an earlier snapshot than the one analysed here, so target "
    "paths that were later renamed or deleted are excluded rather than remapped."
)


def _mean(values: Sequence[Optional[float]]) -> Optional[float]:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def build_fit(
    project_path: Path,
    scenarios_path: Path,
    seed_queries_path: Path,
    trace_paths: Sequence[Path],
    *,
    samples: Optional[int],
    percentile: str,
) -> Dict[str, Any]:
    architecture = PythonGraphAnalyzer(project_path).analyze()
    profile = load_profile(default_profile_path())
    graph = build_agent_view(architecture, profile=profile)
    view = GraphView(graph)
    base_policy = load_exploration_policy(default_policy_path())
    weights = load_cost_weights(default_weights_path())
    cached = CachedSeedQueryGenerator.from_path(seed_queries_path)
    traces = [load_trace(path) for path in trace_paths]

    comparisons: List[Dict[str, Any]] = []
    for scenario in load_scenarios(scenarios_path, view):
        resolved, _ = resolve_seed_queries(scenario, cached)
        for phase_b in POLICIES:
            for ordering in ORDERINGS:
                policy = dataclasses.replace(
                    base_policy, phase_b_policy=phase_b, result_ordering=ordering
                )
                result = run_scenario(view, resolved, policy, weights, samples=samples)
                for trace in traces:
                    comparisons.append(
                        compare_order(trace, result, view, policy, percentile=percentile)
                    )

    policy_fit = {}
    for phase_b in POLICIES:
        for ordering in ORDERINGS:
            selected = [
                item["spearman_rho"]
                for item in comparisons
                if item["policy"]["phase_b"] == phase_b
                and item["policy"]["result_ordering"] == ordering
            ]
            policy_fit[f"{phase_b}|{ordering}"] = {
                "mean_spearman_rho": _mean(selected),
                "comparisons_with_rho": sum(1 for value in selected if value is not None),
            }

    return {
        "schema": SCHEMA,
        "project_path": str(project_path),
        "snapshot_digest": graph.scan.snapshot_digest,
        "percentile": percentile,
        "note": NOTE,
        "target_provenance": TARGET_PROVENANCE,
        "snapshot_note": SNAPSHOT_NOTE,
        "excluded_targets": dict(sorted(EXCLUDED_TARGETS.items())),
        "trace_count": len(traces),
        "traces": [
            {
                "trace_id": trace["trace_id"],
                "task": trace["task"],
                "targets": list(trace["targets"]),
                "event_count": len(trace["events"]),
                "source": dict(trace["source"]),
                "repository": dict(trace["repository"]),
                "agent": dict(trace["agent"]),
            }
            for trace in traces
        ],
        "policy_fit": policy_fit,
        "comparisons": comparisons,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="기록된 에이전트 트레이스와 모델의 대상 발견 순서를 비교합니다."
    )
    parser.add_argument("--project-path", default=".")
    parser.add_argument("--scenarios", default="fixtures/scenarios_self.v1.json")
    parser.add_argument("--seed-queries", default="fixtures/seed_queries.v1.json")
    parser.add_argument("--trace", action="append", required=True)
    parser.add_argument("--samples", type=int, default=None)
    parser.add_argument("--percentile", default="p50", choices=("p5", "p50", "p95"))
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args(argv)

    payload = build_fit(
        Path(args.project_path),
        Path(args.scenarios),
        Path(args.seed_queries),
        [Path(item) for item in args.trace],
        samples=args.samples,
        percentile=args.percentile,
    )
    Path(args.output).write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
