import copy
import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from report.bottlenecks import render_report
from report.bottlenecks.generate import generate
from report.shared.document import ReportInputError
from tests.unified_support import CDN_URL,architecture,node,edge,document,bottleneck_fixture,rows


def test_V1_V3_candidate_kind_filters_and_modal_candidate_summary(open_report,tmp_path):
    nodes=[node('a'),node('b'),node('c')]
    payload=bottleneck_fixture(tmp_path,nodes)
    page=open_report(architecture(nodes),payload)
    assert set(page.locator('#candidate-kind-filter option').evaluate_all('(els)=>els.map(e=>e.value)'))=={'all','large_node','evidence_spread','unresolved_boundary'}
    expected_numbers={'large_node':(2001,),'evidence_spread':(2,),'unresolved_boundary':(2,)}
    for kind,target in [('large_node','a'),('evidence_spread','b'),('unresolved_boundary','c')]:
        page.locator('#candidate-kind-filter').select_option(kind);assert rows(page)==[target]
        label=page.locator(f'#candidate-kind-filter option[value="{kind}"]').text_content().strip()
        page.locator(f'#node-list [data-node-row="{target}"] [data-node-id]').first.click()
        dialog=page.get_by_role('dialog')
        expect(dialog).to_be_visible()
        line=next(l for l in dialog.inner_text().splitlines() if label in l)
        for number in expected_numbers[kind]:
            assert re.search(rf'(?<![\d.]){number}(?![\d.])',line.replace(',','')),(kind,line)
        page.keyboard.press('Escape')
    page.locator('#candidate-kind-filter').select_option('all');assert rows(page)==['a','b','c']


def test_V4_json_only_and_architecture_only_payloads(open_report,tmp_path):
    nodes=[node('a')];payload=bottleneck_fixture(tmp_path,nodes,candidate_count=1)
    page=open_report(None,html=render_report(payload))
    assert page.evaluate('JSON.parse(document.querySelector("#report-data").textContent).architecture') is None
    assert rows(page)==['a']
    page=open_report(architecture(nodes))
    assert page.evaluate('JSON.parse(document.querySelector("#report-data").textContent).bottlenecks') is None
    assert rows(page)==['a']


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
        assert 'id="report-summary"' in html
        assert '<style' in html
        assert set(re.findall(r'<(?:script|link)[^>]+(?:src|href)=["\'](https?:[^"\']+)',html))<={CDN_URL}
        assert not re.search(r'<(?:script|link)[^>]+(?:src|href)=["\'][^"\']+_assets/',html)
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
