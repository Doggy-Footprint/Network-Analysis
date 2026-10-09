---
version: 3
run_id: 9c41e725d083ab6f
status: limit
base_commit: 5737113df15f6ed1705c1adadcf6b9c86bf9523e
max_verifier_invocations: 2
handoff: agent-docs/handoff/e6f962102cb7de1a-ambiguous-route-candidates.md
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| UI1 | repository reviewer | ambiguous-route-candidates handoff를 진행해줘; Implement the plan. | All ambiguous candidate targets contribute symmetrically to analysis and the current JSON/HTML report. |

# Scope
In scope: all existing ambiguous language, enrichment, HTTP, DI, schema and migration relations; symbol/file analysis, file aggregation, bottleneck evidence, current unified JSON/HTML, producers' self-target and deduplication loss.
Out of scope: Mermaid improvements; resolver accuracy expansion; changing exact relation semantics; replacing large-graph betweenness sampling; reconstructing legacy report metrics; performance tuning or new numerical performance targets.

# Paths
Implementation: analysis/, bottlenecks/, language_analyzers/, framework_analyzers/, report/, renderers/html/, code_analyzer/ (only as necessary to propagate policy); excludes tests/ and workflow documents.
Tests: tests/ only.
Test command: .venv/bin/python -m pytest -q
Review evidence: tests/ambiguous_candidates_evidence/9c41e725d083ab6f-architecture-review.md; main records repeatable review of shared projection consumption, candidate group provenance, no misuse of GraphEdge.weight, and preserved sampling. Evidence map: tests/ambiguous_candidates_evidence/9c41e725d083ab6f-evidence-map.md.

# Signatures
GraphEdge existing fields and default weight retain their types and meaning.
GraphAnalyzer.analyze(nodes, edges, project_path=None) -> dict; adds ambiguity_policy="equal-symbol-share.v1".
to_file_architecture(architecture, snapshot) -> FileArchitecture; aggregated edge metadata adds candidate_share in (0,1], retains detail_edge_indices and evidence_count.
analyze_bottlenecks(snapshot, architecture, weights, *, analysis=None) -> BottleneckReport; dependency_network adds ambiguity_policy="equal-symbol-share.v1". When ambiguous evidence exists, candidate_groups maps stable IDs to lossless original {to_id, candidates}; ambiguous evidence references candidate_group_id instead of repeating candidates. Original architecture.edges/details.edges are unchanged; exact evidence shape is unchanged. IDs distinguish original candidate order/duplicates and representative; identical groups share one entry. Report-only HTML resolves the registry to expose complete raw evidence.
architecture_to_dict(architecture) -> dict; newly generated reports expose policy in stats.analysis.ambiguity_policy.
render_unified_report(architecture, bottlenecks=None, ...) -> str; each supplied payload must carry supported policy at its corresponding analysis/network location; otherwise ReportInputError before producing a document.
Current HTML loader displays its existing error surface for a supplied payload with missing/unsupported policy, before rendering metrics or relations.

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| FR1 | An ambiguous relation's target set is deduplicated {to_id}+candidates; order and the stored representative have no computational precedence. Other resolutions keep their original target semantics. A legacy ambiguous edge with no alternatives has one candidate. | must | approved plan |
| FR2 | Allocate w/N to each candidate; w=min(profile.confidence, profile.resolution), or 1 without a profile. This is a contribution, not a probability. GraphEdge.weight remains discovery multiplicity and never multiplies contribution. | must | approved plan |
| FR3 | Weighted fan, PageRank and HITS use allocated contributions. Ordinary fan/degree, directed betweenness, undirected 2/3-hop counts and costs use the union of possible non-self connections. Distinct relations on the same ordered pair use maximum contribution. | must | approved plan |
| FR4 | File aggregation sums candidate shares mapped to the same target file within one original relation, then takes maximum across distinct original relations on the same pair. Self-symbol/internal-file shares are excluded without reallocating; denominator is the complete candidate set. Boundary targets without a source file are retained for every candidate. Aggregated edges are not allocated a second time. | must | approved plan |
| FR5 | Keep original edge fields, full candidate groups, confidence, resolution, evidence, multiplicity and metadata in details. File edge provenance identifies all contributing originals without duplicate indices/counts within a grouped edge. Different candidate sets must not be lost through representative-based dedupe. Producers may omit wholly self-target-only relations as before but never omit external alternatives because the representative equals the source. | must | approved plan |
| FR6 | Bottleneck dependency edge_count counts unique projected non-self ordered pairs. Evidence-spread rules address every possible target, dedupe each original evidence per target/file, and retain the ambiguous candidate group in evidence. Ambiguity alone creates no unresolved-boundary candidate. Preserve unrelated candidate rules. | must | approved plan |
| FR7 | Current HTML symbol/file exploration and relationship details are accessible from source and every candidate, display ambiguity, allocated contribution and whole original group; distinguish discovery multiplicity. Graph neighbor weights follow analysis contribution/max rules. Preserve existing 30-neighbor and 50-row limits and safe text rendering. | must | approved plan |
| FR8 | New analysis and report payloads identify equal-symbol-share.v1, retaining existing schema versions and edge shape. Each supplied architecture/report lacking the marker or carrying another value causes ReportInputError during generation and a visible loader error when loading injected JSON. No legacy fallback, recalculation or misleading new-policy labeling. | must | approved plan and user's legacy-error decision |
| FR9 | Preserve exact/unique/unresolved behavior and weights, serialization fields, route/migration statistics, default matching, existing deterministic sampling and unrelated report behavior. Fix only tests whose expectations/fixtures intentionally change under FR1-FR8. | must | approved plan |

# Errors
Missing/unsupported policy in either supplied report component — ReportInputError before document generation; injected HTML JSON uses visible existing load-error surface, no metric/graph rendering.
Candidate reference outside architecture — BottleneckInputError at analysis/file/report-validation boundary; no silently reduced candidate set or output. Direct analyzer validation may use ValueError as base error when no snapshot is available; full bottleneck API retains BottleneckInputError.
Malformed explicit candidate_share (non-number, bool, nonfinite, <=0 or >1) — ValueError/BottleneckInputError before successful computation; do not invent a fallback weight.
No candidate match in producers — preserve existing unmatched/unresolvable stats, no relation fabricated.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- |
| C1 | normal | source plus 2/3 candidates, default/custom/no profile | all targets; each w/N; independent weighted and union-topology oracle |
| C2 | boundary | producer has 0/1 candidate; ambiguous stored without alternatives | existing absence/unique behavior; single candidate share 1 |
| C3 | edge | duplicate candidate IDs; reversed input/representative; bijective ID rename | deduplicated candidate set; identical corresponding exact metrics within 1e-9 |
| C4 | edge | self candidate and external candidate; all self; internal/external file mixture | exclude self/internal; no redistribution; external alternatives retained by producers |
| C5 | normal | 3 symbol candidates: 2 in B, 1 in C | file shares 2/3 and 1/3; no double allocation |
| C6 | edge | wholly same target file; duplicates; overlapping candidate sets; exact+ambiguous pair | within-original sum, across-original max, provenance retained without double count |
| C7 | error | unknown candidate or malformed share | declared error, no successful partial result |
| C8 | normal | HTTP TS/Retrofit, Python/TS/Kotlin references, enrichment TESTS, FastAPI, Android, migration producers | each producer emits complete group, preserves source evidence/stats, and feeds shared policy |
| C9 | normal | source evidence in multiple files/line ranges, each alternative | symmetric evidence_spread; one original per target/file; no spurious unresolved_boundary |
| C10 | normal | HTML symbol/file, select source and every candidate, original symbols/boundaries | visible group/contribution/ambiguity; links and graph show every candidate; multiplicity separate |
| C11 | error | architecture-only/report-only/combined payload, either missing/unsupported marker | generation error; injected JSON visible load error; supported payload works |
| C12 | edge | hostile candidate labels/paths and large relationship/neighbor collections | safe text/no script or external request; existing limits and navigation retained |
| C13 | normal | existing suite; exact relations; new-run repeat; large-graph analysis | existing regression green apart from intentional new expectations; stable new output; sampling unchanged |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | required symmetric contributions and topology |
| Performance efficiency | no | no new benchmark threshold approved; retain bounded UI and existing checks |
| Compatibility | yes | retain edge schema/weight and fail unsupported report-policy inputs |
| Interaction capability | yes | every alternative must be accessible and visibly ambiguous |
| Reliability | yes | deterministic allocation and explicit invalid-input failures |
| Security | yes | candidate text/links retain safe rendering |
| Maintainability | yes | shared projection and consistent consumers required |
| Flexibility | no | no new platform or configuration dimension |
| Safety | no | static structural facts; no safety-critical action |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| QR1 | Functional suitability / correctness | exact graph metrics on finite tiny graphs and renamings | independent graph oracles plus metamorphic comparison, mismatches | zero mismatches; floating absolute tolerance 1e-9 | automated + mutation | approved plan |
| QR2 | Compatibility | supported JSON roundtrip and policy rejection | C11 partitions plus weight/field checks, failed partitions | zero failures | automated | approved plan |
| QR3 | Interaction capability | candidate navigation, group visibility and limits | symbol/file browser observations C10/C12, failed partitions | zero failures | automated | approved plan |
| QR4 | Reliability | repeat-run output and invalid input | C3/C7/C11/C13, divergent runs or accepted invalid inputs | zero | automated | approved plan |
| QR5 | Security | hostile strings in candidate report surfaces | browser DOM and request/script probes, executed attacks/unexpected external requests | zero | automated | approved plan, existing safe rendering |
| QR6 | Maintainability | projection consumers and provenance/weight semantics | review consumer call paths; for each of metrics/file/bottleneck/HTML verify rule consistency, missing or inconsistent consumers | zero | review + automated | approved plan |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VO1 | FR1,FR2,FR3,QR1,C1,C2,C3 | public analyzer, base-choice graphs | unit | equivalence partitioning + metamorphic | two; three; duplicates; no-alternatives; default-profile; custom-profile; no-profile; representative-swap; bijective-rename | 100% of listed items | contributions/fan/degree/PageRank/HITS/betweenness/hop counts+costs independently correct | Test command and evidence-map |
| VO2 | FR3,FR4,FR5,QR1,C4,C5,C6 | file conversion followed by analysis | integration | decision table | same-file-2-of-3; all-one-target-file; internal+external; all-internal; self+external; boundary-alternative; overlap-max; exact-overlap; no-double-allocation; provenance-count | 100% | declared allocation, max merge and retained provenance | Test command and evidence-map |
| VO3 | FR5,FR9,C2,C4,C8 | producer-to-policy pathways, each-choice selection not Cartesian product | integration | equivalence partitioning | Python; TypeScript; Kotlin; enrichment TESTS; FastAPI named+field-types; Android named; HTTP TS+Retrofit; migration SQLAlchemy+Room; self-representative external retention in language/enrichment emitters; distinct candidate-set dedupe | 100% | complete candidates, stats/evidence retained, no lost external targets | Test command and evidence-map |
| VO4 | FR6,FR9,C9 | bottleneck symbol and file reports | integration | decision table | symbol-alternatives; file-alternatives; collapsed-target-file; overlapping-original-evidence; internal-file-evidence; edge_count; ambiguity-not-unresolved | 100% | symmetric evidence_spread and projected edge counts, unrelated rules preserved | Test command and evidence-map |
| VO5 | FR7,QR3,QR5,C10,C12 | current HTML only, each-choice | end-to-end | scenario | symbol-source; symbol-each-alternative; file-source; file-each-alternative; same-file-symbols; boundary; group/contribution/multiplicity; neighbor-limit; relationship-pagination; hostile-text | 100% | accessible candidates, visible semantics, correct neighbor weights, safe bounded rendering | Test command/browser assertions and evidence-map |
| VO6 | FR8,QR2,QR4,C7,C11 | public report generation and HTML loader | unit/integration/end-to-end, base choice | decision table | supported-architecture-only; supported-report-only; supported-combined; missing-architecture; unknown-architecture; missing-report; unknown-report; combined-one-invalid; injected-missing; injected-unknown; unknown-candidate; invalid-share | 100% | errors before successful partial result; valid shapes retained | Test command and evidence-map |
| VO7 | FR9,QR2,QR4,C13 | entire existing suite, repeat outputs and sampling | integration | regression scenarios + metamorphic | full-suite; exact-unique-unresolved-regression; repeated-new-run; existing-sampler | 100% | zero unexplained failures, exact behavior retained and stable output | Test command and evidence-map |
| VO8 | FR1,FR2,FR4,FR5,FR6,FR7,QR6 | review current shared projection integration | review | scenario | metrics; file aggregation; bottleneck rules; HTML; raw details; weight multiplicity; sampler | 100% | one candidate interpretation, no double allocation/loss/misused weight | 9c41e725d083ab6f-architecture-review.md: record input fixtures, inspect each consumer and expected rule, record path/observation/result |

Specification techniques cover finite partitions, merge decisions, renaming invariants, producers and user-visible scenarios. No structure-based percentage is added: all required behaviors have named observable obligations; no approved statement/branch target. No Cartesian producer x edge-case product is implied. No performance or probabilistic interpretation claim is made.

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
| --- | --- | --- | --- |
| A1 | all ambiguous relations, equal-symbol shares, within-original file sum, across-original max | existing candidate format verified during planning | explicit answers and Implement the plan |
| A2 | no redistribution of excluded self/internal shares; preserve existing schema/weight | explicit planning decisions | explicit answers and Implement the plan |
| A3 | unsupported legacy reports fail, no compatibility display/recompute | user: 해당 상황은 고려하지 않음. 해당 상황 발생시 오류 처리. | explicit answer and Implement the plan |
| A4 | exact ID renaming invariant; existing sampled betweenness retained; JSON/current HTML only | chosen verification/output scope | explicit answers and Implement the plan |
| A5 | finite obligations 100%, absolute floating tolerance 1e-9, full regression, three confirming mutations, verifier maximum 2 | official proposed plan's acceptance section | Implement the plan |
| A6 | metadata/policy names and implementation helper layout are mechanical plan concretization, not new behavior | approved interfaces retained; no new user preference | Implement the plan |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| FR1 | C1,C2,C3 | VO1,VO8 | automated + review |
| FR2 | C1,C3,C6 | VO1,VO2,VO8 | automated + review |
| FR3 | C1,C3,C6 | VO1,VO2 | automated |
| FR4 | C4,C5,C6 | VO2,VO8 | automated + review |
| FR5 | C4,C6,C8 | VO2,VO3,VO8 | automated + review |
| FR6 | C9 | VO4,VO8 | automated + review |
| FR7 | C10,C12 | VO5,VO8 | browser + review |
| FR8 | C7,C11 | VO6 | automated + browser |
| FR9 | C2,C8,C9,C13 | VO3,VO4,VO7 | full suite |
| QR1 | C1,C3,C4,C5,C6 | VO1,VO2 | independent oracles + mutation |
| QR2 | C11,C13 | VO6,VO7 | automated |
| QR3 | C10,C12 | VO5 | browser |
| QR4 | C3,C7,C11,C13 | VO1,VO6,VO7 | automated |
| QR5 | C12 | VO5 | browser |
| QR6 | C5,C6,C9,C10 | VO8 | review |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 7 |
| verifier invocations | 2 |
| open finding ids | V3-F5 |

Audit state:
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| VO1 | 3 | evidence-map revision7; full4; audit2.json; mutations.json; restored-v3 | accepted | audit2 accepts current evidence; previousF1-F4 resolved; VO4/VO8 unchanged dependencies retained; intended mutations3/3 detected and restored | verifier2/2; limit before any correction needing audit3 |
| VO2 | 3 | evidence-map revision7; full4; audit2.json; mutations.json; restored-v3 | accepted | audit2 accepts current evidence; previousF1-F4 resolved; VO4/VO8 unchanged dependencies retained; intended mutations3/3 detected and restored | verifier2/2; limit before any correction needing audit3 |
| VO3 | 3 | evidence-map revision7; full4; audit2.json; mutations.json; restored-v3 | accepted | audit2 accepts current evidence; previousF1-F4 resolved; VO4/VO8 unchanged dependencies retained; intended mutations3/3 detected and restored | verifier2/2; limit before any correction needing audit3 |
| VO4 | 3 | evidence-map revision7; full4; audit2.json; mutations.json; restored-v3 | accepted | audit2 accepts current evidence; previousF1-F4 resolved; VO4/VO8 unchanged dependencies retained; intended mutations3/3 detected and restored | verifier2/2; limit before any correction needing audit3 |
| VO5 | 3 | evidence-map revision7; full4; audit2.json; mutations.json; restored-v3 | open | audit2 V3-F5: symbol weighted contribution0.15 not directly observed; file contribution and all other VO5 items accepted; intended mutations3/3 detected and restored | verifier2/2; limit before any correction needing audit3 |
| VO6 | 3 | evidence-map revision7; full4; audit2.json; mutations.json; restored-v3 | accepted | audit2 accepts current evidence; previousF1-F4 resolved; VO4/VO8 unchanged dependencies retained; intended mutations3/3 detected and restored | verifier2/2; limit before any correction needing audit3 |
| VO7 | 3 | evidence-map revision7; full4; audit2.json; mutations.json; restored-v3 | accepted | audit2 accepts current evidence; previousF1-F4 resolved; VO4/VO8 unchanged dependencies retained; intended mutations3/3 detected and restored | verifier2/2; limit before any correction needing audit3 |
| VO8 | 3 | evidence-map revision7; full4; audit2.json; mutations.json; restored-v3 | accepted | audit2 accepts current evidence; previousF1-F4 resolved; VO4/VO8 unchanged dependencies retained; intended mutations3/3 detected and restored | verifier2/2; limit before any correction needing audit3 |

Execution ledger:
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| P1 | baseline first-target bias | verified representative-only adjacency | tiny graph swaps representative; fan_in 1/0 and PageRank .480519/.259740 swap | approved improvement |
| E1 | .venv interpreter missing encodings; pip/Playwright absent | verified stale uv symlink despite Homebrew pyvenv.cfg | repoint ignored interpreter symlink to installed Python3.12; bootstrap bundled pip | environment restoration in progress |
| E2 | sandbox dependency download DNS/Chrome SIGABRT | verified sandbox networking/browser restriction | installer and headless probe under approved escalation | dependencies/parser/browser restored |
| C1 | focused: 62 passed; I1 group pagination duplicates originals; T1/T2 producers expect single relation kind | I1 verified per-target rows; T1/T2 verified multiple legitimate kinds | implementing original-group relationship lists; correcting test selection independently | correction batch 1 in progress |
| C2 | regression:374 passed/4 failed direct unknown exact endpoint; focused2:199 passed/3 failed | verified I2 changed exact skip; I3 profile metadata noncanonical; T3 assumes extraction/candidate specificity policy | preserve exact skip; effective identity tables; controlled producer fixture and preserve original metadata | fixed, full suite in progress |
| R1 | VO8 consumer review | trace shared group S->{B1,B2,C}, same-file and overlap rules | tests/ambiguous_candidates_evidence/9c41e725d083ab6f-architecture-review.md | seven review items pass; independent audit pending |
| T4 | current independent focused tests | corrected producer selection, fixture-only seams and metadata preservation | /tmp/ambiguity-focused-4.log: 81 passed in 17.45s | VO1-VO6 automated evidence passing; full regression and independent audit pending |
| C3 | full1:41 failed/1198 passed/1 error/191 subtests,750.72s | verified legacy fixture references/markers, strict old metadata/raw byte goldens, CLI Python absent marker, exact evidence wire expansion; some import-state failures predate fixes | fix fixtures/CLI/exact wire; strict source-based raw transition comparator; whole all-one equivalence kept | targeted correction:247 passed/30 subtests,194.81s |
| C4 | standalone8 frozen byte hashes differ under intended all-ambiguity metrics | verified reconstructed pre-task first archive hashes exactly match; new topology/metrics intentionally differ | freeze hash-verified original corpus; independently check raw transitions/fan/edge counts/evidence; keep original archives and unrelated fields | preparing standalone policy regression, full rerun pending |
| C5 | standalone transition oracle false failures from original context assumptions | verified unique-vs-ambiguous propagation, file-level textual sources, exact siblings, file imports, frozen category membership and adaptive hop strategy | bounded source-backed oracle corrections with positive/rejecting cases; no source-backed cost relaxation | O11:1 passed/8 subtests in14.40s; comparator35 passed; metadata golden115 passed; full2 running |
| E3 | original category reference import yaml missing | verified resolving interpreter symlink bypassed venv | invoke absolute venv entry path without resolving symlink | original category vectors independently validated against archived rankings |

| C6 | full2:1247 passed/200 subtests/1 error,753.20s; real report browser has empty report-data text and JSON EOF | verified 599,017,124-byte HTML repeats complete ambiguous candidate lists across evidence targets; valid Python JSON exceeds browser string capacity | lossless candidate-group registry for bottleneck evidence, raw architecture/details retained; independent recovery tests and fresh full regression required | implementation correction pending; verifier remains 0 |

| C6-P1 | v3 focused:91 passed/8 subtests/1 file raw-evidence mismatch,13.77s | verified expected fixture omitted existing detail_edge_index; recovered raw fields and groups otherwise match | include independent original ordinal in file expected record; no fields dropped | within correction batch6; final focused/full run pending |

| C6-P2 | v3 storage-focused final tests | original ordinal fixture corrected; symbol/file raw recovery and report-only HTML observed independently | 121 passed/8 subtests/11 deselected in38.72s; exact full Test command running with timeout1800s | focused pass, full3 pending |

| C6-R | fresh real corpus/browser validation | lossless storage removes browser string limit while preserving raw transition oracle | real-repository-v3:3 independent file workers, median76.188s<180s; 5 fresh Chrome contexts, summary1789.54ms<5000ms/filter28.1ms<300ms/detail45.9ms<1000ms | real validation passes; full3/audit/mutations pending |

| T6 | exact full Test command after v3 correction | fresh settled implementation/test files; finite timeout1800s | tests/ambiguous_candidates_evidence/ambiguity-full-3.log:1252 passed/200 subtests,722.92s | passing baseline; audit1 invocation persisted before dispatch; confirming mutations pending |

| A1 | audit1 four evidence gaps V3-F1/F2/F3/F4 | verified PageRank common share cancels in single-group stars, pytest default relative tolerance, broad exception acceptance, unassociated file contribution text | batch7: mixed exact/ambiguous independent PageRank, rel=0 absolute comparisons, declared error type, per-target file UI contribution and cutoff assertions; no implementation or approved expectation changes | VO1/2/3/5/6 open; VO7 fresh baseline invalidated; VO4/8 accepted; verifier1 of2 used |

| C7-P1 | intermediate strict focused:121 passed/5 failed,29.67s | verified test omitted selected weights in mixed PageRank API call; main supplied wrong three-digit formatting assumption while current UI uses five fractional digits | pass selected profile explicitly; use existing independently specified5-digit visible shares .66667/.33333; retain strict numerical tolerance/target association | within batch7; implementation unchanged; final cutoff fixture and full4 pending |

| C7-P2 | corrected strict focused baseline | profiles passed, five-digit display expectation preserved, file/symbol 30-neighbor allocation contrasted with .15 competitors, rel0 across quantitative siblings and exact exception type | ambiguity-correction-7.log:223 passed in16.73s | batch7 focused passes; full4 running; selected mutations then audit2 required |

| T7 | exact full Test command after all audit1 evidence corrections | no implementation changes; settled evidence revision7 tests | ambiguity-full-4.log:1258 passed/200 subtests,700.94s; fresh real-repository-v3-final median72.907s and browser1817.28ms/28.2ms/43.2ms meet original bounds | passing corrected baseline; selected audit-specific mutations next, final audit2 required |

| M7 | confirming mutations after corrected full4 baseline | selected strongest audit escaping behaviors: PageRank-only full-share, error5e-8, HTML file-sum omission; untouched fan/HITS for first mutation | mutations.json:3/3 intended assertion failures; seed backup/SHA256 restore and pre-injection source equality all pass; restored focused91 passed,15.04s; seed status none | main resolves V3-F1/F2/F3/F4 by revised independent evidence; fresh audit2 invocation persisted before dispatch; no further verifier budget |

| A2 | final audit2 V3-F5 | verified required symbol weighted contribution display0.15 is not independently asserted; current0.5 assertion observes share and could miss wrong contribution0.3 | audit2 acceptsVO1/2/3/4/6/7/8, resolvesF1-F4; VO5 file items accepted but symbolic numerical display remains open | verifier budget2/2 exhausted; status limit; no post-budget test/code correction; handoff preserves remaining concrete work |
| H2 | generated historical output cleanup | tracked benchmark/performance artifacts are test outputs, not implementation or oracle changes | copied10 current artifacts to full-suite-generated-v3, restored their pre-task HEAD bytes without git index mutation; current pass evidence retained separately | no semantic/test source changes; no outstanding seed; handoff active for user audit-budget decision |

# Version Log
## v3
- Lossless evidence storage uses a shared candidate-group registry to make the existing real-repository HTML loadable. Original ordered candidate lists, raw architecture/details, discovery multiplicity, metrics, exact evidence shapes, and approved behavior/coverage/thresholds remain unchanged. This adds an internal reference signature without changing candidate semantics. Full2 exposed the browser string-capacity failure; no passing browser result is inferred from old cached evidence.
## v2
- Evidence document names/paths now follow the project 16-hex naming/index convention. Functional behavior, interfaces, quality thresholds, techniques, coverage targets and approved verification policy unchanged; this is documentation lifecycle alignment.
## v1
- Transcribed approved proposed plan and explicit planning answers after user's Implement the plan. No behavioral decision added beyond that approval.
