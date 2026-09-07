import dataclasses
import unittest
from unittest import mock

from discovery.closure import compute_closure, reachable_sets
from discovery.graph_view import GraphView
from discovery.models import (
    AXES,
    CostVector,
    InvariantError,
    Observations,
    Sample,
    Scenario,
    SeedTerm,
)
from discovery.montecarlo import rank_index, run_scenario
from discovery.policy import default_policy_path, load_exploration_policy
from discovery.simulate import run_phase_a
from discovery.weights import default_weights_path, load_cost_weights
from tests.discovery_graph_fixture import build_graph

SCENARIO = Scenario("s", "t", ("n:a1", "n:a2"), (SeedTerm("alpha", "content"),))


def _policy(**overrides):
    base = dataclasses.replace(
        load_exploration_policy(default_policy_path()),
        repo_map_enabled=False,
        min_samples=20,
        max_samples=60,
        batch=10,
        bootstrap_resamples=50,
    )
    return dataclasses.replace(base, **overrides) if overrides else base


class RankIndexTests(unittest.TestCase):
    def test_nearest_rank_is_clamped_into_the_sample_range(self):
        self.assertEqual(rank_index(0.05, 1), 0)
        self.assertEqual(rank_index(0.05, 20), 0)
        self.assertEqual(rank_index(0.5, 20), 9)
        self.assertEqual(rank_index(0.95, 20), 18)
        self.assertEqual(rank_index(0.95, 1), 0)


class ClosureTests(unittest.TestCase):
    def setUp(self):
        self.view = GraphView(build_graph())
        self.policy = _policy()
        self.weights = load_cost_weights(default_weights_path())

    def test_closure_covers_every_reachable_query_and_read_unit(self):
        phase_a = run_phase_a(self.view, SCENARIO, self.policy)

        queries, units = reachable_sets(self.view, phase_a.seed_query_ids, phase_a)

        self.assertEqual(queries, {"q:root", "q:seed", "q:child", "q:empty"})
        self.assertEqual(units, {"r:doc", "r:a", "r:b", "r:c"})

    def test_closure_includes_phase_a_cost_on_every_axis(self):
        phase_a = run_phase_a(self.view, SCENARIO, self.policy)

        closure = compute_closure(self.view, SCENARIO, self.policy, phase_a.seed_query_ids, phase_a)

        self.assertEqual(
            closure.values(),
            {
                "exploration_turns": 4,
                "search_tool_calls": 4,
                "read_tool_calls": 3,
                "query_result_tokens": 35,
                "readable_node_tokens": 230,
                "zero_result_queries": 1,
                "revisits": 0,
                "exposed_non_target_candidates": 4,
                "duplicate_occurrences": 1,
            },
        )


class RunScenarioTests(unittest.TestCase):
    def setUp(self):
        self.view = GraphView(build_graph())
        self.weights = load_cost_weights(default_weights_path())

    def test_explicit_sample_count_disables_the_adaptive_loop(self):
        result = run_scenario(
            self.view, SCENARIO, _policy(), self.weights, samples=7, seed=101
        )

        self.assertEqual(result.sample_count, 7)
        self.assertIsNone(result.converged)
        self.assertEqual(result.seed, 101)
        self.assertEqual([sample.seed for sample in result.samples], list(range(101, 108)))

    def test_adaptive_loop_stops_at_the_first_batch_within_tolerance(self):
        result = run_scenario(
            self.view, SCENARIO, _policy(relative_tolerance=10.0), self.weights, seed=5
        )

        self.assertTrue(result.converged)
        self.assertEqual(result.sample_count, 30)

    def test_adaptive_loop_runs_to_max_samples_when_it_never_converges(self):
        # The fixture's median is stable enough to converge on any tolerance, so the
        # never-converging branch is driven by samples whose cost grows with the index.
        def growing(view, scenario, policy, weights, rng, index, seed):
            return Sample(
                index=index,
                seed=seed,
                cost=CostVector().add(readable_node_tokens=index),
                observations=Observations(),
                sequence=(),
                status="complete",
                unreached_targets=(),
                id_sequence=(),
            )

        huge = CostVector().add(**{axis: 10 ** 6 for axis in AXES})
        with mock.patch("discovery.montecarlo.run_sample", side_effect=growing):
            with mock.patch("discovery.montecarlo.compute_closure", return_value=huge):
                result = run_scenario(
                    self.view, SCENARIO, _policy(relative_tolerance=1e-12), self.weights, seed=5
                )

        self.assertFalse(result.converged)
        self.assertEqual(result.sample_count, 60)

    def test_adaptive_loop_stops_early_once_the_median_settles(self):
        def steady(view, scenario, policy, weights, rng, index, seed):
            return Sample(
                index=index,
                seed=seed,
                cost=CostVector().add(readable_node_tokens=index % 3),
                observations=Observations(),
                sequence=(),
                status="complete",
                unreached_targets=(),
                id_sequence=(),
            )

        huge = CostVector().add(**{axis: 10 ** 6 for axis in AXES})
        with mock.patch("discovery.montecarlo.run_sample", side_effect=steady):
            with mock.patch("discovery.montecarlo.compute_closure", return_value=huge):
                result = run_scenario(
                    self.view, SCENARIO, _policy(relative_tolerance=1e-12), self.weights, seed=5
                )

        self.assertTrue(result.converged)
        self.assertEqual(result.sample_count, 30)

    def test_adaptive_loop_uses_the_p50_weighted_cost_not_the_mean(self):
        policy = _policy(relative_tolerance=1e-12)

        result = run_scenario(self.view, SCENARIO, policy, self.weights, seed=5)

        ordered = sorted(result.samples, key=self.weights.sort_key)
        median = self.weights.weighted_cost(ordered[rank_index(0.5, len(ordered))].cost)
        self.assertEqual(result.percentiles["p50"]["weighted_cost"], median)

    def test_per_sample_rng_does_not_depend_on_how_many_samples_are_drawn(self):
        twelve = run_scenario(self.view, SCENARIO, _policy(), self.weights, samples=12, seed=5)
        twenty = run_scenario(self.view, SCENARIO, _policy(), self.weights, samples=20, seed=5)

        self.assertEqual(
            [sample.cost for sample in twelve.samples],
            [sample.cost for sample in twenty.samples[:12]],
        )
        self.assertEqual(
            [sample.sequence for sample in twelve.samples],
            [sample.sequence for sample in twenty.samples[:12]],
        )

    def test_seed_defaults_to_the_policy_seed(self):
        policy = _policy()

        result = run_scenario(self.view, SCENARIO, policy, self.weights, samples=4)

        self.assertEqual(result.seed, policy.seed)
        self.assertEqual([sample.seed for sample in result.samples], [policy.seed + index for index in range(4)])

    def test_weighted_cost_is_monotone_across_percentiles(self):
        result = run_scenario(self.view, SCENARIO, _policy(), self.weights, seed=5)

        self.assertLessEqual(
            result.percentiles["p5"]["weighted_cost"], result.percentiles["p50"]["weighted_cost"]
        )
        self.assertLessEqual(
            result.percentiles["p50"]["weighted_cost"], result.percentiles["p95"]["weighted_cost"]
        )
        self.assertTrue(result.invariants["weighted_monotone"])
        self.assertEqual(result.invariants["violations"], [])

    def test_every_sample_axis_stays_within_the_closure(self):
        result = run_scenario(self.view, SCENARIO, _policy(), self.weights, seed=5)

        closure = result.closure.values()
        for sample in result.samples:
            values = sample.cost.values()
            for axis in AXES:
                self.assertLessEqual(values[axis], closure[axis], axis)
        self.assertTrue(result.invariants["axis_within_closure"])

    def test_weighted_monotone_violation_raises_invariant_error(self):
        # Ranking is by weighted cost, so monotonicity can only break if the ranking stops
        # agreeing with the weighted costs. A constant sort key makes sorting a no-op, leaving
        # the samples in generation order, which here is descending in cost.
        def descending(view, scenario, policy, weights, rng, index, seed):
            return Sample(
                index=index,
                seed=seed,
                cost=CostVector().add(readable_node_tokens=100 - index),
                observations=Observations(),
                sequence=(),
                status="complete",
                unreached_targets=(),
                id_sequence=(),
            )

        huge = CostVector().add(**{axis: 10 ** 6 for axis in AXES})
        with mock.patch("discovery.montecarlo.run_sample", side_effect=descending):
            with mock.patch("discovery.montecarlo.compute_closure", return_value=huge):
                with mock.patch.object(
                    type(self.weights), "sort_key", autospec=True, return_value=(0,)
                ):
                    with self.assertRaises(InvariantError) as raised:
                        run_scenario(self.view, SCENARIO, _policy(), self.weights, samples=3, seed=5)

        self.assertIn("weighted_monotone", str(raised.exception))

    def test_closure_violation_raises_invariant_error(self):
        result = run_scenario(self.view, SCENARIO, _policy(), self.weights, samples=3, seed=5)
        shrunk = dataclasses.replace(result.closure, readable_node_tokens=0)

        with mock.patch("discovery.montecarlo.compute_closure", return_value=shrunk):
            with self.assertRaises(InvariantError) as raised:
                run_scenario(self.view, SCENARIO, _policy(), self.weights, samples=3, seed=5)

        self.assertIn("readable_node_tokens", str(raised.exception))
        self.assertIn("axis_within_closure", str(raised.exception))
        offending = min(
            sample.index for sample in result.samples if sample.cost.readable_node_tokens > 0
        )
        self.assertIn(f"sample {offending}", str(raised.exception))

    def test_single_sample_reports_no_bootstrap_interval(self):
        result = run_scenario(self.view, SCENARIO, _policy(), self.weights, samples=1, seed=5)

        for name in ("p5", "p50", "p95"):
            self.assertIsNone(result.percentiles[name]["bootstrap_ci"])
            self.assertEqual(
                result.percentiles[name]["bootstrap_ci_reason"], "fewer than 2 samples"
            )

    def test_bootstrap_interval_brackets_the_point_estimate(self):
        result = run_scenario(self.view, SCENARIO, _policy(), self.weights, samples=40, seed=5)

        entry = result.percentiles["p50"]
        interval = entry["bootstrap_ci"]
        self.assertEqual(interval["resamples"], 50)
        self.assertEqual(interval["interval"], 0.95)
        self.assertLessEqual(interval["low"], interval["high"])
        self.assertLessEqual(interval["low"], entry["weighted_cost"])
        self.assertLessEqual(entry["weighted_cost"], interval["high"])
        self.assertIsNone(entry["bootstrap_ci_reason"])

    def test_bootstrap_resamples_with_replacement(self):
        # Without replacement every resample is a permutation of the sample set, so the rank
        # statistic is constant and the interval collapses onto the point estimate.
        result = run_scenario(self.view, SCENARIO, _policy(), self.weights, samples=40, seed=5)

        entry = result.percentiles["p95"]
        weighted = sorted(self.weights.weighted_cost(sample.cost) for sample in result.samples)
        self.assertGreater(len(set(weighted)), 1)
        self.assertLess(entry["bootstrap_ci"]["low"], entry["bootstrap_ci"]["high"])

    def test_axis_statistics_cover_every_axis(self):
        result = run_scenario(self.view, SCENARIO, _policy(), self.weights, samples=8, seed=5)

        self.assertEqual(set(result.axis_statistics), set(AXES))
        self.assertEqual(result.axis_statistics["revisits"], {"mean": 0.0, "stdev": 0.0})

    def test_results_are_reproducible_for_a_fixed_seed(self):
        first = run_scenario(self.view, SCENARIO, _policy(), self.weights, samples=12, seed=9)
        again = run_scenario(self.view, SCENARIO, _policy(), self.weights, samples=12, seed=9)

        self.assertEqual(
            [sample.cost for sample in first.ranked], [sample.cost for sample in again.ranked]
        )
        self.assertEqual(
            first.percentiles["p95"]["bootstrap_ci"], again.percentiles["p95"]["bootstrap_ci"]
        )

    def test_unreachable_samples_are_counted(self):
        scenario = Scenario("s", "t", ("n:d",), (SeedTerm("alpha", "content"),))

        result = run_scenario(self.view, scenario, _policy(), self.weights, samples=6, seed=5)

        self.assertEqual(result.incomplete_sample_count, 6)
        self.assertEqual(result.percentiles["p50"]["sample"].status, "unreachable")


if __name__ == "__main__":
    unittest.main()
