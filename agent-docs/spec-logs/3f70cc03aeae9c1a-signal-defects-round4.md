---
version: 6
run_id: 3f70cc03aeae9c1a
status: complete
base_commit: 3b768a9b5e9b79c519bfe667b12b8e980cfa636b
max_verifier_invocations: 2
handoff: agent-docs/handoff/dad85e4830f21190-existing-signal-defects.md
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자 | "handoff에 신호 결함 처리가 남았어?" → "처리하자", 범위 "V12 + Open Questions 전부" | 3회차 V12(review evidence)가 엄격한 귀속 규칙으로 닫히고 handoff Open Questions 3건이 처리된다 |
| I2 | 사용자 | file 모드 `evidence_spread` ≈ fan_in ≥ 2 문제 → "디렉터리 단위로 재정의" | `evidence_spread`가 대상 디렉터리 밖 디렉터리 수로 발동한다 |
| I3 | 사용자 | Kotlin 한 줄 body 오파싱 (A)·(B) 모두 복원, `versions.analysis` "6" (brief 승인) | 한 줄 object·class의 선언과 멤버가 그래프에 나온다 |
| I4 | 사용자 | Kotlin primary constructor field 중복 귀속 수정 | constructor field 노드는 자기 parameter 범위만 스캔한다 |
| I5 | 프로젝트 | 고치지 않은 신호는 그대로 둔다 (3회차 I4 계승) | 3b768a9 대비 출력 변화가 모두 R11–R14로 설명된다 |

# Scope
In scope:
- 3회차 V12 review 스크립트 정정(verifier 2 finding VF2-F2–F5), 3회차 base(cf0cf44)→3회차 HEAD(3b768a9) 비교 재실행.
- R11 evidence_spread 디렉터리 재정의(symbol·file 모드), 보고서·HTML 문구와 정렬 지표.
- R12 KotlinAnalyzer(kotlin-core)의 한 줄 body 오파싱 복원 (A)·(B).
- R13 Kotlin primary constructor field 스캔 범위.
- R14 `versions.analysis` "6".

Out of scope:
- `framework_analyzers/android`의 선언 수집(같은 ast helper를 쓰지만 이번 run에서 출력 불변).
- 그 밖의 Kotlin 오파싱 형태(companion object 자체 수집, supertype 있는 top-level 한 줄 object의 class_body는 (A)로만 처리).
- schema 이름 변경, 새 candidate kind, 3회차 R1–R10 동작 변경.
- ADR·rejection record 작성(완료 후 사용자에게 제안만).

# Paths
Implementation: bottlenecks/core.py, language_analyzers/kotlin/analyzer.py, language_analyzers/kotlin/ast.py, report/bottlenecks/generate.py, renderers/html/static/app.js
Tests: tests/test_signal_defects_round4.py (new), tests/signal_defects_round4_support.py (new, 선택), tests/signal_defects_evidence/review_diff.py, tests/signal_defects_evidence/review_run.sh, tests/signal_defects_evidence/nontest_share.py (new, 선택). 기존 tests/ 파일 조정도 허용한다(3회차 D14와 같은 규칙: 결과 기대값만 갱신, 원래 의도를 기대값만으로 지킬 수 없으면 의도를 보존하는 입력·oracle 변경 허용, 약화 금지, 각 변경에 R11–R14 id와 이유를 `tests/signal_defects_evidence/existing-tests-round4.diff`에 기록). main 전용(test role은 쓰지 않음): `tests/signal_defects_evidence/review.md`, `review-output/`, `review-output-round4/`, `fuzz_signal.py`, `fuzz-run*.log`, `hand-mutations*.json`, `mutation-tool*.json`, `manifest-regeneration.md`, `tests/*_evidence/base_manifest.json` 재생성.

Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','fastapi-official-template','android-nowinandroid','typescript-nestjs-realworld')]" && uv run -q --with-requirements requirements-dev.txt --with coverage python -m coverage run --branch --include=bottlenecks/core.py,language_analyzers/kotlin/analyzer.py,language_analyzers/kotlin/ast.py,report/bottlenecks/generate.py -m pytest -q -p no:cacheprovider --deselect tests/test_analysis_coverage_reporting.py::test_V05_characterization_and_V04_cli_stages --deselect tests/test_analysis_coverage_reporting.py::test_V07_read_parse_counts_match_immutable_characterization --deselect tests/test_analyzer.py::FastAPIRealFixtureSmokeTests::test_fastapi_realworld_fixture_analyzes_without_crashing --deselect tests/test_file_analysis_cli.py::test_V01_direct_builder_defaults_characterization && uv run -q --with coverage python -m coverage json -o .coverage-signal.json && python3 tests/fact_defects_evidence/diff_coverage.py --base 3b768a9b5e9b79c519bfe667b12b8e980cfa636b --coverage .coverage-signal.json --fail-under 90

Review evidence:
- 산출물: `tests/signal_defects_evidence/review.md`(main), stage (a) `review-output/`, stage (b) `review-output-round4/`.
- 입력: self(base worktree의 소스를 `-l python`), `typescript-nestjs-realworld`, `android-nowinandroid`, `futuramaapi`, `fastapi-realworld` × `--granularity file|symbol`, `--json`과 `--bottlenecks`, `PYTHONHASHSEED=0` (`review_run.sh`).
- stage (a): 코드 cf0cf44 vs 3b768a9, 규칙 집합 R1–R10(3회차 spec). stage (b): 코드 3b768a9 vs 이번 HEAD, 규칙 집합 R11–R14. 두 stage 모두 self 입력은 같은 base worktree 소스를 쓴다.
- `review_diff.py <base_dir> <head_dir> <name> <mode> <out.json> --stage a|b`가 아래 RV 규칙으로 모든 차이를 R id에 귀속하거나 `unexplained`에 넣는다. non-test 비율은 `review_diff.py`(또는 `nontest_share.py`)가 계산해 out JSON에 기록한다.
- 기대 결과: 두 stage × 10 출력 모두 `unexplained` 0.

Fuzzing:
- 도구: main이 확장하는 `tests/signal_defects_evidence/fuzz_signal.py`, seed 20261020.
- 표면 C(R11): 디렉터리 1–5개, 파일 2–12개의 임시 Python 프로젝트. 대상 함수 1개를 무작위 파일에 두고, 다른 파일에서 0–3회 호출한다. symbol·file 모드 모두 분석한다.
- 표면 D(R12·R13): 임시 Kotlin 프로젝트. 한 줄·여러 줄 object/class body(멤버 0–3개, 마지막 멤버 뒤 같은 줄 `}` 여부), primary constructor parameter 0–4개(val/var/일반, 기본값에 프로젝트 함수 호출 0–2개)를 무작위로 만든다. 10%는 구문 오류 파일 1개를 포함한다.
- oracle (property):
  - C ① 예외 0 ② 후보의 `directory_count`·`file_count`·발동 여부가 생성기의 독립 계산과 같다 ③ `directory_count ≤ file_count`.
  - D ① 예외 0 ② 생성기가 만든 모든 선언 이름(object/class/멤버/val·var parameter)이 노드로 존재 ③ constructor field 노드의 CALLS 대상 집합이 자기 기본값 식의 호출 집합과 같다.
- 예산: C 1,000 프로젝트, D 1,000 프로젝트.

Mutation tool:
- 도구: `tests/dynamic_flags_evidence/ast_mut.py`.
- 대상: base_commit 이후 변경된 Implementation Python 줄만.
- 표본: 최대 30개, seed 20261020.
- 실행 명령: `uv run -q --with-requirements requirements-dev.txt python -m pytest -q -p no:cacheprovider -x tests/test_signal_defects_round4.py tests/test_signal_defects.py`
- 생존율 임계: 40%.

# Signatures
bottleneck JSON `evidence_spread` metrics: `file_count: int`, `directory_count: int`(new), `line_span: int`, `line_threshold: int`
bottleneck JSON `versions.analysis == "6"`; schema 이름 `bottlenecks.v8`(file)·`bottlenecks.v6`(symbol) 불변
KotlinAnalyzer 노드 id 형식 불변: `kotlin:<file>#<qualname>`

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| R11 | `evidence_spread`: 3회차 R5의 근거 제외(ownership 엣지, 대상 T의 파일과 같은 `file_path`)를 그대로 적용한 남은 근거 집합 E에 대해 `file_count` = E의 서로 다른 `file_path` 수(R5와 같음), `directory_count` = E의 `posixpath.dirname(file_path)` 중 T의 디렉터리(`dirname(T 파일)`; T에 파일이 없으면 제외 없음)와 다른 서로 다른 값의 수. 루트 파일의 디렉터리는 `""`. 발동: `directory_count ≥ 2`, 또는 `file_count == 1`이고 그 파일 근거의 줄 범위 > `large_node_line_threshold`. `line_span`·evidence 목록·후보 id·kind 이름은 R5와 같다. symbol·file 모드 모두. | must | I2 |
| R11r | 보고서(`report/bottlenecks/generate.py`)와 HTML(`app.js`)의 evidence_spread 설명 문구는 "대상 디렉터리 밖 둘 이상의 디렉터리" 의미로, 정렬 지표와 카드 값은 `directory_count`(`<n>개 디렉터리`)로 바꾼다. | should | I2 |
| R12 | KotlinAnalyzer 선언 수집: (A) class/object/companion의 `class_body` 직계 child 중 `ERROR` 노드가 있으면 그 직계 child의 `function_declaration`·`class_declaration`·`object_declaration`·`property_declaration`을 class_body 직계 child와 똑같이 멤버로 수집한다(R4 멤버 범위 제외 포함). (B) `source_file` 직계 child이거나 (B)로 복원된 object의 `statements` 직계 child인 `infix_expression`의 children이 정확히 [`object_literal`(자식에 class_body가 없음), `simple_identifier`, `lambda_literal`]이면 이름 = simple_identifier인 top-level object 선언으로 수집한다. 노드 kind = class, span = infix_expression 전체, 멤버 = lambda_literal의 `statements` 직계 선언(위와 같은 종류), file의 DECLARES 엣지 포함. 그 밖의 infix_expression은 바뀌지 않는다. | must | I3 |
| R12b | (B)로 복원된 object 노드는 multi-line `object X {…}`와 같은 방식으로 호출·READS/WRITES·flag 스캔을 받는다(멤버 범위 제외). `signature`는 `object <name>`. | must | I3 |
| R13 | primary constructor의 `val`/`var` parameter로 만든 field 노드는 그 `class_parameter` 노드를 자기 node로 쓴다. span·cost·signature·CONTAINS 근거 줄·호출/READS/WRITES/TYPE_USES 스캔이 그 parameter 범위로 한정된다. class 노드의 primary constructor 스캔(3회차 R4)은 바뀌지 않는다. 같은 이름 field가 body에도 있으면 기존처럼 처음 수집된 것만 남는다. | must | I4 |
| R14 | bottleneck JSON `versions.analysis`는 "6"이다. | must | I3 (brief 승인) |
| R15 | R11–R14로 설명되지 않는 3b768a9의 출력은 바뀌지 않는다. `framework_analyzers/android` 출력은 불변이다. | must | I5 |
| RV | `review_diff.py` 귀속 규칙(V12): 아래 RV1–RV8. | must | I1, VF2-F2–F5 |

RV 규칙 (stage a는 R1–R10, stage b는 R11–R14 귀속):
- RV1 (edge 비교 key) edge는 (from, to, relation, resolution, confidence, evidence start_line, candidates)로 multiset 비교한다.
- RV2 (stage a R9) 제거 edge와 추가 edge가 relation ∈ {IMPORTS, IMPORTS_SYMBOL}이고 Kotlin이며 key가 `start_line`만 다를 때만 짝지어 R9. 짝은 1:1로 소비한다.
- RV3 (stage a R4)
  - symbol 모드 Kotlin class 노드 C에서 제거된 relation ∈ {CALLS, INSTANTIATES, READS, WRITES} edge는 다음 둘 중 하나면 R4다: C의 멤버(CONTAINS 경로)가 HEAD에 같은 (to, relation)을 가진다, 또는 to가 C 자신의 멤버다.
  - 제거된 TESTS edge는 to가 C의 멤버이거나, C→to의 TESTS 외 relation이 base에 있고 HEAD에 하나도 없을 때 R4다.
  - key가 evidence 줄만 다른 짝(제거·추가)은 relation과 양 끝이 같을 때만 R4 re-key다.
  - 추가 edge는 Kotlin이고 RV2·RV3 짝에 속할 때만 설명된다.
  - file 모드 edge 제거는 같은 입력의 symbol 모드에서 R4로 귀속된 제거 중 같은 relation, 같은 (from 파일, to 파일) 쌍이 있을 때만 R4다. `*` relation 매핑은 없다.
- RV4 (구조 kind) dependency_cycle·package_cycle·unstable_dependency만 대상이다. 후보는 제자리 변경만 허용한다(추가·제거는 unexplained). 변경된 후보는 그 구성 파일 또는 패키지 중 하나가 같은 stage에서 귀속된 제거 edge(stage a R4, stage b R13)의 양 끝 파일 또는 패키지와 겹칠 때만 설명된다. 그 밖의 kind는 RV5 규칙 밖이면 unexplained다.
- RV5 (kind별 방향)
  - large_node: stage a에서는 제자리 변경 중 metrics 키 추가(`token_count`, `token_threshold`)만, 또는 token 임계로 생긴 추가만 R8이다. 제거는 unexplained다. stage b에서는 R13으로 span이 바뀐 constructor field 노드의 제거만 R13이다.
  - unresolved_boundary: stage a 제거는 대상 노드의 base `unresolved_calls` 이름이 모두 HEAD에서 `external_calls`에 있거나, (Kotlin) R4 멤버로 옮겨졌을 때만 R1/R4다. stage b에서는 R13 field 노드의 변화만 R13이다.
  - evidence_spread: 양쪽 각각에서 스크립트가 아키텍처 JSON으로부터 독립 재계산한 후보 집합(stage a base: 3회차 이전 정의, HEAD: R5; stage b base: R5, HEAD: R11)이 실제 후보 id 집합·`file_count`·`directory_count`(stage b HEAD)와 같을 때만 모든 차이가 설명된다.
  - untested_hub: 대상의 pagerank가 바뀐 경우만 R7(stage a). stage b에서는 unexplained다.
- RV6 (key 경로) 허용 추가 경로는 위치까지 고정한다.
  - stage a: 노드 `$.metadata.external_call_count`, `$.metadata.external_calls`, `$.metadata.unresolved_reference_total`, bottleneck `edge_weights.large_node_token_threshold`, large_node 후보 `$.metrics.token_count`, `$.metrics.token_threshold`.
  - stage b: evidence_spread 후보 `$.metrics.directory_count`.
  - 허용 제거 경로: stage a의 R1 필터 metadata(`unresolved_*`)와 unresolved_boundary·evidence_spread 후보 `$.evidence[]` 하위.
- RV7 (metadata·flag·노드)
  - 노드 id 집합: stage a는 불변이다. stage b는 Kotlin R12 복원 노드 추가만 허용한다(fixture에는 0건이 기대값).
  - flag: stage a는 기존 규칙(R6, R4 member)이다. stage b는 R13 field 노드의 dynamic_* 제거만 허용한다.
  - metadata 값 변화: stage a는 R1·R3·R4 키와 `analysis`다. stage b는 R13 field 노드의 `unresolved_*`·`external_*`와 모든 노드 `analysis`다.
  - span·cost·signature 변화: stage b의 R13 field 노드에서만 허용한다.
- RV8 (구조 지표·비율)
  - stage a: fan_in·fan_out·token_cost·betweenness·hop_2는 android에서 R4 제거 edge의 끝점 노드와 그 2-hop 이내 노드만 바뀔 수 있다.
  - stage b: token_cost는 R13 field 노드만 바뀔 수 있다. fan·betweenness·hop_2는 R13 제거 edge의 끝점과 2-hop 이내 노드만 바뀔 수 있다.
  - 모든 출력에 file 모드 non-test 파일의 unresolved_boundary·evidence_spread 비율(base→head)을 기록한다. non-test는 경로에 `test`/`tests`/`spec` 디렉터리가 없고 파일명이 `test_*`, `*_test.*`, `*.spec.*`, `*.test.*`, `*Test.kt`, `*Tests.kt`가 아닌 파일이다.

- RV3a (RV3 보정) "Kotlin class 노드"는 R4 대상 kind 전체(class·object·interface; JSON kind `class`·`interface`)다. "to가 C의 멤버"에는 ambiguous edge의 `candidates` 중 C의 멤버가 있는 경우도 포함한다.
- RV6a (RV6 보정) stage a 허용 추가 경로에 file 모드 unresolved_boundary 후보 `$.evidence[].unresolved_reference_total`(3회차 R3)을 더한다.
- RV5a (unresolved_boundary 제자리 변경)
  - stage a: 사라진 base 이름이 모두 RV5의 이동 조건(HEAD `external_calls` 또는 R4 멤버)을 만족하고, HEAD `unresolved_count`가 HEAD 아키텍처 metadata로 다시 계산한 R3 값(symbol: 대상 노드의 `unresolved_reference_total`, 없으면 목록 길이; file: 구성 레코드 합)과 같을 때만 설명된다.
  - stage b: 대상(symbol 모드 노드, file 모드 파일)이 R13 constructor field 노드이거나 그런 노드를 포함하고, HEAD 값이 위 R3 재계산과 같을 때만 설명된다.
- RV10 (stage b R13 edge·metadata, 아래 "constructor field"는 RV11의 식별)
  - 제거: from이 constructor field이고 relation ∈ {CALLS, INSTANTIATES, READS, WRITES, TYPE_USES}이며 evidence 줄이 그 field의 HEAD span 밖이면 R13.
  - re-key: from 또는 to가 constructor field이고 relation이 같고 key 차이가 evidence 줄뿐인 제거·추가 짝은 R13(CONTAINS 포함). 짝은 1:1로 소비한다.
  - stage b에서 추가된 노드(R12)에 닿는 edge는 R12.
  - constructor field의 metadata `line_number`·`end_line_number`가 HEAD span과 같으면 R13. constructor field와 그것을 포함한 file 노드의 `unresolved_*`·`external_*` 키 추가·제거·값 변화는 R13.
- RV11 (constructor field 식별) kind `field`이고, CONTAINS 부모가 class·interface이며, base 쪽 signature가 `(`로 시작하거나 `constructor(`를 포함하고, span이 부모 span 안에 있는 노드.
- RV12 (evidence 색인) R13·R12 edge 변화가 있는 입력에서 후보 evidence 레코드의 `detail_edge_index`·`detail_edge_indices` 값만 다른 제자리 변경은 모든 kind에서 설명된다.
- RV8a (RV8 보정) pagerank·`weighted_centrality_cost`·betweenness·rankings는 전역 지표이므로, 그 입력에 귀속된 edge 변화(stage a R4, stage b R12·R13)가 있을 때 바뀔 수 있다. fan_in·fan_out은 귀속된 edge 끝점만, token_cost는 stage b의 constructor field만, hop_2_token_cost는 그 변화 노드의 2-hop 이내만 바뀔 수 있다.
- RV9 relation은 CONFIGURES로 한정한다.
- RV8b (RV8a 보정) `weighted_fan_in`·`weighted_fan_out`은 fan 규칙, `effective_token_cost`는 token_cost 규칙을 따른다. stage a의 pagerank·rankings는 3회차 R7(전역 정의 변경)에 따라 귀속 edge 변화 없이도 바뀔 수 있다. betweenness는 귀속 edge 변화가 있을 때만 바뀔 수 있다.
- RV5b (RV5a 보정) stage b에서 constructor field 또는 그것을 포함한 대상의 unresolved_boundary 후보 추가·제거는 HEAD 재계산 대상이 없으므로 대상 조건만으로 설명된다.
- RV9 (stage b, R13 → enrichment) R13으로 field span이 좁아지면, 줄 기반 소비자 선택(repository enrichment의 "그 줄을 포함하는 가장 작은 노드")이 다른 field를 고를 수 있다. 다음 조건을 모두 만족하는 제거·추가 edge 짝은 R13으로 귀속된다: relation이 CONFIGURES(또는 그 밖의 enrichment relation)이고, from·evidence가 같고, 양쪽 to가 같은 class의 primary constructor field 노드이며, HEAD 쪽 to field의 span이 evidence 줄을 포함한다. 짝은 1:1로 소비한다.

# Errors
- 구문 오류 Kotlin 파일(ERROR 노드 다수) — 예외 없음, 수집 가능한 선언만 수집, analysis coverage는 기존처럼 has_error 기록.
- (B) 패턴이 아닌 infix_expression(예: `a to b`) — 선언으로 수집하지 않음, 출력 불변.
- `review_diff.py`에 입력 파일 누락 — 예외로 종료(0이 아닌 종료 코드), out JSON 생성 안 함.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | symbol 모드: `a/t.py`의 `f`를 `b/x.py`, `c/y.py`에서 호출 | evidence_spread, file_count 2, directory_count 2 |
| C2 | boundary | `f`를 `b/x.py`, `b/y.py`에서 호출 | file_count 2, directory_count 1, 후보 없음 |
| C3 | boundary | `f`를 `a/u.py`(대상과 같은 디렉터리), `b/x.py`에서 호출 | directory_count 1, 후보 없음 |
| C4 | boundary | 근거 파일 1개, 줄 범위 threshold / threshold+1 | 없음 / 후보(directory_count 1) |
| C5 | normal | file 모드에서 C1·C2 | symbol 모드와 같은 발동, metrics |
| C6 | edge | 루트 파일 `t.py` 대상, `x.py`(루트)·`b/y.py` 근거 | directory_count 1 (루트 `""` = 대상 디렉터리) |
| C7 | normal | `object X { var y = 0 }` | 노드 X(class), X.y(field), CONTAINS X→X.y, DECLARES file→X |
| C8 | normal | `class K { val v = 1 }`, `object O : B() { val y = 0 }`, 중첩 `object B { val c = 1 }` | K.v, O.y, A.B.c field |
| C9 | normal | `object Q { fun f() = g() }` (top-level 한 줄) | Q, Q.f; CALLS Q.f→g, Q에는 CALLS g 없음 |
| C10 | edge | `val p = a to b` 같은 일반 infix | 선언 추가 없음 |
| C11 | normal | `class C(val a: Int = foo(), val b: Int = bar(), c: Int = baz())` | C.a CALLS foo만, C.b CALLS bar만, C CALLS foo·bar·baz |
| C12 | normal | 여러 줄 constructor, parameter별 줄 | field span = 자기 parameter 줄 |
| C13 | error | 구문 오류 Kotlin 파일 + 정상 파일 | 예외 없음, 정상 파일 선언 수집 |
| C14 | normal | 실제 fixture·self, 3b768a9 vs HEAD | 변화가 R11–R14로 설명 |
| C15 | normal | 실제 fixture·self, cf0cf44 vs 3b768a9 | 변화가 R1–R10으로 설명(엄격 규칙) |
| C16 | normal | 임의 bottleneck 출력 | `versions.analysis == "6"` |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 신호 정의·선언 수집 정확성 |
| Performance efficiency | yes | 대형 입력(self) 분석 시간 회귀 방지 |
| Compatibility | yes | JSON key·schema 이름이 소비자 계약 |
| Interaction capability | no | 문구 변경만, 상호작용 변화 없음 |
| Reliability | yes | 구문 오류 Kotlin 파일에서 crash 없음 |
| Security | no | 입력 처리 경계·권한 변화 없음 |
| Maintainability | yes | review evidence가 재현 가능하고 규칙이 문서와 일치 |
| Flexibility | no | 설정·이식성 변화 없음 |
| Safety | no | 물리적·인명 위험 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Compatibility / interoperability | JSON 출력, fixture 5개 | stage b key 경로 차이(RV6 허용 제외)와 schema 이름 | 차이 0 | review(review_diff), automated(V7) | I5 |
| Q2 | Reliability / fault tolerance | 구문 오류 Kotlin 파일 | 표면 D fuzz 예외 수 | 0 | fuzz, automated(V6) | Errors |
| Q3 | Performance / time behaviour | file 모드 `--bottlenecks`, android·nestjs·self | `perf.py` 3회 중앙값 HEAD/3b768a9, 초 비율 | ≤ 1.25 | review(perf 기록) | 3회차 Q4 계승 |
| Q4 | Maintainability / testability | review 절차 | `review.md` 절차대로 재실행 시 같은 out JSON(정렬 후) | 차이 0 | review | VF2-F5 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | R11,C1–C4,C6 | symbol 모드 `analyze_bottlenecks` 후보 (임시 Python 프로젝트 → CLI 또는 analyzer+bottlenecks API) | integration | decision table | 규칙: DT1 외부 디렉터리 2 → 발동; DT2 외부 디렉터리 1·파일 2 → 없음; DT3 같은 디렉터리 파일 + 외부 1 → 없음; DT4 파일 1·범위 threshold → 없음; DT5 파일 1·범위 threshold+1 → 발동; DT6 근거 0 → 없음; DT7 루트 대상(C6); DT8 파일 없는 대상 T(span 없음)에 근거 `x.py`(루트)·`b/y.py` → 제외 없음, directory_count 2(`""`, `b`), 발동 | 100% | 발동, `file_count`, `directory_count`, `line_span` | pytest |
| V2 | R11,C5 | file 모드 같은 DT1–DT5 | integration | decision table | DT1–DT5 file 모드 | 100% | 같음 | pytest |
| V3 | R11r | `report/bottlenecks/generate.py` 출력, `app.js` 문자열 | unit | equivalence partitioning | {생성 보고서의 evidence_spread 설명에 "디렉터리" 포함, 정렬 지표 directory_count 순, app.js 카드 `개 디렉터리`} | 100% | 문자열·순서 | pytest |
| V4 | R12,R12b,C7–C10 | KotlinAnalyzer symbol 노드·엣지 | integration | equivalence partitioning | {(B) object var, (B) object fun + 호출, (B) `data object`, (B) 여러 줄 top-level object 안의 한 줄 중첩 object(`object T {\n fun f() = g()\n object N { val w = 1 }\n}` → T, T.f, T.N, T.N.w; CALLS T.f→g), (A) class val, (A) object : B() val, (A) 중첩 object, (A) companion body property는 out of scope라 제외, 일반 infix(C10), 여러 줄 대조} | 100% | 노드 존재·kind·CONTAINS/DECLARES·CALLS 귀속, signature `object X` | pytest |
| V5 | R13,C11,C12 | KotlinAnalyzer field 노드 | integration | decision table | {val 기본값 호출 → 그 field만; var 기본값 호출 → 그 field만; 일반 parameter 기본값 호출 → class만; 기본값 없는 val → CALLS 없음; 여러 줄 constructor span; parameter 타입 TYPE_USES는 해당 field만; class의 constructor 호출 귀속 유지} | 100% | CALLS/TYPE_USES 대상 집합, span | pytest |
| V6 | C13,Q2 | 구문 오류 Kotlin 파일 | integration | equivalence partitioning | {ERROR만 있는 파일, ERROR + 정상 선언 파일} | 100% | 예외 없음, 정상 선언 수집 | pytest |
| V7 | R14,C16,Q1 | bottleneck JSON symbol·file | unit | equivalence partitioning | {symbol, file} | 100% | `versions.analysis == "6"`, schema 이름 불변 | pytest |
| V8 | R15 | `framework_analyzers/android` 출력 | integration | equivalence partitioning | {android fixture 출력이 3b768a9와 같음(기존 characterization/manifest 통과), C7·C11 입력에서 Android analyzer 출력이 3b768a9와 같음} | 100% | 동일성 | pytest |
| V9 | RV,R15,C14,C15,Q1,Q4 | `review_diff.py` 두 stage × 10 출력 | integration + review | decision table (RV1–RV8 규칙별 합성 JSON 입력) + review | 규칙별 합성 쌍: RV2 start_line만 다름(인정)/resolution도 다름(불인정); RV3 member 동일 edge(인정)/없음(불인정)/file 모드 다른 relation(불인정); RV4 구조 kind 추가(불인정)/겹치지 않는 변경(불인정)/겹치는 변경(인정); RV5 large_node 제거(stage a 불인정), unresolved 이름 external로 이동(인정)/이동 안 함(불인정), evidence_spread 재계산 불일치(불인정); RV6 `external_call_count`가 node_metrics에 나타남(불인정)/node metadata(인정), `token_count`가 large_node 외 후보(불인정); RV7 stage b R13 아닌 노드 span 변화(불인정); RV8 비율 기록 존재; RV6 stage b `directory_count`가 evidence_spread 외 후보 metrics 또는 `node_metrics`에 나타남(불인정); RV9 같은 class field 사이 CONFIGURES 재귀속 + HEAD span이 근거 줄 포함(인정) / 다른 class field로 재귀속(불인정) / HEAD span이 근거 줄 미포함(불인정) | 100% | 합성 입력의 unexplained 유무; 실제 20 출력 unexplained 0 | pytest + review.md |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| D1 | evidence_spread 디렉터리 단위 재정의 | 3회차 review: file 모드 non-test 51–75% 발동 ≈ fan_in ≥ 2 | user answer |
| D2 | Open Questions 전부 포함 | 사용자 범위 선택 | user answer |
| D3 | R12 (B) 복원 포함 | tree dump: top-level 한 줄 object가 infix_expression으로 파싱, 노드 소실. fixture 0건 | user answer (brief 승인) |
| D4 | `versions.analysis` "6", schema 이름 유지, `directory_count` 추가 키 | 발동 의미 변경 | user answer (brief 승인) |
| D5 | 디렉터리 = `posixpath.dirname`, 루트 `""`, 대상 디렉터리 제외, symbol·file 같은 정의 | 단순·결정적 | brief v1 — approved |
| D6 | 보고서·HTML 정렬 지표·문구 directory_count 기준 | 지표 일관성 | brief v1 — approved |
| D7 | R12는 KotlinAnalyzer만, 기존 ast helper 동작은 다른 호출자(android framework)에 불변 | `framework_analyzers/android/analyzer.py`가 같은 helper 사용 | brief v1 — approved (기존 동작 보존 원칙) |
| D8 | review 2단계(a: cf0cf44→3b768a9, b: 3b768a9→HEAD) | 3회차 V12 종결 + 이번 변화 분리 | brief v1 — approved |
| D9 | Test command: 3회차와 같고 diff coverage base 3b768a9, include는 이번 Implementation Python 파일 | 3회차 spec | brief v1 — approved |
| D10 | 기존 테스트 조정 규칙은 3회차 D14 계승 | 3회차 user answer | brief v1 — approved |
| D11 | 이번 run은 3회차(limit)의 후속이며 verifier 예산 2를 새로 갖는다 | handoff Next Step이 새 run을 지정, 범위가 새 요구사항으로 확장됨 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| R11 | C1–C6 | V1, V2 | pytest, fuzz C |
| R11r | — | V3 | pytest |
| R12, R12b | C7–C10 | V4 | pytest, fuzz D |
| R13 | C11, C12 | V5 | pytest, fuzz D |
| R14 | C16 | V7 | pytest |
| R15 | C14 | V8, V9 | pytest, review |
| RV | C14, C15 | V9 | pytest, review |
| Q1 | C14 | V7, V9 | pytest, review |
| Q2 | C13 | V6 | pytest, fuzz D |
| Q3 | — | review(perf) | perf.py |
| Q4 | — | V9 | review |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 2 |
| verifier invocations | 2 |
| open finding ids | none (VF1-F1 closed by verifier 2; advisories VF1-A3 and ledger 7 remain) |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V1 | 6 | tests/test_signal_defects_round4.py (test_V1_*; batch 1, batch 2 DT8), tests/test_signal_defects.py V7 directory_count | accepted (verifier 2) | hand M1, M2, M5, M11 killed; T15 (tool 15/27) killed | R11 symbol code, `expected_spread` support oracle |
| V2 | 5 → 6 (unchanged evidence) | tests/test_signal_defects_round4.py (test_V2_*) | accepted (verifier 1, retained by verifier 2) | hand M3, M4 killed; T15 killed | R11 file code; file 모드 대상은 `details["file_nodes"]`의 file 노드만(파일 항상 있음) → file-less 대상 없음, V2 DT8 불필요 |
| V3 | 5 → 6 (unchanged evidence) | tests/test_signal_defects_round4.py (test_V3_*) | accepted (verifier 1, retained by verifier 2) | hand M6 killed | generate.py, app.js |
| V4 | 5 → 6 (unchanged evidence) | tests/test_signal_defects_round4.py (test_V4_*; batch 1 signatures) | accepted (verifier 1, retained by verifier 2) | hand M7, M8 killed; T16 (tool 16) killed | kotlin ast/analyzer |
| V5 | 5 → 6 (unchanged evidence) | tests/test_signal_defects_round4.py (test_V5_*) | accepted (verifier 1, retained by verifier 2) | hand M9 killed | kotlin analyzer |
| V6 | 5 → 6 (unchanged evidence) | tests/test_signal_defects_round4.py (test_V6_*); fuzz D 1,000 (10% broken file), 0 violations | accepted (verifier 1, retained by verifier 2) | — | kotlin analyzer |
| V7 | 5 → 6 (unchanged evidence) | tests/test_signal_defects_round4.py (test_V7_*) | accepted (verifier 1, retained by verifier 2) | hand M10 killed | core.py version |
| V8 | 5 → 6 (unchanged evidence) | tests/test_signal_defects_round4.py (test_V8_*, git archive of 3b768a9) | accepted (verifier 1, retained by verifier 2) | — | framework_analyzers/android unchanged |
| V9 | 5 | tests/test_review_diff_round4.py (106 synthetic), review_diff.py, review.md Round 4, review-output/ (stage a), review-output-round4/ (stage b): 20/20 unexplained 0; perf Q3 ≤ 1.25; batch 2 RV6 stage b 2 pairs | accepted (verifier 2) | — | review_diff rules RV1–RV12 |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 0 | 3회차 VF2-F2–F5 (V12 귀속 규칙 느슨) | verified (3회차 ledger 11) | RV1–RV8로 규칙 고정, 2단계 review | stage a·b 20개 출력 unexplained 0 (v4 규칙) |
| 1 | stage b android CONFIGURES 14 재귀속이 규칙 밖 | R13 field span 축소로 enrichment 소비자 선택 변화 (verified, TopicFtsEntity line 33) | spec v2 RV9 | 설명됨 |
| 2 | fuzz D: 여러 줄 top-level object 안의 한 줄 중첩 object 누락 | 바깥 object도 (B)로 파싱, 중첩은 statements 안 infix (verified, tree dump) | spec v3, implementer 수정 | fuzz D 1,000 위반 0 |
| 3 | fuzz C harness가 Python symbol id를 경로로 매칭 | harness defect (verified: id `py:e.m0#tgt`) | harness 수정 | fuzz C 1,000 위반 0 |
| 4 | test-implementer spec challenge: RV6 R3 key, RV3 interface·candidates, stage b R13 규칙, RV8 betweenness, detail_edge_index | spec 공백 (verified on real outputs) | spec v4–v5 RV3a·RV5a·RV5b·RV6a·RV8a·RV8b·RV10–RV12 | 20/20 unexplained 0 |
| 5 | 기존 suite 41 failed (manifest 5개·O11 archive) | R11·R13·R14 출력 변화 (verified) | 3회차 절차로 재생성, 6개 모두 patch-r4 이전 byte 재현 확인 | Test command 3277 passed, diff coverage 96.2% |
| 6 | mutation tool 30개 중 27 killed, 3 survived (10%) | triage: 16 declared (V4 data object signature), 15·27 declared (R15 candidate `coverage` 필드; triager insufficient context → main이 `_candidate` 출력 확인) | correction batch 1: test-implementer가 signature·record 필드 assert 추가 | 15·16 재적용 시 killed |
| 7 | diff coverage 미실행 3곳 | analyzer.py 250->252: 이름 없는 멤버(기존 분기 이동, 새 동작 아님); ast.py 112-113: object_literal에 class_body가 있는 infix(R12 (B) 제외 조건, 이 형태를 내는 parser 입력 미확인) | advisory | 96.2% ≥ 90% |
| 8 | verifier 1 RETRY: VF1-F1 R11 file-less target 조항 미검증 (`""`를 자기 디렉터리로 쓰는 변형 통과) | V1 coverage item 누락 (verified, spec gap) | spec v6 DT8, batch 2: V1_TABLE DT8, round-3 V7에 directory_count assert; advisory A1 RV6 stage b 2쌍; A2 stage b 4개 출력 재실행 byte 동일; A4 round4 파일 skip 0; A5 `hand-mutations-round4-recheck.json` | M11·T15·T16 killed |
| 9 | verifier 2 PASS | — | — | complete |

# Version Log
## v1
- 3회차(e91abc221d7deb2a, limit) 후속. V12 정정(RV), Open Questions(R11–R13), R14. 사용자 답변 D1–D4, brief v1 승인.

## v2
- contract-only: RV9 추가. 근거: stage b android symbol 출력에서 CONFIGURES 14개가 `TopicFtsEntity.topicId` → `TopicFtsEntity.name` 등으로 재귀속(config `name` 근거 줄 33 = `@ColumnInfo(name = "name")`, R13 이전에는 모든 constructor field span이 constructor 전체여서 첫 field가 선택됨). R13의 직접 결과이며 brief 항목 변화 없음. V9 coverage item 3개 추가.

## v3
- R12 (B) 범위 보정: 한 줄 중첩 object를 포함한 top-level object는 여러 줄이어도 (B) 형태로 파싱되고, 중첩 object는 복원된 object의 `statements` 안에서 다시 infix_expression이 된다(tree dump, fuzz D #1·#5·#7·#9·#11·#14). (B) 복원을 그 위치까지 적용한다. 승인된 (B) 의도와 같아 brief 재확인 없이 contract 보정으로 기록하고 사용자 보고에 포함. V4 coverage item 1개 추가.

## v4
- contract-only (test-implementer spec challenge 반영): RV3a·RV5a·RV6a·RV8a·RV10–RV12 추가, RV9 relation을 CONFIGURES로 한정. 근거: 실제 출력 review에서 3회차 R3의 file 모드 evidence 키, R4 interface·ambiguous candidates, R13 stage b edge·metadata 변화, 전역 지표 betweenness, edge 제거에 따른 `detail_edge_index` 재번호가 RV1–RV9로 기술되지 않음. unresolved_boundary 제자리 변경은 제안된 "count 비증가" 대신 R3 재계산 일치로 엄격하게 정함. brief 항목 변화 없음.

## v5
- contract-only: test-implementer가 v4 문구 밖에서 해석한 세 가지를 RV8b·RV5b로 명시(weighted fan·effective_token_cost, stage a pagerank R7, stage b unresolved_boundary 추가·제거). 실제 20개 출력 unexplained 0(v4 스크립트). brief 항목 변화 없음.

## v5 (Workflow Control 갱신)
- correction batch 1 기록, verifier 1회차 dispatch 전 invocations 1로 증가.

## v6
- contract-only: verifier 1 VF1-F1(blocking) — R11 "T에 파일이 없으면 제외 없음" 조항이 V1 coverage item에 없음. V1에 DT8 추가. VF1-A1(advisory, 저렴): V9에 stage b `directory_count` 위치 거부 항목 추가. brief 항목 변화 없음.

## v6 (close)
- verifier 2 PASS(V1–V9 accepted, VF1-F1 closed). status complete. 남은 advisory: VF1-A3(R12 (B) object_literal에 class_body가 있는 제외 분기 미실행). 범위 밖으로 남긴 Kotlin 오파싱: 한 줄 class 안의 한 줄 중첩 object(`class A { object B { val c = 1 } }`, top-level ERROR로 파싱), companion object 자체 수집.
