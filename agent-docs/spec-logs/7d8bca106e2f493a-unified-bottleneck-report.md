---
version: 3
run_id: 7d8bca106e2f493a
status: complete
base_commit: 57f2f8c9eac367b077d5bac9a45e0da2d5e1d0d5
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | user | 보고서를 완전히 새로 작성; 핵심은 병목; 밝은 분석 보고서와 크게 줄인 그래프 | Read metric representatives, inspect evidence, and explore a small neighborhood in one offline HTML. |

# Scope
In scope: replacement active HTML, shared offline renderer, CLI integration, browser and regression tests, README migration, bounded direct-neighbor graph and progressive details.
Out of scope: analyzer/candidate rules/metric formula/JSON schema changes, whole-network graph, multi-hop expansion, new aggregate score, archive rewrites, hosting, runtime server.

# Paths
Implementation: renderers/html/, report/unified.py, report/bottlenecks/, report/shared/labels.py (only if necessary), code_analyzer/cli.py, README.md.
Tests: tests/, requirements-dev.txt.
Test command: .venv/bin/python -m pytest -q
Review evidence: local-reports/unified-review.json, local-reports/unified-report.html, local-reports/unified-desktop.png, local-reports/unified-mobile.png, local-reports/unified-chrome.png; reproducible procedures below. Workflow audit artifacts: agent-docs/specs/7d8bca106e2f493a-evidence.json until archival. No structure-based coverage percentage required: behavior boundary/scenario/metamorphic checks are the approved coverage basis.

# Signatures
HTMLRenderer(title: Optional[str] = None, framework_label: str = "")
HTMLRenderer.render(arch: Any, output_path: str, *, bottleneck_report: Optional[Mapping[str, Any]] = None) -> Path
report.unified.render_unified_report(architecture: Optional[Mapping[str, Any]], bottlenecks: Optional[Mapping[str, Any]], *, title: Optional[str] = None, framework_label: str = "") -> str
report.bottlenecks.render_report(payload: Any) -> str (existing signature; validated JSON-only shared presentation)
report.bottlenecks.generate.generate(input_path: Path, output_path: Path, *, read_text, write_text) -> Path (existing signature)

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F1 | Single light Korean report, narrative hierarchy, file-direct offline; inline CSS/JS/Cytoscape 3.30.2 with MIT license; no CDN/assets directory/runtime server or npm runtime. | must | approved plan 1,3 |
| F2 | Summary has project/scope/category node counts and counts of each candidate kind. Exactly six metric groups: pagerank, betweenness_centrality, hop_2_token_cost, weighted_centrality_cost, fan_in, fan_out. Up to three nodes per group, descending raw value then ID ascending, 한국어 meaning/unit. Never aggregate different metric/candidate kinds into a score. | must | approved plan 1 |
| F3 | Default production; choices all, production, test, generated, vendored, unknown. Classification matches existing bottlenecks._category path semantics, precedence vendored/generated/test/production, span absent unknown. Category filters summary representatives and list only, never recompute whole-graph metrics. Zero-valued groups state all-zero, missing finite values excluded from representatives and shown as — in list/detail. Production absent stays empty with an explicit category-switch instruction. | must | approved plan 1,3,4 |
| F4 | List includes all metric-bearing nodes, not just JSON top ten. Search case-insensitive trimmed name/path/ID; sort selector includes all twelve ranking metrics plus token_cost/effective_token_cost/identifier_file_count, descending value (missing last), ID ascending ties; default pagerank. Candidate filter all plus each of three kinds; candidate kinds are filters/badges, not a separate priority score. 50 rows/page, previous/next, reset page after category/search/metric/kind change. | must | approved plan 1; delegated details |
| F5 | Labels name + disambiguating file path; IDs available in details. Selecting representative/list/relationship shows detailed node, all available metrics incl identifier context counts, candidate reasons and entire path/start/end-line evidence, typed fields/doc/flags/metadata in collapsible sections. Aggregate candidate badges by kind/target but preserve every raw candidate and evidence. | must | approved plan 1 |
| F6 | No graph instance before selection. Direct neighbors only, excluding self from neighbor set. Choose max30 distinct neighbors by maximum effective incident edge weight descending then neighbor fan_in descending then ID ascending. Weight = min(confidence/resolution configured values), defaults existing profile; multiple incident edges use maximum. All categories eligible regardless list filter. Selected center always retained. | must | approved plan 2 |
| F7 | Graph includes center-incident edges only, grouped by directed node pair, <=31 nodes/60 arrows. Keep per-edge relationship/confidence/resolution/evidence/candidates in complete incident relationship list (50/page) including omitted neighbors and self edges. Explicit shown/omitted neighbor counts. Deterministic preset: center middle, incoming-only left, outgoing-only right, bidirectional below; no physics/extensions/whole graph/multihop. Node clicks reselect. Fit/zoom+/zoom- buttons; edge selection exposes grouped individual evidence. | must | approved plan 2; delegated details |
| F8 | Details/appendix retain all supplied metrics, identifier occurrences, signatures/docs, dynamic metadata, framework collections (expand then 50 rows/page), snapshot/weights/threshold/version/coverage/limitations, betweenness strategy/sample size. Initial main view does not eagerly build these rows. Context counts can overlap; token estimates/overlapping spans explained. | must | approved plan 1 |
| F9 | CLI always runs analyze_bottlenecks on existing snapshot+arch before rendering, including plain -o. -o sole code_analyzer HTML output; remove --bottlenecks-html and reject with argparse error2. Preserve --json architecture schema5, --bottlenecks schema bottlenecks.v4, remaining options and analysis behavior. Pass bottleneck dict to renderer. Preserve collision/output-exclusion validation, excluding historical output _assets path harmlessly if necessary. | must | approved plan 3 |
| F10 | Existing JSON-only render_report/generate APIs validate inputs and use same shell. With no architecture, summary uses supplied rankings/category rankings, detailed metrics/candidates remain available; full category completeness, source and connections explicitly unavailable, no invented graph. Existing direct HTMLRenderer without bottleneck input uses supplied architecture metrics with candidate-data unavailable signal. | must | approved plan 3; delegated compatibility |
| F11 | Remove legacy active UI/assets/vis integration, preserve neutral serialization and archives, update obsolete UI tests and README command/output descriptions. Renderer owns visualization; analyzers do not import renderers. | must | approved plan 3 |

Public test/automation contract (stable selectors, not implementation internals): #report-summary, #category-filter select, [data-metric-group="metric-key"], [data-node-id="id"] on node-selection buttons, #node-search, #metric-sort select, #candidate-kind-filter select, #node-list with [data-node-row="id"], #list-count, #page-prev/#page-next, #node-detail (data-selected-node), #graph-container, #graph-status (data-shown/data-omitted), #graph-fit/#graph-zoom-in/#graph-zoom-out, #relationship-list with [data-relationship-row], #relationship-prev/#relationship-next, #report-appendix, #report-status. Collections: [data-collection-key="key"] wrapper, [data-collection-row] rows, [data-collection-prev]/[data-collection-next] scoped navigation; rows lazy until expansion. Grouped rendered graph topology observable via window.ReportGraph (null until selection; Cytoscape instance thereafter). Inline neutral payload script #report-data contains {architecture: object|null, bottlenecks: object|null}; optional presentation-only fields are allowed outside these two original objects. No testing-dependent behavior. Search/list controls work independently of graph availability.

# Errors
- Invalid CLI/path/weights/snapshot/candidate analysis: existing explicit CLI error and nonzero exit; do not produce a new success report.
- Invalid JSON/schema/nonfinite metrics/unsupported candidate/duplicate candidate ID: preserve ReportInputError and field-path diagnostics; no output written by generate.
- Renderer I/O error: visible CLI stderr/nonzero; no success claim. Transactional multi-output writes not added.
- Browser payload error: visible #report-status error; no partial success claim.
- Graph unavailable/initialization throws: visible #graph-status; relationships and non-graph details remain usable and node selection still works.
- No category/search results: explicit empty result with counts; no fallback category. No candidates: explicit none discovered (or data unavailable for architecture-only input).

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | small graph, six metric values, all three candidate kinds | summary top3, evidence details, bounded selection navigation |
| C2 | boundary | neighbor counts 0,1,30,31; list counts0,1,50,51 | exact limits/counts, next/prev boundaries |
| C3 | edge | same names different paths; ties; missing/all-zero metrics; no production; selected cross-category neighbors; duplicate/bidirectional/self edges | deterministic labels/sort/emptiness, preserve all evidence, graph center only |
| C4 | error | malformed payload, hostile HTML text, graph constructor failure, removed CLI option, I/O failure | explicit errors or inert literal text; usable non-graph surfaces when graph fails |
| C5 | normal | plain -o; -o with both JSON options; Python and mixed analyzers; JSON-only APIs | unified HTML, preserved schema/data, explicit missing capabilities |
| C6 | normal | 10k nodes/30k edges/1k candidates; cold local-file Chrome five times | performance thresholds, all data retained in bounded presentation |
| C7 | normal | 390px/1440px, keyboard, offline Google Chrome | readable hierarchy, no external requests, core journey operable |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | requested representatives/inspection must be correct |
| Performance efficiency | yes | large graphs previously made report unreadable |
| Compatibility | yes | offline Chrome and JSON/interface preservation |
| Interaction capability | yes | reading flow, keyboard and mobile usability |
| Reliability | yes | sparse/empty/error inputs must be explicit |
| Security | yes | source-derived text must stay inert |
| Maintainability | yes | common renderer replaces duplicate UI |
| Flexibility | no | no runtime extensions/hosting/new deployment modes requested |
| Safety | no | informational structural report has no operational control |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Functional suitability / correctness | six representatives, filters, limits, evidence | independently specified fixtures; mismatch count | 0 mismatches | automated | plan4 |
| Q2 | Performance efficiency / time | C6 on current workstation; Chrome 5 fresh pages/contexts, data preparation outside timer; file navigation to summary, filter/page change to painted rows, selected detail/graph ready | performance monotonic ms; median5 cold starts and interactive measurements | summary<=5000ms; filter/page<=300ms; detail/graph<=1000ms | automated; raw timings artifact | plan4 |
| Q3 | Compatibility / interoperability | C5 JSON and C7 offline browsers | schema/assertions, external http(s) request count, detached file opens | unchanged schemas; external requests0; Chrome automated/core journey pass | automated/review | plan3,4 |
| Q4 | Interaction capability / operability | C7 390/1440; keyboard controls; reading hierarchy | screenshot+DOM horizontal overflow and keyboard scenario | body width<=viewport; all named main controls reachable/usable; summary precedes detail; no initial graph | automated/review | plan4 |
| Q5 | Reliability / fault handling | C2/C3/C4 sparse inputs and graph failures | visible failure signal + independent surviving control assertions | all enumerated states100%; no unhandled graph error | automated | plan4 |
| Q6 | Security / inert source text | C4 label/doc/evidence/title/metadata values containing script close/img onerror/HTML | browser execution marker, DOM literal text | marker never executed; hostile fields visible as text;0 external requests | automated/mutation | plan4 |
| Q7 | Maintainability / separation | F11 single active presentation, no analyzer changes for UI | import scan and neutral schema regression |0 visualization imports in analyzers; archive unchanged; both adapters same shell | automated/review | plan3 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | F2,F3,F4,Q1/C1,C3 | summary/list in browser | e2e; each choice | equivalence partitioning/metamorphic | 6 representatives,6 categories,3 kind filters,search match/no-match,metric change,tie,missing,all-zero,no-production |100% enumerated items (not Cartesian) | independent values/order/counts; changing categories never changes metric values | pytest browser fixtures |
| V2 | F6,F7,Q1/C2,C3 | rendered Cytoscape and relationships | e2e + pure model if desired | boundary value analysis/scenario |0,1,30,31 neighbors;rank weight/fanin/id;all-category;bidirectional;duplicate;self; omitted evidence;graph navigation;group-edge evidence; zoom/fit |100% items |<=31 nodes/60 center arrows, raw relationships complete and correct selected30 | pytest fixed graph oracle |
| V3 | F4,F5,F8,Q1/C1,C2,C3 | lists/detail/appendix | e2e | boundary/scenario |0,1,50,51 node rows;prev/next/reset;paths/same names;candidate metrics/evidence ranges;typed/doc/flags/meta;all metrics/identifier contexts;collections50/page;settings/strategy |100% items | bounded DOM, complete inspectable data, no narrated score | pytest independent fixture |
| V4 | F9,F10,F11,Q3,Q7/C5 | files/CLI/APIs | integration/regression | scenario/syntax |plain -o;both JSON;removed option;collision;output exclusion;Python;merged analyzers;JSON-only;architecture-only;invalid JSON/schema/path validation;shared shell/inline/no assets |100% items | correct files/options/errors, schemas preserved, no fake unavailable data | pytest full suite |
| V5 | F1,Q3,Q4/C7 | file-direct Google Chrome | e2e + review | scenario |network blocked;390/1440;keyboard;no initial graph;summary-detail-graph flow;actual Chrome core flow |100% items | readable inert offline report; body no overflow; all controls accessible | pytest; root Chrome screenshot and review.json |
| V6 | Q5,Q6/C4 | generator and browser errors | unit/integration/e2e | error guessing/decision table |graph failure;payload failure;empty graph/category/search;missing metrics;malformed payload;I/O;hostile text label/doc/title/evidence/meta |100% explicitly finite decision states; guessed defects none-experience-based | field errors/inert text/surviving details | pytest; root mutations |
| V7 | Q2/C6 | Chrome file performance | e2e | scenario |5 cold starts;5 filters/page updates;5 detail/graph selections |100%15 observations | all three medians below thresholds,31-node bound | pytest timings artifact |
| V8 | F11,Q7 | architecture/regressions | integration/review | metamorphic |neutral JSON schema;existing static edges/metrics/candidates;single common presentation;archive unmodified |100%items | no analyzer result change beyond default candidate calculation | pytest full suite/import scan/diff review |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
| --- | --- | --- | --- |
| A1 | Core6, production first,30 neighbors,light summary-first,unified offline,-o only,secondary details retained | explicit planning answers | user approved plan then Implement the plan |
| A2 | Korean units, fixed layout, selectors, weight/fanin/id order,50-row pages, error states, test procedures | bounded rendering and existing metric/schema contracts; no new analyzer semantics | user delegated remaining implementation/verification details |
| A3 | Existing vendor Cytoscape3.30.2 and license; no new build/runtime dependencies | local vendor/license verified; sufficient preset/interaction APIs | approved plan2 |
| A4 | Python Playwright dev dependency (<2) and installed Google Chrome (channel=chrome) for automated tests; Node existing tests retained | current Python lacks dependencies; Google Chrome installed; install .venv; no Safari access or bundled browser download | delegated verification details |
| A5 | JSON-only category rankings may be partial; expose supplied ranked entries rather than infer classification of every node; main CLI always has full architecture | bottlenecks.v4 lacks complete source/category metadata | delegated compatibility details |
| A6 | Quality scope/thresholds approved plan plus delegated ISO mapping; no fabricated percent source-code coverage | behavior scenarios enumerate required outcomes | user approved plan4; delegated remaining criteria |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| I1,F1,F2,F3,F4 | C1,C2,C3,C7 | V1,V3,V5 | pytest/browser/review |
| F5,F8 | C1,C3 | V3 | pytest |
| F6,F7 | C2,C3 | V2 | pytest/mutation |
| F9,F10 | C4,C5 | V4,V6 | pytest |
| F11 | C5 | V4,V8 | pytest/diff review |
| Q1 | C1,C2,C3 | V1,V2,V3 | pytest |
| Q2 | C6 | V7 | performance artifact |
| Q3,Q4 | C5,C7 | V4,V5 | pytest/Chrome review |
| Q5,Q6 | C3,C4 | V6 | pytest/mutation |
| Q7 | C5 | V8 | pytest/diff review |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 7 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state:
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V1 |3|7d8bca106e2f493a-evidence.json revision2;tests/unified_evidence/verifier-2.json;test-suite-final.log|accepted|100% approved finite items;VR1-VR6 closed;M1-M3 intended assertions detected and restored|current47 test hashes;unchanged production;renewed full suite/performance|
| V2 |3|7d8bca106e2f493a-evidence.json revision2;tests/unified_evidence/verifier-2.json;test-suite-final.log|accepted|100% approved finite items;VR1-VR6 closed;M1-M3 intended assertions detected and restored|current47 test hashes;unchanged production;renewed full suite/performance|
| V3 |3|7d8bca106e2f493a-evidence.json revision2;tests/unified_evidence/verifier-2.json;test-suite-final.log|accepted|100% approved finite items;VR1-VR6 closed;M1-M3 intended assertions detected and restored|current47 test hashes;unchanged production;renewed full suite/performance|
| V4 |3|7d8bca106e2f493a-evidence.json revision2;tests/unified_evidence/verifier-2.json;test-suite-final.log|accepted|100% approved finite items;VR1-VR6 closed;M1-M3 intended assertions detected and restored|current47 test hashes;unchanged production;renewed full suite/performance|
| V5 |3|7d8bca106e2f493a-evidence.json revision2;tests/unified_evidence/verifier-2.json;test-suite-final.log|accepted|100% approved finite items;VR1-VR6 closed;M1-M3 intended assertions detected and restored|current47 test hashes;unchanged production;renewed full suite/performance|
| V6 |3|7d8bca106e2f493a-evidence.json revision2;tests/unified_evidence/verifier-2.json;test-suite-final.log|accepted|100% approved finite items;VR1-VR6 closed;M1-M3 intended assertions detected and restored|current47 test hashes;unchanged production;renewed full suite/performance|
| V7 |3|7d8bca106e2f493a-evidence.json revision2;tests/unified_evidence/verifier-2.json;test-suite-final.log|accepted|100% approved finite items;VR1-VR6 closed;M1-M3 intended assertions detected and restored|current47 test hashes;unchanged production;renewed full suite/performance|
| V8 |3|7d8bca106e2f493a-evidence.json revision2;tests/unified_evidence/verifier-2.json;test-suite-final.log|accepted|100% approved finite items;VR1-VR6 closed;M1-M3 intended assertions detected and restored|current47 test hashes;unchanged production;renewed full suite/performance|

Execution ledger:
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
|12|verifier2 pass|verified: all47 test hashes match;all V1-V8 accepted;VR1-VR6 closed|independent final audit;3 intended mutation detections;no blockers;VA1 optional unexecuted|complete;7 correction batches,2 verifier invocations;no handoff|
|11|restored final suite941 passed,200 subtests104.02s|verified: source restored matches originalhash;all strengthened expectations pass|evidence revision2;new timing artifact;fresh verifier2 persisted|audit2 pending;all mutations detected|
|10|confirming mutations M1,M2,M3|verified: executed violations detected by intended category,neighbor-cap,execution-marker assertions|M1:6 fails;M2:4 fails;M3:3 fails;all restored with baseline hash identical|restored final suite pending;no new blocker|
|9|suite6:941 passed,200 subtests106.36s|verified: below-max zoom and trusted Unicode native typeahead distinguish behavior reliably|all VR1-VR6 supplemental observations pass;original source unchanged|passing;M1-M3 confirming mutations next|
|8|suite5:938 passed,3 failed,200 subtests78.82s|verified: zoom already max3; minimal Chrome native popup arrow automation also fails, trusted Unicode keyDown succeeds|test uses below-max baseline and native trusted Korean typeahead after actual Tab;no product changes|batch7 pending;V5 invalidated;V2 partial evidence pending|
|7|verifier1 retry VR1-VR6|verified: declared rendered evidence gaps, no scope challenge|test correction batch6 adds exact independent surface observations;V7/V8 accepted|six blockers open;second audit reserved|
|6|suite4:931 passed,200 subtests61.77s|verified: stable disclosure iteration and awaited lazy appendix resolve all tests|final Chrome visual/performance artifacts and unchanged-analyzer/archive/import scans|passing evidence revision1;verifier invocation1 persisted|
|5|suite3:930 passed,1 failed,200 subtests;67.52s|verified: opening outer appendix triggers async toggle; immediate descendant count0 returns before construction|await lazy descendant wrapper before disclosure traversal; visual review stack labels and hide idle graph-edge labels|correction pending; V3 evidence pending; visual representation revision pending|
|4|suite2:926 passed,5 failed,200 subtests;200.76s|verified: Playwright .all() returns nth locators against shrinking :not(open) match set, skipping then timing out; outer appendix not opened|stable disclosure iteration/open-first loop and explicit outer open; bounded action timeout|test correction pending; no product changes; V2,V3,V6 invalidated pending new evidence|
|3|suite1:918 passed,9 failed,5 errors; graph fit tiny stripe|verified: missing fixture; Playwright per-module session loops; collapsed/async disclosure assertions; wrapper focus; argparse2 oracle; single-column graph|prepare futuramaapi; test fixes preserve declared expectations; repack preset neighbors on same required sides|correction pending; all obligations pending|
|2|collection test observability|verified: collection selectors missing from initial public automation contract|add selectors; graph self edges excluded, retained in relationship list|v3 unchanged functional behavior|
|1|Safari computer-use access unavailable|verified: tool reported Safari not approved; user expressly selected Chrome|use installed Chrome channel, no Safari actions|spec v2 browser amendment|
|0|grounding|verified: no active specs, clean worktree; Python lacks pytest/playwright/tree-sitter|approved plan translated without changing decisions|dispatch pending|

# Version Log
## v3
- Additive collection-pagination selectors record delegated verification details; graph self-edge exclusion clarified without changing neighbor/relationship requirements. No accepted evidence exists; all obligations remain pending.

## v2
- User explicitly requested Chrome (chrome을 써); Chrome channel replaces Safari review and bundled Chromium runs. Functional scope and thresholds unchanged; no accepted evidence existed to invalidate.

## v1
- User approved complete proposed plan and explicitly delegated remaining implementation/verification details. Execution spec records those choices and observable verification surfaces.
