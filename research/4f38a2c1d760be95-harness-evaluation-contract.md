# Harness profile support and evaluation constraints

## Implemented baseline

`harness_profile.v1` records case-sensitive fixed-string content and path search, matching-line and matching-path caps, numeric line ordering within lexical paths, one-based inclusive range reads, EOF clamping, the maximum read range, list depth, and automatic injection as an unverified assumption. Semantic search and indexes are unsupported. Context compaction, parallelism, and subagents are observation-only capabilities.

The baseline provenance is `unverified_baseline`. Static replay reports repository facts under this configuration. It does not establish behavior of a particular agent or harness release.

Candidate metrics may include PageRank and directed in/out degree from the original Python architecture nodes and edges. These values explain a candidate after its rule has selected it. They do not select candidates, rank risk, or measure agent effort. The report records the PageRank implementation and its damping, tolerance, and iteration limit.

## Trace comparison

`harness_observation.v1` binds each trace to a snapshot digest and the complete profile content hash. Events preserve repeated calls, returned quantities, unknown fields represented by null, truncation or failure status, and explicit confirmation evidence. Comparisons use only returned fields whose values are known. A trace with no confirmation evidence remains unobserved for confirmation.

Legacy `agent_trace.v1` conversion uses caller-supplied snapshot and profile context. Its binding is unverified, returned ranges and text remain unknown, and output comparison stays disabled.

## Future before-and-after evaluation

No agent before-and-after experiment has been performed for this implementation. A future evaluation must freeze these items before execution:

- repository snapshot, harness profile, model and harness versions, task, required confirmation set, and outcome criteria;
- structural and harness changes as separate comparison factors;
- search rows, read ranges, repeated exposure, preparation work, failed calls, confirmations, and final task outcome for every run;
- success as reduced observed exploration burden with the required confirmations and task outcome preserved.

Runs that fail or stop during preparation remain in the evaluation set with their incurred calls. Duplicate reads and searches remain separate calls and contribute duplicate exposure. Structural replay and harness-output agreement are reported separately from agent outcomes. Probability, general risk score, and claims about real effort require independent calibration and are not outputs of the current baseline.
