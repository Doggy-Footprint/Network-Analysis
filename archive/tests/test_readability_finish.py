"""VO-1..VO-7 for agent-docs/specs/44ff0ed597e46cf3-report-readability-finish.md
v2: report/m1/templates/graph_model.js's new `visibleLabels` pure function
and `weight` field on build()'s node element data (FR-1, FR-2 unit slice),
`expand()`'s new FR-3/FR-4 minimum-gap candidate search for positions, and
renderers/html/static/app.js's `buildOverview` FR-6 category label rule
(ADV-1).

Harness conventions (node -e + JSON.stringify, `_readable_node`/`_connection`/
`_payload_for` fixture builders, `run_overview_js` node-vm loader for app.js)
are reused/imported from tests.test_readability_followup and
tests.test_readability_dashboard rather than duplicated, per this run's task
instructions.

VO-1 (FR-1, C-1..C-4): equivalence partitioning over {겹침 탈락, 비겹침 채택,
동점 id tie-break, 빈 입력, 반환 순서=채택 순서} for `visibleLabels(boxes)`, a
pure function of the `boxes` array alone (no `build()`/fixture graph needed).

VO-2 (FR-1, C-2): boundary value (2-value) over {x 접촉(0 겹침)·x 0.01 겹침,
y 접촉·y 0.01 겹침} for the FR-1 overlap predicate
(`x1<o.x2 && o.x1<x2 && y1<o.y2 && o.y1<y2`).

VO-3 (FR-2, unit/build slice only -- the integration/RV-3 slice is reported
separately): equivalence partitioning over {build 노드 data의 weight가 기존
순위 weight와 순서 일치(연결 많을수록 큼, 같으면 같음)} (v2 coverage item text;
v2's Version Log confirms this ordering-consistency framing as final --
"weight 공식이 스펙 외부에서 독립 도출 불가 → 순서 일치 검증으로 확정"). This
file asserts strict ordering (more edges -> strictly higher weight; equal
edges -> equal weight) using the same edge-count construction
tests.test_readability_followup's 21-neighbor/rank-based fixtures already
rely on, rather than an exact numeric value.

VO-4 (FR-3, FR-5, C-5, C-6): equivalence partitioning over {target 새·anchor
비어 있음, target 새·anchor 점유, 이웃 다수, present 위치 불변, nodes/edges/
parents 기존과 동일}. Expected coordinates are computed by an independent
Python oracle (`fr3_place`/`fr3_expected_positions` below) implementing
FR-3's candidate list (r_k=60k, slots_k=max(1,floor(2*pi*r_k/60)),
angle=2*pi*j/slots_k) and FR-4's last-candidate fallback, compared to the
model's actual output within 1e-9 -- not by re-deriving expectations from
the implementation. The anchor point itself (unchanged rule: first
ranked present neighbor's given position, else nearest present ancestor's
given position, else origin) is supplied to the oracle from the fixture's
own construction (edge-count ranking already established by the followup
file's precedent), not re-derived here.

VO-5 (FR-3, C-7): boundary value (2-value) over {거리 60 허용, 59.99 거부}.
Present blockers are placed at exactly 60 / 59.99 from a candidate point
whose coordinates are independently known from FR-3's formula (the first
new-neighbor candidate, k=2,j=0, is target_position + (120, 0)).

VO-6 (FR-4, C-8): error guessing -- every one of FR-3's 485 candidates
around the target's own (origin) anchor is blocked by a present node placed
exactly on that candidate, forcing FR-4's last-candidate fallback with no
exception.

VO-7 (FR-6, C-9): equivalence partitioning over {category in
file/module/package (label != file_path) x1 each, category=function
(label != file_path)}, checked on `buildOverview`'s `focus` array via the
same node-vm harness as tests.test_readability_dashboard's VO-4/VO-18.
Expected short/full labels reuse file_path pairs already independently
established there (FR-1's short_labels algorithm), not re-derived here.
"""
import json
import math
import unittest

from tests.test_readability_dashboard import run_overview_js
from tests.test_readability_followup import (
    _connection,
    _payload_for,
    _readable_node,
    _run_graph_model,
)

# --- Independent FR-3/FR-4 oracle -------------------------------------------
# MIN_GAP=60 (model coordinates, center-to-center Euclidean distance).
# Candidates: r_k = 60*k for k=0..12; slots_k = max(1, floor(2*pi*r_k/60));
# angle_j = 2*pi*j/slots_k for j=0..slots_k-1, visited in (k, j) order.
MIN_GAP = 60.0
MAX_K = 12


def _fr3_all_candidates():
    candidates = []
    for k in range(0, MAX_K + 1):
        r = 60.0 * k
        slots = max(1, math.floor(2 * math.pi * r / 60.0))
        for j in range(slots):
            angle = 2 * math.pi * j / slots
            candidates.append((k, r * math.cos(angle), r * math.sin(angle)))
    return candidates


_FR3_CANDIDATES = _fr3_all_candidates()


def _fr3_dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def fr3_place(anchor, blockers, min_k=0):
    """Independent oracle for FR-3's candidate search combined with FR-4's
    exhaustion fallback: the first candidate (starting at k=min_k) at
    distance >= MIN_GAP from every point in `blockers`, or -- if none
    qualifies -- the search range's last candidate (k=12, j=slots-1)."""
    fallback = None
    for k, dx, dy in _FR3_CANDIDATES:
        if k < min_k:
            continue
        candidate = (anchor[0] + dx, anchor[1] + dy)
        fallback = candidate
        if all(_fr3_dist(candidate, b) >= MIN_GAP - 1e-9 for b in blockers):
            return candidate
    return fallback


def fr3_expected_positions(anchor, ranked_new_neighbor_ids, present_positions):
    """Independent oracle covering both FR-3 placement rules: the new target
    is placed via `fr3_place` from `anchor` against only `present_positions`
    (min_k=0); each new neighbor, in rank order, is placed via `fr3_place`
    from the (already-placed) target position against `present_positions`
    plus every already-placed new node (min_k=2). Returns
    {"__target__": (x, y), <neighbor id>: (x, y), ...}."""
    present = list(present_positions.values())
    target_pos = fr3_place(anchor, present, min_k=0)
    positions = {"__target__": target_pos}
    placed = [target_pos]
    for neighbor_id in ranked_new_neighbor_ids:
        pos = fr3_place(target_pos, present + placed, min_k=2)
        positions[neighbor_id] = pos
        placed.append(pos)
    return positions


class TestVO1VisibleLabelsPartitions(unittest.TestCase):
    """VO-1: equivalence partitioning over the 5 declared coverage items."""

    def test_C1_overlapping_lower_weight_box_is_rejected_and_non_overlapping_box_is_accepted(self):
        boxes = [
            {"id": "C", "weight": 1, "x1": 100, "y1": 100, "x2": 110, "y2": 110},
            {"id": "B", "weight": 3, "x1": 5, "y1": 5, "x2": 15, "y2": 15},
            {"id": "A", "weight": 5, "x1": 0, "y1": 0, "x2": 10, "y2": 10},
        ]
        result = _run_graph_model(f"model.visibleLabels({json.dumps(boxes)})")
        self.assertEqual(result, ["A", "C"])

    def test_C3_tied_weight_overlapping_boxes_break_ties_by_ascending_id(self):
        boxes = [
            {"id": "b", "weight": 3, "x1": 0, "y1": 0, "x2": 10, "y2": 10},
            {"id": "a", "weight": 3, "x1": 5, "y1": 5, "x2": 15, "y2": 15},
        ]
        result = _run_graph_model(f"model.visibleLabels({json.dumps(boxes)})")
        self.assertEqual(result, ["a"])

    def test_C4_empty_input_returns_empty_array(self):
        result = _run_graph_model("model.visibleLabels([])")
        self.assertEqual(result, [])

    def test_return_order_is_acceptance_order_not_alphabetical_or_input_order(self):
        # weight-descending processing order ("z" then "a" then "m") differs
        # from both alphabetical id order and this input array's own order;
        # none overlap, so all 3 are accepted and the returned order must
        # follow acceptance (== processing) order, not either of the others.
        boxes = [
            {"id": "m", "weight": 1, "x1": 2000, "y1": 2000, "x2": 2010, "y2": 2010},
            {"id": "a", "weight": 5, "x1": 1000, "y1": 1000, "x2": 1010, "y2": 1010},
            {"id": "z", "weight": 10, "x1": 0, "y1": 0, "x2": 10, "y2": 10},
        ]
        result = _run_graph_model(f"model.visibleLabels({json.dumps(boxes)})")
        self.assertEqual(result, ["z", "a", "m"])


class TestVO2VisibleLabelsOverlapBoundary(unittest.TestCase):
    """VO-2: boundary value (2-value) over the 4 declared coverage items."""

    def test_x_edge_touch_is_not_overlap_both_boxes_accepted(self):
        boxes = [
            {"id": "hi", "weight": 5, "x1": 0, "y1": 0, "x2": 10, "y2": 10},
            {"id": "lo", "weight": 1, "x1": 10, "y1": 0, "x2": 20, "y2": 10},
        ]
        result = _run_graph_model(f"model.visibleLabels({json.dumps(boxes)})")
        self.assertEqual(sorted(result), ["hi", "lo"])

    def test_x_overlap_by_0_01_is_overlap_lower_weight_box_rejected(self):
        boxes = [
            {"id": "hi", "weight": 5, "x1": 0, "y1": 0, "x2": 10, "y2": 10},
            {"id": "lo", "weight": 1, "x1": 9.99, "y1": 0, "x2": 19.99, "y2": 10},
        ]
        result = _run_graph_model(f"model.visibleLabels({json.dumps(boxes)})")
        self.assertEqual(result, ["hi"])

    def test_y_edge_touch_is_not_overlap_both_boxes_accepted(self):
        boxes = [
            {"id": "hi", "weight": 5, "x1": 0, "y1": 0, "x2": 10, "y2": 10},
            {"id": "lo", "weight": 1, "x1": 0, "y1": 10, "x2": 10, "y2": 20},
        ]
        result = _run_graph_model(f"model.visibleLabels({json.dumps(boxes)})")
        self.assertEqual(sorted(result), ["hi", "lo"])

    def test_y_overlap_by_0_01_is_overlap_lower_weight_box_rejected(self):
        boxes = [
            {"id": "hi", "weight": 5, "x1": 0, "y1": 0, "x2": 10, "y2": 10},
            {"id": "lo", "weight": 1, "x1": 0, "y1": 9.99, "x2": 10, "y2": 19.99},
        ]
        result = _run_graph_model(f"model.visibleLabels({json.dumps(boxes)})")
        self.assertEqual(result, ["hi"])


class TestVO3BuildNodeWeight(unittest.TestCase):
    """VO-3 (unit/build slice): equivalence partitioning over {build 노드
    data에 weight=모델 weight}. See this module's docstring for why this is
    an ordering-consistency check rather than an exact-value check."""

    def test_more_connected_nodes_have_strictly_higher_build_weight_than_fewer_connected_nodes(self):
        # Same hi/lo edge-count shape as tests.test_readability_followup's
        # 20/21-neighbor VO-2 fixtures: 2 "hi" nodes get 2 edges each
        # (target + shared aux), 2 "lo" nodes get 1 edge each (target only).
        target = _readable_node("twt", "twt.py")
        aux = _readable_node("auxwt", "auxwt.py")
        hi1 = _readable_node("hi1wt", "hi1wt.py")
        hi2 = _readable_node("hi2wt", "hi2wt.py")
        lo1 = _readable_node("lo1wt", "lo1wt.py")
        lo2 = _readable_node("lo2wt", "lo2wt.py")
        connections = [
            _connection("e-t-hi1", "twt", "hi1wt"), _connection("e-hi1-aux", "hi1wt", "auxwt"),
            _connection("e-t-hi2", "twt", "hi2wt"), _connection("e-hi2-aux", "hi2wt", "auxwt"),
            _connection("e-t-lo1", "twt", "lo1wt"),
            _connection("e-t-lo2", "twt", "lo2wt"),
        ]
        value = _payload_for([target, aux, hi1, hi2, lo1, lo2], connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"const byId = elementById(built); "
            f"return {{hi1: byId['hi1wt'].weight, hi2: byId['hi2wt'].weight, "
            f"lo1: byId['lo1wt'].weight, lo2: byId['lo2wt'].weight}}; }})()"
        )
        for key in ("hi1", "hi2", "lo1", "lo2"):
            self.assertIsInstance(result[key], (int, float), f"{key}: expected build() node data.weight to be numeric")
        self.assertEqual(result["hi1"], result["hi2"], "equal edge counts must yield equal weight")
        self.assertEqual(result["lo1"], result["lo2"], "equal edge counts must yield equal weight")
        self.assertGreater(result["hi1"], result["lo1"], "more edges must yield strictly higher weight")


class TestVO4ExpandPositionsFR3(unittest.TestCase):
    """VO-4: equivalence partitioning over the 5 declared coverage items."""

    def test_target_new_anchor_empty_matches_FR3_oracle(self):
        target = _readable_node("t-empty", "t-empty.py")
        value = _payload_for([target], [])
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {{}}, 't-empty'); }})()"
        )
        expected = fr3_place((0.0, 0.0), [], min_k=0)
        actual = result["positions"]["t-empty"]
        self.assertAlmostEqual(actual["x"], expected[0], delta=1e-9)
        self.assertAlmostEqual(actual["y"], expected[1], delta=1e-9)

    def test_target_new_anchor_occupied_by_present_neighbor_matches_FR3_oracle(self):
        # p1 is bumped to weight 2 (target edge + 1 extra edge to a filler
        # node) so it strictly outranks p2 (weight 1) -- same construction as
        # tests.test_readability_followup's anchor-ranking precedent -- so
        # the (unchanged) anchor rule picks p1's given position as the anchor.
        target = _readable_node("t-anchor", "t-anchor.py")
        p1 = _readable_node("p1-anchor", "p1-anchor.py")
        p2 = _readable_node("p2-anchor", "p2-anchor.py")
        filler = _readable_node("filler-anchor", "filler-anchor.py")
        connections = [
            _connection("e-t-p1", "t-anchor", "p1-anchor"),
            _connection("e-t-p2", "t-anchor", "p2-anchor"),
            _connection("e-p1-filler", "p1-anchor", "filler-anchor"),
        ]
        value = _payload_for([target, p1, p2, filler], connections)
        present = {"p1-anchor": {"x": 10.0, "y": 20.0}, "p2-anchor": {"x": 30.0, "y": 40.0}}
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {json.dumps(present)}, 't-anchor'); }})()"
        )
        anchor = (10.0, 20.0)
        blockers = [(10.0, 20.0), (30.0, 40.0)]
        expected = fr3_place(anchor, blockers, min_k=0)
        actual = result["positions"]["t-anchor"]
        self.assertAlmostEqual(actual["x"], expected[0], delta=1e-9)
        self.assertAlmostEqual(actual["y"], expected[1], delta=1e-9)
        for blocker in blockers:
            self.assertGreaterEqual(_fr3_dist((actual["x"], actual["y"]), blocker), MIN_GAP - 1e-9)
        # present 위치 불변: neither present anchor source may leak a position entry.
        self.assertEqual(sorted(result["positions"].keys()), sorted(result["nodes"]))
        self.assertNotIn("p1-anchor", result["positions"])
        self.assertNotIn("p2-anchor", result["positions"])

    def test_multiple_new_neighbors_match_FR3_oracle_and_maintain_min_gap(self):
        # All 4 neighbors tie at weight 1 (single edge to target each), so
        # FR-2's id-ascending tie-break ranks them n-multi0..n-multi3.
        target = _readable_node("t-multi", "t-multi.py")
        neighbors = [_readable_node(f"n-multi{i}", f"n-multi{i}.py") for i in range(4)]
        connections = [_connection(f"e-t-n{i}", "t-multi", f"n-multi{i}") for i in range(4)]
        value = _payload_for([target] + neighbors, connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"const r = model.expand(built, {{}}, 't-multi'); "
            f"return {{target: r.positions['t-multi'], "
            f"neighbors: [0,1,2,3].map(i => r.positions['n-multi' + i])}}; }})()"
        )
        ranked_ids = [f"n-multi{i}" for i in range(4)]
        expected = fr3_expected_positions((0.0, 0.0), ranked_ids, {})
        tx, ty = result["target"]["x"], result["target"]["y"]
        self.assertAlmostEqual(tx, expected["__target__"][0], delta=1e-9)
        self.assertAlmostEqual(ty, expected["__target__"][1], delta=1e-9)
        all_points = [(tx, ty)]
        for i, neighbor_id in enumerate(ranked_ids):
            pos = result["neighbors"][i]
            ex, ey = expected[neighbor_id]
            self.assertAlmostEqual(pos["x"], ex, delta=1e-9, msg=f"neighbor rank {i}")
            self.assertAlmostEqual(pos["y"], ey, delta=1e-9, msg=f"neighbor rank {i}")
            all_points.append((pos["x"], pos["y"]))
        for i in range(len(all_points)):
            for j in range(i + 1, len(all_points)):
                self.assertGreaterEqual(
                    _fr3_dist(all_points[i], all_points[j]), MIN_GAP - 1e-9,
                    f"min-gap violated between placed points {i} and {j}",
                )

    def test_nodes_parents_edges_unchanged_alongside_FR3_positions(self):
        target = _readable_node("t-struct", "lvlX/lvlY/t-struct.py")
        hidden_neighbor = _readable_node("h-struct", "h-struct.py")
        present_neighbor = _readable_node("p-struct", "p-struct.py")
        connections = [
            _connection("e-t-h", "t-struct", "h-struct"),
            _connection("e-t-p", "t-struct", "p-struct"),
        ]
        value = _payload_for([target, hidden_neighbor, present_neighbor], connections)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"const chain = ancestorChainBottomUp(built, 't-struct').slice().reverse(); "
            f"const present = {{'p-struct': {{x: 5, y: 5}}}}; "
            f"const r = model.expand(built, present, 't-struct'); "
            f"return {{r: r, chainTopFirst: chain}}; }})()"
        )
        r = result["r"]
        self.assertEqual(sorted(r["nodes"]), sorted(["t-struct", "h-struct"]))
        self.assertEqual(r["parents"], result["chainTopFirst"])
        self.assertIn("edge:e-t-h", r["edges"])
        self.assertIn("edge:e-t-p", r["edges"])
        self.assertEqual(sorted(r["positions"].keys()), sorted(r["nodes"]))
        self.assertNotIn("p-struct", r["positions"])


class TestVO5ExpandGapBoundary(unittest.TestCase):
    """VO-5: boundary value (2-value) over {거리 60 허용, 59.99 거부}. The
    fixture's single new neighbor's first FR-3 candidate (k=2, j=0) is
    independently known to be target_position + (120, 0), since the target
    itself anchors at the origin (no present neighbor/ancestor)."""

    def _fixture(self, blocker_id):
        target = _readable_node("t-gap", "t-gap.py")
        neighbor = _readable_node("n-gap", "n-gap.py")
        blocker = _readable_node(blocker_id, f"{blocker_id}.py")
        connections = [_connection("e-t-n-gap", "t-gap", "n-gap")]
        return _payload_for([target, neighbor, blocker], connections)

    def test_C7_present_exactly_60_from_the_first_candidate_is_accepted(self):
        value = self._fixture("blocker-60")
        present = {"blocker-60": {"x": 180.0, "y": 0.0}}  # distance 60 from (120, 0)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {json.dumps(present)}, 't-gap').positions['n-gap']; }})()"
        )
        self.assertAlmostEqual(result["x"], 120.0, delta=1e-9)
        self.assertAlmostEqual(result["y"], 0.0, delta=1e-9)

    def test_C7_present_59_99_from_the_first_candidate_is_rejected_and_the_next_candidate_is_used(self):
        value = self._fixture("blocker-59-99")
        present = {"blocker-59-99": {"x": 179.99, "y": 0.0}}  # distance 59.99 from (120, 0)
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {json.dumps(present)}, 't-gap').positions['n-gap']; }})()"
        )
        expected = fr3_place((0.0, 0.0), [(179.99, 0.0), (0.0, 0.0)], min_k=2)
        self.assertAlmostEqual(result["x"], expected[0], delta=1e-9)
        self.assertAlmostEqual(result["y"], expected[1], delta=1e-9)
        # the boundary-rejected first candidate itself must not have been chosen.
        self.assertFalse(abs(result["x"] - 120.0) < 1e-6 and abs(result["y"]) < 1e-6)


class TestVO6ExpandCandidateExhaustion(unittest.TestCase):
    """VO-6 (FR-4, C-8): error guessing -- block every one of FR-3's
    candidates around the target's own (origin) anchor so the search is
    fully exhausted; FR-4 requires the last candidate (k=12, j=slots-1),
    with no exception."""

    def test_target_falls_back_to_the_last_candidate_when_every_candidate_is_blocked(self):
        target = _readable_node("t-block", "t-block.py")
        blockers = [_readable_node(f"blk{i}", f"blk{i}.py") for i in range(len(_FR3_CANDIDATES))]
        value = _payload_for([target] + blockers, [])
        present = {
            f"blk{i}": {"x": dx, "y": dy}
            for i, (_, dx, dy) in enumerate(_FR3_CANDIDATES)
        }
        result = _run_graph_model(
            f"(() => {{ const built = model.build({json.dumps(value)}); "
            f"return model.expand(built, {json.dumps(present)}, 't-block'); }})()"
        )
        self.assertIsNotNone(result)
        _, last_dx, last_dy = _FR3_CANDIDATES[-1]
        self.assertAlmostEqual(result["positions"]["t-block"]["x"], last_dx, delta=1e-9)
        self.assertAlmostEqual(result["positions"]["t-block"]["y"], last_dy, delta=1e-9)


def _overview_node(node_id, label, file_path, category, **metrics):
    return {
        "id": node_id, "label": label, "category": category,
        "span": {"file_path": file_path},
        "metadata": {"analysis": metrics},
    }


class TestVO7BuildOverviewCategoryLabelRule(unittest.TestCase):
    """VO-7 (FR-6, C-9): equivalence partitioning over the 2 declared
    coverage items (category in {file, module, package} x1 each, and
    category=function, all with label != file_path). Expected short/full
    labels reuse file_path pairs already independently established by
    tests.test_readability_dashboard's VO-18 (FR-1's short_labels
    algorithm), not re-derived here."""

    def test_file_category_with_custom_label_shows_the_short_file_label_and_full_label_is_the_file_path(self):
        nodes = [
            _overview_node("py:app/src/pkg/mod.py", "Foo", "app/src/pkg/mod.py", "file", weighted_centrality_cost=30),
            _overview_node("py:app/src/other/util.py", "app/src/other/util.py", "app/src/other/util.py", "file", weighted_centrality_cost=20),
        ]
        result = run_overview_js(json.dumps(nodes))
        by_id = {item["id"]: item for item in result["focus"]}
        item = by_id["py:app/src/pkg/mod.py"]
        self.assertEqual(item["label"], "mod.py")
        self.assertEqual(item["full_label"], "app/src/pkg/mod.py")

    def test_module_category_with_custom_label_shows_the_short_file_label_and_full_label_is_the_file_path(self):
        nodes = [
            _overview_node("py:pkg/graph.py", "Foo", "pkg/graph.py", "module", weighted_centrality_cost=50),
            _overview_node("py:pkg/other.py", "pkg/other.py", "pkg/other.py", "module", weighted_centrality_cost=40),
        ]
        result = run_overview_js(json.dumps(nodes))
        by_id = {item["id"]: item for item in result["focus"]}
        item = by_id["py:pkg/graph.py"]
        self.assertEqual(item["label"], "graph.py")
        self.assertEqual(item["full_label"], "pkg/graph.py")

    def test_package_category_with_custom_label_and_colliding_basenames_shows_the_full_path_label(self):
        # FR-1: "a/x/m.py" vs "b/x/m.py" collide on both basename ("m.py")
        # and one-level-up dir ("x/m.py"), so the full path is the required
        # short label (same pair as VO-18's third coverage item).
        nodes = [
            _overview_node("py:a/x/m.py", "Foo", "a/x/m.py", "package", weighted_centrality_cost=50),
            _overview_node("py:b/x/m.py", "Bar", "b/x/m.py", "package", weighted_centrality_cost=40),
        ]
        result = run_overview_js(json.dumps(nodes))
        by_id = {item["id"]: item for item in result["focus"]}
        item = by_id["py:a/x/m.py"]
        self.assertEqual(item["label"], "a/x/m.py")
        self.assertEqual(item["full_label"], "a/x/m.py")

    def test_non_file_module_package_category_with_custom_label_shows_file_label_colon_label(self):
        nodes = [
            _overview_node("py:pkg/graph.py#resolve", "resolve", "pkg/graph.py", "function", weighted_centrality_cost=50),
            _overview_node("py:pkg/other.py", "pkg/other.py", "pkg/other.py", "module", weighted_centrality_cost=1),
        ]
        result = run_overview_js(json.dumps(nodes))
        by_id = {item["id"]: item for item in result["focus"]}
        item = by_id["py:pkg/graph.py#resolve"]
        self.assertEqual(item["label"], "graph.py:resolve")


if __name__ == "__main__":
    unittest.main()
