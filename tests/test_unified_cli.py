import json
import re
import sys

import pytest

from tests.test_cli_bottlenecks_v3 import project,out,run_cli


def inline(path):
    match=re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>',path.read_text(encoding='utf-8'),re.S)
    assert match
    return json.loads(match.group(1))


def test_V4_plain_output_computes_candidates(monkeypatch,project,out):
    assert run_cli(monkeypatch,str(project),'-l','python','-o',str(out/'report.html')) in (0,None)
    payload=inline(out/'report.html')
    assert payload['architecture']['schema_version']=='5'
    assert payload['bottlenecks']['schema']=='bottlenecks.v6'
    assert any(c['kind']=='unresolved_boundary' for c in payload['bottlenecks']['candidates'])
    assert list(out.iterdir())==[out/'report.html']


def test_V4_both_json_options_preserve_inline_originals(monkeypatch,project,out):
    assert run_cli(monkeypatch,str(project),'-l','python','-o',str(out/'report.html'),'--json','--bottlenecks',str(out/'b.json')) in (0,None)
    payload=inline(out/'report.html')
    assert payload['architecture']==json.loads((out/'report.json').read_text())
    assert payload['bottlenecks']==json.loads((out/'b.json').read_text())
    assert payload['architecture']['schema_version']=='5'
    assert payload['bottlenecks']['schema']=='bottlenecks.v6'


def test_V4_removed_html_option_is_error_two(monkeypatch,capsys,project,out):
    assert run_cli(monkeypatch,str(project),'-l','python','-o',str(out/'report.html'),'--bottlenecks-html',str(out/'b.html'))==2
    assert '--bottlenecks-html' in capsys.readouterr().err
    assert list(out.iterdir())==[]


@pytest.mark.parametrize('case',['html-bottlenecks','json-bottlenecks'],ids=str)
def test_V4_output_collision_rejected(monkeypatch,capsys,project,out,case):
    target=out/('report.html' if case=='html-bottlenecks' else 'report.json')
    args=[str(project),'-l','python','-o',str(out/'report.html'),'--bottlenecks',str(target)]
    if case=='json-bottlenecks':args+=['--json']
    assert run_cli(monkeypatch,*args)==2
    assert capsys.readouterr().err
    assert list(out.iterdir())==[]


def test_V4_output_excluded_inside_project(monkeypatch,project):
    output=project/'report.html'
    stale=project/'report_assets';stale.mkdir();(stale/'old.py').write_text('def OLD_OUTPUT_ORACLE(): return 1\n')
    output.write_text('def OLD_HTML_ORACLE(): return 1\n')
    assert run_cli(monkeypatch,str(project),'-l','python','-o',str(output),'--json','--bottlenecks',str(project/'b.json')) in (0,None)
    payload=inline(output)
    text=json.dumps(payload['architecture'])
    assert 'OLD_OUTPUT_ORACLE' not in text and 'OLD_HTML_ORACLE' not in text
    assert output.name not in {n.get('span',{}).get('file_path') for n in payload['architecture']['nodes'] if n.get('span')}


def test_V6_renderer_io_failure_nonzero(monkeypatch,capsys,project,out):
    class BrokenRenderer:
        def render(self,*args,**kwargs):raise OSError('ORACLE_DISK_FAILURE')
    import code_analyzer.cli as cli
    monkeypatch.setattr(sys,'argv',['code-analyzer',str(project),'-l','python','-o',str(out/'report.html')])
    with pytest.raises(SystemExit) as raised:cli.main(renderer_factory=lambda **kwargs:BrokenRenderer())
    assert raised.value.code==1
    captured=capsys.readouterr()
    assert 'ORACLE_DISK_FAILURE' in captured.err
    assert not (out/'report.html').exists()
