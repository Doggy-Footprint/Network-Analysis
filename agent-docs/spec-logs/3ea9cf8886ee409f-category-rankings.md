---
version: 2
run_id: 3ea9cf8886ee409f
status: limit
base_commit: 698402c15c3b12108d95c0d99d1a9de6857fece4
max_verifier_invocations: 2
handoff: agent-docs/handoff/stale/ef204f17ee13850a-category-rankings-v6-evidence.md
---

# User Intent
| id | stakeholder | intention | observable goal |
|---|---|---|---|
| I1 | user | Separate production bottlenecks from test, generated and vendored nodes in v3 rankings (handoff ec9d04784407ee5b: Room schema JSON dominates hub top-10, test symbols in authority top-5) | `dependency_network.rankings_by_category` lists top-10 per category per metric; HTML report shows it |

# Scope
In scope: additive `rankings_by_category` in bottlenecks.v3 JSON; report validation and HTML rendering of it.
Out of scope: changing `rankings`, metric computation, edge weights, candidates, schema name, `language_analyzers/core/flags.py` rules. Uncommitted fixture-registry changes in the working tree (separate task, already tested).

# Paths
Implementation: bottlenecks/core.py, report/bottlenecks/generate.py
Tests: tests/test_category_rankings_v3.py
Test command: .venv/bin/python -m pytest -q
Review evidence: none — all obligations are automated.

# Signatures
CATEGORY_KEYS = ("production", "test", "generated", "vendored", "unknown")  # in bottlenecks/core.py
dependency_network["rankings_by_category"]: {category: {metric in RANKING_KEYS: [{"node_id": str, "value": number}, ...]}}

# Functional Requirements
| id | requirement | priority | source |
|---|---|---|---|
| F1 | `dependency_network.rankings_by_category` always has exactly the 5 CATEGORY_KEYS, each with exactly RANKING_KEYS; lists may be empty. | must | A1 |
| F2 | Node category: no `span` → `unknown`; else `language_analyzers.core.flags.path_flags(span.file_path)` with precedence vendored > generated > test; no flag → `production`. Each node belongs to exactly one category. | must | A3 |
| F3 | Per category and metric: the whole-graph metric values (same as `node_metrics`), restricted to nodes of that category, ordered by (-value, node_id), capped at 10. | must | A2 |
| F4 | `rankings` and all other existing fields are unchanged; schema stays `bottlenecks.v3`; JSON remains byte-deterministic for equal inputs. | must | A1 |
| F5 | Report input validation applies the same entry checks to `rankings_by_category` as to `rankings` (object of objects of arrays of {node_id, value number}); absent field is accepted (older v3 JSON). | must | A1 |
| F6 | HTML report has a "분류별 순위" section. Each category present in the JSON gets exactly one `<div data-category="<category>">` element inside it; that div contains one panel per metric key of the category, each listing that metric's entries (node ids); a category whose metric lists are all empty contains "순위 데이터가 없습니다." instead of panels, and populated categories do not contain it. | must | A4, user approval v2 |

# Errors
- rankings_by_category not an object / category not an object / metric not an array / entry missing node_id or non-numeric value — report validation raises the existing report input error with a JSON path starting `$.dependency_network.rankings_by_category` — no HTML is written.

# Cases
| id | level | input / state | expected result |
|---|---|---|---|
| C1 | normal | graph with nodes spanning src/app.py, tests/test_app.py, migrations/0001.py, vendor/lib.py, and a span-less node | each lands in production, test, generated, vendored, unknown respectively |
| C2 | edge | node path vendor/tests/test_x.py (vendored+test) and generated test path e.g. generated/foo_test.py | vendored; generated |
| C3 | boundary | a category with 9, 10, 11 nodes | 9, 10, 10 entries |
| C4 | boundary | empty snapshot | all 5 categories present, every metric list empty |
| C5 | normal | any graph | every rankings_by_category value equals node_metrics[node_id][metric]; order (-value, node_id) incl. ties |
| C6 | normal | same graph | `rankings` equal to the value produced by the pre-change algorithm (top-10 over all nodes) |
| C7 | error | report JSON with malformed rankings_by_category (4 variants of Errors) | report input error naming the path |
| C8 | edge | older v3 JSON without rankings_by_category | report renders without error |
| C9 | normal | report render of a C1 graph | each `data-category` div contains all 12 metric names and exactly its own category's node ids (including ids ranked only in some metrics); empty category's div has the no-data message, populated ones do not |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
|---|---|---|
| Functional suitability | yes | core behavior |
| Performance efficiency | no | O(n log n) sort over existing metrics; graphs ≤ few thousand nodes |
| Compatibility | yes | existing v3 consumers and older JSON must keep working |
| Interaction capability | no | HTML layout reuses existing panels; covered by F6 |
| Reliability | no | deterministic pure function, covered by F4 |
| Security | no | HTML escaping already applied by existing helpers; covered via C9 node ids escaped as elsewhere |
| Maintainability | no | small change |
| Flexibility | no | no config |
| Safety | no | offline analysis |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
|---|---|---|---|---|---|---|
| Q1 | Compatibility / interoperability | existing tests and older v3 JSON | existing suite pass count + C8 | 0 failures | automated: Test command; mutation: none | A1 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
|---|---|---|---|---|---|---|---|---|
| V1 | F2, C1 | analyze_bottlenecks output | unit | equivalence partitioning | production, test, generated, vendored, unknown | 100% | node appears only in its category's lists | Test command |
| V2 | F2, C2 | analyze_bottlenecks output | unit | decision table | rules: vendored+test→vendored, generated+test→generated | 100% | expected single category | Test command |
| V3 | F3, C3, C4 | analyze_bottlenecks output | unit | boundary value analysis (3-value) | 9,10,11 nodes; 0 nodes | 100% | lengths 9,10,10; empty lists with all keys (F1) | Test command |
| V4 | F3, F4, C5, C6 | analyze_bottlenecks / bottlenecks_to_json | unit | equivalence partitioning | value equality, tie order, rankings unchanged, byte-identical JSON | 100% | as Cases | Test command |
| V5 | F5, C7, C8 | report render entry | unit | equivalence partitioning | 4 malformed variants, absent field | 100% | error with path / success | Test command |
| V6 | F6, C9 | rendered HTML, per `data-category` div | unit | equivalence partitioning | populated category, empty category, metric-specific membership | 100% | per-div ids, 12 metric names, no-data only in empty div | Test command |
| V7 | Q1 | whole suite | all | none — regression | existing tests | 100% | pass | Test command |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
|---|---|---|---|
| A1 | Additive field, keep `rankings` and schema name | backward compatible | user rejected the options question and said "continue" after approving recommendations ("그렇게 해"); treated as delegation |
| A2 | Filter whole-graph scores, no per-category recomputation | keeps values comparable with rankings | same |
| A3 | Single category by precedence; span-less → unknown | ~65 span-less synthetic nodes in Now in Android | same |
| A4 | HTML shows category tables | | same |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
|---|---|---|---|
| F1 | C4 | V3 | Test command |
| F2 | C1, C2 | V1, V2 | Test command |
| F3 | C3, C5 | V3, V4 | Test command |
| F4 | C6 | V4, V7 | Test command |
| F5 | C7, C8 | V5 | Test command |
| F6 | C9 | V6 | Test command |
| Q1 | C8 | V7 | Test command |

# Workflow Control
| item | value |
|---|---|
| correction batches used | 1 |
| verifier invocations | 2 |
| open finding ids | B2 |

Audit state:
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
|---|---|---|---|---|---|
| V1, V2, V3, V4, V5, V7 | 1 | tests/test_category_rankings_v3.py (initial); Test command 562 passed | accepted | verifier 1; mutations M1 cap-before-filter (V3/V4 fail), M2 test-before-vendored (V2 fail), M3 reversed tie order (V4 fail): all detected | — |
| V6 | 2 | tests rewritten (data-category divs); M4, M5 detected; M6 (drop fan_in/fan_out panels) NOT detected | open | B1: section-slice check misses dropped metrics/entries; S1: F6 lacks per-category observable marker | awaiting user decision on S1 |

Execution ledger:
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
|---|---|---|---|---|
| 1 | verifier 1: B1 (V6 evidence gap), S1 (F6 per-category marker undefined; test author's challenge, main's advisory disposition rejected by verifier) | spec omitted per-category observable in HTML | user approved per-category data-category marker (spec v2) | S1 resolved; B1 correction queued |

| 2 | verifier 2: B2 substring metric check | fan_in ⊂ weighted_fan_in | M6 executed: 25 passed (escape confirmed) | limit; handoff |

# Version Log
## v2
- F6/C9/V6: add `data-category` div marker and per-metric completeness (verifier 1 findings S1, B1); user approved.
## v1
- Initial draft from handoff ec9d04784407ee5b observations.
