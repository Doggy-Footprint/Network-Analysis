---
version: 4
run_id: e91abc221d7deb2a
status: active
base_commit: cf0cf4446106f44026dc40d00ba09df977d61ecc
max_verifier_invocations: 2
handoff: agent-docs/handoff/dad85e4830f21190-existing-signal-defects.md
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자 | "handoff-existing signal defects에서 F3, F4, F5, F6, F9 토큰, F10, F12을 처리해야 해" | handoff 표의 F3·F4·F5·F6·F9(토큰)·F10·F12 재현 입력이 기대 결과를 낸다 |
| I2 | 사용자 | F3은 외부 호출을 별도 지표로 분리, F5는 외부 파일만 세고 이름 유지 (handoff Next Step 2) | `unresolved_boundary`는 프로젝트 경계 미확정 호출·동적 플래그에만, `evidence_spread`는 대상 밖 파일 근거에만 발동 |
| I3 | 사용자 | F6 플래그 제거, F10 PageRank 절대 가중치, Kotlin class 스캔에서 멤버 제외 (이번 세션 답변) | 해당 동작이 R5·R7·R4b대로 바뀐다 |
| I4 | 사용자 | 고치지 않은 신호는 그대로 둔다 | 기존 출력 변화가 모두 R1–R10으로 설명된다 |

# Scope
In scope: F3, F4, F5, F6, F9(토큰 비용), F10(PageRank만), F12. 보고서 설명 문구 갱신(evidence_spread, large_node, pagerank).

Out of scope:
- betweenness·`hop_2_token_cost`·fan_in/fan_out 가중치화(구조 지표로 비가중 유지; `weighted_fan_*`는 이미 존재).
- `external_call_count`를 bottleneck `node_metrics`·rankings·후보에 넣는 것.
- Kotlin 같은 파일 overload 병합(F6 일부), TS class의 호출 귀속 변경.
- Kotlin primary constructor field 노드의 스캔 범위.
- schema 이름 변경(`bottlenecks.v6`/`bottlenecks.v8` 유지), 새 candidate kind.
- 핸드오프 후보 C·D, Gradle module.

# Paths
Implementation: bottlenecks/core.py, analysis/graph_metrics.py, analysis/edge_weights.py, analysis/file_graph.py, profiles/edge_weights.v1.yaml, language_analyzers/core/flags.py, language_analyzers/python/graph.py, language_analyzers/typescript/analyzer.py, language_analyzers/kotlin/analyzer.py, language_analyzers/kotlin/ast.py, report/bottlenecks/generate.py, renderers/html/static/app.js
Tests: tests/test_signal_defects.py (new), tests/signal_defects_support.py (new), tests/signal_defects_evidence/ (new; 단 main이 쓰는 `review.md`, `review-output/`, `fuzz_signal.py`, `fuzz-run.log`, `hand-mutations.json`, `mutation-tool.json` 제외). 기존 tests/ 파일 조정도 허용한다. 허용 범위:
- 결과 기대값(golden, characterization, count, hash, 플래그 목록, pagerank 값, `versions.analysis`, 후보 집합)만 갱신한다.
- 각 변경은 R1–R10 중 하나로 설명할 수 있어야 한다. 약화(assert 삭제, 범위 확대)는 금지한다.
- 모든 변경은 `tests/signal_defects_evidence/existing-tests.diff`에 R id와 함께 기록한다.
- 이전 run의 `tests/*_evidence/base_manifest.json` 재생성이 필요하면 main이 run 1과 같은 절차로 한다. 출처는 `tests/signal_defects_evidence/manifest-regeneration.md`. test role은 그 diff를 보지 않는다.

Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','fastapi-official-template','android-nowinandroid','typescript-nestjs-realworld')]" && uv run -q --with-requirements requirements-dev.txt --with coverage python -m coverage run --branch --include=bottlenecks/core.py,analysis/graph_metrics.py,analysis/edge_weights.py,analysis/file_graph.py,language_analyzers/core/flags.py,language_analyzers/python/graph.py,language_analyzers/typescript/analyzer.py,language_analyzers/kotlin/analyzer.py,language_analyzers/kotlin/ast.py,report/bottlenecks/generate.py -m pytest -q -p no:cacheprovider --deselect tests/test_analysis_coverage_reporting.py::test_V05_characterization_and_V04_cli_stages --deselect tests/test_analysis_coverage_reporting.py::test_V07_read_parse_counts_match_immutable_characterization --deselect tests/test_analyzer.py::FastAPIRealFixtureSmokeTests::test_fastapi_realworld_fixture_analyzes_without_crashing --deselect tests/test_file_analysis_cli.py::test_V01_direct_builder_defaults_characterization && uv run -q --with coverage python -m coverage json -o .coverage-signal.json && python3 tests/fact_defects_evidence/diff_coverage.py --base cf0cf4446106f44026dc40d00ba09df977d61ecc --coverage .coverage-signal.json --fail-under 90

Review evidence:
- 산출물: `tests/signal_defects_evidence/review.md`(+ `review-output/`).
- 절차
  1. main이 이 저장소(python), `typescript-nestjs-realworld`, `android-nowinandroid`, `futuramaapi`, `fastapi-realworld`를 base_commit과 HEAD에서 file·symbol granularity로 `--bottlenecks` 분석한다.
  2. kind별 후보 수, non-test 파일 중 `unresolved_boundary`·`evidence_spread` 후보 비율, 노드 `flags` 차이, `untested_hub` 차이를 집계한다.
  3. kind별로 사라지거나 생긴 후보를 최대 10개씩 열어 R id를 기록한다.
- 기대 결과: R1–R10으로 설명되지 않는 변화 0건. 이 저장소 file 모드 non-test 파일의 `unresolved_boundary` 비율 < 71%, `evidence_spread` 비율 < 77%(handoff 측정값 대비 감소; 감소 폭은 기록만 한다).

Fuzzing:
- 도구: main이 작성하는 stdlib harness `tests/signal_defects_evidence/fuzz_signal.py`, seed 20261020.
- 표면 A(분류): Python·TS·Kotlin 임시 프로젝트(모듈 2–3개)를 만들고, 심볼 본문에 R1 분류의 각 형태(외부 import 호출, builtin/전역, 지역 receiver 메서드, 프로젝트 모듈 receiver의 없는 이름, 프로젝트 import된 없는 이름, self/this + 전부 프로젝트인 base, self/this + 외부 base)를 무작위로 0–4개 넣는다. 각 프로젝트 10%에 구문 오류 파일 1개.
- 표면 B(PageRank): 노드 1–30개, 무작위 가중치 (0,1] 그래프.
- oracle (property): A ① 예외 0 ② 노드별 `unresolved_reference_total`(없으면 0)·`external_call_count`(없으면 0)가 생성기가 독립 계산한 경계/외부 호출 수와 같다. B ① 점수 합 = 1 ± 1e-9 ② 모든 점수 > 0 ③ 모든 가중치가 1.0이면 R7 이전 정의(세트 입력)와 같다(±1e-12) ④ 한 엣지 가중치를 낮추면 그 엣지 대상 점수가 증가하지 않는다.
- 예산: 표면 A 언어별 1,000 프로젝트, 표면 B 2,000 그래프.

Mutation tool:
- 도구: `tests/dynamic_flags_evidence/ast_mut.py`(run 2와 같음).
- 대상: base_commit 이후 변경된 Implementation Python 줄만.
- 표본: 최대 30개, seed 20261020.
- 실행 명령: `uv run -q --with-requirements requirements-dev.txt python -m pytest -q -p no:cacheprovider -x tests/test_signal_defects.py`
- 생존율 임계: 40%.

# Signatures
analysis.edge_weights.DEFAULT_LARGE_NODE_TOKEN_THRESHOLD: int == 24000
analysis.edge_weights.EdgeWeights.large_node_token_threshold: int = DEFAULT_LARGE_NODE_TOKEN_THRESHOLD  # 선택 YAML 키 `large_node_token_threshold`, int ≥ 1
analysis.graph_metrics.pagerank(outgoing, config=None) -> Dict[str, float]  # 시그니처 불변, 정의는 R7
노드 metadata(analyzer 출력): `external_call_count: int`, `external_calls: Dict[str, int]`(최다 20개), `unresolved_reference_total: int`(unresolved가 있으면 항상)
file 노드 metadata: `external_call_count: int`(구성 노드 합, 0이면 키 없음)
bottleneck JSON: `edge_weights.large_node_token_threshold`, `large_node` metrics `token_count`, `token_threshold`; `versions.analysis == "5"`
제거: `language_analyzers.core.flags.AMBIGUOUS_NAME`, 노드 flag `ambiguous_name`

# Functional Requirements
용어:
- **프로젝트 모듈**: Python `PythonModuleIndex.is_internal(name)`이 참인 모듈, TS `_resolve_import`가 프로젝트 파일로 해석한 specifier, Kotlin `kotlin_is_internal(fqn, packages)`가 참인 import. Python 미파싱 내부 모듈은 snapshot/디렉터리에 있으나 구문 오류 등으로 파싱되지 않아 `PythonModuleIndex`에만 등록된 모듈이다.
- **닫힌 클래스**: 프로젝트 클래스이고, 모든 base(Python `bases`, TS `heritage`)가 재귀적으로 프로젝트 클래스로 해석된다. Python `object` base는 무시한다. base가 없으면 닫힌 클래스다.
- **미해결 호출**: 기존 해석 결과 target이 None인 호출(Python `is_call` reference, TS call/new expression, Kotlin `call_expressions` 항목). 지역 이름 제외 등 기존 필터는 유지한다.

| id | requirement | priority | source |
| --- | --- | --- | --- |
| R1 | 미해결 호출을 둘로 나눈다. **경계**: ⓐ receiver가 프로젝트 모듈에 바인딩되어 있고(Python module binding, TS namespace import) 그 이름이 그 모듈에 정의돼 있지 않다. ⓑ receiver 없는 호출 이름이 프로젝트 모듈로부터의 import로 바인딩되어 있다(Python `from <프로젝트 모듈> import n`, TS named/default import, Kotlin 명시 import 마지막 조각; wildcard import `pkg.*`는 이름을 특정하지 않으므로 그 아래의 없는 이름은 외부). ⓒ receiver가 Python `self`/`cls`·TS `this`(소유 클래스) 또는 프로젝트 클래스에 바인딩된 이름이고, 그 클래스가 닫힌 클래스다. **외부**: 그 밖의 모든 미해결 호출(외부 import, builtin·전역, 타입을 모르는 receiver, 열린 클래스의 멤버). 경계만 `unresolved_calls`·`unresolved_references`에 남는다. 외부는 `external_call_count`(총수)와 `external_calls`(이름별 수, 최다 20개)에 기록하고, 외부만 있는 노드에는 `unresolved_*` 키가 없다. | must | F3, I2 |
| R2 | file 아키텍처의 file 노드 metadata에 구성 노드 `external_call_count` 합을 기록한다(0이면 생략). 외부 호출은 어떤 후보도 만들지 않는다. | must | F3, I2 |
| R3 | `unresolved_references` 목록은 source 순서 최초 20개로 유지하되, 미해결(경계) 호출이 있으면 세 analyzer 모두 `unresolved_reference_total`(잘리기 전 총수)을 기록한다. `unresolved_boundary`의 `unresolved_count`는 symbol 모드에서 노드의 `unresolved_reference_total`(없으면 목록 길이), file 모드에서 구성 레코드들의 같은 값 합이다. | must | F4 |
| R4 | Kotlin class/object/interface 노드의 호출 스캔(`unresolved_*`, CALLS/INSTANTIATES 엣지), `dynamic_*` 플래그 스캔, READS/WRITES 이름 스캔은 class body 안의 멤버 선언(function, class, object, body `property_declaration` 중 field 심볼이 된 것) 범위를 제외한다. 그 범위는 해당 멤버 심볼이 스캔한다. 헤더 TYPE_USES·supertype 처리와 primary constructor는 바뀌지 않는다. 결과: 메서드 안 호출 4개는 메서드에만 귀속되고, file 모드 `unresolved_count`가 4다. | must | F4, I3 |
| R5 | `evidence_spread`: 대상 노드 T의 근거에서 ① ownership 엣지(`analysis.file_graph.ownership_edge`; symbol 모드에도 적용) ② 근거 `file_path`가 T의 파일(symbol 모드 `T.span.file_path`, file 모드 `metadata.file_path`; T에 파일이 없으면 제외 없음)과 같은 근거를 뺀다. 남은 근거의 서로 다른 파일 수가 `file_count`다. 발동: `file_count ≥ 2`, 또는 `file_count == 1`이고 그 파일 근거의 줄 범위 > `large_node_line_threshold`. `line_span`은 `file_count == 1`일 때만 그 범위, 아니면 0. evidence 목록은 남은 근거만. 후보 id·kind 이름은 그대로다. | must | F5, I2 |
| R6 | 세 analyzer는 `ambiguous_name` 플래그를 만들지 않고, `flags.AMBIGUOUS_NAME` 상수를 제거한다. ambiguous 엣지·candidate_groups·resolution 가중치는 바뀌지 않는다. | must | F6, I3 |
| R7 | `pagerank`: 출발 노드 s의 각 대상 t로 가는 몫은 `damping · score[s] · w(s,t) / outdeg(s)`이다(`outdeg` = 대상 수). 전달되지 않은 몫 `damping · score[s] · (1 − Σ_t w(s,t)/outdeg(s))`은 dangling 몫과 함께 모든 노드에 균등 분배한다. 세트 입력(가중치 1.0)의 결과는 이전과 같다. 따라서 `pagerank({'a':{'b':1.0},'b':{}})` ≠ `pagerank({'a':{'b':0.3},'b':{}})`. `versions.analysis`는 "5"다. betweenness·fan·hop_2는 바뀌지 않는다. | must | F10, I3 |
| R8 | `EdgeWeights.large_node_token_threshold`(선택 YAML 키, 기본 24000, int ≥ 1이 아니면 기존과 같은 `EdgeWeightsError`/`BottleneckInputError`). profile `edge_weights.v1.yaml`에 24000을 명시한다. `large_node`는 `line_count > large_node_line_threshold` 또는 `token_count > large_node_token_threshold`일 때 발동한다(file·symbol 모두). `token_count`는 그 노드의 `node_metrics[...]["token_cost"]`다. metrics는 `line_count`, `line_threshold`, `token_count`, `token_threshold`. bottleneck `edge_weights` payload에 `large_node_token_threshold`를 넣는다. | must | F9 |
| R9 | Kotlin `_imports`의 줄 번호는 import 키워드가 있는 줄이다(앞 빈 줄 포함 안 함). 들여쓰기 import도 같다. | must | F12 |
| R10 | R1–R9로 설명되지 않는 기존 출력은 바뀌지 않는다. R7에 따른 pagerank·`weighted_centrality_cost`·rankings·`untested_hub` 변화, R4에 따른 Kotlin 엣지·플래그 귀속 변화, 보고서 설명 문구 변화는 설명된 것으로 본다. | must | I4 |

# Errors
- 구문 오류가 있는 파일 — 기존 처리(Python 제외, TS·Kotlin 파싱된 부분만) — 예외 없이 다른 파일 분석 계속.
- `large_node_token_threshold`가 0, 음수, bool, float, 문자열 — `load_edge_weights`는 `EdgeWeightsError`, `analyze_bottlenecks`(직접 생성한 EdgeWeights)는 `BottleneckInputError("edge weight token threshold is invalid")` — 보고서 미생성.
- 순환 상속(Python `class A(B)`, `class B(A)`; TS 동일) — 닫힌 클래스 판정이 종료하고 순환 구성원은 프로젝트 클래스로 본다 — 예외 없음.
- PageRank 입력에서 대상이 없는 노드·자기 루프 없음(기존 전처리) — 기존과 같음.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | Python `def run(x): print(len(x))` | `unresolved_*` 없음, `external_call_count == 2`, `unresolved_boundary` 후보 없음 |
| C2 | normal | Python `import requests; def f(): requests.get(u)`, `def g(o): o.append(1)` | 외부 1 / 외부 1 |
| C3 | normal | Python `import pkg.a as m; m.missing()`(pkg.a 프로젝트), `from pkg.a import gone; gone()` | 경계 1 / 경계 1, 후보 있음 |
| C4 | normal | Python class `A`(base 없음)의 `self.nope()`; class `B(unittest.TestCase)`의 `self.assertEqual()`; `C(A)`의 `self.nope()` | 경계 / 외부 / 경계 |
| C5 | normal | TS `console.log(x)`, `import axios from 'axios'; axios.get(u)`, `import * as m from './m'; m.nope()`, `import { gone } from './m'; gone()`, class `extends Repository<X>`(typeorm)의 `this.find()` | 외부 / 외부 / 경계 / 경계 / 외부 |
| C6 | normal | Kotlin `println(x)`, `listOf(1)`, `import com.proj.util.helper`(프로젝트 패키지, 심볼 미수집) 후 `helper()` | 외부 / 외부 / 경계 |
| C7 | boundary | 서로 다른 경계 호출 30개 | 목록 20개, `unresolved_reference_total == 30`, `unresolved_count == 30` |
| C8 | boundary | 경계 호출 20개 / 21개 | total 20 / 21, count 20 / 21 |
| C9 | normal | Kotlin class 안 메서드에 미해결 호출 4개(경계가 되도록 프로젝트 import 이름) | method 노드 4, class 노드 0, file `unresolved_count == 4`; 메서드 안 CALLS는 method 노드에서만 나감 |
| C10 | normal | `x.py`의 `f`를 `x.py`·`y.py`에서 사용 | `evidence_spread` 없음 |
| C11 | boundary | `f`를 `y.py`·`z.py`에서 사용 / `y.py` 한 파일 안 줄 범위 threshold, threshold+1 | 발동(file_count 2) / 없음 / 발동(file_count 1) |
| C12 | normal | symbol 모드: class `K`의 CONTAINS 엣지 + `y.py` 사용 1건 | `evidence_spread` 없음 |
| C13 | normal | Python 같은 모듈 `A.save`·`B.save`, 모듈 간 같은 이름 함수 | 어떤 노드에도 `ambiguous_name` 없음, ambiguous 엣지는 그대로 |
| C14 | normal | `pagerank({'a':{'b':1.0},'b':{}})` vs `{'a':{'b':0.3},'b':{}}` | b 점수가 앞쪽이 더 큼, 각 합 1 |
| C15 | boundary | 모든 가중치 1.0 / 세트 입력 | 이전 정의와 같은 값 |
| C16 | normal | 한 줄 168KB Python 파일(token_cost > 24000), line threshold 2000 | file·symbol 모드 `large_node` 후보, metrics에 token_count·token_threshold |
| C17 | boundary | token_cost == threshold / threshold+1 (임계 조정) | 없음 / 있음 |
| C18 | error | YAML `large_node_token_threshold: 0`, `true`, `1.5`, `"x"`; 키 없음 | 앞 4개 `EdgeWeightsError`; 키 없음 → 24000 |
| C19 | normal | Kotlin 빈 줄 뒤 첫 import(19행), 들여쓰기 import | evidence 19 / 그 줄 |
| C20 | edge | Python 순환 상속 `A(B)`, `B(A)`의 `self.x()` | 예외 없음, 경계 |
| C21 | error | 각 언어 구문 오류 파일 포함 프로젝트 | 예외 없음 |
| C22 | normal | 실제 fixture·이 저장소 base vs HEAD | 변화가 R1–R10으로 설명됨 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 결함 수정이 본 목적 |
| Performance efficiency | yes | 닫힌 클래스 판정·Kotlin 범위 제외가 순회를 늘릴 수 있음 |
| Compatibility | yes | schema 이름·CLI 유지, edge_weights 선택 키 하위 호환 |
| Interaction capability | no | 설명 문구만 바뀜 |
| Reliability | yes | 구문 오류·순환 상속에서 예외 없어야 함 |
| Security | no | 새 입력 경계 없음(코드를 실행하지 않음) |
| Maintainability | yes | 변경 줄 테스트 가능성 |
| Flexibility | yes | 토큰 임계가 설정 가능해야 함 |
| Safety | no | 물리적 위해 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Compatibility / interoperability | JSON 출력, fixture 5개 | 노드·엣지·후보 JSON key 집합(추가 키 R1·R2·R3·R8 제외)과 schema 이름, base vs HEAD | 차이 0 | automated + review | default |
| Q2 | Compatibility / co-existence | `large_node_token_threshold` 없는 기존 YAML | 로드 성공 여부 | 성공 | automated | default |
| Q3 | Reliability / fault tolerance | 3 언어 analyzer, PageRank | fuzz 예외 수 + property 위반 수 | 0 | fuzz | default |
| Q4 | Performance efficiency / time behaviour | `android-nowinandroid`·`typescript-nestjs-realworld`·이 저장소 file 모드 `--bottlenecks` | 3회 중앙값 wall time, HEAD/base 비율 | ≤ 1.25 | review | default |
| Q5 | Maintainability / testability | base_commit 이후 변경된 Implementation Python 줄 | `diff_coverage.py` 변경 줄·분기 실행 비율, % | ≥ 90 | automated | default |
| Q6 | Flexibility / adaptability | token 임계 변경 | 임계를 바꾼 YAML로 C17 | 결과가 임계를 따른다 | automated | F9 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | R1,C1–C4,C20 | PythonProjectAnalyzer 노드 metadata | integration (임시 프로젝트 → analyzer) | classification tree | 분류 {builtin bare, 외부 import bare, 외부 module receiver, 지역/파라미터 receiver, 프로젝트 module receiver 없는 이름(파싱됨·미파싱 내부 모듈 각 1), 프로젝트 from-import 없는 이름, self·cls × {base 없음, 프로젝트 base, 외부 base, `object` base, 순환}, 프로젝트 클래스 이름 receiver × {닫힘, 열림}}; 위치 {함수, 메서드, module 최상위} 중 함수는 전부, 나머지는 builtin·경계 각 1 | 100% | `external_call_count`·`unresolved_reference_total`·`unresolved_calls` 키 유무와 값 | pytest |
| V2 | R1,C5 | TypeScriptAnalyzer metadata | integration | classification tree | {전역 bare, 외부 named import, 외부 namespace receiver, 지역 receiver, 프로젝트 namespace receiver 없는 이름, 프로젝트 named import 없는 이름, 프로젝트 default import 해석 실패, this × {heritage 없음, 프로젝트 heritage, 외부 heritage}, new 외부 클래스} | 100% | 같음 | pytest |
| V3 | R1,C6 | KotlinAnalyzer metadata | integration | equivalence partitioning | {stdlib bare, receiver 메서드, 외부 import 이름, 프로젝트 패키지 import 이름(미수집), wildcard 프로젝트 import + 없는 이름} | 100% | 같음 | pytest |
| V4 | R2 | file 아키텍처 file 노드 metadata, 후보 | integration | equivalence partitioning | {외부 호출 0 → 키 없음, 여러 노드 합}, 외부만 있는 파일 → `unresolved_boundary` 없음 | 100% | 값과 후보 유무 | pytest |
| V5 | R3,C7,C8 | 3 analyzer metadata, symbol·file `unresolved_count` | integration | boundary value (3-value) | 경계 호출 수 {19,20,21} × 언어 3; 30 × 모드 2; file 모드 노드 2개 합 | 100% | 목록 길이 ≤ 20, total·count 값 | pytest |
| V6 | R4,C9 | Kotlin 노드 metadata·엣지·flags | integration | decision table | 멤버 종류 {fun, 중첩 class, object, body property field} × 스캔 {호출, dynamic flag, READS/WRITES}; 대조 {class 직접 init 블록 호출 → class, primary constructor 호출 → class, 멤버가 있는 class의 init 블록 dynamic 호출 → class 플래그 유지}; UTF-8이 아닌 바이트가 멤버 앞에 있는 파일에서도 같은 귀속 | 100% | 귀속 노드와 file 모드 count | pytest |
| V7 | R5,C10–C12 | `analyze_bottlenecks` symbol·file 후보 | integration | decision table + boundary value (2-value) | 외부 파일 수 {0,1,2}; 1개일 때 줄 범위 {threshold, threshold+1}; 자기 파일 근거 {있음, 없음}; ownership 엣지 {CONTAINS, DECLARES}; T 파일 없음(boundary 노드) 1 | 100% | 발동 여부, `file_count`, `line_span`, evidence 경로 | pytest |
| V8 | R6,C13 | 3 analyzer flags, `flags` 모듈 | integration + unit | equivalence partitioning | 언어 3 × {모듈 간 같은 이름, 같은 모듈 메서드 이름}; `AMBIGUOUS_NAME` 속성 없음; ambiguous 엣지 수 불변 | 100% | 플래그 없음, 엣지 있음 | pytest |
| V9 | R7,C14,C15 | `pagerank`, `GraphAnalyzer` | unit | equivalence partitioning + metamorphic | {단일 엣지 1.0 vs 0.3, 세트 입력 vs 1.0 맵, 혼합 가중치 다중 엣지, dangling 노드, 빈 그래프}; metamorphic: 한 가중치 감소 → 대상 점수 비증가, 합 1 | 100% | 손으로 계산한 기대값(±1e-9)과 관계 | pytest |
| V10 | R8,C16–C18,Q2,Q6 | `load_edge_weights`, `analyze_bottlenecks` 후보·payload | unit + integration | boundary value (3-value) + equivalence partitioning | token {threshold−1, threshold, threshold+1} × 모드 2; line {threshold, threshold+1} × 모드 2(token 임계 미달); YAML 값 {0, -1, true, 1.5, "x", 없음, 1}; 직접 생성 EdgeWeights 잘못된 값 1; line 단독 발동 대조 1 | 100% | 발동·metrics·payload·예외 | pytest |
| V11 | R9,C19 | Kotlin IMPORTS·IMPORTS_SYMBOL evidence 줄 | integration | equivalence partitioning | {첫 줄 import, 빈 줄 1·2개 뒤, 들여쓰기, 주석 뒤} | 100% | 줄 번호 | pytest |
| V12 | R10,C22,Q1 | 실제 fixture 출력 | integration + review | error guessing | 설명 안 되는 후보·플래그·엣지 변화, schema key 변화 | none — experience-based | review.md 집계와 key 비교, 기존 suite 통과 | review + pytest |
| V13 | Q3,C20,C21 | fuzz 표면 A·B | integration / unit | random | seed 20261020, A 언어별 1,000, B 2,000 전량 | 100% | 위반 0 | main fuzz |
| V14 | Q4 | CLI wall time | system | — (측정) | 저장소 3개 | 100% | 비율 ≤ 1.25 | review |
| V15 | Q5 | 변경 Implementation 줄 | — | branch testing | 변경 분기 | 90% | diff_coverage 통과 | Test command |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| D1 | F3: 외부 호출 분리(`external_call_count`) | handoff Next Step 2 | user answer |
| D2 | F5: 외부 파일만 셈, 이름 유지 | handoff Next Step 2 | user answer |
| D3 | F6: `ambiguous_name` 플래그 제거 | 이번 세션 답변 | user answer |
| D4 | F10: PageRank 절대 가중치, betweenness·hop_2·fan 비가중 유지 | 이번 세션 답변 | user answer |
| D5 | Kotlin class 스캔에서 멤버 제외(run 2 D4 대체) | 이번 세션 답변 | user answer |
| D6 | R1 경계 기준 ⓐⓑⓒ: 이름이 어떤 프로젝트 심볼과도 안 맞고 프로젝트에 바인딩되지 않은 호출은 프로젝트 코드에 닿을 수 없다 | 기존 resolver가 None을 내는 경로 분석(`python/graph.py:580-637`, `typescript/analyzer.py:813-879`, `kotlin/analyzer.py:384-393`). 열린 클래스 판정은 외부 base의 상속 멤버 가능성 때문 | brief v1 — approved |
| D7 | R7 몫 = w/outdeg(이전 계획의 w/max(Σw,1) 대신) | max(Σw,1)은 0.3 엣지 4개(Σ=1.2)일 때 할인이 사라져 out-degree에 따라 할인이 달라짐. w/outdeg는 1.0만 있는 그래프에서 이전과 같음 | brief v1 — approved |
| D8 | `external_call_count`는 노드 metadata에만(bottleneck node_metrics·후보 아님) | 범위 최소화; 나중에 node_metrics에 추가 가능 | brief v1 — approved |
| D9 | token 임계 기본 24000 = 2000줄 × 관측 12 token/줄(`typescript/analyzer.py` 925줄 10733 token) | 저장소별 편차 있음; YAML로 변경 | brief v1 — approved |
| D10 | `versions.analysis` "4" → "5", schema 이름 유지 | pagerank 정의 변경; delta는 versions를 비교하지 않음(`bottlenecks/delta.py`) | brief v1 — approved |
| D11 | 변경 줄 branch coverage 90%, fuzz A 언어별 1,000·B 2,000, hand mutation 8–10, mutation tool 30개, 성능 비율 ≤ 1.25 | run 1·2 관행 | brief v1 — approved |
| D13 | 기존 크기 비율 테스트(`test_structure_integration.py::test_V11_size_ratio_per_fixture`)는 비율 대신 같은 절대 예산으로 판정: structure가 더한 byte ≤ 0.25 × 3회차 이전 base file bytes(android 7430385, fastapi-realworld 851949, futuramaapi 1726473, nestjs 645354). 축소 하한(≥0.95)은 새 base 대비 유지 | R1·R5로 base가 작아져 futuramaapi 비율 1.334(추가분 407845 byte는 전후 동일). 이전 run의 허용 증가량을 그대로 보존하므로 약화 아님 | brief v1 — default (사용자에게 보고, veto 가능) |
| D12 | ADR `31d2dee6912427d5`의 pagerank 정의 갱신은 완료 후 사용자에게 제안만 한다 | AGENTS.md ADR 규칙 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| R1 | C1–C6,C20 | V1,V2,V3,V13 | pytest, fuzz |
| R2 | C1 | V4 | pytest |
| R3 | C7,C8 | V5,V13 | pytest, fuzz |
| R4 | C9 | V6 | pytest |
| R5 | C10–C12 | V7 | pytest |
| R6 | C13 | V8 | pytest |
| R7 | C14,C15 | V9,V13 | pytest, fuzz |
| R8 | C16–C18 | V10 | pytest |
| R9 | C19 | V11 | pytest |
| R10 | C22 | V12 | review, pytest |
| Q1 | C22 | V12 | review, pytest |
| Q2 | C18 | V10 | pytest |
| Q3 | C20,C21 | V13 | fuzz |
| Q4 | — | V14 | review |
| Q5 | — | V15 | Test command |
| Q6 | C17 | V10 | pytest |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 3 |
| verifier invocations | 1 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V1 | 4 | tests/test_signal_defects.py::test_V1_* | pending (verifier 1) | hand M8 killed; fuzz A python 1,000 위반 0 | — |
| V2 | 4 | test_V2_* | pending | hand M9 killed; fuzz A typescript 1,000 위반 0 | — |
| V3 | 4 | test_V3_* | pending | fuzz A kotlin 1,000 위반 0 | — |
| V4 | 4 | test_V4_* | pending | — | — |
| V5 | 4 | test_V5_* | pending | hand M6 killed | — |
| V6 | 4 | test_V6_* (batch 1 TD2·TD3, batch 3 dynamic·non-UTF-8 추가) | pending | hand M10 killed; tool 3·8·25 재실행 killed | v4 coverage item 추가 |
| V7 | 4 | test_V7_* | pending | hand M3·M4·M5 killed | — |
| V8 | 4 | test_V8_* | pending | — | — |
| V9 | 4 | test_V9_* | pending | hand M1·M2 killed; fuzz B 2,000 위반 0 | — |
| V10 | 4 | test_V10_* (batch 1 TD1, batch 3 line boundary) | pending | hand M7 killed; tool 10 재실행 killed | v4 coverage item 추가 |
| V11 | 4 | test_V11_* | pending | hand M11 killed | — |
| V12 | 4 | tests/signal_defects_evidence/review.md, existing suite, existing-tests.diff, manifest-regeneration.md | pending | tool 11·19·26·29 existing suite kill | base manifests·O11 archive 재생성 |
| V13 | 4 | tests/signal_defects_evidence/fuzz-run.log | pending | 5,000 executions, 위반 0 | — |
| V14 | 4 | review.md Performance | pending | 0.78–0.98 | — |
| V15 | 4 | Test command | pending | diff coverage 97.9% | — |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 1 | 새 테스트 7 failed (V10 2, V6 5) | test defect: `reach_support.Graph`의 빈 detail 표(verified), Kotlin top-level var 미수집(verified), constructor field 이중 스캔은 범위 밖(verified) | correction batch 1 | 197 passed |
| 2 | 기존 suite 64 failed: base manifest byte/size 비교 | 이번 run의 의도된 출력 변화(verified) | base manifest 5개 재생성(patch-old 재현 확인 후 patch-r3) | 5 failed 남음 |
| 3 | `test_V08` versions '4', futuramaapi size ratio 1.334 | 기대값 갱신 필요 / base 축소로 비율 상승(추가분 동일, verified) | correction batch 2, D13 | pass |
| 4 | O11 8 subfailed | archive 재생성 필요 → 이후 comparator `_spread`가 구 R5 규칙(verified) | archive 재생성, batch 3에서 `_spread` R5 갱신 | pass |
| 5 | report_modal V04[connection] 1회 실패 | flaky(재실행 3/3 통과, base 통과) | 없음 | advisory |
| 6 | hand M8 survived 0 failed | probe가 예외 → ERROR로 집계 안 됨(verified) | 하네스가 ERROR를 inconclusive 처리, M8을 `continue` probe로 변경; M11 anchor 2회 → 고유 anchor | 11/11 killed |
| 7 | mutation tool 9 survived (30%) | triage: 8·25·10 declared gap, 3 undeclared, 22 equivalent, 11·19·26·29 V12 | spec v4 coverage item, batch 3 | 3·8·10·25 killed |
| 8 | mutant 3 batch 3 후에도 survived | 비 UTF-8 offset은 READS/WRITES 제외에만 쓰임(verified) | 비 UTF-8 테스트에 READS/WRITES 관찰 추가(한 줄 object는 기존 analyzer가 field 미수집) | killed |
| 9 | 컨테이너 재시작으로 Test command 중단 | 외부 | 재실행 | 3098 passed, diff coverage 97.9% |

# Version Log
## v1
- Initial draft from handoff dad85e4830f21190 3회차와 이번 세션 답변(F6 제거, F10 절대 가중치, Kotlin 멤버 제외).
## v2
- Contract-only: '미파싱 내부 모듈' 정의와 Kotlin wildcard import 아래 없는 이름 = 외부를 명시(test-implementer 지적 2건). 승인 항목 변경 없음.
## v3
- Contract-only: D13 추가(크기 비율 테스트를 이전 허용 증가량의 절대 예산으로 판정). base_manifest 재생성 결과 `tests/signal_defects_evidence/manifest-regeneration.md`. architecture_rules·delta·external_rules manifest는 `large_node_token_threshold` 키 없이 생성(기존 helper가 추가 키를 제거하고 비교).
## v4
- Contract-only: mutation tool 생존 mutant triage(8·25 → V6 dynamic 대조, 10 → V10 line boundary, 3 → V6 비 UTF-8 귀속)로 coverage item 추가. 22 equivalent(TS 심볼 id 형식 `ts:<file>#<qualname>`), 11·26·29·19는 기존 suite(V12)가 kill.
