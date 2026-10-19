# Q1 benchmark procedure (spec 7ab6320d2eb56ccf v1, V9)

Requirement: file-granularity CLI analysis time, HEAD median of 5 runs divided by base-commit median of 5 runs,
must be <= 1.25 for each of the four fixtures `futuramaapi`, `fastapi-realworld`, `android-nowinandroid`,
`typescript-nestjs-realworld`. Direction: lower is better; threshold and context (file granularity, CLI, 5 runs, four
fixtures) must not be changed to make a result pass.

## Run

```bash
REPO=/home/user/Network-Analysis
BASE=$(mktemp -d)/base
git -C $REPO worktree add --detach $BASE b590d5461c59d93db7800f9be451392f367b8db0
cd $REPO
# make sure the four fixtures are already cloned (the first fixture_root call clones; keep that out of the timing)
uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','fastapi-official-template','android-nowinandroid','typescript-nestjs-realworld')]"
uv run -q --with-requirements requirements-dev.txt python tests/fact_defects_evidence/benchmark.py $BASE $REPO --runs 5 --threshold 1.25 --json /tmp/fact-defects-benchmark.json
```

Conditions: same machine, no other heavy process, `PYTHONHASHSEED=0`, each run a fresh subprocess with the worktree as
working directory, base and HEAD runs interleaved per repetition (drift affects both). The per-fixture flags come from
`tests/structure_evidence/base_manifest.json` (`commands`). The script exits 1 when any ratio exceeds 1.25.

## Record

| fixture | base median (s) | HEAD median (s) | ratio | <= 1.25 |
| --- | --- | --- | --- | --- |
| futuramaapi | | | | |
| fastapi-realworld | | | | |
| android-nowinandroid | | | | |
| typescript-nestjs-realworld | | | | |

Raw run times are in the JSON output (`base`/`head` arrays). If a ratio is above 1.25, repeat the whole benchmark once
to rule out noise; report both runs and fail the requirement if the second also exceeds the threshold. Do not raise the
threshold, reduce the run count or drop a fixture.

Cleanup: `git -C $REPO worktree remove --force $BASE`.
