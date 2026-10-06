# Spec v2 review procedure

Status: main source review and small scan/cache observations completed; full suite/real-repository equivalence remains separate evidence. Reviewer: main, approved spec v1, base 7eb255b0d552771c01e11fc2b4475663815c9567. Exact source SHA256 values are in scan-cache-review.json.

| Obligation | Inputs | Observation | Independent expected result | Repeatable artifact |
| --- | --- | --- | --- | --- |
| V02 / Q04 | frozen baseline snapshot, small case/Unicode/string/comment/boundary/nonidentifier/nested/duplicates/ambiguous-order fixtures, optimized symbol run | main's public scan/cache instrumentation and source inspection | general identifier positions indexed per file; scope lookup reuses index; nonidentifier scan at most once/file/name; preserved order, count and first location | append exact instrumentation command, labelled count rows, inspected symbols and source locations; compare baseline-small-relations.json and optimized-small-relations.json |
| V01 / Q04 | CLI seven singleton variants and three exclusions; four direct builder variants | GraphAnalyzer public call trace in test_file_analysis_cli.py | selected final graph analyzed once; file symbol metric calls zero; direct API retains calculation; excluded extraction zero | full pytest result plus per-variant call trace if a failure occurs |
| V15 shared-converter | main's seven CLI paths, common converter module | main follows each selected extraction result to conversion | one common conversion path, zero adapter-specific file aggregation | append seven path/symbol chains, exact revision, reviewer and observed verdict |
| V15 README | final README | main checks declared examples/descriptions | default file example, explicit symbol example, whole-file cost, file candidate unit, file path does not imply function call chain | append five exact README line references, exact revision, reviewer and observed verdict |

Proposed distinct mutation classes: sum effective pair weights instead of maximum (V03 mixed-key assertion); sum overlapping symbol cost instead of whole text once (V05 tokenizer and duplicate invariance assertions); omit original candidates or evidence during aggregation (V03 full raw relation/order assertion and V06 spread evidence assertion). Main selects and injects mutations; this procedure does not mutate Implementation.

## Main observations

Repeat `.venv/bin/python tests/file_analysis_evidence/scan-cache-review.py`. It wraps public `re.finditer`, identifies complete raw/normalized fixture text by SHA256, compares the full small Kotlin/TESTS serialization to the immutable baseline, and checks lookup/line/range reuse and public dictionary independence. Result: exit0, 12 labelled scans, maximum 1 scan per complete text/pattern, raw relation difference 0. The JSON artifact contains each pattern, input path, hash and count. Initial attempt used an incorrect repository-root calculation and failed importing `tests`; root was corrected before any observations were recorded.

| Check | Inspected input / procedure | Observed result |
| --- | --- | --- |
| V02/Q04 general and nonidentifier names | `language_analyzers/core/positions.py:6` constructor and `matches`; `language_analyzers/kotlin/analyzer.py:261`; `language_analyzers/core/enrichment.py:128`; repeat scan-cache-review.py | One general word index per file text; fallback full regex cached per text/name; sorted range positions queried by bisect; symbol body/header retain relative boundary handling and original iteration order. No per-symbol complete text scan for general names. |
| V02/Q04 source coordinates | Kotlin byte start map and decoded span lookup at analyzer.py:266; TESTS normalized lines/ranges at enrichment.py:140 | Kotlin decoded original text index is mapped from AST bytes; TESTS separately indexes newline-joined splitlines text. Original first evidence line is preserved by indexed newline offsets and baseline equality. |
| V02/Q04 source reuse | `repository/models.py:7` SourceText; snapshot source_map/source_lines at :55; `language_analyzers/core/cost.py:49`; repeat scan-cache-review.py | Internal readonly map, line tuples and identical range cache reused within snapshot; public content_map returns independent original-value dictionary. No cross-snapshot cache. |
| V01/Q04 final calculation | `code_analyzer/cli.py:383` through :404; four framework builders' compute_metrics guards | All selected extractions precede integration and unit conversion. CLI builders receive False; GraphAnalyzer is called on selected final graph once, reused by bottlenecks and output. Direct builder defaults remain True. Dynamic call counts belong to pytest evidence. |

Shared-converter paths inspected from each selected `_run_analyzer` result, optional `_run_merged`, and the single `main` conversion at code_analyzer/cli.py:398:

| Selected analyzer | Extraction chain | File conversion |
| --- | --- | --- |
| Python | PythonGraphAnalyzer.analyze | analysis.file_graph.to_file_architecture |
| TypeScript/JavaScript | TypeScriptAnalyzer.analyze | analysis.file_graph.to_file_architecture |
| Kotlin | KotlinAnalyzer.analyze | analysis.file_graph.to_file_architecture |
| FastAPI | FastAPIAnalyzer.analyze → ArchitectureGraphBuilder.build_graph | analysis.file_graph.to_file_architecture |
| Android | AndroidAnalyzer.analyze → AndroidArchitectureGraphBuilder.build_graph | analysis.file_graph.to_file_architecture |
| SQLAlchemy | SQLAlchemyAnalyzer.analyze → SQLAlchemyGraphBuilder.build_graph | analysis.file_graph.to_file_architecture |
| NestJS | NestJSAnalyzer.analyze → NestJSGraphBuilder.build_graph | analysis.file_graph.to_file_architecture |

Search `rg -n 'to_file_architecture|file-aggregation|granularity' code_analyzer analysis framework_analyzers language_analyzers`; follow the seven selected branches in CLI. Observed common conversion module count 1; adapter-specific aggregation count 0. Language/framework extraction still emits original relations, including metadata/details and uncertain connections. Conversion applies provenance plus declaration kinds to distinguish ownership from real framework dependencies.

README review (repeat `nl -ba README.md`; SHA256 pinned in scan-cache-review.json):

| Required item | Location | Observation |
| --- | --- | --- |
| default-file-example | README.md:18 and :23 | Default command and default file unit described. |
| explicit-symbol-example | README.md:26 | Explicit --granularity symbol example. |
| file-cost | README.md:108 | Whole snapshot text once, boundary cost0, original discounts and symbol overlap distinction. |
| candidate-unit | README.md:114 | One file/kind candidate, all detailed evidence, whole-file large threshold. |
| path-limitation | README.md:172; app.js file detail notice | File paths do not establish a function-call chain; original symbols/evidence must be inspected. |

Source-derived FastAPI baseline observation for independent Tests oracles: load original HEAD analyzer.py and graph.py in isolated modules via `git show HEAD:<path>`, execute against Tests PROJECT_FILES, serialize publicly. get_user/create_user DEPENDS_ON target dep_main_get_db; framework schema_main_UserOut and dep_main_get_db are distinct from language py:main#UserOut and py:main#get_db. Both baseline probes exit0; production code was not replaced.

## Correction batch 1 review

First real extraction retained every raw relation but the file3-run median was220.802s, above180s. The remaining symbol×repository-name loops were diagnosed from source and a one-second native sample. Ordered range-token candidate selection replaced absent-name lookups; candidates are sorted by the original name insertion rank, with clipped boundary tokens and cached nonidentifier matches retained. TESTS now reuses SourceText.lines. Repeat scan-cache-review.py after this revision: still12complete-text scans, each1, exact small baseline equality and source/dictionary/cache assertions pass. Current SHA256 values are pinned in scan-cache-review.json; attempt1 contains earlier measurement evidence.

CLI schema5 compatibility review: historical stats.node_metrics had no identifier counts while node metadata and bottleneck metrics did; single Python+bottlenecks historically omitted stats.analysis. Detached stats preserve those observable structures while a single final GraphAnalyzer result supplies metadata/report metrics. The comment records this otherwise invisible legacy constraint. Byte-characterization checks retain their immutable hashes and explicitly select symbol mode.

Two focused browser tests for V10/V14 passed after approved folded selectors and public layout.stop observation corrections. This checks the same completion boundary as layoutstop followed by two frames; the constructor root layoutstop option was not supported. Full regression and mandatory real-dataset timing remain the separate Test command evidence.

## Current v2 review (supersedes historical v1 single-pass statements)

Approved A07 applies the one final/shared GraphAnalyzer requirement exclusively to file CLI. Symbol CLI deliberately retains the original adapter/standalone-language/merged/bottleneck calculation schedule, including source-less fallback metadata costs; original directAPI defaults remain unchanged. Main inspected the seven branches, four compute_metrics mode guards, merged symbol guard and final file-only calculation in code_analyzer/cli.py. File still uses the single common conversion module and no symbol metrics before conversion; symbol original byte baselines remain immutable.

The default APIs were also observed independently from original commit7eb255b0d552771c01e11fc2b4475663815c9567 in an isolated git-archive checkout, using the exact V01 FILES fixture (SHA467ab5757141843e0f822b25078e251a7057251019f5011c1e738b080995ebd3). Four default builders, their serialized state after default analyze_bottlenecks, and full default reports matched current values. Original public outputs are direct-api-original.json and provenance/results direct-api-review.json. Freeze the first serialization before calling bottlenecks, which mutates metadata. Paths alone are normalized to <PROJECT_ROOT>, including macOS /tmp→/private/tmp alias. Tests independently compare all three stages against these frozen original observations with an input-hash guard. Initial test setup accidentally called build_snapshot without relative_paths; the test was corrected to the exact original manually frozen snapshot helper; focused4 tests passed. Repeat evidence through Test command V01 direct-builder variants; reconstruct original via git archive of the pinned commit and the named FILES fixture if recapture is needed, never refresh golden on a test failure.

A04 valid-source defect was independently reproduced from Python `value = "a\u2028b"` (13characters, no terminalLF): original symbol spans1..1, generated whole-file span1..2, required file line count2. Legacy LF validation previously rejected that file; file validator now uses cached splitlines counts, and symbol LF/terminal-LF validation remains unchanged. Main inspected bottlenecks/core.py's granularity guard. Tests V05 whole-text independently assert cost4tokens/13chars/2lines, original span preservation and successful v5 report. Focused5 tests (V05 + four directAPI cases) pass. This is an implementation/evidence correction under unchanged v2 A04, not a new expected behavior or matrix.

Repeat scan-cache-review.py after the final source revision:12whole-text scans, each1; exact small Kotlin/TESTS equality, source/line/range reuse and independent content_map pass. The artifact is now tagged v2 and includes current CLI/GraphAnalyzer/bottleneck/converter/cache/README hashes. Full current-revision suite and independent audit/mutations remain separate obligations; no draft map or earlier suite acceptance is inherited.

## Current executed evidence

Full exact Test command on correction5/v2: pytest-run5.log, exit0,1041passed/200subtests/652.82s, mandatory skips0. Benchmark file74.796/74.978/75.198s, median74.978≤180; original1238.087s; complete original raw relations equal and both browser datasets pass. Source/test SHA256 revision: execution-revision.json; repeatable review and original directAPI artifacts above. Historical failed measurements remain attempt1–attempt4. All16 obligations pending verifier1; no prior acceptance is inherited. Shared validator impact and full rerun recorded in spec R12/coverage correction_batch_5.

## Audit1 evidence correction impact

Verifier1 audits all16/151declared items,12accepted and3blocking classes (V06,V08,V09/V10), no spec challenge. Correction6/7 change only existing Tests scenarios; common browser/performance helpers and all Implementation remain unchanged. Original public CLI Mermaid stdout and architecture are separately captured from pinned originalHEAD/sameFILES; CLI excludes.env whereas explicit directAPI snapshot includes it. New source and stdout hashes are mermaid-original-provenance.json, not current-output goldens. Focused36other assertions plus correctedV08two modes pass; fullsuite6 underway. Strongest3 confirming classes are those current gaps, with corresponding intended assertions; prior max-weight/wholecost assertions remain accepted supplementary evidence.
