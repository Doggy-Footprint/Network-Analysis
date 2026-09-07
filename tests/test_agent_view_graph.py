import base64
import dataclasses
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

from agent_view import (
    AgentViewInputError,
    SCHEMA_VERSION,
    build_agent_view,
    build_snapshot,
    decode_occurrence_block,
    decode_occurrence_ranges,
    default_profile_path,
    diff_agent_view,
    graph_to_json,
    graph_to_dict,
    load_profile,
    list_repository_files,
)
from agent_view.models import Occurrence, OccurrenceRange
from agent_view.occurrence import OccurrenceStoreError, encode_occurrence_blocks
from agent_view.readable import build_readable_graph
from agent_view.profile import ProfileError
from language_analyzers.core.cost import estimate_tokens
from language_analyzers.core.graph_models import GraphEdge, GraphNode, SourceSpan

def node(identifier,path,start,end,label=None):
    return GraphNode(identifier,label or identifier,"symbol","symbol",kind="function",span=SourceSpan(path,start,end))

class V3ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.profile=load_profile(default_profile_path())
    def tearDown(self): self.tmp.cleanup()
    def build(self,files,nodes=(),edges=(),**kwargs):
        arch=SimpleNamespace(project_path=str(self.root),project_name="fixture",nodes=list(nodes),edges=list(edges))
        reader = kwargs.pop(
            "file_reader",
            lambda path: files[path.relative_to(self.root).as_posix()],
        )
        lister = kwargs.pop("file_lister", lambda _:("fixture",list(files)))
        return build_agent_view(
            arch,
            profile=kwargs.pop("profile",self.profile),
            file_reader=reader,
            file_lister=lister,
            **kwargs,
        )

    def test_schema_and_required_sections(self):
        graph=self.build({"a.py":"def Alpha(): return 1\n"},[node("a","a.py",1,1,"Alpha")])
        payload=json.loads(graph_to_json(graph))
        self.assertEqual(SCHEMA_VERSION,"3")
        self.assertEqual(payload["schema_version"], "3")
        self.assertTrue({"profile","scan","read_units","readable_nodes","query_nodes","connections","entry_documents","occurrence_store"}<=payload.keys())

    def test_profile_serializes_every_behavior_limit_version_and_provenance(self):
        payload=json.loads(graph_to_json(self.build({"a.py":"x=1\n"})))
        profile=payload["profile"]
        profile_path = default_profile_path()
        self.assertEqual(profile, {
            "id": "agent_view.v3",
            "version": 3,
            "content_hash": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
            "min_term_length": 3,
            "max_file_bytes": 1048576,
            "transforms": [
                {"id": "split-case", "prefixes": [], "suffixes": []},
                {"id": "token-adjacent-pairs", "prefixes": [], "suffixes": []},
                {"id": "normalize-case", "prefixes": [], "suffixes": []},
                {"id": "plural-singular", "prefixes": [], "suffixes": []},
                {
                    "id": "strip-affix",
                    "prefixes": ["get", "set", "is", "has", "on", "handle", "build", "create"],
                    "suffixes": ["Impl", "Service", "Controller", "Handler", "Manager", "Factory", "ViewModel", "Repository"],
                },
            ],
            "include_agent_docs": True,
            "tracked_files_only": True,
            "read_unit_token_limit": 8000,
            "read_query_candidate_limit": 3,
            "search_output_limit": 30,
            "hint_query_limit": 4,
            "refinement_threshold": 50,
            "refinement_query_limit": 4,
            "refinement_depth_limit": 2,
            "root_list_depth": 2,
            "root_list_entry_limit": 200,
            "occurrence_block_rows": 4096,
            "context_lines": 0,
            "generated_marker_lines": 8,
            "vendor_globs": ["vendor/**", "node_modules/**", "third_party/**"],
            "generated_globs": ["build/**", "dist/**", "*.min.js"],
            "generated_markers": ["generated file", "do not edit"],
            "lockfile_names": ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock"],
            "split_version": "symbol-greedy-v1",
            "ordering_version": "path-line-byte-v1",
            "output_format_version": "match-line-v1",
            "query_equivalence_version": "kind-term-surface-scope-rules-v1",
            "read_limit_provenance": "Harness command: sed -n '1,2000p' FILE; measured ceiling: 8000 estimated tokens",
            "search_limit_provenance": "Harness command: rg --json TERM ROOT | head -n 30; configured visible occurrence ceiling: 30",
            "query_candidate_limit_provenance": "Harness trace field: follow_up_queries_after_read; retained positions: 1-3",
        })
        self.assertNotIn("max_arrival_nodes", profile)

    def test_snapshot_reads_every_candidate_once_and_reversed_listing_is_identical(self):
        files={"a.py":"Alpha\n","b.py":"Beta\n"}; calls={}
        for path,text in files.items(): (self.root/path).write_text(text)
        def reader(path): calls[path.name]=calls.get(path.name,0)+1; return path.read_text()
        arch=SimpleNamespace(project_path=str(self.root),project_name="x",nodes=[node("a","a.py",1,1,"Alpha")],edges=[])
        first=build_agent_view(arch,profile=self.profile,file_reader=reader,file_lister=lambda _:("x",list(reversed(files))))
        second=build_agent_view(arch,profile=self.profile,file_lister=lambda _:("x",list(files)))
        self.assertEqual(calls,{"a.py":1,"b.py":1}); self.assertEqual(graph_to_json(first),graph_to_json(second))

    def test_supplied_snapshot_is_used_without_reader_or_lister_calls(self):
        files = {"a.py": "Alpha Alpha\n"}
        (self.root / "a.py").write_text(files["a.py"])
        snapshot = build_snapshot(
            self.root,
            ["a.py"],
            profile=self.profile,
            reader=lambda path: files[path.name],
            ignore_source="injected",
        )
        architecture = SimpleNamespace(
            project_path=str(self.root),
            project_name="fixture",
            nodes=[node("a", "a.py", 1, 1, "Alpha")],
            edges=[],
        )

        def forbidden(*_args):
            raise AssertionError("snapshot build must not touch filesystem inventory")

        graph = build_agent_view(
            architecture,
            profile=self.profile,
            snapshot=snapshot,
            file_reader=forbidden,
            file_lister=forbidden,
        )

        self.assertEqual(graph.scan.ignore_source, "injected")
        self.assertEqual(graph.scan.snapshot_digest, snapshot.digest)

    def test_exclusion_reasons_cover_contract_and_renamed_artifact(self):
        artifact=json.dumps({"schema_version":"3","query_nodes":[],"occurrence_store":[]})
        files={"out.json":"x","renamed.data":artifact,"yarn.lock":"x","vendor/x.py":"x","build/x.py":"x","huge.txt":"x"*20,"blob":"x\0y"}
        profile=dataclasses.replace(self.profile,max_file_bytes=10)
        graph=self.build(files,profile=profile,excluded_paths=(self.root/"out.json",))
        reasons={x.file_path:x.reason for x in graph.scan.excluded_files}
        self.assertEqual(reasons,{"blob":"binary","build/x.py":"generated_path","huge.txt":"too_large","out.json":"explicit_output","renamed.data":"analyzer_artifact","vendor/x.py":"vendored","yarn.lock":"lockfile"})

    def test_custom_exclusion_profile_replaces_default_rules(self):
        profile = dataclasses.replace(
            self.profile,
            vendor_globs=["custom_vendor/**"],
            generated_globs=["custom_generated/**"],
            generated_markers=[r"CUSTOM AUTOGENERATED"],
            lockfile_names=["custom.lock"],
        )
        graph = self.build(
            {
                "vendor/default.py": "default vendor is included\n",
                "build/default.py": "default build is included\n",
                "yarn.lock": "default lock is included\n",
                "custom_vendor/x.py": "excluded\n",
                "custom_generated/x.py": "excluded\n",
                "custom.lock": "excluded\n",
                "marker.txt": "CUSTOM AUTOGENERATED\nexcluded\n",
            },
            profile=profile,
        )

        self.assertEqual(
            [(item.file_path, item.reason) for item in graph.scan.excluded_files],
            [
                ("custom.lock", "lockfile"),
                ("custom_generated/x.py", "generated_path"),
                ("custom_vendor/x.py", "vendored"),
                ("marker.txt", "generated_marker"),
            ],
        )
        self.assertEqual(
            {item.file_path for item in graph.readable_nodes},
            {"build/default.py", "vendor/default.py", "yarn.lock"},
        )
        self.assertEqual(
            graph.scan.exclusion_counts,
            {
                "generated_marker": 1,
                "generated_path": 1,
                "lockfile": 1,
                "vendored": 1,
            },
        )

    def test_tracked_renamed_json_and_html_artifacts_have_exact_reason(self):
        json_artifact = json.dumps({
            "schema_version": "3",
            "query_nodes": [],
            "occurrence_store": [],
        })
        html_artifact = (
            "<!doctype html><html><script id=\"agent-view-v3-payload\" "
            "type=\"application/octet-stream\">payload</script></html>"
        )
        graph = self.build({
            "source.py": "Source Source\n",
            "renamed-json.data": json_artifact,
            "renamed-html.data": html_artifact,
        }, file_lister=lambda _: (
            "git-tracked",
            ["source.py", "renamed-json.data", "renamed-html.data"],
        ))

        self.assertEqual(graph.scan.ignore_source, "git-tracked")
        self.assertEqual(
            [(item.file_path, item.reason) for item in graph.scan.excluded_files],
            [
                ("renamed-html.data", "analyzer_artifact"),
                ("renamed-json.data", "analyzer_artifact"),
            ],
        )
        self.assertEqual(graph.scan.exclusion_counts, {"analyzer_artifact": 2})
        self.assertEqual({item.file_path for item in graph.readable_nodes}, {"source.py"})

    def test_tracked_inventory_omits_untracked_files(self):
        with mock.patch(
            "agent_view.scan._git_tracked_files",
            return_value=["tracked.py"],
        ) as tracked, mock.patch("agent_view.scan._walk_files") as fallback:
            source, paths = list_repository_files(self.root, tracked_files_only=True)

        self.assertEqual(source, "git-tracked")
        self.assertEqual(paths, ["tracked.py"])
        tracked.assert_called_once_with(self.root)
        fallback.assert_not_called()

    def test_explicit_output_exclusion_has_precedence_and_covers_output_directory(self):
        graph=self.build({"build/out.json":"x","reports/a.js":"x"},excluded_paths=(self.root/"build/out.json",self.root/"reports"))
        self.assertEqual({x.file_path:x.reason for x in graph.scan.excluded_files},{"build/out.json":"explicit_output","reports/a.js":"explicit_output"})

    def test_small_exact_limit_greedy_and_oversized_symbol_units_cover_text(self):
        text="one\n"+"x"*24+"\nmid\n"+"y"*24+"\ntail\n"
        profile=dataclasses.replace(self.profile,read_unit_token_limit=5)
        graph=self.build({"m.py":text},[node("x","m.py",2,2),node("y","m.py",4,4)],profile=profile)
        units=sorted(graph.read_units,key=lambda x:x.start_line)
        self.assertEqual(units[0].start_line,1); self.assertEqual(units[-1].end_line,5)
        self.assertTrue(any(x.oversized_symbol for x in units))
        self.assertEqual([(x.start_line,x.end_line) for x in units],sorted((x.start_line,x.end_line) for x in units))

    def test_search_cap_preserves_all_occurrences_but_exposes_only_limit(self):
        profile=dataclasses.replace(self.profile,search_output_limit=2,refinement_threshold=2)
        graph=self.build({"a.py":"Alpha Alpha Alpha\n"},[node("a","a.py",1,1,"Alpha")],profile=profile)
        query=next(q for q in graph.query_nodes if q.term=="Alpha" and q.surface=="content")
        self.assertEqual((query.total_count,query.visible_count,query.truncated),(3,2,True))
        rows=[row for ref in query.occurrence_ranges for row in decode_occurrence_block(next(b for b in graph.occurrence_store if b.id==ref.block_id))]
        self.assertEqual(len(rows),3)

    def test_hidden_occurrences_affect_no_arrivals_cost_or_hints(self):
        profile = dataclasses.replace(self.profile, search_output_limit=2)
        files = {
            "a.py": "Needle visibleA\nNeedle visibleA\n",
            "b.py": "Needle visibleB\nNeedle visibleB\n",
            "c.py": "Needle hiddenC\nNeedle hiddenC\n",
        }
        nodes = [node(name, f"{name}.py", 1, 2, name.upper()) for name in "abc"]
        graph = self.build(files, nodes, profile=profile)
        query = next(
            item
            for item in graph.query_nodes
            if item.kind == "exact" and item.term == "Needle" and item.surface == "content"
        )
        result_edges = [
            edge
            for edge in graph.connections
            if edge.from_id == query.id and edge.kind == "result"
        ]
        visible_id = next(item.id for item in graph.readable_nodes if item.symbol_id == "a")
        self.assertEqual(query.arrival_node_ids, [visible_id])
        self.assertEqual([edge.to_id for edge in result_edges], [visible_id])
        hints = [graph.hint_store[edge.evidence["hint_id"]] for edge in result_edges]
        self.assertNotIn("hiddenC", json.dumps(hints))
        self.assertEqual(
            query.output_tokens,
            estimate_tokens("a.py:1:Needle visibleA\na.py:2:Needle visibleA"),
        )

    def test_search_cap_exact_boundary_is_not_truncated(self):
        profile=dataclasses.replace(self.profile,search_output_limit=2)
        graph=self.build({"a.py":"Alpha Alpha\n"},[node("a","a.py",1,1,"Alpha")],profile=profile)
        query=next(q for q in graph.query_nodes if q.term=="Alpha" and q.surface=="content")
        self.assertEqual((query.total_count,query.visible_count,query.truncated),(2,2,False))
        readable_id = next(item.id for item in graph.readable_nodes if item.symbol_id == "a")
        self.assertEqual(query.arrival_node_ids, [readable_id])

    def test_no_legacy_arrival_cap_below_at_and_above_fifty(self):
        files = {}
        nodes = []
        edges = []
        for term, count in (("Below", 49), ("AtLimit", 50), ("Above", 51), ("Capped", 52)):
            for index in range(count):
                path = f"{term}/{index:03d}.py"
                files[path] = f"{term}\n"
                nodes.append(node(f"{term}-{index}", path, 1, 1, term))
            driver_path = f"drivers/{term}.py"
            files[driver_path] = "Driver Driver\n"
            nodes.append(node(f"driver-{term}", driver_path, 1, 1, f"Driver{term}"))
            edges.append(
                GraphEdge(
                    f"driver-{term}",
                    f"{term}-0",
                    "CALLS",
                    resolution="exact",
                )
            )
        profile = dataclasses.replace(
            self.profile,
            read_query_candidate_limit=2,
            search_output_limit=51,
            refinement_threshold=1000,
        )
        graph = self.build(files, nodes, edges, profile=profile)
        groups = {
            query.term: query
            for query in graph.query_nodes
            if query.kind == "exact" and query.surface == "content"
        }

        self.assertEqual(
            {
                term: (
                    groups[term].total_count,
                    groups[term].visible_count,
                    len(groups[term].arrival_node_ids),
                    groups[term].truncated,
                )
                for term in ("Below", "AtLimit", "Above", "Capped")
            },
            {
                "Below": (49, 49, 49, False),
                "AtLimit": (50, 50, 50, False),
                "Above": (51, 51, 51, False),
                "Capped": (52, 51, 51, True),
            },
        )
        self.assertNotIn("max_arrival_nodes", graph.profile)

    def test_occurrence_blocks_round_trip_and_corruption_is_typed(self):
        graph=self.build({"a.py":"Alpha\n"},[node("a","a.py",1,1,"Alpha")])
        block=graph.occurrence_store[0]; self.assertEqual(len(decode_occurrence_block(block)),block.count)
        corrupt=dataclasses.replace(block,data=base64.b64encode(gzip.compress(b"[]",mtime=0)).decode())
        with self.assertRaisesRegex(ValueError,block.id): decode_occurrence_block(corrupt)

    def test_occurrence_block_boundary_order_hash_and_determinism(self):
        rows=[Occurrence("a.py",index+1,0,str(index),"code","a") for index in range(4097)]
        first,refs=encode_occurrence_blocks([rows],4096); second,_=encode_occurrence_blocks([rows],4096)
        self.assertEqual([b.count for b in first],[4096,1]); self.assertEqual(first,second)
        decoded=[row for block in first for row in decode_occurrence_block(block)]
        self.assertEqual(decoded,rows); self.assertEqual([r.count for r in refs[0]],[4096,1])
        self.assertEqual([(b.start, b.end) for b in first], [(0, 4096), (4096, 4097)])

    def test_build_uses_custom_occurrence_block_rows_for_query_ranges(self):
        profile = dataclasses.replace(
            self.profile,
            occurrence_block_rows=2,
            search_output_limit=10,
            refinement_threshold=1000,
        )
        graph = self.build(
            {"a.py": "Needle Needle Needle Needle Needle\n"},
            [node("needle", "a.py", 1, 1, "Needle")],
            profile=profile,
        )
        query = next(
            item for item in graph.query_nodes
            if (item.kind, item.term, item.surface)
            == ("exact", "Needle", "content")
        )
        blocks_by_id = {block.id: block for block in graph.occurrence_store}
        query_blocks = [blocks_by_id[item.block_id] for item in query.occurrence_ranges]
        first_start = query_blocks[0].start

        self.assertEqual(graph.profile["occurrence_block_rows"], 2)
        self.assertEqual(
            [(item.start, item.count) for item in query.occurrence_ranges],
            [(0, 2), (0, 2), (0, 1)],
        )
        self.assertEqual([block.count for block in query_blocks], [2, 2, 1])
        self.assertEqual(
            [(block.start, block.end) for block in query_blocks],
            [
                (first_start, first_start + 2),
                (first_start + 2, first_start + 4),
                (first_start + 4, first_start + 5),
            ],
        )
        self.assertEqual(
            [row.matched_text for row in decode_occurrence_ranges(
                query.occurrence_ranges,
                graph.occurrence_store,
            )],
            ["Needle"] * 5,
        )

    def test_occurrence_decoder_rejects_encoding_count_hash_and_range_corruption(self):
        rows = [Occurrence("a.py", 1, 0, "Alpha", "code", "a")]
        blocks, ranges = encode_occurrence_blocks([rows], 4096)
        block = blocks[0]
        corruptions = (
            dataclasses.replace(block, encoding="plain"),
            dataclasses.replace(block, count=2),
            dataclasses.replace(block, sha256="0" * 64),
        )
        for corrupt in corruptions:
            with self.subTest(corrupt=corrupt), self.assertRaises(OccurrenceStoreError):
                decode_occurrence_block(corrupt)
        with self.assertRaises(OccurrenceStoreError):
            decode_occurrence_ranges([OccurrenceRange(block.id, 1, 1)], blocks)
        self.assertEqual(decode_occurrence_ranges(ranges[0], blocks), rows)

    def test_read_unit_contract_below_exact_greedy_and_uncovered_ranges(self):
        symbols=[node("a","m.py",2,2),node("b","m.py",4,4)]
        contents={"m.py":"lead\naaaa\ngap\nbbbb\ntail"}
        small,small_units,_=build_readable_graph(symbols,["m.py"],contents,100)
        exact_tokens=small_units[0].read_cost.token_estimate
        _,exact_units,_=build_readable_graph(symbols,["m.py"],contents,exact_tokens)
        _,greedy,_=build_readable_graph(symbols,["m.py"],contents,2)
        self.assertEqual(len(small_units),1); self.assertEqual(len(exact_units),1)
        ordered=sorted(greedy,key=lambda unit:unit.start_line)
        self.assertEqual(ordered[0].start_line,1); self.assertEqual(ordered[-1].end_line,5)
        self.assertEqual([(x.start_line,x.end_line) for x in ordered],[(1,2),(3,5)])
        self.assertEqual(len({x.id for x in ordered}),2)

    def test_exact_content_path_list_zero_result_and_dedup_semantics(self):
        profile = dataclasses.replace(self.profile, read_query_candidate_limit=20)
        files = {
            "src/Needle.py": "Needle Needle\n",
            "plain.py": "plain\n",
            "drivers/a.py": "Driver Driver\n",
            "drivers/b.py": "Driver Driver\n",
        }
        nodes = [
            node("needle", "src/Needle.py", 1, 1, "Needle"),
            node("ghost", "plain.py", 1, 1, "Ghost"),
            node("driver-a", "drivers/a.py", 1, 1, "DriverA"),
            node("driver-b", "drivers/b.py", 1, 1, "DriverB"),
        ]
        edges = [
            GraphEdge("driver-a", "ghost", "CALLS", resolution="exact"),
            GraphEdge("driver-b", "ghost", "CALLS", resolution="exact"),
        ]
        graph = self.build(files, nodes, edges, profile=profile)
        identities = [
            (query.kind, query.term, query.surface, query.scope)
            for query in graph.query_nodes
        ]
        self.assertEqual(len(identities), len(set(identities)))

        content = next(
            query for query in graph.query_nodes
            if (query.kind, query.term, query.surface, query.scope)
            == ("exact", "Needle", "content", "repository")
        )
        path = next(
            query for query in graph.query_nodes
            if (query.kind, query.term, query.surface, query.scope)
            == ("exact", "Needle", "path", "repository")
        )
        listing = next(query for query in graph.query_nodes if query.kind == "list")
        zero = next(
            query for query in graph.query_nodes
            if (query.kind, query.term, query.surface, query.scope)
            == ("exact", "Ghost", "content", "repository")
        )

        self.assertEqual((content.total_count, content.visible_count), (2, 2))
        self.assertEqual(
            [row.file_path for row in decode_occurrence_ranges(content.occurrence_ranges, graph.occurrence_store)],
            ["src/Needle.py", "src/Needle.py"],
        )
        self.assertEqual((path.total_count, path.visible_count), (1, 1))
        self.assertEqual(
            [row.file_path for row in decode_occurrence_ranges(path.occurrence_ranges, graph.occurrence_store)],
            ["src/Needle.py"],
        )
        self.assertEqual(
            (listing.term, listing.surface, listing.scope, listing.total_count),
            (".", "path", "root", 4),
        )
        self.assertEqual((zero.total_count, zero.visible_count, zero.arrival_node_ids), (0, 0, []))
        ghost_queries = [
            query for query in graph.query_nodes
            if (query.kind, query.term, query.surface, query.scope)
            == ("exact", "Ghost", "content", "repository")
        ]
        self.assertEqual(len(ghost_queries), 1)
        self.assertEqual(len(ghost_queries[0].origin_node_ids), 2)
        self.assertEqual(ghost_queries[0].duplicate_suppressed_count, 1)

    def test_proxy_candidate_cap_below_at_and_above_exact_actions(self):
        expected_actions = [
            ("exact", "alpha", "content"),
            ("exact", "alpha", "path"),
            ("derived", "alphas", "content"),
            ("derived", "alphas", "path"),
            ("exact", "m.py", "path"),
        ]
        for cap, selected_count, filtered, truncated in (
            (4, 4, 1, True),
            (5, 5, 0, False),
            (6, 5, 0, False),
        ):
            with self.subTest(cap=cap):
                profile = dataclasses.replace(
                    self.profile,
                    read_query_candidate_limit=cap,
                    refinement_threshold=1000,
                )
                graph = self.build(
                    {"m.py": "alpha alpha\n"},
                    [node("alpha", "m.py", 1, 1, "alpha")],
                    profile=profile,
                )
                actions = {
                    (query.kind, query.term, query.surface)
                    for query in graph.query_nodes
                    if query.kind != "list"
                }
                self.assertEqual(actions, set(expected_actions[:selected_count]))
                for query in graph.query_nodes:
                    if query.kind == "list":
                        continue
                    self.assertEqual(query.candidate_filtered_count, filtered)
                    self.assertEqual(query.candidate_cap_truncated, truncated)

    def test_hint_and_refinement_edges_obey_caps(self):
        profile=dataclasses.replace(self.profile,search_output_limit=2,refinement_threshold=1,hint_query_limit=1,refinement_query_limit=1)
        graph=self.build({"a.py":"Alpha Alpha\n","pkg/b.py":"Alpha\n"},[node("a","a.py",1,1,"Alpha"),node("b","pkg/b.py",1,1,"Alpha")],profile=profile)
        by_source={}
        for edge in graph.connections:
            if edge.kind in ("hint_query","refines"): by_source.setdefault((edge.from_id,edge.kind),[]).append(edge)
        self.assertTrue(all(len(values)<=1 for values in by_source.values()))
        self.assertTrue(any(q.kind=="refinement" for q in graph.query_nodes))

    def test_hint_query_edges_are_nonempty_exact_and_capped(self):
        profile = dataclasses.replace(
            self.profile,
            read_query_candidate_limit=20,
            hint_query_limit=2,
            refinement_threshold=1000,
        )
        files = {
            "source.py": "Needle Alpha Beta Gamma\nNeedle\n",
            "alpha.py": "Alpha Alpha\n",
            "beta.py": "Beta Beta\n",
            "gamma.py": "Gamma Gamma\n",
        }
        nodes = [
            node("source", "source.py", 1, 2, "Needle"),
            node("alpha", "alpha.py", 1, 1, "Alpha"),
            node("beta", "beta.py", 1, 1, "Beta"),
            node("gamma", "gamma.py", 1, 1, "Gamma"),
        ]
        edges = [
            GraphEdge("source", target, "CALLS", resolution="exact")
            for target in ("alpha", "beta", "gamma")
        ]
        graph = self.build(files, nodes, edges, profile=profile)
        source_query = next(
            query for query in graph.query_nodes
            if (query.kind, query.term, query.surface)
            == ("exact", "Needle", "content")
        )
        expected_targets = {
            term: next(
                query.id for query in graph.query_nodes
                if (query.kind, query.term, query.surface)
                == ("exact", term, "content")
            )
            for term in ("Alpha", "Beta")
        }
        hint_edges = [
            edge for edge in graph.connections
            if edge.from_id == source_query.id and edge.kind == "hint_query"
        ]

        self.assertEqual(
            sorted((edge.evidence["term"], edge.to_id) for edge in hint_edges),
            [(term, expected_targets[term]) for term in ("Alpha", "Beta")],
        )
        self.assertNotIn("Gamma", {edge.evidence["term"] for edge in hint_edges})

    def test_refinement_recurses_to_depth_and_every_child_is_a_strict_subset(self):
        profile = dataclasses.replace(
            self.profile,
            refinement_threshold=1,
            refinement_query_limit=1,
            refinement_depth_limit=2,
        )
        files = {
            "d1/sub1/a.py": "Needle Needle\n",
            "d1/sub2/b.py": "Needle Needle\n",
            "d2/c.py": "Needle Needle\n",
        }
        nodes = [
            node("a", "d1/sub1/a.py", 1, 1, "A"),
            node("b", "d1/sub2/b.py", 1, 1, "B"),
            node("c", "d2/c.py", 1, 1, "C"),
        ]
        graph = self.build(files, nodes, profile=profile)
        queries = {query.id: query for query in graph.query_nodes}
        refines = [edge for edge in graph.connections if edge.kind == "refines"]
        self.assertTrue(refines)
        self.assertEqual(max(query.refinement_depth for query in queries.values()), 2)
        blocks = graph.occurrence_store
        for edge in refines:
            parent = queries[edge.from_id]
            child = queries[edge.to_id]
            parent_rows = decode_occurrence_ranges(parent.occurrence_ranges, blocks)
            child_rows = decode_occurrence_ranges(child.occurrence_ranges, blocks)
            self.assertLess(len(child_rows), len(parent_rows))
            self.assertTrue(set(child_rows) < set(parent_rows))
            self.assertEqual(child.refinement_depth, parent.refinement_depth + 1)

    def test_hints_are_a_projection_of_visible_match_lines(self):
        profile = dataclasses.replace(self.profile, search_output_limit=1)
        graph = self.build(
            {"a.py": "def Needle(otherName):\n    return Needle(otherName)\n"},
            [node("a", "a.py", 1, 2, "Needle")],
            profile=profile,
        )
        query = next(
            item
            for item in graph.query_nodes
            if item.kind == "exact" and item.term == "Needle" and item.surface == "content"
        )
        edge = next(
            item
            for item in graph.connections
            if item.from_id == query.id and item.kind == "result"
        )
        hint = graph.hint_store[edge.evidence["hint_id"]]
        self.assertEqual(hint["path"], "a.py")
        self.assertEqual(hint["file_name"], "a.py")
        self.assertEqual(hint["symbol_name"], "Needle")
        self.assertEqual(hint["roles"], ["declaration"])
        self.assertEqual(hint["identifiers"], ["Needle", "def", "otherName"])

    def test_framework_unique_is_direct_and_narrowing_uses_query(self):
        unique=GraphEdge("a","b","LINK",metadata={"framework_rule":{"id":"r.unique","specificity":"unique"}})
        narrowing=GraphEdge("a","c","LINK",metadata={"framework_rule":{"id":"r.group","specificity":"narrowing"}})
        graph=self.build({"a.py":"Alpha Alpha\n","b.py":"Beta\n","c.py":"Gamma\n"},[node("a","a.py",1,1,"Alpha"),node("b","b.py",1,1,"Beta"),node("c","c.py",1,1,"Gamma")],[unique,narrowing])
        readable_ids = {
            item.symbol_id: item.id
            for item in graph.readable_nodes
            if item.symbol_id is not None
        }
        self.assertTrue(any(edge.from_id==readable_ids["a"] and edge.to_id==readable_ids["b"] and edge.specificity=="unique" for edge in graph.connections))
        query=next(query for query in graph.query_nodes if query.kind=="framework" and query.term=="r.group")
        self.assertEqual(query.arrival_node_ids,[readable_ids["c"]])
        self.assertFalse(any(edge.from_id==readable_ids["a"] and edge.to_id==readable_ids["c"] for edge in graph.connections))

    def test_ambiguous_connection_keeps_target_and_candidates_in_query(self):
        ambiguous = GraphEdge("a", "b", "CALLS", candidates=["c"])
        graph = self.build(
            {"a.py": "Alpha Alpha\n", "b.py": "Beta\n", "c.py": "Beta\n"},
            [node("a", "a.py", 1, 1, "Alpha"), node("b", "b.py", 1, 1, "Beta"), node("c", "c.py", 1, 1, "Beta")],
            [ambiguous],
        )
        query = next(item for item in graph.query_nodes if item.term == "relation:CALLS")
        readable_ids = {
            item.symbol_id: item.id
            for item in graph.readable_nodes
            if item.symbol_id is not None
        }
        self.assertEqual(query.arrival_node_ids, sorted([readable_ids["b"], readable_ids["c"]]))
        generator = next(
            edge
            for edge in graph.connections
            if edge.from_id == readable_ids["a"] and edge.to_id == query.id
        )
        self.assertEqual(generator.evidence["relation"], "CALLS")

    def test_entry_documents_record_injection(self):
        graph=self.build({"AGENTS.md":"rules\n","README.md":"intro\n"})
        self.assertEqual([(x.file_path,x.injected) for x in graph.entry_documents],[('AGENTS.md',True),('README.md',False)])

    def test_rerun_with_prior_output_does_not_grow(self):
        seed = self.build({"a.py":"Alpha Alpha\n"},[node("a","a.py",1,1,"Alpha")])
        files = {
            "a.py": "Alpha Alpha\n",
            "renamed-output.data": graph_to_json(seed),
        }
        rerun = self.build(files, [node("a", "a.py", 1, 1, "Alpha")])
        excluded = [(item.file_path, item.reason) for item in rerun.scan.excluded_files]
        self.assertEqual(excluded, [("renamed-output.data", "analyzer_artifact")])

        def normalized(graph):
            payload = graph_to_dict(graph)
            payload["scan"]["excluded_files"] = []
            payload["scan"]["exclusion_counts"] = {}
            return payload

        self.assertEqual(normalized(seed), normalized(rerun))
        indexed_paths = {
            row.file_path
            for query in rerun.query_nodes
            for row in decode_occurrence_ranges(query.occurrence_ranges, rerun.occurrence_store)
        }
        self.assertNotIn("renamed-output.data", indexed_paths)

    def test_profile_invalid_version_type_range_and_yaml_are_typed(self):
        valid = yaml.safe_load(default_profile_path().read_text(encoding="utf-8"))
        cases = {
            "malformed": "[",
            "version": yaml.safe_dump({**valid, "version": 2}),
            "version_type": yaml.safe_dump({**valid, "version": "3"}),
            "limit_type": yaml.safe_dump({
                **valid,
                "limits": {**valid["limits"], "search_output_limit": "30"},
            }),
            "limit_bool": yaml.safe_dump({
                **valid,
                "limits": {**valid["limits"], "search_output_limit": True},
            }),
            "positive_range": yaml.safe_dump({
                **valid,
                "limits": {**valid["limits"], "search_output_limit": 0},
            }),
            "context_range": yaml.safe_dump({
                **valid,
                "limits": {**valid["limits"], "context_lines": -1},
            }),
            "boolean_type": yaml.safe_dump({**valid, "tracked_files_only": "yes"}),
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                path = self.root / f"{name}.yaml"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ProfileError):
                    load_profile(path)

    def test_diff_rejects_every_non_v3_input_and_is_deterministic(self):
        valid={"schema_version":"3","readable_nodes":[],"query_nodes":[],"connections":[],"profile":{}}
        for version in (None,"1","2"):
            with self.subTest(version=version), self.assertRaises(AgentViewInputError):
                diff_agent_view({**valid,"schema_version":version},valid)
        self.assertEqual(diff_agent_view(valid,valid),diff_agent_view(valid,valid))
