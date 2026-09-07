# Goal: AI Agent Repository Exploration Analyzer

## Purpose

This project approximates, as a static graph, the process by which an AI coding agent locates a change target in a repository and checks the range that change can affect. The analyzer answers:

- Given a task, what must the agent search and how much must it read to find the target?
- Before modifying the target, how far must it read and verify?
- Where do needed nodes exist but stay easy to miss, buried in candidates or reachable only through a weak connection?
- Which nodes, edges, queries or subgraphs increase exploration turns, tool calls and token consumption?
- How would changing the repository structure reduce that cost and that miss risk?

The graph does not reconstruct the repository's meaning. It models explicit clues available in code, documents and comments; exact search; searches derived from read identifiers through a fixed rule table; static relations; and framework rules. Inference that recalls expressions outside the rule table through outside knowledge or semantic similarity is out of scope. The result is therefore a deterministic approximation of the repository as seen from an agent's viewpoint.

## Core concepts

- `task`: a natural-language request given to an agent.
- `query`: a search action the agent runs to expose the next candidates.
- `seed query`: the first search terms an agent runs after receiving a task.
- `target`: one or more nodes that must be found and read to complete the task.
- `readable node`: a repository entity the agent can read independently — file, code unit, config, test, document.
- `exploration connection`: a connection along which a query can be formed from what has been read and a next readable node discovered.
- `potential zone of effect`: the full candidate range that may be affected by a target change and therefore must be read and verified before modifying.
- `verification accessibility`: a separate ranking of how likely the agent is to naturally reach and attempt verification of each zone member. It does not mean impact importance.
- `structural bottleneck`: a node, query, edge or subgraph that repeatedly raises target-discovery or zone-verification cost.
- `list query`: a search action whose surface is the path namespace rather than file contents.
- `refinement query`: a query generated deterministically from an already-exposed result set to expose a subset of it.
- `hint`: deterministic information a query result exposes before the arrival node is read. It is a property of the edge joining a query node and a readable node, not an independent node.
- `entry document`: a repository entry document the agent reads before searching.
- `exploration policy`: the rule governing selection order of pending queries and result nodes.
- `session phase`: one of the three phases in the agent session model below.

## Agent session model

An agent session is modeled as three phases. The phases share one graph, one profile and one cost contract; they differ in what starts them, what ends them, and which relation directions they traverse.

| Phase | Name | Starts with | Ends when | Traversal direction |
|---|---|---|---|---|
| A | Orientation | task text only | first query derived from task text is issued | entry documents, root list queries |
| B | Target discovery | phase A pending query set | all targets have been read | forward: query → result → read |
| C | Pre-modification verification | the target set from phase B | the accessibility cutoff is exhausted | reverse dependency direction (see Zone of effect) |

The unit of analysis is a `(task, target set)` pair, never a single target. A single-target task is the size-1 case of the same contract. Phase B ends when every member of the set has been read, so reads shared between targets are charged once rather than duplicated across independent per-target analyses. Phase C computes each target's zone separately and reports their union, with per-target provenance on every zone member, so overlap between targets is visible instead of double-counted and a verification bottleneck stays attributable to the target that caused it.

Phases are sampled jointly in a single simulation run so that cross-phase correlation is preserved. Per-phase and total cost are both reported. A phase boundary is a reporting boundary, not a reset: read units read in phase B stay read in phase C and cost nothing to revisit.

Phase C is not a second discovery problem with a different name. In phase B the agent does not know where the target is; in phase C it knows the target and must decide which of the target's dependents it needs to open. Modeling them with one policy would erase that difference, so each phase carries its own exploration policy parameter.

## Graph model

The graph represents exploration actions as well as repository entities.

### Readable nodes

Files, modules, classes, functions, methods, types, configs, tests, documents and API endpoints. The arrival point of a query result is the symbol node enclosing the occurrence.

Read cost is counted over the whole read unit containing the symbol, not the symbol's own span, because agents open files rather than slicing out symbols.

A read unit is a file, or a chunk when the file's tokens exceed threshold N. Chunk boundaries are symbol-aligned, not line windows, so the chunk set does not shift with parser state. N lives in the profile together with the tool limit it was derived from.

Oversized files split greedily: symbols are appended in source order until adding the next would exceed N; a single symbol over N is its own chunk; top-level text outside any symbol attaches to the adjacent chunk by position. The split rule carries a version recorded in results.

- Reaching another symbol in an already-read read unit costs zero tool calls and zero tokens.
- All targets in a read unit are considered found the moment it is read.
- Queries generated from that read unit's symbols become candidates at that moment, bounded by the read-query candidate rule below.
- Other chunks of the same file stay unread. Reaching them needs another read tool call or a refinement query scoped to that file.

Read units are a cost-model decision, not a node boundary. Symbol-level relation direction and zone propagation are unaffected.

### Default exclusions

Files an agent does not purposefully search or read are not readable nodes: lockfiles, binaries, build outputs, generated code. Exclusion rules live in a versioned config file and can be overridden per repository. Excluded files are never targets or zone members.

Generated status is decided by exactly two deterministic sources: a path glob list, and a generated-marker regex list matched within a fixed number of leading lines. Both lists and the line count are config values. Results record the config version and the number of files excluded by each source. Content-based guessing is not used.

### Query nodes and result groups

A query node represents the result group exposed by one search action. Query candidates are exact queries and derived queries; both are generated deterministically from already-read repository content.

Exact queries search explicit clues verbatim: identifiers and qualified names, string literals, file and module paths, config keys, URLs and routes, error messages, and code-shaped expressions written in documents and comments.

Derived queries transform already-read identifiers through a versioned rule table, imitating the partial-match searching an agent performs alongside exact search. They are a first-class query kind, not a fallback for empty exact results. Permitted transforms are limited to: case- and digit-boundary token splitting; combinations of split tokens with adjacent tokens; case normalization, plural/singular variation, and prefix/suffix removal registered in the rule table. External synonym dictionaries are not used.

#### Query candidates generated from a read

Generating every exact and derived query from every identifier in a read unit would produce hundreds of pending queries per read, which does not match agent behavior. The real selection criterion is task relevance, which this analyzer places outside the model. Candidates are instead limited to three reproducible proxy signals:

- Target identifiers of static edges leaving the read unit — calls, imports, inheritance, type references.
- Identifiers appearing two or more times within the read unit.
- Identifiers referenced but not declared within the read unit.

A per-read-unit cap on generated queries applies after the filter; the cap and its deterministic truncation order live in the profile. The number of identifiers dropped by the filter and whether the cap truncated are recorded on the query node, so a discovery failure caused by the cap is distinguishable in results.

This rule applies only to queries generated from a read. Hint-based generation follows its own cap below.

#### Search surface

Search targets both file contents and the path namespace. Exact and derived queries match against file contents and against normalized repository-relative paths. Path and filename form a searchable namespace, so the derived rule table is reused on path tokens. Treating paths only as strings inside file contents would systematically overestimate discovery cost for targets findable by filename alone.

Search actions against the path namespace alone are list queries. The result group is the matched path set, the arrival nodes are those files, and result tokens are computed over the exposed path strings. Directory listing is a list query and is not a zero-cost node. Root tree listing during phase A is allowed by default with depth and entry caps in the profile, and its output tokens are charged normally.

#### Occurrences and hints

Occurrences are not independent readable nodes. An occurrence is the evidence for a query result; the arrival point is the enclosing readable node. Query output cost is computed over exposed occurrences, bounded by the output cap below.

Information an occurrence exposes before the arrival node is read is carried as a hint property on the query node → readable node edge. A hint is a deterministic projection of the occurrence through the search tool's output format, which is a contract parameter. Hint values are limited to:

- The arrival node's path, filename and symbol name.
- The occurrence's syntactic role: declaration, import, call, string literal, comment, document mention, test.
- The identifier set inside the exposed line window.

Hints may only use text already charged on the `query result token` axis. The default output format is therefore match lines with zero context; widening the window grows the hint surface and the result token cost together. Because of this invariant, hints create no new cost axis.

#### Search output cap

Real search tools truncate results at an occurrence or output-line cap. The cap is a contract parameter.

- The cap value and unit live in the profile alongside the tool limit it was derived from.
- When a result group exceeds the cap, only the cap is exposed, in lexicographic order of normalized repository-relative path and line number.
- Only exposed occurrences are charged as result tokens and only exposed occurrences create hint edges. Arrival nodes of truncated occurrences are not discovered by that query.
- Truncated query nodes record the truncation flag and total occurrence count. This is the evidence for candidate-dilution diagnosis.

Without the cap, high-result queries would be overcharged and refinement would become pure added cost that no cost-minimizing path ever selects — which would delete the agent's actual reason for narrowing a search from the model.

Truncation and the refinement threshold K are different values on the same axis: K triggers narrowing behavior, the cap is what the tool actually shows. Their relative order is free in the profile, and both are recorded in results.

#### Queries generated without a read

Query node → query node edges exist: an agent re-searches an identifier visible in a result line without opening the file. Constraining every query to originate from a read would make already-charged, already-exposed clues inexpressible. Because this edge sharply raises query branching, it carries caps:

- Candidate identifiers are limited to the exposed line window.
- A per-result-group cap on generated queries lives in the profile.
- Duplicates are removed by the query equivalence rule.

#### Refinement queries

When a result group exceeds threshold K, a narrowing refinement query is generated instead of discarding the query. Candidates are generated deterministically from the already-exposed result set only, using no repository-global knowledge:

- Path prefixes at directory boundaries appearing in the results.
- Extensions appearing in the results.
- Token combinations registered in the rule table.

Refinement is a query → query edge, costs one search tool call, and its result group is a subset of the parent group. Because the output cap leaves large groups partially exposed, refinement has meaning inside the model: it pays extra to reveal what was truncated. Refinement depth and per-query candidate caps are required profile values recorded with K.

#### Query equivalence and duplicate suppression

A query node's identity is the combination of query kind, normalized query string, search surface, scope and rule-table version.

- Different nodes producing the same string are the same query node; discovery provenance is expressed as multiple in-edges. Common bottlenecks across targets surface in this form.
- Different scope means a different query node. A file-scoped refinement is distinct from a global query.
- An already-executed query re-entering the pending set is discarded at zero cost, and the suppression count is recorded.

### Connection specificity and framework connections

Connections divide by how far they narrow the arrival node. This is a general property of every exploration connection, not something specific to frameworks.

- Uniquely identifying: move to the arrival node with a single read, no query node.
- Candidate-narrowing: create a query node whose result group is the narrowed set.

Language import and qualified-name resolution is the first kind. An agent reading `import a.b.Foo` opens that file without searching. Unique identification holds only when the resolver actually succeeded; wildcard imports, re-exports, dynamic imports and multi-candidate modules are candidate-narrowing and are reported as unresolved-boundary diagnostics.

Connections established by framework rules are included even without exact string-match evidence. The criterion is whether the agent can move on that rule alone, not the shape of the evidence. Each framework rule declares in its adapter whether it is uniquely identifying or candidate-narrowing, and results report the governing rule.

### Entry documents

Agents read root entry documents — README, AGENTS.md, CLAUDE.md — before searching. The list lives in versioned config and is overridable per repository.

Entry documents are treated as read at the start of phase A, and queries generated from them enter the initial pending query set. Documents auto-injected by the harness cost zero read tool calls and are charged normally for tokens; auto-injection is flagged in config.

Documents and code that entry documents mention are not treated as read in bulk. Mentions are ordinary exploration connections; when a path or identifier resolves, unique identification applies and one read reaches it. Treating mentions as discovered would make it definitionally impossible to measure whether entry documents actually lower discovery cost, and would automatically favor repositories that list files in their docs.

### Boundaries of modeled exploration

These actions are not made into ordinary exploration connections:

- Semantically recalling an expression absent from what has been read.
- Non-deterministic search terms built from repository-external knowledge alone.
- Selecting a target directly through analyzer-internal information no real agent has.

Derived queries, path and list queries, hint-based generation, refinement, and framework connections are not in this set. Each is either already-paid exposed content or regenerates identically from a fixed rule table.

A relation with no analyzable direct connection, discoverable only by running one specific exact query, is a separate diagnostic candidate.

## Target discovery model

### Initial query generation

Without an explicit seed query, an sLLM produces the initial search term set. It receives the task only — no file listing, no graph, no ground-truth target. Generated terms form one initial pending query set, not one scenario per term.

Model identifier and revision are profile values, not document text or code constants, so that swapping models remains a comparable change.

Generated queries reproduce the agent's first search action; they are not target predictions, and sLLM generation quality is not itself under evaluation. Reproducibility is still required, and recording a model revision is not sufficient because inference-backend batching can shift output. One of the following must hold:

- Run with greedy decoding and a fixed seed, recording the backend and its version.
- Cache generation output as a version-controlled fixture and use the cache as input on later runs.

Prompt, decoding settings and actual generation output are recorded in results either way.

### Exploration policy and turns

Selection order of pending queries and result nodes is governed by the exploration policy, a parameter whose phase-B default is `bfs-exhaust`.

One `bfs-exhaust` turn:

1. Select an unexecuted query.
2. Expose the whole result group and charge output tokens for every exposed occurrence.
3. Order the unique arrival nodes using hints.
4. Read the result nodes one at a time.
5. New queries from read nodes and hints wait until the current result group is exhausted.
6. On exhaustion, select the next pending query.

Group exhaustion is the default because it is the conservative baseline that charges every exposed result and read. Real agents pivot away from a group on a strong clue, so this default is biased toward overestimating cost. The alternative `best-first-pivot` policy prioritizes by hint and leaves a group early; it runs on the same graph with only the policy changed. Policy dominates every reported cost value, so it is a profile value and every result records the policy used. Results produced under different policies are not compared.

`query → result selection → read` is one depth-1 exploration turn. Query and read tool calls and tokens are recorded on separate axes.

Exploration turns are serial-equivalent turns. Real agents issue several searches per turn in parallel, so this axis is not directly comparable to turn counts in real agent logs. Parallel batching is an uncalibrated behavior parameter and stays out of the model until the strategy survey milestone reports on it.

A target appearing in search results is not discovery. Discovery is assumed to happen immediately when the target node is read. Phase B ends when every target has been read. Alternative implementation sites are not considered in the baseline.

Termination is an oracle. An agent stopping after finding only part of the target set is expressed as an observation axis, not a termination rule. Modeling the moment an agent believes it is done is non-deterministic and out of scope.

Revisiting read nodes is supported with an initial probability of 0. The probability is set later from real agent logs.

## Cost contract

Costs are reported on their original axes together with a weighted cost used for path selection.

- exploration turns
- search tool calls
- read tool calls
- query result tokens
- readable node tokens
- 0-result queries
- revisits
- exposed non-target candidates and duplicate occurrences

0-result queries produce no result tokens and no non-target exposure but consume a turn and a search tool call. The purpose of the separate axis is not to grade the seed-query generator but to observe how far the vocabulary that arises naturally from task phrasing diverges from the repository's vocabulary.

The following are early-termination risk observations, not costs. They exist to derive miss risk after the fact while keeping oracle termination, and they are excluded from the weighted cost:

- Discovery turn index per target.
- Number of targets exposed in results but never read.
- Number of nodes that received a hint but were never read — readable nodes with at least one incoming hint edge, unread at termination.

The revisit axis is always 0 while revisit probability is 0. It is a placeholder that takes a value once the probability is set from real agent logs.

The weighted cost is not a repository score. It is the scalar that ranks whole simulation samples so that a reported percentile is one coherent run rather than a per-axis composite; see the cost distribution section. Early on it uses an explicitly temporary default weight profile, and every original axis is reported alongside the weights.

Weight values live in a version-controlled profile file in the repository, not in this document and not in code constants. Cost weight profiles and verification accessibility weights are managed the same way, and every result records the profile id and version. Replacing a temporary value is tracked in the profile file's history, and costs across the replacement are compared on the same graph.

### Tokenizer

Token cost is approximated as `character count ÷ C`, rounded up. `C` is characters per token, not tokens per character, and is a profile value defaulting to 4. Replacing it records the rationale in the profile history.

Digits are excluded from that approximation and counted by a separate rule: a run of digit characters is grouped three at a time from the left, each group counting as one token, with the remainder as one group. Phrasing that depends on an external implementation is not used. This rule carries a version recorded in results.

### Cost distribution: p5 / p50 / p95

There is one cost estimator: a Monte Carlo simulation over the order space the exploration policy permits.

**The percentile unit is a whole sample, not an axis.** Each sample is one complete simulated run producing a value on every cost axis. Samples are ranked by their weighted cost, and p5, p50 and p95 name the runs at those ranks. Every axis value reported at a percentile therefore comes from the same run, and each percentile carries the query and read sequence that produced it.

The alternative — computing percentiles per axis independently — was rejected because it produces a composite that no run ever executed, and therefore no evidence path. Bottleneck attribution and what-if comparison both need a replayable sequence behind the number they move.

Consequences that must be stated in every result:

- Individual axes are **not** monotone across p5, p50, p95. The p5 run can have more turns than the p50 run while costing less overall. Only the weighted cost is monotone by construction.
- The weight profile selects which run is reported at each percentile, so replacing weights changes the reported axis values even though the sample set is unchanged. The profile id and version are already required in results; this is the reason they are load-bearing rather than informational.

Each percentile is reported with the full axis vector, the run's execution sequence, the mean and sample count over the whole set, the random seed, and a bootstrap confidence interval on the weighted cost at that rank. Percentile uncertainty is estimated by bootstrap, not from the mean's standard error. Per-axis means and standard deviations over the whole sample set are reported alongside, as distribution shape rather than as percentiles.

Result-node selection order is weighted by a deterministic hint-based prior. Reading declaration occurrences before use occurrences, preferring exact filename matches, and deprioritizing tests are behaviors reproducible from information already charged for at search time. Discarding that information and sampling uniformly biases the distribution pessimistically. Because the prior is an uncalibrated behavior model, a uniform policy is kept alongside it: `uniform` and `hint-prior` are named profile policies, the policy used is recorded, and the prior's effect is observable and falsifiable as the difference between two runs. The default is `hint-prior`.

The given seed query set is input, not a choice, so every seed query is charged as executed in every sample. Ties in sample-internal ordering are broken by a versioned deterministic cascade so that a given seed reproduces a given sample:

1. Lexicographic comparison of the original cost axes, with axis priority fixed in the profile independently of the weights.
2. Shorter execution sequence.
3. Lexicographic minimum of the id sequence, where an id combines the normalized repository-relative path and the qualified symbol name, separators normalized, compared bytewise. Depending on filesystem enumeration order or hashes would break M1's deterministic serialization.

**Replaced definitions.** Earlier revisions defined an exact weighted minimum and a BFS maximum. Both are removed.

- The exact minimum required searching a state space of `executed query set × read read-unit set`, exponential in the worst case, and needed a search budget, a `budget-exceeded` status and tie-set enumeration to stay tractable.
- The BFS maximum converged, under oracle termination, to `seed-reachable closure cost − one final target`, so it varied with closure size rather than with the task and was insensitive to structural change in what-if comparison.

The structural upper bound is kept, but as a separate directly computed axis rather than as a search: **seed reachable closure cost**, the total cost of reading everything reachable from the seed query set. It is cheap to compute, it explains how much of p95 is closure size rather than task difficulty, and it gives a checkable invariant.

Invariants, both verified per run:

- `weighted(p5) ≤ weighted(p50) ≤ weighted(p95)` — holds by construction, since the ranking is by weighted cost. It does **not** hold per axis, and a per-axis assertion would be a false invariant.
- `axis(p95) ≤ seed reachable closure cost`, for every axis — holds while revisit probability is 0, because any single run reads a subset of the closure. This is asserted per axis on every sample, not only on p95. Raising revisit probability above 0 can break it, and the contract is rewritten at that point.

Minimum sample count, convergence condition and maximum sample count are profile values. Defaults and tolerances are tuned against fixtures and real repository analysis.

### Reachability failure

An approximated graph may not reach every target. No arbitrary penalty is added to the cost. The failure state and the unreached targets are stated explicitly. Detailed failure output — failed queries, partially discovered targets — is defined in the phase-B output contract.

## Zone of effect

The potential zone of effect is the full candidate range that a target change may affect and that the agent must therefore read and verify.

### Directionality

Propagation runs along the **reverse** of dependency edges: from a target to the things that depend on it. If A uses B and B uses C, then modifying B puts A in the zone and leaves C out. C is what B depends on; changing B does not change C.

This is not the same as what the agent must read. To modify B correctly the agent may still need to read C to know the contract B is calling. That is forward-direction **comprehension closure**, and it is charged as phase-C read cost without making C a zone member. Conflating the two inflates every zone by the target's whole forward dependency cone.

Comprehension closure is bounded by a profile depth, default 1: the direct forward dependencies of the read unit being modified are charged, and nothing deeper. Unbounded, it is the whole forward cone and dominates phase C. Depth 1 matches the observable behavior — an agent reads what B calls, not what those callees call — and the depth is a parameter rather than a constant so its effect can be measured instead of assumed. The depth used is recorded in results.

Direction is declared per relation kind in the profile, not inferred. Three cases:

| Case | Relation kinds | Direction | Note |
|---|---|---|---|
| Ordinary dependency | calls, imports, type reference, inheritance, interface implementation, test-of, document mention | reverse only | dependents enter the zone; dependencies do not |
| Contract-carrying pair | shared-state read/write, config key producer/consumer, event publish/subscribe, message enqueue/dequeue, route registration/handler | both | the relation is a contract between two parties, so a change on either side can break the other; the edge pair is materialized in one direction only, so the reverse traversal alone would miss the consumer |
| Substitutable member | overrides of a common base, implementations of a common interface | sibling | changing one implementation can break callers that hold the base type, so the base and its other implementations are reachable in two hops through the base; this is reverse propagation, listed separately because it is the case most often mistaken for forward propagation |

Exceptions are enumerated in the profile as an explicit relation-kind → direction table. A relation kind absent from the table defaults to reverse-only and is flagged in results, so adding a language or framework adapter cannot silently introduce untyped propagation.

### Zone records

Each zone node records:

- The potential impact path from the target.
- Relation kind and direction, and which row of the direction table applied.
- The evidence: code, query, framework rule or document mention.
- Static analysis confidence and its limits.
- The verification accessibility components.
- Whether it fell inside the user cutoff.

Verification accessibility is ordered by a weighted sum over source kind, relation kind, distance and static confidence. It is not an impact-importance or change-necessity score. Low accessibility does not remove a node from the potential zone; it is reported as *possible impact, unobserved in this verification scenario*.

Tests are always in the potential zone but are excluded by default from the accessibility ranking and cutoff result; inclusion is configurable.

### Zone size

Reverse reachability is unbounded in principle: a widely used utility's transitive dependent set can be most of the repository. If that is the common case, the zone stops distinguishing targets and the cutoff mechanism becomes the only thing doing work — which would mean the analyzer measures the cutoff, not the repository.

This is measured before any mitigation is designed. See the phase-C milestone's decision gate.

## Task-less graph-wide analysis

The repository is analyzed without a task. Every readable node is treated as a potential target, reported per metric:

- PageRank, centrality, connected components, k-hop cost
- Targets producing large potential zones
- Nodes and subgraphs that must be read but have low verification accessibility
- Cycles, bridges, articulation points, excessive query branching
- Unresolved or dynamic boundaries
- Points where exact queries expose excessive non-target candidates
- Abnormally large or disconnected subgraphs

No single global quality score is produced. Every result must be traceable back to the related nodes, queries, edges, paths, cost components and uncertainty.

## Generated evaluation scenarios

Targets likely to be problematic are selected from the graph-wide analysis, and an sLLM generates natural-language tasks from target information. Given `SettingsTab.kt` and `AudioSettingDialog` as targets, it might produce *change the audio output selection UI*.

- Several tasks per target.
- Easy scenarios may name the filename or identifier directly.
- At least one task contains no target identifier.
- Generated tasks are flagged as synthetic in result metadata.
- The seed-query sLLM receives the task only, never targets or the graph.
- Scenarios that deliberately point at a wrong target are not generated.

Synthetic tasks do not claim to be real user tasks. They exist to evaluate how differently the same target is discovered depending on task phrasing.

## Structural bottlenecks and improvement candidates

A bottleneck is explained by at least one of:

- A node, query or edge where valid paths to a target or zone concentrate
- A query that raises cost by exposing many non-target results
- A search-only relation hard to find without one specific exact query
- A relation whose code, config, docs and tests are far apart
- A node repeatedly exposed or hinted but never read
- A potential impact node easily missed due to low verification accessibility
- A common bottleneck recurring across several targets or zones
- A target whose removal or cost reduction lowers exploration cost

Improvement candidates are compared as what-if results on a limitedly modified graph, without changing the repository. Cost reduction, number of affected targets and prediction confidence are reported separately.

## Roadmap

Every milestone defines its own output schema and traceability fields as part of its completion criteria. There is no separate output-contract milestone.

From M1 onward every milestone delivers machine-readable JSON plus an HTML report generated from that JSON alone.

| Milestone | HTML must show |
|---|---|
| M1 | graph composition, cost distribution, node/query/framework evidence relations |
| M2 | surveyed agent strategies and tools, and which model parameters each one changes |
| M3 | phase A and B discovery process with p5/p50/p95 and closure cost |
| M4 | per-target zone, direction table applied, cutoff result, verification accessibility |
| M5 | bottleneck ranking, evidence paths, what-if before/after |
| M6 | discovery cost compared across targets and task phrasings |
| M7 | calibration data coverage, before/after error comparison |

Existing implementation status:

| Status | Feature |
|---|---|
| Keep | language and framework analyzers, static relations and evidence, graph metrics including effective and weighted measures, renderers |
| Replace or extend | the existing symbol graph becomes M1 readable and query nodes; serialization and CLI output extend per milestone contract. Current graph metrics are M5 input and do not constitute M5 completion. |
| Remove | previous exploration cost, task difficulty, repository cost diff, git diff impact analysis, structural friction diagnostics, Android inject-field arbitrary costs and warnings |

### M0. Document and contract realignment — complete

- Project purpose, graph boundary and non-goals fixed
- Query groups, exploration turns, cost axes and the cost contract documented
- Zone of effect separated from verification accessibility
- Keep/replace/remove mapping table for existing features
- Code, tests and fixtures for removed features deleted

Done when: every reference document uses the same purpose and vocabulary, every existing feature has a mapping-table status, no references to removed features remain, and the full test suite collects without import errors.

### M1. Agent-view graph — complete

Scalability invariants: read the repository as one immutable snapshot; exclude explicit identified analyzer output from re-analysis; cap exposed search results by profile while preserving full occurrence evidence losslessly in deterministic compressed blocks.

- Readable node and query node model
- Token-threshold read-unit splitting; greedy sequential split, single oversized symbol allowed
- Search surface covering file contents and path namespace; list queries
- Exact query extraction
- Derived query generation from a versioned rule table
- Proxy-signal filter and per-read-unit cap for queries generated from a read
- Connections split into uniquely identifying and candidate narrowing; import and qualified-name resolution and framework connections carry the same property
- Code, document and comment occurrences and connection evidence
- Occurrence hint edges over a fixed output format
- Hint-based query generation without a read, with caps
- Refinement queries with depth and candidate caps
- Query equivalence and duplicate suppression
- Entry document handling and auto-injection flag
- Query result groups and raw output cost
- Deterministic graph serialization and diff

**Delivered**: `agent_view/` package, `profiles/agent_view.v3.yaml`, `agent-view.json` schema, HTML report via `generate_html.py` + `html_template/`, golden fixtures under `tests/fixtures/agent_view/`.

Done when: the same repository and settings reproduce the same query groups, results, evidence and costs. Read-unit splitting, hint projection and query equivalence are covered by reproducibility tests.

### M2. Agent strategy and tool survey — initial pass complete, re-run before M3

The behavior parameters this project treats as defaults — serial turns, grep-loop search, `bfs-exhaust`, `hint-prior` — were chosen without evidence. Several are already known to be wrong in one direction: real agents batch searches in parallel, delegate exploration to subagents, and some run against a semantic index or a precomputed repository map rather than a grep loop. Freezing the phase-B cost contract before surveying this means measuring a tool model that no shipped agent uses.

This milestone is a survey, not an implementation, and it is deliberately placed before the cost contract is frozen.

- Survey current agent exploration designs and record, per design, which model parameters it changes: search surface, output cap, parallel batching, subagent fan-out, index or repo-map preloading, context-window eviction
- Survey published work on predicting developer navigation — degree-of-interest models, interaction-trace recommenders, head-to-head evaluations of navigation predictors — and record what carries over from human interaction traces to agent tool logs and what does not
- Survey change-impact-analysis literature for the pre-modification checklist in M4
- For each finding: state whether it is adopted now, deferred to a later milestone, or rejected, with the reason
- Record which currently modeled parameters the survey contradicts

**Proposed outcome**
- `research/<id>-agent-strategy-survey.md` — versioned findings file, one entry per surveyed design or paper, each with source, claim, and the model parameter it touches.
- A parameter delta table: every current profile parameter the survey contradicts, the evidence, and the disposition.
- Profile changes that follow directly from the survey, applied before M3 begins.

Done when: every default behavior parameter in the cost contract either has a survey citation or is explicitly recorded as unevidenced. The findings file is re-run and re-versioned before each later milestone rather than treated as done once.

### M3. Phase A and B — orientation and target discovery cost

- Explicit query sets and sLLM-generated initial query sets
- Injection and recording of sLLM model revision, prompt and decoding settings
- Phase A orientation: entry documents, root list queries, auto-injection cost
- Parameterized exploration policy, phase-B default `bfs-exhaust`
- Result-group exhaustion and pending-query behavior
- Temporary weighted cost profile in a versioned profile file
- Versioned tie-break cascade for sample-internal determinism
- `uniform` and `hint-prior` result-ordering policies
- Monte Carlo p5/p50/p95 as whole-sample order statistics ranked by weighted cost, each percentile carrying its full axis vector and replayable execution sequence, with bootstrap CI
- Seed reachable closure cost as a separately computed axis
- 0-result queries, discovery turn index, unread target and hint observation axes
- Multi-target termination and unreachable handling
- Trace schema for validating against real agent behavior
- Minimum procedure for comparing real agent traces against model predictions

**Proposed outcome**
- `phase_b_cost.json` — per `(task, target set)`: the p5/p50/p95 runs with their full axis vectors and execution sequences, per-axis mean and standard deviation over the sample set, n, seed, bootstrap CI, closure cost, both invariant checks, the profile and policy ids used.
- HTML report: discovery timeline per sample, cost distribution per axis, the closure-cost bar next to p95.
- `profiles/cost_weights.v1.yaml` and `profiles/exploration_policy.v1.yaml`.
- A trace schema plus at least one recorded real agent trace in the same schema.
- A flat `versions` block in every emitted result, recording every version stamp the run actually consumed — split, ordering, output format, query equivalence, derived rules, tokenizer, exclusions, policy, tie-break, cost weights — each as an id and version, with no scoping or grouping applied. Result comparability rules are deliberately not defined here; recording the stamps as data lets a scoping rule be defined later over existing results instead of requiring reruns.

Done when: fixture state transitions and cost axes match, and Monte Carlo results reproduce within the recorded error bounds under a fixed seed. Results under different policies or tie-break versions are reproduced separately and never compared.

Additional falsification gate. Closing this milestone on reproducibility alone would leave open the possibility that every cost value through M6 is unrelated to real exploration.

- Collect a minimal set of real agent traces and report the rank correlation between each trace's target discovery order and the model's predicted discovery turn index.
- Record sample count, repositories, agent and tool settings.
- Compare `hint-prior` against `uniform`, and `bfs-exhaust` against `best-first-pivot`, on the same trace set, and report which fits better.
- No pass threshold is set here. The gate requires that the measurement is recorded and becomes the stated basis for the defaults, not that it exceeds a level.

### M4. Phase C — zone of effect and pre-modification verification

- Relation-kind → direction table in the profile, covering ordinary dependency, contract-carrying pairs and substitutable members
- Propagation over that table, with unlisted relation kinds defaulting to reverse-only and flagged
- Forward comprehension closure charged as phase-C read cost without entering zone membership, bounded by a profile depth defaulting to 1
- Full potential zone per target and their union across the target set, with per-target provenance on every member
- Accessibility ranking, with weights in a versioned profile file
- User cutoff mechanism and unobserved-impact reporting; defaults temporary and flagged as such
- Tests excluded by default from ranking and cutoff, configurable to include
- Phase-C exploration policy: how the agent traverses the zone, sampled under the same Monte Carlo contract as phase B
- Zone verification cost and evidence paths

**Zone size decision gate.** Before any mitigation is designed, measure on fixtures and on real repositories: the distribution of `|zone| / |readable nodes|` at depth 1, 2, 3 and unbounded; how much of the zone comes from a small number of high-fan-in utility nodes; and the variance of zone size across targets in the same repository. Only after that measurement is recorded is a mitigation chosen from:

- Bound propagation depth, report the depth used and the truncation flag.
- Report zone size at each depth as separate axes rather than one number.
- Treat high-fan-in nodes as a separate reported class so that generic utility fan-out is not attributed to the target.

Choosing a mitigation before the measurement would mean the reported zone measures the mitigation heuristic rather than the repository.

**Pre-modification checklist.** A script that, given a target, emits the ordered list of things to check before modifying it: the zone members, the evidence for each, and the accessibility rank. The rank is a rank, not a probability that an agent visits the item. Calling it a probability requires calibration against agent traces and is deferred to M7. Whether the rank predicts real agent visits at all is measured as part of M7's calibration, using the same trace corpus as the M3 gate — and if the M2 survey finds that developer-navigation predictors do not carry over to agent logs, the checklist ships as a static list with no visit-likelihood claim.

**Proposed outcome**
- `zone.json` — per target set: the union of zones, each member carrying path, the targets it came from, relation kind, direction-table row, evidence, confidence, accessibility components, cutoff membership.
- `zone_size.json` — the decision-gate measurement, with the chosen mitigation and its rationale.
- `profiles/zone_direction.v1.yaml` and `profiles/accessibility_weights.v1.yaml`.
- HTML report: per-target zone with direction shown on each edge, cutoff boundary, and the unobserved-impact list.
- `scripts/pre_modify_checklist.py` producing the checklist for a named target.

Done when: per target, the full zone, the direction row applied to each edge, the cutoff result and the accessibility evidence reproduce separately; the zone-size measurement is recorded; and any unlisted relation kind is flagged rather than silently propagated.

### M5. Graph-wide bottleneck analysis

- Graph metric and potential zone aggregation
- Query branching, candidate dilution and search-only relations
- Candidate-narrowing framework rule modeling and the query branching those rules create
- Cycles, bridges, articulation points, unresolved boundaries and abnormal subgraphs
- Discovery bottlenecks separated from zone verification bottlenecks
- Counterfactual cost comparison for bottleneck removal or mitigation

M1 implemented the representation and cost computation for candidate-narrowing rules but registered none. Message enqueue/dequeue and event publish/subscribe — relations whose arrival node cannot be statically fixed — belong here. Registering them adds edges, so M3 and M4 results are recomputed against a new baseline.

**Proposed outcome**
- `bottlenecks.json` — ranked bottlenecks, each with its evidence paths, the cost axis it raises, which targets or zones it affects, and the what-if delta.
- Registered candidate-narrowing framework rules in an adapter, each reporting the query branching it creates.
- HTML report: bottleneck ranking with evidence path drill-down and a before/after what-if view.
- Recomputed M3 and M4 baselines against the new edge set.

Done when: each bottleneck is explained by path and what-if result in terms of which cost axis of which target or zone it raises, and every registered candidate-narrowing rule reports its query branching.

### M6. Generated evaluation scenarios

- Selecting targets likely to be problematic
- Generating several natural-language tasks per target
- Difficulty variants with and without identifiers
- Task-only seed query generation reusing the M3 sLLM execution contract, with synthetic metadata
- Evaluation on real public repositories and fixed fixtures

**Proposed outcome**
- `scenarios.json` — generated tasks with target, phrasing variant, synthetic flag, model revision, prompt, decoding settings.
- `scenario_cost.json` — discovery cost per target across phrasings, on the M3 cost contract.
- HTML report: same target, cost spread across phrasings, with the identifier-present and identifier-absent split shown.

Done when: tasks and initial queries reproduce under the same model revision and settings, and discovery cost is compared across phrasings.

### M7. Calibration and operation — deferred

- Behavior model calibration from real agent tool and read traces
- Adjusting temporary weights and zone accessibility weights
- Deciding default zone cutoff input and accessibility weight defaults
- Measuring whether accessibility rank predicts real agent visits; only if it does may the checklist state a visit likelihood
- Additional language and framework adapters
- Performance budget for large graphs
- Validation dataset versioning and regression evaluation

**Proposed outcome**
- A versioned trace corpus with agent, tool settings and repository recorded per trace.
- Calibrated profile versions replacing every parameter flagged temporary, each with the measurement that set it.
- Before/after error comparison against the M3 falsification gate metrics.

Done when: calibration data, model and tool settings, and the evaluation procedure are version-controlled, and existing contract fixtures still pass.

## Verification principles

- Distinguish what the graph represents as observable from the semantic inference it does not represent.
- Record the sLLM's input, model revision, prompt and decoding settings.
- Distinguish synthetic tasks from real tasks.
- Inject time, randomness, model and tool settings, and record the random seed.
- Report Monte Carlo results with sample count and error.
- Report costs with the original axes, the weight profile id and version, and the weighted result.
- Record the exploration policy, result-ordering policy, tie-break rule version and search output format used.
- Verify bottlenecks by cost change before and after removal or mitigation.
- Every result must be traceable to nodes, queries, edges, occurrences and path evidence.
- Do not treat what a real agent read and what it should have read as the same ground truth.

## Non-goals

- Predicting a task's semantic implementation difficulty or a developer's skill level.
- Claiming to automatically determine the correct target from a task.
- Treating an LLM's semantic association without reproducible evidence as a graph edge.
- Replacing conventional code quality, security or runtime performance analysis.
- Claiming full static recovery of dynamic runtime connections.
- Asserting p50 cost as a specific AI model's actual cost prediction.
- Claiming the potential zone is the definitive set of real change impact.
- Reducing multiple metrics to one repository quality score or a general task difficulty ranking.
