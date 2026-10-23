import ast
import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from tests.external_rules_support import strip_external_imports

from tests.coverage_reporting_support import ADAPTERS, BUILDERS, IDS, adapter, analyze, baseline_runner, coverage_of, dump, own_result, snapshot, without_coverage
from tests.test_repository_scan import policy, snapshot_of
from tests.candidate_policy_metadata_support import without_candidate_policy_metadata
from tests.legacy_metric_transition_support import legacy_to_current
from tests.structure_support import without_structure_facts


def assert_wire_version(coverage):
    assert type(coverage['version']) is int
    assert coverage['version']==1


@pytest.mark.parametrize('ident', IDS)
@pytest.mark.parametrize('kind', ('normal','empty','no-declarations'))
def test_V01_valid_partitions(tmp_path, ident, kind):
    _, _, ext, declaration = ADAPTERS[ident]
    source = {'normal':declaration,'empty':'','no-declarations':'# comment\n' if ext=='.py' else '// comment\n'}[kind]
    path='valid'+ext
    coverage=coverage_of(analyze(ident,tmp_path,snapshot(tmp_path,{path:source})))
    assert own_result(coverage,path,ident)=={'analyzer_id':ident,'status':'complete','reasons':[]}
    assert coverage['summary']['complete_file_count']==1


@pytest.mark.parametrize('ident', ('python-core','fastapi','sqlalchemy','nestjs','typescript-core','kotlin-core','android'))
def test_V01_parse_errors_and_surviving_sibling(tmp_path,ident):
    _,_,ext,valid=ADAPTERS[ident]
    invalid='def (:\n' if ext=='.py' else 'export class Broken { @@@' if ext=='.ts' else 'class Broken { fun broken( @@@'
    coverage=coverage_of(analyze(ident,tmp_path,snapshot(tmp_path,{'broken'+ext:invalid,'valid'+ext:valid})))
    expected='partial' if ident in ('typescript-core','kotlin-core','android') else 'failed'
    result=own_result(coverage,'broken'+ext,ident)
    assert result['status']==expected
    assert 'syntax_error' in {reason['code'] for reason in result['reasons']}
    assert all(reason['message'] for reason in result['reasons'])
    assert own_result(coverage,'valid'+ext,ident)['status']=='complete'


NEST_COMMON="import { Module, Controller, Get } from '@nestjs/common';\n"
SEMANTICS={
 'unsupported_expression':NEST_COMMON+'@Module({imports:[makeModule()]}) class Root {}\n',
 'unresolved_reference':NEST_COMMON+'@Module({imports:[Missing]}) class Root {}\n',
 'ambiguous_reference':NEST_COMMON+'@Module({imports:[Shared]}) class Root {}\n@Module({}) class Shared {}\n@Module({}) class Shared {}\n',
 'bootstrap_unresolved':NEST_COMMON+'@Controller() class C { @Get() route() {} }\n@Module({controllers:[C]}) class Root {}\n',
}


@pytest.mark.parametrize('code',tuple(SEMANTICS))
def test_V01_nestjs_existing_diagnostics_preserved(tmp_path,code):
    arch=analyze('nestjs',tmp_path,snapshot(tmp_path,{'main.ts':SEMANTICS[code]}),builder=True,language=False)
    result=own_result(coverage_of(arch),'main.ts','nestjs')
    assert result['status']=='partial'
    diagnostics=[d for d in arch.stats['nestjs']['diagnostics'] if d['code']==code]
    assert diagnostics
    for diagnostic in diagnostics:
        reasons=[r for r in result['reasons'] if r['code']==code]
        assert reasons
        span=diagnostic.get('span')
        if span:
            assert any(r.get('span')==span for r in reasons)
        message=diagnostic.get('message',diagnostic.get('reason'))
        if message:
            assert any(r['message']==message for r in reasons)


@pytest.mark.parametrize('states,expected,same_producer', [
 (['complete'],'complete',False),(['partial'],'partial',False),(['failed'],'failed',False),(['skipped'],'skipped',False),
 (['complete','failed'],'partial',False),(['complete','skipped'],'partial',False),(['partial','failed'],'partial',False),
 (['failed','skipped'],'failed',False),(['complete','complete'],'complete',True),(['failed','complete','skipped'],'partial',True)])
def test_V03_merge_decision_table(tmp_path,states,expected,same_producer):
    from language_analyzers.core.analysis_coverage import analysis_report, build_analysis_coverage
    reports=[analysis_report('python-core' if same_producer else f'producer-{i}',[{'file_path':'a.py','status':state,'reasons':[]}]) for i,state in enumerate(states)]
    coverage=build_analysis_coverage(snapshot(tmp_path,{'a.py':'','notes.txt':''}),reports)
    assert_wire_version(coverage)
    rows=coverage['files']
    assert all(row['reasons']==[] for row in rows)
    assert all(result['reasons']==[] for row in rows for result in row['results'])
    assert rows[0]['status']==expected
    assert rows[1]['status']=='not_targeted'
    assert len(rows[0]['results'])==(1 if same_producer else len(states))
    producer_states={'python-core':expected} if same_producer else {f'producer-{i}':state for i,state in enumerate(states)}
    assert [producer['analyzer_id'] for producer in coverage['analyzers']]==sorted(producer_states)
    for producer in coverage['analyzers']:
        producer_state=producer_states[producer['analyzer_id']]
        assert producer['summary']=={**{f'{state}_file_count':int(state==producer_state) for state in ('complete','partial','failed','skipped')},'targeted_file_count':1}
    assert {result['analyzer_id']:result['status'] for result in rows[0]['results']}==producer_states
    assert coverage['summary']=={**{f'{s}_file_count':int(s==expected) for s in ('complete','partial','failed','skipped')},'not_targeted_file_count':1,'excluded_file_count':0,'inventory_file_count':2,'collected_file_count':2,'targeted_file_count':1}


def test_V03_deterministic_reasons_empty_and_excluded(tmp_path):
    from language_analyzers.core.analysis_coverage import analysis_report, build_analysis_coverage
    reasons=[{'code':'z','message':'last'},{'code':'a','message':'first','span':{'file_path':'a.py','start_line':2,'end_line':2}}]
    snap=snapshot_of({'a.py':'','out.txt':'old'},root=tmp_path,excluded_paths=['out.txt'])
    reports=[analysis_report('python-core',[{'file_path':'a.py','status':'partial','reasons':reasons+reasons},{'file_path':'out.txt','status':'complete','reasons':[]}]),analysis_report('typescript-core',[{'file_path':'a.py','status':'skipped','reasons':list(reversed(reasons))}])]
    forward=build_analysis_coverage(snap,reports)
    backward=build_analysis_coverage(snap,list(reversed(reports)))
    assert_wire_version(forward)
    assert_wire_version(backward)
    assert forward==backward
    assert sorted(forward['files'][0]['reasons'],key=lambda reason:reason['code'])==[
        {'code':'a','message':'first','span':{'file_path':'a.py','start_line':2,'end_line':2}},
        {'code':'z','message':'last'},
    ]
    assert len(forward['files'][0]['reasons'])==2
    assert forward['files'][1]['status']=='excluded'
    assert forward['files'][1]['results']==[]
    assert forward['files'][1]['reasons'][0]['code']=='explicit_output'
    empty=build_analysis_coverage(snapshot(tmp_path,{}),[])
    assert_wire_version(empty)
    assert empty['files']==[] and empty['analyzers']==[]
    assert all(n==0 for n in empty['summary'].values())


def test_V02_scanner_codes_and_size_boundary(tmp_path):
    from language_analyzers.core.analysis_coverage import build_analysis_coverage
    files={'equal.txt':'x'*1000,'over.txt':'x'*1001,'out.txt':'x','my.lock':'x','vendor/a.py':'x','gen/a.py':'x','unread.txt':'x','binary.dat':'a\0b','marked.txt':'Generated File\nx','AGENTS.md':'guide'}
    snap=snapshot_of(files,root=tmp_path,unreadable=('unread.txt',),excluded_paths=['out.txt','new-output.txt'])
    coverage=build_analysis_coverage(snap,[])
    expected={'over.txt':'too_large','out.txt':'explicit_output','my.lock':'lockfile','vendor/a.py':'vendored','gen/a.py':'generated_path','unread.txt':'unreadable','binary.dat':'binary','marked.txt':'generated_marker','AGENTS.md':'agent_document_disabled'}
    assert {r['file_path']:r['reasons'][0]['code'] for r in coverage['files'] if r['status']=='excluded'}==expected
    assert next(r for r in coverage['files'] if r['file_path']=='equal.txt')['status']=='not_targeted'
    assert len(coverage['files'])==len(files)
    assert all(r['reasons'][0]['message'] for r in coverage['files'] if r['status']=='excluded')


@pytest.mark.parametrize('ident', ('typescript-core','kotlin-core','android','nestjs'))
def test_V02_discovery_excluded_vs_unrelated(tmp_path,ident):
    _,_,ext,source=ADAPTERS[ident]
    directory='build' if ident in ('kotlin-core','android') else 'node_modules'
    ignored=directory+'/ignored'+ext
    files={ignored:source,'notes.txt':'hello'}
    cov=coverage_of(analyze(ident,tmp_path,snapshot(tmp_path,files)))
    result=own_result(cov,ignored,ident)
    assert result['status']=='skipped'
    assert result['reasons'][0]['code']=='analyzer_excluded'
    assert next(r for r in cov['files'] if r['file_path']=='notes.txt')['results']==[]


@pytest.mark.parametrize('ident',IDS)
def test_V04_direct_snapshot_api(tmp_path,ident):
    _,_,ext,source=ADAPTERS[ident]
    snap=snapshot(tmp_path,{'main'+ext:source})
    arch=analyze(ident,tmp_path,snap,builder=True)
    cov=coverage_of(arch)
    assert_wire_version(cov)
    expected={ident,BUILDERS[ident][2]} if ident in BUILDERS else {ident}
    assert {a['analyzer_id'] for a in cov['analyzers']}==expected
    from analysis.file_graph import to_file_architecture
    converted=coverage_of(to_file_architecture(arch,snap))
    assert_wire_version(converted)
    assert converted==cov


def test_V04_source_and_build_only_apis(tmp_path):
    from language_analyzers.python.source import PythonSourceAnalyzer
    from language_analyzers.kotlin import KotlinAnalyzer
    snap=snapshot(tmp_path,{'a.py':'','a.kt':''})
    for obj,method,ident,path in [(PythonSourceAnalyzer(tmp_path,snapshot=snap),'analyze','python-core','a.py'),(KotlinAnalyzer(tmp_path,snapshot=snap),'build','kotlin-core','a.kt')]:
        getattr(obj,method)()
        assert_wire_version(obj.analysis_coverage)
        assert own_result(obj.analysis_coverage,path,ident)['status']=='complete'


@pytest.mark.parametrize('framework',tuple(BUILDERS))
def test_V04_framework_disabled_language(tmp_path,framework):
    _,_,ext,source=ADAPTERS[framework]
    arch=analyze(framework,tmp_path,snapshot(tmp_path,{'a'+ext:source}),builder=True,language=False)
    assert_wire_version(coverage_of(arch))
    assert [a['analyzer_id'] for a in coverage_of(arch)['analyzers']]==[framework]


def test_V05_characterization_and_V04_cli_stages():
    baseline=json.loads((Path(__file__).parent/'coverage_reporting_evidence'/'characterization-baseline.json').read_text())
    current=baseline_runner().capture()
    from tests.report_size_support import legacy_v8_full
    for name,record in current.items():
        if name.endswith(':file'):
            record['bottlenecks']=legacy_v8_full(record['bottlenecks'],record['architecture'])
    normalized = {name: {surface: without_structure_facts(without_candidate_policy_metadata(strip_external_imports(payload), surface)) for surface, payload in record.items()} for name, record in current.items()}
    assert without_coverage(normalized)==without_coverage(legacy_to_current(baseline)), 'Characterization: extraction, schema, metrics and candidates changed'
    expected={**{key:{key+'-core'} for key in ('python','typescript','kotlin')},'fastapi':{'fastapi','python-core'},'sqlalchemy':{'sqlalchemy','python-core'},'android':{'android','kotlin-core'},'nestjs':{'nestjs','typescript-core'},'fastapi-sqlalchemy':{'fastapi','sqlalchemy','python-core'},'nestjs-typescript':{'nestjs','typescript-core'},'android-kotlin':{'android','kotlin-core'}}
    for name,record in current.items():
        cov=record['architecture']['stats']['analysis_coverage']
        assert_wire_version(cov)
        assert_wire_version(record['bottlenecks']['coverage']['analysis_coverage'])
        assert cov==record['bottlenecks']['coverage']['analysis_coverage']
        assert {a['analyzer_id'] for a in cov['analyzers']}==expected[name.split(':')[0]]
        assert cov['summary']['inventory_file_count']==5
        assert all(len({r['analyzer_id'] for r in f['results']})==len(f['results']) for f in cov['files'])
    dump('regression.json',{'spec_version':2,'cases':sorted(current),'equal_after_asserting_candidate_policy_metadata_and_removing_coverage':True})


@pytest.mark.parametrize('ident',IDS)
def test_V07_snapshot_has_no_extra_source_reads(tmp_path,ident):
    _,_,ext,source=ADAPTERS[ident]
    snap=snapshot(tmp_path,{'main'+ext:source})
    obj=adapter(ident,tmp_path,snap)
    with patch.object(Path,'read_bytes',side_effect=AssertionError('extra source read')),patch.object(Path,'read_text',side_effect=AssertionError('extra source read')),patch.object(Path,'rglob',side_effect=AssertionError('extra inventory walk')):
        arch=obj.analyze()
    assert own_result(coverage_of(arch),'main'+ext,ident)['status']=='complete'


def cli_capture(monkeypatch,root,files,flags,extra=()):
    import code_analyzer.cli as cli
    from language_analyzers.core.serialization import architecture_to_dict
    captured={}
    reads=[]
    class Capture:
        def __init__(self,**kwargs):pass
        def render(self,arch,path,*,bottleneck_report=None):
            captured.update(architecture=architecture_to_dict(arch),bottlenecks=bottleneck_report)
            return Path(path)
    monkeypatch.setattr(sys,'argv',['code-analyzer',str(root),*flags,'-o',str(root/'out.html'),*extra])
    def reader(path):
        name=path.relative_to(root).as_posix()
        reads.append(name)
        return files[name]
    cli.main(file_lister=lambda *a,**kw:('provided',list(files)),file_reader=reader,renderer_factory=Capture)
    return captured,reads


def test_V02_cli_output_inventory_without_reading_or_invention(monkeypatch,tmp_path):
    current,reads=cli_capture(monkeypatch,tmp_path,{'a.py':'','out.html':'stale'},['-l','python'])
    coverage=current['architecture']['stats']['analysis_coverage']
    assert reads==['a.py']
    assert next(r for r in coverage['files'] if r['file_path']=='out.html')['status']=='excluded'
    assert coverage['scope']=={'ignore_source':'provided','unlisted_files':'not_enumerated'}
    current,reads=cli_capture(monkeypatch,tmp_path,{'a.py':''},['-l','python'])
    assert [r['file_path'] for r in current['architecture']['stats']['analysis_coverage']['files']]==['a.py']


def test_V04_explicit_python_sqlalchemy_disabled(monkeypatch,tmp_path):
    current,_=cli_capture(monkeypatch,tmp_path,{'a.py':'class A: pass\n'},['-l','python','-f','sqlalchemy','--no-language-graph'])
    coverage=current['architecture']['stats']['analysis_coverage']
    assert_wire_version(coverage)
    assert_wire_version(current['bottlenecks']['coverage']['analysis_coverage'])
    assert {r['analyzer_id'] for r in coverage['analyzers']}=={'python-core','sqlalchemy'}
    assert coverage==current['bottlenecks']['coverage']['analysis_coverage']


def test_V04_no_snapshot_and_unknown_legacy_architecture(tmp_path):
    from tests.file_analysis_support import architecture
    from bottlenecks import analyze_bottlenecks,bottlenecks_to_json
    from analysis.edge_weights import load_edge_weights,default_edge_weights_path
    root=tmp_path.resolve()
    (root/'a.py').write_text('class A: pass\n')
    from language_analyzers.python.graph import PythonGraphAnalyzer
    assert 'analysis_coverage' not in PythonGraphAnalyzer(root).analyze().stats
    legacy=architecture(root=str(root))
    snap=snapshot(root,{'a.py':''})
    payload=json.loads(bottlenecks_to_json(analyze_bottlenecks(snap,legacy,load_edge_weights(default_edge_weights_path()))))
    assert 'analysis_coverage' not in payload['coverage']


@pytest.mark.parametrize('signal',('reader','analyzer'))
def test_V05_fatal_signals_preserved(monkeypatch,tmp_path,signal):
    import code_analyzer.cli as cli
    marker=RuntimeError('fatal-coverage-oracle')
    monkeypatch.setattr(sys,'argv',['code-analyzer',str(tmp_path),'-l','python','-o',str(tmp_path/'out.html')])
    def reader(path):
        if signal=='reader':raise marker
        return 'class A: pass\n'
    if signal=='analyzer':
        monkeypatch.setattr(cli.PythonGraphAnalyzer,'analyze',lambda self: (_ for _ in ()).throw(marker))
    with pytest.raises(RuntimeError,match='fatal-coverage-oracle'):
        cli.main(file_lister=lambda *a,**kw:('provided',['a.py']),file_reader=reader)
    assert not (tmp_path/'out.html').exists()


def test_V07_read_parse_counts_match_immutable_characterization(tmp_path):
    import subprocess
    workspace=Path(__file__).resolve().parents[1]
    runner=Path(__file__).parent/'coverage_counter_runner.py'
    output=tmp_path/'counter-current.json'
    subprocess.run([sys.executable,str(runner),str(output)],cwd=workspace,check=True,timeout=120)
    baseline=json.loads((Path(__file__).parent/'coverage_reporting_evidence'/'counter-baseline.json').read_text())
    actual=json.loads(output.read_text())
    assert actual==baseline, 'Added source reads/parses or changed existing parser delegation'
    dump('counters.json',{'spec_version':2,'baseline':baseline,'actual':actual,'zero_extra_reads_parses':True})


@pytest.mark.parametrize('mode',('file','symbol'))
def test_V05_json_exports_and_regeneration(monkeypatch,tmp_path,mode):
    import re
    import code_analyzer.cli as cli
    from report.unified import render_unified_report
    output=tmp_path/'out.html'
    bottlenecks_path=tmp_path/'b.json'
    monkeypatch.setattr(sys,'argv',['code-analyzer',str(tmp_path),'-l','python','--granularity',mode,'-o',str(output),'--json','--bottlenecks',str(bottlenecks_path)])
    cli.main(file_lister=lambda *a,**kw:('provided',['a.py']),file_reader=lambda p:'class A: pass\n')
    arch=json.loads(output.with_suffix('.json').read_text())
    bottlenecks=json.loads(bottlenecks_path.read_text())
    inline=json.loads(re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>',output.read_text(),re.S).group(1))
    assert {k:v for k,v in inline['architecture'].items() if k not in ('schema_version','details_file')}=={k:v for k,v in arch.items() if k not in ('schema_version','details_file')}
    assert {k:v for k,v in inline['bottlenecks'].items() if k!='details_file'}=={k:v for k,v in bottlenecks.items() if k!='details_file'}
    assert inline['architecture']['schema_version']==('6' if mode=='file' else '5') and 'details_file' not in inline['architecture'] and 'details_file' not in inline['bottlenecks']
    assert arch['schema_version']==('7' if mode=='file' else '5')
    assert bottlenecks['schema']==('bottlenecks.v9' if mode=='file' else 'bottlenecks.v6')
    for value in (arch['stats']['analysis_coverage'],bottlenecks['coverage']['analysis_coverage'],inline['architecture']['stats']['analysis_coverage'],inline['bottlenecks']['coverage']['analysis_coverage']):
        assert_wire_version(value)
    assert arch['stats']['analysis_coverage']==bottlenecks['coverage']['analysis_coverage']
    regenerated=render_unified_report(arch,bottlenecks)
    data=json.loads(re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>',regenerated,re.S).group(1))
    assert_wire_version(data['architecture']['stats']['analysis_coverage'])
    assert_wire_version(data['bottlenecks']['coverage']['analysis_coverage'])
    assert data['architecture']==arch and data['bottlenecks']==bottlenecks


def test_V03_common_coverage_composition(tmp_path):
    from language_analyzers.core.analysis_coverage import analysis_report,build_analysis_coverage
    snap=snapshot(tmp_path,{'a.py':'','b.ts':''})
    python=analysis_report('python-core',[{'file_path':'a.py','status':'complete','reasons':[]}])
    typescript=analysis_report('typescript-core',[{'file_path':'b.ts','status':'partial','reasons':[{'code':'syntax_error','message':'oracle-recovery'}]}])
    direct=build_analysis_coverage(snap,[python,typescript])
    standalone=[build_analysis_coverage(snap,[python]),build_analysis_coverage(snap,[typescript])]
    composed=build_analysis_coverage(snap,standalone)
    for value in [direct,composed,*standalone]:
        assert_wire_version(value)
    for value in [direct,composed]:
        assert value['files'][0]['reasons']==[]
        assert value['files'][1]['reasons']==[{'code':'syntax_error','message':'oracle-recovery'}]
    assert composed==direct
    assert composed['summary']['complete_file_count']==1
    assert composed['summary']['partial_file_count']==1
