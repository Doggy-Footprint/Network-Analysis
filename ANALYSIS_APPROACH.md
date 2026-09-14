# Analysis approach

A snapshot fixes sorted repository paths, contents, exclusions, and a digest. Dependency adjacency is directed, ignores self-edges, and deduplicates endpoint pairs. Node token costs use explicit costs or deterministic fallback costs; vendored, generated, and migration nodes retain effective-cost multipliers of 0.0, 0.1, and 0.1.

The dependency network reports independent PageRank, HITS hub and authority scores, degree and betweenness centrality, weighted centrality cost, fan-in/out, and two- and three-hop token costs. Rankings are independently ordered by value then node id. Large graphs use deterministic betweenness sampling.

The exploration network is static. A harness profile fixes search output and read-line limits. Generated probes preserve total, visible, and omitted output counts. Candidates identify output truncation, multiple results, evidence spread, read limits, connection constraints, and unresolved analyzer boundaries with concrete evidence.

All serialization is deterministic. The HTML report accepts only `bottlenecks.v2` JSON and embeds the validated data. Python analysis consumes the fixed snapshot directly; the other analyzers currently scan the same filesystem before their graph is checked against that snapshot, so concurrent filesystem mutation is a recorded limitation until snapshot-native parsing is implemented. Results describe static structure and profile-bound exposure only; they do not describe observed agents, probabilities, aggregate scores, or safety outcomes.
