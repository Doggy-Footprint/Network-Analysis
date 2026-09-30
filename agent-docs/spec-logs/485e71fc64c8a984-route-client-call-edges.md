---
version: 2
run_id: 485e71fc64c8a984
status: complete
base_commit: dc2101909a93277f2ca867af2512e7dd04caea26
max_verifier_invocations: 2
handoff: agent-docs/handoff/db77d50f78afc60d-route-client-call-edges.md
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| UI1 | repository analyst | Connect client HTTP calls to the FastAPI route handlers they target by path string | A single CLI run over one project emits `CALLS_ROUTE` edges from TypeScript call sites and Android Retrofit endpoints to FastAPI endpoint nodes |
| UI2 | repository analyst | Analyze several analyzers in one run | `-f` and `-l` may be repeated and mixed; the merged graph feeds HTML, JSON and bottlenecks output |

# Scope
In scope:
- CLI: `-f/--framework` and `-l/--language` repeatable and mixable; analyzers run in argv order on the same `project_path` and snapshot; node/edge sets merged; route matching pass over the merged set.
- TypeScript analyzer: collect HTTP client call sites (fetch, axios module calls, axios instances incl. `axios.create({baseURL})`, same file or imported via relative import of an exported const).
- Route matching: exact matching of normalized (method, path) between client call sites/Retrofit endpoints and FastAPI endpoints.
- New relation `CALLS_ROUTE`.

Out of scope:
- Retrofit `baseUrl` from `Retrofit.Builder` (Retrofit endpoint path is used as declared).
- Non-FastAPI servers; other HTTP clients (ky, superagent, XMLHttpRequest, Kotlin OkHttp direct calls).
- Unresolved/external route nodes; edges for zero-candidate calls.
- Mermaid for multi-analyzer runs.
- Changing single-analyzer output.

# Paths
Implementation: code_analyzer/cli.py, language_analyzers/typescript/analyzer.py, language_analyzers/typescript/http_calls.py, language_analyzers/core/graph_models.py, framework_analyzers/route_matching.py, analysis/, renderers/
Tests: tests/test_route_client_call_edges.py, tests/test_cli_multi_analyzer.py, tests/test_typescript_http_calls.py
Test command: .venv/bin/python -m pytest -q
Review evidence: none — all obligations are automated.

# Signatures
language_analyzers.core.graph_models.RelationKind.CALLS_ROUTE == "CALLS_ROUTE"
TypeScriptAnalyzer(...).analyze() -> result with attribute `http_calls: list[HttpCallSite]` (not added to nodes/edges)
HttpCallSite(source_id: str, http_method: Optional[str], path: Optional[str], evidence: SourceSpan)   # method/path None when not statically resolvable
framework_analyzers.route_matching.normalize_route_path(path: str) -> Optional[str]
framework_analyzers.route_matching.match_routes(nodes: list[GraphNode], http_calls: list[HttpCallSite]) -> tuple[list[GraphEdge], dict]   # edges, stats
CLI: `code-analyzer PATH [-f FRAMEWORK]... [-l LANGUAGE]... [other existing flags]`

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| FR1 | `-f` and `-l` are repeatable and mixable; analyzers run in argv order. No `-f`/`-l` → `fastapi` only (current default). Only `-l X` → that language only (current behavior). A repeated identical value is a parser error. | must | user decision |
| FR2 | Single-analyzer runs produce output identical to the base commit (HTML, JSON, bottlenecks, stdout), with no `CALLS_ROUTE` edges and no `route_matching` stats key. | must | compatibility |
| FR3 | Multi-analyzer runs merge nodes and edges in argv order; `report_collections` concatenated; `stats["analysis"]` computed once over the merged graph; `stats["route_matching"]` = `{"matched": n, "ambiguous": n, "unmatched": n, "unresolvable": n}`; dashboard `framework_label` = labels joined by ` + ` in argv order. | must | user decision |
| FR4 | Duplicate node id across analyzers → stderr `[!] Error: duplicate node id across analyzers: <id>` (first duplicate in merge order), exit code 1, no output files written. | must | user decision |
| FR5 | `--mermaid` with ≥2 analyzers → argparse error (exit 2). `--entrypoint` valid iff `fastapi` is among `-f`. `--no-models/--no-deps/--no-language-graph` apply to every framework analyzer. | must | user decision |
| FR6 | TS call-site collection: `fetch(url[, init])` (method from `init.method` string literal, default GET); `axios.<get|post|put|patch|delete|head|options>(url, ...)`; `axios(config)` / `axios.request(config)` with object literal `url`/`method` (default GET); same calls on an axios instance `x` where `const x = axios.create({baseURL: <literal>})` is declared at module scope in the same file or imported by named/default import through a relative import resolving to a file exporting it. `url` must be a string literal or template string; otherwise path=None (unresolvable). Non-literal method → method=None. `source_id` = innermost enclosing function/method that exists as a node in the TS graph (anonymous callbacks and other non-node scopes are skipped outward), else the module node id. | must | user decision |
| FR7 | Path normalization: drop scheme+host (`https?://host[:port]`); a leading template interpolation before the first `/` (e.g. `${API}/x`) is dropped as base URL; instance baseURL path is prefixed; strip query string and fragment; ensure leading `/`; collapse `//`; strip trailing `/` (except root `/`); each segment that is `{...}`, `:name`, or contains `${...}` becomes `{}`. FastAPI `{name:path}` also becomes `{}`. Returns None for non-str input or the empty string `""`; a host-only URL such as `https://h` normalizes to `/`. A None result makes the client `unresolvable`. | must | user decision |
| FR8 | Matching: client (method, normalized path) equals FastAPI endpoint (`http_method` upper-case, normalized `full_path`) exactly. Clients: every `HttpCallSite` and every Retrofit endpoint node (`group == "retrofit_endpoint"`, metadata `http_method`, `path`). Server: nodes whose metadata has `full_path` and `http_method` from the FastAPI analyzer. | must | user decision |
| FR9 | 1 candidate → edge `CALLS_ROUTE`, `confidence=framework_inferred`, `resolution=unique_name`, `candidates=[]`. ≥2 → one edge to lowest node id (sorted), `resolution=ambiguous`, `candidates` = remaining ids sorted. 0 → no edge, counted `unmatched`. method or path None → no edge, counted `unresolvable`. Edge `evidence` = call-site span (TS) or endpoint span (Retrofit); `metadata["framework_rule"] = {"id": "http.client_calls_route", "specificity": "unique"|"ambiguous"}`. Duplicate (from, to) pairs from multiple call sites in the same function are kept as one edge. Stats count per client (call site or Retrofit endpoint), mutually exclusive: 1 candidate → matched, ≥2 → ambiguous only, 0 → unmatched, method/path None → unresolvable; deduped call sites are each counted; the four values sum to the number of clients. | must | user decision |
| FR10 | Weighted metrics treat `CALLS_ROUTE` via the existing confidence/resolution profile; no profile change. | must | handoff (edge-weight policy) |

# Errors
- Duplicate node id across analyzers — stderr message per FR4, exit 1 — no output files created.
- `--mermaid` with ≥2 analyzers — argparse error, exit 2 — nothing analyzed.
- `--entrypoint` without `-f fastapi` — argparse error, exit 2 (existing message kept).
- Same `-f`/`-l` value twice — argparse error, exit 2.
- Non-literal URL / method — non-exception: no edge, counted `unresolvable` — analysis continues.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | FastAPI `@router.get("/users/{id}")` with prefix `/api`; TS `fetch(\`/api/users/${id}\`)` in function `load` | edge `ts:...#load` → FastAPI endpoint, unique_name |
| C2 | normal | Retrofit `@GET("api/users/{userId}")`; same FastAPI route | edge retrofit endpoint → FastAPI endpoint |
| C3 | normal | `const api = axios.create({baseURL: "https://h/api"})` exported in `client.ts`; `import { api } from "./client"`; `api.post("/users")`; FastAPI POST `/api/users` | edge from caller function |
| C4 | normal | `fetch("/api/users", {method: "POST"})` vs GET-only route | unmatched=1, no edge |
| C5 | boundary | trailing slash `/api/users/`, query `?q=1`, `http://localhost:8000/api/users` | all match `/api/users` |
| C6 | boundary | `${API_URL}/api/users` | matches `/api/users` |
| C7 | boundary | root path `/` client and server | match |
| C8 | edge | two FastAPI apps both GET `/health` | one edge to lowest id, ambiguous, candidates = other id |
| C9 | error | `fetch(url)` with variable `url`; `fetch("/x", {method: m})` | unresolvable=2, no edges |
| C10 | error | `-f android -l kotlin` producing overlapping `kotlin:` ids | exit 1, duplicate id message, no outputs |
| C11 | error | `-f fastapi -f android --mermaid` | exit 2 |
| C12 | error | `-f fastapi -f fastapi` | exit 2 |
| C13 | normal | `-f fastapi` alone and `-l typescript` alone | outputs equal to base-commit behavior; no CALLS_ROUTE, no route_matching |
| C14 | normal | `-f fastapi -l typescript --bottlenecks b.json --json` | bottlenecks node set = merged nodes; JSON contains CALLS_ROUTE edges; label "FastAPI + TypeScript/JavaScript" |
| C15 | edge | `axios({url: "/api/users", method: "delete"})`, `axios.request({...})` | method normalized to DELETE; matches |
| C16 | edge | fetch at module top level | source_id = module node id |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | core behavior |
| Performance efficiency | no | matching is a dict lookup over existing nodes; no user target |
| Compatibility | yes | single-analyzer output must not change (FR2) |
| Interaction capability | no | CLI flags only; covered by FR |
| Reliability | yes | deterministic output for identical input |
| Security | no | no new input channels beyond repository files |
| Maintainability | no | no user target set |
| Flexibility | no | no user target set |
| Safety | no | no safety function |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| QR1 | Compatibility / co-existence | single-analyzer runs on existing fixtures (fastapi, android, python, kotlin, typescript) | compare JSON + bottlenecks output with base-commit expectations (existing suite + new equality test); count of differing outputs | = 0 | automated; mutation | FR2 |
| QR2 | Reliability / faultlessness | multi-analyzer run executed twice on same input | byte comparison of JSON and bottlenecks outputs; differing bytes | = 0 | automated | determinism |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VO1 | FR1, FR5, C11, C12 | argv combinations via `parse_args`/`main` | unit | decision table | rules: none; -l only; -f only; -f+-l mixed; order preserved; duplicate value; mermaid+multi; entrypoint with/without fastapi; mermaid single | 100% | analyzer order / exit code | Test command |
| VO2 | FR6, C1, C3, C9, C15, C16 | TS source strings → `http_calls` | unit | equivalence partitioning | fetch literal; fetch template; fetch init method; axios.<7 methods>; axios(config); axios.request; same-file instance; imported instance; non-literal url; non-literal method; top-level call; nested function | 100% | (source_id, method, path) tuples | Test command |
| VO3 | FR7, C5, C6, C7 | `normalize_route_path` | unit | boundary value analysis (2-value) + equivalence partitioning | scheme+host; port; leading interpolation; query; fragment; trailing slash; root; `//`; `{x}`; `:x`; `${x}`; partial `a-${x}`; `{p:path}`; missing leading slash | 100% | normalized string | Test command |
| VO4 | FR8, FR9, C1, C2, C4, C8 | `match_routes` over constructed nodes | unit | decision table | 0/1/≥2 candidates × method match/mismatch; unresolvable; Retrofit source; duplicate pair dedupe; edge fields (confidence, resolution, candidates, evidence, framework_rule); stats exclusivity and sum incl. deduped call sites; empty path → unresolvable | 100% | edges + stats | Test command |
| VO5 | FR3, FR4, C10, C14 | CLI on tmp project with FastAPI + TS + Android sources | integration | scenario | merged run success; label; stats keys; bottlenecks node count = merged; duplicate id failure w/o outputs | 100% | output files / exit | Test command |
| VO6 | FR2, QR1, C13 | single-analyzer runs | integration | equivalence partitioning | fastapi; android; python; kotlin; typescript | 100% | no CALLS_ROUTE, no route_matching key; existing suite green | Test command |
| VO7 | QR2 | multi-analyzer run twice | integration | metamorphic | repeat-run equality | 100% | identical bytes | Test command |
| VO8 | FR10 | weighted metrics on merged graph | unit | equivalence partitioning | unique_name CALLS_ROUTE edge; ambiguous CALLS_ROUTE edge | 100% | weight equals `min(confidence[framework_inferred], resolution[...])` of the loaded profile (0.3 for both under v1 profile) | Test command |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
| --- | --- | --- | --- |
| A1 | Retrofit baseUrl is not combined; declared path used | Builder baseUrl is often runtime config; user chose exact matching | user approved spec v1 (2026-09-30) |
| A2 | Leading `${...}` before first `/` treated as base URL | common `${API_URL}/x` idiom; would otherwise never match under exact rule | user approved spec v1 (2026-09-30) |
| A3 | Ambiguous edge targets lowest sorted id | mirrors existing `named_edge` pattern of one edge + candidates; deterministic | user approved spec v1 (2026-09-30) |
| A4 | No coverage tool installed → specification-based techniques only | `.venv` lacks `coverage` | user approved spec v1 (2026-09-30) |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| FR1 | C12 | VO1 | Test command |
| FR2 | C13 | VO6 | Test command |
| FR3 | C14 | VO5 | Test command |
| FR4 | C10 | VO5 | Test command |
| FR5 | C11 | VO1 | Test command |
| FR6 | C1, C3, C9, C15, C16 | VO2 | Test command |
| FR7 | C5, C6, C7 | VO3 | Test command |
| FR8 | C1, C2, C4 | VO4 | Test command |
| FR9 | C8, C9 | VO4 | Test command |
| FR10 | C8 | VO8 | Test command |
| QR1 | C13 | VO6 | Test command |
| QR2 | C14 | VO7 | Test command |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 2 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| VO1–VO4, VO6–VO8 | 2 | tests/test_cli_multi_analyzer.py, tests/test_route_client_call_edges.py, tests/test_typescript_http_calls.py @ 686 passed | accepted | verifier 1 accepted; verifier 2 retained; M1 (ambiguous counted as matched) and M2 (dedupe by from_id) detected by VO4 tests | — |
| VO5 | 2 | tests/test_cli_multi_analyzer.py duplicate-id tests with independent reference-run oracle | accepted | F1 closed by verifier 2; M3 (report last duplicate) detected | reopened by F1 in verifier 1 |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 1 | test-implementer spec challenges: stats semantics, nested source_id, normalize None undefined | spec gap | user decisions → v2 | amend; redispatch both roles |
| 2 | F1: duplicate-id test did not pin first duplicate (verifier 1) | test defect | composition oracle from single-analyzer runs + reversed argv test; A2 Retrofit missing method/path test added | 686 passed; verifier 2 pass |

# Version Log
## v1
- Initial draft from handoff db77d50f78afc60d and user decisions (both clients, mixed repeatable -f/-l, axios instances, exact matching, CALLS_ROUTE matched-only, duplicate id error, mermaid multi error).
## v2
- User decisions on test-implementer spec challenges: stats per client and mutually exclusive (as implemented); source_id skips non-node scopes to nearest graph node; empty string path normalizes to None (unresolvable).
