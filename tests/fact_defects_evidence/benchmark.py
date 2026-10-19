#!/usr/bin/env python3
"""Q1 benchmark: file-granularity CLI wall time, HEAD median(5) / base median(5) per fixture, threshold <= 1.25.

Usage: benchmark.py BASE_WORKTREE HEAD_WORKTREE [--runs 5] [--threshold 1.25] [--json OUT.json]

BASE_WORKTREE and HEAD_WORKTREE are checkouts (e.g. `git worktree add --detach <dir> b590d5461c59d93db7800f9be451392f367b8db0`
and the repository under test). Each run is a fresh subprocess of the CLI with PYTHONHASHSEED=0, started with the
worktree as the working directory. Base and head runs are interleaved per repetition so machine drift hits both sides.
Fixture checkouts are resolved by the HEAD worktree's fixtures.registry and shared by both sides. Exit code 1 if any ratio
exceeds the threshold.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

FIXTURES = ('futuramaapi', 'fastapi-realworld', 'android-nowinandroid', 'typescript-nestjs-realworld')
MAIN = 'from code_analyzer.cli import main; main()'
MANIFEST = 'tests/structure_evidence/base_manifest.json'


def fixture_path(head, name):
    code = f"from fixtures.registry import fixture_root; print(fixture_root({name!r}).resolve())"
    done = subprocess.run([sys.executable, '-c', code], cwd=head, capture_output=True, text=True, check=True)
    return done.stdout.strip().splitlines()[-1]


def fixture_flags(head):
    return json.loads((Path(head) / MANIFEST).read_text(encoding='utf-8'))['commands']


def timed_run(worktree, project, flags, scratch):
    out = Path(scratch)
    command = [sys.executable, '-c', MAIN, project, *flags, '--granularity', 'file', '-o', str(out / 'r.html'),
               '--bottlenecks', str(out / 'b.json')]
    started = time.perf_counter()
    done = subprocess.run(command, cwd=worktree, env=dict(os.environ, PYTHONHASHSEED='0'), capture_output=True, text=True)
    elapsed = time.perf_counter() - started
    if done.returncode != 0:
        raise SystemExit(f'CLI failed in {worktree} for {project}: {done.stderr[-1500:]}')
    return elapsed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('base')
    parser.add_argument('head')
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--threshold', type=float, default=1.25)
    parser.add_argument('--json')
    args = parser.parse_args()
    flags = fixture_flags(args.head)
    results, failed = {}, False
    print(f'{"fixture":<30}{"base median s":>15}{"head median s":>15}{"ratio":>9}  verdict')
    with tempfile.TemporaryDirectory() as scratch:
        for name in FIXTURES:
            project = fixture_path(args.head, name)
            times = {'base': [], 'head': []}
            for _ in range(args.runs):
                for side, tree in (('base', args.base), ('head', args.head)):
                    times[side].append(timed_run(tree, project, flags[name], scratch))
            base_median, head_median = statistics.median(times['base']), statistics.median(times['head'])
            ratio = head_median / base_median
            verdict = 'PASS' if ratio <= args.threshold else 'FAIL'
            failed |= verdict == 'FAIL'
            results[name] = {'base': times['base'], 'head': times['head'], 'base_median': base_median,
                             'head_median': head_median, 'ratio': ratio, 'verdict': verdict}
            print(f'{name:<30}{base_median:>15.3f}{head_median:>15.3f}{ratio:>9.3f}  {verdict}')
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding='utf-8')
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
