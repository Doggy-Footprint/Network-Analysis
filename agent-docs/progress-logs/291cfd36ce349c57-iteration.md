---
session: 4d7b0c3c-66fd-42d7-aa6e-8f8019257d86
before: agent-docs/progress-logs/2e536f4a85267799-pr-push.md
previous: none
branch: dev
commit: a7546777664d2195c7aa370ee9da6ffd4ee4e888
---

# README evaluation section

## Next Session

### State
- README.md has a new `# 평가` section summarizing the injection eval: 74 types (52 agent-reported, weight 3), 4 repos, validity and match judging, first measure (analyzer 27 of 454 valid, any comparison tool 92, rename false positives 15/16), the three improvements, and the current result (91 of 454; 41 of 51 on the 7 types no tool caught at first: P11–P15, P20, P50). Committed on branch dev and sent as a PR dev -> master; the user chose to ignore, for now, that README is read by agents at session start.
  - files: README.md, tests/test_signals_evidence/r1_comparison.md, tests/symbol_changes_evidence/r1_comparison.md, agent-docs/progress-logs/b6b52b71cce3df29-agent-problem-injection-eval.md
- The blog post `~/toy-projects/doggy-portfolio/content/posts/is-my-code-ai-friendly.mdx` was not changed. Its `## Next` lists analysis coverage reporting and equal-share ambiguous candidates, both already complete (spec-logs cfa172d091b48e63, 9c41e725d083ab6f).
  - files: agent-docs/spec-logs/cfa172d091b48e63-analysis-coverage-reporting.md, agent-docs/spec-logs/9c41e725d083ab6f-ambiguous-route-candidates.md

### Next Step
- Merge the dev -> master PR after the user reviews it.
  - files: README.md
- The previous session's open step (push master and close PR #8) is still in agent-docs/progress-logs/2e536f4a85267799-pr-push.md.
  - files: agent-docs/progress-logs/2e536f4a85267799-pr-push.md

### Constraints
- "summary 그대로 둬. 너무 ai 티난다.."
  - source: user message 4 in this session
- "안되겠다. Blog는 건드리지 말고 README에만 추가 내용으로 넣자."
  - source: user message 4 in this session

### Verify
- Recompute the 27/92/91 counts from `~/toy-projects/network-analysis-eval/inject/<repo>/runs/*/result.json` (valid, match verdict per tool) or read the cited r1_comparison files.
  - files: tests/test_signals_evidence/r1_comparison.md, tests/symbol_changes_evidence/r1_comparison.md

### Dead Ends
- A full rewrite of the blog post for a portfolio audience was drafted and rejected by the user as reading too AI-written; the blog stays as it was.
  - files: none

### Related
- agent-docs/progress-logs/b6b52b71cce3df29-agent-problem-injection-eval.md
  - files: agent-docs/progress-logs/b6b52b71cce3df29-agent-problem-injection-eval.md
- agent-docs/todos/6cddcdd2e2ebc085-uncaught-agent-type-groups.md
  - files: agent-docs/todos/6cddcdd2e2ebc085-uncaught-agent-type-groups.md

## Record

### Changes
- README.md: appended `# 평가` section.

### Commands
- none run beyond reading records and appending README.md.

### Failed Attempts
| attempt | failure evidence | cause |
| --- | --- | --- |
| Rewrite of is-my-code-ai-friendly.mdx (draft in scratchpad only) | user: "summary 그대로 둬. 너무 ai 티난다.." | verified: user rejected the style |

### Sources
- tests/test_signals_evidence/r1_comparison.md (91 matched, 41/51 on target types via P11–P15 rows)
- tests/symbol_changes_evidence/r1_comparison.md (P20 8/8, P50 6/7 matched)
- agent-docs/progress-logs/b6b52b71cce3df29-agent-problem-injection-eval.md (full-run 27 vs 92, control false positives)

### User Requests

#### 1 — 2026-11-23T11:00:32Z

> 일부로 결함을 주입해서 개선 신호를 만들고 iteration을 반복하는 중이었지? 최근에

#### 2 — 2026-11-23T11:03:38Z

> Readme보면 연결되는 블로그 - ~/toy-projects/doggy-portfolio에 있어. Url과 같은 파일을 찾으면 돼. 이 내용을 추가해줄래? 어투는 다른 글 참고해서.
> 일단 추가하기 전에 draft부터 보여줘

#### 3 — 2026-11-23T11:12:32Z

> Next 한 게 한정된 면접관의 시간을 소모시킬 가치가 있을까?
> 아니면 빼자. 있으면 feature로 적고.
> 
> 재측정을 같은걸로 한건 괜찮아.
> 
> 숫자는 의미만 정확히 설명해줘
> 
> 그것도 고쳐줘.
> 
> ---
> 
> 정보를 일방적으로 append하지말고 목적(포트폴리오 블로그)에 맞게 쓰고, 새로운 눈으로 다듬어. 이해하기 쉽게 쓰고

#### 4 — 2026-11-23T11:18:38Z

> summary 그대로 둬. 너무 ai 티난다..
> 안되겠다. Blog는 건드리지 말고 README에만 추가 내용으로 넣자.

#### 5 — 2026-11-23T11:52:05Z

> dev -> master로 보내. 일단은 간섭은 무시.
