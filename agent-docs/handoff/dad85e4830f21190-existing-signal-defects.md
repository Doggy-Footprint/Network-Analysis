# 기존 후보 신호의 결함 수정

## Goal

> sonnet high subagent 호출해서 이미 지원하는 거 제대로 지원하고 있는지 검수해보고, C, D는 handoff에 넣어놓고, A, B는 이 세션에서 진행하자.

> 결함에 대한 handoff 작성.

> 기존 신호 결함 수정할 계획 세워. /workflow-approach

AI agent 친화 코드 특성 중 이미 지원한다고 본 5개 항목을 검수했고, 아래 결함이 나왔다. 이 문서는 그 수정 작업을 인계한다.

## State

- Branch: `research/ai-friendly-code-structure`.
- Base commit: `4c0d5ed`(검수 시점 HEAD는 `6444895451a89f4450b9123b7beb17b11506e534` + 문서 변경만).
- 변경된 파일: 이 문서, `agent-docs/handoff/index.md`. 구현 변경은 없다.
- 진행: 3회 분할 중 1회차(F11, F7, F8, F9 줄 수)와 2회차(F1, F2)를 완료했다(spec `agent-docs/spec-logs/7ab6320d2eb56ccf-analyzer-fact-defects.md`, `agent-docs/spec-logs/f3972ebd2386454f-dynamic-flags.md`). 남은 것은 3회차(F3, F4, F5, F6, F9 토큰, F10, F12)다.
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
| 2회차 mutation tool 첫 sanity check(`ast.unparse`만 적용한 파일로 145 failed) | 확인 명령이 `open(p,'w')`로 파일을 읽기 전에 비움 | verified: 읽은 뒤 쓰도록 고친 재실행 145 passed |

## Next Step

1. 결함별로 의도된 동작인지 먼저 확인한다. F10과 F3 일부는 "recall 우선" 정책에서 나온 설계일 수 있다.
2. 남은 순서: 3회차 F3·F4·F5·F6·F9(토큰)·F10·F12. F3은 "외부 호출 분리(`external_call_count`)", F5는 "외부 파일만 셈(이름 유지)"으로 사용자가 결정했다. F6·F10은 3회차에서 정한다. 앞의 것일수록 후보가 거꾸로 나오거나 대부분 파일에 나와 신호 가치를 잃는다.
3. 각 수정은 `workflow-approach`로 진행한다. 재현 입력은 검수 agent가 만든 scratchpad fixture(세션 종료 시 사라짐) 대신 테스트 fixture로 다시 만든다.

## Open Questions

- F3: builtin·표준 라이브러리·외부 import 호출을 미확정에서 빼면 recall이 줄어든다. 빼는 대신 별도 metric으로 분리할지 정해야 한다.
- F5: `evidence_spread`를 "다른 파일 수"로 다시 정의할지, 이름과 의미를 바꿀지 정해야 한다. baseline·HTML 소비자에 영향이 있다.
- F10: PageRank에 절대 가중치를 반영하면 ADR `31d2dee6912427d5-consolidate-overlapping-metrics.md`의 지표 정의가 바뀐다.

## Spec

- 1회차: `agent-docs/spec-logs/7ab6320d2eb56ccf-analyzer-fact-defects.md`, v4, complete, run `7ab6320d2eb56ccf`.
- 2회차: `agent-docs/spec-logs/f3972ebd2386454f-dynamic-flags.md`, v2, complete, run `f3972ebd2386454f`.
- 3회차: 시작 전.

## Execution Ledger

1회차: Test command 2738 passed, diff coverage 100%, fuzz 20,500회 위반 0, hand mutation 13/13 killed, mutation tool 29개 중 27 killed·2 equivalent, 성능 비율 0.79–1.05, verifier 2회, 수정 4회. 자세한 내용은 spec-logs.

2회차: Test command 2894 passed, diff coverage 98.1%, fuzz 3×1,000 위반 0(구문 오류 파일·중복 검사 포함), hand mutation 14/14 killed, mutation tool 30/30 killed, 실제 fixture 5개 출력 변화 0(해당 구문 없음), verifier 2회, 수정 1회. F4 관련: Kotlin 동적 플래그도 기존 call 스캔 귀속을 따라 method와 class에 모두 붙는다(D4).

검수 agent 실행 기록: 관련 테스트 650 passed, browser 31 error(Chromium 없음). 결함 F1–F10은 scratchpad fixture로 재현했다. mutation·fuzz 실행 없음.
