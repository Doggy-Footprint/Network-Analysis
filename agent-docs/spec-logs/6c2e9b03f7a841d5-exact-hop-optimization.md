---
version: 2
run_id: 6c2e9b03f7a841d5
status: complete
base_commit: bec2e3e1da62a27c471f5de81924cbe83113eae3
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| U1 | user | 정확한 값을 유지하는 선에서 2-hop, 3-hop 최적화 | Exact neighborhoods and mathematically identical cost policy, with measured runtime and memory. |

# Scope
In scope: exact undirected two/three-hop metrics, component-local adaptive bitsets, integer-tenths cost aggregation, cache budget, strategy metadata, independent correctness and performance evidence.
Out of scope: sampling/approximation, edge removal, other centrality algorithms, external dependencies, CLI changes, hard RSS limits, speed pass thresholds, ADRs.

# Paths
Implementation: analysis/graph_metrics.py
Tests: tests/test_exact_neighborhoods.py, scripts/benchmark_hops.py, tests/nestjs_evidence/baselines.json
Test command: PYTHONPATH=.venv/lib/python3.12/site-packages python3 -m pytest -q
Review evidence: scripts/benchmark_hops.py run with the same PYTHONPATH; its JSON artifact at /private/tmp/network-analysis-exact-hop-benchmark.json includes graph parameters, medians and traced peaks. Main records results and cache-lifetime review in this spec. No structure-based coverage target; all finite behavior obligations below have 100% coverage.

# Signatures
GraphAnalysisConfig(..., neighborhood_memory_budget_bytes: int = 256 * 1024 * 1024)
GraphAnalyzer.analyze(nodes, edges, project_path=None) -> Dict[str, Any] (existing)
GraphAnalyzer._neighborhoods(start, adjacency) -> tuple[Set[str], Set[str]] (existing exact BFS retained)
GraphAnalyzer._neighborhood_metrics(adjacency: Mapping[str, Set[str]], tick_costs: Mapping[str, int]) -> tuple[Dict[str, Tuple[int, float, int, float]], str]
GraphAnalyzer._estimate_neighborhood_bitset_bytes(node_count: int, cost_bit_count: int) -> int
The tuple is (hop_2_node_count, hop_2_token_cost, hop_3_node_count, hop_3_token_cost); tick_costs are nonnegative integer tenths of a token.

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F1 | Undirected reachability within 2/3 edges; exclude start; unique targets. Preserve edge normalization and all nodes including zero-cost nodes. | must | approved plan |
| F2 | Component-local indexing. BFS if n < 64 or sum(degree**2) < 64*n. Otherwise use bitsets only if estimated peak bitset representation fits budget. Boundary equality selects bitsets. | must | approved plan |
| F3 | Closed 1-hop masks -> cached closed 2-hop masks -> union neighbors' 2-hop masks for closed 3-hop; remove start for metrics; never cache all 3-hop masks. | must | approved plan |
| F4 | Policy tenths: vendored 0, generated/migration 1, ordinary 10 times integer token cost. Sum integer ticks; bitset cost planes use AND/bit_count with binary place weights. Divide by 10 for reported hop costs. BFS uses identical policy. Preserve raw/effective token cost and other metric calculations. | must | approved plan |
| F5 | Config budget defaults 256 MiB; 0 disables bitsets; negative ValueError at config construction. Estimate counts simultaneously live bitset integer buffers, list references, cost planes and working masks conservatively using running Python object sizes. Estimate is not process RSS. Decide before dense masks are allocated. Release component buffers before the next component; no persistent analyzer cache. | must | user memory selection and plan |
| F6 | Strategy: single_bfs_to_3_hops if BFS only, including empty; exact_bitset if bitsets only; exact_hybrid if both. Existing numeric keys, ranking rules, metadata propagation, and unrelated fields remain. | must | approved plan |

# Errors
E1: Negative neighborhood_memory_budget_bytes -> ValueError at GraphAnalysisConfig construction; no analysis or node metadata mutation.
E2: Budget too small -> successful exact BFS fallback, not an error or partial report.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | chain, cycle, hub, dense, seeded random | Independent BFS-matching counts, membership and costs. |
| C2 | boundary | 0/1 node; distance 2/3/4; n 63/64; degree-work 64*n equality; budget estimate-1/estimate/estimate+1; 0 budget | Exact boundaries and strategy choices. |
| C3 | edge | disconnected mixed components; zero-cost intermediary; duplicate/self/unknown edges; fractional discounted costs | No lost reachability; unique costs; exact_hybrid where applicable. |
| C4 | error | negative budget | E1; E2 covers fallback success. |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | Exact metrics are the primary constraint. |
| Performance efficiency | yes | Runtime/memory measurement and cache budget are the requested improvement. |
| Compatibility | yes | Report keys, ranking rules and existing metrics must remain usable. |
| Interaction capability | no | No UI/CLI interaction changes. |
| Reliability | yes | Exact fallback and repeated-run cache lifecycle. |
| Security | no | No new inputs, permissions, network or execution capabilities. |
| Maintainability | no | No separate maintainability target; normal repository rules apply. |
| Flexibility | no | No platform adaptation requirement beyond current Python environment. |
| Safety | no | No safety-relevant operation. |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Functional suitability / correctness | All finite graph variants and every node | Independent deque BFS, explicit cost policy and marker-cost membership reconstruction | Counts/membership exactly equal; costs math.isclose(rel_tol=1e-12, abs_tol=1e-9) | automated and mutation | approved values policy |
| Q2 | Performance efficiency / resources | Every algorithm/budget boundary | Strategy observation; conservative representation estimator; peak trace and lifetime inspection | Estimate <= configured budget for bitset selection; 0 persistent component buffers | automated, review, mutation | approved 256 MiB |
| Q3 | Performance efficiency / time | chain1500, tree1500, hub1500, dense300, random800 with seed1729 and 8*n random edge pairs | At least 3 repeats; median seconds including component/mask/cost setup and aggregation; tracemalloc peak bytes measured separately on optimized and independent baseline | Report all 5 datasets; no speed/peak ratio pass threshold | review | user chose correctness-only acceptance |
| Q4 | Compatibility | Public analyze report and non-hop metrics | Existing full suite plus direct budget0/default comparison | No removed metric keys; non-hop values and ranking rules unchanged; metadata updated | automated | approved plan |
| Q5 | Reliability | Repeated calls, mixed components and budget fallback | Repeated helper/analyze observations, source lifetime review | Same metrics; budget fallback completes; no graph-specific bitset state on analyzer | automated and review | approved plan |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | F1,F3,Q1,C1,C2 | All-node helper outputs and marker-derived membership | unit, all nodes in each finite graph | equivalence partitioning, boundary value analysis | empty, isolated, chain, cycle, hub64+, dense64+, random64+; distance2/3/4; start exclusion | 100% | independent BFS counts/costs; marker membership exact on BFS and bitset cases | tests/test_exact_neighborhoods.py |
| V2 | F2,F5,Q2,C2,C4 | Config, estimator and helper strategy | unit, each declared boundary | boundary value analysis, decision table | negative, zero, estimate-1/equal/+1; n63/64; work below/equal64*n | 100% | ValueError or expected exact strategy and unchanged values | tests/test_exact_neighborhoods.py |
| V3 | F1,F4,Q1,C3 | Cost policy and normalized analyze graph | integration, all declared variants | equivalence partitioning, metamorphic testing | default,generated,migration,vendor; zero-cost bridge; mixed costs; duplicate,self,unknown; direction reversal | 100% | no lost membership; oracle costs; normalized identical reports | tests/test_exact_neighborhoods.py |
| V4 | F6,Q4,C3 | Strategy/report/rank metadata | integration, all strategy values and unrelated metrics | decision table, scenario | empty/BFS,bitset,hybrid; budget0/default compare; metadata propagation | 100% | declared strategy names, matching non-hop metrics, same ranking rules | tests/test_exact_neighborhoods.py and full suite |
| V5 | F3,F5,Q2,Q5,C3 | Component lifetime and repeated analysis | unit plus main source review, repeated inputs | scenario, error guessing | dense -> chain -> empty; mixed components; no persistent buffers; no all-3-hop cache; budget checked before allocation | 100% | stable results; scoped/released buffers; conservative size accounting | tests plus main review recorded below |
| V6 | Q3 | Hop phase including preparation/aggregation | benchmark, all named graphs | equivalence partitioning | chain1500,tree1500,hub1500,dense300,random800(seed1729,8*n pairs) | 100% | exact oracle equivalence; median seconds and peak bytes; no performance pass threshold | scripts/benchmark_hops.py JSON and recorded summary |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
| --- | --- | --- | --- |
| A1 | 256 MiB estimated bitset working memory, not hard RSS | Python allocation overhead varies; estimates include bitset objects and buffers | explicit user choice and approved plan |
| A2 | Numeric rounding differences allowed at Q1 tolerances; no approximation of reachability or cost policy | Existing float sums depend on traversal order | explicit user choice and approved plan |
| A3 | Correctness-only performance acceptance; thresholds64/64*n as initial heuristic | Prototypes favor bitsets for broad graphs but regress on chain | explicit performance answer and approved plan |
| A4 | No new dependencies; run Python3 with existing .venv site-packages | .venv interpreter fails stdlib lookup; python3.12 plus its site-packages imports pytest/yaml/tree-sitter | implementation environment, no product policy change |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| U1,F1,F3,Q1 | C1,C2,C3 | V1,V3,V5 | oracle tests and source review |
| F2,F5,Q2 | C2,C3,C4 | V2,V5 | budget tests and source review |
| F4 | C1,C3 | V1,V3 | cost/marker tests |
| F6,Q4 | C1,C3 | V4 | report/full suite |
| Q3 | C1 | V6 | benchmark JSON |
| Q5 | C3 | V5 | repeat tests/lifetime review |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 1 |
| verifier invocations | 1 |
| open finding ids | none |

Audit state:
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V1 | 2 | tests/test_exact_neighborhoods.py revision1; T2; verifier1; M1/M3 logs | accepted | Counts/membership/cost accepted; M1 start inclusion and M3 doubled weighted costs detected by intended V1 assertions; restored | no final source/test changes |
| V2 | 2 | tests/test_exact_neighborhoods.py revision1; T2; verifier1; M2 log | accepted | Boundary evidence accepted; M2 ignored budget detected by intended below-budget strategy assertion; restored | no final source/test changes |
| V3 | 2 | tests/test_exact_neighborhoods.py revision1; T2; verifier1 | accepted | Explicit policy/normalization oracle accepted | none |
| V4 | 2 | T2; golden comparison artifact; verifier1 | accepted | Full suite and independently justified byte goldens accepted | golden artifact updated with independent comparison |
| V5 | 2 | tests/test_exact_neighborhoods.py revision1; T2; Review Evidence; verifier1 | accepted | Repeat/state and source lifetime/budget-before-allocation review accepted | source unchanged since I1 |
| V6 | 2 | Review Evidence; benchmark JSON; verifier1 | accepted | All five datasets and medians/peaks accepted | Comparator replacement B1; v2 metadata-only annotation |

Execution ledger:
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| P1 | .venv Python cannot locate encodings | verified: broken stdlib prefix /install | use system python3.12 and existing .venv site-packages | environment workaround; no dependency installs |
| P2 | Existing metric tests failed with missing _neighborhood_metrics during active editing | verified: incomplete implementation snapshot | defer execution until implementer reports ready | inconclusive run; not implementation evidence |
| I1 | Initial source review found changed fallback invocation order | verified: component set traversal differs from adjacency order | defer fallback and iterate original adjacency; reserve 4*n list slots to cover append overhead | resolved before independent test dispatch; 58 existing metric tests pass |
| T1 | Full suite: 936 pass, 192 subtests pass; 11 failures include 8 golden subtests, two retired-path cache dirs and unavailable Android fixture | verified: expected output serialization changes; only bytecode in retired dirs; fixture content did not match pin | compare HEAD/current outputs independently before refreshing goldens; remove only obsolete bytecode cache dirs; fetch pinned public Android commit and verify hash | all 8 legacy outputs match stored goldens; recursive differences only allowed hop numeric types/rounding and strategy; fixture hash verified |
| B1 | Initial benchmark timed an independently written deque BFS | verified: valid oracle but different performance comparator from retained production BFS | keep deque oracle, time retained _neighborhoods with legacy separate float sums | evidence replaced; V1-V5 unchanged |
| T2 | All environment and expected golden mismatches resolved | verified: matching pins and independently justified snapshots | exact full Test command on spec v2 | 939 passed, 200 subtests passed in 24.35s; no remaining failure |
| A1 | Independent verifier audit | verified: complete evidence map, all finite coverage items accepted | test-verifier invocation1, no implementation access | pass V1-V6; no blocking findings; confirming mutations remain main closure gate |
| M1 | Deliberately retain start in 3-hop bitset | verified: bitset cases include start, count/membership invariant violated | backup all edited source; inject; exact Test command with 120s timeout; restore with manifest SHA256 verification | intended V1 hub/dense/random count assertions detect; 16 failures, 929 pass, 194 subtests pass in 24.30s; /private/tmp/network-analysis-hop-M1.log; restored |
| M2 | Deliberately ignore nonzero memory budget | verified: estimate-1 selects forbidden bitsets while values remain exact | backup source; inject; exact Test command with 120s timeout; restore with manifest SHA256 verification | intended V2 below-budget strategy assertion detects; 1 failure, 938 pass, 200 subtests pass in 24.43s; /private/tmp/network-analysis-hop-M2.log; restored |
| M3 | Deliberately shift 3-hop cost-plane weights higher | verified: costs doubled with unchanged membership/counts | backup source; inject; exact Test command with 120s timeout; restore with manifest SHA256 verification | intended V1 hub/dense/random cost assertions detect; 16 failures, 929 pass, 194 subtests pass in 24.34s; /private/tmp/network-analysis-hop-M3.log; restored |
| T3 | Final verification after every mutation restored | verified: seed manifest restore and no remaining backup | exact full Test command, diff whitespace check | 939 passed, 200 subtests passed in 24.52s; all obligations accepted; no open findings; 1 correction batch, 1 verifier invocation, 3/3 confirming mutations detected |

Confirming mutations selected for first audit: M1 start inclusion (V1), M2 ignored memory budget (V2), M3 shifted cost-plane weights (V1/F4). These are three distinct highest-impact defect classes covering traversal, resource-policy selection and aggregation. All three executed, failed the intended independent assertions, and were restored before continuing. V3's separate policy integration evidence remains accepted and unchanged. No final production/test change resulted, so audit acceptance is retained; no further verifier invocation is required.

## Review Evidence
- V5 source review (main, revision1): inspect `_neighborhood_metrics`, `_estimate_neighborhood_bitset_bytes` and `_bitset_component_metrics`. Budget comparison occurs before calling mask allocator; component-local helper owns indices/closed1/closed2/planes and returns only numeric tuples; no persistent graph buffers or all-node closed3 array. Helper frame is gone before next component; component/queue are deleted. Estimator reserves max-width integers for two mask arrays, all cost planes, eight working masks and eight wider cost accumulators; four list headers with 4*n reference slots cover component growth plus closed1/closed2; per-node dict/index reserve is conservative. Other centrality calculations and stable ranking implementation remain unchanged.
- V6 benchmark revision2: all five datasets oracle-equivalent. Median baseline/optimized seconds: chain1500 0.004552/0.004780, tree1500 0.005834/0.006024, hub1500 0.653842/0.008901, dense300 0.807610/0.024156, random800 0.225048/0.007807. Traced baseline/optimized peak bytes: 331104/309156, 331104/309156, 798864/1047328, 156744/135136, 357668/456712. These are hop-phase measurements, not complete pipeline speedups. JSON artifact: /private/tmp/network-analysis-exact-hop-benchmark.json.
- Golden refresh procedure (main): execute each of the eight pinned CLI cases twice at hash seed0, once loading `git show HEAD:analysis/graph_metrics.py` into the analysis module and once with current code. Every legacy portable digest matches the existing baseline. Recursively compare all JSON keys/list order/non-hop fields exactly and allow only hop costs/numeric representation and strategy labels; costs use Q1 tolerance. All cases pass. Comparison artifact: /private/tmp/network-analysis-hop-output-comparison.json. Refresh only those verified portable/raw digests and captured-root/base revision metadata. No expectation or verification threshold changed.

# Version Log
## v1
- Formalizes the user-approved plan and selections; Implement the plan authorizes dispatch. Private helper signatures expose independent test/benchmark surfaces without changing public behavior.
## v2
- Add independently verified refresh of existing CLI golden artifact required by the approved numeric/strategy changes. Functional and quality expectations and coverage policy are unchanged; no new user decision. Record environment recovery, replaced benchmark comparator, source lifetime review and measured results.
