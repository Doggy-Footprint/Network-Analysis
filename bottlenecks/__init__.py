from .core import (
    BottleneckInputError, BottleneckReport, HarnessProfile, HarnessProfileError,
    ObservationTrace, ObservationTraceError, Probe, ProbeOutput,
    analyze_bottlenecks, bottlenecks_to_json, convert_legacy_trace, parse_harness_profile,
    parse_observation_trace, replay_probe,
)


_EVALUATION_EXPORTS = {
    "EvaluationCase", "EvaluationCaseError", "EvaluationComparisonError",
    "EvaluationRun", "EvaluationRunError", "HarnessSupport", "HarnessSupportError",
    "RunComparison", "RunEvaluation", "compare_runs", "evaluate_run",
    "evaluation_to_json", "parse_evaluation_case", "parse_evaluation_run",
    "parse_harness_support",
}


def __getattr__(name):
    if name in _EVALUATION_EXPORTS:
        from . import evaluation
        return getattr(evaluation, name)
    raise AttributeError(name)

__all__ = [
    "BottleneckInputError", "BottleneckReport", "HarnessProfile",
    "HarnessProfileError", "ObservationTrace", "ObservationTraceError", "Probe",
    "ProbeOutput", "analyze_bottlenecks", "bottlenecks_to_json", "convert_legacy_trace",
    "parse_harness_profile", "parse_observation_trace", "replay_probe",
    "EvaluationCase", "EvaluationCaseError", "EvaluationComparisonError",
    "EvaluationRun", "EvaluationRunError", "HarnessSupport", "HarnessSupportError",
    "RunComparison", "RunEvaluation", "compare_runs", "evaluate_run",
    "evaluation_to_json", "parse_evaluation_case", "parse_evaluation_run",
    "parse_harness_support",
]
