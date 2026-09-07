import random
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from .graph_view import GraphView
from .models import (
    CostVector,
    ExecutionStep,
    Observations,
    Sample,
    Scenario,
    SeedTerm,
)
from .policy import ExplorationPolicy
from .weights import CostWeights


@dataclass(frozen=True)
class PhaseAResult:
    cost: CostVector
    steps: Tuple[ExecutionStep, ...]
    read_units: Tuple[str, ...]
    executed_query_ids: Tuple[str, ...]
    open_groups: Tuple[str, ...]
    seed_query_ids: Tuple[str, ...]
    initial_pending_query_ids: Tuple[str, ...]
    unmatched_terms: Tuple[SeedTerm, ...]
    hinted_nodes: Tuple[str, ...]
    exposed_nodes: Tuple[str, ...]
    repo_map_node_ids: Tuple[str, ...]
    repo_map_tokens: int
    discovery_turn_index: Dict[str, int]
    id_sequence: Tuple[str, ...]
    turn: int


class _State:
    def __init__(self, view: GraphView, scenario: Scenario, policy: ExplorationPolicy):
        self.view = view
        self.policy = policy
        self.cost = CostVector()
        self.steps: List[ExecutionStep] = []
        self.read_units: Set[str] = set()
        self.executed: Set[str] = set()
        self.hinted: Set[str] = set()
        self.exposed: Set[str] = set()
        self.discovery_turn_index: Dict[str, int] = {}
        self.id_sequence: List[str] = []
        self.turn = 0
        self.duplicate_suppressed_queries = 0
        self.targets = tuple(scenario.target_node_ids)
        self.target_set = set(self.targets)
        self.target_units = {view.unit_of_node[node_id] for node_id in self.targets}

    def record(self, phase: str, action: str, identifier: str, **deltas: int) -> None:
        self.cost = self.cost.add(**deltas)
        self.steps.append(
            ExecutionStep(
                step=len(self.steps),
                phase=phase,
                action=action,
                id=identifier,
                turn=self.turn,
                cost_delta={key: value for key, value in deltas.items() if value},
            )
        )

    def all_found(self) -> bool:
        return self.target_units <= self.read_units

    def read_unit(self, phase: str, unit_id: str, charge_tool_call: bool = True) -> None:
        self.read_units.add(unit_id)
        self.id_sequence.append(self.view.unit_label(unit_id))
        self.record(
            phase,
            "read",
            unit_id,
            read_tool_calls=1 if charge_tool_call else 0,
            readable_node_tokens=self.view.unit_tokens(unit_id),
        )
        for node_id in self.view.nodes_in_unit.get(unit_id, ()):
            if node_id in self.target_set and node_id not in self.discovery_turn_index:
                self.discovery_turn_index[node_id] = self.turn

    def execute(self, phase: str, query_id: str) -> None:
        query = self.view.queries[query_id]
        arrivals = self.view.arrivals.get(query_id, ())
        self.turn += 1
        self.executed.add(query_id)
        self.hinted.update(arrivals)
        self.exposed.update(arrivals)
        self.record(
            phase,
            "search",
            query_id,
            exploration_turns=1,
            search_tool_calls=1,
            query_result_tokens=query.output_tokens,
            zero_result_queries=1 if query.visible_count == 0 else 0,
            exposed_non_target_candidates=len(set(arrivals) - self.target_set),
            duplicate_occurrences=max(0, query.visible_count - len(arrivals)),
        )


def _read_direct_closure(state: _State, phase: str, unit_id: str, *, charge_tool_call: bool = True) -> List[str]:
    generated: List[str] = []
    pending_units = [(unit_id, charge_tool_call)]
    while pending_units:
        current_unit_id, current_charge = pending_units.pop(0)
        if current_unit_id in state.read_units:
            continue
        state.read_unit(phase, current_unit_id, charge_tool_call=current_charge)
        generated.extend(state.view.queries_from_unit.get(current_unit_id, ()))
        direct_units: Set[str] = set()
        for node_id in state.view.nodes_in_unit.get(current_unit_id, ()):
            for target_node_id in state.view.direct_out.get(node_id, ()):
                target_unit_id = state.view.unit_of_node[target_node_id]
                if target_unit_id not in state.read_units:
                    direct_units.add(target_unit_id)
        pending_units.extend((target_unit_id, True) for target_unit_id in sorted(direct_units))
    return generated


def _seed_order_key(view: GraphView, query_id: str) -> Tuple[str, str]:
    query = view.queries[query_id]
    return query.surface, query.term


def run_phase_a(view: GraphView, scenario: Scenario, policy: ExplorationPolicy) -> PhaseAResult:
    state = _State(view, scenario, policy)
    initial_pending: Set[str] = set()

    for document in view.entry_documents:
        unit_id = view.unit_of_node.get(document.node_id)
        if unit_id is None or unit_id in state.read_units:
            continue
        initial_pending.update(
            _read_direct_closure(
                state, "A", unit_id, charge_tool_call=not document.injected
            )
        )

    open_groups: List[str] = []
    if policy.root_list_query and view.root_list_query_id is not None:
        state.execute("A", view.root_list_query_id)
        open_groups.append(view.root_list_query_id)

    repo_map_nodes: Tuple[str, ...] = ()
    repo_map_tokens = 0
    if policy.repo_map_enabled:
        repo_map_nodes, repo_map_tokens = view.repo_map(
            policy.repo_map_max_entries, policy.repo_map_token_budget
        )
        state.hinted.update(repo_map_nodes)
        state.record("A", "inject", "repo_map", query_result_tokens=repo_map_tokens)

    seed_query_ids: List[str] = []
    unmatched: List[SeedTerm] = []
    for term in sorted(set(scenario.seed_terms), key=lambda item: (item.surface, item.term)):
        query_id = view.query_by_term.get((term.term, term.surface))
        if query_id is None:
            unmatched.append(term)
            state.turn += 1
            state.record(
                "A",
                "search",
                f"seed:{term.surface}:{term.term}",
                exploration_turns=1,
                search_tool_calls=1,
                zero_result_queries=1,
            )
        elif query_id not in seed_query_ids:
            seed_query_ids.append(query_id)

    return PhaseAResult(
        cost=state.cost,
        steps=tuple(state.steps),
        read_units=tuple(sorted(state.read_units)),
        executed_query_ids=tuple(sorted(state.executed)),
        open_groups=tuple(open_groups),
        seed_query_ids=tuple(seed_query_ids),
        initial_pending_query_ids=tuple(sorted(initial_pending)),
        unmatched_terms=tuple(unmatched),
        hinted_nodes=tuple(sorted(state.hinted)),
        exposed_nodes=tuple(sorted(state.exposed)),
        repo_map_node_ids=repo_map_nodes,
        repo_map_tokens=repo_map_tokens,
        discovery_turn_index=dict(state.discovery_turn_index),
        id_sequence=tuple(state.id_sequence),
        turn=state.turn,
    )


def _order_arrivals(
    view: GraphView,
    policy: ExplorationPolicy,
    query_id: str,
    rng: random.Random,
) -> List[str]:
    arrivals = list(view.arrivals.get(query_id, ()))
    if len(arrivals) < 2:
        return arrivals
    if policy.result_ordering == "uniform":
        rng.shuffle(arrivals)
        return arrivals
    scores = list(view.arrival_scores(query_id, policy))
    ordered: List[str] = []
    while arrivals:
        total = sum(scores)
        threshold = rng.random() * total
        accumulated = 0.0
        chosen = len(arrivals) - 1
        for position, weight in enumerate(scores):
            accumulated += weight
            if threshold < accumulated:
                chosen = position
                break
        ordered.append(arrivals.pop(chosen))
        scores.pop(chosen)
    return ordered


def _select(
    view: GraphView,
    policy: ExplorationPolicy,
    pending: Set[str],
    rng: random.Random,
) -> str:
    candidates = sorted(pending)
    if policy.phase_b_policy == "best-first-pivot":
        return min(candidates, key=lambda query_id: (-view.query_score(query_id, policy), query_id))
    return candidates[rng.randrange(len(candidates))]


def run_sample(
    view: GraphView,
    scenario: Scenario,
    policy: ExplorationPolicy,
    weights: CostWeights,
    rng: random.Random,
    index: int,
    seed: int,
) -> Sample:
    phase_a = run_phase_a(view, scenario, policy)
    state = _State(view, scenario, policy)
    state.cost = phase_a.cost
    state.steps = list(phase_a.steps)
    state.read_units = set(phase_a.read_units)
    state.executed = set(phase_a.executed_query_ids)
    state.hinted = set(phase_a.hinted_nodes)
    state.exposed = set(phase_a.exposed_nodes)
    state.discovery_turn_index = dict(phase_a.discovery_turn_index)
    state.id_sequence = list(phase_a.id_sequence)
    state.turn = phase_a.turn

    pending: Set[str] = set(phase_a.initial_pending_query_ids) - state.executed
    open_groups: List[str] = list(phase_a.open_groups)
    # ROADMAP: the seed query set is input, not a choice, so every matched seed query is
    # charged as executed in every sample even when phase A already discharged every target.
    for query_id in sorted(
        set(phase_a.seed_query_ids) - state.executed,
        key=lambda item: _seed_order_key(view, item),
    ):
        state.execute("B", query_id)
        open_groups.append(query_id)

    status = "complete"
    while True:
        if state.all_found():
            break
        if open_groups:
            query_id = open_groups.pop(0)
        elif pending:
            query_id = _select(view, policy, pending, rng)
            pending.discard(query_id)
            state.execute("B", query_id)
        else:
            status = "unreachable"
            break

        queued: List[str] = []
        group_best = (
            view.query_score(query_id, policy)
            if policy.phase_b_policy == "best-first-pivot"
            else 0.0
        )
        for node_id in _order_arrivals(view, policy, query_id, rng):
            if state.all_found():
                break
            unit_id = view.unit_of_node[node_id]
            if unit_id in state.read_units:
                continue
            queued.extend(_read_direct_closure(state, "B", unit_id))
            if policy.phase_b_policy == "best-first-pivot" and any(
                view.query_score(candidate, policy) > group_best
                for candidate in queued
                if candidate not in state.executed and candidate not in pending
            ):
                break
        queued.extend(view.queries_from_query.get(query_id, ()))
        for candidate in queued:
            if candidate in state.executed:
                state.duplicate_suppressed_queries += 1
            else:
                pending.add(candidate)

    unreached = tuple(
        node_id
        for node_id in sorted(state.target_set)
        if view.unit_of_node[node_id] not in state.read_units
    )
    observations = Observations(
        discovery_turn_index=dict(sorted(state.discovery_turn_index.items())),
        unread_targets=[node_id for node_id in unreached if node_id in state.exposed],
        hinted_unread_nodes=sum(
            1
            for node_id in state.hinted
            if view.unit_of_node.get(node_id) not in state.read_units
        ),
        duplicate_suppressed_queries=state.duplicate_suppressed_queries,
    )
    return Sample(
        index=index,
        seed=seed,
        cost=state.cost,
        observations=observations,
        sequence=tuple(state.steps),
        status=status,
        unreached_targets=unreached,
        id_sequence=tuple(state.id_sequence),
    )
