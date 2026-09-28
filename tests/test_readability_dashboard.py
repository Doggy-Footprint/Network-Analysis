"""VO-3, VO-4, VO-5, VO-15, and the dashboard slice of VO-10 for the
architecture dashboard (renderers/html).

VO-3 (FR-3, C-6, C-7, C-16): decision table over
{파일노드/display_label 있음, 파일노드/없음, 심볼노드, 특수문자 label}, checked on the
`#architecture-data` payload produced by `HTMLRenderer.render`.

VO-4 (FR-4, C-8, C-9): boundary value (2-value) over {7개, 5개, 0개 지표, 동점},
checked on `buildOverview` in a Node vm (independent hand-computed order).

VO-5 (FR-5): equivalence partitioning over {탭명 "개요", 용어 11개, confidence
한국어 설명 4종}, checked as literal-string presence in the rendered
dashboard/app.js text.

VO-10 (QR-5, dashboard slice): metamorphic — regenerating from the same input
twice yields byte-identical HTML.

VO-15 (FR-16): equivalence partitioning over {영어 문구 목록 부재, effective_token_cost
정의에 0.1 포함}, checked on user-visible text only (dashboard.html text nodes
and placeholder=/title= attributes; app.js quoted string literals), not code
identifiers or comments (TD-7); hand-computed from FR-16's exact phrase list
and coefficient.

VO-18 (FR-20, spec v5): equivalence partitioning over {심볼 노드 `f.py:sym`, 파일
노드 짧은 라벨, 같은 basename 충돌 파일의 심볼}, checked on `buildOverview`'s
`focus` array (which carries both `label` and `full_label`, per the v5
Signature) in a Node vm. Expected labels are hand-computed from FR-1's
short-labels algorithm applied to the `span.file_path`s in each fixture, not
by calling report/shared/labels.py.
"""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from language_analyzers.core.graph_models import GraphNode, SourceSpan
from renderers.html import HTMLRenderer

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "renderers/html/static/app.js"
DASHBOARD_TEMPLATE = ROOT / "renderers/html/templates/dashboard.html"

# FR-12: judgement words that must never appear in generated report text.
FORBIDDEN_WORDS = ("위험", "나쁨", "품질")

# FR-5: metric glossary terms that must be documented somewhere on the page.
GLOSSARY_TERMS = (
    "token_estimate", "effective_token_cost", "pagerank", "hub", "authority",
    "degree", "betweenness", "weighted_centrality_cost", "fan_in", "fan_out", "hop_2",
)

HANGUL_RE = re.compile(r"[가-힣]")


def render_architecture(architecture):
    with tempfile.TemporaryDirectory() as directory:
        report = Path(directory) / "report.html"
        HTMLRenderer(title="Readability").render(architecture, str(report))
        return report.read_bytes()


def extract_architecture_data(html_bytes):
    # TD-1: attribute quote style is not a contract; accept either ' or ".
    document = html_bytes.decode("utf-8")
    match = re.search(
        r"""<script id=['"]architecture-data['"][^>]*>(.*?)</script>""",
        document, re.DOTALL,
    )
    assert match is not None, "missing #architecture-data payload"
    return json.loads(match.group(1).replace("\\u003c", "<")), document


def architecture_with_nodes(nodes, edges=None):
    return SimpleNamespace(
        project_name="readability", project_path="/project", stats={},
        nodes=nodes, edges=edges or [], report_collections=[],
    )


def combined_dashboard_source():
    parts = [APP_JS.read_text(encoding="utf-8")]
    if DASHBOARD_TEMPLATE.exists():
        parts.append(DASHBOARD_TEMPLATE.read_text(encoding="utf-8"))
    return "\n".join(parts)


# FR-16: English UI phrases that must not remain in the graph tab's
# user-visible text (checked case-insensitively for HTML text/attributes,
# since the source may capitalize them differently).
DASHBOARD_ENGLISH_PHRASES = ("Controls & Filters", "LEGEND", "Fit View", "Physics: On", "Node Spacing", "Search routes")

# TD-7: app.js has no HTML text nodes, so identifiers (e.g. a function or id
# named `legend`) would false-positive on a plain substring search. Instead,
# only quoted string literals are checked, case-sensitively, against this
# expanded phrase list (which includes markup fragments some code embeds as
# strings, e.g. `"...Legend</span>..."`).
APP_JS_ENGLISH_PHRASES = ("LEGEND", "Legend</", ">Legend", "Controls & Filters", "Fit View", "Physics: On", "Node Spacing", "NODE SPACING", "Search routes")


def _visible_html_text(html):
    """TD-7: strip <!-- comments -->, <script>, and <style> blocks, then
    return remaining text-node content plus placeholder=/title= attribute
    values — i.e. only what a user would actually see."""
    without_comments = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    without_scripts = re.sub(r"<script\b[^>]*>.*?</script>", " ", without_comments, flags=re.DOTALL | re.IGNORECASE)
    without_styles = re.sub(r"<style\b[^>]*>.*?</style>", " ", without_scripts, flags=re.DOTALL | re.IGNORECASE)
    attribute_values = [match.group(2) for match in re.finditer(r"""(?:placeholder|title)\s*=\s*(["'])(.*?)\1""", without_styles, flags=re.DOTALL | re.IGNORECASE)]
    text_nodes = re.sub(r"<[^>]+>", " ", without_styles)
    return text_nodes + " " + " ".join(attribute_values)


def _js_string_literals(source):
    """TD-7: quoted string literal contents only (single/double/backtick),
    not bare source text — so identifiers are excluded from the check."""
    pattern = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|`((?:[^`\\]|\\.)*)`", re.DOTALL)
    return [group for match in pattern.finditer(source) for group in match.groups() if group is not None]


class TestVO3DashboardLabels(unittest.TestCase):
    """VO-3: decision table over the 4 declared node-label variants."""

    def test_file_node_without_display_label_gets_short_vis_label_and_full_path_title(self):
        node = GraphNode(
            id="py:app/src/pkg/mod.py", label="app/src/pkg/mod.py",
            group="module", category="module", kind="module", language="python",
            span=SourceSpan("app/src/pkg/mod.py", 1, 10),
        )
        payload, _ = extract_architecture_data(render_architecture(architecture_with_nodes([node])))
        rendered = payload["nodes"][0]
        self.assertEqual(rendered["label"], "mod.py")
        self.assertIn("app/src/pkg/mod.py", rendered.get("title", ""))

    def test_symbol_node_keeps_symbol_name_label_and_carries_file_path_in_title(self):
        module = GraphNode(
            id="py:app/src/pkg/mod.py", label="app/src/pkg/mod.py",
            group="module", category="module", kind="module", language="python",
            span=SourceSpan("app/src/pkg/mod.py", 1, 10),
        )
        symbol = GraphNode(
            id="py:app/src/pkg/mod.py#run", label="run",
            group="function", category="function", kind="function", language="python",
            span=SourceSpan("app/src/pkg/mod.py", 3, 8), symbol_path="mod.run",
        )
        payload, _ = extract_architecture_data(render_architecture(architecture_with_nodes([module, symbol])))
        rendered_symbol = next(item for item in payload["nodes"] if item["id"] == symbol.id)
        self.assertEqual(rendered_symbol["label"], "run")
        self.assertNotIn(":", rendered_symbol["label"])
        self.assertIn("app/src/pkg/mod.py", rendered_symbol.get("title", ""))

    def test_display_label_node_is_left_unchanged(self):
        node = GraphNode(
            id="android:MainActivity", label="MainActivity", display_label="MainActivity",
            group="activity", category="activity", kind="activity", language="kotlin",
        )
        payload, _ = extract_architecture_data(render_architecture(architecture_with_nodes([node])))
        rendered = payload["nodes"][0]
        self.assertEqual(rendered["label"], "MainActivity")
        self.assertEqual(rendered["display_label"], "MainActivity")

    def test_C16_hostile_label_and_path_are_escaped_in_the_rendered_document(self):
        hostile = "<script>alert(1)</script>"
        node = GraphNode(
            id="py:" + hostile, label=hostile,
            group="module", category="module", kind="module", language="python",
            span=SourceSpan(hostile, 1, 1),
        )
        html_bytes = render_architecture(architecture_with_nodes([node]))
        document = html_bytes.decode("utf-8")
        self.assertNotIn(hostile, document)
        payload, _ = extract_architecture_data(html_bytes)
        # The payload, once JSON-decoded, must still carry the literal string
        # (i.e. it round-trips inertly rather than being corrupted or dropped).
        self.assertIn(hostile, json.dumps(payload["nodes"][0]))


class TestVO10DashboardDeterminism(unittest.TestCase):
    """VO-10 (dashboard slice, QR-5): identical input -> byte-identical output."""

    def test_same_architecture_renders_byte_identical_html_twice(self):
        node = GraphNode(
            id="py:app/src/pkg/mod.py", label="app/src/pkg/mod.py",
            group="module", category="module", kind="module", language="python",
            span=SourceSpan("app/src/pkg/mod.py", 1, 10),
        )
        architecture = architecture_with_nodes([node])
        first = render_architecture(architecture)
        second = render_architecture(architecture)
        self.assertEqual(first, second)


def run_overview_js(nodes_json, edges_json="[]"):
    """Loads app.js in a vm (same stub pattern as test_dashboard_initial_load.py)
    and calls the global `buildOverview` function directly."""
    script = f'''
const fs = require('fs');
const vm = require('vm');
let elements = new Map();
const element = id => {{
  if (!elements.has(id)) elements.set(id, {{innerHTML: '', innerText: '', classList: {{add(){{}}, remove(){{}}, toggle(){{}}}}}});
  return elements.get(id);
}};
let ctx = {{
  document: {{ getElementById: id => id === 'architecture-data'
    ? {{textContent: JSON.stringify({{nodes: {nodes_json}, edges: {edges_json}, collections: {{}}, project_name: 'sample'}})}}
    : element(id),
    addEventListener: (name, fn) => {{}}, querySelectorAll: () => [], createElement: () => ({{click(){{}}}}) }},
  window: {{addEventListener(){{}}}}, lucide: {{createIcons(){{}}}},
  setTimeout: fn => fn(), console,
  Blob: class {{constructor(parts) {{}}}},
  URL: {{createObjectURL: () => ''}},
  vis: {{DataSet: class {{
    constructor(items = []) {{this.items = []; this.add(items)}}
    add(items) {{this.items.push(...items)}}
    clear() {{this.items = []}}
    get(id) {{return id === undefined ? this.items : this.items.find(x => String(x.id) === String(id))}}
    update(items) {{for (const item of items) Object.assign(this.get(item.id), item)}}
  }}, Network: class {{
    constructor() {{this.focused = null}}
    on(){{}} once(){{}} setSize(){{}} redraw(){{}} fit(){{}}
    focus(id) {{this.focused = id}}
    getConnectedNodes() {{return []}}
    getConnectedEdges() {{return []}}
  }}}}
}};
vm.createContext(ctx);
ctx.ctx = ctx;
vm.runInContext(fs.readFileSync({json.dumps(str(APP_JS))}, 'utf8'), ctx);
const result = vm.runInContext('buildOverview(ARCH_DATA)', ctx);
console.log(JSON.stringify(result));
'''
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def node_with_metrics(node_id, **metrics):
    return {"id": node_id, "label": node_id, "metadata": {"analysis": metrics}}


class TestVO4BuildOverview(unittest.TestCase):
    """VO-4: boundary value (2-value) over {7개, 5개, 0개 지표, 동점}."""

    def test_seven_nodes_with_ties_and_missing_field_exclusion(self):
        # A and B tie on weighted_centrality_cost (50); tie-break by id ascending.
        nodes = [
            node_with_metrics("A", weighted_centrality_cost=50, pagerank=0.10, fan_in=1, hop_2_token_cost=100),
            node_with_metrics("B", weighted_centrality_cost=50, pagerank=0.90, fan_in=7, hop_2_token_cost=700),
            node_with_metrics("C", weighted_centrality_cost=40, pagerank=0.20, fan_in=2, hop_2_token_cost=200),
            node_with_metrics("D", weighted_centrality_cost=30, pagerank=0.30, fan_in=3, hop_2_token_cost=300),
            node_with_metrics("E", weighted_centrality_cost=20, pagerank=0.40, fan_in=4, hop_2_token_cost=400),
            node_with_metrics("F", weighted_centrality_cost=10, pagerank=0.50, fan_in=5, hop_2_token_cost=500),
            # G lacks weighted_centrality_cost and pagerank entirely.
            {"id": "G", "label": "G", "metadata": {"analysis": {"fan_in": 6, "hop_2_token_cost": 600}}},
        ]
        result = run_overview_js(json.dumps(nodes))
        self.assertEqual([item["id"] for item in result["focus"]], ["A", "B", "C", "D", "E"])
        self.assertEqual([item["metric"] for item in result["focus"]], ["weighted_centrality_cost"] * 5)
        self.assertEqual([item["value"] for item in result["focus"]], [50, 50, 40, 30, 20])
        # G is excluded from pagerank ranking (missing the field) but present in fan_in.
        self.assertNotIn("G", [item["id"] for item in result["rankings"]["pagerank"]])
        self.assertIn("G", [item["id"] for item in result["rankings"]["fan_in"]])
        self.assertEqual([item["id"] for item in result["rankings"]["pagerank"]], ["B", "F", "E", "D", "C", "A"])
        self.assertEqual([item["id"] for item in result["rankings"]["fan_in"]], ["B", "G", "F", "E", "D", "C", "A"])
        self.assertEqual([item["id"] for item in result["rankings"]["hop_2_token_cost"]], ["B", "G", "F", "E", "D", "C", "A"])

    def test_exactly_five_metric_nodes_all_included_in_order(self):
        nodes = [
            node_with_metrics("P", weighted_centrality_cost=5, pagerank=0.1, fan_in=1, hop_2_token_cost=1),
            node_with_metrics("Q", weighted_centrality_cost=4, pagerank=0.1, fan_in=1, hop_2_token_cost=1),
            node_with_metrics("R", weighted_centrality_cost=3, pagerank=0.1, fan_in=1, hop_2_token_cost=1),
            node_with_metrics("S", weighted_centrality_cost=2, pagerank=0.1, fan_in=1, hop_2_token_cost=1),
            node_with_metrics("T", weighted_centrality_cost=1, pagerank=0.1, fan_in=1, hop_2_token_cost=1),
        ]
        result = run_overview_js(json.dumps(nodes))
        self.assertEqual([item["id"] for item in result["focus"]], ["P", "Q", "R", "S", "T"])

    def test_zero_nodes_with_metrics_yields_empty_focus_without_error(self):
        nodes = [{"id": "X", "label": "X", "metadata": {}}, {"id": "Y", "label": "Y", "metadata": {"analysis": {}}}]
        result = run_overview_js(json.dumps(nodes))
        self.assertEqual(result["focus"], [])
        for metric in ("pagerank", "fan_in", "hop_2_token_cost"):
            self.assertEqual(result["rankings"][metric], [])


def node_with_span_and_metrics(node_id, label, file_path=None, **metrics):
    node = {"id": node_id, "label": label, "metadata": {"analysis": metrics}}
    if file_path is not None:
        node["span"] = {"file_path": file_path}
    return node


class TestVO18BuildOverviewSymbolAndFileLabels(unittest.TestCase):
    """VO-18: equivalence partitioning over the 3 declared coverage items,
    checked on `buildOverview`'s `focus` array (FR-20)."""

    def test_symbol_node_label_is_short_file_label_colon_symbol_and_full_label_is_file_path_colon_symbol(self):
        # FR-1: "pkg/graph.py" and "pkg/other.py" share the "pkg/" prefix and
        # have distinct basenames -> short_labels gives "graph.py"/"other.py".
        nodes = [
            node_with_span_and_metrics(
                "py:pkg/graph.py#resolve", "resolve", "pkg/graph.py",
                weighted_centrality_cost=50,
            ),
            node_with_span_and_metrics(
                "py:pkg/other.py", "pkg/other.py", "pkg/other.py",
                weighted_centrality_cost=40,
            ),
        ]
        result = run_overview_js(json.dumps(nodes))
        by_id = {item["id"]: item for item in result["focus"]}
        symbol = by_id["py:pkg/graph.py#resolve"]
        self.assertEqual(symbol["label"], "graph.py:resolve")
        self.assertEqual(symbol["full_label"], "pkg/graph.py:resolve")

    def test_file_node_label_is_the_short_file_label_and_full_label_is_the_file_path(self):
        # FR-1: "app/src/pkg/mod.py" and "app/src/other/util.py" share the
        # "app/src/" prefix and have distinct basenames -> "mod.py"/"util.py".
        nodes = [
            node_with_span_and_metrics(
                "py:app/src/pkg/mod.py", "app/src/pkg/mod.py", "app/src/pkg/mod.py",
                weighted_centrality_cost=30,
            ),
            node_with_span_and_metrics(
                "py:app/src/other/util.py", "app/src/other/util.py", "app/src/other/util.py",
                weighted_centrality_cost=20,
            ),
        ]
        result = run_overview_js(json.dumps(nodes))
        by_id = {item["id"]: item for item in result["focus"]}
        module = by_id["py:app/src/pkg/mod.py"]
        self.assertEqual(module["label"], "mod.py")
        self.assertEqual(module["full_label"], "app/src/pkg/mod.py")

    def test_symbols_in_same_basename_files_keep_the_minimal_distinguishing_path_in_their_labels(self):
        # FR-1: "a/x/m.py" vs "b/x/m.py" -- no common leading directory, and
        # basenames ("m.py") and one-level-up dirs ("x/m.py") both collide, so
        # the full path is needed to distinguish them (same shape as C-4).
        nodes = [
            node_with_span_and_metrics(
                "py:a/x/m.py#f", "f", "a/x/m.py", weighted_centrality_cost=50,
            ),
            node_with_span_and_metrics(
                "py:b/x/m.py#g", "g", "b/x/m.py", weighted_centrality_cost=40,
            ),
        ]
        result = run_overview_js(json.dumps(nodes))
        by_id = {item["id"]: item for item in result["focus"]}
        self.assertEqual(by_id["py:a/x/m.py#f"]["label"], "a/x/m.py:f")
        self.assertEqual(by_id["py:a/x/m.py#f"]["full_label"], "a/x/m.py:f")
        self.assertEqual(by_id["py:b/x/m.py#g"]["label"], "b/x/m.py:g")
        self.assertEqual(by_id["py:b/x/m.py#g"]["full_label"], "b/x/m.py:g")


class TestVO5DashboardKoreanCopyAndGlossary(unittest.TestCase):
    """VO-5: equivalence partitioning over {탭명 "개요", 용어 11개, confidence 한국어 설명 4종}."""

    def _combined_source(self):
        return combined_dashboard_source()

    def test_overview_tab_is_labelled_in_korean(self):
        self.assertIn("개요", self._combined_source())

    def test_all_eleven_glossary_terms_are_present(self):
        source = self._combined_source()
        missing = [term for term in GLOSSARY_TERMS if term not in source]
        self.assertEqual(missing, [], f"missing glossary terms: {missing}")

    def test_confidence_levels_have_korean_descriptions(self):
        source = self._combined_source()
        for level in ("static_certain", "static_inferred", "framework_inferred", "dynamic_required"):
            self.assertIn(level, source)
        self.assertTrue(HANGUL_RE.search(source), "expected Korean text describing confidence levels")

    def test_page_contains_korean_text(self):
        self.assertTrue(HANGUL_RE.search(self._combined_source()))

    def test_no_indicator_of_missing_metrics_notice_and_no_forbidden_judgement_words(self):
        source = self._combined_source()
        self.assertIn("지표 없음", source)
        for word in FORBIDDEN_WORDS:
            self.assertNotIn(word, source, f"forbidden judgement word present: {word}")

    def test_rendered_dashboard_html_contains_no_forbidden_judgement_words(self):
        node = GraphNode(
            id="py:app/src/pkg/mod.py", label="app/src/pkg/mod.py",
            group="module", category="module", kind="module", language="python",
            span=SourceSpan("app/src/pkg/mod.py", 1, 10),
        )
        document = render_architecture(architecture_with_nodes([node])).decode("utf-8")
        for word in FORBIDDEN_WORDS:
            self.assertNotIn(word, document, f"forbidden judgement word present: {word}")


class TestVO15DashboardGraphTabKoreanAndGlossaryDefinition(unittest.TestCase):
    """VO-15: equivalence partitioning over {영어 문구 목록 부재, effective_token_cost
    정의에 0.1 포함}, on the rendered dashboard + app.js text (FR-16).

    TD-7: scoped to user-visible text only (not code identifiers or HTML
    comments) — dashboard.html's text nodes + placeholder=/title= attribute
    values (case-insensitive), and app.js's quoted string literals only
    (case-sensitive, per the expanded APP_JS_ENGLISH_PHRASES list)."""

    def test_dashboard_template_visible_text_has_none_of_the_stale_english_phrases(self):
        if not DASHBOARD_TEMPLATE.exists():
            self.skipTest("dashboard.html template not found")
        visible = _visible_html_text(DASHBOARD_TEMPLATE.read_text(encoding="utf-8")).lower()
        present = [phrase for phrase in DASHBOARD_ENGLISH_PHRASES if phrase.lower() in visible]
        self.assertEqual(present, [], f"stale English phrase(s) still present in visible text: {present}")

    def test_app_js_string_literals_have_none_of_the_stale_english_phrases(self):
        literals = "\n".join(_js_string_literals(APP_JS.read_text(encoding="utf-8")))
        present = [phrase for phrase in APP_JS_ENGLISH_PHRASES if phrase in literals]
        self.assertEqual(present, [], f"stale English phrase(s) still present in a string literal: {present}")

    def test_rendered_dashboard_html_visible_text_has_none_of_the_stale_english_phrases(self):
        node = GraphNode(
            id="py:app/src/pkg/mod.py", label="app/src/pkg/mod.py",
            group="module", category="module", kind="module", language="python",
            span=SourceSpan("app/src/pkg/mod.py", 1, 10),
        )
        document = render_architecture(architecture_with_nodes([node])).decode("utf-8")
        visible = _visible_html_text(document).lower()
        present = [phrase for phrase in DASHBOARD_ENGLISH_PHRASES if phrase.lower() in visible]
        self.assertEqual(present, [], f"stale English phrase(s) still present in visible text: {present}")

    def test_effective_token_cost_glossary_definition_contains_0_1(self):
        # FR-16: effective_token_cost = token_cost x (0 for vendored/vendor/
        # node_modules paths, 0.1 for generated/migration, 1 otherwise).
        source = combined_dashboard_source()
        term_index = source.find("effective_token_cost")
        self.assertNotEqual(term_index, -1, "effective_token_cost term not found")
        definition_window = source[term_index:term_index + 500]
        self.assertIn("0.1", definition_window)


def run_legend_color_js(nodes_json):
    """VO-15 (FR-16, legend color coverage item): loads app.js in the same
    node vm stub pattern as tests/test_dashboard_initial_load.py's `run_js`
    (`ctx.initNetwork()` populates `nodesDataSet` from `ARCH_DATA.nodes`;
    `ctx.element(id)` is the stub document's element registry). `buildLegend`
    is an existing global (discovered by black-box introspection of app.js's
    vm context, the same way `initNetwork`/`nodesDataSet` were discovered by
    the pre-existing test) that renders swatches into `#legend-content`.

    For each category, the swatch color is the hex/rgb color token found
    closest before that category's label text inside `legend-content`'s
    innerHTML (the swatch precedes the label in the rendered markup); the
    node color is the first hex/rgb color token found in the JSON-stringified
    vis dataset node for that category. Neither extraction assumes any
    specific CSS class name or JSON field name -- only that a category's
    rendered legend swatch color is textually adjacent to its label, and that
    a vis node's color is present somewhere in its serialized data, per the
    Signature/FR-16 contract ("legend의 category 색 견본이 실제 노드 색과 같다")
    rather than any particular markup shape."""
    script = f'''
const fs = require('fs');
const vm = require('vm');
let elements = new Map();
const element = id => {{
  if (!elements.has(id)) {{
    let html = '';
    elements.set(id, {{id, innerText: '',
      get innerHTML() {{return html}}, set innerHTML(value) {{html = value}},
      classList: {{ add(){{}}, remove(){{}}, toggle(){{}} }},
    }});
  }}
  return elements.get(id);
}};
let ctx = {{
  document: {{ getElementById: id => id === 'architecture-data'
    ? {{textContent: JSON.stringify({{nodes: {nodes_json}, edges: [], collections: {{}}, project_name: 'sample'}})}}
    : element(id),
    addEventListener: (name, fn) => {{}}, querySelectorAll: () => [], createElement: () => ({{click(){{}}}}) }},
  window: {{addEventListener(){{}}}}, lucide: {{createIcons(){{}}}},
  setTimeout: fn => fn(), console,
  Blob: class {{constructor(parts) {{}}}},
  URL: {{createObjectURL: () => ''}},
  vis: {{DataSet: class {{
    constructor(items = []) {{this.items = []; this.add(items)}}
    add(items) {{this.items.push(...items)}}
    clear() {{this.items = []}}
    get(id) {{return id === undefined ? this.items : this.items.find(x => String(x.id) === String(id))}}
    update(items) {{for (const item of items) Object.assign(this.get(item.id), item)}}
  }}, Network: class {{
    constructor() {{this.focused = null}}
    on(){{}} once(){{}} setSize(){{}} redraw(){{}} fit(){{}}
    focus(id) {{this.focused = id}}
    getConnectedNodes() {{return []}}
    getConnectedEdges() {{return []}}
  }}}}
}};
vm.createContext(ctx);
ctx.ctx = ctx;
vm.runInContext(fs.readFileSync({json.dumps(str(APP_JS))}, 'utf8'), ctx);
const inputNodes = {nodes_json};
if (vm.runInContext('typeof initNetwork', ctx) !== 'function') {{
  console.log(JSON.stringify({{missingObservable: 'initNetwork is not a function in app.js'}}));
}} else if (vm.runInContext('typeof buildLegend', ctx) !== 'function') {{
  console.log(JSON.stringify({{missingObservable: 'buildLegend is not a function in app.js'}}));
}} else {{
  vm.runInContext('initNetwork()', ctx);
  vm.runInContext('buildLegend()', ctx);
  const legendHtml = element('legend-content').innerHTML;
  const colorPattern = /#[0-9a-fA-F]{{3,8}}|rgba?\\([^)]*\\)/g;
  function extractColorNear(html, label) {{
    const idx = html.toLowerCase().indexOf(String(label).toLowerCase());
    if (idx === -1) return null;
    const w = html.slice(Math.max(0, idx - 300), idx);
    const matches = w.match(colorPattern);
    return matches ? matches[matches.length - 1] : null;
  }}
  function extractColorFromNode(node) {{
    if (!node) return null;
    const matches = JSON.stringify(node).match(colorPattern);
    return matches ? matches[0] : null;
  }}
  const result = {{legendHtml, byCategory: {{}}}};
  for (const inputNode of inputNodes) {{
    const category = inputNode.category;
    if (result.byCategory[category]) continue;
    ctx.__lookupId = inputNode.id;
    const node = vm.runInContext('nodesDataSet.get(__lookupId)', ctx);
    result.byCategory[category] = {{legend: extractColorNear(legendHtml, category), node: extractColorFromNode(node)}};
  }}
  console.log(JSON.stringify(result));
}}
'''
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class TestVO15LegendColorMatchesNodeColor(unittest.TestCase):
    """VO-15 (FR-16, new coverage item): the legend's per-category color
    swatch must equal the vis color actually assigned to a node of that
    category. Checked in the node vm harness with >=3 distinct categories
    and no explicit `color` field on any input node, so the color is
    whatever the deterministic palette (FR-5/FR-16) assigns."""

    def test_each_categorys_legend_swatch_color_equals_a_same_category_nodes_vis_color(self):
        nodes = [
            {"id": "n-file", "label": "n-file", "category": "file"},
            {"id": "n-module", "label": "n-module", "category": "module"},
            {"id": "n-activity", "label": "n-activity", "category": "activity"},
        ]
        result = run_legend_color_js(json.dumps(nodes))
        if "missingObservable" in result:
            self.fail(
                "VO-15 legend-color coverage item cannot be observed without "
                f"an additional global: {result['missingObservable']}"
            )
        self.assertTrue(result["legendHtml"].strip(), "expected #legend-content to be populated after buildLegend()")
        for node in nodes:
            category = node["category"]
            entry = result["byCategory"][category]
            self.assertIsNotNone(entry["node"], f"no color token found on the vis node for category={category}")
            self.assertIsNotNone(
                entry["legend"],
                f"no color token found near the '{category}' label inside #legend-content innerHTML "
                f"({result['legendHtml']!r})",
            )
            self.assertEqual(
                entry["legend"].lower(), entry["node"].lower(),
                f"legend swatch color for category={category} does not match that category's node vis color",
            )


class TestVO22DashboardNoForbiddenJudgementWords(unittest.TestCase):
    """VO-22 (FR-12): equivalence partitioning over the dashboard's declared
    coverage item -- both the static template+app.js source and a rendered
    HTML document must contain none of the 3 forbidden judgement words.
    (VO-5's tests already check this incidentally; these are the dedicated
    VO-22 obligation tests, kept independent so VO-5 could be narrowed
    without silently dropping FR-12 coverage.)"""

    def test_dashboard_template_and_app_js_source_have_no_forbidden_judgement_words(self):
        source = combined_dashboard_source()
        for word in FORBIDDEN_WORDS:
            self.assertNotIn(word, source, f"forbidden judgement word present in source: {word}")

    def test_rendered_dashboard_html_has_no_forbidden_judgement_words(self):
        node = GraphNode(
            id="py:app/src/pkg/mod.py", label="app/src/pkg/mod.py",
            group="module", category="module", kind="module", language="python",
            span=SourceSpan("app/src/pkg/mod.py", 1, 10),
        )
        document = render_architecture(architecture_with_nodes([node])).decode("utf-8")
        for word in FORBIDDEN_WORDS:
            self.assertNotIn(word, document, f"forbidden judgement word present in rendered HTML: {word}")


if __name__ == "__main__":
    unittest.main()
