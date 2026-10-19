# Base manifest regeneration (spec 7ab6320d2eb56ccf v3, Paths)

The characterization manifests of earlier runs pin CLI outputs of their own base commit. This run changes analyzer
facts (F7 TS relative import resolution, F8/F9 line counting, F11 Kotlin FQN imports), so each manifest was rebuilt from
its base commit with this run's Implementation diff applied.

## Common procedure

- Patch: `git diff b590d5461c59d93db7800f9be451392f367b8db0 HEAD -- language_analyzers/core/enrichment.py language_analyzers/typescript/analyzer.py language_analyzers/kotlin/analyzer.py language_analyzers/python/symbols.py repository/models.py language_analyzers/core/cost.py bottlenecks/core.py`
  (6 files, +71/-16; `bottlenecks/core.py` has no change in that range).
- Patched worktree: `git worktree add --detach <dir> <base_commit>`, then the patch applied uncommitted, so `HEAD`
  stays `<base_commit>`. For ef8adb3, 2627174 and 6fda6d5 a strict `git apply` fails on context in
  `kotlin/analyzer.py` and `typescript/analyzer.py`; those worktrees were patched by main. For f5ab529 and 6444895
  `git apply --index` applies cleanly. In all five worktrees the `+`/`-` lines of `git diff HEAD` are identical to
  the patch's `+`/`-` lines.
- CLI: `python -c 'from code_analyzer.cli import main; main()' <fixture_root(name).resolve()> <args> --granularity <g> -o <tmp>/r.html ...`
  with `cwd=<worktree>`, `PYTHONHASHSEED=0`, fixtures from the current repo (`fixtures.registry.fixture_root`).
- Reproduction check: each generator was first run on a clean `git worktree add --detach` of the unpatched base commit
  and its output compared with the committed manifest.
- `base_commit` values are kept unchanged: `tests/test_reach_candidates.py::test_V7_manifest_is_for_the_declared_base_commit`
  asserts `manifest['base_commit'] == BASE_COMMIT`, and the same field is kept in the other manifests for uniformity.
  Provenance (base commit + this run's patch) is recorded here instead of the `<commit>+fact-defects-7ab6320d2eb56ccf`
  form that spec v3 names.
- Size baselines: the size-ratio tests (`test_V11_size_ratio_realworld`, `test_V13_Q04_size_ratio`,
  `test_V14_architecture_size_ratio`, `test_V14_bottleneck_size_ratio_realworld`, `test_V11_size_ratio_per_fixture`)
  read only the `bytes` / `bottleneck_bytes` / `architecture_bytes` fields of `base_manifest.json`. The `size.json`
  files are review evidence of the earlier runs and are not read by any test; they are left unchanged.

## Generator for architecture_rules, delta, external_rules, structure

`regen_manifest.py <feature> <worktree> <out.json>` (kept in the session scratchpad, not in the repo). It loads the
committed manifest as a skeleton (key order, entries, `args`/`commands`, `rules`, descriptive strings, `base_commit`),
recomputes every measured value from fresh CLI output, and writes `json.dumps(indent=2, ensure_ascii=False)` with the
original trailing-newline convention.

```python
REPO = Path('/home/user/Network-Analysis')
MAIN = 'from code_analyzer.cli import main; main()'
BASE_KINDS = ('large_node', 'unresolved_boundary', 'evidence_spread')  # tests/structure_support.py

def sha(data): return hashlib.sha256(data).hexdigest()
def canonical_sha(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8'))

def run(worktree, name, args, granularity, out, extra=()):
    out.mkdir(parents=True)
    command = [sys.executable, '-c', MAIN, str(fixture_root(name).resolve()), *args, '--granularity', granularity,
               '-o', str(out / 'r.html'), *extra]
    done = subprocess.run(command, cwd=worktree, env=dict(os.environ, PYTHONHASHSEED='0'), capture_output=True, text=True)
    if done.returncode != 0: raise SystemExit(done.stderr[-3000:])
    return out

def architecture_rules(m, wt, tmp):
    for name, entry in m['fixtures'].items():
        o = run(wt, name, entry['args'], 'file', tmp / name, ['--bottlenecks', str(tmp / name / 'b.json')])
        data = (o / 'b.json').read_bytes()
        entry['bytes'], entry['sha256'] = len(data), sha(data)

def delta(m, wt, tmp):
    for i, entry in enumerate(m['runs']):
        d = tmp / f'run{i}'
        extra = ['--bottlenecks', str(d / 'b.json')]
        if entry['rules']:
            extra += ['--architecture-rules', entry['rules']]  # relative to the worktree cwd
        o = run(wt, entry['fixture'], entry['args'], 'file', d, extra)
        data = (o / 'b.json').read_bytes()
        entry['bottleneck_bytes'], entry['bottleneck_sha256'] = len(data), sha(data)

def external_rules(m, wt, tmp):
    for name, entry in m['fixtures'].items():
        for g in ('file', 'symbol'):
            if g not in entry: continue
            d = tmp / f'{name}-{g}'
            extra = ['--json'] + (['--bottlenecks', str(d / 'b.json')] if g == 'file' else [])
            o = run(wt, name, entry['args'], g, d, extra)
            arch = (o / 'r.json').read_bytes()
            payload = json.loads(arch); payload.pop('project_path', None)
            entry[g]['architecture_bytes'] = len(arch)
            entry[g]['architecture_canonical_sha256'] = canonical_sha(payload)
            if 'bottleneck_bytes' in entry[g]:
                data = (o / 'b.json').read_bytes()
                entry[g]['bottleneck_bytes'], entry[g]['bottleneck_sha256'] = len(data), sha(data)

def structure(m, wt, tmp):
    for name, entry in m['fixtures'].items():
        for g in ('file', 'symbol'):
            d = tmp / f'{name}-{g}'
            o = run(wt, name, m['commands'][name], g, d, ['--bottlenecks', str(d / 'b.json')])
            data = (o / 'b.json').read_bytes(); payload = json.loads(data)
            e = entry[g]
            e['bytes'], e['sha256'], e['schema'] = len(data), sha(data), payload['schema']
            if g == 'file':
                network = payload['dependency_network']
                for key in ('rankings', 'rankings_by_category', 'node_metrics', 'candidate_groups'):
                    e[key] = canonical_sha(network[key])
                base = [c for c in payload['candidates'] if c['kind'] in BASE_KINDS]
                e['candidate_count'], e['candidates'] = len(base), canonical_sha(base)
```

Invocation (from the repo root): `uv run -q --with-requirements requirements-dev.txt python regen_manifest.py <feature> <worktree> <out.json>`.

## Generator for reach

`tests/reach_evidence/make_base_manifest.py <worktree>` (committed generator, unchanged). It requires worktree
`HEAD == BASE_COMMIT`, which holds because the patch is uncommitted.

## Per manifest

| manifest | base commit | patched worktree | reproduction on clean base |
|---|---|---|---|
| `tests/architecture_rules_evidence/base_manifest.json` | ef8adb352c32936b102ed06d8dcb3ad2f28e6bdd | prepared by main (3-way context) | byte-equal |
| `tests/delta_evidence/base_manifest.json` | f5ab529bd2cdd8a084d66e2759d172fc3579cfd5 | `git apply --index` of the patch | byte-equal |
| `tests/external_rules_evidence/base_manifest.json` | 2627174d8a454a427965b5becee666c295454435 | prepared by main (3-way context) | canonically equal; see below |
| `tests/reach_evidence/base_manifest.json` | 6444895451a89f4450b9123b7beb17b11506e534 | `git apply --index` of the patch | byte-equal |
| `tests/structure_evidence/base_manifest.json` | 6fda6d5a91eee508088292ad8b428694ee70b32f | prepared by main (3-way context) | byte-equal |

external_rules: every `architecture_canonical_sha256`, `bottleneck_bytes` and `bottleneck_sha256` reproduced exactly.
All seven `architecture_bytes` came out exactly 25 bytes smaller than committed. `architecture_bytes` is the raw size
of the architecture JSON, which embeds the absolute fixture path once in top-level `project_path`; the manifest's own
canonical form excludes `project_path`, and the canonical hashes match. The original was therefore produced with a
fixture path 25 characters longer than `/home/user/Network-Analysis/.fixtures/<name>`. The regenerated values use the
current fixture path, which is the path the tests measure against.

## Entries changed (old manifest -> regenerated)

Python fixtures (futuramaapi, fastapi-realworld, fastapi-official-template) change only in hashes, with equal byte
counts except in architecture JSON. Kotlin (android-nowinandroid) and TypeScript (typescript-nestjs-realworld) change
in size and content.

- architecture_rules (file): android-nowinandroid bytes 7854408 -> 7803572 + sha256; typescript-nestjs-realworld
  bytes 645507 -> 725096 + sha256; fastapi-realworld, futuramaapi sha256 only.
- delta (file): android-nowinandroid 7854408 -> 7803572; typescript-nestjs-realworld (`-l typescript`, no `-f`)
  588166 -> 678170; futuramaapi, fastapi-realworld, fastapi-realworld+rules, fastapi-official-template sha256 only.
- external_rules: android-nowinandroid file architecture_bytes 8853602 -> 8832368, bottleneck_bytes 7854408 ->
  7803572; typescript-nestjs-realworld file architecture_bytes 1300683 -> 1465756, bottleneck_bytes 645507 -> 725096,
  symbol architecture_bytes 1196613 -> 1279736; futuramaapi file architecture_bytes 6794851 -> 6794814;
  fastapi-realworld file/symbol and fastapi-official-template file architecture_bytes -25 (project_path only); all
  canonical and bottleneck hashes of all fixtures changed.
- reach: android-nowinandroid file bytes 7864604 -> 7813747, candidate_count 106 -> 108; symbol bytes 6713411 ->
  6641877, candidate_count 490 -> 489; typescript-nestjs-realworld file bytes 650051 -> 729707, candidate_count 69 ->
  71; symbol bytes 550191 -> 568427, candidate_count 173 -> 210 (sections `candidates`, `dependency_network` changed);
  futuramaapi and fastapi-realworld file: `candidates` section and whole-file hashes only; futuramaapi delta:
  `canonical` and `sections.candidates` (the `delta` section hash is unchanged).
- structure: android-nowinandroid file bytes 7487354 -> 7430385 (rankings, rankings_by_category, node_metrics,
  candidate_groups, candidates changed; candidate_count 87 unchanged), symbol bytes 6713411 -> 6641877;
  typescript-nestjs-realworld file bytes 574330 -> 645354, candidate_count 53 -> 54 (all network sections changed),
  symbol bytes 550191 -> 568427; futuramaapi and fastapi-realworld file: `candidates` and sha256 only.
