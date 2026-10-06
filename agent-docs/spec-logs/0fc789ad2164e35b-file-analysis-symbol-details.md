---
version: 2
run_id: 0fc789ad2164e35b
status: complete
base_commit: 7eb255b0d552771c01e11fc2b4475663815c9567
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I01 | 사용자 | 파일 기본 분석과 심볼 상세 탐색 | 기본 CLI의 순위·후보·그래프는 파일 단위이며 같은 오프라인 HTML에서 심볼과 원본 근거를 탐색한다. |
| I02 | 사용자 | 관계 보존과 성능 개선 | 기존 해석 결과를 보존하고 현재 환경의 Tag-Manager 3회 실행 중앙값이 180초 이하이다. |
| I03 | 사용자 | 기존 전역 심볼 분석 유지 | 명시적 symbol 실행과 직접 호출 API의 기본 의미가 유지된다. |

# Scope
In scope: 사용자 메시지 「파일 기본 분석과 심볼 상세 탐색 구현 계획」의 1–5절 전체. Python, TypeScript/JavaScript, Kotlin, FastAPI, Android, SQLAlchemy, NestJS; 공통 파일 변환; 검색 인덱스와 실행 내 소스 캐시; CLI; architecture 6 및 bottlenecks.v5; 파일 화면과 심볼 상세; 기존 schema 5 및 bottlenecks.v4 호환; README; 성능·브라우저·관계 보존 산출물.

Out of scope: 동명 해석 정확도 개선, 파일 내부 별도 중심성 순위, 서버 기반 재분석, 분석 대상 애플리케이션 실행, AI 에이전트 행동 예측·코드 품질·변경 위험·작업 난이도 판정, 다중 분석기의 기존 Mermaid 제한 해제, 새로운 언어·프레임워크 지원.

아래 v1 세부 계약과 A01–A06은 2026-10-05 전체 승인되었다. 2026-10-06 사용자는 나머지 v1과 직접 API 기본 동작을 유지하며 “file만 1회 계산, symbol 기존 계산·출력값 보존” 정책으로 v2 전체 수정을 승인했다. A07과 F01/F02/C01/Q04/V01의 계산 정책을 제외한 기대값·180초 및 browser 기준·관계 보존·검증 상한은 변경하지 않는다.

# Paths
Implementation: code_analyzer/, analysis/, repository/, language_analyzers/, framework_analyzers/, bottlenecks/, renderers/html/, report/, README.md

Tests: tests/, scripts/benchmark_file_analysis.py

Test command: `.venv/bin/python -m pytest -q`

Review evidence: tests/file_analysis_evidence/{coverage.json,baseline-manifest.json,baseline-relations.json,baseline-timing.json,optimized-symbol-relations.json,symbol-equivalence.json,benchmark.json,browser.json,architecture-review.md,mutations.json}. 테스트 담당은 실행기와 독립 기대값을 작성하고, main은 구현 변경 전에 기준선을 실행·저장한다. 기준선 확보 전 implementer는 구현을 변경하지 않는다. 성능·브라우저 검증은 pytest에서 실행하며 필수 산출물 누락을 실패로 처리한다.

# Signatures
기존 시그니처의 기존 인수·기본 동작을 유지한다. 새 계약:

`analysis.file_graph.FileArchitecture`: project_name, project_path, nodes, edges, stats, report_collections, details, granularity="file"을 가진 architecture 객체.

`analysis.file_graph.to_file_architecture(architecture: Any, snapshot: RepositorySnapshot) -> FileArchitecture`

`bottlenecks.core.analyze_bottlenecks(snapshot: RepositorySnapshot, architecture: Any, weights: EdgeWeights, *, analysis: Optional[Mapping[str, Any]] = None) -> BottleneckReport`

`framework_analyzers.{fastapi,android,sqlalchemy,nestjs}.graph.*GraphBuilder.__init__(<기존 인수>, compute_metrics: bool = True)` — 새 인수는 keyword로 제공하며 file CLI는 False, symbol CLI와 기존 직접 호출은 True를 사용한다.

`scripts/benchmark_file_analysis.py --baseline|--verify --project PATH --evidence-dir PATH` — baseline은 변경 전 스냅샷·관계·시간을 저장한다. verify는 동일 스냅샷 확인, 최적화 symbol 비교, file 3회 측정을 수행한다. 별도 CLI benchmark 옵션은 추가하지 않는다.

`architecture_to_dict(architecture)`, `HTMLRenderer.render(...)`, `render_unified_report(...)`는 기존 시그니처로 두 형식을 지원한다. 검색 인덱스와 소스 캐시의 내부 API는 구현 담당이 정할 수 있으나 F03의 관측 가능한 결과와 계산 범위는 변경할 수 없다.

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F01 | file CLI 순서는 스냅샷→선택한 언어·프레임워크 관계 추출→통합→파일 단위 변환→지표·후보 계산→출력. symbol은 기존 adapter/단독언어→통합→병목 계산 경로와 순서를 보존한다. 두 모드 모두 추출 옵션을 먼저 적용하며 제외한 언어 분석을 상세 탐색 때문에 재실행하지 않는다. | required | 계획2·4, 사용자 v2 승인 |
| F02 | file CLI는 최종 파일 그래프에서 GraphAnalyzer를 한 번 실행하며 HTML·architecture JSON·bottleneck JSON이 그 결과를 재사용한다. file에서 전역 symbol 지표를 계산하지 않는다. symbol CLI는 기존 계산 횟수·순서·결과를 보존하며 반복 계산이 허용된다. 직접 API의 기본 동작은 유지한다. symbol의 소스 없는 fallback 비용에 이전 metadata.analysis가 반영되는 기존 동작도 보존한다. | required | 계획2, 사용자 v2 승인 |
| F03 | Kotlin의 전체 이름 검색과 TESTS 보강을 파일별 출현 위치 인덱스로 대체하여 심볼 범위 내 일치를 조회한다. 기존 단어 경계·대소문자·문자열/주석 처리·연결 순서·중복 횟수·선택 대상·동명 후보·confidence·resolution·최초 근거 위치를 보존한다. 일반 식별자 외 이름의 검색 결과는 파일/name별 캐시한다. snapshot map·줄 분리·소스 범위 결과를 실행 내 재사용한다. | required | 계획2 |
| F04 | 공통 변환의 파일 ID는 file:<저장소 상대 POSIX 경로>. 추출 결과에 실제 포함된 소스·설정 파일만 대상으로 하고 스냅샷 문서 전체를 새 노드로 만들지 않는다. 내부 연결만 있는 파일도 유지한다. | required | 계획3 |
| F05 | 심볼·프레임워크 노드를 소유 파일에 대응시킨다. 언어 선언 소속 관계와 IMPLEMENTED_BY는 소유·상세 정보로 보존한다. 프레임워크의 실제 의존 관계는 관계 이름만으로 제거하지 않는다. 파일 내 관계는 details에 보존하고 file self-edge에서 제외한다. 소스 없는 package 소속 노드는 탐색 metadata로 유지한다. 대응 파일 없는 실제 의존 대상은 원래 ID의 경계 노드로 유지하며 소스 비용 0, 파일 순위에서 제외한다. | required | 계획3 |
| F06 | 집계 key는 출발 file/boundary ID·도착 file/boundary ID·relation·confidence·resolution. 집계 연결은 details 내 모든 원본 edge index를 참조한다. 같은 방향의 노드 쌍의 지표 가중치는 원본 유효 가중치의 최댓값이며 건수나 edge.weight를 더하지 않는다. 원본 candidates·소스 위치·중복 weight를 유지한다. | required | 계획3 |
| F07 | PageRank·HITS·degree·Betweenness·fan·hop을 file graph에서 다시 계산한다. 원본 symbol 점수 합산은 금지한다. 파일 토큰은 snapshot 전체 텍스트를 한 번 계산하고 기존 tokenizer·할인 정책을 적용한다. 경계 비용은 0이며 네트워크 지표 계산에는 참여한다. file에는 identifier_file_count와 컨텍스트별 지표를 제공하지 않고 symbol에서는 유지한다. | required | 계획3 |
| F08 | large_node는 파일 전체 줄 수가 기존 threshold를 초과할 때, unresolved_boundary는 소속 심볼의 미확정 edge·reference·dynamic flag로 생성한다. evidence_spread는 해당 파일로 들어오는 원본 근거가 여러 파일에 있거나 단일 근거 파일의 줄 범위가 threshold를 초과할 때 생성한다. 같은 file/kind는 한 후보로 묶고 모든 세부 근거와 static_candidate 상태를 보존한다. | required | 계획3 |
| F09 | --granularity file|symbol의 기본값은 file. symbol은 기존 ID·지표 의미·출력 schema를 유지한다. Mermaid는 선택 단위를 반영하고 단일 framework 한정과 기존 다중 분석기 오류를 유지한다. 분석기 순서·중복 ID 오류를 유지한다. | required | 계획4 |
| F10 | file architecture는 schema_version="6", granularity="file"이고 nodes/edges는 파일 그래프다. details 계약은 아래와 같다. file bottleneck은 schema="bottlenecks.v5", granularity="file". symbol은 architecture "5"와 bottlenecks.v4의 기존 구조다. HTML에 포함된 결과와 별도 JSON을 파싱한 데이터가 동일하다. | required | 계획4 |
| F11 | 대표 순위·후보 목록·주변 그래프는 파일 중심이다. 기존 6개 대표 지표·검색·분류·상위100·전체 전환·50개 페이지·후보 필터를 유지한다. 경계는 근거와 그래프에서 탐색하며 파일 순위·목록·후보 대상에서 제외한다. | required | 계획4、A02 |
| F12 | 파일 상세에 class·interface·최상위 function 목록을 제공한다. method/field는 소유 class로 접고 그 외 참조는 파일 본문으로 연결한다. 중첩 class/function의 소속을 보존한다. framework role은 구현 symbol에 붙여 중복 표시를 줄인다. 언어 제외 시 제공 가능한 framework 정보만 표시한다. | required | 계획4 |
| F13 | symbol 선택 시 대상과 직접 이웃 최대30개의 그래프를 지연 생성한다. 내부 대상은 표시되는 소유 class 또는 파일 본문에 연결하고, 외부 대상은 상대 파일로 묶되 원래 target symbol을 근거에서 확인할 수 있다. 그래프에서 생략된 연결도 50개 페이지의 전체 연결 목록에서 접근 가능하다. 외부 파일 선택은 그 파일 상세로 이동한다. | required | 계획4 |
| F14 | 상세 데이터와 그래프 asset을 HTML 안에 유지하여 offline 동작한다. schema5/v4의 기존 renderer API를 유지한다. 파일 간 경로가 함수 호출 연쇄를 보장하지 않는다는 설명을 HTML과 README에 추가한다. README의 기본 file 실행·명시 symbol 실행 예시와 비용·후보·지표 단위를 갱신한다. | required | 계획4·5 |
| F15 | 최적화 전후 모든 node·edge·target·candidate·confidence·resolution·evidence·중복 횟수가 작은 예제와 실제 저장소에서 일치해야 한다. 원본 node metadata의 analysis와 시간만 비교에서 제외한다. 스냅샷 내용을 hash로 고정하고 각 단계의 초와 전체 시간을 산출물에 저장한다. 출력 단위 변경만으로 최적화 합격을 판단하지 않는다. | required | 계획2·5 |
| F16 | 잘못된 option·출력 경로 충돌·잘못된 snapshot/graph/weights는 출력 전에 실패한다. 쓰기 실패는 비정상 종료와 원인 진단으로 처리하며 성공으로 보고하지 않는다. 기존 API 오류형을 유지한다. | required | 계획5 |

details JSON 계약(A03):
- nodes: 기존 node serializer의 원본 결과. metadata.analysis 등 전역 심볼 지표를 포함하지 않는다.
- edges: 기존 edge serializer의 원본 결과. 원래 연결 순서·후보 순서·중복 weight를 보존한다.
- node_files: 원본 node ID → file ID 또는 null. 경계/package의 파일 미대응은 null이다.
- node_owners: 원본 node ID → 소유 class/선언 node ID 또는 null. 원본 소속 edge도 유지한다.
- file_nodes: file ID → 원본 node ID의 순서 있는 배열.
- 집계 edge.metadata에 detail_edge_indices와 evidence_count를 포함한다. 전자는 details.edges의 0부터 시작하는 index, 후자는 원본 edge 개수다. 원본 edge.weight의 중복 횟수는 별도 근거로 표시하며 지표에 더하지 않는다.
- 소유 판정 우선순위는 유효 span → 유효 metadata.file_path → IMPLEMENTED_BY의 구현 대상 → 언어 선언의 부모다. 직접 소스가 없는 경우에만 전파하며 서로 다른 소유 파일이 충돌하면 임의 선택하지 않고 입력 오류로 처리한다. 관계 이름과 함께 언어 provenance/선언 node kind를 사용하여 실제 framework 의존을 제거하지 않는다.

# Errors
| id | failure condition | observable signal | post-failure state |
| --- | --- | --- | --- |
| E01 | 잘못된 granularity·중복 analyzer·부적절한 entrypoint·다중 Mermaid·출력 충돌 | argparse exit2와 진단 | 추출·쓰기를 실행하지 않고 기존 출력을 유지한다. |
| E02 | 대상 경로 없음/디렉터리 아님·잘못된 weights/snapshot·graph ID/reference·소유 충돌 | CLI exit1과 진단, 기존 BottleneckInputError/ValueError API 계약 | 출력을 시작하지 않는다. |
| E03 | HTML/architecture JSON/bottleneck JSON 쓰기 실패 | CLI exit1과 원인 진단 | 실패한 출력을 성공으로 보고하지 않는다. 이미 쓴 다른 출력의 rollback은 추가하지 않는다. |
| E04 | benchmark 스냅샷 hash 불일치·관계 차이·시간 초과·필수 browser 산출물 누락 | 실행기/test 실패와 원인 산출물 | 합격으로 기록하지 않으며 다른 스냅샷으로 기준선을 대체하지 않는다. |

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C01 | normal | Python/TypeScript/Kotlin 및 4 framework의 각 단독 CLI | 기본 file·명시 symbol 관계 유지, file 지표1회·symbol 기존 계산/출력 보존 |
| C02 | normal | FastAPI+TypeScript, Android+FastAPI, FastAPI+SQLAlchemy+TypeScript, NestJS+TypeScript, SQLAlchemy+Python | 기존 중복 조정·DI·HTTP CALLS_ROUTE·ORM/MIGRATES 유지와 파일 집계 |
| C03 | edge | Kotlin/TESTS 동명 후보·대소문자·Unicode·문자열·주석·단어 경계·비일반식별자 이름·중첩 범위·반복 출현 | 기존 대상/후보 순서·최초 위치·중복 weight까지 완전 일치 |
| C04 | normal | A:a1/a2, B:b1의 같은 방향 연결, relation2종·confidence1.0/0.3·resolution exact/ambiguous·duplicate weight7 | key별 집계, pair 지표 weight1.0, 후보 b2의 파일을 실제 dependency로 추가하지 않음 |
| C05 | boundary | 내부 연결만 있는 파일·고립 파일·추출된 빈 파일·빈 그래프·스냅샷 문서만 존재 | 파일 노드 유지·self-edge0·빈 지표/후보·문서만 새 노드로 추가하지 않음 |
| C06 | edge | 소스 없는 package 소속·실제 의존 경계·경계→file 연결 | 소속 metadata·경계0비용·그래프 참여·파일 순위/목록 제외·근거 탐색 |
| C07 | edge | 중첩 class/function·method/field·최상위 참조·framework IMPLEMENTED_BY·설정 파일 | 소속 보존·비용 집계·구현 역할 표시·CONFIGURES 등 실제 의존 유지 |
| C08 | normal | 손으로 만든 A→B→C, 고립D, 중복 심볼과 겹치는 source span | 독립 file 지표/전체텍스트 비용 기대값 일치, symbol 점수/텍스트 중복 합산 검출 |
| C09 | boundary | large threshold T-1/T/T+1줄, 단일근거 줄 범위 T-1/T/T+1, 근거파일2개 | 초과만 후보·여러파일 spread·file/kind당1후보·전체 근거 |
| C10 | edge | 같은 파일의 여러 unresolved node/edge·dynamic flag·ambiguous만 있는 edge | 기존 조건 유지·ambiguous만으로 새 unresolved 조건을 만들지 않음·file/kind집계 |
| C11 | normal | no-language-graph/no-models/no-deps, 단일framework Mermaid file/symbol | 제외 후 변환·언어 재실행0·선택 단위 Mermaid |
| C12 | normal | architecture5/v4, architecture6/v5, v4만 있는 기존 renderer API | 기존symbol/새file 의미·HTML과 별도JSON 동일·없는 details를 생성하지 않음 |
| C13 | boundary | file100/101, list50/51, symbol 이웃0/1/30/31, 같은 외부파일의 여러target | 기존상위100/전체/페이지·graph최대31노드·정확한 생략·전체근거 접근 |
| C14 | normal | file→class/function→외부file→돌아오기, 분류/검색/후보 전환 | 올바른 대상과 소속·지연graph·대표/후보/목록은 file 중심 |
| C15 | edge | 공격성 title/path/docstring/evidence/candidate 문자열, file://와 HTTP(S) 차단 | escaping·예기치 않은 script0·외부요청0·미처리 browser 오류0·상세 접근 |
| C16 | error | E01의 각 입력 | exit2·추출/쓰기0·기존output hash불변 |
| C17 | error | E02의 각 입력, HTML/architectureJSON/bottleneckJSON 각각 쓰기 실패 | 지정 error/exit1·입력 오류는쓰기0·실패 출력을 성공으로 보고하지 않음 |
| C18 | normal | 동일 Tag-Manager snapshot의 변경 전/최적화symbol, 최종file 독립process3회 | 관계 등가·6단계 시간·스냅샷 시작~HTML저장 끝 중앙값≤180초 |
| C19 | normal | 기존10000node/30000edge/1000candidate browser fixture 및 Tag-Manager file HTML | 각5fresh context 중앙값 초기≤5초/filter≤300ms/detail≤1초 |
| C20 | error | 변경된 snapshot·변조relation·초과timing·누락browser artifact | E04의 실패와 원인 기록 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 모든 지원 분석기의 집계·상세·지표 의미를 만족해야 한다. |
| Performance efficiency | yes | 사용자 지정 CLI·브라우저 성능 기준이 있다. |
| Compatibility | yes | 명시symbol·직접API·기존보고서를 유지한다. |
| Interaction capability | yes | 파일·심볼·외부 파일 탐색을 검증한다. |
| Reliability | yes | 입력 오류와 쓰기 실패를 성공으로 처리하지 않는다. |
| Security | yes | 소스 유래 데이터 escaping과 offline 동작을 검증한다. |
| Maintainability | yes | 언어별로 다른 파일 집계 의미를 만들지 않고 공통 계층을 사용한다. |
| Flexibility | no | 새 환경/분석기 적응은 제외하며 단위 전환은 기능 요구로 검증한다. |
| Safety | no | 정적 구조 표시 변경이며 안전 제어 기능이 없다. 품질/위험 판정을 추가하지 않는 범위는 유지한다. |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | Functional suitability / correctness | 원본 관계와 파일 집계 | C01–C10 열거 항목·전체 관계 비교·독립 기대값 | 열거 항목100%, 관계차이0, 정수정확, float abs≤1e-9 또는 rel≤1e-8 | automated + mutation | 계획3·5, A06 |
| Q02 | Performance efficiency / time behaviour | 현재환경 Tag-Manager -f android, 준비/브라우저 제외 | 동일snapshot 독립process3회, snapshot시작~HTML쓰기완료 및 단계별 seconds | 중앙값≤180, 생값3개, 6단계 누락0 | automated + review | 계획1·2·5 |
| Q03 | Performance efficiency / time behaviour | C19의 두browser dataset, 각5fresh context | summary/filter 이후 두animation-frame, detail graph완료까지 ms | 중앙값 초기≤5000/filter≤300/detail≤1000 | automated | 계획5, 기존browser절차 |
| Q04 | Performance efficiency / resource use | 작은 예제·실repo 추출과 CLI | 이름scan/cache·GraphAnalyzer 호출 횟수·전후 단계시간 | file CLI지표1회·전역symbol지표0회; symbol은 원본 계산 경로 보존으로 반복허용; 일반명 전체검색을symbol별반복하지 않음, 비일반명 scan≤1/file/name | automated + review | 계획2, 사용자 v2 승인 |
| Q05 | Compatibility / coexistence | C11–C12 및 전체pytest | 명시symbol·직접API·schema5/v4 기대값과 새schema | 선언항목100%, pytest실패0, 새 필수의무를skip으로면제하지 않음 | automated | 계획2·4·5 |
| Q06 | Interaction capability / operability | C13–C14 | UI전환·이웃·페이지·전체근거 접근 항목 | 선언항목100%, 대상/개수/근거차이0 | automated + review | 계획4·5 |
| Q07 | Reliability / faultlessness | C16–C17,C20 | exit/error형/write trace/기존output hash | 선언오류100%, 잘못된입력 write0 | automated | 계획5 |
| Q08 | Security / integrity | C15 | 공격성 입력·script sentinel·network trace·browser errors | 예기치않은script0, HTTP(S)요청0, 미처리error0, 선언surface100% | automated | 계획5 |
| Q09 | Maintainability / modularity | 7분석기 변환과 README | main의 호출/변환module 확인, README5설명항목 확인 | 공통변환1, 분석기별별도집계0, 설명누락0 | review | 계획3·5 |

# Verification Obligations
coverage는 아래 열거 집합을 분모로 한다. 따로 나열한 차원의 암묵적 직적을 요구하지 않는다. 경험 기반 항목은 추가 결함 추정이며 아래 관측 기준을 반드시 확인한다.

| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V01 | F01,F02,F09,Q04,Q05,C01,C11 | CLI/직접API | integration;기본 file7단독분석기·4builder 직접호출·3제외옵션 각1예제; symbol 기존값은 V08/V16의 원본 byte 특성검사 | scenario | python;typescript;kotlin;fastapi;android;sqlalchemy;nestjs;direct-fastapi;direct-android;direct-sqlalchemy;direct-nestjs;no-language;no-models;no-deps | 100% | file 순서·CLI1회·기존API기본계산·제외분석재실행0; symbol 기존 계산/출력은 V08/V16으로 보존 확인 | pytest trace, coverage.json, immutable Nest standalone byte baselines |
| V02 | F03,F15,Q01,Q04,C03,C18 | Kotlin/TESTS관계 | integration;열거 작은fixture와 고정Tag-Manager | metamorphic testing | case;unicode;string;comment;boundary;nonidentifier;nested;duplicates;ambiguous-order;Tag-Manager | 100% | 변경전후 전체관계완전일치·scan횟수 | --baseline 변경전/--verify 변경후, symbol-equivalence.json |
| V03 | F04,F05,F06,Q01,C04,C05,C06 | 공통변환 | unit;손으로만든GraphNode/Edge, 추출결과를oracle로쓰지 않음 | equivalence partitioning | internal-only;isolated;empty-file;empty-graph;docs-only;mixed-key;candidate-only;duplicate-weight;package-membership;real-boundary;boundary-incoming | 100% | 독립ID/edge/ref·self0·maxweight·boundary0 | pytest, coverage.json |
| V04 | F05,F12,Q01,C07 | 소속/role/config | unit+integration;적합한 각언어/framework예제 | classification tree | nested-class;nested-function;method;field;top-reference;implemented-by;configuration;framework-same-relation-name | 100% | 소속과실제의존보존 | pytest, browser.json, coverage.json |
| V05 | F07,Q01,C08 | file지표/비용 | unit;A→B→C+D손그래프·전체텍스트·겹치는symbol | metamorphic testing | PageRank;HITS;degree;betweenness;fan;weighted-fan;hop2;hop3;whole-text;duplicate-symbol-invariance;boundary-zero;discount-1;discount-0.1;discount-0;no-identifier | 100% | 독립손계산/고정선형방정식·기존tokenizer산술·Q01오차 | pytest, coverage.json |
| V06 | F08,Q01,C09,C10 | 후보 | unit;고정threshold열거입력 | boundary value analysis (3-value) | large-T-1;large-T;large-T+1;spread-T-1;spread-T;spread-T+1;spread-2files;unresolved-many;dynamic-flag;ambiguous-only | 100% | 초과조건·file/kind1후보·모든근거 | pytest, coverage.json |
| V07 | F01,F05,F09,Q01,Q05,C02 | 다중분석기·semantic관계 | integration;C02의5조합 각1fixture의file/symbol | scenario | fastapi-ts;android-fastapi;fastapi-sqlalchemy-ts;nestjs-ts;sqlalchemy-python | 100% | DI/HTTP/ORM/MIGRATES·기존대상보전 | pytest 독립원본기대값, coverage.json |
| V08 | F09,F10,F14,Q05,C11,C12 | schema/JSON/Mermaid | integration;file/symbol/기존입력 | syntax testing | architecture6;v5;architecture5;v4;v4-only;html-json-identical;no-symbol-metrics;file-mermaid;symbol-mermaid;language-mermaid-existing-limit | 100% | schema·ID·details참조·동일데이터·기존제한 | pytest, coverage.json |
| V09 | F11,F13,Q06,C13 | 순위/페이지/graph | end-to-end;열거경계 | boundary value analysis (2-value) | top100;top101;page50;page51;neighbors0;neighbors1;neighbors30;neighbors31;external-file-group;all-evidence | 100% | 개수·페이지·상한·생략·근거접근 | Playwright pytest, browser.json |
| V10 | F11,F12,F13,Q06,C14 | 탐색/필터/role | end-to-end;고정mixedfixture의각전이 | state transition testing | file-to-class;file-to-function;symbol-to-external-file;back-to-file;method-fold;field-fold;nested-owner;framework-role;framework-only;search;category;candidate-filter;initial-no-graph | 100% | 대상·소속·file중심·지연생성 | Playwright pytest, browser.json |
| V11 | F14,Q08,C15 | escaping/offline | end-to-end;5surface와network차단 | error guessing | title;path;docstring;evidence;candidate;offline-navigation | none — experience-based | 모든열거surface script/외부요청/error0·상세접근 | Playwright pytest, browser.json |
| V12 | F16,Q07,E01,E02,E03,C16,C17 | 오류 | integration;E01/E02각조건·3출력쓰기 | decision table | granularity;duplicate-analyzer;entrypoint;multi-mermaid;output-collision;missing-path;not-directory;bad-weights;bad-snapshot;bad-graph-id;bad-reference;ownership-conflict;html-write;architecture-write;bottleneck-write | 100% | 정의신호·후속상태 | pytest writer/read spies·기존hash, coverage.json |
| V13 | F15,Q02,Q04,E04,C18,C20 | 추출/전체시간 | end-to-end;같은snapshot·file3독립process·symbol비교·실행기거절입력 | scenario | baseline-snapshot;baseline-relations;optimized-symbol;file-run1;file-run2;file-run3;snapshot-mismatch;relation-mismatch;timing-failure;missing-browser-evidence | 100% | 완전등가·중앙값≤180·6단계/전체시간·오류거절 | --verify를pytest에포함, benchmark.json·baseline산출물 |
| V14 | Q03,C19 | browser시간 | end-to-end;기존largefixture와Tag-Manager fileHTML 각5freshcontexts | scenario | synthetic-initial;synthetic-filter;synthetic-detail;Tag-Manager-initial;Tag-Manager-filter;Tag-Manager-detail | 100% | 각중앙값 Q03·생값5개 | Playwright pytest, browser.json |
| V15 | F14,Q09 | 공통변환/README | review;main의7분석기경로/README열거확인 | scenario | shared-converter;no-adapter-specific-aggregation;default-file-example;explicit-symbol-example;file-cost;candidate-unit;path-limitation | 100% | Q09구조와설명 | architecture-review.md |
| V16 | I01,I02,I03,Q05 | 회귀 | integration;기존전체pytest | scenario | full-pytest | 100% | 전체실패0·필수항목skip면제0 | Test command, coverage.json |

새 구조 기반 coverage 비율은 요구하지 않는다. 관계 보존·파일 지표 의미·시간 기준은 독립 기대값, 열거한 관측, 변경 전 특성 비교와 mutation으로 검증하며 코드 실행률만으로 대체할 수 없다.

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
| --- | --- | --- | --- |
| A01 | /Users/hwansu/toy-projects/Tag-Manager를 -f android로 측정한다. 기준선의 snapshot 전체내용과hash를 고정해 모든측정에 사용한다. | 기존 local-reports/tag-manager-timing.json·실경로확인. 기존1회1229.9초는준비/시작을포함하므로 새기준선을대체하지않는다. | 사용자 전체명세 승인: 2026-10-05 |
| A02 | 소스없는경계는file순위·목록·후보대상에서제외하고 근거/graph에서탐색한다. symbol모드분류는유지한다. | 계획의파일순위제외·경계유지를목록/후보로구체화했다. | 사용자 전체명세 승인: 2026-10-05 |
| A03 | details구조와소유우선순위는F10후열거를따른다. 소유충돌은오류. symbol상세이웃순위는최대weight→상대file fan_in→ID이며내부이웃은표시owner ID로묶는다. | 기존graph는weight/fan_in/ID를사용한다. 새상세에서전역symbol중심성을계산하지않는다. | 사용자 전체명세 승인: 2026-10-05 |
| A04 | 파일줄수는len(text.splitlines()), 빈파일0줄, 말단개행의가상빈줄은세지않는다. token은기존estimate_tokens 전체text로계산해빈파일도기존최소1token, 소스없는경계만0token. | 기존cost_for_text줄수는말단개행에서+1이고tokenizer는최소1이다. file경계를구체화하며symbol의기존의미는유지한다. | 사용자 전체명세 승인: 2026-10-05 |
| A05 | 들어오는원본근거는파일간·파일내실제dependency를포함한다. 소유정보뿐인선언소속/IMPLEMENTED_BY는spread/미확정dependency근거에서제외한다. 경계향미확정edge는소유출발file의후보에도근거를남긴다. | 파일후보의근거손실을막는제안이며ambiguous만으로기존후보조건을확장하지않는다. | 사용자 전체명세 승인: 2026-10-05 |
| A06 | 지표float허용오차는abs≤1e-9 또는rel≤1e-8. 관계·건수·위치는완전일치. browser는기존largefixture의5freshcontext중앙값과Tag-Manager fileHTML에동일기준을적용한다. | 기존browser검증의5회중앙값절차를사용한다. 계획에없는오차·새filedataset선정을구체화했다. | 사용자 전체명세 승인: 2026-10-05 |
| A07 | file만 1회 계산하고 symbol의 기존 계산·출력값을 보존한다. CLI symbol 및 직접 API fallback 비용의 이전 analysis 포함 동작을 고치지 않는다. | 원본HEAD byte 비교로 FastAPI181→42/Android200→59 차이를 확인했다. 기존 반복 경로가 앞선 metadata.analysis를 fallback에 포함하므로 모든 CLI 단일 결과와 기존 symbol 값 보존이 충돌했다. file180초 기준은 이미 만족했고 기존 symbol 값 보존이 선택됐다. | 사용자 2026-10-06: “file만 1회 계산, symbol 기존 계산·출력값 보존 (추천)” 선택, 나머지 승인 v1 및 직접 API 유지한 v2 전체 승인 |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F01,F02 | C01,C02,C11 | V01,V07 | CLI/직접API trace |
| F03,F15 | C03,C18,C20 | V02,V13 | 기준선/최적화관계와benchmark |
| F04,F05,F06 | C04–C07 | V03,V04,V07 | 손그래프와framework통합 |
| F07 | C08 | V05 | 독립지표/비용 |
| F08 | C09,C10 | V06 | threshold·합친근거 |
| F09 | C01,C02,C11,C16 | V01,V07,V08,V12 | CLI/Mermaid |
| F10 | C12 | V08 | schema와동일데이터 |
| F11,F12,F13 | C07,C13,C14 | V04,V09,V10 | browser전이/페이지 |
| F14 | C12,C15 | V08,V11,V15 | 기존renderer·offline·README |
| F16 | C16,C17,C20 | V12,V13 | 오류/후속상태 |
| Q01 | C01–C10 | V02–V07 | 정확성/관계보존 |
| Q02,Q04 | C01,C03,C11,C18,C20 | V01,V02,V13 | 호출횟수/단계/benchmark |
| Q03 | C19 | V14 | browser생값/중앙값 |
| Q05 | C01,C02,C11,C12 | V01,V07,V08,V16 | 호환/전체pytest |
| Q06 | C13,C14 | V09,V10 | UI관측 |
| Q07 | C16,C17,C20 | V12,V13 | 실패신호/출력유지 |
| Q08 | C15 | V11 | escaping/offline |
| Q09 | C01,C02 | V15 | 구조/README검토 |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 8 |
| verifier invocations | 2 |
| open finding ids | none — verifier2 all16 accepted, VF01/VF02/VF03 closed |

Audit state:
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V01 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V02 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V03 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V04 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V05 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V06 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V07 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V08 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V09 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V10 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V11 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V12 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V13 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V14 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V15 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |
| V16 | 2 | coverage.json / execution-revision.json / pytest-run7.log / restoration-review.json / verifier2-audit.md | accepted | verifier2 current evidence accepted;151declared items accounted;3classes/4probes intended detected/restored; no blocking findings | correction6–8 impact assessed; unchanged dependencies retained explicitly; exactsource/artifactSHA restoration and focusedcheck preserve fullsuite7 scope |

Execution ledger:
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| G01 | none | none | main이HEAD/clean상태·active명세없음·CLI/builders/bottleneck/renderer/기존Tag-Manager측정을확인 | draft작성, 구현·테스트·기준선·verifier 미실행 |
| G00 | none | none | 사용자 2026-10-05 전체명세 승인 | v1 active, 작업 시작 |
| G02 | none | none | 작은 Kotlin/Python 원본관계와 Tag-Manager snapshot 고정, 원본CLI 기준실행 시작 | baseline 실행중; 원본 구현 변경 없음 |
| X01 | implementer usage limit | verified: gpt-6.1-sol 담당 실행 한도 소진 | 사용자에게 대체 모델 지정을 요청, 기준 측정은 계속 실행 | 구현 변경 전 중단, 모델 응답 대기 |
| G03 | none | none | 변경 전 Tag-Manager 실행 완료: 1238.087초, 추출1231.257초, 지표/후보5.212초, 출력1.552초, 스냅샷0.067초; 5417nodes/73747edges | 기준선 확보, snapshot hash 40acc8efd2d3ff9dabc5b88f7a5c29bbff4446cb09d9a69848ee5f8779fee99c |
| P01 | user pause | 사용자 선택: 한도 복구 후 이어가기 | 테스트 초안·원본 관계·스냅샷·미적용 frontend 초안을 보존하고 handoff 작성 | active 명세와 verifier0/2 유지, 구현 변경 없음 |
| R01 | user resume | 사용자 file-analysis-paused handoff 재개 요청 | lifecycle --resume 성공; base_commit/HEAD 일치; 불변 snapshot hash/343파일/1238.087초 기준선 확인; backend/frontend/test 분리 재개 | v1·verifier0/2 유지, 구현 진행 |
| R02 | browser launch sandbox failure | verified: sandbox Chrome launch SIGABRT/kill EPERM | 임시 headless Chrome 사전 점검을 require_escalated로 실행 | 동일 Chrome 사전 점검 exit0; 최종 browser suite도 sandbox 밖에서 실행 |
| R03 | independent evidence draft corrections | Tests의 Mermaid 관측·옵션 종류·관계 이름 존재 검사·graph 완료 관측·browser 실패 후 benchmark passed=true 초안 결함 | 독립 source 기대값/원본 HEAD public FastAPI baseline probe/공개 graph 완료 관측으로 보강 | 94개 collect exit0, 실제 suite 실행 시작; 모든 acceptance pending |
| R04 | main review observer import failure | verified: review script ROOT가 repo 상위 디렉터리를 가리킴 | parents[2]로 교정 후 공개 re.finditer·snapshot 관측을 실행 | 작은 관계 완전 일치; complete-text scan12개 각1회; dict/line/range cache 확인; scan-cache-review.json |
| R05 | performance investigation | 최적화 symbol228.759초, 추출224.455초; file-run1 221.140초 | 원본 관계·3회 측정을 계속 보존, backend source에서 여전히 남은 name×symbol loops 진단; native worker1초 sample 확인 | 모든 이름 대신 범위 내 등장 이름을 원래 이름 순서대로 조회하는 보정 접근 대기; 측정 중 소스 변경 없음 |
| R06 | full-suite failure; R06-PERF/R06-EVIDENCE | pytest-run1.log: 13failed/1035passed/1error/192subtests; file3회221.140/220.802/220.625초; browser root layoutstop observer 오류; fold selector/언어호출spy/PageRank 독립산술/기존CLI기준선 default-file 전환 결함 | correction batch1: 이름×심볼 loop 제거; helper layout.stop 관측; 승인 fold selector/명시symbol baseline/실제 public build spy/독립rank 방정식 교정; A05/F12 의무공백 보강 | 모든의무 pending 유지, verifier0/2; attempt1 timing/실패artifact 보존; 다음 실행은 새근거/보정 후 |
| R07 | suite2 failure; R07-ARTIFACT/R07-COMPAT | 3failed/1040passed/198subtests, pytest-run2.log; real file73.947/73.796/73.879초 중앙값73.879, raw관계완전일치, 두browser기준통과; benchmark raw_seconds에 마지막browser5개 값이 덮어씀; fastapi-template/android symbol bytehash 불일치 | correction batch2: file/browser 변수 분리와 raw-vs-run 일치검사; 남은2symbol byte차이를 원본HEAD 출력으로 비교진단 | artifact수정 및 호환원인 진단중, baseline hash 유지; 모든의무 pending, verifier0/2 |
| R08 | R07-ARTIFACT resolved; R07-COMPAT confirmed spec challenge | corrected verify_artifacts exit0, raw file3 totals/median coherence; isolated original HEAD source outputs match immutable FastAPI/Android JSON+bottleneck hashes; current differences exclusively fallback-cost/token/hop/weighted-cost fields | baseline metadata.analysis counted in later cost fallback; merged adapter/global prior metrics cannot be reconstructed by one shared result without extra calculation. Async user decision: file-only single-pass + legacy symbol preservation (recommended), or all CLI single-pass + explicit symbol fallback-cost compatibility exception; direct API defaults preserved | artifact defect resolved; v1 expectations unchanged pending v2 approval; source frozen, verifier0/2 |
| R09 | v1 provisional suite interrupted after user v2 approval | 사용자 전체 테스트 재개 요청으로 artifact수정 후 suite3 실행; 진행 중 v2 file-only single-pass 정책을 명시 선택 | v1 suite3을 SIGINT 종료(exit130), pytest/benchmark worker 종료 확인; same run/원본 baseline/검증상한 보존 | v2 승인·correction batch3 시작; 완료 suite로 인정하지 않음, verifier0/2·mutation0 |
| R10 | direct-API golden setup failure | 原HEAD public default4builder→bottleneck before/after/fullreport 관측을 동일 V01 fixture로 확보; focused4테스트는 첫builder 단계 정확일치 후 build_snapshot 인수누락으로 실패 | Tests가 원본 관측과 동일한 snapshot(FILES,root=...) helper로 교정, 원본골든·bytehash·기대값 유지; 공통4variants 대응 | correction batch4, samev2; focused 재확인 후 전체 suite 대기, verifier0/2 |
| R11 | suite4 passes but valid Unicode file rejected | pytest-run4.log 1041passed/200subtests, median74.956s/관계완전일치/browser통과/legacy symbol byte모두일치; public Python a.py=value="a\u2028b"(13chars,no terminalLF) raw spans1..1→file span1..2→BottleneckInputError | file span contract A04=splitlines vs validator legacy LF bounds 충돌. file architecture만 cached splitlines bounds로 검증하고 symbol bounds 그대로 유지; 기존 V05 whole-text 의무에 독립 cost4/char13/line2/span1..2 관측 보강 | correction batch5, same approvedv2/no policychange; source 수정 후 전체 fresh suite/independentaudit 필요, verifier0/2 |
| R12 | correction5 full-suite success; R11-UNICODE resolved | current v2 validator and whole-text evidence | pytest-run5.log:1041passed/200subtests/652.82s, mandatoryskip0; file74.796/74.978/75.198s median74.978; rawrelation equality and browser criteria pass; reviews pin current hashes in execution-revision.json | all16 pending independent audit; verifier1/2 persisted before dispatch, prior acceptance none; shared-validator impact V01/V03/V05/V06/V07/V08/V12/V13/V16 executed, unchanged siblings also full-rerun |
| R13 | verifier1 complete retry: VF01-MERMAID-UNIT/VF02-BOUNDARY-BROWSER/VF03-CANDIDATE-SELECTION | verified evidence gaps: constant Mermaid passes substring; browser fixtures omit boundary; v5 candidate examples omit internal/ownership selection | all16/151items audited; no spec challenge; correction6 adds only observations of approved F09/A02/A05 to existing scenarios; implementer source unchanged | verifier1/2; other12 accepted at suite5; V04/V06/V08/V09/V10/V16 reopening for impacted Tests/full regression; selected3 strongest mutations correspond to3blocking classes, outweigh supplementary already-strong pair/cost assertions |
| R14 | focused correction6 1failed/36passed; VF01 expected snapshot mismatch | verified: directAPI manually supplied FILES includes.env, pinned-original CLI scanner excludes.env; actual original CLI selectedsourcepaths3 match current; probe lookup/tmp defaultTMPDIR failed and regenerated explicit/tmp fixture | original HEAD public CLI --json source captured mermaid-original-architecture.json/provenance; same FILES hash, old symbol stdout unchanged; V08expected source switched from directAPI to originalCLI target | correction7 evidence-only, v2 unchanged; other36 core/internal-ownership/browserboundary/symbolMermaid checks pass; V08/V16 pending fresh execution/audit2 |
| R15 | focused correction7 pass | original CLI selectedsource3 vs explicitAPI4 distinction proven, immutableCLIgoldenSHA guarded | V08two modes2passed0.23s; correction6 other36passed retained; common performance/browser helpers unchanged; suite6 started | autoapproval first attempt timedout before process start, permitted1retry succeeded; current suite6inprogress; verifier1/2, mutations0/no seed |
| R16 | correction7 full suite6 passes; first confirming mutation started | current Tests observations close expected-source/setup gaps, all Implementation unchanged | pytest-run6.log1041passed/200subtests/654.08s, median74.931; attempt6 revision saved; seedbackup CLIhash8b23f5... confirmed, constantMermaid mutation injected | exact full Test command inprogress, restore guaranteed in finally; verifier1/2 retained; intended V08file/symbol node-relation assertions; mutations.json records injectedSHA |
| M01 | constant selected-unit Mermaid defect detected | mutation executed: CLI sourceSHAc33830...; expected nodes/relations violated | mutation1-mermaid.log:3failed/1038passed/197subtests; intendedV08file1vs3declarednodes andsymbola/main.pyvsoriginalapp/router fail; additionalNestRootfailure | CLIrestoredSHA8b23f5...exactmatch, seedremoved; VF01confirmingmutationpass,1of3done; temporaryseedrestoration creates no permanent source dependencychange; Tests/fullsuite6 revisionretained |
| M02 | source-less boundary browser inclusion detected | mutation executed: frontend isFile exclusion disabled, injectedSHAb07c2f... | mutation2-boundary.log:1failed1040passed200subtests; intendedV10all-category three-file list gains external-boundary, exactsetassertion fails | app.jsrestoredSHA13453b...exactmatch/seedremoved; VF02confirmingmutationpass,2of3done; originalsourcebehavior/evidence dependencies unchanged after restoration |
| M03 | file-internal actual dependency evidence loss detected | mutation executed: injectedSHA6e060b... drops actualsame-file detailsedges beforecandidate collection | mutation3-candidates.log:2failed1039passed200subtests; intendedV06spread0vs1 andunresolveduniqueinternal line4missing fail | core.pyrestoredSHA4b4f7b...exactmatch/seedremoved; VF03confirmingmutationpass, selected3classes detected; originalsourceunchanged |
| R17 | VF01-MERMAID-RELATIONS required observation refinement | main confirmed originalV08file projection edgesempty, so filearrow omission could escape selected-unit relation assertions although symbol6edges andfile3nodes are covered | correction8 strengthens SAMEexisting V08example with prefix from models import User; globalFILES/directAPI/originalstandalone goldens unchanged; originalHEAD publicCLI captures linked graph IMPORTS+IMPORTS_SYMBOL main.py→models.py; no added variant/coverage policy | V08/V16 reopened; priorconstantnode-unit mutation retainedhistory; repeat SAMEselectedMermaid class with relation-omission probe on newevidence; other2classes remainvalid unchangeddetectingfunctions/helpers/source; verifier1/2 retained |
| R18 | correction8 focused observations pass | SAMEV08fixture linkedsource independently originalCLI captures2nonemptyfilearrows; globalFILES/goldens untouched | V08file/symbol+defaultdirect4API6passed0.87s; commonhelpers/core/browserdetectingfunctions unchanged, M02/M03retained scopeddependencies; fullsuite7started | sourceallrestored/no seed; SAMEMermaidclass requires relationomission reprobe after newTestevidencerevision; no fourthdistinctclass/expectationamendment/verifierreset |
| R19 | user interrupted conversation for duration, then requested check/resume | verified: suite7session9122 remainsrunning; recent optimizedsymbol/file1timing writes prove progress; seednone and all3sourcebeforeSHA match | retained existing in-flight exactTestcommand, no duplicate/restart; explicitremainingwork SAMEMermaidclass relationprobe andfreshverifier2 | counters8corrections/1verifier unchanged; aftertemporaryprobe restore exactsourceSHA, reuse savedclean suite7evidence and focusedMermaid validation; no additional whole-suite repetition without permanentdependencychange ornewfailure |
| R20 | correction8 fullsuite7 passes after conversation interruption | suitecontinued withoutrestart, sourcealloriginalrestored | pytest-run7.log1041passed/200subtests/680.26s, median77.838; complete immutable relation equality/browsercriteria/oldsymbolbytes/directAPI pass; attempt7containscleanrevisionandHTML/timings/browserSHAmanifest | currentexactTestcommand baseline is currentTests8/sourcebeforeM04; repeatSAMEMermaidclass once, exactsourceSHArestore and savedcleanartifacts/relevantfocusedcheck retaincurrentacceptance; freshverifier2next, no addedwhole-suite retry |
| M04 | SAMEselectedMermaidclass relation-loss reprobe detected | mutation executed: CLIinjectedSHAb6729f... retainsnodes butdropsarrows | mutation4-mermaid-relations.log2failed1039passed200subtests; intendedfile0vs2IMPORTS arrows andsymbol0vs6originalarrowsfail | CLIoriginalSHA8b23f5...restored; 3distinctclasses/4executed probes allintendeddetected, nooutstandingseed; otherM02/M03dependenciesunchanged |
| R21 | final current-revision evidence ready; audit2dispatch | savedcleanfullsuite7 source/Test hashesallmatch aftertemporaryrestore; normalperformance/browser/HTML13files restoredbySHA fromattempt7, not mutant evidence | restoration-review.json+focusedV08two cases2passed0.27s+seednone+diffcheckpass; baseline1238.087→cleanmedian77.838s; source/rawrelationships/API/symbolbytes remainpreserved | verifier2/2 persistedbeforedispatch; no furtherwhole-suite retry required: currentfullsuite7predatesonlyexactrestoredtemporaryprobe; all3addressedfindingspendingfreshfinalaudit |

| R22 | verifier2 final pass and closure | fresh independent audit confirms all16current accepted/151declareditems, no blocking/spec/advisory findings | verifier2-audit.md reaudits affected6 andretains10 by explicitdependencyassessment, checks13positive artifactSHAs/originalMermaid/Testhashes/rawequivalence; all3classes4probes intendeddetected/restored | VF01/VF02/VF03 closed; correction8/verifier2of2 preserved; statuscomplete, no outstandingbackup; archive and stale completedhandoffs, no commitrequested |

승인 후 순서:
1. lifecycle start를 확인한다. 같은 명세로 테스트 담당이 기준선 실행기를 준비하고 main이 변경 전 기준선을 확보한다. 구현 담당은 기준선 완료까지 구현 변경을 기다린다.
2. implementer와 test-implementer가 같은 버전으로 분리 수행한다. 서로 구현 소스·테스트·보고서를 읽지 않는다. main이 두 보고서를 조정한다.
3. main이 Test command를 유한 timeout으로 실행한다. 기준선은 기존 약20분 기록을 고려해3600초, 최종전체suite는7200초, 성능각file실행은600초 상한이다. timeout은 실패로 조사하며 새근거없이같은실행을반복하지않는다.
4. suite 합격 후 카운터를 먼저 기록하고 fresh test-verifier가 전체의무를 독립감사한다. 중단/실패도 포함해 최대2회다.
5. main이 가장 강한 서로 다른2–3결함 종류를 선택해 순차적으로 seed backup→mutation→Test command→restore를 수행한다. 첫 제안은 pair가중치합산·symbol텍스트중복비용·후보/원본근거유실이며 최종선택근거와 의도한 assertion의 검출을기록한다. mutation미실행/다른실패원인은불충분증거다.
6. 모든필수의무의현행증거·독립감사·mutation합격과 열린필수지적0일때만complete/보관한다. 검증상한·외부차단·사용자결정대기는스킬에따라명세와handoff를유지한다.

# Version Log
## v1
- 사용자 계획의 범위·성능·호환·검증상한을 보존해 구체화했다. A01–A06, 새signature/JSON계약/유한coverage집합을 포함해 사용자가 승인했다.

## v2
- 사용자 2026-10-06 전체 v2 정책 승인: file만 최종 GraphAnalyzer1회와 결과 재사용; symbol은 원본 반복 계산·순서·fallback 비용·출력값 보존, 직접 API 기본 동작 유지.
- F01/F02/C01/Q04/V01의 단일 계산 적용 단위를 file로 한정하고 A07에 원본 byte 진단과 선택 이유를 기록했다. V08/V16은 원본 symbol byte baselines를 계속 사용하며 갱신하지 않는다. 다른 functional/quality/coverage 기대값·성능 기준·verifier0/2·과거 시도는 그대로다.
