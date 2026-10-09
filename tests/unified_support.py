import copy
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

CORE = ('pagerank', 'betweenness_centrality', 'hop_2_token_cost', 'weighted_centrality_cost', 'fan_in', 'fan_out')
METRICS = CORE + ('hub_score', 'authority_score', 'degree_centrality', 'hop_3_token_cost', 'weighted_fan_in', 'weighted_fan_out')
CATEGORIES = ('production', 'test', 'generated', 'vendored', 'unknown')
PATHS = {'production': 'src/app.py', 'test': 'tests/test_app.py', 'generated': 'generated/app.py', 'vendored': 'vendor/app.py', 'unknown': None}
HOSTILE = '</script><img src="https://invalid.example/x" onerror="window.attack=1"><script>window.attack=1</script>'
REGRESSION_EDGE_WEIGHTS = {'confidence': {'static_certain': 1, 'static_inferred': .3, 'framework_inferred': .3, 'dynamic_required': .3}, 'resolution': {'exact': 1, 'unique_name': 1, 'ambiguous': .3, 'unresolved': .3}}


def node(node_id, category='production', value=1):
    path = PATHS[category]
    return {'id': node_id, 'label': 'same', 'display_label': '', 'group': 'function', 'category': 'function', 'kind': 'function', 'language': 'python', 'span': None if path is None else {'file_path': path, 'start_line': 2, 'end_line': 9, 'start_col': 0, 'end_col': 0}, 'cost': {'token_estimate': 42, 'char_count': 168, 'line_count': 8}, 'signature': 'def same(value: int) -> int', 'docstring': 'DOC_ORACLE', 'symbol_path': 'oracle.same', 'flags': ['FLAG_ORACLE'], 'provenance': 'python-core', 'exported': True, 'metadata': {'custom': 'META_ORACLE', 'analysis': {**{key: value for key in METRICS}, 'token_cost': 42, 'effective_token_cost': 21, 'identifier_file_count': 7, 'identifier_file_count_by_context': {'code': 3, 'comment': 2, 'doc': 4}}}}


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
        browser = playwright.chromium.launch(channel="chrome")
        yield browser
        browser.close()


@pytest.fixture
def open_report(chromium, tmp_path):
    contexts = []
    def open_page(arch, bottlenecks=None, width=1440, initial_script=None, html=None, **kwargs):
        path = tmp_path / f'report-{len(contexts)}.html'
        path.write_text(document(arch, bottlenecks, **kwargs) if html is None else html, encoding='utf-8')
        context = chromium.new_context(viewport={'width': width, 'height': 900})
        context.set_default_timeout(5000)
        contexts.append(context)
        requests, errors = [], []
        context.route('http://**/*', lambda route: route.abort())
        context.route('https://**/*', lambda route: route.abort())
        context.on('request', lambda request: requests.append(request.url) if request.url.startswith(('http:', 'https:')) else None)
        if initial_script:
            context.add_init_script(initial_script)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(path.as_uri())
        page.locator('#report-summary').wait_for()
        page.external_requests = requests
        page.unhandled_errors = errors
        return page
    yield open_page
    for context in contexts:
        context.close()


def rows(page):
    return page.locator('#node-list [data-node-row]').evaluate_all('(rows) => rows.map(row => row.dataset.nodeRow)')


def select(page, node_id):
    page.locator(f'[data-node-id="{node_id}"]').first.click()
    assert page.locator('#node-detail').get_attribute('data-selected-node') == node_id


def topology(page):
    return page.evaluate('''() => ({nodes: ReportGraph.nodes().map(n => ({id:n.id(), pos:n.position()})), edges:ReportGraph.edges().map(e => ({source:e.source().id(), target:e.target().id()}))})''')


def bottleneck_fixture(directory,nodes,edges=(),candidate_count=3):
    from tests.test_report_bottlenecks_v3 import v3_payload
    payload=v3_payload(directory)
    metrics={n['id']:copy.deepcopy(n['metadata']['analysis']) for n in nodes}
    for row in metrics.values():
        row.setdefault('hop_2_node_count',2); row.setdefault('hop_3_node_count',3)
        row['identifier_file_count_by_context'].update(docstring=1,config=1)
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


def open_disclosures(scope):
    for _ in range(200):
        closed = scope.locator('details:not([open]) > summary')
        if closed.count() == 0:
            return
        summary = closed.first
        summary.click()
        scope.evaluate('() => new Promise(resolve => requestAnimationFrame(resolve))')
    raise AssertionError('Disclosure expansion did not finish within 200 user actions')


def visible_record(scope,label):
    summary=scope.get_by_text(label,exact=True)
    summary.wait_for(state='visible',timeout=5000)
    disclosure=summary.locator('..')
    if not disclosure.evaluate('(element)=>element.open'):
        summary.click()
    pre=disclosure.locator('pre').first
    expect(pre).to_be_visible()
    import json
    return json.loads(pre.inner_text())


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


def visible_records(scope,label):
    summaries=scope.get_by_text(label,exact=True)
    summaries.first.wait_for(state='visible',timeout=5000)
    import json
    records=[]
    for summary in summaries.all():
        disclosure=summary.locator('..')
        if not disclosure.evaluate('(element)=>element.open'):
            summary.click()
        pre=disclosure.locator('pre').first
        expect(pre).to_be_visible()
        records.append(json.loads(pre.inner_text()))
    return records
