---
version: 2
run_id: cfa172d091b48e63
status: complete
base_commit: e0d6eff58e970e14dd265edd55c07d68e5e8c299
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| U01 | report reader | analysis-coverage-reporting handoff를 작업해줘 | See observed analysis gaps alongside the dependency report. |
| U02 | maintainer | Implement the plan. | Implement the approved coverage plan without changing extraction or metrics. |

# Scope
In scope: Python, TypeScript/JavaScript, Kotlin, FastAPI, Android, SQLAlchemy, NestJS snapshot-based analysis; CLI integration; file/symbol JSON; unified offline HTML; observed parse results and existing NestJS diagnostics.
Out of scope: new unsupported-pattern detection, new inventory exploration, extraction changes, graph/metric changes, no-snapshot coverage guarantees, new CLI switches.

# Paths
Implementation: repository/scan.py, language_analyzers/core/analysis_coverage.py, language_analyzers/python/source.py, language_analyzers/python/graph.py, language_analyzers/typescript/analyzer.py, language_analyzers/kotlin/analyzer.py, framework_analyzers/fastapi/analyzer.py, framework_analyzers/fastapi/graph.py, framework_analyzers/android/analyzer.py, framework_analyzers/android/graph.py, framework_analyzers/sqlalchemy/analyzer.py, framework_analyzers/sqlalchemy/graph.py, framework_analyzers/nestjs/analyzer.py, framework_analyzers/nestjs/graph.py, code_analyzer/cli.py, bottlenecks/core.py, report/bottlenecks/generate.py, renderers/html/static/app.js, renderers/html/static/styles.css, renderers/html/templates/dashboard.html
Tests: tests/, scripts/coverage_reporting_checks.py
Test command: /private/tmp/network-analysis-coverage-venv/bin/python scripts/coverage_reporting_checks.py
Review evidence: tests/coverage_reporting_evidence/{coverage.json,regression.json,browser.json,performance.json,verifier-1.md,mutations.json}; automated independent assertions and before/after characterization, main records verifier/mutation results. Baselines at /private/tmp/network-analysis-coverage-baseline.json and /private/tmp/network-analysis-coverage-baseline-runner.py, captured by main before implementation; immutable inputs/expected results. Preserve previous evidence baselines.

# Signatures
`language_analyzers.core.analysis_coverage.build_analysis_coverage(snapshot: RepositorySnapshot, reports: Sequence[Mapping[str, Any]]) -> dict`
`language_analyzers.core.analysis_coverage.analysis_report(analyzer_id: str, results: Sequence[Mapping[str, Any]]) -> dict`
`architecture.stats["analysis_coverage"]: dict` when snapshot-based analyzer reporting exists; absent for no-snapshot execution.
`analyzer.analysis_coverage: dict` for source/build-only APIs (including PythonSourceAnalyzer and KotlinAnalyzer.build), absent or empty for no-snapshot execution.

Producer report: `{analyzer_id, results: [{file_path, status, reasons: [{code, message, span?}]}]}`. Producer status is complete/partial/failed/skipped; no rows for unrelated extensions. Analyzer ids: python-core, typescript-core, kotlin-core, fastapi, android, sqlalchemy, nestjs. Implicit stages use the same id as explicit stages. No synthetic disabled stage.

Common coverage: `{version: 1, scope: {ignore_source, unlisted_files: "not_enumerated"}, summary: {inventory_file_count, collected_file_count, excluded_file_count, targeted_file_count, complete_file_count, partial_file_count, failed_file_count, skipped_file_count, not_targeted_file_count}, analyzers: [{analyzer_id, summary: {complete_file_count, partial_file_count, failed_file_count, skipped_file_count, targeted_file_count}}], files: [{file_path, status, reasons, results: [{analyzer_id, status, reasons}]}]}`. All summary keys present even for zero; analyzers sorted by id, files by repository-relative POSIX path. Reasons deduplicated deterministically by code/message/span. Optional span uses existing SourceSpan wire shape. Exclusion reasons use the existing reason code and a nonempty descriptive message. Aggregated files preserve reasons from every producer.

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F01 | Report observed results at existing parse/extraction points, without extra source reads/parses. Complete means the selected procedure finished without observed parse recovery or existing semantic diagnostics, not exhaustive relationship extraction. Empty/no-declaration valid files complete. | must | approved plan |
| F02 | Python parse exceptions already caught become failed with syntax_error reason; NestJS error AST remains skipped by extraction and is reported failed/syntax_error; TypeScript/Kotlin/Android error AST remains processed and is reported partial/syntax_error. Normal parses complete. Existing NestJS unsupported_expression, unresolved_reference, ambiguous_reference, bootstrap_unresolved make its file partial with original code/reason/span. Do not promote dynamic graph flags, unresolved graph boundaries or matcher counters to new diagnostics. | must | observed gaps choice |
| F03 | Preserve all scanner exclusion codes and precedence. CLI retains original inventory output paths as excluded/explicit_output without reading them, and does not add nonexistent/new output paths. Inventory source and not-enumerated limitation retained. Recognized extension excluded by the existing analyzer discovery rule is skipped/analyzer_excluded; unrelated extensions have no producer row. | must | approved plan |
| F04 | Merge by file and analyzer id; repeated actual stages do not double count. All complete => complete; any partial or complete mixed with failed/skipped => partial; failed with only failed/skipped => failed; all skipped => skipped. File with no results => not_targeted; scanner exclusions => excluded and no producer results. Apply the same merge rule within repeated producer results and across distinct analyzers. collected=complete+partial+failed+skipped+not_targeted; targeted=complete+partial+failed+skipped; inventory=collected+excluded. Preserve all distinct reasons. | must | file+analyzer choice |
| F05 | Propagate actual implicit language reporting even when a builder uses build() or suppresses duplicate language graph emission. --no-language-graph adds no implicit language stage; explicit selections still report. Builders/merge must preserve reporting despite stats replacement. File conversion retains the same common coverage. snapshot-based direct API returns coverage; no-snapshot API reports unavailable. Common accumulator can combine standalone common coverage values without losing producer identity. | must | API choice |
| F06 | Add identical common values at architecture.stats.analysis_coverage and bottlenecks.coverage.analysis_coverage. Keep architecture 5/6, bottlenecks.v4/v5, existing source_file_count semantics and all other fields. No coverage fabricated for legacy duck-typed architecture without reports. JSON-only regeneration and HTML payload preserve new fields. Old JSON remains valid and displays coverage unavailable. | must | additive compatibility choice |
| F07 | HTML summary shows six status counts, collected/targeted/inventory counts and scope limitation. Dedicated disclosure shows all files with path/status/producer/reason, path and reason search, status and analyzer filters, 50 rows/page with previous/next and empty-result indication. Analyzer filter includes files with that producer; excluded/not_targeted appear under all-analyzers. Build row DOM lazily and bound it to 50 file rows. Keep snapshot-free and legacy report capability messaging. | must | UI choice/delegation |
| F08 | Existing nodes/edges/evidence, metrics, candidates, graph details, CLI selection/error behavior, file/symbol modes and output exclusions stay identical except coverage additions. Existing fatal errors keep their signal and stop result generation. | must | approved plan |

# Errors
E01 existing parse failure — failed file result and reason, other files continue; extraction handling unchanged.
E02 existing recoverable error AST — partial result and reason, original recovered extraction continues.
E03 existing fatal scanner/analyzer/CLI error — original exception/exit and output behavior; no new broad recovery.
E04 absent reporting in old/no-snapshot payload — visible coverage unavailable; existing report works.
E05 empty inventory or filter result — zero counts/no matches, no divide-by-zero or fabricated success.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C01 | normal | valid declaration, empty source, valid no declarations for seven standalone analyzers | complete independently of graph node presence |
| C02 | error | invalid Python/FastAPI/SQLAlchemy/NestJS source | failed/syntax_error, remaining valid file completes |
| C03 | error | TypeScript/Kotlin/Android recoverable error AST | partial/syntax_error; graph extraction unchanged |
| C04 | edge | four NestJS semantic diagnostic classes | partial with code/message/span |
| C05 | boundary | too_large at max and max+1; every current exclusion code; existing vs new output path | same scan decisions, reasons reported, output never read |
| C06 | edge | recognized-but-discovery-excluded vs unrelated extension; empty inventory | skipped vs not_targeted, zero-safe |
| C07 | normal | all aggregation combinations defined in F04, duplicate same producer and shuffled inputs | correct unique counts, deterministic reasons/order |
| C08 | normal | fastapi+sqlalchemy, nestjs+typescript, android+kotlin with --no-language-graph; each file/symbol | preserved producer identity, deduplication and data flow |
| C09 | edge | four framework --no-language-graph, explicit python+sqlalchemy with --no-language-graph | actual stages only |
| C10 | normal | direct snapshot source/build/analyze+builder+bottleneck and CLI JSON exports | common reporting available and identical payloads |
| C11 | edge | legacy/no-snapshot, architecture-only, bottlenecks-only regenerated HTML | compatibility and honest unavailable reporting |
| C12 | error | hostile path/reason strings and existing fatal read/analyzer signal | literal safe display / unchanged fatal behavior |
| C13 | boundary | 0, 1, 50, 51, 10000 file rows, 7 producers per file | correct lazy pages, filter resets, timing thresholds |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | accurate file and producer accounting |
| Performance efficiency | yes | added reporting and UI preserve existing performance, no duplicate parsing |
| Compatibility | yes | additive schemas and extraction invariance |
| Interaction capability | yes | readable searchable offline report |
| Reliability | yes | partial/failure reporting and legacy behavior |
| Security | yes | untrusted path and diagnostic strings in HTML |
| Maintainability | yes | single shared accounting implementation |
| Flexibility | no | deployment/platform expansion excluded |
| Safety | no | report is structural evidence, no safety-critical action |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | Functional suitability / correctness | finite Cases and summary conservation | independent fixture expected states/counts, discrepancies in rows/counts | =0 discrepancies; 100% declared items | automated, mutation | approved plan |
| Q02 | Performance efficiency / time/resources | 10000 files, max7 producers; 5 fresh browser contexts | median summary ms<=5000; disclosure/search/status/analyzer/page ms<=300 each; max50 file rows; existing full-suite performance criteria retained | <= named thresholds; 0 extra source reads/parses | automated | approved plan/delegated details |
| Q03 | Compatibility / coexistence | before/after characterization all7 standalone plus3 combinations, file/symbol | graph/details/metrics/candidate equality ignoring only added coverage fields; schema/export equality | =0 discrepancies | automated | approved plan |
| Q04 | Interaction capability / operability | C11/C13 plus filters in offline browser | counts/reasons/paths matches independent fixtures; navigation no page errors or external requests | =0 discrepancies/errors/requests | automated | approved plan |
| Q05 | Reliability / fault tolerance | C02/C03/C06/C12 | result signal and unaffected-state assertions | =0 incorrect states | automated | approved plan |
| Q06 | Security / integrity | malicious path/message/code as text and embedded data | browser attack flag, injected elements, external requests | =0 execution/injected elements/requests | automated | approved plan |
| Q07 | Maintainability / modularity | shared accumulator and producer integration | repeatable main review of all aggregation call sites and parse/read counters; record results | one common merge implementation; zero extra parsing/reading | review, automated | delegated details |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V01 | F01,F02,Q01,Q05,C01,C02,C03,C04 | standalone snapshot producer results | integration, each listed item | equivalence partitioning | 7 analyzers normal/empty/no-declaration each;4 strict parse failures;3 recovered AST;4 NestJS semantic codes | 100% | actual parser/extractor reports match independent status/reason/span; valid sibling survives | pytest and coverage.json |
| V02 | F03,Q01,Q05,C05,C06 | snapshot+CLI scan surface | unit/integration, named items only | boundary value analysis (2-value) | 9 current exclusions explicit_output/lockfile/vendored/generated_path/unreadable/too_large/binary/generated_marker/agent_document_disabled; max/max+1; TS/Kotlin/Android/NestJS own discovery exclusion; unrelated; empty inventory; existing output/new output | 100% | reasons unchanged, output never read or invented | pytest |
| V03 | F04,Q01,C07 | shared accumulator public API | unit, finite merge table | decision table | complete;partial;failed;skipped;complete+failed;complete+skipped;partial+failed;failed+skipped;duplicate complete;duplicate mixed;no result;excluded;shuffled reasons/reports | 100% | exact unique summaries, reasons, deterministic records | pytest |
| V04 | F05,F06,Q01,Q03,C08,C09,C10 | CLI and snapshot direct APIs | integration, named combinations in each granularity | combinatorial (base choice) | 7 standalone file/symbol;3 combinations from C08 file/symbol;4framework disabled language;explicit python+sqlalchemy disabled;PythonSourceAnalyzer, Kotlin.build,7 analyzer APIs+4 builders;unknown legacy architecture | 100% | stages retained, duplicate counts eliminated, common values identical and schema preserved | pytest |
| V05 | F06,F08,Q03,Q05,C10,C11,C12 | serialization/regeneration and regression | integration, listed before/after and failure scenarios | scenario | 7 standalone+3 combinations file/symbol before/after;old architecture5/6+bottlenecks4/5;JSON-only regeneration;fatal file reader/analyzer signal | 100% | graph/details/network/candidates same; fields/exports preserved; signal unchanged | pytest + regression.json |
| V06 | F07,Q04,Q06,C11,C12,C13 | offline HTML | end-to-end, named fixtures and interactions | scenario | combined,architecture-only,bottlenecks-only,legacy,no-snapshot;0/1/50/51 rows;path search,reason search,status filter,producer filter,reset/page bounds;hostile path/code/message | 100% | summary/detail exact; safe literal output,0external requests,0pageerrors | pytest + browser.json |
| V07 | F01,F07,Q02,Q07,C13 | reporting read/parse cost and UI timing | integration/end-to-end, standalone7 and synthetic10k | scenario | read/parse counters seven standalone;10000files/7producers;5fresh contexts summary/disclosure/search/status/producer/page;existing performance suite | 100% | zero added reads/parses; bounded rows and median thresholds; existing criteria pass | pytest + performance.json |
| V08 | F01,F04,F05,F08,Q07 | shared accounting architecture | integration + repeatable review | scenario | one merger implementation;7producer recording paths;4implicit builder paths;merge+file conversion+bottleneck propagation | 100% | main records explicit call-path findings and counter evidence; no extraction changes | coverage.json review entries |

Technique policy: finite equivalence classes, boundary pairs, merge decisions and workflow/UI scenarios cover the stated risk; arbitrary Cartesian combinations and statement/branch targets are excluded because they are not behavior requirements. No success percentage is presented as semantic coverage.

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
| --- | --- | --- | --- |
| A01 | Concrete wire keys, ids, deterministic merge, reason codes,50-row pages and exact signature choices above | existing provenance ids/schema nested dictionaries/discovery rules support additive fields | user selected technical delegation and approved plan, then Implement the plan |
| A02 | applicable quality decisions and finite test selections above | approved correctness/compat/UI/safety/performance scope; no new safety/deployment role | same delegation/approval |
| A03 | system Python temporary venv using requirements-dev; preserve broken repo .venv | existing interpreter cannot import encodings; installed packages lack playwright | approved temporary validation environment |
| A04 | approval covers this faithful operational spec; no new behavior approval round | this spec concretizes final approved plan and delegated details only | Implement the plan |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F01,F02 | C01-C04 | V01,V07,V08 | automated+review |
| F03 | C05,C06 | V02 | automated |
| F04 | C07 | V03 | automated+mutation |
| F05 | C08-C10 | V04,V08 | automated+review+mutation |
| F06 | C10,C11 | V04,V05 | automated |
| F07 | C11-C13 | V06,V07 | automated |
| F08 | C02,C03,C10-C12 | V05,V08 | automated+review |
| Q01,Q05 | C01-C10,C12 | V01-V05 | automated |
| Q02,Q07 | C01,C08-C10,C13 | V07,V08 | automated+review |
| Q03 | C08-C12 | V04,V05 | automated |
| Q04,Q06 | C11-C13 | V06 | automated |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 7 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state:
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V01 | 2 | coverage.json r1; suite7; mutations.json; verifier-1.md | accepted | audit1 retained; recovery mutation detects | audit2 accepted; CR07 impact confirmed; all mutation source hashes restored |
| V02 | 2 | coverage.json r2; suite7; mutations.json; verifier-1.md | accepted | audit1 retained; no changed dependency | audit2 accepted; CR07 impact confirmed; all mutation source hashes restored |
| V03 | 2 | coverage.json r7; suite7; mutations.json; verifier-1.md | accepted | corrected aggregate reason/version evidence; span/version/count probes detect | audit2 accepted; CR07 impact confirmed; all mutation source hashes restored |
| V04 | 2 | coverage.json r7; suite7; mutations.json; verifier-1.md | accepted | corrected independent version evidence; version/export probes detect | audit2 accepted; CR07 impact confirmed; all mutation source hashes restored |
| V05 | 2 | coverage.json r7; suite7; mutations.json; verifier-1.md | accepted | corrected independent version evidence; version/export probes detect | audit2 accepted; CR07 impact confirmed; all mutation source hashes restored |
| V06 | 2 | coverage.json r7; suite7; mutations.json; verifier-1.md | accepted | corrected human scope limitation; generic tally probe detects | audit2 accepted; CR07 impact confirmed; all mutation source hashes restored |
| V07 | 2 | coverage.json r1; suite7; mutations.json; verifier-1.md | accepted | audit1 retained; counter/timing inputs/helpers unchanged | audit2 accepted; CR07 impact confirmed; all mutation source hashes restored |
| V08 | 2 | coverage.json r1; suite7; mutations.json; verifier-1.md | accepted | audit1 retained; source restored byte-for-byte after every probe | audit2 accepted; CR07 impact confirmed; all mutation source hashes restored |

Execution ledger:
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| R01 | repository .venv cannot initialize encodings; system Python lacks pytest, existing packages lack playwright | verified unusable managed Python prefix; missing browser package | temporary system-Python venv from requirements-dev | environment preparation pending; no implementation changes |

| R02 | parser1.21 cache directory creation rejected | verified default cache outside writable roots; original1.20 cache available | pin temporary environment parser to original1.20 | imports/parsers restored |
| R03 | baseline combined graph duplicate config node | verified existing enrichment duplicate-ID contract | characterization fixture uses non-enriched notes.txt; same declared analyzer combinations | 20 before-change CLI outputs captured, immutable baseline; implementation not started |

| R04 | initial implementation review: legacy stats=None and per-producer displayed reason attribution | new additive access could reject legacy data; merged reason display obscured origin | implementer preserved None compatibility and prefixed reasons with human producer labels | corrected during initial reconcile, no tests/acceptance changed |
| R05 | suite1: kotlin-core discovery fixture expected skipped in node_modules; actual complete;45 passed/1failed | verified test assumption conflicts existing Kotlin discovery policy (build excluded, node_modules included) | correct same declared discovery-exclusion item to analyzer-specific original excluded directory; inspect Android sibling too | V02 test defect CR02, no behavior/spec change; verifier0/2 |

| R06 | suite2:60passed/1failed full-payload characterization equality | verified only four FastAPI top_reused_dependencies entries differ in Python type: JSON-frozen baseline lists vs in-memory current tuples; values identical | compare both at declared JSON serialization boundary using JSON roundtrip, excluding only coverage additions | V05 test/evidence defect CR03; immutable baseline unchanged; verifier0/2 |

| R07 | suite3:78passed/1failed architecture-only disclosure immediately read empty rows | hypothesis native details toggle event is asynchronously delivered; DOM assertion reads before update | main probe eventual rows and absence of page errors; wait for documented observable populated/empty-result table | V06 evidence defect CR04 pending probe confirmation; verifier0/2 |
| R08 | TF04-PRODUCER-COUNTS evidence gap discovered during main review | verified tests checked common summaries/producer identities but never exact per-producer summary; all-zero producer counters could escape | strengthen SAME V03 merge table assertions with independently expected per-producer state/target counts | V03 evidence correction CR04, no added variant or changed target; acceptance still pending |

| R09 | suite4:675passed/104subtests passed;8legacy standalone output hash subfailures after595.64s | verified old byte hashes include full JSON; approved optional nested coverage changes bytes | preserve immutable old hashes; strip only new coverage keys and reserialize using ORIGINAL CLI byte formats before comparison | V05 compatibility evidence correction CR05; performance passes preserved; verifier0/2 |

| R10 | CR05 targeted original hash diagnostic | original byte formatting and coverage-only removal validated | exact legacy O11 check executed independently before whole suite retry | 1passed/8subtests passed in6.84s; immutable old hashes unchanged; suite5 pending |

| R11 | TF06-UI-RESULTS main pre-audit evidence gap | verified DOM checks observe paths/reasons/counts but could miss omitted/mislabeled file and producer statuses or summary labels | strengthen same six-state fixtures and existing hostile fixture with independent human label/status/attribution assertions | CR06 V06/V07 evidence revision6; no new variants or implementation changes; suite5 pre-edit remains provisional, verifier0/2 |

| R12 | suite5 full command passed before CR06 assertions were loaded | unchanged implementation/legacy correction validated; current test modules were imported before CR06 edits | preserve unchanged-obligation proof; confirm stronger same-variant UI observations, then exact current-suite rerun | 1132passed/200subtests passed in703.65s; V06 current revision6 remains pending; verifier0/2 |

| R13 | CR06 strengthened same-variant UI observations | explicit status/producer/reason ownership assertions added without timing changes | focused V06 diagnostic run before current exact-suite replay | diagnostic result recorded with suite6 below; no implementation changes; verifier0/2 |

| R14 | final current evidence suite6 | CR06 focused13passed then exact full current command, no implementation changes | all declared automated checks pass; V08 main review and current evidence map ready | 1132passed/200subtests passed in718.09s; independent verifier invocation1/2 persisted before dispatch |

| R15 | independent audit1 complete retry,3 blocking evidence gaps | exact aggregate reason fields, common version1, and human scope limitation not independently observed | accepted findings as evidence gaps; preserve V01/V02/V07/V08 acceptance and all past dispositions; one CR07 evidence batch, no behavior/spec changes | verifier1/2; three findings open pending corrections and confirming probes |

| R16 | CR07 evidence corrections complete | exact same-fixture aggregate reasons, integer wireversion1 at declared surfaces, and actual human unlisted-scope notice now observed | V03-V06 revised7 pending; accepted V01/V02/V07/V08 dependencies unchanged (no shared observation/counter/timing/architecture helpers changed) | focused diagnostic then suite7 and confirming probes pending; verifier1/2 preserved |

| R17 | CR07 focused and exact command pass | same declared variants now reject aggregate-field/version/scope omissions | focused91passed in10.54s; current full suite7 passed, no code changes | 1132passed/200subtests passed in686.34s; confirming probes pending; verifier1/2 |

| R18 | confirming probes after positive restored suite7 | three strongest classes: duplicate producer counts, recovery state, coverage information corruption; prioritize audit gaps within information class | six sequential probes span/version/scope/count/recovery/export, each exact Test command; every intended assertion detected; seed restore hashes match; passing evidence restored | 6run/6detected/6restored; findings corrected pending final audit; invocation2/2 persisted before dispatch |

| R19 | independent audit2 complete pass | corrected wire/display evidence and retained acceptance dependencies audited against current full suite and mutation artifacts | all V01-V08 accepted; three audit findings closed; previous dispositions retained; no advisory/spec challenge | verifier2/2, correction batches7,6probes detected/restored; completion authorized by all stop conditions |

# Version Log
## v1
- Operational spec of the approved plan, with user-delegated interface/test details. Initial workflow; prior handoff was unimplemented and consumed no verifier budget.

## v2
- Before dispatch, aligned delegated concrete combinations with existing duplicate-ID policy: FastAPI+SQLAlchemy, NestJS+TypeScript, Android+Kotlin with --no-language-graph. Default Android+Kotlin and FastAPI+Python remain duplicate-ID errors; preserving these existing errors is part of F08/V05. No approved behavior, threshold, or verification target changed.
