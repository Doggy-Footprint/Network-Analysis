---
version: 1
run_id: 74b78d6823637a21
status: draft
base_commit: 6444895451a89f4450b9123b7beb17b11506e534
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 저장소를 검토하는 사람·agent | 중심성이 높은데 테스트에서 직접 닿지 않는 파일을 찾는다 (근거: SWE-agent arXiv 2405.15793, 테스트 실행 피드백) | file granularity bottleneck JSON에 `untested_hub` 후보가 나온다 |
| I2 | 저장소를 검토하는 사람·agent | 저장소 안의 production 코드와 정적 연결이 없는 파일을 찾는다 (근거: arXiv 2506.24015, 구조적으로 고립된 버그는 맥락을 다 줘도 어렵다) | file granularity bottleneck JSON에 `isolated_node` 후보가 나온다 |
| I3 | 기존 사용자 | 기존 설정 파일, baseline, 후보가 깨지지 않는다 | 기존 edge_weights YAML이 그대로 로드되고, 기존 후보 종류의 출력이 바뀌지 않으며, `--baseline` 비교 결과가 같다 |

# Scope
In scope: file granularity(`--granularity file`, 기본값)에서 두 후보 종류를 생성한다. edge_weights 설정에 선택 키 `untested_hub_top_n`을 추가한다. HTML 보고서와 bottleneck 보고서에 두 종류의 라벨, 설명, 대표 수치를 추가한다.
Out of scope: symbol granularity 후보. 전이적(간접) 테스트 도달 계산. 분석 대상 테스트를 실행하는 mutation 단계(후속 workflow). `bottlenecks/delta.py` 비교 대상 확장. schema 문자열 변경(`bottlenecks.v8` 유지).

# Paths
Implementation: bottlenecks/reach.py (new), bottlenecks/core.py, analysis/edge_weights.py, profiles/edge_weights.v1.yaml, report/bottlenecks/generate.py, renderers/html/static/app.js
Tests: tests/test_reach_candidates.py (new), tests/reach_support.py (new), tests/reach_evidence/ (new), 그리고 기존 tests/ 파일 조정(허용 범위: edge_weights key 집합 assertion에 `untested_hub_top_n` 추가, 후보 kind 목록·개수·golden·hash 비교에서 `untested_hub`·`isolated_node` 후보를 제외하고 비교, 보고서 kind 라벨 목록 assertion에 두 kind 추가. 약화 금지. 모든 변경은 `tests/reach_evidence/existing-tests.diff`에 기록)
Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','fastapi-official-template','android-nowinandroid','typescript-nestjs-realworld')]" && uv run -q --with-requirements requirements-dev.txt --with coverage python -m coverage run --branch --include=bottlenecks/reach.py -m pytest -q -p no:cacheprovider && uv run -q --with coverage python -m coverage report --fail-under=90
Review evidence: tests/reach_evidence/review.md — main이 4개 실제 fixture(futuramaapi, fastapi-realworld, android-nowinandroid, typescript-nestjs-realworld)의 두 후보 목록을 출력하고, 후보마다 경로와 근거 엣지를 열어 정의와 맞는지 확인한 기록. 기대 결과: 정의 위반 0건.
Fuzzing: main이 scratchpad에 작성한 stdlib harness, seed 20261019. 표면: `analyze_bottlenecks`(file granularity)에 무작위 합성 FileArchitecture(파일 1–60개, 무작위 경로 category, 무작위 relation·confidence·resolution·ambiguous candidates, 무작위 `untested_hub_top_n` 1–20). oracle property — (a) BottleneckInputError 외 예외 0, (b) `untested_hub` 수 ≤ N, (c) 모든 `isolated_node` 대상에 대해 C-B 정의의 static production 연결 수가 0, (d) 두 kind 외의 후보 목록이 기능 추가 전 참조 함수 결과와 같다. 예산 20,000 입력.
Mutation tool: main이 scratchpad에 작성한 AST mutation 스크립트(비교 연산자 교체, 경계 상수 ±1, 불리언 연산자 교체, 조건 부정, 집합 원소 제거). base_commit 이후 변경된 Implementation Python 줄만 대상. 최대 30개 표본, seed 20261019. 실행 명령 `uv run -q --with-requirements requirements-dev.txt python -m pytest -q -p no:cacheprovider -x tests/test_reach_candidates.py`. 생존율 임계 40%.

# Signatures
EdgeWeights.untested_hub_top_n: int  (선택 YAML 키, 없으면 10)
bottlenecks.reach.reach_candidates(architecture: FileArchitecture, metrics: Mapping[str, Mapping[str, Any]], top_n: int) -> list[Mapping[str, Any]]
candidate kind "untested_hub": metrics {"pagerank": float, "pagerank_rank": int, "top_n": int, "uncertain_test_edge_count": int}; evidence {"path": str, "uncertain_test_edges": [edge record]}; coverage "static_analyzer_relation"
candidate kind "isolated_node": metrics {"line_count": int, "framework_edge_count": int, "dynamic_edge_count": int, "uncertain_static_edge_count": int}; evidence {"path": str, "edges": [edge record]}; coverage "static_analyzer_relation"

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| R1 | 허브 후보군은 production category이고 boundary가 아닌 file 노드다. PageRank 내림차순, 같으면 node id 오름차순으로 정렬한 상위 `untested_hub_top_n`개다. | must | user answer (상위 N, PageRank) |
| R2 | 허브 중 확정 TESTS 엣지가 들어오지 않는 파일마다 `untested_hub` 후보를 하나 낸다. 확정 TESTS 엣지는 test category file에서 오고, resolution이 `exact` 또는 `unique_name`이며, `to_id`가 그 파일인 `TESTS` 엣지다. | must | I1 |
| R3 | `untested_hub` metrics의 `uncertain_test_edge_count`는 그 파일을 `to_id` 또는 ambiguous candidates로 가리키는 비확정 TESTS 엣지(resolution `ambiguous`/`unresolved`) 수다. evidence에 그 엣지들을 담는다. | must | 프로젝트 정의 (recall 우선, 불확실 관계 유지) |
| R4 | `isolated_node` 대상은 production category, boundary 아님, 확장자 ∈ {py, ts, tsx, js, jsx, mjs, cjs, kt}, line_count ≥ 1인 file 노드다. | must | D4, D5 |
| R5 | 대상 파일과 다른 production file 노드 사이의 엣지 중, 방향 무관, 자기 자신 제외, confidence ∈ {static_certain, static_inferred}, resolution ∈ {exact, unique_name}인 엣지(정적 연결)가 0개이면 `isolated_node` 후보를 낸다. test/generated/vendored 파일, boundary(외부) 노드와의 엣지는 세지 않는다. | must | user answer (고립 기준 세 항목) |
| R6 | `isolated_node` metrics는 production 파일과의 엣지 중 framework_inferred 수, dynamic_required 수, 정적이지만 ambiguous/unresolved인 수를 센다. evidence에 그 엣지들을 담는다. | must | 프로젝트 정의 (recall 우선) |
| R7 | 후보 id는 기존 `_candidate` 규칙(`"b:" + sha256(identifier)[:16]`)을 따르고 identifier는 `<file id>|untested_hub`, `<file id>|isolated_node`다. 후보 목록 정렬은 기존과 같이 (kind, id)다. | must | 기존 후보 규칙 |
| R8 | `untested_hub_top_n`은 선택 키다. 없으면 10이다. 있으면 int ≥ 1이어야 한다. 출력 JSON의 `edge_weights`에 항상 포함한다. | must | I3, D2 |
| R9 | 기존 후보 종류의 출력, `schema`(`bottlenecks.v8`), delta 결과는 바뀌지 않는다. symbol granularity 출력은 바뀌지 않는다. | must | I3, user answer (v8 유지) |
| R10 | 보고서(report/bottlenecks/generate.py, HTML app.js)는 두 kind의 한국어 라벨과 설명을 보여주고, 대표 수치는 `untested_hub`은 `pagerank_rank`, `isolated_node`은 `line_count`다. | must | Scope |

# Errors
- `untested_hub_top_n`이 int가 아니거나(bool 포함) 1 미만 — `EdgeWeightsError`(메시지에 키 이름 포함), CLI는 기존 설정 오류와 같은 종료 코드 — 출력 파일을 쓰지 않는다.
- 엣지가 없는 file 노드를 가리키는 등 입력 구조 오류 — 기존과 같이 `BottleneckInputError` — 보고서를 만들지 않는다.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | production 파일 3개 중 PageRank 1위가 test 파일에서 exact TESTS 엣지를 받고, 2위는 받지 않음, N=2 | 2위에만 `untested_hub`, `pagerank_rank` = 2 |
| C2 | boundary | 허브 후보군이 N개 미만(production 파일 1개, N=10) | 존재하는 파일만 대상, 오류 없음 |
| C3 | boundary | N=1, PageRank 동률 두 파일 | id가 작은 파일만 허브 |
| C4 | edge | 허브에 들어오는 TESTS 엣지가 ambiguous(candidates에 허브 포함)뿐 | `untested_hub` 생성, `uncertain_test_edge_count` = 1 |
| C5 | edge | 허브에 들어오는 TESTS 엣지가 unique_name | 후보 없음 |
| C6 | normal | production 파일 A가 다른 production 파일과 static_certain exact 엣지 없음, framework_inferred 엣지 1개만 있음 | A에 `isolated_node`, `framework_edge_count` = 1 |
| C7 | edge | A가 test 파일, vendored 파일, 외부 boundary 노드와만 static_certain 엣지 | A에 `isolated_node` |
| C8 | edge | A가 다른 production 파일에서 static_certain exact IMPORTS를 받음(들어오는 방향) | 후보 없음 |
| C9 | edge | A의 정적 엣지가 static_inferred ambiguous뿐 | `isolated_node`, `uncertain_static_edge_count` = 1 |
| C10 | boundary | line_count 0인 py 파일, 확장자 yaml 파일, test 파일 | 후보 없음 |
| C11 | edge | A의 엣지가 자기 자신으로 가는 것뿐 | `isolated_node` |
| C12 | error | YAML에 `untested_hub_top_n: 0`, `true`, `"3"` | 각각 `EdgeWeightsError` |
| C13 | normal | YAML에 키 없음(기존 profiles 파일) | 로드 성공, 값 10, 출력 `edge_weights.untested_hub_top_n` = 10 |
| C14 | normal | 4개 실제 fixture | 기존 kind 후보 목록이 base_commit 결과와 같고 schema가 `bottlenecks.v8` |
| C15 | normal | symbol granularity 실행 | 두 kind가 나오지 않음, 출력이 base_commit과 같음 |
| C16 | normal | HTML·bottleneck 보고서 렌더링 | 두 kind 라벨·설명·대표 수치가 표시됨 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 후보 정의가 정확해야 한다 |
| Performance efficiency | yes | 큰 저장소에서 분석 시간이 크게 늘면 안 된다 |
| Compatibility | yes | 기존 설정, baseline, 출력 소비자 |
| Interaction capability | yes | 보고서에서 두 kind를 이해할 수 있어야 한다 |
| Reliability | yes | 어떤 그래프 입력에도 정의된 오류 외 예외가 없어야 한다 |
| Security | no | 새 입력 표면이 없다(설정 키 하나, 기존 YAML safe_load) |
| Maintainability | yes | 새 로직을 한 모듈에 둔다 |
| Flexibility | no | 설치·이식 조건 변화 없음 |
| Safety | no | 물리적 위해와 무관 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Functional suitability / correctness | 두 kind 정의 | 참조 구현(테스트 쪽 독립 알고리즘)과의 후보 id 집합 일치, 합성 그래프 + 4 fixture | 불일치 0 | automated, review, mutation | R1–R7 |
| Q2 | Performance efficiency / time behaviour | fastapi-realworld, typescript-nestjs-realworld file granularity 분석 | 기능 on 실행 시간 / base_commit 실행 시간, 각 3회 중앙값 | ≤ 1.10 | automated (benchmark marker) | D7 |
| Q3 | Compatibility / interoperability | 기존 YAML, baseline JSON, 기존 kind 출력 | C13, C14, C15 및 기존 delta 테스트 통과 | 실패 0 | automated | I3 |
| Q4 | Interaction capability / learnability | 보고서 | C16 렌더링 확인 | 두 kind 모두 표시 | automated | R10 |
| Q5 | Reliability / fault tolerance | `analyze_bottlenecks` | fuzz harness property (a)–(d) | 위반 0 / 20,000 입력 | fuzz | D8 |
| Q6 | Maintainability / modularity | 새 후보 로직 | `bottlenecks/reach.py` branch coverage | ≥ 90% | automated (Test command) | D9 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | R1, C1, C2, C3 | `analyze_bottlenecks` file granularity, 합성 FileArchitecture | unit | boundary value analysis (3-value) | N ∈ {후보군−1, 후보군, 후보군+1}; 동률 순서 {id 작음, id 큼} | 100% | 허브 집합이 참조 정렬과 같다 | pytest |
| V2 | R2, R3, C1, C4, C5 | 같은 표면 | unit | decision table | 규칙: TESTS 엣지 {없음, exact, unique_name, ambiguous 포함, unresolved} × 출발 category {test, production} | 100% (10규칙) | 후보 유무와 `uncertain_test_edge_count`가 표와 같다 | pytest |
| V3 | R4, R5, R6, C6–C11 | 같은 표면 | unit | decision table | 규칙: 상대 {production, test, generated, vendored, boundary, 자기 자신} × confidence {static_certain, static_inferred, framework_inferred, dynamic_required} × resolution {exact, ambiguous}; 방향 {in, out}은 production·static_certain·exact 규칙에만 | 100% (선택된 50규칙: 6×4×2 + 방향 2) | 후보 유무와 metrics 수가 표와 같다 | pytest |
| V4 | R4, C10 | 같은 표면 | unit | equivalence partitioning | 확장자 {py, ts, tsx, js, jsx, mjs, cjs, kt, yaml, md}; line_count {0, 1}; category {production, test, generated, vendored} | 100% | 대상 여부가 R4와 같다 | pytest |
| V5 | R7 | 후보 id·정렬 | unit | equivalence partitioning | {id 형식, (kind,id) 정렬, 두 kind 동시 발생} | 100% | 참조 계산 id와 같다 | pytest |
| V6 | R8, C12, C13, Errors | `load_edge_weights` | unit | boundary value analysis (3-value) + equivalence partitioning | 값 {0, 1, 2, -1, true, "3", 1.0, 키 없음} | 100% | 0/-1/true/"3"/1.0 → EdgeWeightsError(키 이름 포함), 1/2 → 그 값, 없음 → 10 | pytest |
| V7 | R8, R9, C14, C15, Q3 | 4개 실제 fixture, CLI file·symbol | integration | equivalence partitioning | fixture 4개 × granularity 2 + delta(baseline=자기 자신) 1 | 100% | 두 kind 제외 시 base_commit 결과와 동일, schema v8, `edge_weights.untested_hub_top_n` 존재(file) | pytest, base_commit 결과는 `tests/reach_evidence/base_manifest.json` |
| V8 | Q1 | 4개 실제 fixture | integration | metamorphic testing | 관계: (M1) N을 늘리면 `untested_hub` 집합은 부분집합 관계를 유지(단조 증가), (M2) test 파일을 snapshot에서 제거하면 `untested_hub` 집합은 커지거나 같다, (M3) 고립 파일과 production 파일 사이에 static_certain exact 엣지를 추가하면 그 파일의 `isolated_node`가 사라진다 | 100% (3관계 × 4 fixture) | 관계 성립 | pytest |
| V9 | R10, C16, Q4 | 보고서 생성, HTML | integration | equivalence partitioning | {generate.py 라벨, 설명, 대표 수치, app.js 라벨, 대표 수치} × 2 kind | 100% | 문자열 존재와 값 표시 | pytest (기존 browser 테스트 방식) |
| V10 | Q2 | 2 fixture | integration (benchmark marker) | none — measurement | 2 fixture | 100% | 비율 ≤ 1.10 | `pytest -m benchmark` 결과를 `tests/reach_evidence/benchmark.md`에 기록 |
| V11 | Q5 | `analyze_bottlenecks` | fuzz | random testing | property (a)–(d) | 20,000 입력 | 위반 0 | main 실행, 결과를 ledger에 기록 |
| V12 | Q6 | `bottlenecks/reach.py` | unit | branch testing | coverage.py branch | ≥ 90% | Test command 통과 | Test command |
| V13 | R1–R7 | 실제 fixture 후보 | review | none — experience-based | 후보마다 정의 위반 여부 | none — experience-based | 위반 0 | `tests/reach_evidence/review.md` |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| D1 | file granularity에서만 생성한다 | 기본 granularity이고 structure 후보도 file 전용. symbol은 노드 종류가 많아 의미가 다르다 | pending |
| D2 | `untested_hub_top_n`은 선택 키, 기본 10 | loader가 정확한 키 집합을 요구하므로 필수 키로 만들면 기존 사용자 YAML이 깨진다. 10은 기존 rankings 상위 10과 같다 | pending |
| D3 | 허브 후보군은 production category만 | test/generated/vendored 파일이 테스트되지 않는 것은 검토 대상이 아니다 | pending |
| D4 | 고립 대상은 분석 언어 소스 확장자만 | 설정·문서 파일은 원래 코드 엣지가 없어 모두 후보가 된다 | pending |
| D5 | line_count 0 파일은 고립 대상에서 제외 | 빈 `__init__.py` 등이 대량 후보가 된다 | pending |
| D6 | 직접 TESTS 엣지만 본다(전이 도달 없음) | 정적 직접 관계가 가장 확실한 사실. 전이 도달은 후속 mutation 단계가 다룬다 | pending |
| D7 | 성능 임계 1.10배 | 후보 계산은 엣지 1회 순회. 기존 benchmark marker 사용 | pending |
| D8 | fuzz 20,000 입력, seed 20261019 | 이전 workflow와 같은 예산 | pending |
| D9 | 새 로직은 `bottlenecks/reach.py`, branch coverage ≥ 90% | 이전 workflow 기준과 같다 | pending |
| D10 | 고립 판정에서 test 파일, 외부 라이브러리, generated/vendored 파일과의 엣지는 세지 않는다 | — | user answer |
| D11 | 허브 기준은 PageRank 상위 N개 | — | user answer |
| D12 | schema `bottlenecks.v8` 유지 | delta는 kind를 순환·위반만 비교 | user answer |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| R1 | C1, C2, C3 | V1, V8, V13 | pytest, review |
| R2 | C1, C5 | V2, V8, V13 | pytest, review |
| R3 | C4 | V2 | pytest |
| R4 | C10 | V3, V4 | pytest |
| R5 | C6, C7, C8, C11 | V3, V8, V13 | pytest, review |
| R6 | C6, C9 | V3 | pytest |
| R7 | — | V5 | pytest |
| R8 | C12, C13 | V6, V7 | pytest |
| R9 | C14, C15 | V7 | pytest |
| R10 | C16 | V9 | pytest |
| Q1–Q6 | — | V8, V10, V7, V9, V11, V12 | 위 표 |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 0 |
| verifier invocations | 0 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V1–V13 | 1 | none | pending | — | — |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |

# Version Log
## v1
- 초안. 사용자 답변(PageRank 상위 N, v8 유지, 고립 기준 세 항목)을 반영하고, mutation 단계는 후속 workflow로 분리.
