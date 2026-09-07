import base64
import contextlib
import copy
import gzip
import hashlib
import io
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent_view import build_agent_view
from agent_view.models import AgentViewGraph
from agent_view.serialize import graph_to_json
from generate_html import ReportInputError, ReportOutputError, generate_report
from language_analyzers.core.graph_models import GraphNode, SourceSpan


def _occurrence(file_path="source.py", line=1, matched_text="needle", node_id="node:source"):
    return {"file_path": file_path, "line": line, "col": 0, "matched_text": matched_text, "context": "code", "enclosing_node_id": node_id, "surface": "content"}


def _query_digest(rows):
    return hashlib.sha256("\n".join(f"{row['file_path']}|{row['line']}|{row['col']}|{row['matched_text']}|{row['context']}|{row['enclosing_node_id']}|{row['surface']}" for row in rows).encode()).hexdigest()


def _payload(project_name="fixture"):
    rows = [_occurrence()]
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    block = {"id": "occ:00000000", "start": 0, "end": 1, "count": 1, "sha256": hashlib.sha256(raw).hexdigest(), "encoding": "gzip+base64", "data": base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode()}
    cost = {"token_estimate": 2, "char_count": 8, "line_count": 1}
    return {
        "schema_version": "3", "project_name": project_name,
        "profile": {"id": "fixture.v3", "version": 3, "content_hash": "a" * 64, "min_term_length": 3, "max_file_bytes": 1048576, "transforms": [{"id": "split-case", "prefixes": [], "suffixes": []}], "include_agent_docs": True, "tracked_files_only": True, "read_unit_token_limit": 8000, "read_query_candidate_limit": 8, "search_output_limit": 100, "hint_query_limit": 4, "refinement_threshold": 50, "refinement_query_limit": 4, "refinement_depth_limit": 2, "root_list_depth": 2, "root_list_entry_limit": 200, "occurrence_block_rows": 4096, "context_lines": 0, "generated_marker_lines": 8, "vendor_globs": ["vendor/**"], "generated_globs": ["build/**"], "generated_markers": ["generated file"], "lockfile_names": ["package-lock.json"], "split_version": "symbol-greedy-v1", "ordering_version": "path-line-byte-v1", "output_format_version": "match-line-v1", "query_equivalence_version": "equivalence-v1", "read_limit_provenance": "fixture read", "search_limit_provenance": "fixture search"},
        "scan": {"ignore_source": "fixture", "scanned_file_count": 1, "excluded_files": [{"file_path": "out.html", "reason": "explicit_output"}], "exclusion_counts": {"explicit_output": 1}, "snapshot_digest": "b" * 64},
        "read_units": [{"id": "unit:source", "file_path": "source.py", "start_line": 1, "end_line": 1, "symbol_ids": ["node:source"], "read_cost": cost, "oversized_symbol": False}],
        "readable_nodes": [{"id": "node:source", "file_path": "source.py", "symbol_id": None, "label": "source.py", "kind": "file", "start_line": 1, "end_line": 1, "read_cost": cost, "flags": [], "read_unit_id": "unit:source"}],
        "query_nodes": [{"id": "query:needle", "term": "needle", "kind": "framework", "surface": "content", "scope": "repository", "clue_kinds": ["framework"], "origin_node_ids": ["node:source"], "rule_id": "fixture-rule", "source_terms": [], "occurrence_ranges": [{"block_id": block["id"], "start": 0, "count": 1}], "occurrence_digest": _query_digest(rows), "arrival_node_ids": ["node:source"], "total_count": 1, "visible_count": 1, "truncated": False, "output_tokens": 1, "duplicate_suppressed_count": 0, "candidate_filtered_count": 0, "candidate_cap_truncated": False, "refinement_depth": 0}],
        "connections": [{"id": "connection:one", "from_id": "node:source", "to_id": "query:needle", "kind": "generates", "specificity": "narrowing", "evidence": {"rule": "fixture-rule"}}, {"id": "connection:two", "from_id": "query:needle", "to_id": "node:source", "kind": "result", "specificity": "narrowing", "evidence": {"paths": ["source.py"]}}],
        "entry_documents": [{"node_id": "node:source", "file_path": "source.py", "injected": False}],
        "hint_store": {},
        "occurrence_store": [block],
    }


def _payload_text(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def _embedded_payload(html):
    matches = re.findall(r'<script id="agent-view-v3-payload"[^>]*>([^<]+)</script>', html)
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one payload, got {len(matches)}")
    return json.loads(gzip.decompress(base64.b64decode(matches[0])))


def _representative_large_payload():
    value = _payload("pinned-large-v3")
    node_count = 6476
    query_count = 6832
    occurrence_count = 91242
    cost = {"token_estimate": 2, "char_count": 8, "line_count": 1}
    node_ids = [f"node:{index:05d}" for index in range(node_count)]
    value["read_units"] = [{"id": "unit:all", "file_path": "src/all.py", "start_line": 1, "end_line": node_count, "symbol_ids": node_ids, "read_cost": cost, "oversized_symbol": False}]
    value["readable_nodes"] = [{"id": node_id, "file_path": f"src/module_{index % 372:03d}.py", "symbol_id": f"symbol:{index:05d}", "label": f"Symbol{index:05d}", "kind": "function", "start_line": index + 1, "end_line": index + 1, "read_cost": cost, "flags": [], "read_unit_id": "unit:all"} for index, node_id in enumerate(node_ids)]
    rows = [_occurrence(f"src/module_{index % 372:03d}.py", index // 372 + 1, f"term{index % 6832:04d}", node_ids[index % node_count]) for index in range(occurrence_count)]
    blocks = []
    ranges = []
    for start in range(0, len(rows), 4096):
        chunk = rows[start:start + 4096]
        raw = json.dumps(chunk, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        block_id = f"occ:{len(blocks):08d}"
        blocks.append({"id": block_id, "start": start, "end": start + len(chunk), "count": len(chunk), "sha256": hashlib.sha256(raw).hexdigest(), "encoding": "gzip+base64", "data": base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode()})
        ranges.append({"block_id": block_id, "start": 0, "count": len(chunk)})
    empty_digest = _query_digest([])
    queries = []
    for index in range(query_count):
        broad = index == 0
        queries.append({"id": f"query:{index:05d}", "term": f"term{index:04d}", "kind": "exact", "surface": "content", "scope": "repository", "clue_kinds": ["identifier"], "origin_node_ids": [node_ids[index % node_count]], "rule_id": None, "source_terms": [], "occurrence_ranges": ranges if broad else [], "occurrence_digest": _query_digest(rows) if broad else empty_digest, "arrival_node_ids": node_ids[:100] if broad else [], "total_count": occurrence_count if broad else 0, "visible_count": 100 if broad else 0, "truncated": broad, "output_tokens": 100 if broad else 0, "duplicate_suppressed_count": 0, "candidate_filtered_count": 0, "candidate_cap_truncated": False, "refinement_depth": 0})
    value["query_nodes"] = queries
    value["connections"] = [{"id": f"connection:{index:05d}", "from_id": node_ids[index % node_count], "to_id": f"query:{index:05d}", "kind": "generates", "specificity": "narrowing", "evidence": {}} for index in range(query_count)]
    value["entry_documents"] = []
    value["occurrence_store"] = blocks
    value["scan"]["scanned_file_count"] = 372
    return value


def _assert_offline(test_case, html):
    executable = re.sub(r'(<script id="agent-view-v3-payload"[^>]*>)[^<]+(</script>)', r"\1\2", html)
    forbidden_apis = ("fetch", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon", "importScripts")
    for api in forbidden_apis:
        test_case.assertIsNone(re.search(rf"\b{api}\b", executable), api)
    test_case.assertIsNone(re.search(r"\bimport\s*\(", executable), "dynamic import")
    test_case.assertIsNone(re.search(r"(?:https?|wss?|ftp)://|(?<!:)//[^/\s]", executable, re.IGNORECASE), "network scheme")
    test_case.assertIsNone(re.search(r"<(?:script|link|img|iframe|audio|video|source)\b[^>]*\b(?:src|href)\s*=", executable, re.IGNORECASE), "external resource attribute")


class ReportContractTests(unittest.TestCase):
    def write_payload(self, root, value=None):
        source = root / "view.json"
        source.write_text(_payload_text(value or _payload()), encoding="utf-8")
        return source

    def test_deterministic_offline_report_round_trips_hostile_strings_inertly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = _payload('</script><img src=x onerror="alert(1)">\u2028')
            source = self.write_payload(root, value)
            stderr = io.StringIO()
            first = generate_report(source, root / "first.html", stderr=stderr)
            second = generate_report(source, root / "second.html", stderr=stderr)
            html = first.read_text(encoding="utf-8")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(_embedded_payload(html), value)
            self.assertNotIn(value["project_name"], html)
            self.assertEqual(html.count('id="agent-view-v3-payload"'), 1)
            _assert_offline(self, html)
            self.assertNotIn("warning:", stderr.getvalue())
            self.assertLess(first.stat().st_size, 10 * 1024 * 1024)

    def test_report_contains_graph_cost_distribution_and_all_evidence_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = generate_report(self.write_payload(root))
            html = output.read_text(encoding="utf-8")
            for marker in ("전체 관계 그래프", "구성과 비용 분포", "read-unit token", "query 전체 결과 수", "connection specificity", "viewport culling", "decodeOccurrenceBlock", "data.connections", "framework"):
                self.assertIn(marker, html)
            self.assertNotIn("slice(0,100)", html.replace(" ", ""))

    def test_browser_bootstrap_decompresses_graph_then_occurrences_lazily(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = generate_report(self.write_payload(root)).read_text(encoding="utf-8")
            encoded = re.search(r'<script id="agent-view-v3-payload"[^>]*>([^<]+)</script>', html).group(1)
            bootstrap = re.search(r'</script>\s*<script>\s*((?:.|\n)*?)</script>', html[html.index('id="agent-view-v3-payload"'):]).group(1)
            driver = f'''const native=DecompressionStream; let calls=0; globalThis.DecompressionStream=class {{ constructor(kind){{ calls+=1; return new native(kind); }} }}; globalThis.window=globalThis; const status={{textContent:"",className:""}}; globalThis.CustomEvent=class {{constructor(name,options){{this.name=name;this.detail=options.detail;}}}}; globalThis.document={{getElementById:(id)=>id==="agent-view-v3-payload"?{{textContent:{json.dumps(encoded)}}}:status,dispatchEvent:()=>{{}}}}; eval({json.dumps(bootstrap)}); ReportReady.then(async graph=>{{const startup=calls; const rows=await ReportPayload.decodeOccurrenceBlock(graph.occurrence_store[0]); console.log(JSON.stringify({{startup:startup,after:calls,rows:rows,status:status.textContent}}));}}).catch(error=>{{console.error(error);process.exit(1);}});'''
            result = subprocess.run(["node", "-"], input=driver, text=True, capture_output=True, check=True)
            state = json.loads(result.stdout)
            self.assertEqual(state["startup"], 1)
            self.assertEqual(state["after"], 2)
            self.assertEqual(state["rows"], [_occurrence()])
            self.assertIn("로드 완료", state["status"])

    def test_unsupported_browser_shows_usable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = generate_report(self.write_payload(root)).read_text(encoding="utf-8")
            encoded = re.search(r'<script id="agent-view-v3-payload"[^>]*>([^<]+)</script>', html).group(1)
            bootstrap = re.search(r'</script>\s*<script>\s*((?:.|\n)*?)</script>', html[html.index('id="agent-view-v3-payload"'):]).group(1)
            driver = f'''globalThis.DecompressionStream=undefined;globalThis.window=globalThis;const status={{textContent:"",className:""}};globalThis.document={{getElementById:(id)=>id==="agent-view-v3-payload"?{{textContent:{json.dumps(encoded)}}}:status,dispatchEvent:()=>{{}}}};eval({json.dumps(bootstrap)});ReportReady.catch(()=>console.log(JSON.stringify(status)));'''
            result = subprocess.run(["node", "-"], input=driver, text=True, capture_output=True, check=True)
            state = json.loads(result.stdout)
            self.assertEqual(state["className"], "error")
            self.assertIn("DecompressionStream", state["textContent"])
            self.assertIn("Chromium", state["textContent"])

    def test_v3_only_required_nested_range_count_hash_and_encoding_validation(self):
        valid = _payload()
        corruptions = []
        for value in ({}, {"schema_version": "1"}, {"schema_version": "2"}):
            corruptions.append(value)
        missing = copy.deepcopy(valid); del missing["connections"]; corruptions.append(missing)
        nested = copy.deepcopy(valid); nested["profile"] = []; corruptions.append(nested)
        nested_cost = copy.deepcopy(valid); nested_cost["read_units"][0]["read_cost"]["token_estimate"] = True; corruptions.append(nested_cost)
        bad_range = copy.deepcopy(valid); bad_range["query_nodes"][0]["occurrence_ranges"][0]["count"] = 2; corruptions.append(bad_range)
        bad_count = copy.deepcopy(valid); bad_count["occurrence_store"][0]["count"] = 2; bad_count["occurrence_store"][0]["end"] = 2; corruptions.append(bad_count)
        bad_hash = copy.deepcopy(valid); bad_hash["occurrence_store"][0]["sha256"] = "0" * 64; corruptions.append(bad_hash)
        bad_encoding = copy.deepcopy(valid); bad_encoding["occurrence_store"][0]["encoding"] = "base64"; corruptions.append(bad_encoding)
        bad_data = copy.deepcopy(valid); bad_data["occurrence_store"][0]["data"] = "not-base64"; corruptions.append(bad_data)
        bad_total = copy.deepcopy(valid); bad_total["query_nodes"][0]["total_count"] = 0; bad_total["query_nodes"][0]["visible_count"] = 0; corruptions.append(bad_total)
        dangling = copy.deepcopy(valid); dangling["connections"][0]["from_id"] = "missing"; corruptions.append(dangling)
        bad_hint = copy.deepcopy(valid); bad_hint["hint_store"] = {"h:bad": {"paths": ["source.py"], "roles": [], "identifiers": []}}; corruptions.append(bad_hint)
        dangling_hint = copy.deepcopy(valid); dangling_hint["connections"][0]["evidence"] = {"hint_id": "h:missing"}; corruptions.append(dangling_hint)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, value in enumerate(corruptions):
                with self.subTest(index=index):
                    source = root / f"bad-{index}.json"
                    source.write_text(_payload_text(value), encoding="utf-8")
                    with self.assertRaises(ReportInputError):
                        generate_report(source, root / f"bad-{index}.html")
            malformed = root / "malformed.json"; malformed.write_text("{", encoding="utf-8")
            with self.assertRaises(ReportInputError):
                generate_report(malformed)

    def test_read_template_write_and_compression_failures_are_typed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.write_payload(root)
            with self.assertRaises(ReportOutputError):
                generate_report(source, read_text=lambda path: (_ for _ in ()).throw(OSError("read")))
            source_text = source.read_text(encoding="utf-8")
            def fail_template(path):
                if path.name == source.name:
                    return source_text
                raise OSError("template")
            with self.assertRaises(ReportOutputError):
                generate_report(source, read_text=fail_template)
            with self.assertRaises(ReportOutputError):
                generate_report(source, compress=lambda raw: (_ for _ in ()).throw(OSError("compress")))
            with self.assertRaises(ReportOutputError):
                generate_report(source, compress=lambda raw: b"not-gzip")
            with self.assertRaises(ReportOutputError):
                generate_report(source, write_text=lambda path, text: (_ for _ in ()).throw(OSError("write")))
            with self.assertRaises(ReportOutputError):
                generate_report(source, source)

    def test_scale_warning_does_not_change_embedded_payload_or_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = _payload()
            source = self.write_payload(root, value)
            stderr = io.StringIO()
            source_text = source.read_text(encoding="utf-8")
            template_root = Path(__file__).resolve().parents[1] / "html_template"
            def large_template_reader(path):
                if path.name == source.name:
                    return source_text
                text = (template_root / path.name).read_text(encoding="utf-8")
                return text + ("x" * (10 * 1024 * 1024) if path.name == "common.css" else "")
            output = generate_report(source, stderr=stderr, read_text=large_template_reader)
            self.assertGreater(output.stat().st_size, 10 * 1024 * 1024)
            self.assertIn("warning:", stderr.getvalue())
            self.assertEqual(_embedded_payload(output.read_text(encoding="utf-8")), value)

    def test_pinned_representative_large_v3_report_is_below_budget_without_warning(self):
        value = _representative_large_payload()
        graph = AgentViewGraph(
            schema_version=value["schema_version"], project_name=value["project_name"], project_path="/pinned/representative",
            profile=value["profile"], scan=value["scan"], read_units=value["read_units"], readable_nodes=value["readable_nodes"],
            query_nodes=value["query_nodes"], connections=value["connections"], entry_documents=value["entry_documents"],
            hint_store=value["hint_store"], occurrence_store=value["occurrence_store"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_stderr = io.StringIO()
            with contextlib.redirect_stderr(json_stderr):
                serialized = graph_to_json(graph)
            source = root / "view.json"
            source.write_text(serialized, encoding="utf-8")
            stderr = io.StringIO()
            output = generate_report(source, stderr=stderr)
            self.assertGreater(source.stat().st_size, 5 * 1024 * 1024)
            self.assertLess(len(serialized.encode("utf-8")), 10 * 1024 * 1024)
            self.assertEqual(json_stderr.getvalue(), "")
            self.assertLess(output.stat().st_size, 10 * 1024 * 1024)
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(_embedded_payload(output.read_text(encoding="utf-8")), value)

    def test_real_agent_view_graph_hint_round_trips_into_report_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_file = root / "source.py"
            source_file.write_text("def Needle(otherName):\n    return Needle(otherName)\n", encoding="utf-8")
            architecture = SimpleNamespace(
                project_path=str(root), project_name="real-hint",
                nodes=[GraphNode("symbol:needle", "Needle", "symbol", "symbol", kind="function", span=SourceSpan("source.py", 1, 2))],
                edges=[],
            )
            graph = build_agent_view(architecture, file_lister=lambda unused: ("integration", ["source.py"]))
            self.assertTrue(graph.hint_store)
            result_connection = next(item for item in graph.connections if item.kind == "result" and "hint_id" in item.evidence)
            expected_hint = graph.hint_store[result_connection.evidence["hint_id"]]
            self.assertEqual(set(expected_hint), {"path", "file_name", "symbol_name", "roles", "identifiers"})
            source = root / "view.json"
            source.write_text(graph_to_json(graph), encoding="utf-8")
            output = generate_report(source)
            report_data = _embedded_payload(output.read_text(encoding="utf-8"))
            model_path = Path(__file__).resolve().parents[1] / "html_template" / "evidence_model.js"
            driver = f'''const model=require({json.dumps(str(model_path))});const data={json.dumps(report_data)};const item=model.build(data).find(value=>value.value.id==={json.dumps(result_connection.id)});if(!item||!item.value.resolved_hint)process.exit(2);console.log(JSON.stringify(item.value.resolved_hint));'''
            result = subprocess.run(["node", "-"], input=driver, text=True, capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout), expected_hint)


if __name__ == "__main__":
    unittest.main()
