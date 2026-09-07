import dataclasses
import random
import unittest

from discovery.graph_view import GraphView
from discovery.models import Scenario, SeedTerm
from discovery.policy import default_policy_path, load_exploration_policy
from discovery.simulate import _select, run_phase_a, run_sample
from discovery.weights import default_weights_path, load_cost_weights
from tests.discovery_graph_fixture import build_graph


def _policy(**overrides):
    base = dataclasses.replace(
        load_exploration_policy(default_policy_path()), repo_map_enabled=False
    )
    return dataclasses.replace(base, **overrides) if overrides else base


def _actions(sample):
    return [(step.phase, step.action, step.id) for step in sample.sequence]


class PhaseATests(unittest.TestCase):
    def setUp(self):
        self.view = GraphView(build_graph())
        self.weights = load_cost_weights(default_weights_path())

    def test_injected_entry_document_charges_tokens_but_no_read_call(self):
        result = run_phase_a(
            self.view, Scenario("s", "t", ("n:doc",), ()), _policy(root_list_query=False)
        )

        self.assertEqual(result.cost.read_tool_calls, 0)
        self.assertEqual(result.cost.readable_node_tokens, 40)
        self.assertEqual(result.steps[0].id, "r:doc")
        self.assertEqual(result.steps[0].turn, 0)

    def test_non_injected_entry_document_charges_a_read_call(self):
        view = GraphView(build_graph(entry_injected=False))

        result = run_phase_a(view, Scenario("s", "t", ("n:doc",), ()), _policy(root_list_query=False))

        self.assertEqual(result.cost.read_tool_calls, 1)
        self.assertEqual(result.cost.readable_node_tokens, 40)

    def test_entry_document_generated_queries_start_phase_b_pending(self):
        view = GraphView(
            build_graph(extra_edges=(("n:doc", "q:child", "generates"),))
        )

        result = run_phase_a(
            view, Scenario("s", "t", ("n:c",), ()), _policy(root_list_query=False)
        )
        sample = run_sample(
            view, Scenario("s", "t", ("n:c",), ()), _policy(root_list_query=False),
            self.weights, random.Random(0), 0, 0,
        )

        self.assertEqual(result.initial_pending_query_ids, ("q:child",))
        self.assertEqual(sample.status, "complete")
        self.assertIn(("B", "search", "q:child"), _actions(sample))

    def test_root_list_query_is_executed_and_its_group_is_deferred(self):
        result = run_phase_a(self.view, Scenario("s", "t", ("n:a1",), ()), _policy())

        self.assertEqual(result.open_groups, ("q:root",))
        self.assertEqual(result.executed_query_ids, ("q:root",))
        self.assertEqual(result.cost.exploration_turns, 1)
        self.assertEqual(result.cost.search_tool_calls, 1)
        self.assertEqual(result.cost.query_result_tokens, 10)
        self.assertEqual(result.cost.read_tool_calls, 0)

    def test_unmatched_seed_term_is_charged_as_a_zero_result_query(self):
        scenario = Scenario("s", "t", ("n:a1",), (SeedTerm("nope", "content"),))

        result = run_phase_a(self.view, scenario, _policy(root_list_query=False))

        self.assertEqual(result.unmatched_terms, (SeedTerm("nope", "content"),))
        self.assertEqual(result.seed_query_ids, ())
        self.assertEqual(result.cost.exploration_turns, 1)
        self.assertEqual(result.cost.search_tool_calls, 1)
        self.assertEqual(result.cost.zero_result_queries, 1)
        self.assertEqual(result.cost.query_result_tokens, 0)
        self.assertEqual(result.steps[-1].id, "seed:content:nope")

    def test_repo_map_is_truncated_by_max_entries(self):
        scenario = Scenario("s", "t", ("n:a1",), ())
        policy = _policy(repo_map_enabled=True, repo_map_max_entries=2)

        result = run_phase_a(self.view, scenario, policy)

        self.assertEqual(result.repo_map_node_ids, ("n:b", "n:a1"))
        self.assertEqual(result.repo_map_tokens, 5)

    def test_repo_map_takes_the_longest_prefix_within_the_token_budget(self):
        scenario = Scenario("s", "t", ("n:a1",), ())

        for budget, entries, tokens in ((10, 3, 7), (6, 2, 5), (1, 0, 0)):
            with self.subTest(budget=budget):
                policy = _policy(repo_map_enabled=True, repo_map_token_budget=budget)

                result = run_phase_a(self.view, scenario, policy)

                self.assertEqual(len(result.repo_map_node_ids), entries)
                self.assertEqual(result.repo_map_tokens, tokens)
                self.assertLessEqual(result.repo_map_tokens, budget)

    def test_repo_map_is_ranked_by_descending_score_then_node_id(self):
        scenario = Scenario("s", "t", ("n:a1",), ())

        result = run_phase_a(self.view, scenario, _policy(repo_map_enabled=True))

        self.assertEqual(result.repo_map_node_ids[0], "n:b")
        self.assertEqual(list(result.repo_map_node_ids[1:]), sorted(result.repo_map_node_ids[1:]))

    def test_repo_map_charges_result_tokens_without_a_tool_call(self):
        scenario = Scenario("s", "t", ("n:a1",), ())

        result = run_phase_a(self.view, scenario, _policy(repo_map_enabled=True))

        self.assertEqual(len(result.repo_map_node_ids), 6)
        self.assertEqual(result.repo_map_tokens, 17)
        self.assertEqual(result.cost.query_result_tokens, 10 + 17)
        self.assertEqual(result.cost.read_tool_calls, 0)
        inject = next(step for step in result.steps if step.action == "inject")
        self.assertEqual(inject.id, "repo_map")
        self.assertEqual(inject.cost_delta, {"query_result_tokens": 17})


class PhaseBTests(unittest.TestCase):
    def setUp(self):
        self.view = GraphView(build_graph())
        self.weights = load_cost_weights(default_weights_path())

    def run_sample(self, scenario, policy=None, seed=0, view=None):
        return run_sample(
            view or self.view,
            scenario,
            policy or _policy(),
            self.weights,
            random.Random(seed),
            0,
            seed,
        )

    def test_several_targets_in_one_unit_cost_one_read_and_share_a_turn(self):
        scenario = Scenario("s", "t", ("n:a1", "n:a2"), (SeedTerm("alpha", "content"),))

        sample = self.run_sample(scenario, seed=1)

        self.assertEqual(sample.status, "complete")
        self.assertEqual(_actions(sample).count(("B", "read", "r:a")), 1)
        self.assertEqual(
            sample.observations.discovery_turn_index, {"n:a1": 2, "n:a2": 2}
        )
        self.assertEqual(sample.cost.read_tool_calls, 2)
        self.assertEqual(sample.cost.readable_node_tokens, 40 + 60 + 100)

    def test_entry_document_direct_read_finds_target_without_a_search(self):
        view = GraphView(
            build_graph(extra_edges=(("n:doc", "n:b", "static", "unique"),))
        )
        sample = self.run_sample(
            Scenario("s", "t", ("n:b",), ()), policy=_policy(root_list_query=False), view=view
        )

        self.assertEqual(sample.status, "complete")
        self.assertEqual(_actions(sample), [("A", "read", "r:doc"), ("A", "read", "r:b")])
        self.assertEqual(sample.cost.exploration_turns, 0)

    def test_search_result_direct_read_follows_unique_chain_once(self):
        view = GraphView(
            build_graph(
                extra_edges=(
                    ("n:a1", "n:b", "static", "unique"),
                    ("n:b", "n:a1", "static", "unique"),
                )
            )
        )
        sample = self.run_sample(
            Scenario("s", "t", ("n:b",), (SeedTerm("alpha", "content"),)),
            policy=_policy(root_list_query=False), view=view,
        )

        self.assertEqual(sample.status, "complete")
        self.assertEqual(_actions(sample).count(("B", "read", "r:a")), 1)
        self.assertEqual(_actions(sample).count(("B", "read", "r:b")), 1)
        self.assertEqual(sample.cost.exploration_turns, 1)

    def test_narrowing_static_connection_is_not_directly_read(self):
        view = GraphView(
            build_graph(extra_edges=(("n:doc", "n:d", "static", "narrowing"),))
        )
        sample = self.run_sample(
            Scenario("s", "t", ("n:d",), ()), policy=_policy(root_list_query=False), view=view
        )

        self.assertEqual(sample.status, "unreachable")
        self.assertNotIn(("A", "read", "r:d"), _actions(sample))

    def test_target_inside_an_already_read_unit_costs_no_extra_read(self):
        scenario = Scenario("s", "t", ("n:doc",), (SeedTerm("alpha", "content"),))

        sample = self.run_sample(scenario)

        self.assertEqual(sample.status, "complete")
        self.assertEqual(sample.observations.discovery_turn_index, {"n:doc": 0})
        self.assertEqual(sample.cost.read_tool_calls, 0)
        self.assertEqual(sample.cost.readable_node_tokens, 40)

    def test_matched_seed_query_is_charged_even_when_phase_a_found_every_target(self):
        scenario = Scenario("s", "t", ("n:doc",), (SeedTerm("alpha", "content"),))

        sample = self.run_sample(scenario)

        self.assertEqual(
            _actions(sample),
            [("A", "read", "r:doc"), ("A", "search", "q:root"), ("B", "search", "q:seed")],
        )
        self.assertEqual(sample.cost.exploration_turns, 2)
        self.assertEqual(sample.cost.search_tool_calls, 2)
        self.assertEqual(sample.cost.query_result_tokens, 30)
        self.assertEqual(sample.cost.duplicate_occurrences, 1)
        self.assertEqual(sample.observations.hinted_unread_nodes, 3)

    def test_arrival_in_an_already_read_unit_is_not_read_twice(self):
        scenario = Scenario("s", "t", ("n:c",), (SeedTerm("child", "content"),))

        sample = self.run_sample(scenario)

        self.assertEqual(
            _actions(sample),
            [
                ("A", "read", "r:doc"),
                ("A", "search", "q:root"),
                ("B", "search", "q:child"),
                ("B", "read", "r:b"),
                ("B", "read", "r:c"),
            ],
        )
        self.assertEqual(sample.cost.read_tool_calls, 2)
        self.assertEqual(sample.observations.duplicate_suppressed_queries, 1)

    def test_zero_result_query_is_counted_and_exposes_nothing(self):
        scenario = Scenario("s", "t", ("n:d",), (SeedTerm("alpha", "content"),))

        sample = self.run_sample(scenario)

        empty = next(step for step in sample.sequence if step.id == "q:empty")
        self.assertEqual(
            empty.cost_delta,
            {"exploration_turns": 1, "search_tool_calls": 1, "zero_result_queries": 1},
        )
        self.assertEqual(sample.cost.zero_result_queries, 1)

    def test_unreachable_target_reports_status_without_a_penalty(self):
        scenario = Scenario("s", "t", ("n:d",), (SeedTerm("alpha", "content"),))

        sample = self.run_sample(scenario)

        self.assertEqual(sample.status, "unreachable")
        self.assertEqual(sample.unreached_targets, ("n:d",))
        self.assertEqual(
            sample.cost.values(),
            {
                "exploration_turns": 4,
                "search_tool_calls": 4,
                "read_tool_calls": 3,
                "query_result_tokens": 35,
                "readable_node_tokens": 230,
                "zero_result_queries": 1,
                "revisits": 0,
                "exposed_non_target_candidates": 5,
                "duplicate_occurrences": 1,
            },
        )

    def test_already_executed_query_is_requeued_at_zero_cost(self):
        scenario = Scenario("s", "t", ("n:d",), (SeedTerm("alpha", "content"),))

        sample = self.run_sample(scenario)

        self.assertEqual(sample.observations.duplicate_suppressed_queries, 1)
        self.assertEqual([step.id for step in sample.sequence].count("q:seed"), 1)

    def test_duplicate_occurrences_charge_the_hidden_visible_matches(self):
        scenario = Scenario("s", "t", ("n:a1", "n:a2"), (SeedTerm("alpha", "content"),))

        sample = self.run_sample(scenario, seed=1)

        step = next(item for item in sample.sequence if item.id == "q:seed")
        self.assertEqual(step.cost_delta["duplicate_occurrences"], 1)
        self.assertEqual(step.cost_delta["exposed_non_target_candidates"], 1)

    def test_unread_hinted_and_unread_target_observations(self):
        scenario = Scenario("s", "t", ("n:a1", "n:a2"), (SeedTerm("alpha", "content"),))

        sample = self.run_sample(scenario, seed=1)

        self.assertEqual(sample.observations.hinted_unread_nodes, 1)
        self.assertEqual(sample.observations.unread_targets, [])

    def test_unread_target_is_reported_when_it_was_exposed_but_not_read(self):
        view = GraphView(
            build_graph(
                root_arrivals=("n:b", "n:d"),
                role_overrides={
                    ("q:root", "n:b"): ["comment"],
                    ("q:root", "n:d"): ["comment"],
                },
            )
        )
        scenario = Scenario("s", "t", ("n:d",), (SeedTerm("alpha", "content"),))

        sample = run_sample(
            view, scenario, _policy(phase_b_policy="best-first-pivot"), self.weights,
            random.Random(1), 0, 1,
        )

        self.assertEqual(sample.status, "unreachable")
        self.assertEqual(sample.unreached_targets, ("n:d",))
        self.assertEqual(sample.observations.unread_targets, ["n:d"])

    def test_id_sequence_records_read_units_in_read_order(self):
        scenario = Scenario("s", "t", ("n:a1", "n:a2"), (SeedTerm("alpha", "content"),))

        sample = self.run_sample(scenario, seed=0)

        self.assertEqual(
            sample.id_sequence,
            ("docs.md#Doc", "b.py#B", "pkg/nested/c.py#C", "a.py#A1,A2"),
        )

    def test_uniform_ordering_consumes_the_injected_rng(self):
        scenario = Scenario("s", "t", ("n:a1", "n:a2"), (SeedTerm("alpha", "content"),))
        policy = _policy(result_ordering="uniform")

        first = run_sample(self.view, scenario, policy, self.weights, random.Random(0), 0, 0)
        again = run_sample(self.view, scenario, policy, self.weights, random.Random(0), 0, 0)
        other = run_sample(self.view, scenario, policy, self.weights, random.Random(1), 1, 1)

        self.assertEqual(first.id_sequence, again.id_sequence)
        self.assertNotEqual(first.id_sequence, other.id_sequence)

    def test_best_first_pivot_breaks_score_ties_on_the_lower_query_id(self):
        view = GraphView(
            build_graph(
                extra_queries=(
                    ("q:aaa", "aaa", "exact", "content", "repository", ["n:d"], 1, 1, 4),
                    ("q:zzz", "zzz", "exact", "content", "repository", ["n:d"], 1, 1, 4),
                )
            )
        )
        policy = _policy(phase_b_policy="best-first-pivot")

        self.assertEqual(
            view.query_score("q:aaa", policy), view.query_score("q:zzz", policy)
        )
        self.assertEqual(
            _select(view, policy, {"q:zzz", "q:aaa"}, random.Random(0)), "q:aaa"
        )

    def test_best_first_pivot_leaves_the_rest_of_a_group_unread(self):
        view = GraphView(
            build_graph(
                root_arrivals=("n:b", "n:c"),
                role_overrides={
                    ("q:root", "n:b"): ["comment"],
                    ("q:root", "n:c"): ["comment"],
                },
            )
        )
        scenario = Scenario("s", "t", ("n:a1",), (SeedTerm("alpha", "content"),))

        pivot = run_sample(
            view, scenario, _policy(phase_b_policy="best-first-pivot"), self.weights,
            random.Random(3), 0, 3,
        )
        exhaust = run_sample(view, scenario, _policy(), self.weights, random.Random(3), 0, 3)

        self.assertEqual(
            _actions(pivot),
            [
                ("A", "read", "r:doc"),
                ("A", "search", "q:root"),
                ("B", "search", "q:seed"),
                ("B", "read", "r:b"),
                ("B", "read", "r:a"),
            ],
        )
        self.assertIn(("B", "read", "r:c"), _actions(exhaust))
        self.assertEqual(exhaust.cost.read_tool_calls, 3)
        self.assertEqual(pivot.observations.hinted_unread_nodes, 1)

    def test_repo_map_entries_count_as_hints_when_never_read(self):
        scenario = Scenario("s", "t", ("n:doc",), ())

        without = self.run_sample(scenario, policy=_policy(root_list_query=False))
        with_map = self.run_sample(
            scenario, policy=_policy(root_list_query=False, repo_map_enabled=True)
        )

        self.assertEqual(without.observations.hinted_unread_nodes, 0)
        self.assertEqual(with_map.observations.hinted_unread_nodes, 5)
        self.assertEqual(with_map.cost.read_tool_calls, 0)

    def test_execution_step_numbers_increment_across_the_whole_sample(self):
        scenario = Scenario("s", "t", ("n:a1", "n:a2"), (SeedTerm("alpha", "content"),))

        sample = self.run_sample(scenario, seed=0)

        self.assertGreater(len(sample.sequence), 3)
        self.assertEqual(
            [step.step for step in sample.sequence], list(range(len(sample.sequence)))
        )

    def test_matched_seed_queries_execute_in_surface_then_term_order(self):
        view = GraphView(
            build_graph(
                extra_queries=(
                    ("q:alphapath", "alpha", "exact", "path", "repository", ["n:d"], 1, 1, 4),
                )
            )
        )
        scenario = Scenario(
            "s", "t", ("n:a1",),
            (SeedTerm("alpha", "path"), SeedTerm("alpha", "content")),
        )

        sample = run_sample(view, scenario, _policy(root_list_query=False), self.weights, random.Random(0), 0, 0)

        searches = [step.id for step in sample.sequence if step.action == "search"]
        self.assertEqual(searches[:2], ["q:seed", "q:alphapath"])

    def test_a_sample_is_reproducible_from_its_seed(self):
        scenario = Scenario("s", "t", ("n:a1", "n:a2"), (SeedTerm("alpha", "content"),))

        first = self.run_sample(scenario, seed=11)
        again = self.run_sample(scenario, seed=11)

        self.assertEqual(first.cost, again.cost)
        self.assertEqual(first.sequence, again.sequence)


if __name__ == "__main__":
    unittest.main()
