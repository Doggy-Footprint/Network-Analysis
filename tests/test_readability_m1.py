"""VO-8, VO-9, and the M1 slice of VO-10 for report/m1 (M1 report generation
and report/m1/templates/graph_model.js).

VO-8 (FR-8, QR-1, QR-3, QR-7, C-13, C-15): equivalence partitioning over
{인라인 확인, 오프라인, 크기, vendor 누락, 라이선스·버전} for `generate_report`.

VO-9 (FR-9, FR-10, C-14, spec v2): boundary value (2-value) over
{300개, 301개, compound parent, 짧은 라벨, focus 3목록 순서} for
`ReportGraphModel.build`/`focus`. Expected short labels are hand-computed
from FR-1's algorithm (not by calling report/shared/labels.py), matching the
independent-oracle style of tests/test_readability_labels.py. Per v2's
Signature, `build` returns all nodes with `default_visible`/`capped`/
`limit`/`total`, and `focus` concatenates 3 lists (weight = token_estimate
or total_count + connection count; connection count = from/to occurrences);
all 3 focus lists' orderings, including the connection-count list, are now
hand-computed fixtures rather than left unverified.

VO-10 (QR-5, M1 slice): metamorphic — regenerating from the same input twice
yields byte-identical HTML.

VO-16 (FR-17, FR-18, spec v4): decision table over {같은 read unit 3
readable→1건 dup 3, 같은 term 2 query→1건 dup 2(omitted 큰 쪽), 심볼 label→
`f.py:Sym`, label==file_path→`f.py`} for `ReportGraphModel.build`/`focus`.
Hand-computed from FR-17/FR-18's rules.

v4 correction to VO-9's `TestVO9GraphModelFocus._fixture`: previously every
readable node in that fixture defaulted to the *same* `read_unit_id`
("unit:all"), which FR-17's new token-list dedup (VO-16) would now collapse
into a single item, breaking group 1's top-5 expectations. `_readable_node`'s
default `unit_id` is now unique per node (derived from the node id) unless a
test explicitly shares one to exercise dedup (VO-16). No VO-9 *build* test
needed a change: FR-18's label composition only changes output when
`label != file_path`, and every existing VO-9 fixture already used
`label == file_path`.

VO-20 (FR-22, spec v5): boundary value (2-value) over {weight 20위
always_label=true, 21위 false, 20/21위 동점 id 오름차순} for
`ReportGraphModel.build`'s new `always_label` node field (unit only; the
fit-scale/directory-label-legibility and hover/zoom coverage items are RV-1's
review, not this file's). Weight here is `token_estimate + connection count`
per the v2 Signature; expected rankings are hand-computed directly from the
fixtures' `token_estimate` values (with 0 connections), independent of the
implementation.

MUT-3 correction (evidence-defect review): every VO-9 C-14 fixture and every
VO-20 fixture previously used 0 connections, so a mutant that drops the
"+ connection count" term from the weight formula (both the readable
`token_estimate + connections` and the query `total_count + connections`
variants) passed every test in this file. Added, with hand-computed
arithmetic in comments at each site:
  - `TestVO9GraphModelBuild.test_301_readable_nodes_where_connections_reverse_the_excluded_node`
    (VO-9/C-14): a 301-node cap case where a low-token_estimate readable
    node's connections raise its weight above another node's, so a
    *different* node (not the lowest token_estimate) is the one excluded.
  - `TestVO9GraphModelBuild.test_301_nodes_query_node_connection_count_reverses_the_excluded_node`
    (VO-9/C-14): the same reversal using a query node whose weight is
    `total_count + connection count`, mixed with readable nodes in one 301-
    node cap.
  - `TestVO20AlwaysLabelWeightRanking.test_connection_count_moves_a_node_across_the_top_20_boundary`
    (VO-20): connection count moves one node into the top 20 and pushes a
    higher-token_estimate, connection-less node out, at the 20/21 boundary.
No other VO-9/VO-20 fixtures needed a change; the 300-node (non-capped) case
and the label/compound-parent cases don't exercise the weight ordering at
all, and the existing 301/tie-break cases are still valid boundary evidence
for the id-tiebreak and cap-arithmetic items independent of this defect.
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from report.m1.generate import generate_report
from report.shared.document import ReportOutputError

from tests.test_report_m1 import _assert_offline, _payload, _payload_text

ROOT = Path(__file__).resolve().parents[1]
GRAPH_MODEL = ROOT / "report/m1/templates/graph_model.js"
VENDOR_DIR = ROOT / "report/m1/vendor"


def _run_graph_model(function_call):
    script = f"const model = require({json.dumps(str(GRAPH_MODEL))}); console.log(JSON.stringify({function_call}));"
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def _readable_node(node_id, file_path, label, token_estimate=1, unit_id=None):
    # v4/FR-17: default to a unique read_unit_id per node (derived from the
    # node id) so existing fixtures aren't accidentally deduped by the new
    # token-list dedup rule; pass `unit_id` explicitly to share one on purpose.
    return {
        "id": node_id, "file_path": file_path, "symbol_id": None, "label": label,
        "kind": "file", "start_line": 1, "end_line": 1,
        "read_cost": {"token_estimate": token_estimate, "char_count": token_estimate * 4, "line_count": 1},
        "flags": [], "read_unit_id": unit_id if unit_id is not None else f"unit:{node_id}",
    }


def _read_unit_entry(unit_id, file_path="a"):
    return {"id": unit_id, "file_path": file_path, "start_line": 1, "end_line": 1, "symbol_ids": [], "read_cost": {"token_estimate": 1, "char_count": 1, "line_count": 1}, "oversized_symbol": False}


def _query_node(id_, term, total, visible, truncated):
    return {
        "id": id_, "term": term, "kind": "exact", "surface": "content", "scope": "repository",
        "clue_kinds": [], "origin_node_ids": [], "rule_id": None, "source_terms": [],
        "occurrence_ranges": [], "occurrence_digest": ("d" * 64), "arrival_node_ids": [],
        "total_count": total, "visible_count": visible, "truncated": truncated, "output_tokens": visible,
        "duplicate_suppressed_count": 0, "candidate_filtered_count": 0, "candidate_cap_truncated": False,
        "refinement_depth": 0,
    }


def _read_units_for(nodes):
    """One read_units entry per distinct read_unit_id among `nodes`, so a
    fixture's read_units stay self-consistent regardless of how many
    distinct (or shared) unit ids the readable nodes use."""
    seen = []
    for node in nodes:
        if node["read_unit_id"] not in seen:
            seen.append(node["read_unit_id"])
    return [_read_unit_entry(unit_id, file_path=nodes[0]["file_path"] if nodes else "a") for unit_id in seen]


@unittest.skipUnless(shutil.which("node"), "node is required to run the JS graph model")
class TestVO9GraphModelBuild(unittest.TestCase):
    """VO-9: boundary value (2-value) over the 5 declared coverage items."""

    def test_300_readable_nodes_are_all_default_visible_and_not_capped(self):
        # TD-4 (v2): build() now returns ALL nodes plus capped/limit/total/
        # default_visible metadata, rather than truncating the nodes array.
        value = _payload("m1-300")
        nodes = [_readable_node(f"node:{i:04d}", f"src/module_{i:04d}.py", f"src/module_{i:04d}.py", token_estimate=i + 1) for i in range(300)]
        value["readable_nodes"] = nodes
        value["read_units"] = _read_units_for(nodes)
        value["query_nodes"] = []
        value["connections"] = []
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return {{length: built.nodes.length, capped: built.capped, limit: built.limit, total: built.total, "
            f"allDefaultVisible: built.nodes.every(n => n.default_visible === true)}}; }})()"
        )
        self.assertEqual(result["length"], 300)
        self.assertEqual(result["total"], 300)
        self.assertEqual(result["limit"], 300)
        self.assertFalse(result["capped"])
        self.assertTrue(result["allDefaultVisible"])

    def test_301_readable_nodes_are_capped_with_lowest_weight_node_excluded(self):
        # TD-4 (v2): weight = token_estimate + connection count. With no
        # connections and token_estimate = i + 1, node:0000 (token=1) has the
        # single lowest weight and must be the one excluded from default_visible.
        value = _payload("m1-301")
        nodes = [_readable_node(f"node:{i:04d}", f"src/module_{i:04d}.py", f"src/module_{i:04d}.py", token_estimate=i + 1) for i in range(301)]
        value["readable_nodes"] = nodes
        value["read_units"] = _read_units_for(nodes)
        value["query_nodes"] = []
        value["connections"] = []
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return {{length: built.nodes.length, capped: built.capped, limit: built.limit, total: built.total, "
            f"visible: built.nodes.filter(n => n.default_visible === true).map(n => n.id), "
            f"hidden: built.nodes.filter(n => n.default_visible !== true).map(n => n.id)}}; }})()"
        )
        self.assertEqual(result["length"], 301)
        self.assertEqual(result["total"], 301)
        self.assertEqual(result["limit"], 300)
        self.assertTrue(result["capped"])
        self.assertEqual(len(result["visible"]), 300)
        self.assertEqual(result["hidden"], ["node:0000"])
        self.assertNotIn("node:0000", result["visible"])

    def test_301_readable_nodes_where_connections_reverse_the_excluded_node(self):
        # MUT-3: weight = token_estimate + connection count (FR-9/FR-10
        # Signature). Without the connection-count term, node:0000 (the
        # single lowest token_estimate=1) would be the excluded node. Giving
        # node:0000 5 connections (to node:0002..node:0006) raises its
        # weight above node:0001's, so node:0001 becomes the new unique
        # minimum and must be the excluded node instead.
        #
        # Hand-computed weights (token_estimate=i+1 for node:{i:04d}):
        #   node:0000: token=1, connections=5 (to 0002..0006) -> weight=6
        #   node:0001: token=2, connections=0                 -> weight=2  <- minimum
        #   node:0002: token=3, connections=1 (from 0000)     -> weight=4
        #   node:0003: token=4, connections=1                 -> weight=5
        #   node:0004: token=5, connections=1                 -> weight=6
        #   node:0005: token=6, connections=1                 -> weight=7
        #   node:0006: token=7, connections=1                 -> weight=8
        #   node:0007..node:0300: token=i+1, connections=0    -> weight=i+1 (>=8)
        # Every other weight is >= 4, so node:0001 (weight 2) is the unique
        # minimum: it must be excluded, and node:0000 (weight 6, the lowest
        # token_estimate) must NOT be excluded.
        value = _payload("m1-301-conn")
        nodes = [_readable_node(f"node:{i:04d}", f"src/module_{i:04d}.py", f"src/module_{i:04d}.py", token_estimate=i + 1) for i in range(301)]
        value["readable_nodes"] = nodes
        value["read_units"] = _read_units_for(nodes)
        value["query_nodes"] = []
        value["connections"] = [
            {"id": f"c:conn-{i}", "from_id": "node:0000", "to_id": f"node:{i:04d}", "kind": "generates", "specificity": "narrowing", "evidence": {}}
            for i in range(2, 7)
        ]
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return {{hidden: built.nodes.filter(n => n.default_visible !== true).map(n => n.id)}}; }})()"
        )
        self.assertEqual(result["hidden"], ["node:0001"])
        self.assertNotIn("node:0000", result["hidden"])

    def test_301_nodes_query_node_connection_count_reverses_the_excluded_node(self):
        # MUT-3: query weight = total_count + connection count (Signature).
        # "low_r" (readable, token_estimate=2, 0 connections) and
        # "q_boundary" (query, total_count=1, 5 connections) are the two
        # lowest-weight nodes among 301 total; 299 filler readable nodes
        # with token_estimate >= 1000 always rank above both regardless of
        # a handful of +1 connection bumps.
        #
        # Hand-computed weights:
        #   low_r:      weight = 2 + 0 = 2   <- minimum, must be excluded
        #   q_boundary: weight = 1 + 5 = 6   <- must remain visible
        # Without the connection-count term on the query weight,
        # q_boundary's weight would be 1 (< low_r's 2), making q_boundary
        # the excluded node instead of low_r.
        fillers = [_readable_node(f"filler:{i:04d}", f"src/filler_{i:04d}.py", f"src/filler_{i:04d}.py", token_estimate=1000 + i * 10) for i in range(299)]
        low_r = _readable_node("low_r", "src/low_r.py", "src/low_r.py", token_estimate=2)
        readable_nodes = fillers + [low_r]
        query_node = _query_node("q_boundary", "term", total=1, visible=1, truncated=False)
        value = _payload("m1-301-query-conn")
        value["readable_nodes"] = readable_nodes
        value["read_units"] = _read_units_for(readable_nodes)
        value["query_nodes"] = [query_node]
        value["connections"] = [
            {"id": f"c:q-{i}", "from_id": "q_boundary", "to_id": f"filler:{i:04d}", "kind": "generates", "specificity": "narrowing", "evidence": {}}
            for i in range(5)
        ]
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return {{hidden: built.nodes.filter(n => n.default_visible !== true).map(n => n.id), total: built.total}}; }})()"
        )
        self.assertEqual(result["total"], 301)
        self.assertEqual(result["hidden"], ["low_r"])
        self.assertNotIn("q_boundary", result["hidden"])

    def test_short_labels_resolve_basename_conflicts_like_FR1(self):
        value = _payload("m1-labels")
        nodes = [
            _readable_node("node:r1", "app/src/ui/Config.py", "app/src/ui/Config.py"),
            _readable_node("node:r2", "app/src/data/Config.py", "app/src/data/Config.py"),
            _readable_node("node:r3", "single.py", "single.py"),
        ]
        value["readable_nodes"] = nodes
        value["read_units"] = _read_units_for(nodes)
        value["query_nodes"] = []
        value["connections"] = []
        result = _run_graph_model(f"model.build({json.dumps(value)}).nodes.map(n => ({{id: n.id, label: n.label, full_label: n.full_label}}))")
        by_id = {item["id"]: item for item in result}
        self.assertEqual(by_id["node:r1"]["label"], "ui/Config.py")
        self.assertEqual(by_id["node:r2"]["label"], "data/Config.py")
        self.assertEqual(by_id["node:r3"]["label"], "single.py")
        self.assertEqual(by_id["node:r1"]["full_label"], "app/src/ui/Config.py")
        self.assertEqual(by_id["node:r2"]["full_label"], "app/src/data/Config.py")

    def test_readable_nodes_are_placed_under_a_directory_compound_parent(self):
        value = _payload("m1-compound")
        nodes = [_readable_node("node:r1", "app/src/ui/Config.py", "app/src/ui/Config.py")]
        value["readable_nodes"] = nodes
        value["read_units"] = _read_units_for(nodes)
        value["query_nodes"] = []
        value["connections"] = []
        elements = _run_graph_model(f"model.build({json.dumps(value)}).elements")
        node_elements = [item for item in elements if "source" not in item.get("data", {})]
        own = next(item for item in node_elements if item["data"]["id"] == "node:r1")
        parent_id = own["data"].get("parent")
        self.assertTrue(parent_id, "expected readable node to have a compound directory parent")
        self.assertTrue(any(item["data"]["id"] == parent_id and item is not own for item in node_elements),
                         "expected the referenced parent id to exist as its own element")


def _group_by_consecutive_reason(items):
    """TD-5: focus() concatenates 3 lists that each share one `reason`
    string; group the flat array back into those 3 lists by consecutive
    `reason` runs (no assumption about the literal reason text)."""
    groups = []
    for item in items:
        if groups and groups[-1][0] == item["reason"]:
            groups[-1][1].append(item)
        else:
            groups.append((item["reason"], [item]))
    return [group for _, group in groups]


@unittest.skipUnless(shutil.which("node"), "node is required to run the JS graph model")
class TestVO9GraphModelFocus(unittest.TestCase):
    """VO-9: focus() 3목록 순서 = [token_estimate top-n readable] ++
    [truncated-omitted top-n query] ++ [연결 수 top-n readable+query], each
    sharing one `reason` string per list (per v2 Signature). All three
    expected orderings are hand-computed from the fixture below."""

    def _fixture(self):
        value = _payload("m1-focus")
        # Group 1 pool: 6 readable nodes with distinct token_estimate,
        # top-5 by value desc, id asc: tok:5(60),tok:4(50),tok:3(40),tok:2(30),tok:1(20); tok:0(10) excluded.
        token_nodes = [_readable_node(f"tok:{i}", f"a/tok{i}.py", f"a/tok{i}.py", token_estimate=(i + 1) * 10) for i in range(6)]
        # Group 3 pool: readable nodes with token_estimate=1 (below tok:1's 20,
        # so they never leak into group 1's top-5) but distinct connection counts.
        # Connections: hub->r1..hub->r6 (hub degree 6, each r degree 1), plus
        # q1->hub (hub degree 7, q1 degree 1). Hand-computed top-5 by
        # connection count desc, id asc on ties:
        #   hub=7; tie at 1: {conn:q1, conn:r1..conn:r6} sorted asc -> q1,r1,r2,r3,r4,r5,r6
        #   top5 = hub, q1, r1, r2, r3 (r4..r6 excluded).
        connection_nodes = [_readable_node("conn:hub", "c/hub.py", "c/hub.py", token_estimate=1)]
        connection_nodes += [_readable_node(f"conn:r{i}", f"c/r{i}.py", f"c/r{i}.py", token_estimate=1) for i in range(1, 7)]
        all_readable_nodes = token_nodes + connection_nodes
        value["readable_nodes"] = all_readable_nodes
        # v4/FR-17: each node above has a distinct (per-node) read_unit_id via
        # _readable_node's default, so none of them are deduped by the new
        # token-list dedup rule — that dedup behavior is exercised separately
        # in TestVO16GraphModelDedupAndSymbolLabels.
        value["read_units"] = _read_units_for(all_readable_nodes)

        def _query(id_, total, visible, truncated):
            return {
                "id": id_, "term": id_, "kind": "exact", "surface": "content", "scope": "repository",
                "clue_kinds": [], "origin_node_ids": [], "rule_id": None, "source_terms": [],
                "occurrence_ranges": [], "occurrence_digest": ("d" * 64), "arrival_node_ids": [],
                "total_count": total, "visible_count": visible, "truncated": truncated, "output_tokens": visible,
                "duplicate_suppressed_count": 0, "candidate_filtered_count": 0, "candidate_cap_truncated": False,
                "refinement_depth": 0,
            }

        # Group 2 pool: 6 truncated queries, distinct omitted = total - visible
        # (visible fixed at 5): query:0=15 .. query:5=115 -> top5 desc:
        # query:5,query:4,query:3,query:2,query:1 (query:0 excluded, 6th largest).
        query_nodes = [_query(f"query:{i}", (i + 1) * 20, 5, True) for i in range(6)]
        # Must be excluded from group 2 (not truncated) regardless of a large total.
        query_nodes.append(_query("query:not-truncated", 999999, 999999, False))
        # Group 3 participant: non-truncated (so excluded from group 2), degree 1 (from q1->hub).
        query_nodes.append(_query("conn:q1", 1, 1, False))
        value["query_nodes"] = query_nodes

        connections = [
            {"id": f"c:hub-r{i}", "from_id": "conn:hub", "to_id": f"conn:r{i}", "kind": "generates", "specificity": "narrowing", "evidence": {}}
            for i in range(1, 7)
        ]
        connections.append({"id": "c:q1-hub", "from_id": "conn:q1", "to_id": "conn:hub", "kind": "generates", "specificity": "narrowing", "evidence": {}})
        value["connections"] = connections
        return value

    def _focus_groups(self, value, n=5):
        result = _run_graph_model(f"model.focus({json.dumps(value)}, {n})")
        groups = _group_by_consecutive_reason(result)
        self.assertEqual(len(groups), 3, f"expected 3 reason-grouped lists, got {len(groups)}: {result}")
        return groups

    def test_group1_token_estimate_top5_readable_nodes_are_correctly_ordered(self):
        groups = self._focus_groups(self._fixture())
        ids = [item["id"] for item in groups[0]]
        self.assertEqual(ids, ["tok:5", "tok:4", "tok:3", "tok:2", "tok:1"])

    def test_group2_truncated_query_omitted_top5_excludes_non_truncated(self):
        groups = self._focus_groups(self._fixture())
        ids = [item["id"] for item in groups[1]]
        self.assertEqual(ids, ["query:5", "query:4", "query:3", "query:2", "query:1"])
        self.assertNotIn("query:not-truncated", ids)
        self.assertNotIn("conn:q1", ids)

    def test_group3_connection_count_top5_spans_readable_and_query_with_id_tiebreak(self):
        groups = self._focus_groups(self._fixture())
        items = groups[2]
        self.assertEqual([item["id"] for item in items], ["conn:hub", "conn:q1", "conn:r1", "conn:r2", "conn:r3"])
        self.assertEqual([item["value"] for item in items], [7, 1, 1, 1, 1])

    def test_focus_is_deterministic_across_repeated_calls(self):
        value = self._fixture()
        call = f"model.focus({json.dumps(value)}, 5)"
        first = _run_graph_model(call)
        second = _run_graph_model(call)
        self.assertEqual(first, second)


@unittest.skipUnless(shutil.which("node"), "node is required to run the JS graph model")
class TestVO16GraphModelDedupAndSymbolLabels(unittest.TestCase):
    """VO-16 (FR-17, FR-18): decision table over the 4 declared coverage
    items. All expected values are hand-computed from FR-17/FR-18's rules."""

    def _base_payload(self, tag):
        # A filler readable node keeps the token-list `reason` run non-empty
        # by default, so `_group_by_consecutive_reason`'s positional groups
        # (0=token, 1=query, 2=connection) stay valid for tests that only
        # care about the query list and don't set their own readable_nodes.
        value = _payload(tag)
        filler = _readable_node("zzz-filler", "zzz/filler.py", "zzz/filler.py", token_estimate=1)
        value["readable_nodes"] = [filler]
        value["query_nodes"] = []
        value["connections"] = []
        value["read_units"] = _read_units_for([filler])
        return value

    def test_3_readable_nodes_sharing_one_read_unit_collapse_to_1_with_duplicate_count_3(self):
        # Same token_estimate (15) on all 3 so the representative's `value`
        # is unambiguous regardless of which node is kept; id-ascending
        # picks "d1" (< "d2" < "d3") as the representative per FR-17.
        nodes = [
            _readable_node("d3", "x/d3.py", "x/d3.py", token_estimate=15, unit_id="shared-unit"),
            _readable_node("d1", "x/d1.py", "x/d1.py", token_estimate=15, unit_id="shared-unit"),
            _readable_node("d2", "x/d2.py", "x/d2.py", token_estimate=15, unit_id="shared-unit"),
        ]
        value = self._base_payload("vo16-token-dedup")
        value["readable_nodes"] = nodes
        value["read_units"] = _read_units_for(nodes)
        groups = _group_by_consecutive_reason(_run_graph_model(f"model.focus({json.dumps(value)}, 5)"))
        token_list = groups[0]
        self.assertEqual(len(token_list), 1)
        self.assertEqual(token_list[0]["id"], "d1")
        self.assertEqual(token_list[0]["value"], 15)
        self.assertEqual(token_list[0]["duplicate_count"], 3)

    def test_2_truncated_queries_with_same_term_collapse_keeping_larger_omitted(self):
        # omitted = total - visible. "q-bigger" (omitted 90) must be kept
        # over "q-smaller" (omitted 50) even though its id sorts higher,
        # proving omitted (not id) is the primary key here.
        queries = [
            _query_node("q-bigger", "dup-term", total=100, visible=10, truncated=True),   # omitted 90
            _query_node("q-smaller", "dup-term", total=100, visible=50, truncated=True),   # omitted 50
        ]
        value = self._base_payload("vo16-query-dedup-distinct")
        value["query_nodes"] = queries
        groups = _group_by_consecutive_reason(_run_graph_model(f"model.focus({json.dumps(value)}, 5)"))
        query_list = groups[1]
        self.assertEqual(len(query_list), 1)
        self.assertEqual(query_list[0]["id"], "q-bigger")
        self.assertEqual(query_list[0]["value"], 90)
        self.assertEqual(query_list[0]["duplicate_count"], 2)

    def test_2_truncated_queries_with_same_term_and_tied_omitted_break_by_id_ascending(self):
        queries = [
            _query_node("term-b", "dup-term", total=100, visible=50, truncated=True),  # omitted 50
            _query_node("term-a", "dup-term", total=100, visible=50, truncated=True),  # omitted 50 (tie)
        ]
        value = self._base_payload("vo16-query-dedup-tie")
        value["query_nodes"] = queries
        groups = _group_by_consecutive_reason(_run_graph_model(f"model.focus({json.dumps(value)}, 5)"))
        query_list = groups[1]
        self.assertEqual(len(query_list), 1)
        self.assertEqual(query_list[0]["id"], "term-a")
        self.assertEqual(query_list[0]["value"], 50)
        self.assertEqual(query_list[0]["duplicate_count"], 2)

    def test_symbol_label_composes_short_file_label_and_symbol_name(self):
        # "pkg/f.py" and "other/g.py" have distinct basenames -> no FR-1
        # conflict, so short_labels resolves "pkg/f.py" to "f.py" directly.
        nodes = [
            _readable_node("sym-node", "pkg/f.py", "Sym"),
            _readable_node("other-node", "other/g.py", "other/g.py"),
        ]
        value = self._base_payload("vo16-symbol-label")
        value["readable_nodes"] = nodes
        value["read_units"] = _read_units_for(nodes)
        result = _run_graph_model(f"model.build({json.dumps(value)}).nodes.map(n => ({{id: n.id, label: n.label, full_label: n.full_label}}))")
        by_id = {item["id"]: item for item in result}
        self.assertEqual(by_id["sym-node"]["label"], "f.py:Sym")
        self.assertEqual(by_id["sym-node"]["full_label"], "pkg/f.py:Sym")

    def test_label_equal_to_file_path_gets_the_short_file_label_only(self):
        nodes = [
            _readable_node("sym-node", "pkg/f.py", "Sym"),
            _readable_node("other-node", "other/g.py", "other/g.py"),
        ]
        value = self._base_payload("vo16-plain-label")
        value["readable_nodes"] = nodes
        value["read_units"] = _read_units_for(nodes)
        result = _run_graph_model(f"model.build({json.dumps(value)}).nodes.map(n => ({{id: n.id, label: n.label, full_label: n.full_label}}))")
        by_id = {item["id"]: item for item in result}
        self.assertEqual(by_id["other-node"]["label"], "g.py")
        self.assertEqual(by_id["other-node"]["full_label"], "other/g.py")


@unittest.skipUnless(shutil.which("node"), "node is required to run the JS graph model")
class TestVO20AlwaysLabelWeightRanking(unittest.TestCase):
    """VO-20 (FR-22): boundary value (2-value) over the always_label
    top-20/21st-and-below boundary, including the tie-break-by-id case."""

    def _build_always_label_map(self, nodes):
        value = self._payload_with(nodes)
        result = _run_graph_model(
            f"model.build({json.dumps(value)}).nodes.map(n => ({{id: n.id, always_label: n.always_label}}))"
        )
        return {item["id"]: item["always_label"] for item in result}

    def _payload_with(self, nodes):
        value = _payload("vo20-always-label")
        value["readable_nodes"] = nodes
        value["read_units"] = _read_units_for(nodes)
        value["query_nodes"] = []
        value["connections"] = []
        return value

    def test_21_distinct_weights_top_20_are_always_label_true_and_the_lowest_is_false(self):
        # 21 nodes, distinct token_estimate (== weight, since there are no
        # connections) 1..21. The single lowest-weight node (weight 1) is
        # rank 21 and must be the only one with always_label=false.
        nodes = [_readable_node(f"r{i:02d}", f"p/r{i:02d}.py", f"p/r{i:02d}.py", token_estimate=i + 1) for i in range(21)]
        always_label = self._build_always_label_map(nodes)
        self.assertEqual(always_label["r00"], False)
        for i in range(1, 21):
            self.assertEqual(always_label[f"r{i:02d}"], True, f"expected r{i:02d} (weight {i + 1}) to be in the top 20")

    def test_tie_at_the_20_21_boundary_breaks_by_id_ascending(self):
        # 19 nodes with distinct weights 12..30 (all comfortably in the top
        # 20 regardless of the tie below). 2 more nodes tie at weight 10,
        # competing for the single remaining (20th) slot: "a-tie" < "z-tie"
        # ascending, so "a-tie" must win the slot (always_label=true) and
        # "z-tie" must be excluded (always_label=false).
        higher = [_readable_node(f"hi{i:02d}", f"p/hi{i:02d}.py", f"p/hi{i:02d}.py", token_estimate=30 - i) for i in range(19)]
        tied = [
            _readable_node("z-tie", "p/z-tie.py", "p/z-tie.py", token_estimate=10),
            _readable_node("a-tie", "p/a-tie.py", "p/a-tie.py", token_estimate=10),
        ]
        nodes = higher + tied
        always_label = self._build_always_label_map(nodes)
        for i in range(19):
            self.assertEqual(always_label[f"hi{i:02d}"], True)
        self.assertEqual(always_label["a-tie"], True, "lower id must win the tied 20th slot")
        self.assertEqual(always_label["z-tie"], False, "higher id must lose the tied slot and fall to rank 21")

    def test_connection_count_moves_a_node_across_the_top_20_boundary(self):
        # MUT-3: weight = token_estimate + connection count. "low_conn" and
        # "high_base" are the two lowest-weight nodes among 21 total; 19
        # filler nodes with token_estimate >= 100 always rank above both
        # regardless of a handful of +1 connection bumps.
        #
        # Hand-computed weights:
        #   low_conn:  token=5,  connections=11 (to filler00..filler10) -> weight = 5 + 11 = 16
        #   high_base: token=15, connections=0                          -> weight = 15
        # 16 > 15, so low_conn ranks 20th (in the top 20, always_label=true)
        # and high_base ranks 21st (excluded, always_label=false). Without
        # the connection-count term, low_conn's weight would be 5 (< 15),
        # reversing which of the two is excluded.
        fillers = [_readable_node(f"filler{i:02d}", f"p/filler{i:02d}.py", f"p/filler{i:02d}.py", token_estimate=100 + i * 10) for i in range(19)]
        low_conn = _readable_node("low_conn", "p/low_conn.py", "p/low_conn.py", token_estimate=5)
        high_base = _readable_node("high_base", "p/high_base.py", "p/high_base.py", token_estimate=15)
        nodes = fillers + [low_conn, high_base]
        value = self._payload_with(nodes)
        value["connections"] = [
            {"id": f"c:lc-{i}", "from_id": "low_conn", "to_id": f"filler{i:02d}", "kind": "generates", "specificity": "narrowing", "evidence": {}}
            for i in range(11)
        ]
        result = _run_graph_model(
            f"model.build({json.dumps(value)}).nodes.map(n => ({{id: n.id, always_label: n.always_label}}))"
        )
        always_label = {item["id"]: item["always_label"] for item in result}
        for i in range(19):
            self.assertEqual(always_label[f"filler{i:02d}"], True)
        self.assertEqual(always_label["low_conn"], True, "connection count must raise low_conn's weight (16) above high_base's (15), keeping it in the top 20")
        self.assertEqual(always_label["high_base"], False, "high_base has no connections and must fall to rank 21")


# FR-12: judgement words that must never appear in generated report text.
FORBIDDEN_WORDS = ("위험", "나쁨", "품질")


def _strip_payload_script(html):
    """VO-22: the M1 payload (repo-derived data, out of this obligation's
    scope) is embedded verbatim as gzip+base64 in `#agent-view-v3-payload`
    (see tests/test_report_m1.py's `_embedded_payload`); strip that one
    script element before scanning the rest of the generated HTML (renderer
    prose, glossary, section copy, etc.) for forbidden judgement words."""
    stripped, count = re.subn(
        r'<script id="agent-view-v3-payload"[^>]*>.*?</script>', "", html, flags=re.DOTALL,
    )
    assert count == 1, f"expected exactly one #agent-view-v3-payload script, found {count}"
    return stripped


class TestVO22M1NoForbiddenJudgementWords(unittest.TestCase):
    """VO-22 (FR-12): equivalence partitioning over the single declared
    coverage item for M1 -- the generated HTML (excluding the payload script
    content, which is repo-derived data out of this obligation's scope) must
    contain none of the 3 forbidden judgement words."""

    def test_generated_m1_html_excluding_payload_has_no_forbidden_judgement_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "view.json"
            source.write_text(_payload_text(_payload()), encoding="utf-8")
            output = generate_report(source)
            html = output.read_text(encoding="utf-8")
            prose = _strip_payload_script(html)
            for word in FORBIDDEN_WORDS:
                self.assertNotIn(word, prose, f"forbidden judgement word present outside the payload: {word}")


def _vendor_files():
    return sorted(VENDOR_DIR.glob("*.min.js")) if VENDOR_DIR.is_dir() else []


class TestVO8M1Generate(unittest.TestCase):
    """VO-8: equivalence partitioning over the 5 declared coverage items."""

    def write_payload(self, root, value=None):
        source = root / "view.json"
        source.write_text(_payload_text(value or _payload()), encoding="utf-8")
        return source

    def test_C13_cytoscape_is_inlined_and_focus_section_is_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = generate_report(self.write_payload(root))
            html = output.read_text(encoding="utf-8")
            self.assertIn("cytoscape", html.lower())
            # TD-1: attribute quote style is not a contract; accept either ' or ".
            self.assertRegex(html, r"""id=['"]focus['"]""")

    def test_C13_offline_rules_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = generate_report(self.write_payload(root))
            html = output.read_text(encoding="utf-8")
            _assert_offline(self, html)

    def test_C13_deterministic_bytes_across_two_generations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.write_payload(root)
            first = generate_report(source, root / "first.html")
            second = generate_report(source, root / "second.html")
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_QR1_vendor_footprint_is_within_1_5MB_and_output_within_10MB(self):
        vendor_files = _vendor_files()
        self.assertGreater(len(vendor_files), 0, "expected vendor files under report/m1/vendor")
        total_vendor_bytes = sum(path.stat().st_size for path in vendor_files)
        self.assertLessEqual(total_vendor_bytes, int(1.5 * 1024 * 1024))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = generate_report(self.write_payload(root))
            self.assertLess(output.stat().st_size, 10 * 1024 * 1024)

    def test_QR7_each_vendor_library_has_a_versioned_file_and_a_license(self):
        # TD-6: license is `<name>-<semver>.LICENSE` next to `<name>-<semver>.min.js`.
        matched = 0
        for name in ("cytoscape", "cytoscape-fcose", "layout-base", "cose-base"):
            candidates = sorted(VENDOR_DIR.glob(f"{name}-*.min.js"))
            if name == "cytoscape":
                candidates = [path for path in candidates if not path.name.startswith("cytoscape-fcose")]
            self.assertTrue(candidates, f"missing versioned min.js for {name}")
            script_path = candidates[0]
            self.assertTrue(script_path.name.endswith(".min.js"))
            name_semver = script_path.name[: -len(".min.js")]
            self.assertRegex(name_semver, rf"^{re.escape(name)}-\d+\.\d+\.\d+$")
            license_path = script_path.with_name(f"{name_semver}.LICENSE")
            self.assertTrue(license_path.exists(), f"missing {license_path.name} next to {script_path.name}")
            matched += 1
        self.assertEqual(matched, 4)

    def test_C15_missing_vendor_file_raises_and_writes_no_output(self):
        vendor_files = _vendor_files()
        if not vendor_files:
            self.skipTest("no vendor files found to remove")
        missing_name = vendor_files[0].name
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.write_payload(root)
            source_text = source.read_text(encoding="utf-8")
            output_path = root / "out.html"

            def read_text_missing_vendor(path):
                if path.name == source.name:
                    return source_text
                if path.name == missing_name:
                    raise OSError(f"missing vendor file: {missing_name}")
                return path.read_text(encoding="utf-8")

            with self.assertRaises(ReportOutputError):
                generate_report(source, output_path, read_text=read_text_missing_vendor)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
