---
version: 5
run_id: 2afad1e5c96b32ff
status: complete
base_commit: 9ea723bfce0b18890e16084f9d9edce27c5b0f77
max_verifier_invocations: 2
commit: 9ea723bfce0b18890e16084f9d9edce27c5b0f77
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자 | "AI agent를 사용함으로서 생기는 문제를 얼마나 잘 잡아내는 지를 기준으로 삼는 게 맞아. 그리고 그걸 목표로 개선해야해" — 결함 주입 eval은 주입 전 실행을 baseline으로 두고 주입 후 새로 생기거나 강해진 후보로 판정한다 | `--baseline` 비교 결과(`delta`)에 순환·규칙 위반 밖의 모든 후보 종류가 새로 생김 / 강해짐 / 사라짐(개수)으로 나온다 |
| I2 | 사용자 | "둘 다 권장으로" — policy를 `delta.v2`로 올리고 필드 추가, 기존 다섯 목록 유지 | 기존 `new_cycles`·`grown_cycles`·`new_violations`·`new_package_dependencies`·`instability_changes`와 기존 `resolved` 값은 그대로이고, 새 필드가 추가된다 |
| I3 | 사용자 | "2에 오탐이 있을 것이고 그걸 음성대조에서 보는 점은 확실히 적어놔" — 이름 변경은 추적하지 않는다 | 이름을 바꾼 파일의 후보는 baseline 쪽은 사라짐, 현재 쪽은 새로 생김으로 나온다. 이 오탐은 eval 음성 대조 NC1(이름 변경)에서 측정한다(A02) |

# Scope
In scope: `bottlenecks/delta.py`의 baseline 검증 확장(순환·규칙 위반 밖 후보의 target·metrics·evidence 형태), 일반 후보 비교(`new_candidates`, `strengthened_candidates`, `resolved.candidates`, `counts` 두 항목), `DELTA_POLICY = "delta.v2"`, CLI `[Δ]` 요약 줄 끝의 두 개수.
Out of scope: 파일 이름 변경 추적(git rename 감지 포함), HTML 보고서 delta 패널, `--fail-on-new` 조건 확장, symbol granularity delta, 새 후보 종류 추가, 후보 생성 로직·지표 변경, eval 주입 하네스와 판정 스크립트, `bottlenecks/handout.py`와 HTML의 "구조적 사실" 문구.

# Paths
Implementation: bottlenecks/delta.py, code_analyzer/cli.py
Tests: tests/test_delta_candidates.py, tests/delta_candidates_support.py, tests/delta_candidates_evidence/, 그리고 기존 tests/ file(조정 허용 범위: `"delta.v1"` 기대값을 `"delta.v2"`로, delta key 집합에 `new_candidates`·`strengthened_candidates` 추가, `counts` key 집합에 같은 두 이름 추가, `resolved` key 집합에 `candidates` 추가, `[Δ]` 요약 줄 기대 문자열 끝에 `, new candidates N, strengthened candidates M` 추가, 기존 delta 기준 구현(`tests/delta_support.py` `ref_delta`)이 새 필드를 같은 규칙으로 계산하도록 확장, 합성 baseline 후보 중 `target`·`metrics`가 없는 비순환·비위반 후보에 `target`(문자열)과 `metrics: {}` 추가, delta 전체를 hash로 고정한 characterization(예: `tests/test_reach_candidates.py`)은 hash 전에 `policy`를 `"delta.v1"`로 되돌리고 새 key(`new_candidates`, `strengthened_candidates`, `counts`의 두 key, `resolved.candidates`)를 제거한 뒤 비교하고 새 필드는 같은 test에서 별도로 기대값을 단언. 다른 assertion 약화 금지. 모든 변경은 `tests/delta_candidates_evidence/existing-tests.diff`에 기록)
Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','fastapi-official-template','android-nowinandroid','typescript-nestjs-realworld')]" && uv run -q --with-requirements requirements-dev.txt --with pytest-cov python -m pytest -q -p no:cacheprovider --cov=bottlenecks.delta --cov-branch --cov-report=term-missing --cov-fail-under=90 --deselect 'tests/test_analysis_coverage_reporting.py::test_V05_characterization_and_V04_cli_stages' --deselect 'tests/test_doc_references.py::test_V8_base_choice_cli_output_equals_base_after_removing_new_keys' --deselect 'tests/test_file_analysis_cli.py::test_V01_direct_builder_defaults_characterization' --deselect 'tests/test_nestjs_quality.py::TestRegression::test_O11_characterization_existing_standalone_outputs_are_byte_identical' --deselect 'tests/test_signal_defects_round4.py::test_V4_B_data_object' --deselect 'tests/test_report_modal.py::test_V04_graph_tab_active_modal_selects_and_centres_node' --deselect 'tests/test_report_size_format.py::test_V01_fixture_details_equal_base_details'
Review evidence: none — CLI 동작은 V05 integration test가 subprocess로 관찰한다.
Fuzzing: main이 scratchpad에 작성한 stdlib harness, seed 20261110. (a) `load_baseline`: fastapi-realworld 실제 file granularity bottleneck JSON의 비순환·비위반 후보를 무작위 변형(target·metrics·evidence 삭제·타입 교체, 강도 지표에 문자열·null·bool, evidence 원소 타입 교체)한 baseline 파일, oracle crash — `BaselineError` 외 예외 0, 10,000 입력. (b) `compute_delta`: 합성 payload 쌍(종류 8개 + 미지 종류 1개, 무작위 target·지표·evidence), oracle property — P1 `compute_delta(x, x)`의 `new_candidates`·`strengthened_candidates`가 비고 `resolved.candidates == 0`; P2 `counts.new_candidates(a, b) == resolved.candidates(b, a)`; P3 `strengthened_candidates`의 모든 `increased` 항목은 current > baseline; P4 입력 후보 순서를 섞어도 결과 동일, 20,000 입력.
Mutation tool: none — mutmut·cosmic-ray 미설치; hand mutation으로 대신한다.

# Signatures
`bottlenecks.delta.DELTA_POLICY = "delta.v2"`
`bottlenecks.delta.load_baseline(path: str | os.PathLike) -> dict` — 기존 검사 + F11.
`bottlenecks.delta.compute_delta(current: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict` — 기존 출력 + F04–F10.
`bottlenecks.delta.regressions(delta, fail_on) -> list[str]` — 변경 없음(F13).

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F01 | `delta["policy"] == "delta.v2"`. 기존 key `baseline`, `rules_changed`, 다섯 목록, `resolved.cycles`·`resolved.violations`·`resolved.package_dependencies`의 값은 base_commit 구현과 같다 | must | I2 |
| F02 | 일반 비교 대상은 `kind`가 `dependency_cycle`, `package_cycle`, `rule_violation`이 아닌 모든 후보다. 이 버전이 모르는 `kind`도 포함한다 | must | I1 |
| F03 | 짝 맞춤 key = (`kind`, `target`, `structure`에서 `tier`를 뺀 나머지를 key 정렬한 JSON 문자열; `structure`가 없으면 빈 문자열). 한 보고서 안에서 같은 key가 두 번 이상 나오면 그 key의 후보들은 key 끝에 후보 `id`를 덧붙여 구분한다(그 보고서 안에서만 적용; 다른 쪽에서 한 번만 나오면 짝이 맞지 않아 새로 생김 + 사라짐이 된다) | must | I1 |
| F04 | `new_candidates`: 현재 보고서에만 있는 key의 후보. 원소 `{candidate_id, kind, target, metrics}`(`metrics`는 현재 후보의 것 그대로) | must | I1 |
| F05 | `strengthened_candidates`: 양쪽에 있는 key 중 (a) F06 강도 지표가 양쪽 모두 number이고 현재 > baseline인 지표가 하나 이상이거나 (b) F06 근거 서명 중 현재에만 있는 것이 하나 이상인 후보. 원소 `{candidate_id, baseline_candidate_id, kind, target, increased, added_evidence}`; `increased` = 커진 지표만 `{지표: {"baseline": x, "current": y}}`, `added_evidence` = 현재에만 있는 서명(각 서명은 문자열 list) 정렬 목록, 없으면 `[]` | must | I1 |
| F06 | 강도 지표와 근거 서명. `large_node`: `line_count`, `token_count`. `unresolved_boundary`: `unresolved_count`; 서명 — evidence 원소에 `unresolved_references` list가 있으면 그 안의 문자열 `name`마다 `["reference", node_id, name]`, `flags` list의 문자열마다 `["flag", node_id, flag]`, 원소에 문자열 `from_id`·`to_id`가 있으면 `["edge", from_id, to_id, relation 또는 ""]`(node_id는 원소의 `node_id`, 없으면 후보 `target`). `evidence_spread`: `file_count`, `directory_count`. `dangling_doc_reference`: `dangling_count`; 서명 — evidence 원소마다 `["doc", notation, text]`(둘 다 문자열일 때). `unstable_dependency`: `file_pair_count`. 그 밖의 종류(`untested_hub`, `isolated_node`, 미지 종류)는 강도 지표·서명이 없다 | must | I1 |
| F07 | F06에 없는 지표(`line_span`, `*_threshold`, `pagerank`, `pagerank_rank`, instability 값 등)와 서명에 없는 evidence 필드(줄 번호, path, `detail_edge_index`)는 강해짐 판정에 쓰지 않는다 | must | I1 (포맷팅만 바뀌어도 줄 범위가 변함) |
| F08 | `resolved.candidates` = baseline에만 있는 key의 수(F02 대상만) | must | I1 |
| F09 | `counts`에 `new_candidates`, `strengthened_candidates` 원소 수가 추가된다 | must | I1 |
| F10 | `new_candidates`·`strengthened_candidates`는 (`kind`, `target`, `candidate_id`) 오름차순, `added_evidence`는 서명 list의 사전순 | must | 결정성 |
| F11 | `load_baseline`은 F02 대상 baseline 후보마다 `target`이 문자열, `metrics`가 object, F06 강도 지표가 있으면 number(bool 제외)임을 검사하고, `unresolved_boundary`·`dangling_doc_reference`는 `evidence`가 list이고 각 원소가 object임을 검사한다. 위반은 `BaselineError("baseline <path>: <위치> must be <expected>")`이고 위치는 `$.candidates[<i>].target`, `$.candidates[<i>].metrics`, `$.candidates[<i>].metrics.<지표>`, `$.candidates[<i>].evidence`, `$.candidates[<i>].evidence[<j>]`. `target`·`metrics` 검사는 미지 종류에도 적용하고, 강도 지표·evidence 검사는 F06에 있는 종류에만 적용한다. 순환·`rule_violation` 후보의 `target`·`metrics`는 검사하지 않는다 | must | Errors |
| F12 | CLI `[Δ]` 요약 줄은 기존 문구 끝에 `, new candidates {counts.new_candidates}, strengthened candidates {counts.strengthened_candidates}`를 붙인 한 줄이다 | must | I2 |
| F13 | `regressions`와 `--fail-on-new`의 판정·exit code는 바뀌지 않는다 | must | Scope |
| F14 | `bottlenecks.v8` baseline도 F02–F11을 같은 방식으로 적용한다 | must | 호환 |

# Errors
baseline 후보의 target·metrics·강도 지표·evidence 형태 위반(F11) — `BaselineError`, 메시지에 baseline 경로와 JSON 위치; CLI는 기존 baseline 오류 경로대로 exit 1, 출력 file을 쓰지 않는다.
현재 보고서 쪽 강도 지표가 number가 아님 — 예외 없음, 그 지표는 비교하지 않는다(현재 보고서는 분석기가 만든 값).

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C01 | normal | `large_node` 같은 target, `line_count` 2100 → 2300, `token_count` 같음 | strengthened 1, `increased == {"line_count": {"baseline": 2100, "current": 2300}}`, `added_evidence == []` |
| C02 | normal | 현재에만 `isolated_node` 1개 | `new_candidates` 1, `metrics` 그대로 |
| C03 | boundary | 강도 지표 같음 / +1 | 같음은 목록에 없음, +1은 strengthened |
| C04 | boundary | 강도 지표 감소 | strengthened·new·resolved 모두 아님 |
| C05 | edge | 같은 후보가 target만 다름(파일 이름 변경) | baseline 쪽 `resolved.candidates` +1, 현재 쪽 `new_candidates` +1 (알려진 오탐, A02) |
| C06 | edge | 미지 종류 `duplicate_code`: 현재에만 있음 / 양쪽에 있고 지표 증가 | 앞은 new, 뒤는 목록에 없음 |
| C07 | edge | `unstable_dependency` 같은 package 쌍, `structure.tier`만 변경 | new·strengthened·resolved 아님 |
| C08 | edge | `evidence_spread` `line_span`만 증가 | 목록에 없음 |
| C09 | normal | `unresolved_boundary` `unresolved_count` 같고 reference name 하나가 다른 이름으로 바뀜 | strengthened, `added_evidence == [["reference", node, 새 이름]]`, `increased == {}` |
| C10 | normal | `dangling_doc_reference` 새 text 1개 추가, count +1 | strengthened, `increased`에 `dangling_count`, `added_evidence`에 `["doc", notation, text]` |
| C11 | edge | 순환·`rule_violation` 후보만 바뀜 | 일반 목록 비어 있고 기존 목록은 base 동작대로 |
| C12 | error | baseline 일반 후보 `target`이 number | `BaselineError`, 메시지에 `$.candidates[i].target` |
| C13 | error | baseline `large_node.metrics.line_count`가 `"2100"` / `true` / `null` | 각각 `BaselineError` |
| C14 | error | baseline `unresolved_boundary.evidence`가 object / 원소가 문자열 | 각각 `BaselineError` |
| C15 | normal | fixture 사본: baseline 실행 후 production 파일 하나에 프로젝트 module을 겨냥한 존재하지 않는 이름 호출(프로젝트 module을 import한 뒤 그 module에 없는 attribute 호출; bare 미정의 이름은 Python 분석기가 외부 호출로 분류하므로 쓰지 않는다)을 추가하고 아무도 import하지 않는 새 module 추가, `--baseline`으로 재실행 | JSON `delta.new_candidates` 또는 `strengthened_candidates`에 해당 `unresolved_boundary`, `new_candidates`에 새 module의 `isolated_node`; stdout 요약 줄이 F12 형식 |
| C16 | edge | `compute_delta(x, x)` | 일반 목록 비고 `resolved.candidates == 0` |
| C17 | edge | 한 보고서 안 같은 key 두 후보(미지 종류) | id로 구분해 짝 맞춤 |
| C18 | edge | `bottlenecks.v8` baseline | F02–F11 적용 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | eval 판정의 근거가 되는 비교 결과 |
| Performance efficiency | yes | 큰 저장소 보고서(후보 수만 개)에서도 비교가 분석 시간에 비해 무시할 수준이어야 한다 |
| Compatibility | yes | 기존 delta 목록·CLI 출력 소비자(HTML, 기존 테스트) 유지 |
| Interaction capability | no | 사람이 읽는 출력은 요약 줄 한 줄 확장(F12)뿐이고 기능 요구로 다룬다 |
| Reliability | yes | 깨진 baseline에 대해 `BaselineError` 외 예외 없이 실패해야 한다 |
| Security | no | 로컬 JSON 파일 비교, 신뢰 경계 변화 없음 |
| Maintainability | yes | 분기 coverage |
| Flexibility | yes | 앞으로 추가될 후보 종류가 코드 변경 없이 new로 나와야 한다(F02, C06) |
| Safety | no | 정적 비교, 안전 관련 동작 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | Performance efficiency / time behaviour | `compute_delta`, 양쪽 각 50,000개 일반 후보(종류 6개, 절반 공통 key) + 기존 fixture 수준 순환 | 개발 기기 단일 프로세스 `time.perf_counter` 3회 중 최솟값, 초 | ≤ 3.0 s | automated(Test command) | 기본값 |
| Q02 | Compatibility / co-existence | 기존 delta 테스트(test_delta·test_delta_cli·test_delta_integration·test_structure_panel_browser) | 허용 범위 조정 후 통과 여부 | 전부 통과 | automated(Test command), existing-tests.diff | I2 |
| Q03 | Reliability / fault tolerance | `load_baseline` 변형 입력 | fuzz (a) 비-`BaselineError` 예외 수 | 0 | fuzz | Errors |
| Q04 | Maintainability / testability | `bottlenecks/delta.py` | coverage.py branch | ≥ 90% | automated(Test command) | 기본값 |
| Q05 | Flexibility / adaptability | 미지 종류 후보 | C06·C17 관찰 | 통과 | automated | F02 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V01 | F02–F07, C01, C02, C04, C06–C10, C17 | `compute_delta` 합성 payload | unit; 전부 | decision table | 규칙: R1 key 현재에만, R2 baseline에만, R3 양쪽·지표 증가, R4 양쪽·지표 같음, R5 양쪽·지표 감소, R6 양쪽·서명 추가만, R7 양쪽·서명 제거만, R8 양쪽·F07 지표만 변경, R9 양쪽·tier만 변경, R10 미지 종류 양쪽·지표 증가, R11 같은 key 중복 — 종류별 적용: 강도 지표 있는 5종 × R1–R5, R8; 서명 있는 2종 × R6, R7; `untested_hub`·`isolated_node` × R1–R3; `unstable_dependency` × R9; 미지 종류 × R1, R10, R11 | 100% | 목록 분류·`increased`·`added_evidence`·`resolved.candidates`가 독립 계산 기대값과 일치 | Test command |
| V02 | F05, F06, C03 | 강도 지표 경계 | unit; 강도 지표 7개(종류·지표 쌍) 각각 | boundary value analysis (2-value) | 지표마다 {같음, +1} = 14 | 100% | 같음은 미보고, +1은 해당 지표만 `increased`에 | Test command |
| V03 | F11, C12–C14, Errors | `load_baseline` | unit; F11 검사 조건 하나씩 위반 | syntax testing | target 비문자열, metrics 비object, 강도 지표 문자열·bool·null(지표 7개 중 `line_count`·`unresolved_count`·`file_pair_count` 대표 3개 × 3값), evidence 비list(2종), evidence 원소 비object(2종), 미지 종류의 target 비문자열·metrics 비object(2), 순환·위반 후보의 비문자열 target·비object metrics가 그대로 load됨(2), 미지 종류에 강도 지표·evidence 검사 미적용(1) — 20 | 100% | `BaselineError`, 메시지에 baseline 경로와 F11 위치 문자열; 미적용 대상은 정상 | Test command |
| V04 | F01, F09, F13, F14, C11, C18 | 기존 출력과 형식 | unit; 전부 | equivalence partitioning | policy 값, 기존 다섯 목록·resolved 세 값 불변(기존 delta 테스트가 고정한 기대값을 허용 범위 밖 수정 없이 통과, Q02), counts 두 key, regressions 불변(일반 목록만 있는 delta에서 빈 결과), v8 baseline — 5 | 100% | 값 일치 | Test command |
| V05 | F12, C15 | CLI | integration; fixture 사본 subprocess(Python fixture 1개) | scenario testing | C15 단계: baseline 생성, 결함 추가, 재실행, JSON 확인, 요약 줄 확인 — 1 시나리오 | 100% | exit 0, JSON 목록에 기대 후보, stdout 요약 줄 F12 형식 | Test command |
| V06 | F08, C05, C16 | 사라짐·이름 변경·항등 | unit | metamorphic testing | M1 항등(C16), M2 swap(new(a,b) == resolved(b,a)), M3 후보 순서 섞기 불변, M4 target 이름 변경 → resolved +1·new +1(C05) — 4 | 100% | 관계 성립 | Test command, fuzz (b) |
| V07 | Q01 | 성능 | integration | boundary value analysis (2-value) | Q01 임계 — 1 | 100% | 시간 ≤ 3.0 s | Test command |
| V08 | F03–F07 | 오류 추측 | unit | error guessing | 짝 맞춤에 id 사용(이름 변경 없는 경우에도 hash 의존), key에 tier 포함, 감소를 강해짐으로 보고, `increased`에 안 커진 지표 포함, 서명에 줄 번호 포함, 순환·위반을 일반 목록에 포함, 미지 종류 누락 | none — experience-based | 각 결함이 테스트 실패로 드러남 | Test command, hand mutation |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v1 — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| A01 | policy `delta.v2`로 올리고 필드만 추가, 기존 다섯 목록 유지 | 소비자는 이 저장소의 CLI·HTML·테스트와 eval 스크립트뿐 | user answer |
| A02 | 파일 이름 변경은 추적하지 않는다. 이름을 바꾼 파일의 후보는 baseline 쪽 사라짐 + 현재 쪽 새로 생김으로 나오는 **알려진 오탐**이며, eval 음성 대조 NC1(이름 변경)에서 이 오탐률을 측정·보고한다 | file 후보 id·target이 경로 기반(`bottlenecks/core.py` `_candidate`, node id `file:<path>`) | user answer |
| A03 | F06 강도 지표·서명 표(참조 분산의 단일 파일 줄 범위 제외, 테스트 없는 hub·고립 노드는 새로 생김만) | 줄 범위는 포맷팅만으로 변함; 상수 표라 나중에 바꾸기 쉬움 | brief v1 — approved |
| A04 | `unresolved_references`는 node당 20개로 잘리므로 21번째 이후 새 이름은 서명으로 안 잡히고 `unresolved_count` 증가로만 잡힌다 | `language_analyzers/python/graph.py:580`, typescript·kotlin 동일 | brief v1 — approved |
| A05 | HTML delta 패널·`--fail-on-new`는 바꾸지 않는다 | HTML `deltaGroups`가 명시 목록이라 새 key를 무시함(`renderers/html/static/app.js:743`) | brief v1 — approved |
| A06 | Mutation tool none, hand mutation 8–10개 | 설치된 mutation 도구 없음 | brief v1 — approved |
| A07 | implementer·test-implementer·test-verifier 모델은 저장소 기본값 | 단일 module 변경 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F01, F09, F13, F14 | C11, C18 | V04 | Test command |
| F02–F07 | C01–C04, C06–C10, C17 | V01, V02, V08 | Test command, fuzz (b), hand mutation |
| F08 | C05, C16 | V06 | Test command, fuzz (b) |
| F10 | C01, C09, C10 | V01 | Test command |
| F11 | C12–C14 | V03 | Test command, fuzz (a) |
| F12 | C15 | V05 | Test command |
| Q01 | — | V07 | Test command |
| Q02 | C11 | V04 | Test command |
| Q03 | C12–C14 | V03 | fuzz (a) |
| Q04 | — | — | Test command coverage gate |
| Q05 | C06, C17 | V01 | Test command |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 3 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V01 | 5 | tests/test_delta_candidates.py test_V01_* incl. batch-3 tests | accepted (verifier 2) | B-01, B-02 closed; M11–M13 detected | F03, F06 |
| V02 | 5 | test_V02_strength_metric_boundary | accepted (verifier 1) | literal expectations | none |
| V03 | 5 | test_V03_* | accepted (verifier 1) | exact F11 locations; M8 detected | none |
| V04 | 5 | test_V04_* + adjusted existing tests (existing-tests.diff) | accepted (verifier 1) | M6 detected | existing-tests.diff unchanged in batch 3 |
| V05 | 5 | test_V05_cli_baseline_rerun_reports_new_unresolved_boundary_and_isolated_node | accepted (verifier 1) | — | none |
| V06 | 5 | test_V06_M1..M4 (+ M5 added in batch 3) | accepted (verifier 1 M1–M4, verifier 2 M5) | M13 detected by M5 | none |
| V07 | 5 | test_V07_fifty_thousand_candidates_per_side_in_three_seconds | accepted (verifier 1) | — | none |
| V08 | 5 | test_V08_* | accepted (verifier 1) | M1–M5, M7, M9, M10 detected | none |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 0 | reconcile: test-implementer challenges (V03 count 18≠17, unknown-kind F11 applicability, F11 location, F03 one-sided duplicate, `good()` baseline lacks target/metrics, whole-delta hash pins in tests/test_reach_candidates.py); implementer challenges (F03 asymmetry, relation default, non-object reference entries) | spec gaps in v1 | spec v2 (contract-only); implementer code already matched v2 locations; tests correction batch 1 | resolved; implementer reading of relation default (missing/non-string → "") and skipping non-object current-side reference entries accepted as consistent with F06 |
| 1 | fuzz (a) seed 20261110: 10,000 inputs, 5,041 BaselineError, 4,959 accepted, 0 other exceptions; fuzz (b) 20,000 inputs, P1–P4 violations 0, exceptions 0 | — | harness `scratchpad/fuzz/fuzz_delta_v2.py` on fastapi-realworld file bottleneck JSON (55 general candidates) | pass |
| 2 | Test command run 1: 21 failed / 3807 passed; coverage "No data was collected" | coverage run cannot see xdist workers (pytest.ini `-n auto`); 17 failures pre-existing at base_commit; V05 and test_reach V7_Q3 test defects | spec v3 (C15), v4 (pytest-cov, deselect pre-existing); test correction batch 2 | — |
| 3 | Test command run 2: 2 failed (test_report_size_format V01, test_report_modal V04[connection]) / 3808 passed; delta.py branch 99% | pre-existing flakes (verified at base_commit: modal fails in 2/2 base full runs; size-format fails at base when doc/handout tests run first in-process) | spec v5 deselect | — |
| 4 | Test command run 4: rc 0, 3806 passed; delta.py branch 99% (missing: 93->exit no `coverage` key, 183 RecursionError guard — both pre-existing; 250->249 non-object current evidence record, 289->293 non-object current metrics — current-side defensive skips) | — | advisory A-01 (current-side defensive branches untested) | pass |
| 5 | hand mutations M1–M10 (key keeps tier, match by id, decrease reported, increased lists every metric, signature keeps line, violations enter general, unknown kinds dropped, baseline accepts bool, no duplicate id suffix, edge signature drops relation) | strongest defect classes: each breaks one F03–F07/F11 rule the eval relies on | `scratchpad/mutations.jsonl`; seed.py backup/restore, restore verified by diff stat | 10/10 detected by the intended V01/V03/V08/existing-delta test |
| 6 | verifier 1: retry; B-01 (edge relation default and element node_id in flag/reference signatures unobserved), B-02 (sorted structure keys in pairing key unobserved); V02–V08 accepted; advisories A-01..A-05 | test evidence gaps | test correction batch 3: 5 tests (edge relation default, node_id signatures ×2, structure key order pairing, V06 M5) | — |
| 7 | Test command run 5: rc 0, 3811 passed; delta.py branch 99% (same uncovered lines as run 4) | — | confirming mutations M11 relation default None, M12 flag signature ignores node_id, M13 unsorted structure keys (`scratchpad/mutations2.jsonl`) | 3/3 detected by the new B-01/B-02 tests; restore verified |
| 8 | verifier 2: pass; V01 and V06 M5 accepted, prior acceptances retained; advisories: M5 relation compares run with run (anchored by V01 literals); non-string element node_id unspecified in F06 | — | — | complete |

# Version Log
## v1
- Initial draft.

## v2
- Contract-only: F03 duplicate-key rule clarified as per-report (literal v1 reading confirmed); F11 error locations and kind applicability made explicit; V03 items recounted (v1 listed 18 items as 17) and unknown-kind target/metrics checks added (20); Tests adjustment range extended to `ref_delta`, synthetic baselines missing `target`/`metrics`, and hash-pinned whole-delta characterizations — challenges raised by test-implementer and implementer after dispatch.
## v3
- Contract-only: C15 injection clarified to a call aimed at project code; evidence: on fastapi-realworld, 25 bare undefined calls appended to app/services/security.py produced no unresolved_references (`language_analyzers/python/graph.py` `_is_boundary_call` returns False for unbound bare names, so they count as external).
## v4
- Contract-only (evidence defect): Test command used `coverage run` around pytest, but `pytest.ini` addopts `-n auto` (xdist, added a0987d9 after the earlier delta spec) runs tests in workers, so coverage collected no data; switched to pytest-cov. Deselected the 5 test functions (12 node ids) that already fail at base_commit 9ea723b with the full suite and fixtures present (17 failed / 3703 passed at base; all are characterization hashes of analyzer output unrelated to delta; log `scratchpad/base-suite.log`).
## v5
- Contract-only (evidence defect): two more pre-existing failures deselected. `test_report_modal.py::test_V04_graph_tab_active_modal_selects_and_centres_node[card|connection]` fails in both base_commit full-suite runs (graph view centring off by ~38 px under parallel load) and passes alone; `test_report_size_format.py::test_V01_fixture_details_equal_base_details` fails at base_commit when tests/test_doc_references.py or tests/test_report_size_handout.py runs first in the same process (lru_cached architecture gains `doc_references`), so it depends on xdist file placement.

# Retrospective
## 2026-11-10
| observation | evidence | how to re-check |
| --- | --- | --- |
| `coverage run -m pytest` collects no data in this repo | `pytest.ini` addopts contains `-n auto`; run 1 printed "No data was collected" with 3807 tests run | `grep addopts pytest.ini` |
| At base 9ea723b the full suite already fails 5 characterization test functions (12 node ids) and 2 flaky tests | three full-suite runs in a base worktree at 9ea723b | run `pytest -q` in a worktree at 9ea723b with fixtures acquired |
| The Python analyzer classifies a call to an unbound bare name as external; no `unresolved_references` entry is produced | 25 such calls appended to fastapi-realworld produced no unresolved_boundary | `language_analyzers/python/graph.py` `_is_boundary_call`, or repeat the injection and inspect details |
| In a fresh worktree `.fixtures` must be acquired with `fixtures.registry.fixture_root`; with partial fixtures the doc-reference tests skip with "fixture not acquired" and the run looks green | first base-worktree run skipped K1, K4, K5 | `pytest tests/test_doc_references.py -rs` in a fresh worktree |
