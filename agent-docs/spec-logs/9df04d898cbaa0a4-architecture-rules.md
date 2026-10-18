---
version: 4
run_id: 9df04d898cbaa0a4
status: complete
base_commit: ef8adb352c32936b102ed06d8dcb3ad2f28e6bdd
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자 | "Architecture 분석 기능을 추가하고 싶어. goal: keep AI written codes maintanable" | 사용자가 YAML로 선언한 layer 경계를 넘는 file 의존이 `rule_violation` 구조 사실로 bottleneck JSON과 HTML에 나온다 |
| I2 | 사용자 | layer 선택자는 경로 glob과 package id 둘 다 | 규칙 file의 layer가 `paths` glob과 Phase 1 package id 패턴 `packages`로 file을 고른다 |
| I3 | 사용자 | `allow`는 layer별 허용 목록(①) | `allow`에 적힌 layer에서 목록 밖 layer로 가는 의존만 allow 위반이고, 적히지 않은 layer는 `forbid`만 적용된다 |
| I4 | 사용자 | 외부 library 규칙은 2b run으로 분리 | 이번 run에서 `external`/`to_external` key는 "아직 지원하지 않음" 오류로 거부된다 |

# Scope
In scope: `--architecture-rules PATH` CLI 옵션, 규칙 YAML loader와 strict 검증, path glob/package 패턴 매칭, file→layer 배정, file 모드에서 `rule_violation` candidate와 `coverage.architecture_rules`, `profiles/architecture_rules.example.yaml`, report validator의 새 kind label, HTML의 위반 이유 표시.
Out of scope: 외부 library 규칙과 외부 import 추출(2b), 위반 시 exit code 변경과 baseline 비교(Phase 3), HTML Structure 패널(Phase 3), symbol granularity 지원, Gradle module 체계(handoff `agent-docs/handoff/b6db876d7191e86d-gradle-module-package-scheme.md`), 규칙이 없을 때의 출력 변경, 기존 candidate kind·지표·Phase 1 구조 사실의 의미 변경, `report/bottlenecks/generate.py`의 `_KIND_SCORE_FIELDS` 우선순위 점수, glob의 `[...]`·`{a,b}` 문법.

# Paths
Implementation: analysis/architecture_rules.py, analysis/structure.py, bottlenecks/core.py, code_analyzer/cli.py, report/bottlenecks/generate.py, renderers/html/static/app.js, profiles/architecture_rules.example.yaml
Tests: tests/test_architecture_rules.py, tests/test_architecture_rules_integration.py, tests/test_architecture_rules_browser.py, tests/architecture_rules_support.py, tests/architecture_rules_evidence/
Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','android-nowinandroid','typescript-nestjs-realworld')]" && uv run -q --with-requirements requirements-dev.txt --with coverage python -m coverage run --branch --include=analysis/architecture_rules.py -m pytest -q -p no:cacheprovider && uv run -q --with coverage python -m coverage report --fail-under=90
Review evidence: R1 — main이 fastapi-realworld를 `-l python --granularity file --bottlenecks`로 규칙 없이, 그리고 예제 규칙과 함께 실행하고, `tests/architecture_rules_evidence/size.json`(`{no_rules_bytes, rules_bytes, ratio, violation_counts_by_rule}`)에 기록한다. 위반 목록이 F07 예제의 의도(domain→services, db→api)와 맞는지 사람이 읽고 확인한다. R2 — main이 예제 규칙을 적용한 fastapi-realworld HTML을 브라우저로 열어 위반 이유 표시를 스크린샷으로 `tests/architecture_rules_evidence/`에 남긴다.
Fuzzing: main이 scratchpad에 작성한 stdlib 기반 harness. 표면 (a) `load_architecture_rules`: 문법 기반 무작위 YAML 문서(정상 문서의 key 삭제·추가·타입 교체·값 변형)와 byte 변형. oracle: crash — `ArchitectureRulesError` 외 예외 0. (b) `match_path`: 무작위 pattern(`*`, `**`, `?`, 리터럴, `/`)과 무작위 경로. oracle: differential — 재귀 segment 매처(main 작성)와 결과가 같다. seed 20261018, 예산 각 20,000 입력.
Mutation tool: main이 scratchpad에 작성한 AST mutation 스크립트(비교·산술·불리언·상수·조건 삭제 연산자). base_commit 이후 변경된 Implementation Python 줄만 대상. 최대 30개 표본, seed 20261018. 실행 명령 `uv run -q --with-requirements requirements-dev.txt python -m pytest -q -p no:cacheprovider -x tests/test_architecture_rules.py tests/test_architecture_rules_integration.py`. 생존율 임계 40%.

# Signatures
`analysis.architecture_rules.RULES_POLICY = "architecture_rules.v1"`
`analysis.architecture_rules.ArchitectureRulesError(ValueError)` — 메시지는 사람이 읽을 수 있는 원인을 담는다.
`analysis.architecture_rules.load_architecture_rules(path: str | Path) -> ArchitectureRules`
`analysis.architecture_rules.ArchitectureRules` (frozen dataclass): `version: int`, `layers: Mapping[str, LayerSelector]`(layer 이름 정렬 순), `allow: Mapping[str, tuple[str, ...]]`(정렬·중복 제거), `forbid: Mapping[str, tuple[str, ...]]`(from layer → 금지 to layer, 정렬·중복 제거, 같은 from의 여러 항목은 합집합)
`analysis.architecture_rules.LayerSelector` (frozen dataclass): `paths: tuple[str, ...]`, `packages: tuple[str, ...]`(입력 순서 유지)
`analysis.architecture_rules.match_path(pattern: str, path: str) -> bool` — F03 의미. pattern은 load 시 검증을 통과한 것만 받는다.
`analysis.architecture_rules.layer_assignments(rules: ArchitectureRules, files: Iterable[str], packages: Mapping[str, Mapping[str, list[str]]]) -> dict[str, str]` — `{file_id: layer}`, 매칭된 file만 포함. `packages`는 `analysis.structure.package_assignments` 형식. F05 다중 매칭이면 `ArchitectureRulesError`.
`analysis.structure.analyze_structure(architecture, weights, rules: ArchitectureRules | None = None) -> StructureResult` — `rules`가 None이면 Phase 1과 같은 결과. rules가 있으면 `rule_violation` candidate가 `candidates`에 합쳐지고 `coverage["architecture_rules"]`(F10)가 추가된다. file id가 `file:`로 시작하지 않으면 id 전체를 경로로 쓴다.
`bottlenecks.core.analyze_bottlenecks(snapshot, architecture, weights, *, analysis=None, rules: ArchitectureRules | None = None) -> BottleneckReport`

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F01 | 규칙 문서는 YAML mapping이다. top-level key는 `version`(필수), `layers`(필수), `allow`(선택), `forbid`(선택)이고 그 외 key는 오류다. 단 `external` key는 F02의 전용 메시지로 거부한다. `version`은 bool이 아닌 int 1이어야 한다. 파일 읽기 실패, UTF-8 decode 실패, YAML 구문 오류, top-level이 mapping이 아님은 모두 `ArchitectureRulesError`다. | required | 계획 Phase 2a, edge_weights loader 패턴 |
| F02 | `external`(top-level) 또는 forbid 항목의 `to_external` key가 있으면 메시지에 `external`과 `not supported`를 포함한 `ArchitectureRulesError`를 낸다. | required | I4 |
| F03 | `layers`는 비어 있지 않은 mapping이다. layer 이름은 정규식 `^[A-Za-z][A-Za-z0-9_-]*$`를 만족하는 문자열이다. 값은 key가 `paths`·`packages`의 비어 있지 않은 부분집합인 mapping이고, 각 값은 비어 있지 않은 list, 원소는 비어 있지 않은 문자열이다. path 패턴은 `/`로 시작할 수 없고, `**`는 segment 전체로만 쓸 수 있다(`a**`, `**b`는 오류). | required | I2 |
| F04 | path 패턴 의미(`match_path`): 패턴과 경로를 `/`로 나눈 segment 단위로 전체 일치를 본다. 패턴 끝이 아닌 segment `**`는 0개 이상의 segment와 일치하고, 패턴의 마지막 segment인 `**`는 1개 이상의 segment와 일치한다(gitignore와 같이 `app/**`는 `app` 자신이 아니라 그 아래 경로만 고른다). 연속된 `**` segment는 하나로 본다. segment 안의 `*`는 `/`를 제외한 0개 이상의 문자, `?`는 `/`를 제외한 문자 1개와 일치한다. 그 외 문자는 리터럴이다(`[`, `]`, `{`, `.` 포함). 대소문자를 구분한다. 경로는 file id에서 `file:` 접두를 뗀 snapshot root 기준 posix 경로다. 예: `app/**`는 `app/a.py`, `app/x/y.py`와 일치하고 `app`, `apps/a.py`와 불일치. `app/*.py`는 `app/a.py`와 일치하고 `app/x/a.py`와 불일치. `**/models.py`는 `models.py`와 `a/b/models.py`에 일치. | required | I2 |
| F05 | file F가 layer L에 매칭되는 조건: L의 path 패턴 중 하나가 F 경로와 일치하거나, L의 package 패턴 중 하나가 `fnmatch.fnmatchcase` 의미로 F의 package id(`package_assignments`의 모든 체계, 모든 package) 중 하나와 일치한다. 대상 file은 boundary가 아닌 file node 전부다. 한 file이 2개 이상 layer에 매칭되면 `ArchitectureRulesError`이고, 메시지에 그런 file 수와 정렬 순 앞 10개 file 경로 및 각 file의 매칭 layer 이름을 담는다(A01). | required | I2, D1 |
| F06 | `allow`는 mapping `layer → list[layer]`(빈 list 허용)다. `forbid`는 list이고 각 항목은 key가 정확히 `from`, `to`인 mapping이다. `from`은 layer 이름, `to`는 비어 있지 않은 layer 이름 list다. 다음은 오류다: 정의되지 않은 layer 이름 참조, `allow` 목록이나 `forbid.to`에 자기 자신(key/`from`과 같은 layer) 포함, 타입 불일치. list 안의 중복은 제거한다. | required | I3 |
| F07 | `profiles/architecture_rules.example.yaml`은 아래 내용(주석 제외 의미 동일)이고 F01–F06 검증을 통과한다. ```version: 1 / layers: {api: {paths: ["app/api/**"]}, services: {paths: ["app/services/**"]}, db: {paths: ["app/db/**"]}, domain: {packages: ["pkg:python:app.models.domain"]}, schemas: {packages: ["pkg:python:app.models.schemas"]}, core: {paths: ["app/core/**", "app/resources/**"]}} / allow: {domain: []} / forbid: [{from: db, to: [api]}, {from: services, to: [api]}]``` | required | 계획, R1 측정 |
| F08 | 위반 판정: `all` tier file pair 기록(Phase 1 F02, TESTS·boundary 제외) (F→G)마다, F≠G이고 F, G가 모두 layer에 배정되었고 layer(F)=A ≠ layer(G)=B일 때: (a) A가 `allow` key이고 B가 `allow[A]`에 없으면 allow 위반, (b) B가 `forbid[A]`에 있으면 forbid 위반. 둘 다 해당하면 candidate 2개다. 같은 layer 안 의존, 배정되지 않은 file이 끝점인 의존은 위반이 아니다. | required | I3 |
| F09 | `rule_violation` candidate: identifier = `rule|<allow\|forbid>|<A>|<B>|<F>|<G>`(F, G는 file id). `id`·`status`는 `bottlenecks.core._candidate` 규칙. `kind` = `rule_violation`, `target` = F, `metrics` = {`evidence_count`, `max_weight`}(pair 기록 값), `evidence` = [pair 기록](Phase 1 F02 필드: from_id, to_id, relations, max_weight, evidence_count, detail_edge_indices, tier), `coverage` = `static_analyzer_relation`, `structure` = {`rule_type`: `allow`\|`forbid`, `from_layer`: A, `to_layer`: B, `tier`: pair tier, `relations`: pair relations}. candidate는 기존·Phase 1 candidate와 합쳐 (kind, id) 순으로 정렬한다. | required | 계획 |
| F10 | 규칙이 주어지면 `coverage.architecture_rules` = {`policy`: RULES_POLICY, `version`: 규칙 version, `layer_file_counts`: {layer: 배정 file 수}(모든 정의 layer, 0 포함, 이름 정렬), `unassigned_file_count`, `unassigned_files`(file id, `file:` 접두 포함, 정렬), `empty_layers`(배정 file 0인 layer, 정렬), `violation_count`: rule_violation candidate 수}. empty layer는 오류가 아니다. | required | 계획 |
| F11 | 규칙이 없으면(`rules=None`, CLI 옵션 없음) bottleneck JSON은 base_commit 출력과 byte 단위로 같다(HTML은 app.js 변경으로 달라질 수 있다). schema는 `bottlenecks.v8`를 유지한다. | required | D3, 호환성 |
| F12 | CLI `--architecture-rules PATH`. (a) `--granularity symbol`과 함께 쓰면 argparse `parser.error`(exit 2, 기존 `--entrypoint` 검사와 같은 방식). (b) 규칙 load 실패는 snapshot 단계 오류와 같은 형식 `[!] Error: <message>`을 stderr에 쓰고 exit 1이며, 출력 file을 쓰지 않는다. (c) F05 다중 매칭 오류도 `[!] Error: <ArchitectureRulesError 메시지>` 형식으로 exit 1이고 출력 file을 쓰지 않는다. `analyze_bottlenecks`는 `ArchitectureRulesError`를 `BottleneckInputError`로 감싸지 않고 메시지를 보존한다. (d) 위반이 있어도 exit code는 0이다(A02). | required | 계획, D2 |
| F13 | `report/bottlenecks/generate.py`: `KIND_LABELS["rule_violation"] = "경계 규칙 위반"`, `KIND_DESCRIPTIONS`에 설명 추가. v8 검증은 `rule_violation` kind와 `coverage.architecture_rules`를 받아들인다. | required | 계획 |
| F14 | HTML file 모드: `rule_violation`은 target file의 기존 candidate 표시 자리에 kind label `경계 규칙 위반`과 이유 `<from_layer> → <to_layer> · <허용 목록 밖\|금지 규칙>`(allow→`허용 목록 밖`, forbid→`금지 규칙`)로 표시된다. 문자열은 text로 삽입된다. | required | 계획 |
| F15 | 같은 입력과 규칙에 대한 결과는 실행마다 byte 단위로 같다(PYTHONHASHSEED 무관). | required | 기본 원칙, Phase 3 전제 |

# Errors
- 규칙 file 없음/읽기 불가, 비 UTF-8, YAML 구문 오류, schema 위반(F01–F03, F06) — `ArchitectureRulesError`(원인 메시지). CLI: stderr `[!] Error: ...`, exit 1. post-state: 분석을 시작하지 않고 출력 file이 써지지 않는다.
- `external`/`to_external` 사용 — 메시지에 `external`, `not supported`. 나머지는 위와 같다.
- 다중 layer 매칭(F05) — 분석 후 `ArchitectureRulesError`. CLI: stderr `[!] Error: ...`(file 수와 앞 10개), exit 1. post-state: HTML·JSON·bottleneck 출력 file이 써지지 않는다.
- `--architecture-rules`와 `--granularity symbol` — argparse 오류, exit 2. post-state: 아무 file도 읽거나 쓰지 않는다.
- layer가 아무 file과도 매칭되지 않음 — 오류가 아니다. `empty_layers`에 기록하고 exit 0.
- 위반 존재 — 오류가 아니다. exit 0.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C01 | normal | layers a(`src/a/**`), b(`src/b/**`), allow {a: []}, edge a/x→b/y | allow 위반 1개, id·target·structure 명세대로 |
| C02 | normal | 같은 layer, forbid [{from: a, to: [b]}], edge a/x→b/y와 b/y→a/x | forbid 위반 1개(a→b), b→a는 위반 아님 |
| C03 | normal | allow {a: [c]}, forbid [{from: a, to: [b]}], edge a→b | allow·forbid 위반 2개 |
| C04 | edge | allow {a: []}, edge a/x→a/z, edge a/x→unassigned/u | 위반 0, unassigned_files에 u |
| C05 | edge | allow에 없는 layer b에서 a로 가는 edge, forbid 없음 | 위반 0 |
| C06 | edge | 위반 edge가 TESTS relation뿐, 또는 boundary node 끝점 | 위반 0 |
| C07 | normal | 위반 pair에 certain edge와 ambiguous edge가 섞임 | candidate 1개, tier certain, evidence_count 합, max_weight 최대 |
| C08 | normal | 위반 pair가 ambiguous edge뿐 | candidate 있음, tier all |
| C09 | boundary | `match_path` 표: `app/**`×{`app/a.py`✓, `app/x/y.py`✓, `app`✗, `apps/a.py`✗}, `app/*.py`×{`app/a.py`✓, `app/x/a.py`✗, `app/.py`✓}, `**/m.py`×{`m.py`✓, `a/b/m.py`✓, `am.py`✗}, `a/**/b`×{`a/b`✓, `a/x/y/b`✓}, `a?c`×{`abc`✓, `a/c`✗, `ac`✗}, `a.b[1]`×{`a.b[1]`✓, `axb1`✗}, `App/x`×`app/x`✗ | 표와 같음 |
| C10 | normal | package 패턴 `pkg:python:app.models.domain`과 `pkg:nestjs:Feed*`, framework 체계 shared file | 각 file이 package id로 layer에 매칭 |
| C11 | error | 두 layer에 매칭되는 file 12개 | `ArchitectureRulesError`, 메시지에 12와 정렬 앞 10개 경로·layer 이름 |
| C12 | error | loader 오류 표: file 없음, 비 UTF-8, YAML 구문 오류, top-level list, 미지 key, version 누락/0/2/"1"/true, layers 누락/빈 mapping/list, layer 이름 `1a`/`a b`/숫자, selector 빈 mapping/미지 key/빈 list/비문자열/빈 문자열, path `/abs`/`a**`/`**b`, allow 비 mapping/미정의 layer/자기 참조/비 list, forbid 비 list/항목 key 누락·추가/to 빈 list/미정의/자기 참조 | 각각 `ArchitectureRulesError` |
| C13 | error | top-level `external: {...}`, forbid 항목 `to_external: [...]` | `ArchitectureRulesError`, 메시지에 `external`과 `not supported` |
| C14 | normal | allow와 forbid 목록에 중복, 같은 from의 forbid 항목 2개 | 정상 load, 정렬·중복 제거·합집합 |
| C15 | normal | 예제 규칙 + fastapi-realworld CLI(`-l python --granularity file`) | allow 위반 from domain 존재(domain→services), forbid 위반 db→api 존재, coverage 명세대로, exit 0 |
| C16 | normal | 4개 fixture를 규칙 없이 CLI | bottleneck JSON이 base_commit 출력과 byte 단위로 같음 |
| C17 | error | CLI 잘못된 규칙 file, 다중 매칭 규칙 | stderr `[!] Error:`, exit 1, 출력 file 없음 |
| C18 | error | CLI `--architecture-rules` + `--granularity symbol` | exit 2, 출력 file 없음 |
| C19 | normal | fastapi-realworld 사본에 `app/models/domain`→`app/api` import 추가 | 규칙 적용 시 allow 위반이 원본보다 늘어남(새 pair 포함) |
| C20 | normal | 예제 규칙 HTML에서 위반 file 선택 | `경계 규칙 위반`, `domain → services · 허용 목록 밖` 형식 표시 |
| C21 | normal | 같은 입력 두 번, PYTHONHASHSEED 다르게 | byte 같음 |
| C22 | boundary | 합성 20,000 file, layer 10개(각 path 5 + package 5 패턴), file pair 100,000 | 규칙 평가 시간 ≤ 5.0 s. 규칙 평가 시간 = `layer_assignments` 단독 중앙값, 그리고 `analyze_structure`의 (rules 있음 − rules 없음) 중앙값 차이. 둘 다 상한 이하 |
| C23 | normal | v8 JSON with rule_violation을 `python -m report.bottlenecks.generate`로 렌더링 | 성공, label `경계 규칙 위반` |
| C24 | edge | 규칙 있음, file graph 비어 있음 | 위반 0, 모든 layer empty, 예외 없음 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 규칙 판정이 명세대로여야 한다 |
| Performance efficiency | yes | 사용자가 분량 폭증을 우려했다. 규칙 평가는 file 수 × 패턴 수에 비례한다 |
| Compatibility | yes | 규칙이 없을 때 기존 출력이 바뀌면 안 된다 |
| Interaction capability | yes | 오류 메시지와 HTML 이유가 사람이 읽고 고칠 수 있어야 한다 |
| Reliability | yes | 결정성(Phase 3 baseline 비교의 전제), 잘못된 입력에서 crash 없음 |
| Security | yes | 사용자 YAML을 읽는다(`yaml.safe_load` 필수). layer 이름이 HTML에 들어간다 |
| Maintainability | yes | 범용 analysis layer가 framework·언어별 analyzer를 import하면 안 된다 |
| Flexibility | yes | 사용자가 repo마다 규칙을 바꿔 쓰는 설정 표면이다 |
| Safety | no | 물리적 위해와 관련이 없는 정적 분석 도구다 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | Functional suitability / correctness | F01–F10 | 손 계산 기대값, 독립 위반 판정 oracle(support에 명세 문장으로 작성) | 선언 coverage item 100% 통과 | automated + mutation | 계획 |
| Q02 | Performance efficiency / resource use | fastapi-realworld 예제 규칙 | 규칙 적용 bottleneck JSON byte ÷ 규칙 없음 byte | ≤ 1.25 | automated(실측) + review R1 | 사용자 우려 |
| Q03 | Performance efficiency / time behaviour | C22 합성 입력, 규칙 평가 | 같은 process 3회 중앙값, 초(C22 정의: Phase 1 계산 시간은 제외) | ≤ 5.0 s | automated | 사용자 우려 |
| Q04 | Compatibility / coexistence | 규칙 없음 | C16 base_commit 비교 | byte 차이 0, 기존 pytest 실패 0 | automated | F11 |
| Q05 | Interaction capability / user error protection | 오류 메시지 | C11–C13, C17 | file 수준 오류(읽기 실패, 비 UTF-8, YAML 구문 오류)는 규칙 file 경로를 포함. top-level 형태 오류는 기대 형태(`mapping`)를 포함. 그 외 schema 오류는 원인 key 또는 값을 포함. 다중 매칭은 F05 내용 포함 | automated | 계획 |
| Q06 | Interaction capability / recognizability | HTML 위반 표시 | C20 browser 검사 | label과 이유 문자열 일치 | automated(Playwright) + review R2 | F14 |
| Q07 | Reliability / faultlessness | 결정성, 잘못된 입력 | C21, fuzz (a)(b) | byte 차이 0, ArchitectureRulesError 외 예외 0, glob differential 불일치 0 | automated + fuzz | F15 |
| Q08 | Security / integrity | YAML 로드, HTML 삽입 | `!!python/object` 태그 문서 load, layer 이름이 text로 삽입되는지 | 태그 문서는 ArchitectureRulesError이고 객체 생성 없음. 주입 script 실행 0 | automated | 기존 `tests/test_report_security.py` 정책 |
| Q09 | Maintainability / modularity | `analysis/architecture_rules.py` import | AST import 검사 | framework_analyzers·language_analyzers.<lang> import 0 | automated | 프로젝트 경계 |
| Q10 | Maintainability / testability | `analysis/architecture_rules.py` | coverage.py branch | ≥ 90% | automated(Test command) | 기본값 |
| Q11 | Flexibility / adaptability | 예제 profile | F07 문서가 load되고 C15 결과를 낸다 | load 성공, C15 통과 | automated | F07 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V01 | F01, F02, F03, F06, C12, C13, Q05, Q08 | `load_architecture_rules` 오류 | unit; tmp_path YAML file | syntax testing | C12 표의 각 행(행마다 1 item), external-top, to-external, python-object-tag | 100% | 각 입력이 ArchitectureRulesError, 메시지에 원인 key 또는 값 포함 | pytest |
| V02 | F01, F03, F06, C14, Q11 | `load_architecture_rules` 정상 | unit | equivalence partitioning | layer-name-hyphen-underscore-upper(`Core-Layer_2`); minimal-paths; minimal-packages; both-selectors; allow-empty-list; allow-dup; forbid-dup; forbid-merge-same-from; example-profile | 100% | 반환 객체 필드가 명세 정규화와 같음 | pytest |
| V03 | F04, C09 | `match_path` | unit | boundary value analysis (2-value) | C09 표의 각 (pattern, path) 쌍 | 100% | 표와 같은 bool | pytest |
| V04 | F05, C10, C11 | `layer_assignments` | unit | equivalence partitioning | path-only; package-language; package-framework-shared; path-or-package; unmatched; multi-match-error-12; multi-match-error-1 | 100% | 배정 dict, 오류 메시지의 수·앞 10개·layer 이름 | pytest |
| V05 | F08, F09, C01–C08 | 위반 판정과 candidate 형식 | unit; analyze_structure에 합성 FileArchitecture | decision table | rule: (A∈allow, B∉allow[A], B∉forbid[A]); (A∈allow, B∈allow[A], B∈forbid[A]); (A∈allow, B∉allow[A], B∈forbid[A]); (A∉allow, B∈forbid[A]); (A∉allow, B∉forbid[A]); same-layer; unassigned-end; tests-only; boundary-end; mixed-tier; ambiguous-only; candidate-fields | 100% | 위반 수·id·target·metrics·evidence·structure가 독립 oracle과 같음 | pytest |
| V06 | F10, C04, C24 | `coverage.architecture_rules` | unit | equivalence partitioning | counts-all-layers; zero-layer-listed; unassigned-list; empty-layers; violation-count; empty-graph | 100% | coverage dict가 명세와 같음 | pytest |
| V07 | F11, F15, Q04, Q07, C16, C21 | 규칙 없음 호환·결정성 | integration; 4개 fixture | scenario testing | no-rules-byte-equal ×4(bottleneck JSON), determinism-hashseed(규칙 적용) | 100% | base_commit 출력과 byte 같음, 두 실행 byte 같음 | pytest; main이 구현 전 base_commit 트리에서 만든 `tests/architecture_rules_evidence/base_manifest.json`(fixture별 file 모드 bottleneck JSON의 byte 크기·sha256)과 비교 |
| V08 | F07, F12, C15, C17, C18, C19 | CLI | integration(subprocess) | scenario testing | example-realworld; bad-rules-exit1-no-output; multi-match-exit1-no-output; symbol-exit2; reverse-import-copy | 100% | exit code, stderr 접두, 출력 file 유무, 위반 존재/증가 | pytest |
| V09 | F13, C23 | report validator | unit | equivalence partitioning | v8-with-rule-violation-ok; label; coverage-architecture-rules-accepted | 100% | 렌더링 성공과 label | pytest |
| V10 | F14, Q06, Q08, C20 | HTML | end-to-end(Playwright) | scenario testing | allow-reason; forbid-reason; layer-name-text-insert | 100% | DOM text, dialog 미발생 | pytest browser |
| V11 | Q02, Q03, C22 | 분량·시간 | integration(benchmark 아님, 기본 실행) | boundary value analysis (2-value) | size-ratio-realworld; synthetic-time | 100% | 각 상한 이하 | pytest |
| V12 | Q09 | import 경계 | unit | syntax testing | no-framework-import; no-lang-specific-import | 100% | AST import 목록 | pytest |
| V13 | Errors, C24 | 경계 사례 | unit | error guessing | 추정 결함: empty-graph-with-rules(규칙 있고 graph 비면 예외); rules-none-equals-phase1-result(rules=None이 Phase 1 결과를 바꿈); layer-pattern-matching-nothing(빈 layer를 오류로 냄); file-id-without-prefix-path(`file:` 없는 id를 버리거나 접두를 요구) | none — experience-based | 명세대로 | pytest |
| V14 | Q10 | branch coverage | 전체 Test command | branch testing (coverage.py) | analysis/architecture_rules.py branches | ≥ 90% | coverage report 통과 | Test command |
| V15 | Q07 | fuzz | main 실행 | random testing | loader-20000; match_path-20000 | 100% (예산 전부 실행) | crash 0, differential 불일치 0 | main fuzz harness, ledger 기록 |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| A01 | 한 file이 여러 layer에 매칭되면 오류(D1) | 엄격→완화는 기존 규칙 file을 깨지 않는다. NestJS 공유 file이 package 패턴 두 개에 걸리면 막힐 수 있다 | 계획 D1 — approved |
| A02 | 위반으로 exit code를 바꾸지 않음(D2) | Phase 3 `--fail-on-new violation` 담당 | 계획 D2 — approved |
| A03 | layer 선택자는 `paths`·`packages` | 사용자 선택 | user answer |
| A04 | allow는 layer별 허용 목록 | 사용자 선택 | user answer |
| A05 | `external`은 예약 후 오류 | 2b 분리 | user answer |
| A06 | 위반 판정은 `all` tier pair 기준이고 tier를 표시 | recall 우선. 불확실 위반을 tier로 구분 | brief v1 — approved |
| A07 | allow 목록/forbid.to의 자기 참조는 오류 | 같은 layer 의존은 항상 허용이라 의미 없는 항목. 엄격→완화 가능 | brief v1 — approved |
| A08 | path glob은 `*`, `**`, `?`만 지원. `[...]`, `{a,b}`는 리터럴 | 단순성. 나중에 추가해도 기존 패턴 의미가 바뀌는 문자는 `[`, `{` 뿐 | brief v1 — approved |
| A09 | `--granularity symbol` 조합은 exit 2(argparse) | 기존 `--entrypoint` 검사와 같음. 계획 검증 절의 "exit 1"을 대체 | brief v1 — approved |
| A10 | Q02 1.25배, Q03 5초, Q10 branch 90% | Phase 1과 같은 수준 | brief v1 — approved |
| A11 | schema `bottlenecks.v8` 유지 | v8은 배포 전 | 계획 — approved |
| A12 | candidate target은 from file만. HTML에서도 from file에만 표시 | to file에도 붙이면 양쪽 file에 중복 표시. Phase 3 패널에서 양쪽 강조 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F01, F02, F03, F06 | C12, C13, C14 | V01, V02 | pytest |
| F04 | C09 | V03, V15 | pytest, fuzz |
| F05 | C10, C11 | V04 | pytest |
| F07 | C15 | V02, V08 | pytest |
| F08, F09 | C01–C08 | V05 | pytest |
| F10 | C04, C24 | V06 | pytest |
| F11, F15 | C16, C21 | V07 | pytest + base manifest |
| F12 | C17, C18, C19 | V08 | pytest |
| F13 | C23 | V09 | pytest |
| F14 | C20 | V10 | Playwright, R2 |
| Q01–Q11 | C22 | V01–V15 | pytest, R1, R2, fuzz |
| Errors | C24 | V13 | pytest |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 2 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V01 | 4 | tests/test_architecture_rules.py V01 tests(batch 2: 경로·`mapping` 분리 assertion, forbid 비 list 6종); test_V08_bad_rules_exit1_no_output[syntax] stderr 경로; Test command run 2 rc 0, branch 100% | accepted (verifier 2) | F-01 수정. 재-mutation: M01 killed(forbid_not_a_list[empty-mapping]), 경로 누락 hand mutation H12 killed(non_utf8, yaml_syntax_error) | none |
| V02 | 4 | tests/test_architecture_rules.py::test_V02_layer_name_hyphen_underscore_upper 추가 | accepted (verifier 2) | A-3 반영 | none |
| V03–V14 | 3 | 위 테스트 파일들; Test command run 1 rc 0 (1798 passed, branch 100%); hand mutations H01–H11 killed | accepted (verifier 1, retained by verifier 2) | 증거가 표면·layer·독립 oracle·목표를 충족 | batch 2는 V01·V02 함수와 V08 assertion 1개만 변경, helper·구현 변경 없음 |
| V15 | 3 | scratchpad fuzz harness; loader 20,000 execs crash 0 (accepted 967), match_path 20,000 execs mismatch 0, seed 20261018 | accepted | main 실행, 예산 전부 소진 | spec v3 F04 |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 0 | implementer challenge: F04 "0개 이상"과 C09 `app/**`×`app`✗ 모순 | spec defect (verified) | v2: 마지막 `**`는 1개 이상 | amended, both roles aligned |
| 0 | test-implementer challenges: Q05 측정 기준, F10 id 형식, coverage 위치, C22 측정 맥락 | spec gap (verified) | v3 명확화 | amended; 구현·테스트 이미 같은 해석 |
| 1 | `test_V01_C12_non_utf8` 실패: 비 UTF-8 오류 메시지에 file 경로 없음 | implementation defect (verified) | correction batch 1: file 수준 오류 메시지에 경로 포함 | Test command rc 0 |
| 1 | fuzz harness 무한 순회(공유 list 객체가 자기 자신에 삽입) | main harness defect (verified) | 삽입 값 deepcopy | fuzz 완료, crash 0, mismatch 0 |
| 1 | R2: 같은 from file의 위반 2건이 같은 문구로 표시되어 구분 불가 | F14 형식에 도착 file이 없음 | advisory A-1 기록, 사용자 결정 대기 | advisory (non-blocking) |
| 3 | verifier 2: pass, blocking 0. advisory A-6(file_not_found는 basename만 확인), A-7(일부 needle이 BASE layer 이름) | test strengthening only | 적용 안 함 | advisory (non-blocking) |
| 2 | verifier 1 A-5: no-output 검사의 `report_assets`가 양성 대조 없이 검사됨 | 일반 실행에서 `_assets` 디렉터리가 생기지 않음(test-implementer 측정) | 적용 안 함 | advisory (non-blocking) |
| 2 | verifier 1 F-01: V01 Q05 assertion이 OR 조건이라 경로 누락·`mapping` 누락을 거부하지 못함 | test evidence gap (verified, 테스트 코드 확인) | correction batch 2: 분리 assertion | fixed; H12(경로 제거) killed; Test command rc 0 |
| 2 | mutation tool: 30 executed, 28 killed, 2 survived (6.7%). M12 equivalent(연속 `**` 비접기 — 같은 언어, main 재확인 동의). M01 declared(`forbid` 비 list 검사 제거: `{}`가 load되고 `5`/`null`은 TypeError) | V01 evidence gap (verified) | correction batch 2에 forbid 비 list 매개변수화 추가 | fixed; M01 재실행 killed |
| 2 | verifier 1 A-2/A-3: V13 추정 결함 미기재, layer 이름 허용 측 미검증 | spec/evidence omission | v4: V13 추정 결함 기재, V02 layer-name 항목 추가 | done |

# Version Log
## v1
- 초안. 계획 Phase 2a와 사용자 답변(선택자 paths+packages, allow ①, external 2b 분리), fastapi-realworld layer 간 의존 측정(domain→services certain 2, db→api 3)으로 예제 규칙 결정.
## v2
- F04: 마지막 segment `**`는 1개 이상, 그 외 `**`는 0개 이상, 연속 `**`는 하나로 봄. 근거: implementer challenge — v1 F04("0개 이상")와 C09(`app/**`×`app`✗)가 모순. C09와 gitignore 의미를 따름. brief 항목 변경 없음(계약 정밀화).
## v3
- Q05 측정 기준을 오류 종류별로 구체화(file 수준 오류는 경로 포함). 근거: test-implementer challenge — 비 UTF-8 오류 메시지에 key·값·file이 없음, 구문 오류에는 key가 없음.
- F10 `unassigned_files`는 file id(Phase 1 `structure.unassigned_files`와 같음), `coverage["architecture_rules"]` 위치, `file:` 접두 없는 id 처리를 Signatures에 명시. 근거: test-implementer intent gap 보고, 구현과 테스트가 이미 같은 해석.
- C22/Q03 측정 맥락: Phase 1 계산(합성 입력에서 3–4.5 s)을 제외한 규칙 평가 시간. 근거: test-implementer 측정.
## v4
- V02에 layer-name-hyphen-underscore-upper 항목 추가, V13 행에 추정 결함 명시. 근거: verifier 1 advisory A-2, A-3. contract-only 변경.
