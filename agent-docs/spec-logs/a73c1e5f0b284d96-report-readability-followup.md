---
version: 3
run_id: a73c1e5f0b284d96
status: complete
base_commit: 68b5d01a4585f8e10482058a4bcb02ae5996fcd5
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
|---|---|---|---|
| UI-1 | 보고서 사용자 | 숨은 노드 검색 시 그래프가 예측 가능하게 확장된다 (이전 run SPEC-4) | 추가 요소 집합과 기존 위치 불변이 자동 검증된다 |
| UI-2 | 사용자 | 브라우저 리뷰 증거가 raw 콘솔 로그로 남는다 (RV-ARTIFACT-1, 사용자 결정) | local-reports/review/console-*.log 존재 |
| UI-3 | 사용자 | 이전 run 권고 3건 개선 | 라벨 화면 크기 ≥11px, 검색 후 이웃이 보이는 줌, 이유 문장 라벨 중복 제거 |

# Scope
In scope: FR-15의 이웃 추가 로직을 graph_model.js 순수 함수로 분리, M1 always-label 글자 크기, 숨은 노드 검색 후 줌, Bottlenecks #focus 이유 문장, RV-1 재수행(콘솔 raw 로그).
Out of scope: ADV-1(VO-18 category fixture; 사용자 결정으로 제외, handoff 대상), 이전 run의 나머지 FR 동작 변경.

# Paths
Implementation: report/m1/templates/graph_model.js, report/m1/templates/graph.js, report/bottlenecks/generate.py
Tests: tests/test_readability_followup.py, tests/test_readability_bottlenecks.py, tests/test_readability_m1.py
Test command: .venv/bin/python -m pytest -q --deselect tests/test_bottlenecks_contract.py::test_NA_05_outside_edge_raises_before_cli_writes --deselect tests/test_bottlenecks_contract.py::test_NA_06_outside_span_raises_before_cli_writes
Review evidence: RV-2 — 이 리포로 세 HTML(대시보드, bottlenecks, M1)을 생성해 Chrome 1440×900으로 열고, 각 페이지 스크린샷을 local-reports/review/screens/rv2-*.jpg, 콘솔 메시지 원문을 local-reports/review/console-<page>.log로 저장하고, 측정 시간과 판독 결과를 local-reports/review/RV-2.md에 기록

# Signatures
report/m1/templates/graph_model.js: `ReportGraphModel.expand(built, present, targetId) -> null | {nodes: string[], parents: string[], edges: string[], positions: {[id]: {x, y}}}` — `built` = `build(data)` 결과, `present` = 현재 Cytoscape에 있는 모든 노드(디렉터리 포함) id → `{x, y}` 위치 맵
report/m1/templates/graph_model.js: `ReportGraphModel.labelFontSize(zoom: number) -> number`
report/m1/templates/graph_model.js: `ReportGraphModel.focusZoom(fitZoom: number) -> number`
기존 `build`, `focus` 시그니처·동작 유지

# Functional Requirements
| id | requirement | priority | source |
|---|---|---|---|
| FR-1 | `expand`: targetId가 built에 없거나 디렉터리 노드면 null. targetId가 present에 있으면 빈 배열들과 빈 positions | must | SPEC-4 |
| FR-2 | `expand` 이웃 선택: target과 edge로 직접 연결된 비디렉터리 노드(자기 자신 제외, 중복 제거)를 연결 수 내림차순, 동점 id 오름차순 정렬해 상위 20개. 연결 수는 build의 weight 계산과 같은 정의(from/to로 등장한 connection 수) | must | SPEC-4 |
| FR-3 | `expand.nodes` = [target] ++ 선택된 이웃 중 present에 없는 것 (target 먼저, 이후 이웃 순위순). `parents` = nodes의 조상 디렉터리 중 present에 없는 것, 중복 없이 상위 조상이 하위보다 먼저. `edges` = 추가 후 양 끝이 모두 존재하고 한쪽 끝이 {target}∪선택된 이웃이며 present 간 기존 edge가 아닌 edge의 built element id(`"edge:" + connection.id`), 중복 없음 | must | SPEC-4 |
| FR-4 | `expand.positions` 키 집합 = `nodes` 집합(present 노드·디렉터리 위치는 포함하지 않음 → 기존 위치 불변). target 위치 = 순위가 가장 높은 present 이웃의 위치, 없으면 present에 있는 가장 가까운 조상 디렉터리 위치, 없으면 {0,0}. target 외 새 노드 k개(순위순 i=0..k-1)는 위치 (ax + 120·cos(2πi/k), ay + 120·sin(2πi/k)), (ax, ay)=target 위치 | must | SPEC-4 |
| FR-5 | graph.js는 숨은 노드 검색/focus 링크 시 `expand` 결과의 요소만 cy에 추가하고 `positions`만 적용하며 레이아웃을 다시 실행하지 않는다 | must | SPEC-4 |
| FR-6 | `labelFontSize(zoom)` = max(9, 11/zoom). graph.js는 readable·query 노드 라벨 font-size를 줌마다 이 값으로 갱신해 화면상 ≥11px | must | 사용자 결정 |
| FR-7 | `focusZoom(fitZoom)` = max(fitZoom, 1). 검색/focus 이동 시 대상 노드와 그 직접 이웃(보이는 것)에 padding 40으로 맞춘 줌을 구해 이 값으로 대상 노드 중심 이동 | must | 사용자 결정 |
| FR-8 | Bottlenecks #focus 이유 문장은 라벨을 포함하지 않고 측정 문장만 쓴다(예: "결과 40건 중 12건이 생략되었습니다."). 라벨은 `<strong>`에 한 번, 원문 target은 title에 유지 | must | 사용자 결정 |

# Errors
- expand에 알 수 없는/디렉터리 id — 반환 null — graph.js는 요소를 추가하지 않고 기존 "일치하는 표시 가능 node가 없습니다." 흐름 유지

# Cases
| id | level | input / state | expected result |
|---|---|---|---|
| C-1 | normal | 숨은 target, 이웃 3개(1개 present) | nodes=[target, 숨은 이웃 2], edges에 target–present 이웃 포함, positions 키=nodes |
| C-2 | boundary | 이웃 20개 / 21개 | 20개 전부 / 연결 수 최하위(동점 id 큰 쪽) 1개 제외 |
| C-3 | edge | target이 이미 present | 모두 빈 결과 |
| C-4 | error | 없는 id, 디렉터리 id | null |
| C-5 | edge | 조상 디렉터리 일부만 present | parents = 없는 조상만, 상위 먼저 |
| C-6 | boundary | labelFontSize(1.0)=11, (11/9)=9, (2)=9, (0.5)=22 | 식대로 |
| C-7 | boundary | focusZoom(0.3)=1, (1)=1, (1.6)=1.6 | 식대로 |
| C-8 | normal | 각 kind 후보 1개 render_report | #focus 각 li 텍스트에 라벨 정확히 1회 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
|---|---|---|
| Functional suitability | yes | FR 전체 |
| Performance efficiency | yes | 숨은 노드 검색 시간(QR-9 유지) |
| Compatibility | yes | 기존 테스트 유지 |
| Interaction capability | yes | 라벨 판독·검색 후 가시성 |
| Reliability | yes | 콘솔 error 0 |
| Security | no | 새 입력 경로 없음, 이스케이프는 기존 VO 유지 |
| Maintainability | no | 순수 함수 분리 자체가 FR로 다뤄짐 |
| Flexibility | no | 환경 변화 없음 |
| Safety | no | 해당 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
|---|---|---|---|---|---|---|
| QR-1 | Functional suitability / correctness | FR-1..FR-8 | VO 통과 비율 % | 100% | automated + mutation | spec |
| QR-2 | Performance / time behaviour | 이 리포 M1, Chrome 1440×900 | 로드→JS 평가 가능 초; 숨은 노드 검색→평가 가능 초 | ≤10초, ≤3초 | review RV-2 | 이전 QR-9 |
| QR-3 | Compatibility / co-existence | 기존 테스트 | Test command 결과 | 전부 통과(문구 계약 갱신은 기록) | automated | 이전 QR-2 |
| QR-4 | Interaction / operability | M1 fit 배율, 검색 후 | 스크린샷 판독 | always-label 라벨 판독 가능, 검색 후 대상과 이웃 라벨 보임 | review RV-2 | 사용자 결정 |
| QR-5 | Reliability / faultlessness | 세 페이지 로드 + M1 검색 | console-*.log의 error 수 | 0 | review RV-2 | RV-ARTIFACT-1 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
|---|---|---|---|---|---|---|---|---|
| VO-1 | FR-1, C-3, C-4 | expand via node | unit | equivalence partitioning | {알 수 없는 id, 디렉터리 id, present target, 숨은 target} | 100% | null / 빈 / 비어있지 않음 | automated |
| VO-2 | FR-2, C-2 | expand via node | unit | boundary value (2-value) | {이웃 20, 이웃 21(동점 id 제외 규칙), 중복 edge 2개가 같은 이웃, 자기 루프} | 100% | nodes 수·제외 노드 | automated |
| VO-3 | FR-3, C-1, C-5 | expand via node | unit | decision table | {이웃 present/숨음, 조상 present/없음(상위 먼저), edge: target–present, 숨은 이웃–present 비이웃, present–present 제외, 20위 밖 이웃 edge 제외} | 100% | 집합·순서 일치 | automated |
| VO-4 | FR-4 | expand via node | unit | decision table | {positions 키=nodes, present 이웃 있을 때 앵커, 조상만 present, 둘 다 없음 {0,0}, 이웃 배치 반지름 120·각도 0 시작} | 100% | 좌표 ±1e-6 | automated |
| VO-5 | FR-6, FR-7, C-6, C-7 | labelFontSize/focusZoom via node | unit | boundary value (3-value) | C-6, C-7 값 | 100% | 식대로 | automated |
| VO-6 | FR-8, C-8 | render_report | integration | equivalence partitioning | {kind 5종 각 1건} | 100% | li 텍스트에 label 1회, title에 원문 target | automated |
| VO-7 | FR-5, FR-6, FR-7, QR-2, QR-4, QR-5 | 세 페이지 in Chrome | end-to-end review | scenario | {대시보드 로드, bottlenecks 로드, M1 로드·fit 스크린샷, M1 숨은 노드 검색(기존 노드 위치 검색 전후 동일: JS로 3개 노드 position 비교), M1 없는 검색어 검색과 존재하지 않는 id의 focus-node-request 이벤트(노드 수 불변, no-match 안내 또는 무변화)} | 100% | 시간 임계, 콘솔 error 0, 위치 불변, 라벨 판독 | RV-2 |
| VO-8 | QR-3 | 전체 suite | integration | none — experience-based(회귀) | 기존 테스트 | none — experience-based | 통과 | automated |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
|---|---|---|---|
| A-1 | FR-3 edge 규칙은 현재 graph.js 동작(새 focus 집합 노드와 present 노드 사이 edge 포함)을 그대로 명세 | graph.js:173-184 | 사용자 승인 v1 |
| A-2 | FR-4 앵커·반지름 120은 현재 graph.js 동작을 명세 | graph.js:186-205 | 사용자 승인 v1 |
| A-3 | NA_05/NA_06 제외 유지 | 이전 run A-4 | 이전 승인 |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
|---|---|---|---|
| FR-1 | C-3, C-4 | VO-1 | automated |
| FR-2 | C-2 | VO-2 | automated |
| FR-3 | C-1, C-5 | VO-3 | automated |
| FR-4 | — | VO-4 | automated |
| FR-5 | — | VO-7 | RV-2 |
| FR-6, FR-7 | C-6, C-7 | VO-5, VO-7 | automated + RV-2 |
| FR-8 | C-8 | VO-6 | automated |
| QR-2, QR-4, QR-5 | — | VO-7 | RV-2 |
| QR-3 | — | VO-8 | automated |

# Workflow Control
| item | value |
|---|---|
| correction batches used | 2 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state:
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
|---|---|---|---|---|---|
| VO-1, VO-2, VO-3, VO-5 | 2 | tests/test_readability_followup.py | accepted (verifier 1) | MUT-1 detected (VO-2/VO-3), MUT-2 detected (VO-3) | test file 수정 시 재확인 |
| VO-4 | 3 | tests/test_readability_followup.py (FG-2 보강) | accepted (verifier 2) | MUT-5(anchor 이웃 positions 누출) detected | FG-2 |
| VO-6 | 3 | tests/test_readability_followup.py (FG-1 보강) | accepted (verifier 2) | MUT-3 detected, MUT-4(<strong>→<span>) detected (5 subtests) | FG-1 |
| VO-7 | 3 | local-reports/review/RV-2.md (+ M1 error scenarios), console-m1-errors.log, console-{m1,bottlenecks,dashboard}.log, screens/rv2-*.jpg | accepted (verifier 2) | — | — |
| VO-8 | 2 | Test command 462 passed | accepted (verifier 1) | — | — |

Execution ledger:
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
|---|---|---|---|---|
| 1 | VO-3 4건 실패: 기대 `e-t-p3c`, 실제 `edge:e-t-p3c` | spec 모호(edge id 표기) — test defect | FR-3에 built element id 명시(v2), test-implementer 재작업 | Test command 462 passed |
| 2 | mutation 첫 실행: zsh에서 $TC 단어 분리 안 됨 → 테스트 미실행, seed restore가 첫 복원 뒤 백업 소진해 MUT-2/3 주입이 남음 | verified | 수동 복원(diff로 확인) 후 bash 배열로 mutation마다 backup/restore | MUT-1 detected (VO-2, VO-3), MUT-2 detected (VO-3), MUT-3 detected (VO-6 5 subtests); 복원 후 462 passed |

| 3 | verifier 1 retry: FG-1 VO-6 <strong> 미검증, FG-2 VO-4 present 이웃 positions 누출 미검증, FG-3 Errors 행 graph.js 쪽 VO 없음, FG-4 mutation 증거 누락 | FG-1/2 test evidence gap; FG-3 spec gap; FG-4 증거 전달 누락(MUT-1..3 실행됨) | FG-3: VO-7 항목 추가(v3, 사용자 승인); FG-1/2 test-implementer 보강; FG-4 ledger 2 참조 | 462 passed; MUT-1..5 전부 detected; RV-2 error 시나리오 기록 |

# Version Log
## v1
- 이전 run 5f7e8ab6e7b7fa1b(limit)의 SPEC-4, RV-ARTIFACT-1, 권고 3건을 이어받음. 콘솔 raw 로그, 라벨 ≥11px, 이웃 fit 줌(≥1), 이유 문장 라벨 제거, ADV-1 제외는 사용자 결정.
## v2
- FR-3 edge id를 built element id로, FR-4 배치 좌표식을 명시. A-1/A-2(현재 graph.js 동작 재현, 승인됨)에서 도출한 명확화로 동작 변경 없음. 근거: VO-3 실패, test-implementer의 각도 방향 질의.
## v3
- VO-7에 없는 검색어/없는 id focus 이벤트 시나리오 추가(FG-3, 사용자 승인).
- verifier 2 pass: FG-1..FG-4 closed. Advisory: M1 fit 배율 라벨 겹침, 숨은 노드 이웃 배치 시 기존 노드와 겹침.
