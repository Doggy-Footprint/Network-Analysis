---
version: 7
run_id: 5f7e8ab6e7b7fa1b
status: limit
base_commit: b8277a733d5da59b1f88cbf3513e122077baff00
max_verifier_invocations: 2
handoff: agent-docs/handoff/9c41d27e5ab03f86-report-readability.md
---

# User Intent
| id | stakeholder | intention | observable goal |
|---|---|---|---|
| UI-1 | 분석 결과를 받는 사용자 | 그래프 노드를 식별할 수 있어야 한다 | 그래프 라벨이 `app/src/...` 전체 경로가 아니라 공통 prefix가 제거된 짧은 이름이다 |
| UI-2 | 분석 결과를 받는 사용자 | 어디를 봐야 할지 알 수 있어야 한다 | 세 보고서 첫 화면에 데이터에서 결정적으로 계산한 "먼저 볼 곳" 목록과 한국어 설명이 있다 |
| UI-3 | 분석 결과를 받는 사용자 | 디자인과 그래프 가독성이 개선되어야 한다 | 한국어 UI, 지표 용어 사전, 크기·색 인코딩, M1의 라이브러리 기반 그래프 |

# Scope
In scope: Architecture 대시보드(`renderers/html`), Bottlenecks HTML(`report/bottlenecks`), M1 보고서(`report/m1`, `report/shared`)의 HTML/CSS/JS, 이를 위한 Python 렌더 코드와 짧은 라벨 유틸리티, M1용 vendored Cytoscape.js와 fcose.
Out of scope: 분석 알고리즘, JSON 스키마(architecture v5, bottlenecks.v2, agent-view v3)의 필드 변경, CLI 인자, 사전에 실패하던 NA_05/NA_06 수정.

# Paths
Implementation: report/shared/labels.py, report/shared/common.css, report/shared/base.html, report/shared/document.py, report/shared/index.md, report/m1/generate.py, report/m1/index.md, report/m1/templates/, report/m1/vendor/, report/bottlenecks/generate.py, report/bottlenecks/templates/, renderers/html/renderer.py, renderers/html/templates/dashboard.html, renderers/html/static/, architecture_assets/ (git 추적 제거)
Tests: tests/test_readability_labels.py, tests/test_readability_dashboard.py, tests/test_readability_bottlenecks.py, tests/test_readability_m1.py, 기존 tests/*.py 중 문구·구조 계약이 바뀌는 부분(test_dashboard_initial_load.py, test_report_m1.py, test_serialization_and_rendering.py, test_architecture_boundaries.py)
Test command: .venv/bin/python -m pytest -q --deselect tests/test_bottlenecks_contract.py::test_NA_05_outside_edge_raises_before_cli_writes --deselect tests/test_bottlenecks_contract.py::test_NA_06_outside_span_raises_before_cli_writes
Review evidence: RV-1 — 샘플 리포에 대해 세 HTML을 생성하고 Chrome으로 열어 스크린샷과 콘솔 로그를 `local-reports/review/`에 저장

# Signatures
report/shared/labels.py: `short_labels(paths: Iterable[str]) -> dict[str, str]`
report/m1/templates/label_model.js: UMD `ReportLabels.shortLabels(paths: string[]) -> {[path]: label}` (Node `require` 가능)
report/bottlenecks/generate.py: `prioritize_candidates(data: Mapping) -> list[dict]` — 각 원소 `{candidate: <원본 candidate 객체>, score, label}`; `focus_candidates(data: Mapping) -> list[dict]` — 각 원소 `{candidate, score, label, duplicate_count}`; 기존 `render_report(payload) -> str`, `generate(...)`, `main(...)` 시그니처 유지
renderers/html/static/app.js: 전역 함수 `buildOverview(data) -> {focus: Array<{id, label, full_label, metric, value}>, rankings: {[metric]: Array<{id, label, value}>}}`; 기존 전역 함수·변수 이름 유지
report/m1/templates/graph_model.js: `ReportGraphModel.build(data)`가 `nodes`(readable+query 전체), 각 `nodes[i].label`(짧은 라벨)·`full_label`(원래 라벨)·`default_visible`(bool), `capped`(bool), `limit`(300), `total`, `elements`(Cytoscape element 배열, 디렉터리 compound parent 포함) 반환. 순위 weight = readable: token_estimate + 연결 수, query: total_count + 연결 수 (연결 수 = from/to로 등장한 connection 수), 동점 id 오름차순; `ReportGraphModel.focus(data, n) -> Array<{id,label,reason,value}>` = [token_estimate 상위 n readable] ++ [truncated query의 total-visible 상위 n] ++ [연결 수 상위 n, readable+query] 순서로 이어 붙인 배열, 같은 목록 안의 항목은 같은 `reason` 문자열

# Functional Requirements
| id | requirement | priority | source |
|---|---|---|---|
| FR-1 | `short_labels`: 입력 경로들의 최장 공통 디렉터리 prefix(경로 구분자 단위)를 제거한 뒤 basename을 쓰고, basename이 겹치는 경로끼리는 모두 구분될 때까지 상위 디렉터리를 하나씩 붙인다. 경로가 1개이면 basename. 입력 순서와 무관하게 결정적. 빈 입력은 빈 dict. 중복 입력은 한 키 | must | UI-1 |
| FR-2 | JS `shortLabels`는 FR-1과 같은 입력에 같은 결과를 낸다 | must | UI-1 |
| FR-3 | 대시보드: `display_label`이 없고 `span.file_path` 또는 경로형 label을 가진 파일 노드의 vis `label`은 짧은 라벨이다. 심볼 노드 label은 `<파일 짧은 라벨>:<심볼명>` 형식이 아니라 심볼명을 유지하고 title에 파일 경로를 포함한다. 모든 노드의 `title`(툴팁)과 inspector 부제에 원래 전체 경로가 남는다. `display_label` 노드는 변경하지 않는다 | must | UI-1 |
| FR-4 | 대시보드: 첫 화면은 "개요" 탭이다. `buildOverview`는 `metadata.analysis.weighted_centrality_cost` 내림차순(동점은 id 오름차순) 상위 5개를 focus로, pagerank·fan_in·hop_2_token_cost별 상위 10개를 rankings로 반환한다. 지표가 없는 노드는 제외하고, 모두 없으면 focus는 빈 배열이며 화면에 "지표 없음" 안내를 보인다. 행 클릭 시 `focusNodeInGraph(id)` 호출 | must | UI-2 |
| FR-5 | 대시보드: UI 문구(탭, 버튼, legend, confidence 이름 설명, inspector 섹션명)는 한국어. 노드 색은 category별 결정적 팔레트, 크기는 weighted_centrality_cost 로그 스케일(없으면 기본 크기). 지표 용어 사전(token_estimate, effective_token_cost, pagerank, hub/authority, degree, betweenness, weighted_centrality_cost, fan_in/out, hop_2/3)이 페이지에 있다 | must | UI-3 |
| FR-6 | Bottlenecks: `prioritize_candidates` 점수 — output_truncation: omitted_count; multiple_results: total_count; read_limit: line_count - read_line_limit; evidence_spread: file_count; unresolved_boundary: unresolved_count(없으면 1). 정렬은 score 내림차순, 동점은 id 오름차순. label은 target의 짧은 라벨(노드 id/경로 target 간 short_labels) | must | UI-2 |
| FR-7 | Bottlenecks HTML 섹션(id): `#overview`(snapshot, 한계값, candidate·probe 수), `#focus`(prioritize 상위 10개, 각 항목에 kind 한국어 이름·score·이유 문장), `#kinds`(kind별 한국어 설명과 건수; connection_constraint는 "현재 생성되지 않음"으로 표기), `#candidates`(kind 필터·검색 표, evidence는 `path:line` 목록, raw JSON은 `<details>`), `#rankings`(dependency_network.rankings 지표별 상위 10 막대), `#appendix`(coverage, limitations, probes raw JSON 접힘), `#glossary`. candidate 0개면 `#focus`에 "발견된 후보 없음" | must | UI-2, UI-3 |
| FR-8 | M1: Cytoscape.js 3.30.2와 cytoscape-fcose 2.2.0(및 layout-base 2.0.1, cose-base 2.2.0)을 terser로 주석 제거·최소화한 파일을 `report/m1/vendor/`에 두고 라이선스 파일을 함께 둔다. 생성 HTML에 인라인된다 | must | UI-3 |
| FR-9 | M1 그래프: readable 노드는 디렉터리 compound 노드 아래, 짧은 라벨이 표시되고, 크기는 read_cost.token_estimate, query 노드는 다른 모양. 노드 클릭 시 이웃 강조·나머지 흐림, inspector에 사람이 읽는 표 + raw JSON `<details>`. 노드가 300개 초과면 token_estimate+연결 수 상위 300개만 그래프에 둔다("전체 보기" 없음, FR-15) | must | UI-1, UI-3 |
| FR-10 | M1: 요약 앞에 "먼저 볼 곳" 섹션(`#focus`) — token_estimate 상위 readable 5개, truncated query 중 omitted(total-visible) 상위 5개, 연결 수 상위 5개. 결정적 순서(값 내림차순, id 오름차순) | must | UI-2 |
| FR-11 | M1 용어 사전을 확장하고, 섹션 설명 문구를 "무엇을 보여주고 어떻게 읽는지" 수준으로 보강한다 | should | UI-3 |
| FR-12 | 결과 서술에 판단어(위험, 나쁨, 품질 등)를 쓰지 않고 측정 사실만 쓴다 | must | AGENTS.md |
| FR-14 | Bottlenecks `focus_candidates`: prioritize 결과를 (kind, target)으로 묶어 그룹마다 최고 점수 항목 1개(동점 id 오름차순)만 남기고 `duplicate_count`=그룹 크기. kind마다 상위 2개를 고른 뒤 score 내림차순, id 오름차순으로 정렬. `#focus`는 이 결과를 표시하고 duplicate_count>1이면 "같은 대상 N건"을 함께 표시 | must | UI-2, RV-1 |
| FR-15 | M1 graph.js: default_visible 노드와 그 compound parent, 양 끝이 보이는 edge만 Cytoscape에 추가하고 fcose를 그 집합에만 실행한다. "전체 보기" 버튼과 느림 안내는 제거한다. 검색·focus 링크로 그래프에 없는 노드를 찾으면 그 노드와 직접 이웃(연결 수 상위 20개까지)과 그 사이 edge, compound parent만 추가하고, 추가된 요소만 대상 노드 주변에 배치(전체 재배치 없음)한 뒤 그 노드로 이동한다 | must | 사용자 결정 v7 |
| FR-16 | 대시보드 그래프 탭의 모든 UI 문구(Controls & Filters, Layout, Node categories, Edge confidence, Node spacing, Legend, Fit View, Physics, 검색 placeholder, 버튼 title)가 한국어이고, legend의 category 색 견본이 실제 노드 색과 같다. 용어 사전 정의는 코드와 일치한다: effective_token_cost = token_cost × (vendored·/vendor/·/node_modules/ 0, generated·migration 0.1, 그 외 1) | must | RV-1 |
| FR-17 | M1 `focus`: token 목록은 read_unit_id 단위로 한 항목만(같은 read unit 중 id 오름차순 첫 readable), query 목록은 term 단위로 한 항목만(omitted 최대, 동점 id 오름차순) 남기고 각 항목에 `duplicate_count`를 둔다. 화면에서 duplicate_count>1이면 "같은 항목 N건" 표시 | must | 사용자 결정 v4 |
| FR-18 | M1 readable 노드 라벨: `label`이 있고 `file_path`와 다르면 `<파일 짧은 라벨>:<label>`, 아니면 파일 짧은 라벨. full_label은 `file_path` 또는 `file_path:label` | must | 사용자 결정 v4 |
| FR-19 | M1 그래프 컨테이너는 화면에서 높이 ≥ 480px이고, 레이아웃 뒤 보이는 요소 전체에 fit한다 | must | RV-1 |
| FR-20 | 대시보드 `buildOverview`의 focus·rankings 항목 `label`: 파일 노드 = category ∈ {file, module, package} 이거나 label == span.file_path 인 노드; 그 외 span.file_path가 있는 노드는 심볼 노드이며 `<파일 짧은 라벨>:<심볼 label>`, 파일 노드는 짧은 라벨. `full_label`은 `<file_path>:<label>` 또는 file_path. 그래프 vis label은 FR-3 그대로 | must | 사용자 결정 v5 |
| FR-21 | Bottlenecks 노드 id target(`<lang>:<module>#<qual>` 형식) 라벨: 모든 노드 id target의 module 부분을 '.'→'/'로 바꾼 경로에 short_labels를 적용한 결과 + `:<qual>`(qual 없으면 module 짧은 라벨만). id 형식이 아닌 target은 FR-6 그대로. `#focus`의 이유 문장에 target 원문을 반복하지 않고, 원문은 title 속성에 둔다. candidate 표 검색은 기존처럼 원문 target으로도 일치한다 | must | 사용자 결정 v5 |
| FR-22 | M1 그래프 LOD: 디렉터리 compound 라벨은 전체 fit 배율에서 읽을 수 있는 크기(화면상 ≥ 12px)로 표시. 노드 라벨은 weight 상위 20개는 항상, 나머지는 줌 ≥ 1 또는 hover 시 표시 | must | 사용자 결정 v5 |
| FR-13 | `architecture_assets/`를 git 추적에서 제거한다(.gitignore 대상인 stale 산출물) | should | plan |

# Errors
- Bottlenecks 스키마 위반 입력 — `ReportInputError` 발생(기존과 동일) — 출력 파일 미작성.
- M1 vendor 파일 누락 — `generate`가 템플릿 누락과 같은 방식의 오류(`ReportOutputError` 또는 기존 템플릿 누락 오류)를 낸다 — 출력 미작성.
- M1에서 DecompressionStream 미지원 — 기존과 동일하게 status `error`와 "DecompressionStream", "Chromium" 문구.
- 대시보드에 분석 지표 없음 — 예외 없이 개요에 "지표 없음" 안내(FR-4).

# Cases
| id | level | input / state | expected result |
|---|---|---|---|
| C-1 | normal | `["app/src/main/a/Foo.kt","app/src/main/b/Bar.kt"]` | `{…Foo.kt:"Foo.kt", …Bar.kt:"Bar.kt"}` |
| C-2 | edge | `["app/src/ui/Button.kt","app/src/data/Button.kt","app/src/X.kt"]` | `ui/Button.kt`, `data/Button.kt`, `X.kt` |
| C-3 | boundary | 경로 1개 `["a/b/c.py"]` / 빈 입력 / 중복 입력 | `c.py` / `{}` / 키 1개 |
| C-4 | edge | 3단계 충돌 `["x/a/m/f.py","y/a/m/f.py"]`, 입력 순서 뒤집기 | `x/a/m/f.py`, `y/a/m/f.py` (공통 prefix 없음, 구분되는 최소 접미사), 순서 반전해도 동일 |
| C-5 | normal | Python·JS 구현에 C-1~C-4 동일 입력 | 결과 동일 |
| C-6 | normal | 모듈 노드 label `app/src/pkg/mod.py` 포함 architecture 렌더 | vis label 짧음, title에 전체 경로 |
| C-7 | edge | `display_label`이 있는 Android 노드 | label 불변 |
| C-8 | normal | weighted_centrality_cost 있는 노드 7개 `buildOverview` | 상위 5개, 내림차순, 동점 id 오름차순 |
| C-9 | boundary | 지표 없는 architecture | focus `[]`, 예외 없음, "지표 없음" 문구 |
| C-10 | normal | 각 kind 1개 이상 bottlenecks.v2 payload | prioritize 점수·정렬 FR-6대로, HTML에 FR-7 섹션 id 전부와 kind 한국어 이름 |
| C-11 | boundary | candidates `[]` | "발견된 후보 없음", 예외 없음 |
| C-12 | error | `{"schema":"bottlenecks.v1"}` | ReportInputError |
| C-13 | normal | M1 `_payload()` 생성 | 오프라인 검사 통과(기존 `_assert_offline` 규칙 그대로), `cytoscape` 인라인, `#focus` 존재, 결정적 바이트 동일 |
| C-14 | boundary | readable 300개 / 301개 payload | 300개: `capped=false`, 모두 default_visible; 301개: `capped=true`, default_visible 300개, weight 최하위 1개 제외 |
| C-15 | error | vendor 파일 하나 제거 후 generate | 오류, 출력 미작성 |
| C-16 | edge | label·경로에 `<script>`/`"` 포함 | 세 HTML 모두 이스케이프되어 실행 불가 텍스트로만 표시 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
|---|---|---|
| Functional suitability | yes | FR 전부 |
| Performance efficiency | yes | M1 10MB 제한과 큰 그래프 표시 |
| Compatibility | yes | 기존 스키마·스크립트 id·전역 함수 계약과 오프라인 요구 |
| Interaction capability | yes | 이번 작업의 목적(가독성·안내) |
| Reliability | yes | 결정적 출력 |
| Security | yes | 리포 유래 문자열이 HTML에 들어감(XSS) |
| Maintainability | yes | vendor 버전 고정과 라이선스, index.md 갱신 |
| Flexibility | no | 새 플랫폼·환경 요구 없음 |
| Safety | no | 물리적·인명 위험 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
|---|---|---|---|---|---|---|
| QR-1 | Performance / capacity | M1 `_payload()` 생성 HTML | 바이트 수 | vendor 포함 ≤ 1.5 MB 증가, 기존 10MB 상한 유지 | automated | plan |
| QR-2 | Compatibility / co-existence | 기존 계약 테스트 | Test command 통과 수 | 기존 테스트 전부 통과(문구 변경으로 갱신된 것 제외, 갱신은 기록) | automated | plan |
| QR-3 | Compatibility / interoperability | M1 오프라인 | 기존 `_assert_offline` 규칙 | 위반 0 | automated | plan |
| QR-4 | Interaction / learnability | 세 보고서 | RV-1에서 첫 화면(스크롤 없이 1440×900)에 "먼저 볼 곳"이 보이는지, 그래프 라벨이 짧은지 | 3/3 | review | UI-2 |
| QR-5 | Reliability / faultlessness | M1·Bottlenecks·대시보드 renderer | 같은 입력 2회 생성 바이트 비교 | 동일 | automated | plan |
| QR-6 | Security / integrity | C-16 | 생성 HTML에 비이스케이프 `<script>` 주입 여부 | 0 | automated | plan |
| QR-7 | Maintainability / modifiability | vendor | 각 `<name>-<semver>.min.js`에 대응하는 `<name>-<semver>.LICENSE` 존재 | 4/4 | automated | plan |
| QR-8 | Interaction / user error protection | RV-1 콘솔 | 브라우저 콘솔 error 수 | 0 | review | plan |
| QR-9 | Performance / time behaviour | 이 리포(readable 1769, query 867, connection 12699)로 만든 M1을 Chrome 1440×900에서 열기, 그리고 그래프에 없는 노드를 검색 | 로드부터 JS 평가 가능까지 초; 검색 실행부터 JS 평가 가능까지 초 | 로드 ≤ 10초, 숨은 노드 검색 ≤ 3초 | review (RV-1) | 사용자 결정 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
|---|---|---|---|---|---|---|---|---|
| VO-1 | FR-1, C-1..C-4 | `short_labels` | unit, 전 Case | equivalence partitioning + boundary value (2-value) | {무충돌, 1단계 충돌, 다단계 충돌, 단일, 빈, 중복, 순서 반전} | 100% | Case 기대값과 일치 | automated |
| VO-2 | FR-2, C-5 | JS `shortLabels` via node | unit, VO-1과 같은 입력 | metamorphic (Python=JS) | VO-1 7 items | 100% | 결과 동일 | automated |
| VO-3 | FR-3, C-6, C-7, C-16 | `HTMLRenderer.render` 출력 `#architecture-data` | integration | decision table | {파일노드/display_label 있음, 파일노드/없음, 심볼노드, 특수문자 label} | 100% | label·title 규칙, 이스케이프 | automated |
| VO-4 | FR-4, C-8, C-9 | app.js `buildOverview` in node vm | unit | boundary value (2-value) | {7개, 5개, 0개 지표, 동점} | 100% | 순서·개수·빈 배열 | automated |
| VO-5 | FR-5 | 렌더된 대시보드+app.js 문자열 | integration | equivalence partitioning | {탭명 "개요", 용어 11개, confidence 한국어 설명 4종} | 100% | 문자열 존재 | automated |
| VO-6 | FR-6, C-10 | `prioritize_candidates` | unit | decision table | kind 5종 × {점수 계산, 동점 tie-break} | 100% | 점수·순서 | automated |
| VO-7 | FR-7, FR-12, C-10, C-11, C-12, C-16 | `render_report` HTML | integration | equivalence partitioning | {섹션 id 7개, 빈 candidate, v1 거부, bottlenecks-data 계약, 이스케이프, 금지어 부재} | 100% | 존재·예외·JSON 동일 | automated |
| VO-8 | FR-8, QR-1, QR-3, QR-7, C-13, C-15 | M1 generate | integration | equivalence partitioning | {인라인 확인, 오프라인, 크기, vendor 누락, 라이선스·버전} | 100% | 규칙 준수, 누락 시 오류·미작성 | automated |
| VO-9 | FR-9, FR-10, C-14 | graph_model.js `build`/`focus` via node | unit | boundary value (2-value) | {300개, 301개, compound parent, 짧은 라벨, focus 3목록 순서} | 100% | FR대로 | automated |
| VO-10 | QR-5 | 3개 renderer | integration | metamorphic (재생성 동일) | {M1, bottlenecks, dashboard} | 100% | 바이트 동일 | automated |
| VO-11 | FR-11, QR-4, QR-8 | 실제 브라우저 | end-to-end review | scenario | {대시보드, bottlenecks, M1} | 100% | 스크린샷·콘솔 0 error | RV-1 |
| VO-13 | FR-14 | `focus_candidates` | unit | decision table | {같은 (kind,target) 3건→1건·duplicate_count 3, kind당 3건 이상→2건, 동점 id, 서로 다른 kind 혼합 정렬, #focus에 "같은 대상 3건"} | 100% | FR-14대로 | automated |
| VO-14 | FR-15, QR-9 | graph.js in 브라우저 | end-to-end review | scenario | {기본 보기 로드 시간, 그래프에 없는 노드 검색 시 추가·이동 시간, "전체 보기" 버튼 부재} | 100% | 로드 ≤10초, 검색 ≤3초, 콘솔 error 0 | RV-1 |
| VO-15 | FR-16 | 렌더된 대시보드+app.js | integration | equivalence partitioning | {영어 문구 목록 부재: "Controls & Filters","LEGEND","Fit View","Physics: On","Node Spacing","Search routes"; effective_token_cost 정의에 0.1 포함; category 3종 이상 노드 입력 시 legend의 category별 색 견본 = 같은 category 노드의 vis color(node vm)} | 100% | 부재·포함 | automated |
| VO-16 | FR-17, FR-18 | graph_model.js build/focus via node | unit | decision table | {같은 read unit 3 readable→1건 dup 3, 같은 term 2 query→1건 dup 2(omitted 큰 쪽), 심볼 label→`f.py:Sym`, label==file_path→`f.py`} | 100% | FR대로 | automated |
| VO-17 | FR-19 | 브라우저 | end-to-end review | scenario | {그래프 영역 높이, 노드가 화면에 보임} | 100% | 높이≥480, 스크린샷에 노드 | RV-1 |
| VO-18 | FR-20 | buildOverview in node vm | unit | equivalence partitioning | {심볼 노드 `f.py:sym`, 파일 노드 짧은 라벨, 같은 basename 충돌 파일의 심볼} | 100% | FR대로 | automated |
| VO-19 | FR-21 | `focus_candidates`/`prioritize_candidates` label, render_report | unit+integration | equivalence partitioning | {`py:a.b.graph#C.m`+`py:x.y.other#f` → `graph:C.m`,`other:f`; qual 없는 `py:a.b.mod`→`mod`; 모듈 basename 충돌 `py:a.x.m#f`,`py:b.x.m#g` → `a/x/m:f`,`b/x/m:g`; 검색어 target 불변; #focus 이유 문장에 원문 id 부재·title에 존재} | 100% | FR대로 | automated |
| VO-20 | FR-22 | graph_model build 또는 스타일 결정 함수 + 브라우저 | unit + RV-1 | boundary value (2-value) | {weight 20위 always_label=true, 21위 false; fit 배율 스크린샷에서 디렉터리 이름 판독} | 100% | FR대로 | automated + RV-1 |
| VO-21 | FR-21 (검색) | Bottlenecks 렌더 HTML의 candidate 표 + 인라인 필터 스크립트 | integration (node로 렌더 HTML의 필터 스크립트를 최소 DOM stub에서 실행) | equivalence partitioning | {원문 id 전체 문자열로 검색 → 해당 행 표시·다른 행 숨김, 짧은 라벨로 검색 → 표시, 일치 없음 → 0행} | 100% | FR대로 | automated |
| VO-22 | FR-12 | M1 generate 출력, 대시보드 렌더 출력 | integration | equivalence partitioning | {M1 HTML(payload 제외)에 위험·나쁨·품질 부재, 대시보드 HTML+app.js에 부재} | 100% | 부재 | automated |
| VO-12 | FR-14 | Bottlenecks `focus_candidates`: prioritize 결과를 (kind, target)으로 묶어 그룹마다 최고 점수 항목 1개(동점 id 오름차순)만 남기고 `duplicate_count`=그룹 크기. kind마다 상위 2개를 고른 뒤 score 내림차순, id 오름차순으로 정렬. `#focus`는 이 결과를 표시하고 duplicate_count>1이면 "같은 대상 N건"을 함께 표시 | must | UI-2, RV-1 |
| FR-15 | M1 graph.js: 처음에는 default_visible 노드와 그 compound parent, 양 끝이 모두 보이는 edge만 Cytoscape에 추가하고 그 집합에만 fcose를 실행한다. "전체 보기"는 나머지를 추가하고 cose(animate:false)로 다시 배치하며, 노드 수가 많아 느릴 수 있다는 안내를 표시한다 | must | RV-1 |
| FR-16 | 대시보드 그래프 탭의 모든 UI 문구(Controls & Filters, Layout, Node categories, Edge confidence, Node spacing, Legend, Fit View, Physics, 검색 placeholder, 버튼 title)가 한국어이고, legend의 category 색 견본이 실제 노드 색과 같다. 용어 사전 정의는 코드와 일치한다: effective_token_cost = token_cost × (vendored·/vendor/·/node_modules/ 0, generated·migration 0.1, 그 외 1) | must | RV-1 |
| FR-13 | git | review | none — experience-based | architecture_assets 추적 여부 | none — experience-based | `git ls-files architecture_assets` 비어 있음 | review |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
|---|---|---|---|
| A-1 | 대시보드는 vis-network 유지 | 대시보드 JS 테스트가 vis stub 사용 | 계획 승인 |
| A-2 | M1 vendor는 terser로 주석 제거하여 기존 `_assert_offline`을 완화하지 않음 | 스캐너 결과 최소화 후 URL·`//`·네트워크 API 0건 | 계획의 "vendor 검사" 결정을 이 방식으로 확정 — 승인 필요 |
| A-3 | "viewport culling" 등 기존 M1 필수 문자열은 설명 문구에 유지 | Cytoscape도 viewport 밖을 그리지 않음 | 사용자 승인 (spec v1) |
| A-4 | Test command에서 기존 실패 NA_05/NA_06 제외 | base_commit에서 이미 실패 | 사용자 승인 (spec v1) |
| A-5 | 대시보드 외부 CDN(tailwind, vis, lucide) 유지 | 사용자가 외부 의존성 허용 | 사용자 허용 |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
|---|---|---|---|
| FR-1 | C-1..C-4 | VO-1 | automated |
| FR-2 | C-5 | VO-2 | automated |
| FR-3 | C-6, C-7, C-16 | VO-3 | automated |
| FR-4 | C-8, C-9 | VO-4 | automated |
| FR-5 | — | VO-5 | automated |
| FR-6 | C-10 | VO-6 | automated |
| FR-7, FR-12 | C-10..C-12, C-16 | VO-7, VO-22 | automated |
| FR-8 | C-13, C-15 | VO-8 | automated |
| FR-9, FR-10 | C-14 | VO-9 | automated |
| FR-11 | — | VO-11 | RV-1 |
| FR-14 | Bottlenecks `focus_candidates`: prioritize 결과를 (kind, target)으로 묶어 그룹마다 최고 점수 항목 1개(동점 id 오름차순)만 남기고 `duplicate_count`=그룹 크기. kind마다 상위 2개를 고른 뒤 score 내림차순, id 오름차순으로 정렬. `#focus`는 이 결과를 표시하고 duplicate_count>1이면 "같은 대상 N건"을 함께 표시 | must | UI-2, RV-1 |
| FR-15 | M1 graph.js: 처음에는 default_visible 노드와 그 compound parent, 양 끝이 모두 보이는 edge만 Cytoscape에 추가하고 그 집합에만 fcose를 실행한다. "전체 보기"는 나머지를 추가하고 cose(animate:false)로 다시 배치하며, 노드 수가 많아 느릴 수 있다는 안내를 표시한다 | must | RV-1 |
| FR-16 | 대시보드 그래프 탭의 모든 UI 문구(Controls & Filters, Layout, Node categories, Edge confidence, Node spacing, Legend, Fit View, Physics, 검색 placeholder, 버튼 title)가 한국어이고, legend의 category 색 견본이 실제 노드 색과 같다. 용어 사전 정의는 코드와 일치한다: effective_token_cost = token_cost × (vendored·/vendor/·/node_modules/ 0, generated·migration 0.1, 그 외 1) | must | RV-1 |
| FR-13 | — | VO-13 | FR-14 | `focus_candidates` | unit | decision table | {같은 (kind,target) 3건→1건·duplicate_count 3, kind당 3건 이상→2건, 동점 id, 서로 다른 kind 혼합 정렬, #focus에 "같은 대상 3건"} | 100% | FR-14대로 | automated |
| VO-14 | FR-15, QR-9 | graph.js in 브라우저 | end-to-end review | scenario | {기본 보기 로드 시간, 그래프에 없는 노드 검색 시 추가·이동 시간, "전체 보기" 버튼 부재} | 100% | 로드 ≤10초, 검색 ≤3초, 콘솔 error 0 | RV-1 |
| VO-15 | FR-16 | 렌더된 대시보드+app.js | integration | equivalence partitioning | {영어 문구 목록 부재: "Controls & Filters","LEGEND","Fit View","Physics: On","Node Spacing","Search routes"; effective_token_cost 정의에 0.1 포함; category 3종 이상 노드 입력 시 legend의 category별 색 견본 = 같은 category 노드의 vis color(node vm)} | 100% | 부재·포함 | automated |
| VO-12 | review |
| QR-1, QR-3, QR-7 | C-13 | VO-8 | automated |
| QR-2 | — | Test command | automated |
| QR-4, QR-8 | — | VO-11 | RV-1 |
| QR-5 | — | VO-10 | automated |
| QR-6 | C-16 | VO-3, VO-7 | automated |

# Workflow Control
| item | value |
|---|---|
| correction batches used | 6 |
| verifier invocations | 2 |
| open finding ids | SPEC-4, RV-ARTIFACT-1 |

Audit state:
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
|---|---|---|---|---|---|
| VO-1..VO-10, VO-12, VO-13, VO-16, VO-17, VO-19, VO-20(unit+RV) | 6 | verifier 1 audit, tests/test_readability_*.py | accepted (v6); VO-9/VO-20 re-opened by MUT-3 and re-evidenced at v7 | MUT-1 tie-break reverse → detected (VO-6); MUT-2 basename-only labels → detected (VO-1, VO-19); MUT-3 weight w/o connections → survived at v6, detected at v7 after new tests | FR-15 v7 rewrite touches graph.js only; graph_model.js build/focus unchanged, so VO-9/16/20 stay valid |
| VO-11 | 7 | RV-1.md v6 re-check | pending (verifier 2) | RV-EVIDENCE-1 addressed | — |
| VO-14 | 7 | RV-1.md v7 VO-14 | pending (verifier 2) | coverage items changed in v7 | FR-15 rewrite |
| VO-15, VO-18 | 7 | new legend-color test; VO-18 unchanged | pending (verifier 2) | SPEC-1 addressed | — |
| VO-21, VO-22 | 7 | new tests | pending (verifier 2) | SPEC-2, SPEC-3 addressed | — |

Execution ledger:
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
|---|---|---|---|---|
| 1 | first Test command 8 failed | ID-1 impl, TD-1..6 test over-specification | batch 1, spec v2 | 400 passed |
| 2 | RV-1: focus all `and`, M1 froze, EN copy | missing dedup, full-graph fcose, incomplete FR-5 | batch 2, spec v3 | fixed; TD-7 test scope |
| 3 | RV-1: M1 #cy height 0, focus repeats | CSS height, no dedup per read unit | batch 3, spec v4 | fixed |
| 4 | RV-1: ambiguous symbol labels, tiny M1 labels | label rules not specified | batch 4-5, spec v5-v6 (agents stopped once by user, redone) | fixed |
| 5 | verifier 1 retry: SPEC-1..3, RV-EVIDENCE-1..2 | missing obligations; show-all froze Chrome >2 min | spec v7 (show-all removed), new tests, RV-1 additions | 431 passed |
| 6 | MUT-3 survived | fixtures had 0 connections | new VO-9/VO-20 tests | detected; 434 passed |

# Version Log
## v1
- 초안. 계획(/Users/hwansu/.claude/plans/imperative-roaming-chipmunk.md)과 조사 결과에서 도출.
## v2
- 첫 Test command 실행에서 드러난 모호함을 명확히 함(사용자 관찰 동작 변경 없음): prioritize 원소의 `candidate`는 객체, M1 build 반환 필드와 300 cap weight, focus 반환 구성, vendor LICENSE 명명 규칙. HTML 속성 따옴표 종류는 계약이 아니며, `bottlenecks-data`만 기존 작은따옴표 계약을 유지한다.
## v3
- RV-1 첫 검토 결과로 추가: FR-14(focus 중복 제거·kind당 2개, 사용자 결정), FR-15/QR-9(M1 기본 300개만 레이아웃, 10초 이내, 사용자 결정), FR-16(대시보드 그래프 탭 한국어화·legend 색·effective_token_cost 정의 수정). 근거: Chrome에서 focus 10개가 모두 `and`, M1이 2636 노드에서 응답 없음, 그래프 탭 영어 잔존.
## v4
- RV-1 두 번째 검토: M1 그래프 컨테이너 높이 0(노드 312개 배치됐지만 보이지 않음), M1 focus가 같은 read unit·term 반복, 심볼 노드 라벨이 파일명만 표시. FR-17/18(사용자 결정: 중복 제거 + 심볼 라벨 보강), FR-19 추가.
## v5
- RV-1 세 번째 검토: 대시보드 개요의 심볼 이름이 모호함(resolve, main), Bottlenecks 노드 id 라벨이 길고 이유 문장에서 반복됨, M1 fit 배율에서 라벨을 읽을 수 없음. FR-20~22 추가(사용자 승인). M1 build 노드에 `always_label`(bool) 필드를 추가한다.
## v6
- FR-20 파일/심볼 판정 명확화: renderer가 파일 노드 label을 이미 줄이므로 category 기준을 추가(label==file_path 기준과 OR). FR-21: candidate 표 검색에서 원문 target 일치를 유지(기존 관찰 동작 보존, v5 구현에서 사라짐).
## v7
- verifier 1회차(retry): SPEC-1(legend 색 일치 VO 없음)→VO-15 coverage 추가, SPEC-2(FR-21 검색 VO 없음)→VO-21, SPEC-3(FR-12가 Bottlenecks에만 추적)→VO-22. RV-EVIDENCE-1은 RV-1.md 보강으로 해소 예정.
- RV-1: "전체 보기"가 Chrome에서 2분 이상 응답 없음 → 사용자 결정으로 제거, 숨은 노드는 검색 시 이웃만 추가(FR-15 재작성, QR-9·VO-14 변경). FR-9의 토글 문구 제거.
