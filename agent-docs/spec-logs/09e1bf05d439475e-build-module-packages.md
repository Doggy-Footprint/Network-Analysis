---
version: 6
run_id: 09e1bf05d439475e
status: complete
base_commit: a8a301272683e61b3e1f669995f969564b9cb907
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 분석기 사용자(사람·에이전트) | Gradle module과 npm workspace package를 의미 단위로 쓰는 저장소에서 module 단위 의존 구조를 본다 | file granularity 리포트에 `build` 체계의 `package_metrics`, `package_dependencies`, `package_cycle`, `unstable_dependency`, coverage가 나온다 |
| I2 | 분석기 사용자 | 빌드 파일에 선언된 module 간 의존을 graph에 넣어, 선언 의존과 코드 의존을 함께 본다 | `DECLARES_DEPENDENCY` edge가 module 노드 사이에 생기고, 해석하지 못한 대상은 버리지 않고 `unresolved`로 남는다 |
| I3 | eval 실험(handoff `e16d433ef30afd87`) | nowinandroid와 vendure 리포트가 이 체계를 쓴다 | 실제 저장소에서 build 체계가 계산된다(R1) |

# Scope
In scope:
- `language_analyzers/core/enrichment.py`에서 snapshot 내용만으로 다음을 한다:
  - Gradle module 탐지: 루트 `settings.gradle(.kts)`의 `include`, settings가 없으면 `build.gradle(.kts)` 디렉터리 fallback.
  - npm workspace package 탐지: 루트 `package.json`의 `workspaces`.
  - module 노드와 `DECLARES_DEPENDENCY` edge 생성.
- `analysis/structure.py`에 `build` 체계를 추가하고, `STRUCTURE_POLICY`를 `structure.v2`로 올린다.
- `RelationKind.DECLARES_DEPENDENCY` 추가.

Out of scope:
- Gradle 스크립트 실행 또는 평가.
- `project(":x").projectDir = ...` 재지정, `includeBuild`(composite build), version catalog(`libs.*`), 외부 artifact 의존.
- pnpm `pnpm-workspace.yaml`, lerna, nx `project.json`.
- 기존 `language`/`framework` 체계의 배정 규칙 변경.
- edge weight 프로필 변경(weight는 confidence·resolution으로만 정해진다).
- HTML 렌더러 UI 변경(체계 이름을 일반적으로 표시하므로 불필요).

# Paths
Implementation: language_analyzers/core/enrichment.py, language_analyzers/core/build_modules.py, language_analyzers/core/graph_models.py, analysis/structure.py, code_analyzer/cli.py
Tests: tests/
Test command: .venv/bin/python -m pytest -q
Review evidence: R1 real-repo run — main이 GCP VM(`e2-highmem-8`, asia-northeast3)에서 `scripts/eval/repos.json`의 nowinandroid, vendure 고정 commit을 depth-1 fetch한다. 각 저장소에서 base_commit 분석기와 변경 후 분석기를 실행한다(`.venv/bin/python -m code_analyzer.cli <clone> <analyzers> -o <out>/a.html --bottlenecks <out>/b.json`, analyzers는 nowinandroid `-f android`, vendure `-f nestjs`). 기록 항목: build 체계 package 수, unassigned 수, `DECLARES_DEPENDENCY` edge 수(resolution별), wall time. 산출물은 scratchpad `build-modules-r1/summary.md`, 요약은 Execution ledger에 남긴다.
Fuzzing: none — 입력 표면은 settings/build/package.json 텍스트의 정규식·JSON 해석이다. 깨진 입력은 error guessing Case(E1–E4)로 다룬다. 환경에 fuzz 도구(hypothesis 등)가 없다.
Mutation tool: main이 scratchpad에 작성하는 AST mutation 스크립트(비교·불리언·상수·조건 삭제 연산자). 대상은 base_commit 이후 변경된 Implementation Python 줄이다. 최대 30개 표본, seed 20261022. 실행 명령 `.venv/bin/python -m pytest -q -p no:cacheprovider -x -n 0 <이번 run이 추가·수정한 테스트 파일>`. 생존율 임계 40%.

# Signatures
- `RelationKind.DECLARES_DEPENDENCY = "DECLARES_DEPENDENCY"`
- module 노드 id: Gradle `build-module:gradle:<gradle path>`(예: `build-module:gradle::core:data`, 루트 `build-module:gradle::`), npm `build-module:npm:<package name>`.
- module 노드 필드:
  - `kind="module"`, `category="configuration"`, `group="configuration"`, `language="configuration"`.
  - `provenance`는 `"gradle"` 또는 `"npm-workspace"`.
  - `metadata` = `{"build_system": "gradle"|"npm", "module_path": <gradle path 또는 package name>, "module_dir": <snapshot root 기준 posix 디렉터리, 루트는 "">}`. 여기에 `file_path`와, span 있는 노드에 enrichment가 공통으로 붙이는 `line_number`·`end_line_number`가 더해질 수 있다.
  - build 파일이 snapshot에 있으면 `span=SourceSpan(<build file>, 1, 1)`과 `metadata.file_path=<build file>`을 둔다. Gradle은 `build.gradle.kts`를 `build.gradle`보다 우선하고, npm은 `package.json`이다.
  - `cost`는 `NodeCost(0, 0, 0)`이다(span 없는 노드도 cost가 있어 fallback 비용 limitation을 만들지 않는다).
- `DECLARES_DEPENDENCY` edge: source module 노드 → target module 노드.
  - `confidence="static_certain"`.
  - target이 탐지된 module이면 `resolution="exact"`, 아니면 `"unresolved"`. unresolved target은 같은 id 형식의 노드로 만든다(span 없음, `metadata.module_dir` 없음).
  - `evidence=SourceSpan(<build file>, <선언 줄>, <선언 줄>)`.
  - `metadata={"configuration": <Gradle configuration 이름 또는 npm dependency 필드 이름>}`.
  - 같은 (source, target, configuration)은 edge 하나로 합친다. evidence는 첫 줄이다.
- `analysis.structure.STRUCTURE_POLICY == "structure.v2"`.
- `build` 체계 package id: Gradle `pkg:gradle:<gradle path>`(예: `pkg:gradle::core:data`), npm `pkg:npm:<package name>`.

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F1 | 루트 `settings.gradle.kts` 또는 `settings.gradle`이 snapshot에 있으면, 그 안의 `include` 호출 인자 문자열 각각이 Gradle module이다. 지원 형식: `include(":a")`, `include(":a", ":b")`, `include ':a', ':b'`, 앞 콜론 없는 `"a:b"`(→`:a:b`). `//` 줄 주석과 `/* */` 블록 주석 안의 include는 무시한다. module 디렉터리는 path의 `:`를 `/`로 바꾼 값이다(`:core:data`→`core/data`). 루트 project `:`(디렉터리 `""`)도 항상 module이다. | must | handoff Next Step 2, A4 |
| F2 | 루트 settings 파일이 없고 `build.gradle(.kts)`가 하나 이상 있으면, 그 파일이 있는 디렉터리마다 module을 만든다. path는 `:` + 디렉터리의 `/`를 `:`로 바꾼 값이고, 루트 디렉터리는 `:`이다. | must | handoff Next Step 2, A2 |
| F3 | 루트 `package.json`의 `workspaces`(문자열 배열 또는 `{"packages": [...]}`) glob과 매칭되는 디렉터리 중 `package.json`이 snapshot에 있는 것마다 npm module을 만든다. glob은 `*`(한 경로 단계)와 `**`(0개 이상 단계)를 지원한다. `!` 부정 패턴은 매칭에서 제외한다. module id는 그 `package.json`의 문자열 `name`이고, 없으면 디렉터리 경로다. 루트 `package.json`도 `workspaces`가 있을 때 module이다(이름 없으면 `"(root)"`). | must | 사용자 답변(npm 포함), A5 |
| F4 | Gradle module의 build 파일에서 `project(":x")`, `project(path = ":x")`, 타입 안전 accessor `projects.a.bC`를 configuration 호출(`<ident>(...)`) 인자로 쓴 줄마다 `DECLARES_DEPENDENCY`를 만든다. accessor는 탐지된 module path의 각 단계를 kebab/snake → lowerCamel로 바꾼 값과 비교해 해석한다(`:core:data-test`→`projects.core.dataTest`). 해석 실패 시 `unresolved` target 노드는 `build-module:gradle:<accessor 원문>`이다. 주석 줄은 무시한다. | must | 사용자 답변(선언 의존 포함), A6 |
| F5 | npm module의 `package.json`에서 `dependencies`, `devDependencies`, `peerDependencies`, `optionalDependencies` key 중 workspace package 이름과 같은 것마다 `DECLARES_DEPENDENCY`(exact)를 만든다. evidence 줄은 그 key가 있는 줄이다. workspace에 없는 이름은 외부 의존이라 edge를 만들지 않는다. | must | 사용자 답변, A7 |
| F6 | file granularity에서 `build` 체계는 module 노드(provenance `gradle`/`npm-workspace`, `metadata.module_dir` 있음)가 하나 이상일 때만 계산한다. file은 같은 build system 안에서 `module_dir`이 가장 긴 접두(`dir == module_dir` 또는 `dir`이 `module_dir + "/"`로 시작, `""`는 모두 매칭)인 module 하나에 배정된다. Gradle과 npm이 함께 있으면 file은 각 build system에서 하나씩, 최대 2개 package를 가진다(shared). 어디에도 매칭되지 않는 file은 unassigned다. | must | 사용자 답변(build 체계), ADR 58424b9754efe9a2 |
| F7 | build 체계는 기존 체계와 같은 방식으로 `package_metrics`, `package_dependencies`, `package_cycle`, `unstable_dependency`, coverage(`assigned/unassigned/shared`)를 낸다. | must | I1 |
| F8 | `STRUCTURE_POLICY`는 `structure.v2`다. 그래서 build 체계가 없던 baseline과의 delta는 기존 policy 불일치 오류로 거부된다. | must | A3 |
| F9 | `code_analyzer/cli.py` `_run_merged`는 provenance가 `repository-enrichment`, `gradle`, `npm-workspace`인 노드가 여러 analyzer에서 같은 id로 나오면, 내용(`node_to_dict` 결과)이 같을 때 하나만 남긴다. 내용이 다르거나 다른 provenance의 중복 id는 기존처럼 `duplicate node id across analyzers` 오류로 종료한다. edge는 (from_id, to_id, relation, confidence, resolution, candidates, evidence, metadata)가 같은 것을 하나만 남긴다. 그래서 config 노드 중복으로 merge가 실패하던 기존 동작도 고쳐진다. | must | 사용자 답변(F9 추천안), 기존 enrichment 호출 구조 |
| F10 | Gradle·npm module이 없는 저장소의 분석 결과는 base_commit 대비 `structure_policy` 값 외에 바뀌지 않는다. | must | 기존 동작 보존 |

# Errors
- settings/build 파일이 정규식에 맞지 않는 내용이면 일치한 부분만 쓴다. 신호: 예외 없음, 매칭 안 된 include는 module이 아니다. 사후 상태: 나머지 분석은 정상이다.
- 루트 `package.json`이 JSON이 아니거나 `workspaces`가 문자열 배열/`{"packages": [...]}`가 아니면 npm module을 만들지 않는다. 신호: 예외 없음, npm module 0개. 사후 상태: Gradle 탐지와 나머지 분석은 정상이다.
- workspace `package.json`이 JSON이 아니면 그 module은 디렉터리 경로 id로 만들고 의존 edge는 만들지 않는다. 신호: 예외 없음. 사후 상태: 다른 module은 정상이다.
- include된 module의 build 파일이 snapshot에 없으면 module 노드는 span 없이 만든다(`module_dir`은 있음). 신호: 그 module로 배정된 file은 있을 수 있고, 그 노드는 file graph에서 edge가 닿을 때만 boundary가 된다.
- 같은 npm package 이름이 둘 이상이면 경로 사전순 첫 디렉터리만 그 이름을 쓰고, 나머지는 디렉터리 경로 id다. 신호: 예외 없음.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| N1 | normal | settings.gradle.kts `include(":app")`, `include(":core:data", ":core:model")`. 각 디렉터리에 build.gradle.kts와 `.kt` 파일. `core/data/build.gradle.kts`에 `implementation(projects.core.model)`, `app/build.gradle.kts`에 `implementation(project(":core:data"))` | module 노드 `:`, `:app`, `:core:data`, `:core:model`. edge `:app→:core:data`, `:core:data→:core:model`(exact, configuration `implementation`). build 체계에서 각 file이 `pkg:gradle::app` 등에 배정된다. package_dependencies에 해당 쌍이 있다 |
| N2 | normal | Groovy `settings.gradle`: `include ':a', ':b'`. `a/build.gradle`에 `api project(':b')` | module `:a`, `:b`. edge `:a→:b`(configuration `api`) |
| N3 | normal | settings 없이 `build.gradle.kts`가 `core/data`, `feature/topic/impl`에 있음 | module `:core:data`, `:feature:topic:impl`. 루트 build 파일이 없으면 루트 module도 없다. 다른 경로 file은 unassigned |
| N4 | normal | 루트 package.json `{"workspaces": ["packages/*"]}`. `packages/a/package.json` name `@x/a`, dependencies `{"@x/b": "*", "lodash": "^4"}`. `packages/b/package.json` name `@x/b` | module `@x/a`, `@x/b`, 루트 `(root)`. edge `@x/a→@x/b`(exact, configuration `dependencies`, evidence는 `"@x/b"` 줄). lodash edge는 없다. file 배정 `pkg:npm:@x/a` 등 |
| N5 | normal | workspaces `{"packages": ["libs/**"]}`, `libs/x/y/package.json` | `libs/x/y`가 module이다 |
| B1 | boundary | 중첩 module `:core`(core/)와 `:core:data`(core/data/) | `core/data/src/A.kt`는 `pkg:gradle::core:data`에만 배정된다. `core/B.kt`는 `pkg:gradle::core`에 배정된다 |
| B2 | boundary | 디렉터리 이름 접두 충돌: module `core`와 `core-ui` 디렉터리의 file | `core-ui/X.kt`는 `:core`에 배정되지 않는다 |
| B3 | boundary | module이 루트 `:` 하나뿐(settings에 include 없음) | build 체계에 `pkg:gradle::` 하나, 모든 file이 배정된다 |
| B4 | boundary | Gradle과 npm이 한 저장소에 함께 있음 | 양쪽 module에 매칭되는 file은 2개 package를 가진다. coverage `shared_files`에 포함된다 |
| B5 | boundary | 같은 의존이 `implementation`과 `testImplementation`으로 두 번 선언됨 | edge 2개(configuration별)이고, 같은 configuration 반복은 1개다 |
| E1 | error | `include(":ghost")`가 있지만 `ghost/` 디렉터리가 snapshot에 없음. 다른 module이 `project(":ghost")`를 참조 | `:ghost` 노드는 span 없이 생긴다. edge는 exact다. 예외는 없다 |
| E2 | error | `project(":missing")`(include 안 됨), `projects.nope` 참조 | target `build-module:gradle::missing`, `build-module:gradle:projects.nope`, resolution `unresolved` |
| E3 | error | 루트 package.json이 깨진 JSON | npm module 0개, Gradle 탐지는 정상, 예외 없음 |
| E4 | error | 주석 처리된 include와 project 참조(`// include(":x")`, `/* project(":y") */`) | 그것들로부터는 module과 edge가 없다 |
| E5 | error | 두 workspace package.json이 같은 name | 사전순 첫 디렉터리가 name id, 다른 쪽은 디렉터리 id |
| G1 | edge | Gradle·npm 빌드 파일이 없는 기존 fixture(fastapi-realworld, typescript-nestjs-realworld) | base_commit과 비교해 candidates, package_metrics, coverage가 policy 값(`dependency_network.structure_policy`, `coverage.structure.policy`) 외에 같다. coverage `schemes`에 `build`가 없다 |
| G2 | edge | python, kotlin, android 등 여러 analyzer가 한 저장소에 merge됨 | module 노드와 DECLARES_DEPENDENCY edge가 중복되지 않는다 |
| G4 | edge | 두 analyzer가 같은 id의 비-enrichment 노드를 냄 | 기존처럼 `duplicate node id across analyzers` 오류, 종료코드 1 |
| G3 | edge | `.fixtures/android-nowinandroid`(settings 없음) | fallback으로 `:core:data`, `:core:database` 등 module이 생기고 build 체계가 계산된다 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 체계와 relation이 정의대로 계산되어야 한다 |
| Performance efficiency | yes | vendure(대형 TS)와 nowinandroid에서 분석 시간이 늘면 안 된다 |
| Compatibility | yes | build 파일 없는 저장소의 출력 보존, delta policy 호환 신호 |
| Interaction capability | no | UI 변경 없음 |
| Reliability | yes | 깨진 빌드 파일에서 실패하면 안 된다 |
| Security | no | snapshot 텍스트만 읽고 빌드 스크립트를 실행하지 않는다 |
| Maintainability | yes | 프로젝트 주석 규칙과 기존 구조(체계별 배정 함수) 준수 |
| Flexibility | no | 설정 가능한 항목을 추가하지 않는다 |
| Safety | no | 물리적 위해 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Performance efficiency / time behaviour | 실제 nowinandroid, vendure 분석 | R1: base_commit 대비 변경 후 wall time 비율, 각 1회, 초 | ≤ 1.10배(낮을수록 좋음) | review R1 | A8 |
| Q2 | Compatibility / co-existence | build 파일 없는 fixture | G1: base_commit 출력과 비교한 차이 항목 수 | 0(`structure_policy` 제외) | automated | F10 |
| Q3 | Reliability / fault tolerance | 깨진 settings, build 파일, package.json | E1–E5에서 예외 발생 수 | 0 | automated, mutation | Errors |
| Q4 | Maintainability / modifiability | 변경된 Implementation 파일 | main 리뷰: AGENTS.md Comment Enforcement 위반 수, 새 외부 의존성 수 | 0, 0 | review (diff 검토 결과를 Execution ledger에 기록) | AGENTS.md |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | F1, N1, N2, E4 | settings 문법 분할: kts 단일 인자, kts 다중 인자, Groovy 공백 호출, 앞 콜론 없음, 줄 주석, 블록 주석 | integration: tmp 저장소 → `enrich_repository(..., snapshot=...)` 또는 analyzer 실행 후 노드 확인 | equivalence partitioning | 6개 분할 + 빈 문자열 뒤 줄 주석(`include(":a", "")  // include(":ghost")`), 빈 블록 주석(`/**/` 다음 줄 include) | 100% | 기대 module id 집합과 정확히 같다 | automated |
| V2 | F2, N3, B3, G3 | settings 유무 × 루트 build 파일 유무(4조합) + nowinandroid fixture | integration | decision table | 4개 규칙 + fixture 1 | 100% | module 집합이 F1/F2 규칙과 같다 | automated |
| V3 | F3, N4, N5, E3, E5 | workspaces 형식(배열, 객체, 깨진 JSON, 비지원 타입), glob(`*`, `**`, `!`), name(있음, 없음, 중복) | integration | equivalence partitioning | 10개 분할 + 패턴보다 얕은 디렉터리(`packages/*`일 때 `packages/package.json`은 module 아님), 긍정 패턴 꼬리가 다른 디렉터리 이름과 같음(`["*", "ab"]`일 때 `b`는 module) | 100% | 기대 npm module id 집합 | automated |
| V4 | F4, N1, N2, B5, E1, E2, E4 | Gradle 참조 형식(`project(":x")`, `project(path=)`, accessor 단순, accessor camel 변환, 미해석 project, 미해석 accessor, 주석) × configuration 구분 | integration | equivalence partitioning | 7개 분할 + B5 + 빈 문자열 뒤 줄 주석의 project 참조 무시 + module 노드 cost `NodeCost(0, 0, 0)` | 100% | edge (from,to,resolution,configuration,evidence 줄)가 기대값과 같다 | automated |
| V5 | F5, N4 | npm 의존 필드 4종, workspace 아닌 이름, evidence 줄 | integration | equivalence partitioning | 6개 분할 | 100% | 기대 edge 집합 | automated |
| V6 | F6, B1, B2, B3, B4, E1 | 최장 접두 배정 경계: 정확히 같은 dir, 하위 dir, 접두 문자열만 같은 형제 dir, 루트 `""`, 두 build system 공존, build 파일 없는 include module(span 없음) 아래 file | integration: `analyze_structure` 또는 bottleneck payload | boundary value analysis (2-value) | 6개 경계 | 100% | package 배정, unassigned, shared가 기대값과 같다. span 없는 module 아래 file은 그 module의 `pkg:gradle:<path>`에 배정된다 | automated |
| V7 | F7, N1, N4 | build 체계 출력: package_metrics, package_dependencies, package_cycle(서로 참조하는 두 module), unstable_dependency, coverage | end-to-end: CLI `--bottlenecks` JSON | scenario testing | 5개 출력 항목 | 100% | 각 항목에 build 체계 값이 기대대로 존재 | automated |
| V8 | F8 | policy 값, 구 baseline(`structure.v1`) delta | unit | equivalence partitioning | 2 | 100% | 값 `structure.v2`, v1 baseline delta는 기존 policy 불일치 오류 | automated |
| V9 | F9, G2, G4 | merge 분할: (a) python+typescript, Gradle settings·npm workspaces 저장소, (b) python+typescript, yaml config 저장소(기존 실패 재현), (c) 허용 provenance 집합(`repository-enrichment`, `gradle`, `npm-workspace`) 밖의 같은 id 중복 → 오류, (d) 허용 provenance에서 같은 id·같은 provenance·다른 `node_to_dict` 내용 → 오류, (e) 같은 id, 서로 다른 허용 provenance(`gradle` vs `repository-enrichment`) → 오류, (f) 같은 module 쌍을 두 configuration으로 선언한 저장소의 python+typescript merge → 두 edge가 각각 하나씩 남음, (g) unit 정상 경로: 두 arch에 같은 허용 provenance 노드(내용 동일)와, F9 key 중 metadata 또는 evidence만 다른 edge → 노드 1개, 완전히 같은 edge는 1개, metadata·evidence만 다른 edge는 각각 남음 | end-to-end CLI(a, b, c, f), unit `_run_merged(args, project_path, None, None, results=[(arch, None, []), ...])`(d, e, g). (g)는 `args.granularity="file"`이면 coverage·route 단계를 통과해 merged 객체를 돌려준다(main 확인). arch는 `project_name`, `project_path`, `nodes`, `edges=[]`, `report_collections=[]`, `stats={}` 속성을 가진 객체다. 중복 검사는 coverage 계산 전에 종료한다 | equivalence partitioning | 7 | 100% | (g) 기대 노드·edge 목록, (a)(b)(f) 종료코드 0, 노드 id 중복 0, edge는 F9 key 기준 중복 0이고 (f)는 configuration별 edge 2개, (c)(d)(e) `SystemExit` 코드 1과 `[!] Error: duplicate node id across analyzers: <id>` | automated |
| V10 | F10, G1, Q2 | build 파일 없는 fixture 2개 | end-to-end: base_commit 출력 golden과 비교 | metamorphic testing | 2개 fixture | 100% | `structure_policy` 외 차이 0 | automated |
| V11 | Q3, Errors | 깨진 입력 추측 결함: 예외 전파, 부분 매칭 실패, JSON 타입 오류(`workspaces: 3`, `name: 5`), 비UTF8 없음(snapshot이 이미 텍스트) | integration | error guessing | E1–E5 + 타입 오류 2 + E1 boundary 조건(file granularity에서 span 없는 module 노드는 edge가 닿을 때만 boundary 노드로 나타나고, 닿지 않으면 file graph 노드에 없다) | none — experience-based | 예외 없이 Errors 절의 사후 상태 | automated |
| V12 | Q1 | 실제 저장소 | review | — | nowinandroid, vendure | 100% | wall time 비율 ≤1.10 | review R1 |
| V13 | Q4 | 변경 diff | review | — | 변경 파일 전체 | 100% | 위반 0 | review |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| A1 | 별도 `build` 체계, npm workspace 포함, 선언 의존 edge 포함 | 사용자 답변 | user answer |
| A2 | settings가 없으면 `build.gradle(.kts)` 디렉터리 fallback을 쓴다. settings가 있으면 fallback을 쓰지 않는다 | 부분 snapshot(nowinandroid fixture)에서도 체계를 낸다. 실제 저장소는 settings가 있다 | brief v1 — approved |
| A3 | `STRUCTURE_POLICY`를 `structure.v2`로 올린다 | 올리지 않으면 이전 baseline과의 delta가 build 체계와 새 edge를 모두 "새 package 의존"으로 보고한다(`bottlenecks/delta.py` `_dependency_map`) | user answer |
| A4 | 루트 project `:`는 항상 module이다(settings가 있을 때). 그래서 `build-logic/` 같은 included build file도 루트에 배정된다 | Gradle에서 루트 project는 항상 존재한다. includeBuild는 범위 밖이다 | brief v1 — approved |
| A5 | npm은 `workspaces`가 있을 때만 탐지하고, 디렉터리 fallback은 없다 | package.json마다 module로 만들면 예제·fixture package.json이 섞인다 | brief v1 — approved |
| A6 | test configuration(`testImplementation` 등)도 edge로 만들고 configuration 이름을 metadata에 남긴다 | 재현율 우선(AGENTS.md). 가중 차등은 하지 않는다 | brief v1 — approved |
| A7 | npm `workspace:` 프로토콜이나 버전 문자열과 무관하게, key 이름이 workspace package 이름이면 edge를 만든다 | npm workspace는 이름으로 링크한다 | brief v1 — approved |
| A8 | 성능 임계는 R1 wall time ≤1.10배다 | 탐지는 build 파일 수에 선형이라 영향이 작을 것으로 예상한다. 측정 1회라 잡음이 있을 수 있다 | brief v1 — approved |
| A10 | `platform(...)`, `enforcedPlatform(...)`, `testFixtures(...)` 안의 project 참조는 그 바깥 호출 이름을 configuration으로 쓴다 | 이 셋은 configuration이 아니라 의존 표기 wrapper다 | brief v2 — 기본값 고지 |
| A11 | 내용이 빈 build 파일의 module 노드는 span과 `metadata.file_path`가 없다(`module_dir`은 있다) | 1:1 span이 file granularity 줄 범위 검증에 걸린다 | brief v2 — 기본값 고지 |
| A12 | 자기 자신을 가리키는 참조와, 감싸는 호출 이름이 없는 참조는 edge를 만들지 않는다 | 기존 `_append_edge`가 self-edge를 만들지 않는다 | brief v2 — 기본값 고지 |
| A9 | 새 탐지 코드는 `language_analyzers/core/build_modules.py`에 두고 enrichment에서 호출한다 | enrichment.py가 이미 크다 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F1 | N1, N2, E4 | V1 | automated |
| F2 | N3, B3, G3 | V2 | automated |
| F3 | N4, N5, E3, E5 | V3, V11 | automated |
| F4 | N1, N2, B5, E1, E2, E4 | V4, V11 | automated |
| F5 | N4 | V5 | automated |
| F6 | B1, B2, B3, B4 | V6 | automated |
| F7 | N1, N4 | V7 | automated |
| F8 | — | V8 | automated |
| F9 | G2, G4 | V9 | automated |
| F10 | G1 | V10 | automated |
| Q1 | — | V12 | review R1 |
| Q2 | G1 | V10 | automated |
| Q3 | E1–E5 | V11 | automated |
| Q4 | — | V13 | review |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 5 |
| verifier invocations | 2 |
| open finding ids | none (advisory A-1~A-4 남음) |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V1–V11 | 6 | tests/test_build_modules.py(78), tests/android_build_support.py, tests/structure_support.py, tests/build_modules_evidence/*; suite 7 failed(전부 base 기존 실패)/3522 passed | accepted | verifier 2 pass. 손 mutation 10 + 생존 재적용 5 모두 killed, 도구 생존율 20% | Implementation·test helper 변경 시 재검토 |
| V12 | 3 | ledger 3, scratchpad `build-modules-r1/summary.md` | accepted | Q1 1.009배 이하 | 분석기 동작 변경 시 재측정 |
| V13 | 3 | main diff 리뷰: 주석 3개(cli.py 중복 사유, build_modules.py wrapper·빈 파일 span 제약) 모두 비자명 제약, 새 import는 표준 라이브러리만 | accepted | 위반 0 | Implementation 변경 시 재검토 |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 1 | implementer: F9 막힘(`cli.py` `_run_merged` 중복 id 종료) | verified: `cli.py:329-332` | v2에서 cli.py를 Implementation에 추가 | F9 구현, implementer smoke 통과 |
| 2 | 전체 suite 36 failed / 3483 passed | 분류: (a) base_commit worktree에서도 실패하는 기존 실패 6개(`test_file_analysis_cli` V01×4, `test_analysis_coverage_reporting` V05, `test_report_modal`[connection]), (b) policy v2 문자열이 들어간 golden 비교, (c) android-nowinandroid 출력 변화(build module 추가로 정상) | (a)는 범위 밖 기존 결함으로 기록. (b)(c)는 test defect로 correction batch 1 | (b) policy 문자열 정규화(`with_base_policy`), (c) nowinandroid는 build-only 차이 검사(`tests/android_build_support.py`)와 base 증거 파일로 대체. 정확 제거 방식은 graph 전역 지표(pagerank 등)가 모든 노드에서 바뀌어 불가(test-implementer 측정). Q04 크기 비율은 android만 build 부분 제거 후 측정(1.005). 결과 6 failed(전부 (a)) |
| 2b | `-f android` symbol에서 `component_synth_SingletonComponent` token_cost −1, 주변 hop_2 −1 | verified: fallback cost가 `metadata.analysis` 직렬화 길이를 포함(`analysis/graph_metrics.py` `_node_token_cost`), 전역 지표 문자열 길이 변화(19→18자) | 기존 동작의 부수 효과로 판정, android 사례에 ±1 허용 | accepted |
| 4 | verifier 1: retry, F-1 V9 edge dedup key 증거 없음, F-2 span 없는 module 배정·boundary 증거 없음, F-3 허용 provenance 내 다른 내용 중복 미검증 | — | 손 mutation: (1) cli edge key를 (from,to,relation)으로 축소 → 첫 시도는 치환이 문법 오류를 만들어 inconclusive, 재시도에서 tests/test_build_modules.py 66 passed(생존, 공백 확인). (2) structure `_build_packages`에 span 조건 추가 → 66 passed(생존, 공백 확인) | F-1·F-2 obligation evidence gap, F-3 spec challenge → v4에서 V9(d)(e)(f), V6 경계, V11 boundary 조건 추가, correction batch 3 |
| 5 | 손 mutation 10개(M1–M10, scratchpad `hand.py`, 대상 tests/test_build_modules.py + tests/test_structure_integration.py) | — | M2 span 무시, M3 id만으로 dedup, M4 `/` 없는 접두, M5 최단 접두, M6 configuration 없는 edge key, M7 build 파일 주석 미제거, M8 camel 변환 제거, M9 `!` 무시, M10 unresolved→exact: 모두 killed. M1 merge edge key 축소: survived | M1 생존 원인 verified: dedup은 analyzer 간에만 일어나고 같은 snapshot에서 enrichment edge는 analyzer마다 동일해 CLI 관찰면에서 구분 불가. unit 주입 정상 경로가 동작함을 main이 확인 → v5 V9(g) 추가, correction batch 4 |
| 6 | M1 재실행: V9(g) 2개 테스트가 잡음(killed). mutation 도구(scratchpad `mutate.py`, seed 20261022, cap 30, 대상 tests/test_build_modules.py + tests/test_structure_integration.py): 30 실행, 24 killed, 6 survived(2·3번은 같은 상수 중복 표본) → 생존율 20% < 40% | — | mutant-triager: 2 undeclared(module cost 값 미정), 4·7·20·23 declared(빈 문자열 뒤 주석, 빈 블록 주석, 얕은 디렉터리 glob, 긍정 패턴 꼬리) | v6에서 cost 값 명시, V1·V3·V4 coverage item 추가, correction batch 5 |
| 7 | 생존 mutant 재적용(T2 cost, T4 문자열 스캔, T7 빈 블록 주석, T20 얕은 glob, T23 부정 패턴): 모두 killed. tests/test_build_modules.py 78 passed | — | — | 4·7·20·23 declared gap 해소, 2 undeclared는 v6 spec 명시 후 해소 |
| 8 | verifier 2: pass, F-1~F-3 closed | — | advisory A-1(confidence·resolution·candidates만 다른 edge merge 미검증), A-2(span 없는 module cost 미검증), A-3(V9 e가 d와 분리되지 않음), A-4(fuzz oracle 제안) | complete |
| 3 | R1 review (GCP `na-eval` e2-highmem-8) | — | 산출물 scratchpad `build-modules-r1/summary.md` | nowinandroid wall 9.39s→7.18s(0.76), RSS 341→325MB, build 36 pkg(35 include+root), assigned/unassigned/shared 372/0/0, DECLARES exact 106, build candidate package_cycle 5·unstable_dependency 206. vendure 201.7s→203.6s(1.009), RSS 3.18→3.25GB, build 19 pkg, 3706/0/0, DECLARES exact 42, package_cycle 3. Q1(≤1.10) 통과. 관찰: Gradle은 module 간 선언 순환을 허용하지 않으므로 nowinandroid build package_cycle 5개는 코드 edge(ambiguous 등) 기원으로 추정(hypothesis) |

# Version Log
## v6
- mutation 도구 생존 mutant 반영: module 노드 cost를 `NodeCost(0, 0, 0)`으로 명시(기존 구현값, 동작 변화 없음), V1·V3·V4에 경계 coverage item 추가.
## v5
- V9(g) 추가: M1(merge edge key 축소) 손 mutation이 CLI 관찰면에서 생존. unit 주입 정상 경로로 F9 edge key를 관찰한다.
## v4
- verifier 1 F-1~F-3 반영: V9에 (d)(e)(f) 추가와 (c) 문구 명확화(허용 provenance 집합 밖), V9 (d)(e)의 관찰면을 `_run_merged` unit 주입으로 지정. V6에 span 없는 module 경계 추가, V11에 E1 boundary 조건 추가.
## v3
- contract-only: module 노드 metadata의 공통 키(`line_number`, `end_line_number`, `file_path`) 허용, G1 예외에 `coverage.structure.policy` 명시, V9(c) 관찰면을 CLI로 변경(기존 테스트에 `_run_merged` results 구성 예가 없음). test-implementer 보고의 해석(`libs/**`는 `libs` 포함, 문자열 `workspaces`는 미지원, settings가 있으면 루트 `:`는 build 파일이 없어도 module)을 그대로 확정.
## v2
- F9 범위를 `code_analyzer/cli.py` `_run_merged`로 넓혔다. 근거: implementer 보고와 main 확인(`cli.py:329-332`가 analyzer 간 중복 id에서 종료한다). 기존 config 노드 중복 실패도 같은 원인이다. 사용자가 추천안을 승인했다.
- G4 Case, V9 분할 추가. A10–A12는 implementer 보고의 미정 항목을 기본값으로 정했다.
- R1 실행 위치를 GCP VM으로 바꿨다(사용자 결정).
## v1
- 초안. handoff `b6db876d7191e86d`와 사용자 답변(build 체계, npm 포함, 선언 의존 포함)에서 작성.
