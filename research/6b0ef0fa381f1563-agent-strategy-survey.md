File: 6b0ef0fa381f1563-agent-strategy-survey.md
마일스톤: M2
버전: 3

# 목적

M3에서 B단계 비용 계약을 확정하기 전에, 분석기가 현재 기본값으로 취급하는 행동 매개변수(직렬 탐색 턴, grep 루프 방식 검색, `bfs-exhaust`, `hint-prior`)에 관한 발표된 근거와 M4 수정 전 체크리스트를 위한 변경 영향 분석 문헌을 조사한다. 각 발견에는 출처, 주장, 영향을 받는 모델 매개변수, 처리 결정(즉시 채택 / 연기 / 거절) 및 사유를 기록한다.

출처 수집 방법: 필수 여섯 영역을 웹 검색한 뒤 관련성·신뢰성 필터를 적용한다(어느 축이든 점수 2 이하이면 제외하고, 중복 주장은 신뢰성이 가장 높은 하나의 출처로 통합). 아래는 필터를 통과한 항목이다.

# 근거 상태 및 운영 규칙

직접적인 1차 제품 출처 또는 실증 연구가 있는 발견은 현재 모델과 이미 선언된 범위의 근거가 된다. 제3자 제품 설명이나 개발자 상호작용 흔적을 에이전트 행동으로 전이한 발견만으로는 기본값을 정할 수 없다. 이들은 **확장 후보**로 기록한다. M3 이후의 프로필 옵션은 1차 근거나 에이전트 흔적 보정이 매개변수와 그 값을 확립한 뒤에만 이를 구현할 수 있다.

| 상태 | 발견 | 처리 |
|---|---|---|
| 직접적이며 출처 범위가 명확한 근거 | F2, F4, F7 | 출처가 직접 진술한 모델 결정에만 사용한다. |
| 간접적이거나 불완전한 근거 | F1, F5, F6 | 기본값을 확인하거나 정하는 데 사용하지 않고, 확장 후보 또는 보정 질문으로 보존한다. |

# 발견 사항

## F1 — Claude Code 하위 에이전트 팬아웃 및 병렬 탐색

- Source: "Claude Code Subagents: Official Documentation Reference (2026)", https://thepromptshelf.dev/blog/claude-code-subagents-official-documentation-reference-2026/
- Reliability: 3/5 (third-party writeup, not the primary vendor doc; treated as directionally indicative, not authoritative)
- Claim: Claude Code ships a read-only "Explore" subagent that fans out concurrently across a codebase on a fast/cheap model, reading excerpts rather than whole files; subagents run with independent context and nested fan-out is supported.
- Parameter touched: parallel batching, subagent fan-out
- Disposition: **extension candidate; default unchanged.** The source is a third-party writeup, so it is not sufficient evidence to change the serial-turn default or establish that nested fan-out is representative. Parallel batching and subagent fan-out may become explicit M3 profile options after primary product documentation and agent traces establish their behavior and cost semantics.

## F2 — Cursor 의미/임베딩 코드베이스 인덱스

- Source: Cursor official blog, "Securely indexing large codebases", https://cursor.com/blog/secure-codebase-indexing
- Reliability: 5/5 (primary vendor source)
- Claim: Cursor chunks files into semantic units via AST-based chunking, embeds chunks into vectors, and serves `@codebase` queries via vector similarity search rather than exact or path-namespace search; a Merkle tree over the tree avoids full reprocessing on change.
- Parameter touched: index/repo-map preloading (semantic)
- Disposition: **rejected.** This is a real, deployed design, but embedding-based semantic retrieval is exactly what ROADMAP.md's scope statement excludes: "Inference that recalls expressions outside the rule table through outside knowledge or semantic similarity is out of scope." Recording it here so the exclusion is a documented decision against known practice, not an oversight — not adopting it into the model.

## F4 — SWE-agent / OpenHands 에이전트-컴퓨터 인터페이스(grep 루프 기준선)

- Source: "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering" (arXiv v3), https://arxiv.org/abs/2405.15793
- Reliability: 4/5 (primary empirical paper; the cited URL is a preprint)
- Claim: SWE-agent exposes structured `find_file` / `search_file` / `search_dir` commands over filenames and file contents, caps each search at 50 results, presents a file viewer of at most 100 lines, and collapses older observations. Its reported ablations compare summarized search, iterative search, and shell-only operation. This source does not establish OpenHands behavior.
- Parameter touched: search surface, search output cap, context-window eviction
- Disposition: **adopted for the source-bounded defaults; extension candidate for eviction.** The structured path/content search and capped output directly support the analyzer's existing search surface and output cap; the study does not prescribe the profile's numeric values. Observation collapse is direct evidence that context management exists in a deployed interface, but it does not establish an eviction policy or value for this analyzer. Model it, if at all, as a later profile option calibrated on agent traces.

## F5 — Mylyn 상호작용 흔적의 잡음

- Source: "Noise in Mylyn interaction traces and its impact on developers and recommendation systems", Empirical Software Engineering (Springer), https://link.springer.com/article/10.1007/s10664-017-9529-x
- Reliability: 5/5 (peer-reviewed journal)
- Claim: Interaction-trace logs behind degree-of-interest (DOI) style navigation recommenders contain systematic noise, and this noise measurably degrades recommendation accuracy unless filtered.
- Parameter touched: navigation-prediction (carries over to `hint-prior`)
- Disposition: **extension candidate; default not confirmed.** The study establishes noise behavior in developer interaction traces, not in deterministic analyzer hints or agent tool logs. It therefore cannot support `hint-prior` over `uniform`. If M7 calibrates a trace-derived ordering feature, its input must be filtered and its transfer to agent traces tested.

## F6 — 합의 기반 상호작용 흔적 추천기

- Source: "Consensus task interaction trace recommender to guide developers' software navigation", Empirical Software Engineering (Springer), https://link.springer.com/article/10.1007/s10664-024-10528-7
- Reliability: 5/5 (peer-reviewed journal)
- Claim: A recommender that aggregates multiple developers' interaction traces outperforms single-trace navigation-prediction baselines.
- Parameter touched: navigation-prediction (carries over to `hint-prior` / M7 trace corpus)
- Disposition: **extension candidate; default not confirmed.** The result concerns aggregated developer traces. It is useful when designing an M7 agent-trace corpus, but does not demonstrate that aggregation improves an agent ordering policy. M7 must test that transfer before using it for calibration.

## F7 — 변이 테스트로 검증한 호출 그래프 영향 예측

- Source: "A large-scale study of call graph-based impact prediction using mutation testing", Software Quality Journal, https://doi.org/10.1007/S11219-016-9332-8 (open version: https://arxiv.org/pdf/1812.06286)
- Reliability: 5/5 (published empirical study)
- Claim: Static call-graph-based change impact prediction is empirically evaluated against a mutation-testing-derived ground truth of actual fault propagation, rather than assumed correct by construction.
- Parameter touched: change-impact-analysis (M4 zone of effect)
- Disposition: **adopted, actioned at M4.** Confirms that static reverse-dependency propagation — the mechanism M4's zone-of-effect model already commits to — has published predictive validity (imperfect, but measured, not assumed). Recorded as: (a) evidence basis for the zone-of-effect design already specified in ROADMAP.md M4, and (b) a candidate methodology — mutation-testing-based ground truth — for M4 or M7 to validate the analyzer's own zone predictions against, alongside real agent traces.

# 매개변수 변경 표

| Parameter | Current default | Evidence | Contradicted? | Disposition |
|---|---|---|---|---|
| Turn model (serial-equivalent turns) | Serial, one query→read at a time (ROADMAP.md "Exploration turns and turns") | F1 | Indirect | Default unchanged; extension candidate pending primary evidence and agent traces |
| Subagent fan-out | Not modeled | F1 | Indirect | Extension candidate pending primary evidence and agent traces |
| Search surface (path + content, exact + derived) | `profiles/agent_view.v3.yaml` | F4 | No | Adopted / confirmed, no change |
| Search output cap (`search_output_limit: 30`, match-line format) | `profiles/agent_view.v3.yaml` | F4 | No | Adopted / confirmed, no change |
| Index/repo-map preloading — semantic | Not modeled | F2 | N/A (out of declared scope) | Rejected |
| `bfs-exhaust` (phase-B default exploration policy) | ROADMAP.md "Exploration policy and turns" | none found | Unevidenced | Recorded unevidenced; M3's already-planned `bfs-exhaust` vs `best-first-pivot` trace comparison is the falsification path |
| `hint-prior` (vs `uniform` result-ordering) | ROADMAP.md "Cost distribution" | F5, F6 | Indirect | Default remains explicitly uncalibrated; trace-derived ordering is an M7 extension candidate |
| Context-window eviction | Not modeled | F4 | Yes (by omission) | Extension candidate; define and calibrate a profile option before adoption |

# 적용한 프로필 변경

None. Direct evidence does not prescribe a change to an existing profile value.
Context-window eviction is an M3-or-later profile option. The indirect findings on turn model, subagent fan-out, and trace-derived
ordering remain extension candidates rather than default changes. The relevant profile files do not exist yet
(`profiles/exploration_policy.v1.yaml`, `profiles/cost_weights.v1.yaml` — both M3
deliverables) or to phase-A scope itself, which is ROADMAP.md prose rather than a profile
value. Editing the existing frozen M1 profile (`profiles/agent_view.v3.yaml`) is out of
scope here: F4 supports the existing search surface and capped output but does not prescribe
their values, so no value change is warranted, and its content is
pinned by M1 golden-fixture and provenance-string tests
(`tests/test_agent_view_graph.py::test_profile_serializes_every_behavior_limit_version_and_provenance`).
This delta table is the recorded input M3 consumes when it creates the exploration-policy
and cost-weight profiles.

# 재실행 정책

Version 3: removed F3 (Aider PageRank repository map) and its two parameter-delta rows.
Structural repo-map preloading is implemented in M3 as a phase-A seed mechanism enabled by
default, and PageRank as a graph-wide metric predates this survey; carrying them here as
survey findings made a design decision look evidence-driven when it is not. Their provenance
now lives in `profiles/exploration_policy.v1.yaml`.

Version 2 cross-check: separated direct evidence from indirect evidence, corrected F4's
source-bounded claims, recorded F4 evidence for context-window eviction, and replaced F7's
preprint-only citation with its published source.

Per ROADMAP.md M2: "The findings file is re-run and re-versioned before each later
milestone rather than treated as done once." Re-run before M3, M4, M6 and M7, bump
`Version:` in this file's header, and append new findings rather than deleting superseded
ones — a superseded finding's disposition is updated in place with a note on why.
