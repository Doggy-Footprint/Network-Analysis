---
version: 2
run_id: 8fd668e309160b58
status: complete
base_commit: d9e563db0e74f01b98b8a9747c8eb352f296c1f0
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
|---|---|---|---|
| I1 | maintainer | agent 행동 모사 코드를 파이프라인에서 떼어 보관 | agent_view, probe/harness profile, M1 보고서가 `archive/`에 있고 활성 코드가 import하지 않음 |
| I2 | maintainer | FastAPI 동적 분석 제거 | `dynamic_analyzer.py`와 `--app` 옵션이 없음 |
| I3 | maintainer | 불확실한 엣지를 버리지 않되 중심성에서 할인 | 설정 파일의 가중치가 PageRank·HITS·weighted fan에 반영되고 기본 0.3 |
| I4 | maintainer | 탐색 모사 없는 병목 보고서 | `bottlenecks.v3` JSON/HTML이 의존성 네트워크와 정적 후보만 담음 |

# Scope
In scope: archive 이동, CLI 옵션 정리, 스냅샷 정책을 `profiles/snapshot.v1.yaml`에서 로드, 엣지 가중치 설정 로더, 가중 PageRank/HITS, weighted_fan_in/out, bottlenecks.v3 JSON·HTML, agent-docs stale 처리.
Out of scope: 새 framework 엣지 추가, betweenness·hop 비용 가중, archive 코드의 동작 보장·테스트 실행, TS 스냅샷 import handoff.

# Paths
Implementation: archive/, agent_view/, report/m1/, bottlenecks/, analysis/, code_analyzer/cli.py, repository/scan.py, framework_analyzers/fastapi/, profiles/, report/bottlenecks/, README.md, agent-docs/handoff/, agent-docs/issues/, adr/
Tests: tests/, fixtures/
Test command: .venv/bin/python -m pytest -q
Review evidence: R1 — `grep -rnE "^\s*(from|import)\s+(agent_view|report\.m1|archive)" --include=*.py analysis bottlenecks code_analyzer framework_analyzers language_analyzers renderers report repository` 출력이 비어 있음 (tests/test_architecture_boundaries.py가 자동화하면 그것으로 대체)

# Signatures
analysis/edge_weights.py: `class EdgeWeightsError(ValueError)`
analysis/edge_weights.py: `@dataclass(frozen=True) class EdgeWeights: id: str; version: int; content_hash: str; confidence: Mapping[str, float]; resolution: Mapping[str, float]; large_node_line_threshold: int` + `def weight_for(self, edge) -> float`
analysis/edge_weights.py: `def default_edge_weights_path() -> Path`  # profiles/edge_weights.v1.yaml
analysis/edge_weights.py: `def load_edge_weights(path: str | Path) -> EdgeWeights`
analysis/graph_metrics.py: `GraphAnalysisConfig(..., edge_weights: Optional[EdgeWeights] = None)`  # None = 모든 엣지 1.0
analysis/graph_metrics.py: `def pagerank(outgoing: Mapping[str, Mapping[str, float]] | Mapping[str, Set[str]], config=None) -> Dict[str, float]`
bottlenecks/core.py: `def analyze_bottlenecks(snapshot: RepositorySnapshot, architecture: Any, weights: EdgeWeights) -> BottleneckReport`
bottlenecks/core.py: `def bottlenecks_to_json(report: BottleneckReport) -> str`
CLI: `--edge-weights PATH` (기본 profiles/edge_weights.v1.yaml). 제거: `--agent-view`, `--agent-view-profile`, `--agent-view-diff`, `--harness-profile`, `--app`.

profiles/edge_weights.v1.yaml:
```
id: edge_weights
version: 1
confidence: {static_certain: 1.0, static_inferred: 0.3, framework_inferred: 0.3, dynamic_required: 0.3}
resolution: {exact: 1.0, unique_name: 1.0, ambiguous: 0.3, unresolved: 0.3}
large_node_line_threshold: 2000
```

# Functional Requirements
| id | requirement | priority | source |
|---|---|---|---|
| F1 | `agent_view/`, `report/m1/`, 구 bottlenecks probe/harness 코드(`HarnessProfile`, `parse_harness_profile`, `replay_probe`, probe 후보), `profiles/agent_view.v3.yaml`, `profiles/harness.fixed-baseline.v1.json`, 해당 전용 테스트가 `archive/` 아래로 이동(git mv)하고 원래 위치에 없음 | must | I1 |
| F2 | 활성 패키지(analysis, bottlenecks, code_analyzer, framework_analyzers, language_analyzers, renderers, report, repository)가 agent_view·report.m1·archive를 import하지 않음 | must | I1 |
| F3 | `framework_analyzers/fastapi/dynamic_analyzer.py` 삭제, fastapi `__init__` export 및 CLI `--app` 제거 | must | I2 |
| F4 | CLI 스냅샷은 `repository.policy.load_scan_policy(default_scan_policy_path())`의 정책과 `tracked_files_only`로 생성 | must | I1 |
| F5 | `load_edge_weights`는 위 스키마를 검증: 키 집합 정확 일치, confidence/resolution 각각 enum 값 전부 존재, 가중치는 0 < w ≤ 1 수치(int 허용·float로 변환, bool 제외), threshold는 양의 정수, version ≥ 1 정수. content_hash = 파일 바이트 sha256 | must | I3 |
| F6 | 엣지 가중치 = min(confidence[edge.confidence], resolution[edge.resolution]). `GraphEdge.weight` 필드는 무시 | must | I3 |
| F7 | 동일 (source,target) 쌍의 여러 엣지는 가중치 max로 병합. self-loop·미존재 노드 엣지 제외(기존과 동일) | must | I3 |
| F8 | PageRank: source의 기여를 out 가중치 비율(w/Σw)로 분배. dangling 처리·damping(0.85)·tolerance(1e-10, L1)·max_iterations(100)은 기존과 동일; 반복 상한 도달 시 정확해와의 차이는 허용 | must | I3 |
| F9 | HITS: authority(t)=Σ hub(s)·w(s,t), hub(s)=Σ authority(t)·w(s,t), 이후 기존 L2 정규화 | must | I3 |
| F10 | node_metrics에 `weighted_fan_in`=Σ 들어오는 병합 가중치, `weighted_fan_out`=Σ 나가는 병합 가중치 추가. `fan_in`/`fan_out`(개수), betweenness, degree, hop_2/3 비용은 가중치와 무관하게 기존 값 | must | I3 |
| F11 | 모든 가중치가 1.0이면 모든 지표가 가중치 도입 전 구현과 동일 | must | I3 |
| F12 | `analyze_bottlenecks` 결과 schema `bottlenecks.v3`: 최상위 키 = {schema, snapshot, edge_weights, versions, coverage, dependency_network, candidates, limitations}. edge_weights = {id, version, content_hash, confidence, resolution, large_node_line_threshold}. rankings 키에 weighted_fan_in, weighted_fan_out 추가 | must | I4 |
| F13 | 줄 수 = end_line - start_line + 1. candidates kind는 `unresolved_boundary`(기존 규칙), `evidence_spread`(한 타깃을 가리키는 evidence 엣지들의 파일 수 > 1 이거나, 단일 파일일 때 max(end)-min(start)+1 > large_node_line_threshold; metrics {file_count, line_span, line_threshold}), `large_node`(architecture 노드 span 줄 수 > threshold; metrics {line_count, line_threshold}; evidence {path,start_line,end_line}). id·정렬 규칙 기존과 동일 | must | I4 |
| F14 | CLI `--bottlenecks`는 `--edge-weights`만으로 동작(harness profile 불필요). `--edge-weights`는 모든 언어/프레임워크의 GraphAnalyzer 호출에 적용 | must | I3, I4 |
| F15 | `report/bottlenecks` HTML 렌더러가 v3를 검증·렌더링하고 probes/exploration 섹션이 없음. v2 입력은 검증 오류 | must | I4 |
| F16 | `repository/scan.py`의 `_is_agent_view_artifact` 판정 제거(해당 파일도 일반 파일로 스냅샷에 포함) | must | 사용자 결정 |
| F17 | agent-docs: handoff 36233e8bd84b6f88, issue 71544b671815742f를 stale 처리(규칙 4). | must | 사용자 결정 |

# Errors
- 가중치 파일 없음/읽기 실패/YAML 오류/스키마 위반 — `EdgeWeightsError`(메시지에 원인); CLI는 stderr `[!] Error:` + exit 1, 어떤 출력 파일도 쓰지 않음
- 제거된 CLI 옵션 사용 — argparse 오류 exit 2
- v2/형식 오류 JSON을 HTML 렌더러에 입력 — 기존 검증 오류 경로, 출력 파일 없음
- 스냅샷 불일치 입력 to analyze_bottlenecks — `BottleneckInputError`(기존)

# Cases
| id | level | input / state | expected result |
|---|---|---|---|
| C1 | normal | 기본 yaml 로드 | 값이 위 표와 일치, content_hash=sha256(bytes) |
| C2 | normal | A→B static_certain/exact, A→C framework_inferred | out 분배 B:1/1.3, C:0.3/1.3 비율 |
| C3 | normal | A→B에 certain 엣지와 inferred 엣지 동시 존재 | 병합 가중치 1.0, fan_in(B)=1 |
| C4 | normal | exact confidence + ambiguous resolution | 가중치 0.3 (min) |
| C5 | boundary | 가중치 1.0 전부인 설정 | 모든 지표가 가중치 없는 결과와 같음 (F11) |
| C6 | boundary | 가중치 값 1.0 허용, 0 / 1.0000001 / 음수 거부; threshold 1 허용, 0 거부 | 허용/EdgeWeightsError |
| C7 | boundary | span 줄 수 = threshold, threshold+1 | large_node 없음 / 있음 |
| C8 | error | 키 누락, 여분 키, enum 값 누락, bool/문자열 가중치, 파일 없음, 잘못된 YAML | EdgeWeightsError; CLI exit 1, 출력 없음 |
| C9 | error | CLI `--agent-view x`, `--app x`, `--harness-profile x` | argparse exit 2 |
| C10 | edge | 빈 스냅샷 | v3 보고서, node/edge 0, rankings 빈 목록 |
| C11 | edge | self-loop만 있는 엣지 | 무시, weighted_fan 0 |
| C12 | normal | CLI 전체 실행(python fixture, --bottlenecks, --bottlenecks-html) | v3 JSON과 HTML 생성, 동일 입력 2회 실행 시 JSON 바이트 동일 |
| C13 | normal | 활성 코드 import 검사 | agent_view/report.m1/archive import 없음 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
|---|---|---|
| Functional suitability | yes | 지표 정확성 핵심 |
| Performance efficiency | no | 복잡도 불변(가중합으로 대체) |
| Compatibility | no | v2→v3는 의도된 파괴 변경 |
| Interaction capability | no | CLI 오류는 Errors/F로 커버 |
| Reliability | yes | 결정성: 동일 입력 동일 출력 |
| Security | no | 로컬 정적 분석, 새 입력면은 yaml.safe_load |
| Maintainability | yes | 보관 코드와 활성 코드 분리 |
| Flexibility | no | 설정 교체는 F5/F14로 커버 |
| Safety | no | 해당 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
|---|---|---|---|---|---|---|
| Q1 | Reliability / faultlessness | bottlenecks_to_json 결정성 | 같은 입력 2회 실행 JSON 바이트 비교 / 불일치 수 | = 0 | automated (C12) | AGENTS.md 결정성 |
| Q2 | Maintainability / modularity | 활성 패키지 → archive 의존 | 금지 import 수 (AST 검사) | = 0 | automated + R1 | I1 |

# Verification Obligations
| id | parent | variant and target surface | test layer and selection policy | technique | coverage items | coverage target | observation and expected result | evidence procedure |
|---|---|---|---|---|---|---|---|---|
| V1 | F5,C1,C6,C8 | load_edge_weights | unit | boundary value (2-value) + equivalence partitioning | 가중치 {0,최소양수,1.0,1.0초과,음수,bool,str}, threshold {0,1}, 키 {누락,여분}, enum 누락, 파일 없음, YAML 오류 | 100% | 허용/EdgeWeightsError, hash | pytest |
| V2 | F6,F7,C3,C4 | EdgeWeights.weight_for + 병합 | unit | decision table | confidence 4 × resolution 4 중 각 행/열 값 1회 이상(each choice) + 중복 쌍 병합 | 100% each choice | min 규칙·max 병합 | pytest |
| V3 | F8,F9,C2 | GraphAnalyzer pagerank/hub/authority | unit | 독립 손계산 oracle 소형 그래프 | 3노드 가중 그래프 1개, 분기 가중 hub 그래프 1개 | 100% | 손계산 값 ±1e-9 | pytest |
| V4 | F11,C5 | 전 지표 | unit | metamorphic | 가중치 1.0 설정 vs edge_weights=None, 기존 fixture 그래프 ≥2 | 100% | 전 node_metrics 동일 | pytest |
| V5 | F10,C11 | weighted_fan, 비가중 지표 불변 | unit | equivalence partitioning | inferred 엣지 포함 그래프에서 betweenness/hop/fan 개수가 가중치 0.3 vs 1.0 동일, weighted fan 값 | 100% | 명시 값 | pytest |
| V6 | F12,F13,C7,C10 | analyze_bottlenecks v3 | unit | boundary value + equivalence | 최상위 키 집합, rankings 키, large_node 경계 2값, evidence_spread 임계, unresolved_boundary, 빈 스냅샷 | 100% | 명시 구조·후보 | pytest |
| V7 | F14,F4,F3,C9,C8,C12,Q1 | CLI | integration (main() 호출) | scenario | 성공 실행, 제거 옵션 3종, 잘못된 가중치 파일, 2회 실행 결정성, 스냅샷 정책 로드(snapshot.v1 제외 규칙 적용 확인 1건) | 100% | exit code, 파일 존재/부재, 바이트 동일 | pytest |
| V8 | F15 | report/bottlenecks render | unit | equivalence partitioning | v3 정상, v2 입력, probes 섹션 부재 | 100% | 렌더 성공/오류, HTML에 probe 문구 없음 | pytest |
| V9 | F1,F2,F16,Q2,C13 | 저장소 구조 | unit | equivalence partitioning | 활성 패키지 AST import 검사; agent_view/, report/m1/, dynamic_analyzer.py 부재; archive 경로 존재; _is_agent_view_artifact 부재 시 agent_view 형태 JSON이 스냅샷에 포함 | 100% | 명시 | pytest + R1 |
| V10 | F17 | agent-docs | review | none — 문서 이동 | index/stale.md/stale/ 반영 | 100% | 파일 위치 | main 확인 |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
|---|---|---|---|
| A1 | dynamic_required, unresolved도 0.3, unique_name은 1.0 | 사용자는 "확정 아닌 엣지 전부"=STATIC_INFERRED/FRAMEWORK_INFERRED/AMBIGUOUS 선택; 나머지는 미정 | 사용자 승인 2026-09-29 |
| A2 | confidence·resolution 결합은 min | 두 축 모두 불확실성; 곱은 이중 할인 | 사용자 승인 2026-09-29 |
| A3 | large_node 기본 2000줄 | 앞서 "200줄"이라 제시했으나 실제 harness read.max_lines = 2000 | 사용자 승인 2026-09-29 |
| A4 | 기존 테스트 중 agent_view/M1/probe 전용 테스트는 archive/tests/로 이동, pytest testpaths(tests) 밖이므로 실행 안 됨 | archive는 보관 목적 | 사용자 승인 2026-09-29 |
| A6 | YAML 정수 가중치 허용(1 → 1.0) | 구현 기존 동작 | 사용자 승인 2026-09-29 |
| A5 | ADR 77ee4cf0(versioned profile)는 유지 — 동일 원칙을 edge_weights에 적용 | 원칙이 계속 유효 | 사용자 승인 2026-09-29 |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
|---|---|---|---|
| F1,F2,F16 | C13 | V9 | pytest, R1 |
| F3,F4,F14 | C9,C12 | V7 | pytest |
| F5 | C1,C6,C8 | V1 | pytest |
| F6,F7 | C3,C4 | V2 | pytest |
| F8,F9 | C2 | V3 | pytest |
| F10 | C11 | V5 | pytest |
| F11 | C5 | V4 | pytest |
| F12,F13 | C7,C10 | V6 | pytest |
| F15 | — | V8 | pytest |
| F17 | — | V10 | review |
| Q1 | C12 | V7 | pytest |
| Q2 | C13 | V9 | pytest, R1 |

# Workflow Control
| item | value |
|---|---|
| correction batches used | 3 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state:
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
|---|---|---|---|---|---|
| V1–V9 | 2 | tests/ @ 537 passed | accepted | verifier#2 PASS; M1–M4 검출 | — |
| V10 | 2 | agent-docs stale 이동 | accepted | main review | — |

Execution ledger:
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
|---|---|---|---|---|
| 1 | V3 PageRank 3건 1.3e-8 오차 | verified: 이분 주기 그래프에서 max_iterations 100 도달(0.85^100≈9e-8) — test defect | 오라클 허용오차를 반복 상한 반영 또는 config max_iterations 상향 | 수정 완료, 499 passed |
| 1 | V6 evidence_spread 2000에서도 후보 | verified: 파일 수>1 규칙 — test defect | spec v2에 규칙 명시 | 수정 완료, 499 passed |
| 2 | verifier#1 F-1..F-5 증거 공백(F14 비python 경로, 잘못된 v3, 후보 정렬·span 출처·범위 계산, F5 version/threshold/root, bottlenecks 잔존 코드) | test gap | 테스트 보강 | 추가 테스트 중 2건 실패 → 렌더러 숫자 검증 누락(implementation defect) 수정, 531 passed |
| 3 | mutation M4(android 재계산 제거) 생존 | verified: 테스트가 bottlenecks JSON만 관찰 | --json stats.analysis 관찰 테스트 추가(5경로) | M4 검출, 537 passed |
| M | mutation M1 min→곱, M2 max→합, M3 >→>=, M4 android 가중 재계산 제거 | 가장 강한 결함 부류: 가중치 결합·병합·경계·전파 | seed backup/restore | 4건 모두 의도한 단언이 검출 |
| 1 | analysis.__all__ 정확 일치 단언 실패 | 새 export는 spec 미규정 — test defect | 단언을 기존 3개 포함으로 완화 | 수정 완료, 499 passed |

# Version Log
## v2
- Test command를 .venv/bin/python으로 교체(시스템 python에 pytest·yaml 없음). 테스트 역할 challenge 반영: 정수 가중치 허용(사용자 승인), 줄 수 정의, evidence_spread 규칙 명시, PageRank 매개변수·반복 상한 명시. V4 '기존 fixture'는 fixtures/가 네트워크 클론뿐이라 저장소 내 그래프 2개로 대체.
## v1
- Initial draft from user decisions (archive, dynamic 삭제, 가중치 0.3·max 병합·PageRank/HITS만, v3 보고서, large_node, snapshot.v1 정책, M1 archive).
