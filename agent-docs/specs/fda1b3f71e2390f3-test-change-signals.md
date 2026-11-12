---
version: 1
run_id: fda1b3f71e2390f3
status: active
base_commit: 0f17dd29afc6a0d916529c10562e72a1692f8eab
max_verifier_invocations: 2
commit: 0f17dd29afc6a0d916529c10562e72a1692f8eab
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자(eval 소유자, 상시 지시: AI agent 문제를 얼마나 잡는가) | 바뀐 코드에 테스트가 닿지 않는 문제 P15(바뀐 코드 미테스트)·P11(오류 처리 경로 미테스트)를 분석기가 잡는다 | 재측정에서 P15·P11 유효 주입 14건 중 분석기 located ≥ 7, matched ≥ 3 |
| I2 | 사용자 | 테스트를 고쳐 통과시키는 P12, 약하거나 없는 검증 P13을 분석기가 잡는다 | P12 유효 8건 중 located ≥ 3, matched ≥ 2(테스트 파일을 고친 4건 대상); P13 유효 7건 중 located ≥ 5, matched ≥ 3 |
| I3 | 사용자 | 과도한 mock P14를 분석기가 잡는다 | P14 유효 7건 중 located ≥ 5, matched ≥ 3 |
| I4 | 사용자 | 앞선 작업에서 줄인 음성 대조 오탐이 크게 늘지 않는다 | NC1 ≤ 2/16, NC2 ≤ 1/16, NC3 = 0/13, NC4 ≤ 3/14 |
| I5 | 기존 delta·bottleneck 소비자(CLI, eval harness, HTML 보고서, agent handout) | 새 열·표·delta 목록이 더해져도 기존 소비 코드가 동작한다 | 새 데이터가 없는 이전 baseline도 읽히고, 새 열·key를 뺀 출력은 base_commit과 같다 |

# Scope
In scope: (1) file granularity bottleneck JSON 심볼 표의 새 열 `branches`·`test_reach`. (2) 새 테스트 케이스 표 `dependency_network.test_cases`·`test_case_columns`(Python·TypeScript/JavaScript·Kotlin 테스트 파일). (3) `--baseline` delta의 `untested_changes`·`weakened_tests`·`added_mocks` 목록과 `test_changes` 상태 객체, policy `delta.v5`. (4) CLI 요약 줄. (5) 주입 eval 재측정.
Out of scope: 테스트 실행·coverage 도구 사용, production 코드가 테스트 입력을 특별 취급하는 P12 변형(sonnet 방식 4건), P45와 다른 유형, symbol granularity 출력, 새 단독 후보 종류(candidates 목록), 언어 분석기(language_analyzers·framework_analyzers)의 출력 변경, HTML 보고서·handout 렌더링 변경, harness 코드 변경, pytest fixture·테스트 helper 함수 안의 assertion·mock 추적.

# Paths
Implementation: bottlenecks/test_signals.py, bottlenecks/symbols.py, bottlenecks/core.py, bottlenecks/delta.py, code_analyzer/cli.py
Tests: tests/test_test_signals.py, tests/test_test_changes_delta.py, tests/test_signals_support.py, tests/test_signals_evidence/, 그리고 기존 tests/ file(조정 허용 범위: `"delta.v4"` 기대값을 `"delta.v5"`로; delta key 집합과 `counts` key 집합에 새 key 추가; `symbol_columns` 기대값 끝에 `branches`·`test_reach` 추가와 그에 따른 행 길이; bottleneck JSON의 `dependency_network` key 집합에 `test_cases`·`test_case_columns` 추가; base 출력과 hash·byte·크기 비율로 비교하는 characterization은 비교 전에 `test_cases`·`test_case_columns`와 심볼 행의 두 새 열을 제거한 뒤 비교하고 새 항목은 같은 test에서 별도로 단언; `tests/delta_support.py` `ref_delta`를 새 목록까지 독립 구현으로 확장; `--baseline` CLI test의 stdout 기대값에 `[Δ] Test changes: …` 한 줄, stderr 기대값에 `[!] Warning: test changes not compared (<reason>)` 한 줄 허용. 다른 assertion 약화 금지. 모든 변경은 `tests/test_signals_evidence/existing-tests.diff`에 기록)
Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','fastapi-official-template','android-nowinandroid','typescript-nestjs-realworld')]" && uv run -q --with-requirements requirements-dev.txt --with pytest-cov python -m pytest -q -p no:cacheprovider --cov=bottlenecks.delta --cov=bottlenecks.symbols --cov=bottlenecks.test_signals --cov-branch --cov-report=term-missing --cov-fail-under=90 --deselect 'tests/test_analysis_coverage_reporting.py::test_V05_characterization_and_V04_cli_stages' --deselect 'tests/test_doc_references.py::test_V8_base_choice_cli_output_equals_base_after_removing_new_keys' --deselect 'tests/test_file_analysis_cli.py::test_V01_direct_builder_defaults_characterization' --deselect 'tests/test_nestjs_quality.py::TestRegression::test_O11_characterization_existing_standalone_outputs_are_byte_identical' --deselect 'tests/test_signal_defects_round4.py::test_V4_B_data_object' --deselect 'tests/test_report_modal.py::test_V04_graph_tab_active_modal_selects_and_centres_node' --deselect 'tests/test_report_size_format.py::test_V01_fixture_details_equal_base_details'
Review evidence: R1 — eval 재측정(Traceability F11): 네 저장소 baseline 재생성(`harness.py baseline <repo>`) 뒤 608 task 전체를 `tests/rename_comment_evidence/r1_reanalyze.py <repo> --match --workers 4`로 재분석, 산출물 `~/toy-projects/network-analysis-eval/inject/<repo>/score-tests.txt`와 main이 쓰는 `tests/test_signals_evidence/r1_comparison.md`(직전 점수 `score-symbols.txt`와 비교, 이전 결과는 `backup-symbols/`에 보관). R2 — 크기·시간: 네 eval 저장소 clone(`base` commit)에서 file granularity CLI를 base_commit과 현재 코드로 각 3회 실행해 bottleneck JSON byte 비와 분석 시간 비(최솟값)를 기록.
Fuzzing: main이 작성하는 stdlib harness `tests/test_signals_evidence/fuzz/fuzz_test_changes.py`, seed 20261113, 대상 `compute_delta`. 생성: 파일 2~8개(일부는 test 파일), 심볼 0~20개(kind·branches·test_reach 무작위)와 테스트 케이스 0~20개(강·약 검증 수, mocks, skipped 무작위)를 가진 합성 payload 쌍과 파일 이름 변경. oracle — P1(metamorphic) 같은 모델을 이름 변경 경로로 다시 그린 payload와 renames를 주면 세 새 목록이 비고; P2(differential) 새 열·표를 뺀 payload의 결과는 base_commit delta.v4 결과(새 key 제외)와 같고; P3 세 목록이 F05~F07 정의를 모델 key로 직접 계산한 기준과 같다. 5,000 입력, 예외 0.
Mutation tool: none — mutmut·cosmic-ray 미설치; hand mutation으로 대신한다.

# Signatures
`bottlenecks.symbols.SYMBOL_COLUMNS == ["id", "file", "kind", "name", "signature", "visibility", "external_refs", "uncertain_external_refs", "branches", "test_reach"]`
`bottlenecks.symbols.symbol_table(architecture, index=None, contents: Mapping[str, str] | None = None) -> list[dict]` — 각 dict는 SYMBOL_COLUMNS key를 가진다(`file`은 `file:` id). `contents`는 저장소 상대 경로 → 파일 내용; None이면 모든 `branches`가 null.
`bottlenecks.test_signals.TEST_CASE_COLUMNS == ["id", "file", "name", "strong_assertions", "weak_assertions", "mocks", "skipped"]`
`bottlenecks.test_signals.test_case_table(contents: Mapping[str, str], test_paths: Iterable[str]) -> list[dict]` — `test_paths`는 저장소 상대 경로; 각 dict는 TEST_CASE_COLUMNS key, `file`은 `"file:" + path`, `id` 오름차순.
`bottlenecks.test_signals.branch_count(path: str, source: str, start_line: int, name: str) -> int | None` — `path` 확장자로 언어를 고르고, `start_line`(1부터)에서 시작하는 이름 `name`의 함수·메서드 선언의 분기 수(F01 표 B). 맞는 선언이 없거나 구문 오류·미지원 언어면 None.
`bottlenecks.test_signals.test_reach(architecture) -> dict[str, str]` — production 파일의 function·method·class·constant node id → `"tested"`·`"uncertain"`·`"untested"`(F02).
bottleneck JSON(file granularity): `dependency_network.symbol_columns`(위 목록), `dependency_network.symbols` 행 길이 10; `dependency_network.test_case_columns`(TEST_CASE_COLUMNS), `dependency_network.test_cases` 행 `[id, file_ids 색인, name, strong, weak, mocks, skipped]`, id 오름차순.
`bottlenecks.delta.DELTA_POLICY == "delta.v5"`; `compute_delta` 결과에 `test_changes: {"status": "applied"|"skipped", "reason": None|"baseline_without_test_data"|"current_without_test_data"}`, `untested_changes`, `weakened_tests`, `added_mocks`(목록), `counts`에 세 목록 이름.
`untested_changes` 항목: `{"id", "file", "kind", "name", "baseline_branches": int|None, "current_branches": int|None, "test_reach": "uncertain"|"untested"}`
`weakened_tests` 항목: `{"id", "file", "name", "reasons": [정렬된 reason 문자열], "baseline": counts|None, "current": counts|None}`, counts = `{"strong_assertions", "weak_assertions", "mocks", "skipped"}`, reason ∈ `fewer_strong_assertions`·`newly_skipped`·`removed`·`new_without_strong_assertions`
`added_mocks` 항목: `{"id", "file", "name", "baseline_mocks": int|None, "current_mocks": int}`
세 목록 모두 `id` 오름차순, `file`은 `file:` 경로 id(현재 쪽, removed는 이름 변경 반영 뒤 baseline 쪽).
CLI(`--baseline`, applied): stdout `[Δ] Test changes: untested changes <n>, weakened tests <n>, added mocks <n>`; skipped: stderr `[!] Warning: test changes not compared (<reason>)`.

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F01 | 심볼 표 `branches`: kind가 function·method인 행은 표 B 규칙으로 센 분기 수, class·constant 행과 span·내용이 없거나 구문 오류·미지원 언어인 행은 null. 범위는 그 선언 node 전체(안의 lambda·arrow function·function expression 포함)에서 안쪽에 선언된 이름 있는 function·method·class 선언의 몸통을 뺀 부분. 선언은 span 시작 줄에서 시작하고 이름이 행 `name`의 마지막 `.` 뒤 부분과 같은 함수·메서드 선언 | must | I1 |
| F02 | 심볼 표 `test_reach`: seed는 test 범주 파일의 모든 node. 따라가는 edge는 relation이 CALLS·INSTANTIATES·CALLS_ROUTE·IMPLEMENTED_BY·DECORATES인 edge의 후보 target 전체(`candidate_targets`); INSTANTIATES로 class에 닿으면 그 class가 CONTAINS·DECLARES로 가진 `__init__`·`__post_init__`·`constructor`·`init` 메서드에도 닿는다. `tested` = seed에서 confirmed edge(confidence static_certain·static_inferred이고 resolution exact·unique_name)만으로 닿음. `uncertain` = tested가 아니고, seed에서 아무 edge로나 닿거나 framework 진입점(언어 provenance가 아닌 node에서 오는 edge의 target인 production node)에서 아무 edge로나 닿음(진입점 자신 포함). 그 밖은 `untested` | must | I1, 사용자 답 |
| F03 | 테스트 케이스 표: test 범주 파일(`path_flags`에 test) 중 `.py`·`.ts`·`.tsx`·`.js`·`.jsx`·`.mjs`·`.cjs`·`.kt` 파일에서 표 T로 케이스를 찾아 한 행씩. 같은 파일 안 같은 id는 원본 순서로 두 번째부터 ` [2]`·` [3]`… 를 붙인다. 구문 오류 파일은 행 없음 | must | I2, I3 |
| F04 | 각 케이스의 `strong_assertions`·`weak_assertions`는 표 A, `mocks`는 표 M, `skipped`는 표 S로 센다 | must | I2, I3 |
| F05 | delta `untested_changes`: current 심볼 중 kind function·method이고, (baseline에 같은 id가 없음) 또는 (양쪽 `branches`가 정수이고 current > baseline)이며, current `test_reach`가 `tested`가 아닌 것 | must | I1, 사용자 답 |
| F06 | delta `weakened_tests`: 같은 id 케이스는 current strong < baseline strong이면 `fewer_strong_assertions`, baseline skipped false → current true이면 `newly_skipped`; baseline에만 있는 id는 `removed`; current에만 있는 id이고 strong = 0이면 `new_without_strong_assertions`. reason이 하나 이상인 케이스만 항목이 된다 | must | I2 |
| F07 | delta `added_mocks`: current에만 있는 id이고 mocks ≥ 3, 또는 같은 id이고 current mocks − baseline mocks ≥ 2 | must | I3 |
| F08 | `test_changes` 상태: baseline에 `test_cases`가 없거나 `symbol_columns`에 `branches`·`test_reach`가 없으면 `baseline_without_test_data`(먼저 검사), current가 그렇면 `current_without_test_data`; skipped면 세 목록은 비고 counts는 0. policy `delta.v5`. CLI는 Signatures의 줄을 쓴다 | must | I5 |
| F09 | 파일 이름 변경 매핑(`renames.pairs`)을 test case id·file과 심볼 id에 적용한 뒤 비교한다(기존 매핑 규칙과 같은 치환) | must | I4 |
| F10 | `load_baseline`은 새 데이터를 검증한다: `test_cases`가 있으면 `test_case_columns`가 TEST_CASE_COLUMNS를 포함하는 문자열 목록, 행은 열 수와 같은 길이 목록, id·name 문자열, file은 `file_ids` 범위 안 정수, strong·weak·mocks는 0 이상 정수(bool 아님), skipped는 bool. `symbol_columns`에 `branches`가 있으면 값은 0 이상 정수 또는 null, `test_reach`가 있으면 세 문자열 중 하나. 위반은 기존과 같은 `BaselineError`(JSON 경로 포함) | must | I5 |
| F11 | 주입 eval 재측정(R1)과 크기·시간 측정(R2) | must | I1–I4 |
| F12 | symbol granularity 출력과, file granularity 출력에서 새 열·표를 뺀 부분은 base_commit과 같다 | must | I5 |

표 B — 분기로 세는 구문(각 1):
- Python(`ast`): `if`/`elif`, `for`/`async for`, `while`, `except` 처리기 각각, 조건식(`a if c else b`), comprehension의 `if` 절 각각, `match`의 `case` 각각, 불 연산(`and`/`or`) 피연산자 수 − 1.
- TypeScript/JavaScript(tree-sitter): `if`, `for`, `for…in/of`, `while`, `do…while`, `catch`, 삼항 연산자, `switch`의 `default`가 아닌 `case` 각각, 이항 연산자 `&&`·`||`·`??` 각각.
- Kotlin(tree-sitter): `if`, `for`, `while`, `do…while`, `catch`, `when`의 `else`가 아닌 항목 각각, elvis `?:`, `&&`, `||`.

표 T — 테스트 케이스와 id(`file:<path>#<이름>`):
- Python: module 최상위 또는 class 안(중첩 class 포함)에 정의된 이름이 `test`로 시작하는 함수·메서드. 이름 = 둘러싼 class 이름들과 함수 이름을 `.`로 이음.
- TS/JS: `it`·`test` 호출(`.only`·`.skip`·`.todo`·`.each(...)` 변형과 `xit`·`xtest`, `fit` 포함). 이름 = 둘러싼 `describe`(`.only`·`.skip`·`.each`·`xdescribe`·`fdescribe` 포함) 제목들과 자기 제목을 ` > `로 이음. 제목은 첫 인자가 문자열·template literal이면 그 원문 내용(따옴표 제외, `${…}`는 원문 그대로), 아니면 `<dynamic>`.
- Kotlin: 이름이 `Test`인 annotation(`@Test`, `@org.junit.Test` 등)이 붙은 함수. 이름 = 둘러싼 class·object 이름들과 함수 이름을 `.`로 이음.

표 A — 검증 분류(케이스 몸통 안, 안쪽 lambda·callback 포함):
- Python 강: `assert` 문 중 비교 연산자가 하나이고 `==`·`is`인 것; `assertEqual`·`assertEquals`·`assertIs`·`assertIsNone`·`assertDictEqual`·`assertListEqual`·`assertCountEqual`·`assertSequenceEqual`·`assertTupleEqual`·`assertSetEqual`·`assertMultiLineEqual`·`assertAlmostEqual`·`assertRaises`·`assertRaisesRegex` 호출; `pytest.raises` 호출; mock의 `assert_called_once_with`·`assert_called_with`·`assert_any_call`·`assert_has_calls`·`assert_not_called`; 위와 약 목록에 없는 호출 중 호출 이름(마지막 속성 이름)이 `assert`·`check`·`verify`·`expect`로 시작하는 것.
- Python 약: 그 밖의 모든 `assert` 문(`!=`·`<`·`<=`·`>`·`>=`·`in`·`not in`·`is not`, 비교 연산자 둘 이상, 비교가 아닌 식); `assertTrue`·`assertFalse`·`assertIsNotNone`·`assertIn`·`assertNotIn`·`assertGreater`·`assertGreaterEqual`·`assertLess`·`assertLessEqual`·`assertNotEqual`·`assertIsInstance`·`assertIsNot`·`assertNotAlmostEqual`·`assertRegex`; mock의 `assert_called`·`assert_called_once`.
- TS/JS: `expect(...)` 사슬의 마지막 matcher 호출 하나가 검증 1개. 사슬에 `.not`이 있으면 약(단 `.not.toHaveBeenCalled`·`.not.toBeCalled`는 강). 강 matcher: `toBe`·`toEqual`·`toStrictEqual`·`toBeNull`·`toBeUndefined`·`toBeNaN`·`toBeCloseTo`·`toHaveLength`·`toHaveBeenCalledWith`·`toBeCalledWith`·`toHaveBeenLastCalledWith`·`toHaveBeenNthCalledWith`·`toHaveBeenCalledTimes`·`toHaveReturnedWith`·`toMatchSnapshot`·`toMatchInlineSnapshot`·`toThrowErrorMatchingSnapshot`·`toContainEqual`, 인자가 있는 `toThrow`·`toThrowError`, 인자 둘인 `toHaveProperty`. 약 matcher: `toBeDefined`·`toBeTruthy`·`toBeFalsy`·`toMatchObject`·`toHaveBeenCalled`·`toBeCalled`·`toHaveReturned`·`toContain`·`toBeGreaterThan`·`toBeGreaterThanOrEqual`·`toBeLessThan`·`toBeLessThanOrEqual`·`toBeInstanceOf`·`toMatch`, 인자 없는 `toThrow`·`toThrowError`, 인자 하나인 `toHaveProperty`. 목록에 없는 matcher는 강. Node `assert`: `assert.strictEqual`·`deepStrictEqual`·`equal`·`deepEqual`·`throws`·`rejects` 강, `assert(...)`·`assert.ok`·`assert.notEqual`·`assert.notStrictEqual`·`assert.notDeepEqual` 약.
- Kotlin 강: `assertEquals`·`assertSame`·`assertContentEquals`·`assertArrayEquals`·`assertNull`·`assertFailsWith`·`assertThrows`; mockk `verify`·`coVerify`·`verifyOrder`·`verifySequence`; `assertThat(x)` 사슬의 matcher 중 약 목록에 없는 것; 위·약 목록에 없는 호출 중 이름이 `assert`·`verify`·`expect`로 시작하는 것.
- Kotlin 약: `assertTrue`·`assertFalse`·`assertNotNull`·`assertNotEquals`·`assertNotSame`·`assertIs`·`assertIsNot`·`assertContains`·`assertFails`; `assertThat(x)` 사슬의 `isNotNull`·`isTrue`·`isFalse`·`isNotEmpty`·`contains`·`isNotEqualTo`·`isInstanceOf`·`isGreaterThan`·`isLessThan`·`isAtLeast`·`isAtMost`.

표 M — mock 수(호출 1개 = 1):
- Python: `patch`·`patch.object`·`patch.dict`·`patch.multiple`(`mock.`·`unittest.mock.`·`mocker.` 접두 포함) 호출과 같은 이름의 decorator, `Mock`·`MagicMock`·`AsyncMock`·`NonCallableMock`·`PropertyMock`·`create_autospec` 호출, `monkeypatch.setattr`·`monkeypatch.setitem`. 범위: 케이스 몸통 + 케이스 decorator + 둘러싼 class decorator + module 최상위 문(함수·class 정의 밖).
- TS/JS: `jest.mock`·`jest.fn`·`jest.spyOn`·`jest.doMock`·`vi.mock`·`vi.fn`·`vi.spyOn`. 범위: 케이스 callback + 둘러싼 각 `describe` callback의 직접 문(hook `beforeEach`·`beforeAll` 포함, 다른 케이스 callback 제외) + 파일 최상위 문(`describe`·`it` 호출 밖).
- Kotlin: `mockk`·`spyk`·`mockkObject`·`mockkStatic`·`mockkConstructor`·`every`·`coEvery`·`mock`(mockito)·`whenever`. 범위: 케이스 함수 몸통 + 둘러싼 class의 property 초기화식과 `@Before`·`@BeforeEach` 함수.

표 S — skipped:
- Python: 케이스 또는 둘러싼 class의 decorator `pytest.mark.skip`·`skipif`·`xfail`, `unittest.skip`·`skipIf`·`skipUnless`·`expectedFailure`(접두 `mark.`·`unittest.` 생략형 포함); 몸통의 `pytest.skip(...)`·`self.skipTest(...)` 호출.
- TS/JS: `it.skip`·`test.skip`·`xit`·`xtest`·`it.todo`·`test.todo`, 또는 둘러싼 `describe.skip`·`xdescribe`.
- Kotlin: 케이스 또는 둘러싼 class의 `@Ignore`·`@Disabled`.

# Errors
- baseline의 `test_cases`·`test_case_columns`·새 심볼 열이 F10을 어김 — `BaselineError`(JSON 경로 포함), CLI는 기존 baseline 오류와 같은 메시지·종료 코드 — 출력 파일 없음, 기존과 같은 상태.
- baseline에 테스트 데이터가 없음(base_commit 이전 출력) — `test_changes.status = "skipped"`와 reason, CLI stderr 경고 한 줄, 종료 코드 0 — 세 목록 빔, 나머지 delta는 정상.
- 소스 파일 구문 오류·디코딩 실패·미지원 언어 — 예외 없음 — 그 파일 심볼 `branches` null, 그 테스트 파일 행 없음.
- tree-sitter 의존성 없음 — 기존 TypeScript·Kotlin 분석과 같은 오류 경로(새 경로 추가 없음).

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C01 | normal | Python 함수에 `if`·`try/except` 하나씩 추가, 그 함수는 테스트가 닿지 않음 | `untested_changes`에 그 함수, baseline_branches n, current n+2, test_reach `untested` |
| C02 | normal | 새 TS 함수(분기 0)를 추가, 다른 production 코드만 호출 | `untested_changes`에 그 함수, baseline_branches null |
| C03 | normal | 테스트에서 confirmed CALLS로 닿는 함수의 분기 증가 | `untested_changes`에 없음 |
| C04 | normal | Flask route handler(framework 진입점)의 분기 증가 | test_reach `uncertain`, `untested_changes`에 있음 |
| C05 | normal | 테스트 `assert x == 0` → `assert x >= 0` | `weakened_tests` reason `fewer_strong_assertions` |
| C06 | normal | 새 jest 케이스가 `toBeDefined`·`not.toBeNull`만 사용 | `new_without_strong_assertions` |
| C07 | normal | 새 Kotlin `@Test` 함수에 `mockk` 2 + `every` 3 | `added_mocks` current_mocks 5 |
| C08 | normal | 기존 spec 파일 최상위에 `jest.mock` 4개 추가 | 그 파일 모든 케이스가 `added_mocks`에(증가 4) |
| C09 | boundary | 새 케이스 mocks 2 / 3; 기존 케이스 mocks 증가 1 / 2 | 3과 증가 2만 보고 |
| C10 | boundary | 분기 수 같고 본문만 바뀜; 포맷·주석만 바뀜 | `untested_changes` 없음 |
| C11 | boundary | 새 케이스 strong 0·weak 0(검증 없음) / strong 1 | 앞만 `new_without_strong_assertions` |
| C12 | error | baseline `test_cases` 행의 mocks가 문자열 / skipped가 0 / file 색인 범위 밖 / `branches`가 -1 / `test_reach`가 "maybe" | `BaselineError` |
| C13 | error | baseline이 base_commit 출력(테스트 데이터 없음) | skipped `baseline_without_test_data`, stderr 경고, 종료 0 |
| C14 | edge | 테스트 파일 이름 변경(내용 같음) + renames | 세 목록 빔 |
| C15 | edge | 구문 오류 테스트 파일 / 구문 오류 production 파일 | 앞은 행 없음, 뒤는 branches null, 예외 없음 |
| C16 | edge | 같은 describe 안 같은 제목 케이스 둘 | id `… > t`와 `… > t [2]` |
| C17 | edge | 케이스에 `@pytest.mark.skip` 추가 | `newly_skipped` |
| C18 | edge | 케이스 삭제 | `removed`, baseline counts, current null |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 새 유형 탐지와 대조 오탐 |
| Performance efficiency | yes | 파일 재파싱·도달 계산이 file 분석마다 추가되고 JSON이 커짐 |
| Compatibility | yes | 기존 baseline·delta·bottleneck 소비자와 기존 test |
| Interaction capability | no | CLI 출력은 한 줄씩 F08·Signatures가 다룸 |
| Reliability | yes | 깨진 소스·baseline이 분석을 깨면 안 됨 |
| Security | no | 새 외부 실행·입력 경계 없음(소스는 이미 읽은 내용을 파싱) |
| Maintainability | yes | 새 module coverage |
| Flexibility | no | 새 언어 확장 요구 없음 |
| Safety | no | 물리적 위험 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | Performance efficiency / resource utilization | 네 eval 저장소 file granularity bottleneck JSON | base_commit 대비 byte 크기 비 | ≤ 1.15 | review(R2) | 사용자 답 |
| Q02 | Performance efficiency / time behaviour | 네 eval 저장소 file granularity CLI 분석 | base_commit 대비 시간 비, 3회 최솟값 | ≤ 1.15 | review(R2) | 기본값 A06 |
| Q03 | Compatibility / co-existence | 기존 tests | 허용 범위 조정 후 통과 | 전부 통과 | automated, existing-tests.diff | I5 |
| Q04 | Reliability / fault tolerance | C12·C13·C15·fuzz | 예외 수 | 0 | automated, fuzz | Errors |
| Q05 | Functional suitability / functional correctness | 재측정(F11) | P11~P15 located·matched; NC1~NC4 분석기 FP; 저장소×방법 칸별 분석기 matched 하락 | I1~I4 기준; 칸별 하락 ≤ 0.02 또는 건별 원인 보고 | review(R1) | I1–I4 |
| Q06 | Maintainability / testability | bottlenecks/delta.py, symbols.py, test_signals.py | coverage.py branch | ≥ 90% | automated | 기본값 A06 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V01 | F01, C01, C10, C15 | `branch_count` | unit(소스 문자열) | equivalence partitioning | 표 B의 구문 항목(Python 8, TS/JS 8, Kotlin 7) 각각; EP 안쪽 이름 있는 함수·class 몸통 제외; EP lambda·arrow 포함; EP 이름·시작 줄 불일치 → None; EP 구문 오류 → None; EP 미지원 확장자 → None | 100% | 각 항목에서 기대 정수 또는 None | Test command |
| V02 | F01, F12 | CLI file granularity JSON의 심볼 열 | integration(임시 project, Python·TS·Kotlin 각 1) | equivalence partitioning | EP1 `symbol_columns` 순서, EP2 function·method 행 정수, EP3 class·constant 행 null, EP4 새 열을 뺀 행이 base_commit과 같음 | 100% | F01·Signatures와 일치 | Test command |
| V03 | F02, C03, C04 | `test_reach` | unit(합성 architecture) | cause-effect graphing | 원인: confirmed 사슬 / uncertain edge 포함 사슬 / 따라가지 않는 relation(IMPORTS·TYPE_USES·TESTS)만 / framework node에서 오는 edge / 진입점에서 이어지는 호출 / INSTANTIATES → 생성자 메서드 / 닿지 않음 / test 파일 안 node가 seed; 결과: tested·uncertain·untested | 원인·결과 각 1회, 100% | F02 정의와 일치 | Test command |
| V04 | F03, C16 | `test_case_table` 케이스·id | unit | equivalence partitioning | Python: module 함수, class 메서드, 중첩 class, `test` 아닌 이름; TS: `it`, `test`, `.only`, `.each`, `xit`, 중첩 describe, template 제목, 비리터럴 제목, 중복 제목; Kotlin: `@Test`, `@org.junit.Test`, annotation 없음, object 안; 확장자 `.js`·`.mjs`; 구문 오류 | 100% | 행 유무와 id | Test command |
| V05 | F04, C05, C06, C11 | 검증 분류 | unit | equivalence partitioning | 표 A의 각 이름·연산자 항목(언어별 강·약 목록 전부, `.not` 예외, 인자 수로 갈리는 matcher, 미지정 matcher, 접두 규칙) | 100% | strong·weak 수 | Test command |
| V06 | F04, C07, C08 | mock 수 | unit | equivalence partitioning | 표 M의 각 이름, 각 범위(케이스 몸통, decorator, class decorator, module 최상위, describe 직접 문·hook, 다른 케이스 제외, Kotlin property·`@Before`) | 100% | mocks 수 | Test command |
| V07 | F04, C17 | skipped | unit | equivalence partitioning | 표 S 각 항목과 class·describe 상속 | 100% | skipped 값 | Test command |
| V08 | F05, C01–C04, C10 | `untested_changes` | unit(합성 payload) | decision table | D1 새 심볼 untested, D2 새 심볼 uncertain, D3 새 심볼 tested, D4 분기 증가 untested, D5 분기 같음, D6 분기 감소, D7 한쪽 null, D8 class·constant kind, D9 이름 변경으로 id 매핑 | 100% | D1·D2·D4 포함, 나머지 제외 | Test command |
| V09 | F06, C05, C06, C11, C17, C18 | `weakened_tests` | unit | decision table | D1 strong 감소, D2 strong 같고 weak 증가, D3 newly skipped, D4 skipped true→false, D5 removed, D6 새 케이스 strong 0, D7 새 케이스 strong ≥ 1, D8 reason 둘 동시 | 100% | D1·D3·D5·D6·D8 포함(D8은 reasons 2개 정렬), 나머지 제외 | Test command |
| V10 | F07, C07–C09 | `added_mocks` | unit | boundary value analysis(2-value) | 새 케이스 mocks 2·3, 기존 케이스 증가 1·2 | 100% | 3·증가 2만 | Test command |
| V11 | F08, F09, C13, C14 | 상태·매핑·CLI 줄 | unit + integration(CLI `--baseline`) | equivalence partitioning | EP1 applied, EP2 baseline 데이터 없음, EP3 current 데이터 없음, EP4 둘 다 없음(baseline reason), EP5 test 파일 이름 변경 매핑, EP6 production 파일 이름 변경 매핑, EP7 `--baseline` 없음 | 100% | status·reason·빈 목록·counts·stdout/stderr 줄 | Test command |
| V12 | F10, C12 | `load_baseline` | unit | equivalence partitioning | EP1 정상, EP2 `test_cases`가 dict, EP3 columns 누락, EP4 행 길이, EP5 mocks 문자열, EP6 skipped 정수, EP7 file 색인 범위 밖, EP8 strong 음수, EP9 `branches` -1, EP10 `branches` 문자열, EP11 `test_reach` 미지정 값 | 100% | EP2~11 BaselineError(JSON 경로 포함) | Test command |
| V13 | Q04 | `compute_delta` | fuzz | random + metamorphic + differential | Fuzzing 줄 P1~P3 | 5,000 입력 | 위반 0, 예외 0 | main |
| V14 | F11, Q01, Q02, Q05 | 재측정·크기·시간 | review | none — review procedure | R1, R2 | 전부 수행 | 기준 충족 또는 사유 기록 | R1, R2 |
| V15 | Q03, Q06, F12 | 기존 suite, coverage, symbol granularity | automated | branch(coverage.py) | 세 module branch | ≥ 90% | Test command 통과 | Test command |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| A01 | 대상 묶음은 테스트 관련 P11~P15 | 사용자 선택 | user answer |
| A02 | P15·P11의 "바뀐 코드"는 분기 증가 또는 새 심볼 | 주입 14건 중 분기 없는 변경은 1건(nowinandroid P15-sonnet, 새 함수라 포함됨) | user answer |
| A03 | 테스트 도달은 호출 그래프 간접 도달, framework 진입점 경유는 uncertain으로 보고 | Flask test client·NestJS DI는 테스트→handler 정적 edge가 없음 | user answer |
| A04 | Q01 ≤ 1.15 | CTFd 테스트 약 730개 × 행 약 110 B ≈ 80 KB(1.69 MB의 5%) + 심볼 두 열 | user answer |
| A05 | 분기·케이스 계산은 bottlenecks 단계에서 `snapshot.contents`를 다시 파싱(언어 분석기 출력 불변) | 분석기 출력을 바꾸면 symbol granularity·details 크기와 characterization이 바뀜; 대가는 재파싱 시간 | brief v1 — approved |
| A06 | Q02 ≤ 1.15, coverage ≥ 90% | 재파싱 비용 추정 ghostfolio +1~2 s(13 s 기준) | brief v1 — approved |
| A07 | 검증 강·약 분류는 표 A, 미지정 matcher·assertThat 항목은 강 | 사용자 정의 matcher는 대개 구체 값 검사; 미지정을 약으로 두면 새 정상 테스트 오탐 증가 | brief v1 — approved |
| A08 | mock 기준: 새 케이스 ≥ 3, 기존 케이스 증가 ≥ 2 | 주입 P14 7건의 mock 수 4~12; 기존 테스트 분포는 미측정(R1에서 NC로 확인) | brief v1 — approved |
| A09 | 테스트 helper·pytest fixture 안의 assertion·mock은 추적하지 않음; 이름 접두 `assert`·`check`·`verify`·`expect` 호출을 강 검증으로 셈 | 정적 추적 범위 제한; 접두 규칙으로 helper 사용 테스트의 오탐 완화 | brief v1 — approved |
| A10 | `removed`는 파일 삭제로 사라진 케이스도 모두 보고 | 테스트 삭제로 통과시키기는 P12 수법; 대량 삭제 시 항목 수가 많아짐 | brief v1 — approved |
| A11 | schema 이름 `bottlenecks.v9` 유지(추가 열·key만), delta policy는 `delta.v5` | 직전 spec 결정 A05와 같은 방식 | brief v1 — approved |
| A12 | 새 단독 후보 종류는 만들지 않음(delta 목록만) | 미테스트·약한 검증은 변경 맥락에서만 의미; 단독 보고서 크기·HTML 생성기 변경 회피 | brief v1 — approved |
| A13 | 재측정 판정 비용 ≤ $4 예상(직전 약 $2.7) | 누적 약 $48, 상한 $100 | brief v1 — approved |
| A14 | 역할 model: implementer·test-implementer·test-verifier 모두 저장소 기본(sonnet) | 변경이 bottlenecks 안에 국한 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F01 | C01, C10, C15 | V01, V02 | Test command |
| F02 | C03, C04 | V03 | Test command |
| F03 | C16 | V04 | Test command |
| F04 | C05–C08, C11, C17 | V05, V06, V07 | Test command |
| F05 | C01–C04, C10 | V08 | Test command |
| F06 | C05, C06, C11, C17, C18 | V09 | Test command |
| F07 | C07–C09 | V10 | Test command |
| F08 | C13 | V11 | Test command |
| F09 | C14 | V11, V13 | Test command, fuzz |
| F10 | C12 | V12 | Test command |
| F11 | — | V14 | R1, R2 |
| F12 | — | V02, V15 | Test command |
| Q01, Q02, Q05 | — | V14 | R1, R2 |
| Q03, Q06 | — | V15 | Test command |
| Q04 | C12, C13, C15 | V11, V12, V13 | Test command, fuzz |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 0 |
| verifier invocations | 0 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |

# Version Log
## v1
- 초안: 테스트 관련 P11~P15, 사용자 답 A01~A04 반영.

# Retrospective
