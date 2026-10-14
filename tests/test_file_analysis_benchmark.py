import copy
import json
import pickle
import statistics
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.benchmark_file_analysis import STAGES, digest, dump, verify_artifacts
from tests.file_analysis_support import snapshot
from tests.file_analysis_support import CHARACTERIZATION_FILES
from tests.candidate_policy_transition_support import assert_candidate_policy_transition

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=Path(__file__).parent/'file_analysis_evidence'


@pytest.fixture(scope='session')
def file_benchmark_evidence():
    command=[sys.executable,str(ROOT/'scripts/benchmark_file_analysis.py'),'--verify','--project','/Users/hwansu/toy-projects/Tag-Manager','--evidence-dir',str(EVIDENCE)]
    subprocess.run(command,cwd=ROOT,check=True,timeout=6000)
    return EVIDENCE


@pytest.mark.benchmark
def test_V13_real_snapshot_symbol_equivalence_and_three_processes(file_benchmark_evidence):
    directory=file_benchmark_evidence
    manifest=json.loads((directory/'baseline-manifest.json').read_text())
    baseline=json.loads((directory/'baseline-relations.json').read_text())
    optimized=json.loads((directory/'optimized-symbol-relations.json').read_text())
    frozen = pickle.loads((directory/'baseline-snapshot.pickle').read_bytes())
    assert_candidate_policy_transition(baseline, optimized, frozen.contents)
    small_baseline = json.loads((directory/'baseline-small-relations.json').read_text())
    small_optimized = json.loads((directory/'optimized-small-relations.json').read_text())
    assert small_baseline.keys() == small_optimized.keys()
    for name in small_baseline:
        assert_candidate_policy_transition(small_baseline[name], small_optimized[name], CHARACTERIZATION_FILES)
    result=json.loads((directory/'benchmark.json').read_text())
    assert result['spec_version']==2
    assert json.loads((directory/'symbol-equivalence.json').read_text())['spec_version']==2
    assert json.loads((directory/'browser.json').read_text())['spec_version']==2
    assert len(result['raw_seconds'])==3
    assert result['raw_seconds']==[run['total_seconds'] for run in result['runs']]
    assert result['median_seconds']==statistics.median(result['raw_seconds'])
    assert result['median_seconds']<=180
    for index,run in enumerate(result['runs'],1):
        assert run['spec_version']==2
        assert run['snapshot_hash']==manifest['snapshot_hash']
        assert set(run['stages'])==set(STAGES)
        assert all(value>=0 for value in run['stages'].values())
        assert sum(run['stages'].values())==pytest.approx(run['total_seconds'],abs=1e-9,rel=1e-8)
        assert Path(run['html']).name==f'file-run{index}.html'
        assert Path(run['html']).is_file()


@pytest.mark.parametrize('defect',['snapshot-mismatch','relation-mismatch','timing-failure','missing-browser-evidence'])
def test_V13_runner_rejects_false_acceptance(monkeypatch,tmp_path,defect):
    import tests.file_analysis_support as support
    small_oracle = {'small': {'nodes': [{'id': 'small-oracle', 'metadata': {}}], 'edges': []}}
    monkeypatch.setattr(support,'characterization',lambda:copy.deepcopy(small_oracle))
    dump(tmp_path/'baseline-small-inputs.json',support.CHARACTERIZATION_FILES)
    dump(tmp_path/'baseline-small-relations.json',small_oracle)
    relations={'nodes':[{'id':'oracle','metadata':{}}],'edges':[]}
    dump(tmp_path/'baseline-relations.json',relations)
    alternate=copy.deepcopy(relations)
    if defect=='relation-mismatch': alternate['nodes'][0]['id']='mutated'
    dump(tmp_path/'optimized-symbol-relations.json',alternate)
    frozen=snapshot({'oracle.py':'fixed-independent-input'})
    frozen_hash=digest(frozen)
    (tmp_path/'baseline-snapshot.pickle').write_bytes(pickle.dumps(frozen))
    dump(tmp_path/'baseline-manifest.json',{'snapshot_hash':frozen_hash})
    dump(tmp_path/'optimized-symbol-timing.json',{'snapshot_hash':frozen_hash})
    for index in range(1,4):
        seconds=181 if defect=='timing-failure' else 179
        dump(tmp_path/f'file-run{index}-timing.json',{'snapshot_hash':'different' if defect=='snapshot-mismatch' else frozen_hash,'pid':index,'mode':f'file-run{index}','stages':{stage:seconds/6 for stage in STAGES},'total_seconds':seconds})
    if defect!='missing-browser-evidence': dump(tmp_path/'browser.json',{'datasets':{name:{'fresh_context_count':5,'raw_ms':{metric:[1]*5 for metric in ('summary_ms','filter_page_ms','detail_graph_ms')}} for name in ('synthetic','Tag-Manager')}})
    with pytest.raises((AssertionError,FileNotFoundError)):
        verify_artifacts(tmp_path)
    assert json.loads((tmp_path/'benchmark.json').read_text())['passed'] is False
