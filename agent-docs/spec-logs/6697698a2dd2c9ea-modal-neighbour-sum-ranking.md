---
version: 2
run_id: 6697698a2dd2c9ea
status: complete
base_commit: 6444895451a89f4450b9123b7beb17b11506e534
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자 | handoff agent-docs/handoff/0c3bcfad9643613b-report-graph-modal-redesign.md 의 남은 blocking finding E07을 닫는다("1번 마무리 해줘") | modal 연결 목록이 이웃 파일별 유효 가중치 **합**으로 상위 10을 고른다는 것을 테스트가 검증하고, 합 대신 max/첫 값을 쓰면 실패한다 |

# Scope
In scope: 통합 HTML 보고서 modal의 들어오는/나가는 직접 연결 목록(상위 10 선택과 총 개수). 선행 run 0c3bcfad9643613b(spec-logs, v3)의 F10과 A11을 그대로 계승한다.
Out of scope: 선행 run의 advisory(V01 generated/vendored, glossary stamp, shot.py, candidate 테두리 toggle), Open Questions(심볼 보고서 파일 KPI), 다른 modal 동작(열기 경로, focus, 전환), 분석기와 지표 계산, JSON 스키마, CLI.

# Paths
Implementation: report/unified.py, renderers/html/templates/dashboard.html, renderers/html/static/app.js, renderers/html/static/styles.css, renderers/html/renderer.py
Tests: tests/
Test command: .venv/bin/python -m pytest -q
Review evidence: none — 관찰 대상이 modal 텍스트이므로 자동 테스트로 충분하다.
Fuzzing: none — 입력이 고정 fixture이고 파싱 표면이 바뀌지 않는다.
Mutation tool: none — 선행 spec에도 도구가 없고, 이번 run은 구현 변경이 없을 것으로 예상된다. 구현이 바뀌면 hand mutation만으로 확인한다.

# Signatures
report.unified.render_unified_report(architecture, bottlenecks=None, *, title=None, framework_label="") -> str  (변경 없음)

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F10 | (선행 v3 F10 계승) modal은 들어오는/나가는 직접 연결 각각에 대해 유효 가중치 상위 10개 이웃 파일과 총 개수를 보여준다 | must | 선행 spec |
| F10a | 이웃 파일의 순위 값은 그 이웃과의 모든 파일 단위 edge(같은 방향)의 유효 가중치 **합**이다. 유효 가중치 = min(confidence 가중치, resolution 가중치) × 배분 몫(A11). 총 개수는 서로 다른 이웃 파일 수다. 파일 단위 edge는 (from, to, relation, confidence, resolution)가 같은 심볼 relation을 하나로 합친 것이며(analysis/file_graph.py), 합친 edge는 evidence_count와 무관하게 한 번만 더한다 | must | 선행 A11, E07 |

# Errors
none — 이번 범위에 새 실패 조건이 없다. 선행 spec의 Errors를 계승한다.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C01 | boundary | 허브 H에 대해 한 방향으로: 이웃 N1–N10은 relation 1개씩 유효 가중치 0.6; 이웃 S는 파일 edge 2개(relation 종류가 달라 병합되지 않음, 예: CALLS와 IMPORTS), 각 0.4(합 0.8); 이웃 T는 파일 edge 2개, 0.4와 0.1(합 0.5). 배분 몫은 모두 1 | 목록에 S가 포함되고 T는 제외된다. 0.6 이웃 중 하나가 밀려나며(10개 중 S 포함 → 0.6 이웃 9개 표시) 총 개수 12 |
| C02 | boundary | C01과 같은 구성을 반대 방향(나가는 연결)으로 | C01과 같은 결과 |
| C03 | normal | 선행 C09(이웃마다 relation 1개) | 기존 기대 유지 |
| C04 | error | none — 새 실패 조건 없음 | — |
| C05 | edge | S의 단일 relation 최댓값(0.4)과 첫 relation 값(0.4)은 모두 컷(0.6) 아래 | max/first 구현이면 S가 제외되어 C01이 실패한다 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 순위 규칙의 정확성이 대상이다 |
| Performance efficiency | no | 선행 Q 요구가 그대로 유효하며 이번 변경은 테스트 추가뿐이다 |
| Compatibility | no | 출력 형식 변경 없음 |
| Interaction capability | no | 화면 구성 변경 없음 |
| Reliability | no | 새 실패 경로 없음 |
| Security | no | 새 입력 표면 없음 |
| Maintainability | no | 선행 run 기준 유지 |
| Flexibility | no | 해당 없음 |
| Safety | no | 해당 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | Functional suitability / functional correctness | modal 연결 목록의 이웃 순위 | 선언된 coverage item(B1–B4) 중 통과한 비율, % | 100%, 높을수록 좋음 | pytest V04S; mutation M4, M4b 검출 | E07 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V04S | F10,F10a,C01,C02,C05,Q01 | 렌더된 modal의 들어오는/나가는 연결 섹션 텍스트 (브라우저, 목록 경로로 H를 연다) | e2e; 아래 4개 항목 전부 | boundary value analysis (2-value) — 경계는 10위 컷 값 0.6 | B1 in/합이 컷 위(S, 0.8) 포함; B2 in/합이 컷 아래(T, 0.5) 제외; B3 out/S 포함; B4 out/T 제외. 각 항목은 총 개수 12와 표시된 0.6 이웃 9개도 확인 | 100% | 기대값은 fixture 가중치 표에서 독립적으로 계산(렌더 결과에서 역산 금지) | pytest; hand mutation M4(합→max), M4b(첫 relation만) |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v1 — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| D01 | 새 run_id, verifier 예산 2회. 선행 V01–V10 accepted 상태는 계승하고 V04의 sum 측면만 V04S로 감사 | 선행 handoff Next Step이 새 run을 명시 | brief v1 — approved |
| D02 | 기법 BVA 2-value, coverage 100% | 컷 경계 위/아래 한 쌍이 sum과 max를 구분 | brief v1 — approved |
| D03 | hand mutation M4, M4b; mutation 도구와 fuzzing 없음 | 구현 변경 없을 가능성이 높음 | brief v1 — approved |
| D04 | Test command 선행과 동일 | 선행 spec | brief v1 — approved |
| D06 | (v2) 같은 key의 심볼 relation 여러 개는 파일 edge 하나로 합쳐져 한 번만 기여한다. 이는 기존 제품 집계 규칙이며 이번 run에서 바꾸지 않는다 | analysis/file_graph.py:167; test-implementer 1차 실행에서 같은 key 2개가 0.4 하나로 관찰됨 | 계약 명확화(brief 항목 아님) |
| D05 | 0.6 이웃 10개 중 표시에서 밀려나는 1개는 tie이므로 어느 것인지 단언하지 않고 개수(9)만 단언 | 선행 spec에 tie 순서 규칙이 없음 | brief v1 — approved (기본값) |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F10,F10a | C01,C02,C05 | V04S | pytest + M4/M4b |
| F10 | C03 | V04 (선행 accepted) | pytest |
| Q01 | C01,C02 | V04S | pytest |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 1 |
| verifier invocations | 1 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V04S | 2 | tests/test_report_modal.py::test_V04S_modal_neighbours_ranked_by_summed_effective_weight[in,out] (v2 fixture) | accepted (verifier-1) | — | tests/report_redesign_support.py build_report |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 1 | V04S[in/out] `SumWinner` 미표시, 피어 0.6만 표시 | verified: S의 두 relation이 같은 key(CALLS/dynamic_required/exact)라 파일 edge 하나(0.4)로 병합됨. implementer가 app.js:305 합 집계 확인 | spec v2: S의 edge를 서로 다른 relation 종류로 | test defect, 재작성 |
| 2 | full suite: 7 failed / 3284 passed, 재실행 6 failed | V04 centres_node[card/connection]: 병렬 부하 flake (verified: 단독 5회 연속 통과). characterization 5개(test_file_analysis_cli V01 ×4, test_analysis_coverage_reporting V05): verified 기존 실패, 변경 stash 후 HEAD 74d1858에서도 5 failed. golden 비교 대상이라 이번 범위 밖 | 없음 | advisory A1(characterization golden drift), A2(centres_node flake) |
| M | M4 합→max, M4b 첫 edge만, M4c edge 개수 | 가장 강한 결함 클래스: 순위 값 집계 방식 3종 | seed backup/restore (app.js:305) | M4/M4b: winner assertion 실패, M4c: loser assertion 실패 — 모두 검출, 복원 확인 |
| V1 | verifier-1: V04S accepted, blocking 0 | — | advisory ADV-1(header 12 부분 일치), ADV-2(out 섹션이 dialog 끝까지), A3(evidence_count>1 병합 edge를 한 번만 더하는 규칙은 고정 테스트 없음; attempt 1 실패가 일회성 관찰 증거) | 선행 E07 closed |
| 1b | Test command가 `-n` 미인식으로 시작 실패 | verified: .venv에 pytest-xdist 미설치(requirements-dev.txt에는 있음) | `pip install 'pytest-xdist>=3.6,<4'` (3.8.0) | 환경 수정 |

# Version Log
## v1
- Initial draft. 선행 run 0c3bcfad9643613b(limit)의 E07을 닫기 위한 후속 run.
## v2
- F10a·C01을 파일 단위 edge 기준으로 명확화하고 D06 추가. 근거: V04S 1차 실패가 같은 key relation 병합 때문임을 analysis/file_graph.py와 implementer 보고로 확인.
- complete: verifier-1 accepted V04S. base_commit 이후 HEAD가 74d1858로 이동(사용자 merge, 이번 run과 무관).
