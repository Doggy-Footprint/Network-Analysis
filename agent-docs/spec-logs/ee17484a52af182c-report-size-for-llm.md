---
version: 4
run_id: ee17484a52af182c
status: complete
base_commit: 5ddd4261850450578d610b2d3d309a5d0b7729cd
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자 | "handoff를 체크해서 결과물 경량화를 수행하자. 코어 내용만 남긴 상태로 LLM에게 체크해야 할 목록을 경량화" (handoff agent-docs/handoff/85aa37516a23897d-report-size-for-llm.md) | `--bottlenecks`를 주면 LLM에게 그대로 전달할 수 있는 작은 Markdown handout이 함께 나온다 |
| I2 | 사용자 | "전체적인 규모 축소 (few MB + LLM handout)", vendure ~47MB 허용, "details도 분리" | file granularity의 `bottlenecks.json`, `report.json`, `report.html`이 candidate나 relation을 빼지 않고 크게 줄어든다 |
| I3 | 프로젝트(AGENTS.md) | recall 우선: 불확실한 relation도 남긴다 | 줄인 출력에서 줄이기 전과 같은 candidate 집합과 근거 내용을 참조로 복원할 수 있다 |

# Scope
In scope: file granularity 출력의 직렬화 형식. (1) `bottlenecks.json` schema `bottlenecks.v9`: evidence_spread, dependency_cycle, package_cycle, unstable_dependency의 evidence 표현. (2) `--json` `report.json` schema_version "7": `details` 분리, compact 출력. (3) details 파일(`<HTML stem>.details.json`). (4) HTML 임베드 데이터에서 details 제거. (5) handout Markdown 자동 생성. (6) `--baseline` delta가 v8과 v9 baseline을 모두 읽는다.
Out of scope: symbol granularity 출력(`bottlenecks.v6`, report.json schema "5" 형식 — compact 여부만 F07 적용), candidate 선정·지표 계산 로직, large_node·unresolved_boundary·untested_hub·isolated_node·rule_violation의 evidence 형식, file edge의 시각화 필드, docs/scripts READS 순환 문제(별도 작업), `scripts/eval/*` 수정, 평가 실험.

# Paths
Implementation: bottlenecks/core.py, bottlenecks/handout.py, report/bottlenecks/generate.py, bottlenecks/delta.py, analysis/structure.py, code_analyzer/cli.py, language_analyzers/core/serialization.py, report/unified.py, renderers/html/renderer.py, renderers/html/static/app.js
Tests: tests/
Test command: .venv/bin/python -m pytest -q
Review evidence: R1 real-repo size run — main이 scratchpad에서 7개 평가 저장소(`scripts/eval/repos.json`의 github/commit, depth-1 clone)에 `.venv/bin/python -m code_analyzer <clone> <analyzers> -o <out>/report.html --json --bottlenecks <out>/bottlenecks.json`을 실행하고, 파일 크기·`json.load` 최대 RSS(`/usr/bin/time -l python3 -c 'import json;json.load(open(p))'`)·base_commit 출력과의 candidate id 집합 비교·handout 크기를 표로 남긴다. 산출물: scratchpad `size-after/summary.md`, 실행 기록은 Execution ledger에 요약.
Fuzzing: none — 새 입력 표면은 v9 baseline 검증뿐이고 구조 검증이라 등가 분할(E 계열 Case)로 다룬다. hypothesis 등 fuzz 도구가 환경에 없다.
Mutation tool: main이 scratchpad에 작성한 AST mutation 스크립트(비교·산술·불리언·상수·조건 삭제 연산자). base_commit 이후 변경된 Implementation Python 줄만 대상. 최대 30개 표본, seed 20261022. 실행 명령 `.venv/bin/python -m pytest -q -p no:cacheprovider -x -n 0 <이번 run이 추가·수정한 테스트 파일>`. 생존율 임계 40%.

# Signatures
bottlenecks.core.analyze_bottlenecks(snapshot, architecture, weights, *, analysis=None, rules=None) -> BottleneckReport  (변경 없음; file granularity에서 schema "bottlenecks.v9")
bottlenecks.core.bottlenecks_to_json(report) -> str  (변경 없음)
bottlenecks.handout.render_handout(report: Mapping, architecture: Mapping) -> str  (신규; report는 bottlenecks.json과 같은 dict, architecture는 details를 포함한 `architecture_to_dict` 결과)
bottlenecks.delta.load_baseline(path) -> dict  (v8, v9 모두 허용)
language_analyzers.core.serialization.architecture_to_dict(architecture) -> dict  (변경 없음; details 포함 그대로)
CLI: 새 플래그 없음. 출력 파일 추가: `<HTML stem>.details.json`, `<bottlenecks 경로에서 끝의 ".json" 제거>.handout.md`

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F01 | file granularity `bottlenecks.json`의 `schema`는 `"bottlenecks.v9"`다. symbol granularity는 `"bottlenecks.v6"` 그대로다 | must | I2, D01 |
| F02 | v9 `dependency_network.file_ids`는 `dependency_network.node_metrics`의 key를 오름차순 정렬한 문자열 목록이다. v9 `dependency_network.evidence_columns`는 정확히 `{"file_pair": ["from","to","relations","max_weight","evidence_count","tier"], "package_pair": ["from_id","to_id","relations","max_weight","evidence_count","tier","file_pairs"]}`이다 | must | I2, D02 |
| F03 | evidence_spread의 evidence는 그 candidate 근거 edge들의 `report details.edges` index(0부터)를 중복 없이 오름차순으로 담은 정수 목록이다. index가 가리키는 detail edge 집합은 v8 evidence 레코드의 `detail_edge_index` 집합과 같다 | must | I3, D03 |
| F04 | dependency_cycle과 unstable_dependency의 evidence 항목은 file_pair 행 `[from, to, relations, max_weight, evidence_count, tier]`이다. from/to는 `file_ids`의 정수 index, relations는 정렬된 문자열 목록이다. 행의 순서와 각 값은 v8 레코드의 같은 필드(from_id, to_id, relations, max_weight, evidence_count, tier)와 같다. v8의 `detail_edge_indices`는 행에 없다 | must | I3, D02 |
| F05 | package_cycle의 evidence 항목은 package_pair 행 `[from_id, to_id, relations, max_weight, evidence_count, tier, file_pairs]`이다. from_id/to_id는 package id 문자열, file_pairs는 `[from_index, to_index]` 쌍 목록(`file_ids` index)이다. 순서와 값은 v8 레코드와 같다 | must | I3, D02 |
| F06 | F03~F05 밖의 candidate kind, candidate의 id·kind·target·metrics·status·coverage·structure(cut_candidates 포함), dependency_network의 다른 key, candidate 집합은 v8과 같다 | must | I3 |
| F07 | `--json`의 report.json은 공백 없는 compact JSON(`separators=(",", ":")`)이다. file granularity에서는 `schema_version`이 `"7"`이고 `details` key가 없으며, `details_file`에 details 파일의 이름(report.json 디렉터리 기준 상대 경로)을 담는다. symbol granularity는 schema "5"와 key 구성이 그대로다 | must | I2, D04 |
| F08 | file granularity에서 `--json` 또는 `--bottlenecks`가 있으면 `<HTML 출력 경로의 stem>.details.json`(HTML과 같은 디렉터리)에 `architecture.details`(nodes, edges, node_files, node_owners, file_nodes) 전체를 compact JSON으로 쓴다. v9 `bottlenecks.json`의 최상위 `details_file`은 bottlenecks.json 디렉터리 기준 이 파일의 상대 경로다. `--json`도 `--bottlenecks`도 없으면 details 파일을 쓰지 않는다 | must | I3, D05 |
| F09 | HTML 리포트에 임베드되는 architecture에는 `details`가 없다. 파일 layer(`file_layers`) 결과와 화면 동작(candidate 목록, 구조 탭의 순환 파일 강조, rule_violation 문구)은 details가 있던 때와 같다. package_cycle의 순환 파일 목록은 v9 package_pair 행의 file_pairs를 `file_ids`로 풀어 얻는다 | must | I2, D06 |
| F10 | file granularity에서 `--bottlenecks PATH`가 있으면 handout을 `PATH`에서 끝의 `.json`을 뗀 경로 + `.handout.md`에 쓴다(`.json`으로 끝나지 않으면 PATH + `.handout.md`). symbol granularity에서는 handout을 쓰지 않는다 | must | I1, D07 |
| F11 | handout(영문 Markdown)은 다음 절을 이 순서로 갖는다: `# Dependency bottleneck handout` 제목과 project/파일 수/edge 수; `## How to read`(relation·confidence·resolution·weight·tier의 뜻, bottlenecks.json과 details 파일의 관계, evidence 참조 해석법); `## Candidate counts`(kind별 개수 표, 0개 kind 생략); `## Production rankings`(`rankings_by_category.production`의 key별 상위 10); `## Packages`(scheme별 instability 상위 10 package와 file_count, ca, ce); `## Candidates`(kind마다 `### <kind>` 절). | must | I1, D08 |
| F12 | `### <kind>` 절은 kind별 정렬 규칙(D09)의 상위 10개 candidate를 보여준다. 각 항목: candidate id, target, metrics 전부, structure가 있으면 scheme/tier/members 수와 cut_candidates 상위 5개(from→to, relations, max_weight), 근거 개수, 대표 근거 최대 3개(evidence_spread는 detail edge의 `from_id → to_id`, relation, `file_path:start_line`; 순환·unstable은 from→to 파일 경로와 relations; 그 밖은 evidence의 path/start_line 또는 to_id). 10개를 넘으면 `… N more <kind> candidates in bottlenecks.json` 한 줄로 남은 개수를 적는다 | must | I1, I3, D09 |
| F13 | 같은 입력에 대해 bottlenecks.json, report.json, details 파일, handout은 바이트 단위로 같다 | must | I2 |
| F15 | 단독 렌더러 `python -m report.bottlenecks.generate`(`report.bottlenecks.render_report`)는 `bottlenecks.v9` 입력을 받아 HTML을 만든다. evidence 항목이 정수(evidence_spread)나 행 배열(순환·unstable)이어도 검증 오류가 나지 않는다. v6·v7·v8 입력 동작은 그대로다 | must | I2(호환), 프로젝트 기본값: 기존 동작 보존 |
| F14 | `load_baseline`은 schema `"bottlenecks.v8"`과 `"bottlenecks.v9"`를 모두 받는다. 같은 분석 결과를 v8로 직렬화한 baseline과 v9로 직렬화한 baseline에 대한 delta 결과(new/grown/resolved cycle, new_internal_pairs, violations, package dependency, instability 변화)는 같다 | must | I2, D10 |

# Errors
- E01 v9 baseline에 `dependency_network.file_ids`(문자열 목록) 또는 `evidence_columns`가 없거나 형식이 틀림 — `BaselineError`(메시지에 baseline 경로와 JSON 위치), CLI는 기존 baseline 오류와 같은 종료 코드와 stderr — 출력 파일 미생성은 기존 baseline 오류 동작과 같다.
- E02 v9 baseline의 순환 evidence 행이 list가 아니거나, 길이가 columns와 다르거나, file index가 정수가 아니거나 `file_ids` 범위 밖 — E01과 같은 신호와 상태.
- E03 v8/v9가 아닌 schema baseline — 기존과 같이 `BaselineError`(기대값에 v8, v9 모두 표시).
- E04 details 파일이나 handout 쓰기 실패(OSError) — 기존 출력 쓰기 실패와 같이 `[!] Error:` stderr와 종료 코드 1.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C01 | normal | evidence_spread·dependency_cycle·package_cycle·unstable_dependency가 모두 나오는 file granularity fixture를 base_commit 형식(v8 기대값, 테스트가 architecture에서 독립 계산)과 비교 | F01~F06 모두 만족, candidate id 집합 동일 |
| C02 | normal | 같은 fixture, `--json --bottlenecks` CLI 실행 | report.json compact·schema "7"·details 없음·details_file 존재, details 파일 내용 = architecture.details, bottlenecks.json details_file 해석 시 같은 파일 |
| C03 | normal | 같은 fixture로 handout 생성 | F11 절 순서, F12 항목 내용, 파일 경로 규칙 F10 |
| C04 | boundary | 어떤 kind의 candidate가 정확히 10개 / 11개 | 10개: "more" 줄 없음; 11개: 10개 표시 + `… 1 more` |
| C05 | boundary | 근거가 1개·3개·4개인 candidate | 대표 근거 1·3·3개 |
| C06 | boundary | `--bottlenecks out/b.json` / `--bottlenecks out/b` / `--bottlenecks out/b.JSON` | handout 경로 `out/b.handout.md` / `out/b.handout.md` / `out/b.JSON.handout.md` |
| C07 | edge | candidate가 하나도 없는 작은 저장소 | v9 형식 유지(candidates 빈 목록, file_ids 존재), handout에 Candidates 절 제목과 "No candidates." |
| C08 | edge | 순환이 없는 저장소(cycle kind 0개) | Candidate counts 표에 cycle kind 없음 |
| C09 | normal | `--bottlenecks`만(--json 없음) | details 파일과 handout 생성, report.json 없음 |
| C10 | normal | `--json`·`--bottlenecks` 모두 없음 | details 파일·handout 없음 |
| C11 | normal | symbol granularity `--json --bottlenecks` | bottlenecks.v6 형식·handout 없음·details 파일 없음, report.json compact이고 schema "5" |
| C12 | normal | 같은 입력 2회 실행 | 네 출력 파일 바이트 동일 |
| C13 | normal | HTML 생성 | 임베드 데이터에 details 없음, layer 결과와 package_cycle 순환 파일 강조 목록이 details가 있을 때와 같음 |
| C14 | normal | 같은 저장소 v8 baseline 파일(테스트가 v8 형식으로 작성) vs v9 baseline 파일, 변경된 현재 분석 | 두 delta 결과 동일, 신규/성장 순환 검출 |
| C15 | error | v9 baseline에서 file_ids 누락 / evidence_columns 누락 | E01 |
| C16 | error | v9 baseline의 cycle 행 file index 범위 밖 / 음수 / 문자열 / 행 길이 불일치 | E02 |
| C17 | error | schema "bottlenecks.v7" baseline | E03 |
| C19 | normal | CLI가 쓴 v9 bottlenecks.json으로 `python -m report.bottlenecks.generate` 실행 / v8 golden으로 실행 | 둘 다 종료 코드 0, HTML 생성, package_cycle 순환 파일 강조가 동작 |
| C18 | error | details 파일 경로가 디렉터리로 존재해 쓰기 실패 | E04 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 형식 변환이 근거를 빠뜨리지 않아야 한다(I3) |
| Performance efficiency | yes | 이번 작업의 목적이 출력 크기와 읽기 메모리 축소다 |
| Compatibility | yes | 기존 v8 baseline과 HTML 리포트 동작을 유지해야 한다 |
| Interaction capability | yes | handout이 LLM이 바로 읽을 수 있는 구조여야 한다 |
| Reliability | yes | 잘못된 baseline에서 crash 없이 정해진 오류를 내고, 출력이 결정적이어야 한다 |
| Security | no | 새 신뢰 경계 없음. 로컬 파일만 읽고 쓰며 baseline 검증은 Reliability에서 다룬다 |
| Maintainability | no | 일반 리뷰 범위. 별도 측정 목표 없음 |
| Flexibility | no | 설치·이식 환경 변화 없음 |
| Safety | no | 물리적·인적 위해 경로 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | Functional suitability / completeness | 7개 평가 저장소 실제 출력 | base_commit 분석기 출력과 새 출력의 candidate id 집합 및 kind별 근거 개수(v8 레코드 수 = v9 항목 수) 비교 / 개수 차이 | 차이 0 | review R1; automated C01 | I3 |
| Q02 | Performance efficiency / capacity | `bottlenecks.json` 크기, 7개 저장소 | 파일 바이트 / MB(10^6) | vendure ≤ 80MB, 나머지 각 ≤ 20MB (낮을수록 좋음) | review R1 | I2, D11 |
| Q03 | Performance efficiency / resource utilization | vendure `bottlenecks.json`을 Python `json.load`로 읽는 최대 RSS | `/usr/bin/time -l` maximum resident set size / MB | ≤ 1000MB | review R1 | I2, D11 |
| Q04 | Performance efficiency / capacity | handout 크기, 7개 저장소 | 파일 바이트 / KB(10^3) | 각 ≤ 200KB | review R1; automated C04(상위 10 제한) | I1, D08 |
| Q05 | Performance efficiency / time behaviour | vendure 분석 전체 시간 | CLI wall time / s, base_commit 측정 136s 기준 | ≤ 150s | review R1 | D11 |
| Q06 | Compatibility / interoperability | v8 baseline으로 delta | C14 결과 동일성 | 차이 0 | automated C14 | D10 |
| Q07 | Interaction capability / appropriateness recognizability | handout 구조 | F11 절 존재·순서, F12 항목 필드 | 모든 절과 필드 존재 | automated C03; review R1(vendure handout 육안 확인) | I1 |
| Q08 | Reliability / fault tolerance | 잘못된 v9 baseline | C15~C17이 BaselineError로 끝나고 다른 예외 없음 | 모든 Case 통과 | automated | E01~E03 |
| Q09 | Reliability / maturity | 결정성 | C12 바이트 비교 | 동일 | automated | F13 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V01 | F01,F02,F03,F04,F05,F06,C01,Q01 | `analyze_bottlenecks` + `bottlenecks_to_json` 결과 dict, file granularity fixture | integration; 네 kind가 모두 나오는 fixture 1개 이상 | equivalence partitioning | EP1 evidence_spread, EP2 dependency_cycle, EP3 package_cycle, EP4 unstable_dependency, EP5 변경 안 된 kind(large_node·unresolved_boundary·untested_hub·isolated_node 중 fixture에 있는 것), EP6 dependency_network 나머지 key | 100% | 테스트가 architecture(details, file pair)에서 v8 의미의 기대값을 독립 계산하고 v9 출력을 디코드해 같음을 확인 | pytest |
| V02 | F07,F08,C02,C09,C10,C11 | CLI 출력 파일 | integration(CLI 호출) | decision table | 조건: granularity(file/symbol) × --json(y/n) × --bottlenecks(y/n); 규칙 R1 file,y,y R2 file,y,n R3 file,n,y R4 file,n,n R5 symbol,y,y | 100% (5 rules) | 파일 존재/부재, report.json schema·compact·details_file, details 내용 | pytest |
| V03 | F10,C06 | handout 경로 | unit 또는 CLI | boundary value analysis (2-value) / syntax | `.json` 접미사 있음, 없음, 대문자 `.JSON` | 100% | C06 경로 | pytest |
| V04 | F11,F12,C03,C04,C05,C07,C08,Q07 | handout 내용 | unit(`render_handout`)과 CLI | boundary value analysis (2-value) | candidate 수 10/11, 근거 수 1/3/4, candidate 0개, cycle kind 0개, 절 순서 | 100% | 절 제목 순서, 항목 필드, more 줄 | pytest |
| V05 | F13,C12,Q09 | 네 출력 파일 | integration | equivalence partitioning | 두 번 실행 바이트 비교 1 class | 100% | 동일 | pytest |
| V06 | F09,C13 | HTML 임베드 데이터와 브라우저 동작 | integration(임베드 JSON) + 기존 browser 테스트 방식(playwright)으로 package_cycle 강조 | scenario testing | S1 임베드에 details 없음, S2 layers 동일, S3 package_cycle 순환 파일 강조, S4 dependency_cycle 강조, S5 rule_violation 문구 to_id | 100% | 각 시나리오 기대값 | pytest |
| V07 | F14,C14,Q06 | `load_baseline` + delta | integration | equivalence partitioning | baseline schema v8, v9 | 100% | delta 결과 동일 | pytest |
| V08 | E01,E02,E03,C15,C16,C17,Q08 | `load_baseline` | unit | equivalence partitioning + boundary value analysis | file_ids 누락, evidence_columns 누락, 행 길이 불일치, index 문자열, index -1, index = len(file_ids), schema v7 | 100% | BaselineError, 경로와 위치 메시지 | pytest |
| V09 | E04,C18 | CLI 쓰기 실패 | integration | error guessing | details 경로가 디렉터리, handout 경로가 디렉터리 | none — experience-based | 종료 코드 1, `[!] Error:` | pytest |
| V11 | F15,C19 | 단독 렌더러 CLI와 `render_report` | integration | equivalence partitioning | 입력 schema v9, v8 | 100% | 오류 없이 HTML, v9 package_cycle 파일 목록이 file_ids로 풀림 | pytest |
| V10 | Q02,Q03,Q04,Q05,Q01 | 7개 실제 저장소 | review | — | R1 표 | 7 repos | 임계 만족 | review R1 |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| D01 | file granularity만 v9로 올리고 symbol(v6)은 그대로 둔다 | 평가와 크기 문제는 file granularity. symbol 경로(`evidence_record`)는 별도 | brief v1 — approved |
| D02 | 순환·unstable 근거를 열 이름이 선언된 행 배열 + 정수 file index로 바꾸고 `detail_edge_indices`는 행에서 뺀다(report.json file edge의 metadata.detail_edge_indices로 복원 가능) | 시뮬레이션: dict 레코드 유지 시 vendure 114MB, 행+index 시 약 60MB | user answer (행+index 승인) |
| D03 | evidence_spread는 detail edge index만 남기고 위치(path/line)는 details 파일에서 찾게 한다 | path 문자열을 남기면 vendure +50MB(시뮬레이션) | brief v1 — approved |
| D04 | report.json schema "6"→"7", details는 별도 파일 | 사용자 선택 "details도 분리" | user answer |
| D05 | details 파일은 HTML 출력 옆 `<stem>.details.json`, `--json` 또는 `--bottlenecks`일 때 생성; report.json과 bottlenecks.json에 상대 경로 `details_file` | `--bottlenecks`만 쓸 때도 v9 참조가 풀려야 한다 | brief v1 — approved |
| D06 | HTML 임베드에서 details 제거, `file_layers`는 제거 전 Python에서 계산 | app.js는 details를 검증에만 쓴다(app.js:902). vendure HTML 1.2GB 중 약 0.3GB | brief v1 — approved |
| D07 | handout은 `--bottlenecks` 시 자동, 경로는 bottlenecks 경로 기반, file granularity만 | 사용자 선택 "--bottlenecks 시 자동 생성" | user answer |
| D08 | handout 영문 Markdown, 저장소당 ≤200KB | 분석기 CLI 메시지가 영문. HTML은 한글이라 바꿀 수 있음 | brief v1 — approved |
| D09 | kind별 정렬: evidence_spread(directory_count↓, file_count↓, id), dependency_cycle·package_cycle(member_count↓, tier 순서 all→resolved→certain(그 밖 tier는 마지막), id), unstable_dependency(evidence_count↓, instability_delta↓, id), large_node(token_count↓, id), unresolved_boundary(unresolved_count↓, id), isolated_node(line_count↓, id), untested_hub(pagerank_rank↑, id), rule_violation(evidence_count↓, id), 그 밖 kind(id) | 지표 의미에 따른 기본값 | brief v1 — approved |
| D10 | delta는 v8 baseline도 계속 받는다 | 사용자가 저장해 둔 baseline 호환 | brief v1 — approved |
| D11 | 크기·시간 임계: vendure bottlenecks ≤80MB, 나머지 ≤20MB(v1 10MB, ghostfolio 실측 14.2MB로 변경), json.load RSS ≤1000MB, 분석 ≤150s | 시뮬레이션(vendure 약 60MB) + 여유. 사용자 "~47MB 허용". ghostfolio 잔여는 unstable_dependency 6,282개 본체 4.4MB·package_cycle file_pairs 3.5MB·package_dependencies 2.7MB로 recall 데이터 | brief v1 — approved; v2 20MB user answer |
| D13 | handout 제목 아래 파일 수는 `snapshot.file_count`, edge 수는 `dependency_network.edge_count` | implementer 질의(F11 "파일 수/edge 수" 출처 미지정). 계약 세부 | v2 contract-only |
| D14 | F12 "근거 개수": evidence가 list면 길이, dict면 `edges` 또는 `uncertain_test_edges` 길이(둘 다 없거나 비면 1), 그 밖 1 | implementer 질의(reach kind 근거 개수 미정의). 계약 세부 | v2 contract-only |
| D15 | HTML 임베드 architecture는 `architecture_to_dict` 결과에서 `details`만 뺀 것이다(schema_version은 "6" 그대로, `details_file` 없음). 임베드 bottlenecks에는 `details_file`이 없다 | test-implementer challenge. 임베드는 내부 데이터라 현재 구현 동작으로 고정 | v3 contract-only |
| D16 | F12 package_cycle 대표 근거는 package id `from_id → to_id`와 relations다 | test-implementer challenge. 현재 구현 동작으로 고정 | v3 contract-only |
| D17 | F12 대표 근거는 evidence 순서의 앞 3개다 | test-implementer challenge | v3 contract-only |
| D18 | candidate가 0개인 kind는 `### <kind>` 절이 없다 | test-implementer challenge | v3 contract-only |
| D12 | evidence_spread의 ambiguous 레코드가 사라지므로 `candidate_groups`는 남은 dict 레코드(unresolved_boundary, reach)에서만 만들어진다 | 기존 `_intern_candidate_groups` 로직 유지 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F01-F06 | C01 | V01 | pytest |
| F07,F08 | C02,C09,C10,C11 | V02 | pytest |
| F09 | C13 | V06 | pytest |
| F10 | C06 | V03 | pytest |
| F11,F12 | C03,C04,C05,C07,C08 | V04 | pytest |
| F13 | C12 | V05 | pytest |
| F14 | C14 | V07 | pytest |
| F15 | C19 | V11 | pytest |
| E01-E03 | C15,C16,C17 | V08 | pytest |
| E04 | C18 | V09 | pytest |
| Q01-Q05 | — | V10 | review R1 |
| Q06 | C14 | V07 | pytest |
| Q07 | C03 | V04 | pytest |
| Q08 | C15-C17 | V08 | pytest |
| Q09 | C12 | V05 | pytest |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 3 |
| verifier invocations | 2 |
| open finding ids | none (advisory A-02 timing tests under -n auto, A-05 unknown tier, A-06 id-only fallback) |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V01 | 4 | tests/test_report_size_format.py test_V01_*, goldens tests/report_size_evidence/ (base 5ddd426) | accepted | verifier 2 pass | report_size_support decoders |
| V02 | 4 | test_report_size_format.py test_V02_* (R1–R5) | accepted | verifier 2 pass | — |
| V03 | 4 | test_report_size_format.py test_V03_* | accepted | verifier 2 pass | — |
| V04 | 4 | tests/test_report_size_handout.py test_V04_* (batch 1 strengthened C05/C07/C08, D16–D18) | accepted | verifier 2 pass | — |
| V05 | 4 | test_report_size_format.py test_V05_* | accepted | verifier 2 pass | — |
| V06 | 4 | tests/test_report_size_html.py test_V06_* + unified_support.document() as_v9 browser suite (batch 1 D15) | accepted | verifier 2 pass | unified_support |
| V07 | 4 | tests/test_report_size_baseline.py test_V07_*, test_delta_cli.py | accepted | verifier 2 pass | delta_support.ref_delta |
| V08 | 4 | test_report_size_baseline.py test_V08_* (7 items) | accepted | verifier 2 pass | — |
| V09 | 4 | test_report_size_format.py test_V09_* (details, handout dir) | accepted | verifier 2 pass | — |
| V10 | 4 | review R1 scratchpad size-after/summary.md | accepted | verifier 2 pass; Q01–Q05 통과(v2 임계) | — |
| V11 | 4 | tests/test_report_size_standalone.py test_V11_* | accepted | verifier 2 pass; 브라우저 강조 대신 임베드 데이터 디코드 확인 | — |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 0 | base_commit 크기 재측정: CTFd bottlenecks 36MB/report 32MB/html 63MB/RSS 1.6GB, mealie 53/357/316MB/4.9GB, vendure 684/690/1247MB/9.1GB(136s) | handoff 기록과 일치 | scratchpad size-baseline, simulate2.py: 행+index 변환 시 CTFd 3.8MB·mealie 8.3MB·vendure 114MB(spread에 path 포함), spread index만이면 vendure 약 64MB | 설계 근거 |
| 0b | base_commit Test command: 6 failed / 3285 passed(75s). 재실행 시 `tests/test_file_analysis_cli.py::test_V01_direct_builder_defaults_characterization` 4개(fastapi, android, sqlalchemy, nestjs)는 매번 실패, `tests/test_report_modal.py::test_V04_graph_tab_active_modal_selects_and_centres_node[connection]`은 단독 재실행에서 통과(flaky) | verified: 이번 run 변경 이전부터 존재. builder golden 불일치는 이번 범위 밖 | 통과 판정 = 이 사전 실패 외 새 실패 없음 | 기준선 |
| 1 | implement+test 후 Test command: 8 failed / 3397 passed. 사전 실패 외 추가: `test_analysis_coverage_reporting.py::test_V05_characterization_and_V04_cli_stages`, `test_structure_integration.py::test_V11_chain_of_20000_files_time`, `test_report_modal.py::...[card]` | V05: base worktree에서 PYTHONPATH=. 로 같은 단언(symbol characterization) 실패 — verified 사전 실패. V11 timing·modal card: 단독 재실행 통과 — hypothesis: -n auto 부하 | 사전 실패 목록에 V05 추가, timing·modal은 flaky로 기록 | 기준선 갱신 |
| 2 | correction batch 1 후 Test command: 7 failed / 3408 passed(70s). 사전 실패 5개(V01×4, V05 coverage) + modal[connection] flaky + `test_structure_integration.py::test_V11_chain_of_20000_files_time` 5.26s>5.0s | V11 chain: `analyze_structure`만 측정, analysis/ 와 해당 테스트 파일 변경 없음, 단독 0.57s — verified 이번 변경 무관, hypothesis 테스트 수 증가(3285→3408)로 -n auto 부하 증가 | advisory A01로 기록(이 timing 테스트를 benchmark marker로 옮길지는 사용자 결정) | 비차단 |
| 3 | verifier 1(retry): 차단 F-01 V05 PYTHONHASHSEED 고정으로 해시 순서 비결정성 은폐, F-02 V04 D09 2차 키 미관찰, F-03 V04 metrics·cut_candidates 값 미단언, F-04 SC-1 D09 tier 순서 생략, F-05 V11 단독 페이지 렌더링·강조 미관찰. advisory A-01(E01/E02 추가 분할), A-02(timing), A-03(vendure handout 육안 확인 기록), A-04(Packages 순서·기준 필드 미관찰) | 모두 evidence gap(F-04는 spec 생략) | F-04: TIERS=(certain,resolved,all) 근거로 D09 tier 순서 고정(v4). A-04는 F11 "instability 상위 10"의 evidence gap이라 차단으로 승격. batch 2를 test-implementer에 전달 | 진행 |
| 4 | hand mutation H01~H11(scratchpad hand_mutations.py, 변경 테스트 8개 파일): H02~H11 killed(의도한 단언: V01 EP2/EP4, delta_integration C27, V08 index=len, delta_integration V12, V04 C04, V04 C03, V03 upper-JSON, V02 R3, V06 S2, V11 C19). H01(spread index sorted/unique 제거) survived | H01: incoming 목록이 detail edge index 오름차순으로 쌓이고 한 edge는 target 파일당 한 번만 들어가므로 관찰 가능한 출력이 같다 — equivalent(verified by code reading, core.py `_file_candidates`) | 동등 mutant로 기록 | 10/11 killed, 1 equivalent |
| 5 | batch 2(test): F-01 V05 PYTHONHASHSEED 0/1/31337/0 바이트 비교, F-02 D09 2차 키 tie 테스트, F-03 metric 값·structure·cut 값·rankings 순서, A-04 packages instability 선택, F-05 단독 페이지 playwright(v9 package_cycle 클릭 시 file_ids로 푼 파일 modal, v8 golden 무오류), A-01 V08 5개 추가. Test command 7 failed / 3435 passed: 사전 5 + modal flaky + `test_external_rules_integration.py::test_V14_C29_synthetic_time_and_correctness`(5.75s-0.72s>5.0) | V14_C29·V11 chain: 단독 3회 통과, base worktree 단독 4.58s/0.53s vs 현재 4.49s/0.54s — verified 부하 flaky, 회귀 아님 | A-02에 V14_C29 추가 | 비차단 |
| 6 | confirming mutation C01~C07(confirm_mutations.py): C01 spread 2차 키 제거·C02 cycle tier 제거·C03 unstable 2차 키 제거 → 각 V04 D09 테스트 실패; C04 metric 값 상수 → V04 F12 9개 실패; C05 packages 입력 순서 → V04 F11 packages 실패; C06 kind 반복을 set 순서로 → V05 hash-seed 테스트 + V04 C03 실패; C07 app.js file_ids 디코드 제거 → V06 S3 등 3개 실패 | — | F-01, F-02, F-03, A-04, F-05 확인 | 7/7 killed |
| 7 | A-03 vendure handout 육안 확인: 727줄 69.6KB, F11 절 순서·항목(metrics, structure, cut 5, evidence 3, more 줄) 확인. 상위 순환·spread가 docs/scripts READS로 채워짐(범위 밖 별도 작업과 일치) | — | — | Q07 review 완료 |
| 8 | mutation tool(mutate.py seed 20261022, cap 30, pool 202, 변경 테스트 7개 파일): 26 killed, 4 survived(13% < 40%). triager: M05 handout.py:90 `value or 0`→`or 1` declared(V04 F11), M10 handout.py:59 and→or declared(V04 F12), M19 core.py:182 `is not None`→`is None` declared(V01 F06), M12 handout.py:32 sort_keys True→False insufficient context | M12: `_value`에 dict가 들어가는 경로는 fallback 설명뿐이고 그 dict는 생성 코드가 고정 순서로 만든다. 출력은 결정적이고 spec은 dict 내부 key 순서를 고정하지 않는다 — main 판정 equivalent. M19: 전체 Test command로 재실행 시 base 바이트 비교 테스트 5개(architecture_rules_integration V07, delta_integration C27, external_rules_integration V11, reach_candidates V7_R9_C14, structure_integration V08) 실패 — killed(mutation 명령의 테스트 범위가 좁았음) | M05, M10을 batch 3(test)로 전달 | 진행 |
| 9 | batch 3(test): test_V04_G_M05_*(instability 0/1.0/None, 10개 cutoff) 3개, test_V04_G_M10_*(unresolved_boundary edge·node·to_id, large_node, isolated_node·untested_hub) 6개. M05·M10 재주입: 각각 G_M05 3개, G_M10 테스트로 killed | — | — | G-M05, G-M10 해소 |
| 10 | verifier 2(final): pass, 차단 없음. V01~V11 accepted. advisory A-02(timing 테스트를 benchmark marker로 옮길지 사용자 결정), A-05(D09 미지 tier 미검증), A-06(id-only fallback 미검증) | — | — | complete |
| 1b | R1 실측(새 코드): Q01 7개 모두 일치, vendure 77.2MB·RSS 684MB·97.5s, handout 최대 69.6KB, ghostfolio 14.2MB(v1 Q02 10MB 초과) | recall 데이터 잔여 | 사용자 재승인으로 Q02 20MB(v2) | Q02~Q05 통과 |

# Version Log
## v4
- D09 tier 순서를 all→resolved→certain(그 밖 마지막)으로 고정, package_cycle 동일(verifier SC-1). 구현 동작과 일치.
## v3
- F15/C19/V11 추가: 단독 렌더러 `report/bottlenecks/generate.py`가 v9를 거부하던 호환성 회귀(test-implementer challenge, generate.py:228). Implementation 경로에 추가.
- D15~D18: test-implementer 질의를 현재 구현 동작으로 고정(계약 세부). V09 coverage에 handout 경로 실패 추가.
## v2
- Q02/D11 임계 '나머지 ≤10MB' → '≤20MB'. R1 실측 ghostfolio 14.2MB(나머지 1.2~4.2MB, vendure 77.2MB). 잔여는 recall 데이터. 사용자 재승인.
- D13, D14 추가(계약 세부, implementer 질의).
## v1
- 최초 작성. 사용자 답: 둘 다(기존 축소 + handout), vendure ~47MB 허용, report.json details 분리, handout은 --bottlenecks 시 자동, docs/scripts READS는 별도.
