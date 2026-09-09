import copy
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from bottlenecks import (EvaluationCaseError, EvaluationComparisonError,
    EvaluationRunError, HarnessSupportError, compare_runs, evaluate_run,
    evaluation_to_json, parse_evaluation_case, parse_evaluation_run,
    parse_harness_profile, parse_harness_support)
from bottlenecks.evaluation import BURDEN_AXES, main

ROOT = Path(__file__).resolve().parents[1]
BASE_HASH = "08e10a27427fb0c2c27662c890c2d2f083dc74f2da8746b26ad15c4cd2adb66a"
ALT_HASH = "4a9edaa590d428ffaf79192934b546965306862ac220121734227f275523f33b"


def load(name): return json.loads((ROOT / name).read_text())
def profile_data(alternate=False):
    value = load("profiles/harness.fixed-baseline.v1.json")
    if alternate: value["read"]["max_lines"] = 1000
    return value
def binding(alternate=False): return {"id": "fixed-string-line-baseline", "version": 1, "content_hash": ALT_HASH if alternate else BASE_HASH}
def event(identifier, kind, status="completed", inputs=None, returned=None): return {"id": identifier, "kind": kind, "status": status, "inputs": {} if inputs is None else inputs, "returned": {} if returned is None else returned}
def fulfilled_events(): return [event("search", "search", "truncated", returned={"visible_count": 2, "rows": [{"path": "a.py", "start_line": 1, "end_line": 1}], "truncated": True}), event("confirm", "confirm", inputs={"confirmation_id": "boundary"}, returned={"status": "passed", "evidence": "a.py:1"}), event("outcome", "outcome", inputs={"outcome_id": "completed"}, returned={"status": "passed", "evidence": "changed"})]
def run_data(case, cell_id, trace_events, alternate=False, legacy=False):
    cell = next(cell for cell in case["comparison"]["cells"] if cell["id"] == cell_id)
    trace = {"schema": "agent_trace.v1", "events": [{"kind": "search", "paths": ["a.py"]}]} if legacy else {"schema": "harness_observation.v1", "id": "trace-" + cell_id, "snapshot_digest": cell["snapshot_digest"], "profile": binding(alternate), "events": trace_events}
    return {"schema": "harness_evaluation_run.v1", "id": "run-" + cell_id, "case_id": case["id"], "cell_id": cell_id, "environment": {"model_version": "m1", "harness_version": "h1"}, "trace": trace}


class HarnessEvaluationContractTests(unittest.TestCase):
    def setUp(self):
        self.profile = parse_harness_profile(profile_data())
        self.alternate = parse_harness_profile(profile_data(True))
        self.support = load("profiles/harness.fixed-baseline.support.v1.json")
        self.structure_raw = load("fixtures/harness-evaluation/independent-python-structure.v1.json")
    def parsed_run(self, raw, cell="structure-before", events=None, alternate=False):
        case = parse_evaluation_case(raw)
        return case, parse_evaluation_run(run_data(raw, cell, fulfilled_events() if events is None else events, alternate), case, self.alternate if alternate else self.profile)

    def test_fixture_cases_parse_for_structure_harness_and_interaction(self):
        for filename, count in (("independent-python-structure.v1.json", 2), ("independent-python-harness.v1.json", 2), ("independent-python-interaction.v1.json", 4)):
            self.assertEqual(len(parse_evaluation_case(load("fixtures/harness-evaluation/" + filename)).cells), count)

    def test_M2_E01_rejects_every_support_partition_without_partial_result(self):
        mutations = [lambda d: d.pop("language_scope"), lambda d: d.__setitem__("extra", 1), lambda d: d.__setitem__("language_scope", []), lambda d: d.__setitem__("language_scope", ["python", "python"]), lambda d: d["settings"].pop(), lambda d: d["settings"].append(copy.deepcopy(d["settings"][0])), lambda d: d["settings"].append({"pointer": "/unknown", "value": 1, "support": "replayed", "provenance": {"status": "unverified", "evidence": []}}), lambda d: d["settings"][0].__setitem__("pointer", "not-a-pointer"), lambda d: d["settings"][0].__setitem__("value", "wrong"), lambda d: d["settings"][0].__setitem__("support", "live"), lambda d: d["settings"][0].__setitem__("provenance", {"status": "sourced", "evidence": []}), lambda d: d["settings"][0].__setitem__("provenance", {"status": "wrong", "evidence": [1]})]
        for mutate in mutations:
            raw = copy.deepcopy(self.support); before = copy.deepcopy(raw); mutate(raw)
            serialized = json.dumps(raw, sort_keys=True)
            with self.assertRaises(HarnessSupportError): parse_harness_support(raw, self.profile)
            self.assertEqual(json.dumps(raw, sort_keys=True), serialized); self.assertNotEqual(raw, before)

    def test_support_nested_shapes_and_evidence_references(self):
        mutations = [
            lambda d: d["profile"].pop("id"),
            lambda d: d["profile"].__setitem__("extra", 1),
            lambda d: d["settings"][0].pop("support"),
            lambda d: d["settings"][0].__setitem__("extra", 1),
            lambda d: d["settings"][0]["provenance"].pop("status"),
            lambda d: d["settings"][0]["provenance"].__setitem__("extra", 1),
            lambda d: d.__setitem__("language_scope", [""]),
        ]
        for mutate in mutations:
            raw = copy.deepcopy(self.support); mutate(raw); serialized = json.dumps(raw, sort_keys=True)
            with self.assertRaises(HarnessSupportError): parse_harness_support(raw, self.profile)
            self.assertEqual(json.dumps(raw, sort_keys=True), serialized)
        for evidence in (["/absolute/path"], ["../escape"], ["dir/../escape"], ["file:///tmp/x"], ["ftp://example.test/x"]):
            raw = copy.deepcopy(self.support); raw["settings"][0]["provenance"] = {"status": "sourced", "evidence": evidence}
            serialized = json.dumps(raw, sort_keys=True)
            with self.assertRaises(HarnessSupportError): parse_harness_support(raw, self.profile)
            self.assertEqual(json.dumps(raw, sort_keys=True), serialized)
        for evidence in (["research/evidence.md"], ["https://example.test/evidence"]):
            raw = copy.deepcopy(self.support); raw["settings"][0]["provenance"] = {"status": "sourced", "evidence": evidence}
            parsed = parse_harness_support(raw, self.profile)
            setting = next(item for item in parsed.settings if item["pointer"] == "/provenance_status")
            self.assertEqual(setting["provenance"], {"status": "sourced", "evidence": evidence})

    def test_M2_E02_E03_support_binding_hash_and_replay_statuses(self):
        for key, value in (("id", "wrong"), ("version", 2), ("content_hash", "A" * 64), ("content_hash", "0" * 63)):
            raw = copy.deepcopy(self.support); raw["profile"][key] = value
            serialized = json.dumps(raw, sort_keys=True)
            with self.assertRaises(HarnessSupportError): parse_harness_support(raw, self.profile)
            self.assertEqual(json.dumps(raw, sort_keys=True), serialized)
        settings = {item["pointer"]: item for item in parse_harness_support(self.support, self.profile).settings}
        self.assertEqual(settings["/assumptions/list_depth"]["support"], "replayed")
        self.assertEqual(settings["/content_search/visible_lines"]["support"], "replayed")
        self.assertEqual(settings["/features/index"]["support"], "unsupported")
        self.assertEqual(settings["/provenance_status"]["provenance"], {"status": "unverified", "evidence": []})

    def test_M2_E04_case_wire_schema_partitions(self):
        mutations = [lambda d: d.pop("task"), lambda d: d.__setitem__("extra", 1), lambda d: d.__setitem__("id", ""), lambda d: d.__setitem__("confirmations", []), lambda d: d["confirmations"].append(copy.deepcopy(d["confirmations"][0])), lambda d: d["outcomes"][0].__setitem__("extra", 1), lambda d: d["comparison"].__setitem__("factor", "wrong"), lambda d: d["comparison"]["cells"][0].__setitem__("repository_variant", "bad"), lambda d: d["comparison"]["cells"].pop(), lambda d: d["comparison"]["cells"][1].__setitem__("snapshot_digest", "snapshot-before"), lambda d: d["comparison"]["cells"][1].__setitem__("profile", {**binding(), "content_hash": "0" * 64})]
        for mutate in mutations:
            raw = copy.deepcopy(self.structure_raw); mutate(raw)
            serialized = json.dumps(raw, sort_keys=True)
            with self.assertRaises(EvaluationCaseError): parse_evaluation_case(raw)
            self.assertEqual(json.dumps(raw, sort_keys=True), serialized)
        harness = load("fixtures/harness-evaluation/independent-python-harness.v1.json"); harness["comparison"]["cells"][1]["snapshot_digest"] = "other"
        with self.assertRaises(EvaluationCaseError): parse_evaluation_case(harness)
        interaction = load("fixtures/harness-evaluation/independent-python-interaction.v1.json"); interaction["comparison"]["cells"][3]["profile"] = binding()
        with self.assertRaises(EvaluationCaseError): parse_evaluation_case(interaction)

    def test_M2_E04_rejects_duplicate_outcomes_and_empty_requirement_ids(self):
        for path in (("confirmations", 0), ("outcomes", 0)):
            raw = copy.deepcopy(self.structure_raw); raw[path[0]][path[1]]["id"] = ""
            serialized = json.dumps(raw, sort_keys=True)
            with self.assertRaises(EvaluationCaseError): parse_evaluation_case(raw)
            self.assertEqual(json.dumps(raw, sort_keys=True), serialized)
        raw = copy.deepcopy(self.structure_raw); raw["outcomes"].append(copy.deepcopy(raw["outcomes"][0])); serialized = json.dumps(raw, sort_keys=True)
        with self.assertRaises(EvaluationCaseError): parse_evaluation_case(raw)
        self.assertEqual(json.dumps(raw, sort_keys=True), serialized)

    def test_M2_E05_run_wire_schema_and_binding_partitions(self):
        case = parse_evaluation_case(self.structure_raw)
        mutations = [lambda d: d.pop("trace"), lambda d: d.__setitem__("extra", 1), lambda d: d["environment"].__setitem__("model_version", ""), lambda d: d.__setitem__("case_id", "wrong"), lambda d: d.__setitem__("cell_id", "none"), lambda d: d["trace"].__setitem__("schema", "wrong"), lambda d: d["trace"].__setitem__("snapshot_digest", "wrong"), lambda d: d["trace"]["profile"].__setitem__("content_hash", "0" * 64)]
        for mutate in mutations:
            raw = run_data(self.structure_raw, "structure-before", fulfilled_events()); mutate(raw)
            serialized = json.dumps(raw, sort_keys=True)
            with self.assertRaises(EvaluationRunError): parse_evaluation_run(raw, case, self.profile)
            self.assertEqual(json.dumps(raw, sort_keys=True), serialized)
        with self.assertRaises(EvaluationRunError): parse_evaluation_run(run_data(self.structure_raw, "structure-before", fulfilled_events()), case, self.alternate)

    def test_case_and_run_nested_wire_schema_partitions(self):
        case_mutations = [
            lambda d: d["comparison"].pop("cells"),
            lambda d: d["comparison"].__setitem__("extra", 1),
            lambda d: d["comparison"]["cells"][0].pop("profile"),
            lambda d: d["comparison"]["cells"][0].__setitem__("extra", 1),
            lambda d: d["comparison"]["cells"][0].__setitem__("id", ""),
            lambda d: d["comparison"]["cells"][1].__setitem__("id", d["comparison"]["cells"][0]["id"]),
            lambda d: d["comparison"]["cells"][0].__setitem__("snapshot_digest", ""),
            lambda d: d["comparison"]["cells"][0]["profile"].pop("id"),
            lambda d: d["comparison"]["cells"][0]["profile"].__setitem__("extra", 1),
            lambda d: d.__setitem__("language", ""),
            lambda d: d.__setitem__("task", ""),
            lambda d: d.__setitem__("outcomes", []),
        ]
        for mutate in case_mutations:
            raw = copy.deepcopy(self.structure_raw); mutate(raw); serialized = json.dumps(raw, sort_keys=True)
            with self.assertRaises(EvaluationCaseError): parse_evaluation_case(raw)
            self.assertEqual(json.dumps(raw, sort_keys=True), serialized)
        case = parse_evaluation_case(self.structure_raw)
        run_mutations = [
            lambda d: d.__setitem__("id", ""),
            lambda d: d["environment"].pop("model_version"),
            lambda d: d["environment"].__setitem__("extra", 1),
            lambda d: d["environment"].__setitem__("harness_version", ""),
            lambda d: d["trace"].pop("events"),
            lambda d: d["trace"].__setitem__("extra", 1),
        ]
        for mutate in run_mutations:
            raw = run_data(self.structure_raw, "structure-before", fulfilled_events()); mutate(raw); serialized = json.dumps(raw, sort_keys=True)
            with self.assertRaises(EvaluationRunError): parse_evaluation_run(raw, case, self.profile)
            self.assertEqual(json.dumps(raw, sort_keys=True), serialized)

    def test_M2_E06_preserves_eof_truncated_and_known_return_quantities(self):
        source = fulfilled_events(); source.insert(1, event("read", "read", returned={"rows": [{"start_line": 7, "end_line": 9}], "ranges": None, "visible_count": None, "truncated": True})); source.insert(2, event("paths", "search", returned={"paths": ["x", "y"], "range": {"start_line": 10, "end_line": 10}}))
        case, run = self.parsed_run(self.structure_raw, events=source); result = evaluate_run(case, run)
        self.assertEqual({key: result.burden[key] for key in ("search_calls", "read_calls", "returned_items", "returned_lines")}, {"search_calls": 2, "read_calls": 1, "returned_items": 5, "returned_lines": 5})
        self.assertIsNone(run.trace.events[1]["returned"]["visible_count"]); self.assertTrue(run.trace.events[1]["returned"]["truncated"])

    def test_M2_E07_counts_duplicate_paths_ranges_text_and_null_free_identity(self):
        source = fulfilled_events(); repeated = event("read-one", "read", returned={"paths": ["p"], "ranges": [{"start_line": 3, "end_line": 4}], "text": "x", "visible_count": None}); repeated_again = copy.deepcopy(repeated); repeated_again["id"] = "read-two"; repeated_again["returned"] = {"text": "x", "ranges": [{"end_line": 4, "start_line": 3}], "paths": ["p"]}; empty = event("empty", "read", returned={"rows": [], "text": None}); empty_again = copy.deepcopy(empty); empty_again["id"] = "empty-again"; source[0:0] = [repeated, repeated_again, empty, empty_again]
        case, run = self.parsed_run(self.structure_raw, events=source); burden = evaluate_run(case, run).burden
        self.assertEqual((burden["returned_items"], burden["returned_lines"], burden["duplicated_exposure"]), (4, 5, 1))

    def test_M2_E07_counts_repeated_singular_range_by_lines_when_items_are_zero(self):
        source = fulfilled_events()
        first = event("range-one", "read", returned={"range": {"start_line": 20, "end_line": 22}})
        second = copy.deepcopy(first); second["id"] = "range-two"
        source[0:0] = [first, second]
        case, run = self.parsed_run(self.structure_raw, events=source)
        burden = evaluate_run(case, run).burden
        self.assertEqual((burden["returned_items"], burden["returned_lines"], burden["duplicated_exposure"]), (2, 7, 3))

    def test_M2_E08_retains_failed_unknown_and_stopped_event_burden(self):
        source = fulfilled_events(); source[0:0] = [event("failed-search", "search", "failed", returned={"visible_count": 1}), event("unknown-read", "read", "unknown", returned={"range": {"start_line": 1, "end_line": 2}}), event("stop", "preparation", "failed")]
        case, run = self.parsed_run(self.structure_raw, events=source); result = evaluate_run(case, run)
        self.assertEqual({key: result.burden[key] for key in ("total_calls", "search_calls", "read_calls", "preparation_calls", "failed_calls", "returned_items", "returned_lines")}, {"total_calls": 6, "search_calls": 2, "read_calls": 1, "preparation_calls": 1, "failed_calls": 3, "returned_items": 3, "returned_lines": 3})
        self.assertEqual(run.trace.events[0]["status"], "failed")

    def test_M2_E09_confirmation_statuses_and_order(self):
        raw = copy.deepcopy(self.structure_raw); raw["confirmations"] = [{"id": "z", "description": "z"}, {"id": "a", "description": "a"}]; case = parse_evaluation_case(raw); source = fulfilled_events(); source[1] = event("z2", "confirm", inputs={"confirmation_id": "z"}, returned={"status": "passed", "evidence": "x"}); source.insert(1, event("z1", "confirm", inputs={"confirmation_id": "z"}, returned={"status": "passed", "evidence": "x"})); result = evaluate_run(case, parse_evaluation_run(run_data(raw, "structure-before", source), case, self.profile))
        self.assertEqual(result.confirmations, ({"id": "a", "event_ids": [], "status": "missing"}, {"id": "z", "event_ids": ["z1", "z2"], "status": "duplicate"}))
        for returned, expected in (({"status": "failed", "evidence": "x"}, "failed"), ({"status": "passed", "evidence": ""}, "evidence_missing")):
            source = fulfilled_events(); source[1]["returned"] = returned; case, run = self.parsed_run(self.structure_raw, events=source); self.assertEqual(evaluate_run(case, run).confirmations[0]["status"], expected)

    def test_M2_E10_outcome_statuses_and_unknown_id_rejection(self):
        for returned, expected in (({"status": "failed", "evidence": "x"}, "failed"), ({"status": "passed", "evidence": ""}, "evidence_missing")):
            source = fulfilled_events(); source[2]["returned"] = returned; case, run = self.parsed_run(self.structure_raw, events=source); self.assertEqual(evaluate_run(case, run).outcomes[0]["status"], expected)
        source = fulfilled_events(); source[2]["inputs"] = {"outcome_id": "unknown"}; case = parse_evaluation_case(self.structure_raw)
        with self.assertRaises(EvaluationRunError): parse_evaluation_run(run_data(self.structure_raw, "structure-before", source), case, self.profile)

    def test_M2_E09_E10_rejects_unknown_confirmation_and_duplicate_passing_outcome(self):
        case = parse_evaluation_case(self.structure_raw)
        unknown = fulfilled_events(); unknown[1]["inputs"] = {"confirmation_id": "unknown"}
        with self.assertRaises(EvaluationRunError): parse_evaluation_run(run_data(self.structure_raw, "structure-before", unknown), case, self.profile)
        duplicate = fulfilled_events(); extra = copy.deepcopy(duplicate[2]); extra["id"] = "outcome-duplicate"; duplicate.append(extra)
        result = evaluate_run(case, parse_evaluation_run(run_data(self.structure_raw, "structure-before", duplicate), case, self.profile))
        self.assertEqual(result.outcomes, ({"id": "completed", "event_ids": ["outcome", "outcome-duplicate"], "status": "duplicate"},))
        self.assertFalse(result.eligible)

    def test_M2_E09_E10_event_failed_or_unknown_overrides_passing_returned_evidence(self):
        for index, row, expected in ((1, "confirmations", "failed"), (2, "outcomes", "failed")):
            for status in ("failed", "unknown"):
                source = fulfilled_events(); source[index]["status"] = status
                case, run = self.parsed_run(self.structure_raw, events=source)
                result = evaluate_run(case, run)
                self.assertEqual(getattr(result, row)[0]["status"], expected)
                self.assertFalse(result.eligible)

    def comparison(self, before_events, after_events):
        case = parse_evaluation_case(self.structure_raw); before = evaluate_run(case, parse_evaluation_run(run_data(self.structure_raw, "structure-before", before_events), case, self.profile)); after = evaluate_run(case, parse_evaluation_run(run_data(self.structure_raw, "structure-after", after_events), case, self.profile)); return compare_runs(case, before, after)
    def test_M2_E11_E14_full_deltas_and_pareto_states(self):
        before = fulfilled_events() + [event("prep", "preparation")]; improved = self.comparison(before, fulfilled_events())
        self.assertEqual(improved.status, "improved"); self.assertEqual(improved.burden_delta, {"total_calls": -1, "search_calls": 0, "read_calls": 0, "preparation_calls": -1, "failed_calls": 0, "returned_items": 0, "returned_lines": 0, "duplicated_exposure": 0}); self.assertEqual(set(improved.burden_delta), set(BURDEN_AXES))
        self.assertEqual(self.comparison(fulfilled_events(), fulfilled_events()).status, "unchanged"); self.assertEqual(self.comparison(fulfilled_events(), before).status, "regressed"); costly = fulfilled_events(); costly[0]["returned"]["visible_count"] = 5; self.assertEqual(self.comparison(costly, before).status, "mixed")

    def test_M2_E11_E14_each_requested_burden_axis_controls_pareto_status(self):
        case = parse_evaluation_case(self.structure_raw)
        before = evaluate_run(case, parse_evaluation_run(run_data(self.structure_raw, "structure-before", fulfilled_events()), case, self.profile))
        after = evaluate_run(case, parse_evaluation_run(run_data(self.structure_raw, "structure-after", fulfilled_events()), case, self.profile))
        zero = {axis: 0 for axis in BURDEN_AXES}
        for axis in ("search_calls", "read_calls", "failed_calls", "returned_lines", "duplicated_exposure"):
            higher = dict(zero); higher[axis] = 1
            self.assertEqual(compare_runs(case, replace(before, burden=higher), replace(after, burden=zero)).status, "improved")
            self.assertEqual(compare_runs(case, replace(before, burden=zero), replace(after, burden=higher)).status, "regressed")
            mixed_after = dict(zero); mixed_after[axis] = 1
            mixed_before = dict(zero); mixed_before["total_calls"] = 1
            self.assertEqual(compare_runs(case, replace(before, burden=mixed_before), replace(after, burden=mixed_after)).status, "mixed")
    def test_M2_E15_both_sides_ineligible_override_lower_cost(self):
        absent_confirmation = [event("outcome", "outcome", inputs={"outcome_id": "completed"}, returned={"status": "passed", "evidence": "x"})]; absent_outcome = [event("confirm", "confirm", inputs={"confirmation_id": "boundary"}, returned={"status": "passed", "evidence": "x"})]
        self.assertEqual(self.comparison(absent_confirmation, fulfilled_events()).status, "ineligible"); self.assertEqual(self.comparison(fulfilled_events() + [event("prep", "preparation")], absent_outcome).status, "ineligible")

    def test_M2_E16_valid_and_invalid_factor_edges(self):
        structure = parse_evaluation_case(self.structure_raw); b = evaluate_run(structure, parse_evaluation_run(run_data(self.structure_raw, "structure-before", fulfilled_events()), structure, self.profile)); a = evaluate_run(structure, parse_evaluation_run(run_data(self.structure_raw, "structure-after", fulfilled_events()), structure, self.profile)); self.assertEqual(compare_runs(structure, b, a).factor, "structure")
        raw = load("fixtures/harness-evaluation/independent-python-interaction.v1.json"); interaction = parse_evaluation_case(raw); bb = evaluate_run(interaction, parse_evaluation_run(run_data(raw, "before-before", fulfilled_events()), interaction, self.profile)); ba = evaluate_run(interaction, parse_evaluation_run(run_data(raw, "before-after", fulfilled_events(), True), interaction, self.alternate)); ab = evaluate_run(interaction, parse_evaluation_run(run_data(raw, "after-before", fulfilled_events()), interaction, self.profile)); aa = evaluate_run(interaction, parse_evaluation_run(run_data(raw, "after-after", fulfilled_events(), True), interaction, self.alternate))
        self.assertEqual(compare_runs(interaction, bb, ba).factor, "harness"); self.assertEqual(compare_runs(interaction, bb, ab).factor, "structure"); self.assertEqual(compare_runs(interaction, ba, aa).factor, "structure"); self.assertEqual(compare_runs(interaction, ab, aa).factor, "harness")
        for left, right in ((bb, bb), (bb, aa)):
            with self.assertRaises(EvaluationComparisonError): compare_runs(interaction, left, right)

    def test_M2_E17_canonical_order_and_mapping_seed_independence(self):
        case = parse_evaluation_case(self.structure_raw); first = evaluate_run(case, parse_evaluation_run(run_data(self.structure_raw, "structure-before", fulfilled_events()), case, self.profile)); raw = json.loads(json.dumps(self.structure_raw, sort_keys=True)); raw["comparison"]["cells"].reverse(); other = parse_evaluation_case(raw); second = evaluate_run(other, parse_evaluation_run(run_data(raw, "structure-before", list(reversed(fulfilled_events()))), other, self.profile)); self.assertEqual(evaluation_to_json(first), evaluation_to_json(second))

    def test_M2_E17_comparison_json_is_byte_identical_for_mapping_order(self):
        case = parse_evaluation_case(self.structure_raw)
        before = evaluate_run(case, parse_evaluation_run(run_data(self.structure_raw, "structure-before", fulfilled_events()), case, self.profile))
        after = evaluate_run(case, parse_evaluation_run(run_data(self.structure_raw, "structure-after", fulfilled_events()), case, self.profile))
        raw = json.loads(json.dumps(self.structure_raw, sort_keys=True)); raw["comparison"]["cells"].reverse()
        reordered_case = parse_evaluation_case(raw)
        reordered_before = evaluate_run(reordered_case, parse_evaluation_run(run_data(raw, "structure-before", list(reversed(fulfilled_events()))), reordered_case, self.profile))
        reordered_after = evaluate_run(reordered_case, parse_evaluation_run(run_data(raw, "structure-after", list(reversed(fulfilled_events()))), reordered_case, self.profile))
        self.assertEqual(evaluation_to_json(compare_runs(case, before, after)), evaluation_to_json(compare_runs(reordered_case, reordered_before, reordered_after)))

    def test_M2_E17_hash_seed_does_not_change_evaluation_or_comparison_bytes(self):
        code = """
import sys, types
yaml = types.ModuleType('yaml')
yaml.YAMLError = ValueError
sys.modules['yaml'] = yaml
from tests.test_harness_evaluation import load, profile_data, fulfilled_events, run_data
from bottlenecks import parse_harness_profile, parse_evaluation_case, parse_evaluation_run, evaluate_run, compare_runs, evaluation_to_json
profile = parse_harness_profile(profile_data())
raw = load('fixtures/harness-evaluation/independent-python-structure.v1.json')
case = parse_evaluation_case(raw)
before = evaluate_run(case, parse_evaluation_run(run_data(raw, 'structure-before', fulfilled_events()), case, profile))
after = evaluate_run(case, parse_evaluation_run(run_data(raw, 'structure-after', fulfilled_events()), case, profile))
sys.stdout.write(evaluation_to_json(before) + evaluation_to_json(compare_runs(case, before, after)))
"""
        outputs = []
        for seed in ("1", "777"):
            environment = dict(os.environ); environment["PYTHONHASHSEED"] = seed
            outputs.append(subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=environment, check=True, capture_output=True, text=True).stdout)
        self.assertEqual(outputs[0], outputs[1])
    def test_M2_E18_legacy_binding_retains_event_burden_and_envelope_metadata(self):
        case = parse_evaluation_case(self.structure_raw); result = evaluate_run(case, parse_evaluation_run(run_data(self.structure_raw, "structure-before", [], legacy=True), case, self.profile)); self.assertEqual((result.binding_status, result.case_id, result.cell_id, result.environment, result.burden["search_calls"], result.burden["returned_items"]), ("caller_supplied_unverified", "independent-python-structure", "structure-before", {"harness_version": "h1", "model_version": "m1"}, 1, 1))

    def test_cli_evaluate_compare_support_errors_and_argument_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory); paths = {name: directory / (name + ".json") for name in ("case", "run", "profile", "support", "out", "after")}; paths["case"].write_text(json.dumps(self.structure_raw)); paths["profile"].write_text(json.dumps(profile_data())); paths["support"].write_text(json.dumps(self.support)); paths["run"].write_text(json.dumps(run_data(self.structure_raw, "structure-before", fulfilled_events()))); paths["after"].write_text(json.dumps(run_data(self.structure_raw, "structure-after", fulfilled_events())))
            with patch("subprocess.run", side_effect=AssertionError("live subprocess")), patch("os.system", side_effect=AssertionError("live system")), patch("socket.create_connection", side_effect=AssertionError("live socket")):
                self.assertEqual(main(["evaluate", str(paths["case"]), str(paths["run"]), str(paths["profile"]), "-s", str(paths["support"]), "-o", str(paths["out"])]), 0)
            self.assertEqual(json.loads(paths["out"].read_text()), {"schema": "harness_run_evaluation.v1", "case_id": "independent-python-structure", "run_id": "run-structure-before", "cell_id": "structure-before", "binding_status": "declared", "environment": {"model_version": "m1", "harness_version": "h1"}, "burden": {"total_calls": 3, "search_calls": 1, "read_calls": 0, "preparation_calls": 0, "failed_calls": 0, "returned_items": 2, "returned_lines": 1, "duplicated_exposure": 0}, "confirmations": [{"id": "boundary", "event_ids": ["confirm"], "status": "fulfilled"}], "outcomes": [{"id": "completed", "event_ids": ["outcome"], "status": "fulfilled"}], "eligible": True})
            with patch("subprocess.run", side_effect=AssertionError("live subprocess")), patch("os.system", side_effect=AssertionError("live system")), patch("socket.create_connection", side_effect=AssertionError("live socket")):
                self.assertEqual(main(["compare", str(paths["case"]), str(paths["run"]), str(paths["profile"]), str(paths["after"]), str(paths["profile"]), "-o", str(paths["out"])]), 0)
            self.assertEqual(json.loads(paths["out"].read_text()), {"schema": "harness_run_comparison.v1", "case_id": "independent-python-structure", "factor": "structure", "before_run_id": "run-structure-before", "after_run_id": "run-structure-after", "burden_delta": {axis: 0 for axis in BURDEN_AXES}, "status": "unchanged"})
            paths["run"].write_text("[]"); stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as error: main(["evaluate", str(paths["case"]), str(paths["run"]), str(paths["profile"]), "-o", str(paths["out"])])
            self.assertEqual(error.exception.code, 1); self.assertNotIn("Traceback", stderr.getvalue())
            bad_support = copy.deepcopy(self.support); bad_support["profile"]["content_hash"] = "0" * 64; paths["support"].write_text(json.dumps(bad_support)); paths["run"].write_text(json.dumps(run_data(self.structure_raw, "structure-before", fulfilled_events()))); stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as error: main(["evaluate", str(paths["case"]), str(paths["run"]), str(paths["profile"]), "-s", str(paths["support"]), "-o", str(paths["out"])])
            self.assertEqual(error.exception.code, 1); self.assertNotIn("Traceback", stderr.getvalue())
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error: main([])
            self.assertEqual(error.exception.code, 2)

if __name__ == "__main__": unittest.main()
