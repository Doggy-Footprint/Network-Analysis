# OSS 저장소로 리포트 기반 리팩토링 효과 평가

## User Query

> 커밋하고, 프레임워크 - 언어를 2 축으로 해서 여러 open source (github 별 최소 1k 이상, 사이즈 어느 수준 이상, --depth 1 clone)를 가져와서 리포트를 가져와서 제대로 나오는지 평가해보자.
> 리포트를 통해 리팩토링 포인트를 서브에이전트에게 각각 찾게 하고, 실제로 진행해서 얼마나 개선되었는지 체크하자.
> 하기 전에 실제로 정량적인 분석 방법부터 셋업. 정량적인 분석을 할 수 없다면 리팩토링은 진행하지 않고 opus-medium으로 직접 분석한 것과 비교하여 평가.

후속 지시(요지, 원문 순서):
- clone한 저장소 등은 `./eval`에 두고 gitignore → 이후 "실험 폴더를 옮기자"로 변경.
- 대조군을 두고, report 포함 실행의 token 소모량과 개선 수치를 기록. agent 실행·결과 raw 데이터를 남기고, 매 실험은 새 `git clone --depth 1`에서 진행.
- 메모리: 분석기 실행 전 남은 메모리를 고려(조금 더 써도 됨).
- 금지 준수는 최대한 rule 기반. 찾기/리팩토링을 한 에이전트에서 처음부터 끝까지("병목 체크, 리팩토링" 구조).
- 지금까지 한 실험은 버림.
- sonnet-medium으로 **실험 1회 + 대조 1회**를 먼저 돌리고, 그 결과로 추가 run 여부와 opus 여부를 결정.
- 리포트를 주는 run에는 리포트가 무엇인지 설명해 줄 것.
- 샌드박스 실행 희망; hook은 샌드박스 보완용.

## State

- 브랜치 `test/modal-sum-ranking`, HEAD `5cbfbc1` (E07 테스트 커밋, 미푸시). 분석기(평가 대상) 버전 = 이 HEAD.
- 미커밋: `.gitignore`(`/eval/` 추가 — 처음엔 `eval/`이라 `scripts/eval/`까지 무시되던 것을 루트 고정으로 수정), `scripts/eval/` 전체(신규), `tests/*_evidence/performance.json` 2개(테스트 실행 부산물, 커밋 제외 대상).
- 실험 루트는 아직 저장소 안 `./eval/`(gitignored). 이동 예정지 `~/toy-projects/network-analysis-eval/`.
  - `eval/repos/<repo>`: 고정 commit의 depth-1 clone(파일럿 브랜치 `eval/p1..p3`이 남아 있음 — 새 실험은 새 clone 사용).
  - `eval/envs/<repo>`: 저장소별 테스트 환경(venv, node, bun). `eval/.venv`: lizard, grimp. `eval/node`: dependency-cruiser 18.7.0, typescript 5.9.3.
  - `eval/results/<repo>/test-baseline.json`: 테스트 gate 기준선(유효). `eval/results/<repo>/before/`: 분석기 리포트(`report.html`, `report.json`, `bottlenecks.json`)와 독립 지표(유효, 재활용 대상). 그 외 `eval/results/*`는 버린 파일럿(`DISCARDED-report-informed-pilot.txt`).
- 대상 저장소와 고정 commit(별 1k+, 소스 150~3000 파일):

  | cell | repo | commit |
  |---|---|---|
  | python/fastapi | mealie-recipes/mealie | 204bffd468c8601a911310c15cb1e303eb0a0347 |
  | python/fastapi | lnbits/lnbits | 04b37f0d761222561bc8606cfe7edc86cabcce35 |
  | python/sqlalchemy | CTFd/CTFd | d21c9cd3bb154e0e285aba2a20e176777b5f7d5d |
  | python/sqlalchemy | pallets-eco/flask-admin | 4f8be4580b082c6047492baa801f3f08642c9a75 |
  | typescript/nestjs | ghostfolio/ghostfolio | eaa4c3e6efc84298a20e5fdbe1116f67798b0d70 |
  | typescript/nestjs | vendurehq/vendure | 99bdc303cddcef64e52077b082ff5e6a562c95f2 |
  | kotlin/android | android/nowinandroid | 2982e63cb691ad49cd009aab43dc206fee6699c2 |
  | kotlin/android | bitwarden/android | 6d08ab550eb69efda46b9cd4616a63aedf71ccb7 (리포트 없음 → 이번 실험 제외) |

- 테스트 gate(8개 모두 실행 가능, 사전 실패 0): 정확한 명령은 각 `test-baseline.json`. 주의점:
  - CTFd: 바깥 `pytest.ini`를 집어오므로 `-c setup.cfg --rootdir=.` 필수(실험 폴더를 저장소 밖으로 옮기는 이유 중 하나).
  - lnbits: `rm -rf tests/data` 선행 필수, 단일 파일 실행 불가, `test_notification_for_internal_payment`는 네트워크 flaky. 인터넷 필요.
  - mealie: warning을 error로 취급.
  - flask-admin, lnbits venv는 원래 clone을 editable로 가리킴 → 새 clone에서는 `PYTHONPATH=<clone>` 필요(미검증).
  - ghostfolio: nx 출력 줄에 `api: ` 접두사(gate.py에서 처리됨), api typecheck 2개 포함.
  - vendure: Node 22.23.4(`eval/envs/vendure`), `--hookTimeout=60000`, packages/common 수정 시 재빌드, core typecheck 포함. 새 clone은 `node_modules`를 `cp -c`로 복제하거나 `bun install` 재실행 필요.
  - nowinandroid, bitwarden: `local.properties`(untracked) 필요, `--no-build-cache` + test-results 삭제로 재실행 보장, 새 clone은 전체 재컴파일. bitwarden은 `:app`/`:authenticator` 제외(GitHub Packages 토큰 필요) — bitwarden 기준선 에이전트의 마지막 종료 알림은 사용자가 잔여 작업을 끈 것이며 기준선(911 passed)은 유효.
- `scripts/eval/`:
  - `repos.json`: 저장소와 분석기 플래그.
  - `measure.py <repo> <label> --rev`: git archive 스냅샷, 분석기, lizard, 독립 import 그래프(Python grimp / TS dependency-cruiser / Kotlin 자체 regex 해석기), 분석기-독립그래프 agreement.
  - `compare.py`: 전후 비교(touched files 기준 + 전역).
  - `gate.py <repo> --cwd`: 테스트 gate와 통과 수 비교.
  - `judge.py`: 사전 예측 지표 대비 판정. 방향성 예측 적중 + 전역 가드 무악화일 때만 improved.
  - `verify.sh`: gate, measure, compare, judge 일괄.
  - `collect_agents.py`: transcript 보관과 토큰 집계.
  - `FINDER_PROMPT.md`, `REFACTOR_PROMPT.md`: 파일럿용(분리 구조), 새 설계에 맞게 교체 필요.
  - 경로가 `ROOT/eval`로 하드코딩됨 → `EVAL_ROOT` 환경변수와 clone 경로 인자로 바꿔야 함.

## Failed Attempts

| attempt | failure evidence | cause |
|---|---|---|
| 파일럿: 찾기 서브에이전트 1 + 리팩토링 서브에이전트 3(포인트별), 저장소 7개, opus 세션 기본 effort, 같은 clone 재사용, 1회 | 사용자가 결과 폐기 지시(21개 중 improved 16, mixed 4, not_improved 1이었으나 비교 불가) | verified(설계): end-to-end가 아니고, clone 재사용, run 1회, 대조군 없음. 서브에이전트가 이 프로젝트 CLAUDE.md/AGENTS.md를 상속해 지시가 오염됨 |
| bitwarden 분석기 1차(`-f android`, 2579 kt) | 4027초 후 rc -9, 로그 비어 있음, 당시 swap 10.9/11GB | hypothesis: 메모리 압박으로 OS가 kill |
| bitwarden 분석기 2차(`/usr/bin/time -l`) | 45분, RSS 약 3GB 시점에 사용자 지시로 중단 | 미완료(원인 미확정) |
| gate.py ghostfolio 집계 | 710 통과인데 passed=0 | verified: nx 출력 접두사 `api: `. 정규식 수정 완료 |
| Kotlin 독립 해석기 | `NiaApp.kt` fan-out 변화 미검출 | verified: `fun Foo<T>.bar` 제네릭 수신 확장 함수 미인식. 정규식 수정 완료 |
| judge 판정 | "unchanged" 예측 적중만으로 improved 가능 | verified: 방향성 예측만 인정하도록 수정 완료 |
| finder 예측 지표 지정 | lnbits p3: `max_file_fan_out`이 touched 전체 최대(app.py 31)라 logger.py 3→2 미반영. 존재하지 않는 지표명은 None | verified: 프롬프트에 compare 키와 `(file)` 단일 파일 표기를 정확히 제시해야 함. 크기는 판정에 반영되지 않음(방향만) |
| `measure.py --skip-analyzer` | 기존 summary의 analyzer, agreement 소실 | verified: 기존 결과를 유지하도록 수정 완료 |

## Next Step

1. 실험 루트를 `~/toy-projects/network-analysis-eval/`로 이동한다(`envs`, `node`, `.venv`, `results/<repo>/{test-baseline.json,before/}`). `scripts/eval/*`를 `EVAL_ROOT`와 clone 경로 인자 기반으로 수정한다. 이동 후 Python venv(`python -m` 호출), vendure node 경로, `PYTHONPATH` 덮어쓰기를 저장소별 gate 1회로 검증한다.
2. run 단위 격리: run마다 `runs/<treatment|control>-<n>/<repo>/clone`(고정 commit에 새 `git clone --depth 1` + `fetch --depth 1 origin <sha>`)에서 headless `claude -p --model sonnet --effort medium --settings <run별 settings.json> --output-format stream-json`을 실행한다. cwd는 run 폴더로 둔다(이 저장소 CLAUDE.md 오염 방지).
   - settings에 넣을 것: Read/Grep/Glob/Edit/Write deny(실험 결과 루트, 이 저장소, 다른 run, 대조군이면 리포트 경로), Bash 샌드박스 파일 제한(필드명은 문서로 확인), 네트워크는 허용(테스트에 필요).
   - PreToolUse hook: `points.json`은 최초 1회만 Write 허용하고 이후 Write/Edit deny, Bash 명령에 금지 경로 문자열이 있으면 deny.
   - 본 실험 전에 금지 경로 접근이 실제로 막히는지 시험 run 1개로 확인한다.
3. 단일 에이전트 프롬프트(두 군 공통, 리포트 유무만 다름): 병목 확인 → 포인트 3개를 `points.json`에 선언(근거·계획·예측 지표, 예측 지표는 compare 키 목록에서 정확히 선택) → 포인트마다 base에서 `eval/pN` 브랜치 → 구현 → gate → 커밋. 실험군에는 리포트 설명을 포함한다.
   - 설명 대상: `bottlenecks.json`의 candidates kind, `rankings_by_category.production`, `package_metrics`, `candidate_groups`, `report.json` file graph의 relation, confidence, resolution, 크기 경고(JSON 수십 MB, jq/python 질의).
   - 리포트는 `results/<repo>/before/`를 run 폴더 `report/`로 복사하고, 분석기 commit을 함께 기록한다.
4. 저장소 7개 × (실험 1 + 대조 1) = 14 run을 실행한다. 동시 실행 전에 메모리 대기(RAM free+inactive ≥ 2GB, swap free ≥ 1GB), Gradle 동시 1개 + 종료 후 `--stop`. 끝나면 run마다 `verify.sh`, stream-json 원본, 토큰을 `results/raw/<run>/`에 보관하고 실험군·대조군 비교표를 만든다(판정, 예측 적중, 회귀, 토큰, 대조군 포인트의 리포트 후보 파일 비율).
5. 결과를 사용자에게 보고하고 추가 run(3+3)과 opus 진행 여부를 결정받는다.

## Open Questions

- Bash 샌드박스 settings 필드명과, deny 규칙이 headless `-p` run의 Read/Grep에 그대로 적용되는지(문서와 시험 run으로 확인).
- bitwarden 분석기 규모 문제(별도 제품 이슈로 다룰지, 단독 재실행으로 원인 확정할지).
- 파일럿에서 관찰된 리포트 결함을 제품 작업으로 넘길지:
  - TS: 루트 `tsconfig.json`만 읽고 `tsconfig.base.json` path alias 미해석(`language_analyzers/typescript/analyzer.py:184`, ghostfolio import recall 0.224).
  - DECORATES edge가 정의 파일 → 사용 파일 방향이라 가짜 순환이 생김.
  - ambiguous CALLS로 fan-in이 40~120배 부풀려짐.
  - `hop_2_token_cost` 포화.
  - JSON, 설정, 테스트 파일이 production 순위와 large_node에 섞임.
  - 같은 순환이 tier별로 중복 보고됨.
  - `unresolved_count` 0인 unresolved_boundary.
  - 함수 복잡도 신호 없음.
- 대조군의 독립 지표 도구(lizard, measure.py) 사용 허용 여부. 파일럿에서는 실험군 찾기 에이전트에게도 지표 목록을 줬음.

## Spec

없음. 평가 실험이며 workflow-approach spec을 만들지 않았다(`agent-docs/specs/`, `spec-logs/`에 해당 항목 없음).

## Execution Ledger

- 독립 지표 baseline(분석기 대비 독립 import 그래프, 파일럿 측정값):

  | repo | analyzer 시간 | import recall | import precision |
  |---|---|---|---|
  | mealie | 44s | 1.0 | 0.888 |
  | lnbits | 10s | 1.0 | 0.896 |
  | CTFd | 6s | 0.984 | 0.985 |
  | flask-admin | 3s | 1.0 | 0.846 |
  | ghostfolio | 20s | 0.224 | 1.0 |
  | vendure | 146s | 0.999 | 0.999 |
  | nowinandroid | 6s | 0.759 | 0.716(Kotlin 독립 해석기 자체 한계 포함) |
  | bitwarden | 실패 | — | — |

- 파일럿 토큰(폐기 데이터, 참고용):
  - 찾기 에이전트, 저장소당: output 1.7만~3.5만, 캐시 포함 210만~450만.
  - 리팩토링 21개 합: output 13.7만, 캐시 포함 1401만.
  - 원본: `eval/results/raw/report-informed/agents/`, `eval/results/agents-report-informed.json`.
- fuzz, mutation: 해당 없음. correction 및 verifier 카운터: 해당 없음(workflow-approach 미사용).
