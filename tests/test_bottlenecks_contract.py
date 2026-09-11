import copy
import hashlib
import builtins
import io
import json
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from agent_view import build_agent_view, load_profile
from agent_view.models import RepositorySnapshot
from agent_view.models import Connection
from bottlenecks import BottleneckInputError, HarnessProfileError, ObservationTraceError, Probe, analyze_bottlenecks, bottlenecks_to_json, convert_legacy_trace, parse_harness_profile, parse_observation_trace, replay_probe
from language_analyzers.python.graph import PythonGraphAnalyzer
from language_analyzers.python.symbols import build_symbol_table


ROOT = Path(__file__).resolve().parents[1]
def profile_payload(visible=30, maximum=2000, depth=2):
    return {"schema": "harness_profile.v1", "id": "test-fixed", "version": 1, "provenance_status": "unverified_baseline", "content_search": {"matching": "fixed_string_case_sensitive", "order": "path_lexical_then_numeric_line", "visible_lines": visible, "cap_unit": "matching_lines", "same_line_occurrences": "preserved"}, "path_search": {"matching": "fixed_string_case_sensitive", "order": "path_lexical_then_numeric_line", "visible_lines": visible, "cap_unit": "matching_paths"}, "read": {"bounds": "one_based_inclusive", "max_lines": maximum, "eof": "clamp", "truncation": "actual_omitted_lines"}, "features": {"fixed_string_search": "supported", "line_range_read": "supported", "semantic_search": "unsupported", "index": "unsupported", "context_compaction": "observation_only", "parallelism": "observation_only", "subagents": "observation_only"}, "assumptions": {"automatic_injection": "unverified_baseline", "list_depth": depth}}


def snapshot(contents):
    rows = tuple(sorted(contents.items()))
    digest = hashlib.sha256("".join(f"{p}\0{hashlib.sha256(t.encode()).hexdigest()}\n" for p, t in rows).encode()).hexdigest()
    return RepositorySnapshot("/repo", "test", rows, (), digest)


def trace_payload(profile, events, digest):
    content_hash = hashlib.sha256(json.dumps(asdict(profile), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    normalized = []
    for event in events:
        item = dict(event)
        item.setdefault("status", "completed")
        normalized.append(item)
    return {"schema": "harness_observation.v1", "id": "trace-1", "snapshot_digest": digest, "profile": {"id": profile.id, "version": profile.version, "content_hash": content_hash}, "events": normalized}


class HarnessReplayContractTests(unittest.TestCase):
    def setUp(self): self.profile = parse_harness_profile(profile_payload())

    def test_scope_extension_root_list_and_caps(self):
        repo = snapshot({"foo/a.py": "needle needle\nneedle\n", "foobar/a.py": "needle", "foo/a.txt": "needle", "root.py": "needle", "deep/x/y.py": "needle"})
        result = replay_probe(repo, Probe("scope", "exact", "content", "needle", "repository|path_prefix:foo|extension:.py"), self.profile)
        self.assertEqual([(r["path"], r["line"]) for r in result.rows], [("foo/a.py", 1), ("foo/a.py", 2)])
        paths = replay_probe(repo, Probe("paths", "exact", "path", "a", "extension:.py"), self.profile)
        self.assertEqual([r["path"] for r in paths.rows], ["foo/a.py", "foobar/a.py"])
        listed = replay_probe(repo, Probe("root", "list", "path", "", "root"), parse_harness_profile(profile_payload(depth=1)))
        self.assertEqual([r["path"] for r in listed.rows], ["root.py"])
        cap = replay_probe(repo, Probe("cap", "exact", "content", "needle"), parse_harness_profile(profile_payload(2)))
        self.assertEqual((cap.total_count, cap.visible_count, cap.omitted_count, cap.truncated), (6, 2, 4, True))

    def test_empty_equal_cap_read_eof_and_invalid_bounds(self):
        repo = snapshot({"a.py": "one\ntwo\nthree\nfour"})
        self.assertEqual(replay_probe(snapshot({}), Probe("empty", "exact", "content", "needle"), self.profile).total_count, 0)
        equal = replay_probe(snapshot({"a.py": "x\nx"}), Probe("equal", "exact", "content", "x"), parse_harness_profile(profile_payload(2)))
        self.assertEqual((equal.omitted_count, equal.truncated), (0, False))
        active = parse_harness_profile(profile_payload(maximum=2))
        read = replay_probe(repo, Probe("read", "exact", "read", "", path="a.py", start_line=2, end_line=4), active)
        self.assertEqual((read.rows[0]["start_line"], read.rows[0]["end_line"], read.rows[0]["text"], read.omitted_count), (2, 3, "two\nthree\n", 1))
        self.assertEqual(replay_probe(repo, Probe("eof", "exact", "read", "", path="a.py", start_line=5, end_line=9), active).rows, ())
        blank = snapshot({"empty.py": "", "newline.py": "\n"})
        self.assertEqual(replay_probe(blank, Probe("empty-read", "exact", "read", "", path="empty.py", start_line=1, end_line=1), active).rows, ())
        newline = replay_probe(blank, Probe("newline-read", "exact", "read", "", path="newline.py", start_line=1, end_line=1), active)
        self.assertEqual((newline.rows[0]["text"], newline.rows[0]["end_line"]), ("\n", 1))
        for probe in (Probe("", "exact", "content", "x"), Probe("bad", "exact", "read", "", path="x", start_line=1, end_line=1), Probe("bad", "exact", "read", "", path="a.py", start_line=True, end_line=1), Probe("bad", "exact", "read", "", path="a.py", start_line=2, end_line=1), Probe("bad", "exact", "content", "x", "path_prefix:")):
            with self.subTest(probe=probe), self.assertRaises(BottleneckInputError): replay_probe(repo, probe, active)


class ParsingAndObservationContractTests(unittest.TestCase):
    def test_symbol_table_default_resolves_and_snapshot_mode_rejects_relative_root(self):
        self.assertEqual(build_symbol_table([], Path(".")).modules, {})
        with self.assertRaises(ValueError): build_symbol_table([], Path("relative"), resolve_root=False)

    def test_profile_nested_types_bools_null_and_unknowns_are_rejected(self):
        for change in (lambda x: x.__setitem__("version", True), lambda x: x["content_search"].__setitem__("visible_lines", "30"), lambda x: x["read"].__setitem__("max_lines", None), lambda x: x["features"].__setitem__("index", True), lambda x: x.__setitem__("extra", None)):
            data = profile_payload(); change(data)
            with self.assertRaises(HarnessProfileError): parse_harness_profile(data)
        for value in (0, -1):
            data = profile_payload(value, value)
            with self.assertRaises(HarnessProfileError): parse_harness_profile(data)
        self.assertEqual(parse_harness_profile(profile_payload(10**9, 10**9)).read["max_lines"], 10**9)

    def test_trace_is_strict_and_legacy_is_unverified_unknown(self):
        active = parse_harness_profile(profile_payload())
        valid = trace_payload(active, [{"id": "e", "kind": "search", "inputs": {"probe_id": "p"}, "returned": {"rows": [], "total_count": 0, "visible_count": 0, "omitted_count": 0, "truncated": False}}], "d")
        self.assertEqual(parse_observation_trace(valid).events[0]["id"], "e")
        bad = [{**valid, "events": valid["events"] * 2}, {**valid, "profile": {"id": active.id, "version": True, "content_hash": "x"}}, {**valid, "events": [{"id": "e", "kind": "search", "inputs": {}, "returned": {"visible_count": True}}]}]
        for item in bad:
            with self.assertRaises(ObservationTraceError): parse_observation_trace(item)
        legacy = convert_legacy_trace({"events": [{"kind": "search", "paths": ["a.py"]}]}, snapshot_digest="d", profile=active)
        self.assertEqual(legacy.binding_status, "caller_supplied_unverified")
        self.assertFalse(legacy.events[0]["returned"]["exposure_known"])
        status_list = trace_payload(active, [{"id": "bad-status", "kind": "search", "status": [], "inputs": {}, "returned": {}}], "d")
        with self.assertRaises(ObservationTraceError): parse_observation_trace(status_list)

    def test_trace_nested_field_type_matrix_rejects_invalid_values_and_allows_unknown_nulls(self):
        active = parse_harness_profile(profile_payload())
        valid = trace_payload(active, [{"id": "event", "kind": "read", "inputs": {"path": "a.py", "start_line": 1, "end_line": 1}, "returned": {"rows": None, "ranges": None, "range": None, "text": None}}], "digest")
        self.assertEqual(parse_observation_trace(valid).id, "trace-1")
        cases = []
        root = copy.deepcopy(valid); root["events"] = None; cases.append(root)
        event = copy.deepcopy(valid); event["events"][0] = None; cases.append(event)
        profile = copy.deepcopy(valid); profile["profile"]["content_hash"] = None; cases.append(profile)
        inputs = copy.deepcopy(valid); inputs["events"][0]["inputs"]["path"] = []; cases.append(inputs)
        returned = copy.deepcopy(valid); returned["events"][0]["returned"]["rows"] = {}; cases.append(returned)
        ranges = copy.deepcopy(valid); ranges["events"][0]["returned"]["ranges"] = [{"start_line": None, "end_line": 1}]; cases.append(ranges)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ObservationTraceError):
                parse_observation_trace(data)


class BottleneckAnalysisContractTests(unittest.TestCase):
    def setUp(self):
        self.repo = snapshot({"a.py": "def shared():\n    return 1\n", "b.py": "from a import shared\nshared()\n", "bad.py": "def bad(:\n", "notes.txt": "shared"})
        self.architecture = PythonGraphAnalyzer("/repo", self.repo).analyze()
        self.graph = build_agent_view(self.architecture, profile=load_profile(ROOT / "profiles/agent_view.v3.yaml"), snapshot=self.repo)
        self.profile = parse_harness_profile(profile_payload(1, 1))

    def report(self, traces=()): return analyze_bottlenecks(self.repo, self.architecture, self.graph, self.profile, traces=traces)

    def test_report_deterministic_schema_coverage_and_profile_sensitivity(self):
        first, second = bottlenecks_to_json(self.report()), bottlenecks_to_json(self.report())
        payload = json.loads(first)
        self.assertEqual(first, second)
        self.assertEqual(payload["schema"], "bottlenecks.v1")
        self.assertEqual(payload["snapshot"]["digest"], self.repo.digest)
        self.assertEqual(payload["profile"]["content_search"]["visible_lines"], 1)
        self.assertIn("content_hash", payload["profile"])
        self.assertIn("invalid_python_files", payload["coverage"])
        self.assertEqual(payload["candidates"], sorted(payload["candidates"], key=lambda x: (x["kind"], x["id"])))
        wider = analyze_bottlenecks(self.repo, self.architecture, self.graph, parse_harness_profile(profile_payload(30, 30)))
        self.assertNotEqual([p["output"]["visible_count"] for p in self.report().probes], [p["output"]["visible_count"] for p in wider.probes])

    def test_positive_candidate_rules_carry_targets_evidence_counts_and_candidate_status(self):
        candidates = self.report().candidates
        by_kind = {item["kind"]: item for item in candidates}
        for kind in ("multiple_results", "evidence_spread", "read_limit", "connection_constraint"):
            self.assertIn(kind, by_kind)
        search = by_kind["multiple_results"]
        self.assertTrue(search["probe_ids"])
        self.assertGreater(search["metrics"]["total_rows"], search["metrics"]["visible_rows"])
        self.assertEqual(search["metrics"]["hidden_rows"], search["metrics"]["total_rows"] - search["metrics"]["visible_rows"])
        spread = by_kind["evidence_spread"]
        self.assertEqual(spread["target"], "py:a#shared")
        self.assertGreaterEqual(spread["metrics"]["file_count"], 2)
        self.assertTrue(all(item["status"] == "static_candidate" for item in candidates))

    def test_m3_ec_01_static_candidates_include_profile_validation_and_obstacle(self):
        for candidate in self.report().candidates:
            with self.subTest(candidate=candidate["id"]):
                self.assertEqual(candidate["status"], "static_candidate")
                self.assertEqual(candidate["validation_status"], "unverified")
                self.assertEqual(candidate["affected_profile_ids"], [self.profile.id])
                self.assertEqual(set(candidate["obstacle"]), {"axis", "explanation"})
                self.assertIsInstance(candidate["obstacle"]["axis"], str)
                self.assertTrue(candidate["obstacle"]["explanation"])

    def test_m3_ec_02_candidate_obstacles_identify_static_exploration_barriers(self):
        expected_axes = {
            "multiple_results": "result_dilution",
            "output_truncated": "output_truncation",
            "evidence_spread": "evidence_spread",
            "read_limit": "read_limit",
            "connection_constraint": "connection_constraint",
            "unresolved_boundary": "unresolved_boundary",
        }
        for candidate in self.report().candidates:
            with self.subTest(candidate=candidate["id"]):
                self.assertEqual(candidate["obstacle"]["axis"], expected_axes[candidate["kind"]])
                self.assertNotIn("agent", candidate["obstacle"]["explanation"].lower())

    def test_m3_ec_02_output_truncation_only_candidate_has_output_truncation_axis(self):
        repo = snapshot({"a.py": "def repeated():\n    needle\n    needle\n"})
        architecture = PythonGraphAnalyzer("/repo", repo).analyze()
        base = build_agent_view(architecture, profile=load_profile(ROOT / "profiles/agent_view.v3.yaml"), snapshot=repo)
        query = replace(base.query_nodes[0], kind="exact", surface="content", term="needle", scope="repository")
        graph = replace(base, query_nodes=[query], connections=[])
        report = analyze_bottlenecks(repo, architecture, graph, parse_harness_profile(profile_payload(visible=1)))
        candidate = next(item for item in report.candidates if item["kind"] == "output_truncated")
        self.assertEqual(candidate["reasons"], ["output_truncated"])
        self.assertEqual(candidate["obstacle"]["axis"], "output_truncation")

    def test_pagerank_is_attached_explanation_not_candidate_selection_or_score(self):
        baseline = self.report()
        with patch("bottlenecks.core.pagerank", side_effect=lambda outgoing, _config: {node_id: 999.0 - index for index, node_id in enumerate(outgoing)}):
            changed = self.report()
        identity = lambda report: [(item["id"], item["kind"], item["target"]) for item in report.candidates]
        self.assertEqual(identity(baseline), identity(changed))
        payload = json.loads(bottlenecks_to_json(changed))
        self.assertNotIn("risk_score", json.dumps(payload))
        self.assertNotIn("safety_score", json.dumps(payload))
        self.assertNotIn("probability", json.dumps(payload))

    def test_analysis_rejects_binding_and_unknown_probe(self):
        with self.assertRaises(BottleneckInputError): analyze_bottlenecks(replace(self.repo, digest="other"), self.architecture, self.graph, self.profile)
        for trace in (parse_observation_trace(trace_payload(self.profile, [], "wrong")), parse_observation_trace(trace_payload(self.profile, [{"id": "e", "kind": "search", "inputs": {"probe_id": "unknown"}, "returned": {"rows": []}}], self.repo.digest))):
            with self.assertRaises(BottleneckInputError): self.report((trace,))
        bound = parse_observation_trace(trace_payload(self.profile, [], self.repo.digest))
        with self.assertRaises(BottleneckInputError): self.report((replace(bound, profile_content_hash=None),))

    def test_analysis_rejects_each_profile_binding_component_and_architecture_digest(self):
        bound = parse_observation_trace(trace_payload(self.profile, [], self.repo.digest))
        for trace in (replace(bound, profile_id="other"), replace(bound, profile_version=2), replace(bound, profile_content_hash="other")):
            with self.subTest(trace=trace), self.assertRaises(BottleneckInputError):
                self.report((trace,))
        for architecture in (replace(self.architecture, snapshot_digest="wrong"),):
            with self.assertRaises(BottleneckInputError):
                analyze_bottlenecks(self.repo, architecture, self.graph, self.profile)

    def test_legacy_trace_cannot_be_used_as_a_verified_probe_comparison(self):
        legacy = convert_legacy_trace({"events": [{"kind": "search", "term": "shared", "paths": ["a.py"], "probe_id": "malicious"}]}, snapshot_digest=self.repo.digest, profile=self.profile)
        observation = self.report((legacy,)).observations[0]
        self.assertEqual(observation["binding_status"], "caller_supplied_unverified")
        self.assertEqual(observation["comparisons"], [])

    def test_repeated_python_analysis_resets_snapshot_coverage(self):
        analyzer = PythonGraphAnalyzer("/repo", self.repo)
        first = analyzer.analyze().snapshot_coverage
        second = analyzer.analyze().snapshot_coverage
        self.assertEqual(first, second)
        self.assertIn("bad.py", second["invalid_python_files"])

    def test_empty_snapshot_analysis_has_no_candidates_and_explicit_zero_coverage(self):
        empty = snapshot({})
        architecture = PythonGraphAnalyzer("/repo", empty).analyze()
        graph = build_agent_view(architecture, profile=load_profile(ROOT / "profiles/agent_view.v3.yaml"), snapshot=empty)
        report = analyze_bottlenecks(empty, architecture, graph, parse_harness_profile(profile_payload()))
        self.assertEqual(report.candidates, ())
        self.assertEqual(report.coverage["source_file_count"], 0)
        self.assertEqual(report.coverage["python_file_count"], 0)

    def test_supplied_snapshot_analysis_does_not_read_or_walk_the_filesystem(self):
        repo = snapshot({"a.py": "def value():\n    return 1\n"})
        profile = load_profile(ROOT / "profiles/agent_view.v3.yaml")
        with patch("builtins.open", side_effect=AssertionError("disk read")), patch("io.open", side_effect=AssertionError("disk read")), patch("pathlib.Path.read_text", side_effect=AssertionError("disk read")), patch("pathlib.Path.read_bytes", side_effect=AssertionError("disk read")), patch("pathlib.Path.resolve", side_effect=AssertionError("resolve")), patch("pathlib.Path.rglob", side_effect=AssertionError("disk walk")), patch("pathlib.Path.iterdir", side_effect=AssertionError("disk walk")), patch("pathlib.Path.glob", side_effect=AssertionError("disk walk")), patch("os.walk", side_effect=AssertionError("disk walk")), patch("os.listdir", side_effect=AssertionError("disk walk")), patch("os.scandir", side_effect=AssertionError("disk walk")):
            architecture = PythonGraphAnalyzer("/repo", repo).analyze()
            graph = build_agent_view(architecture, profile=profile, snapshot=repo)
            report = analyze_bottlenecks(repo, architecture, graph, parse_harness_profile(profile_payload()))
        self.assertEqual(report.snapshot["digest"], repo.digest)

    def test_unresolved_reference_omission_is_retained_in_candidate_metrics(self):
        calls = "\n".join(f"    unknown_{index}()" for index in range(25))
        repo = snapshot({"a.py": f"def caller():\n{calls}\n"})
        architecture = PythonGraphAnalyzer("/repo", repo).analyze()
        graph = build_agent_view(architecture, profile=load_profile(ROOT / "profiles/agent_view.v3.yaml"), snapshot=repo)
        candidates = analyze_bottlenecks(repo, architecture, graph, parse_harness_profile(profile_payload())).candidates
        unresolved = next(item for item in candidates if item["kind"] == "unresolved_boundary" and item["metrics"].get("unresolved_total", 0) == 25)
        self.assertEqual({key: unresolved["metrics"][key] for key in ("unresolved_total", "evidence_limit", "evidence_truncated")}, {"unresolved_total": 25, "evidence_limit": 20, "evidence_truncated": True})

    def test_same_file_evidence_span_uses_end_line_and_strict_read_limit_threshold(self):
        source = "def target():\n    return 1\n\ndef first():\n    return target()\n\n\n\ndef second():\n    return target()\n"
        repo = snapshot({"a.py": source})
        architecture = PythonGraphAnalyzer("/repo", repo).analyze()
        graph = build_agent_view(architecture, profile=load_profile(ROOT / "profiles/agent_view.v3.yaml"), snapshot=repo)
        equal = analyze_bottlenecks(repo, architecture, graph, parse_harness_profile(profile_payload(maximum=10))).candidates
        over = analyze_bottlenecks(repo, architecture, graph, parse_harness_profile(profile_payload(maximum=9))).candidates
        self.assertFalse(any(item["kind"] == "evidence_spread" and item["target"] == "py:a#target" for item in equal))
        candidate = next(item for item in over if item["kind"] == "evidence_spread" and item["target"] == "py:a#target")
        self.assertEqual(candidate["metrics"]["line_span"], 10)

    def test_smallest_content_arrival_path_arrival_and_duplicate_term_clue_deduplication(self):
        repo = snapshot({"a.py": "def repeated():\n    repeated\n    repeated\n"})
        architecture = PythonGraphAnalyzer("/repo", repo).analyze()
        base = build_agent_view(architecture, profile=load_profile(ROOT / "profiles/agent_view.v3.yaml"), snapshot=repo)
        function = next(node for node in base.readable_nodes if node.kind == "function")
        module = next(node for node in base.readable_nodes if node.kind == "module")
        control = base.query_nodes[0]
        content = replace(control, id="content-repeated", kind="exact", surface="content", term="repeated", scope="repository")
        duplicate = replace(control, id="derived-repeated", kind="derived", surface="content", term="repeated", scope="repository")
        path = replace(control, id="path-a", kind="exact", surface="path", term="a.py", scope="repository")
        graph = replace(base, query_nodes=[content, duplicate, path], connections=[])
        report = analyze_bottlenecks(repo, architecture, graph, parse_harness_profile(profile_payload()))
        entries = {item["probe"]["id"]: item for item in report.probes}
        content_entry = next(item for item in entries.values() if item["probe"]["surface"] == "content" and item["probe"]["term"] == "repeated")
        path_entry = next(item for item in entries.values() if item["probe"]["surface"] == "path")
        self.assertEqual(content_entry["visible_arrival_ids"], [function.id])
        self.assertEqual(path_entry["visible_arrival_ids"], [module.id])
        self.assertFalse(any(item["kind"] == "multiple_results" and content_entry["probe"]["id"] in item["probe_ids"] for item in report.candidates))
        clue = next(item for item in report.candidates if item["kind"] == "connection_constraint" and item["target"] == function.id)
        self.assertEqual(clue["metrics"]["independent_visible_clue_count"], 1)

    def test_analysis_rejects_broken_graph_references(self):
        broken = replace(self.graph, connections=[*self.graph.connections, Connection("broken", "missing", "also-missing", "query", "exact")])
        with self.assertRaises(BottleneckInputError):
            analyze_bottlenecks(self.repo, self.architecture, broken, self.profile)

    def test_analysis_rejects_all_graph_and_architecture_reference_escapes(self):
        readable = self.graph.readable_nodes[0]
        unit = self.graph.read_units[0]
        query = self.graph.query_nodes[0]
        cases = [
            ("readable symbol", self.architecture, replace(self.graph, readable_nodes=[replace(readable, symbol_id="missing-symbol"), *self.graph.readable_nodes[1:]])),
            ("readable path", self.architecture, replace(self.graph, readable_nodes=[replace(readable, file_path="outside.py"), *self.graph.readable_nodes[1:]])),
            ("read unit path", self.architecture, replace(self.graph, read_units=[replace(unit, file_path="outside.py"), *self.graph.read_units[1:]])),
            ("query arrival", self.architecture, replace(self.graph, query_nodes=[replace(query, arrival_node_ids=["missing-readable"]), *self.graph.query_nodes[1:]])),
            ("query origin", self.architecture, replace(self.graph, query_nodes=[replace(query, origin_node_ids=["missing-readable"]), *self.graph.query_nodes[1:]])),
            ("edge candidate", replace(self.architecture, edges=[replace(self.architecture.edges[0], candidates=["missing-node"]), *self.architecture.edges[1:]]), self.graph),
        ]
        for label, architecture, graph in cases:
            with self.subTest(label=label), self.assertRaises(BottleneckInputError):
                analyze_bottlenecks(self.repo, architecture, graph, self.profile)

    def test_observation_match_mismatch_partial_duplicate_and_no_confirm(self):
        entry = next(item for item in self.report().probes if item["output"]["total_count"] > 0)
        probe, output = entry["probe"], json.loads(json.dumps(entry["output"]))
        events = [{"id": "match", "kind": "search", "inputs": {"probe_id": probe["id"]}, "returned": copy.deepcopy(output)}, {"id": "mismatch", "kind": "search", "inputs": {"probe_id": probe["id"]}, "returned": {"rows": [], "total_count": 0, "visible_count": 0, "truncated": False}}, {"id": "partial", "kind": "search", "inputs": {"probe_id": probe["id"]}, "returned": {"visible_count": output["visible_count"]}}, {"id": "again", "kind": "search", "inputs": {"probe_id": probe["id"]}, "returned": copy.deepcopy(output)}]
        trace = parse_observation_trace(trace_payload(self.profile, events, self.repo.digest))
        observation = self.report((trace,)).observations[0]
        self.assertEqual([x["status"] for x in observation["comparisons"]], ["match", "mismatch", "partial", "match"])
        self.assertEqual(observation["duplicated_exposure_count"], output["visible_count"])
        self.assertEqual(observation["returned_visible_count"], output["visible_count"] * 3)
        self.assertEqual(observation["confirmation_status"], "unobserved")

    def test_observation_omission_truncation_and_successful_confirmation_are_material(self):
        entry = next(item for item in self.report().probes if item["output"]["total_count"] > 0)
        output = json.loads(json.dumps(entry["output"])); probe = entry["probe"]
        omitted = dict(output, omitted_count=output["omitted_count"] + 1)
        truncated = dict(output, truncated=not output["truncated"])
        events = [{"id": "omit", "kind": "search", "inputs": {"probe_id": probe["id"]}, "returned": omitted}, {"id": "trunc", "kind": "search", "inputs": {"probe_id": probe["id"]}, "returned": truncated}, {"id": "confirm", "kind": "confirm", "inputs": {}, "returned": {"status": "ok"}}]
        observation = self.report((parse_observation_trace(trace_payload(self.profile, events, self.repo.digest)),)).observations[0]
        self.assertEqual([item["status"] for item in observation["comparisons"]], ["mismatch", "mismatch"])
        self.assertEqual(observation["confirmation_status"], "observed")

    def test_completed_empty_confirmation_remains_unobserved(self):
        trace = parse_observation_trace(trace_payload(self.profile, [{"id": "confirm", "kind": "confirm", "status": "completed", "inputs": {}, "returned": {}}], self.repo.digest))
        self.assertEqual(self.report((trace,)).observations[0]["confirmation_status"], "unobserved")
