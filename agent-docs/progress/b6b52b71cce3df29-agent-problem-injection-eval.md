---
session: 011c7b90-abc9-4536-ae24-1068deddade2
before: none
previous: none
branch: eval
commit: 95a617ddd4dbfcbaa05a2bacd74b141d59764477
---

# Fault-injection eval weighted toward AI-agent problems

## Next Session

### State
- Project definition in AGENTS.md now covers structure, code quality, security, and correctness candidates; `bottlenecks/handout.py:109` still prints "Candidates are structural facts to review, not verdicts." and was left unchanged because only structural candidate kinds exist so far.
  - commit: 12da674; files: AGENTS.md, bottlenecks/handout.py
- Scoring catalog: 74 types (52 agent-reported, weight 3; 22 general, weight 1), 68 injectable, total injectable weight 160. Regenerate with `python3 scripts/eval/defects/build_catalog.py`.
  - commit: 12da674; files: scripts/eval/defects/build_catalog.py, scripts/eval/defects/catalog.json, scripts/eval/defects/agent-reported.md
- Delta comparison (`bottlenecks/delta.py`, policy delta.v1) covers only new_cycles, grown_cycles, new_violations, new_package_dependencies, instability_changes; other candidate kinds have no baseline comparison.
  - commit: 12da674; files: bottlenecks/delta.py

### Next Step
- Extend delta comparison to every candidate kind, matching cycles by member superset and other kinds by kind + target path + metrics (candidate ids hash node ids, so ids change on rename and growth).
  - commit: 12da674; files: bottlenecks/delta.py, bottlenecks/core.py, code_analyzer/cli.py
- Then build the injection harness (script-chosen and Sonnet-chosen locations, reported separately) and run the CTFd pilot locally; then start improvement with duplicate/clone detection (P16).
  - commit: 12da674; files: scripts/eval/measure.py, scripts/eval/gate.py

### Constraints
- "프로젝트 정의를 바꾼다. (대안) agent 문제로 보고된 적 없더라도 발생가는한 케이스는 넣는다. 단, agent 문제로 보고된 문제들은 3배의 가중치를 받는다."
  - source: user message in session 011c7b90
- "분석기는 이제 local에서 돌려야 함 (크레딧 다 떨어짐) - pilot만 돌리고, 본격적인 run은 잘 때 돌리는 것으로"
  - source: user message in session 011c7b90
- "이 프로젝트에 맞는 eval을 택하는 게 아니라 AI agent를 사용함으로서 생기는 문제를 얼마나 잘 잡아내는 지를 기준으로 삼는 게 맞아. 그리고 그걸 목표로 개선해야해"
  - source: user message in session 011c7b90

### Verify
- `python3 scripts/eval/defects/build_catalog.py` regenerates catalog.json without diff.
  - commit: 12da674; files: scripts/eval/defects/catalog.json

### Dead Ends
- none: no implementation attempt has failed yet in this session

### Related
- agent-docs/todos/stale/e16d433ef30afd87-oss-report-refactoring-eval.md (earlier OSS eval dropped for lack of a validation dataset; saturation numbers on large cycles)
  - commit: 12da674; files: agent-docs/todos/stale/e16d433ef30afd87-oss-report-refactoring-eval.md

## Record

### Changes
- AGENTS.md: project definition rewritten per the user's choice of the broader scope.
- scripts/eval/defects/agent-reported.md: catalog of 52 problem types reported for AI-written code, compiled by an Opus subagent without analyzer knowledge, with source verification status.
- scripts/eval/defects/build_catalog.py, catalog.json: weighted scoring denominator.

### Commands
- `python3 scripts/eval/defects/build_catalog.py`

### Failed Attempts
| attempt | failure evidence | cause |
|---|---|---|
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
