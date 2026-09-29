---
version: 1
run_id: 59af3fa02a94cdfd
status: complete
base_commit: 9dfbe7cc478bea5eef2dd118c6d0450ca46c30d0
max_verifier_invocations: 2
handoff: agent-docs/handoff/5e5f4c6a7336658f-repository-scan-test-advisories.md
---

# User Intent
| id | stakeholder | intention | observable goal |
|---|---|---|---|
| UI-1 | 유지보수자 | static fallback walk의 디렉터리 제외가 깊이와 무관함을 명세·테스트로 고정한다(동작 변경 없음) | 중첩 경로의 숨김·정적 제외 디렉터리 아래 파일이 목록에 없고, 같은 이름의 파일이나 이름이 비슷한 디렉터리는 목록에 있음 |

# Scope
In scope: `repository.scan.list_repository_files`의 static_fallback 경로(walk)의 디렉터리 제외 규칙.
Out of scope: git-tracked 경로, build_snapshot의 제외 사유(vendor/generated glob 등), 구현 변경.

# Paths
Implementation: repository/scan.py
Tests: tests/test_repository_scan.py
Test command: .venv/bin/python -m pytest -q --deselect tests/test_bottlenecks_contract.py::test_NA_05_outside_edge_raises_before_cli_writes --deselect tests/test_bottlenecks_contract.py::test_NA_06_outside_span_raises_before_cli_writes
Review evidence: none — 자동 테스트로 관찰 가능

# Signatures
repository.scan.list_repository_files(root: Path, *, tracked_files_only: bool = True) -> tuple[str, list[str]]   # 불변

# Functional Requirements
| id | requirement | priority | source |
|---|---|---|---|
| FR-1 | static_fallback walk는 모든 깊이에서, 이름이 `.`으로 시작하거나 {.git, __pycache__, build, dist, env, node_modules, venv}에 속하는 디렉터리와 그 하위 전체를 목록에서 뺀다 | must | 사용자 결정(handoff 항목 3 (b)) |
| FR-2 | 제외는 디렉터리 이름 전체 일치로만 판정한다. 같은 이름의 파일(예: 파일 `build`), 이름이 접두/접미로 비슷한 디렉터리(예: `builds`, `my_env`)는 제외하지 않는다 | must | 기존 동작 명시 |
| FR-3 | 반환 목록은 root 기준 posix 상대경로의 정렬 목록, ignore_source는 "static_fallback" | must | 기존 FR-6(spec 3dfc6bf47f6a3947) |

# Errors
none — 이 동작에 새 실패 경로 없음

# Cases
| id | level | input / state | expected result |
|---|---|---|---|
| C-1 | normal | `pkg/node_modules/x.js`, `a/b/build/y.py`, `sub/.cache/z.py`, `deep/1/2/venv/w.py`, `pkg/__pycache__/m.pyc`, `x/dist/d.js`, `x/env/e.py`, 유지 파일 `pkg/keep.py` | 제외 디렉터리 하위 파일 없음, `pkg/keep.py` 있음 |
| C-2 | edge | 파일 `sub/build`(디렉터리 아님), 디렉터리 `sub/builds/b.py`, `sub/my_env/c.py`, 파일 `sub/.hidden_file` | 모두 목록에 있음 |
| C-3 | boundary | 최상위(깊이 1)와 깊이 3 이상에 같은 제외 디렉터리 | 두 깊이 모두 제외 |
| C-4 | error | none — 입력 오류 경로 없음 | — |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
|---|---|---|
| Functional suitability | yes | 목록 정확성 |
| Performance efficiency | no | 동작 변경 없음 |
| Compatibility | no | 인터페이스 불변 |
| Interaction capability | no | UI 없음 |
| Reliability | no | 새 실패 경로 없음 |
| Security | no | 새 입력 표면 없음 |
| Maintainability | no | 구조 변경 없음 |
| Flexibility | no | 해당 없음 |
| Safety | no | 해당 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
|---|---|---|---|---|---|---|
| QR-1 | Functional suitability / Functional correctness | static_fallback 목록 | C-1~C-3 기대 목록과의 불일치 건수 / 건 | = 0 | automated (VO-1, VO-2), mutation | FR-1, FR-2 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
|---|---|---|---|---|---|---|---|---|
| VO-1 | FR-1, FR-3, C-1, C-3 | 실제 임시 디렉터리, tracked_files_only=False | unit · 제외 이름 전체 | equivalence partitioning | D1 `.`시작 이름, D2 .git, D3 __pycache__, D4 build, D5 dist, D6 env, D7 node_modules, D8 venv — 각각 깊이 ≥2 위치에서; 추가로 한 이름을 깊이 1과 깊이 ≥3에 동시 배치 | 100% | 정확한 목록 일치, ignore_source "static_fallback" | Test command |
| VO-2 | FR-2, C-2 | 실제 임시 디렉터리 | unit | equivalence partitioning | K1 제외 이름과 같은 이름의 파일, K2 접미 유사 디렉터리(builds), K3 접두 유사 디렉터리(my_env), K4 `.`시작 파일 | 100% | 모두 목록에 있음 | Test command |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
|---|---|---|---|
| A-1 | 구현 변경 없이 테스트만 추가(implementer 단계 생략) | 현재 walk는 os.walk 각 단계에서 이름으로 가지치기함; 테스트가 실패하면 구현 결함으로 보고 | 사용자 전체 승인 (v1) |
| A-2 | Test command의 NA_05/NA_06 deselect는 이전 spec과 동일 | spec 3dfc6bf47f6a3947 승인 사항 | 이전 승인 승계 |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
|---|---|---|---|
| FR-1, FR-3 / QR-1 | C-1, C-3 | VO-1 | Test command |
| FR-2 / QR-1 | C-2 | VO-2 | Test command |

# Workflow Control
| item | value |
|---|---|
| correction batches used | 0 |
| verifier invocations | 1 |
| open finding ids | none |

Audit state:
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
|---|---|---|---|---|---|
| VO-1 | 1 | NestedWalkExclusionTests D1..D8, depth 1+4 조합 | accepted | M11(최상위만 가지치기)·M13(. 접두 제거) 검출 | — |
| VO-2 | 1 | NestedWalkExclusionTests K1..K4 | accepted | M12(부분 문자열) 검출 | — |

Execution ledger:
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
|---|---|---|---|---|
| 1 | 550 passed; verifier 1 pass, finding 0 | — | 뮤테이션 M11~M13 3/3 검출 | complete |

# Version Log
## v1
- 최초 작성. handoff 5e5f4c6a7336658f 항목 3에 대한 사용자 결정 (b).
