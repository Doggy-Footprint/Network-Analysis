# Base manifest regeneration (workflow run e91abc221d7deb2a, signal defects round 3)

The characterization manifests of earlier runs pin CLI outputs of their own base commit. This run changes analyzer
and bottleneck output (external vs unresolved call classification in Python/TypeScript/Kotlin, Kotlin member
exclusion and import regex, `unresolved_reference_total`, `external_call_count`, PageRank residual distribution,
token-based `large_node`, self-file evidence excluded from `evidence_spread`, ownership edges excluded from symbol
`evidence_spread`, `versions.analysis` "4" -> "5"). Each manifest was rebuilt from its base commit with the earlier
runs' code fixes plus this run's code fixes applied.

## Patches

- `patch-old`: `git diff b590d54..cf0cf44` restricted to non-test code (9 files: `core/cost.py`,
  `core/enrichment.py`, `kotlin/analyzer.py`, `kotlin/ast.py`, `python/graph.py`, `python/symbols.py`,
  `typescript/analyzer.py`, `typescript/ast.py`, `repository/models.py`). The committed manifests already contained
  these changes (`tests/fact_defects_evidence/manifest-regeneration.md`).
- `patch-r3`: `cf0cf44..<working tree>` restricted to code: `analysis/edge_weights.py`, `analysis/file_graph.py`,
  `analysis/graph_metrics.py`, `bottlenecks/core.py`, `core/flags.py`, `kotlin/analyzer.py`, `kotlin/ast.py`,
  `python/graph.py`, `typescript/analyzer.py`, `profiles/edge_weights.v1.yaml`, `report/bottlenecks/generate.py`
  (Korean description strings in the HTML renderer only; no JSON effect). Before the test run,
  `git diff cf0cf44 -- language_analyzers analysis bottlenecks profiles` of the main tree had the same `+`/`-` lines
  as `patch-r3`, and `git diff --stat -- language_analyzers analysis bottlenecks` was empty.

## Common procedure

- Worktree: `git worktree add --detach <dir> <base_commit>`, `git apply -3 patch-old`, conflicts resolved by hand,
  then `git apply -3 patch-r3`, conflicts resolved by hand. Patches stay uncommitted, so `HEAD == base_commit`.
- After `patch-old`, the `+`/`-` lines of `git diff --cached HEAD` equal the patch's in all five worktrees.
  Conflict in `kotlin/analyzer.py` for ef8adb3, 2627174 and 6fda6d5 (`self._import_statements` does not exist
  there): resolved as in the fact-defects run, keeping only the added `self._file_package` / `self._exact_imports`
  fields.
- After `patch-r3`, the `+`/`-` lines of `diff -u <old-patched> <r3-patched>` were compared with `patch-r3` per file.
  Only the deviations listed under "Per manifest" remain.
- Generators: `regen_manifest.py` (architecture_rules, delta, external_rules, structure), recreated from the code in
  `tests/fact_defects_evidence/manifest-regeneration.md` with a `main()` that loads the committed manifest as the
  skeleton and writes `json.dumps(indent=2, ensure_ascii=False)` with the original trailing-newline convention; and
  the committed `tests/reach_evidence/make_base_manifest.py`. CLI runs use `cwd=<worktree>`, `PYTHONHASHSEED=0`, and
  the current repo's fixtures. `base_commit` fields are unchanged.
- Reproduction check: each generator run on the old-patched worktree (before `patch-r3`) reproduced the committed
  manifest byte for byte, all five including external_rules (its `architecture_bytes` already use the current
  fixture path since the fact-defects regeneration).

## Hunk adaptations common to all five base commits

All five base commits predate b590d54 (`untested_hub_top_n`, optional edge-weight keys).

- `analysis/edge_weights.py`: `_OPTIONAL_KEYS` line skipped (the optional-key mechanism does not exist; the old loader
  requires the exact key set `_KEYS`). Kept: `DEFAULT_LARGE_NODE_TOKEN_THRESHOLD = 24000`, the
  `large_node_token_threshold` dataclass field, its `document.get(..., default)` read and validation, and the
  constructor argument. The `untested_hub_top_n` context lines were not added.
- `profiles/edge_weights.v1.yaml`: hunk skipped. The old loader rejects any key outside `_KEYS`; the skipped value
  (24000) equals the default, so `weights.large_node_token_threshold` is 24000 either way.
- `bottlenecks/core.py` `_weights`: added only the `large_node_token_threshold` check (no `untested_hub_top_n` check).
- `bottlenecks/core.py` final `return`: `{"analysis": "4"}` -> `"5"` applied to the base commit's own line (which
  lacks `package_dependencies` / `ArchitectureRulesError` before f5ab529/6444895, and returns `bottlenecks.v7` at
  6fda6d5).
- `bottlenecks/core.py` edge-weights payload: `"large_node_token_threshold"` added after
  `large_node_line_threshold` (the `if is_file: payload["untested_hub_top_n"]` lines not added) for reach and
  structure. For architecture_rules, delta and external_rules the payload key was NOT added, see below.

## Per manifest

| manifest | base commit | reproduction (old-patched) | patch-r3 conflicts |
|---|---|---|---|
| `tests/architecture_rules_evidence/base_manifest.json` | ef8adb352c32936b102ed06d8dcb3ad2f28e6bdd | byte-equal | edge_weights.py, yaml, core.py, file_graph.py, kotlin/analyzer.py |
| `tests/delta_evidence/base_manifest.json` | f5ab529bd2cdd8a084d66e2759d172fc3579cfd5 | byte-equal | edge_weights.py, yaml, core.py |
| `tests/external_rules_evidence/base_manifest.json` | 2627174d8a454a427965b5becee666c295454435 | byte-equal | edge_weights.py, yaml, core.py, file_graph.py, kotlin/analyzer.py |
| `tests/reach_evidence/base_manifest.json` | 6444895451a89f4450b9123b7beb17b11506e534 | byte-equal | edge_weights.py, yaml, core.py |
| `tests/structure_evidence/base_manifest.json` | 6fda6d5a91eee508088292ad8b428694ee70b32f | byte-equal | edge_weights.py, yaml, core.py (also the candidates/payload block), file_graph.py, kotlin/analyzer.py |

f5ab529 and 6444895: only the common adaptations. All other `patch-r3` hunks applied with identical `+`/`-` lines.

ef8adb3, 2627174 and 6fda6d5 predate f5ab529 (external imports: `external_records`, `normalize_external_imports`,
`kotlin_is_internal`, `PythonModuleIndex`, `_record_external_imports`, `_import_statements`). Additional adaptations:

- `analysis/file_graph.py`: `external_records` lines skipped (feature absent; no output there). Kept
  `external_calls` with its accumulation from `node_metadata` and a new `for file_node in output_nodes:` loop setting
  `metadata["external_call_count"]`, so file-granularity nodes carry `external_call_count` as in `patch-r3`.
- `kotlin/analyzer.py`: the `_record_external_imports` hunk only adds the `self._project_imports[key] = ...` line, and
  the call classification `if target is None and name not in self._project_imports...` depends on it. Added
  `_record_project_imports()` (same `packages` expression; iterates `self._imports`; inline
  `any(raw == package or raw.startswith(package + ".") or package.startswith(raw + ".") ...)`, the body of
  `kotlin_is_internal` at cf0cf44), called after the file loop where cf0cf44 calls `_record_external_imports()`.
  `self._imports` is used because, after `patch-r3` changes its regex to `^[^\S\n]*import\s+([\w.*]+)`, it has the same
  regex and line formula as `_import_statements` at cf0cf44. No `external_imports` metadata is emitted.
- `python/graph.py`: `_is_boundary_call` calls `self._module_index.is_internal`, which does not exist before f5ab529.
  Added `PythonModuleIndex` (verbatim from `language_analyzers/core/external_imports.py` at cf0cf44, placed in
  `python/graph.py`, `Iterable` added to the typing import) and the `self._module_index = PythonModuleIndex(...)`
  construction verbatim from cf0cf44 `build()`. `getattr(self, "_unparsed_modules", [])` is `[]` at these commits.
- 6fda6d5 `bottlenecks/core.py`: the block that at later commits adds structure/reach candidates does not exist; the
  `_file_candidates` / `_candidates` call got the `large_node_token_threshold, metrics` arguments.

### Edge-weights payload key for architecture_rules, delta, external_rules

`tests/delta_support.py::base_form_bytes` (used by `test_V07_no_rules_byte_equal_to_base`,
`test_V11_bottleneck_json_byte_equal_to_base`, `test_V14_bottleneck_size_ratio_realworld`) and
`tests/test_delta_integration.py` (`test_V06_C27_...`) pop `edge_weights.large_node_token_threshold` (with
`untested_hub_top_n`) from the current output before comparing it with the base bytes. With the key added to the
base payload, all 16 of those comparisons were exactly 35 bytes short (`"large_node_token_threshold":24000,`). These
three manifests were therefore generated without the payload key. `tests/reach_support.py::without_reach` does not
pop it and `test_V08_symbol_mode_is_byte_identical_to_base` compares raw bytes, so reach and structure keep it.

## Entries changed (committed -> regenerated)

- architecture_rules (file bytes + sha256): android-nowinandroid 7803572 -> 5200039; fastapi-realworld 943448 ->
  782266; futuramaapi 2134318 -> 1632809; typescript-nestjs-realworld 725096 -> 559719.
- delta (bottleneck_bytes + sha256): futuramaapi 2134318 -> 1632809; fastapi-realworld 943448 -> 782266;
  fastapi-official-template 490343 -> 354930; android-nowinandroid 7803572 -> 5200039; typescript-nestjs-realworld
  (`-l typescript`) 678170 -> 529311; fastapi-realworld+rules 948864 -> 787682.
- external_rules (all architecture canonical hashes and bottleneck hashes changed): android-nowinandroid file
  architecture_bytes 8832368 -> 7359757, bottleneck_bytes 7803572 -> 5200039; fastapi-official-template file
  1475804 -> 1303503, 490343 -> 354930; fastapi-realworld file 3004525 -> 2851724, 943448 -> 782266, symbol
  2649377 -> 2504202; futuramaapi file 6794814 -> 6397487, 2134318 -> 1632809; typescript-nestjs-realworld file
  1465756 -> 1413409, 725096 -> 559719, symbol 1279736 -> 1229393.
- reach: every fixture changes in `bytes`, `sha256`, `canonical` and sections `candidates`, `dependency_network`,
  `edge_weights`, `versions`. android-nowinandroid file 7813747 -> 5210249, candidate_count 108 -> 67, symbol
  6641877 -> 4290069, 489 -> 218 (`unresolved_boundary` gone from `candidate_kinds` in both); fastapi-realworld file
  951189 -> 790042, 120 -> 68, symbol 535904 -> 362814, 335 -> 98 (`unresolved_boundary` gone in both); futuramaapi
  file 2170810 -> 1669336, 278 -> 169, symbol 1435879 -> 994640, 677 -> 200; typescript-nestjs-realworld file
  729707 -> 564365, 71 -> 46, symbol 568427 -> 436952, 210 -> 103. delta: `canonical` and sections `candidates`,
  `dependency_network`, `edge_weights`, `versions` changed; the `delta` hash is unchanged.
- structure (file: bytes, sha256, candidate_count, candidates, node_metrics, rankings, rankings_by_category; symbol:
  bytes, sha256): android-nowinandroid file 7430385 -> 4832704, 87 -> 46, symbol 6641877 -> 4290069;
  fastapi-realworld file 851949 -> 690802, 94 -> 42, symbol 535904 -> 362814; futuramaapi file 1726473 -> 1224999,
  192 -> 83 (`candidate_groups` also changed), symbol 1435879 -> 994640; typescript-nestjs-realworld file 645354 ->
  480012, 54 -> 29, symbol 568427 -> 436952. `candidate_groups` is unchanged for the other three fixtures.

## Test outcome

`pytest tests/test_architecture_rules_integration.py tests/test_delta_integration.py tests/test_external_rules_integration.py tests/test_reach_candidates.py tests/test_structure_integration.py`:
`5 failed, 345 passed, 2 deselected`. All failures are in `tests/test_structure_integration.py`:

- `test_V08_file_mode_keeps_base_parts_and_adds_v8_fields[*]` (4 fixtures): `assert payload['versions']['analysis']
  == '4'` fails on `'5'`, which this run sets in `bottlenecks/core.py`. Run separately, the remaining assertions of
  that test (rankings, rankings_by_category, node_metrics, candidate_groups, base candidate count and hash) match the
  regenerated manifest for all four fixtures.
- `test_V11_size_ratio_per_fixture[futuramaapi]`: ratio 1.334 > 1.25. The bytes structure adds on top of the base
  are 407845 both before (2134318 - 1726473) and after (1632809 + 35 - 1224999) regeneration; the ratio rose because
  this run removed about 500 KB of `unresolved_boundary` candidates from the base output.
