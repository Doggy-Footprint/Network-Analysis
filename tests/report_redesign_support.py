"""Shared fixtures and observation helpers for the report graph/modal redesign evidence (spec 0c3bcfad9643613b v1).

Every selector that is not named by the spec is declared once in SEL so an interface mismatch is a one-place fix.
"""
import copy
import json
import re
from pathlib import Path

from tests.file_analysis_browser_support import file_arch, file_bottlenecks, file_node, symbol
from tests.unified_support import CDN_URL, GRAPH_READY, document, edge

EVIDENCE_DIR = Path(__file__).parent / 'report_redesign_evidence'

# Assumed (retained from the pre-redesign list UI, see report assumptions); spec-named controls use roles/labels instead.
SEL = {
    'rows': '#node-list [data-node-row]',
    'category': '#category-filter',
    'search': '#node-search',
    'sort': '#metric-sort',
    'candidate_kind': '#candidate-kind-filter',
    'limit': '#list-limit',
    'next': '#page-next',
    'prev': '#page-prev',
    'count': '#list-count',
    'card_group': '[data-metric-group]',
}

CORE_KEYS = ('pagerank', 'betweenness_centrality', 'hop_2_token_cost', 'weighted_centrality_cost', 'fan_in', 'fan_out')
CORE_LABELS = ('참조가 모이는 곳', '경로를 잇는 곳', '주변 코드가 넓은 곳', '중심에 있는 큰 코드', '들어오는 연결이 많은 곳', '나가는 연결이 많은 곳')
SIZE_OPTIONS = set(CORE_KEYS) | {'token_cost'}

# F05/A03/A05 oracle lists (independent of the implementation)
ROLE_PRIORITY = {
    'android': ['viewmodel', 'activity_fragment', 'room_database', 'room_dao', 'room_entity', 'room_migration', 'dagger_component', 'di_module', 'di_binding', 'retrofit_api', 'composable'],
    'fastapi': ['app', 'router', 'endpoint', 'dependency', 'middleware', 'schema'],
    'sqlalchemy': ['alembic_migration', 'sqlalchemy_model'],
    'nestjs': ['application', 'module', 'controller', 'endpoint', 'provider'],
}
STATE_TERMS = ('완료', '부분 분석', '실패', '건너뜀', '대상 밖', '제외')
FIXED_TERMS = ('할인', '가중', '배분 몫', '가중 기여도', 'hop', 'PageRank', 'Hub', 'Authority', 'Betweenness', 'Fan-in', 'Fan-out', 'layer')

# Effective edge weight is min(confidence weight, resolution weight) (analysis/edge_weights.py). The tiers in
# test_report_modal.py are chosen so that a product, confidence-only or resolution-only rule changes the top-10 cut.
WEIGHT_TABLE = {
    'confidence': {'static_certain': 1.0, 'static_inferred': .8, 'framework_inferred': .6, 'dynamic_required': .4},
    'resolution': {'exact': 1.0, 'unique_name': .6, 'ambiguous': .5, 'unresolved': .1},
}


def make_file(path, metrics=None, drop=(), cost=None, label=None):
    item = file_node(path)
    item['metadata']['analysis'].update(metrics or {})
    for key in drop:
        item['metadata']['analysis'].pop(key, None)
    if cost:
        item['cost'].update(cost)
    if label is not None:
        item['label'] = label
    return item


def file_id(path):
    return 'file:' + path


def sym_id(path):
    return 'sym:' + path


def candidate(index, kind, path, metrics=None):
    default = {'line_count': 2001, 'line_threshold': 2000} if kind == 'large_node' else {'file_count': 2, 'line_span': 9, 'line_threshold': 2000} if kind == 'evidence_spread' else {'unresolved_count': 2}
    return {'id': f'b:{index:016x}', 'kind': kind, 'target': file_id(path), 'metrics': metrics or default,
            'evidence': [{'path': f'candidate-{index}.py', 'start_line': 13, 'end_line': 29}] if kind == 'evidence_spread' else {'path': f'candidate-{index}.py', 'start_line': 13, 'end_line': 29},
            'coverage': 'ORACLE_COVERAGE', 'status': 'static_candidate'}


def coverage_payload(statuses):
    """Same shape as tests.coverage_reporting_support.synthetic, with caller-chosen status counts."""
    files = []
    for i, status in enumerate(statuses):
        reasons = [] if status == 'complete' else [{'code': 'oracle_code', 'message': f'oracle-reason-{i:05}'}]
        results = [] if status in ('excluded', 'not_targeted') else [{'analyzer_id': 'python-core', 'status': status, 'reasons': copy.deepcopy(reasons)}]
        files.append({'file_path': f'src/oracle-{i:05}.py', 'status': status, 'reasons': reasons, 'results': results})
    names = ('complete', 'partial', 'failed', 'skipped', 'not_targeted', 'excluded')
    counts = {s: sum(r['status'] == s for r in files) for s in names}
    summary = {f'{s}_file_count': n for s, n in counts.items()}
    summary.update(inventory_file_count=len(files), collected_file_count=len(files) - counts['excluded'], targeted_file_count=sum(counts[s] for s in names[:4]))
    return {'version': 1, 'scope': {'ignore_source': 'provided', 'unlisted_files': 'not_enumerated'}, 'summary': summary,
            'analyzers': [{'analyzer_id': 'python-core', 'summary': {**{f'{s}_file_count': counts[s] for s in names[:4]}, 'targeted_file_count': summary['targeted_file_count']}}], 'files': files}


def build_report(files, relations=(), roles=None, framework='fastapi', weights=None, candidates=(), manual_edges=(), coverage=None, details='full', generic=None):
    """Returns (architecture, bottlenecks). relations: (src_path, dst_path, relation, confidence, resolution, line).
    manual_edges: (src_path, dst_path, relation) file-level edges appended verbatim (e.g. self loops, which file_arch never emits)."""
    symbols, mappings = [], {}
    for item in files:
        path = item['span']['file_path']
        symbols.append(symbol(sym_id(path), path))
        for kind in (roles or {}).get(path, ()):
            role = symbol(f'role:{path}:{kind}', path, kind)
            role.update(provenance=framework, group=kind, category=kind)
            role['metadata'] = {'framework': framework}
            symbols.append(role)
    for path, kinds in (generic or {}).items():
        for kind in kinds:
            core = symbol(f'core:{path}:{kind}', path, kind)
            core['provenance'] = 'python-core'
            symbols.append(core)
    raw = []
    for src, dst, relation, confidence, resolution, line in relations:
        item = edge(sym_id(src), sym_id(dst), confidence=confidence, resolution=resolution, line=line)
        item['relation'] = relation
        raw.append(item)
    arch = file_arch(files, symbols, raw)
    for src, dst, relation in manual_edges:
        item = edge(file_id(src), file_id(dst))
        item.update(relation=relation, candidates=[], weight=1, metadata={'candidate_share': 1, 'detail_edge_indices': [], 'evidence_count': 1})
        arch['edges'].append(item)
    if details == 'absent':
        arch.pop('details')
    elif details == 'empty-mapping':
        arch['details']['node_files'] = {}
        arch['details']['file_nodes'] = {f['id']: [] for f in files}
    bn = file_bottlenecks(arch, 0)
    bn['candidates'] = list(candidates)
    if weights:
        arch['stats']['analysis']['edge_weights'] = copy.deepcopy(weights)
        bn['edge_weights'].update(copy.deepcopy(weights))
    if coverage:
        arch['stats']['analysis_coverage'] = copy.deepcopy(coverage)
        bn['coverage']['analysis_coverage'] = copy.deepcopy(coverage)
    return arch, bn


def render(arch, bn=None, **kwargs):
    return document(arch, bn, **kwargs)


# ---------------------------------------------------------------- page observation helpers

def tab(page, name):
    return page.get_by_role('tab', name=name, exact=True).or_(page.get_by_role('button', name=name, exact=True)).first


def tab_active(page, name):
    element = tab(page, name)
    return element.get_attribute('aria-selected') == 'true' or element.get_attribute('aria-pressed') == 'true'


def goto_list(page):
    tab(page, '목록').click()
    page.locator(SEL['rows']).first.wait_for(state='attached')


def goto_graph(page):
    tab(page, '그래프').click()
    page.wait_for_function(GRAPH_READY, timeout=15000)


def set_category(page, value):
    goto_list(page)
    page.locator(SEL['category']).select_option(value)
    goto_graph(page)


GRAPH_DATA_JS = """() => {
  const text = (t) => t == null ? null : (typeof t === 'string' ? t : (t.textContent || String(t)));
  const body = window.ReportGraph.body.data;
  const color = (n) => (n.color && typeof n.color === 'object') ? {fill: n.color.background ?? null, border: n.color.border ?? null} : {fill: n.color ?? (n.group != null ? 'group:' + n.group : null), border: null};
  return {
    nodes: body.nodes.get().filter(n => !n.hidden).map(n => ({id: n.id, label: n.label, title: text(n.title), size: n.size, borderWidth: n.borderWidth ?? null, ...color(n)})),
    edges: body.edges.get().filter(e => !e.hidden).map(e => ({from: e.from, to: e.to, title: text(e.title)})),
  };
}"""


def graph_data(page):
    return page.evaluate(GRAPH_DATA_JS)


def settle_view(page):
    page.evaluate("""() => new Promise(resolve => { let last = null, same = 0;
      const tick = () => { const v = ReportGraph.getViewPosition(), s = ReportGraph.getScale(); const key = [v.x.toFixed(1), v.y.toFixed(1), s.toFixed(3)].join();
        same = key === last ? same + 1 : 0; last = key; same >= 8 ? resolve() : requestAnimationFrame(tick); }; tick(); })""")


def node_point(page, node_id):
    return page.evaluate("""(id) => { const p = ReportGraph.getPositions([id])[id]; const d = ReportGraph.canvasToDOM(p);
      const r = document.querySelector('canvas').getBoundingClientRect(); return {x: r.left + d.x, y: r.top + d.y}; }""", node_id)


def prepare_canvas(page):
    page.locator('canvas').first.scroll_into_view_if_needed()
    settle_view(page)


def click_graph_node(page, node_id):
    prepare_canvas(page)
    point = node_point(page, node_id)
    page.mouse.click(point['x'], point['y'])


def dialog(page):
    return page.get_by_role('dialog')


def open_from_list(page, node_id):
    goto_list(page)
    row = page.locator(SEL['rows']).nth(row_ids(page).index(node_id))
    target = row.locator('[data-node-id]').first if row.locator('[data-node-id]').count() else row
    target.scroll_into_view_if_needed()
    return target


def close_button(page):
    return dialog(page).get_by_role('button', name='닫기').first


def dialog_text(page):
    return dialog(page).inner_text()


def _plain(text):
    return re.sub(r'(?<=\d),(?=\d{3})', '', text)


def numbers(text):
    return [int(m) for m in re.findall(r'(?<![\d.])\d+(?![\d.])', _plain(text))]


def has_number(text, value):
    return re.search(rf'(?<![\d.]){re.escape(str(value))}(?![\d.])', _plain(text)) is not None


def install_pointer_trace(page):
    page.evaluate("""() => { document.addEventListener('pointerup', () => { if (window.__before == null) window.__before = document.activeElement; }, true); }""")


def record(key, value):
    EVIDENCE_DIR.mkdir(exist_ok=True)
    path = EVIDENCE_DIR / 'browser.json'
    data = json.loads(path.read_text()) if path.exists() else {'measurements': {}}
    data['spec_version'] = 3
    data['measurements'][key] = value
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def control(page, key):
    selector = SEL[key]
    return page.locator(f'select{selector}, {selector} select').first


def text_input(page, key):
    selector = SEL[key]
    return page.locator(f'input{selector}, {selector} input').first


def row_ids(page):
    return page.locator(SEL['rows']).evaluate_all('(rows) => rows.map(row => row.dataset.nodeRow)')


def search_box(page):
    return page.locator('input[list]:visible').first


def pill_numbers(page, label):
    block = page.get_by_text(label, exact=True).first.locator('xpath=..')
    return [int(n) for n in re.findall(r'\d+', block.inner_text())]
