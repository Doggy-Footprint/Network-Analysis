---
version: 4
run_id: f80bb8ba5e7ac1ef
status: complete
base_commit: 6fda6d5a91eee508088292ad8b428694ee70b32f
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자 | "Architecture 분석 기능을 추가하고 싶어. goal: keep AI written codes maintanable" | file 모드 bottleneck JSON에 file cycle, package 결합도, package cycle, 불안정 의존이 구조 사실 candidate로 나온다 |
| I2 | 사용자 | 언어·framework가 정의한 package를 쓰고, 정의가 없으면 디렉터리로 fallback | `agent-docs/adr/58424b9754efe9a2-package-grouping-schemes.md`의 `language`/`framework` 체계대로 package id가 생성된다 |
| I3 | 사용자 | 예전 symbol graph처럼 분량이 폭증하지 않을 것 | 실제 fixture에서 JSON 크기 증가와 계산 시간이 Q1/Q2 상한 안에 있다 |
| I4 | 사용자 | 거대한 cycle 문제를 tier별 candidate로 대응 | 같은 cycle이 certain ⊂ resolved ⊂ all tier별 candidate로 나오고 상위 tier candidate id를 가리킨다 |

# Scope
In scope: file granularity에서만, 기존 file architecture(`analysis/file_graph.py:to_file_architecture` 결과)를 입력으로 받는 후처리. file SCC 기반 `dependency_cycle`, `language`·`framework` 체계 package 지표, `package_cycle`, `unstable_dependency` candidate. `bottlenecks.v8` schema. report validator와 HTML에서 새 kind 표시(dependency_cycle은 member file마다 표시).
Out of scope: symbol mode 출력 변경, 새 관계 추출(언어/framework analyzer 수정), Gradle module·npm workspace(handoff `agent-docs/handoff/b6db876d7191e86d-gradle-module-package-scheme.md`), FastAPI APIRouter 단위, 규칙 파일(Phase 2), baseline 비교(Phase 3), HTML Structure 전용 패널, package candidate의 HTML 표시, 최소 feedback edge set 계산, 기존 10개 지표와 기존 3개 candidate kind의 의미 변경, `report/bottlenecks/generate.py`의 `_KIND_SCORE_FIELDS` 우선순위 점수(새 kind의 metric 누락 시 fallback 포함; 파이프라인 출력에는 해당 metric이 항상 있음).

# Paths
Implementation: analysis/structure.py, bottlenecks/core.py, report/bottlenecks/generate.py, renderers/html/static/app.js
Tests: tests/test_structure_facts.py, tests/test_structure_packages.py, tests/test_structure_integration.py, tests/test_structure_browser.py, tests/structure_support.py, tests/structure_evidence/, tests/test_file_analysis_core.py, tests/test_search_mimicry_schema_and_structure.py, tests/test_file_analysis_cli.py, tests/test_search_mimicry_metrics.py, tests/standalone_candidate_policy_support.py, tests/file_analysis_browser_support.py, tests/legacy_metric_transition_support.py, tests/test_analysis_coverage_reporting.py
Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','android-nowinandroid','typescript-nestjs-realworld')]" && uv run -q --with-requirements requirements-dev.txt --with coverage python -m coverage run --branch --include=analysis/structure.py -m pytest -q -p no:cacheprovider && uv run -q --with coverage python -m coverage report --fail-under=90
Review evidence: R1 — main이 base_commit 워크트리와 현재 트리에서 4개 fixture를 같은 옵션(`-l python` ×2, `-l kotlin`, `-l typescript -f nestjs`, 모두 `--granularity file --bottlenecks`)으로 실행하고 `tests/structure_evidence/size.json`(`{fixture: {base_bytes, v8_bytes, ratio, structure_median_s, kind_counts}}`)에 기록한다. 자동 판정은 V11의 실시간 측정이 하고, size.json은 review 기록이다. R2 — main이 futuramaapi와 nestjs HTML을 브라우저로 열어 cycle 표시를 스크린샷으로 `tests/structure_evidence/`에 남긴다.
Fuzzing: none — 새 파서나 외부 입력 표면이 없다. graph 입력 공간은 V2의 무작위 graph differential 검사(독립 SCC oracle)가 다룬다.
Mutation tool: main이 scratchpad에 작성한 AST mutation 스크립트(비교·산술·불리언·상수·조건 삭제 연산자). base_commit 이후 변경된 Implementation Python 줄만 대상. 최대 30개 표본, seed 20261018. 실행 명령은 `uv run -q --with-requirements requirements-dev.txt python -m pytest -q -p no:cacheprovider -x tests/test_structure_facts.py tests/test_structure_packages.py tests/test_structure_integration.py`. 생존율 임계 40%.

# Signatures
`analysis.structure.STRUCTURE_POLICY = "structure.v1"`
`analysis.structure.TIERS = ("certain", "resolved", "all")`
`analysis.structure.edge_tier(edge) -> str` — 가장 엄격한 tier 이름. `certain`: confidence `static_certain` 그리고 resolution `exact`. `resolved`: resolution `exact` 또는 `unique_name`. 그 외는 `all`.
`analysis.structure.strongly_connected_components(nodes: Iterable[str], adjacency: Mapping[str, Iterable[str]]) -> list[list[str]]` — 크기 2 이상인 SCC만 반환. 각 SCC는 정렬된 list이고, 결과 list는 첫 원소 기준으로 정렬. 재귀를 쓰지 않는다.
`analysis.structure.package_assignments(architecture: FileArchitecture) -> dict[str, dict[str, list[str]]]` — `{scheme: {file_id: [package_id, ...]}}`. `framework` key는 NestJS module node가 있을 때만 존재.
`analysis.structure.analyze_structure(architecture: FileArchitecture, weights: EdgeWeights) -> StructureResult`
`analysis.structure.StructureResult` (frozen dataclass): `candidates: tuple[Mapping, ...]`((kind, id) 순 정렬), `package_metrics: Mapping[str, Mapping[str, Mapping]]`, `coverage: Mapping[str, Any]` = `{"structure": <F13 객체>}`

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F01 | 입력 edge 집합 E는 file architecture의 `edges` 중 relation이 `TESTS`가 아니고, 양 끝이 boundary가 아닌 file node(`metadata.boundary`가 참이 아님)인 edge다. tier t의 edge 집합은 `edge_tier(e)`가 t 이상으로 엄격한 edge다(certain ⊂ resolved ⊂ all). | required | brief, 측정 결과 |
| F02 | file pair 기록: (from_id, to_id)마다 하나로 묶는다. 포함 필드는 `relations`(정렬·중복 제거), `max_weight` = max(`EdgeWeights.weight_for(e)` × `e.metadata.candidate_share`(없으면 1)), `evidence_count` 합, `detail_edge_indices`(정렬·중복 제거 합집합), `tier`(pair 안 edge 중 가장 엄격한 tier). tier t의 pair는 t에 속하는 edge만으로 다시 집계한다. | required | 계획 Phase 1 |
| F03 | tier마다 file SCC를 계산하고, 크기 2 이상인 SCC마다 `dependency_cycle` candidate를 하나 낸다. 서로 다른 tier에서 member가 같아도 tier별로 따로 낸다. | required | 사용자 선택(tier별 candidate) |
| F04 | cycle candidate(`dependency_cycle`, `package_cycle`) 공통 형식. `id` = `bottlenecks.core._candidate` 규칙(identifier sha256 앞 16 hex, 접두 `b:`). identifier = `cycle|<scheme>|<tier>|` + 정렬 member를 `\n`으로 연결한 것(file cycle의 scheme은 `file`). `target` = `cycle:<scheme>:<tier>:` + identifier sha256 앞 16 hex. `metrics` = {`member_count`, `internal_pair_count`, `internal_evidence_count`, `min_pair_weight`}. `evidence` = 해당 tier의 SCC 내부 pair 기록 list(from_id, to_id 순 정렬). `coverage` = `static_analyzer_relation`. `status` = `static_candidate`. 추가 필드 `structure` = {`scheme`, `tier`, `members`, `parent_id`, `cut_candidates`}. | required | 계획, 사용자 선택 |
| F05 | `parent_id`는 바로 다음 느슨한 tier(certain→resolved, resolved→all)에서 이 SCC의 member를 모두 포함하는 SCC candidate의 id다. `all` tier에서는 null이다. | required | 사용자 선택 |
| F06 | `cut_candidates`는 내부 pair를 (`max_weight` 오름차순, `evidence_count` 오름차순, from_id, to_id)로 정렬한 앞 최대 10개다. 각 항목은 {from_id, to_id, relations, max_weight, evidence_count}. | required | 계획, 분량 대응 |
| F07 | `language` 체계 package. file F에 대해 다음 순서로 정한다. (a) F에 소속된 python-core `module` node가 있으면: file 이름이 `__init__.py`이면 `pkg:python:<module dotted name>`, 아니면 `pkg:python:<dotted name에서 마지막 요소를 뺀 것>`(점이 없으면 `pkg:python:(root)`). dotted name은 node의 `symbol_path`이고, 없으면 id에서 `py:`를 뗀 값. (b) kotlin-core file node가 F이고 그 node로 들어오는 `kotlin-package:<name>` CONTAINS edge가 있으면 `pkg:kotlin:<name>`. (c) 그 외는 `pkg:dir:<snapshot root 기준 디렉터리 posix 경로>`, 루트 file은 `pkg:dir:.`. 각 file은 package를 정확히 하나 갖는다. | required | 사용자 답변, ADR 58424b9754efe9a2 |
| F08 | `framework` 체계 package. details에 provenance `nestjs`, kind `module` node가 하나 이상 있을 때만 계산한다. module M의 member file은 다음의 합집합이다: M의 file, M이 `DECLARES`하는 controller의 file, M이 `PROVIDES`하는 provider의 file(`details.node_files` 기준). id는 `pkg:nestjs:` + M id에서 `nestjs:module:`을 뗀 값. 여러 module에 속한 file은 속한 모든 module의 member다(A01). 어느 module에도 속하지 않는 file은 이 체계의 package가 없다. | required | ADR 58424b9754efe9a2 |
| F09 | 체계 S의 package graph: file pair (F→G)마다 F의 package 집합의 각 P와 G의 package 집합의 각 Q에 대해, P≠Q이면 package pair (P→Q)에 기여한다. package pair의 `max_weight`는 기여한 file pair `max_weight`의 최댓값이고, `evidence_count`는 합이다. tier는 F02와 같은 방식으로 정한다. | required | 계획 |
| F10 | `network.package_metrics[S][P]` = {`file_count`, `ca`, `ce`, `instability`, `weighted_ca`, `weighted_ce`, `weighted_instability`}. 모두 `all` tier package graph 기준이다. ce = P에서 나가는 서로 다른 Q의 수, ca = P로 들어오는 서로 다른 Q의 수. weighted_ce/ca = 해당 package pair `max_weight`의 합. instability = ce/(ca+ce)이고, 분모가 0이면 null. weighted_instability도 같은 방식. | required | 계획 |
| F11 | 체계와 tier마다 package SCC를 계산하고, 크기 2 이상인 SCC마다 `package_cycle` candidate를 F04·F05·F06 형식으로 낸다. scheme은 `language` 또는 `framework`, evidence와 cut_candidates는 package pair 기록이다. package pair 기록 필드는 {`from_id`, `to_id`, `relations`(기여 file pair relations의 정렬 합집합), `max_weight`, `evidence_count`, `tier`, `file_pairs`([from_id, to_id] 정렬 list)}이며 `detail_edge_indices`는 넣지 않는다. | required | 계획 |
| F12 | `all` tier package pair (P→Q)마다 `instability(Q) > instability(P)`이면 `unstable_dependency` candidate를 하나 낸다. identifier = `unstable|<scheme>|<P>|<Q>`. target = P. metrics = {`instability_from`, `instability_to`, `instability_delta`, `evidence_count`, `file_pair_count`}이고, 분모가 0이 아닐 때 `weighted_instability_from`/`_to`도 넣는다. evidence = 기여한 file pair 기록 list. `structure` = {`scheme`, `tier`(package pair tier), `from_package`, `to_package`}. `coverage` = `static_analyzer_relation`, `status` = `static_candidate`. weighted 분모가 0이면(candidate_share 0 포함) 해당 weighted 값은 생략한다. | required | 사용자 답변(차이가 0보다 크면 모두) |
| F13 | `coverage.structure` = {`policy`: STRUCTURE_POLICY, `schemes`: {S: {`assigned_file_count`, `unassigned_file_count`, `unassigned_files`(정렬), `shared_file_count`, `shared_files`(정렬; package 2개 이상에 속한 file)}}}. `language`는 항상 unassigned 0, shared 0이다. bottleneck JSON에서는 `coverage.structure`에 둔다. member file이 하나도 매핑되지 않은 NestJS module은 package를 만들지 않는다. | required | ADR 58424b9754efe9a2 |
| F14 | file 모드 bottleneck: schema `bottlenecks.v8`, `granularity: "file"`. `network.package_metrics`와 `network.structure_policy`를 추가하고, 새 candidate를 기존 candidate와 합쳐 (kind, id) 순으로 정렬한다. 새 candidate의 evidence pair 기록에는 `candidates` 필드가 없으므로 `_intern_candidate_groups`의 동작은 바뀌지 않는다. `versions.analysis`는 "4"로 유지한다. symbol 모드 출력은 base_commit과 byte 단위로 같다. | required | 사용자 승낙(v8) |
| F15 | `report/bottlenecks/generate.py._validate`는 v6, v7, v8을 받는다. v8은 `granularity: "file"`이 필수다. `KIND_LABELS`/`KIND_DESCRIPTIONS`에 새 3종을 추가한다. `METRIC_DEFINITIONS`와 기존 kind는 바꾸지 않는다. | required | 계획, A03 |
| F16 | HTML file 모드: `dependency_cycle` candidate를 `structure.members`의 각 file에 붙여, 기존 candidate 표시 자리에 kind label과 이유 `<member_count>개 파일 순환 · <tier label>`로 보여준다. tier label: certain=`확정 연결`, resolved=`해석된 연결`, all=`불확실 포함`. `package_cycle`/`unstable_dependency`는 HTML에 표시하지 않는다. | required | A04 |
| F17 | 같은 입력에 대한 `analyze_structure` 결과와 bottleneck JSON은 실행마다 byte 단위로 같다. 순서는 dict/set 반복 순서에 의존하지 않는다. | required | 기본 원칙 |

# Errors
- 입력에 file node가 없거나 E가 비어 있음 — 예외 없이 cycle·unstable candidate 0개, `language` package_metrics는 file 수만큼(모두 ca=ce=0, instability null). post-state: 기존 출력은 그대로다.
- edge의 confidence/resolution 값이 EdgeWeights에 없음 — 기존과 같이 `BottleneckInputError`가 발생한다. post-state: 출력 file이 써지지 않는다(CLI 기존 동작).
- NestJS module node가 file에 매핑되지 않음(node_files가 None) — 그 module의 file 기여만 빠진다. 다른 member는 유지하고 예외는 없다.
- `--granularity symbol` — structure 계산이 실행되지 않는다. 출력은 base와 같다.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C01 | normal | A→B(certain), B→A(certain), C 고립 | certain/resolved/all 각 `dependency_cycle` [A,B] 1개. resolved의 parent = all id, certain의 parent = resolved id |
| C02 | normal | A→B certain, B→C ambiguous, C→A certain, A→C unique_name | all tier [A,B,C]. resolved tier [A,C](A→C unique_name, C→A certain). certain tier 없음 |
| C03 | edge | A→B relation TESTS, B→A IMPORTS | cycle 없음 |
| C04 | edge | 끝점 하나가 boundary node인 edge로만 닫히는 순환 | cycle 없음 |
| C05 | boundary | 내부 pair 9/10/11개인 SCC | cut_candidates 길이 9/10/10, 정렬 규칙 일치 |
| C06 | boundary | 20,000개 file 선형 chain과 마지막→첫 edge 하나 | RecursionError 없음, SCC 1개, member 20,000 |
| C07 | normal | 같은 pair에 relation 2종, (certain, share 1)·(ambiguous, share 0.5) edge | pair relations 2종, max_weight = max(1.0, 0.3×0.5) = 1.0, tier certain, evidence_count 합 |
| C08 | normal | Python: `pkg/__init__.py`, `pkg/a.py`, `top.py` | `pkg:python:pkg`, `pkg:python:pkg`, `pkg:python:(root)` |
| C09 | normal | Kotlin file `x/Y.kt`, `package com.a.b` | `pkg:kotlin:com.a.b`(디렉터리 `x`와 무관) |
| C10 | normal | TS file `src/a/b.ts`, 루트 `main.ts` | `pkg:dir:src/a`, `pkg:dir:.` |
| C11 | normal | NestJS module M(file m.ts) DECLARES controller(c.ts), PROVIDES provider(s.ts), entity e.ts는 어느 module에도 없음 | framework: m.ts·c.ts·s.ts → `pkg:nestjs:<M>`, e.ts unassigned 1 |
| C25 | edge | provider s.ts를 M1과 M2가 모두 PROVIDES, x.ts(M3 소속)→s.ts | s.ts는 M1·M2 member, shared_file_count 1, package pair M3→M1과 M3→M2 모두 존재 |
| C12 | edge | NestJS node 없음 | `framework` 체계 key 없음(package_metrics·coverage 모두) |
| C13 | boundary | P: ca=0, ce=1 / Q: ca=1, ce=0 / 고립 R | I(P)=1.0, I(Q)=0.0, I(R)=null. P→Q는 unstable_dependency 아님 |
| C14 | normal | P→Q, I(P)=0.5, I(Q)=0.6667 | unstable_dependency 1개, instability_delta ≈ 0.1667 |
| C15 | boundary | P→Q, I(P) = I(Q) | candidate 없음 |
| C16 | normal | 서로 다른 package의 file 사이 순환 P↔Q | language 체계 `package_cycle` [P,Q], evidence의 각 pair에 `file_pairs` |
| C17 | edge | 같은 package 안의 file만으로 이루어진 순환 | dependency_cycle 있음, package_cycle 없음 |
| C18 | normal | 4개 fixture file 모드 CLI | schema v8, 새 kind 존재, 기존 candidate·rankings·node_metrics가 base와 같음 |
| C19 | normal | 같은 fixture symbol 모드 CLI | bottleneck JSON이 base_commit 출력과 byte 단위로 같음 |
| C20 | normal | v6, v7, v8 JSON을 `python -m report.bottlenecks.generate`로 렌더링 | 셋 다 성공. v8에 granularity가 없으면 ReportInputError |
| C21 | normal | futuramaapi HTML에서 cycle member file 선택 | 해당 file의 candidate 목록에 `dependency_cycle` label과 `N개 파일 순환 · <tier label>` 표시 |
| C22 | error | 경로에 `<img src=x onerror=alert(1)>`가 들어간 file이 cycle member인 HTML | 문자열이 text로 표시되고 script는 실행되지 않음 |
| C23 | edge | 빈 file graph(node 0) | 예외 없음, candidate 0, package_metrics 빈 language 체계 |
| C24 | normal | 같은 입력으로 두 번 실행(별도 process, PYTHONHASHSEED 다르게) | bottleneck JSON byte 단위로 같음 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 새 candidate와 지표가 정의대로 계산되어야 한다 |
| Performance efficiency | yes | 사용자가 symbol graph 분량 폭증의 재발을 명시적으로 우려했다 |
| Compatibility | yes | symbol 모드, v6/v7 렌더링, 기존 candidate가 바뀌면 안 된다 |
| Interaction capability | yes | HTML에서 cycle을 사람이 읽을 수 있어야 한다 |
| Reliability | yes | 출력이 결정적이어야 하고, 빈 graph나 큰 graph에서 죽으면 안 된다(Phase 3 baseline 비교의 전제) |
| Security | yes | file 경로가 HTML에 새로 들어간다(XSS) |
| Maintainability | yes | 범용 분석 layer가 framework analyzer를 import하면 안 된다(`tests/test_architecture_boundaries.py`) |
| Flexibility | no | 새 설정이나 플랫폼 표면이 없다. 기존 edge_weights profile만 쓴다 |
| Safety | no | 물리적 위해와 관련이 없는 정적 분석 도구다 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | Functional suitability / correctness | F01–F13 계산 | 손으로 계산한 기대값과 무작위 graph differential(독립 SCC oracle: 반복 BFS 기반 상호 도달성) | 선언 coverage item 100% 통과 | automated + mutation | 계획 |
| Q02 | Performance efficiency / resource use | 4개 fixture bottleneck JSON | v8 byte 크기 ÷ base_commit v7 byte 크기 | 각 fixture ≤ 1.25 | automated(R1 산출물 검사) + review R1 | I3, 사용자 우려 |
| Q03 | Performance efficiency / time behaviour | 4개 fixture `analyze_structure` | 같은 process 안 3회 실행 중앙값, 초 | 각 ≤ 1.0 s. C06 chain 20,000 file ≤ 5.0 s | automated | I3 |
| Q04 | Compatibility / coexistence | symbol 모드, 기존 kind, v6/v7 | C18–C20 | 차이 0, 기존 pytest 실패 0(v7→v8 기대값 갱신 외 기존 assertion 의미 변경 없음) | automated | F14, F15 |
| Q05 | Interaction capability / recognizability | HTML cycle 표시 | C21 browser 검사 | label과 이유 문자열 일치 | automated(Playwright) + review R2 | F16 |
| Q06 | Reliability / faultlessness | 결정성, 빈 graph, 큰 graph | C06, C23, C24 | 예외 0, byte 차이 0 | automated | F17 |
| Q07 | Security / integrity | HTML 주입 | C22 | 주입 script 실행 0, text 그대로 표시 | automated(Playwright) | 기존 `tests/test_report_security.py` 정책 |
| Q08 | Maintainability / modularity | `analysis/structure.py` import | 기존 `tests/test_architecture_boundaries.py`와 새 import 검사 | framework_analyzers·language_analyzers.<lang> import 0 | automated | 프로젝트 경계 |
| Q09 | Maintainability / testability | `analysis/structure.py` | coverage.py branch coverage | ≥ 90% | automated(Test command) | 기본값 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V01 | F01, F02, C03, C04, C07 | `edge_tier`, pair 집계 | unit; 손으로 만든 FileArchitecture 유사 입력 | equivalence partitioning | tier-certain; tier-resolved-unique; tier-resolved-dynamic-exact; tier-all-ambiguous; tier-all-unresolved; tests-excluded; boundary-excluded; multi-relation-pair; share-weight; detail-index-union | 100% | tier·max_weight·evidence_count·relations가 손 계산값과 같음 | pytest |
| V02 | F03, Q01, C01, C02, C06 | `strongly_connected_components` | unit; 고정 사례와 seed 0..49 무작위 directed graph(node 1..60, 밀도 0.02..0.3) | random testing | fixed-2cycle; fixed-nested; fixed-dag; fixed-selfdisjoint; random-seeds-0..49; chain-20000 | 100% | 독립 상호 도달성 oracle과 SCC 집합이 같음, 출력 정렬, RecursionError 없음 | pytest |
| V03 | F03, F04, F05, F06, C01, C02, C05 | `dependency_cycle` candidate 형식 | unit | decision table | rule-tiers-all-three; rule-resolved-only; rule-all-only; rule-same-members-across-tiers; parent-chain; id-and-target-derivation; metrics-four; cut-9; cut-10; cut-11; cut-order-ties | 100% | 필드·id·parent·cut 정렬이 명세 산술과 같음 | pytest |
| V04 | F07, C08, C09, C10 | `package_assignments` language | unit + integration(fixture 1개씩) | equivalence partitioning | py-init; py-module; py-root; py-no-symbol-path; kt-package; kt-default-package; kt-dir-mismatch; ts-dir; root-dir; non-code-file | 100% | 기대 package id | pytest |
| V05 | F08, F13, C11, C12, C25 | framework 체계 | unit + integration(nestjs fixture) | equivalence partitioning | nest-module-file; nest-controller; nest-provider; nest-unassigned; nest-module-unmapped; no-nest; multi-membership-C25 | 100% | membership과 coverage 수치 | pytest |
| V06 | F09, F10, C13, C14, C15 | package graph·지표 | unit | boundary value analysis (3-value) | instability-denominator-0; ca0-ce1; ca1-ce0; delta-negative; delta-zero; delta-positive; weighted-sum-max-per-pair; weighted-null | 100% | 손 계산 지표와 같음, delta 0 이하에서 candidate 없음 | pytest |
| V07 | F11, F12, C16, C17 | package_cycle·unstable_dependency | unit | decision table | pkg-cycle-cross; pkg-cycle-intra-none; pkg-cycle-tiers; unstable-fields; unstable-weighted-present; unstable-weighted-absent; file-pairs-listing | 100% | candidate 유무와 필드 | pytest |
| V08 | F14, F17, Q04, Q06, C18, C19, C24 | CLI 출력 | integration; 4개 fixture file + 동일 4개 symbol | scenario testing | file-futurama; file-realworld; file-nia; file-nest; symbol-byte-equal ×4; determinism-hashseed | 100% | v8, 기존 부분이 base와 같음, symbol byte 같음, 두 실행 byte 같음 | pytest; main이 구현 전 base_commit 트리에서 생성한 `tests/structure_evidence/base_manifest.json`(fixture·모드별 bottleneck JSON byte 크기와 sha256, file 모드의 `rankings`·`rankings_by_category`·`node_metrics`·기존 candidate list 각각의 canonical JSON sha256)과 비교 |
| V09 | F15, C20 | report validator | unit | equivalence partitioning | v6-ok; v7-ok; v8-ok; v8-no-granularity; new-kind-labels; unknown-kind-rejected | 100% | 성공/ReportInputError | pytest |
| V10 | F16, Q05, Q07, C21, C22 | HTML | end-to-end(Playwright) | scenario testing | cycle-on-each-member; tier-label-3; package-kinds-hidden; xss-path | 100% | DOM text와 dialog 미발생 | pytest browser |
| V11 | Q02, Q03 | 분량·시간 | integration(benchmark 아님, 기본 실행) | boundary value analysis (2-value) | size-ratio ×4; time-median ×4; chain-time | 100% | 각 상한 이하 | pytest가 R1 산출물과 실시간 측정 검사 |
| V12 | Q08 | import 경계 | unit | syntax testing | no-framework-import; no-lang-specific-import | 100% | AST import 목록 검사 | pytest |
| V13 | Errors, C23 | 빈 입력·미등록 confidence | unit | error guessing | empty-graph; no-edges; unknown-confidence; unmapped-nest-module | none — experience-based | 예외/무예외가 명세대로 | pytest |
| V14 | Q09 | branch coverage | 전체 Test command | branch testing (coverage.py) | analysis/structure.py branches | ≥ 90% | coverage report 통과 | Test command |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| A01 | 여러 NestJS module에 속한 file은 모든 module의 member이고, coverage에 shared로 기록 | provider는 여러 module의 `providers`에 들어갈 수 있다. fixture에서는 발생하지 않음 | user answer |
| A02 | TESTS edge와 boundary node는 구조 계산에서 제외 | TESTS는 test→prod 단방향 복사 edge, boundary는 file이 없음 | brief v2 — approved |
| A03 | v7 JSON 렌더링 유지 | 기존 저장 JSON 호환 | brief v2 — approved |
| A04 | Phase 1 HTML은 dependency_cycle만 member file에 표시, package candidate는 JSON 전용 | Structure 패널은 Phase 3 | brief v2 — approved |
| A05 | member가 같아도 tier별로 candidate를 따로 냄 | Phase 3에서 tier별 diff가 단순해짐. 출력이 약간 중복됨 | brief v2 — approved |
| A06 | CONFIGURES 등 모든 비-TESTS relation을 cycle에 포함 | recall 우선. 측정상 CONFIGURES 제외해도 SCC 변화 없음 | brief v2 — approved |
| A07 | Q02 1.25배, Q03 1초, Q09 branch 90% | 측정 기반 여유 | brief v2 — approved |
| A08 | package_metrics는 all tier 기준 | recall 우선. tier별 지표는 출력만 늘림 | brief v2 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F01, F02 | C03, C04, C07 | V01 | pytest |
| F03–F06 | C01, C02, C05, C06 | V02, V03 | pytest |
| F07 | C08–C10 | V04 | pytest |
| F08, F13 | C11, C12, C25 | V05 | pytest |
| F09, F10 | C13–C15 | V06 | pytest |
| F11, F12 | C16, C17 | V07 | pytest |
| F14, F17 | C18, C19, C24 | V08 | pytest + base 출력 |
| F15 | C20 | V09 | pytest |
| F16 | C21, C22 | V10 | Playwright |
| Q01–Q09 | C06, C22–C24 | V02, V08, V10–V14 | pytest, R1, R2 |
| Errors | C23 | V13 | pytest |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 2 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V01–V06, V08–V14 | 3 | verifier 1 accepted (V08은 Q04 diff 확인 대기 → tests/structure_evidence/existing-tests.diff로 해소) | accepted (verifier 1, verifier 2 retained; F-02 closed) | hand mutation H01–H16 전부 의도 assertion으로 kill (tests/structure_evidence/hand-mutations.json); mutation tool 30개 중 29 kill, M29 undeclared | correction batch 2는 테스트 추가만(F-01, A-1, A-3, A-4)이라 기존 수용 유지 |
| V07 | 4 | test_V07_unstable_weighted_from_key_absent_when_from_side_denominator_is_zero 추가; run4 1591 passed | accepted (verifier 2; F-01 closed) | H14 kill | — |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 0 | 전체 edge SCC가 futuramaapi 188 file 중 106, nowinandroid 78 중 41 | ambiguous edge가 순환을 이음(verified: resolved tier에서 최대 6) | tier별 SCC로 설계 | 사용자 선택으로 채택 |
| 1 | 첫 Test command: 2 failed, 11 errors, 1566 passed, branch 100% | 테스트 결함 3건(verified): without_structure_facts가 architecture에 candidates 추가; V09가 F16상 숨김 kind label을 HTML에서 요구; test_structure_browser가 conftest의 session chromium fixture를 재import해 sync_playwright 이중 기동(단독 실행 11 passed) | test-implementer에 correction batch 1, 이후 v3 명확화 assertion 추가 | 해결: run3 rc=0, 1588 passed |
| 2 | verifier 1: F-01 from 측 weighted 생략 증거 없음; F-02 기존 테스트 diff 미확인 | F-01 테스트 결함(verified), F-02 증거 미제출 | F-01 테스트 추가 + A-1/A-3/A-4; F-02 diff를 tests/structure_evidence/existing-tests.diff로 제출; 테스트 실행이 재생성한 기존 evidence 4개 파일은 HEAD로 복원(이번 작업과 무관한 산출물) | run4 rc=0, 1591 passed, branch 100% |
| 3 | mutation tool M29 survived(generate.py `_KIND_SCORE_FIELDS` package_cycle default 0→1) | mutant-triager: undeclared — metric 누락 JSON에서만 관측 | v4에서 해당 우선순위 점수를 Out of scope로 명시(사용자 요구가 아니며 파이프라인 출력에는 영향 없음) | closed as out-of-scope |

# Version Log
## v1
- 초안 작성. 측정 결과(scratchpad scc2.py)와 사용자 답변(v8 승낙, package 정의, tier별 candidate, 체계별 계산, Gradle 제외)을 반영.
## v2
- A01 사용자 답변 반영: 다중 소속 file은 모든 module의 member, F09 package 집합 기준 기여, F13 shared 필드, C25 추가.
- [contract] V08 base 증거를 전체 JSON 저장 대신 base_manifest.json의 크기·hash로 고정(저장소 용량). brief 항목 변경 없음.
## v3
- [contract] 양 역할의 spec challenge 정리: StructureResult.candidates 정렬과 coverage 형태, package pair 기록 필드(relations 합집합, detail_edge_indices 없음), unstable_dependency의 coverage/status와 weighted 생략 조건, coverage.structure의 JSON 위치, member 없는 NestJS module, R1 size.json 형식. 모두 구현 보고와 일치하며 brief 항목 변경 없음.
## v4
- [contract] mutation M29(undeclared)에 따라 `_KIND_SCORE_FIELDS` 우선순위 점수를 Out of scope로 명시. brief 항목 변경 없음.
