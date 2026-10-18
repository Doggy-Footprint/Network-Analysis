---
version: 4
run_id: f0ef5182f4d4207c
status: complete
base_commit: f5ab529bd2cdd8a084d66e2759d172fc3579cfd5
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자 | "Architecture 분석 기능을 추가하고 싶어. goal: keep AI written codes maintanable" | AI 변경 직후 이전 bottleneck JSON 대비 구조 악화(새·커진 순환, 새 경계 위반, 새 package 의존, instability 큰 변화)가 bottleneck JSON `delta`와 HTML에 나온다 |
| I2 | 사용자 | Phase 3 계획: `--baseline`, `--fail-on-new`, Structure 패널 | `--fail-on-new` 조건이 걸리면 CLI가 exit 3으로 끝나 CI·hook이 사용할 수 있다 |
| I3 | 사용자 | 새 package 의존을 delta에 포함하기 위해 package 의존 쌍을 항상 출력 | file granularity bottleneck JSON의 `dependency_network.package_dependencies`에 scheme별 package 의존 쌍이 있다 |
| I4 | 사용자 | 새 cycle 판정은 모든 tier | certain·resolved·all tier 모두에서 새·커진 순환이 delta와 실패 조건에 들어간다 |
| I5 | 사용자 | HTML에서 순환·위반·delta를 보고 그래프에서 확인 | HTML "구조" 섹션 항목을 누르면 그래프에서 관련 file이 선택·강조된다 |

# Scope
In scope: `bottlenecks/delta.py`(baseline 읽기·검증, delta 계산, 실패 판정), `BottleneckReport.delta`, `network.package_dependencies`, 규칙 coverage `rules_sha256`, CLI `--baseline`·`--fail-on-new`와 exit 3, report validator의 `delta` 허용, HTML "구조" 섹션(순환·경계 위반·delta 목록과 그래프 강조).
Out of scope: git ref checkout·재분석, 별도 baseline 저장 형식, README·예제 hook, symbol granularity delta, delta에서의 tier 변화·edge 수 변화·relation 변화 추적, 같은 SCC 안 내부 edge만 늘어난 경우의 보고, package 의존 delta의 file 근거, 기존 candidate·지표·architecture JSON의 변경, 모달 이웃 순위(E07 handoff 영역), Gradle module 체계.

# Paths
Implementation: bottlenecks/delta.py, bottlenecks/core.py, bottlenecks/__init__.py, analysis/structure.py, analysis/architecture_rules.py, code_analyzer/cli.py, report/bottlenecks/generate.py, report/unified.py, renderers/html/static/app.js, renderers/html/static/styles.css, renderers/html/templates/dashboard.html
Tests: tests/test_delta.py, tests/test_delta_cli.py, tests/test_delta_integration.py, tests/test_structure_panel_browser.py, tests/delta_support.py, tests/delta_evidence/, 그리고 기존 tests/ file(조정 허용 범위: golden·hash·characterization 비교 전에 `dependency_network.package_dependencies`와 `coverage.architecture_rules.rules_sha256`만 제거, coverage·network key 집합 assertion에 이 두 key 추가, HTML section 목록 assertion에 새 섹션 추가, `StructureResult` field 목록 assertion에 `package_dependencies`를 마지막 field로 추가(약화 금지), 크기 비율 assertion은 `package_dependencies`를 제거한 정규 직렬화 크기로 계산. 모든 변경은 `tests/delta_evidence/existing-tests.diff`에 기록)
Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','fastapi-official-template','android-nowinandroid','typescript-nestjs-realworld')]" && uv run -q --with-requirements requirements-dev.txt --with coverage python -m coverage run --branch --include=bottlenecks/delta.py -m pytest -q -p no:cacheprovider && uv run -q --with coverage python -m coverage report --fail-under=90
Review evidence: R1 — main이 5개 fixture를 base_commit과 현재 구현으로 `--granularity file --bottlenecks`로 실행해 `tests/delta_evidence/size.json`(fixture별 `{base_bytes, bytes, ratio, package_dependency_count}`)을 기록하고, 현재 출력에서 `package_dependencies`를 지우면 base 출력과 byte가 같음을 함께 기록한다. R2 — main이 fastapi-realworld 사본에 역방향 import를 넣고 예제 규칙과 baseline으로 만든 HTML을 브라우저로 열어 구조 섹션의 delta 목록과 그래프 강조를 스크린샷으로 `tests/delta_evidence/`에 남긴다.
Fuzzing: main이 scratchpad에 작성한 stdlib 기반 harness, seed 20261018. (a) `load_baseline`·`compute_delta`: fastapi-realworld 실제 bottleneck JSON을 무작위로 변형(필드 삭제, 타입 교체, 값 교체, 목록 원소 복제·삭제, 깊은 중첩, 잘린 JSON byte)한 baseline. oracle crash — `BaselineError` 외 예외 0, 20,000 입력. (b) `compute_delta`: 합성 bottleneck payload 쌍(무작위 file 집합, 무작위 cycle 분할, 무작위 위반 id, 무작위 package 쌍·instability). oracle property — `compute_delta(x, x)`의 모든 목록이 비고 `rules_changed`가 false; `compute_delta(a, b).counts.new_violations == compute_delta(b, a).resolved.violations`; `new_package_dependencies` 수와 반대 방향 `resolved.package_dependencies` 수가 같다, 20,000 입력.
Mutation tool: main이 scratchpad에 작성한 AST mutation 스크립트(2b와 같은 연산자). base_commit 이후 변경된 Implementation Python 줄만 대상. 최대 30개 표본, seed 20261018. 실행 명령 `uv run -q --with-requirements requirements-dev.txt python -m pytest -q -p no:cacheprovider -x tests/test_delta.py tests/test_delta_cli.py tests/test_delta_integration.py`. 생존율 임계 40%.

# Signatures
`bottlenecks.delta.DELTA_POLICY = "delta.v1"`
`bottlenecks.delta.BaselineError(ValueError)` — 메시지는 `baseline <path>: ` 또는 `baseline: `로 시작한다.
`bottlenecks.delta.load_baseline(path: str | os.PathLike) -> dict` — F05.
`bottlenecks.delta.compute_delta(current: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict` — F06–F12. `current`와 `baseline`은 bottleneck JSON을 `json.loads`한 dict.
`bottlenecks.delta.regressions(delta: Mapping[str, Any], fail_on: Iterable[str]) -> list[str]` — F14. 결과는 `"cycle"`, `"violation"` 중 걸린 것, 이 순서.
`bottlenecks.core.BottleneckReport`에 `delta: Optional[Mapping[str, Any]] = None` 필드 추가.
`analysis.architecture_rules.rules_digest(rules: ArchitectureRules) -> str` — F03.
`analysis.structure.StructureResult`에 마지막 field `package_dependencies: Mapping[str, list]` 추가(F01 값).
CLI: `--baseline PATH`, `--fail-on-new {cycle,violation,any}`(반복 가능).

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F01 | file granularity bottleneck JSON의 `dependency_network.package_dependencies`는 `package_metrics`와 같은 scheme key를 가진 mapping이다. 값은 그 scheme의 `all` tier package 쌍(Phase 1의 package 쌍: 서로 다른 package, TESTS 제외) 목록 `{"from_id", "to_id", "tier"}`이고 (from_id, to_id) 오름차순이다. `tier`는 쌍을 이루는 file 의존 중 가장 강한 tier다. 쌍이 없는 scheme은 `[]`. symbol granularity 출력은 바뀌지 않는다. | required | I3 |
| F02 | `--baseline`을 쓰지 않은 출력은 base_commit 출력에서 F01의 `package_dependencies`와 F03의 `rules_sha256`만 추가된 것이다. architecture JSON은 바뀌지 않는다. | required | 호환성 |
| F03 | 규칙을 쓴 실행의 `coverage.architecture_rules.rules_sha256`은 `rules_digest(rules)`다. `rules_digest`는 `{"version", "layers": {이름: {"paths", "packages"}}, "allow", "forbid", "external", "forbid_external", "allow_external"}`(값은 `ArchitectureRules`에 저장된 tuple을 list로. 단 `layers`의 `paths`·`packages`는 저장 순서와 중복이 입력 그대로이므로 정렬·중복 제거한 list로)을 `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`한 UTF-8 byte의 sha256 hex다. 따라서 YAML key 순서·주석·목록 중복·같은 from의 forbid 분할만 다른 규칙 file은 같은 digest를, 규칙 의미가 다르면 다른 digest를 낸다. | required | F10 |
| F04 | delta는 `--baseline`을 준 실행의 bottleneck JSON 최상위 `delta` key에만 있고, 없을 때는 key 자체가 없다. HTML에 넣는 bottleneck 데이터도 같은 `delta`를 가진다. | required | I1 |
| F05 | `load_baseline`은 file을 읽어 UTF-8 JSON으로 파싱하고 다음을 검사한다. 위반은 `BaselineError`(위반한 JSON 경로와 기대값을 메시지에 포함). 루트 object; `schema == "bottlenecks.v8"`; `granularity == "file"`; `snapshot.file_count` 정수; `dependency_network.structure_policy` 문자열; `dependency_network.package_dependencies`가 scheme → 목록이고 원소가 문자열 `from_id`, `to_id`, `tier`(TIERS 중 하나)를 가진 object; `dependency_network.package_metrics`가 scheme → package → object이고 `instability`가 number 또는 null; `candidates` 목록이고 원소가 문자열 `id`·`kind`를 가진 object; `dependency_cycle`·`package_cycle` 원소는 `structure.scheme` 문자열, `structure.tier`(TIERS 중 하나), `structure.members` 문자열 목록, `evidence` 목록이고 각 원소가 문자열 `from_id`·`to_id`를 가진 object; `rule_violation` 원소는 문자열 `structure.rule_type`·`structure.from_layer`와 문자열 `structure.to_layer` 또는 `structure.to_external` 중 하나; `coverage.architecture_rules`가 있으면 object이고 `rules_sha256`은 있으면 문자열. 그 밖의 필드는 읽지 않으며 baseline의 `delta`는 무시한다. 읽기 실패(OSError), UTF-8 오류, JSON 오류, 중첩 깊이 초과(RecursionError)도 `BaselineError`다. | required | 신뢰성 |
| F06 | `compute_delta`는 호환성을 검사한다: baseline과 current의 `structure_policy`가 다르면, 또는 `coverage.architecture_rules`가 한쪽에만 있으면 `BaselineError`. 둘 다 있고 `rules_sha256`이 다르면(한쪽이라도 없으면, 양쪽 모두 없는 경우 포함, 다름으로 본다) `rules_changed: true`, 아니면 false. 비교는 계속한다. | required | 기본값 D1 |
| F07 | 순환 대응: key (kind, scheme, tier)별로 current의 각 `dependency_cycle`·`package_cycle` C에 대해 같은 key의 baseline 순환 중 member가 C와 하나 이상 겹치는 것들을 O라 한다. O가 비면 C는 새 순환이다. O가 있고 C의 member 중 O 합집합에 없는 것이 있거나 \|O\| ≥ 2이면 C는 커진 순환이다. 그 밖(O가 하나이고 C ⊆ 그 member)은 보고하지 않는다. 같은 SCC에서 내부 edge만 늘어난 경우는 보고하지 않는다. | required | I1, I4 |
| F08 | 순환 delta 항목은 `{"candidate_id", "kind", "scheme", "tier", "members", "baseline_candidate_ids", "added_members", "new_internal_pairs"}`다. `members`는 C의 member, `baseline_candidate_ids`는 O의 id 정렬 목록(새 순환은 `[]`), `added_members`는 C − ∪O 정렬 목록(새 순환은 members 전체), `new_internal_pairs`는 C evidence의 `[from_id, to_id]` 중 O evidence 쌍 합집합에 없는 것을 (from, to) 오름차순으로. `new_cycles`와 `grown_cycles`는 각각 (kind, scheme, tier, candidate_id) 오름차순. | required | I1 |
| F09 | 위반 대응: current `rule_violation` 중 `id`가 baseline `rule_violation` id 집합에 없는 것이 새 위반이다. 항목은 `{"candidate_id", "rule_type", "from_layer", "target"}`에 내부 위반이면 `"to_layer"`와 `"to_id"`(evidence[0].to_id), 외부 위반이면 `"to_external"`을 더한 것이고 candidate_id 오름차순. | required | I1 |
| F10 | package 의존 대응: scheme별로 current `package_dependencies`의 (from_id, to_id) 중 baseline 같은 scheme에 없는 것이 새 package 의존이다(baseline에 scheme이 없으면 전부 새것). 항목 `{"scheme", "from_id", "to_id", "tier"}`, (scheme, from_id, to_id) 오름차순. tier 변화는 보고하지 않는다. | required | I3 |
| F11 | instability 변화: 양쪽 `package_metrics[scheme][package].instability`가 모두 number이고 `abs(current − baseline) >= 0.2 − 1e-12`인 package. 항목 `{"scheme", "package", "baseline", "current", "delta"}`(delta = current − baseline), (−\|delta\|, scheme, package) 순. 한쪽에만 있는 package는 보고하지 않는다. | required | 기본값 D3 |
| F12 | delta 객체는 정확히 `{"policy": "delta.v1", "baseline": {"file_count", "rules_sha256"(없으면 null)}, "rules_changed", "new_cycles", "grown_cycles", "new_violations", "new_package_dependencies", "instability_changes", "resolved", "counts"}`다. `resolved`는 `{"cycles", "violations", "package_dependencies"}` 개수: 같은 key의 current 순환과 member가 하나도 겹치지 않는 baseline 순환 수, current에 없는 baseline 위반 id 수, current에 없는 baseline package 의존 쌍 수. `counts`는 다섯 목록의 길이(`new_cycles`, `grown_cycles`, `new_violations`, `new_package_dependencies`, `instability_changes`). 같은 입력이면 byte 단위로 같은 결과다. | required | 결정성 |
| F13 | CLI `--baseline PATH`: `--granularity symbol`과 함께면 argparse 오류(exit 2). baseline은 규칙 file과 같은 시점(snapshot 전)에 읽고, 실패하면 `[!] Error: <BaselineError 메시지>`를 stderr에 쓰고 exit 1, 출력 file을 만들지 않는다. baseline 경로는 snapshot 제외 경로에 넣는다. `--bottlenecks`와 같은 경로여도 된다(읽은 뒤 덮어씀). 분석 후 `compute_delta`의 `BaselineError`도 exit 1이며 출력 file을 만들지 않는다. 성공하면 stdout에 `[Δ] Delta vs baseline: new cycles N, grown cycles N, new violations N, new package dependencies N, instability changes N` 한 줄, `rules_changed`면 stderr에 `[!] Warning: architecture rules differ from the baseline` 한 줄을 쓴다. | required | I2 |
| F14 | `--fail-on-new`: `--baseline` 없이 쓰면 argparse 오류(exit 2). `cycle`은 `new_cycles`·`grown_cycles` 중 하나라도 비지 않으면, `violation`은 `new_violations`가 비지 않으면, `any`는 둘 중 하나면 걸린다. 새 package 의존과 instability 변화는 실패 조건이 아니다. 걸리면 모든 출력 file을 쓴 뒤 stderr에 `[!] Structural regression (--fail-on-new <걸린 이름들 쉼표 구분>): new cycles N, grown cycles N, new violations N`를 쓰고 exit 3. 안 걸리면 기존과 같이 exit 0. `regressions(delta, fail_on)`은 `any`를 둘로 펼친 뒤 걸린 이름을 `["cycle", "violation"]` 순서로 돌려준다. | required | I2, user answer exit 3 |
| F15 | report validator(`report/bottlenecks/generate.py`)는 v8 payload의 최상위 `delta` key(object)를 허용한다. 다른 schema에서는 여전히 unknown field다. | required | F04 |
| F16 | HTML "구조" 섹션(`#structure-section`, 제목 `03 / 구조`)은 bottleneck 데이터가 file granularity일 때만 보이고 리뷰 섹션 다음에 온다. 하위 목록: (a) delta가 있을 때만 "baseline 대비" — counts 요약 한 줄, `rules_changed`면 경고 문구, 새·커진 순환, 새 위반, 새 package 의존, instability 변화 항목. (b) "순환" — `dependency_cycle`·`package_cycle` candidate, `structure.tier`가 tier 선택(certain/resolved/all, 기본 all) 값과 같은 것만. (c) "경계 규칙 위반" — `rule_violation` candidate, 기존 `candidateReason` 문구 사용. 목록마다 최대 50개를 보이고 넘으면 `외 N개` 문구. 비면 `없음`. 모든 이름은 text로 넣는다(HTML 해석 금지). | required | I5 |
| F17 | 구조 섹션 항목 중 file 집합이 있는 것을 누르면 그래프 탭으로 바꾸고 그 file 중 현재 그래프에 있는 node를 선택하고 화면에 맞춘다. 그래프 상태 문구는 `N개 파일 강조`이고, 현재 코드 분류 필터 때문에 빠진 file이 M > 0개면 ` · M개는 현재 코드 분류 밖`을 붙인다. file 집합: dependency_cycle·순환 delta(scheme file) = members; package_cycle·순환 delta(package scheme) = 현재 candidate evidence의 `file_pairs` file 합집합(delta 항목은 같은 candidate_id의 현재 candidate에서 찾는다); 내부 위반 = target과 to_id; 외부 위반 = target. package 의존·instability 항목은 누를 수 없다. 그래프를 쓸 수 없으면 집합의 첫 file(정렬 기준)의 modal을 연다. | required | I5 |

# Errors
- baseline file 읽기 실패·UTF-8 오류·JSON 오류·깊은 중첩 — stderr `[!] Error: baseline <path>: ...`, exit 1 — 출력 file 없음(HTML, `_assets`, JSON, bottleneck 모두).
- baseline 형식 위반(F05) — stderr에 JSON 경로와 기대값, exit 1 — 출력 file 없음.
- baseline 비호환(F06) — stderr `[!] Error: baseline: ...`, exit 1 — 출력 file 없음.
- `--baseline`과 `--granularity symbol`, 또는 `--baseline` 없는 `--fail-on-new` — argparse usage 오류, exit 2 — 분석하지 않음.
- 구조 회귀(F14) — 출력 file은 모두 정상 작성, stderr 회귀 한 줄, exit 3 — 출력은 회귀가 없을 때와 같은 형식.
- 규칙 변경(F06) — 실패가 아님: stderr 경고 한 줄, `rules_changed: true`, exit는 F14대로.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C01 | normal | fastapi-realworld 실행 결과를 baseline으로 같은 commit 재실행, `--fail-on-new any` | delta 목록 모두 빔, resolved 모두 0, rules_changed false, exit 0 |
| C02 | normal | fastapi-realworld 사본에 순환을 새로 만드는 import 추가 | `new_cycles` 또는 `grown_cycles`에 그 file들이 있고 `--fail-on-new cycle` exit 3, 출력 file 존재 |
| C03 | normal | 예제 규칙으로 fastapi-realworld baseline, 사본에 domain→services import 추가 | `new_violations`에 그 위반, `--fail-on-new violation` exit 3, `--fail-on-new cycle`은 순환이 없으면 exit 0 |
| C04 | normal | 사본에 새 package 간 import 추가 | `new_package_dependencies`에 그 쌍, `--fail-on-new any` exit 0 |
| C05 | normal | 합성: baseline 순환 {a,b}, current {a,b,c} | grown, added_members [c], baseline_candidate_ids [id(a,b)] |
| C06 | normal | 합성: baseline {a,b}, {c,d}; current {a,b,c,d} | grown(\|O\|=2), added_members [] |
| C07 | boundary | 합성: baseline {a,b,c}, current {a,b} | 보고 없음, resolved.cycles 0 |
| C08 | boundary | 합성: baseline {a,b}, current {a,b} 내부 edge 추가 | 보고 없음 |
| C09 | boundary | 합성: baseline {a,b}, current {b,c}(겹침 1, c 추가) | grown, added_members [c] |
| C10 | boundary | 합성: 같은 member 순환이 certain tier에만 새로 생김(all tier엔 이미 있음) | certain tier 항목만 new_cycles |
| C11 | boundary | instability 변화 0.2(부동소수 0.19999999999999996 포함), 0.1999, −0.25 | 0.2와 −0.25만 보고, −0.25가 먼저 |
| C12 | boundary | baseline에 framework scheme 없음, current에 있음 | 그 scheme 쌍 전부 새 package 의존 |
| C13 | boundary | 규칙 file의 key 순서·주석·중복만 다름 | 같은 rules_sha256, rules_changed false |
| C14 | boundary | 규칙에 layer 하나 추가 | rules_sha256 다름, rules_changed true, 경고 한 줄, 비교 계속 |
| C15 | boundary | `--baseline b.json --bottlenecks b.json` | 정상 delta, 파일이 새 출력으로 덮임 |
| C16 | error | baseline 경로 없음, 디렉터리, 잘못된 UTF-8, 잘린 JSON, 10만 단계 중첩 배열 | exit 1, stderr `[!] Error: baseline`, 출력 file 없음 |
| C17 | error | schema v6/v7, granularity 없음, structure_policy 다름, package_dependencies 없음, cycle members 타입 오류, rule_violation에 to_layer·to_external 둘 다 없음 | exit 1, 메시지에 JSON 경로 |
| C18 | error | current는 규칙 사용, baseline은 미사용(그 반대도) | exit 1 |
| C19 | error | `--baseline x --granularity symbol`; `--fail-on-new any`만 | exit 2 |
| C20 | edge | baseline에 `delta` key 있음(이전 delta 실행 결과) | 무시하고 정상 비교 |
| C21 | edge | baseline candidate evidence에 candidate_group_id 치환 record | 정상 비교 |
| C22 | edge | `--fail-on-new cycle --fail-on-new violation`, 둘 다 걸림 | stderr에 `cycle,violation`, exit 3 |
| C23 | edge | delta 항목 이름에 `<img onerror=...>` 포함 file 경로 | HTML에서 text로 보이고 실행되지 않음 |
| C24 | normal | HTML: 순환 항목 클릭 | 그래프 탭, 선택 node = members, 상태 `N개 파일 강조` |
| C25 | edge | HTML: 코드 분류 필터 "운영 코드"에서 test file 포함 순환 클릭 | 보이는 file만 선택, ` · M개는 현재 코드 분류 밖` |
| C26 | edge | HTML: 그래프 라이브러리 없음 | 클릭 시 첫 file modal |
| C27 | normal | `--baseline` 없음, 5개 fixture | F02: package_dependencies(와 규칙 시 rules_sha256) 제거 후 base 출력과 byte 동일 |
| C28 | normal | 위반 51개 | 목록 50개와 `외 1개` |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | delta 판정이 기능 핵심 |
| Performance efficiency | yes | CI·hook에서 매 변경마다 실행; 출력 크기 증가 |
| Compatibility | yes | 기존 출력·validator·HTML과 공존, baseline 형식 호환 |
| Interaction capability | yes | HTML 구조 섹션과 CLI 메시지 |
| Reliability | yes | 잘못된 baseline에도 traceback 없이 실패 |
| Security | yes | baseline·경로 문자열이 HTML로 들어감 |
| Maintainability | yes | 새 module 테스트 가능성 |
| Flexibility | no | 설치·이식 환경 변화 없음 |
| Safety | no | 물리적 위해 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | Functional suitability / correctness | delta 판정 | 합성 결정표와 fixture 사본 | Cases 전부 기대값 | automated, mutation | F07–F12 |
| Q02 | Performance efficiency / time behaviour | `compute_delta` 단독, futuramaapi 실제 bottleneck JSON 두 개 | wall-clock 초, 3회 중 최소 | ≤ 1.0 s | automated | 기본값 |
| Q03 | Performance efficiency / time behaviour | 합성 대형 입력: 순환 1,000개(각 member 20), 위반 20,000개, package 쌍 20,000개 | wall-clock 초 | ≤ 3.0 s | automated | 기본값 |
| Q04 | Performance efficiency / resource utilization | 5개 fixture bottleneck JSON 크기 | 현재 bytes / base bytes | ≤ 1.03 | review R1 + automated | user answer(측정 0.07–1.3%) |
| Q05 | Compatibility / co-existence | `--baseline` 없는 출력 | F02 byte 비교 | 5개 fixture 전부 동일 | automated | F02 |
| Q06 | Reliability / fault tolerance | 잘못된 baseline | fuzz (a) crash 수 | 0 / 20,000 | fuzz | F05 |
| Q07 | Reliability / faultlessness | delta 대칭 성질 | fuzz (b) 위반 수 | 0 / 20,000 | fuzz | F12 |
| Q08 | Security / integrity | HTML에 들어가는 이름 | C23 브라우저 확인 | script 실행 0 | automated | F16 |
| Q09 | Interaction capability / operability | CLI 메시지·exit code | F13·F14 문구와 exit | 정확히 일치 | automated | F13, F14 |
| Q10 | Maintainability / testability | `bottlenecks/delta.py` | coverage.py branch | ≥ 90% | automated(Test command) | 기본값 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V01 | F07, F08, C05–C10 | `compute_delta` 순환 판정, 합성 payload | unit; 전부 | decision table | 규칙: (O 비어 있음), (O=1, 추가 member 있음), (O=1, 부분집합), (O≥2, 추가 없음), (O≥2, 추가 있음), (내부 edge만 증가), tier별 독립, kind별 독립(dependency_cycle·package_cycle), scheme별 독립 — 9 | 100% | 항목 분류·필드가 독립 계산한 기대값과 일치 | Test command |
| V02 | F09, F10, F12 | 위반·package 의존·resolved 개수 | unit; 전부 | equivalence partitioning | 내부 위반 신규, 외부 위반 신규, 기존 위반 유지, 사라진 위반, package 쌍 신규, 쌍 유지, 쌍 사라짐, baseline에 없는 scheme, tier만 바뀐 쌍 — 9 | 100% | 목록·resolved·counts 일치 | Test command |
| V03 | F11, C11 | instability 경계 | unit; 전부 | boundary value analysis (3-value) | +0.2 경계(0.19999999999999996, 0.2, 0.2000001), −0.2 경계 동일 3값, null 한쪽, 한쪽 package만 — 8 | 100% | 보고 여부·정렬 | Test command |
| V04 | F05, F06, C16–C18, C20, C21 | `load_baseline`·`compute_delta` 오류 경로 | unit; F05 각 검사 조건 하나씩 위반 | syntax testing | F05 조건 각각(읽기·UTF-8·JSON·깊이·루트·schema·granularity·file_count·structure_policy·package_dependencies 형태·tier 값·package_metrics instability·candidates 형태·cycle structure·cycle evidence·rule_violation 필드·rules_sha256 타입), F06 두 비호환 조건, 무시 대상(delta key, 추가 필드, candidate_group_id) — 각 1 | 100% | `BaselineError`, 메시지에 경로; 무시 대상은 정상 | Test command |
| V05 | F03, C13, C14 | `rules_digest` | unit; 전부 | metamorphic testing | 관계: key 순서 변경 불변, 주석 추가 불변, 목록 중복 불변, forbid 분할 불변, 각 규칙 section(layers·allow·forbid·external·forbid_external·allow_external)에서 한 값 변경 시 변함 — 10 | 100% | digest 같음/다름; 정의식 독립 계산과 같음 | Test command |
| V06 | F01, F02, C27 | bottleneck JSON `package_dependencies`, 무변화 | integration; 5개 fixture | equivalence partitioning | fixture 5개 × {package_dependencies가 독립 계산한 쌍과 일치, 제거 시 base byte 동일} = 10 | 100% | 일치 | Test command (base 출력은 base_commit에서 만든 manifest) |
| V07 | F13, F14, C01–C04, C15, C19, C22 | CLI | integration; fixture 사본 subprocess | scenario testing | C01, C02, C03, C04, C15, C19(2개), C22, rules_changed 경고(C14) — 9 | 100% | exit code, stdout·stderr 문구, 출력 file 존재 | Test command |
| V08 | Errors, C16–C18 | CLI 오류 시 출력 없음 | integration | equivalence partitioning | 읽기 실패, 형식 위반, 비호환 — 3 | 100% | exit 1, 출력 file 4종 부재 | Test command |
| V09 | F14 | `regressions` | unit | combinatorial (all combinations) | fail_on 부분집합 {cycle, violation, any}의 비어 있지 않은 7조합 × delta 상태(new만·grown만·violation만·모두 빔·package/instability만) 5 = 35 | 100% | 반환 목록 | Test command |
| V10 | F04, F15 | JSON·validator | unit | equivalence partitioning | delta 있는 v8 허용, delta 없는 v8 key 부재, v6에 delta 거부 — 3 | 100% | validator 통과/거부 | Test command |
| V11 | F16, F17, C23–C26, C28 | HTML 구조 섹션 | end-to-end; Playwright | scenario testing | 섹션 표시(file)/숨김(symbol), baseline 대비 목록(delta 있음/없음), rules_changed 경고, tier 선택, 위반 문구, 50개 상한, 순환 클릭 강조, package_cycle 클릭 file 집합, 외부 위반 클릭, 필터 밖 문구, 그래프 없음 modal, XSS 문자열 — 12 | 100% | DOM 문구, `ReportGraph.getSelectedNodes()`, script 미실행 | Test command |
| V12 | Q02, Q03 | 성능 | integration | boundary value analysis (2-value) | Q02, Q03 각 임계 — 2 | 100% | 시간 ≤ 임계 | Test command |
| V13 | Q04 | 크기 | integration + review | equivalence partitioning | 5개 fixture 비율 | 100% | ≤ 1.03 | Test command, R1 |
| V14 | F07–F12 | 오류 추측 | unit | error guessing | 겹침을 member 대신 id로 비교, 커진 순환을 new로 분류, added_members에 O 밖 baseline member 포함, 위반 비교에 tier 포함, scheme 섞임, resolved에 겹치는 baseline 순환 포함 | none — experience-based | 각 결함이 테스트 실패로 드러남 | Test command, hand mutation |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| D1 | baseline이 v8·file·같은 structure_policy가 아니거나 규칙 사용 여부가 다르면 exit 1 | 비교 의미 없음 | brief v1 — approved |
| D2 | 규칙 의미가 바뀌면 오류 대신 `rules_changed` 경고, 비교 계속 | 규칙 강화 뒤 baseline 재생성은 사용자 몫 | brief v1 — approved |
| D3 | instability 변화 임계 \|Δ\| ≥ 0.2, 보고만 | 임의 기준; 상수 하나로 변경 가능 | brief v1 — approved |
| D4 | 새 package 의존·instability 변화는 `--fail-on-new` 대상 아님 | 정상 성장일 수 있음 | brief v1 — approved |
| D5 | 회귀 시에도 모든 출력 file을 쓴 뒤 exit 3 | CI가 보고서를 남길 수 있게 | brief v1 — approved |
| D6 | 같은 SCC 내부 edge만 늘어난 경우 보고 안 함 | 계획의 "새로 생긴·커진 SCC" 정의 | brief v1 — approved |
| D7 | `rules_sha256`은 규칙 file byte가 아니라 해석된 규칙의 정규형 hash | 주석·순서 변경으로 경고가 뜨지 않게 | brief v1 — approved |
| D8 | baseline 경로를 snapshot에서 제외, `--bottlenecks`와 같은 경로 허용 | 덮어쓰기 ratchet 사용 편의 | brief v1 — approved |
| D9 | HTML 목록 상한 50, 구조 섹션은 리뷰 섹션 뒤 `03 / 구조` | 기존 페이지 크기 50과 맞춤 | brief v1 — approved |
| D10 | package 의존·instability delta 항목은 그래프 강조 없음 | package_dependencies에 file 근거를 넣지 않음(크기) | brief v1 — approved |
| D11 | exit 3 | user answer | user answer |
| D12 | 모든 tier가 실패 조건 | user answer | user answer |
| D13 | package_dependencies 항상 출력 | user answer | user answer |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F01, F02 | C27 | V06, V13 | Test command, R1 |
| F03 | C13, C14 | V05, V07 | Test command |
| F04, F15 | C20 | V10 | Test command |
| F05, F06 | C16–C18, C20, C21 | V04, V08 | Test command, fuzz (a) |
| F07, F08 | C05–C10, C02 | V01, V07, V14 | Test command, fuzz (b), mutation |
| F09, F10, F12 | C03, C04, C12 | V02, V07, V14 | Test command, fuzz (b) |
| F11 | C11 | V03 | Test command |
| F13, F14 | C01–C04, C15, C19, C22 | V07, V08, V09 | Test command |
| F16, F17 | C23–C26, C28 | V11 | Test command, R2 |
| Q02, Q03 | — | V12 | Test command |
| Q04 | — | V13 | Test command, R1 |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 2 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V01, V02, V03, V04, V06, V08, V09, V10, V12, V13, V14 | 3 | tests at batch 1; run 3 | accepted (verifier 1) | H01, H02, H04–H10, H12, H13 killed; H03 equivalent (any baseline cycle sharing a member with C is in O, so ∪O ⊇ C∩all-baseline-members) | batch 2 additive (new tests only in test_delta/test_delta_cli/test_structure_panel_browser; F-05 restores a stricter existing assertion) |
| V05, V07, V11 | 4 | batch 2 tests; run 4 | accepted (verifier 2) | F-01→H15 killed, F-02→H14 killed, F-03→H11 killed, F-04→H16 killed; H17 killed | F-05 v4 scope |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 1 | Test command run 1: 15 failed / 2384 passed | — | 분류 아래 | correction batch 1 |
| 1 | `test_V05_C13_list_duplicates_are_irrelevant`, `test_V07_C13_reordered_commented_rules_do_not_warn`: digest differs for duplicated layer paths | spec gap (verified: `LayerSelector.paths/packages` keep input order and duplicates, F03 hashed stored tuples) | v3 F03 sorts/dedupes layer paths·packages | pending |
| 1 | `test_V07_C01/C02/C03/C22`: `r_assets` absent on success | test defect (verified: renderer at base_commit never creates `_assets`; only excluded as output path) | test: do not require `_assets` on success | pending |
| 1 | `test_report_structure::test_V06_*` ×5: section count 5≠4 and `^03` text present | expected change (F16 new section) within allowed adjustment | test: section list includes `#structure-section`; `03` allowed when file granularity | pending |
| 1 | `test_structure_integration::test_V11_size_ratio_per_fixture[futuramaapi]` 1.257 > 1.25 | expected change (F01 growth; Q04 bounds it separately) | test: strip `package_dependencies` before ratio | pending |
| 2 | Test command run 2: 1 failed / 2398 passed (`test_architecture_rules_integration::test_V11_synthetic_time` 12.65−4.13 s > 5.0) | environment (verified: load average peaked 28–70; isolated reruns pass twice at load 70) | none | not a defect; batch 1 items resolved |
| 2 | fuzz harness setup failures (module path; harness RecursionError in its own path walk) | main harness defect (verified traceback in harness `paths`) | PYTHONPATH, depth cap 40, raw-byte deep nesting | inconclusive runs discarded |
| 2 | fuzz (a) 20,000 execs, crashes 0 (accepted 13,016); (b) 20,000 execs, violations 0 | — | `tests/delta_evidence/fuzz/` | pass |
| 2 | R1 `tests/delta_evidence/size.json`: ratios 1.0013–1.0171 (≤1.03), stripped output equals base for all 6 runs; R2 screenshots `r2-structure-section.png`, `r2-graph-highlight.png` (new_cycles click → 2 nodes, `2개 파일 강조`, exit 3 with `cycle,violation`) | — | review | pass |
| 3 | Test command run 3: rc 0, 2399 passed; delta.py branch 99% (missing: baseline without `coverage` key 83->exit/86->exit; line 132 RecursionError guard around `_check_baseline`) | test gap minor / undeclared defensive code | advisory A-01 (no coverage key case untested), A-02 (line 132 unreachable guard) | pass |
| 3 | verifier 1 retry: F-01 tier select not exact per tier; F-02 baseline snapshot exclusion unobserved; F-03 digest sort of multi-element layer lists unexercised; F-04 tab switch not observed from 목록 tab; F-05 `StructureResult` field assertion weakened to `[:3]` outside allowed scope | F-01–F-04 obligation evidence gaps (main probe: app.js filters `c.structure?.tier === tier`, `highlightFiles` calls `setTab('graph')`, `rules_digest` uses `sorted(set(...))`, cli adds baseline to `excluded_paths`); F-05 spec challenge | v4: Signatures declare the field; allowed scope extended; batch 2 tests (+A-03 labelled summary, +violation identity same pair two rule types) | tests added |
| 4 | hand mutations H01–H17 (`tests/delta_evidence/hand-mutations.json`): 16 killed, H03 survived | H03 equivalent (main reasoning above) | — | accepted |
| 4 | mutation tool (`tests/delta_evidence/mutation-tool.json`): seed 20261018, pool 159, 30 executed, 30 killed, survival 0% | — | no triage needed | pass |
| 4 | Test command run 4: rc 0, 2407 passed; delta.py branch 99% | — | — | pass |
| 4 | verifier 2 pass: F-01–F-05 closed, H03 equivalence agreed; advisories A-01 (baseline without `coverage` untested), A-02 (line 132 guard uncovered), A-03 (summary labels not asserted, order is) | — | — | complete |
| 4 | narrating test docstrings removed (delta_support ×2, test_delta_cli module, test_delta_integration helper, browser helper); delta tests rerun 275 passed | — | — | no behavior change |

# Version Log
## v4
- [contract] verifier 1 F-05: Signatures declare `StructureResult.package_dependencies`; existing-test allowed scope adds field-list extension and stripped-size ratio. No brief item changed.
## v3
- [contract] F03: layer paths·packages sorted+deduped in the digest form (run 1 evidence: stored tuples keep duplicates, contradicting the stated invariance). Brief statement unchanged.
## v2
- Contract clarification (test-implementer ambiguities): F16 tier 선택은 값 동일 비교; F06 `rules_sha256`이 양쪽 모두 없을 때도 다름. 구현 보고와 일치, brief 항목 변경 없음.
## v1
- Initial draft from Phase 3 plan and user answers (package_dependencies 항상 출력, exit 3, 모든 tier).
