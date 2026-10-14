import copy
import json
import hashlib
from pathlib import Path
import statistics
import time

from tests.unified_support import CDN_URL, METRICS, VIS_FILE, architecture, node, edge, document, rows

EVIDENCE_DIR = Path(__file__).parent / 'file_analysis_evidence'


def file_node(path, value=1, category='production'):
    result = node('file:' + path, category, value)
    result.update(label=path, kind='file', group='file', category='file', symbol_path=None, signature=None, docstring=None)
    result['span'] = dict(file_path=path, start_line=1, end_line=20, start_col=0, end_col=0)
    result['metadata'].update(file_path=path)
    return result


def symbol(ident, path, kind='function', label=None):
    result = node(ident)
    result.update(kind=kind, group=kind, category=kind, label=label or ident, display_label=label or ident)
    result['span']['file_path'] = path
    result['metadata'].pop('analysis')
    return result


def file_arch(files, symbols=(), relations=(), owners=None, mappings=None):
    result = architecture(files)
    result.update(schema_version='6', granularity='file')
    mappings = mappings or {s['id']: 'file:' + s['span']['file_path'] if s.get('span') else None for s in symbols}
    result['details'] = {'nodes': list(symbols), 'edges': list(relations), 'node_files': mappings,
                         'node_owners': {s['id']: (owners or {}).get(s['id']) for s in symbols},
                         'file_nodes': {f['id']: [s['id'] for s in symbols if mappings.get(s['id']) == f['id']] for f in files}}
    grouped = {}
    for index, relation in enumerate(relations):
        source = mappings.get(relation['from_id']) or relation['from_id']
        if relation['relation'] in ('CONTAINS', 'IMPLEMENTED_BY'):
            continue
        candidates = set([relation['to_id'], *relation.get('candidates', [])]) if relation['resolution'] == 'ambiguous' else {relation['to_id']}
        shares = {}
        for candidate in candidates:
            target = mappings.get(candidate) or candidate
            if candidate == relation['from_id'] or target == source:
                continue
            shares[target] = shares.get(target, 0) + 1 / len(candidates)
        for target, share in shares.items():
            key = (source, target, relation['relation'], relation['confidence'], relation['resolution'])
            if key not in grouped:
                aggregate = copy.deepcopy(relation)
                aggregate.update(from_id=source, to_id=target, candidates=[], weight=1, metadata={'candidate_share': share, 'detail_edge_indices': [], 'evidence_count': 0})
                grouped[key] = aggregate
            grouped[key]['metadata']['candidate_share'] = max(grouped[key]['metadata']['candidate_share'], share)
            grouped[key]['metadata']['detail_edge_indices'].append(index)
            grouped[key]['metadata']['evidence_count'] += 1
    result['edges'] = list(grouped.values())
    return result


def file_bottlenecks(arch, candidate_count=3):
    metrics = copy.deepcopy(arch['stats']['analysis']['node_metrics'])
    categories = {key: [] for key in ('production', 'test', 'generated', 'vendored', 'unknown')}
    for item in arch['nodes']:
        path = item['span']['file_path'] if item.get('span') else ''
        category = 'test' if path.startswith('tests/') else 'generated' if path.startswith('generated/') else 'vendored' if path.startswith('vendor/') else 'production'
        categories[category].append(item['id'])
    def rankings(ids):
        return {key: [{'node_id': ident, 'value': metrics[ident].get(key, 0)} for ident in sorted(ids, key=lambda ident: (-metrics[ident].get(key, 0), ident))[:10]] for key in METRICS}
    candidates = []
    for i in range(candidate_count if arch['nodes'] else 0):
        kind = ('large_node', 'evidence_spread', 'unresolved_boundary')[i % 3]
        candidates.append({'id': f'b:{i:016x}', 'kind': kind, 'target': arch['nodes'][i % len(arch['nodes'])]['id'],
                           'metrics': {'line_count': 2001, 'line_threshold': 2000} if kind == 'large_node' else {'file_count': 2, 'line_span': 9, 'line_threshold': 2000} if kind == 'evidence_spread' else {'unresolved_count': 2},
                           'evidence': [{'path': f'candidate-{i}.py', 'start_line': 13, 'end_line': 29}] if kind == 'evidence_spread' else {'path': f'candidate-{i}.py', 'start_line': 13, 'end_line': 29},
                           'coverage': 'ORACLE_COVERAGE', 'status': 'static_candidate'})
    return {'schema': 'bottlenecks.v7', 'granularity': 'file', 'snapshot': {}, 'versions': {}, 'coverage': {},
            'edge_weights': {'confidence': {'static_certain': 1, 'static_inferred': .3, 'framework_inferred': .3, 'dynamic_required': .3}, 'resolution': {'exact': 1, 'unique_name': 1, 'ambiguous': .3, 'unresolved': .3}, 'large_node_line_threshold': 2000},
            'dependency_network': {'ambiguity_policy': 'equal-symbol-share.v1', 'node_count': len(arch['nodes']), 'edge_count': len(arch['edges']), 'node_metrics': metrics, 'rankings': rankings(metrics), 'rankings_by_category': {key: rankings(ids) for key, ids in categories.items()}, 'betweenness_strategy': 'exact', 'betweenness_sample_size': None},
            'candidates': candidates, 'limitations': []}


def record_browser(key, value, evidence_dir=EVIDENCE_DIR):
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / 'browser.json'
    payload = json.loads(path.read_text()) if path.exists() else {'spec_version': 2, 'obligations': {}, 'datasets': {}}
    payload['spec_version']=2
    payload['datasets' if key in ('synthetic', 'Tag-Manager') else 'obligations'][key] = value
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')


def measure_html(chromium, html_path, dataset, evidence_dir=EVIDENCE_DIR):
    html_path = Path(html_path).resolve()
    assert html_path.is_file(), f'Mandatory browser input missing: {html_path}'
    readings = {'summary_ms': [], 'filter_page_ms': [], 'detail_graph_ms': []}
    for iteration in range(5):
        context = chromium.new_context(viewport={'width': 1440, 'height': 900})
        context.set_default_timeout(5000)
        assert context.pages == []
        requests, errors = [], []
        context.route('http://**/*', lambda route: route.abort())
        context.route('https://**/*', lambda route: route.abort())
        context.route(CDN_URL, lambda route: route.fulfill(status=200, content_type='application/javascript', body=VIS_FILE.read_bytes()))
        context.on('request', lambda r: requests.append(r.url) if r.url.startswith(('http:', 'https:')) else None)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            start = time.perf_counter()
            page.goto(html_path.as_uri())
            page.locator('#node-list [data-node-row]').first.wait_for(state='attached')
            page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
            readings['summary_ms'].append((time.perf_counter() - start) * 1000)
            if dataset == 'synthetic':
                assert page.evaluate('window.ReportGraph == null')
            initial_ids = rows(page)
            initial_count = page.locator('#list-count').inner_text()
            assert initial_ids
            readings['filter_page_ms'].append(page.evaluate('''async () => {
                const start=performance.now(); const control=document.querySelector('select#category-filter, #category-filter select');
                control.value='all'; control.dispatchEvent(new Event('change',{bubbles:true}));
                await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                return performance.now()-start;
            }'''))
            assert page.locator('select#category-filter, #category-filter select').input_value() == 'all'
            selected = rows(page)[0]
            # key name kept for scripts/benchmark_file_analysis.py: it now times a click until the modal dialog is visible
            readings['detail_graph_ms'].append(page.evaluate('''async () => {
                const start=performance.now();
                document.querySelector('#node-list [data-node-id]').click();
                while (!document.querySelector('[role=dialog]') || document.querySelector('[role=dialog]').getBoundingClientRect().height===0) {
                    if (performance.now()-start>5000) throw Error('Modal never opened');
                    await new Promise(r=>requestAnimationFrame(r));
                }
                return performance.now()-start;
            }'''))
            page.keyboard.press('Escape')
            assert not errors and set(requests) <= {CDN_URL}
            if dataset == 'synthetic':
                assert rows(page) == [f'n{i:05}' for i in range(50)]
                assert initial_ids == [f'n{i:05}' for i in range(50)]
                assert '9900' in ''.join(c for c in initial_count if c.isdigit())
                page.locator('#page-next').click()
                assert rows(page) == [f'n{i:05}' for i in range(50, 100)]
                payload = page.evaluate('JSON.parse(document.querySelector("#report-data").textContent)')
                assert len(payload['architecture']['nodes']) == 10000
                assert len(payload['architecture']['edges']) == 30000
                assert len(payload['bottlenecks']['candidates']) == 1000
                assert '10000' in ''.join(c for c in page.locator('#list-count').inner_text() if c.isdigit())
            else:
                assert page.evaluate('JSON.parse(document.querySelector("#report-data").textContent).architecture.granularity') == 'file'
                assert selected.startswith('file:')
        finally:
            context.close()
    result = {'context': 'current workstation, installed Chrome, local file, five fresh contexts; preparation excluded',
              'html_path': str(html_path), 'html_sha256': hashlib.sha256(html_path.read_bytes()).hexdigest(), 'fresh_context_count': 5, 'graph_completion': 'click until [role=dialog] has a non-empty box', 'raw_ms': readings, 'median_ms': {key: statistics.median(values) for key, values in readings.items()},
              'threshold_ms': {'summary_ms': 5000, 'filter_page_ms': 300, 'detail_graph_ms': 1000}}
    record_browser(dataset, result, evidence_dir)
    for key, threshold in result['threshold_ms'].items():
        assert result['median_ms'][key] <= threshold, result
    return result


def measure_tag_manager_html(chromium, html_path, evidence_dir=EVIDENCE_DIR):
    return measure_html(chromium, html_path, 'Tag-Manager', evidence_dir)


def measure_all(chromium, html_path, evidence_dir=EVIDENCE_DIR):
    import tempfile
    from tests.unified_support import bottleneck_fixture
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        nodes = [node(f'n{i:05}', 'test' if i % 100 == 99 else 'production', value=10000-i) for i in range(10000)]
        edges = [edge(f'n{i:05}', f'n{(i+delta)%10000:05}', line=delta) for i in range(10000) for delta in (1,2,3)]
        payload = bottleneck_fixture(directory, nodes, edges, candidate_count=1000)
        synthetic_path = directory / 'synthetic.html'
        synthetic_path.write_text(document(architecture(nodes, edges), payload), encoding='utf-8')
        synthetic = measure_html(chromium, synthetic_path, 'synthetic', evidence_dir)
        actual = measure_tag_manager_html(chromium, html_path, evidence_dir)
        return {'synthetic': synthetic, 'Tag-Manager': actual}
