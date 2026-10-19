---
version: 1
run_id: f3972ebd2386454f
status: draft
base_commit: 963d70018442629e55c0b7415882357e77e152ae
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자 | "결함 수정 2회차 이어서 해줘": handoff `agent-docs/handoff/dad85e4830f21190-existing-signal-defects.md`의 F1·F2(`dynamic_*` 플래그 누락)를 고친다 | F1·F2 재현 입력마다 기대 플래그가 붙고, 그 노드가 `unresolved_boundary` 후보 입력이 된다 |
| I2 | 사용자 | 고치지 않은 신호는 그대로 둔다 | 기존 출력 변화가 모두 R1–R10으로 설명된다 |

# Scope
In scope:
- TypeScript: `dynamic_import`(비리터럴 포함), `dynamic_eval`, `dynamic_attr`(Reflect 계열과 `Object.defineProperty`).
- Kotlin: `dynamic_import`(클래스 로딩), `dynamic_attr`(리플렉션 멤버 조회).
- Python: 별칭 호출, `builtins` receiver, `__dict__[k]`, 속성 훅 메서드 정의.

Out of scope:
- 3회차 결함: F3, F4, F5, F6, F9 토큰 비용, F10, F12.
- TS 계산된 속성 접근 `obj[name]`(사용자 결정).
- Kotlin `dynamic_eval`.
- 새 후보 종류, 새 플래그 이름, schema 버전 변경(`bottlenecks.v8` 유지).
- 리터럴이 아닌 동적 import 대상에 대한 엣지 생성.
- 플래그를 bottleneck이 소비하는 방식(`bottlenecks/core.py`) 변경.

# Paths
Implementation: language_analyzers/typescript/analyzer.py, language_analyzers/typescript/ast.py, language_analyzers/kotlin/analyzer.py, language_analyzers/kotlin/ast.py, language_analyzers/python/graph.py
Tests: tests/test_dynamic_flags.py (new), tests/dynamic_flags_support.py (new), tests/dynamic_flags_evidence/ (new; 단 main이 쓰는 `review.md`, `review-output/`, `fuzz_dynamic.py`, `fuzz-run.log`, `hand-mutations.json`, `mutation-tool.json` 제외). 기존 tests/ 파일 조정도 허용한다. 허용 범위:
- 실제 fixture 분석 결과의 golden, characterization, count, hash 기대값만 갱신한다.
- 각 변경은 R1–R10 중 하나로 설명할 수 있어야 한다. 약화는 금지한다.
- 모든 변경은 `tests/dynamic_flags_evidence/existing-tests.diff`에 R id와 함께 기록한다.
- 이전 run의 `tests/*_evidence/base_manifest.json` 재생성이 필요하면 main이 run 1과 같은 절차로 한다(각 manifest의 base worktree에 이번 Implementation diff 적용, `base_commit` 필드 유지, 출처는 `tests/dynamic_flags_evidence/manifest-regeneration.md`). test role은 그 diff를 보지 않는다.

Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','fastapi-official-template','android-nowinandroid','typescript-nestjs-realworld')]" && uv run -q --with-requirements requirements-dev.txt --with coverage python -m coverage run --branch --include=language_analyzers/typescript/analyzer.py,language_analyzers/typescript/ast.py,language_analyzers/kotlin/analyzer.py,language_analyzers/kotlin/ast.py,language_analyzers/python/graph.py -m pytest -q -p no:cacheprovider --deselect tests/test_analysis_coverage_reporting.py::test_V05_characterization_and_V04_cli_stages --deselect tests/test_analysis_coverage_reporting.py::test_V07_read_parse_counts_match_immutable_characterization --deselect tests/test_analyzer.py::FastAPIRealFixtureSmokeTests::test_fastapi_realworld_fixture_analyzes_without_crashing --deselect tests/test_file_analysis_cli.py::test_V01_direct_builder_defaults_characterization && uv run -q --with coverage python -m coverage json -o .coverage-fact.json && python3 tests/fact_defects_evidence/diff_coverage.py --base 963d70018442629e55c0b7415882357e77e152ae --coverage .coverage-fact.json --fail-under 90

Review evidence:
- 산출물: `tests/dynamic_flags_evidence/review.md`(+ `review-output/`).
- 절차
  1. main이 `typescript-nestjs-realworld`, `android-nowinandroid`, `futuramaapi`, `fastapi-realworld`, `fastapi-official-template`를 base_commit과 HEAD에서 각각 분석한다(file·symbol granularity, `--bottlenecks`).
  2. 노드별 `dynamic_*` 플래그 차이와 `unresolved_boundary` 후보 차이를 집계한다.
  3. 바뀐 항목마다 소스 줄을 열어 해당 R id를 기록한다.
- 기대 결과: R1–R9로 설명되지 않는 변화 0건, 플래그 없는 위치에 붙은 플래그 0건.

Fuzzing:
- 도구: main이 작성하는 stdlib harness `tests/dynamic_flags_evidence/fuzz_dynamic.py`, seed 20261019.
- 표면: 언어별 생성기가 함수/클래스 1–3개짜리 임시 프로젝트를 만들고, 각 심볼 본문에 R1–R9 구문(양성·음성 변형, 리터럴/비리터럴 인자, 별칭, 인자 개수 0–3)을 무작위로 0–3개 넣는다. Python·TS·Kotlin analyzer에 snapshot 없이 넣는다.
- oracle (property): ① 예외 0 ② 생성기가 계산한 기대 플래그 집합과 각 노드의 `dynamic_*` 플래그 집합이 같다(R1–R9 규칙의 독립 구현).
- 예산: 언어별 1,000 프로젝트.

Mutation tool:
- 도구: scratchpad의 AST mutation 스크립트(`ast_mut.py`, run 1과 같음).
- 대상: base_commit 이후 변경된 Implementation Python 줄만 mutate한다.
- 표본: 최대 30개, seed 20261019.
- 실행 명령: `uv run -q --with-requirements requirements-dev.txt python -m pytest -q -p no:cacheprovider -x tests/test_dynamic_flags.py`
- 생존율 임계: 40%.

# Signatures
변경 없음. 공개 함수·CLI·JSON 필드 이름과 타입은 유지한다. 바뀌는 것은 노드 `flags` 값과, 그로 인한 `unresolved_boundary` 후보뿐이다. 플래그 문자열은 `language_analyzers/core/flags.py`의 `DYNAMIC_IMPORT`, `DYNAMIC_ATTR`, `DYNAMIC_EVAL`을 쓴다.

# Functional Requirements
용어:
- **리터럴 키**(TS): `string` 노드, `${}` 치환이 없는 `template_string`, 또는 `number` 노드.
- **리터럴 이름**(Kotlin): `$` 치환(`interpolated_*`)이 없는 문자열 리터럴.
- **TS 플래그 위치**: 호출이 있는 파일의 module(file) 노드(기존 위치).
- **Kotlin 플래그 위치**: 기존 `ka.call_expressions(symbol.node, ...)` 스캔이 그 호출을 포함하는 모든 심볼 노드(기존 `unresolved_calls` 귀속과 같은 집합).
- **Python 플래그 위치**: 기존 `_BodyScanner`가 그 구문을 스캔하는 심볼(함수·클래스 본문) 또는 module 노드.

| id | requirement | priority | source |
| --- | --- | --- | --- |
| R1 | TS: 함수 부분 텍스트가 정확히 `import` 또는 `require`인 `call_expression`이 하나라도 있으면 그 파일 module 노드에 `dynamic_import`를 붙인다. 인자의 개수·종류와 무관하다. IMPORTS 엣지와 `external_imports`의 `dynamic` 레코드는 기존처럼 비어 있지 않은 리터럴 인자일 때만 만든다. | must | F1, 사용자 결정(리터럴 유지) |
| R2 | TS: 함수 부분이 식별자 `eval` 또는 `Function`인 `call_expression`, 생성자가 식별자 `Function`인 `new_expression`이 있으면 module 노드에 `dynamic_eval`을 붙인다. 멤버 접근(`window.eval`, `x.Function`)은 해당하지 않는다. | must | F1 |
| R3 | TS: 함수 부분 텍스트가 `Reflect.get`, `Reflect.set`, `Reflect.has`, `Reflect.defineProperty`, `Reflect.deleteProperty`, `Object.defineProperty`이고 두 번째 인자가 없거나 리터럴 키가 아니면 module 노드에 `dynamic_attr`를 붙인다. `Reflect.apply`는 인자와 무관하게 붙인다. 계산된 접근 `obj[name]`에는 붙이지 않는다. | must | F1, 사용자 결정(Reflect 계열만) |
| R4 | Kotlin: receiver가 있는 호출 중 ① 메서드 `forName`이고 receiver 텍스트의 마지막 `.` 조각이 `Class` ② 메서드 `load`이고 receiver 마지막 조각이 `ServiceLoader` ③ 메서드 `loadClass`(receiver 무관)이면 Kotlin 플래그 위치에 `dynamic_import`를 붙인다. 엣지는 만들지 않는다. | must | F1 |
| R5 | Kotlin: receiver가 있는 호출 중 메서드가 `getMethod`, `getDeclaredMethod`, `getField`, `getDeclaredField`이고 첫 번째 값 인자가 없거나 리터럴 이름이 아니면 Kotlin 플래그 위치에 `dynamic_attr`를 붙인다. | must | F1 |
| R6 | Python 별칭: 같은 모듈 최상위(정의 안이 아닌 module 본문, `if`/`try` 블록 포함) 또는 스캔 중인 본문 자신 안의 `from importlib import X as A`, `from builtins import X as A`, `import importlib as A`, `import builtins as A`를 별칭으로 기록한다. 호출 이름(또는 receiver)이 별칭 A이면 원래 이름 X(또는 모듈 이름)로 바꾼 호출로도 기존 판정(`_mark_dynamic`)을 한다. 원래 이름 판정이 플래그·리터럴 import 엣지를 내면 별칭 호출도 똑같이 낸다. 별칭 해석은 플래그를 더하기만 하고, 기존 판정으로 붙던 플래그를 없애지 않는다. | must | F2 |
| R7 | Python: receiver가 `builtins`(R6 별칭 해석 후)인 호출은 attr·eval 판정에서 receiver가 없는 호출과 같이 취급한다. | must | F2 |
| R8 | Python: `<expr>.__dict__[k]` 구독(Load·Store·Del 모두)에서 k가 `str` 상수가 아니면 `dynamic_attr`를 붙인다. | must | F2 |
| R9 | Python: 클래스 본문에 직접 정의된 `__getattr__`, `__getattribute__`, `__setattr__`, `__delattr__`(def·async def)가 있으면 그 class 노드에 `dynamic_attr`를 붙인다. module 최상위에 `def __getattr__`(PEP 562)이 있으면 module 노드에도 `dynamic_attr`를 붙인다(module 최상위 `__setattr__`·`__dir__`은 해당 없음). | must | F2 |
| R10 | R1–R9로 설명되지 않는 기존 출력(엣지, 다른 플래그, 메타데이터, 후보)은 바뀌지 않는다. 플래그 추가로 생기는 `unresolved_boundary` 후보 변화는 R1–R9로 설명되는 것으로 본다. | must | I2 |

# Errors
- 파싱 오류가 있는 파일(tree-sitter error node, Python SyntaxError).
  - 관찰 신호: 기존과 같이 처리된다(Python은 파싱되지 않은 파일 제외, TS·Kotlin은 파싱된 부분만 스캔). 예외 없음.
  - 실패 후 상태: 다른 파일 분석은 계속된다.
- 인자 노드가 없거나 예상 밖 구조(`require()`, `Reflect.get()`, `x.getMethod()`).
  - 관찰 신호: R1/R3/R5 규칙대로 플래그(인자 없음 = 비리터럴). 예외 없음.
  - 실패 후 상태: 해당 없음.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | TS `const m = await import(name)` / `require(name)` | module 노드 `dynamic_import`, IMPORTS 엣지 없음 |
| C2 | normal | TS `require('fs')`, `import('./b')`(b.ts 존재) | `dynamic_import`; `./b`는 기존대로 dynamic_required IMPORTS 엣지 |
| C3 | normal | TS `eval(code)`, `Function('a', body)`, `new Function(body)` | `dynamic_eval` |
| C4 | edge | TS `window.eval(x)`, `obj.Function()`, `evaluate(x)` | `dynamic_eval` 없음 |
| C5 | normal | TS `Reflect.get(o, k)`, `Reflect.set(o, k, v)`, `Object.defineProperty(o, k, d)`, `Reflect.apply(f, t, a)` | `dynamic_attr` |
| C6 | boundary | TS `Reflect.get(o, 'a')`, `Reflect.get(o, 0)`, `` Reflect.get(o, `a`) ``, `` Reflect.get(o, `a${x}`) ``, `Reflect.get(o)`, `obj[name]` | 없음 / 없음 / 없음 / 있음 / 있음 / 없음 |
| C7 | normal | Kotlin `Class.forName(n)`, `java.lang.Class.forName("a.B")`, `ServiceLoader.load(Svc::class.java)`, `loader.loadClass(n)` | 해당 심볼 `dynamic_import` |
| C8 | boundary | Kotlin `cls.getMethod(n)`, `cls.getMethod("run")`, `cls.getDeclaredField("$n")`, `cls.getField()` | 있음 / 없음 / 있음 / 있음 |
| C9 | edge | Kotlin `forName(n)`(receiver 없음), `x.load()`(receiver가 ServiceLoader 아님), `getMethod(n)`(receiver 없음) | 플래그 없음 |
| C10 | normal | Python `from importlib import import_module as im; im(n)` / `im("pkg.mod")`(pkg.mod 존재) / 함수 안 `import importlib as il; il.import_module(n)` | `dynamic_import` / + dynamic_required IMPORTS 엣지 / `dynamic_import` |
| C11 | normal | Python `from builtins import eval as e; e(c)`, `import builtins as b; b.getattr(o, n)`, `builtins.exec(c)`, `builtins.getattr(o, "x")` | `dynamic_eval` / `dynamic_attr` / `dynamic_eval` / 없음 |
| C12 | boundary | Python `o.__dict__[n]`, `o.__dict__["x"]`, `o.__dict__[n] = v`, `o.mapping[n]` | 있음 / 없음 / 있음 / 없음 |
| C13 | normal | Python class `A`에 `def __getattr__(self, n)`, class `B`에 `async def __setattr__`, module 최상위 `def __getattr__(name)` | A·B class 노드와 module 노드에 `dynamic_attr`; 메서드 노드 자체는 본문 판정만 따름 |
| C14 | edge | Python 다른 모듈에서 정의된 별칭(`from m import im`), 별칭 이름을 지역 변수로 다시 할당 후 호출 | 별칭으로 보지 않음(기존 판정만) |
| C15 | error | TS `require()`, Kotlin 구문 오류가 있는 파일 안 `Class.forName(n)` | `dynamic_import`; 예외 없음 |
| C16 | normal | 실제 fixture 5개 base vs HEAD | 변화가 모두 R1–R9로 설명됨(R10) |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 결함 수정이 본 목적 |
| Performance efficiency | no | 기존 트리 순회에 판정만 추가; 새 순회는 TS 파일당 1회 이하. 측정 대신 리뷰에서 확인 |
| Compatibility | yes | JSON schema·CLI·플래그 이름 유지 필요 |
| Interaction capability | no | UI 변경 없음 |
| Reliability | yes | 비정상 인자·구문 오류 파일에서 예외 없어야 함 |
| Security | no | 새 입력·권한 경계 없음(코드를 실행하지 않고 판정만 함) |
| Maintainability | yes | 변경 줄 테스트 가능성 |
| Flexibility | no | 설정·확장점 변경 없음 |
| Safety | no | 물리적 위해 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Compatibility / interoperability | JSON 출력, fixture 5개 | 노드·엣지·후보 JSON key 집합과 schema_version, base vs HEAD | 차이 0 | automated + review | default |
| Q2 | Reliability / fault tolerance | 3 언어 analyzer, 무작위 프로젝트 | fuzz 예외 수 + property 위반 수 | 0 | fuzz | default |
| Q3 | Maintainability / testability | base_commit 이후 변경된 Implementation 줄 | `diff_coverage.py`: 변경 실행 줄·변경 분기 중 실행된 비율, % | ≥ 90 | automated | default |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | R1,C1,C2,C15 | TypeScriptAnalyzer module 노드 flags, IMPORTS 엣지, external_imports | integration (임시 프로젝트 → analyzer) | equivalence partitioning | 호출 `import`/`require` × 인자 {식별자, 비어 있지 않은 리터럴(내부 파일), 외부 패키지 리터럴, 빈 문자열, 인자 없음, 치환 template}; 음성 {`require.resolve(x)`, `x.require(y)`} | 100% | 플래그 유무, 엣지는 비어 있지 않은 내부 리터럴만 | pytest |
| V2 | R2,C3,C4 | TS module 노드 flags | integration | equivalence partitioning | 양성 {`eval(x)`, `Function(x)`, `new Function(x)`}; 음성 {`window.eval(x)`, `o.Function()`, `new o.Function()`, `evaluate(x)`} | 100% | `dynamic_eval` 유무 | pytest |
| V3 | R3,C5,C6 | TS module 노드 flags | integration | decision table | 함수 6종(Reflect.get/set/has/defineProperty/deleteProperty, Object.defineProperty) × 두 번째 인자 {식별자, string, number, 무치환 template, 치환 template, 없음} 중 각 함수는 {식별자, string} 2개, `Reflect.get`은 6개 전부; `Reflect.apply` {리터럴 인자, 식별자 인자}; 음성 {`obj[name]`, `Reflect.ownKeys(o)`, `Object.keys(o)`} | 100% | `dynamic_attr` 유무 | pytest |
| V4 | R4,C7,C9,C15 | KotlinAnalyzer 심볼 노드 flags | integration | decision table | {Class.forName 단순/정규화 receiver, ServiceLoader.load, x.loadClass}; 음성 {receiver 없는 forName·loadClass, `Foo.forName`, `x.load()`}; 귀속 {top-level fun, class 안 method → method와 class 노드 둘 다}; 구문 오류 파일 1 | 100% | `dynamic_import` 유무·위치, 새 엣지 없음 | pytest |
| V5 | R5,C8,C9 | Kotlin 심볼 flags | integration | boundary value (2-value) + equivalence partitioning | 메서드 4종 × {리터럴 이름} 중 `getMethod`는 {식별자, 리터럴, 치환 문자열, 인자 없음, 리터럴 + 추가 인자} 전부, 나머지 3종은 {식별자, 리터럴}; 음성 {receiver 없는 getMethod} | 100% | `dynamic_attr` 유무 | pytest |
| V6 | R6,C10,C14 | Python 심볼·module flags와 IMPORTS 엣지 | integration | decision table | 별칭 형태 {`from importlib import import_module as im`, `import importlib as il`, `from builtins import eval as e`, `import builtins as b`} × 정의 위치 {module 최상위, `if`/`try` 블록, 스캔 본문 안}; 리터럴 인자 별칭 → 엣지; 음성 {다른 모듈 정의 별칭, 다른 함수 본문의 별칭} | 형태 4 × 위치는 각 형태가 module 최상위·본문 안 1회 이상, `if`/`try` 1회 이상; 나머지 100% | 플래그·엣지 | pytest |
| V7 | R7,C11 | Python flags | integration | equivalence partitioning | `builtins.` receiver × {eval 계열 1개 이상, attr 계열 비상수·상수 인자}; 별칭 receiver 1 | 100% | 플래그 유무 | pytest |
| V8 | R8,C12 | Python flags | integration | equivalence partitioning | k {Name, str 상수, 정수 상수, f-string}; ctx {Load, Store, Del}(비상수 k에서); 음성 `o.mapping[n]` | 100% | `dynamic_attr` 유무 | pytest |
| V9 | R9,C13 | Python class·module flags | integration | equivalence partitioning | 메서드 4종 각 1회(def), async def 1회, 중첩 클래스 안 정의(바깥 클래스는 해당 없음), module 최상위 `__getattr__`, 음성 module 최상위 `__setattr__`·`__dir__` | 100% | 플래그 유무·위치 | pytest |
| V10 | R10,C16,Q1 | 실제 fixture 출력 | integration + review | error guessing | 설명 안 되는 플래그·후보·엣지 변화, schema key 변화 | none — experience-based | review.md 집계와 key 비교, 기존 suite 통과 | review + pytest |
| V11 | Q2 | fuzz 표면 | integration | random | seed 20261019, 언어별 1,000 프로젝트 전량 | 100% | 위반 0 | main fuzz |
| V12 | Q3 | 변경 Implementation 줄 | — | branch testing | 변경 분기 | 90% | diff_coverage 통과 | Test command |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| D1 | TS 리터럴 `require('fs')`·`import('./x')`도 `dynamic_import` 유지 | 런타임 로딩 지점이라는 의미 유지 | user answer |
| D2 | TS `dynamic_attr`는 Reflect 계열(+`Object.defineProperty`)만; `obj[name]` 제외 | 배열·Map 인덱싱과 구분 불가 | user answer |
| D3 | TS 플래그는 module 노드에 둔다 | 기존 위치; 옮기면 baseline이 바뀜 | brief v1 — approved |
| D4 | Kotlin 플래그 위치는 기존 call 스캔 귀속(class와 method 둘 다)을 따른다 | 기존 `unresolved_calls`와 같은 집합. 중복 집계(F4)는 3회차 범위 | brief v1 — approved |
| D5 | Kotlin `Class.forName`은 `dynamic_import`로 분류 | handoff는 "dynamic_attr 계열"로 적었으나 클래스 로딩은 import 성격. 승인된 계획 R4 | brief v1 — approved |
| D6 | Kotlin `dynamic_eval` 없음 | 언어에 eval 없음; 이름 매칭은 오탐 | brief v1 — approved |
| D7 | 비리터럴 동적 import는 플래그만, 엣지 없음 | 대상을 알 수 없음; Python 기존 동작과 같음 | brief v1 — approved |
| D8 | Python 속성 훅 정의는 class 노드에, PEP 562 module `__getattr__`은 module 노드에 `dynamic_attr` | 훅은 그 소유자 전체의 속성 접근을 바꾼다 | brief v1 — approved |
| D9 | 별칭 해석은 플래그를 더하기만 한다 | R10 보존(예: 기존에 이름만으로 붙던 플래그 유지) | brief v1 — approved |
| D10 | TS `eval`·`Function`은 bare 식별자만 | `globalThis.eval` 등은 드묾; 멤버 접근은 사용자 정의 메서드와 구분 어려움 | brief v1 — approved |
| D11 | 변경 줄 branch coverage 90%, fuzz 언어별 1,000, hand mutation 8–10, mutation tool 30개 | run 1 관행 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| R1 | C1,C2,C15 | V1,V11 | pytest, fuzz |
| R2 | C3,C4 | V2,V11 | pytest, fuzz |
| R3 | C5,C6 | V3,V11 | pytest, fuzz |
| R4 | C7,C9,C15 | V4,V11 | pytest, fuzz |
| R5 | C8,C9 | V5,V11 | pytest, fuzz |
| R6 | C10,C14 | V6,V11 | pytest, fuzz |
| R7 | C11 | V7,V11 | pytest, fuzz |
| R8 | C12 | V8,V11 | pytest, fuzz |
| R9 | C13 | V9,V11 | pytest, fuzz |
| R10 | C16 | V10 | review, pytest |
| Q1 | C16 | V10 | review, pytest |
| Q2 | — | V11 | fuzz |
| Q3 | — | V12 | Test command |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 0 |
| verifier invocations | 0 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V1–V12 | 1 | — | pending | — | — |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |

# Version Log
## v1
- 초안 작성. 승인된 계획 `/root/.claude/plans/golden-cooking-boole.md`의 R1–R9를 R1–R10으로 구체화.
