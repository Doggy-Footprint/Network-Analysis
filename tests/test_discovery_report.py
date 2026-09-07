import dataclasses
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from agent_view.profile import default_profile_path, load_profile
from discovery.graph_view import GraphView
from discovery.scenario import load_scenarios
from discovery.seed_query import CachedSeedQueryGenerator, resolve_seed_queries
from discovery.simulate import run_phase_a
from discovery.models import AXES, Scenario, SeedQuerySet, SeedTerm
from discovery.montecarlo import rank_index, run_scenario
from discovery.policy import default_policy_path, load_exploration_policy
from discovery.report import build_report, report_to_json
from discovery.weights import default_weights_path, load_cost_weights
from tests.discovery_graph_fixture import build_graph

SCENARIO = Scenario("s", "t", ("n:a1", "n:a2"), (SeedTerm("alpha", "content"),))
SEED_SET = SeedQuerySet(
    source="cache",
    terms=(SeedTerm("alpha", "content"),),
    generator={
        "model_id": "hand-written",
        "revision": "1",
        "backend": "none",
        "prompt_id": "seed-terms-v1",
        "prompt": "prompt",
        "decoding": {"strategy": "greedy"},
        "fixture_sha256": "b" * 64,
        "raw_output": "content:alpha",
    },
)
EXPECTED_VERSION_IDS = [
    "cost_weights", "derived_rules", "exclusions", "ordering", "output_format",
    "phase_b_schema", "policy", "query_equivalence", "seed_query_generator",
    "split", "tie_break", "tokenizer",
]


def _reference_payload():
    graph = build_graph()
    view = GraphView(graph)
    policy = dataclasses.replace(
        load_exploration_policy(default_policy_path()),
        repo_map_enabled=False,
        bootstrap_resamples=20,
    )
    weights = load_cost_weights(default_weights_path())
    result = run_scenario(view, SCENARIO, policy, weights, samples=8, seed=5)
    payload = build_report(
        graph, view, [result], load_profile(default_profile_path()),
        policy, weights, {"s": SEED_SET},
    )
    return report_to_json(payload)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_graph()
        self.view = GraphView(self.graph)
        self.profile = load_profile(default_profile_path())
        self.policy = dataclasses.replace(
            load_exploration_policy(default_policy_path()),
            repo_map_enabled=False,
            bootstrap_resamples=20,
        )
        self.weights = load_cost_weights(default_weights_path())
        self.result = run_scenario(
            self.view, SCENARIO, self.policy, self.weights, samples=8, seed=5
        )
        self.payload = build_report(
            self.graph, self.view, [self.result], self.profile,
            self.policy, self.weights, {"s": SEED_SET},
        )

    def test_top_level_shape(self):
        self.assertEqual(self.payload["schema"], "phase_b_cost.v1")
        self.assertEqual(self.payload["project_name"], "discovery-fixture")
        self.assertEqual(self.payload["snapshot_digest"], "fixture-digest")
        self.assertEqual(
            sorted(self.payload["profiles"]),
            ["agent_view", "cost_weights", "exploration_policy"],
        )
        self.assertEqual(
            self.payload["profiles"]["cost_weights"],
            {"id": "cost_weights.v1", "version": 1, "content_hash": self.weights.ref.content_hash},
        )

    def test_versions_is_a_flat_sorted_list_of_id_version_pairs(self):
        versions = self.payload["versions"]

        self.assertEqual([item["id"] for item in versions], EXPECTED_VERSION_IDS)
        for item in versions:
            self.assertEqual(sorted(item), ["id", "version"])
            self.assertIsInstance(item["version"], str)

    def test_version_values_come_from_the_profiles_that_were_consumed(self):
        versions = {item["id"]: item["version"] for item in self.payload["versions"]}

        self.assertEqual(versions["cost_weights"], "cost_weights.v1:1")
        self.assertEqual(versions["policy"], "exploration_policy.v1:1")
        self.assertEqual(versions["derived_rules"], f"{self.profile.ref.id}:3")
        self.assertEqual(versions["exclusions"], f"{self.profile.ref.id}:3")
        self.assertEqual(versions["split"], self.profile.split_version)
        self.assertEqual(versions["ordering"], self.profile.ordering_version)
        self.assertEqual(versions["output_format"], self.profile.output_format_version)
        self.assertEqual(versions["query_equivalence"], self.profile.query_equivalence_version)
        self.assertEqual(versions["tokenizer"], self.profile.tokenizer_version)
        self.assertEqual(versions["tie_break"], "axis-lex-seqlen-idseq-v1")
        self.assertEqual(versions["phase_b_schema"], "1")
        self.assertEqual(versions["seed_query_generator"], "hand-written:1")

    def test_scenario_payload_carries_targets_seeds_and_phase_a(self):
        scenario = self.payload["scenarios"][0]

        self.assertEqual(scenario["id"], "s")
        self.assertEqual(
            scenario["targets"][0],
            {"node_id": "n:a1", "file_path": "a.py", "label": "A1", "read_unit_id": "r:a"},
        )
        self.assertEqual(scenario["seed_queries"]["source"], "cache")
        self.assertEqual(scenario["seed_queries"]["generator"], SEED_SET.generator)
        self.assertEqual(scenario["seed_queries"]["resolved_query_ids"], ["q:seed"])
        self.assertEqual(scenario["seed_queries"]["unmatched_terms"], [])
        self.assertEqual(scenario["phase_a"]["root_list_query_id"], "q:root")
        self.assertEqual(scenario["phase_a"]["repo_map_entry_count"], 0)
        self.assertEqual(
            scenario["phase_a"]["entry_documents"],
            [{"node_id": "n:doc", "file_path": "docs.md", "injected": True}],
        )
        self.assertEqual(set(scenario["phase_a"]["axes"]), set(AXES))

    def test_run_metadata_is_reported(self):
        scenario = self.payload["scenarios"][0]

        self.assertEqual(scenario["percentile_method"], "nearest-rank")
        self.assertEqual(scenario["sample_count"], 8)
        self.assertIsNone(scenario["converged"])
        self.assertEqual(scenario["seed"], 5)

    def test_percentile_rank_and_weighted_cost_match_the_ranked_samples(self):
        scenario = self.payload["scenarios"][0]
        ranked = self.result.ranked

        for name, fraction in (("p5", 0.05), ("p50", 0.5), ("p95", 0.95)):
            with self.subTest(name=name):
                entry = scenario["percentiles"][name]
                expected = rank_index(fraction, len(ranked))
                self.assertEqual(entry["rank"], expected)
                self.assertEqual(
                    entry["weighted_cost"], self.weights.weighted_cost(ranked[expected].cost)
                )
                self.assertEqual(entry["axes"], ranked[expected].cost.values())

        self.assertEqual(scenario["percentiles"]["p5"]["rank"], 0)
        self.assertEqual(scenario["percentiles"]["p50"]["rank"], 3)
        self.assertEqual(scenario["percentiles"]["p95"]["rank"], 7)

    def test_each_percentile_carries_its_own_ranked_samples_sequence(self):
        scenario = self.payload["scenarios"][0]
        ranked = self.result.ranked

        for name in ("p5", "p50", "p95"):
            with self.subTest(name=name):
                entry = scenario["percentiles"][name]
                sample = ranked[entry["rank"]]
                self.assertEqual(
                    [step["id"] for step in entry["execution_sequence"]],
                    [step.id for step in sample.sequence],
                )
                self.assertEqual(
                    entry["observations"]["discovery_turn_index"],
                    dict(sample.observations.discovery_turn_index),
                )

    def test_only_the_three_percentiles_carry_an_execution_sequence(self):
        scenario = self.payload["scenarios"][0]

        self.assertEqual(sorted(scenario["percentiles"]), ["p5", "p50", "p95"])
        for name in ("p5", "p50", "p95"):
            entry = scenario["percentiles"][name]
            self.assertEqual(set(entry["axes"]), set(AXES))
            self.assertTrue(entry["execution_sequence"])
            self.assertEqual(
                sorted(entry["execution_sequence"][0]),
                ["action", "cost_delta", "id", "phase", "step", "turn"],
            )
            self.assertEqual(sorted(entry["observations"]), [
                "discovery_turn_index", "duplicate_suppressed_queries",
                "hinted_unread_nodes", "unread_targets",
            ])

    def test_closure_and_invariants_are_reported(self):
        scenario = self.payload["scenarios"][0]

        self.assertEqual(set(scenario["closure"]["axes"]), set(AXES))
        self.assertEqual(scenario["closure"]["query_count"], 4)
        self.assertEqual(scenario["closure"]["read_unit_count"], 4)
        self.assertTrue(scenario["invariants"]["weighted_monotone"])
        self.assertTrue(scenario["invariants"]["axis_within_closure"])
        self.assertEqual(scenario["invariants"]["violations"], [])
        self.assertEqual(scenario["reachability"]["status"], "complete")
        self.assertEqual(scenario["reachability"]["incomplete_sample_count"], 0)

    def test_axis_statistics_cover_every_axis_with_mean_and_stdev(self):
        statistics = self.payload["scenarios"][0]["axis_statistics"]

        self.assertEqual(set(statistics), set(AXES))
        for axis in AXES:
            self.assertEqual(sorted(statistics[axis]), ["mean", "stdev"])

    def test_json_is_sorted_compact_and_newline_terminated(self):
        text = report_to_json(self.payload)

        self.assertTrue(text.endswith("\n"))
        self.assertNotIn(", ", text)
        self.assertEqual(json.loads(text), self.payload)
        self.assertEqual(text, json.dumps(json.loads(text), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")

    def test_report_bytes_do_not_depend_on_the_process_hash_seed(self):
        # compute_closure and reachable_sets build Python sets, whose iteration order varies
        # with PYTHONHASHSEED, so this can only surface across processes.
        root = Path(__file__).resolve().parents[1]
        driver = (
            "import json,sys;"
            f"sys.path.insert(0, {json.dumps(str(root))});"
            "from tests.test_discovery_report import _reference_payload;"
            "sys.stdout.write(_reference_payload())"
        )
        outputs = []
        for hash_seed in ("0", "1", "12345"):
            environment = dict(os.environ, PYTHONHASHSEED=hash_seed)
            result = subprocess.run(
                [sys.executable, "-c", driver],
                capture_output=True, text=True, check=True, env=environment, cwd=str(root),
            )
            outputs.append(result.stdout)

        self.assertEqual(len(set(outputs)), 1)
        self.assertEqual(json.loads(outputs[0])["schema"], "phase_b_cost.v1")

    def test_report_is_byte_identical_for_the_same_seed(self):
        again = run_scenario(self.view, SCENARIO, self.policy, self.weights, samples=8, seed=5)
        payload = build_report(
            self.graph, self.view, [again], self.profile,
            self.policy, self.weights, {"s": SEED_SET},
        )

        self.assertEqual(report_to_json(payload), report_to_json(self.payload))


class ProducedReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from framework_analyzers.fastapi.analyzer import FastAPIAnalyzer
        from framework_analyzers.fastapi.graph import ArchitectureGraphBuilder
        from agent_view import build_agent_view

        cls.root = Path(__file__).resolve().parents[1]
        architecture = FastAPIAnalyzer(str(cls.root / "examples" / "realworld_app")).analyze()
        architecture = ArchitectureGraphBuilder().build_graph(architecture)
        cls.graph = build_agent_view(architecture, profile=load_profile(default_profile_path()))
        cls.view = GraphView(cls.graph)

    def test_every_committed_scenario_target_resolves_against_the_example_repository(self):
        scenarios = load_scenarios(self.root / "fixtures" / "scenarios.v1.json", self.view)

        self.assertEqual(len(scenarios), 3)
        self.assertTrue(any(len(item.target_node_ids) >= 2 for item in scenarios))
        self.assertTrue(any(item.seed_terms for item in scenarios))
        self.assertTrue(any(not item.seed_terms for item in scenarios))
        for scenario in scenarios:
            with self.subTest(scenario=scenario.id):
                self.assertTrue(scenario.target_node_ids)
                for node_id in scenario.target_node_ids:
                    self.assertIn(node_id, self.view.readable)

    def test_committed_seed_terms_are_not_all_zero_result_queries(self):
        cached = CachedSeedQueryGenerator.from_path(
            self.root / "fixtures" / "seed_queries.v1.json"
        )
        policy = load_exploration_policy(default_policy_path())

        for scenario in load_scenarios(self.root / "fixtures" / "scenarios.v1.json", self.view):
            with self.subTest(scenario=scenario.id):
                resolved, seed_set = resolve_seed_queries(scenario, cached)
                phase_a = run_phase_a(self.view, resolved, policy)

                self.assertTrue(seed_set.terms)
                self.assertTrue(
                    phase_a.seed_query_ids,
                    f"every seed term of {scenario.id} degenerated to a zero-result query",
                )


if __name__ == "__main__":
    unittest.main()
