# Review procedure: observable change audit (spec 7ab6320d2eb56ccf v1, V8 / C14 / R12 / I2)

Acceptance: 0 unexplained changes, 0 wrong edges. A change is explained only when it is traced to one of
F11 (TS relative import resolution), F7 (Kotlin FQN import + imported-name references), F8 (module end_line),
F9 (line count rule). Anything else is a finding.

Inputs: base commit `b590d5461c59d93db7800f9be451392f367b8db0`, HEAD (working tree under review), fixtures
`typescript-nestjs-realworld` and `android-nowinandroid`, granularity `file` and `symbol`, sample seed `20261019`.

## 1. Produce the outputs

```bash
REPO=/home/user/Network-Analysis
BASE=$(mktemp -d)/base            # any empty parent dir outside the repo
git -C $REPO worktree add --detach $BASE b590d5461c59d93db7800f9be451392f367b8db0
OUT=$(mktemp -d)
NEST=$(cd $REPO && uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; print(fixture_root('typescript-nestjs-realworld').resolve())")
ANDROID=$(cd $REPO && uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; print(fixture_root('android-nowinandroid').resolve())")
run() {  # run <worktree> <tag> <fixture-name> <path> <flags...>
  wt=$1; tag=$2; name=$3; path=$4; shift 4
  for g in file symbol; do
    (cd $wt && PYTHONHASHSEED=0 uv run -q --with-requirements $REPO/requirements-dev.txt python \
      -c 'from code_analyzer.cli import main; main()' "$path" "$@" --granularity $g --json \
      -o $OUT/$tag-$name-$g.html --bottlenecks $OUT/$tag-$name-$g.bottlenecks.json >/dev/null)
  done
}
for tag_wt in "base:$BASE" "head:$REPO"; do
  run ${tag_wt#*:} ${tag_wt%%:*} nestjs "$NEST" -l typescript -f nestjs      # flags from tests/structure_evidence/base_manifest.json
  run ${tag_wt#*:} ${tag_wt%%:*} android "$ANDROID" -l kotlin
done
```

Each run writes `<tag>-<name>-<granularity>.json` (nodes, edges, evidence) next to the `.html`, and
`...bottlenecks.json` (candidates, package dependencies, schema).

## 2. Aggregate and diff

```bash
for name in nestjs android; do
  for g in file symbol; do
    echo "######## $name $g"
    python3 $REPO/tests/fact_defects_evidence/review_diff.py \
      $OUT/base-$name-$g.json $OUT/head-$name-$g.json \
      --root $( [ $name = nestjs ] && echo $NEST || echo $ANDROID ) \
      --base-bottlenecks $OUT/base-$name-$g.bottlenecks.json \
      --head-bottlenecks $OUT/head-$name-$g.bottlenecks.json \
      --seed 20261019 --sample 10 | tee $OUT/review-$name-$g.txt
  done
done
```

The script prints: (relation, resolution) count diff; added/removed edge groups by (relation, resolution, confidence);
nodes whose `end_line` / `cost.line_count` changed; schema and key-set diff; candidate kind counts and
new/gone candidates; 10 sampled added edges (seeded) with the cited source line.

## 3. Attribute each change to an F id

Expected causes (use as a checklist, not as proof):

| observed change | allowed F id | how to confirm |
| --- | --- | --- |
| TS edges added/upgraded where the specifier has a dotted last segment (`./x.entity`) | F11 | open importer line; target file name is `<segment>.ts` etc. per R5 |
| TS edges that previously pointed at a wrong file (stem + ext replaced) | F11 | old target differs from R5 target |
| TESTS edges / untested_hub or isolated_node candidate changes in TS | F11 | follows from added test-to-production IMPORTS |
| Kotlin edge ambiguous/unique_name -> exact, target now the FQN match | F7 (R8) | import line FQN equals target `package.qualname` |
| Kotlin reference edge retargeted to the imported symbol | F7 (R10) | importing file contains the import; name equals last import segment |
| Kotlin package dependency tier/direction changes | F7 (R11) | follows from retargeted edges |
| module/file node `end_line` or `line_count` lower by one (or file with form feed / CR / U+2028 etc.) | F8 / F9 | recount `\n` with `wc -l` (+1 if no trailing newline) |
| large_node candidate gone/new at threshold | F8 (R4) | file length vs `edge_weights.large_node_line_threshold` |
| anything else | none: record as finding | -- |

Record every distinct change group below. Do not leave a group without an F id.

| # | project / granularity | change group (relation, resolution or candidate kind, count) | F id | evidence (sample line or recount) | verdict (explained / finding) |
| --- | --- | --- | --- | --- | --- |
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |

Also check that the removed-edge groups are only edges superseded by an added edge (same source, same relation,
better resolution or a corrected target). A removed edge with no counterpart is a finding.

## 4. Sampled edge verification (10 per project/granularity, seed 20261019)

For each sampled edge printed by the script, confirm against the printed source line:

1. the cited line contains the import / reference named by the edge;
2. the target file is the one R5 (TS) or R8/R10 (Kotlin) yields for that text (resolve by hand with `ls`);
3. relation and resolution are plausible for that syntax (static import -> IMPORTS exact; dynamic import -> dynamic_required).

| # | project/granularity | edge (from -> to, relation, resolution) | cited file:line and text | matches (yes/no) |
| --- | --- | --- | --- | --- |
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| 7 | | | | |
| 8 | | | | |
| 9 | | | | |
| 10 | | | | |

If evidence is a file-level aggregate whose cited line does not contain the import (aggregated edges keep one
representative location), re-run that project at `--granularity symbol` and verify the symbol-level edge with the same
endpoints instead; record that substitution in the table.

## 5. Result

- unexplained changes: ___ (expected 0)
- wrong sampled edges: ___ (expected 0)
- schema / key-set differences between base and head: ___ (expected none; script section "bottleneck payload")
- cleanup: `git -C $REPO worktree remove --force $BASE`
