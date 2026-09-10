# Harness profile support and evaluation constraints

## Implemented baseline

`harness_profile.v1` records case-sensitive fixed-string content and path search, matching-line and matching-path caps, numeric line ordering within lexical paths, one-based inclusive range reads, EOF clamping, the maximum read range, list depth, and automatic injection as an unverified assumption. Semantic search and indexes are unsupported. Context compaction, parallelism, and subagents are observation-only capabilities.

The baseline provenance is `unverified_baseline`. Static replay reports repository facts under this configuration. It does not establish behavior of a particular agent or harness release.

Candidate metrics may include PageRank and directed in/out degree from the original Python architecture nodes and edges. These values explain a candidate after its rule has selected it. They do not select candidates, rank risk, or measure agent effort. The report records the PageRank implementation and its damping, tolerance, and iteration limit.

## Trace comparison

`harness_observation.v1` binds each trace to a snapshot digest and the complete profile content hash. Events preserve repeated calls, returned quantities, unknown fields represented by null, truncation or failure status, and explicit confirmation evidence. Comparisons use only returned fields whose values are known. A trace with no confirmation evidence remains unobserved for confirmation.

`harness_support.v1` records the support and provenance state for every scalar profile setting. `harness_evaluation_case.v1` fixes confirmation, outcome, snapshot, profile, and comparison-cell inputs. `harness_evaluation_run.v1` binds an embedded observation trace to one cell. `python -m bottlenecks.evaluation` deterministically evaluates or compares these recorded inputs without calling an agent or live harness.

Legacy `agent_trace.v1` conversion uses caller-supplied snapshot and profile context. Its binding is unverified, returned ranges and text remain unknown, and output comparison stays disabled.

## M2–M7 handoff to M8

M2–M7 use deterministic replay and independent inline change, mutation, or contract cases without live harness or agent calls. Their tests verify functional results, errors, and invariants without pinning a full-output hash or golden artifact. Passing checks the declared static contract; it does not establish agreement with a live harness. The milestone completion criteria are maintained in [ROADMAP.md](../ROADMAP.md#로드맵).

| Prepared in | Inputs handed to M8 | Claims remaining `unverified` until live evaluation |
|---|---|---|
| M2 | Profile support and provenance, trace contract, independent case definitions, confirmation and outcome criteria, comparison plan | Team harness baseline agreement |
| M3 | Global candidates with evidence, probes, profile conditions and coverage | Candidate behavior in agent runs |
| M4 | Independent review candidates and change, mutation or contract cases with omission and excess-candidate checks | Usefulness during agent review |
| M5 | Reproducible changes, before/after snapshots and profiles, deterministic what-if expectations | Reduced effort with confirmations and outcomes preserved |
| M6 | Review evidence joined to static exposure conditions, with extraction errors evaluated separately | Actual exploration or confirmation omissions and combined usefulness |
| M7 | Versioned corpus and profiles, calibration/validation split, execution conditions, calibration procedure and static regression results | Calibration quality and generalization across environments |

These are evaluation inputs. Fixed trace comparison remains available before M8; collecting live traces and using them to validate behavior belongs to M8.

## M8 before-and-after evaluation

No agent before-and-after experiment has been performed for this implementation. M2–M7 prepare the inputs and retain live-dependent results as `unverified`; M8 must freeze these items before repeated live execution:

- repository snapshot, harness profile, model and harness versions, task, required confirmation set, and outcome criteria;
- structural and harness changes as separate comparison factors;
- search rows, read ranges, repeated exposure, preparation work, failed calls, confirmations, and final task outcome for every run;
- success as reduced observed exploration burden with the required confirmations and task outcome preserved.

Runs that fail or stop during preparation remain in the evaluation set with their incurred calls. Duplicate reads and searches remain separate calls and contribute duplicate exposure. Structural replay and harness-output agreement are reported separately from agent outcomes. Probability, general risk score, and claims about real effort require independent calibration and are not outputs of the current baseline.
