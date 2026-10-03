---
version: 3
run_id: d01cf9063bb1e4aa
status: complete
base_commit: 88b6fe107dfdba42c8a80b22a733c32bd929b06a
max_verifier_invocations: 2
handoff: agent-docs/handoff/ed8784db945e193f-identifier-ambiguity-metric.md
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자 | 노드 식별자가 저장소에 얼마나 넓게 퍼져 있는지 정적 모호성 신호로 확인 | `bottlenecks.v3` JSON의 `dependency_network.node_metrics[<id>]`에 맥락별 파일 수가 나타남 |

# Scope
In scope: snapshot 전체 파일에서 노드 이름이 단어 단위로 정확히 일치하여 나타나는 파일 수를 맥락(code/comment/docstring/doc/config)별로 세고, `analyze_bottlenecks`의 node_metrics에 병합.
Out of scope: 새 candidate kind, 임계값, `RANKING_KEYS`/rankings 변경, `GraphAnalyzer` 변경, `edge_weights.v1.yaml` 변경, archive 코드 import, 대소문자 무시 매칭, 언어별 완전한 lexer.

# Paths
Implementation: bottlenecks/identifier_occurrence.py, bottlenecks/core.py
Tests: tests/test_identifier_occurrence.py, tests/nestjs_evidence/baselines.json
Test command: .venv/bin/python -m pytest -q
Review evidence: V6 — scratchpad 스크립트 o11_diff.py가 base commit 워크트리와 현재 트리에서 O11 8개 케이스 CLI 출력을 생성하고, 현재 출력에서 identifier_file_count/identifier_file_count_by_context 키를 재귀 제거한 JSON이 base 출력 JSON과 동일함을 출력

# Signatures
bottlenecks.identifier_occurrence.CONTEXTS: tuple[str, ...] == ("code", "comment", "docstring", "doc", "config")
bottlenecks.identifier_occurrence.file_context_kind(path: str) -> str  # "code" | "doc" | "config"
bottlenecks.identifier_occurrence.identifier_file_counts(contents: Mapping[str, str], names: Iterable[str]) -> dict[str, dict[str, int]]  # 각 값의 키 = {"total", *CONTEXTS}
bottlenecks.identifier_occurrence.node_identifier(label: Any) -> str  # 매칭 불가면 ""

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F1 | `file_context_kind`: 확장자(소문자 비교) `.md/.rst/.txt` → doc; `.json/.yaml/.yml/.toml/.properties/.gradle`, 이름이 `.gradle.kts`로 끝나거나 파일명 `.env` → config; 그 외 → code. | must | plan |
| F2 | 매칭: 파일 텍스트를 `[A-Za-z0-9_]+` 토큰으로 나누어 토큰 전체가 이름과 대소문자 포함 정확히 같을 때만 출현. (`Foo`는 `FooBar`, `foo`, `_Foo`와 불일치) | must | plan |
| F3 | code 파일 내부 맥락: `.py/.pyi`는 `#`~줄끝 → comment, `"""`/`'''` 구간 → docstring. 그 외 code 파일은 `//`~줄끝, `/* */` → comment. 한 줄짜리 `'`/`"` 문자열 리터럴 안은 주석 시작으로 보지 않으며 code로 집계. 닫히지 않은 주석/docstring은 파일 끝까지. doc/config 파일은 전체가 해당 맥락. | must | plan, A1 |
| F4 | 파일 단위 집계: 한 파일은 각 맥락에 최대 1 기여; `total`은 어느 맥락이든 출현한 서로 다른 파일 수. 출현이 없으면 모든 값 0. | must | user(파일 수, 맥락별 분리) |
| F5 | `node_identifier(label)`: str이 아니거나 빈 문자열 → ""; 아니면 마지막 `.` 이후 세그먼트이며 그것이 `[A-Za-z0-9_]+` 전체 일치가 아니면 "". `identifier_file_counts`에서 "" 이름은 전부 0. | must | plan |
| F6 | `analyze_bottlenecks`가 모든 노드의 `node_metrics[id]`에 `identifier_file_count`(=total, int)와 `identifier_file_count_by_context`(CONTEXTS 키 5개 dict)를 추가. 기존 metric 키·rankings·candidates는 불변. | must | plan |
| F7 | 결정성: 같은 입력이면 같은 결과(dict 삽입 순서 무관 비교 기준). | must | plan |

# Errors
None introduced. 기존 `analyze_bottlenecks`의 입력 오류 처리(BottleneckInputError)는 변경 없음. 비문자열 label은 오류가 아니라 0 집계(F5).

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | `a.py`: `Foo()` ; 이름 Foo | total 1, code 1, 나머지 0 |
| C2 | normal | `a.py` 주석 `# Foo`, `b.py` docstring `"""Foo"""`, `c.md` Foo, `d.yaml` Foo, `e.ts` `// Foo` | total 5, comment 2, docstring 1, doc 1, config 1, code 0 |
| C3 | boundary | 한 파일에 Foo 10회(code) | code 1, total 1 |
| C4 | boundary | 한 `.py` 파일에 code Foo와 `# Foo` 동시 | code 1, comment 1, total 1 |
| C5 | edge | `FooBar`, `foo`, `_Foo`만 존재 | 모두 0 |
| C6 | edge | `.py`에 `x = "# Foo"` | code 1, comment 0 |
| C7 | edge | `.py`에 `a // Foo` (나눗셈) | code 1, comment 0 |
| C8 | edge | `.ts`에 `/* Foo` (미종결) | comment 1 |
| C9 | edge | label `pkg.mod.Foo` → Foo; label `""`, `None`, `a.b-c` → "" | 마지막은 "" ; "" 이름 값 전부 0 |
| C10 | normal | `x.gradle.kts`, `.env`, `README.MD`, `x.kt` | config, config, doc, code |
| C11 | normal | `analyze_bottlenecks` (snapshot에 노드 이름 출현) | node_metrics에 두 키, 값이 C1 방식과 일치; 기존 키 유지 |
| C12 | error | none — 새 오류 경로 없음 | — |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 지표 정확성이 핵심 |
| Performance efficiency | no | 사용자 미요구; snapshot당 단일 패스 구현 방향만 지시 |
| Compatibility | yes | bottlenecks.v3 기존 키 불변 |
| Interaction capability | no | UI 없음 |
| Reliability | yes | 결정성(F7) |
| Security | no | 외부 입력 실행 없음 |
| Maintainability | no | 별도 측정 목표 없음 |
| Flexibility | no | 해당 없음 |
| Safety | no | 해당 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Functional suitability / correctness | identifier_file_counts | C1–C10 기대값 일치 비율, % | =100% | automated V1–V3 | F1–F5 |
| Q2 | Compatibility / co-existence | bottlenecks.v3 JSON | 기존 node_metrics 키·rankings 키·candidates 동일 여부 | 차이 0 | automated V4 | F6 |
| Q3 | Reliability / faultlessness | 반복 실행 | 동일 입력 3회 결과 동일 | 불일치 0 | automated V5 | F7 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | F1, C10 | file_context_kind | unit | equivalence partitioning | doc, config(suffix), config(.gradle.kts), config(.env), code, 대문자 suffix | 100% | 반환 문자열 | Test command |
| V2 | F2–F4, C1–C8 | identifier_file_counts | unit | equivalence partitioning + boundary value (2-value: 1회/다회, 단일/복수 맥락) | C1–C8 | 100% | 반환 dict 전체 동일 | Test command |
| V3 | F5, C9 | node_identifier + "" 이름 | unit | equivalence partitioning | qualified, bare, "", None, 비단어 세그먼트 | 100% | 반환값 | Test command |
| V4 | F6, C11, Q2 | analyze_bottlenecks → bottlenecks_to_json | integration | scenario | 키 존재, 값 일치(Foo, Foo와 다른 비영 노드, 전부 0 노드), 기존 키·rankings·candidates 불변 | 100% | JSON 파싱 비교 | Test command |
| V6 | F6, Q2 | O11 8개 픽스처 CLI json/bottlenecks 출력 | review + regression (baselines.json 재생성) | scenario | 8 cases × {json, bottlenecks} | 100% | 두 키 제거 시 base 출력과 JSON 동일; 재생성 후 O11 통과 | o11_diff.py 출력, Test command |
| V5 | F7, Q3 | identifier_file_counts (contents 삽입 순서 다르게) | unit | metamorphic | 순서 순열 1개 | 100% | 결과 동일 | Test command |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |
| --- | --- | --- | --- |
| A1 | 주석 문법을 suffix별로 분리(.py/.pyi는 `#`, 그 외 code는 `//`,`/* */`). archive는 모든 code 파일에 둘 다 적용해 Python `//` 나눗셈을 주석으로 오분류. | archive/agent_view/occurrence.py `_classify_regions` | 사용자 승인 (spec v1) |
| A2 | 이름 = label 마지막 `.` 세그먼트 | 계획 승인 | plan 승인 |
| A3 | 문자열 리터럴 안 출현은 code로 집계 | archive 동작 계승, 재현율 우선 원칙 | 사용자 승인 (spec v1) |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F1 | C10 | V1 | Test command |
| F2 | C5 | V2 | Test command |
| F3 | C2, C6, C7, C8 | V2 | Test command |
| F4 | C1, C3, C4 | V2 | Test command |
| F5 | C9 | V3 | Test command |
| F6 | C11 | V4, V6 | Test command, o11_diff.py |
| F7 | — | V5 | Test command |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 2 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state:
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V1, V2, V3, V6 | 3 | verifier#1 | accepted | 독립 oracle, 선언 항목 100% | V6: baselines 재생성 시 모든 bottlenecks 출력에 identifier_file_count 존재 assert 수행(A2) |
| V4 | 3 | test rev2 (Foo/helper/use/py 기대값, type is int) | accepted (verifier#2) | mutation: 전 노드에 마지막 노드 이름 사용 → V4 실패(감지); 전체 label 사용 → 픽스처 label에 '.' 단어 없음으로 inconclusive | — |
| V5 | 3 | test rev2 (순열 + 3회 반복) | accepted (verifier#2) | 독립 oracle | — |

Execution ledger:
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 1 | O11 byte-hash 8 subtests fail | 새 node_metrics 키로 출력 바이트 변경(예상된 변화) | 사용자 결정: baselines.json 재생성 + V6 diff 증거 | spec v2 |
| 2 | verifier#1 B1: V4가 Foo 외 노드 값 미검증; S1: Q3(3회 반복) vs V5(순열 1개) 불일치 | 테스트 증거 부족 / obligation이 승인된 Q3를 덜 반영 | V4 값 검증 확대, V5에 3회 반복 추가(Q3 기대값 불변) | spec v3 |
| 3 | mutations | — | M-map(nodes[-1]) 감지 by V4; M-total(sum of contexts) 감지 by V2[C4], V4; M-py-// 감지 by V2[C7]; M1(full label) inconclusive — 동등 변이 | full suite 917 passed |

# Version Log
## v1
- Initial draft from approved plan and user decisions (파일 수, 맥락별 분리, 지표만).
## v2
- O11 byte baselines conflict with F6 (implementer challenge). User chose baseline regeneration; added baselines.json to Tests paths and V6 review evidence. Test command uses .venv interpreter (system python3 lacks pytest).
## v3
- Verifier#1: B1 → V4 coverage items expanded to non-Foo nonzero and all-zero nodes. S1 → V5 aligned to already-approved Q3 (3 repeated runs added); no approved expectation changed. Advisory A1 (extra lexical cases) left out of scope; A3 o11_diff.py retained in scratchpad only.
