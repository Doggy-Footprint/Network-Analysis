---
version: 3
run_id: 0c3bcfad9643613b
status: limit
base_commit: bca6eee2921f159d8097510e46fc17e9e250c73b
max_verifier_invocations: 2
handoff: agent-docs/handoff/0c3bcfad9643613b-report-graph-modal-redesign.md
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 보고서 독자 | 보고서 용어를 그 자리에서 이해한다 | 용어에 hover하거나 focus하면 정의가 보인다. '할인'과 '가중'도 포함한다 |
| I2 | 보고서 독자 | 파일 단위 전체 연결을 그래프로 본다 | 블로그 참고 iframe처럼 vis-network 그래프를 보여주고, 그래프와 목록을 전환할 수 있다 |
| I3 | 보고서 독자 | 선택한 대상의 요약을 스크롤 없이 본다 | 선택하면 아래로 이동하지 않고 modal로 요약이 뜬다 |
| I4 | 보고서 독자 | 설명이 적고 읽기 쉬운 보고서 | 남기는 섹션은 KPI, 01 대표 대상, 02 그래프/목록, 부록뿐이다. 서술형 문단을 제거한다 |

# Scope
In scope: 통합 HTML 보고서(renderers/html의 template·JS·CSS, report/unified.py). 용어 사전과 tooltip, 파일 레이어 계산, vis-network 그래프, 그래프/목록 전환, modal, 섹션 정리, 기존 DOM에 의존하는 테스트 갱신.
Out of scope: 분석기와 지표 계산, JSON 스키마(architecture·bottlenecks), CLI 옵션, 심볼 granularity 그래프(심볼 보고서는 목록만 제공), report/bottlenecks/generate.py 마일스톤 보고서.

# Paths
Implementation: report/unified.py, renderers/html/templates/dashboard.html, renderers/html/static/app.js, renderers/html/static/styles.css, renderers/html/renderer.py, renderers/html/vendor/
Tests: tests/
Test command: .venv/bin/python -m pytest -q
Review evidence: tests/report_redesign_evidence/{browser.json,glossary.json,mutations.json,verifier-<n>.md}. tag-manager 보고서를 1440x900 Chromium에서 스크린샷으로 남기고 main이 육안 검토한다(review.md).

# Signatures
report.unified.render_unified_report(architecture, bottlenecks=None, *, title=None, framework_label="") -> str  (변경 없음)
report.unified.file_layers(architecture: Mapping) -> dict[str, dict]  # file node id -> {"layer": str, "source": "framework"|"package"}
window.ReportGraph: vis.Network 인스턴스 또는 null
window.ReportGlossary: {term: definition} 객체

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F01 | 용어 사전 G(아래 Assumptions A05의 목록)의 용어가 화면에 나오면 `data-term` 속성을 붙인다. hover와 keyboard focus 시 정의 tooltip(role=tooltip, aria-describedby로 연결)을 보여주고 mouseleave·blur·Escape 시 숨긴다. 대상은 KPI, 대표 카드, 목록 헤더, 그래프 툴바·범례, modal, 부록이다 | must | I1 |
| F02 | file granularity이고 architecture가 있으면 02 섹션 기본 탭은 '그래프'다. 노드는 kind=file인 architecture 노드이고, 현재 코드 분류 필터(기본 운영 코드)를 따른다. 엣지는 보이는 노드 사이의 (from,to) 쌍마다 하나로 합치고, 툴팁에 relation별 개수를 보여준다. self loop는 제외한다 | must | I2 |
| F03 | 노드 색은 file_layers의 layer로 정한다. 같은 layer는 같은 색이고, 범례에 layer 이름과 노드 수를 보여준다 | must | I2 |
| F04 | file_layers 규칙: 파일에 속한 detail 노드(details.node_files) 중 프레임워크 kind가 있으면 우선순위가 가장 높은 역할을 쓴다(A03). 없으면 패키지 경로를 쓴다: 언어 소스 루트(A04)를 제거하고, 운영 파일 경로 전체의 최장 공통 디렉터리 prefix를 제거한 뒤 남은 첫 디렉터리를 쓴다. 남은 디렉터리가 없으면 '(root)'다 | must | I2 |
| F05 | 툴바의 '크기 기준' select로 노드 크기 지표를 고른다. 선택지는 핵심 6개 지표와 token_cost이고 기본값은 pagerank다. 크기는 해당 지표 값의 sqrt를 표시 노드 안에서 [10,50] px로 선형 정규화한다. 값이 없거나 모두 같으면 10이다 | must | I2 |
| F06 | 툴바 검색(파일 경로 부분 일치, datalist 제공)으로 일치 노드에 focus·select한다. 결과가 없으면 툴바 상태 문구에 '일치하는 파일 없음'을 표시한다. '화면 리셋'은 fit하고 선택을 해제한다 | must | I2 |
| F07 | 후보가 있는 노드는 테두리를 강조한다(후보 종류와 관계없이 동일 스타일). 범례에 '후보' 표식을 둔다 | should | I2 |
| F08 | '목록' 탭은 기존 검토 목록(검색, 정렬 지표, 후보 종류, 표시 범위, 50개 페이지)을 유지한다. 행에서 서술 문단은 빼고 대상·후보 요약·지표 값만 보여준다. 탭 상태와 필터는 탭을 전환해도 유지된다 | must | I2 |
| F09 | 그래프 노드 클릭, 목록 행 클릭, 대표 카드 클릭, modal 안의 연결 클릭은 모두 같은 modal을 연다. 페이지 스크롤 위치는 바뀌지 않는다. 그래프 탭이 활성 상태면 노드에도 focus한다 | must | I3 |
| F10 | modal 내용: 제목(짧은 라벨, 전체 경로, layer 배지), 핵심 6지표와 줄 수·토큰 수, 후보 요약(종류명 + 핵심 수치 한 줄씩, 없으면 '후보 없음'), 들어오는/나가는 직접 연결 각각 유효 가중치 상위 10개와 총 개수. 상세 근거(선언, 근거 위치, 모호 후보 대안)는 표시하지 않는다 | must | I3 |
| F11 | modal은 role=dialog, aria-modal=true이고 닫기 버튼·Escape·배경 클릭으로 닫힌다. 열릴 때 닫기 버튼에 focus하고, 닫히면 이전 focus를 복원한다. focus trap을 둔다 | must | I3 |
| F12 | 페이지 구성은 masthead, KPI pill 줄, 01 지표별 대표 대상, 02 그래프/목록, 부록(details: 설정값 표와 '읽는 방법' 짧은 목록)이다. 제거 대상: lead/설명 문단, 파일별 분석 범위 표(coverage-details), 03 대상 상세 섹션, 각 섹션의 muted 설명 문단 | must | I4 |
| F13 | KPI pill: 파일 수, 연결 수, 후보 수(종류별), 분석 범위(완료/부분/실패 파일 수). 분석 범위 정보가 없으면 해당 pill은 '분석 범위 정보 없음'이다 | must | I4 |
| F14 | vis-network는 `https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js` 한 개만 외부에서 로드한다. cytoscape vendor 파일과 내장 코드는 제거한다 | must | I2, 사용자 결정 |
| F15 | vis-network 로드에 실패하거나 symbol granularity이거나 architecture가 없으면 그래프 탭을 비활성화하고 목록 탭을 기본으로 연다. 그래프 영역에는 사유 한 줄을 표시한다 | must | I2 |
| F16 | 그래프는 physics로 안정화한 뒤 physics를 끈다(stabilization iterations ≤ 300) | should | I2 |

# Errors
vis-network 스크립트 로드 실패(오프라인, CDN 차단) — 그래프 탭 disabled, 그래프 영역 문구 '그래프 라이브러리를 불러오지 못했습니다. 목록을 사용하세요.' — 목록·modal·KPI·대표 카드는 정상 동작하고 pageerror는 0건이다.
보고서 입력 검증 실패(기존 ReportInputError·BottleneckInputError) — 기존과 같은 예외 — HTML을 생성하지 않는다.
보고서 데이터 구조 오류(런타임) — 기존 #report-status 오류 문구 — 다른 섹션은 렌더하지 않는다.
details.node_files가 없거나 파일 매핑이 없음 — 예외 없이 해당 파일은 패키지 경로 규칙을 쓴다.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C01 | normal | Android fixture: composable과 viewmodel이 함께 있는 파일, composable만 있는 파일, 역할 없는 파일 | 각 layer가 viewmodel, composable, 패키지 첫 디렉터리 |
| C02 | normal | FastAPI·SQLAlchemy·NestJS 각 fixture | A03 우선순위대로 layer 결정 |
| C03 | boundary | 공통 prefix를 빼면 디렉터리가 없는 파일, 소스 루트 바로 아래 파일, 운영 파일이 1개 | '(root)' |
| C04 | normal | 운영 6파일과 테스트 2파일, 기본 필터 | 노드 6개. 필터를 '전체'로 바꾸면 8개 |
| C05 | normal | 같은 (from,to)에 CALLS 2개와 IMPORTS 1개, self loop 1개 | 엣지 1개, 툴팁 'CALLS 2 · IMPORTS 1', self loop 없음 |
| C06 | boundary | 크기 지표 값이 모두 같음, 하나만 존재, 0과 최댓값 | 모두 10 / 해당 노드 10 / 0→10, 최대→50 |
| C07 | normal | 검색 'Repo' 일치, 일치 없음 | 노드 select와 focus / '일치하는 파일 없음' |
| C08 | normal | 그래프 노드 클릭, 목록 행 클릭, 대표 카드 클릭, modal 내 연결 클릭 | 같은 modal 구조, window.scrollY 변화 0 |
| C09 | normal | 연결 15/15인 노드, 후보 2종인 노드, 후보 없는 노드 | 각 목록 10개 + 총 15, 후보 두 줄, '후보 없음' |
| C10 | normal | Escape, 닫기, 배경 클릭, Tab 순환 | 닫히고 focus 복원 / focus가 modal 안에 머문다 |
| C11 | normal | 용어 사전 G의 각 용어 hover와 focus | tooltip 텍스트가 사전 정의와 일치하고, 이탈 시 숨겨진다 |
| C12 | error | CDN 요청 abort | 그래프 탭 disabled, 목록 기본, 안내 문구, pageerror 0 |
| C13 | edge | symbol granularity 보고서, architecture-only, bottlenecks-only | 그래프 탭 disabled + 사유 / KPI 일부 '—' / 목록 동작 |
| C14 | normal | 렌더된 DOM | 제거 대상 id(coverage-details, node-detail)와 lead 문단이 없고, 섹션 순서는 KPI → 01 → 02 → 부록 |
| C15 | edge | 경로·라벨에 `<script>`, `"`, `&` 포함 | 그래프 라벨, tooltip, modal에 literal 텍스트로 나오고 실행되지 않는다 |
| C16 | normal | 탭 전환 왕복 | 필터, 검색어, 정렬, 페이지가 유지된다 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | F01–F16 |
| Performance efficiency | yes | tag-manager 규모(운영 ~250노드, ~3.8k 엣지)에서 그래프 표시 |
| Compatibility | yes | 기존 JSON 입력과 symbol 보고서가 계속 렌더되어야 한다 |
| Interaction capability | yes | tooltip, modal의 keyboard 접근성 |
| Reliability | yes | CDN 실패 시 저하 동작 |
| Security | yes | 저장소 경로·이름이 HTML에 들어간다(XSS) |
| Maintainability | no | 별도 측정 목표 없음. 기존 테스트 구조를 따른다 |
| Flexibility | no | 범위에 이식성 요구 없음 |
| Safety | no | 물리적 위해 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | Performance / time behaviour | tag-manager HTML, Chromium 1440x900, CDN은 로컬 파일로 route | navigation 시작부터 network 'stabilizationIterationsDone' 또는 그래프 ready 표식까지, ms, 5회 중앙값 | ≤ 5000 ms | browser.json | main 제안 |
| Q02 | Performance / time behaviour | 같은 조건, modal 열기 | 클릭부터 dialog visible까지, ms, 5회 중앙값 | ≤ 300 ms | browser.json | main 제안 |
| Q03 | Compatibility / interoperability | 기존 fixture의 architecture 5/6과 bottlenecks 4/5, symbol 보고서 | 렌더 성공과 pageerror 수 | 실패 0, pageerror 0 | pytest | 기존 계약 |
| Q04 | Interaction / accessibility | modal, tooltip, 탭 | keyboard만으로 C10, C11, 탭 전환 수행 | 모든 항목 성공 | pytest(browser) | main 제안 |
| Q05 | Reliability / fault tolerance | CDN abort | C12 | pageerror 0, 목록 동작 | pytest | 사용자 결정 |
| Q06 | Security / integrity | hostile 경로·라벨 | C15. 실행 여부(window 플래그), DOM의 literal 텍스트 | 실행 0 | pytest | 기존 계약 |
| Q07 | Compatibility / co-existence | 외부 요청 | Playwright request 로그 | 허용 URL은 F14 하나뿐이고 다른 외부 요청은 0 | pytest | 사용자 결정(기존 0건 요구 폐기) |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V01 | F04,C01,C02,C03 | file_layers() | unit, 모든 항목 | decision table | Android, FastAPI, SQLAlchemy, NestJS 각각 {역할 2개 이상, 역할 1개, 역할 없음} + C03 세 경우 + node_files 없음 | 100% | 독립 기대 layer와 source 일치 | pytest |
| V02 | F02,F03,F05,F07,C04,C05,C06 | 렌더된 그래프 데이터(ReportGraph.body.data) | e2e, 나열 항목 | equivalence partitioning + boundary value (2-value) | 필터 기본/전체, 엣지 병합/self loop, 크기 동일/단일/0·최대, 후보 테두리 유무, 범례 수 | 100% | 노드·엣지 수, 색 일관성, 크기 px, 툴팁 문자열 | pytest |
| V03 | F06,F08,F16,C07,C16 | 툴바와 목록 탭 | e2e | scenario | 검색 일치/불일치/리셋, 탭 왕복 상태 유지, 목록 필터 4종 | 100% | 선택 노드, 상태 문구, 필터 값 | pytest |
| V04 | F09,F10,F11,C08,C09,C10,Q02,Q04 | modal | e2e | state transition | 4개 열기 경로 × {닫기, Escape, 배경}, 연결 클릭으로 전환, Tab 순환, focus 복원 | 모든 전이 100% | dialog 속성, 내용, scrollY 0 변화, focus 위치 | pytest + browser.json |
| V05 | F01,C11,Q04 | tooltip | e2e | equivalence partitioning | 사전 G 각 용어 × {hover, focus} × 위치 부류(KPI, 카드, 목록, 그래프, modal, 부록 중 실제 등장 위치) | 100% | 정의 텍스트 일치, aria-describedby, 이탈 시 숨김 | pytest |
| V06 | F12,F13,C13,C14 | 페이지 구조 | e2e | equivalence partitioning | 결합/architecture-only/bottlenecks-only/symbol/coverage 없음 | 100% | 섹션 순서, 제거 id 부재, KPI 값 | pytest |
| V07 | F14,F15,C12,Q05,Q07 | 네트워크 경계 | e2e | scenario | CDN 로컬 route 성공, abort, request 로그 | 100% | 탭 상태, 문구, 외부 요청 목록 | pytest |
| V08 | C15,Q06 | XSS | e2e | error guessing | 그래프 라벨, 엣지 툴팁, tooltip, modal, 목록, 범례(layer 이름) | none — experience-based | 실행 플래그 false, literal 텍스트 | pytest |
| V09 | Q01,Q02 | tag-manager 성능 | e2e, 실제 tag-manager JSON | scenario | Q01, Q02 각 5회 | 100% | 중앙값 ≤ 임계값 | browser.json |
| V10 | Q03 | 기존 회귀 | 기존 테스트 중 DOM과 무관한 계약 | scenario | 기존 fixture 렌더 | 100% | 실패 0 | pytest |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
| --- | --- | --- | --- |
| A01 | vis-network CDN 로드. 기존 '외부 요청 0건' 요구 폐기 | 사용자 선택 | 사용자 결정(2026-10-10) |
| A02 | 색 기준: 프레임워크 역할 우선, 없으면 패키지 경로 | 사용자 선택 | 사용자 결정 |
| A03 | 역할 우선순위(왼쪽이 높음). Android: viewmodel > activity_fragment > room_database > room_dao > room_entity > room_migration > dagger_component > di_module > di_binding > retrofit_api > composable. FastAPI: app > router > endpoint > dependency > middleware > schema. SQLAlchemy: alembic_migration > sqlalchemy_model. NestJS: application > module > controller > endpoint > provider. 표시 이름은 kind 문자열 그대로 쓴다 | kind 목록은 framework_analyzers의 group/category 값에서 수집했다. 우선순위는 main이 제안했다 | 사용자 승인(2026-10-10) |
| A04 | 언어 소스 루트: src/main/java, src/main/kotlin, src/test/java, src/test/kotlin, src/androidTest/java, src/androidTest/kotlin, src. 경로에서 처음 일치하는 루트까지 제거한다 | main 제안 | 사용자 승인(2026-10-10) |
| A05 | 용어 사전 G(정의는 app.js의 한 객체로 관리): 기존 지표 15개의 라벨(정의 = 기존 설명 문구 + 단위), 후보 종류 3개, 분석 상태 6개(완료·부분 분석·실패·건너뜀·대상 밖=분석기가 다루지 않는 파일·제외=수집 정책상 제외), 코드 분류 6개, 그리고 '할인'=생성·외부 코드나 불확실한 연결의 기여를 설정 비율만큼 줄여 반영하는 것, '가중'=연결마다 확실도·해석 방식에 따른 가중치(설정값 표)를 곱해 합산한 값, '배분 몫'=모호한 참조를 후보 수로 나눈 몫, '가중 기여도'=가중치×배분 몫, 'hop'=연결을 따라 이동한 단계 수, 'PageRank', 'Hub', 'Authority', 'Betweenness', 'Fan-in', 'Fan-out', 'layer' | 정의 문구는 구현 시 이 의미를 지켜 한 문장으로 쓴다 | 사용자 승인(2026-10-10) |
| A06 | modal에 상세 근거(선언, 근거 위치, 모호 후보 대안)를 넣지 않는다. 기존 상세 근거 화면에 의존하던 브라우저 테스트(file_analysis, ambiguous_candidates, analysis_coverage browser)는 새 구조에 맞게 바꾸거나 삭제한다. JSON 수준 계약 테스트는 유지한다 | 사용자가 modal 내용에서 '상세 근거 펼치기'를 고르지 않았다 | 사용자 결정 |
| A07 | symbol granularity 보고서는 그래프 없이 목록만 제공한다 | 사용자 요청은 파일 단위 그래프다 | 사용자 승인(2026-10-10) |
| A08 | 테스트에서는 CDN URL을 page.route로 로컬 vis-network 사본(tests/ 아래 fixture)에 연결한다 | 네트워크 없는 CI | 사용자 승인(2026-10-10) |
| A09 | Q01/Q02 임계값 5000ms/300ms | main 제안 | 사용자 승인(2026-10-10) |

| A10 | (v2) 패키지 fallback: 공통 prefix는 A04 소스 루트가 제거된 production 파일끼리만 계산한다. 소스 루트가 없는 파일은 저장소 경로 첫 디렉터리, 없으면 '(root)'. '운영 파일'=categories의 production | v1 규칙으로 tag-manager 232/296 파일이 'com'이 됨(main 실측) | 사용자 승인(2026-10-11) |
| A11 | (v2) 유효 가중치 = min(confidence 가중치, resolution 가중치) × 배분 몫(analysis/edge_weights.py 기준). modal 연결은 이웃 파일별 합의 상위 10, 총 개수=서로 다른 이웃 파일 수 | test-implementer challenge | 사용자 승인(2026-10-11) |
| A12 | (v2) 후보 핵심 수치: 미확정 참조=건수, 근거 분산=파일 수, 큰 노드=줄 수. KPI 라벨: 파일/연결/후보/분석 범위 | challenge | 사용자 승인(2026-10-11) |
| A13 | (v2) 그래프 비활성 사유 우선순위: architecture 없음('아키텍처 데이터가 없어 그래프를 그릴 수 없습니다.') > symbol('파일 단위 보고서에서만 그래프를 제공합니다.') > 라이브러리 실패(Errors 문구) | challenge | 사용자 승인(2026-10-11) |
| A14 | (v2) Escape 한 번에 tooltip과 modal을 함께 닫는다. 소스 루트는 목록 순서로 첫 일치. 언어 core provenance 노드(module 등)는 프레임워크 역할이 아니다. modal 내 연결 이동 후 닫으면 최초로 modal을 연 요소로 focus 복원 | challenge | 사용자 승인(2026-10-11) |
| A15 | (v3) file_layers의 production 판정 = language_analyzers.core.flags.path_flags에 test/generated/vendored가 없는 파일(보고서 categories와 같은 규칙) | verifier S01 | 사용자 승인(2026-10-11) |
| A16 | (v3) 용어 정의 의미 검토는 review 절차: main이 tests/report_redesign_evidence/glossary.json을 A05 의미 체크리스트로 검토해 review.md에 기록 | verifier S02 | 사용자 승인(2026-10-11) |
| A17 | (v3) bottlenecks-only KPI: 파일=snapshot.file_count 없으면 '—', 연결=dependency_network.edge_count 없으면 '—', 후보·분석 범위는 동일 규칙 | verifier E06b | 사용자 승인(2026-10-11) |
| A18 | (v3) Errors의 입력 검증 실패·데이터 구조 오류 행을 V10에 매핑 | verifier S03 | 사용자 승인(2026-10-11) |
# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F01 | C11 | V05 | pytest |
| F02,F03,F05,F07 | C04,C05,C06 | V02 | pytest |
| F04 | C01,C02,C03 | V01 | pytest |
| F06,F08,F16 | C07,C16 | V03 | pytest |
| F09,F10,F11 | C08,C09,C10 | V04 | pytest |
| F12,F13 | C13,C14 | V06 | pytest |
| F14,F15 | C12 | V07 | pytest |
| Q01,Q02 | — | V09 | browser.json |
| Q03, Errors(입력 검증·데이터 구조) | C13 | V10 | pytest |
| Q04 | C10,C11 | V04,V05 | pytest |
| Q05,Q07 | C12 | V07 | pytest |
| Q06 | C15 | V08 | pytest |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 3 |
| verifier invocations | 2 |
| open finding ids | E07 |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V02,V07,V08,V09 | 2→3 | verifier-1 | accepted (v3 변경은 이들 기대를 바꾸지 않음) |
| V01,V03,V05,V06,V08,V10 | 3 | verifier-2 | accepted |
| V04 | 3 | verifier-2 E07 | open | — | — |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 1 | F04 v1 rule collapses tag-manager to 'com'; appendix '큰 노드' missing data-term | spec gap / impl defect | spec v2 A10–A14; impl D1–D6; tests updated | full suite pass |
| 2 | verifier-1 E01–E06,S01–S03 | evidence gaps / spec gaps | spec v3 A15–A18; tests strengthened; impl tab keyboard | suite 1293/1 fail (V08 hover flake) |
| 3 | V08 node hover flake | overlapping random layout → hover hits wrong target (verified: retry-only fix failed 3/10) | pin node positions + hover helper | 12/12 isolated; full suite 1294 passed |
| M | mutations M1 min→product, M2 prefix incl. unrooted, M3 focus last opener | strongest classes per verifier-1 | seed backup/restore | all detected by intended assertions; restored |

# Version Log
## v1
- Initial draft.
## v2
- F04 패키지 fallback 규칙 수정(A10), 미정의 항목 A11–A14 결정. 근거: tag-manager 실측과 implementer/test-implementer challenge. 사용자 재확인 완료.
## v3
- A15–A18 추가(verifier-1 spec challenge S01–S03, E06b). 사용자 승인.
