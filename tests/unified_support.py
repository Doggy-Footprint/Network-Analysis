import os
import copy
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

CORE = ('pagerank', 'betweenness_centrality', 'hop_2_token_cost', 'weighted_centrality_cost', 'fan_in', 'fan_out')
METRICS = CORE + ('weighted_fan_in', 'weighted_fan_out')
CATEGORIES = ('production', 'test', 'generated', 'vendored', 'unknown')
PATHS = {'production': 'src/app.py', 'test': 'tests/test_app.py', 'generated': 'generated/app.py', 'vendored': 'vendor/app.py', 'unknown': None}
HOSTILE = '</script><img src="https://invalid.example/x" onerror="window.attack=1"><script>window.attack=1</script>'
REGRESSION_EDGE_WEIGHTS = {'confidence': {'static_certain': 1, 'static_inferred': .3, 'framework_inferred': .3, 'dynamic_required': .3}, 'resolution': {'exact': 1, 'unique_name': 1, 'ambiguous': .3, 'unresolved': .3}}


def node(node_id, category='production', value=1):
    path = PATHS[category]
    return {'id': node_id, 'label': 'same', 'display_label': '', 'group': 'function', 'category': 'function', 'kind': 'function', 'language': 'python', 'span': None if path is None else {'file_path': path, 'start_line': 2, 'end_line': 9, 'start_col': 0, 'end_col': 0}, 'cost': {'token_estimate': 42, 'char_count': 168, 'line_count': 8}, 'signature': 'def same(value: int) -> int', 'docstring': 'DOC_ORACLE', 'symbol_path': 'oracle.same', 'flags': ['FLAG_ORACLE'], 'provenance': 'python-core', 'exported': True, 'metadata': {'custom': 'META_ORACLE', 'analysis': {**{key: value for key in METRICS}, 'token_cost': 42, 'effective_token_cost': 21}}}


def edge(source, target, confidence='static_certain', resolution='exact', line=5):
    return {'from_id': source, 'to_id': target, 'relation': 'CALLS', 'confidence': confidence, 'resolution': resolution, 'weight': 999, 'evidence': {'file_path': f'evidence-{line}.py', 'start_line': line, 'end_line': line + 2}, 'candidates': []}


def architecture(nodes=(), edges=(), collection_count=0):
    return {'schema_version': '5', 'project_name': 'ORACLE PROJECT', 'project_path': '/oracle', 'nodes': list(nodes), 'edges': list(edges), 'stats': {'analysis': {'ambiguity_policy': 'equal-symbol-share.v1', 'edge_weights': copy.deepcopy(REGRESSION_EDGE_WEIGHTS), 'node_metrics': {n['id']: copy.deepcopy(n['metadata']['analysis']) for n in nodes}, 'betweenness_strategy': 'sampled', 'betweenness_sample_size': 37}}, 'collections': {'oracle': {'label': 'ORACLE COLLECTION', 'view': 'table', 'columns': [{'key': 'id', 'label': 'ID', 'format': 'text'}], 'rows': [{'id': f'collection-{i:03}'} for i in range(collection_count)]}}}


def document(arch, bottlenecks=None, **kwargs):
    from report.unified import render_unified_report
    return render_unified_report(arch, bottlenecks, **kwargs)


@pytest.fixture(scope='session')
def chromium():
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome")
        except Exception:
            bundled = sorted(Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")).glob("chromium-*/chrome-linux/chrome"))
            if not bundled:
                raise
            browser = playwright.chromium.launch(executable_path=str(bundled[-1]))
        yield browser
        browser.close()


CDN_URL = 'https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js'
VIS_FILE = Path(__file__).parent / 'fixtures' / 'vis-network-9.1.9' / 'vis-network.min.js'
GRAPH_READY = "() => window.ReportGraph != null && document.body.dataset.graphReady === 'true'"


def wants_graph(arch):
    return bool(arch) and arch.get('granularity') == 'file' and any(item.get('kind') == 'file' for item in arch.get('nodes', ()))


@pytest.fixture
def open_report(chromium, tmp_path):
    contexts = []
    def open_page(arch, bottlenecks=None, width=1440, initial_script=None, html=None, cdn='local', graph=None, **kwargs):
        """cdn: 'local' serves the pinned vis-network copy at the CDN URL (A08); 'abort' fails that request; 'http-500' answers it with an error status.
        graph: wait for the graph-ready marker; default waits when a file-granularity architecture has file nodes and cdn is local."""
        path = tmp_path / f'report-{len(contexts)}.html'
        path.write_text(document(arch, bottlenecks, **kwargs) if html is None else html, encoding='utf-8')
        context = chromium.new_context(viewport={'width': width, 'height': 900})
        context.set_default_timeout(5000)
        contexts.append(context)
        requests, errors = [], []
        context.route('http://**/*', lambda route: route.abort())
        context.route('https://**/*', lambda route: route.abort())
        if cdn == 'local':
            context.route(CDN_URL, lambda route: route.fulfill(status=200, content_type='application/javascript', body=VIS_FILE.read_bytes()))
        elif cdn == 'http-500':
            context.route(CDN_URL, lambda route: route.fulfill(status=500, content_type='text/plain', body='unavailable'))
        context.on('request', lambda request: requests.append(request.url) if request.url.startswith(('http:', 'https:')) else None)
        if initial_script:
            context.add_init_script(initial_script)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(path.as_uri())
        page.wait_for_load_state('load')
        page.external_requests = requests
        page.unhandled_errors = errors
        if graph is None:
            graph = html is None and cdn == 'local' and wants_graph(arch)
        if graph:
            page.wait_for_function(GRAPH_READY, timeout=15000)
        return page
    yield open_page
    for context in contexts:
        context.close()


def rows(page):
    return page.locator('#node-list [data-node-row]').evaluate_all('(rows) => rows.map(row => row.dataset.nodeRow)')


def bottleneck_fixture(directory,nodes,edges=(),candidate_count=3):
    from tests.test_report_bottlenecks_v3 import v3_payload
    payload=v3_payload(directory)
    metrics={n['id']:copy.deepcopy(n['metadata']['analysis']) for n in nodes}
    def ranking(members,key):
        ordered=sorted(members,key=lambda ident:(-metrics[ident].get(key,0),ident))
        return [{'node_id':ident,'value':metrics[ident].get(key,0)} for ident in ordered[:10]]
    categories={c:[] for c in CATEGORIES}
    for n in nodes:
        category=next(c for c in CATEGORIES if (None if n['span'] is None else n['span']['file_path']) == PATHS[c])
        categories[category].append(n['id'])
    payload['dependency_network'].update(node_count=len(nodes),edge_count=len(edges),node_metrics=metrics,rankings={key:ranking(metrics,key) for key in METRICS},rankings_by_category={c:{key:ranking(ids,key) for key in METRICS} for c,ids in categories.items()},betweenness_strategy='deterministic_sampled',betweenness_sample_size=37)
    payload['candidates']=[]
    for i in range(candidate_count if nodes else 0):
        kind=('large_node','evidence_spread','unresolved_boundary')[i%3]
        target=nodes[min(i,len(nodes)-1)]['id']
        payload['candidates'].append({'id':f'b:{i:016x}','kind':kind,'target':target,'metrics':{'line_count':2001,'line_threshold':2000} if kind=='large_node' else {'file_count':2,'line_span':9,'line_threshold':2000} if kind=='evidence_spread' else {'unresolved_count':2},'evidence':[{'path':f'candidate-{i}.py','start_line':13,'end_line':29},{'path':f'candidate-{i}-other.py','start_line':31,'end_line':39}] if kind=='evidence_spread' else {'path':f'candidate-{i}.py','start_line':13,'end_line':29},'coverage':'ORACLE_COVERAGE','status':'static_candidate'})
    return payload




def tab_to(page,selector,limit=400):
    target=page.locator(selector).first
    for _ in range(limit):
        if target.evaluate('(element)=>element===document.activeElement'):
            return target
        page.keyboard.press('Tab')
    raise AssertionError(f'Control unreachable using Tab: {selector}')


def keyboard_choose(page,selector,value):
    control=tab_to(page,selector)
    options=control.locator('option').evaluate_all('(options)=>options.map(option=>({value:option.value,label:option.textContent.trim()}))')
    desired=next(option for option in options if option['value']==value)
    prefix=desired['label']
    for length in range(1,len(prefix)+1):
        candidate=prefix[:length]
        if sum(option['label'].startswith(candidate) for option in options)==1:
            prefix=candidate
            break
    page.wait_for_timeout(1100)
    session=page.context.new_cdp_session(page)
    try:
        for character in prefix:
            session.send('Input.dispatchKeyEvent',{'type':'keyDown','key':character,'text':character})
            session.send('Input.dispatchKeyEvent',{'type':'keyUp','key':character})
    finally:
        session.detach()
    expect(control).to_have_value(value)

