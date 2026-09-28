"""VO-1..VO-6 for report/m1/templates/graph_model.js's new `expand`,
`labelFontSize`, `focusZoom` pure functions (report/m1/templates/graph.js's
FR-15 extraction) and report/bottlenecks/generate.py's `render_report` FR-8
`#focus` reason-sentence contract change, per
agent-docs/specs/a73c1e5f0b284d96-report-readability-followup.md v3 (FR
text for this file's obligations is unchanged from v2; v3 only added a VO-7
review scenario, which is out of this file's automated scope).

VO-1 (FR-1, C-3, C-4): equivalence partitioning over {알 수 없는 id, 디렉터리
id, present target, 숨은 target} for `ReportGraphModel.expand`. `built` is
produced by the real `ReportGraphModel.build` (trusted fixture-construction
infra, not itself under test here); directory ids are discovered from
`built.elements`' `parent`/`is_directory` fields rather than hardcoded, per
the task's instruction, since the id scheme itself is not part of any
Signature.

VO-2 (FR-2, C-2): boundary value (2-value) over {이웃 20, 이웃 21(동점 id
제외 규칙), 중복 edge 2개가 같은 이웃, 자기 루프}. The 21-neighbor case is
built so the excluded node is determined purely by the id tie-break (20
neighbors share one clearly-higher weight; 2 more neighbors tie at a lower
weight competing for the last slot; the lexicographically larger id must
lose).

VO-3 (FR-3, C-1, C-5): decision table over {이웃 present/숨음, 조상
present/없음(상위 먼저), edge: target–present, 숨은 이웃–present 비이웃,
present–present 제외, 20위 밖 이웃 edge 제외}. The last item's fixture
includes an edge between a rank->20th (excluded) neighbor and an otherwise
present node, and a target<->present-neighbor edge is deliberately paired
with an edge directly between two present neighbors (present–present) so the
exclusion is specific to the present–present case, not a blanket omission.
Per v2's FR-3, `edges` holds the connection's *built element id*
(`"edge:" + connection.id`), not the bare `connection.id`; every edge-id
assertion in this class uses that `"edge:"`-prefixed form.

VO-4 (FR-4): decision table over {positions 키=nodes, present 이웃 있을 때
앵커, 조상만 present, 둘 다 없음 {0,0}, 이웃 배치 반지름 120·각도 0 시작}.
Expected coordinates are hand-computed from FR-4's v2 formula: for k new
(non-present) nodes ranked i=0..k-1, position_i = (ax + 120*cos(2*pi*i/k),
ay + 120*sin(2*pi*i/k)), (ax,ay) = target position -- computed independently
in Python via `math.cos`/`math.sin`, not by re-deriving the implementation.
FG-2 correction: the two anchor tests that give `present` a non-empty map
(the present-neighbor anchor and present-ancestor anchor tests) now also
assert `positions` keys == `nodes` and that none of the given present ids
(the anchor neighbor, the other present neighbor, the present ancestor
directory) leak a position entry -- a defect here (e.g. positions including
present ids) was previously undetected because those 2 tests only inspected
`positions['t4*']` and never the full `positions`/`nodes` sets. Every other
VO-4 test uses an empty `present` map (no present id could leak), so no
change was needed there; `test_positions_keys_equal_the_nodes_set` already
covered the general keys==nodes property for that empty-present case.

VO-5 (FR-6, FR-7, C-6, C-7): boundary value (3-value) over C-6/C-7's declared
input values for `labelFontSize`/`focusZoom`, computed independently from
FR-6/FR-7's formulas.

VO-6 (FR-8, C-8): equivalence partitioning over {kind 5종 각 1건} for
`render_report`'s `#focus` section. Each candidate's `target` is an
id-format string (`py:<module>#<qual>`) so its FR-1/FR-21 short label
differs from the raw target, letting the test distinguish "label appears
once (in <strong>)" from "raw target kept only in a title attribute" per
FR-8's new contract (label must not be repeated in the visible reason
sentence, unlike the prior "<label>: <sentence>" contract). FG-1 correction:
in addition to the visible-text occurrence count, each kind now also asserts
the label's one visible occurrence is specifically inside a `<strong>`
element and absent from the title-stripped text outside every `<strong>`
element -- a render that emitted the label once as plain reason text (no
`<strong>`, or moved outside it) previously passed the count-only check.

Checked-no-change note (FR-8 contract change vs. tests/test_readability_bottlenecks.py
and tests/test_readability_m1.py): neither file asserts the prior
"<label>: <reason>" #focus prefix contract (grep confirms no test in either
file inspects a label-colon-prefixed reason string), so FR-8 does not require
editing either file; both are left unchanged.
"""
import json
import math
import re
import subprocess
import unittest
from pathlib import Path

from tests.test_readability_bottlenecks import (
    _base_payload,
    _candidate,
    _payload_with_candidates,
    _section_content,
    _without_title_attributes,
)
from report.bottlenecks.generate import render_report
from tests.test_report_m1 import _payload as _m1_payload

ROOT = Path(__file__).resolve().parents[1]
GRAPH_MODEL = ROOT / "report/m1/templates/graph_model.js"

# JS helpers used to discover structural facts (directory ids, ancestor
# chains) from `build()`'s own output, rather than hardcoding the id scheme
# (which is not part of any Signature).
_HELPERS_JS = """
function nodeElements(built) {
  return built.elements.filter((e) => !("source" in e.data));
}
function elementById(built) {
  const map = {};
  nodeElements(built).forEach((e) => { map[e.data.id] = e.data; });
  return map;
}
function ancestorChainBottomUp(built, nodeId) {
  const byId = elementById(built);
  const chain = [];
  let current = byId[nodeId] ? byId[nodeId].parent : undefined;
  while (current) {
    chain.push(current);
    current = byId[current] ? byId[current].parent : undefined;
  }
  return chain;
}
function directoryIds(built) {
  const ids = new Set();
  nodeElements(built).forEach((e) => { if (e.data.parent) { ids.add(e.data.parent); } });
  return Array.from(ids);
}
"""


def _run_graph_model(function_call):
    script = f"const model = require({json.dumps(str(GRAPH_MODEL))}); {_HELPERS_JS}\nconsole.log(JSON.stringify({function_call}));"
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def _readable_node(node_id, file_path, token_estimate=1, unit_id=None):
    return {
        "id": node_id, "file_path": file_path, "symbol_id": None, "label": file_path,
        "kind": "file", "start_line": 1, "end_line": 1,
        "read_cost": {"token_estimate": token_estimate, "char_count": token_estimate * 4, "line_count": 1},
        "flags": [], "read_unit_id": unit_id if unit_id is not None else f"unit:{node_id}",
    }


def _read_unit_entry(unit_id, file_path):
    return {"id": unit_id, "file_path": file_path, "start_line": 1, "end_line": 1, "symbol_ids": [], "read_cost": {"token_estimate": 1, "char_count": 1, "line_count": 1}, "oversized_symbol": False}


def _read_units_for(nodes):
    seen = []
    for node in nodes:
        if node["read_unit_id"] not in seen:
            seen.append(node["read_unit_id"])
    return [_read_unit_entry(unit_id, file_path=nodes[0]["file_path"] if nodes else "a") for unit_id in seen]


def _connection(id_, from_id, to_id):
    return {"id": id_, "from_id": from_id, "to_id": to_id, "kind": "generates", "specificity": "narrowing", "evidence": {}}


def _payload_for(nodes, connections):
    value = _m1_payload("followup")
    value["readable_nodes"] = nodes
    value["read_units"] = _read_units_for(nodes)
    value["query_nodes"] = []
    value["connections"] = connections
    return value


class TestVO1ExpandIdPartitions(unittest.TestCase):
    """VO-1: equivalence partitioning over the 4 declared coverage items."""

    def _fixture(self):
        nodes = [_readable_node("leaf:iso", "root_dir/leaf_iso.py")]
        return _payload_for(nodes, [])

    def test_unknown_id_returns_null(self):
        value = self._fixture()
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{}}, 'does-not-exist:0001'); }})()"
        )
        self.assertIsNone(result)

    def test_directory_id_returns_null(self):
        value = self._fixture()
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"const dirs = directoryIds(built); "
            f"return {{dirs: dirs, expand: dirs.length ? model.expand(built, {{}}, dirs[0]) : 'NO_DIR'}}; }})()"
        )
        self.assertGreater(len(result["dirs"]), 0, "expected the nested fixture path to produce a directory node")
        self.assertIsNone(result["expand"])

    def test_present_target_returns_all_empty(self):
        value = self._fixture()
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{'leaf:iso': {{x: 5, y: 6}}}}, 'leaf:iso'); }})()"
        )
        self.assertEqual(result, {"nodes": [], "parents": [], "edges": [], "positions": {}})

    def test_hidden_target_returns_non_empty_result(self):
        value = self._fixture()
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{}}, 'leaf:iso'); }})()"
        )
        self.assertIsNotNone(result)
        self.assertIn("leaf:iso", result["nodes"])
        self.assertGreater(len(result["nodes"]) + len(result["parents"]), 0)


class TestVO2ExpandNeighborBoundary(unittest.TestCase):
    """VO-2: boundary value (2-value) over the 4 declared coverage items."""

    def test_20_neighbors_are_all_selected(self):
        target = _readable_node("t20", "t20.py")
        neighbors = [_readable_node(f"n{i:02d}", f"n{i:02d}.py") for i in range(20)]
        connections = [_connection(f"e-t-n{i:02d}", "t20", f"n{i:02d}") for i in range(20)]
        value = _payload_for([target] + neighbors, connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{}}, 't20'); }})()"
        )
        selected = [n for n in result["nodes"] if n != "t20"]
        self.assertEqual(len(selected), 20)
        self.assertEqual(sorted(selected), sorted(n["id"] for n in neighbors))

    def test_21_neighbors_excludes_the_higher_id_of_the_tied_pair(self):
        # 19 "hi" neighbors get a bumped weight (2: 1 target edge + 1 shared-aux
        # edge) so they unconditionally occupy 19 of the 20 slots. "a-tie" and
        # "z-tie" both have weight 1 (target edge only) and compete for the
        # last slot; FR-2's id-ascending tie-break must keep "a-tie" (< "z-tie")
        # and exclude "z-tie".
        target = _readable_node("t21", "t21.py")
        aux = _readable_node("aux21", "aux21.py")
        hi_nodes = [_readable_node(f"hi{i:02d}", f"hi{i:02d}.py") for i in range(19)]
        tie_nodes = [_readable_node("a-tie", "a-tie.py"), _readable_node("z-tie", "z-tie.py")]
        connections = [_connection(f"e-t-hi{i:02d}", "t21", f"hi{i:02d}") for i in range(19)]
        connections += [_connection(f"e-hi{i:02d}-aux", f"hi{i:02d}", "aux21") for i in range(19)]
        connections += [_connection("e-t-atie", "t21", "a-tie"), _connection("e-t-ztie", "t21", "z-tie")]
        value = _payload_for([target, aux] + hi_nodes + tie_nodes, connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{}}, 't21'); }})()"
        )
        selected = [n for n in result["nodes"] if n != "t21"]
        self.assertEqual(len(selected), 20)
        self.assertIn("a-tie", selected)
        self.assertNotIn("z-tie", selected)

    def test_2_duplicate_edges_to_the_same_neighbor_still_select_it_once(self):
        target = _readable_node("tdup", "tdup.py")
        neighbor = _readable_node("ndup", "ndup.py")
        connections = [_connection("e-dup-1", "tdup", "ndup"), _connection("e-dup-2", "tdup", "ndup")]
        value = _payload_for([target, neighbor], connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{}}, 'tdup'); }})()"
        )
        selected = [n for n in result["nodes"] if n != "tdup"]
        self.assertEqual(selected, ["ndup"])

    def test_self_loop_connection_does_not_create_a_phantom_neighbor(self):
        target = _readable_node("tself", "tself.py")
        connections = [_connection("e-self", "tself", "tself")]
        value = _payload_for([target], connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{}}, 'tself'); }})()"
        )
        self.assertEqual(result["nodes"], ["tself"])


class TestVO3ExpandEdgesAndParents(unittest.TestCase):
    """VO-3: decision table over the 6 declared coverage items."""

    def test_neighbor_present_vs_hidden_only_the_hidden_one_is_added_to_nodes(self):
        target = _readable_node("t3a", "t3a.py")
        hidden_neighbor = _readable_node("h3a", "h3a.py")
        present_neighbor = _readable_node("p3a", "p3a.py")
        connections = [_connection("e-t-h", "t3a", "h3a"), _connection("e-t-p", "t3a", "p3a")]
        value = _payload_for([target, hidden_neighbor, present_neighbor], connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{'p3a': {{x: 1, y: 1}}}}, 't3a'); }})()"
        )
        self.assertEqual(result["nodes"], ["t3a", "h3a"])
        self.assertNotIn("p3a", result["nodes"])

    def test_ancestor_directories_missing_entries_are_top_first_ordered(self):
        # 3-level nesting: only the root-most ancestor is present, so the 2
        # missing ancestors (mid, then immediate) must appear top-first.
        target = _readable_node("t3b", "lvlA/lvlB/lvlC/t3b.py")
        value = _payload_for([target], [])
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"const chain = ancestorChainBottomUp(built, 't3b').slice().reverse(); "
            f"const present = {{}}; present[chain[0]] = {{x: 0, y: 0}}; "
            f"return {{parents: model.expand(built, present, 't3b').parents, chainTopFirst: chain}}; }})()"
        )
        expected_missing = result["chainTopFirst"][1:]
        self.assertEqual(len(result["chainTopFirst"]), 3, "expected a 3-level ancestor chain")
        self.assertEqual(result["parents"], expected_missing)

    def test_target_present_neighbor_edge_is_included(self):
        target = _readable_node("t3c", "t3c.py")
        present_neighbor = _readable_node("p3c", "p3c.py")
        connections = [_connection("e-t-p3c", "t3c", "p3c")]
        value = _payload_for([target, present_neighbor], connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{'p3c': {{x: 0, y: 0}}}}, 't3c'); }})()"
        )
        self.assertIn("edge:e-t-p3c", result["edges"])

    def test_hidden_neighbor_to_present_non_neighbor_edge_is_included(self):
        target = _readable_node("t3d", "t3d.py")
        hidden_neighbor = _readable_node("h3d", "h3d.py")
        present_non_neighbor = _readable_node("u3d", "u3d.py")
        connections = [_connection("e-t-h3d", "t3d", "h3d"), _connection("e-h3d-u3d", "h3d", "u3d")]
        value = _payload_for([target, hidden_neighbor, present_non_neighbor], connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{'u3d': {{x: 3, y: 3}}}}, 't3d'); }})()"
        )
        self.assertIn("edge:e-h3d-u3d", result["edges"])
        self.assertIn("edge:e-t-h3d", result["edges"])

    def test_present_present_edge_between_two_selected_neighbors_is_excluded(self):
        target = _readable_node("t3e", "t3e.py")
        p1 = _readable_node("p1-3e", "p1-3e.py")
        p2 = _readable_node("p2-3e", "p2-3e.py")
        connections = [
            _connection("e-t-p1", "t3e", "p1-3e"),
            _connection("e-t-p2", "t3e", "p2-3e"),
            _connection("e-p1-p2", "p1-3e", "p2-3e"),
        ]
        value = _payload_for([target, p1, p2], connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{'p1-3e': {{x: 0, y: 0}}, 'p2-3e': {{x: 1, y: 1}}}}, 't3e'); }})()"
        )
        self.assertIn("edge:e-t-p1", result["edges"])
        self.assertIn("edge:e-t-p2", result["edges"])
        self.assertNotIn("edge:e-p1-p2", result["edges"])

    def test_edge_from_a_rank_below_20_excluded_neighbor_to_a_present_node_is_excluded(self):
        # 20 "hi" neighbors get weight 2 (target edge + 1 shared-aux edge);
        # "lo" gets weight 1 (target edge only) and is therefore excluded
        # from selection (rank 21). "lo" also has a peripheral edge to a
        # present node ("x6"), which must NOT appear in the result since
        # "lo" itself is never added.
        target = _readable_node("t3f", "t3f.py")
        aux = _readable_node("aux3f", "aux3f.py")
        x6 = _readable_node("x3f", "x3f.py")
        hi_nodes = [_readable_node(f"hi3f{i:02d}", f"hi3f{i:02d}.py") for i in range(20)]
        lo = _readable_node("lo3f", "lo3f.py")
        connections = [_connection(f"e-t-hi{i:02d}", "t3f", f"hi3f{i:02d}") for i in range(20)]
        connections += [_connection(f"e-hi{i:02d}-aux", f"hi3f{i:02d}", "aux3f") for i in range(20)]
        connections += [_connection("e-t-lo", "t3f", "lo3f"), _connection("e-lo-x6", "lo3f", "x3f")]
        value = _payload_for([target, aux, x6] + hi_nodes + [lo], connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{'x3f': {{x: 9, y: 9}}}}, 't3f'); }})()"
        )
        selected = [n for n in result["nodes"] if n != "t3f"]
        self.assertEqual(len(selected), 20)
        self.assertNotIn("lo3f", selected)
        self.assertNotIn("edge:e-lo-x6", result["edges"])
        self.assertIn("edge:e-t-hi00", result["edges"])


class TestVO4ExpandPositions(unittest.TestCase):
    """VO-4: decision table over the 5 declared coverage items."""

    def test_positions_keys_equal_the_nodes_set(self):
        target = _readable_node("t4a", "t4a.py")
        h1 = _readable_node("h1-4a", "h1-4a.py")
        h2 = _readable_node("h2-4a", "h2-4a.py")
        connections = [_connection("e-t-h1", "t4a", "h1-4a"), _connection("e-t-h2", "t4a", "h2-4a")]
        value = _payload_for([target, h1, h2], connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{}}, 't4a'); }})()"
        )
        self.assertEqual(sorted(result["positions"].keys()), sorted(result["nodes"]))
        self.assertEqual(sorted(result["nodes"]), ["h1-4a", "h2-4a", "t4a"])

    def test_target_anchors_to_the_highest_ranked_present_neighbor(self):
        # p1 is bumped to weight 2 (target edge + 1 extra edge to a filler
        # node) so it strictly outranks p2 (weight 1); the target's position
        # must equal p1's given present position exactly.
        target = _readable_node("t4b", "t4b.py")
        p1 = _readable_node("p1-4b", "p1-4b.py")
        p2 = _readable_node("p2-4b", "p2-4b.py")
        filler = _readable_node("filler-4b", "filler-4b.py")
        connections = [
            _connection("e-t-p1", "t4b", "p1-4b"),
            _connection("e-t-p2", "t4b", "p2-4b"),
            _connection("e-p1-filler", "p1-4b", "filler-4b"),
        ]
        value = _payload_for([target, p1, p2, filler], connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{'p1-4b': {{x: 10, y: 20}}, 'p2-4b': {{x: 30, y: 40}}}}, 't4b'); }})()"
        )
        self.assertAlmostEqual(result["positions"]["t4b"]["x"], 10, delta=1e-6)
        self.assertAlmostEqual(result["positions"]["t4b"]["y"], 20, delta=1e-6)
        # FG-2: positions must be keyed exactly by `nodes` -- neither present
        # anchor neighbor (p1-4b, the anchor source) nor the other present
        # neighbor (p2-4b) may leak a stale/duplicate position entry.
        self.assertEqual(sorted(result["positions"].keys()), sorted(result["nodes"]))
        self.assertNotIn("p1-4b", result["positions"])
        self.assertNotIn("p2-4b", result["positions"])

    def test_target_anchors_to_the_nearest_present_ancestor_directory_when_no_present_neighbor(self):
        target = _readable_node("t4c", "dirX4c/t4c.py")
        value = _payload_for([target], [])
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"const chain = ancestorChainBottomUp(built, 't4c'); "
            f"const present = {{}}; present[chain[0]] = {{x: 50, y: 60}}; "
            f"const r = model.expand(built, present, 't4c'); "
            f"return {{r: r, presentAncestorId: chain[0]}}; }})()"
        )
        positions = result["r"]["positions"]
        self.assertAlmostEqual(positions["t4c"]["x"], 50, delta=1e-6)
        self.assertAlmostEqual(positions["t4c"]["y"], 60, delta=1e-6)
        # FG-2: positions must be keyed exactly by `nodes` -- the present
        # ancestor directory used as the anchor source must not leak a
        # position entry of its own.
        self.assertEqual(sorted(positions.keys()), sorted(result["r"]["nodes"]))
        self.assertNotIn(result["presentAncestorId"], positions)

    def test_target_anchors_to_origin_when_neither_present_neighbor_nor_ancestor_exists(self):
        target = _readable_node("t4d", "t4d.py")
        value = _payload_for([target], [])
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{}}, 't4d').positions['t4d']; }})()"
        )
        self.assertAlmostEqual(result["x"], 0, delta=1e-6)
        self.assertAlmostEqual(result["y"], 0, delta=1e-6)

    def test_single_new_neighbor_is_placed_at_radius_120_angle_zero(self):
        # Target anchors to {0,0} (no present neighbor/ancestor, per the
        # previous coverage item), so the first (and only) new neighbor's
        # angle-0 position is unambiguously (0+120, 0) regardless of
        # rotation direction (sin(0)=0 either way).
        target = _readable_node("t4e", "t4e.py")
        neighbor = _readable_node("n4e", "n4e.py")
        connections = [_connection("e-t-n", "t4e", "n4e")]
        value = _payload_for([target, neighbor], connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{}}, 't4e').positions['n4e']; }})()"
        )
        self.assertAlmostEqual(result["x"], 120, delta=1e-6)
        self.assertAlmostEqual(result["y"], 0, delta=1e-6)

    def test_multiple_new_neighbors_are_placed_at_the_exact_FR4_circle_formula_coordinates(self):
        # FR-4 (v2): for k new (non-present) nodes ranked i=0..k-1, position_i
        # = (ax + 120*cos(2*pi*i/k), ay + 120*sin(2*pi*i/k)), (ax,ay) = target
        # position. Target anchors to {0,0} here (no present neighbor/
        # ancestor, per the origin-anchor coverage item), so (ax,ay)=(0,0).
        # All 4 neighbors tie at weight 1 (single edge to target each), so
        # FR-2's id-ascending tie-break ranks them n4f0,n4f1,n4f2,n4f3 (i=0..3).
        target = _readable_node("t4f", "t4f.py")
        neighbors = [_readable_node(f"n4f{i}", f"n4f{i}.py") for i in range(4)]
        connections = [_connection(f"e-t-n{i}", "t4f", f"n4f{i}") for i in range(4)]
        value = _payload_for([target] + neighbors, connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"const r = model.expand(built, {{}}, 't4f'); "
            f"return {{target: r.positions['t4f'], neighbors: [0,1,2,3].map(i => r.positions['n4f' + i])}}; }})()"
        )
        tx, ty = result["target"]["x"], result["target"]["y"]
        self.assertAlmostEqual(tx, 0, delta=1e-6)
        self.assertAlmostEqual(ty, 0, delta=1e-6)
        k = 4
        for i, pos in enumerate(result["neighbors"]):
            expected_x = tx + 120 * math.cos(2 * math.pi * i / k)
            expected_y = ty + 120 * math.sin(2 * math.pi * i / k)
            self.assertAlmostEqual(pos["x"], expected_x, delta=1e-6, msg=f"neighbor rank {i}")
            self.assertAlmostEqual(pos["y"], expected_y, delta=1e-6, msg=f"neighbor rank {i}")


class TestVO5LabelFontSizeAndFocusZoom(unittest.TestCase):
    """VO-5: boundary value (3-value) over C-6/C-7's declared input values,
    computed independently from FR-6 (`max(9, 11/zoom)`) and FR-7
    (`max(fitZoom, 1)`)."""

    def test_labelFontSize_at_zoom_1_is_11(self):
        self.assertAlmostEqual(_run_graph_model("model.labelFontSize(1.0)"), 11, delta=1e-6)

    def test_labelFontSize_at_zoom_11_over_9_is_9(self):
        self.assertAlmostEqual(_run_graph_model("model.labelFontSize(11/9)"), 9, delta=1e-6)

    def test_labelFontSize_at_zoom_2_is_9(self):
        self.assertAlmostEqual(_run_graph_model("model.labelFontSize(2)"), 9, delta=1e-6)

    def test_labelFontSize_at_zoom_half_is_22(self):
        self.assertAlmostEqual(_run_graph_model("model.labelFontSize(0.5)"), 22, delta=1e-6)

    def test_focusZoom_below_1_clamps_to_1(self):
        self.assertAlmostEqual(_run_graph_model("model.focusZoom(0.3)"), 1, delta=1e-6)

    def test_focusZoom_at_1_is_1(self):
        self.assertAlmostEqual(_run_graph_model("model.focusZoom(1)"), 1, delta=1e-6)

    def test_focusZoom_above_1_passes_through(self):
        self.assertAlmostEqual(_run_graph_model("model.focusZoom(1.6)"), 1.6, delta=1e-6)


# FR-8/VO-6: one candidate per scored kind, each with an id-format target so
# label != raw target (FR-1/FR-21 short-labels composition), letting the
# tests distinguish "label once in the visible reason" from "raw target only
# in a title attribute". Metrics/labels are hand-computed:
#   output_truncation: score=omitted_count; total=40,visible=28,omitted=12
#     (matches FR-8's own worked example "40건 중 12건이 생략되었습니다.");
#     module "pkg.trunc" -> "trunc" (no conflict) + ":read" -> "trunc:read".
#   multiple_results: score=total_count=5; "pkg.multi"->"multi"+":find".
#   read_limit: score=line_count-read_line_limit=120-40=80;
#     "pkg.readl"->"readl"+":big".
#   evidence_spread: score=file_count=3; "pkg.spread"->"spread"+":wide".
#   unresolved_boundary: score=unresolved_count=4; "pkg.unres"->"unres"+":dep".
VO6_FIXTURES = [
    ("output_truncation", "py:pkg.trunc#read", {"total_count": 40, "visible_count": 28, "omitted_count": 12}, "trunc:read"),
    ("multiple_results", "py:pkg.multi#find", {"total_count": 5, "visible_count": 5, "omitted_count": 0}, "multi:find"),
    ("read_limit", "py:pkg.readl#big", {"line_count": 120, "read_line_limit": 40}, "readl:big"),
    ("evidence_spread", "py:pkg.spread#wide", {"file_count": 3, "line_span": 5, "read_line_limit": 40}, "spread:wide"),
    ("unresolved_boundary", "py:pkg.unres#dep", {"unresolved_count": 4}, "unres:dep"),
]


def _split_strong_contents_and_rest(html):
    """FG-1: split title-stripped HTML into (list of each `<strong>...</strong>`
    element's inner text, remaining text with all `<strong>` elements
    removed), so a label's presence can be checked specifically inside a
    `<strong>` element vs. outside every `<strong>` element -- not just
    counted anywhere in the visible text."""
    strong_contents = re.findall(r"<strong[^>]*>(.*?)</strong>", html, re.DOTALL)
    rest = re.sub(r"<strong[^>]*>.*?</strong>", "", html, flags=re.DOTALL)
    return strong_contents, rest


class TestVO6FocusReasonSentenceOmitsLabel(unittest.TestCase):
    """VO-6 (FR-8, C-8): equivalence partitioning over the 5 declared
    coverage items (kind x1 each). Per FR-8, the #focus reason sentence must
    not repeat the label (label appears exactly once, inside <strong>); the
    raw target is kept only in a title attribute."""

    def _focus_section_for(self, kind, target, metrics):
        candidate = _candidate(f"cand-{kind}", kind, target, metrics)
        html = render_report(_payload_with_candidates([candidate]))
        return _section_content(html, "focus")

    def test_each_kind_shows_its_label_exactly_once_and_keeps_the_raw_target_in_a_title_only(self):
        for kind, target, metrics, expected_label in VO6_FIXTURES:
            with self.subTest(kind=kind):
                focus_section = self._focus_section_for(kind, target, metrics)
                self.assertIn(target, focus_section, f"{kind}: expected raw target somewhere in #focus (title attribute)")
                visible_only = _without_title_attributes(focus_section)
                self.assertNotIn(target, visible_only, f"{kind}: raw target must not appear in the visible reason text")
                self.assertEqual(
                    visible_only.count(expected_label), 1,
                    f"{kind}: expected label {expected_label!r} exactly once in the visible #focus text, "
                    f"got {visible_only.count(expected_label)} (prior contract repeated it as '<label>: ...')",
                )
                # FG-1: "라벨은 <strong>에 한 번" -- the label's one visible
                # occurrence must specifically be inside a <strong> element,
                # and must not also (or instead) appear as plain reason-sentence
                # text outside every <strong> element. A render that emits the
                # label once as plain text (no <strong> at all, or the label
                # moved outside it) must fail this pair of assertions even
                # though the overall visible count above would still be 1.
                strong_contents, rest = _split_strong_contents_and_rest(visible_only)
                self.assertTrue(
                    any(expected_label in content for content in strong_contents),
                    f"{kind}: expected label {expected_label!r} inside a <strong> element, got <strong> contents {strong_contents!r}",
                )
                self.assertNotIn(
                    expected_label, rest,
                    f"{kind}: label {expected_label!r} must not appear in the reason text outside <strong>",
                )


if __name__ == "__main__":
    unittest.main()
