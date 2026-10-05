import copy
import json
import re

import pytest
from playwright.sync_api import expect

from tests.unified_support import CORE,METRICS,CATEGORIES,HOSTILE,architecture,node,edge,bottleneck_fixture,rows,select,topology,open_disclosures,visible_record,visible_records,tab_to,keyboard_choose

METRIC_DISCLOSURE='전체 지표 · 식별자 출현 컨텍스트'
SYMBOL_DISCLOSURE='심볼 · 시그니처 · 문서 · 플래그 · 메타데이터'
CANDIDATE_DISCLOSURE='후보의 전체 기록'


def test_VR1_summary_counts_units_category_representatives_precedence(open_report,tmp_path):
    assigned=[('p0','production',91),('p1','production',81),('t0','test',71),('t1','test',61),('g0','generated',51),('g1','generated',41),('v0','vendored',31),('v1','vendored',21),('u0','unknown',11)]
    nodes=[node(ident,category,value) for ident,category,value in assigned]
    payload=bottleneck_fixture(tmp_path,nodes,candidate_count=3)
    payload['snapshot']['file_count']=87
    nodes[5]['span']['file_path']='generated/foo_test.py'
    nodes[7]['span']['file_path']='vendor/tests/test_x.py'
    page=open_report(architecture(nodes),payload)
    summary=page.locator('#report-summary')
    for label,count in [('운영 코드',2),('테스트',2),('생성 코드',2),('외부 코드',2),('미분류',1),('정적 분석 미확정 참조 후보',1),('근거 분산 후보',1),('큰 노드 후보',1)]:
        block=summary.get_by_text(label,exact=True).locator('..')
        assert re.findall(r'\d+',block.inner_text()) == [str(count)]
    expect(page.get_by_text('ORACLE PROJECT',exact=True).first).to_be_visible()
    expect(summary).to_contain_text('87개 스냅샷 파일')
    expect(summary).to_contain_text('9개 노드')
    expect(summary).to_contain_text('0개 연결')
    meanings=['참조받는 상대적 중심성','최단 경로','두 단계','할인된 코드 토큰','참조하는 직접 연결 대상 수','참조하는 직접 연결 대상 수']
    units=['상대값','상대값','추정 토큰','가중 토큰','대상','대상']
    for metric,meaning,unit in zip(CORE,meanings,units):
        group=page.locator(f'[data-metric-group="{metric}"]')
        expect(group).to_contain_text(meaning)
        expect(group).to_contain_text(unit)
    for category in ('all',*CATEGORIES):
        page.locator('#category-filter').select_option(category)
        members=[(ident,value) for ident,c,value in assigned if category=='all' or c==category]
        expected=[ident for ident,value in members[:10]]
        for metric in CORE:
            group=page.locator(f'[data-metric-group="{metric}"]')
            assert group.locator('[data-node-id]').evaluate_all('(els)=>els.map(e=>e.dataset.nodeId)')==expected
            for ident,value in members[:10]:
                expect(group.locator(f'[data-node-id="{ident}"]')).to_contain_text(str(value))


def test_VR1_VR6_missing_detail_and_explicit_empty_states(open_report,tmp_path):
    missing=node('missing');missing['metadata']['analysis'].pop('pagerank')
    page=open_report(architecture([missing,node('present',value=4)]))
    assert page.locator('[data-metric-group="pagerank"] [data-node-id]').evaluate_all('(els)=>els.map(e=>e.dataset.nodeId)')==['present']
    select(page,'missing')
    metric_box=page.locator('#node-detail').get_by_text('참조가 모이는 곳',exact=True).locator('..')
    expect(metric_box).to_contain_text('—')
    page=open_report(architecture([]),bottleneck_fixture(tmp_path,[],candidate_count=0))
    assert rows(page)==[]
    expect(page.locator('#list-count')).to_contain_text('0')
    assert re.search('없|일치.*않',page.locator('#node-list').inner_text())
    page=open_report(architecture([node('a')]),bottleneck_fixture(tmp_path,[node('a')],candidate_count=0))
    select(page,'a')
    expect(page.locator('#node-detail')).to_contain_text('발견된 후보 없음')
    expect(page.locator('#relationship-list')).to_contain_text(re.compile('없|0'))
    expect(page.locator('#graph-status')).to_contain_text('0')
    page.locator('#node-search').fill('no-such-oracle')
    assert rows(page)==[]
    expect(page.locator('#list-count')).to_contain_text('0')
    assert re.search('없|일치.*않',page.locator('#node-list').inner_text())


def test_VR2_configured_resolution_minimum_and_raw_relation_identity(open_report,tmp_path):
    nodes=[node('center',value=100)]+[node(f'n{i:02}',value=10) for i in range(32)]
    edges=[edge('center',f'n{i:02}',resolution='ambiguous' if i==0 else 'exact',confidence='framework_inferred' if i==31 else 'static_certain',line=i+101) for i in range(32)]
    edges[0]['relation']='IMPORTS'
    edges += [edge('center','center',confidence='dynamic_required',resolution='unresolved',line=901)]
    payload=bottleneck_fixture(tmp_path,nodes,edges,candidate_count=0)
    payload['edge_weights']['confidence'].update(static_certain=.8,framework_inferred=.1,dynamic_required=.4)
    payload['edge_weights']['resolution'].update(exact=1,ambiguous=.2,unresolved=.3)
    page=open_report(architecture(nodes,edges),payload);select(page,'center')
    assert {n['id'] for n in topology(page)['nodes']}=={'center'}|{f'n{i:02}' for i in range(1,31)}
    relationships=page.locator('#relationship-list')
    open_disclosures(relationships)
    raw_records=[json.loads(pre.inner_text()) for pre in relationships.locator('pre').all()]
    for expected in edges:
        assert expected in raw_records
    self_record=next(record for record in raw_records if record.get('from_id')=='center' and record.get('to_id')=='center')
    assert self_record['confidence']=='dynamic_required' and self_record['resolution']=='unresolved'
    assert self_record['evidence']['start_line']==901 and self_record['evidence']['end_line']==903
    relationships.locator('[data-node-id="n01"]').first.click()
    assert page.locator('#node-detail').get_attribute('data-selected-node')=='n01'


def test_VR2_fit_and_both_zoom_buttons_have_effect(open_report):
    page=open_report(architecture([node('a',value=10),node('b')],[edge('a','b')]))
    select(page,'a')
    initial=page.evaluate('ReportGraph.zoom()')
    page.locator('#graph-zoom-out').click();assert page.evaluate('ReportGraph.zoom()')<initial
    before=page.evaluate('ReportGraph.zoom()')
    page.locator('#graph-zoom-in').click();assert page.evaluate('ReportGraph.zoom()')>before
    before=page.evaluate('ReportGraph.zoom()')
    page.locator('#graph-zoom-out').click();assert page.evaluate('ReportGraph.zoom()')<before
    page.evaluate('ReportGraph.pan({x:9999,y:9999})')
    page.locator('#graph-fit').click()
    assert page.evaluate('ReportGraph.pan()')!={'x':9999,'y':9999}
    bounds=page.evaluate('''() => ({box:ReportGraph.nodes().renderedBoundingBox(),width:ReportGraph.width(),height:ReportGraph.height()})''')
    assert bounds['box']['x1']>=0 and bounds['box']['y1']>=0
    assert bounds['box']['x2']<=bounds['width'] and bounds['box']['y2']<=bounds['height']


def test_VR3_exact_visible_metric_context_typed_mappings_and_appendix(open_report,tmp_path):
    n=node('a')
    metrics={key:101+i for i,key in enumerate(METRICS)}
    metrics.update(token_cost=307,effective_token_cost=211,hop_2_node_count=17,hop_3_node_count=23,identifier_file_count=29,identifier_file_count_by_context={'code':31,'comment':37,'docstring':41,'doc':43,'config':47})
    n['metadata']['analysis']=copy.deepcopy(metrics)
    arch=architecture([n]);payload=bottleneck_fixture(tmp_path,[n],candidate_count=0)
    payload['dependency_network']['node_metrics']['a']=copy.deepcopy(metrics)
    payload['snapshot'].update(file_count=83,ignore_source='ORACLE_IGNORE')
    payload['versions']['analysis']='ORACLE_VERSION_17'
    payload['coverage']['source_file_count']=79
    payload['limitations'].append('ORACLE_LIMITATION_OVERLAP')
    page=open_report(arch,payload);select(page,'a')
    detail=page.locator('#node-detail')
    assert visible_record(detail,METRIC_DISCLOSURE)==metrics
    labels=['참조가 모이는 곳','경로를 잇는 곳','주변 코드가 넓은 곳','중심에 있는 큰 코드','들어오는 연결이 많은 곳','나가는 연결이 많은 곳']
    for metric,label in zip(CORE,labels):
        assert detail.get_by_text(label,exact=True).locator('..').locator('strong').inner_text()==str(metrics[metric])
    typed=visible_record(detail,SYMBOL_DISCLOSURE)
    for field in ['id','kind','language','span','cost','signature','docstring','symbol_path','flags','provenance','exported','metadata']:
        assert typed[field]==n[field]
    appendix=page.locator('#report-appendix');appendix.locator(':scope > summary').click()
    appendix.locator('details > summary').first.wait_for(state='visible',timeout=5000)
    for label,key in [('스냅샷 · 제외 정책','snapshot'),('연결 가중치 · 줄 수 임계값','edge_weights'),('버전','versions'),('분석 범위','coverage'),('한계','limitations')]:
        assert visible_record(appendix,label)==payload[key]
    text=appendix.inner_text()+detail.inner_text()
    assert re.search('컨텍스트.*(겹|중복)|맥락.*(겹|중복)',text)
    assert re.search('토큰.*추정|추정.*토큰',text)
    assert re.search('(범위|구간|span).*(겹|중복)|(겹|중복).*(범위|구간|span)',text)


def test_VR3_candidate_reasons_metrics_and_single_kind_badge(open_report,tmp_path):
    nodes=[node('a'),node('b'),node('c')];payload=bottleneck_fixture(tmp_path,nodes)
    extra=copy.deepcopy(payload['candidates'][0]);extra['id']='b:000000000000001f';extra['evidence']['path']='extra-evidence.py';payload['candidates'].append(extra)
    page=open_report(architecture(nodes),payload)
    for target,kind,reason in [('a','large_node','줄|크기|임계'),('b','evidence_spread','파일|분산'),('c','unresolved_boundary','해결|확정')]:
        row=page.locator(f'[data-node-row="{target}"]')
        assert row.locator('.badge').count()==1
        select(page,target)
        detail=page.locator('#node-detail')
        records=visible_records(detail,CANDIDATE_DISCLOSURE)
        expected=[record for record in payload['candidates'] if record['target']==target]
        assert records==expected
        assert re.search(reason,detail.inner_text())
        for candidate in expected:
            for value in candidate['metrics'].values():expect(detail).to_contain_text(str(value))


def test_VR4_json_only_rankings_metrics_and_unavailable_capabilities(open_report,tmp_path):
    from report.bottlenecks import render_report
    nodes=[node('a',value=17),node('b','test',value=23)]
    payload=bottleneck_fixture(tmp_path,nodes,candidate_count=1)
    page=open_report(None,html=render_report(payload))
    summary=page.locator('#report-summary')
    expect(summary).to_contain_text('분류별 전체 목록')
    expect(summary).to_contain_text('소스 위치')
    expect(summary).to_contain_text('제공할 수 없습니다')
    expect(summary).to_contain_text('일부 대상')
    for category,target,value in [('production','a',17),('test','b',23),('all','b',23)]:
        page.locator('#category-filter').select_option(category)
        for metric in CORE:
            group=page.locator(f'[data-metric-group="{metric}"]')
            assert group.locator('[data-node-id]').first.get_attribute('data-node-id')==target
            expect(group).to_contain_text(str(value))
    select(page,'b')
    assert visible_record(page.locator('#node-detail'),METRIC_DISCLOSURE)==payload['dependency_network']['node_metrics']['b']
    assert page.evaluate('window.ReportGraph') is None
    page=open_report(architecture([node('a')]));select(page,'a')
    expect(page.locator('#node-detail')).to_contain_text('후보 데이터가 제공되지 않았습니다')
    expect(page.locator('#node-detail')).not_to_contain_text('발견된 후보 없음')


@pytest.mark.parametrize('width',[390,1440],ids=['mobile','desktop'])
def test_VR5_actual_tab_keyboard_filters_pages_relationships_graph(open_report,tmp_path,width):
    nodes=[node('center',value=100)]+[node(f'n{i:02}',value=1) for i in range(51)]+[node('test-only','test',value=200)]
    edges=[edge('center',f'n{i:02}',line=i+1) for i in range(51)]
    nodes[1]['metadata']['analysis']['token_cost']=999
    page=open_report(architecture(nodes,edges),bottleneck_fixture(tmp_path,nodes,edges),width=width)
    keyboard_choose(page,'#category-filter select','test');assert rows(page)==['test-only']
    keyboard_choose(page,'#category-filter select','production');assert rows(page)[0]=='center'
    keyboard_choose(page,'#metric-sort select','token_cost');assert rows(page)[0]=='n00'
    keyboard_choose(page,'#metric-sort select','pagerank');assert rows(page)[0]=='center'
    keyboard_choose(page,'#candidate-kind-filter select','large_node');assert rows(page)==['center']
    keyboard_choose(page,'#candidate-kind-filter select','all')
    tab_to(page,'#node-search');page.keyboard.type('n50');assert rows(page)==['n50']
    page.keyboard.press('Backspace');page.keyboard.press('Backspace');page.keyboard.press('Backspace');assert len(rows(page))==50
    tab_to(page,'#page-next');page.keyboard.press('Enter');assert rows(page)==['n49','n50']
    tab_to(page,'#page-prev');page.keyboard.press('Enter');assert rows(page)[0]=='center'
    tab_to(page,'#node-list [data-node-id="center"]');page.keyboard.press('Enter')
    assert page.locator('#node-detail').get_attribute('data-selected-node')=='center'
    tab_to(page,'#relationship-next');page.keyboard.press('Enter');assert page.locator('[data-relationship-row]').count()==1
    tab_to(page,'#relationship-prev');page.keyboard.press('Enter');assert page.locator('[data-relationship-row]').count()==50
    initial=page.evaluate('ReportGraph.zoom()');tab_to(page,'#graph-zoom-out');page.keyboard.press('Enter');assert page.evaluate('ReportGraph.zoom()')<initial
    before=page.evaluate('ReportGraph.zoom()');tab_to(page,'#graph-zoom-in');page.keyboard.press('Enter');assert page.evaluate('ReportGraph.zoom()')>before
    before=page.evaluate('ReportGraph.zoom()');tab_to(page,'#graph-zoom-out');page.keyboard.press('Enter');assert page.evaluate('ReportGraph.zoom()')<before
    page.evaluate('ReportGraph.pan({x:9999,y:9999})');tab_to(page,'#graph-fit');page.keyboard.press('Enter');assert page.evaluate('ReportGraph.pan()')!={'x':9999,'y':9999}
    assert page.external_requests==[]


def test_VR6_every_hostile_source_field_distinct_and_visible(open_report):
    hostile={field:HOSTILE.replace('window.attack=1',f'window.attack_{field}=1')+f'ORACLE_{field}' for field in ['label','doc','title','evidence','metadata']}
    n=node('a');n['label']=hostile['label'];n['docstring']=hostile['doc'];n['metadata']['custom']=hostile['metadata']
    relation=edge('a','a');relation['evidence']['file_path']=hostile['evidence']
    page=open_report(architecture([n],[relation]),title=hostile['title']);select(page,'a')
    expect(page.get_by_text(hostile['title'],exact=True).first).to_be_visible()
    typed=visible_record(page.locator('#node-detail'),SYMBOL_DISCLOSURE)
    assert typed['label']==hostile['label'] and typed['docstring']==hostile['doc'] and typed['metadata']['custom']==hostile['metadata']
    open_disclosures(page.locator('#relationship-list'))
    rendered_relations=[json.loads(pre.inner_text()) for pre in page.locator('#relationship-list pre').all()]
    assert rendered_relations[0]['evidence']['file_path']==hostile['evidence']
    for field in hostile: assert page.evaluate(f'window.attack_{field}') is None
    assert page.external_requests==[] and page.unhandled_errors==[]
