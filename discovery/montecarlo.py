import math
import random
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .closure import compute_closure, reachable_sets
from .graph_view import GraphView
from .models import AXES, CostVector, InvariantError, Sample, Scenario
from .policy import ExplorationPolicy
from .simulate import PhaseAResult, run_phase_a, run_sample
from .weights import CostWeights

PERCENTILES = (("p5", 0.05), ("p50", 0.5), ("p95", 0.95))
PERCENTILE_METHOD = "nearest-rank"
BOOTSTRAP_SEED_MASK = 0x5EED


@dataclass(frozen=True)
class ScenarioResult:
    scenario: Scenario
    seed: int
    sample_count: int
    converged: Optional[bool]
    phase_a: PhaseAResult
    samples: Tuple[Sample, ...]
    ranked: Tuple[Sample, ...]
    percentiles: Dict[str, Dict[str, Any]]
    axis_statistics: Dict[str, Dict[str, float]]
    closure: CostVector
    closure_weighted_cost: float
    closure_query_count: int
    closure_read_unit_count: int
    invariants: Dict[str, Any]
    incomplete_sample_count: int


def rank_index(fraction: float, count: int) -> int:
    return min(count - 1, max(0, math.ceil(fraction * count) - 1))


def _bootstrap(
    values: List[float],
    fraction: float,
    policy: ExplorationPolicy,
    seed_root: int,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    count = len(values)
    if count < 2:
        return None, "fewer than 2 samples"
    rng = random.Random(seed_root ^ BOOTSTRAP_SEED_MASK)
    index = rank_index(fraction, count)
    statistics_list = []
    for _ in range(policy.bootstrap_resamples):
        resample = sorted(values[rng.randrange(count)] for _ in range(count))
        statistics_list.append(resample[index])
    statistics_list.sort()
    tail = (1.0 - policy.bootstrap_interval) / 2.0
    low = statistics_list[rank_index(tail, len(statistics_list))]
    high = statistics_list[rank_index(1.0 - tail, len(statistics_list))]
    return (
        {
            "low": low,
            "high": high,
            "resamples": policy.bootstrap_resamples,
            "interval": policy.bootstrap_interval,
        },
        None,
    )


def run_scenario(
    view: GraphView,
    scenario: Scenario,
    policy: ExplorationPolicy,
    weights: CostWeights,
    *,
    samples: Optional[int] = None,
    seed: Optional[int] = None,
) -> ScenarioResult:
    seed_root = policy.seed if seed is None else seed
    phase_a = run_phase_a(view, scenario, policy)

    def draw(start: int, stop: int) -> List[Sample]:
        return [
            run_sample(
                view,
                scenario,
                policy,
                weights,
                random.Random(seed_root + index),
                index,
                seed_root + index,
            )
            for index in range(start, stop)
        ]

    def median_weighted(drawn: List[Sample]) -> float:
        ordered = sorted(drawn, key=weights.sort_key)
        return weights.weighted_cost(ordered[rank_index(0.5, len(ordered))].cost)

    converged: Optional[bool]
    if samples is not None:
        if samples < 1:
            raise ValueError("samples must be >= 1")
        drawn = draw(0, samples)
        converged = None
    else:
        drawn = draw(0, policy.min_samples)
        previous = median_weighted(drawn)
        converged = False
        while len(drawn) < policy.max_samples:
            stop = min(policy.max_samples, len(drawn) + policy.batch)
            drawn.extend(draw(len(drawn), stop))
            current = median_weighted(drawn)
            change = abs(current - previous) / abs(previous) if previous else float(current != 0)
            previous = current
            if change <= policy.relative_tolerance:
                converged = True
                break

    ranked = sorted(drawn, key=weights.sort_key)
    count = len(ranked)
    weighted_values = [weights.weighted_cost(sample.cost) for sample in ranked]

    closure = compute_closure(view, scenario, policy, phase_a.seed_query_ids, phase_a)
    closure_queries, closure_units = reachable_sets(view, phase_a.seed_query_ids, phase_a)
    closure_values = closure.values()

    violations: List[Dict[str, Any]] = []
    for sample in drawn:
        values = sample.cost.values()
        for axis in AXES:
            if values[axis] > closure_values[axis]:
                violations.append(
                    {"invariant": "axis_within_closure", "sample_index": sample.index, "axis": axis}
                )

    percentiles: Dict[str, Dict[str, Any]] = {}
    for name, fraction in PERCENTILES:
        index = rank_index(fraction, count)
        sample = ranked[index]
        interval, reason = _bootstrap(weighted_values, fraction, policy, seed_root)
        percentiles[name] = {
            "rank": index,
            "sample": sample,
            "weighted_cost": weighted_values[index],
            "bootstrap_ci": interval,
            "bootstrap_ci_reason": reason,
        }
    monotone = (
        percentiles["p5"]["weighted_cost"]
        <= percentiles["p50"]["weighted_cost"]
        <= percentiles["p95"]["weighted_cost"]
    )
    if not monotone:
        violations.append({"invariant": "weighted_monotone", "sample_index": None, "axis": None})

    axis_statistics = {}
    for axis in AXES:
        column = [sample.cost.values()[axis] for sample in drawn]
        axis_statistics[axis] = {
            "mean": statistics.fmean(column),
            "stdev": statistics.pstdev(column),
        }

    invariants = {
        "weighted_monotone": monotone,
        "axis_within_closure": not any(
            item["invariant"] == "axis_within_closure" for item in violations
        ),
        "violations": violations,
    }
    if violations:
        first = violations[0]
        raise InvariantError(
            f"{first['invariant']} violated at sample {first['sample_index']} axis {first['axis']}"
        )

    return ScenarioResult(
        scenario=scenario,
        seed=seed_root,
        sample_count=count,
        converged=converged,
        phase_a=phase_a,
        samples=tuple(drawn),
        ranked=tuple(ranked),
        percentiles=percentiles,
        axis_statistics=axis_statistics,
        closure=closure,
        closure_weighted_cost=weights.weighted_cost(closure),
        closure_query_count=len(closure_queries),
        closure_read_unit_count=len(closure_units),
        invariants=invariants,
        incomplete_sample_count=sum(1 for sample in drawn if sample.status != "complete"),
    )
