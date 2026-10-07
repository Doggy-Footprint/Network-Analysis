import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'tests' / 'coverage_reporting_evidence'


def main():
    EVIDENCE.mkdir(exist_ok=True)
    immutable = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in EVIDENCE.glob('*-baseline.json')}
    first = ['tests/test_analysis_coverage_reporting.py', 'tests/test_analysis_coverage_browser.py']
    remaining = sorted(str(path.relative_to(ROOT)) for path in (ROOT/'tests').rglob('test_*.py') if str(path.relative_to(ROOT)) not in first)
    command = [sys.executable, '-m', 'pytest', *first, *remaining, '-q', '-x', '--junitxml=' + str(EVIDENCE/'pytest.xml')]
    preserved = {}
    with tempfile.TemporaryDirectory(prefix='coverage-evidence-preservation-') as temporary:
        backup = Path(temporary)
        for directory in ('file_analysis_evidence','unified_evidence','nestjs_evidence'):
            source = ROOT/'tests'/directory
            for path in source.rglob('*'):
                if path.is_file():
                    target=backup/path.relative_to(ROOT/'tests')
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(path,target)
                    preserved[path]=target
        try:
            with (EVIDENCE/'pytest.log').open('w') as log:
                result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=7800)
            exit_code=result.returncode
        except subprocess.TimeoutExpired:
            exit_code=124
        finally:
            for path,target in preserved.items():
                shutil.copy2(target,path)
            for path,expected in immutable.items():
                assert hashlib.sha256(path.read_bytes()).hexdigest()==expected, f'Immutable baseline modified: {path}'
    (EVIDENCE/'run.json').write_text(json.dumps({'spec_version':2,'command':command,'timeout_seconds':7800,'exit_code':exit_code,'historical_evidence_restored':True,'immutable_baselines_preserved':True},indent=2))
    print((EVIDENCE/'pytest.log').read_text()[-16000:])
    return exit_code


if __name__=='__main__':
    raise SystemExit(main())
