"""VO-6, VO-7, and the bottlenecks slice of VO-10 for report/bottlenecks/generate.py.

VO-6 (FR-6, C-10): decision table over kind 5종 x {점수 계산, 동점 tie-break} for
`prioritize_candidates`. Expected scores/order are hand-computed from FR-6's
formulas, independent of the implementation.

VO-7 (FR-7, FR-12, C-10, C-11, C-12, C-16): equivalence partitioning over
{섹션 id 7개, 빈 candidate, v1 거부, bottlenecks-data 계약, 이스케이프, 금지어 부재}
for `render_report`.

VO-10 (QR-5, bottlenecks slice): metamorphic — regenerating from the same
input twice yields byte-identical HTML.

VO-13 (FR-14): decision table over {같은 (kind,target) 3건→1건·duplicate_count
3, kind당 3건 이상→2건, 동점 id, 서로 다른 kind 혼합 정렬, #focus에 "같은 대상 3건"}
for `focus_candidates`. Expected grouping/order is hand-computed from FR-14's
rules, independent of the implementation.

VO-19 (FR-21, spec v5): equivalence partitioning over {`<lang>:<module>#<qual>`
id target with qual, id target without qual, module-basename conflict across
2 id targets, non-id-format ("검색어") target unchanged, #focus 이유 문장에서
원문 부재·title 속성에 존재} for `prioritize_candidates`/`focus_candidates`
labels (unit) and `render_report`'s `#focus` section (integration). Expected
labels are hand-computed by converting the id target's module ('.' -> '/')
and applying FR-1's short-labels algorithm, then appending `:<qual>` when a
qual is present -- independent of the implementation.
"""
import json
import re
import subprocess
import unittest
from pathlib import Path

from agent_view import build_agent_view, build_snapshot, default_profile_path, load_profile
from bottlenecks import analyze_bottlenecks, bottlenecks_to_json, parse_harness_profile
from language_analyzers.python.graph import PythonGraphAnalyzer
from report.bottlenecks.generate import focus_candidates, prioritize_candidates, render_report
from report.shared.document import ReportInputError

# FR-12: judgement words that must never appear in generated report text.
FORBIDDEN_WORDS = ("위험", "나쁨", "품질")

SECTION_IDS = ("overview", "focus", "kinds", "candidates", "rankings", "appendix", "glossary")


def _harness(visible=100, maximum=100):
    return parse_harness_profile({
        "schema": "harness_profile.v1", "id": "fixed", "version": 1,
        "provenance_status": "unverified_baseline",
        "content_search": {"matching": "fixed_string_case_sensitive", "order": "path_lexical_then_numeric_line", "visible_lines": visible, "cap_unit": "matching_lines", "same_line_occurrences": "preserved"},
        "path_search": {"matching": "fixed_string_case_sensitive", "order": "path_lexical_then_numeric_line", "visible_lines": visible, "cap_unit": "matching_paths"},
        "read": {"bounds": "one_based_inclusive", "max_lines": maximum, "eof": "clamp", "truncation": "actual_omitted_lines"},
        "features": {"fixed_string_search": "supported", "line_range_read": "supported", "semantic_search": "unsupported", "index": "unsupported", "context_compaction": "observation_only", "parallelism": "observation_only", "subagents": "observation_only"},
        "assumptions": {"automatic_injection": "unverified_baseline", "list_depth": 2},
    })


def _base_payload():
    """A structurally valid bottlenecks.v2 payload built from the real,
    non-implementation analyzer pipeline (bottlenecks/core.py), so that
    dependency_network/probes/coverage/etc. are self-consistent. The
    `candidates` list is then overwritten by each test with a hand-crafted
    fixture to exercise FR-6/FR-7 deterministically."""
    files = {"a.py": "def one():\n return 1\n", "b.py": "from a import one\none()\n"}
    root, profile = Path("/repo"), load_profile(default_profile_path())
    snapshot = build_snapshot(root, sorted(files), policy=profile.scan_policy(), reader=lambda path: files[path.relative_to(root).as_posix()], ignore_source="test")
    architecture = PythonGraphAnalyzer(root, snapshot).analyze()
    graph = build_agent_view(architecture, profile=profile, snapshot=snapshot)
    report = analyze_bottlenecks(snapshot, architecture, graph, _harness())
    return json.loads(bottlenecks_to_json(report))


def _candidate(id_, kind, target, metrics):
    return {"id": id_, "kind": kind, "target": target, "probe_ids": [], "metrics": metrics, "evidence": [], "coverage": "static_profile_probe", "status": "static_candidate"}


# Hand-crafted candidates covering all 5 scored kinds plus a tie, per FR-6.
FIXTURE_CANDIDATES = [
    _candidate("cand-b-trunc", "output_truncation", "needle_term", {"total_count": 10, "visible_count": 3, "omitted_count": 7}),
    _candidate("cand-a-trunc", "output_truncation", "other_term", {"total_count": 9, "visible_count": 2, "omitted_count": 7}),
    _candidate("cand-multi", "multiple_results", "dup_term", {"total_count": 5, "visible_count": 5, "omitted_count": 0}),
    _candidate("cand-read", "read_limit", "node-read", {"line_count": 120, "read_line_limit": 40}),
    _candidate("cand-spread", "evidence_spread", "node-spread", {"file_count": 3, "line_span": 5, "read_line_limit": 40}),
    _candidate("cand-unresolved-with-count", "unresolved_boundary", "node-unres1", {"unresolved_count": 4}),
    _candidate("cand-unresolved-empty", "unresolved_boundary", "node-unres2", {}),
]

# Independently hand-computed from FR-6's formulas:
#   output_truncation -> omitted_count; multiple_results -> total_count;
#   read_limit -> line_count - read_line_limit; evidence_spread -> file_count;
#   unresolved_boundary -> unresolved_count (default 1 if absent).
# cand-read=80, cand-a-trunc=7, cand-b-trunc=7 (tie -> id asc),
# cand-multi=5, cand-unresolved-with-count=4, cand-spread=3, cand-unresolved-empty=1.
EXPECTED_ORDER = [
    ("cand-read", 80), ("cand-a-trunc", 7), ("cand-b-trunc", 7), ("cand-multi", 5),
    ("cand-unresolved-with-count", 4), ("cand-spread", 3), ("cand-unresolved-empty", 1),
]


def _payload_with_candidates(candidates):
    payload = _base_payload()
    payload["candidates"] = candidates
    return payload


def _has_id(html, element_id):
    # TD-1: attribute quote style is not a contract; accept either ' or ".
    return re.search(rf"""id=['"]{element_id}['"]""", html) is not None


def _without_title_attributes(html):
    """VO-19: strip `title="..."` (or `'...'`) attribute values so a check
    for the raw target id can distinguish "only inside a title attribute"
    from "present in the visible reason text"."""
    return re.sub(r"""title\s*=\s*(["']).*?\1""", " ", html, flags=re.DOTALL)


def _section_content(html, section_id):
    """TD-3: content of the <section ...> whose id is `section_id`, scoped
    from that id attribute up to the next `<section` tag (or end of doc)."""
    marker = re.search(rf"""id=['"]{section_id}['"]""", html)
    assert marker is not None, f"missing id={section_id}"
    rest = html[marker.end():]
    next_section = re.search(r"<section\b", rest, re.IGNORECASE)
    return rest[:next_section.start()] if next_section else rest


class TestVO6PrioritizeCandidates(unittest.TestCase):
    """VO-6: decision table, kind 5종 x {점수 계산, 동점 tie-break}."""

    def test_all_five_kinds_are_scored_per_FR6_and_ties_break_by_id_ascending(self):
        data = _payload_with_candidates(FIXTURE_CANDIDATES)
        result = prioritize_candidates(data)
        self.assertEqual([(item["candidate"]["id"], item["score"]) for item in result], EXPECTED_ORDER)

    def test_output_truncation_score_is_omitted_count(self):
        data = _payload_with_candidates([FIXTURE_CANDIDATES[0]])
        result = prioritize_candidates(data)
        self.assertEqual(result[0]["score"], 7)

    def test_multiple_results_score_is_total_count(self):
        data = _payload_with_candidates([FIXTURE_CANDIDATES[2]])
        result = prioritize_candidates(data)
        self.assertEqual(result[0]["score"], 5)

    def test_read_limit_score_is_line_count_minus_read_line_limit(self):
        data = _payload_with_candidates([FIXTURE_CANDIDATES[3]])
        result = prioritize_candidates(data)
        self.assertEqual(result[0]["score"], 80)

    def test_evidence_spread_score_is_file_count(self):
        data = _payload_with_candidates([FIXTURE_CANDIDATES[4]])
        result = prioritize_candidates(data)
        self.assertEqual(result[0]["score"], 3)

    def test_unresolved_boundary_score_is_unresolved_count_or_one_when_absent(self):
        data = _payload_with_candidates([FIXTURE_CANDIDATES[5]])
        self.assertEqual(prioritize_candidates(data)[0]["score"], 4)
        data_missing = _payload_with_candidates([FIXTURE_CANDIDATES[6]])
        self.assertEqual(prioritize_candidates(data_missing)[0]["score"], 1)

    def test_label_is_the_short_label_of_the_target(self):
        # All fixture targets are distinct, slash-free strings, so short_labels
        # (FR-1: basename with no conflicts) resolves each to itself.
        data = _payload_with_candidates(FIXTURE_CANDIDATES)
        result = prioritize_candidates(data)
        by_id = {item["candidate"]["id"]: item["label"] for item in result}
        for candidate in FIXTURE_CANDIDATES:
            self.assertEqual(by_id[candidate["id"]], candidate["target"])


class TestVO7RenderReport(unittest.TestCase):
    """VO-7: equivalence partitioning over the 6 declared coverage items."""

    def test_all_seven_section_ids_are_present(self):
        html = render_report(_payload_with_candidates(FIXTURE_CANDIDATES))
        for section_id in SECTION_IDS:
            self.assertTrue(_has_id(html, section_id), f"missing section #{section_id}")

    def test_connection_constraint_kind_is_marked_as_not_currently_generated_with_zero_count(self):
        html = render_report(_payload_with_candidates(FIXTURE_CANDIDATES))
        self.assertIn("현재 생성되지 않음", html)
        # The literal marker text is pinned by FR-7; the count near it (this
        # kind is never generated) must be 0. Korean kind *names* for the
        # other kinds are not pinned by the spec (see report), so this is the
        # one kind-count pairing checkable without an invented Korean oracle.
        kinds_section = _section_content(html, "kinds")
        window = re.search(r"현재 생성되지 않음.{0,200}?(\d+)\D{0,20}건", kinds_section, re.DOTALL)
        self.assertIsNotNone(window, "expected a nearby '<count>건' after the connection_constraint marker")
        self.assertEqual(window.group(1), "0")

    def test_empty_candidates_shows_none_found_message_without_raising(self):
        html = render_report(_payload_with_candidates([]))
        self.assertIn("발견된 후보 없음", html)

    def test_v1_schema_payload_is_rejected(self):
        with self.assertRaises(ReportInputError):
            render_report({"schema": "bottlenecks.v1"})

    def test_bottlenecks_data_script_round_trips_the_input_payload(self):
        # TD-2: this script's quote style IS an existing contract (single
        # quotes) — see tests/test_m3_futuramaapi_acceptance.py:96-98.
        payload = _payload_with_candidates(FIXTURE_CANDIDATES)
        html = render_report(payload)
        match = re.search(r"<script id='bottlenecks-data' type='application/json'>(.*?)</script>", html, re.DOTALL)
        self.assertIsNotNone(match, "expected a #bottlenecks-data payload script")
        self.assertEqual(json.loads(match.group(1)), payload)

    def test_C16_hostile_candidate_target_is_escaped_not_executable(self):
        hostile = "<script>alert(1)</script>"
        candidates = [_candidate("cand-hostile", "evidence_spread", hostile, {"file_count": 2})]
        html = render_report(_payload_with_candidates(candidates))
        self.assertNotIn(hostile, html)

    def test_FR12_forbidden_judgement_words_are_absent(self):
        html = render_report(_payload_with_candidates(FIXTURE_CANDIDATES))
        for word in FORBIDDEN_WORDS:
            self.assertNotIn(word, html, f"forbidden judgement word present: {word}")

    def test_kinds_section_reports_the_correct_count_per_candidate_kind(self):
        # TD-3: scope this check to the #kinds section content only (not,
        # e.g., a <select> filter option elsewhere on the page). The spec
        # does not pin the Korean display name for each kind (only for
        # connection_constraint and the empty-candidates message, checked
        # separately), so this asserts the independently-known multiset of
        # per-kind counts is present, rather than inventing a name->kind
        # mapping: output_truncation=2, multiple_results=1, read_limit=1,
        # evidence_spread=1, unresolved_boundary=2, connection_constraint=0.
        html = render_report(_payload_with_candidates(FIXTURE_CANDIDATES))
        kinds_section = _section_content(html, "kinds")
        counts = [int(value) for value in re.findall(r"(\d+)\D{0,20}건", kinds_section)]
        self.assertEqual(sorted(counts), [0, 1, 1, 1, 2, 2])
        self.assertEqual(len(counts), 6, "expected exactly 6 kind panels (5 scored + connection_constraint)")


# FR-14/VO-13 fixture: hand-crafted candidates covering all 5 declared
# coverage items in one integrated set (plus a dedicated group for item 1).
#
# Group G1 (kind=output_truncation, target="dup", 3 candidates -> collapses
# to 1 with duplicate_count=3, keeping the highest score with id-ascending
# tie-break): g1-a/g1-b both score 7 (tie -> "g1-a" < "g1-b" wins), g1-c=5.
#
# Kind K2 (multiple_results, score=total_count) has 4 *distinct* targets
# (duplicate_count=1 each) -> only the top 2 by score survive: k2-1(40),
# k2-2(30); k2-3(20), k2-4(10) are dropped.
#
# K3 (read_limit, score=line_count-read_line_limit): a single candidate,
# k3-x, scored to exactly tie G1's representative (7), to exercise the
# *final*, cross-kind tie-break (distinct from G1's within-group tie-break).
FOCUS_FIXTURE_CANDIDATES = [
    _candidate("g1-b", "output_truncation", "dup", {"total_count": 10, "visible_count": 3, "omitted_count": 7}),
    _candidate("g1-a", "output_truncation", "dup", {"total_count": 9, "visible_count": 2, "omitted_count": 7}),
    _candidate("g1-c", "output_truncation", "dup", {"total_count": 8, "visible_count": 3, "omitted_count": 5}),
    _candidate("k2-1", "multiple_results", "M1", {"total_count": 40, "visible_count": 40, "omitted_count": 0}),
    _candidate("k2-2", "multiple_results", "M2", {"total_count": 30, "visible_count": 30, "omitted_count": 0}),
    _candidate("k2-3", "multiple_results", "M3", {"total_count": 20, "visible_count": 20, "omitted_count": 0}),
    _candidate("k2-4", "multiple_results", "M4", {"total_count": 10, "visible_count": 10, "omitted_count": 0}),
    _candidate("k3-x", "read_limit", "R1", {"line_count": 47, "read_line_limit": 40}),
]

# Independently hand-computed final order (score desc, id asc), after
# (kind,target) collapse and per-kind top-2 selection:
#   k2-1=40, k2-2=30, {g1-a=7 (dup_count 3), k3-x=7 (dup_count 1)} tie -> id asc.
FOCUS_EXPECTED_ORDER = [
    ("k2-1", 40, 1), ("k2-2", 30, 1), ("g1-a", 7, 3), ("k3-x", 7, 1),
]


class TestVO13FocusCandidates(unittest.TestCase):
    """VO-13: decision table over the 5 declared coverage items."""

    def test_same_kind_target_group_of_3_collapses_to_1_with_duplicate_count_3(self):
        data = _payload_with_candidates(FOCUS_FIXTURE_CANDIDATES)
        result = focus_candidates(data)
        representative = next(item for item in result if item["candidate"]["id"] in ("g1-a", "g1-b", "g1-c"))
        self.assertEqual(representative["candidate"]["id"], "g1-a")
        self.assertEqual(representative["score"], 7)
        self.assertEqual(representative["duplicate_count"], 3)
        survivors = [item for item in result if item["candidate"]["target"] == "dup"]
        self.assertEqual(len(survivors), 1)

    def test_kind_with_3_or_more_distinct_targets_keeps_only_its_top_2(self):
        data = _payload_with_candidates(FOCUS_FIXTURE_CANDIDATES)
        result = focus_candidates(data)
        multiple_results_ids = [item["candidate"]["id"] for item in result if item["candidate"]["kind"] == "multiple_results"]
        self.assertEqual(multiple_results_ids, ["k2-1", "k2-2"])

    def test_tied_final_score_across_different_kinds_breaks_by_id_ascending(self):
        data = _payload_with_candidates(FOCUS_FIXTURE_CANDIDATES)
        result = focus_candidates(data)
        tied = [item["candidate"]["id"] for item in result if item["score"] == 7]
        self.assertEqual(tied, ["g1-a", "k3-x"])

    def test_final_order_is_score_desc_then_id_asc_mixed_across_kinds(self):
        data = _payload_with_candidates(FOCUS_FIXTURE_CANDIDATES)
        result = focus_candidates(data)
        observed = [(item["candidate"]["id"], item["score"], item["duplicate_count"]) for item in result]
        self.assertEqual(observed, FOCUS_EXPECTED_ORDER)

    def test_focus_section_shows_same_target_marker_for_duplicate_count_3(self):
        html = render_report(_payload_with_candidates(FOCUS_FIXTURE_CANDIDATES))
        self.assertIn("같은 대상 3건", html)
        # A duplicate_count of 1 (e.g. k2-1/k2-2/k3-x) must not get a marker.
        self.assertNotIn("같은 대상 1건", html)


class TestVO19IdTargetLabels(unittest.TestCase):
    """VO-19 (FR-21): equivalence partitioning over the 5 declared coverage
    items. Expected labels are hand-computed from FR-21's rule (module
    '.'->'/' then FR-1 short-labels, plus ':<qual>' when present), independent
    of the implementation."""

    def test_id_targets_with_qual_use_module_short_label_colon_qual(self):
        # Modules "a.b.graph" -> "a/b/graph" and "x.y.other" -> "x/y/other"
        # have distinct basenames ("graph","other") and no conflict, so FR-1
        # resolves each to its basename with no escalation.
        candidates = [
            _candidate("c1", "evidence_spread", "py:a.b.graph#C.m", {"file_count": 1}),
            _candidate("c2", "evidence_spread", "py:x.y.other#f", {"file_count": 1}),
        ]
        result = prioritize_candidates(_payload_with_candidates(candidates))
        by_id = {item["candidate"]["id"]: item["label"] for item in result}
        self.assertEqual(by_id["c1"], "graph:C.m")
        self.assertEqual(by_id["c2"], "other:f")

    def test_id_target_without_qual_is_the_module_short_label_alone(self):
        candidates = [_candidate("c1", "evidence_spread", "py:a.b.mod", {"file_count": 1})]
        result = prioritize_candidates(_payload_with_candidates(candidates))
        self.assertEqual(result[0]["label"], "mod")

    def test_module_basename_conflict_across_two_id_targets_keeps_minimal_distinguishing_path(self):
        # Modules "a.x.m" -> "a/x/m" and "b.x.m" -> "b/x/m": no common leading
        # directory, and both the basename ("m") and one level up ("x/m")
        # collide, so FR-1 needs the full module path to distinguish them.
        candidates = [
            _candidate("c1", "evidence_spread", "py:a.x.m#f", {"file_count": 1}),
            _candidate("c2", "evidence_spread", "py:b.x.m#g", {"file_count": 1}),
        ]
        result = prioritize_candidates(_payload_with_candidates(candidates))
        by_id = {item["candidate"]["id"]: item["label"] for item in result}
        self.assertEqual(by_id["c1"], "a/x/m:f")
        self.assertEqual(by_id["c2"], "b/x/m:g")

    def test_non_id_format_search_term_target_label_is_unchanged_alongside_an_id_target(self):
        # "needle_term" has no "<lang>:<module>#<qual>" shape, so FR-21 does
        # not apply to it; it keeps FR-6's target-short-label behaviour
        # (a single non-path target resolves to itself), even in the
        # presence of an id-format target that FR-21 does apply to.
        candidates = [
            _candidate("c-id", "evidence_spread", "py:a.b.graph#C.m", {"file_count": 1}),
            _candidate("c-term", "evidence_spread", "needle_term", {"file_count": 2}),
        ]
        result = prioritize_candidates(_payload_with_candidates(candidates))
        by_id = {item["candidate"]["id"]: item["label"] for item in result}
        self.assertEqual(by_id["c-id"], "graph:C.m")
        self.assertEqual(by_id["c-term"], "needle_term")

    def test_focus_section_reason_text_omits_the_raw_id_target_but_keeps_it_in_a_title_attribute(self):
        target = "py:pkg.mod#Sym"
        candidates = [_candidate("cand-id-target", "evidence_spread", target, {"file_count": 5})]
        html = render_report(_payload_with_candidates(candidates))
        focus_section = _section_content(html, "focus")
        self.assertIn(target, focus_section, "expected the raw target id to appear somewhere in #focus (in a title attribute)")
        visible_only = _without_title_attributes(focus_section)
        self.assertNotIn(target, visible_only, "raw target id must not be repeated in the visible reason text")


def _extract_candidate_rows(html):
    """VO-21: parse `<tr data-candidate-row ...>...</tr>` rows out of the
    rendered candidate table -- attributes (including any `data-*`, e.g.
    `data-search`) and tag-stripped textContent -- without assuming any
    other markup shape."""
    rows = []
    for match in re.finditer(r"<tr\s+data-candidate-row([^>]*)>(.*?)</tr>", html, re.DOTALL):
        attrs_blob, inner = match.groups()
        attrs = {name: value for name, _quote, value in re.findall(
            r"""([a-zA-Z0-9_-]+)\s*=\s*(["'])(.*?)\2""", attrs_blob, re.DOTALL)}
        text_content = re.sub(r"<[^>]+>", "", inner)
        rows.append({"attrs": attrs, "textContent": text_content})
    assert rows, "expected at least one <tr data-candidate-row ...> in the rendered HTML"
    return rows


def _extract_last_unlabelled_script(html):
    """VO-21: the inline filter script is the last `<script>` tag with no
    `id` attribute (the data payload and any other scripts on the page all
    carry an `id`, per FR-7/VO-7's `#bottlenecks-data` contract)."""
    scripts = re.findall(r"<script(\s[^>]*)?>(.*?)</script>", html, re.DOTALL)
    unlabelled = [body for attrs, body in scripts if attrs is None or "id=" not in attrs]
    assert unlabelled, "expected at least one <script> without an id attribute"
    return unlabelled[-1]


def _run_filter_script(html, query):
    """VO-21: executes the rendered HTML's inline candidate-filter script in
    a minimal node DOM stub (no browser, no implementation-side helpers),
    then reports each row's `hidden` state and the `#candidate-count` text.
    Row `dataset` is reconstructed from each row's `data-*` attributes, per
    the note that the existing filter script reads `row.dataset`."""
    rows = _extract_candidate_rows(html)
    script_body = _extract_last_unlabelled_script(html)
    rows_json = json.dumps([
        {
            "dataset": {
                # `dataset.foo` <-> `data-foo` (camelCase, but none of our
                # fixture attribute names contain '-', so no conversion is
                # needed here).
                key[len("data-"):]: value
                for key, value in row["attrs"].items() if key.startswith("data-")
            },
            "textContent": row["textContent"],
        }
        for row in rows
    ])
    script = f'''
const vm = require('vm');
const rowsData = {rows_json};
const rows = rowsData.map((r) => ({{...r, hidden: false}}));
let inputListener = null;
let kindListener = null;
const input = {{value: '', addEventListener: (name, fn) => {{ if (name === 'input') inputListener = fn; }}}};
const kindSelect = {{value: 'all', addEventListener: (name, fn) => {{ if (name === 'change') kindListener = fn; }}}};
const count = {{textContent: ''}};
const elementsById = {{
  'candidate-filter': input, 'candidate-kind-filter': kindSelect, 'candidate-count': count,
}};
const ctx = {{
  document: {{
    getElementById: (id) => elementsById[id],
    querySelectorAll: (selector) => selector === '[data-candidate-row]' ? rows : [],
  }},
}};
vm.createContext(ctx);
vm.runInContext({json.dumps(script_body)}, ctx);
if (typeof inputListener !== 'function') {{
  console.log(JSON.stringify({{missingObservable: "the filter script never called input.addEventListener('input', ...)"}}));
}} else {{
  input.value = {json.dumps(query)};
  inputListener();
  console.log(JSON.stringify({{
    count: count.textContent,
    visibleTextContents: rows.filter((r) => !r.hidden).map((r) => r.textContent),
    hiddenByIndex: rows.map((r) => r.hidden),
  }}));
}}
'''
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class TestVO21CandidateFilterScript(unittest.TestCase):
    """VO-21 (FR-21 검색): equivalence partitioning over the 3 declared
    coverage items, exercising the rendered HTML's own inline filter script
    (not a reimplementation of it) against a minimal node DOM stub."""

    def _html(self):
        candidates = [
            _candidate("cand-id-target", "evidence_spread", "py:pkg.mod#Sym", {"file_count": 3}),
            _candidate("cand-term-target", "output_truncation", "needle_term", {"total_count": 5, "visible_count": 1, "omitted_count": 4}),
            _candidate("cand-other", "multiple_results", "other_target", {"total_count": 2, "visible_count": 2, "omitted_count": 0}),
        ]
        return render_report(_payload_with_candidates(candidates))

    def test_searching_the_raw_id_target_shows_exactly_that_row(self):
        html = self._html()
        result = _run_filter_script(html, "py:pkg.mod#Sym")
        if "missingObservable" in result:
            self.fail(f"VO-21 filter-script coverage item cannot be observed: {result['missingObservable']}")
        self.assertEqual(result["hiddenByIndex"].count(False), 1, result)
        self.assertIn("mod:Sym", result["visibleTextContents"][0])

    def test_searching_the_short_label_shows_the_same_row(self):
        html = self._html()
        result = _run_filter_script(html, "mod:Sym")
        self.assertGreaterEqual(result["hiddenByIndex"].count(False), 1, result)
        self.assertTrue(any("mod:Sym" in text for text in result["visibleTextContents"]))

    def test_a_nonsense_query_shows_zero_rows(self):
        html = self._html()
        result = _run_filter_script(html, "zzz_no_such_candidate_zzz")
        self.assertEqual(result["hiddenByIndex"].count(False), 0, result)
        self.assertEqual(result["visibleTextContents"], [])


class TestVO10BottlenecksDeterminism(unittest.TestCase):
    """VO-10 (bottlenecks slice, QR-5): identical input -> byte-identical HTML."""

    def test_same_payload_renders_byte_identical_html_twice(self):
        payload = _payload_with_candidates(FIXTURE_CANDIDATES)
        first = render_report(payload)
        second = render_report(payload)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
