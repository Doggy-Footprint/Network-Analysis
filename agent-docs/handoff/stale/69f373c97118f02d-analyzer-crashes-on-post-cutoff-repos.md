# 컷오프 이후 OSS 저장소에서 드러난 분석기 크래시 3건

## User Query

> 좋아. 지금까지 PR하고, 브랜치 바꿔서 handoff 만들어

후속: "커밋해서 푸시하고, fix 브랜치로 넘어가자", "새로운 세션에서 작업을 이어갈건데, 그에 필요한 정보를 handoff에 다 정리했어?", "VM은 ADR에 올려줘. cpu/memory intensive한 작업은 cloud에서 수행한다.고" → 초안 확인 후 "응 그대로 써줘"

맥락: eval handoff(`agent-docs/handoff/stale/e16d433ef30afd87-oss-report-refactoring-eval.md`)의 마지막 시도에서 후보 저장소 5개에 분석기 `0224570`을 돌렸고, 3개가 아래 버그로 실패했다. 사용자는 eval을 포기했고("일단 정지하고, eval handoff는 검증에 필요한 데이터 셋을 확보하지 못해서 포기라고 적어줘"), 버그가 우리 것인지 물은 뒤 이 handoff를 요청했다. 수정은 아직 지시받지 않았다.

## State

- 브랜치 `fix/analyzer-crashes`(로컬 전용, push 안 함). `test/modal-sum-ranking`은 PR #6(https://github.com/Doggy-Footprint/Network-Analysis/pull/6)으로 `master`에 merge됐다(`c34d6f4`). 이 브랜치는 `97387af`에서 갈라져 handoff 커밋 뒤 `master`를 merge했고(`927e7a6`), 그 위에 ADR `agent-docs/adr/a89462012bf595dd-cloud-for-heavy-workloads.md`(+ index, handoff 보완) 커밋이 있다. 분석기 코드는 바꾸지 않았다. `origin`은 저장소 이전에 맞춰 `https://github.com/Doggy-Footprint/Network-Analysis.git`으로 바꿨다.
- 사용자는 이 브랜치로 넘어와 수정 작업을 이어가려 한다. "workflow-approach로 spec부터 만들어 진행할까요?"라는 질문에는 아직 답을 받지 않았다.
- 재현 입력은 GCP VM `na-eval`(project `playground-472408`, zone `asia-northeast3-a`, `n2-standard-16` = 16 vCPU/64GB, 사용자 지정 사양, TERMINATED)의 `~/eval-b/repos/<name>`에 있다(depth 1 clone, 아래 commit). 분석기 사본은 VM `~/pin`(`0224570`, `.venv` 포함). VM은 쓸 때만 켜고 끝나면 끈다(사용자 지시, ADR `agent-docs/adr/a89462012bf595dd-cloud-for-heavy-workloads.md`).
  - 로컬 `gcloud` 기본 project가 다르므로 항상 `--project playground-472408 --zone asia-northeast3-a`를 붙인다. 켜기 `gcloud compute instances start na-eval ...`, 끄기 `... stop ...`, 접속 `gcloud compute ssh na-eval ... --command '...'`. 부팅 직후 수십 초는 ssh가 `Connection refused`를 낸다.
  - 재현: `cd ~/pin && .venv/bin/python -m code_analyzer.cli ~/eval-b/repos/<name> <명령> -o /tmp/<name>.html --bottlenecks /tmp/<name>.json`. segfault 위치는 `python -X faulthandler`로 얻었다.
  - 수정한 코드를 VM에서 돌리려면 로컬에서 `git archive`로 tar를 만들어 `gcloud compute scp`로 올리고, 풀어 둔 폴더에 `.venv`를 `~/venv` symlink로 둔다(eval 때 `~/pin`을 만든 방식). 작은 진단 스크립트는 `PYTHONPATH=~/pin`이 있어야 `bottlenecks` 등을 import한다.

  | name | repo | commit | 명령 | 결과 |
  |---|---|---|---|---|
  | apowerb | apowerb/apowerb | 04e4f1fd061c6b4b8568cf519ec537a736afadb9 | `-f fastapi -f sqlalchemy` | 버그 1 |
  | ailh | 7nvv8hyfbn-eng/AI-Learning-Hub | 1dba04fac18c3702d9d7610f1a888b25e26afec6 | `-f nestjs` | 버그 2 |
  | lastwave | Clash-Projects/LastWave-Native | 3eaf19f9b218ad0d86c84c803e2c209fdbb027e9 | `-f android` | 버그 3 |

- 버그 1 (verified): `language_analyzers/python/graph.py:366` `(symbol.docstring or "").strip().splitlines()[0]`은 공백·개행뿐인 docstring에서 `IndexError`를 낸다. 같은 패턴이 `:341`(module docstring)에도 있다. 분석 전체가 rc 1로 끝난다.
- 버그 2 (위치 verified, 원인 hypothesis): `framework_analyzers/nestjs/analyzer.py:393` `_modules` → `:337` `_resolve`의 `_diagnostic`(unresolved/ambiguous reference) → `:43` `_text` → `language_analyzers/typescript/ast.py:51` `node_text`의 `node.start_byte`에서 SIGSEGV(rc 139, `python -X faulthandler`로 확인). 가설: `expression` 노드의 tree가 해제된 뒤 접근한다(tree-sitter Python binding에서 Node가 Tree 수명을 붙잡지 않는 사용 방식). 어떤 파일·노드인지는 특정하지 않았다.
- 버그 3 (verified): `framework_analyzers/android/analyzer.py:506` Retrofit endpoint id가 `retrofit_<interface>_<method>`이고 `module`이 없다(`module_placeholder`는 선언만 되고 쓰이지 않는다). 다른 Android id는 `{module}`을 넣는다(예: `:190` `api_{module}_{name}`). `module`은 `_module_for`(`:122`)가 주는 프로젝트 기준 상대 파일 경로다. lastwave에서는 저장소 안 앱 사본 `reference zip/extracted/LastWave/...`의 같은 `LastFmApiService.get/post`와 충돌해 `bottlenecks/core.py` `_validate_structure`가 `architecture node ids are invalid`로 거부했다. 진단은 `_validate_structure`를 감싸 중복 id를 출력하는 일회성 스크립트로 했다(저장하지 않음).
- 미확인: 예전 eval 후보 Tusky·wikimedia/apps-android-wikipedia도 같은 메시지로 실패했다. 버그 3과 같은 원인인지 보지 않았다.

## Failed Attempts

| attempt | failure evidence | cause |
|---|---|---|
| 없음(수정 시도 전) | — | — |
| 버그 2 가설(tree 해제 후 Node 접근) 확인 | 로컬 재현을 ailh 2파일로 최소화; 크래시 위치가 `_routes`·diagnostics 정렬 등으로 바뀌고 `SourceSpan.start_col` 객체가 다른 객체로 바뀌어 있음; tree-sitter 0.26.0에서 `.column` 반복 접근 뒤 refcount 비정상, `[1]`·0.24.0·0.25.2는 정상 | 가설 기각(verified). 원인은 tree-sitter 0.26.0 Point 속성 접근 결함. 수정·검증은 spec `agent-docs/spec-logs/3974b0fa12e686e6-analyzer-crashes.md` |

## Next Step

1. 사용자에게 workflow-approach로 진행할지 확인한다. 동작이 바뀌는 수정이라 그 대상이다. 세 버그를 spec 하나로 묶을지, 버그마다 따로 만들지도 함께 묻는다.
2. 버그 1: 첫 비어 있지 않은 줄을 쓰거나 없으면 `None`. `:341`, `:366` 둘 다. 공백 docstring fixture로 회귀 테스트.
3. 버그 3: endpoint id에 `module`을 넣는다(`retrofit_{module}_{name}_{method}`). 같은 interface 이름이 두 파일에 있는 fixture로 회귀 테스트. id가 바뀌므로 골든·report 영향 확인.
4. 버그 2: VM에서 ailh로 재현해 실패 파일·노드를 특정하고, 최소 fixture를 만든 뒤 tree 수명 가설을 확인한다. 가설이 맞으면 `NestJS` 분석기가 노드를 쓰는 동안 해당 tree(또는 파일 객체)를 유지하게 고친다.
5. 고친 뒤 VM에서 세 저장소를 다시 돌려 끝까지 도는지 확인하고, 시간이 되면 Tusky·wikipedia도 돌린다.

## Open Questions

- 버그 3 수정으로 Android 노드 id가 바뀐다. 기존 report·골든의 id 호환이 필요한가.
- 저장소 안에 앱 사본이 있는 경우(lastwave `reference zip/`)를 분석 대상에서 빼는 정책이 필요한가, 아니면 id 충돌만 고치면 되는가.

## Spec

없음. 아직 workflow-approach spec을 만들지 않았다.

## Execution Ledger

- 분석기 실행(VM, `0224570`, 2026-10-23): apowerb 0:16 rc 1 RSS 0.77GB; ailh 0:09 SIGSEGV RSS 0.19GB; lastwave 0:33 rc 1 RSS 1.2GB. 같은 배치에서 성공: stevezau/shortlist 1:06 RSS 1.6GB, kienpt012/dashboard 0:08.
- fuzz, mutation, correction 및 verifier 카운터: 해당 없음.
