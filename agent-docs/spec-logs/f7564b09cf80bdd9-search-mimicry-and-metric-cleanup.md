---
version: 3
run_id: f7564b09cf80bdd9
status: complete
base_commit: e1709f09d6c31289e8ee2536b7fce618a147be39
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자(분석 도구 소유자) | 의존성 그래프 대신 텍스트·파일명 검색으로 대상을 찾는 "탐색 모방" 코드를 제거한다 | `identifier_file_count` 지표와 이름·파일명 매칭 TESTS 엣지가 출력에서 사라지고, 문자열 매칭 CONFIGURES 엣지는 `static_inferred`로 표시된다 |
| I2 | 사용자 | 정보가 겹치는 노드 지표를 통합하고 ADR로 남긴다 | node_metrics가 10개 지표만 담고, 스키마 버전이 오르며, ADR 파일과 index 항목이 존재한다 |
| I3 | 사용자 | 스냅샷을 우회하는 토큰 비용 디스크 재읽기·ast 재파싱 fallback을 archive로 옮긴다 | 활성 코드는 디스크를 읽지 않고, 옮긴 코드와 전용 테스트가 `archive/` 아래에 있다 |

# Scope
In scope: 아래 Paths의 Implementation 경로에서 지표·엣지 생성·스키마·보고서 정의를 변경하고, 해당 테스트를 갱신·이동·삭제한다. ADR 1건을 작성한다.
Out of scope: 새 지표·엣지 추가; `language_analyzers/core/positions.py` 삭제(Kotlin analyzer가 사용); `GraphNode.__post_init__` 주석 변경(`_cost_multiplier`가 여전히 `metadata["file_path"]`를 읽음); `GraphAnalyzer.analyze`의 `project_path` 매개변수 제거; `tests/*_evidence/`, `agent-docs/spec-logs/`, `archive/` 기존 파일 내용 수정(README 한 줄 추가 제외); 이전 스키마(v4/v5) 렌더링 호환; 이번 변경과 무관한 기존 dead code(`_first_line` 등) 정리; bitset 메모리 추정식 변경.

# Paths
Implementation: analysis/graph_metrics.py, bottlenecks/core.py, bottlenecks/identifier_occurrence.py, language_analyzers/core/enrichment.py, report/bottlenecks/generate.py, renderers/html/static/app.js, archive/token_cost_disk_fallback/, archive/README.md, agent-docs/adr/
Tests: tests/, archive/tests/
Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; fixture_root('futuramaapi')" && uv run -q --with-requirements requirements-dev.txt python -m pytest -q -p no:cacheprovider
Review evidence: R1 — main이 scratchpad 스크립트로 base_commit 워크트리와 현재 트리에서 (a) 시드 0..19 무작위 그래프(노드 10..300, bitset 경로를 타는 고밀도 그래프 포함)와 (b) 이 저장소 대상 CLI(`-l python`, `-f fastapi`, `-f sqlalchemy` × file/symbol)를 실행해, 남은 10개 지표·`top_pagerank`/`top_betweenness`/`top_weighted_cost`/`top_hop_2_cost`·`neighborhood_strategy` 선택 결과가 (a)에서는 완전히 같고 (b)에서는 차이 노드가 모두 제거된 TESTS 엣지 또는 CONFIGURES 가중치 변경의 끝점·그 2-hop 이웃으로 설명됨을 출력한다. R2 — 같은 스크립트가 600노드 고밀도·희소 그래프 각 1개에 대해 `GraphAnalyzer.analyze` 5회 중앙값 실행 시간을 base와 현재에서 측정해 출력한다. R3 — main이 생성된 HTML 보고서(file/symbol)를 브라우저로 열어 정렬·크기 선택 목록과 용어 tooltip에 제거된 지표가 없음을 확인하고 스크린샷을 scratchpad에 남긴다.
Fuzzing: none — 새 파서·입력 표면이 없고, 그래프 입력 공간은 V4 무작위 테스트와 R1 차등 비교가 다룬다.
Mutation tool: scratchpad `mutate.py`(AST 기반 비교·산술·불리언·상수·조건 삭제 연산자), base_commit 이후 변경된 Implementation Python 줄만 대상, 최대 30개 표본 seed 20261014, 테스트 명령 `uv run -q --with-requirements requirements-dev.txt python -m pytest -q -p no:cacheprovider -x tests/test_graph_metrics.py tests/test_exact_neighborhoods.py tests/test_symbol_graph_and_enrichment.py tests/test_bottlenecks_v3.py tests/test_report_bottlenecks_v3.py` 및 V1–V8 신규 테스트 파일, 생존율 임계 40%.

# Signatures
GraphAnalyzer.analyze(self, nodes: Sequence[Any], edges: Sequence[Any], project_path: Optional[str] = None) -> Dict[str, Any]  # project_path는 허용하되 사용하지 않음
analyze_bottlenecks(snapshot: RepositorySnapshot, architecture: Any, weights: EdgeWeights, *, analysis: Optional[Mapping[str, Any]] = None) -> BottleneckReport  # 변경 없음
render_report(payload: Any) -> str  # 변경 없음
enrich_repository(architecture, *, file_inventory=None, file_reader=None, snapshot=None)  # 변경 없음
RANKING_KEYS = ("pagerank", "betweenness_centrality", "weighted_centrality_cost", "fan_in", "fan_out", "weighted_fan_in", "weighted_fan_out", "hop_2_token_cost")

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F1 | 심볼 모드 bottlenecks `dependency_network.node_metrics`의 모든 행에 `identifier_file_count`, `identifier_file_count_by_context`가 없다. `bottlenecks/identifier_occurrence.py`는 존재하지 않는다 | must | I1, 계획 §1 |
| F2 | 보강 단계가 만드는 TESTS 엣지는 "기존 엣지 중 출발점이 테스트 노드이고 후보 대상 중 하나 이상이 운영 노드인 엣지"의 복제뿐이다. 복제 엣지는 원본의 confidence, resolution, evidence, candidates를 그대로 갖는다. "테스트 노드"는 flags에 `test`가 있거나 경로가 `is_test_path`에 해당하는 노드이고, 운영 노드는 그 밖의 노드다. 모든 relation이 복제 대상이며, 중복 제거 키는 base와 같은 `candidate_relation_key(source, target, TESTS, resolution, candidates)`라서 같은 키의 원본이 여럿이면 첫 원본 하나만 복제된다. 테스트 본문의 이름 출현, 테스트 파일명 stem만으로는 TESTS 엣지가 생기지 않는다 | must | I1, 계획 §1 |
| F3 | CONFIGURES 엣지의 생성 조건, 대상, evidence, metadata는 base와 같다. confidence만 `static_inferred`이고 resolution은 `exact`다 | must | I1, 계획 §1 |
| F4 | `GraphAnalyzer.analyze()`의 각 `node_metrics` 행과 bottlenecks node_metrics 행의 키 집합은 정확히 {token_cost, effective_token_cost, pagerank, betweenness_centrality, weighted_centrality_cost, fan_in, fan_out, weighted_fan_in, weighted_fan_out, hop_2_token_cost}이다. 노드 `metadata["analysis"]`도 같다 | must | I2 |
| F5 | `analyze()` 결과는 `top_hubs`, `top_hop_3_cost` 키를 갖지 않고, `top_pagerank`, `top_betweenness`, `top_weighted_cost`, `top_hop_2_cost`와 나머지 기존 키는 유지한다. BFS 경로만 쓴 경우 `neighborhood_strategy`는 `single_bfs_to_2_hops`이고, `exact_bitset`/`exact_hybrid`의 선택 조건은 base와 같다 | must | I2, A6 |
| F6 | 같은 nodes/edges/config 입력이면 남은 10개 지표 값과 남은 top_* 순위가 base와 같다(부동소수점 동일) | must | I2, 계획 검증 |
| F7 | bottlenecks `rankings`와 `rankings_by_category.<category>`의 키 집합은 정확히 RANKING_KEYS다 | must | I2 |
| F8 | 심볼 모드 bottlenecks `schema`는 `bottlenecks.v6`, 파일 모드는 `bottlenecks.v7`이며 `granularity: "file"`를 갖는다. `versions.analysis`는 `"4"`이다 | must | I2, A5 |
| F9 | 보고서 검증은 `bottlenecks.v6`(granularity 없음)과 `bottlenecks.v7`(granularity "file" 필수)만 받는다. 그 외 schema는 Errors의 E1로 실패한다 | must | I2 |
| F10 | `report/bottlenecks/generate.py`의 METRIC_DEFINITIONS와 `renderers/html/static/app.js`의 `definitions`에 hub_score, authority_score, degree_centrality, hop_3_token_cost, identifier_file_count가 없다. app.js의 `core` 6개(pagerank, betweenness_centrality, hop_2_token_cost, weighted_centrality_cost, fan_in, fan_out)와 순서는 base와 같다. 렌더링된 HTML의 정렬·크기 선택 목록과 용어 tooltip에 제거된 지표 이름이 없다 | must | I1, I2 |
| F11 | 노드 토큰 비용: cost.token_estimate가 양의 정수면 그 값, 0이고 metadata.boundary가 참이면 0, 그 외에는(cost 없음+boundary 포함) label/title/metadata JSON 추정값이다. 양의 cost는 boundary여도 그 값이다. 어떤 경우에도 디스크 파일을 읽거나 ast로 파싱하지 않는다. `GraphAnalyzer`에 `_source_for_line`, `_source_cache`, `_tree_cache`가 없고 `analysis/graph_metrics.py`는 `ast`를 import하지 않는다 | must | I3 |
| F12 | 옮긴 fallback 코드가 `archive/token_cost_disk_fallback/graph_metrics_fallback.py`에, 그 전용 테스트가 `archive/tests/` 아래에 있고, `archive/README.md`에 이를 설명하는 한 줄이 있다. 활성 패키지는 archive를 import하지 않는다 | must | I3 |
| F13 | 이웃 계산(bitset·BFS)은 2-hop 집합만 계산한다. 3-hop 집합·비용·노드 수를 계산하지 않는다 | should | I2 |
| F14 | `agent-docs/adr/<16hex>-consolidate-overlapping-metrics.md`가 Title/Status, Context, Decision, Alternatives, Consequences 섹션을 갖고 `agent-docs/adr/index.md`에 형식에 맞는 항목이 있다 | must | I2, AGENTS.md ADR 규칙 |
| F15 | bottlenecks `coverage.limitations`의 "Token cost fallback applies to nodes without a source span or explicit cost." 조건과 문구는 base와 같다 | should | 계획 §3 |

# Errors
E1: `render_report`/`generate`에 schema가 `bottlenecks.v6`/`bottlenecks.v7`가 아닌 payload(예: `bottlenecks.v4`, `bottlenecks.v5`) — `ReportInputError`, 메시지에 `$.schema` 포함 — 출력 파일을 쓰지 않음.
E2: `bottlenecks.v7` payload에 `granularity`가 없거나 `"file"`이 아님 — `ReportInputError`, 메시지에 `$.granularity` 또는 `$` 포함 — 출력 파일을 쓰지 않음.
E3: cost가 없거나 0(비경계)이고 metadata.file_path가 존재하지 않는 파일·스냅샷 밖 파일·읽을 수 없는 파일을 가리키는 노드 — 예외 없음(비예외 실패 신호 없음), token_cost는 JSON 추정값 — 분석 결과 정상 반환, 파일 접근 없음.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | 심볼 모드 CLI(`-l python`)로 작은 프로젝트 분석 | bottlenecks schema v6, node_metrics 키 10개, identifier_* 없음, rankings 키 8개 |
| C2 | normal | 파일 모드 CLI로 같은 프로젝트 분석 | schema v7, granularity file, node_metrics 키 10개, rankings 키 8개 |
| C3 | normal | 테스트 함수가 운영 함수를 호출(CALLS 엣지 존재) | 같은 쌍의 TESTS 엣지가 원본 confidence/resolution/evidence/candidates로 생김 |
| C4 | edge | 테스트 본문이 운영 클래스 이름을 문자열·주석에서만 언급하고 그래프 엣지 없음 | 그 쌍에 TESTS 엣지 없음 |
| C5 | edge | `test_foo.py`와 운영 클래스 `Foo`가 있고 엣지 없음 | TESTS 엣지 없음 |
| C6 | edge | 테스트→테스트 엣지만 존재 | TESTS 엣지 없음 |
| C7 | normal | `.env`의 `API_KEY`와 코드 문자열 `"API_KEY"` | CONFIGURES 엣지가 config 노드→소비 노드로 생기고 confidence `static_inferred`, resolution `exact`, metadata.occurrence_lines 유지 |
| C8 | boundary | 노드 cost.token_estimate = 0, metadata.boundary = true | token_cost 0 |
| C9 | boundary | 노드 cost.token_estimate = 0, boundary 없음, metadata.file_path가 실제 파일 | token_cost = JSON 추정값, 파일 내용 기반 값과 다름, 파일을 읽지 않음 |
| C10 | error | cost 없음, metadata.file_path가 존재하지 않는 파일 | 예외 없이 JSON 추정값 (E3) |
| C11 | normal | cost.token_estimate = 7 | token_cost 7 |
| C12 | error | `render_report({"schema": "bottlenecks.v4", ...유효 필드})`, v5+file 동일 | ReportInputError `$.schema` (E1) |
| C13 | error | v7 payload에서 granularity 누락 또는 `"symbol"` | ReportInputError (E2) |
| C14 | normal | v6, v7 유효 payload | HTML 문자열 반환 |
| C15 | boundary | 노드 63개 고밀도 그래프(bitset 하한 직전)와 64개 고밀도 그래프 | 각각 `single_bfs_to_2_hops`, `exact_bitset`; hop_2_token_cost가 brute-force BFS 값과 같음 |
| C16 | boundary | 연결 요소 하나는 bitset, 하나는 BFS 조건 | `exact_hybrid`, 전 노드 hop_2_token_cost가 brute-force 값과 같음 |
| C17 | edge | 빈 그래프, 단일 노드 | 예외 없음, 단일 노드 키 10개, hop_2_token_cost 0 |
| C18 | normal | HTML 보고서(file/symbol) 로드 | 정렬·크기 select 옵션과 tooltip에 Hub/Authority/Degree/3-hop/식별자 출현 파일 없음; core 카드 6개 순서 base와 같음 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 지표·엣지·스키마의 정확성이 작업의 본체 |
| Performance efficiency | yes | 이웃 계산을 2-hop으로 줄이므로 시간이 늘면 안 됨 |
| Compatibility | yes | 스키마 버전 변경, 저장소 내 소비자(CLI·통합 보고서) 공존 |
| Interaction capability | yes | HTML 보고서 선택 목록·용어 표시가 바뀜 |
| Reliability | no | 새 실패 경로가 없고 fallback 제거는 E3로 기능 요구에서 다룸 |
| Security | no | 새 입력·권한 경계 없음. 스냅샷 밖 디스크 읽기가 사라지는 방향뿐 |
| Maintainability | yes | 제거 대상 심볼 잔재 0, archive 격리 유지 |
| Flexibility | no | 설치·이식 환경 변화 없음 |
| Safety | no | 물리·인명 위해 경로 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Functional suitability / functional correctness | 남은 지표 값이 base와 같음 | R1(a): 무작위 그래프 20개에서 지표별 불일치 노드 수 / 노드 | 0, 같거나 작아야 통과 | review R1, automated V4 | F6 |
| Q2 | Performance efficiency / time behaviour | `GraphAnalyzer.analyze` 실행 시간 | R2: 600노드 고밀도·희소 그래프 각각 5회 중앙값, 현재/base 비율 | ≤ 1.05, 작을수록 좋음 | review R2 | F13 |
| Q3 | Compatibility / interoperability | 저장소 내 소비자(code_analyzer CLI, report.unified, report.bottlenecks)가 새 스키마로 끝까지 동작 | 기존 CLI·통합 보고서 테스트 통과 수 / 실패 수 | 실패 0 | automated V5, V8 | F8, F9 |
| Q4 | Interaction capability / appropriateness recognizability | 보고서에 제거된 지표가 노출되지 않음 | V8 browser 테스트, R3: 선택 목록·tooltip의 제거 지표 이름 출현 수 | 0 | automated V8, review R3 | F10 |
| Q5 | Maintainability / modifiability | 활성 패키지 잔재 | `grep -rnE "identifier_file_count\|hub_score\|authority_score\|degree_centrality\|hop_3\|_source_for_line\|_tree_cache\|_source_cache\|top_hubs\|identifier_occurrence"` over analysis bottlenecks report renderers language_analyzers code_analyzer framework_analyzers repository, 그리고 enrichment.py 내 `NamePositions` — 일치 줄 수 | 0 | automated V7 | F1, F4, F11 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | F1, F4, F5, F7, C1, C2, C17 | `GraphAnalyzer.analyze()` 반환값, `analyze_bottlenecks` 반환 payload, CLI `--bottlenecks` JSON | unit + integration; 각 파티션 대표 1개 | equivalence partitioning | P1 analyze node_metrics, P2 analyze top_* 키, P3 node metadata.analysis, P4 symbol bottlenecks node_metrics, P5 file bottlenecks node_metrics, P6 rankings, P7 rankings_by_category(모든 category), P8 빈/단일 노드 그래프 | 100% | 키 집합이 F4/F5/F7 목록과 정확히 같음; identifier_* 부재 | pytest |
| V2 | F2, C3–C6 | `enrich_repository` 결과 edges (snapshot 입력) | unit; 규칙당 1 케이스 | decision table | R1 테스트→운영 기존 엣지(복제, 속성 동일), R2 이름 출현만(없음), R3 파일명 stem만(없음), R4 테스트→테스트(없음), R5 운영→운영(없음), R6 ambiguous 엣지에서 후보 중 운영 노드 존재(복제, candidates 동일), R7 flag `test`만 있고 비테스트 경로인 출발 노드(복제), R8 flag 없이 `is_test_path` 경로인 출발 노드(복제), R9 CALLS가 아닌 relation(IMPORTS, READS 각각) 원본(복제), R10 같은 dedup 키를 갖는 원본 2개(relation 또는 evidence만 다름)(TESTS 1개, 첫 원본의 confidence·evidence), R11 대상이 flag `test`만 있고 비테스트 경로(없음) | 100% | TESTS 엣지 집합이 규칙 기대와 정확히 같음 | pytest |
| V3 | F3, C7 | `enrich_repository` CONFIGURES 엣지; 기본 edge weight에서 config 노드 weighted_fan_out | unit + integration | equivalence partitioning | K1 .env 키, K2 .json 키, K3 .yaml 키, K4 gradle buildConfigField, K5 가중치 효과(weighted 값 = confidence weight `static_inferred` 기준) | 100% | confidence `static_inferred`, resolution `exact`, evidence·metadata.occurrence_lines 기대값; K5 weighted 값 일치 | pytest |
| V4 | F6, F13, C15, C16 | `GraphAnalyzer.analyze` hop_2_token_cost·fan·neighborhood_strategy | unit; 고정 시드 무작위 그래프 | random testing | S1 BFS 전용 경로, S2 exact_bitset, S3 exact_hybrid, S4 경계 63/64노드 | 100% | hop_2_token_cost = 독립 brute-force(무방향 2-hop 집합의 token_cost × round(10×배율) / 10 합); strategy 값 F5 기대와 같음 | pytest + review R1 |
| V5 | F8, F9, E1, E2, C12–C14 | `render_report`, `generate`, `analyze_bottlenecks` schema/versions | unit | equivalence partitioning | A1 v6 수용, A2 v7+file 수용, J1 v4 거부, J2 v5 거부, J3 v7 granularity 누락 거부, J4 v7 granularity symbol 거부, J5 v6에 granularity 추가 거부, O1 symbol 출력 v6, O2 file 출력 v7, O3 versions.analysis "4" | 100% | 수용은 HTML 문자열, 거부는 ReportInputError와 지정 경로 메시지, generate 거부 시 write 미호출 | pytest |
| V6 | F11, E3, C8–C11 | `GraphAnalyzer.analyze` token_cost; 파일 접근 관찰(Path.read_text/open 감시 또는 존재 파일 내용 대비 값) | unit | decision table | D1 cost>0, D2 cost=0+boundary, D3 cost=0 비경계+실존 file_path, D4 cost 없음+실존 file_path+line_number/end_line_number, D5 cost 없음+부재 file_path, D6 cost 없음+file_path 없음, D7 cost 없음+boundary(JSON 추정값), D8 cost>0+boundary(cost 값) | 100% | D1·D8 값, D2 0, D3–D7 JSON 추정값(`estimate_tokens(json.dumps({"label","title","metadata"}, ensure_ascii=False, default=str))`), 파일 읽기 0회 | pytest |
| V7 | F1, F11, F12, F14, Q5 | 저장소 파일 트리 | unit(구조 검사) | equivalence partitioning | T1 Q5 grep 0줄, T2 identifier_occurrence.py 부재, T3 archive fallback 파일 존재·`_source_for_line` 포함, T4 archive/tests fallback 테스트 존재, T5 archive/README.md 언급, T6 ADR 파일 섹션, T7 adr/index.md 항목 형식, T8 graph_metrics.py에 ast import 없음 | 100% | 각 항목 기대 충족 | pytest |
| V8 | F10, Q3, Q4, C18 | 렌더링된 HTML(통합 보고서, playwright) 및 정적 정의 | end-to-end; file/symbol 각 1 | equivalence partitioning | H1 symbol 모드 select·tooltip, H2 file 모드 select·tooltip, H3 core 카드 6개 순서, H4 METRIC_DEFINITIONS 내용 | 100% | 제거 지표 이름·키 0회, core 순서 [pagerank, betweenness_centrality, hop_2_token_cost, weighted_centrality_cost, fan_in, fan_out] | pytest + review R3 |
| V9 | Q2 | `GraphAnalyzer.analyze` 실행 시간 | review | none — 측정 절차 | M1 고밀도 600, M2 희소 600 | 100% | 비율 ≤ 1.05 | review R2 |
| V10 | F2, F3, F5, F10, F15 | 전 표면 | unit/integration | error guessing | G1 TESTS 복제가 원본 속성 대신 고정 confidence를 씀, G2 CONFIGURES confidence 변경이 TESTS 복제·다른 relation에 번짐, G3 rankings_by_category에 제거 키 잔존, G4 app.js core slice가 다른 지표를 집음, G5 limitations 조건 변경, G6 3-tuple/4-tuple 언패킹 잔재로 hop_2 값이 node_count를 담음 | none — experience-based | 각 추측 결함이 테스트로 거부됨 | pytest |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v1 — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| A1 | `positions.py` 유지 | `language_analyzers/kotlin/analyzer.py:18`이 import | user answer (understanding round 확인) |
| A2 | `GraphNode.__post_init__` 주석 유지 | `analysis/graph_metrics.py` `_cost_multiplier`가 metadata.file_path를 읽음 | user answer |
| A3 | `analyze(project_path)` 매개변수 유지·무시 | 호출처 CLI·framework 4곳+테스트 다수; 제거는 별도 정리 | user answer |
| A4 | bitset 메모리 추정식 유지 | 3-hop 배열이 줄어 실제 사용량은 추정 이하; 전략 선택 동일성(F5) 보장 | brief v1 — approved |
| A5 | `versions.analysis` "3"→"4" | 지표 집합 변경을 소비자가 구분하도록 | user answer (올리기) |
| A6 | BFS strategy 값 `single_bfs_to_3_hops`→`single_bfs_to_2_hops` | 3-hop을 더 계산하지 않음; architecture JSON stats.analysis에 기록되는 값 | user answer (이름 변경 확인) |
| A7 | 기준선 O11 실패는 `.fixtures/futuramaapi` 부재 탓, Test command가 먼저 fixture를 확보 | fixture 확보 후 O11 통과 확인(1 passed, 8 subtests) | brief v1 — approved |
| A8 | ADR 지표 수 표기 16→10(계획의 "11"은 계산 오류) | 현재 node_metrics 16키 − 6 = 10 | brief v1 — approved |
| A9 | 과거 evidence JSON·로그는 수정하지 않음; characterization 테스트는 비교 helper에서 제거 지표를 빼는 방식으로 갱신 | 기록 보존 원칙 | user answer |
| A10 | METRIC_DEFINITIONS는 현재 참조처가 없지만 계획대로 항목만 제거 | grep 결과 정의만 존재 | brief v1 — approved |
| A11 | 변경으로 dead가 된 import·helper만 제거(예: enrichment.py의 NamePositions import, graph_metrics.py의 ast/Path) | 기존 dead code는 범위 밖 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F1 | C1 | V1, V7 | pytest |
| F2 | C3, C4, C5, C6 | V2, V10 | pytest |
| F3 | C7 | V3, V10 | pytest |
| F4 | C1, C2, C17 | V1 | pytest |
| F5 | C15, C16 | V1, V4, V10 | pytest |
| F6 | C15, C16 | V4 | pytest + R1 |
| F7 | C1, C2 | V1, V10 | pytest |
| F8 | C1, C2 | V5 | pytest |
| F9 | C12, C13, C14 | V5 | pytest |
| F10 | C18 | V8, V10 | pytest + R3 |
| F11 | C8, C9, C10, C11 | V6, V7 | pytest |
| F12 | — | V7 | pytest |
| F13 | C15, C16 | V4, V9 | pytest + R2 |
| F14 | — | V7 | pytest |
| F15 | — | V10 | pytest |
| Q1 | — | V4 | R1 |
| Q2 | — | V9 | R2 |
| Q3 | C1, C2, C14 | V5, V8 | pytest |
| Q4 | C18 | V8 | pytest + R3 |
| Q5 | — | V7 | pytest |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 1 |
| verifier invocations | 2 |
| open finding ids | none blocking; advisory: X1, A1, A3–A7, M4, M12, M21, R10 evidence-variant |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V1 | 2 | tests/test_search_mimicry_*.py, 갱신된 기존 테스트; full run 1349 passed | accepted | verifier 1 accepted | 공유 helper·해당 테스트 변경 시 재개 |
| V2 | 3 | tests/test_search_mimicry_enrichment.py R1–R11 | accepted | B1 보완; H3/H4/H14 killed (ledger 10) | verifier 2 재감사 |
| V3 | 2 | tests/test_search_mimicry_*.py, 갱신된 기존 테스트; full run 1349 passed | accepted | verifier 1 accepted | 공유 helper·해당 테스트 변경 시 재개 |
| V4 | 3 | tests/test_search_mimicry_metrics.py S1–S4; review R1(a) ledger 7 | accepted | 자동 부분 verifier 1 accepted; R1(a) 산출물 B2 → ledger 7 | 재감사 |
| V5 | 2 | tests/test_search_mimicry_*.py, 갱신된 기존 테스트; full run 1349 passed | accepted | verifier 1 accepted | 공유 helper·해당 테스트 변경 시 재개 |
| V6 | 3 | tests/test_search_mimicry_metrics.py D1–D8 | accepted | D1–D6 verifier 1 accepted, D7·D8 추가; H8 killed | verifier 2는 D7·D8만 감사 |
| V7 | 2 | tests/test_search_mimicry_*.py, 갱신된 기존 테스트; full run 1349 passed | accepted | verifier 1 accepted | 공유 helper·해당 테스트 변경 시 재개 |
| V8 | 2 | tests/test_search_mimicry_*.py, 갱신된 기존 테스트; full run 1349 passed | accepted | verifier 1 accepted | 공유 helper·해당 테스트 변경 시 재개 |
| V9 | 3 | review R2 (ledger 7: /private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-cleanup/7ad6a56a-06a7-494b-b32c-5c9046cac71a/scratchpad/review/dump_metrics.py time, r2.txt) | accepted | verifier 1 B2: 산출물 미기재 → ledger 7에 기록 | 재감사 |
| V10 | 2 | tests/test_search_mimicry_*.py, 갱신된 기존 테스트; full run 1349 passed | accepted | verifier 1 accepted | 공유 helper·해당 테스트 변경 시 재개 |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 0 | 기준선 pytest 1 failed: O11 `fastapi-futuramaapi` "Project path does not exist: .fixtures/futuramaapi" | verified: fixture 미확보 | `fixture_root('futuramaapi')` 실행 후 O11 재실행 | 1 passed, 8 subtests passed; Test command에 fixture 확보 단계 추가 |
| 1 | R1(a) 무작위 그래프 40케이스 차등 비교 | — | base 트리(scratchpad/base) 대비 남은 지표·top_*·strategy 비교 | 불일치 0 (Q1 충족) |
| 2 | R2 600노드 시간 3회 반복 | 첫 측정은 병렬 test-implementer 부하로 잡음 | 에이전트 종료 후 재측정 | dense 비율 0.85–0.97, sparse 0.48–0.73 (Q2 충족) |
| 3 | 전체 Test command: 1349 passed, 1 error — `test_file_analysis_benchmark.py::test_V13_real_snapshot_symbol_equivalence_and_three_processes` Tag-Manager `filter_page_ms` 중앙값 323 > 300 | hypothesis→verified: 측정 환경 편차, 변경과 무관 | scratchpad/bench에서 같은 Tag-Manager file 보고서를 base·현재 트리로 만들어 measure_html 3라운드 교대 측정 | base 302/306/313ms, 현재 319/306/308ms — base도 임계 초과, 차이 없음. 범위 밖 사전 환경 실패(X1)로 분류 |
| 4 | R1(b) 이 저장소 대상 CLI 6조합 base↔현재 | — | scratchpad/r1b/compare.py | 노드 집합 동일; 엣지 차이는 제거된 TESTS(file 761, symbol 2828–2829)와 CONFIGURES confidence 변경뿐; token_cost 차이 0; fan·가중 fan·hop_2 차이는 모두 제거 TESTS 끝점/CONFIGURES 끝점/그 2-hop 안 — 설명 안 되는 차이 0 |
| 5 | R3 브라우저 검토 | — | scratchpad/r3.py, r3_file.png, r3_symbol.png | file 29·symbol 22 옵션과 ReportGlossary에 제거 지표 0, core 카드 순서 일치 |
| 6 | 테스트 실행이 tests/*_evidence timing JSON을 다시 씀 | verified | git checkout으로 HEAD 복원 | 기록 보존(A9) |
| 7 | verifier 1 B2: R1(a)/R2 산출물 미기재 | verified | 산출물 명시: base 트리 `/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-cleanup/7ad6a56a-06a7-494b-b32c-5c9046cac71a/scratchpad/base` (= `git archive e1709f09`), 스크립트 `/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-cleanup/7ad6a56a-06a7-494b-b32c-5c9046cac71a/scratchpad/review/dump_metrics.py` (`<root> metrics` / `<root> time`), 출력 `/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-cleanup/7ad6a56a-06a7-494b-b32c-5c9046cac71a/scratchpad/review/base_metrics.json`·`cur_metrics.json`(sha256 앞 16자 둘 다 31922e779608096a), 비교 `/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-cleanup/7ad6a56a-06a7-494b-b32c-5c9046cac71a/scratchpad/review/r1a_compare.txt`, 시간 `/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-cleanup/7ad6a56a-06a7-494b-b32c-5c9046cac71a/scratchpad/review/r2.txt` | R1(a): 40케이스, 노드 5540, 불일치 0, strategy BFS 27·bitset 13. R2(각 값 = 5회 중앙값 초, base/현재): 1회 dense 2.603/2.218 sparse 0.218/0.121; 2회 dense 3.061/2.912 sparse 0.214/0.157; 3회 dense 3.016/2.776 sparse 0.250/0.119 → 비율 dense 0.85/0.95/0.92, sparse 0.56/0.73/0.47 |
| 8 | verifier 1 B1: F2 v2 조항 증거 공백 | verified: v2 보완 시 V2 coverage item을 늘리지 않은 spec 결함 | spec v3: V2에 R7–R11, V6에 D7·D8 추가; test-implementer 재투입 | 진행 중 |
| 9 | 손 mutation 14종(`/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-cleanup/7ad6a56a-06a7-494b-b32c-5c9046cac71a/scratchpad/hand_mut.py`, 결과 `/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-cleanup/7ad6a56a-06a7-494b-b32c-5c9046cac71a/scratchpad/hand_mut_1.txt`, seed.py backup/restore, 매 회 원복 확인) | 선택 근거: verifier 1이 제안한 강한 결함 부류(TESTS 복제 속성, CONFIGURES confidence, 테스트 노드 판정, relation 범위, dedup, 2-hop 깊이·시작 노드, bitset 경계, boundary 비용, schema/granularity 완화, RANKING_KEYS, limitations 조건, app.js core) | H1·H2·H5–H13 각 의도 assertion(V2_R1/G1, V3_K*, V4_S*, V6_D3, V5_J2/J4, V1_P6, G5, V8_H3)이 실패시킴 → killed | H3(flag만 판정)·H4(CALLS만 복제)·H14(dedup 없음) survived → B1 확인, correction batch 1로 V2 R7–R11 추가 요청 |
| 10 | correction batch 1 후 H3·H4·H14 재실행(`/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-cleanup/7ad6a56a-06a7-494b-b32c-5c9046cac71a/scratchpad/hand_mut_2.txt`) | — | V2 R7–R11, V6 D7·D8 테스트 추가 | H3→V2_R8, H4→V2_R9, H14→V2_R10 실패 → 모두 killed; B1 해소 |
| 11 | mutation 도구 `/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-cleanup/7ad6a56a-06a7-494b-b32c-5c9046cac71a/scratchpad/mutate.py` (pool 45, 표본 30, seed 20261014; 실행 전 4개 파일 사본 `/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-cleanup/7ad6a56a-06a7-494b-b32c-5c9046cac71a/scratchpad/pre_mut_*`과 cmp로 원복 확인), 결과 `/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-cleanup/7ad6a56a-06a7-494b-b32c-5c9046cac71a/scratchpad/mutation_tool.json` | — | 생존율 3/30 = 10% < 40% → mutant-triager | M4(core.py:250 snapshot `file_count` 키명), M12(generate.py:212 `$.schema` 경로 토큰 → `$.schema_m`, 여전히 `$.schema` 포함), M21(같은 줄 메시지 문구) 모두 undeclared. main 판정: M4는 이번 변경이 바꾸지 않은 기존 동작(같은 줄의 schema 문자열 때문에 표본에 포함), M12·M21은 E1 계약(`$.schema` 포함) 안의 문구 변화 → spec 요구 누락 아님, advisory로 종결 |
| 12 | correction batch 1 후 전체 Test command | X1 재현 | — | 1360 passed, 1 error(X1 동일), evidence 파일 변경 없음 |
| 13 | verifier 2 (최종) | — | V2 R1–R11, V6 D7·D8, V4 R1(a), V9, M4/M12/M21 처분 감사 | PASS, 차단 finding 없음; 기존 acceptance 유지 |

# Version Log
## v3
- [계약] verifier 1 B1: V2 coverage item R7–R11 추가(F2 v2 조항: 테스트 노드 판정 두 조건, 모든 relation 복제, dedup 키). V6에 D7·D8 추가, F11 문구 명확화(advisory A2, 동작 변경 없음). B2 산출물 ledger 7 기록. 감사 상태 갱신.

## v2
- 계약 보완(F2): test-implementer 질의에 따라 테스트/운영 노드 정의, 복제 relation 범위, 중복 제거 키를 base 동작 그대로 명시. 동작 변경 없음.
- Workflow Control·Execution ledger: 1차 구현·테스트 결과와 R1(a)/R2 결과 기록.

## v1
- 이전 세션 계획과 understanding round 확인을 바탕으로 초안 작성.
