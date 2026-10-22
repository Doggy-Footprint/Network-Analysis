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
- (이번 세션) "oss-report-refactoring-eval handoff에 따라 테스트를 진행하려는데, 다른 handoff 보다 먼저 해도 될까?" → "커밋하고 진행하자".
- "분석기는 나중에 천천히 돌려도 되니까 서브 에이전트 병렬로 실행하자. 평가 대상에서 git remote 등으로 체크 못하게 해줘. 나한테 pid 알려줘"
- 실험 루트 이동(`mv`)은 사용자가 실행 직전에 중단시켰다. 이후 run 폴더만 저장소 밖에 두는 방식으로 바꿨다.
- "다른 handoff랑 그 무거운 것부터 어떻게 해결을 해야겠네.. -> 핸들오프 추가 / 핸드오프 정리해서 다른 핸드오프, 그리고 LLM 에게 제공할 보고서 경량화 과정을 거치게 하고 기존 데이터는 싹 폐기해 그냥." → 폐기 범위 질문에 "./eval 전부 폐기".

## State

- 브랜치 `test/modal-sum-ranking`. **평가 대상 분석기 commit은 `0224570`으로 고정한다**(선행 작업 3개 완료; 이후 commit은 테스트·문서 정리뿐). 이전 기록: HEAD `a8a3012` 시점에 `scripts/eval/` 최초 커밋은 `5ddd426`, run 격리 초안(`repos.json`의 `github`·`commit`, `prepare_runs.py`, `run_hook.py`, `TASK_PROMPT.md`)은 `abd1df2`, 리포트 경량화는 `3373b36`에 커밋했다. 작업 트리는 깨끗하다.
- **`./eval`은 사용자 지시로 전부 삭제했다.** 삭제한 것: clone, 테스트 환경(`envs`, `node`, `.venv`), 기준선(`test-baseline.json`), 분석기 리포트, 파일럿 결과, raw transcript. `~/toy-projects/network-analysis-eval/`은 만들지 않았다. 아무 run도 실행하지 않았다.
- 선행 작업(이 실험보다 먼저 한다. Next Step 0):
  - `85aa37516a23897d-report-size-for-llm.md`: LLM용 리포트 경량화. vendure `bottlenecks.json`이 684MB이고 `json.load`에 RSS 5GB가 필요하다. 병렬 run이 불가능한 크기다.
    - 완료(spec `agent-docs/spec-logs/ee17484a52af182c-report-size-for-llm.md` v4, complete; handoff는 `stale/`). file granularity `bottlenecks.json`은 `bottlenecks.v9`(evidence_spread는 details edge index, 순환·unstable은 `file_ids` index 행), `report.json`은 schema "7" compact이고 details는 `<stem>.details.json`으로 분리, `--bottlenecks`이면 `<stem>.handout.md`가 생긴다. 실측: vendure bottlenecks 684→77MB, json.load RSS 3.8GB→0.68GB, handout 70KB; 나머지 6개 bottlenecks 1.2~14.2MB, handout 28~58KB. 실험군에는 handout을 1차 자료로 주고 `prepare_runs.py`의 `REPORT_FILES`에 details 파일과 handout을 추가해야 한다.
  - `b6db876d7191e86d-gradle-module-package-scheme.md`: 완료(spec `agent-docs/spec-logs/09e1bf05d439475e-build-module-packages.md` v6, complete; handoff는 `stale/`). `build` 체계(`pkg:gradle:<path>`, `pkg:npm:<name>`)와 `DECLARES_DEPENDENCY` relation이 추가되고 `structure_policy`가 `structure.v2`가 됐다. 실험군 `{report_section}`에 build 체계 설명을 넣어야 한다. R1 실측(GCP `na-eval`): nowinandroid build 36 package·DECLARES exact 106·package_cycle 5(Gradle은 선언 순환 불가라 코드 edge 기원 추정), vendure build 19 package·DECLARES exact 42.
  - `fa00b92fe9819b57-agent-context-candidates.md`: 완료(handoff는 `stale/`).
    - C(시그니처 기준 2-hop 맥락 비용)는 구현하지 않고 종료했다(spec `agent-docs/spec-logs/5b0e19017d8b5a79-signature-context-cost.md` v2 aborted). `hop_2_token_cost`와 순위가 거의 같았다(Spearman symbol 0.95–0.99, file 0.87–1.00).
    - D(문서→코드 참조)는 완료했다(spec `agent-docs/spec-logs/64deae051d59caac-doc-code-references.md` v6 complete, commit `0224570`). file granularity의 details 파일에 `doc_references` 표, bottleneck JSON에 `dangling_doc_reference` candidate(문서당 1개)와 `coverage.doc_references`가 생기고 `versions.analysis`가 "7"이 됐다. 그래프와 기존 지표는 바뀌지 않는다. 실험군 `{report_section}`에 이 candidate 설명을 넣어야 한다.
    - R1 실측(GCP `na-eval`): 시간·RSS 증가 없음. nowinandroid는 dangling 8건(문서 3개), vendure는 dangling 56건(문서 32개, 튜토리얼 예시 경로 오탐 포함)과 site_route 2405건이다.
  - 선행 작업 3개가 끝났다. 분석기 commit `0224570`으로 리포트를 새로 만든다.
- **실행 위치는 GCP다(사용자 결정: "추천안으로 한다 (gcp, f9)").** 무거운 작업인 분석기 R1과 eval 실험(14 run 병렬)을 GCP VM에서 돌린다. 코드 수정과 subagent 작업은 로컬 맥에서 한다.
  - VM: `na-eval`, project `playground-472408`(billing "My Billing Account" 연결, Compute API 활성), zone `asia-northeast3-a`, `n2-highmem-16`(16 vCPU, 125GB RAM; 사용자 요청으로 `e2-highmem-8`에서 상향), Ubuntu 24.04, 디스크 200GB(사용 6GB), 외부 IP 34.64.165.101(임시). 상태 RUNNING이다. 사용자가 요청할 때만 중지하고, 삭제는 사용자가 명시할 때만 한다.
  - 접속: 로컬 `gcloud`(계정 khs1903b@gmail.com, 기본 project 설정이 없는 `autonomous-agent-00001`이므로 항상 `--project playground-472408 --zone asia-northeast3-a`를 붙인다). `gcloud compute ssh na-eval ... --command '...'`, `gcloud compute scp`. zsh에서 플래그를 변수에 담으면 분리되지 않으니 직접 쓴다.
  - VM에 있는 것: `~/venv`(Python 3.12.3, 분석기 requirements), `~/nowinandroid`, `~/vendure`(eval 고정 commit, depth 1), `~/r1.sh`·`~/r1d.sh`(base·cur 분석기 비교 스크립트), 이전 R1 산출물 `~/out`, `~/dout`, `~/dbase`, `~/dcur`(지워도 됨). 분석기는 `git archive`/tar로 올려 `.venv`를 `~/venv` symlink로 두고 실행했다.
  - VM에 없는 것: node, Java/JDK, Android SDK, uv, Claude Code(`claude`). eval run은 VM 안에서 `claude -p`를 실행하므로 **Claude Code 설치와 인증(API key 또는 로그인)은 사용자가 직접 해야 한다.** Android gate용 Linux JDK 21·Android SDK, Python용 uv, Node 22·bun도 새로 설치해야 한다.
  - 아래 Next Step의 경로·명령은 macOS 로컬 기준으로 쓰였다. VM으로 옮길 때 바꿔야 할 것:
    - `~/toy-projects/network-analysis-eval/` → VM 홈 아래 실험 루트(이 저장소 사본은 VM에 없음; 분석기 commit `0224570`을 tar로 올리거나 VM에서 clone).
    - `cp -c`(APFS clonefile) → `cp -a` 또는 `cp --reflink=auto`.
    - 기준선 표의 환경(homebrew Python, Android Studio JBR의 `JAVA_HOME`, `local.properties`의 `sdk.dir`) → Linux 경로.
    - `run_hook.py`·settings의 deny 경로(`/private/tmp/claude-501`, `~/.claude`) → VM의 Claude Code 경로.
    - 샌드박스(`sandbox.enabled`, `failIfUnavailable`)는 Linux에서 bubblewrap 기반이므로 VM에 설치·동작을 먼저 확인한다.
- 대상 저장소와 고정 commit(별 1k+, 소스 150~3000 파일). `scripts/eval/repos.json`에 `github`와 `commit`으로 기록했다.

  | cell | repo | commit |
  |---|---|---|
  | python/fastapi | mealie-recipes/mealie | 204bffd468c8601a911310c15cb1e303eb0a0347 |
  | python/fastapi | lnbits/lnbits | 04b37f0d761222561bc8606cfe7edc86cabcce35 |
  | python/sqlalchemy | CTFd/CTFd | d21c9cd3bb154e0e285aba2a20e176777b5f7d5d |
  | python/sqlalchemy | pallets-eco/flask-admin | 4f8be4580b082c6047492baa801f3f08642c9a75 |
  | typescript/nestjs | ghostfolio/ghostfolio | eaa4c3e6efc84298a20e5fdbe1116f67798b0d70 |
  | typescript/nestjs | vendurehq/vendure | 99bdc303cddcef64e52077b082ff5e6a562c95f2 |
  | kotlin/android | android/nowinandroid | 2982e63cb691ad49cd009aab43dc206fee6699c2 |
  | kotlin/android | bitwarden/android | 6d08ab550eb69efda46b9cd4616a63aedf71ccb7 (분석기 실패 → 제외) |

- 삭제 전 테스트 gate 기준선. 환경을 다시 만들 때의 기대값이다. 모두 사전 실패 0이었다.

  | repo | 환경 | 명령(clone 루트에서) | passed |
  |---|---|---|---|
  | mealie | Python 3.14(homebrew) venv, `uv export --frozen --group dev --no-emit-project` | `<venv>/bin/python -m pytest -n auto --dist loadfile -p no:cacheprovider` | 3583(skip 18) |
  | lnbits | uv Python 3.12 venv(editable 설치였음) | `rm -rf tests/data && env -u LNBITS_DATABASE_URL LNBITS_DATA_FOLDER=./tests/data LNBITS_BACKEND_WALLET_CLASS=FakeWallet PYTHONUNBUFFERED=1 DEBUG=true <venv>/bin/python -m pytest tests/unit tests/api tests/wallets -q --no-cov` | 2423(skip 20) |
  | CTFd | uv 관리 CPython 3.11.11, uv.lock 전체 그룹 | `env AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY TESTING_DATABASE_URL='sqlite://' <venv>/bin/python -m pytest -c setup.cfg --rootdir=. -p no:randomly -p no:sugar -p no:cacheprovider -q -rfE --ignore-glob='**/node_modules/' -W ignore::sqlalchemy.exc.SADeprecationWarning -W ignore::sqlalchemy.exc.SAWarning -n 8 tests` (AWS 값은 upstream CI의 더미) | 725 |
  | flask-admin | uv Python 3.12.9 venv, uv.lock group `tests` + extra `all`(editable 설치였음) | `<venv>/bin/python -m pytest -p no:cacheprovider -q -rsx --ignore=flask_admin/tests/geoa --ignore=flask_admin/tests/mongoengine --ignore=flask_admin/tests/pymongo --ignore=flask_admin/tests/sqla/test_postgres.py --ignore=flask_admin/tests/fileadmin/test_fileadmin_azure.py` | 391(skip 83, xfail 13) |
  | ghostfolio | 시스템 node, `npm` 설치 node_modules | `NX_DAEMON=false NX_NO_CLOUD=true CI=true npx dotenv-cli -e .env.example -- npx nx run-many --target=test --projects=api,common --parallel=1 --skip-nx-cache --outputStyle=stream` + `npx tsc --noEmit -p apps/api/tsconfig.app.json`, `npx tsc --noEmit -p apps/api/tsconfig.spec.json` | 710 |
  | vendure | Node 22.23.4 + bun 1.3.10 로컬 다운로드, `bun install`, `packages/common` 빌드(`lib/`) | `cd packages/core && npx vitest --config vitest.config.mts --run --typecheck --hookTimeout=60000` + `cd packages/core && npx tsc -p ./build/tsconfig.build.json --noEmit` | 1753 |
  | nowinandroid | Android Studio JBR(JDK 21), `local.properties`의 `sdk.dir` | `rm -rf */build/test-results */*/build/test-results && JAVA_HOME=".../jbr/Contents/Home" ./gradlew --no-build-cache testDemoDebugUnitTest :core:common:test :lint:test -Proborazzi.test.verify=false --continue` | 173 |
  | bitwarden | 위와 같음, `:app`/`:authenticator` 제외(GitHub Packages 토큰 필요) | `./gradlew --no-build-cache --continue :core:testDebugUnitTest :network:testDebugUnitTest :cxf:testStandardDebugUnitTest :cxf:testFdroidDebugUnitTest :authenticatorbridge:testDebugUnitTest :testharness:testDebugUnitTest :data:testDebugUnitTest :ui:testDebugUnitTest` | 911 |

  주의점(삭제 전 확인):
  - CTFd는 바깥 `pytest.ini`를 집어오므로 `-c setup.cfg --rootdir=.`가 필수다.
  - lnbits는 `test_notification_for_internal_payment`가 네트워크 의존 flaky이고 인터넷이 필요하며, 단일 파일 실행이 안 된다.
  - mealie는 warning을 error로 취급한다.
  - ghostfolio는 nx 출력 줄에 `api: ` 접두사가 붙는다(`gate.py`에서 처리).
  - Gradle은 `--no-build-cache`와 test-results 삭제가 있어야 재실행이 보장된다.
  - CTFd venv는 interpreter가 환경 폴더 안에 있었다. 환경 폴더를 옮기면 `pyvenv.cfg`와 `bin/python` 링크가 깨진다.
- `scripts/eval/`:
  - 측정·판정(파일럿용, 경로가 `ROOT/eval`과 `eval/repos/<repo>` 단일 clone으로 하드코딩됨. run별 clone 경로 인자로 바꿔야 함):
    - `measure.py <repo> <label> --rev`: git archive 스냅샷, 분석기, lizard, 독립 import 그래프(Python grimp / TS dependency-cruiser 18.7.0 / Kotlin 자체 regex 해석기), 분석기-독립그래프 agreement.
    - `compare.py`: 전후 비교(touched files 기준 + 전역).
    - `gate.py`: 테스트 gate와 통과 수 비교.
    - `judge.py`: 사전 예측 지표 대비 판정. 방향성 예측 적중 + 전역 가드 무악화일 때만 improved.
    - `verify.sh`, `collect_agents.py`.
    - `FINDER_PROMPT.md`, `REFACTOR_PROMPT.md`: 파일럿용(분리 구조). `TASK_PROMPT.md`로 대체 예정이라 지워도 된다.
  - run 격리(커밋됨, 미실행):
    - `prepare_runs.py`: `~/toy-projects/network-analysis-eval/runs/<arm>-<n>/<repo>/`에 run을 만든다.
      - clone: remote 없이 URL로 고정 sha를 `fetch --depth 1`해서 `base` 브랜치를 만들고, `FETCH_HEAD`와 reflog를 지운다.
      - seed 복사: ghostfolio `node_modules`, vendure `node_modules`·`packages/*/node_modules`·`packages/common/lib`, nowinandroid `local.properties`를 `cp -c`로 넣는다. seed 원본이던 `eval/repos`가 삭제됐으므로 seed 원천을 새로 정해야 한다.
      - gate wrapper `<run>/gate`: 공유 slot 2개, Gradle slot 1개(mkdir lock), RAM free+inactive ≥ 2GB 대기, Python은 `PYTHONPATH=<clone>`, Gradle은 끝나고 `--stop`.
      - 실험군에는 리포트 3개를 `report/`로 복사한다. 경량화 후 형식에 맞게 고쳐야 한다.
      - `run.json`에 arm, base, 분석기 commit을 기록한다.
    - `run_hook.py <run_dir>`: PreToolUse에서 다음을 deny한다.
      - git 원격 조회(`remote`, `fetch`, `pull`, `push`, `ls-remote`, `clone`, `submodule`), `gh`, `github.com` 등.
      - `../..`와 `.claude`가 들어간 명령.
      - 이 저장소(`eval/envs`, `eval/node`, `eval/.venv` 제외), 다른 run, `~/.claude`, `/private/tmp/claude-501` 경로.
      - `points.json` 재작성과 Edit.
    - `TASK_PROMPT.md`: 단일 에이전트 공통 프롬프트(gate on base → `points.json` 1회 선언 → 포인트별 `eval/pN` 구현·gate·커밋 → `result.json`). `{report_section}`(실험군 리포트 설명)은 아직 작성 전이다. `prepare_runs.py`에 settings 생성, 프롬프트 렌더, launcher도 아직 없다.

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
| 실험 루트를 `~/toy-projects/network-analysis-eval/`로 `mv` | 사용자가 실행을 중단했다(이유는 말하지 않음). 앞서 파일럿 nx daemon(`eval/repos/ghostfolio`) `kill`은 auto mode classifier가 거부했다 | verified: 사용자 중단. 이후 `./eval`을 통째로 폐기했으므로 이동할 대상이 없다 |
| 실험군 리포트를 key별·candidate별 JSONL로 분할해서 제공 | vendure `bottlenecks.json` 684MB(`candidates` 699MB), `json.load` RSS 5.07GB | verified: 리포트 직렬화 크기 문제. 분할하지 않고 경량화(`85aa37516a23897d`)를 먼저 하기로 사용자가 결정 |

## Next Step

0. (완료) 선행 작업 3개를 끝내고 분석기 commit `0224570`을 평가 대상으로 고정했다.
1. 실험 루트를 GCP VM `na-eval`에 새로 만든다(State의 "실행 위치" 참고; 이 저장소 CLAUDE.md/AGENTS.md 오염 방지를 위해 분석기 사본과 분리). 먼저 사용자에게 VM의 Claude Code 설치·인증을 요청한다.
   - `envs`(저장소별 테스트 환경), `node`(dependency-cruiser 18.7.0, typescript 5.9.3), `.venv`(lizard, grimp), seed(node_modules, local.properties)를 다시 만든다.
   - 저장소별 gate를 2회 돌려 State의 기준선 표와 통과 수가 같은지 확인하고 `test-baseline.json`을 다시 쓴다.
   - `scripts/eval/*`의 `ROOT/eval` 하드코딩을 `EVAL_ROOT`와 run별 clone 경로 인자로 바꾼다. `run_hook.py`의 `ROOT_ALLOWED`와 `prepare_runs.py`의 경로도 함께 바꾼다.
2. 고정 분석기로 저장소별 before 리포트를 만든다(`measure.py`). 분석기는 병렬 run과 겹치지 않게 따로 천천히 돌려도 된다(사용자 지시).
3. `prepare_runs.py`를 마저 작성한다.
   - 실험군 `{report_section}`: 경량화된 출력의 candidate kind, rankings, `package_metrics`, `candidate_groups`, edge의 relation·confidence·resolution·weight를 저장소별 실제 값으로 설명한다.
   - run별 settings: `sandbox.enabled`, `failIfUnavailable: true`, `allowUnsandboxedCommands: false`, `network.allowedDomains` 비움(원격 조회를 OS 수준에서 차단), `filesystem.denyRead`(이 저장소의 환경 폴더 외, 다른 run, `~/.claude`, `/private/tmp/claude-501`), `denyWrite`(`gate`, `report/`, `run.json`, `gates/`).
   - gate만 `excludedCommands`와 `Bash(<run>/gate)` allow로 샌드박스 밖에서 실행한다(테스트가 네트워크와 `~/.gradle` 쓰기를 쓴다). 남는 구멍: gate가 실행하는 테스트 코드는 에이전트가 고칠 수 있다.
   - Read/Edit permission은 `//abs/**` 형식으로 쓴다. Edit/Write allow는 `<run>/clone/**`와 `<run>/points.json`, `<run>/result.json`만 둔다.
   - `env`: `BASH_DEFAULT_TIMEOUT_MS=600000`, `BASH_MAX_TIMEOUT_MS=5400000`.
   - hook: `python3 <repo>/scripts/eval/run_hook.py <run>`.
   - launcher(병렬, 사용자 지시): run 폴더를 cwd로 둔다. `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 nohup claude -p "<TASK>" --model sonnet --effort medium --permission-mode dontAsk --setting-sources project --strict-mcp-config --settings <run>/settings.json --disallowedTools WebFetch WebSearch Agent --output-format stream-json --verbose --include-hook-events > stream.jsonl`. PID를 `pid` 파일과 사용자 보고에 남긴다(사용자 지시).
4. 시험 run 1개(flask-admin, gate 약 20초)로 확인할 것:
   - hook이 `--setting-sources project`에서도 로드되는가(stream의 hook event).
   - 금지 경로 Read/`cat`, `git remote -v`, `curl https://github.com`, `points.json` 재작성이 막히는가.
   - gate가 통과하는가.
5. 저장소 7개 × (실험 1 + 대조 1) = 14 run을 병렬로 띄우고 PID를 보고한다.
   - 끝나면 run별로 `verify.sh`(clone 경로 기반으로 수정 후)를 돌리고, stream-json 원본과 토큰을 `results/raw/<run>/`에 보관한다.
   - 실험군·대조군 비교표를 만든다: 판정, 예측 적중, 회귀, 토큰, 대조군 포인트 중 리포트 후보 파일의 비율.
6. 결과를 사용자에게 보고하고 추가 run(3+3)과 opus 진행 여부를 결정받는다.

## Open Questions

- 대조군의 독립 지표 도구(lizard, measure.py) 사용 허용 여부. 이번 설계의 기본값은 양 군 모두 불허이고, 지표 정의만 프롬프트로 준다.
- bitwarden 분석기 규모 문제(경량화 후 재시도할지, 계속 제외할지).
- 파일럿에서 관찰된 리포트 결함을 제품 작업으로 넘길지:
  - TS: 루트 `tsconfig.json`만 읽고 `tsconfig.base.json` path alias 미해석(`language_analyzers/typescript/analyzer.py:184`, ghostfolio import recall 0.224).
  - DECORATES edge가 정의 파일 → 사용 파일 방향이라 가짜 순환이 생김.
  - ambiguous CALLS로 fan-in이 40~120배 부풀려짐.
  - `hop_2_token_cost` 포화.
  - JSON, 설정, 테스트 파일이 production 순위와 large_node에 섞임.
  - 같은 순환이 tier별로 중복 보고됨(경량화 handoff에서 일부 다룸).
  - `unresolved_count` 0인 unresolved_boundary.
  - 함수 복잡도 신호 없음.
- 파일럿 독립 지표 baseline(Execution Ledger)은 원본 데이터가 삭제됐다. 새 분석기로 다시 잰다.

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

- 파일럿 토큰(폐기 데이터, 참고용; 원본 파일은 `./eval`과 함께 삭제됨):
  - 찾기 에이전트, 저장소당: output 1.7만~3.5만, 캐시 포함 210만~450만.
  - 리팩토링 21개 합: output 13.7만, 캐시 포함 1401만.
- fuzz, mutation: 해당 없음. correction 및 verifier 카운터: 해당 없음(workflow-approach 미사용).
