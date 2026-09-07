from typing import Sequence, Set, Tuple

from .graph_view import GraphView
from .models import CostVector, Scenario
from .policy import ExplorationPolicy
from .simulate import PhaseAResult


def reachable_sets(
    view: GraphView,
    seed_query_ids: Sequence[str],
    phase_a: PhaseAResult,
) -> Tuple[Set[str], Set[str]]:
    queries: Set[str] = {
        query_id
        for query_id in (
            set(phase_a.executed_query_ids)
            | set(seed_query_ids)
            | set(phase_a.initial_pending_query_ids)
        )
        if query_id in view.queries
    }
    units: Set[str] = set(phase_a.read_units)
    frontier_queries = set(queries)
    frontier_units = set(units)
    while frontier_queries or frontier_units:
        next_queries: Set[str] = set()
        next_units: Set[str] = set()
        for query_id in frontier_queries:
            for node_id in view.arrivals.get(query_id, ()):
                unit_id = view.unit_of_node.get(node_id)
                if unit_id is not None and unit_id not in units:
                    units.add(unit_id)
                    next_units.add(unit_id)
            for candidate in view.queries_from_query.get(query_id, ()):
                if candidate in view.queries and candidate not in queries:
                    queries.add(candidate)
                    next_queries.add(candidate)
        for unit_id in frontier_units:
            for candidate in view.queries_from_unit.get(unit_id, ()):
                if candidate in view.queries and candidate not in queries:
                    queries.add(candidate)
                    next_queries.add(candidate)
            for node_id in view.nodes_in_unit.get(unit_id, ()):
                for target_node_id in view.direct_out.get(node_id, ()):
                    target_unit_id = view.unit_of_node[target_node_id]
                    if target_unit_id not in units:
                        units.add(target_unit_id)
                        next_units.add(target_unit_id)
        frontier_queries, frontier_units = next_queries, next_units
    return queries, units


def compute_closure(
    view: GraphView,
    scenario: Scenario,
    policy: ExplorationPolicy,
    seed_query_ids: Sequence[str],
    phase_a: PhaseAResult,
) -> CostVector:
    queries, units = reachable_sets(view, seed_query_ids, phase_a)
    targets = set(scenario.target_node_ids)
    # Phase-A cost is added whole and its queries and units are then skipped: repo-map tokens,
    # unmatched seed terms and the injected-document read discount exist only in phase A, and
    # axis(sample) <= axis(closure) fails on those axes if they are recomputed from the graph.
    cost = phase_a.cost
    for query_id in sorted(queries - set(phase_a.executed_query_ids)):
        query = view.queries[query_id]
        arrivals = view.arrivals.get(query_id, ())
        cost = cost.add(
            exploration_turns=1,
            search_tool_calls=1,
            query_result_tokens=query.output_tokens,
            zero_result_queries=1 if query.visible_count == 0 else 0,
            exposed_non_target_candidates=len(set(arrivals) - targets),
            duplicate_occurrences=max(0, query.visible_count - len(arrivals)),
        )
    for unit_id in sorted(units - set(phase_a.read_units)):
        cost = cost.add(read_tool_calls=1, readable_node_tokens=view.unit_tokens(unit_id))
    return cost
