import importlib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from analysis import GraphAnalyzer
from tests.file_analysis_support import architecture, converted, node, snapshot
from tests.edge_weights_support import edge
from tests.test_cli_multi_analyzer import PROJECT_FILES
from tests.test_cli_sqlalchemy import MODELS, REVISION_1
from tests.test_nestjs_cli import NEST

ANDROID_DI = '''package com.example.feature.topic
import androidx.lifecycle.ViewModel
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
@HiltViewModel
class TopicViewModel @Inject constructor(private val name: String): ViewModel()
'''
FILES = {**PROJECT_FILES, 'feature_topic/src/main/kotlin/com/example/feature/topic/TopicViewModel.kt': ANDROID_DI, 'models.py': MODELS, 'alembic/versions/first.py': REVISION_1, 'src/main.ts': NEST, '.env': 'FEATURE_KEY=1\n'}
MODES = {'python':['-l','python'],'typescript':['-l','typescript'],'kotlin':['-l','kotlin'],'fastapi':['-f','fastapi'],'android':['-f','android'],'sqlalchemy':['-f','sqlalchemy'],'nestjs':['-f','nestjs']}
COMBINATIONS = {'fastapi-ts':['-f','fastapi','-l','typescript'],'android-fastapi':['-f','android','-f','fastapi'],'fastapi-sqlalchemy-ts':['-f','fastapi','-f','sqlalchemy','-l','typescript'],'nestjs-ts':['-f','nestjs','-l','typescript'],'sqlalchemy-python':['-f','sqlalchemy','-l','python']}


@pytest.fixture
def file_project(tmp_path):
    root=tmp_path/'project'
    for path,text in FILES.items():
        target=root/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(text,encoding='utf-8')
    subprocess.run(['git','init','-q'],cwd=root,check=True)
    subprocess.run(['git','add','.'],cwd=root,check=True)
    return root


def run(monkeypatch,*args):
    import code_analyzer.cli as cli
    monkeypatch.setattr(sys,'argv',['code-analyzer',*map(str,args)])
    try:
        cli.main()
    except SystemExit as exc:
        return exc.code
    return 0


def inline(path):
    found=re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>',path.read_text(),re.S)
    assert found
    return json.loads(found.group(1))


@pytest.mark.parametrize('mode',list(MODES))
def test_V01_single_cli_order_one_final_metrics(monkeypatch,file_project,tmp_path,mode):
    import code_analyzer.cli as cli
    observations=[]
    original=GraphAnalyzer.analyze
    def metrics(self,nodes,edges,*args,**kwargs):
        observations.append(('metrics',[n.id for n in nodes]))
        return original(self,nodes,edges,*args,**kwargs)
    monkeypatch.setattr(GraphAnalyzer,'analyze',metrics)
    original_snapshot=cli.build_snapshot
    def build(*args,**kwargs):
        observations.append(('snapshot',None)); return original_snapshot(*args,**kwargs)
    monkeypatch.setattr(cli,'build_snapshot',build)
    output=tmp_path/'file.html'
    assert run(monkeypatch,file_project,*MODES[mode],'-o',output,'--json','--bottlenecks',tmp_path/'b.json')==0
    calls=[value for kind,value in observations if kind=='metrics']
    assert len(calls)==1
    assert observations[0][0]=='snapshot'
    data=inline(output)
    assert data['architecture']['schema_version']=='6'
    assert data['architecture']['granularity']=='file'
    assert all(n.startswith('file:') or n in {row['id'] for row in data['architecture']['nodes'] if row.get('span') is None} for n in calls[0])
    assert data['architecture']==json.loads(output.with_suffix('.json').read_text())
    assert data['bottlenecks']==json.loads((tmp_path/'b.json').read_text())
    assert all('analysis' not in row.get('metadata',{}) for row in data['architecture']['details']['nodes'])


@pytest.mark.parametrize(('name','analyzer_path','builder_path'),[
    ('fastapi','framework_analyzers.fastapi.analyzer.FastAPIAnalyzer','framework_analyzers.fastapi.graph.ArchitectureGraphBuilder'),
    ('android','framework_analyzers.android.analyzer.AndroidAnalyzer','framework_analyzers.android.graph.AndroidArchitectureGraphBuilder'),
    ('sqlalchemy','framework_analyzers.sqlalchemy.SQLAlchemyAnalyzer','framework_analyzers.sqlalchemy.SQLAlchemyGraphBuilder'),
    ('nestjs','framework_analyzers.nestjs.NestJSAnalyzer','framework_analyzers.nestjs.NestJSGraphBuilder')])
def test_V01_direct_builder_defaults_characterization(monkeypatch,file_project,name,analyzer_path,builder_path):
    def resolve(path):
        module,symbol=path.rsplit('.',1); return getattr(importlib.import_module(module),symbol)
    original=GraphAnalyzer.analyze; calls=[]
    def observed(self,*args,**kwargs):
        calls.append(1); return original(self,*args,**kwargs)
    monkeypatch.setattr(GraphAnalyzer,'analyze',observed)
    model=resolve(analyzer_path)(str(file_project)).analyze()
    result=resolve(builder_path)().build_graph(model)
    assert calls
    assert result.stats.get('analysis')
    from analysis.edge_weights import load_edge_weights,default_edge_weights_path
    from bottlenecks import analyze_bottlenecks,bottlenecks_to_json
    from tests.file_analysis_support import serialize
    evidence=Path(__file__).parent/'file_analysis_evidence'
    provenance=json.loads((evidence/'direct-api-review.json').read_text())
    fixture_hash=hashlib.sha256(json.dumps(FILES,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    assert fixture_hash==provenance['input_sha256']=='467ab5757141843e0f822b25078e251a7057251019f5011c1e738b080995ebd3'
    assert provenance['original_commit']=='7eb255b0d552771c01e11fc2b4475663815c9567'
    golden=json.loads((evidence/'direct-api-original.json').read_text())[name]
    def normalized(value):
        encoded=json.dumps(value,ensure_ascii=False)
        for root in sorted({str(file_project),str(file_project.resolve())},key=len,reverse=True):
            encoded=encoded.replace(root,'<PROJECT_ROOT>')
        return json.loads(encoded.replace('/private<PROJECT_ROOT>','<PROJECT_ROOT>'))
    assert normalized(serialize(result))==normalized(golden['builder'])
    report=analyze_bottlenecks(snapshot(FILES,root=str(file_project.resolve())),result,load_edge_weights(default_edge_weights_path()))
    assert normalized(serialize(result))==normalized(golden['after_bottlenecks'])
    assert normalized(json.loads(bottlenecks_to_json(report)))==normalized(golden['bottlenecks'])


@pytest.mark.parametrize('option',['--no-language-graph','--no-models','--no-deps'])
def test_V01_exclusions_applied_before_details(monkeypatch,file_project,tmp_path,option):
    import code_analyzer.cli as cli
    language_calls=[]
    original=cli.PythonGraphAnalyzer.build
    def language(self,*args,**kwargs):
        language_calls.append(1); return original(self,*args,**kwargs)
    monkeypatch.setattr(cli.PythonGraphAnalyzer,'build',language)
    output=tmp_path/'excluded.html'
    assert run(monkeypatch,file_project,'-f','fastapi',option,'-o',output)==0
    details=inline(output)['architecture']['details']
    rows=details['nodes']
    ids={n['id'] for n in rows}
    if option=='--no-language-graph':
        assert language_calls==[]
        assert all(n.get('provenance')!='python-core' for n in rows)
    elif option=='--no-models':
        assert language_calls==[1]
        assert 'schema_main_UserOut' not in ids
        assert 'py:main#UserOut' in ids
        assert all(not (n.get('provenance')=='fastapi' and n['kind']=='schema') for n in rows)
    else:
        assert language_calls==[1]
        assert 'dep_main_get_db' not in ids
        assert 'py:main#get_db' in ids
        assert all(n['kind']!='dependency' for n in rows)
        assert all(e['relation']!='DEPENDS_ON' for e in details['edges'])


@pytest.mark.parametrize('combination',list(COMBINATIONS))
def test_V07_combinations_preserve_semantic_details(monkeypatch,file_project,tmp_path,combination):
    from scripts.benchmark_file_analysis import raw_relations
    output=tmp_path/'file.html'; symbol=tmp_path/'symbol.html'
    flags=COMBINATIONS[combination]
    assert run(monkeypatch,file_project,*flags,'-o',output)==0
    assert run(monkeypatch,file_project,*flags,'--granularity','symbol','-o',symbol)==0
    file_data=inline(output)['architecture']; symbol_data=inline(symbol)['architecture']
    assert raw_relations(file_data['details'])==raw_relations(symbol_data)
    relations={e['relation'] for e in file_data['details']['edges']}
    if combination in ('fastapi-ts','android-fastapi','fastapi-sqlalchemy-ts','nestjs-ts'):
        assert 'CALLS_ROUTE' in relations
    if combination in ('fastapi-ts','fastapi-sqlalchemy-ts','android-fastapi'):
        assert 'DEPENDS_ON' in relations
    if 'sqlalchemy' in combination:
        assert 'MIGRATES' in relations
    if combination=='android-fastapi':
        assert 'INJECTS' in relations
    if combination=='nestjs-ts':
        assert 'DEPENDS_ON' in relations and 'PROVIDES' in relations
    original_nodes={n['id']:n for n in file_data['details']['nodes']}
    routes=[e for e in file_data['details']['edges'] if e['relation']=='CALLS_ROUTE']
    expected_routes=set()
    if combination in ('fastapi-ts','fastapi-sqlalchemy-ts'):
        expected_routes={('ts:client.ts#loadUser','GET','/api/users/{user_id}'),('ts:client.ts#createUser','POST','/api/users')}
    elif combination=='android-fastapi':
        clients=[n['id'] for n in original_nodes.values() if n['group']=='retrofit_endpoint']
        assert len(clients)==1
        expected_routes={(clients[0],'GET','/api/users/{user_id}')}
    elif combination=='nestjs-ts':
        expected_routes={('ts:src/main.ts#getOk','GET','/api/ok'),('ts:src/main.ts#postOk','POST','/api/ok')}
    assert {(e['from_id'],original_nodes[e['to_id']]['metadata']['http_method'],original_nodes[e['to_id']]['metadata']['full_path']) for e in routes}==expected_routes
    for relation in routes:
        assert relation['confidence']=='framework_inferred'
        assert relation['resolution']=='unique_name'
        assert relation['candidates']==[]
    if combination in ('fastapi-ts','android-fastapi','fastapi-sqlalchemy-ts'):
        dependency_pairs={(e['from_id'],e['to_id']) for e in file_data['details']['edges'] if e['relation']=='DEPENDS_ON' and e['from_id'].startswith('ep_main_')}
        assert dependency_pairs=={('ep_main_get_user_GET','dep_main_get_db'),('ep_main_create_user_POST','dep_main_get_db')}
    if 'sqlalchemy' in combination:
        migrations=[e for e in file_data['details']['edges'] if e['relation']=='MIGRATES']
        assert {(original_nodes[e['from_id']]['span']['file_path'].replace('\\','/').split('alembic/')[-1],e['to_id'].rsplit('_',1)[-1]) for e in migrations}=={('versions/first.py','User'),('versions/first.py','Post')}
        assert all(original_nodes[e['from_id']]['group']=='alembic_migration' and original_nodes[e['to_id']]['group']=='sqlalchemy_model' for e in migrations)
    if combination=='android-fastapi':
        injects=[e for e in file_data['details']['edges'] if e['relation']=='INJECTS']
        assert len(injects)==1
        assert '_TopicViewModel' in injects[0]['from_id'] and '_providesName' in injects[0]['to_id']
    if combination=='nestjs-ts':
        semantic={(e['from_id'],e['to_id'],e['relation']) for e in file_data['details']['edges']}
        assert ('nestjs:controller:src/main.ts#C','nestjs:provider:src/main.ts#S','DEPENDS_ON') in semantic
        assert ('nestjs:module:src/main.ts#Root','nestjs:provider:src/main.ts#S','PROVIDES') in semantic
    detail=file_data['details']['edges']
    indices=[i for e in file_data['edges'] for i in e['metadata']['detail_edge_indices']]
    assert len(indices)==len(set(indices))
    for e in file_data['edges']:
        assert all(detail[i]['relation']==e['relation'] for i in e['metadata']['detail_edge_indices'])


def mermaid_records(text):
    declarations={}
    links=[]
    for line in text.splitlines():
        declaration=re.fullmatch(r'\s*([A-Za-z_]\w*)\["(.*)"\]\s*',line)
        if declaration:
            assert declaration[1] not in declarations
            declarations[declaration[1]]=json.loads('"'+declaration[2]+'"')
        link=re.fullmatch(r'\s*([A-Za-z_]\w*)\s+(-->|-\.->)(?:\|([^|]+)\|)?\s+([A-Za-z_]\w*)\s*',line)
        if link:
            links.append((link[1],link[2],link[3],link[4]))
        elif '-->' in line or '-.->' in line:
            pytest.fail('Unparsed Mermaid relation: '+line)
    nodes=set(declarations)|{ident for source,_,_,target in links for ident in (source,target)}
    return declarations,links,nodes


@pytest.mark.parametrize('granularity',['file','symbol'])
def test_V08_schemas_json_and_mermaid(monkeypatch,file_project,tmp_path,capsys,granularity):
    linked_files={**FILES,'main.py':'from models import User\n'+FILES['main.py']}
    (file_project/'main.py').write_text(linked_files['main.py'],encoding='utf-8')
    calls=[]
    original=GraphAnalyzer.analyze
    def metrics(self,*args,**kwargs):
        calls.append(1)
        return original(self,*args,**kwargs)
    monkeypatch.setattr(GraphAnalyzer,'analyze',metrics)
    path=tmp_path/f'{granularity}.html'
    assert run(monkeypatch,file_project,'-f','fastapi','--granularity',granularity,'-o',path,'--json','--bottlenecks',tmp_path/'b.json')==0
    data=inline(path)
    if granularity=='file':
        assert calls==[1]
    assert data['architecture']['schema_version']==('6' if granularity=='file' else '5')
    assert data['bottlenecks']['schema']==('bottlenecks.v5' if granularity=='file' else 'bottlenecks.v4')
    assert data['architecture']==json.loads(path.with_suffix('.json').read_text())
    assert data['bottlenecks']==json.loads((tmp_path/'b.json').read_text())
    if granularity=='symbol':
        assert 'details' not in data['architecture']
    capsys.readouterr()
    calls.clear()
    mermaid=tmp_path/'graph.md'
    assert run(monkeypatch,file_project,'-f','fastapi','--granularity',granularity,'--mermaid','-o',mermaid)==0
    text=capsys.readouterr().out
    if granularity=='file':
        assert calls==[1]
    assert re.search(r'(?m)^graph TD\s*$',text)
    evidence=Path(__file__).parent/'file_analysis_evidence'
    provenance=json.loads((evidence/'mermaid-linked-original-provenance.json').read_text())
    original_bytes=(evidence/'mermaid-linked-original-stdout.txt').read_bytes()
    assert hashlib.sha256(original_bytes).hexdigest()==provenance['stdout_sha256']
    assert hashlib.sha256(json.dumps(linked_files,sort_keys=True,ensure_ascii=False).encode()).hexdigest()==provenance['input_sha256']
    assert provenance['base_commit']=='7eb255b0d552771c01e11fc2b4475663815c9567'
    declarations,links,ids=mermaid_records(text)
    if granularity=='symbol':
        original_declarations,original_links,original_ids=mermaid_records(original_bytes.decode())
        assert original_ids=={'app_main_app','router_main_router','ep_main_get_user_GET','ep_main_create_user_POST','dep_main_get_db','schema_main_UserOut'}
        assert declarations==original_declarations
        assert sorted(links,key=str)==sorted(original_links,key=str)
        assert ids==original_ids
    else:
        original_architecture=(evidence/'mermaid-linked-original-architecture.json').read_bytes()
        assert hashlib.sha256(original_architecture).hexdigest()==provenance['architecture_sha256']
        source=json.loads(original_architecture)
        node_paths={n['id']:n['span']['file_path'] if n.get('span') else None for n in source['nodes']}
        expected_paths={'alembic/versions/first.py','main.py','models.py'}
        assert {path for path in node_paths.values() if path}==expected_paths
        assert len(declarations)==len(expected_paths)
        assert set(declarations.values())==expected_paths
        assert ids==set(declarations)
        assert all(re.fullmatch(r'n\d+',ident) for ident in ids)
        expected_links={(node_paths[e['from_id']],'-->',e['relation'],node_paths[e['to_id']]) for e in source['edges'] if e['relation'] not in ('CONTAINS','IMPLEMENTED_BY') and node_paths[e['from_id']] and node_paths[e['to_id']] and node_paths[e['from_id']]!=node_paths[e['to_id']]}
        assert expected_links=={('main.py','-->','IMPORTS','models.py'),('main.py','-->','IMPORTS_SYMBOL','models.py')}
        observed_links=[(declarations[source_id],arrow,relation,declarations[target_id]) for source_id,arrow,relation,target_id in links]
        assert len(observed_links)==len(expected_links)
        assert set(observed_links)==expected_links
        selected=data['architecture']
        assert {n['id'] for n in selected['nodes']}=={'file:'+path for path in expected_paths}
        assert {(e['from_id'].removeprefix('file:'),'-->',e['relation'],e['to_id'].removeprefix('file:')) for e in selected['edges']}==expected_links


@pytest.mark.parametrize(('case','flags'),[
    ('granularity',['--granularity','folder']),('duplicate-analyzer',['-l','python','-l','python']),
    ('entrypoint',['-f','sqlalchemy','--entrypoint','main.py']),('multi-mermaid',['-f','fastapi','-l','python','--mermaid'])])
def test_V12_parser_errors_preserve_output(monkeypatch,tmp_path,file_project,capsys,case,flags):
    import code_analyzer.cli as cli
    monkeypatch.setattr(cli,'build_snapshot',lambda *args,**kwargs: pytest.fail('Invalid parser input reached extraction'))
    output=tmp_path/'existing.html'; output.write_bytes(b'ORACLE_OLD_OUTPUT')
    assert run(monkeypatch,file_project,*flags,'-o',output)==2
    assert output.read_bytes()==b'ORACLE_OLD_OUTPUT'
    assert capsys.readouterr().err


def test_V12_output_collision(monkeypatch,tmp_path,file_project):
    import code_analyzer.cli as cli
    monkeypatch.setattr(cli,'build_snapshot',lambda *args,**kwargs: pytest.fail('Output collision reached extraction'))
    output=tmp_path/'existing.html'; output.write_bytes(b'ORACLE_OLD_OUTPUT')
    assert run(monkeypatch,file_project,'-l','python','-o',output,'--bottlenecks',output)==2
    assert output.read_bytes()==b'ORACLE_OLD_OUTPUT'


@pytest.mark.parametrize('case',['missing-path','not-directory','bad-weights'])
def test_V12_input_errors_no_write(monkeypatch,tmp_path,file_project,capsys,case):
    from renderers.html import HTMLRenderer
    monkeypatch.setattr(HTMLRenderer,'render',lambda *args,**kwargs: pytest.fail('Invalid input reached output'))
    target=tmp_path/'missing' if case=='missing-path' else tmp_path/'plain'
    if case=='not-directory': target.write_text('x')
    extra=[]
    if case=='bad-weights':
        target=file_project; invalid=tmp_path/'weights.yml'; invalid.write_text('x: ['); extra=['--edge-weights',invalid]
    output=tmp_path/'existing.html'; output.write_bytes(b'ORACLE_OLD_OUTPUT')
    assert run(monkeypatch,target,'-l','python','-o',output,*extra)==1
    assert output.read_bytes()==b'ORACLE_OLD_OUTPUT'
    assert capsys.readouterr().err


@pytest.mark.parametrize('case',['bad-snapshot','bad-graph-id','bad-reference','ownership-conflict'])
def test_V12_invalid_api_input(case):
    from analysis.file_graph import to_file_architecture
    from bottlenecks import BottleneckInputError,analyze_bottlenecks
    from analysis.edge_weights import load_edge_weights,default_edge_weights_path
    snap=snapshot({'a.py':'x','b.py':'y'})
    nodes=[node('a','a.py')]; edges=[]
    if case=='bad-snapshot': snap=snapshot({'../a.py':'x'})
    elif case=='bad-graph-id': nodes.append(node('a','a.py'))
    elif case=='bad-reference': edges=[edge('a','absent')]
    else:
        nodes += [node('b','b.py','class'),node('child',None)]
        edges=[edge('a','child',relation='CONTAINS'),edge('b','child',relation='CONTAINS')]
    with pytest.raises((ValueError,BottleneckInputError)):
        to_file_architecture(architecture(nodes,edges),snap)


@pytest.mark.parametrize('surface',['html','architecture','bottleneck'])
def test_V12_write_failures_nonzero(monkeypatch,tmp_path,file_project,capsys,surface):
    import code_analyzer.cli as cli
    output=tmp_path/'report.html'
    if surface=='html': output.mkdir()
    elif surface=='architecture': output.with_suffix('.json').mkdir()
    else: (tmp_path/'b.json').mkdir()
    assert run(monkeypatch,file_project,'-l','python','-o',output,'--json','--bottlenecks',tmp_path/'b.json')==1
    assert capsys.readouterr().err


def test_V08_legacy_v4_only_renderer_does_not_invent_details(tmp_path):
    from tests.test_report_bottlenecks_v3 import v3_payload
    from report.bottlenecks import render_report
    result=render_report(v3_payload(tmp_path))
    found=re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>',result,re.S)
    assert found
    data=json.loads(found.group(1))
    assert data['bottlenecks']['schema']=='bottlenecks.v4'
    if data['architecture'] is not None:
        assert 'details' not in data['architecture']


def test_V08_language_mermaid_existing_limit_characterization(monkeypatch,file_project,tmp_path,capsys):
    assert run(monkeypatch,file_project,'-l','python','--mermaid','-o',tmp_path/'language.html')==0
    captured=capsys.readouterr()
    assert '```mermaid' not in captured.out
    assert not re.search(r'(?m)^\s*(?:graph|flowchart)\s+(?:TD|LR|TB)',captured.out)
    assert re.search(r'Mermaid|mermaid',captured.out+captured.err)
