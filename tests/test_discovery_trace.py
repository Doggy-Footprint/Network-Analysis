import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import dataclasses

from discovery.graph_view import GraphView
from discovery.models import Scenario, SeedTerm
from discovery.montecarlo import run_scenario
from discovery.policy import default_policy_path, load_exploration_policy
from discovery.trace import (
    TraceError,
    _ranks,
    compare_order,
    load_trace,
    observed_discovery_order,
    predicted_discovery_order,
    spearman,
    validate_trace,
)
from discovery.weights import default_weights_path, load_cost_weights
from tests.discovery_graph_fixture import build_graph

ROOT = Path(__file__).resolve().parents[1]
TRACE_PATH = ROOT / "fixtures" / "traces" / "m1-review-session.json"


def _trace(**overrides):
    value = {
        "schema": "agent_trace.v1",
        "trace_id": "abc123",
        "recorded_at": "2026-09-07T00:00:00Z",
        "source": {"tool": "claude-code", "transcript_sha256": "a" * 64, "session_id": "s"},
        "repository": {"name": "repo", "commit": "abc"},
        "agent": {"name": "claude-code", "model": "claude-opus-5", "settings": {}},
        "task": "task",
        "targets": ["a.py", "b.py"],
        "events": [
            {"index": 0, "kind": "search", "paths": [], "raw_tool": "Bash:grep", "surface": "content", "term": "x"},
            {"index": 1, "kind": "read", "paths": ["b.py"], "raw_tool": "Read", "surface": "content", "term": ""},
            {"index": 2, "kind": "read", "paths": ["a.py"], "raw_tool": "Read", "surface": "content", "term": ""},
        ],
    }
    value.update(overrides)
    return value


class RankTests(unittest.TestCase):
    def test_ties_take_the_average_rank(self):
        self.assertEqual(_ranks([1, 1, 2, 3]), [1.5, 1.5, 3.0, 4.0])
        self.assertEqual(_ranks([10, 20, 30]), [1.0, 2.0, 3.0])
        self.assertEqual(_ranks([5, 5, 5]), [2.0, 2.0, 2.0])


class SpearmanTests(unittest.TestCase):
    def test_identical_order_is_one(self):
        self.assertEqual(spearman([1, 2, 3, 4], [1, 2, 3, 4]), 1.0)

    def test_reversed_order_is_minus_one(self):
        self.assertEqual(spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)

    def test_tied_input_uses_average_ranks(self):
        self.assertEqual(spearman([1, 1, 2, 3], [2, 1, 3, 4]), 0.9486832980505138)

    def test_fewer_than_two_points_is_none(self):
        self.assertIsNone(spearman([1], [2]))
        self.assertIsNone(spearman([], []))

    def test_zero_variance_is_none(self):
        self.assertIsNone(spearman([1, 1, 1], [1, 2, 3]))
        self.assertIsNone(spearman([1, 2, 3], [4, 4, 4]))

    def test_mismatched_lengths_raise(self):
        with self.assertRaises(TraceError):
            spearman([1, 2], [1])


class ValidateTraceTests(unittest.TestCase):
    def test_valid_trace_round_trips(self):
        self.assertEqual(validate_trace(_trace())["trace_id"], "abc123")

    def test_wrong_schema_raises(self):
        with self.assertRaises(TraceError):
            validate_trace(_trace(schema="agent_trace.v2"))

    def test_event_index_must_match_position(self):
        events = _trace()["events"]
        events[1]["index"] = 7
        with self.assertRaises(TraceError):
            validate_trace(_trace(events=events))

    def test_unknown_kind_and_surface_raise(self):
        for field, value in (("kind", "compile"), ("surface", "symbol")):
            with self.subTest(field=field):
                events = _trace()["events"]
                events[0][field] = value
                with self.assertRaises(TraceError):
                    validate_trace(_trace(events=events))

    def test_missing_source_field_raises(self):
        with self.assertRaises(TraceError):
            validate_trace(_trace(source={"tool": "claude-code"}))

    def test_non_object_root_raises(self):
        with self.assertRaises(TraceError):
            validate_trace([])

    def test_load_trace_rejects_malformed_json(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(TraceError):
                load_trace(path)

    def test_load_trace_rejects_a_missing_file(self):
        with self.assertRaises(TraceError):
            load_trace(ROOT / "fixtures" / "traces" / "does-not-exist.json")


class ObservedOrderTests(unittest.TestCase):
    def test_first_read_event_index_is_the_discovery_point(self):
        self.assertEqual(observed_discovery_order(_trace()), {"a.py": 2, "b.py": 1})

    def test_search_events_do_not_count_as_discovery(self):
        events = _trace()["events"]
        events[0] = {
            "index": 0, "kind": "search", "paths": ["a.py"],
            "raw_tool": "Bash:grep", "surface": "content", "term": "x",
        }

        self.assertEqual(observed_discovery_order(_trace(events=events))["a.py"], 2)

    def test_targets_never_read_are_absent(self):
        self.assertEqual(observed_discovery_order(_trace(targets=["c.py"])), {})

    def test_recorded_session_trace_matches_its_first_reads(self):
        trace = load_trace(TRACE_PATH)

        self.assertEqual(
            observed_discovery_order(trace),
            {
                "agent_view/exact_query.py": 19,
                "agent_view/models.py": 15,
                "agent_view/occurrence.py": 23,
                "agent_view/profile.py": 110,
            },
        )


class CompareOrderTests(unittest.TestCase):
    def setUp(self):
        self.view = GraphView(build_graph())
        self.policy = dataclasses.replace(
            load_exploration_policy(default_policy_path()),
            repo_map_enabled=False,
            bootstrap_resamples=20,
        )
        self.weights = load_cost_weights(default_weights_path())
        self.scenario = Scenario("s", "t", ("n:a1", "n:a2"), (SeedTerm("alpha", "content"),))
        self.result = run_scenario(
            self.view, self.scenario, self.policy, self.weights, samples=4, seed=5
        )

    def _trace(self, events):
        return validate_trace(_trace(targets=["a.py", "b.py", "c.py"], events=events))

    def test_predicted_order_maps_node_ids_to_paths_and_keeps_the_earliest_turn(self):
        sample = self.result.percentiles["p50"]["sample"]

        predicted = predicted_discovery_order(self.view, sample)

        self.assertEqual(sorted(predicted), ["a.py"])
        self.assertEqual(predicted["a.py"], sample.observations.discovery_turn_index["n:a1"])

    def test_comparison_records_policy_seed_and_shared_targets(self):
        events = [
            {"index": 0, "kind": "read", "paths": ["a.py"], "raw_tool": "Read", "surface": "content", "term": ""},
            {"index": 1, "kind": "read", "paths": ["b.py"], "raw_tool": "Read", "surface": "content", "term": ""},
        ]

        comparison = compare_order(self._trace(events), self.result, self.view, self.policy)

        self.assertEqual(comparison["scenario_id"], "s")
        self.assertEqual(comparison["percentile"], "p50")
        self.assertEqual(comparison["seed"], 5)
        self.assertEqual(comparison["sample_count"], 4)
        self.assertEqual(
            comparison["policy"],
            {"phase_b": "bfs-exhaust", "result_ordering": "hint-prior"},
        )
        self.assertEqual(comparison["compared_targets"], ["a.py"])
        self.assertEqual(comparison["observed_only"], ["b.py"])
        self.assertEqual(comparison["n"], 1)

    def test_a_single_shared_target_yields_no_rho_with_a_reason(self):
        events = [
            {"index": 0, "kind": "read", "paths": ["a.py"], "raw_tool": "Read", "surface": "content", "term": ""},
        ]

        comparison = compare_order(self._trace(events), self.result, self.view, self.policy)

        self.assertIsNone(comparison["spearman_rho"])
        self.assertEqual(comparison["reason"], "fewer than 2 shared targets")


class TraceFitFixtureTests(unittest.TestCase):
    def setUp(self):
        self.fit = json.loads((ROOT / "fixtures" / "trace_fit.json").read_text(encoding="utf-8"))

    def test_fit_records_both_policy_axes_without_a_pass_threshold(self):
        self.assertEqual(self.fit["schema"], "trace_fit.v1")
        self.assertIn("No pass threshold is set", self.fit["note"])
        self.assertEqual(
            sorted(self.fit["policy_fit"]),
            [
                "best-first-pivot|hint-prior", "best-first-pivot|uniform",
                "bfs-exhaust|hint-prior", "bfs-exhaust|uniform",
            ],
        )

    def test_fit_states_target_provenance_and_snapshot_drift(self):
        self.assertIn("actually changed", self.fit["target_provenance"])
        self.assertIn("circular", self.fit["target_provenance"])
        self.assertIn("earlier snapshot", self.fit["snapshot_note"])
        self.assertEqual(
            sorted(self.fit["excluded_targets"]),
            ["agent_view/__init__.py", "agent_view/scan.py"],
        )

    def test_every_comparison_reports_a_rho_or_a_reason(self):
        self.assertTrue(self.fit["comparisons"])
        for comparison in self.fit["comparisons"]:
            with self.subTest(policy=comparison["policy"]):
                if comparison["spearman_rho"] is None:
                    self.assertIsNotNone(comparison["reason"])
                else:
                    self.assertIsNone(comparison["reason"])
                    self.assertGreaterEqual(comparison["spearman_rho"], -1.0)
                    self.assertLessEqual(comparison["spearman_rho"], 1.0)

    def test_scenario_targets_match_the_recorded_trace_targets(self):
        scenarios = json.loads(
            (ROOT / "fixtures" / "scenarios_self.v1.json").read_text(encoding="utf-8")
        )
        trace = load_trace(TRACE_PATH)

        self.assertEqual(sorted(scenarios["scenarios"][0]["targets"]), sorted(trace["targets"]))


if __name__ == "__main__":
    unittest.main()
