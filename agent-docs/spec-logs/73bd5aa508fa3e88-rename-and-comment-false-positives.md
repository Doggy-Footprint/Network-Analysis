---
version: 7
run_id: 73bd5aa508fa3e88
status: complete
base_commit: 1bd6ebe3ff48cffb6ec28394c97278b6fafbff1e
max_verifier_invocations: 3
commit: 1bd6ebe3ff48cffb6ec28394c97278b6fafbff1e
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자(eval 소유자) | 파일 이름만 바꾼 변경에 분석기가 delta 경고를 내지 않는다 | 주입 eval 음성 대조 NC1(이름 변경)에서 분석기 오탐 15/16 → 2/16 이하 |
| I2 | 사용자 | Kotlin 주석만 바꾼 변경에 분석기가 delta 경고를 내지 않는다 | nowinandroid NC3(주석만 추가)에서 분석기 오탐 4/4 → 0/4, 다른 저장소 NC3 0 유지 |
| I3 | 사용자(상시 지시: AI agent 문제를 얼마나 잡는가가 기준) | 오탐을 줄이면서 주입된 문제를 찾는 능력은 잃지 않는다 | 재측정에서 저장소×방식 칸별 위치 기준 가중 recall 하락이 0.02 이하이거나, 넘는 칸은 건별 원인 보고 |
| I4 | 기존 delta 소비자(CLI 사용자, eval harness, agent handout) | 기존 baseline과 출력 소비 코드가 계속 동작한다 | git commit이 없는 기존 baseline도 읽히고, delta의 기존 필드 의미는 이름 변경이 없을 때 v2와 같다 |

# Scope
In scope: (1) file granularity bottleneck JSON의 `snapshot`에 분석 시점 git commit 기록. (2) `--baseline` delta 계산 시 baseline commit과 현재 작업 트리 사이의 이름 변경을 git으로 판정하고, baseline 쪽 id 중 바뀐 파일 경로를 담은 것을 새 경로로 바꾼 뒤 비교. (3) delta 출력의 `renames` 객체, `policy` `delta.v3`, CLI 경고·요약 줄. (4) Kotlin 분석기의 이름 텍스트 스캔(header TYPE_USES, 본문 READS/WRITES)에서 주석 텍스트 제외. (5) 주입 eval 재측정(baseline 재생성 + 전체 rescore).
Out of scope: 포맷 변경 오탐(ghostfolio NC2), import 경로가 길어져 생기는 `large_node` `token_count` 증가(flask-admin NC1-0/NC1-1), Kotlin 문자열 literal 안의 이름, Python·TypeScript 분석기, 새 탐지 유형, symbol granularity delta, `pkg:dir:`·`pkg:python:`·`pkg:kotlin:`·`pkg:gradle:` 처럼 파일 경로를 담지 않는 id의 재매핑(디렉터리를 옮긴 이동은 실제 package 구조 변화로 남는다), harness 코드 변경.

# Paths
Implementation: bottlenecks/delta.py, bottlenecks/renames.py, bottlenecks/core.py, bottlenecks/__init__.py, code_analyzer/cli.py, language_analyzers/kotlin/analyzer.py, language_analyzers/core/positions.py
Tests: tests/test_rename_delta.py, tests/test_kotlin_comment_scan.py, tests/rename_delta_support.py, tests/rename_comment_evidence/, 그리고 기존 tests/ file(조정 허용 범위: `"delta.v2"` 기대값을 `"delta.v3"`로; delta key 집합에 `renames` 추가; `snapshot` key 집합에 `git_commit`·`git_commit_reason` 추가; 기존 기준 구현 `tests/delta_support.py` `ref_delta`가 `renames` 인자 없이 호출될 때 `renames: {"status": "skipped", "reason": "not_requested", "pairs": []}`를 내도록 확장; bottleneck JSON이나 delta 전체를 hash·byte로 고정한 characterization은 비교 전에 위 새 key를 제거하고 `policy`를 이전 값으로 되돌린 뒤 비교하며 새 key는 같은 test에서 별도로 단언; `--baseline` CLI test의 stderr 기대값에 `[!] Warning: renames not detected (<reason>)` 한 줄, stdout 기대값에 `[Δ] Renames applied: N` 한 줄 허용; Kotlin 분석 결과를 고정한 기존 기대값에서 근거가 주석 안의 이름 출현뿐인 edge만 제거. 다른 assertion 약화 금지. 모든 변경은 `tests/rename_comment_evidence/existing-tests.diff`에 기록)
Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','fastapi-official-template','android-nowinandroid','typescript-nestjs-realworld')]" && uv run -q --with-requirements requirements-dev.txt --with pytest-cov python -m pytest -q -p no:cacheprovider --cov=bottlenecks.delta --cov=bottlenecks.renames --cov-branch --cov-report=term-missing --cov-fail-under=90 --deselect 'tests/test_analysis_coverage_reporting.py::test_V05_characterization_and_V04_cli_stages' --deselect 'tests/test_doc_references.py::test_V8_base_choice_cli_output_equals_base_after_removing_new_keys' --deselect 'tests/test_file_analysis_cli.py::test_V01_direct_builder_defaults_characterization' --deselect 'tests/test_nestjs_quality.py::TestRegression::test_O11_characterization_existing_standalone_outputs_are_byte_identical' --deselect 'tests/test_signal_defects_round4.py::test_V4_B_data_object' --deselect 'tests/test_report_modal.py::test_V04_graph_tab_active_modal_selects_and_centres_node' --deselect 'tests/test_report_size_format.py::test_V01_fixture_details_equal_base_details'
Review evidence: R1 — eval 재측정 절차(Traceability Q06 참조), 산출물 `~/toy-projects/network-analysis-eval/inject/<repo>/score-fp-fix.txt` 와 main이 작성하는 비교표. R2 — git 호출 점검: `bottlenecks/renames.py`의 모든 subprocess 호출이 인자 list이고 `shell=True`가 없으며 diff 계열 호출에 `--no-ext-diff --no-textconv`가 있음을 grep으로 확인.
Fuzzing: main이 scratchpad에 작성한 stdlib harness, seed 20261111. 대상 `compute_delta`. 생성: 합성 file granularity payload(파일 2~8개, 일반 후보 8종, 순환·package 순환, 위반, NestJS형 `pkg:nestjs:<path>#M` package id와 의존·metrics). oracle property — P1(metamorphic) payload `a`의 파일 무작위 부분집합을 새 경로로 바꿔 모든 경로 파생 id를 일관되게 치환한 `b`를 만들고 그 map을 `renames`로 주면 `compute_delta(b, a, renames)`의 7개 목록이 모두 비고 resolved 4개 값이 모두 0; P2 `renames` 없이 호출한 결과에서 `policy`·`renames`를 제외하면 base_commit의 `compute_delta` 결과와 같다(differential, base_commit 모듈을 별도 경로에서 import); P3 `renames` pairs가 비어 있으면 P2와 같은 결과. 5,000 입력, 예외 0.
Mutation tool: none — mutmut·cosmic-ray 미설치; hand mutation으로 대신한다.

# Signatures
bottlenecks.renames.repository_commit(project_root: Path, *, exclude: Sequence[Path] = ()) -> tuple[str | None, str | None]  # (40자 commit 또는 None, None 또는 reason "dirty" | "not_a_git_repository" | "git_unavailable" | "git_failed")
bottlenecks.renames.detect_renames(project_root: Path, baseline_commit: str | None, *, exclude: Sequence[Path] = ()) -> dict  # {"status": "applied" | "skipped", "reason": str | None, "pairs": [{"from": str, "to": str, "similarity": int}]}
bottlenecks.delta.compute_delta(current: Mapping, baseline: Mapping, renames: Mapping | None = None) -> dict  # renames는 detect_renames 결과; None이면 {"status": "skipped", "reason": "not_requested", "pairs": []}
bottleneck JSON snapshot (file granularity): {"file_count": int, "ignore_source": str, "git_commit": str | null, "git_commit_reason": null | "dirty" | "not_a_git_repository" | "git_unavailable" | "git_failed"}
delta JSON: 기존 key 전부 + "renames": {"status", "reason", "pairs"}; "policy": "delta.v3"
CLI: `--baseline` 사용 시 status가 skipped이고 reason이 not_requested가 아니면 stderr `[!] Warning: renames not detected (<reason>)`; pairs가 1개 이상이면 stdout `[Δ] Renames applied: N`

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F01 | file granularity 분석은 `snapshot.git_commit`에 project root의 HEAD commit(40자 hex)을 기록한다. 단 tracked file 수정·staged 변경·ignore되지 않은 untracked file이 하나라도 있으면(이번 실행의 출력: `-o` HTML, assets 디렉터리, `--bottlenecks` file, `<out>.json`, `<out>.details.json`, 그리고 `--baseline` file은 제외) `git_commit: null`, `git_commit_reason: "dirty"`. git 저장소가 아니면 `"not_a_git_repository"`, git 실행 file이 없으면 `"git_unavailable"`, 그 밖의 git 실패는 `"git_failed"`. 기록되면 `git_commit_reason: null`. | must | I1, A02 |
| F02 | `--baseline`이 주어지고 baseline의 `snapshot.git_commit`이 문자열이면, 그 commit의 tree와 현재 작업 트리(tracked 수정, staged 변경, ignore되지 않은 untracked file 포함) 사이의 이름 변경을 git 자체의 rename 판정(기본 유사도 50% 이상, git이 정하는 일대일 대응)으로 구해 `pairs`(`from` 오름차순, `similarity`는 git이 보고하는 정수 %)로 낸다. 결과 status `applied`(pairs가 비어도 applied). | must | I1, 사용자 선택 1-A |
| F03 | 이름 변경 판정은 저장소의 index, object database, refs, 작업 트리, config를 바꾸지 않는다. | must | A04 |
| F04 | 판정할 수 없으면 status `skipped`와 reason을 내고 delta는 매핑 없이 계산한다: baseline에 `git_commit` key가 없거나 null → `baseline_without_commit`; project root가 git 저장소가 아님 → `not_a_git_repository`; git 실행 file 없음 → `git_unavailable`; commit이 저장소에 없음 → `commit_not_found`; 그 밖의 git 실패 → `git_failed`. 어떤 경우에도 예외로 끝나지 않고 CLI 종료 코드는 판정 실패 때문에 바뀌지 않는다. | must | I4 |
| F05 | 비교 전에 baseline 쪽의 모든 id 문자열에서, 이름이 바뀐 파일 경로 `old`가 "문자열 시작 또는 `:` 바로 뒤"에서 시작해 "문자열 끝 또는 `#` 바로 앞"에서 끝나는 위치에 있으면 `new`로 바꾼다. 적용 대상: `dependency_network.file_ids`, 후보 `target`, 일반 후보(순환·위반 외) `structure` 안의 문자열 값(`unstable_dependency`의 `from_package`·`to_package` 등), 순환 `structure.members`, evidence의 `from_id`·`to_id`·`node_id`, package 순환 evidence row의 package id, `package_dependencies`의 `from_id`·`to_id`, `package_metrics`의 key, 위반 후보의 `target`·evidence. 또 `old`와 `new`가 모두 `.py`로 끝나는 쌍은 Python module 이름 m(path) = `.py`를 떼고 끝의 `/__init__`을 떼고 `/`를 `.`로 바꾼 것으로 정의하고, 같은 위치들의 id 중 `py:`로 시작하고 그 바로 뒤에 m(old)가 오고 그 뒤가 문자열 끝 또는 `#`인 것을 m(new)로 바꾼다(예: `py:CTFd.admin.users#users_listing` → `py:CTFd.admin.users_impl#users_listing`). 그 밖의 id(`pkg:dir:`, `pkg:python:`, `pkg:kotlin:`, `pkg:gradle:` 등 경로가 위 형태로 들어 있지 않은 것)는 그대로 둔다. | must | I1, A11 |
| F06 | 매핑 후 비교 규칙은 delta.v2와 같다. 단 규칙 위반은 candidate id 대신 (`rule_type`, `from_layer`, `to_layer` 또는 `to_external`, `target`, 첫 evidence의 `to_id`) 동일성으로 대응시킨다. 셈 단위는 v2처럼 위반 candidate(서로 다른 id)다: `new_violations`는 내용 key가 baseline에 없는 현재 위반 candidate마다 한 항목, `resolved.violations`는 내용 key가 현재에 없는 baseline 위반 candidate 수. 이름 변경이 없으면 결과의 기존 key들은 delta.v2 결과와 같다. | must | I1, I4 |
| F07 | delta 출력에 `renames` 객체(F02/F04 형태)를 추가하고 `policy`를 `"delta.v3"`로 한다. `counts`의 key 집합은 그대로다. | must | I4 |
| F08 | CLI는 F04 skipped(reason ≠ `not_requested`) 때 stderr에 `[!] Warning: renames not detected (<reason>)` 한 줄, pairs가 1개 이상이면 stdout에 `[Δ] Renames applied: N` 한 줄을 출력한다. 기존 `[Δ] Delta vs baseline: …` 줄은 그대로다. | should | I4 |
| F09 | Kotlin 분석기의 이름 텍스트 스캔(declaration header의 TYPE_USES 후보, 본문의 READS/WRITES 후보)은 주석 안의 텍스트를 보지 않는다: `//` 줄 주석, `/* */` block 주석, `/** */` KDoc(링크 `[Name]` 포함), tree-sitter-kotlin이 주석으로 파싱하는 중첩 block 주석. 주석 밖 code token의 매칭, edge의 relation·resolution·line 번호는 바뀌지 않는다. 문자열 literal 안의 텍스트는 지금처럼 스캔한다. | must | I2, 사용자 선택 2 |
| F10 | 위 변경 뒤 주입 eval을 재측정한다: 네 저장소 baseline을 새 분석기로 재생성하고(`harness.py baseline <repo>`) 전체 결과를 `harness.py rescore <repo>`로 다시 계산해 NC1~NC4 분석기 오탐과 저장소×방식 칸별 가중 recall(내용/위치)을 본 실험 값과 비교한다. | must | I1, I2, I3 |

# Errors
- baseline에 `git_commit` 없음/null — `renames.status = "skipped"`, `reason = "baseline_without_commit"`, stderr 경고 한 줄 — delta는 v2 규칙으로 계산, 출력 file 정상 기록, 종료 코드는 기존 규칙(`--fail-on-new` 판정)대로.
- project root가 git 저장소 아님 — snapshot `git_commit: null`, `git_commit_reason: "not_a_git_repository"`; delta 시 `reason = "not_a_git_repository"` — 위와 같은 사후 상태.
- PATH에 git 없음 — `git_commit_reason: "git_unavailable"` / `reason = "git_unavailable"` — 같은 사후 상태.
- baseline commit이 저장소에 없음(다른 저장소, shallow clone에서 누락) — `reason = "commit_not_found"` — 같은 사후 상태.
- 그 밖의 git 비정상 종료 — `reason = "git_failed"` — 같은 사후 상태, 저장소 변경 없음.
- baseline 생성 시 작업 트리가 dirty — `git_commit: null`, `git_commit_reason: "dirty"` (예외 아님, 비-exception failure) — bottleneck JSON 정상 기록; 이후 그 baseline으로 delta 시 `baseline_without_commit`.
- baseline의 `snapshot.git_commit`이 문자열·null이 아닌 값 — `load_baseline`이 `BaselineError`(`$.snapshot.git_commit must be a string or null`) — 기존 baseline 오류와 같이 종료 코드 1, 출력 없음.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C01 | normal | 임시 git 저장소(Python 3~4 file, 순환 1개, 후보 여러 개). baseline 분석 → `git mv a.py a_impl.py` + import 한 줄 갱신 → 현재 분석 `--baseline` | `renames.status = applied`, pairs `[{"from": "a.py", "to": "a_impl.py", "similarity": 100}]`; `new_cycles`·`grown_cycles`·`new_candidates`·`strengthened_candidates`·`new_package_dependencies`·`new_violations` 비어 있음 |
| C02 | normal | C01에서 이름 변경과 함께 그 file에 새 import를 추가해 새 package 의존이 생김(git 유사도 ≥ 50%) | pairs에 그 쌍; 새 import로 생긴 의존·후보만 delta에 나옴, 이름 변경 자체로 생기는 항목 없음 |
| C03 | boundary | 삭제된 file과 새 file의 git 유사도가 정확히 50% / 49% (테스트가 `git diff -M --name-status`로 값을 확인) | 50%: pair 있음; 49%: pair 없음, delta는 v2 규칙대로 새 후보 보고 |
| C04 | edge | `git mv` 대신 일반 `mv`로 바꿔 새 file이 untracked | C01과 같은 결과 |
| C05 | edge | NestJS형 합성 payload: `pkg:nestjs:src/events/events.module.ts#EventsModule`이 담긴 package 의존·metrics·후보, renames `events.module.ts → events-impl.module.ts` | `new_package_dependencies`·`new_candidates`·`instability_changes` 비어 있음 |
| C06 | error | baseline에 `git_commit` 없음(기존 v9 baseline) | `reason = baseline_without_commit`; 기존 key들은 base_commit의 delta.v2 결과와 같음; stderr 경고 한 줄 |
| C07 | error | git 저장소가 아닌 디렉터리 분석 | snapshot `git_commit: null`, `git_commit_reason: not_a_git_repository` |
| C08 | error | baseline `git_commit`이 다른 저장소의 commit | `reason = commit_not_found` |
| C09 | error | PATH에서 git 제거 | snapshot reason `git_unavailable`; delta reason `git_unavailable`; 예외 없음 |
| C10 | boundary | baseline 생성 시 tracked file 1개 수정 / untracked file 1개 / 출력 file만 project 안에 씀(`--output` 경로가 project 안) | 앞의 둘: `git_commit: null`, reason `dirty`; 출력 file만 있을 때: commit 기록 |
| C11 | normal | C01·C04 판정 전후 저장소 상태 | `git status --porcelain=v2 --untracked-files=all` 출력, `.git/index` byte, `git count-objects -v`, `git for-each-ref` 출력, `.git/config` byte가 전후 같음 |
| C12 | edge | file을 다른 디렉터리로 옮김(`pkg:dir:`/`pkg:python:` package가 바뀜) | file id 파생 항목은 매핑되어 새 후보 없음; package id가 바뀐 package 의존은 delta에 남음 |
| C13 | edge | 삭제 file과 무관한 새 file(유사도 낮음) | pair 없음 |
| C14 | normal | Kotlin file 쌍: 같은 code에 줄 주석·block 주석·KDoc(`[ProjectSymbol]` 링크, 프로젝트 symbol 이름과 같은 단어 포함)을 추가한 것과 안 한 것 | 두 분석의 Kotlin edge 집합 (from, to, relation, resolution)이 같음 |
| C15 | normal | 주석 밖 code에 있는 이름 참조(READS, WRITES, header의 type 사용) | 해당 edge가 있고 relation·line 번호가 주석 처리 전과 같음 |
| C16 | edge | 문자열 literal `"// not a comment value"` 뒤의 code, 문자열 안의 프로젝트 symbol 이름 | 문자열 뒤 code의 참조 edge 유지; 문자열 안 이름의 edge도 유지(현행) |
| C17 | edge | 중첩 block 주석 `/* a /* value */ b */`, 줄 끝 주석 `foo() // value`, header 안 주석 `class A /* B */ : C` | 주석 안 이름으로 edge 없음; `foo` 호출과 `C` 상속 edge 유지 |
| C18 | normal | integration: 임시 저장소에서 실제 CLI로 baseline → `git mv` → `--baseline … --fail-on-new any` | 종료 코드 0, `[Δ] Renames applied: 1` stdout, delta counts 전부 0 |
| C19 | error | baseline `snapshot.git_commit`이 정수 | `BaselineError` 메시지에 `$.snapshot.git_commit`, CLI 종료 코드 1 |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 오탐 제거와 기존 탐지 유지가 목표 |
| Performance efficiency | yes | delta 실행마다 git 판정이 추가되고 Kotlin 스캔이 바뀜 |
| Compatibility | yes | 기존 baseline·delta 소비자·기존 test |
| Interaction capability | no | 출력은 경고·요약 각 한 줄로 F08이 다룸 |
| Reliability | yes | git 실패가 분석을 깨면 안 됨 |
| Security | yes | 분석 대상 저장소에서 git subprocess 실행 |
| Maintainability | yes | 새 module·delta 분기 coverage |
| Flexibility | no | 새 언어·scheme 확장 요구 없음 |
| Safety | no | 물리적·인명 위험 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | Performance efficiency / time behaviour | `detect_renames`, eval의 ghostfolio clone(`~/toy-projects/network-analysis-eval/inject/ghostfolio/clone`)에서 file 1개 이름 변경 | `time.perf_counter` 3회 중 최솟값, 초 | ≤ 10 s | review(main 측정, R1 기록에 포함) | 기본값 A07 |
| Q02 | Performance efficiency / time behaviour | android-nowinandroid fixture Kotlin 분석 | base_commit 대비 분석 시간 비, 3회 최솟값 | ≤ 1.10 | review(main 측정) | 기본값 A07 |
| Q03 | Compatibility / co-existence | 기존 tests 전체 | 허용 범위 조정 후 통과 | 전부 통과 | automated(Test command), existing-tests.diff | I4 |
| Q04 | Reliability / fault tolerance | C06~C09, fuzz | 예외 수 | 0 | automated, fuzz | F04 |
| Q05 | Security / integrity | 판정 전후 저장소 상태(C11), git 호출 형태(R2) | 상태 차이 수, 위반 호출 수 | 0, 0 | automated(C11), review(R2) | F03, A05 |
| Q06 | Functional suitability / functional correctness | 주입 eval 재측정(F10) | NC1 분석기 오탐 수/유효 수; nowinandroid NC3 오탐 수; NC2·NC4 오탐 수; 칸별 위치 기준 가중 recall 차 | NC1 ≤ 2/16; nowinandroid NC3 = 0; NC2·NC4 본 실험 값 이하; recall 하락 ≤ 0.02 또는 건별 원인 보고 | review(R1) | I1, I2, I3 |
| Q07 | Maintainability / testability | `bottlenecks/delta.py`, `bottlenecks/renames.py` | coverage.py branch | ≥ 90% | automated(Test command) | 기본값 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V01 | F01, C07, C09, C10 | `repository_commit` 결과와 CLI가 쓴 bottleneck JSON `snapshot` | unit + integration(CLI subprocess), 임시 git 저장소 | equivalence partitioning | EP1 clean repo, EP2 tracked 수정, EP3 staged 변경, EP4 untracked file, EP5 출력 file만 project 안, EP6 git 저장소 아님, EP7 git 없음 | 100% | 각 분할의 `git_commit`·`git_commit_reason`이 F01과 일치 | Test command |
| V02 | F02, C01, C02, C04, C13 | `detect_renames` 결과 pairs | unit, 임시 git 저장소 | scenario testing | S1 `git mv` 순수 변경, S2 변경+편집, S3 untracked 새 file, S4 무관한 삭제+추가, S5 이름 변경 2쌍(`from` 정렬 확인), S6 baseline commit ≠ HEAD(baseline 뒤 이름 변경을 commit한 clean tree, 그리고 그 위에 commit하지 않은 이름 변경 하나 더) | 100% | pairs가 같은 상태에서 `git diff -M --name-status`(임시 index로 untracked 포함)가 보고하는 R 쌍과 같음 | Test command |
| V03 | F02, C03 | 유사도 경계 | unit | boundary value analysis (2-value) | B1 50%, B2 49% | 100% | 50%는 pair, 49%는 pair 없음; 유사도 값은 테스트가 git으로 확인 | Test command |
| V04 | F03, C11 | 저장소 상태 | unit | equivalence partitioning | EP1 clean + `git mv`, EP2 untracked 새 file, EP3 commit_not_found 경로 | 100% | C11의 다섯 관찰값이 전후 같음 | Test command |
| V05 | F04, C06, C08, C09 | `detect_renames`·`compute_delta`의 skipped 결과 | unit | equivalence partitioning | EP1 key 없음, EP2 null, EP3 git 저장소 아님, EP4 git 없음, EP5 commit 없음, EP6 git 비정상 종료(문법이 깨진 `.git/config`), EP7 hex가 아닌 commit 문자열(`HEAD`, `--output=x`) → `commit_not_found`이고 project 안에 새 file 없음 | 100% | status `skipped`, reason이 F04 표와 일치, 예외 없음 | Test command |
| V06 | F05, F06, C01, C05, C12 | `compute_delta` 결과 7개 목록·resolved | unit, 합성 payload | classification tree | 분류 A(id 형태): A1 `file:<p>`, A2 `<scheme>:<p>#<rest>`, A3 경로가 다른 위치에 부분 문자열로만 있음(`file:x/<p>`처럼 경계 불일치), A4 경로 비파생 package id, A5 `py:<m(old)>#<qualname>`과 `py:<m(old)>`(`__init__.py` → package module 포함), A6 `py:` 경계 불일치(`py:<m(old)>_x#…`, `py:<m(old)>.sub#…`, `py:` 아닌 접두사 `pyx:<m(old)>#…`); 분류 B(위치): B1 후보 target, B2 순환 members, B3 evidence from/to/node_id, B4 package 의존, B5 package_metrics key, B6 위반 target·evidence, B7 file_ids, B8 일반 후보 structure 문자열(`unstable_dependency` `to_package`), B9 package 순환 members·evidence row의 `pkg:nestjs:<p>#M` | A 6 class·B 9 class 각 1회 이상(each choice), 15 items 100% | A1·A2·A5는 매핑되어 해당 위치에서 새 항목 없음; A3·A4·A6은 매핑되지 않음 | Test command |
| V07 | F06, F07, C06 | 이름 변경 없음 / pairs 빈 applied | unit | metamorphic testing | M1 renames=None, M2 applied+빈 pairs, M3 skipped 각 reason | 100% | 기존 key가 기준 구현(`ref_delta` v2 규칙) 결과와 같고 `policy = delta.v3`, `renames` 형태가 F07과 같음 | Test command |
| V08 | F06 | 위반 대응 | unit | decision table | D1 다섯 필드 모두 같음(이름 변경으로 같아짐 포함) → 새 위반 아님, D2 `target`만 다름, D3 `to_id`만 다름, D4 `to_external` 위반 동일, D5 `rule_type`만 다름, D6 `from_layer`만 다름, D7 `to_layer`만 다름, D8 `to_external`만 다름(같은 target, `requests` vs `boto3`) | 100% | D1 새 위반 0, D2·D3 새 위반 1, D4 0, D5~D8 각 새 위반 1 | Test command |
| V09 | F08, C18 | CLI stdout/stderr, 종료 코드 | integration(subprocess) | equivalence partitioning | EP1 applied pairs ≥ 1, EP2 applied pairs 0, EP3 skipped(baseline_without_commit), EP4 `--baseline` 없음 | 100% | EP1 `[Δ] Renames applied: N` 한 줄; EP2 둘 다 없음; EP3 stderr 경고 한 줄, 종료 코드 기존 규칙; EP4 둘 다 없음 | Test command |
| V10 | C19 | `load_baseline` | unit | equivalence partitioning | EP1 문자열, EP2 null, EP3 key 없음, EP4 정수, EP5 list | 100% | EP1~3 통과, EP4·5 `BaselineError`에 `$.snapshot.git_commit` | Test command |
| V11 | F09, C14, C15 | Kotlin edge 집합 | unit(KotlinAnalyzer를 임시 project에 실행) | equivalence partitioning | EP1 줄 주석, EP2 block 주석, EP3 KDoc 문장 단어, EP4 KDoc 링크 `[Name]`, EP5 주석 밖 READS, EP6 주석 밖 WRITES, EP7 header type 사용 | 100% | EP1~4 주석 추가 전후 edge 집합 같음; EP5~7 edge 존재, relation·line이 base_commit 분석과 같음 | Test command |
| V12 | F09, C16, C17 | Kotlin 주석 경계 | unit | error guessing | G1 문자열 안 `//`, G2 문자열 안 `/*`, G3 중첩 block 주석, G4 줄 끝 주석, G5 header 안 block 주석, G6 file 첫 줄·마지막 줄 주석(EOF 개행 없음), G7 multi-byte 문자가 주석 안에 있어 뒤 offset이 밀리는 경우 | none — experience-based | 주석 안 이름의 edge 없음, 주석 밖 참조 edge와 line 유지 | Test command |
| V13 | Q04 | `compute_delta` | fuzz | random testing + metamorphic | Fuzzing 줄의 P1~P3 | 5,000 입력 전부 실행 | 위반 0, 예외 0 | main이 harness 실행 |
| V14 | Q01, Q02, Q05, Q06 | 재측정, 성능, git 호출 형태 | review | none — review procedure | R1, R2, Q01·Q02 측정 | 전부 수행 | Q01·Q02·Q05·Q06 기준 충족 또는 미충족 사유 기록 | Review evidence R1·R2 |
| V15 | Q03, Q07 | 기존 suite, coverage | automated | statement·branch(coverage.py) | `bottlenecks/delta.py`, `bottlenecks/renames.py` branch | ≥ 90% | Test command 통과 | Test command |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| A01 | 이름 변경 판정은 git으로, baseline JSON에 commit 기록 | 사용자 선택 1-A | user answer |
| A02 | baseline 생성 시 작업 트리가 dirty면 commit을 기록하지 않음(`dirty`) | dirty tree의 HEAD는 baseline 내용과 다르므로 잘못된 매핑을 피함. eval의 baseline clone과 CI의 main checkout은 clean. 불확실: 로컬에서 수정 중 baseline을 만드는 사용자는 이름 변경 판정을 못 받음 | user answer (brief v1 Ask: 추천안 수용) |
| A03 | Kotlin 주석 전체를 이름 스캔에서 제외(KDoc 링크 포함) | 사용자 선택 2 | user answer |
| A04 | untracked file 포함 판정은 저장소를 바꾸지 않는 방식으로(임시 index·임시 object 디렉터리) 구현 | git의 rename 판정은 index에 올라간 file만 보므로 untracked 처리가 필요; 사용자 저장소 무변경이 안전 | brief v1 — approved |
| A05 | git 호출은 인자 list, `--no-ext-diff --no-textconv` | 분석 대상 저장소 설정의 외부 diff·textconv 실행 방지 | brief v1 — approved |
| A06 | 경로를 담지 않는 package id는 매핑하지 않음 | 디렉터리 이동은 package 구조를 실제로 바꿈; eval NC1은 같은 디렉터리 안 이름 변경 | brief v1 — approved |
| A07 | Q01 ≤ 10 s, Q02 ≤ 1.10배, coverage ≥ 90% | 이전 delta spec의 기준 수준; 측정 근거 없음 | brief v1 — approved |
| A08 | 재측정은 전체 608건 rescore, 내용 판정 비용 ≤ $5 예상 | 본 실험 match 실측 건당 $0.0104 × 214건; 누적 $42.66, 상한 $100 | brief v1 — approved |
| A09 | 위반 대응을 내용 기준으로 바꿈 | 위반 id는 경로를 포함한 식별자의 hash라 이름 변경 시 달라짐(`bottlenecks/core.py` `_candidate`) | brief v1 — approved |
| A11 | 이름이 바뀐 `.py` file의 Python symbol id(`py:<module>#…`)도 새 module 이름으로 매핑 | controls pilot(r1_reanalyze `--only-negative`) 뒤 NC1 FP 4/16 중 4건이 `unresolved_boundary` evidence `node_id` `py:<module>#…` 차이; 실제 baseline의 `py:` id 129개 모두 module = root 기준 경로 점 표기. 불확실: src layout처럼 module이 경로와 다르면 매핑 안 됨(누락, 오매핑 아님) | user answer (re-brief v7: 매핑 추가) |
| A12 | verifier 상한 2 → 3 (v7 변경분 V06·V11·V12·V13만 재검토) | verifier 2 pass 뒤 v7 구현 변경으로 4개 obligation acceptance invalidated | user answer (2026-11-11) |
| A13 | R1 전체 재측정 시작 시점 | 사용자가 '지금 시작'을 고른 뒤 다른 작업이 끝나면 알려주겠다고 보류 | user answer (대기) |
| A10 | 역할 model: implementer·test-implementer·test-verifier 모두 저장소 기본(sonnet) | 변경이 두 module에 국한 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F01 | C07, C09, C10 | V01 | Test command |
| F02 | C01, C02, C03, C04, C13 | V02, V03 | Test command |
| F03 | C11 | V04 | Test command |
| F04 | C06, C08, C09 | V05 | Test command |
| F05 | C01, C05, C12 | V06 | Test command |
| F06 | C01, C06 | V06, V07, V08 | Test command |
| F07 | C06 | V07 | Test command |
| F08 | C18 | V09 | Test command |
| F09 | C14, C15, C16, C17 | V11, V12 | Test command |
| F10 | — | V14 | R1: (1) `harness.py baseline <repo>` 4개, 각 `base/bottlenecks.json`의 `snapshot.git_commit`이 manifest commit과 같음 확인; (2) 기존 결과 `score.txt`를 `score-full.txt`로, 각 run의 `result.json`·`delta.json`과 `base/bottlenecks.json`을 `inject/<repo>/backup-full/`로 보존; (3) `python3 tests/rename_comment_evidence/r1_reanalyze.py <repo> --match --workers 4`(먼저 `--only-negative` pilot을 낮에, 전체는 사용자 상시 지시대로 밤에); (4) `harness.py score <repo>` → `score-fp-fix.txt`; (5) main이 NC1~NC4 오탐과 칸별 recall을 본 실험 값과 표로 비교 |
| C19 | C19 | V10 | Test command |
| Q01–Q07 | — | V13, V14, V15 | Fuzzing, R1, R2, Test command |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 4 |
| verifier invocations | 3 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V01 | 4 | tests/test_rename_delta.py V01_* (EP1–EP7, CLI C10) | accepted (verifier 1 v4, retained by verifier 2 v6) | M5 killed by V01_EP5 | rename_delta_support.py |
| V02 | 6 | test_rename_delta.py V02_S1–S5, oracle `git diff --cached -M` on repo copy | accepted (verifier 2, v6) | M7 killed by V02_S3; M12 (diff HEAD) killed by V02_S6 | rename_delta_support.py |
| V03 | 4 | V03_B1, V03_B2 | accepted (verifier 1 v4, retained by verifier 2 v6) | M11 killed by V03_B2; correction batch 2 fixed intermittent B2 failure (20/20 pass after) | none |
| V04 | 4 | V04_EP1–EP3 (five observations) | accepted (verifier 1 v4, retained by verifier 2 v6) | M6 killed by V04_EP1/EP2 | rename_delta_support.py |
| V05 | 6 | V05_EP1–EP6 (EP6 broken .git/config) | accepted (verifier 2, v6) | M15 (commit unvalidated) killed by EP7 | v3 EP6 example |
| V06 | 7 | V06_A1–A6 × B1–B9, C05 | accepted (verifier 3, v7) | M1 killed by V06_A3; M3 killed by V06_A2_B8; M13 (package cycle unmapped) killed by B9 | delta_support.ref_delta (renames extension) |
| V07 | 4 | V07_M1–M3 | accepted (verifier 1 v4, retained by verifier 2 v6) | none | ref_delta |
| V08 | 6 | V08_D1–D4 | accepted (verifier 2, v6) | M4 killed by V08_D1; M14 (key subset) killed by D5–D8 | ref_delta; v4 F06 counting unit (also existing test_delta_integration Q03) |
| V09 | 4 | V09_EP1(C18)–EP4 | accepted (verifier 1 v4, retained by verifier 2 v6) | M10 killed by V09_EP3 | none |
| V10 | 4 | V10_EP1–EP5, C19 | accepted (verifier 1 v4, retained by verifier 2 v6) | none | none |
| V11 | 7 | test_kotlin_comment_scan.py V11_* | accepted (verifier 3, v7) | M19, M20 killed | none |
| V12 | 7 | V12_G1–G7 (G1·G2·G3·G6·G7 rewritten in batch 1 to class members) | accepted (verifier 3, v7) | M8 killed by G7; M9 killed by G5; on batch-4 code M8b killed by G7, M9b killed by G5 | none |
| V13 | 7 | tests/rename_comment_evidence/fuzz/ result.json (v7 harness with `py:` ids, `a/` dir): 5000 inputs, 11591 pairs, P1·P2·P3 0, exceptions 0 | accepted (verifier 3, v7) | n/a | base_delta = 1bd6ebe bottlenecks/delta.py |
| V14 | 7 | R2 grep (1 subprocess.run, list args, no shell=True, diff --no-ext-diff --no-textconv); Q01 0.22 s ghostfolio copy, index unchanged; Q02 main 1.000/1.039/1.031 (`q02_result.txt`); R1 `tests/rename_comment_evidence/r1_comparison.md` | accepted (main review; verifier 3 reviewed the R1 procedure) | Q06: NC1 2/16, nowinandroid NC3 0, NC2 1→1, NC4 0→0; nowinandroid sonnet located -0.051 with 3 per-task causes (comment-derived signals) | none |
| V15 | 4 | Test command: 3916 passed (v6); delta.py 99%, renames.py 94% branch | accepted (verifier 1, v4); re-run green on v6 | n/a | existing-tests.diff incl. regenerated android golden (android_golden/README.md) |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 1 | Test command: 15 failed / 3889 passed; coverage delta 99%, renames 92% | (a) V12 G1·G2·G3·G6·G7은 top-level `var total` 참조를 기대하나 base_commit 분석기도 top-level property node를 만들지 않음(같은 test를 base worktree에서 실행해 실패 확인) — test defect. (b) android-nowinandroid 고정 기대값(golden, Q04 bytes)이 주석 안 이름 edge를 포함 — 허용된 기존 기대값 조정. (c) `test_V12_Q03` resolved.violations 1 ≠ 1000: 내용이 같은 baseline 위반 1000개를 key 하나로 셈 — implementation defect(v4 F06 셈 단위) | (b) main이 재생성: 새 KotlinAnalyzer(원본) edge 2513 = base 1bd6ebe(주석 공백화 사본) edge 2513, 대칭차 0; golden은 a8a3012 worktree에 새 analyzer.py만 적용해 생성(기존 golden 재현 byte 일치 확인 후), Q04 bytes는 주석 효과 90675 byte 차감 → `tests/rename_comment_evidence/android_golden/` | (b) 해당 9개 test 통과; (a)(c) correction batch 1로 test-implementer·implementer에 전달 |
| 2 | Test command: 1 failed / 3903 passed; `test_V03_B2_similarity_49_is_not_a_pair`가 git 판정 R049인데 detect가 similarity 100 쌍을 냄, `-n 0` 12회 반복 중 4회 실패 | 임시 index를 `shutil.copyfile`로 복사해 index file mtime이 새로워져 git racy-clean 검사가 꺼짐: 같은 초·같은 크기로 다시 쓴 file을 stat상 변경 없음으로 보고 옛 blob 유지 — implementation defect | correction batch 2: index 복사 시 timestamp 보존 | 20/20 V03 통과, Test command 3904 passed |
| 3 | verifier 1 retry: VF1-1 V02 baseline commit = HEAD뿐이라 HEAD 대비 diff 결함을 못 거름; VF1-2 V06에 package 순환 nestjs id class 없음; VF1-3 V08이 rule_type·layer·to_external 차이를 안 봄 | evidence gap / spec 누락 | v6: V02 S6, V06 B9, V08 D5–D8, V05 EP7(advisory O7) 추가; test_delta_cli C15 비교에 `renames` 전달(O1) | B9 rows 변형이 file_ids 없는 v8 payload에 v9 row를 넣어 TypeError(base도 같음) → test defect 수정; Test command 3916 passed; M12–M15 전부 의도한 test에 잡힘 |
| 4 | verifier 2 pass: V01–V13·V15 accepted, finding 0; V14 pending(Q02·Q06 미측정) | — | V14는 main 측정(R1 pilot 낮, 전체 밤)으로 닫음 | controls pilot: NC1 15→4/16, NC3 nowinandroid 4→0, NC2 1→1, NC4 0→0 |
| 5 | Q02 main 측정 1.104/1.122/1.147 > 1.10 | 주석 공백화 사본으로 두 번째 NamePositions를 만드는 비용 | correction batch 4: 주석 구간 bisect로 occurrence 필터, 두 번째 index 제거; edge 3156 동일(implementer), base 주석 공백화 사본과 2513 edge 동일(main) | Q02 1.000/1.039/1.031 (`tests/rename_comment_evidence/q02_result.txt`) |
| 6 | NC1 4/16 중 4건이 `py:<module>#…` evidence 차이 | F05가 Python symbol id를 다루지 않음(spec gap) | v7 re-brief 승인, A5·A6 test, fuzz에 `py:` node id 생성 추가 | Test command 3923 passed; fuzz 5000 입력·11591 쌍·위반 0; M16–M18 의도한 test에 잡힘 |
| 7 | v7 controls pilot(`r1_reanalyze.py --only-negative`, 64 controls) | — | — | NC1 분석기 FP 2/16(flask-admin NC1-0·NC1-1 `large_node` token_count, 범위 밖), nowinandroid NC3 0/4, NC2 1/16(ghostfolio NC2-0 `large_node`, 본 실험과 같음), NC4 0/14; Kotlin 새 구현에 M8b·M9b·M19·M20 모두 V11·V12에 잡힘 |
| 8 | verifier 3 pass: V06·V11·V12·V13 재수용, 나머지 유지, finding 0; 권고 O1(`.py`↔비-`.py` 쌍 미시험, 선언된 분할 밖), O2(주석 구간 경계 mutation 제안) | — | 권고는 다음 작업 후보로 기록 | V14만 남음(전체 R1) |
| 9 | 전체 R1(608건, 38분): flask-admin P21·P22-sonnet-0 judge 답이 JSON parse 실패(끝 쉼표) → infra_failed로 제외돼 칸 recall 하락처럼 보임 | 측정 잡음 | `r1_reanalyze.py --only`로 두 건 재판정 | 정상 판정, flask-admin 칸 변화 0; 남은 하락은 nowinandroid sonnet located -0.051(3건, 주석 유래) |

# Version Log
## v1
- 초안. Test command의 deselect 7개는 이전 spec(2afad1e5c96b32ff)과 같고, base_commit에서 이 묶음을 실행하면 17 failed·5 passed(-n 0); deselect 상태 suite는 3811 passed.
- 원인 근거: 본 실험 NC1 delta(`inject/<repo>/runs/NC1-*/delta.json`)에서 이름이 바뀐 file이 `new_candidates`·`grown_cycles`로, ghostfolio NC1-1에서 `pkg:nestjs:…events-impl.module.ts#EventsModule` 관련 `new_package_dependencies` 46개; nowinandroid NC3-0의 새 READS edge `WorkManagerSyncManager → AnalyticsEvent.Param.value` 근거가 KDoc 줄 48의 단어 "value"(`report.details.json`).


## v2
- F05 적용 위치에 일반 후보 `structure` 문자열 값 추가, V06 분류 B8 추가. 근거: ghostfolio baseline의 `unstable_dependency` 중 259개가 framework scheme `pkg:nestjs:<path>#<Module>`를 `structure.to_package`에 담고, delta.v2 `_general`은 (kind, target, tier 제외 structure)로 대응하므로 target만 매핑하면 이름 변경 시 새 후보로 남는다. 브리프 항목(경로를 담은 NestJS id는 매핑) 범위 안의 계약 보완.

## v3
- test-implementer 이의 반영(계약 보완): F01 제외 출력 목록을 명시(구현이 제외하는 html, assets, bottlenecks, `<out>.json`, `<out>.details.json`, baseline). V05 EP6 예시를 `.git/config` 손상으로 교체: 손상된 `.git/HEAD`는 git이 'not a git repository'로 보고해 `git_failed`에 도달하지 않는다(test-implementer 보고). 기존 test 이름 `test_V02_violation_identity_is_the_candidate_id_not_the_file_pair`는 단언이 내용 대응에서도 성립해 그대로 둔다.

## v4
- F06 셈 단위 명시(위반 candidate 단위, v2와 같음). 근거: 기존 `test_V12_Q03_compute_delta_on_large_synthetic_input`은 내용이 같고 id가 다른 baseline 위반 1000개를 resolved 1000으로 기대하며, 내용 key 집합 차로 세면 1이 된다. 기존 관찰 동작 보존(I4).

## v5
- R1 (3) 교체: `harness.py rescore`는 저장된 `delta.json`을 재사용하고 분석기를 다시 돌리지 않는다(`scripts/eval/inject/harness.py` `cmd_rescore`는 `assess`·`assess_match`만 호출). harness 변경은 범위 밖이므로 harness 함수를 import해 diff 재적용·분석기 재실행·assess·assess_match를 하는 `tests/rename_comment_evidence/r1_reanalyze.py`로 대체. 분석기 재실행 비용은 local, 내용 판정 비용은 A08 그대로.

## v6
- verifier 1 (retry) 반영: V02 S6(baseline commit ≠ HEAD), V06 B9(package 순환 nestjs id; v2의 '14 items'는 A 4 + B 8 = 12 class를 잘못 센 값, 이제 13), V08 D5–D8(나머지 key 필드), V05 EP7(hex 아닌 commit 문자열, option 주입 방지 관찰). Paths 허용 범위에 stdout `[Δ] Renames applied` 줄 추가(F08이 정한 출력, test_delta_cli `stdout_summary`가 걸러냄). V01·V03·V04·V07·V09–V13·V15 v4 acceptance 유지: 변경이 test 추가뿐이고 기존 test·helper 동작을 바꾸지 않는다(ref_delta 변경 없음).

## v7
- [re-brief] F05에 Python symbol id 매핑 추가(A11, 사용자 승인). 근거: 낮 controls pilot에서 NC1 분석기 FP 15/16 → 4/16, 남은 4건 중 CTFd NC1-1, flask-admin NC1-0·NC1-1·NC1-2의 `unresolved_boundary` strengthened가 `['flag', 'py:<module>#<qualname>', 'dynamic_attr']` evidence로, module 이름이 file 이름에서 나옴. V06에 A5·A6 추가(15 items), V06·V13 acceptance invalidated(매핑 규칙 변경; fuzz harness에 `py:` id 생성 추가 후 재실행). Q02는 correction batch 4(주석 구간 bisect 필터) 뒤 implementer 측정 1.018–1.037, main 측정 1.000·1.039·1.031(`tests/rename_comment_evidence/q02_result.txt`).

# Retrospective
## 2026-11-11
| observation | evidence | how to re-check |
| --- | --- | --- |
| 내용 판정 답변이 JSON 문법 오류(끝 쉼표)면 verdict가 null이 되고 그 task는 infra_failed로 점수에서 빠져, 분석기 변화 없이 칸 recall이 떨어진 것처럼 보인다 | 전체 R1에서 flask-admin P21·P22-sonnet-0, sonnet 칸 located 0.250 → 0.218; 두 건 재판정 뒤 0.250 | `harness.py score <repo>` 출력의 `infra_failed` 목록 |
| Kotlin 분석 시간 비율은 기계 부하에 따라 같은 코드에서 0.1 가까이 달라진다 | implementer 측정 1.02–1.08, main 유휴 측정 1.10–1.15(같은 구현) | 유휴 상태에서 `tests/rename_comment_evidence/q02.py`를 base worktree와 번갈아 3라운드 |
| 이 환경에서 CLI 출력 위치를 `mktemp -d`(/var/folders) 아래로 주면 종료 코드 0이어도 `b.json`이 생기지 않았다; 원인 미확인 | 6회 모두 파일 없음, scratchpad 디렉터리로 바꾸자 정상 | `python -m code_analyzer <dir> -o "$(mktemp -d)/r.html" --bottlenecks "$(dirname …)/b.json"` 한 번 실행 후 파일 확인 |
