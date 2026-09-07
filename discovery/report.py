import json
from dataclasses import asdict
from typing import Any, Dict, Mapping, Sequence

from agent_view.models import AgentViewGraph
from agent_view.profile import Profile

from .graph_view import GraphView
from .models import AXES, SeedQuerySet, SeedTerm
from .montecarlo import PERCENTILE_METHOD, ScenarioResult
from .policy import ExplorationPolicy
from .weights import CostWeights

SCHEMA = "phase_b_cost.v1"
PHASE_B_SCHEMA_VERSION = "1"


def _profile_ref(ref) -> Dict[str, Any]:
    return {"id": ref.id, "version": ref.version, "content_hash": ref.content_hash}


def _terms(terms: Sequence[SeedTerm]) -> list:
    return [{"term": item.term, "surface": item.surface} for item in terms]


def _versions(
    profile: Profile,
    policy: ExplorationPolicy,
    weights: CostWeights,
    generator: Mapping[str, Any],
) -> list:
    stamps = {
        "cost_weights": f"{weights.ref.id}:{weights.ref.version}",
        "derived_rules": f"{profile.ref.id}:{profile.ref.version}",
        "exclusions": f"{profile.ref.id}:{profile.ref.version}",
        "ordering": profile.ordering_version,
        "output_format": profile.output_format_version,
        "phase_b_schema": PHASE_B_SCHEMA_VERSION,
        "policy": f"{policy.ref.id}:{policy.ref.version}",
        "query_equivalence": profile.query_equivalence_version,
        "seed_query_generator": f"{generator.get('model_id')}:{generator.get('revision')}",
        "split": profile.split_version,
        "tie_break": policy.tie_break_version,
        "tokenizer": profile.tokenizer_version,
    }
    return [{"id": key, "version": stamps[key]} for key in sorted(stamps)]


def _percentile(entry: Dict[str, Any]) -> Dict[str, Any]:
    sample = entry["sample"]
    return {
        "rank": entry["rank"],
        "weighted_cost": entry["weighted_cost"],
        "axes": sample.cost.values(),
        "observations": {
            "discovery_turn_index": dict(sample.observations.discovery_turn_index),
            "unread_targets": list(sample.observations.unread_targets),
            "hinted_unread_nodes": sample.observations.hinted_unread_nodes,
            "duplicate_suppressed_queries": sample.observations.duplicate_suppressed_queries,
        },
        "execution_sequence": [asdict(step) for step in sample.sequence],
        "bootstrap_ci": entry["bootstrap_ci"],
        "bootstrap_ci_reason": entry["bootstrap_ci_reason"],
    }


def _scenario_payload(
    view: GraphView,
    result: ScenarioResult,
    seed_set: SeedQuerySet,
) -> Dict[str, Any]:
    scenario = result.scenario
    phase_a = result.phase_a
    representative = result.percentiles["p50"]["sample"]
    return {
        "id": scenario.id,
        "task": scenario.task,
        "targets": [
            {
                "node_id": node_id,
                "file_path": view.readable[node_id].file_path,
                "label": view.readable[node_id].label,
                "read_unit_id": view.unit_of_node[node_id],
            }
            for node_id in scenario.target_node_ids
        ],
        "seed_queries": {
            "source": seed_set.source,
            "terms": _terms(seed_set.terms),
            "resolved_query_ids": list(phase_a.seed_query_ids),
            "unmatched_terms": _terms(phase_a.unmatched_terms),
        },
        "phase_a": {
            "entry_documents": [
                {
                    "node_id": document.node_id,
                    "file_path": document.file_path,
                    "injected": document.injected,
                }
                for document in view.entry_documents
            ],
            "root_list_query_id": view.root_list_query_id,
            "repo_map_entry_count": len(phase_a.repo_map_node_ids),
            "repo_map_tokens": phase_a.repo_map_tokens,
            "axes": phase_a.cost.values(),
        },
        "sample_count": result.sample_count,
        "converged": result.converged,
        "seed": result.seed,
        "percentile_method": PERCENTILE_METHOD,
        "percentiles": {
            name: _percentile(result.percentiles[name]) for name in ("p5", "p50", "p95")
        },
        "axis_statistics": {axis: result.axis_statistics[axis] for axis in AXES},
        "closure": {
            "axes": result.closure.values(),
            "weighted_cost": result.closure_weighted_cost,
            "query_count": result.closure_query_count,
            "read_unit_count": result.closure_read_unit_count,
        },
        "invariants": result.invariants,
        "reachability": {
            "status": representative.status,
            "unreached_targets": list(representative.unreached_targets),
            "incomplete_sample_count": result.incomplete_sample_count,
        },
    }


def build_report(
    graph: AgentViewGraph,
    view: GraphView,
    scenario_results: Sequence[ScenarioResult],
    profile: Profile,
    policy: ExplorationPolicy,
    weights: CostWeights,
    seed_sets: Mapping[str, SeedQuerySet],
) -> Dict[str, Any]:
    ordered_sets = [seed_sets[result.scenario.id] for result in scenario_results]
    generator = next(
        (item.generator for item in ordered_sets if item.source == "cache"),
        ordered_sets[0].generator if ordered_sets else {},
    )
    return {
        "schema": SCHEMA,
        "project_name": graph.project_name,
        "snapshot_digest": graph.scan.snapshot_digest,
        "profiles": {
            "agent_view": _profile_ref(profile.ref),
            "exploration_policy": _profile_ref(policy.ref),
            "cost_weights": _profile_ref(weights.ref),
        },
        "seed_query_generator": dict(generator),
        "versions": _versions(profile, policy, weights, generator),
        "scenarios": [
            _scenario_payload(view, result, seed_sets[result.scenario.id])
            for result in scenario_results
        ],
    }


def report_to_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
