import copy
import json
import statistics
import time

import pytest
from playwright.sync_api import expect

from tests.coverage_reporting_support import IDS, dump, synthetic
from tests.report_redesign_support import coverage_payload, pill_numbers
from tests.unified_support import CDN_URL, architecture, bottleneck_fixture, node



def payloads(tmp_path,count,variant='combined',cov=None):
    cov=cov or synthetic(count)
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


def kpi_numbers(cov):
    summary = cov['summary']
    return [summary['complete_file_count'], summary['partial_file_count'], summary['failed_file_count']]


@pytest.mark.parametrize('variant',('combined','architecture-only','bottlenecks-only','legacy','no-snapshot'))
def test_V06_coverage_kpi_capabilities(open_report,tmp_path,variant):
    """Rewritten for the KPI pill (A06): the per-file coverage table was removed, the complete/partial/failed counts remain."""
    arch,bottlenecks,cov=payloads(tmp_path,0,variant,cov=coverage_payload(['complete']*5+['partial']*3+['failed']*2+['skipped']))
    page=open_report(arch,bottlenecks)
    if variant in ('legacy','no-snapshot'):
        expect(page.get_by_text('분석 범위 정보 없음')).to_be_visible()
    else:
        assert pill_numbers(page,'분석 범위')==kpi_numbers(cov)
    assert page.locator('#coverage-details').count()==0
    assert set(page.external_requests)<={CDN_URL}
    assert page.unhandled_errors==[]


def test_V07_large_report_five_fresh_context_kpi_medians(open_report,tmp_path):
    arch,bottlenecks,cov=payloads(tmp_path,10000)
    cov=synthetic(10000,all_targeted=True)
    arch['stats']['analysis_coverage']=copy.deepcopy(cov)
    bottlenecks['coverage']['analysis_coverage']=copy.deepcopy(cov)
    raw={'summary':[]}
    for trial in range(5):
        started=time.perf_counter()
        page=open_report(arch,bottlenecks)
        expect(page.get_by_text('분석 범위',exact=True).first).to_be_visible()
        assert pill_numbers(page,'분석 범위')==kpi_numbers(cov)
        raw['summary'].append((time.perf_counter()-started)*1000)
        assert page.unhandled_errors==[]
    medians={key:statistics.median(values) for key,values in raw.items()}
    dump('performance.json',{'spec_version':3,'files':10000,'producers_per_file':7,'fresh_context_count':5,'raw_ms':raw,'median_ms':medians,'threshold_ms':{'summary':5000}})
    assert medians['summary']<=5000


@pytest.mark.parametrize('mode',('file','symbol'))
def test_V06_legacy_schema_pairs(open_report,mode):
    from report.shared.document import ReportInputError
    from tests.unified_support import document
    from tests.coverage_reporting_support import EVIDENCE
    baseline=json.loads((EVIDENCE/'characterization-baseline.json').read_text())
    payload=baseline['python:'+mode]
    assert payload['architecture']['schema_version']==('6' if mode=='file' else '5')
    assert payload['bottlenecks']['schema']==('bottlenecks.v5' if mode=='file' else 'bottlenecks.v4')
    with pytest.raises(ReportInputError, match='ambiguity_policy'):
        document(payload['architecture'],payload['bottlenecks'])
