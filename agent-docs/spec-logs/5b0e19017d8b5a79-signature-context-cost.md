---
version: 2
run_id: 5b0e19017d8b5a79
status: aborted
base_commit: 7d169832420840158671369992f392d025284ff4
max_verifier_invocations: 2
handoff: agent-docs/handoff/fa00b92fe9819b57-agent-context-candidates.md
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 분석기 사용자(사람·에이전트) | 노드 주변 2-hop 코드를 구현부 없이 시그니처만 읽을 때의 토큰 비용을 기존 `hop_2_token_cost`와 나란히 본다 | symbol·file granularity의 node_metrics에 `hop_2_signature_token_cost`가 있고, 두 값의 차이로 시그니처만 읽을 때 줄어드는 맥락 비용을 알 수 있다 |
| I2 | 분석기 사용자 | 이 지표의 상위 노드를 다른 지표처럼 순위로 본다 | bottleneck JSON `rankings`, `rankings_by_category`, handout의 Production rankings, HTML 리포트 정렬·크기 선택에 새 지표가 나온다 |
| I3 | eval 실험(handoff `e16d433ef30afd87`) | 실제 저장소에서 계산 시간과 메모리가 크게 늘지 않는다 | R1에서 nowinandroid·vendure wall time과 최대 RSS가 base 대비 정해진 한도 안이다 |

# Scope
In scope:
- 노드별 시그니처 비용 정의(symbol: 노드 `signature`, file: 소속 symbol 시그니처의 합).
- `GraphAnalyzer.analyze`에 `hop_2_signature_token_cost` 지표와 `top_hop_2_signature_cost` 순위 추가.
- `bottlenecks/core.py` `RANKING_KEYS`에 새 지표 추가(`rankings`, `rankings_by_category`).
- `versions.analysis`를 "7"로 올림. 스키마 이름(`bottlenecks.v6` symbol, `bottlenecks.v9` file)은 유지.
- HTML 리포트(`renderers/html/static/app.js` `definitions`)와 `report/bottlenecks/generate.py` `METRIC_DEFINITIONS`에 새 지표 정의 추가.

Out of scope:
- 언어 분석기의 `signature` 추출 규칙 변경(Python·TS·Kotlin 현재 값 그대로 사용).
- framework 노드(endpoint, router, DI 등)와 configuration 노드에 시그니처를 새로 만드는 일.
- `hop_2_token_cost` 및 기존 9개 지표 값의 변경.
- HTML 개요의 `core` 카드 6개 구성 변경.
- 문서→코드 참조(D, 별도 spec).
- ADR `31d2dee6912427d5` 수정(완료 후 사용자에게 제안만 한다).

# Paths
Implementation: analysis/graph_metrics.py, analysis/file_graph.py, bottlenecks/core.py, report/bottlenecks/generate.py, renderers/html/static/app.js
Tests: tests/
Test command: .venv/bin/python -m pytest -q
Review evidence: R1 real-repo run — main이 GCP VM `na-eval`(n2-highmem-16, asia-northeast3-a)에서 `~/nowinandroid`, `~/vendure`(eval 고정 commit)에 대해 base_commit 분석기와 변경 후 분석기를 file·symbol granularity로 `/usr/bin/time -v`와 함께 실행한다(`python -m code_analyzer.cli <clone> <-f android | -f nestjs> --granularity <g> -o <out>/a.html --bottlenecks <out>/b.json`). 기록: wall time, 최대 RSS, 기존 10개 지표 값의 base 대비 차이 수(기대 0, `component_synth_*` fallback 비용 ±1 예외는 A7), 새 지표의 `hop_2_token_cost` 대비 총합 비율. 산출물 scratchpad `signature-cost-r1/summary.md`, 요약은 Execution ledger에 남긴다. R2 — main이 생성된 file·symbol HTML을 브라우저로 열어 정렬·크기 선택 목록과 용어 설명에 새 지표가 나오고 core 카드 6개가 그대로인지 확인한다.
Fuzzing: none — 새 계산은 기존 2-hop 집합 위의 정수 합이며 입력 표면이 그래프 구조뿐이다. 무작위 그래프 비교는 V3(random testing)이 맡는다.
Mutation tool: main이 scratchpad의 AST mutation 스크립트(비교·불리언·상수·조건 부정)를 base_commit 이후 변경된 Implementation Python 줄에 적용한다. 최대 30개 표본, seed 20261022. 실행 명령 `.venv/bin/python -m pytest -q -p no:cacheprovider -x -n 0 <이번 run이 추가·수정한 테스트 파일>`. 생존율 임계 40%.

# Signatures
GraphAnalyzer.analyze(nodes, edges, project_path=None) -> dict  # node_metrics 행에 "hop_2_signature_token_cost": float, 결과에 "top_hop_2_signature_cost": list 추가
bottlenecks.core.RANKING_KEYS: tuple  # 마지막에 "hop_2_signature_token_cost" 추가
analysis.file_graph.to_file_architecture(architecture, snapshot) -> FileArchitecture  # 파일 노드 metadata에 "signature_token_estimate": int 추가

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F1 | 노드 n의 시그니처 비용 sig(n): `signature`가 비어 있지 않은 문자열이면 `min(token_cost(n), estimate_tokens(signature))`, 아니면 `token_cost(n)`. `token_cost(n)`은 기존 `token_cost` 지표 값이다 | must | I1 |
| F2 | 파일 노드(file granularity)의 sig: `to_file_architecture`가 파일에 속한(`node_files`가 그 파일인) 원본 노드 중 `signature`가 비어 있지 않은 노드의 `estimate_tokens(signature)` 합 S를 `metadata.signature_token_estimate`에 기록한다. 그런 노드가 없으면 키를 넣지 않는다. 키가 있으면 sig = `min(token_cost, S)`, 없으면 sig = `token_cost`. boundary 노드는 token_cost가 0이므로 sig도 0 | must | I1 |
| F3 | `hop_2_signature_token_cost(n)` = n을 제외한 무방향 2-hop 이웃 집합(`hop_2_token_cost`와 같은 집합) 각 노드 m에 대해 `sig(m) × round(10 × 배율(m))`을 더하고 10으로 나눈 값. 배율은 `effective_token_cost` 계산에 쓰는 기존 비용 배율이다. 따라서 모든 노드에서 0 ≤ 새 지표 ≤ `hop_2_token_cost` | must | I1 |
| F4 | BFS 경로, bitset 경로, 혼합 경로가 같은 그래프에서 같은 새 지표 값을 낸다. `neighborhood_strategy` 선택 조건과 값은 base와 같다 | must | I1 |
| F5 | `analyze()` 결과에 `top_hop_2_signature_cost`가 있고, `top_hop_2_cost`와 같은 규칙(boundary 제외, 상위 10개, 내림차순)으로 새 지표를 정렬한다 | must | I2 |
| F6 | `RANKING_KEYS` 마지막에 `hop_2_signature_token_cost`가 추가되어 bottleneck JSON `rankings`와 `rankings_by_category`의 각 category에 새 지표의 상위 10개(값 내림차순, 동점은 node_id 오름차순)가 나온다 | must | I2 |
| F7 | node_metrics 행(analyze 결과, bottleneck JSON, 노드 `metadata.analysis`)의 키 집합은 기존 10개 + `hop_2_signature_token_cost`, 정확히 11개다. 기존 10개 지표 값은 base와 같다(A7 예외) | must | I1 |
| F8 | bottleneck JSON의 `versions.analysis`는 "7"이다. `schema` 값은 base와 같다(symbol `bottlenecks.v6`, file `bottlenecks.v9`). `report/bottlenecks/generate.py`와 `bottlenecks/delta.py`는 기존처럼 이 스키마를 받는다 | must | A1 |
| F9 | `METRIC_DEFINITIONS`에 새 지표의 한국어 설명이 있다. `app.js` `definitions`에 새 지표가 있고 `core`(앞 6개)는 base와 같은 순서·구성이다. 렌더링된 HTML의 정렬·크기 선택 목록과 용어 설명에 새 지표가 나온다 | must | I2 |
| F10 | handout의 `## Production rankings`에 새 지표 순위 블록이 다른 키와 같은 형식으로 나온다 | should | I2 |

# Errors
- 노드 `signature`가 문자열이 아닌 값(None 외)일 때 — 예외 없이 시그니처 없음으로 처리 — sig = token_cost.
- `metadata.signature_token_estimate`가 없거나 음수가 아닌 정수가 아닐 때 — 예외 없이 키 없음으로 처리 — sig = token_cost.
- 빈 그래프, 단일 노드 — 예외 없음 — 단일 노드의 새 지표 0.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | a–b–c 경로, a·c는 signature 있음(본문보다 짧음), b는 없음, 배율 1 | b의 새 지표 = sig(a)+sig(c); a의 새 지표 = token_cost(b)+sig(c) |
| C2 | normal | 배율 0.1(generated) 노드와 0(vendored) 노드가 이웃 | 각 이웃 기여가 sig × round(10×배율)/10 |
| C3 | boundary | signature 토큰이 token_cost보다 큰 노드 | sig = token_cost(새 지표 = hop_2 해당 기여와 같음) |
| C4 | boundary | signature가 빈 문자열 `""` | sig = token_cost |
| C5 | boundary | 노드 63개와 64개 고밀도 그래프(bitset 하한 경계), 연결 요소 하나는 bitset·하나는 BFS | 세 경로 모두 brute-force 기대값과 같음, strategy 값은 base 규칙대로 |
| C6 | normal | file granularity: 파일 X에 signature 있는 symbol 2개(토큰 3, 4)와 없는 symbol 1개 | X `metadata.signature_token_estimate` = 7, sig(X) = min(token_cost(X), 7) |
| C7 | edge | file granularity: signature 있는 symbol이 없는 파일 | `signature_token_estimate` 키 없음, sig = token_cost |
| C8 | edge | boundary 노드(file granularity, token_cost 0)가 이웃 | 기여 0 |
| C9 | error | signature가 정수 등 비문자열, `signature_token_estimate`가 -1·문자열·bool | 예외 없음, sig = token_cost |
| C10 | edge | 빈 그래프, 단일 노드 | 예외 없음, 단일 노드 키 11개, 새 지표 0 |
| C11 | normal | fixture CLI(file·symbol) bottleneck JSON | `rankings`·`rankings_by_category`에 새 키, versions.analysis "7", schema 불변, 기존 지표 값 불변 |
| C12 | normal | 렌더링된 HTML과 handout | 새 지표 정의·선택 목록·순위 블록 존재, core 6개 불변 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 새 지표 값의 정확성 |
| Performance efficiency | yes | 2-hop 합을 한 번 더 계산하므로 실제 저장소 시간·메모리 증가를 제한해야 한다 |
| Compatibility | yes | 기존 지표 값과 스키마 소비자(generate.py, delta.py, app.js)가 깨지지 않아야 한다 |
| Interaction capability | yes | 리포트 용어 설명이 사용자가 지표를 이해하게 해야 한다 |
| Reliability | yes | 비정상 signature 값에 예외 없이 동작 |
| Security | no | 새 입력 표면 없음(기존 그래프 값만 사용) |
| Maintainability | yes | 3개 이웃 계산 경로가 같은 값을 내야 한다(중복 구현 위험) |
| Flexibility | no | 설정 가능한 항목을 추가하지 않는다 |
| Safety | no | 물리·인명 위험 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Functional suitability / correctness | 무작위 그래프의 새 지표 | brute-force 독립 계산 대비 불일치 노드 수 / 개 | 0, 이하 | V3 | I1 |
| Q2 | Performance efficiency / time behaviour, resource utilization | nowinandroid·vendure, file·symbol | (변경 후 wall time / base wall time), (변경 후 최대 RSS / base 최대 RSS) / 비율 | 각 ≤ 1.10 | R1 | I3 |
| Q3 | Compatibility / co-existence | fixture 4개 file·symbol의 기존 10개 지표 | base 대비 값이 다른 (노드, 지표) 수 / 개 | 0(A7 예외) | V6 | F7 |
| Q4 | Interaction capability / learnability | HTML·generate.py 용어 설명 | 새 지표 정의 존재와 core 6개 순서 / 예·아니오 | 존재, core 불변 | V8, R2 | F9 |
| Q5 | Reliability / fault tolerance | C9 비정상 값 | 예외 발생 수 / 개 | 0 | V5 | Errors |
| Q6 | Maintainability / testability | BFS·bitset·혼합 경로 | 경로 간 불일치 노드 수 / 개 | 0 | V3 | F4 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | F1, F3, C1–C4 | `GraphAnalyzer.analyze` node_metrics | unit; 손으로 만든 작은 그래프 | equivalence partitioning | P1 signature 있음·짧음, P2 없음(None), P3 빈 문자열, P4 signature가 token_cost 이상, P5 배율 1, P6 배율 0.1, P7 배율 0 | 100% | 새 지표 = 테스트가 독립 계산한 기대값 | pytest |
| V2 | F1, F3, C3 | `GraphAnalyzer.analyze` | unit | boundary value analysis (2-value) | B1 estimate_tokens(signature) = token_cost, B2 = token_cost + 1 | 100% | B1·B2 모두 sig = token_cost; 바로 아래(token_cost − 1)는 sig = token_cost − 1 | pytest |
| V3 | F3, F4, C5, Q1, Q6 | `GraphAnalyzer.analyze` | unit; 고정 시드 무작위 그래프 | random testing | S1 BFS 전용, S2 exact_bitset, S3 exact_hybrid, S4 63/64노드 경계 | 100% | 전 노드 새 지표 = brute-force(무방향 2-hop 집합, 자기 제외, sig × round(10×배율) / 10 합); 0 ≤ 새 지표 ≤ hop_2_token_cost; strategy 값 base 규칙 | pytest |
| V4 | F2, C6–C8 | `to_file_architecture` 파일 노드와 file granularity analyze | unit/integration | equivalence partitioning | P1 signature 있는 symbol 여럿, P2 없음, P3 일부만 있음, P4 boundary 이웃 | 100% | `signature_token_estimate` 값·부재와 sig 기대값 일치 | pytest |
| V5 | Errors, C9, C10, Q5 | `GraphAnalyzer.analyze`, file granularity | unit | error guessing | G1 signature 정수, G2 signature 리스트, G3 estimate -1, G4 estimate 문자열, G5 estimate bool, G6 빈 그래프, G7 단일 노드 | none — experience-based | 예외 없음, sig = token_cost, 단일 노드 키 11개 | pytest |
| V6 | F6, F7, F8, C11, Q3 | CLI bottleneck JSON(file·symbol) | integration; fixture 4개 × granularity 2 중 base choice: fastapi-realworld file을 기준으로 다른 fixture 3개와 symbol을 한 번씩 바꿈 | combinatorial (base choice) | K1 fastapi-realworld file, K2 typescript-nestjs-realworld file, K3 android-nowinandroid file, K4 futuramaapi file, K5 fastapi-realworld symbol | 100% | 새 순위 키 존재·정렬 규칙, versions.analysis "7", schema 불변, 새 지표 키 제거 후 기존 지표 base golden과 같음(A7) | pytest |
| V7 | F5 | `analyze()` 결과 | unit | equivalence partitioning | P1 boundary 노드 포함 그래프, P2 노드 11개 이상 | 100% | `top_hop_2_signature_cost`가 boundary 제외, 상위 10개, 내림차순 | pytest |
| V8 | F9, F10, C12, Q4 | 렌더링된 HTML(playwright), `METRIC_DEFINITIONS`, handout | end-to-end; file·symbol 각 1 | equivalence partitioning | H1 file select·tooltip, H2 symbol select·tooltip, H3 core 카드 6개 순서, H4 METRIC_DEFINITIONS, H5 handout 순위 블록 | 100% | 새 지표 존재, core [pagerank, betweenness_centrality, hop_2_token_cost, weighted_centrality_cost, fan_in, fan_out] | pytest + R2 |
| V9 | 전 요구 | 전 표면 | unit/integration | error guessing | G1 자기 노드를 집합에 포함, G2 배율 미적용, G3 bitset 경로가 hop_2 비용 plane을 재사용, G4 file 노드가 시그니처 합 대신 첫 symbol만 씀, G5 min 대신 signature 비용 그대로, G6 RANKING_KEYS 순서 변경으로 기존 키 순서 깨짐, G7 generate.py가 새 키를 거부 | none — experience-based | 각 추측 결함이 테스트로 거부됨 | pytest |
| V10 | Q2 | 실제 저장소 | review | — (measurement) | nowinandroid file·symbol, vendure file·symbol | 100% | 비율 ≤ 1.10 | R1 |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v1 — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| A1 | 스키마 이름 유지, `versions.analysis` "7" | 키 추가만 있고 generate.py·app.js·handout은 순위 dict를 일반적으로 순회한다. `bottlenecks/delta.py`는 node_metrics·rankings·versions를 읽지 않는다(grep 확인). generate.py는 rankings를 키 무관하게 순회한다 | pending |
| A2 | 지표 이름 `hop_2_signature_token_cost`, 순위 이름 `top_hop_2_signature_cost` | 기존 이름 규칙(`hop_2_token_cost`, `top_hop_2_cost`) | pending |
| A3 | signature 없는 노드는 전체 비용으로 센다(축소 불가로 간주) | framework·configuration 노드 시그니처 0%; 0으로 세면 비용을 과소평가 | pending |
| A4 | 파일 sig는 소속 symbol 시그니처 합(중첩 class/method 모두 포함), import·상수·주석은 세지 않는다 | 측정(fixture 4개)에서 file 비율 0.17–0.46; skeleton 뷰의 근사이며 과소평가 가능 | pending |
| A5 | 순위 키 추가(ADR `31d2dee6912427d5` 기준과 충돌) | 사용자 답변 "지표 + 순위". 측정: symbol Spearman 0.95–0.99, top-10 5–8/10; file 0.87–1.00, 7–9/10 | user answer |
| A6 | HTML `core` 카드는 바꾸지 않고 정렬·크기 선택과 용어 설명에만 추가 | core는 `Object.keys(definitions).slice(0, 6)`이라 정의 위치로 결정됨 | pending |
| A7 | android symbol의 `component_synth_*` fallback 비용 ±1과 그 2-hop 이웃 hop_2 ±1은 기존 부수 효과로 허용 | fallback 비용이 `metadata.analysis` 직렬화 길이를 포함(spec-log 09e1bf05d439475e 원장 2b). 새 지표 키가 직렬화 길이를 늘린다 | pending |
| A8 | Q2 임계 1.10 | 이웃 집합 계산을 공유하면 증가가 작을 것으로 예상; 근거 없는 추정 | pending |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F1 | C1–C4, C9 | V1, V2, V5, V9 | pytest |
| F2 | C6–C8 | V4, V9 | pytest |
| F3 | C1, C2, C5 | V1, V3, V9 | pytest |
| F4 | C5 | V3 | pytest |
| F5 | — | V7 | pytest |
| F6 | C11 | V6, V9 | pytest |
| F7 | C10, C11 | V5, V6 | pytest |
| F8 | C11 | V6, V9 | pytest |
| F9 | C12 | V8 | pytest + R2 |
| F10 | C12 | V8 | pytest |
| Q2 | — | V10 | R1 |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 0 |
| verifier invocations | 0 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V1–V10 | 1 | — | pending | — | — |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 0 | 사전 측정: 기존 hop_2 재현 오차 0, symbol Spearman 0.95–0.99·top-10 5–8/10, file 0.87–1.00·7–9/10, 비용 비율 symbol 0.49–0.70·file 0.17–0.46 | — | scratchpad `cd/sig2.py`, `cd/sig3.py` | 사용자 결정 A5의 근거 |

# Version Log
## v1
- 초안. 이해 라운드 확인(C/D 분리, C→D), C 형태 "지표 + 순위" 사용자 답변.
## v2
- 승인 전 중단(aborted). 사용자 결정 "aborted하고 D로". 이유: 순위가 hop_2_token_cost와 거의 같고(Spearman symbol 0.95–0.99, file 0.87–1.00), file 단위 시그니처/전체 비율의 노드 간 폭이 좁아(p10–p90 futuramaapi 0.16–0.20, nestjs 0.21–0.24, nowinandroid 0.12–0.21) 노드별 새 정보가 적다. agent 행동 가정에 기대는 지표이며 eval 실험의 입력이 아니다. lifecycle start·telemetry는 실행하지 않았다.
