import dataclasses
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from discovery.graph_view import GraphView
from discovery.models import Scenario, ScenarioError, SeedQueryError, SeedTerm
from discovery.policy import default_policy_path, load_exploration_policy
from discovery.scenario import load_scenarios
from discovery.seed_query import (
    CachedSeedQueryGenerator,
    ExplicitSeedQueries,
    resolve_seed_queries,
)
from tests.discovery_graph_fixture import build_graph

ROOT = Path(__file__).resolve().parents[1]


def _scenarios_file(directory, scenarios, schema="scenarios.v1"):
    path = Path(directory) / "scenarios.json"
    path.write_text(
        json.dumps({"schema": schema, "scenarios": scenarios}), encoding="utf-8"
    )
    return path


class GraphViewTests(unittest.TestCase):
    def setUp(self):
        self.view = GraphView(build_graph())
        self.policy = load_exploration_policy(default_policy_path())

    def test_precomputed_containers_are_sorted_and_resolved(self):
        self.assertEqual(self.view.root_list_query_id, "q:root")
        self.assertEqual(self.view.unit_of_node["n:a2"], "r:a")
        self.assertEqual(self.view.nodes_in_unit["r:a"], ("n:a1", "n:a2"))
        self.assertEqual(self.view.queries_from_unit["r:b"], ("q:child",))
        self.assertEqual(self.view.queries_from_unit["r:a"], ("q:seed",))
        self.assertEqual(self.view.queries_from_query["q:child"], ("q:empty",))
        self.assertEqual(self.view.arrivals["q:seed"], ("n:a1", "n:c"))
        self.assertEqual(self.view.static_out["n:a1"], ("n:b",))
        self.assertNotIn("n:a1", self.view.direct_out)
        self.assertEqual(self.view.query_by_term[("alpha", "content")], "q:seed")
        self.assertEqual(self.view.unit_tokens("r:a"), 100)
        self.assertEqual(self.view.unit_label("r:a"), "a.py#A1,A2")

    def test_hint_roles_resolve_through_the_hint_store(self):
        self.assertEqual(self.view.hint_of[("q:seed", "n:a1")]["roles"], ["declaration"])

    def test_direct_out_keeps_only_unique_static_connections(self):
        view = GraphView(
            build_graph(
                extra_edges=(
                    ("n:doc", "n:b", "static", "unique"),
                    ("n:doc", "n:c", "static", "narrowing"),
                )
            )
        )

        self.assertEqual(view.direct_out["n:doc"], ("n:b",))

    def test_hint_score_sums_role_weights_and_clamps_unknown_nodes(self):
        self.assertEqual(self.view.hint_score("q:seed", "n:a1", self.policy), 3.0)
        self.assertEqual(self.view.hint_score("q:seed", "n:c", self.policy), 1.0)
        self.assertEqual(self.view.hint_score("q:seed", "n:d", self.policy), 1e-9)

    def test_roles_absent_from_the_weight_table_contribute_nothing(self):
        view = GraphView(build_graph(role_overrides={("q:seed", "n:a1"): ["declaration", "unlisted"]}))

        self.assertEqual(view.hint_score("q:seed", "n:a1", self.policy), 3.0)

    def test_queries_from_query_unions_hint_query_and_refines_sorted_and_deduplicated(self):
        view = GraphView(
            build_graph(
                extra_edges=(
                    ("q:child", "q:empty", "refines"),
                    ("q:child", "q:seed", "refines"),
                    ("q:child", "q:seed", "hint_query"),
                    ("q:child", "q:root", "hint_query"),
                )
            )
        )

        self.assertEqual(
            view.queries_from_query["q:child"], ("q:empty", "q:root", "q:seed")
        )

    def test_root_list_query_id_is_none_without_a_root_scoped_list_query(self):
        view = GraphView(build_graph(query_overrides={"q:root": {"scope": "repository"}}))

        self.assertIsNone(view.root_list_query_id)

    def test_a_list_query_outside_root_scope_is_not_the_root_list_query(self):
        view = GraphView(
            build_graph(
                extra_queries=(
                    ("q:list2", "sub", "list", "path", "subtree", ["n:d"], 1, 1, 3),
                )
            )
        )

        self.assertEqual(view.root_list_query_id, "q:root")

    def test_query_by_term_is_keyed_on_term_and_surface_together(self):
        view = GraphView(
            build_graph(
                extra_queries=(
                    ("q:alphapath", "alpha", "exact", "path", "repository", ["n:d"], 1, 1, 4),
                )
            )
        )

        self.assertEqual(view.query_by_term[("alpha", "content")], "q:seed")
        self.assertEqual(view.query_by_term[("alpha", "path")], "q:alphapath")

    def test_zero_weight_roles_still_draw_above_zero(self):
        policy = dataclasses.replace(self.policy, role_weights={"declaration": 0.0}, filename_exact_bonus=0.0)

        self.assertGreater(self.view.hint_score("q:seed", "n:a1", policy), 0.0)

    def test_filename_stem_match_adds_the_bonus(self):
        view = GraphView(build_graph(query_overrides={"q:child": {"term": "c"}}))

        self.assertEqual(view.hint_score("q:child", "n:c", self.policy), 3.0 + 2.0)

    def test_the_bonus_needs_the_stem_not_the_basename_or_the_full_path(self):
        for term in ("c.py", "pkg/nested/c.py", "nested"):
            with self.subTest(term=term):
                view = GraphView(build_graph(query_overrides={"q:child": {"term": term}}))

                self.assertEqual(view.hint_score("q:child", "n:c", self.policy), 3.0)


class ScenarioLoaderTests(unittest.TestCase):
    def setUp(self):
        self.view = GraphView(build_graph())

    def test_symbol_target_resolves_to_one_node(self):
        with TemporaryDirectory() as directory:
            path = _scenarios_file(
                directory,
                [{"id": "s", "task": "t", "targets": ["a.py#A2"]}],
            )
            scenarios = load_scenarios(path, self.view)

        self.assertEqual(scenarios[0].target_node_ids, ("n:a2",))
        self.assertEqual(scenarios[0].seed_terms, ())

    def test_path_target_expands_to_one_representative_per_read_unit(self):
        with TemporaryDirectory() as directory:
            path = _scenarios_file(
                directory, [{"id": "s", "task": "t", "targets": ["a.py"]}]
            )
            scenarios = load_scenarios(path, self.view)

        self.assertEqual(scenarios[0].target_node_ids, ("n:a1",))

    def test_path_target_expands_to_every_read_unit_of_the_file(self):
        graph = build_graph()
        unit = next(item for item in graph.read_units if item.id == "r:a")
        graph = dataclasses.replace(
            graph,
            read_units=list(graph.read_units) + [dataclasses.replace(unit, id="r:a2")],
            readable_nodes=[
                dataclasses.replace(item, read_unit_id="r:a2") if item.id == "n:a2" else item
                for item in graph.readable_nodes
            ],
        )
        view = GraphView(graph)
        with TemporaryDirectory() as directory:
            path = _scenarios_file(directory, [{"id": "s", "task": "t", "targets": ["a.py"]}])
            scenarios = load_scenarios(path, view)

        self.assertEqual(scenarios[0].target_node_ids, ("n:a1", "n:a2"))

    def test_path_target_prefers_the_whole_file_node(self):
        with TemporaryDirectory() as directory:
            path = _scenarios_file(
                directory, [{"id": "s", "task": "t", "targets": ["docs.md"]}]
            )
            scenarios = load_scenarios(path, self.view)

        self.assertEqual(scenarios[0].target_node_ids, ("n:doc",))

    def test_explicit_seed_queries_are_read_from_the_file(self):
        with TemporaryDirectory() as directory:
            path = _scenarios_file(
                directory,
                [
                    {
                        "id": "s",
                        "task": "t",
                        "targets": ["a.py#A1"],
                        "seed_queries": [{"term": "alpha", "surface": "content"}],
                    }
                ],
            )
            scenarios = load_scenarios(path, self.view)

        self.assertEqual(scenarios[0].seed_terms, (SeedTerm("alpha", "content"),))

    def test_unresolvable_target_raises(self):
        cases = ["a.py#Missing", "missing.py", "missing.py#A1"]
        for target in cases:
            with self.subTest(target=target):
                with TemporaryDirectory() as directory:
                    path = _scenarios_file(
                        directory, [{"id": "s", "task": "t", "targets": [target]}]
                    )
                    with self.assertRaises(ScenarioError):
                        load_scenarios(path, self.view)

    def test_ambiguous_symbol_target_raises_naming_path_and_symbol(self):
        graph = build_graph()
        graph = dataclasses.replace(
            graph,
            readable_nodes=[
                dataclasses.replace(item, label="A1") if item.id == "n:a2" else item
                for item in graph.readable_nodes
            ],
        )
        view = GraphView(graph)
        with TemporaryDirectory() as directory:
            path = _scenarios_file(directory, [{"id": "s", "task": "t", "targets": ["a.py#A1"]}])
            with self.assertRaises(ScenarioError) as raised:
                load_scenarios(path, view)
        self.assertIn("a.py", str(raised.exception))
        self.assertIn("A1", str(raised.exception))

    def test_empty_target_list_raises(self):
        with TemporaryDirectory() as directory:
            path = _scenarios_file(directory, [{"id": "s", "task": "t", "targets": []}])
            with self.assertRaises(ScenarioError):
                load_scenarios(path, self.view)

    def test_duplicate_id_and_bad_schema_raise(self):
        with TemporaryDirectory() as directory:
            duplicate = _scenarios_file(
                directory,
                [
                    {"id": "s", "task": "t", "targets": ["a.py#A1"]},
                    {"id": "s", "task": "t", "targets": ["a.py#A2"]},
                ],
            )
            with self.assertRaises(ScenarioError):
                load_scenarios(duplicate, self.view)

            wrong = _scenarios_file(
                directory, [{"id": "s", "task": "t", "targets": ["a.py#A1"]}], schema="scenarios.v2"
            )
            with self.assertRaises(ScenarioError):
                load_scenarios(wrong, self.view)

            missing = Path(directory) / "missing_schema.json"
            missing.write_text(json.dumps({"scenarios": []}), encoding="utf-8")
            with self.assertRaises(ScenarioError):
                load_scenarios(missing, self.view)

            not_a_list = Path(directory) / "not_a_list.json"
            not_a_list.write_text(
                json.dumps({"schema": "scenarios.v1", "scenarios": {}}), encoding="utf-8"
            )
            with self.assertRaises(ScenarioError):
                load_scenarios(not_a_list, self.view)

    def test_scenario_order_is_preserved(self):
        with TemporaryDirectory() as directory:
            path = _scenarios_file(
                directory,
                [
                    {"id": "second", "task": "t", "targets": ["a.py#A1"]},
                    {"id": "first", "task": "t2", "targets": ["a.py#A2"]},
                ],
            )
            scenarios = load_scenarios(path, self.view)

        self.assertEqual([item.id for item in scenarios], ["second", "first"])


if __name__ == "__main__":
    unittest.main()
