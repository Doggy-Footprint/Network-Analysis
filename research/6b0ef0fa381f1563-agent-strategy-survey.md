File: 6b0ef0fa381f1563-agent-strategy-survey.md
Milestone: M2
Version: 2

# Purpose

Survey published evidence for the behavior parameters the analyzer currently treats as
defaults — serial exploration turns, grep-loop-style search, `bfs-exhaust`, `hint-prior` —
before the phase-B cost contract is frozen in M3, plus change-impact-analysis literature
for the M4 pre-modification checklist. Per finding: source, claim, model parameter touched,
disposition (adopted now / deferred / rejected) and reason.

Sourcing method: web search across six required areas, followed by a relevance/reliability
filter (drop score <=2 on either axis; collapse duplicate claims to the single
highest-reliability source). Filtered survivors below.

# Evidence status and operating rule

Findings with a direct primary-product source or empirical study are the evidence basis for the current model and its already-declared scope. Findings from a third-party product description, or from developer interaction traces being transferred to agent behavior, are insufficient to establish a default. They remain recorded as **extension candidates**: an M3-or-later profile option may implement them only after primary evidence or agent-trace calibration establishes the parameter and its value.

| Status | Findings | Treatment |
|---|---|---|
| Direct, source-bounded evidence | F2, F3, F4, F7 | Use only for the model decision directly stated by the source. |
| Indirect or incomplete evidence | F1, F5, F6 | Do not use to confirm or set a default; retain as an extension candidate or calibration question. |

# Findings

## F1 — Claude Code subagent fan-out and parallel exploration

- Source: "Claude Code Subagents: Official Documentation Reference (2026)", https://thepromptshelf.dev/blog/claude-code-subagents-official-documentation-reference-2026/
- Reliability: 3/5 (third-party writeup, not the primary vendor doc; treated as directionally indicative, not authoritative)
- Claim: Claude Code ships a read-only "Explore" subagent that fans out concurrently across a codebase on a fast/cheap model, reading excerpts rather than whole files; subagents run with independent context and nested fan-out is supported.
- Parameter touched: parallel batching, subagent fan-out
- Disposition: **extension candidate; default unchanged.** The source is a third-party writeup, so it is not sufficient evidence to change the serial-turn default or establish that nested fan-out is representative. Parallel batching and subagent fan-out may become explicit M3 profile options after primary product documentation and agent traces establish their behavior and cost semantics.

## F2 — Cursor semantic/embedding codebase index

- Source: Cursor official blog, "Securely indexing large codebases", https://cursor.com/blog/secure-codebase-indexing
- Reliability: 5/5 (primary vendor source)
- Claim: Cursor chunks files into semantic units via AST-based chunking, embeds chunks into vectors, and serves `@codebase` queries via vector similarity search rather than exact or path-namespace search; a Merkle tree over the tree avoids full reprocessing on change.
- Parameter touched: index/repo-map preloading (semantic)
- Disposition: **rejected.** This is a real, deployed design, but embedding-based semantic retrieval is exactly what ROADMAP.md's scope statement excludes: "Inference that recalls expressions outside the rule table through outside knowledge or semantic similarity is out of scope." Recording it here so the exclusion is a documented decision against known practice, not an oversight — not adopting it into the model.

## F3 — Aider PageRank-based structural repo map

- Source: Aider official docs, "Repository map", https://aider.chat/docs/repomap.html
- Reliability: 5/5 (primary vendor source)
- Claim: Aider builds a directed graph of symbol definitions/references from tree-sitter parses (files as nodes, static dependency edges), ranks it with a PageRank-style algorithm, and preloads the top-ranked slice into every prompt up to a token budget, shrinking by dropping lowest-ranked symbols as active file context grows.
- Parameter touched: index/repo-map preloading (structural)
- Disposition: **partially adopted, partially deferred.** Unlike F2, this ranks a purely structural dependency graph — no embeddings, no semantic similarity — so it does not cross the project's stated boundary. Two separate things follow:
  - The ranking mechanism itself (PageRank/centrality over static edges) is already in scope as a task-less graph-wide metric (ROADMAP.md "Task-less graph-wide analysis"). No change needed there; F3 is recorded as external validation that this metric class is used in production tools.
  - The *preloading* mechanism — injecting a ranked structural map into every session before any query is issued — is not modeled. Phase A currently admits only entry documents and root list queries (ROADMAP.md "Agent session model" table). Adding a preloaded ranked map is a phase-A contract change and is deferred to M3, where it should be evaluated as a phase-A query-set seed alongside sLLM-generated queries.

## F4 — SWE-agent / OpenHands agent-computer interface (grep-loop baseline)

- Source: "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering" (arXiv v3), https://arxiv.org/abs/2405.15793
- Reliability: 4/5 (primary empirical paper; the cited URL is a preprint)
- Claim: SWE-agent exposes structured `find_file` / `search_file` / `search_dir` commands over filenames and file contents, caps each search at 50 results, presents a file viewer of at most 100 lines, and collapses older observations. Its reported ablations compare summarized search, iterative search, and shell-only operation. This source does not establish OpenHands behavior.
- Parameter touched: search surface, search output cap, context-window eviction
- Disposition: **adopted for the source-bounded defaults; extension candidate for eviction.** The structured path/content search and capped output directly support the analyzer's existing search surface and output cap; the study does not prescribe the profile's numeric values. Observation collapse is direct evidence that context management exists in a deployed interface, but it does not establish an eviction policy or value for this analyzer. Model it, if at all, as a later profile option calibrated on agent traces.

## F5 — Noise in Mylyn interaction traces

- Source: "Noise in Mylyn interaction traces and its impact on developers and recommendation systems", Empirical Software Engineering (Springer), https://link.springer.com/article/10.1007/s10664-017-9529-x
- Reliability: 5/5 (peer-reviewed journal)
- Claim: Interaction-trace logs behind degree-of-interest (DOI) style navigation recommenders contain systematic noise, and this noise measurably degrades recommendation accuracy unless filtered.
- Parameter touched: navigation-prediction (carries over to `hint-prior`)
- Disposition: **extension candidate; default not confirmed.** The study establishes noise behavior in developer interaction traces, not in deterministic analyzer hints or agent tool logs. It therefore cannot support `hint-prior` over `uniform`. If M7 calibrates a trace-derived ordering feature, its input must be filtered and its transfer to agent traces tested.

## F6 — Consensus interaction-trace recommender

- Source: "Consensus task interaction trace recommender to guide developers' software navigation", Empirical Software Engineering (Springer), https://link.springer.com/article/10.1007/s10664-024-10528-7
- Reliability: 5/5 (peer-reviewed journal)
- Claim: A recommender that aggregates multiple developers' interaction traces outperforms single-trace navigation-prediction baselines.
- Parameter touched: navigation-prediction (carries over to `hint-prior` / M7 trace corpus)
- Disposition: **extension candidate; default not confirmed.** The result concerns aggregated developer traces. It is useful when designing an M7 agent-trace corpus, but does not demonstrate that aggregation improves an agent ordering policy. M7 must test that transfer before using it for calibration.

## F7 — Call-graph impact prediction validated via mutation testing

- Source: "A large-scale study of call graph-based impact prediction using mutation testing", Software Quality Journal, https://doi.org/10.1007/S11219-016-9332-8 (open version: https://arxiv.org/pdf/1812.06286)
- Reliability: 5/5 (published empirical study)
- Claim: Static call-graph-based change impact prediction is empirically evaluated against a mutation-testing-derived ground truth of actual fault propagation, rather than assumed correct by construction.
- Parameter touched: change-impact-analysis (M4 zone of effect)
- Disposition: **adopted, actioned at M4.** Confirms that static reverse-dependency propagation — the mechanism M4's zone-of-effect model already commits to — has published predictive validity (imperfect, but measured, not assumed). Recorded as: (a) evidence basis for the zone-of-effect design already specified in ROADMAP.md M4, and (b) a candidate methodology — mutation-testing-based ground truth — for M4 or M7 to validate the analyzer's own zone predictions against, alongside real agent traces.

# Parameter delta table

| Parameter | Current default | Evidence | Contradicted? | Disposition |
|---|---|---|---|---|
| Turn model (serial-equivalent turns) | Serial, one query→read at a time (ROADMAP.md "Exploration turns and turns") | F1 | Indirect | Default unchanged; extension candidate pending primary evidence and agent traces |
| Subagent fan-out | Not modeled | F1 | Indirect | Extension candidate pending primary evidence and agent traces |
| Search surface (path + content, exact + derived) | `profiles/agent_view.v3.yaml` | F4 | No | Adopted / confirmed, no change |
| Search output cap (`search_output_limit: 30`, match-line format) | `profiles/agent_view.v3.yaml` | F4 | No | Adopted / confirmed, no change |
| Index/repo-map preloading — semantic | Not modeled | F2 | N/A (out of declared scope) | Rejected |
| Index/repo-map preloading — structural, as a phase-A seed mechanism | Not modeled in phase A (only entry docs + root list queries) | F3 | Yes | Deferred to M3 |
| PageRank / centrality as a graph-wide metric | Already modeled (task-less graph-wide analysis) | F3 | No | Adopted / confirmed, no change |
| `bfs-exhaust` (phase-B default exploration policy) | ROADMAP.md "Exploration policy and turns" | none found | Unevidenced | Recorded unevidenced; M3's already-planned `bfs-exhaust` vs `best-first-pivot` trace comparison is the falsification path |
| `hint-prior` (vs `uniform` result-ordering) | ROADMAP.md "Cost distribution" | F5, F6 | Indirect | Default remains explicitly uncalibrated; trace-derived ordering is an M7 extension candidate |
| Context-window eviction | Not modeled | F4 | Yes (by omission) | Extension candidate; define and calibrate a profile option before adoption |

# Profile changes applied

None. Direct evidence does not prescribe a change to an existing profile value. Structural
repo-map preloading is an M3 phase-A option; context-window eviction is an M3-or-later
profile option. The indirect findings on turn model, subagent fan-out, and trace-derived
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

# Re-run policy

Version 2 cross-check: separated direct evidence from indirect evidence, corrected F4's
source-bounded claims, recorded F4 evidence for context-window eviction, and replaced F7's
preprint-only citation with its published source.

Per ROADMAP.md M2: "The findings file is re-run and re-versioned before each later
milestone rather than treated as done once." Re-run before M3, M4, M6 and M7, bump
`Version:` in this file's header, and append new findings rather than deleting superseded
ones — a superseded finding's disposition is updated in place with a note on why.
