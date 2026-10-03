# Code Analyzer for AI Agents

Finds structural bottlenecks in a repository's dependency network so that a human or an AI agent can decide what to refactor.

The analyzer reads an immutable snapshot of the repository, builds a dependency graph from language analyzers and framework adapters, and ranks nodes by network position and token cost. Relations it cannot confirm are kept with a lower edge weight instead of being discarded, so bottlenecks that depend on inferred or ambiguous links still appear.

## Analyzers

- Languages (`-l`): `python`, `typescript`, `kotlin`
- Frameworks (`-f`): `fastapi`, `android`, `sqlalchemy`, `nestjs`

`-l` and `-f` can be repeated and mixed; analyzers run in argument order, and cross-analyzer links such as client HTTP calls to server routes are resolved over the combined graph.

## Usage

```sh
python -m code_analyzer <project_path> -f fastapi --bottlenecks report.json --bottlenecks-html report.html
```

- `-o PATH`: interactive architecture dashboard (HTML); `--json` also writes the graph as JSON.
- `--bottlenecks PATH`, `--bottlenecks-html PATH`: `bottlenecks.v4` report — centrality and token-cost rankings, rankings split by source category, and candidates (`unresolved_boundary`, `evidence_spread`, `large_node`).
- `--edge-weights PATH`: edge-weight profile (default `profiles/edge_weights.v1.yaml`).

## Profiles

Values that change results live in files under `profiles/`.

- `snapshot.v1.yaml`: which files enter the snapshot.
- `edge_weights.v1.yaml`: weight per confidence and resolution grade (non-certain grades default to 0.3) and the `large_node` line threshold. Weights affect PageRank, HITS, and weighted fan-in/out only; betweenness, hop costs, and fan counts stay structural.

## Development

```sh
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

`archive/` keeps the retired agent-exploration model (agent view, probe replay, M1 report) for reference; it is neither imported by the pipeline nor collected by pytest.

## Project records

- [Agent instructions](AGENTS.md) and [CLAUDE.md](CLAUDE.md)
- [Open handoffs](agent-docs/handoff/index.md)
- [Open issues](agent-docs/issues/index.md)
- [Architecture decisions](adr/index.md)
