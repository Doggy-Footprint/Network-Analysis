# 여러 연결 후보를 임의의 한 곳으로 몰지 않기

## Goal

재개 작업의 사용자 원문: “ambiguous-route-candidates handoff를 진행해줘”, “Implement the plan.”, “continue”.

사용자 요청: “Next 2개를 각각 handoff로 만들어줘.”

대상 Next: “여러 연결 후보를 임의의 한 곳으로 몰지 않기”. 출처: `tmp/is-my-code-ai-friendly.mdx`의 `## Next`. 이 복사본은 Git 추적 제외 대상이므로 재개에 필요한 내용은 아래에 기록한다.

## State

- 2026-10-09: 완료. Branch master; base commit5737113df15f6ed1705c1adadcf6b9c86bf9523e. 커밋을 만들지 않았다.
- 모든 ambiguous 후보의 균등 심볼 기여도, 동일 파일 합산, 원본 관계 간 최댓값, 심볼/파일/HTML 전파와 무손실 원본 그룹 보존을 구현했다. 기존 확정 관계 동작과 sampler를 유지했다.
- 최종 전체 테스트1258개/하위검증200개 통과,696.96초. 오류 주입4종 모두 의도된 assertion에서 실패 후 원본 해시 복원. 복원 집중91개 통과,13.51초.
- 독립 감사3/3 pass; V3-F1..F5 모두 해소. Correction batches8. 남은 작업/질문/blocked ID 없음.
- Changed implementation: analysis/candidate_projection.py, analysis/file_graph.py, analysis/graph_metrics.py, bottlenecks/core.py, code_analyzer/cli.py, framework_analyzers/{route_matching,migration_tables}.py, language_analyzers/core/{enrichment,serialization}.py, language_analyzers/{python/graph,typescript/analyzer,kotlin/analyzer}.py, report/unified.py, renderers/html/static/app.js, scripts/benchmark_file_analysis.py.
- Changed tests/evidence: 후보 독립 지표/파일/UI/producer/정책 테스트와 기존 fixture/엄격 수치 비교 형제, tests/ambiguous_candidates_evidence/. 기존 추적 측정 출력10개는 최종 증거를 별도 보존한 뒤 작업 전 HEAD 내용으로 복원했다.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| 해당 없음 | 이 개선의 구현·수정 시도는 아직 없음 | 해당 없음; 실패 원인 진단 없음 |
| E1 가상환경 실행 | `.venv/bin/python`: `ModuleNotFoundError: encodings` | verified: pyvenv.cfg는 Homebrew를 가리키나 실행 symlink는 이전 uv Python을 가리킴 |
| E2 브라우저 준비 | pip 없음, Playwright 없음; sandbox Chrome launch SIGABRT | verified: 의존성 미설치 및 sandbox 실행 제한. bundled ensurepip와 의존성 설치, 승인된 외부 sandbox headless 실행으로 복구 |
| C1 초기 집중 검증 | 62 pass/3 fail: 원본 관계가 후보별 상세 행으로 중복, 언어 관계 종류 한 건 가정 | verified: 화면 원본 그룹 인덱싱 및 테스트 선택 오류; 각 역할에서 수정 |
| C2 기존 지표 회귀 | 374 pass/4 fail: 확정 관계의 미등록 endpoint를 새 검증이 거부 | verified: 기존 direct analyzer skip 정책 변경; 복원 |
| C3 전체 검증 | 41 fail/1198 pass/1 error/191 subtests, 750.72초 | verified: 오래된 fixture 후보 참조·marker, Python CLI 정책 전달 누락, 확정 근거 wire 변화, 승인된 변경과 과거 완전 일치 기대 충돌 |
| C4 standalone 고정 hash | 메타데이터 정규화 후 8 case 실패 | verified: 모든 모호성 후보를 보존한 새 지표는 과거 대표 지표와 다름. 과거 파일은 유지하고 hash 검증된 원본 데이터로 허용된 전이만 검증 |
| C5 원본 기반 전이 검증 | 초기 독립 oracle 일부 입력 가정 오류 | verified: 원본 카테고리·TESTS 전파·기존 전략 선택 맥락을 보존하도록 교정; standalone 8건 통과 |
| C6 실제 대형 보고서 | full2:1247 passed/200 subtests/1 error,753.20초; HTML 599,017,124 bytes, 브라우저 JSON EOF | verified: 후보별 근거에 전체 후보 배열을 반복 저장하여 브라우저 문자열 한도 초과; 무손실 그룹 참조 수정 완료, 새 전체 검증 대기 |
| A1 독립 감사1 | 전체1252 pass/200 subtests에도 테스트 증거4건 부족 | verified: 단일 후보 그룹 PageRank 배분 상쇄, 기본 상대 오차 허용, 예외 종류 과다 허용, 파일 UI 기여도 대상별 미검증; 테스트 교정 batch7 필요 |
| C7-P1 감사 교정 집중 검증 | 121 pass/5 fail,29.67초 | verified: 테스트에서 선택한 프로필 전달 누락2건, main이 잘못 전달한3자리 표시 예상3건; 실제 기존 UI는 소수5자리. 교정 batch7 내 수정, 구현 변화 없음 |
| A2 마지막 독립 감사 | V3-F5: symbol UI의 share0.5만 확인하며 weighted contribution0.15는 직접 검증하지 않음 | verified: 잘못된 기여도0.3 표시가 현재 assertion을 통과할 수 있음; 감사2/2 한도 소진, 요구되는 추가 감사 전 교정 중지 |

## Next Step

없음. 완료된 기록이며 아래 과거 재개·한도 기록은 당시 상태를 보존한다.

## Open Questions

없음. 사용자가 같은 run의 감사 상한3회를 승인했고 최종 감사가 통과했다.

## Spec

Archived spec: `agent-docs/spec-logs/9c41e725d083ab6f-ambiguous-route-candidates.md`, version4, status complete, run_id9c41e725d083ab6f, evidence revision8. 이전 v3 limit 원본은 `agent-docs/spec-logs/9c41e725d083ab6f-ambiguous-route-candidates-v3-limit.md`에 보존했다.

## Execution Ledger

- Finding: 위 State의 현재 동작을 기준 commit 코드에서 재확인했다. Disposition: 미해결 개선으로 이관; 구체적인 표현·집계 정책은 Open Questions에 남겼다.
- Evidence: `framework_analyzers/route_matching.py`, `language_analyzers/core/graph_models.py`, `analysis/file_graph.py`, `analysis/graph_metrics.py`, `analysis/edge_weights.py`, `renderers/html/static/app.js`, `tests/test_route_client_call_edges.py`의 관련 경로를 읽어 확인했다. 이번 handoff 작성에서는 테스트나 성능 측정을 실행하지 않았다.
- Mutation outcomes: 구현 변경·뮤테이션 없음.
- Correction counter: 0. Verifier counter: 0. workflow 미시작 상태이며 검증 예산을 사용하지 않았다.

## Resume 2026-10-07

- 사용자가 승인한 정책: 모든 ambiguous 관계, 심볼별 균등 배분, 파일 내 합산, 관계 간 최댓값, 내부 몫 재배분 없음, 기존 JSON 필드 유지, 과거 정책 입력은 오류, 현재 HTML/JSON 범위.
- 구현과 테스트는 명세 v1을 공유하며 독립 역할로 진행 중이다. 환경 복구 후 Python/TypeScript/Kotlin parser와 headless Chrome 기본 확인이 통과했다.

## Resume 2026-10-09

- 현재 branch master, 기준 commit 5737113df15f6ed1705c1adadcf6b9c86bf9523e. 구현·테스트 변경은 유지 중이며 git commit 없음.
- 활성 명세 v3. Correction batches 6, verifier invocations 0, confirming mutations 아직 실행하지 않음.
- 전체2 결과는 독립 검증 전 중간 증거이다. 대형 보고서 저장 수정 후 새 전체 테스트, verifier, 확인 mutation 3종이 남아 있다.
- 이전 Next Step/Open Questions는 초기 작성 시점의 기록이다. 후보 정책은 승인된 명세에 확정되어 있으며 추가 사용자 결정 대기 사항은 없다.

## Audit 1 2026-10-09

- Spec v3 unchanged, correction batches7, verifier invocations1/2. VO4/VO8 accepted; VO1/2/3/5/6 evidence correction and new full baseline required. VO7 old full3 accepted then invalidated by test revision.
- Findings V3-F1..V3-F4 are required evidence gaps, no implementation defect asserted. Independent test role is correcting them as one batch; original numeric thresholds, exact equality goldens and user behavior unchanged.
- Fresh real report267,141,946 bytes loaded with50 rows and no errors. Real3-run median76.188s, fresh5-context browser summary1789.54ms/filter28.1ms/detail45.9ms meet existing bounds. Captured in tests/ambiguous_candidates_evidence/real-repository-v3/.

## Final verification in progress 2026-10-09

- Spec v3, correction batches7, verifier invocations2/2; final independent audit pending.
- Corrected full4:1258 passed/200 subtests,700.94s. Three intended mutations detected, seed restorations validated, no outstanding seed; restored focused91 passed,15.04s.
- Audit1 findings V3-F1..V3-F4 corrected through independent test evidence only; no approved behavior/threshold changes. Final audit disposition still required before completion.

## Limit disposition 2026-10-09

- Final counters: corrections7; verifier2/2; selected mutations3/3 detected and fully restored. No outstanding seed.
- V3-F1..F4 resolved; VO1/2/3/4/6/7/8 accepted; VO5 file/navigation/bounds/safety accepted, symbol numerical display observation V3-F5 open.
- Evidence: tests/ambiguous_candidates_evidence/ambiguity-full-4.log, ambiguity-correction-7.log, ambiguity-restored-v3.log, audit1.json, audit2.json, mutations.json, named evidence-map/review, real-repository-v3-final/.
- Stop source: .agents/skills/workflow-approach/SKILL.md requires stopping with limit before corrections that would require an audit beyond two invocations. No correction for V3-F5 was made after reaching that limit.

## Approved resume v4

- 사용자 원문: “3회로 늘려서 마무리 하자.” 동일 run의 감사 상한3회 승인, 누적 verifier2/correction8 유지. 기능/품질/커버리지 기대 변경 없음.
- Active spec: agent-docs/specs/9c41e725d083ab6f-ambiguous-route-candidates.md, version4, status active. v3 limit 원본은 spec-logs/9c41e725d083ab6f-ambiguous-route-candidates-v3-limit.md에 내용 변경 없이 보존.
- V3-F5 심볼 대상별 보이는0.5 share/0.15 contribution을 원본 disclosure 전 확인하는 기존3개 선택의 증거를 보완 중. 기존 custom-profile 기여도 표시 형제도 확인한다. 전체 재검증·확인 mutation·audit3 후 완료 처리 예정.

## Completed v4

- 사용자 승인에 따라 같은 run 누적 verifier3/3을 사용했고, audit3.json에서 모든 VO1-VO8 수용 및 V3-F5 해소를 확인했다. Correction8은 기존 심볼 UI 선택의 대상별 표시 증거를 보완했다.
- full5:1258 passed/200 subtests,696.96s; focused browser31 passed; current four distinct mutations all detected and restored; restored91 passed,13.51s.
- 실제3회 파일 분석 median73.069s<180s, 새 Chrome5회 summary1774.34ms<5000/filter29.1ms<300/detail43.2ms<1000.
- 증거: tests/ambiguous_candidates_evidence/9c41e725d083ab6f-evidence-map.md revision8, audit3.json, ambiguity-full-5.log, ambiguity-correction-8.log, mutations-v4.json, mutation-symbol-contribution-v4.json, ambiguity-restored-v4.log, real-repository-v4-final/.
- 감사 중 검증 항목 표 전사 오류를 승인된 v3 원문 그대로 복원했다. 구현/기능/수치 기준/커버리지 선택 변경 없음.
- No outstanding seeds or blocked findings. 최종 검증 이후 구현/테스트 코드 수정 없음.
