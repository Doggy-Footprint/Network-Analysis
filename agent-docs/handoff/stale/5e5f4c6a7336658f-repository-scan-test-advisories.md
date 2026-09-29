# repository 스냅샷 공통층 테스트 보강 제안

## Goal
"커밋하고 제안 받은 거 handoff로" — 워크플로 3dfc6bf47f6a3947 완료 후 test-verifier가 남긴 비블로킹 제안을 이어서 처리한다.

## State
- branch: polish
- commit: 이 handoff와 함께 커밋된 "refactor: 스냅샷 모델·스캔을 repository/ 공통층으로 분리" 커밋
- 관련 파일: repository/scan.py, repository/policy.py, tests/test_repository_scan.py

## Failed Attempts
| attempt | failure evidence | cause |
|---|---|---|
| 뮤테이션 스크립트를 zsh에서 `$TC` 변수로 실행 | pytest 출력이 전혀 없음 | zsh는 변수를 단어 분리하지 않음 (verified) — bash 스크립트로 실행해야 함 |
| 뮤테이션 실행에 `timeout` 사용 | 명령이 실행되지 않음 | macOS에 `timeout` 명령 없음 (verified) |

## Next Step
1. 미실행 뮤테이션을 `python3 .harness/bin/seed.py backup/restore`로 하나씩 주입하고 Test command로 검출 여부 확인:
   - too_large 비교 `>` → `>=` (기대 검출: VO-5 B1)
   - NUL 창 8192 → 8191/8193 (VO-5 B3)
   - 경로의 `./` 정규화 제거 (VO-6 N1)
   - explicit_output을 문자열 접두사 매칭으로 변경, `outside/x` 오인 (VO-6 O4)
2. 생존한 뮤테이션이 있으면 해당 테스트 보강.
3. 선택: git 출력이 비어있지 않고 returncode 0이며 walk 결과와 다른 목록일 때 "git-tracked"를 고정하는 subprocess 수준 테스트 추가(현재는 `_git_tracked_files` mock으로만 커버).

## Open Questions
- FR-2의 `version: true`(파이썬상 == 1) 허용 여부 — 범위 밖으로 미정.
- `list_repository_files` walk에서 중첩 `sub/node_modules` 같은 하위 디렉터리 제외 여부를 명세할지.
- R6 analyzer_artifact의 65536자 창, schema_version "1"/"4" 음성 사례, "do not edit" 표식을 테스트할지.

## Spec
agent-docs/spec-logs/3dfc6bf47f6a3947-repository-snapshot-layer.md, version 4, status complete, run ID 3dfc6bf47f6a3947.

## Execution Ledger
- verifier 1: retry (F-1 spec challenge → FR-8/VO-11, F-2 L2a, F-3 SC2, F-4 diff 제공) — 모두 해결.
- verifier 2: pass, finding 0. 위 Next Step 항목은 advisory.
- 뮤테이션 M1~M6 실행, 최종 6/6 검출 (M3는 보강 전 생존).
- correction batches 3, verifier invocations 2/2.

## Resolution
- 미실행 뮤테이션 5종(too_large `>=`, NUL 창 8191/8193, `./` 정규화 제거, explicit_output 문자열 접두사) 모두 검출 — 테스트 보강 불필요.
- 항목 1(git-tracked 분기 subprocess 테스트): 실제 git 저장소 테스트가 이미 커버하므로 추가하지 않음(사용자 결정).
- 항목 2(`version: true`): 정책 파일은 저장소가 직접 관리하므로 현실적 위험 없음, 다루지 않음(사용자 결정).
- 항목 3(중첩 디렉터리 제외): spec 59af3fa02a94cdfd로 명세·테스트 추가, complete.
- 항목 4(analyzer_artifact 경계): 범위 밖, agent-docs/issues/71544b671815742f-analyzer-artifact-marker-untested-edges.md에 무효화 조건과 함께 기록.
