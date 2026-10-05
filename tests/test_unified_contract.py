import copy
import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from report.bottlenecks import render_report
from report.bottlenecks.generate import generate
from report.shared.document import ReportInputError
from tests.unified_support import architecture,node,edge,document,bottleneck_fixture,HOSTILE,rows,select,open_disclosures


def test_V1_V3_candidate_filters_ranges_aggregation(open_report,tmp_path):
    nodes=[node('a'),node('b'),node('c')]
    payload=bottleneck_fixture(tmp_path,nodes)
    extra=copy.deepcopy(payload['candidates'][0]);extra['id']='b:000000000000000a';extra['evidence']['path']='second-raw-large.py'
    payload['candidates'].append(extra)
    page=open_report(architecture(nodes),payload)
    assert set(page.locator('#candidate-kind-filter option').evaluate_all('(els)=>els.map(e=>e.value)'))=={'all','large_node','evidence_spread','unresolved_boundary'}
    for kind,target in [('large_node','a'),('evidence_spread','b'),('unresolved_boundary','c')]:
        page.locator('#candidate-kind-filter').select_option(kind);assert rows(page)==[target]
        select(page,target)
        open_disclosures(page.locator('#node-detail'))
        expect(page.locator('#node-detail')).to_contain_text(f'candidate-{ord(target)-97}.py')
        detail=page.locator('#node-detail').inner_text()
        assert f'candidate-{ord(target)-97}.py' in detail
        assert '13' in detail and '29' in detail
        if kind=='large_node': assert 'second-raw-large.py' in detail and '2001' in detail
        if kind=='evidence_spread': assert 'candidate-1-other.py' in detail and '31' in detail and '39' in detail
    page.locator('#candidate-kind-filter').select_option('all');assert rows(page)==['a','b','c']


def test_V4_json_only_and_architecture_only_capabilities(open_report,tmp_path):
    nodes=[node('a')];payload=bottleneck_fixture(tmp_path,nodes,candidate_count=1)
    html=render_report(payload)
    page=open_report(None,html=html)
    assert page.evaluate('JSON.parse(document.querySelector("#report-data").textContent).architecture') is None
    select(page,'a')
    assert page.evaluate('window.ReportGraph') is None
    assert re.search('없|불가|제공',page.locator('#graph-status').inner_text())
    assert 'candidate-0.py' in page.locator('#node-detail').inner_text()
    assert re.search('분류|범위',page.locator('#report-summary').inner_text())
    page=open_report(architecture(nodes));select(page,'a')
    assert re.search('후보.*(없|제공)|데이터.*없',page.locator('#node-detail').inner_text())
    assert page.evaluate('JSON.parse(document.querySelector("#report-data").textContent).bottlenecks') is None


@pytest.mark.parametrize('case',['bad-schema','unsupported-kind','duplicate-id','nonfinite','malformed-json'],ids=str)
def test_V4_V6_generator_rejects_invalid_fields_no_output(tmp_path,case):
    payload=bottleneck_fixture(tmp_path,[node('a'),node('b'),node('c')])
    if case=='bad-schema': payload['schema']='bottlenecks.v2'
    elif case=='unsupported-kind': payload['candidates'][0]['kind']='unknown'
    elif case=='duplicate-id': payload['candidates'][1]['id']=payload['candidates'][0]['id']
    elif case=='nonfinite': payload['dependency_network']['node_metrics']['a']['pagerank']=float('inf')
    content='{broken' if case=='malformed-json' else json.dumps(payload)
    writes=[]
    with pytest.raises(ReportInputError) as raised:
        generate(tmp_path/'input.json',tmp_path/'out.html',read_text=lambda path:content,write_text=lambda path,text:writes.append((path,text)))
    assert writes==[] and not (tmp_path/'out.html').exists()
    if case!='malformed-json': assert '$' in str(raised.value)


def test_V4_generate_and_shared_shell_preserves_wire_data(tmp_path):
    arch=architecture([node('a')]);payload=bottleneck_fixture(tmp_path,arch['nodes'],candidate_count=1)
    writes=[]
    returned=generate(tmp_path/'b.json',tmp_path/'b.html',read_text=lambda path:json.dumps(payload),write_text=lambda path,text:writes.append((path,text)))
    assert returned==tmp_path/'b.html' and len(writes)==1
    for html in [document(arch,payload),render_report(payload),writes[0][1]]:
        assert 'id="report-summary"' in html and 'id="node-detail"' in html
        assert '<style' in html and 'MIT' in html
        assert not re.search(r'<(?:script|link)[^>]+(?:src|href)=["\'](?:https?:|[^"\']+_assets/)',html)
        match=re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>',html,re.S)
        neutral=json.loads(match.group(1));assert neutral['bottlenecks']==payload
    assert json.loads(re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>',document(arch,payload),re.S).group(1))['architecture']==arch


def test_V6_payload_browser_error_visible(open_report):
    html=document(architecture([node('a')]))
    html=re.sub(r'(<script[^>]*id="report-data"[^>]*>).*?(</script>)',r'\1{broken\2',html,flags=re.S)
    page=open_report(None,html=html)
    status=page.locator('#report-status')
    expect(status).to_be_visible()
    message=status.inner_text()
    assert message.strip()
    assert re.search('오류|실패|읽을 수 없|읽지 못|invalid|error',message,re.I) or 'error' in (status.get_attribute('class') or '').split()
    assert page.locator('[data-node-id]').count() == 0
    assert page.locator('[data-node-row]').count() == 0
    assert page.evaluate('window.ReportGraph == null')
    assert page.locator('#node-detail').get_attribute('data-selected-node') in (None,'')


def test_V6_hostile_candidate_evidence_is_inert(open_report,tmp_path):
    n=node('a');payload=bottleneck_fixture(tmp_path,[n],candidate_count=1)
    payload['candidates'][0]['evidence']['path']=HOSTILE
    page=open_report(architecture([n]),payload);select(page,'a')
    expect(page.locator('#node-detail')).to_contain_text(HOSTILE)
    assert page.evaluate('window.attack') is None and page.external_requests==[]
