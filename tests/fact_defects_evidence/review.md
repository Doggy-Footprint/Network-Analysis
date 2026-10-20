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

## Results (spec v4, run by main)

Commands: `review-output/run.sh` (the same steps as sections 1–2, using local python3). Raw outputs are in `review-output/review-<fixture>-<granularity>.txt`. The review_diff sample-location printer printed `None:None` for every sample, so main opened the source lines by hand.

| # | project / granularity | change group | F id | evidence | verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | nestjs file | IMPORTS exact +65, IMPORTS_SYMBOL exact +69, RE_EXPORTS exact +4 | F11 | samples [2][4][7][8][9][10]: `user.controller.ts:5` `from './dto'`, `profile.controller.ts:5` `'../user/user.decorator'`, `article.module.ts:2`, `dto/index.ts:1` `export { CreateUserDto } from './create-user.dto'`, `main.ts:2`, `comment.entity.ts:2` | explained |
| 2 | nestjs file | TYPE_USES / INSTANTIATES / READS unique_name·ambiguous → exact (−45 / +45) | F11 | sample [1]: `user.controller.ts:27` `UpdateUserDto`, imported at line 5. Sample [3]: `user.service.ts:8` `UserRO` from `./user.interface` | explained |
| 3 | nestjs file | TESTS exact +3; `src/tag/tag.entity.ts` untested_hub removed | F11 | follows from the spec→production IMPORTS edges | explained |
| 4 | nestjs file | dependency_cycle +1, package_cycle +1, unstable_dependency −1, evidence_spread +1 | F11 | structural results of the newly resolved import edges | explained |
| 5 | nestjs symbol | 18 module nodes with end_line −1 | F8 | each `(end_line, line_count)` goes from (n+1, n) to (n, n) | explained |
| 6 | nestjs symbol | evidence_spread +37, −1 | F11 | evidence_spread counts the evidence sites of references to the target. The newly resolved cross-file references (rows 5a, 5b) add evidence sites, so this follows from the F11 edges alone. The signal definition itself is unchanged. | explained |
| 7 | android file | IMPORTS / IMPORTS_SYMBOL unique_name 102 → exact 103; ambiguous 52 → 38 | F7 (R8) | sample [1]: `TopicDaoTest.kt:19` `import ...core.database.model.TopicEntity`. Sample [4]: `NewsResource.kt:19` `import ...model.NewsResourceEntity`, and the target's `package` matches | explained |
| 8 | android file | READS / TYPE_USES / INSTANTIATES / CALLS / WRITES / IMPLEMENTS / INHERITS / TESTS unique_name → exact | F7 (R10) | samples [2][3][5]–[10] are references from files that import the target | explained |
| 9 | android file | package_cycle +2 (certain) | F7 (R11) | package dependencies are now promoted to the certain tier | explained |
| 10 | android symbol | module end_line −1 (all files) | F8 | as in #5 | explained |
| 11 | android symbol | evidence_spread −1 | F7 | a reference was retargeted to the imported symbol | explained |
| — | both / both | schema and key set | — | no change | explained |

Unexplained changes: 0. Wrong edges among the 10+10 samples: 0.

### Verifier 1 follow-up (VF1-2): edge groups at symbol granularity, sampled source lines, removed-edge counterparts

The full output is `review-output/sample-check.txt`, written by `review-output/sample_check.py` (seed 20261019; `run.sh` runs it last).
- File-granularity edges carry `evidence: null`, so the helper takes the first `details.edges` entry from `metadata.detail_edge_indices`.
- An edge is "plausible" when one of these holds:
  - An import or export line names the target file or symbol.
  - A reference line names the target symbol, or a symbol defined in the target file.
  - The edge is TESTS, which is derived from an underlying edge.

| # | project / granularity | change group | F id | evidence | verdict |
| --- | --- | --- | --- | --- | --- |
| 5a | nestjs symbol | IMPORTS exact +65, IMPORTS_SYMBOL exact +74, RE_EXPORTS exact +4 | F11 | samples [2], [4]–[9] are import lines that name the target (`profile.service.ts:7` `from "./follows.entity"`, etc.) | explained |
| 5b | nestjs symbol | TYPE_USES / INSTANTIATES / READS exact +79, unique_name·ambiguous −79; TESTS exact +6 | F11 | samples [1] `author: UserEntity;`, [3] `Repository<TagEntity>`, [10] `tagService: TagService`. Removed edges without a counterpart at the same (source, relation, line): 0 | explained |
| 10a | android symbol | IMPORTS / IMPORTS_SYMBOL exact +215; unique_name −211 | F7 (R8) | sample [4][5] import lines name the target FQN | explained |
| 10b | android symbol | IMPORTS / IMPORTS_SYMBOL / TESTS ambiguous +20, −30 | F7 (R9) | when several symbols share the FQN (`core.data.model.asExternalModel` is defined in several files of one package), the candidates narrow to the FQN matches, and the old candidates in other packages disappear | explained |
| 10c | android symbol | READS / TYPE_USES / INSTANTIATES / CALLS / WRITES / IMPLEMENTS / INHERITS / TESTS exact +583, unique_name·ambiguous −583 | F7 (R10) | samples [1][2][6][7][8] name the imported symbol | explained |
| 10d | android symbol | 2 removed IMPORTS unique_name edges without an added edge at the same line | F7 (R8) + existing merge by key | `OfflineFirstNewsRepository.kt:22-23` imports `topicCrossReferences` and `topicEntityShells`, both defined in `core/data/model/NewsResource.kt`. Both now resolve exact to the same file and merge into one edge, `exact, line 22, weight 2` (base: ambiguous line 22 + unique_name line 23). The same holds for `OfflineFirstNewsRepositoryTest.kt` | explained |
| 7a | android file | 33 removed projected IMPORTS / IMPORTS_SYMBOL edges without an added edge at the same line | F7 (R9) | e.g. `DefaultRecentSearchRepository.kt:20` `import ...core.data.model.asExternalModel`. The base candidates spanned `core/database/model/*`; now only the FQN matches in `core.data.model` remain, so the file-level projections to the other files disappear | explained |
| 7b | nestjs file | 47 removed edges | F11 | every removed edge has an added counterpart at the same (source, relation, line) | explained |

Sample source-line check (40 sampled added edges):

| set | sampled | plausible | not plausible | cause of "not plausible" | wrong edge |
| --- | --- | --- | --- | --- | --- |
| nestjs file | 10 | 10 | 0 | — | 0 |
| nestjs symbol | 10 | 10 | 0 | — | 0 |
| android file | 10 | 6 | 4 | [3][10] TYPE_USES with the evidence at the class start line `@Database(`, whose `entities = [...]` names the targets; base uses the same line for the same edge. [4] `import ...model.topicCrossReferences` names a function defined in the target `NewsResource.kt:53` (helper heuristic matches file stems only). [9] the evidence line is the blank line before `import ...model.TopicEntity` (line 19). base records the same line 18 (pre-existing Kotlin import line defect, out of scope; recorded for handoff) | 0 |
| android symbol | 10 | 9 | 1 | [9] TYPE_USES with the evidence at the function start line `@Binds`; the next line names the parameter type `CompositeUserNewsResourceRepository`; base has the same edge on line 29 as unique_name | 0 |

Removed-edge counterpart check: every removed edge has an added edge at the same (source, relation, evidence line), except for 10d and 7a, which the rows above explain.

Unexplained changes: 0. Wrong edges: 0. One pre-existing defect is out of scope for this run: Kotlin import evidence lines are one too small when a blank line precedes the import, because `^\s*import` matches across newlines.
