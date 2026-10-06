# 파일 기본 분석 전환과 프로젝트 전반 리팩토링 인계

## Goal

> 이 프로젝트의 분석 대상은 보다시피 파일보다 세분화 했어. 그런데, 막상 그렇게 세분화하니 분석을 위한 시간이 너무 오래 걸리고, 가시성이 떨어져. 기본 설정은 파일 단위였고. 어떤 단위를 분석 대상으로 삼는 게 적절할지 검토해줘
>
> 코드 수정은 하지 말고 검토만 요청

> 구현 계획을 작성해줘.

> 이 구현은 프로젝트 전체에 대한 리팩토링이므로 다른 부분의 변경 계획도 handoff로 작성해줘.

목표는 파일 단위 기본 분석으로 구조적 병목 후보의 가시성을 높이고 실행 시간을 줄이는 것이다. 심볼·프레임워크 의미와 불확실한 관계는 연결 근거로 보존한다. 이 문서는 구현 계획과 연쇄 변경 범위를 인계하며, 구현 완료나 실행 승인을 의미하지 않는다.

## State

- 기준일: 2026-10-05.
- Branch: `fix/report-ui`.
- HEAD/base commit: `df87fb1203f407a6f35dadc13966b659301983df`.
- 문서 작성 직전 작업 트리: clean.
- 이번 변경: 이 문서와 `agent-docs/handoff/index.md`만 추가·수정.
- 구현·테스트 변경, 커밋, 전체 분석 재실행: 없음.
- 활성 spec: 없음. `agent-docs/specs/`에는 빈 `.running/` 디렉터리만 있다.
- 기존 handoff `ec9d04784407ee5b-v3-real-repository-validation.md`는 별도 작업이며 상태를 변경하지 않는다.

### 사용자가 명시적으로 선택한 사항

| ID | 결정 | 근거 |
| --- | --- | --- |
| D1 | 문제의 우선 대상은 분석 실행 시간 | 검토 중 사용자 답변 |
| D2 | 파일 기본·심볼 선택 모드 | 구현 계획 질문의 선택 답변 |
| D3 | 같은 HTML에서 클래스·함수 상세 그래프 제공; 상세 중심성 순위는 계산하지 않음 | 구현 계획 질문의 선택 답변 |
| D4 | Tag-Manager 전체 실행 목표 3분 이내 | 구현 계획 질문의 선택 답변 |
| D5 | 기본 JSON도 파일 단위; 심볼 모드에서는 기존 JSON 형식 유지 | 구현 계획 질문의 선택 답변 |
| D6 | 이번에는 기존 연결 대상 선택·동명 후보·신뢰도·해석 상태 보존 | 구현 계획 질문의 선택 답변 |
| D7 | 파일 쌍별 최대 유효 가중치 사용; 연결 건수는 근거로 보존 | 구현 계획 질문의 선택 답변 |

### 직전 제안 계획의 기준

다음은 대화에서 제시된 구현안이다. D1–D7과 달리 모든 세부 항목이 개별 승인된 것은 아니다. 구현 착수 시 workflow spec에 포함해 확정한다.

- CLI `--granularity file|symbol`, 기본값 `file`.
- 파일 모드: architecture schema `6`, `bottlenecks.v5`, `granularity: file`. 심볼 모드: 기존 schema `5`, `bottlenecks.v4`.
- 파일 그래프에서 지표 재계산. 파일 토큰 규모는 전체 텍스트를 한 번 계산하며 심볼 점수를 합산하지 않는다.
- 원본 심볼·연결과 파일 소유 매핑을 상세 데이터로 보존. 파일 내부 연결은 상세에만 남긴다.
- 큰 파일, 미확정 참조, 근거 분산 후보를 파일 기준으로 생성한다. 파일 모드에서는 `identifier_file_count`를 생략하고 심볼 모드에서는 유지한다.
- 상세 화면에서는 클래스·인터페이스·최상위 함수가 중심이다. 메서드·필드는 소유 클래스로 접고 그 외 참조는 파일 본문에 둔다. 외부 연결은 상대 파일로 묶고 원래 심볼을 근거에 남긴다.
- 초기 화면은 파일 순위이며 기존 상위 100개·50개 페이지 정책을 유지한다. 선택 심볼과 직접 이웃 최대 30개를 그리며 생략한 연결은 전체 목록에서 제공한다.
- 파일 소속 없는 실제 의존 대상은 토큰 규모 0의 경계 노드로 보존하고 파일 순위에서는 제외한다. 소스 없는 패키지 소속 정보는 탐색 메타데이터로 보존한다.
- 성능 합격 측정안은 동일 환경·동일 Tag-Manager 스냅샷의 별도 프로세스 3회 실행 중앙값 ≤180초다. 브라우저 기준은 기존 초기 화면 5초, 필터 300ms, 상세 그래프 1초를 유지한다.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| 구현 시도 없음 | 읽기 전용 코드 검토와 저장된 그래프의 지표 재계산만 수행; 변경 전 작업 트리 clean | verified: 사용자 요청 범위가 검토·계획·handoff 작성임 |

전체 심볼 분석 후 화면만 파일로 묶는 접근은 관계 추출 비용을 남기므로 단독 해결책으로 사용하지 않는다. 이는 코드 검토로 파악한 한계이며 실제 구현 실패 기록은 아니다. 이번 인계에는 사용자 거절 기록이나 ADR을 새로 만들지 않는다.

## Next Step

### 1. 실행 경계와 순서

스냅샷 → 언어·프레임워크 관계 추출 → 분석기 통합 및 라우트 매칭 → 분석 단위 변환 → 지표·후보 계산 → 직렬화·렌더링 순서로 구성한다. 원본 추출 데이터, 지표를 계산할 그래프, 상세 탐색 데이터의 책임을 구분한다. 여러 프레임워크가 같은 언어 노드를 공유하는 기존 중복 조정은 변환 전에 유지한다.

추가 리팩토링은 아래 연결된 경로에 한정한다. 동명 해석 개선, 새 분석기·관계 종류, 스캔 범위 확대, 영구 캐시, 분석 대상 코드 실행은 포함하지 않는다.

### 2. CLI와 공통 실행 제어

대상: `code_analyzer/cli.py`, `analysis/`, `bottlenecks/core.py`.

- 단일·다중 분석기 실행 모두 추출 단계와 지표 계산을 분리한다. CLI 경로에서는 개별 빌더의 지표 계산을 건너뛰고 최종 선택 그래프에 한 번만 적용한다.
- `analyze_bottlenecks`가 같은 지표를 다시 계산하지 않도록 공통 실행 결과를 전달한다. 결과의 노드 집합·분석 단위·가중치 설정 일치 여부를 검증한다. 임의의 `stats['analysis']`를 무조건 신뢰하는 캐시는 만들지 않는다.
- 기존 직접 호출 API는 기본 동작을 유지한다. 빌더의 계산 생략은 명시적 선택으로 제공하고, 사전 계산 결과가 없는 병목 API 호출은 자체 계산한다.
- `stats['analysis']`, 병목 `node_metrics`, HTML, JSON, CLI의 최고 중심성×규모 요약이 모두 같은 분석 단위를 가리키게 한다. 원본 그래프에 남은 이전 지표가 섞이지 않게 한다.
- `--no-language-graph`, `--no-models`, `--no-deps`, 진입점, 출력 경로 충돌, 출력 파일 스냅샷 제외를 기존 의미대로 적용한 후 변환한다.
- 프레임워크 구성 요소 통계와 분석 그래프의 파일·경계 노드 수를 구분한다. 파일 단위로 바뀌어도 기존 부록의 구성 요소 수를 파일 수로 덮어쓰지 않는다.
- 언어별 architecture 타입 전체를 한꺼번에 통합할 필요는 없다. 공통 변환 결과가 원본을 감싸게 해 기존 직접 호출자를 보호한다.

### 3. 스냅샷·소스 범위·비용 계산

대상: `repository/models.py`, `language_analyzers/core/{annotate,cost,enrichment}.py`, 각 언어 분석기의 소스 접근부.

- `RepositorySnapshot.content_map()`은 호출마다 사전을 만든다. 실행 내부에서 한 번 얻은 맵을 공유하되 기존 공개 메서드가 반환하는 독립 사전의 의미를 바꾸지 않는다.
- 파일별 텍스트·줄·이름 출현 위치 인덱스를 재사용한다. 심볼마다 같은 파일을 `splitlines()` 하거나 이름 전부를 검색하는 경로를 줄인다.
- 인덱스와 캐시 수명은 스냅샷/실행 하나다. 같은 프로세스에서 다른 내용의 저장소를 분석해도 이전 결과를 재사용하지 않는다.
- 실제 디스크를 다시 읽지 않고 전달된 스냅샷을 사용한다. 현재 스캔 제외 정책과 생성물 판단은 유지한다. 파일 노드는 추출 결과에 소속된 파일을 기준으로 만들고 스냅샷 내 문서를 무조건 그래프에 추가하지 않는다.
- 파일 비용은 전체 소스 기준으로 한 번 계산한다. 심볼 범위 중첩과 프레임워크 구현 매핑 때문에 같은 텍스트가 중복 합산되지 않게 한다.
- 빈 파일, 마지막 개행, 상대 경로·절대 경로, 설정 파일, 소스 없는 경계 노드를 테스트한다. 혼합 파일의 할인 정책은 아래 Open Questions에서 확정한다.

### 4. 언어 분석기와 공통 관계 보강

대상: `language_analyzers/kotlin/{analyzer,ast}.py`, `language_analyzers/python/{graph,symbols,source}.py`, `language_analyzers/typescript/{analyzer,http_calls,ast}.py`, `language_analyzers/core/enrichment.py`.

- Kotlin `_add_symbol_edges`의 두 전체 이름 순회를 파일별 출현 위치 인덱스로 대체한다. 심볼 범위 안의 매칭을 조회하되 대소문자·단어 경계·문자열/주석 포함 여부·처음 근거 위치·연결 중복 횟수·후보 순서를 보존한다.
- 테스트 관계 보강의 테스트 노드×운영 심볼 반복 검색도 인덱스로 대체한다. 비단순 식별자 라벨은 파일별 검색 결과를 재사용하고 현재 fallback 조건을 보존한다.
- Python·TypeScript는 파일 소유 정보와 상세 그래프 입력을 공통 변환에 제공한다. 속도 개선을 명목으로 import·export·호출·타입 해석을 다시 설계하지 않는다.
- 이름 인덱스는 기존 매칭의 의미를 재현해야 한다. AST 기반 식별자만 세도록 바꾸거나 동명 후보를 재정렬하면 D6 위반이다. 기존 구현과의 차분 검증 외에 수작업 기대값도 둔다.
- 모듈/파일이 가진 top-level 참조, 중첩 선언, 필드·상수·설정 키, 선언 소유 관계를 상세 탐색에서 찾을 수 있게 한다. 이를 모두 기본 그래프의 독립 노드로 올리지는 않는다.

### 5. 네 프레임워크 빌더와 분석기 간 연결

대상: `framework_analyzers/{fastapi,android,sqlalchemy,nestjs}/graph.py`, 각 `models.py`, `framework_analyzers/{route_matching,migration_tables}.py`.

- 네 빌더 모두 CLI에서 지표 계산을 생략할 수 있어야 한다. FastAPI·Android만 바꾸면 NestJS·SQLAlchemy 및 다중 분석기 경로에 중복 계산이 남는다.
- 프레임워크→언어 `IMPLEMENTED_BY`와 선언 위치로 파일 소유·상세 표시를 연결한다. 언어 그래프 제외 시에도 프레임워크 노드 자신의 소스 위치로 파일 분석이 가능해야 한다.
- `DECLARES`·`CONTAINS`라는 문자열만으로 관계를 제거하지 않는다. NestJS 모듈 선언이나 Room 관계와 언어의 단순 선언 소속을 출처·역할로 구분한다.
- TypeScript/Android 클라이언트와 FastAPI/NestJS 라우트 매칭, ORM/Room 마이그레이션 매칭은 파일 변환 전에 수행한다. 같은 파일에 여러 엔드포인트·테이블이 있어도 연결 근거와 모호한 후보가 남아야 한다.
- Python·TypeScript 언어 노드의 emitter 조정과 `pending_implementation_edges` 해소를 유지한다. 원래의 duplicate-ID 오류를 파일 집계로 숨기지 않는다.
- 프레임워크 부록 `ReportCollection.rows`는 원본 심볼 ID를 유지할 수 있으나 파일 모드의 탐색 링크가 소유 파일과 해당 상세 심볼로 이동하도록 연결한다.
- 기존 `generate_mermaid`는 프레임워크 구조와 원본 타입을 가정한다. 파일 모드는 변환된 노드·연결로 출력하고, 심볼 모드는 기존 경로를 유지한다. 기존 단일 프레임워크 지원 범위를 이번 변경으로 확대하지 않는다.

### 6. 파일 변환·지표·병목 후보

대상: `analysis/`의 공통 파일 변환 계층(신규), `analysis/graph_metrics.py`, `language_analyzers/core/{graph_models,flags}.py`, `bottlenecks/{core,identifier_occurrence}.py`.

- 파일 ID는 `file:<저장소 상대 POSIX 경로>`를 사용한다. 원본 노드 ID와 파일 소유 매핑을 함께 보존한다.
- 집계 키는 출발 파일·도착 파일·관계 종류·신뢰도·해석 상태다. 근거 목록과 원본 후보는 상세 레코드로 참조하고 파일 후보의 중복은 제거하되 원본을 잃지 않는다.
- 내부 연결과 단순 소속·구현 매핑은 파일 지표에 넣지 않는다. 내부 연결뿐인 파일도 독립 파일 노드로 유지한다. 실제 소속 불명 대상은 경계 노드로 보존한다.
- 파일 쌍의 유효 가중치는 원본 연결의 `min(confidence, resolution)` 중 최댓값이다. 서로 다른 연결에서 confidence와 resolution을 각각 최대화해 존재하지 않는 높은 신뢰도를 만들지 않는다.
- 파일 중심성은 재계산하며 경계 노드는 계산에 참여하되 파일 순위에서 제외한다. 이 필터는 병목 순위뿐 아니라 `GraphAnalyzer._rank`, HTML의 대표 목록과 전체 목록, CLI 요약에도 일관되게 적용한다.
- 경계 노드 비용 0이 `_node_token_cost`의 양수 검사 때문에 메타데이터 토큰 fallback으로 바뀌지 않게 한다. 심볼 모드의 기존 fallback 의미는 보호한다.
- `large_node`는 파일 전체, `unresolved_boundary`는 소속 원본 노드·연결의 미확정 근거, `evidence_spread`는 해당 파일로 들어오는 원본 근거에 적용한다. 같은 파일·종류의 후보를 합쳐도 원본 근거와 그 출처는 보존한다.
- 파일 모드에서는 `identifier_file_count` 계산·정렬·설명을 제외한다. 값 0을 넣어 ‘출현 없음’으로 오해하게 하지 않는다. 심볼 모드와 기존 JSON 렌더링에서는 유지한다.
- generic analysis/rendering 계층은 프레임워크별 클래스를 import하지 않는다. 기존 architecture boundary 테스트를 유지한다.

### 7. 직렬화·검증기·보고서

대상: `language_analyzers/core/{serialization,report_schema}.py`, `report/{unified.py,bottlenecks/generate.py,shared/labels.py}`, `renderers/html/{renderer.py,static/app.js,static/styles.css,templates/dashboard.html}`.

- `SCHEMA_VERSION`을 전역에서 단순히 6으로 올리지 않는다. 원본 architecture의 기존 직접 직렬화와 심볼 모드는 5를 유지하고 파일 결과만 6으로 내보낸다.
- 파일 JSON의 그래프와 원본 상세 데이터를 구분한다. 상세 데이터에 원본 노드·관계·소유 매핑을 두고 집계 근거는 레코드를 참조한다. 후보와 부록에서 참조하는 원본 ID가 실제 상세 데이터에 존재하는지 검증한다.
- `report/bottlenecks/generate.py`는 현재 `bottlenecks.v4`만 받고 최상위 키도 엄격히 검사한다. v5 분기, 분석 단위, 파일 대상 라벨, 새 근거 구조를 검증기에 추가한다. 허용 스키마만 바꾸고 검증을 느슨하게 만들지 않는다.
- 병목 JSON만 입력받는 `render_report`/`generate`에서도 v5 파일 순위·후보를 렌더링한다. architecture/detail 데이터가 없으면 심볼 상세 탐색을 제공하지 않는다는 상태를 표시한다. v4의 기존 동작을 유지한다.
- v5 병목 JSON은 architecture 파일 없이 후보를 설명할 수 있어야 한다. 단독 파일에 없는 detail 레코드만 가리키는 근거 구조를 사용하지 않는다.
- 현재 `_parse_id_target`은 언어 모듈 ID의 점을 경로 구분자로 바꾼다. `file:src/a.py`의 확장자나 점이 든 경로를 손상하지 않도록 파일 ID 분기를 먼저 처리한다.
- 초기 파일 화면과 상세 심볼 화면의 선택 상태·검색·뒤로 이동을 분리한다. 원본 심볼 검색으로 소유 파일을 찾을 수 있게 하고 상세에서 외부 파일로 이동할 때 원래 심볼 근거를 유지한다.
- 클래스·함수 그래프는 선택 시 생성한다. 선택된 대상과 직접 이웃 최대 30개를 표시하고 나머지 연결은 목록에 유지한다. 숨은 내용을 펼치기 전에는 대규모 DOM을 만들지 않는다.
- JSON 삽입의 `<`, `>`, `&` escaping과 텍스트 표시 안전성을 유지한다. 오프라인 HTML에서 네트워크 호출이나 분석 대상 실행을 추가하지 않는다.
- 저장된 기존 HTML은 자체 완결 파일이므로 재작성하지 않는다. 기존 JSON과 신규 JSON 모두 지원하고 README에서 기본 출력 변경과 심볼 모드 사용법을 설명한다.

### 8. 테스트·fixture·벤치마크·문서

| 영역 | 기존 영향 경로 | 추가·수정 검증 |
| --- | --- | --- |
| CLI/API | `tests/test_cli_contract.py`, `test_cli_bottlenecks_v3.py`, `test_cli_multi_analyzer.py`, `test_unified_cli.py`, `test_nestjs_cli.py`, `test_cli_sqlalchemy.py` | 기본 파일/명시적 심볼, 최종 그래프 1회 계산, 직접 API 호환, 옵션 조합, 출력 충돌·실패 |
| 언어·프레임워크 | `tests/test_python_graph.py`, `test_typescript_graph.py`, `test_symbol_graph_and_enrichment.py`, `test_android_graph_contract.py`, `test_nestjs_quality.py`, `test_route_client_call_edges.py`, `test_room_migration_edges.py` | 추출 의미 보존, 파일 소유, 다중 emitter, 라우트·DI·ORM 근거 보존 |
| 공통 모델·지표 | `tests/test_core_schema.py`, `test_graph_metrics.py`, `test_weighted_graph_metrics.py`, `test_category_rankings_v3.py`, `test_identifier_occurrence.py`, `test_architecture_boundaries.py` | 수작업 파일 그래프 기대값, 경계 비용·순위, 혼합 신뢰도 최대 가중치, 중복 텍스트 방지 |
| 직렬화·보고서 | `tests/test_serialization_and_rendering.py`, `test_report_bottlenecks_v3.py`, `test_unified_browser.py`, `test_unified_representatives.py`, `test_unified_top100.py`, `test_readability_labels.py` | schema 5/6 및 v4/v5, 단독 병목 JSON, 점·공백 포함 경로, 상세 참조 무결성, 목록·이동·생략 근거 |
| 성능·재현 | `tests/test_unified_performance.py`, `tests/unified_support.py`, `fixtures/registry.py`, `scripts/benchmark_hops.py` | 기존 브라우저 회귀 기준 유지, 신규 전체 실행 측정과 단계별 시간, 내용 고정 fixture |
| 사용자 문서 | `README.md` | 기본 파일 단위, 선택 심볼 모드, JSON 버전, 파일 경로의 의미·내부 병목 한계, 지표·후보 해석 |

- 기존 테스트의 schema 5/v4 기대값을 전부 새 버전으로 치환하지 않는다. 기본 CLI 계약 테스트를 파일 모드로 갱신하고, 기존 직접 호출과 심볼 모드 호환 테스트를 유지한다.
- 정상·경계·오류·예외 사례를 갖춘 작은 독립 fixture로 파일 변환 기대값을 직접 작성한다. 저장된 기존 결과를 새 파일 순위의 정답으로 사용하지 않는다.
- 기존 추출 결과와의 차분 검증에서는 노드/연결·후보·신뢰도·소스 범위·중복 횟수를 비교한다. 지표와 실행 시간은 별도로 검증한다.
- Tag-Manager 원본 작업 트리를 변경하지 않는다. 구현 시점에 같은 스냅샷을 고정해 기준/변경 후 모두 사용한다. 과거 1,229.9초 기록을 현재 코드의 새 기준 실행으로 대체하지 않는다.
- 전체 실행 측정은 새 프로세스 3회, 같은 환경·설치 의존성, 브라우저 실행 제외, 스냅샷 생성부터 HTML 저장까지 포함한다. 중앙값 ≤180초를 제안 합격 기준으로 하고 원시 시간·단계별 시간·메모리·HTML 크기를 기록한다. 추가 JSON 출력은 기능 검증하며 이 HTML 기준 시간과 구분한다.
- 기존 `benchmark_hops.py`는 hop 알고리즘 검증용이다. 그 결과로 전체 분석 성능을 대신하지 않는다. 새 전체 실행 측정은 환경·fixture 준비 시간과 명확히 구분한다.
- 전체 자동 검증 기반 명령은 `.venv/bin/python -m pytest -q`이다. 외부 fixture/Chrome이 필요한 절차와 성능 기준은 workflow spec의 검증 의무에 명시한다. 필수 절차를 skip한 결과를 합격으로 기록하지 않는다.
- 관련 없는 archive, 오래된 완료 spec·handoff, 생성된 HTML/이미지, 설치된 `.harness`·`.agents` payload, 스냅샷·가중치 profile의 기본값은 일괄 리팩토링 대상으로 삼지 않는다.

### 9. 후속 실행 순서

1. 이 handoff의 D1–D7과 제안 항목을 읽고 HEAD/작업 트리 drift를 확인한다. Open Questions를 spec에서 확정한다.
2. 기준 추출 결과와 단계별 시간 측정 절차를 준비하고 active spec을 작성한다. 구현·테스트 경로는 분리한다.
3. 검색/소스 인덱스와 CLI 중복 계산 제거를 먼저 구현한다. 심볼 모드 호환 검증을 통과시킨다.
4. 공통 파일 변환·파일 지표·후보와 새 직렬화를 구현한다. 단독 병목 JSON 검증기까지 연결한다.
5. HTML 상세·부록 탐색·Mermaid·CLI 통계·README를 같은 분석 단위로 맞춘다.
6. 전체 기능·브라우저·성능 검증과 독립 verifier 감사를 완료한다. 확인 mutation은 후보 손실, 파일 가중치 합산, 토큰 중복 합산 중 강한 결함 유형 2–3개를 선정한다.
7. 성공 시 이 handoff의 index 항목을 `stale.md`로 원문 이동하고 문서를 `stale/`로 옮긴다. 재개 중 실패 행은 삭제·수정하지 않고 추가한다.

## Open Questions

명시된 제품 선택 D1–D7은 다시 묻지 않는다. 아래는 프로젝트 전반 영향 검토에서 드러난 세부 정책으로, 이번 문서 작성에서 새로 확정하지 않았다.

1. **혼합 파일 할인:** Android는 특정 migration 심볼에만 `migration` flag를 붙일 수 있다. 이를 파일 전체에 승격하면 일반 코드까지 0.1배가 된다. 제안은 파일 경로/파일 자체 분류로 파일 비용을 할인하고, 부분 migration 표시는 상세에만 남기는 것이다. 부분 범위 할인을 원하면 범위 합집합과 중복 제거 규칙을 별도 명세해야 한다.
2. **경계 후보 표시:** 직전 계획은 소스 없는 실제 대상을 그래프에 남기고 파일 순위에서는 제외했다. 이 대상 자체의 미확정 후보를 놓치지 않도록 파일 상세와 별도 경계 목록에서 모두 찾게 하는 정책을 spec에 명시해야 한다.
3. **성능 측정 계약:** 사용자가 고른 3분 목표는 확정이다. 3회 중앙값이라는 합격 방식과 구현 시 고정할 Tag-Manager 스냅샷 식별·준비 절차는 제안 상태다. 개인 경로에 영구 의존하는 CI 테스트로 만들지 않는다.
4. **신규 상세 스키마:** 원본 근거를 보존하고 공유 참조한다는 방향은 계획에 있다. 레코드 ID·필수 필드·누락 참조 오류·v5 단독 후보 근거 형식은 테스트 역할 배정 전에 구체화해야 한다. 기존 공개 API에 사전 계산 결과를 전달하는 타입/검증 계약도 함께 명시한다.

## Spec

- Active/archived spec path: 없음.
- Version/status/run ID: 해당 없음; 구현 workflow 미시작.
- 이 문서의 `df8e06a5dda281c8`은 문서 ID이며 workflow run ID가 아니다.
- 계획의 근거: 대화에서 제시한 “파일 기본 분석과 심볼 상세 탐색 구현 계획”과 이 문서의 D1–D7.
- 재개 시 `.agents/skills/workflow-approach/SKILL.md`에 따라 별도 active spec을 작성하고 전체 명세를 승인받은 뒤 구현을 시작한다. 이 handoff만으로 구현/테스트 subagent를 배정하지 않는다.
- active spec이 생성되면 이 handoff 경로를 해당 spec의 `handoff`에 기록한다. 구현과 테스트는 독립 역할로 수행하며 verifier 상한은 2회다.

## Execution Ledger

| ID | finding / disposition | evidence | mutation / execution outcome |
| --- | --- | --- | --- |
| E1 | 전체 실행 지연의 기록 확인; 현재 단계별 프로파일로 간주하지 않음 | `local-reports/tag-manager-timing.json`: wall 1,229.899초, HTML 98,402,799 bytes, 1회 기존 실행 | 읽기만 수행 |
| E2 | 저장 그래프 규모 확인; 파일 집계의 가시성 근거 | `local-reports/tag-manager.html`: 5,417 nodes, 73,747 edges, 소스 위치 기준 296 files, 소스 없는 20 nodes. FastAPI 저장 결과: 680 nodes/98 files | JSON을 메모리에서 읽어 집계; 파일 변경 없음 |
| E3 | 지표 재계산만으로 과거 전체 시간을 설명하기 어려움 | 저장된 Tag-Manager 그래프를 현재 `GraphAnalyzer`로 1회 재실행: 총 3.1605초; PageRank 0.5914, HITS 1.2049, Betweenness 1.0355, hop 0.1368초 | 추출·후보·HTML 제외; 별도 측정 파일은 없고 수치는 대화 tool 출력에서 인계. 동일 실행의 구간 비율이나 전체 개선율로 해석하지 않음 |
| E4 | Kotlin 반복 검색을 우선 최적화 대상으로 지정 | `language_analyzers/kotlin/analyzer.py`의 `_add_symbol_edges`; 저장 결과 4,770 Kotlin symbols × 3,800 names × 2 순회 ≈3,625만 이름 검사 규모 | 코드상 비용 후보; 전체 지연 원인 비중은 아직 hypothesis |
| E5 | 동명 해석 편중 확인; D6에 따라 이번 해석 변경 제외 | `Favorite.path` 유입 1,237개 중 ambiguous 1,236개; `_resolve`는 첫 후보 연결, 나머지 candidates 보존 | 기존 해석의 정밀도가 보장된다는 결론은 아님 |
| E6 | 지표 중복 계산과 보고서 연쇄 변경 확인 | 네 프레임워크 `graph.py`, CLI `_run_analyzer`/`_run_merged`, `bottlenecks.core.analyze_bottlenecks`; v4 고정 검증기·schema 5 직렬화·원본 ID 부록·Mermaid 경로 | 위 Next Step에 계획만 작성 |
| E7 | 예전 중복 분석 handoff와 현재 사실 구분 | `agent-docs/handoff/stale/3a1c71a7afc82a15-framework-analysis-duplication.md`는 과거 미가중 재계산 사례. 현재 빌더는 `analysis_config`를 받지만 병목 단계 재계산은 남음 | 역사 문서 재활성화·수정 없음 |
| E8 | 문서 작성 범위 | 이 handoff와 handoff index | 문서 구조·링크·git diff 확인; 구현 테스트와 mutation 미실행 |

- Correction batches used: 0.
- Verifier invocations: 0 / 예정 상한 2; 아직 workflow run이 없음.
- Mutation attempts: 0; outstanding backup 없음.
- Open verification findings: 없음; 검증 자체가 미시작이며 합격을 의미하지 않음.
- 남은 작업: Open Questions 확정, 승인된 spec 작성, 위 전체 구현과 기능·호환·성능 검증.
