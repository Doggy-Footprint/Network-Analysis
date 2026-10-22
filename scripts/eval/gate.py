"""Run a repository's behaviour gate (test command recorded in eval/results/<repo>/test-baseline.json) and count outcomes."""
import argparse
import glob
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

EVAL = Path(__file__).resolve().parents[2] / 'eval'
JAVA = 'JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"'
VENDURE_PATH = f'{EVAL}/envs/vendure/node-v22.23.4-darwin-arm64/bin:{EVAL}/envs/vendure/bun-darwin-aarch64'
# gradle and vitest/jest have no junit flag in the recorded commands, so they are parsed from their own reports/output
EXTRA = {
    'ghostfolio': ['npx tsc --noEmit -p apps/api/tsconfig.app.json', 'npx tsc --noEmit -p apps/api/tsconfig.spec.json'],
    'vendure': ['cd packages/core && npx tsc -p ./build/tsconfig.build.json --noEmit'],
}
GRADLE_PREFIX = {'nowinandroid': 'rm -rf */build/test-results */*/build/test-results && ', 'bitwarden': ''}


def counts_from_junit(paths):
    totals = dict(passed=0, failed=0, errors=0, skipped=0)
    for path in paths:
        for case in ET.parse(path).getroot().iter('testcase'):
            tags = {child.tag for child in case}
            key = 'failed' if 'failure' in tags else 'errors' if 'error' in tags else 'skipped' if 'skipped' in tags else 'passed'
            totals[key] += 1
    return totals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('repo')
    parser.add_argument('--cwd', help='checkout to test (default: the clone)')
    parser.add_argument('--label', default='gate')
    args = parser.parse_args()
    cwd = Path(args.cwd or EVAL / 'repos' / args.repo)
    baseline = json.loads((EVAL / 'results' / args.repo / 'test-baseline.json').read_text())
    command = baseline['test_command']
    out = EVAL / 'results' / args.repo / 'gates'
    out.mkdir(parents=True, exist_ok=True)
    junit = out / f'{args.label}.xml'
    env = dict(os.environ)
    if 'pytest' in command:
        command += f' --junitxml={junit}'
    if args.repo in GRADLE_PREFIX:
        command = GRADLE_PREFIX[args.repo] + command
        if '--no-build-cache' not in command:
            command = command.replace('./gradlew ', './gradlew --no-build-cache ')
    if args.repo == 'vendure':
        env['PATH'] = VENDURE_PATH + ':' + env['PATH']
    start = time.perf_counter()
    proc = subprocess.run(command, shell=True, cwd=cwd, env=env, capture_output=True, text=True)
    log = proc.stdout + proc.stderr
    result = {'repo': args.repo, 'cwd': str(cwd), 'command': command, 'returncode': proc.returncode, 'seconds': round(time.perf_counter() - start, 1)}
    if 'pytest' in command and junit.exists():
        result.update(counts_from_junit([junit]))
    elif args.repo in GRADLE_PREFIX:
        result.update(counts_from_junit(glob.glob(str(cwd / '**/build/test-results/**/TEST-*.xml'), recursive=True)))
    else:
        clean = re.sub(r'\x1b\[[0-9;]*m', '', log)
        if args.repo == 'ghostfolio':
            rows = re.findall(r'^(?:[\w-]+:\s+)?Tests:\s+(.*)$', clean, re.M)
            result['passed'] = sum(int(n) for row in rows for n in re.findall(r'(\d+) passed', row))
            result['failed'] = sum(int(n) for row in rows for n in re.findall(r'(\d+) failed', row))
        else:
            row = (re.findall(r'^\s*Tests\s+(.*)$', clean, re.M) or [''])[-1]
            result['passed'] = sum(int(n) for n in re.findall(r'(\d+) passed', row))
            result['failed'] = sum(int(n) for n in re.findall(r'(\d+) failed', row))
            result['type_errors'] = sum(int(n) for n in re.findall(r'Type Errors\s+(\d+)', clean))
    extras = []
    for extra in EXTRA.get(args.repo, []):
        ep = subprocess.run(extra, shell=True, cwd=cwd, env=env, capture_output=True, text=True)
        extras.append({'command': extra, 'returncode': ep.returncode, 'tail': (ep.stdout + ep.stderr)[-1500:]})
    result['extra_checks'] = extras
    expected = baseline['runs'][-1]
    result['expected_passed'] = expected['passed']
    result['ok'] = (proc.returncode == 0 and result.get('failed', 0) == 0 and result.get('errors', 0) == 0
                    and result.get('passed') == expected['passed'] and all(e['returncode'] == 0 for e in extras))
    (out / f'{args.label}.log').write_text(log)
    (out / f'{args.label}.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'extra_checks'} | {'extra_ok': [e['returncode'] == 0 for e in extras]}, indent=1))


if __name__ == '__main__':
    main()
