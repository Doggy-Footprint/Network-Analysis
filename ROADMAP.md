# Roadmap

The project measures repository structures that an AI coding agent can reproducibly observe. It reports dependency-network token metrics and static exploration-network obstacles without claims about agent behavior, probability, or change risk.

## Completed baseline

- Python, TypeScript, Kotlin, FastAPI, and Android produce the shared node/edge architecture shape.
- Dependency analysis reports independent centrality, fan, neighborhood, and token-cost rankings from sparse adjacency.
- Static harness profiles produce query/read exposure counts and evidence-backed exploration candidates.
- One CLI run can write architecture HTML/JSON, agent-view JSON, and `bottlenecks.v2` JSON/HTML for every analyzer mode.
- JSON is deterministic, HTML consumes validated JSON, and observation/evaluation surfaces have been removed.

## Remaining network work

1. Make every analyzer consume one immutable repository snapshot directly; Python already does, while the other analyzers currently scan the same filesystem independently.
2. Expand language and framework relation coverage only with deterministic resolver evidence and explicit unresolved boundaries.
3. Benchmark graph construction, query generation, and sampled betweenness on large repositories; record scale limits without changing metric meaning.
4. Add fixed local cross-language acceptance fixtures when broader real-world coverage is needed, avoiding network-dependent correctness tests.
