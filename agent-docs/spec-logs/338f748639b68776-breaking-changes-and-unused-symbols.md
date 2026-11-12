---
version: 6
run_id: 338f748639b68776
status: complete
base_commit: 075881f86abf2cd8733e74ae8c4df1d79922c05a
max_verifier_invocations: 3
commit: 075881f86abf2cd8733e74ae8c4df1d79922c05a
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자(eval 소유자, 상시 지시: AI agent 문제를 얼마나 잡는가) | 아무 도구도 못 잡던 가중치 3 유형 P50(하위 호환 깨짐)을 분석기가 잡는다 | 재측정에서 P50 유효 주입 7건 중 분석기 located ≥ 5, 내용 기준 matched > 0 |
| I2 | 사용자 | 가중치 3 유형 P20(불필요한 메서드)을 분석기가 잡는다 | P20 유효 주입 8건 중 분석기 located ≥ 6, matched > 0 |
| I3 | 사용자 | 직전 작업에서 줄인 음성 대조 오탐이 다시 늘지 않는다 | NC1 ≤ 2/16, NC2 ≤ 1/16, NC3 = 0/13, NC4 ≤ 1/14 |
| I4 | 기존 delta·bottleneck 소비자(CLI, eval harness, HTML 보고서, agent handout) | 새 key·후보 종류가 더해져도 기존 소비 코드가 동작한다 | `symbols`가 없는 이전 baseline도 읽히고, 새 key를 뺀 기존 출력은 base_commit과 같다 |

# Scope
In scope: (1) file granularity bottleneck JSON의 `dependency_network.symbols` 심볼 표. (2) `--baseline` delta의 `changed_signatures`·`removed_symbols` 목록과 `symbol_changes` 상태 객체, policy `delta.v4`. (3) 단독 후보 `unreferenced_symbol`(P20). (4) 단독 후보 `unprovided_injection`(NestJS 주입 provider가 consumer module에서 보이지 않음, P50의 module export 제거). (5) 주입 eval 재측정.
Out of scope: P45(여러 목적이 섞인 변경, 사용자 결정으로 미룸), 테스트 품질·보안·의존성 유형, symbol granularity 출력, 호출 인자와 signature의 실제 호환성 판정(인자 개수·이름 대조), NestJS 동적 module(`forRoot` 등)·`{provide, useClass}` provider의 해석, Python·Kotlin·TypeScript 분석기의 signature 문자열 형식 변경, harness 코드 변경.

# Paths
Implementation: report/bottlenecks/generate.py, bottlenecks/symbols.py, bottlenecks/nestjs_visibility.py, bottlenecks/core.py, bottlenecks/delta.py, bottlenecks/__init__.py, code_analyzer/cli.py, framework_analyzers/nestjs/analyzer.py, framework_analyzers/nestjs/graph.py
Tests: tests/test_symbol_changes.py, tests/test_unreferenced_symbol.py, tests/test_unprovided_injection.py, tests/symbol_changes_support.py, tests/symbol_changes_evidence/, 그리고 기존 tests/ file(조정 허용 범위: `"delta.v3"` 기대값을 `"delta.v4"`로; delta key 집합과 `counts` key 집합에 새 key 추가; bottleneck JSON의 `dependency_network` key 집합에 `symbols`·`symbol_columns` 추가; base 출력과 hash·byte·크기 비율로 비교하는 characterization은 비교 전에 `dependency_network.symbols`·`symbol_columns`와 새 후보 종류 두 가지를 제거한 뒤 비교하고 새 항목은 같은 test에서 별도로 단언; `tests/delta_support.py` `ref_delta`를 새 목록까지 독립 구현으로 확장; `--baseline` CLI test의 stdout 기대값에 `[Δ] Symbol changes: …` 한 줄, stderr 기대값에 `[!] Warning: symbol changes not compared (<reason>)` 한 줄 허용; NestJS 분석 결과를 고정한 기대값에 module node `metadata.global`·`metadata.unsupported_fields` 추가. 다른 assertion 약화 금지. 모든 변경은 `tests/symbol_changes_evidence/existing-tests.diff`에 기록)
Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','fastapi-official-template','android-nowinandroid','typescript-nestjs-realworld')]" && uv run -q --with-requirements requirements-dev.txt --with pytest-cov python -m pytest -q -p no:cacheprovider --cov=bottlenecks.delta --cov=bottlenecks.symbols --cov=bottlenecks.nestjs_visibility --cov-branch --cov-report=term-missing --cov-fail-under=90 --deselect 'tests/test_analysis_coverage_reporting.py::test_V05_characterization_and_V04_cli_stages' --deselect 'tests/test_doc_references.py::test_V8_base_choice_cli_output_equals_base_after_removing_new_keys' --deselect 'tests/test_file_analysis_cli.py::test_V01_direct_builder_defaults_characterization' --deselect 'tests/test_nestjs_quality.py::TestRegression::test_O11_characterization_existing_standalone_outputs_are_byte_identical' --deselect 'tests/test_signal_defects_round4.py::test_V4_B_data_object' --deselect 'tests/test_report_modal.py::test_V04_graph_tab_active_modal_selects_and_centres_node' --deselect 'tests/test_report_size_format.py::test_V01_fixture_details_equal_base_details'
Review evidence: R1 — eval 재측정(Traceability F09), 산출물 `~/toy-projects/network-analysis-eval/inject/<repo>/score-symbols.txt`와 main이 쓰는 `tests/symbol_changes_evidence/r1_comparison.md`. R2 — 크기·시간: 네 eval baseline의 bottleneck JSON 크기 증가율과 file granularity 분석 시간 비를 base_commit과 비교.
Fuzzing: main이 작성하는 stdlib harness `tests/symbol_changes_evidence/fuzz/fuzz_symbols.py`, seed 20261112, 대상 `compute_delta`. 생성: 파일 2~8개, 심볼 0~20개(kind·signature·visibility·refs 무작위)를 가진 합성 payload 쌍. oracle — P1(metamorphic) 같은 심볼 표를 이름 변경 경로로 다시 그린 payload와 renames를 주면 두 새 목록이 비고; P2(differential) `symbols` key를 뺀 payload는 v3 결과(새 key 제외)와 같고; P3 결과 두 목록이 F04·F05 정의를 직접 계산한 기준과 같다. 5,000 입력, 예외 0.
Mutation tool: none — mutmut·cosmic-ray 미설치; hand mutation으로 대신한다.

# Signatures
bottlenecks.symbols.symbol_table(architecture) -> list[dict]  # file granularity architecture(details 포함)에서 F01 항목 목록, id 오름차순
bottlenecks.symbols.unreferenced_candidates(architecture) -> list[dict]  # F06 후보
bottlenecks.nestjs_visibility.unprovided_candidates(architecture) -> list[dict]  # F07 후보
bottlenecks.delta.compute_delta(current, baseline, renames=None) -> dict  # 기존 서명 유지, 결과에 F04·F05·F08 key 추가
symbol table: `dependency_network.symbol_columns` = ["id", "file", "kind", "name", "signature", "visibility", "external_refs", "uncertain_external_refs"]; `dependency_network.symbols` = 행 배열, 행은 열 순서대로 [str, int(`file_ids` 색인), "function" | "method" | "class" | "constant", str, str | null, "public" | "private", int, int]; `symbol_table`의 반환값은 F01 항목 dict 목록(file은 "file:<path>")이고 bottleneck JSON 직렬화만 행 형식
delta: 기존 key 전부 + "symbol_changes": {"status": "applied" | "skipped", "reason": null | "baseline_without_symbols" | "current_without_symbols"}, "changed_signatures": [ {"id", "file", "kind", "name", "baseline_signature", "current_signature", "visibility", "external_refs", "uncertain_external_refs"} ], "removed_symbols": [ {"id", "file", "kind", "name", "baseline_signature", "visibility", "external_refs", "uncertain_external_refs"} ]; counts에 "changed_signatures", "removed_symbols"; "policy": "delta.v4"
candidate 공통 필드: 다른 후보와 같이 "id" ("b:" + sha256 16 hex), "coverage": "static_analyzer_relation", "status": "static_candidate"를 함께 가진다
strengthened_candidates의 added_evidence 행: unreferenced_symbol은 ["node", node_id], unprovided_injection은 ["injection", consumer_id, provider_id]
candidate unreferenced_symbol: {"kind": "unreferenced_symbol", "target": "file:<path>", "metrics": {"unreferenced_count": int}, "evidence": [{"node_id", "name", "kind", "start_line"}]}
candidate unprovided_injection: {"kind": "unprovided_injection", "target": "file:<consumer path>", "metrics": {"unprovided_count": int, "uncertain_count": int}, "evidence": [{"consumer_id", "provider_id", "module_ids": [..], "certainty": "certain" | "uncertain", "line": int}]}
CLI: symbol_changes가 applied면 stdout `[Δ] Symbol changes: changed signatures N, removed symbols M`; skipped면 stderr `[!] Warning: symbol changes not compared (<reason>)`

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F01 | file granularity bottleneck JSON의 `dependency_network.symbols`(행 형식, Signatures)는 production 파일(`_category` = production)의 details node 중 kind가 function·method·class·constant인 것마다 한 항목을 갖는다. `signature`는 node의 signature 문자열을 공백 연속을 한 칸으로 줄이고 앞뒤 공백을 뗀 값(없으면 null). `visibility`는 이름이 `_` 또는 `#`로 시작하거나 signature의 이름 앞 단어에 `private`·`protected`·`internal`이 있으면 private, 아니면 public. `external_refs`는 ownership이 아닌 details edge 중 이 node를 target(후보 target 포함)으로 하고 source node의 파일이 다르며 confidence ∈ {static_certain, static_inferred}·resolution ∈ {exact, unique_name}인 edge의 서로 다른 source 파일 수, `uncertain_external_refs`는 같은 조건에서 confidence·resolution이 그 밖인 edge의 서로 다른 source 파일 수(앞의 수에 든 파일 제외). | must | I1, 사용자 선택(심볼 표) |
| F02 | symbol granularity 출력과 symbol granularity bottleneck JSON은 바뀌지 않는다(NestJS module node의 `metadata.global`·`unsupported_fields`도 symbol granularity 출력에는 나타나지 않음). | must | I4 |
| F03 | delta는 `symbol_columns`의 열 이름으로 행을 읽고(file은 각 payload의 `file_ids`로 경로 복원), 비교 전에 baseline 심볼 표의 `id`, 후보 evidence의 `consumer_id`·`provider_id`에 이전 spec(73bd5aa508fa3e88) F05와 같은 이름 변경 매핑을 적용하고 같은 `id`끼리 대응시킨다. baseline 또는 current에 `dependency_network.symbols`가 없으면 `symbol_changes` = skipped와 reason(`baseline_without_symbols` 우선), 두 목록은 빈 목록. | must | I4 |
| F04 | `changed_signatures`: baseline·current 모두에 있는 id 중 두 signature가 모두 문자열이고 비교형이 서로 다르며(비교형 = 공백 문자를 모두 지우고, `)`·`]`·`}`·`>` 바로 앞의 `,`·`;`를 (반복해) 지우고, `'`를 `"`로 바꾼 문자열; 목록에 내는 signature 값은 표의 값 그대로), current 항목이 public이거나 baseline `external_refs + uncertain_external_refs` > 0인 것. 값은 current 항목 기준, refs는 baseline 값. id 오름차순. | must | I1 |
| F05 | `removed_symbols`: baseline에 있고 current에 없는 id 중 baseline 항목이 public이거나 refs 합 > 0인 것. 이름만 바뀐 심볼도 제거로 보고한다(새 이름은 별도 심볼). id 오름차순. | must | I1 |
| F06 | 단독 후보 `unreferenced_symbol`: production 파일마다, kind가 function·method인 details node 중 ownership이 아닌 incoming edge(confidence·resolution 무관, 후보 target 포함, 같은 파일 source 포함, 자기 자신 제외)와 framework 선언 node(language provenance가 아닌 node)에서 오는 `IMPLEMENTED_BY` edge가 하나도 없는 것을 모은다. 제외: 이름이 `__x__` 형태, `constructor`, `main`, signature 이름 앞 단어에 `override`가 있는 것. 하나 이상이면 파일당 후보 하나. delta 강화 판정: `unreferenced_count` 증가 또는 evidence `node_id` 추가. | must | I2 |
| F07 | 단독 후보 `unprovided_injection`: NestJS consumer(module·controller·provider declaration)의 `DEPENDS_ON` 대상 provider P가, consumer가 속한 각 module M(M이 consumer를 PROVIDES·DECLARES하거나 consumer가 M 자신)에서 보이지 않으면 기록한다. 보임 = P ∈ providers(M) ∪ exported(I) for I ∈ imports(M) ∪ exported(G) for 전역 module G; exported(X) = X의 EXPORTS 중 provider ∪ EXPORTS 대상 module Y의 exported(Y)(순환 방지). 전역 module = 클래스에 `@Global()` decorator가 있는 module(NestJS 분석기가 module node `metadata.global`에 기록). M의 `imports`·`providers`에 해석하지 못한 항목(`unsupported_expression` 또는 unresolved)이 있으면 module node `metadata.unsupported_fields`에 그 field 이름(`"imports"`·`"providers"`만, 정렬 list; `@Module(...)` 인자가 객체가 아니면 둘 다)을 기록하고, 없으면 빈 list. consumer가 여러 module에 속하면 P가 보이지 않는 module이 하나라도 있을 때 기록하고, evidence `module_ids`는 P가 보이지 않는 module id 정렬 목록, `certainty`는 그 module 중 `unsupported_fields`가 비지 않은 것이 하나도 없으면 `certain`, 아니면 `uncertain`. consumer가 어느 module에도 속하지 않으면 `module_ids` 빈 목록, `uncertain`. evidence `line`은 그 `DEPENDS_ON` edge evidence의 `start_line`. consumer 파일당 후보 하나, metrics는 certainty별 개수. delta 강화 판정: 두 metric 중 하나 증가 또는 evidence (consumer_id, provider_id) 추가. | must | I1 |
| F08 | delta `policy` = `"delta.v4"`, `counts`에 `changed_signatures`·`removed_symbols` 추가. 기존 key의 의미는 v3와 같다. `--fail-on-new` 선택지와 `regressions`는 바뀌지 않는다. | must | I4 |
| F10 | HTML 보고서 생성기(`python -m report.bottlenecks.generate`)는 `symbols`·`symbol_columns`와 두 새 후보 종류가 든 v9 JSON을 받아 종료 코드 0으로 보고서를 만들고, `report.bottlenecks.generate`의 `KIND_LABELS`에 두 종류의 label(`unreferenced_symbol` = "참조 없는 함수·메서드", `unprovided_injection` = "보이지 않는 주입 provider")이, `KIND_DESCRIPTIONS`에 비지 않은 설명 문자열이 있다(기존 종류와 같이 이 표는 입력 검증과 설명용이며 HTML 본문에 label이 렌더링되지는 않음). | must | I4 |
| F09 | 재측정: 네 저장소 baseline 재생성 후 `tests/rename_comment_evidence/r1_reanalyze.py <repo> --match`로 전체 재실행, `harness.py score` → `score-symbols.txt`, 직전 결과(`score-fp-fix.txt`)와 비교표 작성. | must | I1, I2, I3 |

# Errors
- baseline에 `dependency_network.symbols` 없음 — `symbol_changes` skipped `baseline_without_symbols`, stderr 경고 한 줄 — 두 목록 빈 목록, 나머지 delta 정상, 종료 코드 기존 규칙.
- baseline `symbols`가 list가 아니거나, 행이 열 수와 길이가 다른 list가 아니거나, 행의 `id`·`kind`·`name` 문자열, `signature` 문자열/null, refs 정수, `file`이 `file_ids` 범위의 정수가 아님 — `load_baseline`이 `BaselineError`(`$.dependency_network.symbols[<i>]` 또는 `$.dependency_network.symbols[<i>].<column>`) — 종료 코드 1, 출력 없음.
- baseline에 `symbols`는 있는데 `symbol_columns`가 없거나 8개 열 이름을 모두 담은 문자열 list가 아님 — `BaselineError`(`$.dependency_network.symbol_columns`) — 종료 코드 1.
- NestJS 분석이 없는 저장소 — `unprovided_injection` 후보 없음(빈 목록), 오류 아님.
- details node에 signature 없음 — 심볼 표 `signature: null`; 그 심볼은 `changed_signatures` 판정에서 제외.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C01 | normal | Python 임시 project: `a.py`의 `def f(x, y)`를 `b.py`가 호출, baseline 분석 → `def f(y, x)`로 바꾼 뒤 `--baseline` | `changed_signatures`에 `f` 하나, external_refs 1 |
| C02 | normal | 공개 상수 `ALLOWED`를 다른 이름으로 바꿈(참조 없음) | `removed_symbols`에 `ALLOWED`, visibility public, refs 0 |
| C03 | boundary | private 함수 `_g`의 signature 변경, 참조 0 / 참조 1 | 참조 0: 목록에 없음; 참조 1(다른 파일): 목록에 있음 |
| C04 | edge | 공백·줄바꿈만 다른 signature, 닫는 괄호 앞 끝 쉼표·세미콜론만 다른 signature, 따옴표 종류만 다른 signature | 목록에 없음 |
| C05 | edge | 파일 이름 변경(`a.py → a2.py`) + signature 변경 없음 | 두 목록 비어 있음 |
| C06 | normal | 아무도 호출하지 않는 새 method 2개 추가 | `unreferenced_symbol` 후보 unreferenced_count 증가, delta strengthened 또는 new |
| C07 | edge | 같은 파일에서만 호출되는 helper, `__repr__`, Kotlin `override fun`, TS `constructor`, NestJS controller route handler | `unreferenced_symbol` evidence에 없음 |
| C08 | normal | NestJS: AModule이 `exports: [S]`를 빼고 BModule(imports AModule)의 BController가 S를 주입 | BController 파일에 `unprovided_injection`, certainty certain |
| C09 | edge | B의 imports에 `ConfigModule.forRoot()` 같은 동적 항목 | 같은 판정이 uncertain |
| C10 | edge | S를 `@Global()` module이 export | 후보 없음 |
| C11 | edge | re-export: AModule이 CModule을 export하고 CModule이 S를 export | 보임, 후보 없음 |
| C12 | error | baseline에 `symbols` 없음 | skipped `baseline_without_symbols`, 경고 한 줄, 나머지 delta는 v3와 같음 |
| C13 | error | baseline `symbols[0]`의 external_refs 열 값이 문자열 | `BaselineError` 메시지에 `$.dependency_network.symbols[0].external_refs`, 종료 코드 1 |
| C14 | normal | symbol granularity 실행 | 출력이 base_commit과 byte 동일 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 새 유형 탐지와 기존 대조 오탐 유지 |
| Performance efficiency | yes | 심볼 표·후보 계산이 file 분석마다 추가되고 JSON이 커짐 |
| Compatibility | yes | 기존 baseline·delta·bottleneck 소비자와 기존 test |
| Interaction capability | no | CLI 출력은 한 줄씩 F08·Signatures가 다룸 |
| Reliability | yes | 손상된 baseline과 symbols 없는 baseline이 분석을 깨면 안 됨 |
| Security | no | 새 외부 실행·입력 경계 없음(git 호출 추가 없음) |
| Maintainability | yes | 새 module coverage |
| Flexibility | no | 새 언어 확장 요구 없음 |
| Safety | no | 물리적 위험 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | Performance efficiency / resource utilization | 네 eval 저장소 baseline bottleneck JSON | base_commit 대비 byte 크기 비 | ≤ 1.30 | review(R2) | 기본값 A04 |
| Q02 | Performance efficiency / time behaviour | 네 eval 저장소 file granularity 분석(`harness.py baseline`) | base_commit 대비 시간 비, 3회 최솟값, 유휴 상태 | ≤ 1.10 | review(R2) | 기본값 A04 |
| Q03 | Compatibility / co-existence | 기존 tests | 허용 범위 조정 후 통과 | 전부 통과 | automated, existing-tests.diff | I4 |
| Q04 | Reliability / fault tolerance | C12·C13·fuzz | 예외 수 | 0 | automated, fuzz | Errors |
| Q05 | Functional suitability / functional correctness | 재측정(F09) | P50·P20 located·matched; NC1~NC4 분석기 FP; 칸별 located 하락 | I1·I2·I3 기준; 칸별 하락 ≤ 0.02 또는 건별 원인 보고 | review(R1) | I1–I3 |
| Q06 | Maintainability / testability | bottlenecks/delta.py, symbols.py, nestjs_visibility.py | coverage.py branch | ≥ 90% | automated | 기본값 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V01 | F01 | `symbol_table` 항목, CLI bottleneck JSON | unit(합성 architecture) + integration(임시 project CLI, Python·TypeScript·Kotlin 각 1) | equivalence partitioning | EP1 kind 4종, EP2 비대상 kind(field·module), EP3 test 파일 node 제외, EP4 visibility: `_`·`#`·`private`·`protected`·`internal`·public, EP5 refs: confirmed 다른 파일 / 같은 파일 / uncertain / ownership edge / 후보 target, EP6 직렬화: CLI JSON의 `symbol_columns`와 행 순서·`file_ids` 색인 | 100% | 각 분할의 항목 유무·필드 값이 F01·Signatures와 일치 | Test command |
| V02 | F02, C14 | symbol granularity 출력 | integration | metamorphic | M1 fixture 2종 symbol granularity | 100% | base_commit 출력 hash와 같음 | Test command |
| V03 | F03, C05, C12 | 매핑·skipped | unit | equivalence partitioning | EP1 `file:` 경로 id, EP2 `py:` module id, EP3 baseline symbols 없음, EP4 current symbols 없음, EP5 둘 다 있음, EP6 `unprovided_injection` evidence의 consumer·provider 파일 이름 변경(같은 쌍이면 strengthened 없음) | 100% | 매핑 뒤 대응, skipped reason 우선순위 | Test command |
| V04 | F04, C01, C03, C04 | `changed_signatures` | unit | decision table | D1 public+refs0, D2 private+refs0, D3 private+confirmed refs, D4 private+uncertain refs만, D5 signature 공백만 다름, D5b 닫는 괄호(`)`·`]`·`}`·`>`) 앞 `,`·`;`만 다름, D5c `'`/`"`만 다름, D6 한쪽 null, D7 baseline private → current public, refs0, D8 괄호 안 쉼표 위치·인자 순서가 다름(`f(a,b)`→`f(b,a)`, `f(a, b)`→`f(a)`) | 100% | D1·D3·D4·D7·D8 포함, D2·D5·D5b·D5c·D6 제외 | Test command |
| V05 | F05, C02 | `removed_symbols` | unit | decision table | D1 public 제거, D2 private refs0 제거, D3 private refs>0 제거, D4 이름 변경으로 id 매핑되어 남음 | 100% | D1·D3 포함, D2·D4 제외 | Test command |
| V06 | F06, C06, C07 | `unreferenced_symbol` | unit + integration(Python·TS·Kotlin 임시 project) | equivalence partitioning | EP1 incoming 0, EP2 같은 파일 호출, EP3 다른 파일 호출, EP4 uncertain/ambiguous 후보 target, EP5 자기 재귀만, EP6 제외 이름 4종, EP7 test 파일, EP8 framework `IMPLEMENTED_BY`만(NestJS route handler) | 100% | EP1·EP5만 evidence에 | Test command |
| V07 | F06 | delta 강화 | unit | decision table | D1 count 증가, D2 count 같고 node_id 교체, D3 변화 없음 | 100% | D1·D2 strengthened, D3 없음 | Test command |
| V08 | F07, C08–C11 | `unprovided_injection` | unit(합성 architecture) + integration(NestJS 임시 project) | cause-effect graphing | 원인: own providers / 직접 import export / re-export 사슬 / 전역 module / unsupported imports / unsupported providers / module 없음 / 여러 module 중 일부만 안 보임 / 여러 module의 certainty 혼합; 결과: 후보 없음·certain·uncertain; 분석기 `unsupported_fields` 값(`forRoot()` imports → ["imports"], `{provide, useClass}` providers → ["providers"], 둘 다 없음 → []); `line` 값; delta 강화: unprovided_count 증가 / uncertain_count 증가 / 같은 쌍에서 certainty만 바뀜 / count 감소(보고 없음) / 새 consumer 파일(new_candidates) | 원인·결과·분석기 값·delta 항목 각 1회, 100% | C08~C11 기대 결과 | Test command |
| V09 | F08 | policy·counts·CLI 줄 | unit + integration | equivalence partitioning | EP1 applied, EP2 skipped, EP3 `--baseline` 없음 | 100% | stdout/stderr 줄과 counts key | Test command |
| V10 | Errors, C13 | `load_baseline` | unit | equivalence partitioning | EP1 정상, EP2 symbols가 dict, EP3 필드 누락, EP4 refs 문자열, EP5 signature 정수, EP6 `symbol_columns` 없음, EP7 file 색인 범위 밖, EP8 행 길이 불일치 | 100% | EP2~8 BaselineError 경로 메시지 | Test command |
| V11 | Q04 | `compute_delta` | fuzz | random + metamorphic + differential | Fuzzing 줄 P1~P3 | 5,000 입력 | 위반 0, 예외 0 | main |
| V12 | Q01, Q02, Q05 | 재측정·크기·시간 | review | none — review procedure | R1, R2 | 전부 수행 | 기준 충족 또는 사유 기록 | R1, R2 |
| V14 | F10 | 보고서 생성기 | integration(CLI v9 JSON → generate) | equivalence partitioning | EP1 unreferenced_symbol 있음, EP2 unprovided_injection 있음, EP3 둘 다 없음 | 100% | 종료 코드 0; `KIND_LABELS`·`KIND_DESCRIPTIONS` 항목이 F10과 같음 | Test command |
| V13 | Q03, Q06 | 기존 suite, coverage | automated | branch(coverage.py) | 세 module branch | ≥ 90% | Test command 통과 | Test command |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| A01 | 대상 묶음은 ① 변경 구조, P45는 미룸 | 사용자 선택 | user answer |
| A02 | 새 단독 후보는 candidates 목록에 추가 | 사용자 선택 | user answer |
| A03 | 심볼 표 + delta 목록으로 signature 변경·제거 보고 | 사용자 선택 | user answer |
| A04 | Q01 ≤ 1.30(v2, 사용자 답; v1 1.25), Q02 ≤ 1.10, coverage ≥ 90% | 심볼 표 추정 0.2–0.5 MB(CTFd +16%, ghostfolio +4%) | brief v1 — approved |
| A05 | schema 이름은 `bottlenecks.v9` 유지(추가 key만) | 직전 spec도 snapshot key를 같은 방식으로 추가; delta가 v8·v9만 받으므로 이름을 바꾸면 기존 baseline 읽기 경로가 늘어남 | user answer |
| A06 | public 판정은 이름·signature 수식어로만(언어별 export 규칙 미사용) | Python `exported`는 top-level만, Kotlin은 없음(code-explorer 확인); TypeScript method signature는 `name(p1,p2)` 형식이라 `private` 수식어가 없어 TS는 `_`·`#` 이름으로만 private(implementer 확인); 불확실: Kotlin 파일 단위 `private` top-level 판정 누락 가능 | brief v1 — approved |
| A07 | public이면 참조 0이어도 signature 변경·제거를 보고(재현율 우선) | 주입 7건 중 2건이 외부 호출자만 언급; 대가: NC4(리팩터링 대조)에서 공개 함수 인자 이름만 바꾸면 오탐 가능 — I3에서 NC4 ≤ 1/14 허용 | user answer |
| A08 | `unreferenced_symbol`은 단독 실행에서 전체 미참조 심볼을 보고하고, delta는 증가만 보고 | 기존 후보와 같은 방식; 단독 보고서에는 라이브러리 공개 함수가 많이 나올 수 있음 | brief v1 — approved |
| A09 | NestJS 동적 module·provider 객체는 해석하지 않고 그 module의 판정을 uncertain으로 | 범위 밖 해석을 피하면서 재현율 유지 | brief v1 — approved |
| A10 | 재측정 내용 판정 비용 ≤ $4 예상(직전 249건 $2.60) | 누적 약 $45.3, 상한 $100 | brief v1 — approved |
| A12 | 심볼 표는 열 목록 + 행 배열, file은 `file_ids` 색인 | 객체 형식에서 flask-admin JSON 1.46배(심볼 1,790개, 표 536 KB, key 반복이 약 절반) | user answer |
| A14 | signature 비교형(공백·닫는 괄호 앞 `,`·`;`·따옴표 종류 무시)과 verifier 상한 3 | 재측정에서 포맷 대조 오탐 1/16 → 4/16(ghostfolio 끝 쉼표·따옴표, nowinandroid Kotlin 끝 쉼표) | user answer |
| A13 | framework 선언 node에서 오는 `IMPLEMENTED_BY`를 F06 참조로 셈 | implementer 확인: nestjs fixture에서 route handler 14건이 미참조로 나옴 | user answer |
| A11 | 역할 model: implementer·test-implementer·test-verifier 모두 저장소 기본(sonnet) | 변경이 bottlenecks와 NestJS 분석기에 국한 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F01 | C01, C02 | V01 | Test command |
| F02 | C14 | V02 | Test command |
| F03 | C05, C12 | V03 | Test command |
| F04 | C01, C03, C04 | V04 | Test command |
| F05 | C02 | V05 | Test command |
| F06 | C06, C07 | V06, V07 | Test command |
| F07 | C08–C11 | V08 | Test command |
| F08 | C12 | V09 | Test command |
| F10 | — | V14 | Test command |
| F09 | — | V12 | R1: (1) 네 저장소 `harness.py baseline`; (2) 현재 runs의 result.json·delta.json과 base를 `inject/<repo>/backup-fp-fix/`로 보존; (3) `r1_reanalyze.py <repo> --match --workers 4` 두 stream; (4) `harness.py score <repo>` → `score-symbols.txt`; (5) P50·P20 건별 located·matched, NC1~NC4, 칸별 recall을 `score-fp-fix.txt`와 비교한 표 |
| Errors | C12, C13 | V10 | Test command |
| Q01–Q06 | — | V11, V12, V13 | Fuzzing, R1, R2, Test command |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 2 |
| verifier invocations | 3 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V01 | 6 | Test command run 6 (4100 passed, branch 99%) | accepted (round 2) | M07 killed (test_V01_EP4_visibility[modifier-word-after-name]); M08 killed (test_V01_EP5_external_reference_counts[same-file]) | none |
| V02 | 6 | Test command run 6 (4100 passed, branch 99%); worktree of 075881f at test time, 3 fixtures incl. NestJS | accepted (round 2) | none | none |
| V03 | 6 | Test command run 6 (4100 passed, branch 99%) | accepted (round 2) | M03 killed (test_V03_EP4_*); M04 killed (test_V03_EP1_*) | none |
| V04 | 6 | Test command run 6 (4100 passed, branch 99%) | accepted (round 3) | M01 killed; M02 killed (test_V04_D2_*[private-with-current-refs]) | none |
| V05 | 6 | Test command run 6 (4100 passed, branch 99%) | accepted (round 2) | M01 covers the shared rule | none |
| V06 | 6 | Test command run 6 (4100 passed, branch 99%) | accepted (round 2) | M05 killed (test_V06_EP5_*); M06 killed (test_V06_EP8_*) | none |
| V07 | 6 | Test command run 6 (4100 passed, branch 99%) | accepted (round 2) | none | none |
| V08 | 6 | Test command run 6 (4100 passed, branch 99%) | accepted (round 2) | M09 killed (global); M10 killed (re-export); M11 killed (unsupported fields) | none |
| V09 | 6 | Test command run 6 (4100 passed, branch 99%) | accepted (round 2) | none | none |
| V10 | 6 | Test command run 6 (4100 passed, branch 99%) | accepted (round 2) | none | none |
| V11 | 6 | Test command run 6 (4100 passed, branch 99%) fuzz result tests/symbol_changes_evidence/fuzz/result.json: 4959 executed, 0 violations | accepted (round 3) | n/a | none |
| V12 | 6 | R1 tests/symbol_changes_evidence/r1_comparison.md (score-symbols.txt); R2 bytes 1.052–1.266, time 1.008–1.042 | accepted (main review) | P50 6/7·6/7, P20 8/8·8/8, NC1 2/16, NC2 1/16, NC3 0/13, NC4 0/14, no cell drop | none |
| V13 | 6 | Test command run 6 (4100 passed, branch 99%) | accepted (round 2) | n/a | none |
| V14 | 6 | Test command run 6 (4100 passed, branch 99%) | accepted (round 2) | none | none |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| T1 | Test command 1회차: 19 failed, 4051 passed; coverage 98.86% | 보고서 생성기 kind 미지원(4), NestJS metadata가 canonical hash 변경(2), test의 후보 key 집합 4개 단언(12), TS `private` 수식어 기대(1), key 집합 허용 조정 누락(1) | v3 계약 보완, correction batch 1(implementer: generate.py·F02; test-implementer: 7항목) | 해결: run 2 1 failed(test_file_analysis_cli V07 nestjs-ts, 허용 조정), run 3 4075 passed |
| VR1 | verifier round 1: retry; V01·V02·V04–V07·V09–V11·V13 accepted; V03 open(F-1 consumer/provider rename 매핑 미관찰), V08 open(F-2 delta metric 분기, SC-1 여러 module, SC-2 unsupported_fields 형식), V14 open(SC-3 label 관찰 대상 미정) | 계약 공백 3 + 증거 공백 2 | v4 계약 보완, correction batch 2(test 쪽만) | 해결 후 run 4: V14 2 failed(v4 label 계약 오류 → v5), run 5: 4087 passed; mutations M12–M15 추가, M01–M15 15/15 killed |
| VR2 | verifier round 2: pass; R1-F1·F2·SC1·SC2·SC3 closed; advisories: 분석기가 객체가 아닌 `@Module(x)`에서 ["imports","providers"]를 기록하는지 고정한 test 없음(A1), V14 EP3 단언 약함(A2) | — | — | 통과 |
| R1a | F09 재측정 1회차(v5 구현): P50 탐지 6/7·판정 6/7, P20 8/8·8/8, NC1 2/16, NC2 4/16(목표 ≤1 위반), NC3 0/13, NC4 0/14 | NC2 신규 3건은 포맷터의 끝 쉼표·따옴표·괄호 안 공백 | v6 F04 비교형; delta.py `_squeeze`; test D5b·D5c·D8; fuzz SHAPES 형식 변형; mutations M16–M18; run 6 4100 passed; M01–M18 18/18 killed | 41건 재실행 후 NC2 1/16; I1–I3 충족; R2 크기 비 1.052–1.266(≤1.30), 시간 비 1.008–1.042(≤1.10) |
| VR3 | verifier round 3: pass; V04·V11 accepted, 나머지 round 2 승인 유지; advisories: C04 CLI 끝 쉼표 사례가 TS 분석기 정규화로 공허할 수 있음(A1), D5c 역방향 없음(A2), fuzz를 M16–M18에 돌리지 않음(A3) | — | — | 통과 |
| MU1 | hand mutations M01–M11 (`tests/symbol_changes_evidence/mutations/run_mutations.py`, results.json) | — | 11 executed, 11 killed by the intended assertions; strongest classes chosen: report rule, refs source, skip priority, rename mapping, self/same-file/framework references, modifier position, NestJS global/re-export/unsupported | 통과 |
| F1 | fuzz seed 20261112, 5000 입력(실행 4959): P1·P2·P3 위반 0, 예외 0 | — | `tests/symbol_changes_evidence/fuzz/result.json` | 통과(v2 행 형식); 재실행 ce4b2e6 구현(v3, consumer/provider 매핑 포함): 5000 실행(생성기가 파일 2개 미만을 건너뛰지 않고 채움), 위반 0, 예외 0 |
| S1 | 크기: 객체 형식 flask-admin 1.464, CTFd 1.23 | 심볼마다 key 반복 | 행 형식(v2): CTFd 1.121, flask-admin 1.266, ghostfolio 1.052, nowinandroid 1.104; 한도 1.30(사용자 답) | 통과 예정(R2에서 재측정) |

# Version Log
## v1
- 초안. 근거: 직전 재측정에서 P50·P45·P20은 분석기·도구 모두 matched 0; P50 유효 7건 중 5건 signature 변경, 1건 공개 상수 이름 변경, 1건 NestJS export 제거, P20 8건 모두 호출 없는 새 helper(각 run의 `INJECTION_NOTE.json`). bottleneck JSON에는 심볼 정보가 없고 details 파일에만 있음, CALLS edge에 인자 정보 없음, NestJS 분석기는 provider 가시성을 검사하지 않음(code-explorer, `framework_analyzers/nestjs/analyzer.py` `_resolve`·`_constructor_dependencies`).

## v2
- [intent-mismatch] 심볼 표를 열 목록 + 행 배열로 바꿈(A12): eval 저장소 측정에서 flask-admin 1.46배로 Q01 1.25 초과. F06에 framework `IMPLEMENTED_BY`를 참조로 추가(A13): route handler가 미참조로 보고됨. Errors·C07·C13·V01·V06·V10 갱신. 둘 다 사용자 답.
- Q01 한도 1.25 → 1.30(사용자 답): 행 형식 측정 CTFd 1.121, flask-admin 1.266, ghostfolio 1.052, nowinandroid 1.104(분석 시간 3.7/2.2/13.7/3.6 s).
## v3
- Test command 1회차 19건 실패 분류 후 계약 보완: 보고서 생성기가 새 kind를 `is unsupported`로 거부(I4 누락 → F10·V14, Implementation에 report/bottlenecks/generate.py 추가); NestJS module metadata가 symbol granularity canonical hash를 바꿈(F02 명시); 후보 공통 필드와 added_evidence 행 형식 명시(test가 key 집합 4개로 단언); rename 매핑에 consumer_id·provider_id 포함(test-implementer 지적); TS signature에 수식어 없음을 A06 근거에 기록.
## v4
- verifier round 1(retry) 반영, 계약 보완만: F07에 여러 module consumer 규칙(하나라도 안 보이면 기록, module_ids = 안 보이는 module, certainty 규칙), `unsupported_fields` 값 형식("imports"·"providers" 정렬 list), `line` 출처 명시(SC-1·SC-2, 구현 동작과 같음); F10 label 문자열 명시(SC-3); V03 EP6(consumer·provider rename 매핑, F-1), V08 원인·분석기 값·delta 강화 항목 추가(F-2), V04 D7 추가(advisory).
## v5
- F10 관찰 대상 정정: v4의 'HTML에 label 문자열' 계약은 성립하지 않음(Test command run 4에서 V14 EP1·EP2 실패; `KIND_LABELS`는 `report/bottlenecks/generate.py`에서 검증에만 쓰이고 기존 종류 label도 HTML에 없음). 관찰 대상을 module 표 `KIND_LABELS`·`KIND_DESCRIPTIONS`로 바꿈.
## v6
- [intent-mismatch] F09 재측정에서 I3 NC2 위반(4/16): 포맷터가 바꾼 끝 쉼표·따옴표·괄호 안 공백이 `changed_signatures`로 보고됨. F04 비교형 도입, C04·V04(D5b·D5c·D8) 확장, max_verifier_invocations 2 → 3(사용자 답). 재측정은 `changed_signatures`가 있던 41건만 `--only`로 다시 실행.

# Retrospective
## 2026-11-12
| observation | evidence | how to re-check |
| --- | --- | --- |
| `r1_reanalyze.py --match`는 모든 task의 판정을 다시 돌리므로, 도구 결과가 같아도 도구 쪽 matched 재현율이 움직인다 | ghostfolio script any tool 0.108 → 0.081, CTFd sonnet 0.278 → 0.299 (`score-fp-fix.txt`와 `score-symbols.txt`) | `backup-fp-fix/runs/<task>/result.json`과 현재 result.json에서 `tools`는 같고 `match.verdict`만 다른 task를 센다 |
| fixture 기준 크기 비율은 eval 저장소와 다르게 나온다(fastapi-realworld 1.29, flask-admin 1.27, ghostfolio 1.05) | implementer 보고와 R2 표 | 같은 행 형식으로 fixture와 eval clone을 각각 분석해 base 크기와 비교한다 |
