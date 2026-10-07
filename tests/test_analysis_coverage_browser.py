import copy
import json
import statistics
import time

import pytest
from playwright.sync_api import expect

from tests.coverage_reporting_support import IDS, dump, synthetic
from tests.unified_support import HOSTILE, architecture, bottleneck_fixture, node

STATUS_LABELS={'complete':'완료','partial':'부분 분석','failed':'실패','skipped':'건너뜀','not_targeted':'대상 밖','excluded':'제외'}
PRODUCER_LABELS={'python-core':'Python','typescript-core':'TypeScript·JavaScript','kotlin-core':'Kotlin','fastapi':'FastAPI','android':'Android','sqlalchemy':'SQLAlchemy','nestjs':'NestJS'}


def payloads(tmp_path,count,variant='combined'):
    cov=synthetic(count)
    arch=architecture([node('a')])
    arch['stats']['analysis_coverage']=copy.deepcopy(cov)
    bottlenecks=bottleneck_fixture(tmp_path,[node('a')])
    bottlenecks['coverage']['analysis_coverage']=copy.deepcopy(cov)
    if variant=='architecture-only':bottlenecks=None
    if variant=='bottlenecks-only':arch=None
    if variant in ('legacy','no-snapshot'):
        arch['stats'].pop('analysis_coverage')
        bottlenecks['coverage'].pop('analysis_coverage')
    return arch,bottlenecks,cov


def rows(page):
    return page.locator('[data-coverage-row]').evaluate_all('(els)=>els.map(e=>e.getAttribute("data-coverage-row"))')


def expand(page):
    page.locator('#coverage-details > summary').click()
    page.locator('#coverage-list tr').first.wait_for(state='attached')


def assert_clean(page):
    assert page.external_requests==[]
    assert page.unhandled_errors==[]
    assert page.evaluate('window.attack') is None


def assert_summary(page,cov):
    for key,value in cov['summary'].items():
        count=page.locator(f'[data-coverage-count="{key}"]')
        expect(count).to_have_text(str(value))
        status=key.removesuffix('_file_count')
        if status in STATUS_LABELS:
            expect(count.locator('..')).to_contain_text(STATUS_LABELS[status])
    expect(page.locator('#coverage-summary')).to_contain_text('목록 밖 경로와 건수는 집계되지 않았습니다')


def reason_text(reason):
    text=f"{reason['code']}: {reason['message']}"
    span=reason.get('span')
    if span:
        text+=f" ({span['file_path']}:{span['start_line']}-{span['end_line']})"
    return text


def assert_file_row(rendered,expected):
    cells=rendered.locator('td')
    assert cells.count()==4
    expect(cells.nth(0)).to_have_text(expected['file_path'])
    expect(cells.nth(1)).to_have_text(STATUS_LABELS[expected['status']])
    producer_lines=[f"{PRODUCER_LABELS[result['analyzer_id']]}: {STATUS_LABELS[result['status']]}" for result in expected['results']]
    assert sorted(cells.nth(2).inner_text().splitlines())==sorted(producer_lines)
    if expected['results']:
        reason_lines=[f"{PRODUCER_LABELS[result['analyzer_id']]}: {reason_text(reason)}" for result in expected['results'] for reason in result['reasons']]
    else:
        reason_lines=[reason_text(reason) for reason in expected['reasons']]
    assert sorted(cells.nth(3).inner_text().splitlines())==sorted(reason_lines or ['—'])


@pytest.mark.parametrize('variant',('combined','architecture-only','bottlenecks-only','legacy','no-snapshot'))
def test_V06_report_capabilities(open_report,tmp_path,variant):
    arch,bottlenecks,cov=payloads(tmp_path,6,variant)
    page=open_report(arch,bottlenecks)
    if variant in ('legacy','no-snapshot'):
        assert any(word in page.locator('#coverage-summary').inner_text().lower() for word in ('없음','unavailable','제공되지','정보가 없'))
        assert rows(page)==[]
    else:
        assert_summary(page,cov)
        assert rows(page)==[]
        expand(page)
        assert rows(page)==[r['file_path'] for r in cov['files']]
        for index,row in enumerate(cov['files']):
            assert_file_row(page.locator('[data-coverage-row]').nth(index),row)
    assert_clean(page)


@pytest.mark.parametrize('count',(0,1,50,51),ids=('empty','one','full-page','next-page'))
def test_V06_lazy_page_boundaries(open_report,tmp_path,count):
    arch,bottlenecks,cov=payloads(tmp_path,count)
    page=open_report(arch,bottlenecks)
    assert_summary(page,cov)
    assert rows(page)==[]
    expand(page)
    assert rows(page)==[r['file_path'] for r in cov['files'][:50]]
    assert page.locator('#coverage-prev').is_disabled()
    assert page.locator('#coverage-next').is_disabled()==(count<=50)
    if count==0:assert page.locator('#coverage-list').inner_text().strip()
    if count==51:
        page.locator('#coverage-next').click()
        assert rows(page)==['src/oracle-00050.py']
        assert page.locator('#coverage-next').is_disabled()
        page.locator('#coverage-prev').click()
        assert rows(page)[0]=='src/oracle-00000.py'
    assert_clean(page)


def test_V06_search_filters_reset_and_producer_membership(open_report,tmp_path):
    arch,bottlenecks,cov=payloads(tmp_path,51)
    cov['files'][0]['results']=cov['files'][0]['results'][:1]
    arch['stats']['analysis_coverage']=copy.deepcopy(cov)
    bottlenecks['coverage']['analysis_coverage']=copy.deepcopy(cov)
    page=open_report(arch,bottlenecks)
    expand(page)
    for selector,value,expected in [
        ('#coverage-search','oracle-00050',['src/oracle-00050.py']),
        ('#coverage-search','oracle-reason-00001',['src/oracle-00001.py']),
        ('#coverage-status-filter','excluded',[r['file_path'] for r in cov['files'] if r['status']=='excluded']),
        ('#coverage-analyzer-filter','typescript-core',[r['file_path'] for r in cov['files'] if any(p['analyzer_id']=='typescript-core' for p in r['results'])]),
    ]:
        page.locator('#coverage-search').fill('')
        page.locator('#coverage-status-filter').select_option('all')
        page.locator('#coverage-analyzer-filter').select_option('all')
        page.locator('#coverage-next').click()
        if selector=='#coverage-search':page.locator(selector).fill(value)
        else:page.locator(selector).select_option(value)
        assert rows(page)==expected[:50]
        assert page.locator('#coverage-prev').is_disabled()
    page.locator('#coverage-search').fill('NO_MATCH_ORACLE')
    assert rows(page)==[]
    assert page.locator('#coverage-list').inner_text().strip()
    assert_clean(page)


def test_V06_hostile_paths_codes_messages_are_literal(open_report,tmp_path):
    arch,bottlenecks,cov=payloads(tmp_path,1)
    row=cov['files'][0]
    row['file_path']=HOSTILE
    row['reasons']=[{'code':HOSTILE,'message':HOSTILE}]
    row['results'][0]['reasons']=copy.deepcopy(row['reasons'])
    arch['stats']['analysis_coverage']=copy.deepcopy(cov)
    bottlenecks['coverage']['analysis_coverage']=copy.deepcopy(cov)
    page=open_report(arch,bottlenecks)
    expand(page)
    expect(page.locator('#coverage-list')).to_contain_text(HOSTILE)
    assert_file_row(page.locator('[data-coverage-row]').first,row)
    reason_cell=page.locator('[data-coverage-row]').first.locator('td').nth(3)
    assert reason_cell.inner_text().splitlines()==[f'Python: {HOSTILE}: {HOSTILE}']
    assert all(PRODUCER_LABELS[result['analyzer_id']]+':' not in reason_cell.inner_text() for result in row['results'][1:])
    assert page.locator('#coverage-list img,#coverage-list script').count()==0
    assert_clean(page)
    dump('browser.json',{'spec_version':2,'hostile_literal':True,'external_requests':[],'pageerrors':[],'fixtures':['combined','architecture-only','bottlenecks-only','legacy','no-snapshot'],'boundaries':[0,1,50,51],'interactions':['path-search','reason-search','status-filter','producer-filter','reset','page-bounds']})


def test_V07_large_report_five_fresh_context_medians(open_report,tmp_path):
    arch,bottlenecks,cov=payloads(tmp_path,10000)
    cov=synthetic(10000,all_targeted=True)
    arch['stats']['analysis_coverage']=copy.deepcopy(cov)
    bottlenecks['coverage']['analysis_coverage']=copy.deepcopy(cov)
    raw={key:[] for key in ('summary','disclosure','search','status','producer','page')}
    for trial in range(5):
        started=time.perf_counter()
        page=open_report(arch,bottlenecks)
        expect(page.locator('[data-coverage-count="inventory_file_count"]')).to_have_text('10000')
        raw['summary'].append((time.perf_counter()-started)*1000)
        assert rows(page)==[]
        def measure(key,action,expected):
            start=time.perf_counter()
            action()
            assert rows(page)==expected
            raw[key].append((time.perf_counter()-start)*1000)
            assert len(rows(page))<=50
        measure('disclosure',lambda:expand(page),[r['file_path'] for r in cov['files'][:50]])
        measure('search',lambda:page.locator('#coverage-search').fill('oracle-reason-00001'),['src/oracle-00001.py'])
        page.locator('#coverage-search').fill('')
        measure('status',lambda:page.locator('#coverage-status-filter').select_option('partial'),[r['file_path'] for r in cov['files'] if r['status']=='partial'][:50])
        page.locator('#coverage-status-filter').select_option('all')
        measure('producer',lambda:page.locator('#coverage-analyzer-filter').select_option('typescript-core'),[r['file_path'] for r in cov['files'] if r['results']][:50])
        page.locator('#coverage-analyzer-filter').select_option('all')
        measure('page',lambda:page.locator('#coverage-next').click(),[r['file_path'] for r in cov['files'][50:100]])
        assert_clean(page)
    medians={key:statistics.median(values) for key,values in raw.items()}
    dump('performance.json',{'spec_version':2,'files':10000,'producers_per_file':7,'fresh_context_count':5,'raw_ms':raw,'median_ms':medians,'threshold_ms':{'summary':5000,**{key:300 for key in raw if key!='summary'}},'max_rows':50})
    assert medians['summary']<=5000
    assert all(value<=300 for key,value in medians.items() if key!='summary')


@pytest.mark.parametrize('mode',('file','symbol'))
def test_V06_legacy_schema_pairs(open_report,mode):
    from tests.coverage_reporting_support import EVIDENCE
    baseline=json.loads((EVIDENCE/'characterization-baseline.json').read_text())
    payload=baseline['python:'+mode]
    assert payload['architecture']['schema_version']==('6' if mode=='file' else '5')
    assert payload['bottlenecks']['schema']==('bottlenecks.v5' if mode=='file' else 'bottlenecks.v4')
    page=open_report(payload['architecture'],payload['bottlenecks'])
    assert any(word in page.locator('#coverage-summary').inner_text().lower() for word in ('없음','unavailable','제공되지','정보가 없'))
    assert rows(page)==[]
    assert_clean(page)
