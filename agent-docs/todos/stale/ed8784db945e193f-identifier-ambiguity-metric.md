# Add identifier occurrence ambiguity as a node attribute

## Goal

“아직 안 한것들 handoff 들로 작성해줘” — 재구조화(커밋 `2a340fb`) 이후 남은 작업.

## Purpose

Expose how widely a node's identifier occurs across the repository as a static ambiguity signal on dependency nodes.

## State

- Branch: `polish`; base commit: `2a340fb`.
- Changed files for this handoff: this file and `agent-docs/handoff/index.md`.
- `archive/agent_view/occurrence.py` and `archive/agent_view/exact_query.py` computed repository-wide identifier occurrences for the archived exploration graph.
- Active code has no occurrence count on dependency nodes.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| None recorded | — | — |

## Next Step

Reimplement (do not import from `archive/`) a deterministic count of exact identifier occurrences per node name over the snapshot, attach it to node metrics in `analysis/graph_metrics.py` or `bottlenecks/core.py`, and decide whether it produces a new candidate kind.

## Open Questions

- Count unit: files, lines, or occurrences?
- Metric only, or also a candidate kind with a threshold in `profiles/edge_weights.v1.yaml`?

## Spec

No workflow spec exists for this handoff. Version, status, and run ID: not applicable.

## Execution Ledger

- Finding: occurrence logic exists only in archive; disposition: reimplement in active code if selected.
- Evidence and mutation outcomes: source inspection only; no implementation mutation or verification run.
- Correction count: 0; verifier count: 0.
