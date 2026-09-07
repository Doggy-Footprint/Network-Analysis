from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent_view.models import AgentViewGraph, EntryDocument, QueryNode, ReadableNode, ReadUnit
from analysis import pagerank
from language_analyzers.core.cost import estimate_tokens

_HINT_CLAMP = 1e-9


class GraphView:
    def __init__(self, graph: AgentViewGraph):
        self.graph = graph
        self.readable: Dict[str, ReadableNode] = {node.id: node for node in graph.readable_nodes}
        self.read_units: Dict[str, ReadUnit] = {unit.id: unit for unit in graph.read_units}
        self.queries: Dict[str, QueryNode] = {query.id: query for query in graph.query_nodes}

        self.unit_of_node: Dict[str, str] = {
            node.id: node.read_unit_id for node in graph.readable_nodes
        }
        nodes_in_unit: Dict[str, List[str]] = defaultdict(list)
        for node in graph.readable_nodes:
            nodes_in_unit[node.read_unit_id].append(node.id)
        self.nodes_in_unit: Dict[str, Tuple[str, ...]] = {
            unit_id: tuple(sorted(members)) for unit_id, members in sorted(nodes_in_unit.items())
        }

        generated: Dict[str, set] = defaultdict(set)
        from_query: Dict[str, set] = defaultdict(set)
        static_out: Dict[str, set] = defaultdict(set)
        direct_out: Dict[str, set] = defaultdict(set)
        self.hint_of: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for connection in graph.connections:
            if connection.kind == "generates":
                unit_id = self.unit_of_node.get(connection.from_id)
                if unit_id is not None:
                    generated[unit_id].add(connection.to_id)
            elif connection.kind in ("hint_query", "refines"):
                from_query[connection.from_id].add(connection.to_id)
            elif connection.kind == "static":
                static_out[connection.from_id].add(connection.to_id)
                if connection.specificity == "unique":
                    direct_out[connection.from_id].add(connection.to_id)
            elif connection.kind == "result":
                hint = graph.hint_store.get(connection.evidence.get("hint_id"))
                if hint is not None:
                    self.hint_of[(connection.from_id, connection.to_id)] = hint

        self.queries_from_unit: Dict[str, Tuple[str, ...]] = {
            unit_id: tuple(sorted(values)) for unit_id, values in sorted(generated.items())
        }
        self.queries_from_query: Dict[str, Tuple[str, ...]] = {
            query_id: tuple(sorted(values)) for query_id, values in sorted(from_query.items())
        }
        self.static_out: Dict[str, Tuple[str, ...]] = {
            node_id: tuple(sorted(target for target in values if target in self.readable))
            for node_id, values in sorted(static_out.items())
            if node_id in self.readable
        }
        self.direct_out: Dict[str, Tuple[str, ...]] = {
            node_id: tuple(sorted(target for target in values if target in self.readable))
            for node_id, values in sorted(direct_out.items())
            if node_id in self.readable
        }
        self.arrivals: Dict[str, Tuple[str, ...]] = {
            query.id: tuple(query.arrival_node_ids) for query in graph.query_nodes
        }
        self.query_by_term: Dict[Tuple[str, str], str] = {
            (query.term, query.surface): query.id for query in graph.query_nodes
        }
        self.entry_documents: Tuple[EntryDocument, ...] = tuple(graph.entry_documents)
        self.root_list_query_id: Optional[str] = next(
            (
                query.id
                for query in graph.query_nodes
                if query.kind == "list" and query.scope == "root"
            ),
            None,
        )
        by_path: Dict[str, List[str]] = defaultdict(list)
        for node in graph.readable_nodes:
            by_path[node.file_path].append(node.id)
        self.nodes_by_path: Dict[str, Tuple[str, ...]] = {
            path: tuple(sorted(members)) for path, members in sorted(by_path.items())
        }
        self._repo_map: Dict[Tuple[int, int], Tuple[Tuple[str, ...], int]] = {}
        self._hint_policy_key: Any = None
        self._hint_scores: Dict[str, Tuple[float, ...]] = {}
        self._unit_label: Dict[str, str] = {}

    def repo_map(self, max_entries: int, token_budget: int) -> Tuple[Tuple[str, ...], int]:
        cached = self._repo_map.get((max_entries, token_budget))
        if cached is not None:
            return cached
        outgoing = {
            node_id: set(self.static_out.get(node_id, ())) for node_id in self.readable
        }
        scores = pagerank(outgoing)
        ranked = sorted(self.readable, key=lambda node_id: (-scores.get(node_id, 0.0), node_id))
        ranked = ranked[:max_entries]
        lines = [
            f"{self.readable[node_id].file_path}:{self.readable[node_id].label}"
            for node_id in ranked
        ]
        profile = self.graph.profile
        tokenizer = (
            profile.get("characters_per_token", 4),
            profile.get("digit_group_size", 3),
        )
        low, high = 0, len(lines)
        while low < high:
            middle = (low + high + 1) // 2
            if estimate_tokens("\n".join(lines[:middle]), *tokenizer) <= token_budget:
                low = middle
            else:
                high = middle - 1
        tokens = estimate_tokens("\n".join(lines[:low]), *tokenizer) if low else 0
        cached = (tuple(ranked[:low]), tokens)
        self._repo_map[(max_entries, token_budget)] = cached
        return cached

    def unit_tokens(self, unit_id: str) -> int:
        return self.read_units[unit_id].read_cost.token_estimate

    def unit_label(self, unit_id: str) -> str:
        cached = self._unit_label.get(unit_id)
        if cached is None:
            unit = self.read_units[unit_id]
            labels = ",".join(
                sorted(self.readable[node_id].label for node_id in self.nodes_in_unit.get(unit_id, ()))
            )
            cached = f"{unit.file_path}#{labels}"
            self._unit_label[unit_id] = cached
        return cached

    def hint_score(self, query_id: str, node_id: str, policy) -> float:
        hint = self.hint_of.get((query_id, node_id))
        if hint is None:
            return _HINT_CLAMP
        score = sum(policy.role_weights.get(role, 0.0) for role in hint.get("roles", ()))
        query = self.queries.get(query_id)
        if query is not None and Path(hint.get("file_name", "")).stem == query.term:
            score += policy.filename_exact_bonus
        return max(score, _HINT_CLAMP)

    def arrival_scores(self, query_id: str, policy) -> Tuple[float, ...]:
        key = (policy.filename_exact_bonus, tuple(sorted(policy.role_weights.items())))
        if key != self._hint_policy_key:
            self._hint_policy_key = key
            self._hint_scores = {}
        cached = self._hint_scores.get(query_id)
        if cached is None:
            cached = tuple(
                self.hint_score(query_id, node_id, policy)
                for node_id in self.arrivals.get(query_id, ())
            )
            self._hint_scores[query_id] = cached
        return cached

    def query_score(self, query_id: str, policy) -> float:
        scores = self.arrival_scores(query_id, policy)
        return max(scores) if scores else 0.0
