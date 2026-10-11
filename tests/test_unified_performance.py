import json
import re
from pathlib import Path
import statistics
import time

from tests.unified_support import CDN_URL, VIS_FILE, architecture, node, edge, document


def test_V7_five_cold_chrome_runs_and_interactions(chromium,tmp_path):
    nodes=[node(f'n{i:05}', 'test' if i % 100 == 99 else 'production', value=10000-i) for i in range(10000)]
    edges=[edge(f'n{i:05}',f'n{(i+delta)%10000:05}',line=delta) for i in range(10000) for delta in (1,2,3)]
    from tests.unified_support import bottleneck_fixture
    payload=bottleneck_fixture(tmp_path,nodes,edges,candidate_count=1000)
    path=tmp_path/'performance.html'
    path.write_text(document(architecture(nodes,edges),payload),encoding='utf-8')
    readings={'summary_ms':[],'filter_page_ms':[],'modal_ms':[]}
    for iteration in range(5):
        context=chromium.new_context(viewport={'width':1440,'height':900})
        context.set_default_timeout(5000)
        requests=[]
        context.on('request',lambda r:requests.append(r.url) if r.url.startswith(('http:','https:')) else None)
        context.route('http://**/*',lambda route:route.abort())
        context.route('https://**/*',lambda route:route.abort())
        context.route(CDN_URL,lambda route:route.fulfill(status=200,content_type='application/javascript',body=VIS_FILE.read_bytes()))
        page=context.new_page()
        start=time.perf_counter(); page.goto(path.as_uri()); page.locator('#node-list [data-node-row]').first.wait_for(state='attached')
        page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
        readings['summary_ms'].append((time.perf_counter()-start)*1000)
        elapsed=page.evaluate('''async (iteration) => {
            const t=performance.now();
            if(iteration%2===0){document.querySelector('#category-filter select').value='all'; document.querySelector('#category-filter select').dispatchEvent(new Event('change',{bubbles:true}));}
            else document.querySelector('#page-next').click();
            await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
            return performance.now()-t;
        }''',iteration)
        readings['filter_page_ms'].append(elapsed)
        observed_rows = page.locator('#node-list [data-node-row]').evaluate_all('(rows) => rows.map(row => row.dataset.nodeRow)')
        expected_category = 'all' if iteration % 2 == 0 else 'production'
        assert page.locator('#category-filter select').input_value() == expected_category
        expected_ids = [f'n{i:05}' for i in range(10000) if expected_category == 'all' or i % 100 != 99]
        expected_rows = expected_ids[:50] if iteration % 2 == 0 else expected_ids[50:100]
        assert observed_rows == expected_rows
        assert str(len(expected_ids)) in re.sub(r'\D', '', page.locator('#list-count').inner_text())
        elapsed=page.evaluate('''async () => {
            const t=performance.now(); document.querySelector('#node-list [data-node-id]').click();
            while (!document.querySelector('[role=dialog]') || document.querySelector('[role=dialog]').getBoundingClientRect().height===0) {
                if (performance.now()-t>5000) throw new Error('Modal never opened');
                await new Promise(r => requestAnimationFrame(r));
            }
            return performance.now()-t;
        }''')
        readings['modal_ms'].append(elapsed)
        assert page.evaluate('JSON.parse(document.querySelector("#report-data").textContent).architecture.nodes.length')==10000
        assert page.evaluate('JSON.parse(document.querySelector("#report-data").textContent).architecture.edges.length')==30000
        assert page.evaluate('JSON.parse(document.querySelector("#report-data").textContent).bottlenecks.candidates.length')==1000
        assert set(requests)<={CDN_URL}
        context.close()
    result={'spec_version':3,'context':'current workstation, installed Chrome, local file, five fresh contexts; fixture preparation excluded','raw_ms':readings,'median_ms':{key:statistics.median(values) for key,values in readings.items()},'threshold_ms':{'summary_ms':5000,'filter_page_ms':300,'modal_ms':1000}}
    artifact=Path(__file__).parent/'unified_evidence'/'performance.json'
    artifact.parent.mkdir(exist_ok=True); artifact.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    for key,threshold in result['threshold_ms'].items():
        assert result['median_ms'][key]<=threshold, result
