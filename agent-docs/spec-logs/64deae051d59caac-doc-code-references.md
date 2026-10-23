---
version: 6
run_id: 64deae051d59caac
status: complete
base_commit: 7d169832420840158671369992f392d025284ff4
max_verifier_invocations: 2
handoff: agent-docs/handoff/fa00b92fe9819b57-agent-context-candidates.md
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 분석기 사용자(사람·에이전트) | 문서(AGENTS.md, README, docs)가 저장소의 어떤 파일·모듈·심볼을 가리키는지 본다 | file granularity details 파일에 문서별 참조 목록(줄, 표기, 대상, 상태)이 있다 |
| I2 | 분석기 사용자 | 문서가 가리키는데 저장소에 없는 대상(dangling)을 찾는다 | bottleneck JSON과 handout에 `dangling_doc_reference` candidate가 문서별로 나온다 |
| I3 | 분석기 사용자 | 문서 참조가 기존 의존 그래프 지표를 바꾸지 않는다 | 기존 node_metrics, rankings, 구조 candidate, package 지표 값이 base와 같다 |
| I4 | eval 실험(handoff `e16d433ef30afd87`) | 문서가 많은 저장소에서도 오탐과 비용이 감당 가능하다 | R1에서 vendure의 사이트 route 링크가 dangling으로 나오지 않고, 시간 증가가 한도 안이다 |

# Scope
In scope:
- snapshot `contents` 중 `.md`, `.mdx`, `.markdown` 파일(대소문자 무시)의 참조 추출: 마크다운 인라인 링크·이미지, 참조식 링크 정의, 단일 백틱 코드 스팬(경로형, Gradle 모듈 경로, 식별자). fenced code block(``` 또는 ~~~) 안은 제외.
- 참조 해석: 저장소 파일·디렉터리, Gradle build module, 심볼.
- file granularity에서만: details 파일의 `doc_references`, bottleneck JSON의 `dangling_doc_reference` candidate와 `coverage.doc_references` 요약, handout 표시.
- `versions.analysis` "6" → "7". 스키마 이름(`bottlenecks.v9`)은 유지.

Out of scope:
- 문서 노드나 문서 edge를 의존 그래프(`architecture.nodes/edges`)에 추가하는 일(사용자 결정: 별도 출력).
- symbol granularity 출력.
- HTML 리포트 UI 변경(파일 모드 candidate 목록은 파일 노드에 붙는 candidate만 보여 준다. 문서는 파일 노드가 아니다).
- 문서가 agent 작업에 도움이 되는지에 대한 판단이나 점수.
- 외부 URL 검사, 앵커(#fragment) 존재 검사, reStructuredText·AsciiDoc 등 다른 문서 형식.
- snapshot 정책(`repository/policy.py`, `profiles/snapshot.v1.yaml`) 변경.
- `language_analyzers/core/enrichment.py` 변경.

# Paths
Implementation: analysis/doc_references.py, bottlenecks/core.py, bottlenecks/handout.py
Tests: tests/
Test command: .venv/bin/python -m pytest -q
Review evidence: R1 real-repo run — main이 GCP VM `na-eval`(n2-highmem-16, asia-northeast3-a)의 `~/nowinandroid`(`-f android`), `~/vendure`(`-f nestjs`)에서 base_commit 분석기와 변경 후 분석기를 file granularity로 `/usr/bin/time -v`와 함께 실행한다(`python -m code_analyzer.cli <clone> <analyzer> -o <out>/a.html --bottlenecks <out>/b.json`). 기록: wall time, 최대 RSS, `coverage.doc_references`의 상태별·표기별 개수, dangling candidate 수와 상위 사례 10개(오탐 분류는 main이 수동 판정), 기존 node_metrics·rankings·기존 kind candidate의 base 대비 차이 수(기대 0). 산출물 scratchpad `doc-refs-r1/summary.md`, 요약은 Execution ledger에 남긴다.
Fuzzing: main이 scratchpad `doc-refs-fuzz/fuzz.py`를 작성한다. 표면: `analyze_doc_references`에 넣는 문서 1–3개의 무작위 텍스트(백틱·대괄호·괄호·슬래시·콜론·`#`·`~`·개행·유니코드·fence 조각을 섞은 문법 기반 생성)와 무작위 파일 목록. 오라클: (crash) 예외 없음, (property) 모든 행의 `line`이 1 이상 문서 줄 수 이하, `status`가 허용 값, `status`가 `resolved`이면 `target`이 존재하는 대상, candidate의 `dangling_count`가 그 문서의 dangling 행 수와 같음. seed 20261022, 20000 입력.
Mutation tool: main이 scratchpad의 AST mutation 스크립트(비교·불리언·상수·조건 부정)를 base_commit 이후 변경된 Implementation Python 줄에 적용한다. 최대 30개 표본, seed 20261022. 실행 명령 `.venv/bin/python -m pytest -q -p no:cacheprovider -x -n 0 <이번 run이 추가·수정한 테스트 파일>`. 생존율 임계 40%.

# Signatures
analysis.doc_references.analyze_doc_references(snapshot: RepositorySnapshot, details: Mapping[str, Any]) -> tuple[dict, list[dict], dict]  # (table, candidates, summary)
table = {"columns": ["doc", "line", "notation", "text", "status", "target", "target_kind", "candidates", "candidate_total"], "rows": [[...], ...]}
summary = {"document_count": int, "reference_count": int, "by_status": {status: int}, "by_notation": {notation: int}}

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F1 | 문서 = snapshot `contents`의 경로 중 확장자가 `.md`·`.mdx`·`.markdown`(대소문자 무시)인 파일. fenced code block(줄 앞 공백 0–3칸 뒤 ``` 또는 ~~~ 3개 이상으로 열고, 같은 문자로 같은 길이 이상인 줄로 닫음; 닫히지 않으면 문서 끝까지) 안의 텍스트는 참조 추출에서 제외한다 | must | I1 |
| F2 | 링크 표기(`notation` = `link`): 인라인 `[text](target)`·`![alt](target)`(target은 선택적 `<...>` 감싸기, 공백 앞까지)와 줄 시작 참조 정의 `[id]: target`. target이 scheme(`^[A-Za-z][A-Za-z0-9+.-]*:`)으로 시작하거나 `#`로 시작하거나 `#`·`?` 제거 후 비면 무시한다. `#` 이후·`?` 이후를 제거하고 percent-decoding한다 | must | I1, 사용자 답변 |
| F3 | 경로 존재 판정: inventory = snapshot `contents` 경로 ∪ `excluded_files` 경로. 경로 p가 존재 = p가 inventory에 있음(파일) 또는 inventory 어떤 경로의 상위 디렉터리임(디렉터리). 후보 경로 p에 대해 p, p+`.md`, p+`.mdx`, p+`/README.md`, p+`/index.md`, p+`/index.mdx` 순으로 처음 존재하는 것을 대상으로 한다(끝 `/`는 제거 후 적용). p가 디렉터리로 존재하면 p 자체(디렉터리)가 대상이므로 `/README.md`·`/index.md(x)` 접미는 사실상 p가 파일·디렉터리 모두 아닐 때만 의미가 있고, 그 경우 해당 파일도 없으므로 결과에 영향이 없다 | must | I1 |
| F4 | 링크 해석: `/`로 시작하지 않으면 문서 디렉터리 기준으로 결합·정규화한다. 결과가 저장소 밖(`..`로 시작)이면 `dangling`. `/`로 시작하면 저장소 루트 기준으로 해석하고(F3 접미 fallback 동일 적용), 존재하지 않거나 루트 자체(`/`)이거나 저장소 밖이면 `site_route`(dangling 아님). 코드 스팬(F5)에는 F3의 접미 fallback을 적용하지 않는다. 상대 링크가 존재하지 않으면 `dangling` | must | 사용자 답변 |
| F5 | 경로형 코드 스팬(`notation` = `code_path`): 단일 백틱 스팬(이중 백틱 스팬 제외) 내용 s가 공백·`*?<>{}[]$|` 문자를 포함하지 않고 scheme으로 시작하지 않으며 다음 중 하나: (a) `/`를 포함하고, `./`·`/` 접두를 뗀 첫 세그먼트가 문서 디렉터리 또는 루트 기준으로 존재, (b) `/`를 포함하고 `\.[A-Za-z0-9]{1,5}$`로 끝남, (c) `/`를 포함하지 않고 문서 디렉터리 또는 루트 기준으로 존재. 해석 순서: `/` 접두면 루트만, 아니면 문서 디렉터리 → 루트. 존재하면 `resolved`, (a)(b)인데 존재하지 않으면 `dangling`. (c)는 존재할 때만 기록한다 | must | 사용자 답변 |
| F6 | Gradle 모듈 스팬(`notation` = `gradle_module`): s가 `^:[A-Za-z0-9_.-]+(:[A-Za-z0-9_.-]+)*$`. details `nodes` 중 `metadata.build_system == "gradle"`이고 `metadata.module_dir`가 있는 노드가 하나도 없으면 무시한다. 있으면 `metadata.module_dir`가 있고 `metadata.module_path == s`인 노드가 있을 때 `resolved`(target = 노드 id, 그런 노드가 여럿이면 id가 가장 작은 노드, `target_kind` = `build_module`), 없으면 `dangling` | must | 사용자 답변 |
| F7 | 식별자 스팬(`notation` = `identifier`): s에서 끝 `()`를 뗀 값 t가 `^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$`이고 F5·F6에 해당하지 않을 때. 대상 집합 = details `nodes` 중 kind가 class, interface, enum, type_alias, function, method인 노드. t에 `.`이 없으면 `label == t`, 있으면 `symbol_path == t` 또는 `symbol_path`가 `"." + t`로 끝나는 노드. 1개면 `resolved`(`target_kind` = `symbol`), 2개 이상이면 `ambiguous`(target null, `candidates` = id 오름차순 앞 10개, `candidate_total` = 전체 수), 0개면 기록하지 않는다 | must | 사용자 답변 |
| F8 | 경로 대상 표기: 대상 경로가 details `file_nodes`에 `file:<path>`로 있으면 target = `file:<path>`, `target_kind` = `file`. 아니면 target = 경로 문자열, `target_kind` = 디렉터리면 `directory`, 파일이면 `path`. 저장소 루트 디렉터리(상대 링크 `.`·`..` 등이 루트로 정규화된 경우)는 존재하는 디렉터리이며 target = `"."`. `dangling`·`site_route` 행은 target null, `target_kind` null | must | I1 |
| F9 | 행: `[doc, line, notation, text, status, target, target_kind, candidates, candidate_total]`. `line`은 참조 시작 문자의 1-기반 줄. `text`는 링크 target 원문(`<...>` 감싸기는 벗긴 값, `#`·`?` 제거·decoding 전) 또는 스팬 내용. `status` ∈ {resolved, ambiguous, dangling, site_route}. `candidates`·`candidate_total`은 ambiguous가 아니면 null. 행은 (doc, line, 문서 내 시작 위치) 순 | must | I1 |
| F10 | dangling이 1개 이상인 문서마다 candidate 1개: kind `dangling_doc_reference`, id = `"b:" + sha256(doc + "|dangling_doc").hexdigest()[:16]`, target `file:<doc>`, metrics `{"dangling_count": n}`, evidence = 그 문서 dangling 행의 `{"line", "notation", "text"}` 목록(행 순서), coverage `"doc_reference"`, status `"static_candidate"` | must | I2 |
| F11 | file granularity의 `analyze_bottlenecks`가 table을 `architecture.details["doc_references"]`에 넣어 details 파일에 기록되게 하고, candidates를 기존 candidate 목록에 합쳐 (kind, id)로 정렬하고, summary를 `coverage["doc_references"]`에 넣는다. 문서가 없어도 table(빈 rows)과 summary(`document_count`는 참조가 없는 문서도 포함한 F1 문서 수; 문서가 없으면 `document_count`·`reference_count` 0, `by_status`·`by_notation`은 빈 dict; 이 두 dict는 1회 이상 나온 키만 갖는다)는 있다. symbol granularity 출력은 base와 같다 | must | I1, I2 |
| F12 | bottleneck JSON `versions.analysis` = "7"(file·symbol 모두). schema 이름 불변 | must | A1 |
| F13 | handout의 candidate 섹션에서 `dangling_doc_reference`는 `dangling_count` 내림차순(동점 id 오름차순)으로 정렬되고, 기존 kind와 같은 형식·상한으로 나온다 | should | I2 |
| F14 | 기존 node_metrics, rankings, rankings_by_category, 기존 kind candidate, package_metrics·package_dependencies, details의 기존 키는 base와 같다 | must | I3 |

# Errors
- 문서 텍스트에 짝이 맞지 않는 백틱·대괄호·괄호, 닫히지 않은 fence — 예외 없음 — 해당 부분은 참조로 인정하지 않거나 F1 규칙대로 처리.
- percent-decoding 실패(잘못된 `%` 시퀀스) — 예외 없음 — 원문 그대로 해석.
- details `nodes`의 metadata·label·symbol_path가 없거나 문자열이 아님 — 예외 없음 — 그 필드가 필요한 매칭(label: 단순 식별자, symbol_path: dotted 식별자, metadata: Gradle)에서만 그 노드를 제외한다.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | `docs/a.md`에 `[x](../src/m.py)`, `src/m.py`가 file 노드 | resolved, target `file:src/m.py`, target_kind file |
| C2 | normal | `[x](./guide)`, `docs/guide.md` 존재 | resolved, target `docs/guide.md`, target_kind path |
| C3 | normal | `[x](missing.md)` | dangling, candidate 생성 |
| C4 | normal | `[x](/reference/api)`, 루트에 없음 | site_route, candidate 없음 |
| C5 | normal | `[x](/src/m.py)` 루트에 있음 | resolved |
| C6 | normal | `` `src/m.py` ``, `` `src/none.ts` ``, `` `api/users` ``(첫 세그먼트 없음·확장자 없음) | resolved, dangling, 기록 없음 |
| C7 | normal | `` `:core:data` ``, gradle 모듈 존재/부재, gradle 모듈 없는 저장소 | resolved(build_module) / dangling / 기록 없음 |
| C8 | normal | `` `UserService` `` 1개 매칭, `` `id` ``가 method 12개 매칭, `` `master` `` 매칭 없음 | resolved symbol / ambiguous(candidates 10, total 12) / 기록 없음 |
| C9 | normal | `` `Foo.bar()` ``, symbol_path `pkg.Foo.bar` | resolved |
| C10 | boundary | fence 안의 링크·스팬, 닫히지 않은 fence 뒤 | 기록 없음 |
| C11 | boundary | `[x](https://a)`, `[x](mailto:a)`, `[x](#anchor)`, `[x](a.md#h)`, `[x](a%20b.md)` | 앞 3개 무시, `a.md`로 해석, `a b.md`로 해석 |
| C12 | boundary | 식별자 매칭 10개와 11개 | ambiguous candidates 10개, total 10/11 |
| C13 | boundary | 링크 `[x](../../outside.md)`가 저장소 밖 | dangling |
| C14 | edge | 문서 없음 | rows 빈 목록, summary 0, candidate 없음 |
| C15 | edge | 대상이 excluded_files(바이너리 이미지)에만 있음, 디렉터리 링크 `[x](src/)` | resolved, target_kind path / directory |
| C16 | error | 짝 안 맞는 기호, 잘못된 `%zz`, metadata 비정상 노드 | 예외 없음 |
| C17 | normal | fixture CLI(file) 출력 | details `doc_references`, coverage 요약, versions "7", 기존 출력 불변(F14) |
| C18 | normal | symbol granularity CLI | versions "7" 외 base와 같음 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 참조 추출·해석 규칙의 정확성 |
| Performance efficiency | yes | 문서 1000개 규모 저장소(vendure)에서 시간 증가 제한 |
| Compatibility | yes | 기존 출력과 소비자(generate.py, delta.py, handout, HTML)가 깨지지 않아야 한다 |
| Interaction capability | yes | handout에서 dangling을 읽을 수 있어야 한다 |
| Reliability | yes | 임의 마크다운 텍스트에 예외 없이 동작 |
| Security | no | 파일을 새로 읽거나 경로로 접근하지 않고 snapshot 메모리 내용만 쓴다(경로 존재 판정은 inventory 집합 조회) |
| Maintainability | no | 단일 새 모듈, 별도 요구 없음 |
| Flexibility | no | 설정 항목 추가 없음 |
| Safety | no | 물리·인명 위험 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Functional suitability / correctness | 규칙 F1–F10 | 테스트 독립 기대값 대비 불일치 행 수 / 개 | 0 | V1–V7 | I1, I2 |
| Q2 | Performance efficiency / time behaviour, resource utilization | nowinandroid, vendure file granularity | 변경 후/base wall time, 최대 RSS / 비율 | 각 ≤ 1.05 | R1 | I4 |
| Q3 | Compatibility / co-existence | fixture 4개 file + 1개 symbol | F14 대상 값의 base 대비 차이 수 / 개 | 0 | V8 | I3 |
| Q4 | Interaction capability / operability | handout | dangling 블록 존재·정렬 / 예·아니오 | 존재, F13 순서 | V9 | F13 |
| Q5 | Reliability / fault tolerance | 무작위 마크다운 | 예외·property 위반 수 / 개 | 0 | V10, fuzz | Errors |
| Q6 | Functional suitability / appropriateness | vendure 사이트 route | `/` 링크 중 dangling 처리 수 / 개 | 0(모두 site_route 또는 resolved) | R1, V3 | I4 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | F1, C10 | `analyze_doc_references` | unit | equivalence partitioning | P1 ``` fence, P2 ~~~ fence, P3 4칸 들여쓴 ``` (fence 아님), P4 짧은 닫는 fence(닫히지 않음), P5 닫히지 않은 fence, P6 확장자 대소문자(`.MD`, `.mdx`, `.markdown`), P7 비문서 확장자(`.txt`) | 100% | fence 안 기록 없음, 문서 판정 기대대로 | pytest |
| V2 | F2, F3, F4, C1–C5, C11, C13, C15 | 링크 해석 | unit | decision table | 조건: 무시 대상(scheme/#/빈 값), `/` 접두, 존재(직접/접미 fallback 각 5종), 저장소 밖 → 규칙 R1 무시, R2 상대·존재, R3 상대·부재, R4 절대·존재, R5 절대·부재, R6 밖, R7 fallback 5종 각각, R8 excluded_files만, R9 디렉터리, R10 참조 정의 `[id]: t`, R11 이미지 | 100% | status·target·target_kind 기대값 | pytest |
| V3 | F5, C6 | 경로형 스팬 | unit | decision table | 규칙 (a) 존재/부재, (b) 존재/부재, (c) 존재/부재, 금지 문자 포함, scheme, `/` 접두, 이중 백틱 | 100% | F5 결과표 | pytest |
| V4 | F6, C7 | Gradle 스팬 | unit | equivalence partitioning | P1 모듈 존재, P2 부재(gradle 저장소), P3 gradle 모듈 없는 저장소, P4 module_dir 없는 gradle 노드만 있음, P5 형식 불일치(`:a b`) | 100% | resolved/dangling/무기록 | pytest |
| V5 | F7, C8, C9, C12 | 식별자 스팬 | unit | equivalence partitioning + boundary value analysis (2-value) | P1 label 1개, P2 여러 개, P3 0개, P4 dotted symbol_path 일치, P5 dotted 접미 일치, P6 대상 외 kind(field)만 일치, P7 `()` 접미; B1 매칭 10개, B2 11개 | 100% | status·candidates 정렬·상한·total | pytest |
| V6 | F8, F9 | 행 형식 | unit | equivalence partitioning | P1 file 노드 대상, P2 path, P3 directory, P4 null 대상, P5 행 순서(같은 줄 2개, 여러 문서) | 100% | 열 순서·값·정렬 | pytest |
| V7 | F10, F11, C3, C14 | candidate·summary·details 연결 | unit/integration | equivalence partitioning | P1 dangling 0인 문서, P2 1개, P3 여러 개, P4 문서 없음, P5 summary 개수 합 = 행 수 | 100% | candidate 필드·id 공식·evidence·summary 기대값; details·coverage에 들어감 | pytest |
| V8 | F11, F12, F14, C17, C18, Q3 | CLI bottleneck JSON·details 파일 | integration; base choice: fastapi-realworld file 기준, 다른 fixture 3개 file, fastapi-realworld symbol | combinatorial (base choice) | K1–K5 | 100% | 새 키 존재, versions "7", 새 키·새 kind 제거 후 base golden과 같음, symbol은 versions 외 동일 | pytest |
| V9 | F13, Q4 | handout | unit | equivalence partitioning | P1 dangling candidate 여러 개 정렬, P2 상한 초과 시 기존 "more" 문구 | 100% | 순서·형식 | pytest |
| V10 | Errors, C16, Q5 | `analyze_doc_references` | unit | error guessing | G1 짝 없는 `[`, G2 짝 없는 백틱, G3 `%zz`, G4 metadata None 노드, G5 label 정수, G6 빈 문서, G7 CRLF 줄바꿈의 줄 번호 | none — experience-based | 예외 없음, 줄 번호 정확 | pytest + fuzz |
| V11 | 전 요구 | 전 표면 | unit/integration | error guessing | G1 절대 링크 부재를 dangling 처리, G2 fence 안 추출, G3 문서 디렉터리 대신 루트만 사용, G4 fallback 접미 순서 뒤바뀜, G5 식별자 0 매칭을 dangling 처리, G6 ambiguous 상한 미적용, G7 gradle 모듈 없는 저장소에서 `:x`를 dangling 처리, G8 그래프에 노드·edge 추가 | none — experience-based | 각 추측 결함이 테스트로 거부됨 | pytest |
| V12 | Q2, Q6 | 실제 저장소 | review | — (measurement) | nowinandroid, vendure | 100% | 비율 ≤ 1.05, `/` 링크 dangling 0 | R1 |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v1 — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| A1 | 스키마 이름 유지, `versions.analysis` "7" | 키·candidate kind 추가만 있다. `bottlenecks/delta.py`는 cycle·rule_violation kind만 읽고 node_metrics·versions를 읽지 않는다. generate.py는 kind를 일반적으로 순회 | brief v1 — approved |
| A2 | 그래프에 넣지 않고 별도 출력 | 사용자 답변 | user answer |
| A3 | 참조 범위: 링크 + 경로형 스팬 + Gradle 경로 + 식별자 스팬 | 사용자 답변 | user answer |
| A4 | `/` 링크가 루트에 없으면 site_route | 사용자 답변. 측정: vendure 2405건 모두 docs 사이트 route | user answer |
| A5 | resolved 목록은 details 파일 | 사용자 답변 | user answer |
| A6 | candidate는 문서당 1개 | 참조당 1개면 vendure 경로형 스팬만 66개 이상; 문서 단위가 검토 단위와 맞음 | brief v1 — approved |
| A7 | 식별자 매칭 대상 kind: class, interface, enum, type_alias, function, method. field·constant·module 제외. ambiguous 후보 상한 10 | `id`·`name` 같은 field 이름이 대량 ambiguous를 만든다(vendure 식별자 스팬 8057개) | brief v1 — approved |
| A8 | 경로형 스팬은 자리표시자 문자(`*?<>{}[]$|`)를 포함하면 무시 | 측정: vendure dangling 경로 스팬 상당수가 `<name>`·`*` 예시 | brief v1 — approved |
| A9 | 튜토리얼 속 사용자 프로젝트 경로(`./src/index.ts`)는 dangling으로 남는다 | 문법으로 구분할 수 없음; recall 우선 원칙 | brief v1 — approved |
| A10 | HTML UI 변경 없음; 사람용 확인은 handout과 JSON | 파일 모드 candidate 목록은 파일 노드에만 붙음; 문서는 노드가 아님 | brief v1 — approved |
| A11 | Q2 임계 1.05 | 정규식 선형 스캔; 근거 없는 추정 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F1 | C10 | V1, V11 | pytest |
| F2 | C11 | V2 | pytest |
| F3 | C2, C15 | V2, V11 | pytest |
| F4 | C1, C3, C4, C5, C13 | V2, V11, V12 | pytest + R1 |
| F5 | C6 | V3, V11 | pytest |
| F6 | C7 | V4, V11 | pytest |
| F7 | C8, C9, C12 | V5, V11 | pytest |
| F8 | C1, C2, C15 | V6 | pytest |
| F9 | — | V6 | pytest |
| F10 | C3 | V7 | pytest |
| F11 | C14, C17 | V7, V8, V11 | pytest |
| F12 | C17, C18 | V8 | pytest |
| F13 | — | V9 | pytest |
| F14 | C17, C18 | V8, V11 | pytest + R1 |
| Q2, Q6 | — | V12 | R1 |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 2 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V1, V3, V5, V6, V7, V8 | 5 | tests/test_doc_references.py(150 tests), support, base_views.json | accepted (verifier 1) | hand M1, M4, M5, M6, M8, M9, M10 killed | correction 1·2는 V2·V4·V9·V10·V11 테스트만 추가·교체; 이 항목의 테스트·helper 불변 |
| V2, V4, V9, V10, V11 | 5 | correction batch 1(B1–B3, A3), batch 2(루트 링크, Gradle 동점) | accepted (verifier 2) | hand M2, M3, M7 killed; tool #1, #2 재적용 시 killed | B1–B3 closed |
| V12 | 5 | scratchpad doc-refs-r1/summary.md | accepted (main) | 시간 0.95/0.99, RSS 1.00/1.00, 기존 출력 차이 0, `/` 링크 dangling 0 | — |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 1 | 전체 suite: 3657 passed, 11 failed(test_analysis_coverage_reporting V05, test_file_analysis_cli V01×4, test_nestjs_quality O11×6) | 기존 실패 | base 7d16983·a8a3012 worktree에서 O11 재실행: 둘 다 실패 | 이번 변경과 무관(verified) |
| 3 | verifier 1 retry: B1 F3 디렉터리 우선 미고정(V2 R7, V11 G4), B2 Errors 필드별 제외 미검증(V10 G4/G5), B3 handout 형식·정렬 후 상한 미관찰(V9); advisory A1–A6 | 증거 공백(declared) | correction batch 1: test-implementer에 B1–B3 + A3(F4 절대 링크 fallback 고정, spec v4) + A6 지시. A1은 main 확인: skip 0 | 테스트 144개 통과; A2·A4·A5 advisory 유지 |
| 4 | hand mutation M1–M10 | — | scratchpad `doc-refs-hand/hand.py` | 10/10 killed(의도한 단언) |
| 5 | mutation tool seed 20261022, 30/172 표본: 28 killed, 2 survived(6.7%) | triager: #1 line 44 루트 디렉터리 링크 declared(F3/F4 증거 공백), #2 line 129 Gradle 동점 undeclared | spec v5: F8 루트 target ".", F6 동점 시 최소 id. correction batch 2: 테스트 추가 | 재적용 시 두 mutant 모두 killed |
| 6 | 전체 suite 3673 passed, 12 failed: 기존 11 + test_report_modal V04 ×2(flaky 브라우저, 이전 실행 통과) | 기존·flaky | — | 이번 변경과 무관 |
| 7 | R1(VM) | — | scratchpad doc-refs-r1/summary.md | Q2·Q6 충족, F14 실제 저장소 확인 |
| 8 | verifier 2 pass, 차단 finding 0; advisory: docstring 버전(수정함), 4칸 들여쓴 스팬·혼합 fence 경미한 커버리지 | — | — | complete |
| 2 | fuzz seed 20261022, 20000 입력 | — | scratchpad `doc-refs-fuzz/fuzz.py`; 첫 실행 위반 2건은 오라클의 조상 디렉터리 누락 | 오라클 수정 후 위반 0 |
| 0 | 사전 측정(VM, git ls-files 기준 프로토타입): nowinandroid 문서 44, 상대 링크 resolved 20/dangling 4, 경로 스팬 6/4, Gradle 38, 식별자 130. vendure 문서 1029, 상대 링크 184/5, `/` 링크 1/2405, 경로 스팬 90/66, 식별자 8057 | — | scratchpad `cd/docref.py` | A4, A7, A8 근거 |

# Version Log
## v1
- 초안. 사용자 답변: 별도 출력, 링크+경로형+식별자 스팬, `/` 링크 site_route, resolved 목록 details 파일.
## v2
- 계약 명확화(구현자 보고): F6 매칭 노드도 `module_dir` 필수(선언 의존 대상으로만 생긴 미해석 노드는 실제 모듈이 아님). F9 `text`의 `<>` 처리. F11 summary dict는 나온 키만. F4 루트·밖 절대 링크는 site_route, F5에는 fallback 없음. 사용자 brief 항목 변경 없음.
## v3
- 계약 명확화(test-implementer 보고): F3 디렉터리 우선으로 README/index 접미가 결과에 영향 없음을 명시, Errors의 비정상 노드 제외 범위를 필드별로 한정, F11 document_count 정의. 관찰 동작·brief 항목 변경 없음.
## v4
- 계약 명확화(verifier advisory A3): F4 절대 링크에도 F3 접미 fallback 적용 명시. 관찰 동작 변경 없음(구현이 이미 그렇게 동작).
## v5
- mutation 생존자 triage 반영: F8 저장소 루트 디렉터리 target "." 명시(declared 증거 공백), F6 같은 module_path 노드가 여럿이면 최소 id(undeclared → 결정적 규칙으로 확정; build_modules가 module_path로 id를 만들므로 실제 입력에서는 발생하지 않음). 관찰 동작 변경 없음.
## v6
- 완료: verifier 2 pass. status complete.
