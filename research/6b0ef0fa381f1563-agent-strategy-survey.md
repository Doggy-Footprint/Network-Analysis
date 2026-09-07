File: 6b0ef0fa381f1563-agent-strategy-survey.md
Milestone: M2
Version: 1

# Purpose

Survey published evidence for the behavior parameters the analyzer currently treats as
defaults — serial exploration turns, grep-loop-style search, `bfs-exhaust`, `hint-prior` —
before the phase-B cost contract is frozen in M3, plus change-impact-analysis literature
for the M4 pre-modification checklist. Per finding: source, claim, model parameter touched,
disposition (adopted now / deferred / rejected) and reason.

Sourcing method: web search across six required areas, followed by a relevance/reliability
filter (drop score <=2 on either axis; collapse duplicate claims to the single
highest-reliability source). Filtered survivors below.

# Findings

## F1 — Claude Code subagent fan-out and parallel exploration

- Source: "Claude Code Subagents: Official Documentation Reference (2026)", https://thepromptshelf.dev/blog/claude-code-subagents-official-documentation-reference-2026/
- Reliability: 3/5 (third-party writeup, not the primary vendor doc; treated as directionally indicative, not authoritative)
- Claim: Claude Code ships a read-only "Explore" subagent that fans out concurrently across a codebase on a fast/cheap model, reading excerpts rather than whole files; subagents run with independent context and nested fan-out is supported.
- Parameter touched: parallel batching, subagent fan-out
- Disposition: **contradiction recorded, adoption deferred to M3.** The current model charges exploration as serial-equivalent turns and explicitly excludes parallel batching and subagent fan-out from the graph (ROADMAP.md "Exploration turns" section). This finding is real-world evidence that both are common, not edge cases. Redefining the turn unit to admit concurrent queries/reads is a cost-contract change, which M2 (survey-only) is not scoped to make — it belongs to M3, which already names parallel batching as "an uncalibrated behavior parameter" pending this survey. Source reliability (3/5) also argues against making the frozen contract change on this citation alone without a primary source.

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

- Source: "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering" (NeurIPS 2024), https://arxiv.org/abs/2405.15793
- Reliability: 5/5 (peer-reviewed paper)
- Claim: SWE-agent's interface exposes structured `find_file` / `search_file` / `search_dir` commands over filenames and file contents that return a bounded summary rather than a raw dump, and a windowed file viewer (~100 lines/turn) instead of `cat`; an ablation against a naive bash grep/cat baseline shows the structured, capped interface performs better on SWE-bench. OpenHands' interface follows the same shape.
- Parameter touched: search surface, search output cap
- Disposition: **adopted — confirms current defaults, no value change.** This matches the analyzer's existing design: search over both path namespace and file contents (`profiles/agent_view.v3.yaml`, search surface), a capped result output (`search_output_limit: 30`), and read-unit token limiting instead of whole-file dumps (`read_unit_token_limit: 8000`). Recorded as external evidence that a capped, structured grep-loop-style interface is not a modeling convenience but matches what outperforms naive raw search in a controlled study. No profile value changes follow from this finding.

## F5 — Noise in Mylyn interaction traces

- Source: "Noise in Mylyn interaction traces and its impact on developers and recommendation systems", Empirical Software Engineering (Springer), https://link.springer.com/article/10.1007/s10664-017-9529-x
- Reliability: 5/5 (peer-reviewed journal)
- Claim: Interaction-trace logs behind degree-of-interest (DOI) style navigation recommenders contain systematic noise, and this noise measurably degrades recommendation accuracy unless filtered.
- Parameter touched: navigation-prediction (carries over to `hint-prior`)
- Disposition: **adopted for citation; caveat deferred to M7.** This supports keeping `hint-prior` (a deterministic, hint-based ordering prior) as the phase-B/C default over `uniform`, since interaction/hint-based prioritization is an established, studied signal class. The noise-filtering caveat does not change anything now — the analyzer's hints are synthetic and deterministic, not raw developer logs — but is recorded as a concrete risk for M7, when `hint-prior`'s weights are calibrated against real agent traces: raw trace signal should not be used unfiltered.

## F6 — Consensus interaction-trace recommender

- Source: "Consensus task interaction trace recommender to guide developers' software navigation", Empirical Software Engineering (Springer), https://link.springer.com/article/10.1007/s10664-024-10528-7
- Reliability: 5/5 (peer-reviewed journal)
- Claim: A recommender that aggregates multiple developers' interaction traces outperforms single-trace navigation-prediction baselines.
- Parameter touched: navigation-prediction (carries over to `hint-prior` / M7 trace corpus)
- Disposition: **adopted for citation, no immediate action.** Directionally supports the M3/M7 plan of collecting a trace corpus (ROADMAP.md M3 falsification gate, M7) rather than calibrating from a single trace. Does not change any M2/M3 default; recorded so M7's corpus-collection design has a citation for using multiple traces rather than one.

## F7 — Call-graph impact prediction validated via mutation testing

- Source: "A Large-Scale Study of Call Graph-based Impact Prediction using Mutation Testing", https://arxiv.org/pdf/1812.06286
- Reliability: 5/5 (peer-reviewed / arXiv empirical study)
- Claim: Static call-graph-based change impact prediction is empirically evaluated against a mutation-testing-derived ground truth of actual fault propagation, rather than assumed correct by construction.
- Parameter touched: change-impact-analysis (M4 zone of effect)
- Disposition: **adopted, actioned at M4.** Confirms that static reverse-dependency propagation — the mechanism M4's zone-of-effect model already commits to — has published predictive validity (imperfect, but measured, not assumed). Recorded as: (a) evidence basis for the zone-of-effect design already specified in ROADMAP.md M4, and (b) a candidate methodology — mutation-testing-based ground truth — for M4 or M7 to validate the analyzer's own zone predictions against, alongside real agent traces.

# Parameter delta table

| Parameter | Current default | Evidence | Contradicted? | Disposition |
|---|---|---|---|---|
| Turn model (serial-equivalent turns) | Serial, one query→read at a time (ROADMAP.md "Exploration turns and turns") | F1 | Yes | Deferred to M3 |
| Subagent fan-out | Not modeled | F1 | Yes (by omission) | Deferred to M3 |
| Search surface (path + content, exact + derived) | `profiles/agent_view.v3.yaml` | F4 | No | Adopted / confirmed, no change |
| Search output cap (`search_output_limit: 30`, match-line format) | `profiles/agent_view.v3.yaml` | F4 | No | Adopted / confirmed, no change |
| Index/repo-map preloading — semantic | Not modeled | F2 | N/A (out of declared scope) | Rejected |
| Index/repo-map preloading — structural, as a phase-A seed mechanism | Not modeled in phase A (only entry docs + root list queries) | F3 | Yes | Deferred to M3 |
| PageRank / centrality as a graph-wide metric | Already modeled (task-less graph-wide analysis) | F3 | No | Adopted / confirmed, no change |
| `bfs-exhaust` (phase-B default exploration policy) | ROADMAP.md "Exploration policy and turns" | none found | Unevidenced | Recorded unevidenced; M3's already-planned `bfs-exhaust` vs `best-first-pivot` trace comparison is the falsification path |
| `hint-prior` (vs `uniform` result-ordering) | ROADMAP.md "Cost distribution" | F5, F6 | No | Adopted / confirmed, cited; noise-filtering caveat deferred to M7 |
| Context-window eviction | Not modeled | none found | Unevidenced | Recorded unevidenced |

# Profile changes applied

None. Every parameter the survey contradicts (turn model, subagent fan-out, structural
repo-map preloading as a phase-A seed) belongs to profile files that do not exist yet
(`profiles/exploration_policy.v1.yaml`, `profiles/cost_weights.v1.yaml` — both M3
deliverables) or to phase-A scope itself, which is ROADMAP.md prose rather than a profile
value. Editing the existing frozen M1 profile (`profiles/agent_view.v3.yaml`) is out of
scope here: none of its current values (search surface, output cap, read-unit limit) are
contradicted — F4 confirms them — so no value change is warranted, and its content is
pinned by M1 golden-fixture and provenance-string tests
(`tests/test_agent_view_graph.py::test_profile_serializes_every_behavior_limit_version_and_provenance`).
This delta table is the recorded input M3 consumes when it creates the exploration-policy
and cost-weight profiles.

# Re-run policy

Per ROADMAP.md M2: "The findings file is re-run and re-versioned before each later
milestone rather than treated as done once." Re-run before M3, M4, M6 and M7, bump
`Version:` in this file's header, and append new findings rather than deleting superseded
ones — a superseded finding's disposition is updated in place with a note on why.
