from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

AXES = (
    "exploration_turns",
    "search_tool_calls",
    "read_tool_calls",
    "query_result_tokens",
    "readable_node_tokens",
    "zero_result_queries",
    "revisits",
    "exposed_non_target_candidates",
    "duplicate_occurrences",
)


class PolicyError(ValueError):
    pass


class WeightsError(ValueError):
    pass


class ScenarioError(ValueError):
    pass


class SeedQueryError(ValueError):
    pass


class InvariantError(RuntimeError):
    pass


@dataclass(frozen=True)
class CostVector:
    exploration_turns: int = 0
    search_tool_calls: int = 0
    read_tool_calls: int = 0
    query_result_tokens: int = 0
    readable_node_tokens: int = 0
    zero_result_queries: int = 0
    revisits: int = 0
    exposed_non_target_candidates: int = 0
    duplicate_occurrences: int = 0

    def add(self, **deltas: int) -> "CostVector":
        unknown = sorted(set(deltas) - set(AXES))
        if unknown:
            raise KeyError(f"unknown cost axis: {unknown[0]}")
        return CostVector(**{axis: getattr(self, axis) + deltas.get(axis, 0) for axis in AXES})

    def values(self) -> Dict[str, int]:
        return {axis: getattr(self, axis) for axis in AXES}


@dataclass(frozen=True)
class Observations:
    discovery_turn_index: Dict[str, int] = field(default_factory=dict)
    unread_targets: List[str] = field(default_factory=list)
    hinted_unread_nodes: int = 0
    duplicate_suppressed_queries: int = 0


@dataclass(frozen=True)
class ExecutionStep:
    step: int
    phase: str
    action: str
    id: str
    turn: int
    cost_delta: Dict[str, int]


@dataclass(frozen=True)
class Sample:
    index: int
    seed: int
    cost: CostVector
    observations: Observations
    sequence: Tuple[ExecutionStep, ...]
    status: str
    unreached_targets: Tuple[str, ...]
    id_sequence: Tuple[str, ...]


@dataclass(frozen=True)
class SeedTerm:
    term: str
    surface: str


@dataclass(frozen=True)
class Scenario:
    id: str
    task: str
    target_node_ids: Tuple[str, ...]
    seed_terms: Tuple[SeedTerm, ...] = ()


@dataclass(frozen=True)
class SeedQuerySet:
    source: str
    terms: Tuple[SeedTerm, ...]
    generator: Dict[str, Any]
