# 기존 후보 신호의 결함 수정

## Goal

> sonnet high subagent 호출해서 이미 지원하는 거 제대로 지원하고 있는지 검수해보고, C, D는 handoff에 넣어놓고, A, B는 이 세션에서 진행하자.

> 결함에 대한 handoff 작성.

> 기존 신호 결함 수정할 계획 세워. /workflow-approach

> handoff-existing signal defects에서 F3, F4, F5, F6, F9 토큰, F10, F12을 처리해야 해

> 처리하자 (범위: V12 + Open Questions 전부; evidence_spread는 디렉터리 단위로 재정의)

AI agent 친화 코드 특성 중 이미 지원한다고 본 5개 항목을 검수했고, 아래 결함이 나왔다. 이 문서는 그 수정 작업을 인계한다.

## State

- Branch: `research/ai-friendly-code-structure`.
- Base commit: `4c0d5ed`(검수 시점 HEAD는 `6444895451a89f4450b9123b7beb17b11506e534` + 문서 변경만).
- 3회차 종료 시점 HEAD: 이 문서 갱신 커밋(branch `research/ai-friendly-code-structure`). 3회차 구현 변경 파일: `bottlenecks/core.py`, `analysis/{graph_metrics,edge_weights,file_graph}.py`, `profiles/edge_weights.v1.yaml`, `language_analyzers/{core/flags,python/graph,typescript/analyzer,kotlin/analyzer,kotlin/ast}.py`, `report/bottlenecks/generate.py`, `renderers/html/static/app.js`. 테스트·증거: `tests/test_signal_defects.py`, `tests/signal_defects_support.py`, `tests/signal_defects_evidence/`, 이전 run base manifest 5개·O11 archive 재생성, 기존 테스트 조정(`existing-tests.diff`).
- 진행: 1회차(F11, F7, F8, F9 줄 수)·2회차(F1, F2) 완료. 3회차(F3, F4, F5, F6, F9 토큰, F10, F12)는 구현·테스트가 끝났고 V1–V11·V13–V15가 verifier에서 accepted이지만, V12(실제 fixture 출력 review evidence)의 자동 비교 스크립트 귀속 규칙이 느슨하다는 verifier 2 지적(F2–F5)으로 verifier 예산이 소진되어 status `limit`으로 멈췄다.
- 기존 테스트로는 아래 결함이 잡히지 않는다. 검수 당시 관련 테스트는 650 passed, Chromium이 필요한 browser 테스트 31개만 error였다.

### 결함 목록 (모두 실행으로 확인)

재현 명령: `python3 -m code_analyzer -l <lang> <dir> --granularity file|symbol --bottlenecks out.json`.

| id | 신호 | 결함 | 재현 → 관찰 / 기대 | 위치 |
| --- | --- | --- | --- | --- |
| F1 | `dynamic_*` 플래그 | TS는 리터럴 specifier만 `dynamic_import`로 표시한다. `import(name)`·`require(name)`은 표시하지 않고, `require('fs')`는 표시한다. TS·Kotlin에는 `dynamic_eval`·`dynamic_attr`가 없다. Kotlin은 `dynamic_*`를 하나도 만들지 않는다. | `import(name)` → 플래그 없음 / `dynamic_import`. `Class.forName(n)` → 플래그 없음 / `dynamic_attr` 계열 | `language_analyzers/typescript/analyzer.py:285-291, 644-655`, `language_analyzers/kotlin/analyzer.py` |
| F2 | `dynamic_*` 플래그(Python) | 별칭 호출(`from importlib import import_module as im; im(n)`), `builtins.eval(code)`, `o.__dict__[n]`, `__getattr__` 정의를 놓친다. | 각 입력 → 플래그 없음 / 해당 플래그 | `language_analyzers/python/graph.py:37-39, 128-146` |
| F3 | `unresolved_boundary` | 프로젝트 심볼과 이름이 안 맞는 모든 호출을 미확정으로 센다(builtin, 표준 라이브러리, 외부 import 포함). 이 저장소 file 모드에서 non-test 파일 75개 중 53개(71%)에 후보가 나온다. | `def run(x): print(len(x))` → 후보 / 없음 | `language_analyzers/python/graph.py:456-491`, `typescript/analyzer.py:744-760`, `kotlin/analyzer.py:324-340` |
| F4 | `unresolved_count` | 참조 목록이 source 순서로 20개에서 잘린다. Python이 쓰는 `unresolved_reference_total`을 bottleneck이 읽지 않는다. Kotlin은 class와 method가 같은 참조를 각각 가져 두 번 센다. | 서로 다른 호출 30개 → 20 / 30. Kotlin 호출 4개 → 8 / 4 | `bottlenecks/core.py:126, 189`, `kotlin/ast.py` |
| F5 | `evidence_spread` | 대상 파일 안의 참조도 근거 위치로 센다. symbol 모드에서는 CONTAINS 엣지도 근거로 센다. 그래서 file 모드는 "다른 파일 1개 + 내부 사용", symbol 모드는 "다른 파일 1개"로 발동하고, 코드가 모여 있는지를 재지 않는다. 이 저장소 파일의 77%가 해당한다. | `x.py`의 `f`를 `x.py`·`y.py`에서 사용 → `file_count=2` / 외부 파일 1개 | `bottlenecks/core.py:117-139, 190-196` |
| F6 | `ambiguous_name` | 플래그를 만들지만 읽는 곳이 없다. file 모드에서는 file 노드로 옮겨지지 않는다. Python·TS는 모듈 간 충돌만 세고, 같은 모듈 안의 메서드 이름 충돌로 생긴 ambiguous 엣지에는 플래그가 없다. Kotlin은 같은 파일 overload를 노드 하나로 합친다. 모호성을 후보로 내는 경로가 없다. | `A.save`·`B.save` 같은 모듈 → ambiguous 엣지, 플래그 없음 | `python/graph.py:279-281`, `typescript/analyzer.py:542-546`, `kotlin/analyzer.py:266-267`, `analysis/file_graph.py:129-131` |
| F7 | Kotlin import 해석 | 정규화된 import도 단순 이름으로 해석한다. | `com/a/Foo.kt`, `com/b/Foo.kt`, `import com.a.Foo` → ambiguous, `com.c -> com.b` package 의존(tier all) / `com.c -> com.a`(certain) | `language_analyzers/kotlin/analyzer.py:277-290, 357-363` |
| F8 | `large_node`(symbol) | 개행으로 끝나는 파일의 module end_line이 1 크다. | 5줄 파일, 임계 5 → `line_count=6` 후보 / 없음 | `python/symbols.py:368`, `typescript/analyzer.py:251`, `kotlin/analyzer.py:172`, `bottlenecks/core.py:70` |
| F9 | `large_node`(file) | `str.splitlines()`가 `\x0c` 등도 줄바꿈으로 센다. 토큰 비용은 후보를 만들지 않아, 한 줄짜리 168KB 파일(token_cost 66502)이 후보가 되지 않는다. | 위 입력 → 후보 없음 | `repository/models.py:9-10`, `bottlenecks/core.py:181-185` |
| F10 | PageRank 가중치 | 출발 노드의 나가는 가중치 합으로 정규화해서, 나가는 엣지가 하나뿐이면 가중치가 반영되지 않는다. fan_in/fan_out, betweenness, `hop_2_token_cost`는 가중치를 쓰지 않는다. | `pagerank({'a':{'b':1.0}})` == `pagerank({'a':{'b':0.3}})` | `analysis/graph_metrics.py:47, 59, 110, 119` |
| F12 | Kotlin import 근거 줄 | `^\s*import` 정규식이 앞의 빈 줄까지 잡아, 빈 줄 뒤 첫 import의 evidence 줄이 1 작다. `_import_statements`는 `[^\S\n]*`를 써서 정상이다. | android `TopicDaoTest.kt` line 19 `import ...TopicEntity` → evidence 18 / 19 | `language_analyzers/kotlin/analyzer.py` `_collect_file`의 `_imports` |
| F11 | TS 테스트 파일 엣지 | TypeScript analyzer는 IMPORTS 엣지를 만들지 않고, 선언된 심볼 안의 사용(TYPE_USES, CALLS)만 엣지로 만든다. jest `describe`/`it` 콜백처럼 모듈 최상위 익명 함수 안의 사용은 엣지가 되지 않는다. 그래서 `*.spec.ts`에서 `TESTS` 엣지가 하나도 나오지 않고, `untested_hub`가 TS 저장소에서 과다 발생한다. | typescript-nestjs-realworld `src/tag/tag.controller.spec.ts`가 `./tag.entity`를 import하고 `TagEntity`를 사용 → spec 파일의 엣지는 CONFIGURES 2개뿐, `tag.entity.ts`가 `untested_hub` / spec→entity TESTS 엣지 | `language_analyzers/typescript/analyzer.py` |

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| 수정 시도 없음 | 검수 단계에서 사용자가 handoff를 선택함 | verified: 사용자 답변 |
| F11 원인 가설 "모듈 최상위 익명 함수 미스캔" | `_resolve_import('./tag.entity')`가 None. `with_suffix`가 `tag.entity`를 `tag.ts`로 바꿈 | verified: 실행 추적. 1회차에서 상대 import 해석을 고쳐 해결(nestjs IMPORTS 6→71). 모듈 최상위 코드 스캔은 하지 않았다 |
| 1회차 workflow (F11, F7, F8, F9 줄 수) | 완료. verifier 2회(RETRY → PASS), 수정 4회 | verified: spec-logs/7ab6320d2eb56ccf |
| 2회차 workflow (F1, F2) | 완료. verifier 2회(RETRY → PASS), 수정 1회(구문 오류 파일 검증 누락) | verified: spec-logs/f3972ebd2386454f |
| 3회차 workflow (F3–F6, F9 토큰, F10, F12) | verifier 2회 모두 RETRY, 둘 다 V12만 open | verified: spec-logs/e91abc221d7deb2a ledger 10·11 |
| 3회차 V12 review를 수작업 표본으로 작성 | verifier 1 F1: flags·edge·key 비교와 kind별 표본, 재현 산출물 없음 | verified |
| 3회차 `review_diff.py`로 자동 비교, 규칙을 넓혀 unexplained 0 달성 | verifier 2 F2–F5: R4/R9 edge 규칙이 resolution·confidence·candidates 변화를 거르지 않음, file 모드 `*` relation 매핑, 구조 kind "changed only" 규칙이 문서보다 넓고 후보-edge 연결 없음, 후보 label 무조건(large_node 제거도 R8), key 허용 경로 위치 무관(node_metrics에 `external_call_count`가 새도 통과), non-test 비율 계산 미기록 | verified: 코드 검토(verifier 2) |
| 3회차 R4 edge 귀속을 "member가 있는 class면 R4"로 판정 | 너무 느슨해 실제 손실(자기 member READS·TESTS 중복)을 가렸다가 member 동일 edge 조건으로 좁힘 | verified |
| 2회차 mutation tool 첫 sanity check(`ast.unparse`만 적용한 파일로 145 failed) | 확인 명령이 `open(p,'w')`로 파일을 읽기 전에 비움 | verified: 읽은 뒤 쓰도록 고친 재실행 145 passed |
| 4회차 workflow (V12 정정, Open Questions 3건) | 완료. verifier 2회(RETRY → PASS), 정정 batch 2회 | verified: spec-logs/3f70cc03aeae9c1a |
| 4회차 R12 (B) 복원을 top-level에만 적용 | fuzz D: 여러 줄 top-level object 안의 한 줄 중첩 object 누락 | verified: 바깥 object도 infix로 파싱됨. 복원된 object의 statements까지 확장(spec v3) |

## Next Step

1. V12 evidence만 남았다. 구현·다른 obligation은 다시 열 필요가 없다(새 결함 증거가 없는 한). 새 run(spec 새 run id, 3회차 spec의 V12 행과 D1–D14를 이어받음)으로 `tests/signal_defects_evidence/review_diff.py`를 엄격하게 고친다.
   - F2: R9는 IMPORTS·IMPORTS_SYMBOL의 `start_line`만 다를 때만, R4 re-key는 key 차이가 evidence 줄뿐일 때만 인정. file 모드는 relation이 같은 symbol 수준 R4 제거가 같은 파일 쌍에 있을 때만(`*` 제거). 추가 edge는 Kotlin으로 한정.
   - F3: 구조 kind 규칙을 dependency_cycle·package_cycle·unstable_dependency로 한정하고, 변경된 후보의 구성 파일·패키지가 R4 제거 edge의 양 끝과 겹칠 때만 R4.
   - F4: kind별 방향 확인(large_node는 추가·metric 키 추가만 R8, 제거는 unexplained; unresolved_boundary 제거는 HEAD 노드에서 해당 base 이름이 `external_calls`로 옮겨졌는지 확인; evidence_spread 제거·변경은 base evidence에 R5를 재적용해 결과가 HEAD와 같은지 확인). 허용 키 경로를 위치까지 고정(`external_*`는 노드 metadata만, `token_*`는 large_node metrics만).
   - F5: non-test 비율 계산을 스크립트로 옮기고 `review-output/`에 기록.
2. 고친 스크립트로 `review_run.sh`→`review_diff.py`를 다시 실행하고 unexplained가 생기면 원인을 R id로 설명하거나 결함으로 처리한다. 이후 verifier 1회로 V12만 감사한다.
3. 완료 후 ADR `31d2dee6912427d5-consolidate-overlapping-metrics.md`의 PageRank 정의 갱신(w/outdeg, `versions.analysis` "5")을 사용자에게 제안한다(3회차 D12).

## Open Questions

- file 모드 `evidence_spread`는 R5 뒤에도 non-test 파일의 51–75%에 발동한다("다른 파일 2개 이상에서 사용" ≈ file 모드 fan_in ≥ 2). 신호를 유지할지, 임계·정의를 바꿀지 사용자 결정이 필요하다.
- Kotlin 한 줄 `object X { var y = 0 }`의 body property가 field로 수집되지 않는다(기존 동작, 3회차 범위 밖).
- Kotlin primary constructor field 노드가 constructor 전체를 스캔해 호출을 중복 귀속한다(3회차 범위 밖).

## Spec

- 1회차: `agent-docs/spec-logs/7ab6320d2eb56ccf-analyzer-fact-defects.md`, v4, complete, run `7ab6320d2eb56ccf`.
- 2회차: `agent-docs/spec-logs/f3972ebd2386454f-dynamic-flags.md`, v2, complete, run `f3972ebd2386454f`.
- 3회차: `agent-docs/spec-logs/e91abc221d7deb2a-signal-defects-round3.md`, v5, limit, run `e91abc221d7deb2a`.
- 4회차: `agent-docs/spec-logs/3f70cc03aeae9c1a-signal-defects-round4.md`, v6, complete, run `3f70cc03aeae9c1a`.

## Execution Ledger

1회차: Test command 2738 passed, diff coverage 100%, fuzz 20,500회 위반 0, hand mutation 13/13 killed, mutation tool 29개 중 27 killed·2 equivalent, 성능 비율 0.79–1.05, verifier 2회, 수정 4회. 자세한 내용은 spec-logs.

2회차: Test command 2894 passed, diff coverage 98.1%, fuzz 3×1,000 위반 0(구문 오류 파일·중복 검사 포함), hand mutation 14/14 killed, mutation tool 30/30 killed, 실제 fixture 5개 출력 변화 0(해당 구문 없음), verifier 2회, 수정 1회. F4 관련: Kotlin 동적 플래그도 기존 call 스캔 귀속을 따라 method와 class에 모두 붙는다(D4).

검수 agent 실행 기록: 관련 테스트 650 passed, browser 31 error(Chromium 없음). 결함 F1–F10은 scratchpad fixture로 재현했다. mutation·fuzz 실행 없음.

3회차: Test command 3098 passed(1 skipped), diff coverage 97.9%, fuzz 5,000회(언어별 1,000 + PageRank 2,000) 위반 0, hand mutation 11/11 killed(M8 첫 probe는 예외로 inconclusive → 변경 후 killed), mutation tool 30개 중 21 killed·9 survived → triage: 8·25·10·3 declared/undeclared gap을 테스트 보강으로 killed, 11·19·26·29 기존 suite가 kill, 22 equivalent. 성능 비율 0.78–0.98. verifier 2회(RETRY → RETRY, V12만 open), 정정 batch 4회. base manifest 5개·O11 archive 재생성(`tests/signal_defects_evidence/manifest-regeneration.md`). file 모드 non-test 비율: `unresolved_boundary` 72%→11%(이 저장소), `evidence_spread` 77%→75%.

4회차: Test command 3281 passed(1 skipped), diff coverage 96.2%, fuzz 2,000회(표면 C·D) 위반 0, hand mutation 10/10 killed + 재확인 3/3(M11·T15·T16), mutation tool 30개 중 27 killed·3 survived → declared gap으로 테스트 보강 후 killed. review 2단계(cf0cf44→3b768a9, 3b768a9→HEAD) 20개 출력 unexplained 0. 성능 비율 0.85–1.13. verifier 2회(RETRY → PASS), 정정 batch 2회. base manifest 5개·O11 archive 재생성(`tests/signal_defects_evidence/manifest-regeneration.md` Round 4). file 모드 non-test `evidence_spread` 비율: self 75%→72%, nestjs 61%→39%, android 56%→52%, futuramaapi 46%→35%, fastapi-realworld 53%→41%. 범위 밖으로 남긴 것: 한 줄 class 안의 한 줄 중첩 object 오파싱, companion object 자체 수집.
