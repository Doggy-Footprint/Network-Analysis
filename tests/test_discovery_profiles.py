import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from discovery.models import (
    AXES,
    CostVector,
    InvariantError,
    PolicyError,
    Sample,
    ScenarioError,
    SeedQueryError,
    WeightsError,
)
from discovery.policy import default_policy_path, load_exploration_policy
from discovery.weights import default_weights_path, load_cost_weights


def _write(directory, name, document):
    path = Path(directory) / name
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _sample(index=0, **axes):
    return Sample(
        index=index,
        seed=index,
        cost=CostVector().add(**axes),
        observations=None,
        sequence=(),
        status="complete",
        unreached_targets=(),
        id_sequence=(),
    )


class ExplorationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.document = yaml.safe_load(default_policy_path().read_text(encoding="utf-8"))

    def test_default_profile_loads_with_recorded_content_hash(self):
        policy = load_exploration_policy(default_policy_path())

        self.assertEqual(policy.ref.id, "exploration_policy.v1")
        self.assertEqual(policy.ref.version, 1)
        self.assertEqual(policy.phase_b_policy, "bfs-exhaust")
        self.assertEqual(policy.result_ordering, "hint-prior")
        self.assertEqual(policy.repo_map_rank, "pagerank")
        self.assertEqual(policy.revisit_probability, 0.0)
        self.assertEqual(policy.tie_break_version, "axis-lex-seqlen-idseq-v1")
        self.assertEqual(policy.role_weights["declaration"], 3.0)
        self.assertEqual(policy.filename_exact_bonus, 2.0)
        self.assertEqual(policy.seed, 20260907)
        self.assertEqual(
            policy.output()["content_hash"],
            hashlib.sha256(default_policy_path().read_bytes()).hexdigest(),
        )

    def test_non_zero_revisit_probability_is_rejected(self):
        self.document["phase_b"]["revisit_probability"] = 0.1
        with TemporaryDirectory() as directory:
            path = _write(directory, "policy.yaml", self.document)
            with self.assertRaises(PolicyError) as raised:
                load_exploration_policy(path)
        self.assertIn("revisit_probability", str(raised.exception))

    def test_invalid_values_are_rejected_with_the_offending_key(self):
        cases = {
            "phase_b.policy": ("phase_b", "policy", "depth-first"),
            "phase_b.result_ordering": ("phase_b", "result_ordering", "random"),
            "sampling.bootstrap_interval": ("sampling", "bootstrap_interval", 1.0),
            "sampling.relative_tolerance": ("sampling", "relative_tolerance", 0),
            "sampling.min_samples": ("sampling", "min_samples", 1),
            "sampling.batch": ("sampling", "batch", 0),
        }
        for label, (section, key, value) in cases.items():
            with self.subTest(label=label):
                document = yaml.safe_load(default_policy_path().read_text(encoding="utf-8"))
                document[section][key] = value
                with TemporaryDirectory() as directory:
                    path = _write(directory, "policy.yaml", document)
                    with self.assertRaises(PolicyError) as raised:
                        load_exploration_policy(path)
                self.assertIn(key, str(raised.exception))

    def test_max_samples_below_min_samples_is_rejected(self):
        self.document["sampling"]["max_samples"] = 2
        self.document["sampling"]["min_samples"] = 10
        with TemporaryDirectory() as directory:
            path = _write(directory, "policy.yaml", self.document)
            with self.assertRaises(PolicyError):
                load_exploration_policy(path)

    def test_non_pagerank_repo_map_rank_is_rejected(self):
        self.document["phase_a"]["structural_repo_map"]["rank"] = "degree"
        with TemporaryDirectory() as directory:
            path = _write(directory, "policy.yaml", self.document)
            with self.assertRaises(PolicyError):
                load_exploration_policy(path)

    def test_unknown_top_level_key_is_rejected(self):
        self.document["phase_d"] = {}
        with TemporaryDirectory() as directory:
            path = _write(directory, "policy.yaml", self.document)
            with self.assertRaises(PolicyError) as raised:
                load_exploration_policy(path)
        self.assertIn("phase_d", str(raised.exception))

    def test_negative_role_weight_is_rejected(self):
        self.document["hint_prior"]["role_weights"]["call"] = -1.0
        with TemporaryDirectory() as directory:
            path = _write(directory, "policy.yaml", self.document)
            with self.assertRaises(PolicyError):
                load_exploration_policy(path)

    def test_wrong_version_is_rejected(self):
        self.document["version"] = 2
        with TemporaryDirectory() as directory:
            path = _write(directory, "policy.yaml", self.document)
            with self.assertRaises(PolicyError):
                load_exploration_policy(path)


class CostWeightsTests(unittest.TestCase):
    def setUp(self):
        self.document = yaml.safe_load(default_weights_path().read_text(encoding="utf-8"))
        self.weights = load_cost_weights(default_weights_path())

    def test_default_profile_loads(self):
        self.assertEqual(self.weights.ref.id, "cost_weights.v1")
        self.assertEqual(set(self.weights.weights), set(AXES))
        self.assertEqual(
            self.weights.axis_priority,
            (
                "readable_node_tokens", "query_result_tokens", "read_tool_calls",
                "search_tool_calls", "exploration_turns", "zero_result_queries",
                "exposed_non_target_candidates", "duplicate_occurrences", "revisits",
            ),
        )

    def test_cost_vector_values_are_ordered_exactly_as_the_axis_tuple(self):
        values = CostVector().add(read_tool_calls=1).values()

        self.assertEqual(tuple(values), AXES)
        self.assertEqual(list(values.items())[2], ("read_tool_calls", 1))

    def test_loader_errors_are_value_errors_and_invariant_error_is_a_runtime_error(self):
        for error in (PolicyError, WeightsError, ScenarioError, SeedQueryError):
            with self.subTest(error=error.__name__):
                self.assertTrue(issubclass(error, ValueError))
        self.assertTrue(issubclass(InvariantError, RuntimeError))
        self.assertFalse(issubclass(InvariantError, ValueError))

    def test_weighted_cost_sums_weight_times_axis_over_every_axis(self):
        cost = CostVector().add(
            exploration_turns=3,
            search_tool_calls=3,
            read_tool_calls=2,
            query_result_tokens=100,
            readable_node_tokens=1000,
            zero_result_queries=5,
            revisits=4,
            exposed_non_target_candidates=7,
            duplicate_occurrences=9,
        )

        self.assertEqual(
            self.weights.weighted_cost(cost),
            10 * 3 + 10 * 3 + 10 * 2 + 100 + 1000 + 0 * 5 + 10 * 4 + 0 * 7 + 0 * 9,
        )

    def test_zero_weighted_axes_do_not_move_the_weighted_cost(self):
        base = CostVector().add(read_tool_calls=1)
        noisy = base.add(zero_result_queries=99, exposed_non_target_candidates=99, duplicate_occurrences=99)

        self.assertEqual(self.weights.weighted_cost(base), self.weights.weighted_cost(noisy))

    def test_tie_break_cascade_orders_by_axis_priority_then_length_then_ids(self):
        cheaper_tokens = _sample(0, readable_node_tokens=10, query_result_tokens=99)
        more_tokens = _sample(1, readable_node_tokens=11)

        self.assertLess(
            self.weights.tie_break_key(cheaper_tokens),
            self.weights.tie_break_key(more_tokens),
        )

        short = Sample(0, 0, CostVector(), None, (), "complete", (), ("a.py#A",))
        long = Sample(1, 1, CostVector(), None, (1,), "complete", (), ("a.py#A",))
        self.assertLess(self.weights.tie_break_key(short), self.weights.tie_break_key(long))

        first = Sample(0, 0, CostVector(), None, (), "complete", (), ("a.py#A",))
        second = Sample(1, 1, CostVector(), None, (), "complete", (), ("b.py#B",))
        self.assertLess(self.weights.tie_break_key(first), self.weights.tie_break_key(second))

    def test_sort_key_is_the_weighted_cost_then_the_tie_break_tuple(self):
        sample = _sample(0, read_tool_calls=1, readable_node_tokens=5)

        self.assertEqual(
            self.weights.sort_key(sample),
            (
                15.0,
                (5, 0, 1, 0, 0, 0, 0, 0, 0),
                0,
                (),
            ),
        )

    def test_tie_break_level_two_uses_the_shorter_execution_sequence(self):
        cost = CostVector().add(read_tool_calls=1)
        short = Sample(0, 0, cost, None, ("a",), "complete", (), ("x",))
        long = Sample(1, 1, cost, None, ("a", "b"), "complete", (), ("x",))

        self.assertEqual(self.weights.weighted_cost(short.cost), self.weights.weighted_cost(long.cost))
        self.assertEqual(self.weights.tie_break_key(short)[0], self.weights.tie_break_key(long)[0])
        self.assertLess(self.weights.sort_key(short), self.weights.sort_key(long))

    def test_tie_break_level_three_uses_the_id_sequence(self):
        cost = CostVector().add(read_tool_calls=1)
        first = Sample(0, 0, cost, None, ("a",), "complete", (), ("a.py#A",))
        second = Sample(1, 1, cost, None, ("a",), "complete", (), ("b.py#B",))

        self.assertEqual(self.weights.tie_break_key(first)[:2], self.weights.tie_break_key(second)[:2])
        self.assertLess(self.weights.sort_key(first), self.weights.sort_key(second))

    def test_tie_break_level_three_normalizes_separators_and_compares_unicode_bytewise(self):
        cost = CostVector().add(read_tool_calls=1)
        windows_path = Sample(0, 0, cost, None, ("a",), "complete", (), ("pkg\\nested\\c.py#Å",))
        normalized_path = Sample(1, 1, cost, None, ("a",), "complete", (), ("pkg/nested/c.py#Å",))
        later_utf8 = Sample(2, 2, cost, None, ("a",), "complete", (), ("pkg/nested/c.py#ß",))

        self.assertEqual(self.weights.tie_break_key(windows_path), self.weights.tie_break_key(normalized_path))
        self.assertLess(self.weights.sort_key(normalized_path), self.weights.sort_key(later_utf8))

    def test_wrong_version_is_rejected(self):
        self.document["version"] = 2
        with TemporaryDirectory() as directory:
            path = _write(directory, "weights.yaml", self.document)
            with self.assertRaises(WeightsError):
                load_cost_weights(path)

    def test_an_extra_axis_in_weights_is_rejected(self):
        self.document["weights"]["invented_axis"] = 1
        with TemporaryDirectory() as directory:
            path = _write(directory, "weights.yaml", self.document)
            with self.assertRaises(WeightsError) as raised:
                load_cost_weights(path)
        self.assertIn("invented_axis", str(raised.exception))

    def test_axis_priority_of_the_right_length_with_a_duplicate_is_rejected(self):
        priority = list(AXES)
        priority[0] = priority[1]
        self.document["axis_priority"] = priority
        with TemporaryDirectory() as directory:
            path = _write(directory, "weights.yaml", self.document)
            with self.assertRaises(WeightsError):
                load_cost_weights(path)

    def test_non_string_provenance_value_is_rejected(self):
        self.document["provenance"]["revisits"] = 3
        with TemporaryDirectory() as directory:
            path = _write(directory, "weights.yaml", self.document)
            with self.assertRaises(WeightsError):
                load_cost_weights(path)

    def test_missing_axis_is_rejected(self):
        del self.document["weights"]["revisits"]
        with TemporaryDirectory() as directory:
            path = _write(directory, "weights.yaml", self.document)
            with self.assertRaises(WeightsError) as raised:
                load_cost_weights(path)
        self.assertIn("revisits", str(raised.exception))

    def test_negative_weight_is_rejected(self):
        self.document["weights"]["revisits"] = -1
        with TemporaryDirectory() as directory:
            path = _write(directory, "weights.yaml", self.document)
            with self.assertRaises(WeightsError):
                load_cost_weights(path)

    def test_axis_priority_must_be_a_permutation(self):
        self.document["axis_priority"] = list(AXES)[:-1]
        with TemporaryDirectory() as directory:
            path = _write(directory, "weights.yaml", self.document)
            with self.assertRaises(WeightsError):
                load_cost_weights(path)

    def test_provenance_must_cover_every_axis(self):
        del self.document["provenance"]["revisits"]
        with TemporaryDirectory() as directory:
            path = _write(directory, "weights.yaml", self.document)
            with self.assertRaises(WeightsError):
                load_cost_weights(path)


if __name__ == "__main__":
    unittest.main()
