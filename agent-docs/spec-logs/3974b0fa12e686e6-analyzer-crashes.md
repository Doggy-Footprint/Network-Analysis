---
version: 3
run_id: 3974b0fa12e686e6
status: complete
base_commit: 69ecc47a9a406fd2e433667890b3898e99b2bc19
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 분석기 사용자 | 공백만 있는 docstring을 가진 Python 저장소도 끝까지 분석한다 | apowerb(`-f fastapi -f sqlalchemy`)가 rc 0으로 끝난다 |
| I2 | 분석기 사용자 | 256열을 넘는 위치에 NestJS 진단·endpoint·bootstrap이 있는 저장소도 끝까지 분석한다 | ailh(`-f nestjs`)가 rc 0으로 끝난다 |
| I3 | 분석기 사용자 | 같은 이름의 Retrofit interface가 여러 파일에 있거나 메서드가 오버로드된 Android 저장소도 끝까지 분석한다 | lastwave(`-f android`)가 `--bottlenecks`와 함께 rc 0으로 끝난다 |

# Scope
In scope: Python module/symbol 노드 docstring 첫 줄 추출(`language_analyzers/python/graph.py`), NestJS 분석기의 tree-sitter Point 열 접근(`framework_analyzers/nestjs/analyzer.py`, 필요하면 `language_analyzers/typescript/ast.py` helper), Android Retrofit endpoint id 형식(`framework_analyzers/android/analyzer.py`), 저장소 Python 코드의 Point 속성 접근 금지 검사, 두 golden 파일 안의 Retrofit endpoint id 치환.
Out of scope: base_commit부터 실패하는 `test_nestjs_quality` O11 byte-hash characterization(subtest 6개), 저장소 안 앱 사본(lastwave `reference zip/`) 제외 정책, 예전 Retrofit id 호환 매핑, Tusky·wikipedia 실패 조사, 다른 분석기 id 체계 정비, base_commit부터 실패하는 characterization 테스트 5개(`test_file_analysis_cli` V01×4, `test_analysis_coverage_reporting` V05)의 golden drift 수정, `requirements.txt` 버전 범위 변경.

# Paths
Implementation: language_analyzers/python/graph.py, framework_analyzers/nestjs/analyzer.py, language_analyzers/typescript/ast.py, framework_analyzers/android/analyzer.py
Tests: tests/
Test command: .venv/bin/python -m pytest -q --deselect tests/test_file_analysis_cli.py::test_V01_direct_builder_defaults_characterization --deselect tests/test_analysis_coverage_reporting.py::test_V05_characterization_and_V04_cli_stages --deselect tests/test_nestjs_quality.py::TestRegression::test_O11_characterization_existing_standalone_outputs_are_byte_identical
Review evidence: RE1 base 비교 — main이 `git worktree add --detach <scratch>/base 69ecc47a9a406fd2e433667890b3898e99b2bc19`를 만들고 `PYTHONHASHSEED=0`으로 base와 작업 트리에서 `python -m code_analyzer.cli <fixture> <variant> -o a.html --json --bottlenecks b.json`을 실행한다. 대상: fastapi-realworld(`-f fastapi`), android-nowinandroid(`-f android`), typescript-nestjs-realworld(`-f nestjs`). JSON에서 Retrofit endpoint id를 old→new로 대응시켜 바꾼 뒤 `cmp`; 기대 차이 0. RE2 실제 저장소 — main이 로컬 scratchpad clone(apowerb `04e4f1fd`, ailh `1dba04fa`, lastwave `3eaf19f9`)에 handoff의 명령으로 `/usr/bin/time -l`과 함께 실행; 기대 rc 0, 최대 RSS 기록. RE3 tree-sitter 0.25.2 호환 — main이 scratchpad venv(tree-sitter 0.25.2, tree-sitter-language-pack 1.20.0, requirements-dev)에서 이번 run이 추가한 NestJS 열 회귀 테스트를 실행; 기대 통과. 결과는 Audit state와 Execution ledger에 남긴다.
Fuzzing: main이 scratchpad `crash-fuzz/fuzz_docstring.py`를 작성한다. 표면: 무작위 docstring(공백류 `' '`, `\t`, `\n`, `\r`, `\x0b`, `\x0c`, `\x1c`–`\x1f`, `\x85`, ` `, `　`과 ASCII·한글 글자를 섞음)을 module·class·function에 넣은 Python 파일 1개 저장소를 Python 그래프 빌더로 분석. 오라클: (crash) 예외 없음, (property) 각 노드 docstring은 `ast.get_docstring` 결과를 `strip()`한 문자열의 `splitlines()` 첫 원소이고, 그 목록이 비면 `None`. seed 20261023, 3000 입력.
Mutation tool: main이 scratchpad의 AST mutation 스크립트(비교·불리언·상수·조건 부정·인덱스 변경)를 base_commit 이후 변경된 Implementation Python 줄에 적용한다. 최대 30개 표본, seed 20261023. 실행 명령 `.venv/bin/python -m pytest -q -p no:cacheprovider -x -n 0 <이번 run이 추가·수정한 테스트 파일>`. 생존율 임계 40%.

# Signatures
RetrofitEndpointInfo.id == f"retrofit_{module}_{interface}_{method}_{line}"  # module: 프로젝트 기준 상대 파일 경로(RetrofitApiInfo.module와 같음), interface: 선언 이름, method: 함수 이름, line: annotation을 포함한 function_declaration 노드의 시작 줄(1부터, Room `query_` id와 같은 기준)
GraphNode.docstring (Python module/symbol) -> Optional[str]
NestJSDiagnostic.span / NestJSDeclaration.span: SourceSpan(start_col, end_col)  # 노드 시작·끝 Point의 0부터 세는 열(바이트), 기존 의미 유지. span 노드(기존 동작): endpoint declaration = HTTP decorator 노드(`@`부터 닫는 괄호까지), application declaration = `NestFactory.create(...)` call_expression 노드(`NestFactory`부터 닫는 괄호까지, `await` 제외)
NestJS endpoint declaration name == f"{Controller}.{method}@{decorator_start_line}:{decorator_start_col}", application name == f"NestFactory.create@{line}:{col}"  # 기존 형식 유지

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F1 | Python module·symbol 노드의 docstring은 `ast.get_docstring` 결과를 `strip()`한 문자열의 첫 줄이고, docstring이 없거나 공백·개행뿐이면 `None`이다. 분석은 예외 없이 끝난다 | must | handoff 버그 1 |
| F2 | NestJS 분석기가 만드는 span의 `start_col`·`end_col`과 endpoint·application 식별자의 열 값은 노드 위치의 실제 0 기반 열과 같다(열 256 초과 포함). 분석은 프로세스 크래시 없이 끝난다 | must | handoff 버그 2, main 재현 |
| F3 | Retrofit endpoint id는 `retrofit_{module}_{interface}_{method}_{line}` 형식이다. 같은 이름 interface가 다른 파일에 있거나 한 interface 안에 같은 이름 메서드가 있어도 id가 서로 다르고, `-f android --bottlenecks` 실행이 `architecture node ids are invalid` 없이 끝난다 | must | handoff 버그 3, 사용자 승인(Ask 1) |
| F4 | 저장소의 git 추적 Python 파일 중 `tests/` 밖 파일은 tree-sitter Point의 `.row`·`.column` 속성에 접근하지 않는다(`(start|end)_point\s*\.\s*(row|column)\b`). 이 규칙은 자동 테스트로 검사된다 | must | main 진단(tree-sitter 0.26.0 refcount 결함) |
| F5 | golden `tests/coverage_reporting_evidence/characterization-baseline.json`과 `tests/file_analysis_evidence/direct-api-original.json`의 Retrofit endpoint id만 새 형식으로 바꾸고, 다른 내용은 바꾸지 않는다 | should | 사용자 승인(Ask 1), A3 |

# Errors
none — 이번 변경은 크래시를 없애며 새 오류 신호를 만들지 않는다. 기존 NestJS 진단(`unresolved_reference` 등)은 기존 조건 그대로 diagnostics에 남고 분석은 계속된다.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C1 | normal | 함수 docstring `"""Load users.\n\n    Details.\n    """` | 노드 docstring `"Load users."` |
| C2 | edge | 함수 docstring `"""\n    """`(개행 뒤 들여쓰기만) | 노드 docstring `None`, 분석 예외 없음 |
| C3 | edge | class docstring `"""\n    """` | 노드 docstring `None` |
| C4 | edge | 모듈 첫 문장 docstring이 공백·개행뿐(`ast.get_docstring`이 비어 있지 않은 공백 문자열을 돌려주는 형태) | module 노드 docstring `None` |
| C5 | boundary | docstring이 빈 줄로 시작하고 뒤에 글이 있음 `"""\n\n    Text\n    """` | `"Text"` |
| C6 | normal | docstring 없는 함수 | `None` |
| C7 | boundary | NestJS `@Injectable` 생성자 매개변수 타입이 해결되지 않는 참조이고, 그 참조의 시작 열이 255, 256, 257, 1000 근처 | 각 진단 span의 `start_col`·`end_col`이 실제 열과 같고 프로세스 rc 0 |
| C8 | boundary | `@Controller` 메서드의 HTTP decorator가 열 257 이상에서 시작 | endpoint 식별자 `C.m@<line>:<col>`의 col이 실제 열 |
| C9 | boundary | `NestFactory.create(...)` 호출이 열 257 이상에서 시작 | application 식별자 `NestFactory.create@<line>:<col>`의 col이 실제 열 |
| C10 | normal | Retrofit interface 1개(파일 1개, 메서드 2개) | 각 endpoint id가 `retrofit_{module}_{interface}_{method}_{line}` |
| C11 | edge | 서로 다른 두 파일에 같은 이름 interface와 같은 이름 메서드 | 두 endpoint id가 다르고 각 id에 자기 파일 경로가 들어 있음; CLI `-f android --bottlenecks` rc 0 |
| C12 | edge | 한 interface 안에 같은 이름 메서드 두 개(오버로드) | 두 endpoint id가 줄 번호로 구분됨 |
| C12b | boundary | Retrofit 메서드의 `@GET(...)`이 `fun` 바로 윗줄에 있음 | endpoint id의 line은 annotation 줄 |
| C13 | normal | 저장소 현재 상태 | F4 검사 통과 |
| C14 | error | none — 새 오류 경로 없음(Errors 참고) | — |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 세 크래시 수정과 값 정확성 |
| Performance efficiency | no | 상수 시간 문자열 처리·접근 방식 변경뿐이라 복잡도 변화 없음 |
| Compatibility | yes | Android endpoint id 형식이 바뀌고(interoperability), tree-sitter 허용 범위 0.24–0.26에서 동작해야 함(co-existence) |
| Interaction capability | no | CLI·report 표시 변화 없음 |
| Reliability | yes | 실제 저장소 3곳에서 분석이 끝나야 함(fault tolerance) |
| Security | no | 입력·권한 경계 변화 없음 |
| Maintainability | yes | Point 속성 접근 재발을 자동 검사로 막음(modifiability) |
| Flexibility | no | 설치·이식 경로 변화 없음 |
| Safety | no | 물리적 위해 경로 없음 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| QC1 | Compatibility / interoperability | Retrofit endpoint 외 Android 노드·edge와 Python·NestJS 출력은 base와 같음 | RE1: 3개 fixture JSON 차이 파일 수(Retrofit id 대응 후) / 개 | = 0 | review RE1 | 사용자 승인 범위(F3만 id 변경) |
| QC2 | Compatibility / co-existence | tree-sitter 0.25.2에서도 NestJS 열 회귀 테스트 통과 | RE3: 실패 테스트 수 / 개 | = 0 | review RE3 | requirements.txt `tree-sitter>=0.24,<0.27` |
| QR1 | Reliability / fault tolerance | 실제 저장소 apowerb·ailh·lastwave 분석 | RE2: rc 0 저장소 수 / 개 | = 3 | review RE2 | I1–I3 |
| QM1 | Maintainability / modifiability | `tests/` 밖 저장소 Python 코드에 Point 속성 접근이 다시 들어옴 | V5 자동 검사가 위반 파일·줄을 보고하고 실패 / 감지 여부 | 위반 주입 시 실패 | automated V5, mutation | F4 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | F1; C1–C6 | Python 그래프 빌더 결과 노드의 `docstring` | integration(언어 그래프 빌더 public API, tmp 저장소) | equivalence partitioning | P1 함수 일반(C1), P2 함수 개행+들여쓰기(C2), P3 class 개행+들여쓰기(C3), P4 module 공백(C4), P5 빈 줄 뒤 글(C5), P6 docstring 없음(C6) | 100% | 기대 문자열 또는 `None`; 예외 없음 | automated |
| V2 | F1, I1; C2 | CLI `-f fastapi`와 함수 docstring `"""\n    """`를 가진 tmp 저장소 | end-to-end(CLI 하위 프로세스) | equivalence partitioning | E1 공백 docstring 포함 저장소 | 100% | rc 0, HTML·`--bottlenecks` JSON 생성 | automated |
| V3 | F2, I2; C7–C9 | NestJSAnalyzer 결과 진단 span, endpoint·application 식별자와 declaration span | integration, 하위 프로세스에서 분석기 실행(크래시가 테스트 프로세스를 죽이지 않게) | boundary value analysis(3-value, 경계 256: CPython 작은 int 캐시 상한) | B1 진단 start_col 255, B2 256, B3 257, B4 약 1000, B5 진단 end_col > 256, B6 endpoint 식별자 col ≥ 257, B7 application 식별자 col ≥ 257, B8 endpoint declaration span start_col·end_col(decorator 시작 ≥ 257), B9 application declaration span start_col·end_col(call 시작 ≥ 257) | 100% | 하위 프로세스 rc 0, 각 값이 fixture 문자열에서 계산한 독립 기대 열과 같음 | automated; RE3 |
| V4 | F3, I3; C10–C12b | AndroidAnalyzer 결과 `RetrofitEndpointInfo.id`, CLI | integration(분석기) + end-to-end(C11 CLI `-f android --bottlenecks`) | equivalence partitioning | R1 단일 interface(C10), R2 다른 파일 같은 이름(C11 분석기), R3 C11 CLI rc 0, R4 오버로드(C12), R5 HTTP annotation이 `fun` 윗줄에 있을 때 line은 annotation 줄(C12b) | 100% | 기대 id 문자열(fixture 경로·줄에서 독립 계산), id 중복 0, CLI rc 0 | automated |
| V5 | F4, QM1; C13 | git 추적 Python 파일(`tests/` 제외) 소스 텍스트 | unit(정적 검사 테스트) | experience-based (error guessing) | G1 `start_point.column`, G2 `end_point.column`, G3 `start_point.row`, G4 `end_point.row` | none — experience-based | 위반 0이면 통과, 위반 시 파일·줄을 메시지에 담아 실패 | automated, mutation |
| V6 | F5 | 두 golden 파일 | unit(파일 내용 검사) 또는 review | equivalence partitioning | J1 예전 형식 id(`retrofit_<Interface>_<method>`) 0개, J2 새 형식 id 존재, J3 Retrofit id 외 바이트 차이 0(`git diff`에서 바뀐 줄이 모두 Retrofit id 줄) | 100% | 기대 조건 성립 | automated(J1, J2), review(J3: main이 `git diff --word-diff` 확인) |
| V7 | QC1 | fixture 3개 base 비교 | end-to-end review | equivalence partitioning | K1 fastapi-realworld, K2 android-nowinandroid, K3 typescript-nestjs-realworld | 100% | 차이 0 | review RE1 |
| V8 | QR1 | 실제 저장소 3곳 | end-to-end review | equivalence partitioning | X1 apowerb, X2 ailh, X3 lastwave | 100% | rc 0 | review RE2 |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| A1 | Retrofit endpoint id를 `retrofit_{module}_{interface}_{method}_{line}`로 바꾸고 예전 id 호환 매핑은 두지 않는다 | 기존 id는 실제로 충돌해 분석이 거부됨; Room `query_` id가 같은 형식 | user answer |
| A2 | 세 버그를 spec 하나로 묶는다 | 같은 목표(크래시 없이 완료), 같은 검증 경로 | user answer |
| A3 | 버그 2는 Point 인덱스 접근(`[0]`/`[1]`)으로 고치고 requirements 범위는 유지한다 | tree-sitter 0.26.0에서 `.row`/`.column` 결과 int refcount가 깨짐(재현: 열 400 노드 `.column` 반복 후 `sys.getrefcount` 비정상·SIGSEGV), `[1]`은 정상, 0.24.0·0.25.2는 정상 | user answer |
| A4 | golden 두 파일은 전체 재생성 대신 Retrofit endpoint id만 치환한다 | 두 golden을 쓰는 characterization 테스트 5개가 base_commit부터 무관한 drift로 실패(이전 run 기록과 동일). 전체 재생성은 무관한 drift를 함께 승인하게 됨 | brief v1 — approved |
| A5 | Test command에서 base 실패 characterization 5개와 `test_nestjs_quality` O11을 제외하고, `test_report_modal` centres_node·`test_report_size_format` V01 실패는 병렬 부하 flake로 보고 단독 재실행으로 판정한다 | base 전체 실행 12 failed 중 5개만 결정적; 나머지는 단독 2회 통과, 이전 run 기록에도 flake로 남음. O11은 base worktree(.fixtures symlink)에서도 같은 subtest 6개 실패 | brief v1 — approved; O11 추가 brief v2 — approved |
| A6 | RE2 실제 저장소 실행은 VM 대신 로컬 scratchpad clone에서 한다 | handoff 기록 최대 RSS 0.19–1.2GB, ailh는 이미 로컬에서 2.4초로 재현. ADR은 대형·병렬 작업 대상 | brief v1 — approved |
| A7 | 회귀 fixture는 외부 저장소 코드를 복사하지 않고 합성한다 | 외부 저장소 라이선스 미확인; 합성 fixture(생성자 매개변수 31개 한 줄)로 base에서 rc 138/139 재현 확인 | brief v1 — approved |
| A8 | 테스트 기법·coverage 목표: 기능은 equivalence partitioning 100%, 열 경계는 3-value BVA 100%, 정적 검사는 error guessing | 결함이 입력 분류(docstring 형태, id 충돌 형태)와 수치 경계(256)에 있음 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F1 | C1–C6 | V1, V2 | automated, fuzz |
| F2 | C7–C9 | V3 | automated, RE3 |
| F3 | C10–C12b | V4 | automated |
| F4 | C13 | V5 | automated, mutation |
| F5 | — | V6 | automated, review |
| QC1 | — | V7 | RE1 |
| QC2 | C7–C9 | V3 | RE3 |
| QR1 | — | V8 | RE2 |
| QM1 | C13 | V5 | mutation |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 1 |
| verifier invocations | 2 |
| open finding ids | none (advisory A1, A2, A4, A5, A6) |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V1 | 3 | tests/test_analyzer_crash_regressions.py test_V1_docstring_partitions[P1..P6]; fuzz 3000/0 | accepted | verifier 1 accept(A1 advisory). hand M1–M3 killed; fuzz 3000/0 | Implementation·tests/test_analyzer_crash_regressions.py 변경 시 재검토 |
| V2 | 3 | tests/test_analyzer_crash_regressions.py test_V2_E1_cli_fastapi_with_whitespace_docstring | accepted | verifier 1 accept | Implementation·tests/test_analyzer_crash_regressions.py 변경 시 재검토 |
| V3 | 3 | tests/test_analyzer_crash_regressions.py test_V3_* B1–B9 (correction 1: B8 test_V3_B8_endpoint_declaration_span_is_the_decorator, B9 test_V3_B9_application_declaration_span_is_the_create_call; start_col 전용 테스트 제거); RE3 0.25.2 V3+V4 18 passed | accepted | verifier 2 accept; hand M4–M8, M11 killed | Implementation·tests/test_analyzer_crash_regressions.py 변경 시 재검토 |
| V4 | 3 | tests/test_analyzer_crash_regressions.py test_V4_R1..R5 (R5 test_V4_R5_annotation_on_line_above_fun_uses_annotation_line) | accepted | verifier 2 accept; hand M9, M10, M13 killed | Implementation·tests/test_analyzer_crash_regressions.py 변경 시 재검토 |
| V5 | 3 | tests/test_analyzer_crash_regressions.py test_V5_* (G1–G4) | accepted | verifier 1 accept(A4 advisory). hand M8 killed by V5 scan | Implementation·tests/test_analyzer_crash_regressions.py 변경 시 재검토 |
| V6 | 3 | tests/test_analyzer_crash_regressions.py test_V6_J1/J2; J3 review: `git diff --word-diff=porcelain` 바뀐 단어 74개 모두 Retrofit id, android V01 실패 diff에 retrofit 차이 0 | accepted | verifier 1 accept. hand M12 killed by J2 | Implementation·tests/test_analyzer_crash_regressions.py 변경 시 재검토 |
| V7 | 3 | RE1: 3 fixture base/cur `--json --bottlenecks` 비교, 차이는 출력 파일명 `details_file`뿐, HTML·details 동일 (nowinandroid에 Retrofit endpoint 없음) | accepted | verifier 1 accept(A5 advisory) | Implementation·tests/test_analyzer_crash_regressions.py 변경 시 재검토 |
| V8 | 3 | RE2: apowerb rc0 41.9s 2.10GB, ailh rc0 7.6s 0.51GB, lastwave rc0 28.5s 2.57GB (macOS `time -l`) | accepted | verifier 1 accept | Implementation·tests/test_analyzer_crash_regressions.py 변경 시 재검토 |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 0 | ailh `-f nestjs` SIGSEGV | handoff 가설: tree 해제 후 Node 접근 | 로컬 재현 후 ddmin으로 2파일 최소화, diagnostics 값 출력 → `start_col` 객체가 다른 객체로 바뀜; `.column` 반복 접근 probe로 refcount 이상 확인 | 가설 기각(verified). 원인: tree-sitter 0.26.0 Point 속성 접근 결함 |
| 1 | Test command 7 failed: O11 subtest 6개 + centres_node flake | O11은 base 기존 실패(verified: base worktree 같은 6개) | Test command v2에 O11 deselect(사용자 승인) | 재실행 2 failed(centres_node card/connection), 단독 3 passed → A5 flake |
| 2 | verifier 1: S1 declaration span end_col 미검증 | spec이 declaration span 노드를 정의하지 않음(verified: M11 생존) | spec v3 B8·B9, R5 추가 후 test-implementer correction batch 1 | 35 passed; hand 13개 모두 killed(M11은 B8·B9, M13은 R5) |
| 5 | verifier 2 pass; Test command 재실행 2 failed(centres_node card/connection, A5 명시 flake), V07 통과 | A6: V07은 A5 목록 밖 flake(advisory) | 없음 | complete |
| 4 | Test command(v3) 2 failed: centres_node[connection], test_analysis_coverage_browser V07 KPI medians | 병렬 부하 시간 측정 flake(hypothesis); 변경 코드와 무관한 report 브라우저 테스트 | 단독 재실행 | 4 passed → A5 절차로 flake 판정 |
| 3 | mutation tool 30개 중 생존 1: android/analyzer.py:494 `or "?"`→`"?X"` | triager insufficient context → main: 이름 없는 interface는 endpoint를 만들지 않음(실행 확인), fallback은 base부터 존재 | 없음 | equivalent(main 확인), 생존율 3.3% |

# Version Log
## v1
- 초기 작성. handoff `agent-docs/handoff/69f373c97118f02d-analyzer-crashes-on-post-cutoff-repos.md`와 main 재현 결과 반영.
## v2
- Test command에 `test_nestjs_quality` O11 deselect 추가(A5 확장). 근거: base_commit worktree에서 같은 subtest 6개(fastapi-futuramaapi, fastapi-realworld, fastapi-template, python, typescript, sqlalchemy) 실패 확인. 사용자 승인.
## v3
- [contract] verifier 1 S1: declaration span 노드를 기존 동작대로 명시(endpoint=decorator, application=call_expression)하고 V3에 B8·B9 추가. 근거: hand mutation M11(declaration end_col=start_col)이 v2 테스트에서 생존.
- [contract] verifier 1 A3: Retrofit id line을 annotation 포함 function_declaration 시작 줄로 명시(base `ka.start_line(method)`·Room `query_`와 같은 기준), V4에 R5/C12b 추가.
