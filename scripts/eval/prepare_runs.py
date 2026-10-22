"""Prepare isolated end-to-end runs: fresh depth-1 clone, seeded untracked env files, gate wrapper, task prompt, settings.

Layout: <runs>/<arm>-<n>/<repo>/{clone,report?,gate,TASK.md,settings.json,run.json}. The runs root lives outside this
repository so a headless agent started there never discovers this project's CLAUDE.md/AGENTS.md.
"""
import argparse
import json
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / 'eval'
MANIFEST = json.loads((Path(__file__).parent / 'repos.json').read_text())
RUNS = Path.home() / 'toy-projects' / 'network-analysis-eval' / 'runs'
REPOS = ['mealie', 'lnbits', 'CTFd', 'flask-admin', 'ghostfolio', 'vendure', 'nowinandroid']
JAVA_HOME = '/Applications/Android Studio.app/Contents/jbr/Contents/Home'
VENDURE_PATH = f'{EVAL}/envs/vendure/node-v22.23.4-darwin-arm64/bin:{EVAL}/envs/vendure/bun-darwin-aarch64'
# untracked files the gate needs that a fresh clone lacks; copied (APFS clone) from the pilot clones, never their tracked files
SEED = {
    'ghostfolio': ['node_modules'],
    'vendure': ['node_modules', 'packages/*/node_modules', 'packages/common/lib'],
    'nowinandroid': ['local.properties'],
}
EXTRA = {
    'ghostfolio': ['npx tsc --noEmit -p apps/api/tsconfig.app.json', 'npx tsc --noEmit -p apps/api/tsconfig.spec.json'],
    'vendure': ['(cd packages/core && npx tsc -p ./build/tsconfig.build.json --noEmit)'],
}
REPORT_FILES = ['report.html', 'report.json', 'bottlenecks.json']


def git(*args, cwd=None):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def fresh_clone(repo, clone):
    spec = MANIFEST[repo]
    clone.mkdir(parents=True)
    git('init', '-q', cwd=clone)
    # fetch by URL without registering a remote, so the agent's checkout has no upstream to query
    git('fetch', '-q', '--depth', '1', f'https://github.com/{spec["github"]}.git', spec['commit'], cwd=clone)
    git('checkout', '-q', '-b', 'base', 'FETCH_HEAD', cwd=clone)
    (clone / '.git' / 'FETCH_HEAD').unlink()
    shutil.rmtree(clone / '.git' / 'logs', ignore_errors=True)
    git('config', 'user.name', 'eval-agent', cwd=clone)
    git('config', 'user.email', 'eval-agent@localhost', cwd=clone)
    assert git('rev-parse', 'HEAD', cwd=clone) == spec['commit']
    assert git('remote', cwd=clone) == ''


def seed(repo, clone):
    source = EVAL / 'repos' / repo
    for pattern in SEED.get(repo, []):
        for path in sorted(source.glob(pattern)):
            target = clone / path.relative_to(source)
            subprocess.run(['cp', '-c', '-R', str(path), str(target)], check=True)


def gate_script(repo, run_dir, locks):
    baseline = json.loads((EVAL / 'results' / repo / 'test-baseline.json').read_text())
    command = baseline['test_command']
    gradle = repo in ('nowinandroid', 'bitwarden')
    env = []
    if MANIFEST[repo]['language'] == 'python':
        # flask-admin/lnbits venvs carry editable .pth entries into the pilot clones; PYTHONPATH puts this clone first
        env.append(f'export PYTHONPATH={shlex.quote(str(run_dir / "clone"))}')
    if repo == 'vendure':
        env.append(f'export PATH={shlex.quote(VENDURE_PATH)}:"$PATH"')
    if gradle:
        command = 'rm -rf */build/test-results */*/build/test-results && ' + command
        if '--no-build-cache' not in command:
            command = command.replace('./gradlew ', './gradlew --no-build-cache ')
    extras = '\n'.join(f'echo "== extra check: {e}" >> "$LOG"; ( {e} ) >> "$LOG" 2>&1 || EXTRA_FAIL=1' for e in EXTRA.get(repo, []))
    stop = f'JAVA_HOME="{JAVA_HOME}" ./gradlew --stop >/dev/null 2>&1' if gradle else ':'
    kinds = 'gradle slot' if gradle else 'slot'
    return f'''#!/bin/bash
# Behaviour gate for {repo}. Waits for a free shared test slot (and the single Gradle slot) and for free memory,
# then runs the recorded test command in the clone. Expected on the untouched base: {baseline["runs"][-1]["passed"]} passed, 0 failed.
RUN={shlex.quote(str(run_dir))}
LOCKS={shlex.quote(str(locks))}
mkdir -p "$RUN/gates" "$LOCKS"
LOG="$RUN/gates/$(date +%Y%m%d-%H%M%S).log"
HELD=()
release() {{ for l in "${{HELD[@]}}"; do rm -rf "$l"; done; }}
trap release EXIT
take() {{
  while true; do
    for l in "$@"; do
      if mkdir "$l" 2>/dev/null; then echo $$ > "$l/pid"; HELD+=("$l"); return; fi
      p=$(cat "$l/pid" 2>/dev/null); [ -n "$p" ] && ! kill -0 "$p" 2>/dev/null && rm -rf "$l"
    done
    sleep 15
  done
}}
for k in {kinds}; do
  case $k in gradle) take "$LOCKS/gradle";; slot) take "$LOCKS/slot1" "$LOCKS/slot2";; esac
done
while true; do
  free=$(vm_stat | awk '/Pages free|Pages inactive|Pages speculative/ {{gsub("\\\\.","",$NF); s+=$NF}} END {{print int(s*16384/1048576)}}')
  [ "$free" -ge 2048 ] && break
  sleep 20
done
cd "$RUN/clone" || exit 2
{chr(10).join(env)}
echo "== gate: {repo} at $(git rev-parse --short HEAD) ($(git branch --show-current))" > "$LOG"
( {command} ) >> "$LOG" 2>&1
RC=$?
EXTRA_FAIL=0
{extras}
{stop}
tail -n 60 "$LOG"
echo "== gate exit code: $RC, extra checks failed: $EXTRA_FAIL, full log: $LOG"
[ $RC -eq 0 ] && [ $EXTRA_FAIL -eq 0 ]
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arms', nargs='+', default=['treatment', 'control'])
    parser.add_argument('--n', type=int, default=1)
    parser.add_argument('--repos', nargs='+', default=REPOS)
    args = parser.parse_args()
    analyzer_commit = git('rev-parse', 'HEAD', cwd=ROOT)
    for arm in args.arms:
        for repo in args.repos:
            run_dir = RUNS / f'{arm}-{args.n}' / repo
            if run_dir.exists():
                raise SystemExit(f'{run_dir} exists; runs are never reused')
            fresh_clone(repo, run_dir / 'clone')
            seed(repo, run_dir / 'clone')
            if arm == 'treatment':
                (run_dir / 'report').mkdir()
                for name in REPORT_FILES:
                    shutil.copy2(EVAL / 'results' / repo / 'before' / name, run_dir / 'report' / name)
            gate = run_dir / 'gate'
            gate.write_text(gate_script(repo, run_dir, RUNS / '.locks'))
            gate.chmod(0o755)
            (run_dir / 'run.json').write_text(json.dumps({'arm': arm, 'n': args.n, 'repo': repo, 'base': MANIFEST[repo]['commit'],
                                                          'analyzer_commit': analyzer_commit,
                                                          'report_source': str(EVAL / 'results' / repo / 'before') if arm == 'treatment' else None}, indent=1))
            print('prepared', run_dir)


if __name__ == '__main__':
    main()
