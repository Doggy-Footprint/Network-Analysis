# Report graph/modal redesign — verifier limit

## Goal
"1. 페이지 전체에 걸쳐서, "중심에 있는 큰 코드, Authority, 가중 Fan-in, 제외, 대상 밖" 등 보고서를 이해하는데 필요한 용어는 hover 했을 때 설명이 같이 보이게 해줘. 할인이나 가중의 뜻도 설명해주고.
2. 파일 단위로 전체 연결성 그래프를 보여줘. 참고 -> https://blog-steel-ten-13.vercel.app/posts/is-my-code-ai-friendly에 임베딩 되어 있는 iframe 내부 html. : 이걸로 대상을 찾아 근거 확인하기를 대체하고, 기존 대상을 찾아 근거 확인하기는 -> 그래프 옆에 목록으로 확인하기를 추가해서 그래프 or 목록으로 볼 수 있게 해줘.
3. 선택하면 밑으로 이동하는 방식 말고, modal로 요약된 정보를 띄워주고, 지금의 verbose한 보고서 스타일은 버리자. 너무 설명이 많고 가독성이 떨어진다."

## State
- Branch master, base commit bca6eee2921f159d8097510e46fc17e9e250c73b, uncommitted.
- Implementation: report/unified.py, renderers/html/templates/dashboard.html, renderers/html/static/app.js, renderers/html/static/styles.css, renderers/html/vendor/cytoscape-* (deleted, staged).
- Tests: tests/test_report_{layers,graph,modal,tooltips,structure,network,security,performance,compat}.py, tests/report_redesign_support.py, tests/fixtures/vis-network-9.1.9/, tests/report_redesign_evidence/, rewritten legacy browser tests (test_unified_*.py, test_file_analysis_browser.py, test_ambiguous_candidates_browser.py, test_analysis_coverage_browser.py), tests/unified_support.py, tests/file_analysis_browser_support.py; evidence JSON files rewritten by test runs.
- Full suite: 1294 passed, 200 subtests (2026-10-11).

## Failed Attempts
| attempt | failure evidence | cause |
| --- | --- | --- |
| F04 v1 package fallback (common prefix over all production files) | tag-manager 232/296 files → layer 'com' | verified: unrooted files (gradle/, app/build.gradle.kts) emptied the common prefix |
| V08 node-hover retry-only fix | 3/10 failures | verified: random layout overlapped hover targets; fixed by pinning positions |

## Next Step
Close E07: add a V04 test where one neighbour has several relations whose per-neighbour sum (not max/first) moves it across the top-10 cut; run mutation M4 (max instead of sum) to confirm detection; rerun the full suite. A new workflow run (fresh verifier budget) is needed to audit it.

## Open Questions
- Symbol-report 파일 KPI value is unspecified (currently distinct source file count).
- Candidate borders dominate graph colour on tag-manager (almost every file is a candidate); a toggle is a possible follow-up.

## Spec
agent-docs/spec-logs/0c3bcfad9643613b-report-graph-modal-redesign.md, version 3, status limit, run 0c3bcfad9643613b.

## Execution Ledger
- Findings: verifier-1 E01–E06, S01–S03 → closed in v3. verifier-2 E07 (V04 per-neighbour sum ranking untested) → open, blocking. Advisory: V01 generated/vendored flags untested (M7); glossary.json spec_version stamp; shot.py not in repo; candidate border dominance.
- Mutations: M1 min→product detected; M2 prefix incl. unrooted detected; M3 focus last opener detected. M4–M8 proposed, not run.
- Counters: correction batches 3, verifier invocations 2/2.
- Review: tests/report_redesign_evidence/review.md (screenshots + glossary checklist) pass.
