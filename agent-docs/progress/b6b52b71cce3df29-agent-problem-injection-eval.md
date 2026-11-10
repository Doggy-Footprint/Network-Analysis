---
session: 011c7b90-abc9-4536-ae24-1068deddade2
before: none
previous: none
branch: eval
commit: 476ca06328799bb4b76d8c61ec8f7e597b18257e
---

# Fault-injection eval weighted toward AI-agent problems

## Next Session

### State
- Project definition in AGENTS.md now covers structure, code quality, security, and correctness candidates; `bottlenecks/handout.py:109` still prints "Candidates are structural facts to review, not verdicts." and was left unchanged because only structural candidate kinds exist so far.
  - commit: 9ea723b; files: AGENTS.md, bottlenecks/handout.py
- Scoring catalog: 74 types (52 agent-reported, weight 3; 22 general, weight 1), 68 injectable, total injectable weight 160. Regenerate with `python3 scripts/eval/defects/build_catalog.py`.
  - commit: 9ea723b; files: scripts/eval/defects/build_catalog.py, scripts/eval/defects/catalog.json, scripts/eval/defects/agent-reported.md
- Delta comparison is `delta.v2`: besides the five v1 lists it reports `new_candidates`, `strengthened_candidates`, `resolved.candidates` for every non-cycle, non-violation kind (unknown kinds included). Spec run 2afad1e5c96b32ff closed with verifier pass.
  - commit: 6fe7133; files: bottlenecks/delta.py, code_analyzer/cli.py, agent-docs/spec-logs/2afad1e5c96b32ff-delta-all-candidate-kinds.md
- Known false positive: file renames are not tracked, so a renamed file's candidates appear as resolved (old path) plus new (new path). The eval must measure this rate with the rename negative control (NC1) and report it next to recall.
  - commit: 6fe7133; files: bottlenecks/delta.py, tests/test_delta_candidates.py
- The Python analyzer records an unresolved reference only for calls aimed at project code (attribute of an imported project module, name imported from a project module). A call to an unbound bare name (`missing_fn()`) is classified as external and yields no `unresolved_boundary`; observed on fastapi-realworld with 25 such calls. This affects the agent problem "reference to non-existent internal symbol" (P02).
  - commit: 9ea723b; files: language_analyzers/python/graph.py
- At base 9ea723b the full suite has pre-existing failures: 5 characterization tests (12 node ids) and 2 flaky tests (report_modal V04 under parallel load; report_size_format V01 depending on in-process order). The spec Test command deselects them.
  - commit: 9ea723b; files: tests/test_doc_references.py, tests/test_file_analysis_cli.py, tests/test_nestjs_quality.py, tests/test_analysis_coverage_reporting.py, tests/test_signal_defects_round4.py, tests/test_report_modal.py, tests/test_report_size_format.py

- Injection harness `scripts/eval/inject/harness.py` (subcommands baseline, run, score). Workspace `~/toy-projects/network-analysis-eval/inject/<repo>/` holds clone (pinned commit, no remote), env/venv (test env), base/bottlenecks.json, runs/<task>/ (prompt, diff.patch, delta.json, result.json), score.json; `inject/tools` holds ruff 0.8.4, bandit 1.8.0, pylint 3.3.3. Test commands and scopes are in `REPOS`. The earlier `eval/repos` clones and envs no longer exist.
  - commit: f47b0fd; files: scripts/eval/inject/harness.py, scripts/eval/inject/INJECT_PROMPT.md, scripts/eval/inject/NEGATIVE_PROMPT.md
- Per task: Sonnet (`claude -p --restricted`, file tools only, cwd = per-task git worktree) injects; NC1 rename and NC2 format are scripted because file tools cannot delete files (Sonnet renames left the old file, judged invalid). Validity = non-empty diff, primary file touched (script method), py_compile, Sonnet judge on the diff (not for scripted controls), test gate (serialized per process). Catch = Sonnet match judge on anonymized findings (`matched`); `located` = analyzer delta item naming a touched file or its `pkg:python:` package, or a tool finding on an added line. Tools: ruff ALL, bandit, pylint on touched files, new = count increase per (tool, rule, path, message).
  - commit: f47b0fd; files: scripts/eval/inject/harness.py
- CTFd pilot (16 types x 2 methods, 1 replicate, 2 per control): 34 valid of 40. Weighted type recall matched: script analyzer 0.031, ruff 0.50, pylint 0.53, any tool 0.53; sonnet analyzer 0.125, ruff 0.40, pylint 0.35, any tool 0.425. Analyzer-only catches: package cycle, unstable dependency, layer violation (G01, G02, P21). Caught by no finder: hallucinated package, duplicated code, hard-coded credential, XSS, dependency declaration smell, shotgun surgery (P05, P16, P32, P34, P38, G09). Controls: analyzer located false positive 2/2 on rename only (known), 0 on format, comments, refactor; ruff flags format/comment/refactor controls on added lines. Script-chosen locations were judged invalid for G02, G09, P21 (structural types do not fit an arbitrary file). Results in `~/toy-projects/network-analysis-eval/inject/CTFd/score.json`.
  - commit: 6fe7133; files: none
- In G01-script-0 the injected admin <-> utils.challenges import pair is inside the existing large package SCC, so delta reports no new or grown cycle (only new package dependencies and an unstable_dependency candidate).
  - commit: 6fe7133; files: bottlenecks/delta.py
- Harness covers CTFd, flask-admin (Python), ghostfolio (TypeScript, Node 22 at `inject/node`, scope apps/api and libs/common), nowinandroid (Kotlin, androidTest excluded). Gates run in `inject/<repo>/gate` (persistent checkout, dependencies installed there): flask-admin 391 passed (median 43 s), ghostfolio 710 passed plus two tsc checks (median 93 s), nowinandroid 173 passed (median 67 s), CTFd median 137 s. Comparison tools: Python ruff/bandit/pylint/semgrep, TypeScript eslint 9.17 (@eslint/js + typescript-eslint recommended and stylistic)/semgrep, Kotlin detekt 1.23.7/semgrep; semgrep uses the pinned `inject/tools/semgrep-default.yml`.
  - commit: f47b0fd; files: scripts/eval/inject/harness.py, scripts/eval/inject/overnight.sh
- Mini pilot (P02, P10, G01, one of each control) on the three new repos: in ghostfolio and nowinandroid both P02 injections fail the test gate with compile errors (TS2304, Kotlin Unresolved reference), so P02 has no valid injection in compiled languages. Analyzer control false positives: ghostfolio format-only (prettier width 60) strengthened large_node through line_count; nowinandroid comment-only (KDoc with [Name] links in WorkManagerSyncManager.kt) produced a new package dependency sync.status -> core.analytics and an unstable_dependency candidate; renames in every repo (known).
  - commit: f47b0fd; files: bottlenecks/delta.py
- Judge is skipped for scripted controls (rename, format): it rejected a Kotlin rename because the file name no longer matched the class and a format change because a `# type: ignore` moved lines.
  - commit: f47b0fd; files: scripts/eval/inject/harness.py

- Memory guard: before each gate the harness waits until `kern.memorystatus_level` (system-wide free-memory percent) is at least 25, and at least 15 before Sonnet calls and analyzer runs (gives up after 2 h and logs it); gate starts across processes are spaced 60 s apart through `inject/gate-start.lock`; nowinandroid gates end with `./gradlew --stop`. Samples every 60 s and waits go to `inject/<repo>/memory.log`; each gate result carries memory before/after; score.json has a memory summary. A nowinandroid gate check ran with level 38 -> 42 and left no Gradle 9.7.1 daemon.
  - commit: 476ca06; files: scripts/eval/inject/harness.py

### Next Step
- User starts the overnight run as two parallel streams: `scripts/eval/inject/overnight.sh "CTFd flask-admin" & scripts/eval/inject/overnight.sh "ghostfolio nowinandroid" & wait` (all injectable types, both methods, 4 per control; resumable); then read each `inject/<repo>/score.txt` and start improvement with the uncaught weight-3 types (P16 duplication first) and the analyzer false positives on format and comment controls.
  - commit: f47b0fd; files: scripts/eval/inject/overnight.sh, scripts/eval/inject/harness.py

### Constraints
- "프로젝트 정의를 바꾼다. (대안) agent 문제로 보고된 적 없더라도 발생가는한 케이스는 넣는다. 단, agent 문제로 보고된 문제들은 3배의 가중치를 받는다."
  - source: user message in session 011c7b90
- "분석기는 이제 local에서 돌려야 함 (크레딧 다 떨어짐) - pilot만 돌리고, 본격적인 run은 잘 때 돌리는 것으로"
  - source: user message in session 011c7b90
- "이 프로젝트에 맞는 eval을 택하는 게 아니라 AI agent를 사용함으로서 생기는 문제를 얼마나 잘 잡아내는 지를 기준으로 삼는 게 맞아. 그리고 그걸 목표로 개선해야해"
  - source: user message in session 011c7b90

### Verify
- `python3 scripts/eval/defects/build_catalog.py` regenerates catalog.json without diff.
  - commit: 9ea723b; files: scripts/eval/defects/catalog.json
- The Test command line in the archived spec (pytest-cov, deselects) passes: 3811 passed, delta.py branch 99%.
  - commit: 6fe7133; files: agent-docs/spec-logs/2afad1e5c96b32ff-delta-all-candidate-kinds.md

### Dead Ends
- `coverage run -m pytest` collects no data in this repo because pytest.ini adds `-n auto`; use pytest-cov.
  - commit: 9ea723b; files: pytest.ini

### Related
- agent-docs/todos/stale/e16d433ef30afd87-oss-report-refactoring-eval.md (earlier OSS eval dropped for lack of a validation dataset; saturation numbers on large cycles)
  - commit: 12da674; files: agent-docs/todos/stale/e16d433ef30afd87-oss-report-refactoring-eval.md
- agent-docs/spec-logs/2afad1e5c96b32ff-delta-all-candidate-kinds.md (delta.v2 contract, strength-metric table, rename false positive)
  - commit: 6fe7133; files: agent-docs/spec-logs/2afad1e5c96b32ff-delta-all-candidate-kinds.md

## Record

### Changes
- AGENTS.md: project definition rewritten per the user's choice of the broader scope.
- scripts/eval/defects/agent-reported.md: catalog of 52 problem types reported for AI-written code, compiled by an Opus subagent without analyzer knowledge, with source verification status.
- scripts/eval/defects/build_catalog.py, catalog.json: weighted scoring denominator.
- scripts/eval/inject/: injection harness and prompts.
- bottlenecks/delta.py, code_analyzer/cli.py: delta.v2 (spec 2afad1e5c96b32ff); tests/test_delta_candidates.py and support; existing delta tests adjusted within the spec range (tests/delta_candidates_evidence/existing-tests.diff).

### Commands
- `python3 scripts/eval/defects/build_catalog.py`
- `uv venv .venv --python 3.12 && uv pip install -p .venv -r requirements.txt` (analyzer env used by the harness)
- `.venv/bin/python scripts/eval/inject/harness.py run CTFd --types <ids> --negatives 2 --workers 3`; `... score CTFd`

### Failed Attempts
| attempt | failure evidence | cause |
|---|---|---|
| `coverage run` around pytest for delta.py coverage | "No data was collected" with 3807 tests run | verified: xdist workers (`-n auto` in pytest.ini) are outside coverage run |
| V05 injection with bare undefined calls | no unresolved_boundary in delta; details show no unresolved_references on the new function | verified: `_is_boundary_call` treats unbound bare names as external |
| Defect list derived from the analyzer's candidate kinds (18 observable of 39) | user rejected it: the eval must measure AI-agent problems, not fit the tool | verified |

### Sources
- agent-reported.md section 6 lists every source with status; re-checks found ContextCov (arXiv:2603.00822) does not report wrong-layer placement, and no source reports agent-caused migration drift or DI/router registration errors.

### User Requests

#### 1 — 2026-11-10T04:39:05Z

> 이 프로젝트의 성능을 검증하기 위해 결함을 주입해서 테스트 셋을 만들어보려고 해. 
> 
> - sonnet-medium
> - knowledge-cutoff 이후 신설되거나, 많이 수정된 open source를 대상으로
> - 결함은 1. 일반적인 소프트웨어 bad practice / ai agent를 사용할 때 발생하는 것으로 보고된 종류 (opus-medium sub agent이용하여 list-up)
> - 점수는 주입한 결함 중 몇 개나 찾아내는지. (기존에 있는 결함의 경우 대상에서 제외.
> 
> 
> ---
> 
> 이 방식의 eval 이 적절한지 평가해줘

#### 2 — 2026-11-10T04:47:27Z

> sonnet은 주입만 하는 쪽이야.

#### 3 — 2026-11-10T04:51:06Z

> 1. 권장안
> 2. 스크립트 / Sonnet 둘 다 해봐야겠는데?
> 3. 권장안 대로
> 4. 분석기는 이제 local에서 돌려야 함 (크레딧 다 떨어짐)

#### 4 — 2026-11-10T04:51:43Z

> 1. 권장안
> 2. 스크립트 / Sonnet 둘 다 해봐야겠는데?
> 3. 권장안 대로
> 4. 분석기는 이제 local에서 돌려야 함 (크레딧 다 떨어짐) - pilot만 돌리고, 본격적인 run은 잘 때 돌리는 것으로

#### 5 — 2026-11-10T06:00:03Z

> 기대 결과는?

#### 6 — 2026-11-10T06:04:51Z

> 이 프로젝트에 맞는 eval을 택하는 게 아니라 AI agent를 사용함으로서 생기는 문제를 얼마나 잘 잡아내는 지를 기준으로 삼는 게 맞아. 그리고 그걸 목표로 개선해야해

#### 7 — 2026-11-10T06:08:21Z

> 이 프로젝트에 맞는 eval을 택하는 게 아니라 AI agent를 사용함으로서 생기는 문제를 얼마나 잘 잡아내는 지를 기준으로 삼는 게 맞아. 그리고 그걸 목표로 개선해야해

#### 8 — 2026-11-10T07:06:45Z

> 프로젝트 정의를 바꾼다. (대안)
> agent 문제로 보고된 적 없더라도 발생가는한 케이스는 넣는다. 단, agent 문제로 보고된 문제들은 3배의 가중치를 받는다.
> 
> 진행 순서: 기본값 수용.

#### 9 — 2026-11-10T07:16:54Z

> 둘 다 권장으로 가야겠네. 2에 오탐이 있을 것이고 그걸 음성대조에서 보는 점은 확실히 적어놔.

#### 10 — 2026-11-10T07:35:56Z

> 승인

#### 11 — 2026-11-10T07:39:30Z

> <task-notification>
> <task-id>bn8kbdk2r</task-id>
> <tool-use-id>toolu_0112YgSBd6QPrWQtL2wMQgv7</tool-use-id>
> <output-file>/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-eval/011c7b90-abc9-4536-ae24-1068deddade2/tasks/bn8kbdk2r.output</output-file>
> <status>completed</status>
> <summary>Background command "Produce a real file-granularity bottleneck JSON for fuzzing" completed (exit code 0)</summary>
> </task-notification>

#### 12 — 2026-11-10T07:46:40Z

> <task-notification>
> <task-id>bm84b4izb</task-id>
> <tool-use-id>toolu_01LNnhDhSkiHgqHDniuk3C1G</tool-use-id>
> <output-file>/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-eval/011c7b90-abc9-4536-ae24-1068deddade2/tasks/bm84b4izb.output</output-file>
> <status>completed</status>
> <summary>Background command "Run the spec Test command with coverage" completed (exit code 0)</summary>
> </task-notification>

#### 13 — 2026-11-10T08:21:34Z

> 확인했어. 넘어가도 좋아.

#### 14 — 2026-11-10T08:36:07Z

> <task-notification>
> <task-id>bat8gobrz</task-id>
> <tool-use-id>toolu_01MzKPpmm7B5nj889ZHSyziN</tool-use-id>
> <output-file>/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-eval/011c7b90-abc9-4536-ae24-1068deddade2/tasks/bat8gobrz.output</output-file>
> <status>completed</status>
> <summary>Background command "Smoke-test harness on one type, both methods" completed (exit code 0)</summary>
> </task-notification>

#### 15 — 2026-11-10T09:46:00Z

> <task-notification>
> <task-id>byo1janw0</task-id>
> <tool-use-id>toolu_01RzQXsuXmkeJFArRcyxUFBL</tool-use-id>
> <output-file>/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-eval/011c7b90-abc9-4536-ae24-1068deddade2/tasks/byo1janw0.output</output-file>
> <status>completed</status>
> <summary>Background command "Run CTFd pilot (16 types × 2 methods + 8 controls)" completed (exit code 0)</summary>
> </task-notification>

#### 16 — 2026-11-10T09:53:12Z

> <task-notification>
> <task-id>bbbxwi15w</task-id>
> <tool-use-id>toolu_01WSSuzuU7DXqHJjWWNYjfYA</tool-use-id>
> <output-file>/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-eval/011c7b90-abc9-4536-ae24-1068deddade2/tasks/bbbxwi15w.output</output-file>
> <status>completed</status>
> <summary>Background command "Rerun rename controls, rescore, score" completed (exit code 0)</summary>
> </task-notification>

#### 17 — 2026-11-10T10:19:08Z

> 중간에 이동해야해서 인터넷이 끊어졌을텐데 괜찮아?

#### 18 — 2026-11-10T11:40:19Z

> 파일럿으로 보여진 결과는 어때?

#### 19 — 2026-11-10T11:41:43Z

> 본 실험에는 다른 언어도 포함돼?

#### 20 — 2026-11-10T11:42:17Z

> 언어 확장 작업 시작해

#### 21 — 2026-11-10T11:45:44Z

> <task-notification>
> <task-id>bl5vjtg2n</task-id>
> <tool-use-id>toolu_01GxRe9ZJt24pPDreQy2PssM</tool-use-id>
> <output-file>/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-eval/011c7b90-abc9-4536-ae24-1068deddade2/tasks/bl5vjtg2n.output</output-file>
> <status>completed</status>
> <summary>Background command "Install ghostfolio node_modules with Node 22" completed (exit code 0)</summary>
> </task-notification>

#### 22 — 2026-11-10T11:47:47Z

> <task-notification>
> <task-id>bsd5ope31</task-id>
> <tool-use-id>toolu_014uZArFCuKq18LuyAH4W4T2</tool-use-id>
> <output-file>/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-eval/011c7b90-abc9-4536-ae24-1068deddade2/tasks/bsd5ope31.output</output-file>
> <status>completed</status>
> <summary>Background command "Warm nowinandroid Gradle test run and time it" completed (exit code 0)</summary>
> </task-notification>

#### 23 — 2026-11-10T12:14:05Z

> <task-notification>
> <task-id>br73f1i23</task-id>
> <tool-use-id>toolu_01PYLFSYVyoJ66rA6ePwBmLk</tool-use-id>
> <output-file>/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-eval/011c7b90-abc9-4536-ae24-1068deddade2/tasks/br73f1i23.output</output-file>
> <status>completed</status>
> <summary>Background command "Run mini pilots on three new repos" completed (exit code 0)</summary>
> </task-notification>

#### 24 — 2026-11-10T12:24:07Z

> <task-notification>
> <task-id>b4nlso2ps</task-id>
> <tool-use-id>toolu_01TWjP9TxvGo2cc9YPofvFhn</tool-use-id>
> <output-file>/private/tmp/claude-501/-Users-hwansu-orca-workspaces-network-analysis-eval/011c7b90-abc9-4536-ae24-1068deddade2/tasks/b4nlso2ps.output</output-file>
> <status>completed</status>
> <summary>Background command "Rerun scripted controls and rescore all repos" completed (exit code 0)</summary>
> </task-notification>

#### 25 — 2026-11-10T12:36:37Z

> 돌아갈 때 메모리 체크하면서 돌아가게 작업해줄래?
