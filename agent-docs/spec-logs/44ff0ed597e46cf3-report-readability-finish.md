---
version: 3
run_id: 44ff0ed597e46cf3
status: complete
base_commit: e0035d7a2d0eedbc4d6b54f79221c36770e561fa
max_verifier_invocations: 2
handoff: agent-docs/handoff/9c41d27e5ab03f86-report-readability.md
---

# User Intent
| id | stakeholder | intention | observable goal |
|---|---|---|---|
| UI-1 | 보고서 사용자 | M1 그래프 fit 배율에서 라벨이 서로 겹쳐 읽을 수 없는 상태를 없앤다 | always-label 라벨이 화면상 서로 겹치지 않음 |
| UI-2 | 보고서 사용자 | 숨은 노드 검색 시 새로 추가된 노드가 기존 노드 위에 쌓이지 않는다 | 새 노드 중심이 기존·다른 새 노드 중심과 최소 간격 이상 |
| UI-3 | 유지보수자 | 대시보드 overview 라벨의 category 규칙(ADV-1)을 검증 | category∈{file,module,package}, label≠file_path 노드가 파일 라벨로 표시됨을 테스트가 확인 |

# Scope
In scope: `ReportGraphModel`의 라벨 충돌 선택 순수 함수와 graph.js 연결, `expand()`의 positions 계산, app.js `buildOverview` 라벨 규칙의 테스트 추가(동작 변경 없음).
Out of scope: label-zoomed/label-hover 라벨의 충돌 처리, 디렉터리 라벨, fcose 레이아웃 파라미터, Bottlenecks·대시보드 UI 변경, vendoring ADR(별도 제안).

# Paths
Implementation: report/m1/templates/graph_model.js, report/m1/templates/graph.js
Tests: tests/test_readability_finish.py, tests/test_readability_followup.py
Test command: .venv/bin/python -m pytest -q --deselect tests/test_bottlenecks_contract.py::test_NA_05_outside_edge_raises_before_cli_writes --deselect tests/test_bottlenecks_contract.py::test_NA_06_outside_span_raises_before_cli_writes
Review evidence: RV-3 — 이 리포로 M1 HTML을 생성해 Chrome 1440×900으로 열고, (a) 초기 fit 배율 스크린샷 local-reports/review/screens/rv3-fit.jpg, (b) 기본 표시 밖 노드 1개를 검색한 뒤 스크린샷 rv3-expand.jpg, 콘솔 원문 local-reports/review/console-rv3.log, 판독 결과를 local-reports/review/RV-3.md에 기록

# Signatures
ReportGraphModel.visibleLabels(boxes) -> string[]   // boxes: [{id: string, weight: number, x1, y1, x2, y2}] (렌더 좌표)
ReportGraphModel.expand(built, present, targetId) -> {nodes, parents, edges, positions} | null   // 시그니처 불변
build()의 노드 element data에 `weight: number` 추가

# Functional Requirements
| id | requirement | priority | source |
|---|---|---|---|
| FR-1 | `visibleLabels`는 boxes를 weight 내림차순, 동점은 id 오름차순(문자열 비교)으로 순회하며, 이미 채택된 box와 겹치지 않는 box의 id만 채택해 채택 순서대로 반환한다. 겹침 = 두 사각형 내부가 양의 면적으로 교차(x1<o.x2 && o.x1<x2 && y1<o.y2 && o.y1<y2); 변·꼭짓점 접촉은 겹침 아님. 빈 입력 → [] | must | 사용자 결정(충돌 라벨 숨김) |
| FR-2 | graph.js는 초기화, layoutstop, zoom, addMissingNode 후에 화면에 보이는(`:visible`) always_label 노드의 라벨 렌더 bbox와 data.weight로 `visibleLabels`를 호출하고, 채택된 노드만 `label-always` 클래스를 가진다. 나머지 always_label 노드는 클래스를 잃는다(hover·zoomed 라벨은 기존대로) | must | 사용자 결정 |
| FR-3 | `expand()`의 새 노드 배치: 최소 간격 MIN_GAP=60(모델 좌표, 중심 간 유클리드 거리). 후보 목록 = 반지름 r_k = 60·k (k=0..12)마다 slots_k = max(1, floor(2π·r_k/60)) 개 각도 2πj/slots_k (j=0..slots_k−1) 순서. 새 target(이미 present가 아니면)은 anchor(기존 규칙 불변) 기준 후보를 차례로 검사해 모든 present 노드와 거리 ≥ MIN_GAP인 첫 후보에 놓는다. 새 이웃은 ranked 순서대로 target 위치 기준 k=2..12 후보 중 모든 present와 먼저 배치된 새 노드와 거리 ≥ MIN_GAP인 첫 후보에 놓는다 | must | 사용자 결정(빈 자리 탐색) |
| FR-4 | 조건을 만족하는 후보가 없으면 해당 노드는 탐색 범위의 마지막 후보(k=12, j=slots−1)에 놓는다(예외 없음) | must | 결정성 |
| FR-5 | expand의 nodes/parents/edges, 20 이웃 cap, present 노드 위치 불변, positions 키=nodes는 기존과 동일 | must | 기존 FR-15 |
| FR-6 | (테스트만) app.js buildOverview: category∈{file,module,package}이고 label≠span.file_path인 노드는 파일 짧은 라벨(label), full_label=file_path로 표시; category가 그 외이고 label≠file_path면 `파일라벨:label` | must | ADV-1 |

# Errors
- 후보 소진 — 신호: 노드가 마지막 후보 위치에 놓임(FR-4), 예외 없음 — 상태: 그래프에 추가 완료
- visibleLabels에 box 0개 — [] 반환 — label-always 클래스 없음

# Cases
| id | level | input / state | expected result |
|---|---|---|---|
| C-1 | normal | box A(w5)·B(w3) 겹침, C(w1) 비겹침 | [A, C] |
| C-2 | boundary | A·B 변 접촉(A.x2 == B.x1) | 둘 다 채택 |
| C-3 | edge | 동일 weight 겹침 A,B id "a"<"b" | ["a"] |
| C-4 | edge | 빈 입력 | [] |
| C-5 | normal | present 없음 외 anchor 원점, 새 target+이웃 3 | target (0,0), 이웃은 서로·target과 ≥60 |
| C-6 | normal | 기존 이웃이 anchor에 있고 그 주변 r=120 원 위에 present 다수 | target과 새 이웃 모두 모든 present와 ≥60 |
| C-7 | boundary | present가 후보 지점에서 정확히 60 / 59.99 떨어짐 | 60은 허용, 59.99는 거부되어 다음 후보 |
| C-8 | error | 탐색 범위 전 후보가 막히도록 present 배치 | 마지막 후보 위치, 예외 없음 |
| C-9 | normal | ADV-1 노드 category=module, label="Foo"≠file_path | label=파일 짧은 라벨, full_label=file_path |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
|---|---|---|
| Functional suitability | yes | 라벨·배치 규칙 정확성 |
| Performance efficiency | no | box ≤20, 후보 ≤약 500 × present ≤수백; 클릭·zoom 당 무시 가능 |
| Compatibility | yes | 기존 테스트·동작 유지 |
| Interaction capability | yes | 라벨 판독성(RV-3) |
| Reliability | no | 예외 경로 없음(FR-4로 흡수) |
| Security | no | 입력은 로컬 생성 데이터 |
| Maintainability | yes | 규칙을 순수 함수에 두어 node로 검증 |
| Flexibility | no | 대상 환경 변화 없음 |
| Safety | no | 해당 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
|---|---|---|---|---|---|---|
| QR-1 | Functional suitability / correctness | FR-1..FR-6 | VO 통과 수/VO 수 | 100% | automated, mutation | UI-1..3 |
| QR-2 | Compatibility / co-existence | 기존 테스트 | Test command 결과; 기존 followup VO-4의 위치 단언(원형 공식, target=anchor 정확 일치 2건)은 FR-3으로 교체만 허용 | 전부 통과 | automated | 기존 run |
| QR-3 | Interaction capability / user interface aesthetics | M1 fit 배율, 검색 확장 직후, zoom 변경 직후 | RV-3 스크린샷 판독: 겹친 always-label 쌍 수, 기존 노드와 겹친 새 노드 수; 콘솔 error 수 | 모두 0 | review | UI-1, UI-2 |
| QR-4 | Maintainability / testability | visibleLabels, expand positions | DOM 없이 node에서 호출 가능 여부 | 가능 | automated | 계획 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
|---|---|---|---|---|---|---|---|---|
| VO-1 | FR-1, C-1..C-4 | visibleLabels via node | unit | equivalence partitioning | {겹침 탈락, 비겹침 채택, 동점 id tie-break, 빈 입력, 반환 순서=채택 순서} | 100% | 기대 id 배열 일치 | automated |
| VO-2 | FR-1, C-2 | visibleLabels 겹침 경계 | unit | boundary value (2-value) | {x 접촉(0 겹침)·x 0.01 겹침, y 접촉·y 0.01 겹침} | 100% | 접촉 채택, 겹침 탈락 | automated |
| VO-3 | FR-2 | graph.js 소스 + build data.weight | unit(build) + integration(RV-3) | equivalence partitioning | {build 노드 data의 weight가 기존 순위 weight와 순서 일치(연결 많을수록 큼, 같으면 같음), M1 fit 화면 always-label 겹침 0} | 100% | 판독 | automated + RV-3 |
| VO-4 | FR-3, FR-5, C-5, C-6 | expand positions via node | unit | equivalence partitioning | {target 새·anchor 비어 있음, target 새·anchor 점유, 이웃 다수, present 위치 불변, nodes/edges/parents 기존과 동일} | 100% | 모든 새 노드가 present·다른 새 노드와 거리 ≥60; 독립 oracle로 계산한 FR-3 첫 후보와 좌표 일치(1e-9) | automated |
| VO-5 | FR-3, C-7 | expand 간격 경계 | unit | boundary value (2-value) | {거리 60 허용, 59.99 거부} | 100% | 위치 판정 | automated |
| VO-6 | FR-4, C-8 | expand 후보 소진 | unit | error guessing | {전 후보 차단} | none — experience-based | 마지막 후보 좌표, 예외 없음 | automated |
| VO-7 | FR-6, C-9 | app.js buildOverview via node vm | unit | equivalence partitioning | {category∈file/module/package 각 1개(label≠file_path), category=function(label≠file_path)} | 100% | FR-6 라벨 | automated |
| VO-8 | QR-2 | 전체 suite | integration | — (회귀) | Test command | 전부 | pass | automated |
| VO-9 | QR-3 | M1 브라우저 | e2e review | scenario | {fit 초기 화면, 검색 확장 직후, zoom 변경 직후} | 100% | 겹침 0, 콘솔 error 0 | RV-3 |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
|---|---|---|---|
| AD-1 | MIN_GAP=60, 탐색 k≤12(반지름 720), 이웃은 k≥2부터 | 기존 NEIGHBOR_RADIUS=120, readable 노드 size 범위 수십 px | spec 승인으로 확인 |
| AD-2 | 충돌 처리는 always-label에만 적용 | 계획 범위 | spec 승인으로 확인 |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
|---|---|---|---|
| FR-1 | C-1..C-4 | VO-1, VO-2 | automated |
| FR-2 | — | VO-3, VO-9 | automated + RV-3 |
| FR-3 | C-5..C-7 | VO-4, VO-5, VO-9 | automated + RV-3 |
| FR-4 | C-8 | VO-6 | automated |
| FR-5 | C-5 | VO-4, VO-8 | automated |
| FR-6 | C-9 | VO-7 | automated |

# Workflow Control
| item | value |
|---|---|
| correction batches used | 2 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state:
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
|---|---|---|---|---|---|
| VO-1 | 3 | tests/test_readability_finish.py TestVO1 | accepted (verifier 1; retained verifier 2) | unchanged in v3; mutations M1–M3 detected | — |
| VO-2 | 3 | TestVO2 | accepted (verifier 1; retained verifier 2) | unchanged in v3; mutations M1–M3 detected | — |
| VO-3 | 3 | TestVO3BuildNodeWeight + RV-3 | accepted (verifier 1; retained verifier 2) | unchanged in v3; mutations M1–M3 detected | — |
| VO-4 | 3 | TestVO4ExpandPositionsFR3 + followup TestVO4ExpandPositions (2 asserts replaced v2) | accepted (verifier 1; retained verifier 2) | unchanged in v3; mutations M1–M3 detected | — |
| VO-5 | 3 | TestVO5ExpandGapBoundary | accepted (verifier 1; retained verifier 2) | unchanged in v3; mutations M1–M3 detected | — |
| VO-6 | 3 | TestVO6ExpandCandidateExhaustion | accepted (verifier 1; retained verifier 2) | unchanged in v3; mutations M1–M3 detected | — |
| VO-7 | 3 | TestVO7BuildOverviewCategoryLabelRule | accepted (verifier 1; retained verifier 2) | unchanged in v3; mutations M1–M3 detected | — |
| VO-8 | 3 | Test command 482 passed | accepted (verifier 1; retained verifier 2) | unchanged in v3; mutations M1–M3 detected | — |
| VO-9 | 3 | RV-3.md §Fit, §Hidden-node search, §Zoom change; rv3-zoom.jpg, console-rv3-zoom.log | accepted (verifier 2) | SC-1 zoom item added v3 | — |

Execution ledger:
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
|---|---|---|---|---|
| 2 | SC-1: FR-2 zoom trigger has no obligation | spec gap | v3 adds zoom scenario to VO-9/QR-3/RV-3 | RV-3 §Zoom: shown 6→11, overlap 0 |
| 3 | mutations M1 overlap `<`→`<=`, M2 `>=MIN_GAP`→`>`, M3 drop 'package' | strongest: FR-1 boundary, FR-3 gap boundary, FR-6 category set | seed.py backup/restore | all detected by VO-2, VO-5(+VO-4), VO-7 |
| 1 | followup 2 tests fail (target x+60) | spec gap: QR-2 carve-out too narrow vs approved FR-3 | v2 carve-out, tests replaced with FR-3 oracle | Test command 482 passed |

# Version Log
## v1
- 초안. handoff 9c41d27e5ab03f86 잔여 ADV-1, RV-2 두 건.
## v2
- QR-2 carve-out 확장: followup의 target=anchor 정확 일치 단언 2건은 승인된 FR-3(새 target도 기존 노드와 겹치지 않음, 사용자 승인 문구)과 모순이므로 FR-3 oracle로 교체. 근거: test-implementer 보고, 두 테스트가 x 차이 정확히 60으로 실패.
- VO-3 unit: weight 공식이 스펙 외부에서 독립 도출 불가 → 순서 일치 검증으로 확정.
## v3
- verifier 1 SC-1: FR-2의 zoom 트리거를 관찰하는 항목이 없음 → VO-9·QR-3에 'zoom 변경 직후' 항목 추가(동작 변경 없음, 증거 보강).
