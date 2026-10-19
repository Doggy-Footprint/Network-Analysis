---
version: 4
run_id: 7ab6320d2eb56ccf
status: active
base_commit: b590d5461c59d93db7800f9be451392f367b8db0
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자 | "결함에 대한 handoff 작성" 후 "기존 신호 결함 수정할 계획 세워" — 3회 분할 중 1회차: analyzer가 사실을 잘못 만드는 결함(F11, F7, F8, F9 줄 수)을 고친다 | handoff `agent-docs/handoff/dad85e4830f21190-existing-signal-defects.md`의 F11·F7·F8·F9(줄 수) 재현 입력이 기대 출력을 낸다 |
| I2 | 사용자 | 고치지 않은 신호는 그대로 둔다 | 기존 출력 변화가 모두 F11·F7·F8·F9 중 하나로 설명된다 |

# Scope
In scope:
- F11: TypeScript 상대 import 해석. 파일 이름에 점이 있는 specifier(`./tag.entity`)를 해석한다.
- F7: Kotlin 정규화 import 해석과, import된 이름을 그 파일 안에서 참조하는 경우의 해석.
- F8: Python·TypeScript·Kotlin module/file 노드의 `end_line`.
- F9(줄 수): `SourceText.lines`와 이를 쓰는 file 노드 `line_count`의 줄 구분 규칙.

Out of scope:
- F1–F6, F9의 토큰 비용 후보, F10.
- TS 모듈 최상위 코드(`describe` 콜백 등) 안의 CALLS/READS 엣지 생성.
- Kotlin `import ... as Alias`, wildcard import(`.*`) 해석.
- tsconfig path alias 해석 변경.
- schema 버전 변경(`bottlenecks.v8` 유지).

# Paths
Implementation: language_analyzers/core/enrichment.py, language_analyzers/typescript/analyzer.py, language_analyzers/kotlin/analyzer.py, language_analyzers/python/symbols.py, repository/models.py, language_analyzers/core/cost.py, bottlenecks/core.py
Tests: tests/test_fact_defects.py (new), tests/fact_defects_support.py (new), tests/fact_defects_evidence/ (new; 단 `tests/fact_defects_evidence/diff_coverage.py`는 main이 작성). 기존 tests/ 파일 조정도 허용한다. 허용 범위는 다음과 같다.
- 실제 fixture 분석 결과의 golden, characterization, count, hash 기대값만 갱신한다.
- 각 변경은 F11·F7·F8·F9 중 하나로 설명할 수 있어야 한다.
- 약화는 금지한다.
- 모든 변경은 `tests/fact_defects_evidence/existing-tests.diff`에 F id와 함께 기록한다.
- 이전 run의 `tests/*_evidence/base_manifest.json`(architecture_rules, delta, external_rules, reach, structure)은 main이 다시 만든다.
  - 각 manifest의 `base_commit` worktree에 이번 run의 Implementation diff(base_commit b590d54..HEAD, Implementation paths)를 적용한다.
  - 그 worktree에서 원래 형식 그대로 생성한다. `base_commit` 필드는 기존 테스트가 값을 검사하므로 바꾸지 않고, 출처는 `tests/fact_defects_evidence/manifest-regeneration.md`에 기록한다.
  - 적용이 충돌하면 그 manifest는 finding으로 남긴다.
  - test role은 이 diff를 보지 않는다.

Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','fastapi-official-template','android-nowinandroid','typescript-nestjs-realworld')]" && uv run -q --with-requirements requirements-dev.txt --with coverage python -m coverage run --branch --include=language_analyzers/core/enrichment.py,language_analyzers/typescript/analyzer.py,language_analyzers/kotlin/analyzer.py,language_analyzers/python/symbols.py,repository/models.py,language_analyzers/core/cost.py,bottlenecks/core.py -m pytest -q -p no:cacheprovider --deselect tests/test_analysis_coverage_reporting.py::test_V05_characterization_and_V04_cli_stages --deselect tests/test_analysis_coverage_reporting.py::test_V07_read_parse_counts_match_immutable_characterization --deselect tests/test_analyzer.py::FastAPIRealFixtureSmokeTests::test_fastapi_realworld_fixture_analyzes_without_crashing --deselect tests/test_file_analysis_cli.py::test_V01_direct_builder_defaults_characterization && uv run -q --with coverage python -m coverage json -o .coverage-fact.json && python3 tests/fact_defects_evidence/diff_coverage.py --base b590d5461c59d93db7800f9be451392f367b8db0 --coverage .coverage-fact.json --fail-under 90

Review evidence:
- 산출물: `tests/fact_defects_evidence/review.md`.
- 절차
  1. main이 `typescript-nestjs-realworld`와 `android-nowinandroid`를 base_commit과 HEAD에서 각각 분석한다(file·symbol granularity).
  2. 바뀐 엣지와 후보를 relation·resolution별로 집계한다.
  3. 바뀐 항목마다 원인 F id를 기록한다.
  4. 무작위로 고른 엣지 10개는 소스 줄을 열어 실제 import·참조와 맞는지 확인한다.
- 기대 결과: 설명되지 않는 변화 0건, 틀린 엣지 0건.

Fuzzing:
- 도구: main이 scratchpad에 작성한 stdlib harness, seed 20261019.
- 표면 (a): `SourceText`에 무작위 문자열을 넣는다. 문자열은 `\n`·`\r\n`·`\r`·`\x0b`·`\x0c`·`\x1c`·`\x85`·` `·빈 줄·마지막 개행 유무를 섞어 만든다.
- 표면 (b): 무작위 파일 이름(점 0–3개)과 상대 specifier로 만든 TypeScript 프로젝트를 `TypeScriptAnalyzer`에 넣는다.
- oracle (property)
  1. 예외가 0이다.
  2. `len(lines)`가 참조 줄 수 L과 같다.
  3. file/module 노드 `end_line`이 `max(1, L)`이다.
  4. 파일이 존재하는 상대 specifier마다 IMPORTS 엣지가 대상 파일을 가리킨다.
- 예산: (a) 20,000 입력, (b) 500 프로젝트.

Mutation tool:
- 도구: scratchpad의 AST mutation 스크립트(`ast_mut.py`)를 쓴다.
- 대상: base_commit 이후 변경된 Implementation Python 줄만 mutate한다.
- 표본: 최대 30개, seed 20261019.
- 실행 명령: `uv run -q --with-requirements requirements-dev.txt python -m pytest -q -p no:cacheprovider -x tests/test_fact_defects.py`
- 생존율 임계: 40%.

# Signatures
변경 없음. 공개 함수·CLI·JSON 필드 이름과 타입은 유지한다. 바뀌는 것은 값(엣지 집합, resolution, end_line, line_count)뿐이다.

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| R1 | 줄 수 L(text)은 `\n` 문자 수에 1을 더한 값이다. 단 text가 비어 있지 않고 `\n`으로 끝나지 않을 때만 1을 더한다. 빈 text는 0이다. `\r\n`은 줄 구분 1개로 센다. 그 밖의 문자(`\r` 단독, `\x0b`, `\x0c`, `\x1c`–`\x1e`, `\x85`, ` `, ` `)는 줄 구분이 아니다. | must | F9 |
| R2 | `SourceText.lines`의 길이는 L(text)이다. 각 줄은 `\n`으로 나눈 조각이다. 조각이 `\r`로 끝나고 그 `\r`이 `\n` 바로 앞에 있었다면 그 `\r`만 제거한다. file granularity 노드의 `cost.line_count`와 (span이 있을 때) span `end_line`은 이 길이를 따른다. 빈 파일의 file 노드 span은 기존대로 없음. | must | F9 |
| R3 | Python·TypeScript·Kotlin의 module(file) 노드 span `end_line`은 `max(1, L(text))`이다. | must | F8 |
| R4 | symbol granularity `large_node`의 `line_count`는 R3을 따른 module 노드에서 `end_line - start_line + 1`이다. 따라서 L=5인 파일은 임계 5에서 후보가 아니다. | must | F8 |
| R5 | TypeScript 상대 specifier `S`(`.`으로 시작)는 아래 순서로 해석한다. B는 `normpath(dir(importer)/S)`이다. 프로젝트 안의 분석 대상 모듈과 처음 일치하는 것이 해석 대상이다. ① B 자체(B의 마지막 확장자가 SOURCE_EXTENSIONS에 있을 때) ② B 문자열 뒤에 각 SOURCE_EXTENSIONS를 덧붙인 경로(기존 확장자를 교체하지 않는다) ③ B의 마지막 확장자가 SOURCE_EXTENSIONS에 있을 때만, 그 확장자를 각 SOURCE_EXTENSIONS로 교체한 경로(예: `./foo.js` → `foo.ts`; 기존 동작 유지) ④ `B/index<ext>`. 확장자 순서는 기존 SOURCE_EXTENSIONS 순서를 유지한다. | must | F11 |
| R6 | R5는 정적 import, re-export, dynamic import, import binding 해석(IMPORTS_SYMBOL 및 import 기반 참조 해석) 등 상대 specifier를 해석하는 모든 경로에 적용된다. | must | F11 |
| R7 | 결과: 테스트 파일이 production 파일을 상대 import하면 file granularity에 test→production `TESTS` 엣지가 생긴다(기존 `_add_test_relations` 규칙). typescript-nestjs-realworld에서 `src/tag/tag.controller.spec.ts`→`src/tag/tag.entity.ts` TESTS 엣지가 있고, `src/tag/tag.entity.ts`는 `untested_hub` 후보가 아니다. | must | F11 |
| R8 | Kotlin 심볼의 FQN은 `<package>.<qualname>`이다(package 선언이 없으면 `<qualname>`). wildcard가 아닌 import `X`에 대해 FQN이 `X`와 같은 심볼이 정확히 1개이면, 그 import의 IMPORTS_SYMBOL·IMPORTS 엣지는 그 심볼과 그 파일을 가리킨다. 이때 `resolution=exact`, `confidence=static_certain`, candidates는 비어 있다. | must | F7 |
| R9 | FQN 일치가 2개 이상이면 resolution은 `ambiguous`, confidence는 `static_inferred`이다. 대상은 FQN 일치 심볼 중 symbol id 정렬 첫 번째이고, 나머지가 candidates가 된다. FQN 일치가 0개면 기존 단순 이름 해석을 그대로 쓴다. | must | F7 |
| R10 | Kotlin 파일 F가 R8로 심볼 T를 import했다면, F 안의 단순 이름 참조 중 T의 이름(import 경로 마지막 조각)과 같은 참조는 T로 해석한다. 이때 exact, static_certain이다.  | must | F7 |
| R11 | R10의 결과로 package 의존(`analysis/structure.py`)은 handoff 재현에서 `com.c -> com.a`이고 tier는 certain이다. `com.c -> com.b`는 어떤 tier에도 없다. | must | F7 |
| R13 | `smallest_node_at_line`(설정값 사용처 등 줄→노드 귀속)에서 span 길이가 같은 후보가 여럿이면 kind가 file·module이 아닌 노드를 우선한다. 그 밖의 동률은 기존 순서를 유지한다. R3 때문에 파일 전체를 덮는 symbol과 module span이 같아져도 귀속이 바뀌지 않게 하기 위함이다. | must | R12, F8 부작용 |
| R12 | R1–R11로 설명되지 않는 기존 출력은 바뀌지 않는다. | must | I2 |

# Errors
- 상대 specifier가 프로젝트 밖을 가리키거나 일치하는 파일이 없다.
  - 관찰 신호: 엣지가 생기지 않는다. 기존 동작이며 예외는 없다.
  - 실패 후 상태: 나머지 import는 계속 해석된다.
- Kotlin import FQN이 일치하지 않는다.
  - 관찰 신호: 기존 단순 이름 해석 결과가 나온다(unique_name, ambiguous, 또는 엣지 없음).
  - 실패 후 상태: 분석은 계속된다.
- 디코딩 대체 문자(`�`)나 제어 문자가 포함된 소스.
  - 관찰 신호: 예외 없이 R1 규칙대로 줄을 센다.
  - 실패 후 상태: 해당 없음.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | `"a\nb\nc\nd\ne\n"` | L=5, lines 5개 |
| C2 | boundary | `""` / `"\n"` / `"a"` / `"a\n\n"` | L=0/1/1/2 |
| C3 | edge | `"a\x0cb\n"`, `"a\rb\n"`, `"a b"` | L=1, lines[0]이 원문 문자를 보존 |
| C4 | edge | `"a\r\nb\r\n"` | L=2, lines=("a","b") |
| C5 | boundary | 5줄+끝 개행 Python/TS/Kotlin 파일, symbol granularity, 임계 5 / 6줄 파일 임계 5 | module end_line=5, large_node 없음 / 6줄은 후보(line_count 6) |
| C6 | normal | 한 줄 168KB 파일(`\x0c` 포함 없음), file granularity | line_count=1 |
| C7 | normal | TS `a/b.spec.ts`가 `import {X} from './x.entity'`, `a/x.entity.ts`에 `export class X` | IMPORTS(exact) b.spec→x.entity, file granularity TESTS 엣지, `x.entity.ts`는 untested_hub 아님 |
| C8 | boundary | specifier `./x.entity.ts`(확장자 명시) / `./dir`(index.ts) / `./x`와 `./x.ts`·`./x/index.ts` 동시 존재 / `./foo.js`이고 `foo.ts`만 존재 | 각각 x.entity.ts / dir/index.ts / x.ts / foo.ts |
| C9 | error | specifier `./missing.entity`, `../../outside` | 엣지 없음, 예외 없음 |
| C10 | normal | TS re-export `export * from './a.dto'`, dynamic `import('./b.service')` | RE_EXPORTS·dynamic IMPORTS 엣지 생성 |
| C11 | normal | `com/a/Foo.kt`(package com.a, class Foo), `com/b/Foo.kt`(package com.b, class Foo), `com/c/Use.kt`(import com.a.Foo, Foo 사용) | Use→com.a Foo IMPORTS_SYMBOL exact/certain, 참조 엣지 exact, package 의존 com.c→com.a certain, com.c→com.b 없음 |
| C12 | edge | 같은 FQN을 두 파일이 선언 / import FQN 미존재(외부 라이브러리) / default package 심볼 import | ambiguous(R9) / 기존 단순 이름 해석 / qualname FQN 일치 |
| C13 | edge | nested class `import com.a.Outer.Inner` | Inner 심볼로 exact |
| C15 | edge | `consumer.py`가 함수 `consume` 하나(파일 전체 2줄)이고 설정 key 문자열 사용 | CONFIGURES 엣지 대상은 `consume` |
| C14 | normal | 실제 fixture 4개 base vs HEAD | 변화가 모두 F id로 설명됨(R12) |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 결함 수정이 본 목적 |
| Performance efficiency | yes | TS 해석 엣지가 늘어 분석 시간이 바뀔 수 있음 |
| Compatibility | yes | JSON schema·CLI 유지 필요 |
| Interaction capability | no | UI 변경 없음 |
| Reliability | yes | 비정상 개행·이름에서 예외 없어야 함 |
| Security | no | 새 입력·권한 경계 없음 |
| Maintainability | yes | 변경 줄 테스트 가능성 |
| Flexibility | no | 설정·확장점 변경 없음 |
| Safety | no | 물리적 위해 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Performance / time behaviour | file granularity CLI 분석, fixture 4개 | HEAD 실행 시간 중앙값(5회) ÷ base_commit 실행 시간 중앙값(5회), 비율 | ≤ 1.25 | review: `tests/fact_defects_evidence/benchmark.md` | default |
| Q2 | Compatibility / interoperability | JSON 출력 | key 집합·schema_version 비교, base vs HEAD | 차이 0 | automated | default |
| Q3 | Reliability / fault tolerance | SourceText·TS analyzer 무작위 입력 | fuzz oracle 위반 수 | 0 | fuzz | default |
| Q4 | Maintainability / testability | base_commit 이후 변경된 Implementation 줄 | `diff_coverage.py`: 변경 실행 줄 중 실행된 비율과 변경 분기 중 실행된 분기 비율, % | ≥ 90 | automated | default |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | R1,R2,C1–C4 | `repository.models.SourceText.lines` | unit | equivalence partitioning + boundary value (2-value) | EP: 빈 / `\n` 종료 / 비종료 / CRLF / 비구분 제어문자 7종; BVA: 길이 0,1 및 마지막 개행 유무 | 100% | lines 길이·내용이 독립 참조 구현과 일치 | pytest |
| V2 | R2,R3,C5,C6 | file granularity 노드 `cost.line_count`·span end_line, Python·TS·Kotlin module 노드 end_line | integration (임시 프로젝트 → 각 analyzer, CLI 아님) | equivalence partitioning | 3 언어 × {끝 개행 있음, 없음, 빈 파일} | 100% | end_line = max(1,L), file line_count = L | pytest |
| V3 | R4,C5 | `analyze_bottlenecks` symbol granularity large_node | integration | boundary value (3-value) | L ∈ {임계-1, 임계, 임계+1}, Python 1언어 + TS·Kotlin은 임계값만 | 100% | 후보 유무와 line_count | pytest |
| V4 | R5,R6,C7–C10 | TypeScriptAnalyzer 엣지 | integration | decision table | 규칙: ①확장자 명시 ②점 포함 이름+ext 덧붙임 ③JS 확장자 specifier(`./foo.js`)가 TS 파일로 교체 해석 ④index ⑤②·④ 동시 존재 시 ② 우선 ⑥미존재 ⑦프로젝트 밖; 경로: 정적 import, re-export, dynamic import, import binding(IMPORTS_SYMBOL) | 규칙 7개 100%, 경로 4개 각 1회 이상 | 엣지 대상 파일·relation | pytest |
| V5 | R7,C7 | file granularity TESTS 엣지와 untested_hub | integration + fixture | scenario | 합성 프로젝트 1, typescript-nestjs-realworld | 100% | TESTS 엣지 존재, 해당 파일 untested_hub 아님 | pytest |
| V6 | R8,R9,C11–C13 | KotlinAnalyzer import 엣지 | integration | decision table | FQN 일치 1 / ≥2 / 0(단순 이름 fallback) / default package / nested | 100% | target·resolution·confidence·candidates | pytest |
| V7 | R10,R11,C11 | Kotlin 참조 엣지와 package 의존 | integration | scenario | C11 시나리오, import 없는 파일 변형 1 | 100% | 참조 exact, package 의존 tier | pytest |
| V12 | R13,C15 | 설정 귀속(Python analyzer enrichment) | integration | equivalence partitioning | {module=symbol span 동률, symbol이 더 작음, 줄을 덮는 symbol 없음} | 100% | CONFIGURES 대상 | pytest |
| V8 | R12,C14,Q2 | 실제 fixture 출력 | integration | error guessing | 설명 안 되는 변화, schema key 변화 | none — experience-based | review.md 집계와 key 비교 | review + pytest |
| V9 | Q1 | CLI 시간 | system | random(반복 측정) | fixture 4개 | 100% | 비율 ≤1.25 | benchmark.md |
| V10 | Q3 | fuzz 표면 (a)(b) | unit/integration | random | seed 20261019, 예산 전량 | 100% | 위반 0 | main fuzz |
| V11 | Q4 | 변경 Implementation 줄 | — | branch testing | 변경 분기 | 90% | diff_coverage 통과 | Test command |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| D1 | F11 원인은 익명 함수 미스캔이 아니라 `_resolve_import`의 `with_suffix`가 `tag.entity`를 `tag.ts`로 바꾸는 것이다. 수정 범위를 상대 import 해석으로 바꾼다. | 실행 확인: 수정 시뮬레이션에서 nestjs fixture IMPORTS 6→71, TYPE_USES exact 1→65, TESTS 0→6. 모듈 최상위 코드 스캔은 범위 밖으로 둔다. | brief v1 — approved |
| D2 | 줄 구분은 `\n`만 쓰고 CRLF는 1개로 센다. 단독 `\r`은 구분자가 아니다. | tree-sitter는 `\n`으로 행을 센다. Python ast는 단독 `\r`도 개행으로 보므로, 단독 `\r`만 쓰는 Python 파일에서는 span이 어긋날 수 있다(드묾). | brief v1 — approved |
| D3 | Kotlin import된 이름은 그 파일 안에서 import 대상이 우선이다(R10). | Kotlin 언어 규칙. alias·wildcard는 범위 밖이다. | brief v1 — approved |
| D4 | 기존 golden/characterization 기대값은 F id로 설명되는 경우에만 갱신한다. | 해석 엣지가 많이 바뀌어 nestjs 관련 기대값이 바뀔 것으로 예상한다. | brief v1 — approved |
| D5 | 성능 임계 1.25, 변경 줄 branch coverage 90%, fuzz 예산 (a) 20,000·(b) 500 | 직전 run의 관행을 따른다 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| R1,R2 | C1–C4,C6 | V1,V2,V10 | pytest, fuzz |
| R3,R4 | C5 | V2,V3 | pytest |
| R5,R6 | C7–C10 | V4,V10 | pytest, fuzz |
| R7 | C7 | V5 | pytest |
| R8,R9 | C11–C13 | V6 | pytest |
| R10,R11 | C11 | V7 | pytest |
| R13 | C15 | V12 | pytest |
| R12 | C14 | V8 | review, pytest |
| Q1 | — | V9 | benchmark |
| Q2 | C14 | V8 | pytest |
| Q3 | — | V10 | fuzz |
| Q4 | — | V11 | Test command |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 4 |
| verifier invocations | 2 |
| open finding ids | VF1-1, VF1-2 |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V1 | 4 | tests/test_fact_defects.py::test_V1_* (HEAD) | accepted | verifier 1 accept; hand mutations M1–M12 killed (hand-mutations.json) | — |
| V2 | 4 | test_V2_* (+ empty-file span is None ×3) | pending | VF1-1 addressed; M13 killed | test_fact_defects.py changed (batch 4) |
| V3 | 4 | test_V3_* | accepted | verifier 1 accept; hand mutations M1–M12 killed (hand-mutations.json) | — |
| V4 | 4 | test_V4_* (7 rules, 4 paths) | accepted | verifier 1 accept; hand mutations M1–M12 killed (hand-mutations.json) | — |
| V5 | 4 | test_V5_* | accepted | verifier 1 accept; hand mutations M1–M12 killed (hand-mutations.json) | — |
| V6 | 4 | test_V6_* | accepted | verifier 1 accept; hand mutations M1–M12 killed (hand-mutations.json) | — |
| V7 | 4 | test_V7_* | accepted | verifier 1 accept; hand mutations M1–M12 killed (hand-mutations.json) | — |
| V8 | 4 | test_V8_*, review.md Results + VF1-2 follow-up, review-output/sample-check.txt | pending | VF1-2 addressed | — |
| V9 | 4 | benchmark.md, benchmark-result.json | accepted | verifier 1 accept; hand mutations M1–M12 killed (hand-mutations.json) | — |
| V10 | 4 | fuzz_fact.py: (a) 20,000 / (b) 500, 위반 0; old-bug 감지 31/50 | accepted | verifier 1 accept; hand mutations M1–M12 killed (hand-mutations.json) | — |
| V11 | 4 | Test command diff coverage 71/71 = 100% | accepted | verifier 1 accept; hand mutations M1–M12 killed (hand-mutations.json) | — |
| V12 | 4 | test_V12_* | accepted | verifier 1 accept; hand mutations M1–M12 killed (hand-mutations.json) | — |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 6 | — | — | batch 4 applied; Test command 2738 passed, diff coverage 100%; M13 (empty-file span) killed by V2 tests | 재검증 |
| 5 | verifier 1 RETRY: VF1-1 (V2), VF1-2 (V8); advisories A1–A4 | evidence gaps | VF1-1 → test-implementer; VF1-2 → main completes the review record; A1/A2 tests added; A3 fuzz log committed. Hand mutations 10/10 killed; mutation tool 27 killed, 2 survived (equivalent: `rsplit(".", 1)`→`2`, rechecked by main) | 진행 중 |
| 4 | — | — | 비교기 일반화(원본 해석 등급과 관계없이 exact 조각 1개 허용) 후 Test command 2735 passed, diff coverage 100% | 통과 |
| 3 | 전체 Test command 8 failed: nestjs O11 standalone archive 비교(8 subtests). archive 재생성 후 android·kotlin 2건이 `assert_candidate_policy_transition`에서 실패 | test/evidence defect: base는 Kotlin에서 (from,to,relation)가 같은 엣지를 하나로 합쳤다. F7 이후 합쳐진 엣지가 exact일 수 있는데, 비교기는 ambiguous/unique_name 원본의 분할만 허용한다 (verified: `diffk.py`, DefaultSearchContentsRepository→PopulatedNewsResource IMPORTS) | archive·baselines를 patched 5737113에서 재생성. 비교기에 exact 원본 분할 규칙 추가를 test-implementer에 지시 | 진행 중 |
| 2 | 전체 suite 50 failed: `test_all_config_formats_direction_and_value_not_key`(CONFIGURES가 함수 대신 module로), unicode line_count 2→1(F9), TS file span end 3→2(F8), 이전 run의 base manifest byte-equal·size ratio 47건 | 설정 귀속은 R3로 module·symbol span 동률이 생겨 `smallest_node_at_line`이 module을 고름(verified: min은 첫 원소 선택). 나머지는 F id로 설명되는 기대값 변화 | v3: R13, enrichment.py 추가, manifest 재생성 절차 | 재dispatch |
| 1 | test-implementer challenge: `./foo.js`→`foo.ts` 해석이 v1 R5에서 사라짐(기존 동작 회귀, R12 충돌); R10 멤버 우선 조항은 Kotlin analyzer에 해당 메커니즘이 없어 검증 불가 | spec gap | v2: R5 ③ 교체 규칙 추가, R10 조항 삭제, V7 변형 교체 | 재dispatch |
| 0 | handoff F11 가설: 모듈 최상위 익명 함수 미스캔 | hypothesis | `_resolve_import` 실행 추적: `./tag.entity` → None | 가설 기각. D1로 범위 변경 |

# Version Log
## v1
- 초안 작성.
## v2
- R5에 ③(SOURCE_EXTENSIONS 확장자 교체) 추가: v1이 `./foo.js`→`foo.ts` 기존 동작을 없애 R12와 충돌. 계약 보완, 승인된 R12 범위 안.
- R10의 멤버 해석 우선 조항 삭제: Kotlin analyzer에 그런 해석이 없음(implementer 보고). V7 변형을 import 없는 파일로 교체.
- R2: 빈 파일 file 노드 span 없음 명시(기존 동작).
- Python 단독 `\r` 파일의 span 불일치는 D2의 알려진 한계로 테스트하지 않음.
## v3
- R13 추가와 Implementation에 `language_analyzers/core/enrichment.py` 추가: R3 적용 후 설정 귀속 회귀(R12 위반)를 막는다. 계약 보완.
- Tests에 이전 run base manifest 재생성 절차 추가: 원래 base commit에 이번 Implementation diff를 적용해 각 기능 테스트의 의미를 보존한다.
## v4
- manifest `base_commit` 필드 유지로 변경: `test_V7_manifest_is_for_the_declared_base_commit`가 값을 검사함. 출처는 manifest-regeneration.md. 계약만 변경.
