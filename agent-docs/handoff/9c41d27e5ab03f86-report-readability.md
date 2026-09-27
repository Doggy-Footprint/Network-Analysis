# HTML 보고서 가독성 개선 (verifier 한도 도달)

## Goal
"분석 결과의 가독성이 많이 떨어지는 것 같아. UI 디자인부터, 그래프 가독성 등을 개선하고 싶어. (component name이 `app/src/...`로 시작해서 식별이 어려운 것 포함) 그리고 전체적으로 설명이 부실해. 사용자가 이 분석을 받았을 때 어디를 봐야 할지 알 수 있게 해줘. html에 대한 대규모 리팩토링 및 외부 의존성 사용을 허락할게"

## State
- branch polish, base b8277a733d5da59b1f88cbf3513e122077baff00, 미커밋 작업 트리
- 변경: report/shared/labels.py(신규), report/shared/{document.py,common.css,index.md}, report/m1/{generate.py,index.md,templates/*,vendor/*}, report/bottlenecks/{generate.py,templates/*}, renderers/html/{renderer.py,static/app.js,templates/dashboard.html}, architecture_assets/ 추적 제거, tests/test_readability_{labels,dashboard,bottlenecks,m1}.py(신규)
- Test command: 434 passed, 2 deselected(기존 실패 NA_05/NA_06)
- 리뷰 산출물: local-reports/review/RV-1.md, local-reports/review/screens/*.jpg (git ignore 대상)

## Failed Attempts
| attempt | failure evidence | cause |
|---|---|---|
| 첫 Test command | 8 failed / 391 passed | verified: ID-1 prioritize `candidate`가 id 문자열(impl), TD-1 id 따옴표 가정, TD-2 bottlenecks-data 큰따옴표 regex, TD-3 kind 개수 검색 범위, TD-4 300 cap 반환 해석, TD-5 focus 목록 구분, TD-6 LICENSE 이름(test) |

| 첫 Test command 이후 batch 1~6 | spec v2~v7, execution ledger 참조 | verified: 테스트 과잉 명세, 누락된 dedup, M1 전체 fcose 멈춤, #cy 높이 0, 라벨 규칙 미정 |
| M1 "전체 보기"(전체 cose 재배치) | Chrome 탭 2분 이상 무응답 | verified: 2642 노드·12725 연결 전체 레이아웃 → 사용자 결정으로 제거(v7) |
| mutation MUT-3(weight에서 연결 수 제외) v6 | 테스트 전부 통과 | verified: fixture 연결 수 0 → v7 테스트 보강 후 검출 |
| verifier 2회차 | retry: SPEC-4, RV-ARTIFACT-1 | verified: FR-15 세부 조항(이웃 20개 cap, edge·parent만 추가, 기존 노드 위치 유지)에 검증 항목 없음; RV 절차가 요구한 콘솔 로그 파일 없음 |

## Next Step
1. 새 workflow run에서 SPEC-4: FR-15 세부 조항용 검증 추가(예: graph.js의 추가 로직을 순수 함수로 분리해 node로 테스트: 이웃 20개 cap, 추가 요소 집합, 기존 노드 position 불변).
2. RV-ARTIFACT-1: Chrome 콘솔 로그를 local-reports/review/console-*.log로 저장하는 절차로 VO-11/VO-14 재수행(또는 서술형 콘솔 기록 허용을 사용자가 결정).
3. 권고: M1 always-label 노드 글자가 fit 배율에서 작음, 숨은 노드 검색 후 줌이 fit 수준 유지, Bottlenecks 이유 문장에 짧은 라벨 반복, ADV-1(VO-18 category 조건 fixture).
4. 커밋 여부와 vendoring ADR 초안 제안.

## Open Questions
- RV 콘솔 기록을 raw 로그 파일로 요구할지, 서술형 기록으로 충분한지.

## Spec
agent-docs/spec-logs/5f7e8ab6e7b7fa1b-report-readability.md, version 7, status limit, run 5f7e8ab6e7b7fa1b

## Execution Ledger
- accepted: VO-1..VO-10, VO-12, VO-13, VO-15, VO-16, VO-19..VO-22 (verifier 2)
- open: VO-11, VO-14 (RV-ARTIFACT-1), FR-15 세부 조항(SPEC-4, 스펙 결정 필요); advisory ADV-1
- mutations: MUT-1 detected(VO-6), MUT-2 detected(VO-1, VO-19), MUT-3 detected at v7(VO-9, VO-20)
- correction batches: 6 / verifier invocations: 2 of 2
