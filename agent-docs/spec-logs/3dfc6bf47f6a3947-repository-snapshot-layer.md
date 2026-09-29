---
version: 4
run_id: 3dfc6bf47f6a3947
status: complete
base_commit: 87d3a72514464495ff991694e1333da0d1daf434
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
|---|---|---|---|
| UI-1 | 유지보수자 | 언어·framework 분석기가 agent_view 패키지에 의존하지 않는다 | `language_analyzers/`, `framework_analyzers/`의 Python 소스에 `agent_view` 또는 `agent_view.*` import 0건 |
| UI-2 | 유지보수자 | 스냅샷 모델과 생성 로직이 agent_view 밖 공통층 `repository/`에 있다 | `repository`가 공개 API를 export하고 agent_view를 import하지 않음 |
| UI-3 | 유지보수자 | 제외 규칙을 버전 관리되는 새 profile 파일로 둔다(ADR 77ee4cf0755552e5) | `profiles/snapshot.v1.yaml`을 로드하면 id/version/sha256 ref를 가진 정책이 나옴 |
| UI-4 | 유지보수자 | agent_view는 삭제하지 않고 새 위치를 사용하며 기존 동작을 유지한다 | agent_view 경유 import가 계속 동작하고, 기존 스냅샷 결과(내용, 제외 사유, digest)가 불변 |

# Scope
In scope: `repository/` 패키지(모델, 스캔, 정책 로더), `profiles/snapshot.v1.yaml`, agent_view의 재노출과 `Profile.scan_policy()`, 분석기·`bottlenecks/core.py`·`code_analyzer/cli.py`의 import/호출부 전환, 이 변경으로 깨진 기존 테스트의 호출부 갱신.
Out of scope: agent_view 삭제, `agent_view/occurrence.py` 이동, CLI 실행 경로를 snapshot.v1로 전환, `profiles/agent_view.v3.yaml` 수정, 기존 실패 NA_05/NA_06 수정.

# Paths
Implementation: repository/, profiles/snapshot.v1.yaml, agent_view/models.py, agent_view/profile.py, agent_view/scan.py, agent_view/__init__.py, bottlenecks/core.py, code_analyzer/cli.py, language_analyzers/, framework_analyzers/
Tests: tests/
Test command: .venv/bin/python -m pytest -q --deselect tests/test_bottlenecks_contract.py::test_NA_05_outside_edge_raises_before_cli_writes --deselect tests/test_bottlenecks_contract.py::test_NA_06_outside_span_raises_before_cli_writes
Review evidence: none — 모든 의무가 자동 테스트로 관찰 가능

# Signatures
repository.models.ScanPolicyRef(id: str, version: int, content_hash: str)   # frozen dataclass
repository.models.ScanPolicy(ref: ScanPolicyRef, max_file_bytes: int, generated_marker_lines: int = 8, include_agent_docs: bool = True, tracked_files_only: bool = True, vendor_globs: list[str] = [], generated_globs: list[str] = [], generated_markers: list[str] = [], lockfile_names: list[str] = [])   # frozen dataclass
repository.models.ExcludedFile(file_path: str, reason: str)   # frozen dataclass
repository.models.RepositorySnapshot(root: str, ignore_source: str, contents: tuple[tuple[str, str], ...], excluded_files: tuple[ExcludedFile, ...], digest: str); .content_map() -> dict[str, str]
repository.policy.load_scan_policy(path: str | Path) -> ScanPolicy
repository.policy.default_scan_policy_path() -> Path   # <repo>/profiles/snapshot.v1.yaml
repository.policy.ScanPolicyError(ValueError)
repository.scan.read_file(path: Path) -> str | None
repository.scan.list_repository_files(root: Path, *, tracked_files_only: bool = True) -> tuple[str, list[str]]
repository.scan.build_snapshot(root: Path, relative_paths: Sequence[str], *, policy: ScanPolicy, reader: Callable[[Path], str | None] = read_file, ignore_source: str = "provided", excluded_paths: Sequence[str] = ()) -> RepositorySnapshot
repository (package) exports: ExcludedFile, RepositorySnapshot, ScanPolicy, ScanPolicyRef, ScanPolicyError, build_snapshot, default_scan_policy_path, list_repository_files, load_scan_policy, read_file
agent_view.profile.Profile.scan_policy() -> ScanPolicy
agent_view.models.RepositorySnapshot / ExcludedFile  is  repository.models 의 같은 객체
agent_view.scan.build_snapshot / list_repository_files / read_file  is  repository.scan 의 같은 객체; agent_view.scan.scan_files(root: Path, relative_paths: Sequence[str], *, max_file_bytes: int, reader: Callable[[Path], str | None], include_agent_docs: bool = True) -> tuple[list[str], list[ExcludedFile], dict[str, str]]  # (포함 경로 정렬 목록, reason≠agent_document_disabled인 제외 목록, 포함 path→text); vendor_globs·generated_globs는 빈 목록(비적용); lockfile_names=[package-lock.json, yarn.lock, pnpm-lock.yaml, poetry.lock, Pipfile.lock], generated_markers=["generated file", "do not edit"], generated_marker_lines=8은 적용; 그 외 사유(explicit_output 제외)는 FR-4와 동일
mock 대상 이동: git 목록/파일 walk 내부 함수는 repository.scan._git_tracked_files, repository.scan._walk_files

# Functional Requirements
| id | requirement | priority | source |
|---|---|---|---|
| FR-1 | `language_analyzers/`, `framework_analyzers/`, `repository/` 아래 모든 `.py`는 `agent_view` 또는 `agent_view.`로 시작하는 모듈을 import하지 않는다(AST의 Import/ImportFrom 기준) | must | 사용자 완료 조건 |
| FR-2 | `load_scan_policy`는 YAML 매핑에서 id(비어있지 않은 str), version(==1), max_file_bytes(int ≥1, bool 아님), exclusions(매핑; vendor_globs/generated_globs/generated_markers/lockfile_names 각각 str 배열)를 필수로 읽는다. 선택: generated_marker_lines(int ≥1, 기본 8), include_agent_docs·tracked_files_only(bool, 기본 True). ref = (id, 1, 파일 바이트 sha256 hex) | must | ADR 77ee4cf0755552e5 |
| FR-3 | `profiles/snapshot.v1.yaml`의 정책은 ref를 제외한 모든 필드가 `load_profile(agent_view.v3.yaml).scan_policy()`와 같고, ref.id="snapshot", ref.version=1 | must | 사용자 결정(새 profile, 값 복제) |
| FR-4 | `build_snapshot`은 입력 경로를 posix화·선행 "./" 제거·중복 제거·정렬하고, 각 파일에 대해 다음 순서로 첫 해당 사유를 매긴다: explicit_output(excluded_paths 자체 또는 그 하위; 절대경로는 root 기준 상대화, root 밖은 무시) → lockfile(파일명 ∈ lockfile_names) → vendored(fnmatch vendor_globs) → generated_path(fnmatch generated_globs) → unreadable(reader가 None 반환 또는 OSError/UnicodeError) → analyzer_artifact(텍스트에 `"schema_version": "2"|"3"`(콜론 뒤 공백 0/1) 가 있고 `"occurrence_store"` 또는 `"query_nodes"`가 있음, 또는 앞 65536자에 `agent-view-v3-payload` 또는 `id="agent-view-data"`) → too_large(UTF-8 바이트 > max_file_bytes) → binary(앞 8192자에 NUL) → generated_marker(앞 generated_marker_lines 줄에 generated_markers 정규식이 대소문자 무시로 일치) → agent_document_disabled(include_agent_docs=False이고 파일명 ∈ {AGENTS.md, CLAUDE.md, README.md}). 사유 없는 파일은 contents에, 있는 파일은 excluded_files에 경로 정렬 순서로 들어간다 | must | 기존 동작 보존 |
| FR-5 | digest = sha256(각 포함 파일에 대해 `path\0sha256(text utf-8 hex)\n`을 경로 순서로 이은 문자열) hex. 같은 입력이면 결정적 | must | 기존 동작 보존 |
| FR-6 | `list_repository_files`는 tracked_files_only=True이고 `git ls-files -z`가 returncode 0이고 NUL로 나눈 비어있지 않은 항목이 1개 이상이면 ("git-tracked", 정렬 목록), 아니면 ("static_fallback", walk 결과 정렬; `.`로 시작하는 디렉터리와 .git/__pycache__/build/dist/env/node_modules/venv 제외) | must | 기존 동작 보존 |
| FR-7 | agent_view 호환: FR-signature의 재노출 객체 동일성, `Profile.scan_policy()`가 profile의 max_file_bytes·generated_marker_lines·include_agent_docs·tracked_files_only·네 제외 목록과 ref(id, version, content_hash)를 그대로 옮긴다. `build_agent_view`와 CLI는 agent_view profile의 정책으로 스냅샷을 만든다(CLI의 `--agent-view-profile`로 선택된 profile의 `scan_policy()`가 `build_snapshot(policy=...)`로 전달) | must | 사용자 지시(삭제 없이 새 위치 사용) |
| FR-8 | `build_snapshot` 결과의 root = str(root 인자), ignore_source = 인자값(생략 시 "provided"). `read_file(path)`는 파일 바이트를 UTF-8(errors=replace)로 디코드한 str을 반환하고, OSError면 None | must | verifier F-1, 사용자 결정(기존 동작 명시) |

# Errors
- 정책 파일 읽기 실패(OSError) — ScanPolicyError(메시지에 경로) — 정책 없음, 부작용 없음
- YAML 파싱/디코딩 실패, 루트가 매핑 아님, 필수 키 누락, id 빈 값/비문자열, version≠1, max_file_bytes·generated_marker_lines가 int≥1 아님(bool 포함), include_agent_docs·tracked_files_only가 bool 아님, exclusions가 매핑 아님, 제외 목록이 str 배열 아님 — ScanPolicyError — 정책 없음
- build_snapshot의 reader 예외(OSError/UnicodeError) — 예외 전파 없이 해당 파일 excluded reason "unreadable" — 나머지 파일 정상 처리

# Cases
| id | level | input / state | expected result |
|---|---|---|---|
| C-1 | normal | 저장소 소스 트리 | FR-1 대상 import 0건 |
| C-2 | normal | 기본 snapshot.v1.yaml | FR-3 등식, ref=("snapshot",1,64자 hex), content_hash = 파일 바이트 sha256 |
| C-3 | normal | 제외 사유별 파일 1개씩 + 일반 파일 | FR-4 각 사유, 일반 파일만 contents |
| C-4 | boundary | too_large: 바이트 = max, max+1 / marker: 줄 = generated_marker_lines, +1 / binary NUL 위치 8191, 8192(0-index) | = max 포함, max+1 too_large / 경계 줄 안은 generated_marker, 밖은 포함 / 8191 binary, 8192 포함 |
| C-5 | edge | 한 파일이 여러 사유 해당(예: vendor 아래 lockfile, generated 경로의 unreadable) | 우선순위상 첫 사유 |
| C-6 | edge | 경로 "./a.py"와 "a.py" 중복, 역순 입력; excluded_paths 절대경로(root 하위/밖), "out"과 "outside/x" | 하나로 정규화·정렬; root 밖 무시; "out/..."만 explicit_output, "outside/x" 아님 |
| C-7 | normal | 같은 입력 2회, 내용 1바이트 변경 | digest 동일 / 변경 시 다름; 기대값은 테스트가 독립 계산 |
| C-8 | error | FR-2 Errors의 각 잘못된 정책 | ScanPolicyError |
| C-9 | error | reader가 OSError, None 반환 | unreadable, 다른 파일 계속 |
| C-10 | normal | git 성공(항목 있음)/실패/빈 목록, tracked_files_only False | FR-6 각 분기 |
| C-11 | normal | agent_view 재노출, Profile.scan_policy, CLI의 선택 profile 전달, build_agent_view 스냅샷 | FR-7 |
| C-13 | normal | root·ignore_source 지정/생략; read_file에 정상 UTF-8, 깨진 바이트, 없는 경로 | FR-8 |
| C-12 | normal | 기존 테스트 스위트(호출부 갱신 후) | 전부 통과(deselect 2건 제외) |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
|---|---|---|
| Functional suitability | yes | 스냅샷 결과 정확성·완전성 |
| Performance efficiency | no | 로직 이동뿐, 알고리즘 불변 |
| Compatibility | yes | agent_view 경유 사용자와 공존 |
| Interaction capability | no | UI 변경 없음 |
| Reliability | no | 오류 처리 동작 불변이며 FR/Errors로 커버 |
| Security | no | 신규 입력 표면 없음(yaml.safe_load 유지는 FR-2 테스트 범위 밖) |
| Maintainability | yes | 모듈 경계(의존 방향) 자체가 목표 |
| Flexibility | no | 이식성 변경 없음 |
| Safety | no | 해당 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
|---|---|---|---|---|---|---|
| QR-1 | Maintainability / Modularity | language_analyzers, framework_analyzers, repository 패키지 | AST로 수집한 import 중 agent_view* 개수 / 건 | = 0 | automated (VO-1), mutation | UI-1 |
| QR-2 | Compatibility / Co-existence | agent_view 경유 API와 기존 스위트 | 재노출 객체 동일성 위반 수 + Test command 실패 수 / 건 | = 0 | automated (VO-9, VO-10), mutation | UI-4 |
| QR-3 | Functional suitability / Functional correctness | build_snapshot 사유·digest | FR-4/FR-5 기대값과 불일치 건수 / 건 | = 0 | automated (VO-3~VO-6) | FR-4, FR-5 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
|---|---|---|---|---|---|---|---|---|
| VO-1 | FR-1, QR-1, C-1 | 세 패키지의 소스 파일 | unit(정적) · 전 파일 | equivalence partitioning | P1 language_analyzers, P2 framework_analyzers, P3 repository | 100% | 각 패키지 파일 1개 이상 검사, agent_view import 0 | Test command |
| VO-2 | FR-2, FR-3, C-2 | 기본 정책 파일, 임시 정책 파일 | unit | equivalence partitioning | V1 기본 파일 등식·ref, V2 선택 키 생략 시 기본값(8, True, True), V3 선택 키 명시값 반영 | 100% | 기대값은 테스트가 hashlib/load_profile로 독립 산출 | Test command |
| VO-3 | FR-2, Errors, C-8 | load_scan_policy | unit | equivalence partitioning | E1 파일 없음, E2 YAML 오류, E3 루트 비매핑, E4 최상위 필수 키 누락(id, version, max_file_bytes, exclusions 각각) 및 exclusions의 4개 목록 각각 누락, E5 id 빈값, E6 version≠1, E7 max_file_bytes 0, E8 bool 값, E9 bool 필드 비bool, E10 exclusions 비매핑, E11 목록 원소 비문자열 | 100% | 각 ScanPolicyError | Test command |
| VO-4 | FR-4, C-3, C-5 | build_snapshot 사유 | unit | decision table | 10개 사유 각 1행(R1..R10) + 포함 행 R0 + 우선순위 인접 쌍 8쌍 R1>R2, R2>R3, R3>R4, R4>R5, R6>R7, R7>R8, R8>R9, R9>R10 (각 앞뒤 사유 동시 충족 시 앞 사유; R5 unreadable은 내용이 없어 R6과 동시 충족 불가하므로 제외) | 100% | excluded_files 매핑이 기대와 동일 | Test command |
| VO-5 | FR-4, C-4 | too_large, generated_marker, binary | unit | boundary value analysis (2-value) | B1 max/max+1, B2 marker 줄 N/N+1, B3 NUL 8191/8192 | 100% | 경계 안/밖 분류 | Test command |
| VO-6 | FR-4, FR-5, C-6, C-7, C-9 | 정규화·explicit_output·digest·unreadable | unit | equivalence partitioning | N1 ./ 제거+중복, N2 정렬, O1 상대 하위, O2 절대 하위, O3 root 밖 무시, O4 접두사 유사 경로 비해당, D1 digest 독립 계산 일치, D2 내용 변경 시 변화, U1 reader OSError, U2 reader None | 100% | 기대 동작 | Test command |
| VO-7 | FR-6, C-10 | list_repository_files | unit(mock 허용: repository.scan._git_tracked_files, subprocess) 또는 임시 git 저장소 | decision table | L1 git 항목 있음, L2 git 실패 — L2a returncode≠0이면서 stdout 비어있지 않음(subprocess.run mock), L2b OSError, L2c 출력 항목 0개(실제 git 또는 subprocess 수준) — 각각 static_fallback, L3 tracked_files_only False, L4 walk에서 숨김·정적 제외 디렉터리 | 100% | ignore_source와 목록 | Test command |
| VO-8 | FR-7, C-11 | Profile.scan_policy | unit | equivalence partitioning | S1 기본 profile, S2 제외 값을 바꾼 임시 profile | 100% | 모든 필드 전달 | Test command |
| VO-9 | FR-7, QR-2, C-11 | agent_view 재노출 | unit | equivalence partitioning | X1 models.RepositorySnapshot, X2 models.ExcludedFile, X3 scan.build_snapshot, X4 scan.list_repository_files, X5 scan.read_file, X6 agent_view 패키지 build_snapshot, X7 scan_files 반환 형식(Signatures 참조: vendor/generated glob 비적용, lockfile·generated_marker 적용, agent_document_disabled 제외 항목 누락, include_agent_docs=False 시 AGENTS.md 비포함) | 100% | `is` 동일, scan_files는 기존 반환 형식 | Test command |
| VO-10 | FR-7, QR-2, C-11, C-12 | CLI·build_agent_view, 기존 스위트 | integration | scenario | SC1 CLI `--agent-view-profile` 선택 profile의 scan_policy()가 build_snapshot policy로 전달, SC2 build_agent_view(snapshot 없음)가 profile 정책으로 스냅샷 생성 — 기본값과 다른 lockfile_names·generated_globs(예: 비움)로 기본 lockfile명·기본 generated glob 일치 파일이 포함되거나 그 반대, max_file_bytes·markers·agent docs 포함, SC3 기존 테스트 호출부 갱신 후 전부 통과 | 100% | 기대 동작 | Test command |
| VO-11 | FR-8, C-13 | build_snapshot 결과 필드, read_file | unit | equivalence partitioning | T1 root=str(root), T2 ignore_source 지정값, T3 생략 시 "provided", F1 정상 UTF-8, F2 잘못된 UTF-8 바이트가 U+FFFD로 대체, F3 없는 경로 None | 100% | 기대 동작 | Test command |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
|---|---|---|---|
| A-1 | Test command에서 NA_05/NA_06을 deselect | 변경 전 기준 실행(base_commit)에서도 실패; 이전 spec 44ff0ed597e46cf3도 같은 deselect 사용 | 사용자 전체 승인 (v1) |
| A-2 | 구조 기반 커버리지 없음 | .venv에 pytest-cov 없음; 명세 기반 기법으로 대체 | 사용자 전체 승인 (v1) |
| A-3 | implementer 단계는 이미 수행됨(본 세션 main이 구현); 테스트 역할은 Implementation을 읽지 않음 | 사용자 지시 | 사용자 지시 |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
|---|---|---|---|
| FR-1 / QR-1 | C-1 | VO-1 | Test command |
| FR-2 | C-2, C-8 | VO-2, VO-3 | Test command |
| FR-3 | C-2 | VO-2 | Test command |
| FR-4 / QR-3 | C-3~C-6, C-9 | VO-4, VO-5, VO-6 | Test command |
| FR-5 / QR-3 | C-7 | VO-6 | Test command |
| FR-6 | C-10 | VO-7 | Test command |
| FR-7 / QR-2 | C-11, C-12 | VO-8, VO-9, VO-10 | Test command |
| FR-8 | C-13 | VO-11 | Test command |

# Workflow Control
| item | value |
|---|---|
| correction batches used | 3 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state:
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
|---|---|---|---|---|---|
| VO-1..VO-6, VO-8, VO-9 | 4 | verifier 1(v3) 수용, verifier 2 유지 | accepted | M1·M2·M4 검출 | 해당 테스트/헬퍼 변경 시 재개 |
| VO-7 | 4 | test_VO7_L1..L4, L2a | accepted | M3 검출(보강 후) | — |
| VO-10 | 4 | SC1, SC2 2건, SC3(diff 검토) | accepted | M5 검출 | — |
| VO-11 | 4 | SnapshotMetadataTests | accepted | M6 검출 | — |

Execution ledger:
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
|---|---|---|---|---|
| 0 | 테스트 revert 후 53 failed(test_agent_view_graph 2, test_bottlenecks_contract 20, test_cli_contract 1, test_m3 2, test_readability_bottlenecks 28) | build_snapshot `profile=`→`policy=` 및 mock 경로 이동 | test-implementer가 호출부 갱신(VO-10 SC3) | resolved: 527 passed, 2 deselected |
| 1 | test-implementer challenge: X7 서명 미정, R5>R6 불가능, E4 모호, 빈 git 목록 판정 수준, artifact 표식 미정 | spec 명세 누락(구현 동작 자체는 기존과 동일) | v2에서 기존 동작 명시 | X7 추가 테스트 요청 |
| 2 | X7 실패: scan_files가 yarn.lock을 lockfile로 제외 | spec v2가 기존 동작을 잘못 서술(base 87d3a72의 scan_files도 Profile 기본 lockfile_names 적용) | v3에서 spec 정정; 구현 변경 없음 | 테스트 재정렬 요청 |
| 3 | verifier 1 retry: F-1 spec challenge, F-2/F-3 evidence gap, F-4 diff 미제공 | F-1 FR 누락; F-2/F-3 테스트 누락; F-4 증거 미제공 | F-1 → FR-8/VO-11(사용자 승인), F-2 → L2a, F-3 → SC2 보강, F-4 → git diff 확인(호출부·mock 경로만) | 테스트 보강 요청 |
| 4 | F-2/F-3/VO-11 보강 후 537 passed | — | 뮤테이션 M3(returncode 무시)→L2a 검출, M5(build_agent_view 기본 정책)→SC2 검출, M6(ignore_source 상수화)→VO-11 T2 검출 | verifier 2 dispatch |
| 5 | verifier 2 pass, finding 0 | — | advisory만 남음(git-tracked 분기 강화 제안, 경계·정규화 뮤테이션 미실행) | complete |

# Version Log
## v1
- 최초 작성. 구현은 1단계 계획(repository/ 공통층) 승인 후 선행 완료, 테스트는 사용자 지시로 revert.
## v2
- test-implementer challenge 반영: scan_files 시그니처·반환 형식, analyzer_artifact 표식, git 빈 목록 판정 수준(git 출력 수준), E4 키 범위를 기존 동작 그대로 명시; VO-4에서 동시 충족 불가 쌍 R5>R6 제거. 승인된 동작 변경 없음. FR-2 version에 bool True(파이썬상 ==1) 허용 여부는 범위 밖으로 테스트하지 않음.
## v3
- v2의 scan_files 서술 오류 정정: base 커밋 agent_view/scan.py의 scan_files는 vendor/generated glob만 비우고 lockfile_names·generated_markers는 Profile 기본값을 적용함(git show 87d3a72 확인). 승인된 동작 변경 없음.
## v4
- verifier 1 F-1: FR-8/C-13/VO-11 추가(기존 동작 명시, 사용자 승인). F-2: VO-7 L2를 L2a/b/c로 분리. F-3: VO-10 SC2에 lockfile_names·generated_globs 배선 관찰 명시. F-4: 기존 테스트 diff가 호출부·mock 경로 교체와 VO-1 추가뿐임을 확인해 SC3 accepted.
