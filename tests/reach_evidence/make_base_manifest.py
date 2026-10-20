"""Digests use canonical JSON (sorted keys, compact separators, ensure_ascii=False, UTF-8 sha256), the form the
reach tests compare against."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from fixtures.registry import fixture_root  # noqa: E402
from tests.reach_support import BASE_COMMIT, FIXTURES, MANIFEST_PATH, canonical_sha  # noqa: E402
import hashlib  # noqa: E402

MAIN = 'from code_analyzer.cli import main; main()'
COMMANDS = {'android-nowinandroid': ['-l', 'kotlin'], 'fastapi-realworld': ['-l', 'python'],
            'futuramaapi': ['-l', 'python'], 'typescript-nestjs-realworld': ['-l', 'typescript', '-f', 'nestjs']}
DELTA_FIXTURE = 'futuramaapi'


def run_cli(worktree, name, granularity, out_dir, extra=()):
    command = [sys.executable, '-c', MAIN, str(fixture_root(name).resolve()), *COMMANDS[name], '--granularity', granularity,
               '-o', str(out_dir / 'report.html'), '--bottlenecks', str(out_dir / 'b.json'), *extra]
    done = subprocess.run(command, cwd=worktree, env=dict(os.environ, PYTHONHASHSEED='0'), capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(done.stderr[-2000:])
    return (out_dir / 'b.json').read_bytes()


def digest_sections(payload):
    return {key: canonical_sha(value) for key, value in payload.items()}


def main():
    worktree = Path(sys.argv[1]).resolve()
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=worktree, capture_output=True, text=True, check=True).stdout.strip()
    if head != BASE_COMMIT:
        raise SystemExit(f'worktree is at {head}, expected {BASE_COMMIT}')
    manifest = {'base_commit': BASE_COMMIT,
                'canonical_json': "json.dumps(value, sort_keys=True, separators=(',',':'), ensure_ascii=False) UTF-8 sha256",
                'commands': COMMANDS, 'fixtures': {}, 'delta': {}}
    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        for name in FIXTURES:
            entry = {}
            for granularity in ('file', 'symbol'):
                target = scratch / f'{name}-{granularity}'
                target.mkdir()
                data = run_cli(worktree, name, granularity, target)
                payload = json.loads(data)
                entry[granularity] = {'schema': payload['schema'], 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                                      'canonical': canonical_sha(payload), 'sections': digest_sections(payload),
                                      'candidate_kinds': sorted({c['kind'] for c in payload['candidates']}),
                                      'candidate_count': len(payload['candidates'])}
            manifest['fixtures'][name] = entry
        first = scratch / 'delta-first'
        first.mkdir()
        run_cli(worktree, DELTA_FIXTURE, 'file', first)
        second = scratch / 'delta-second'
        second.mkdir()
        data = run_cli(worktree, DELTA_FIXTURE, 'file', second, extra=['--baseline', str(first / 'b.json')])
        payload = json.loads(data)
        manifest['delta'] = {'fixture': DELTA_FIXTURE, 'delta': canonical_sha(payload['delta']), 'canonical': canonical_sha(payload),
                             'sections': digest_sections(payload)}
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print('wrote', MANIFEST_PATH)


if __name__ == '__main__':
    main()
