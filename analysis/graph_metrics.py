import json
import sys
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Set, Tuple, Union

from analysis.edge_weights import EdgeWeights
from analysis.candidate_projection import AMBIGUITY_POLICY, candidate_projection, edge_value
from language_analyzers.core.cost import CHARACTERS_PER_TOKEN, DIGIT_GROUP_SIZE, estimate_tokens
from language_analyzers.core.graph_models import Confidence, Resolution


def _display_name(node: Any, fallback: str) -> str:
    return getattr(node, "display_label", "") or getattr(node, "label", "") or fallback


@dataclass(frozen=True)
class GraphAnalysisConfig:
    damping: float = 0.85
    tolerance: float = 1e-10
    max_iterations: int = 100
    characters_per_token: float = CHARACTERS_PER_TOKEN
    digit_group_size: int = DIGIT_GROUP_SIZE
    exact_betweenness_threshold: int = 500
    betweenness_sample_size: int = 100
    betweenness_sampler: Optional[Callable[[Sequence[str], int], Sequence[str]]] = None
    edge_weights: Optional[EdgeWeights] = None
    neighborhood_memory_budget_bytes: int = 256 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.neighborhood_memory_budget_bytes < 0:
            raise ValueError("neighborhood_memory_budget_bytes must be nonnegative")


def pagerank(
    outgoing: Union[Mapping[str, Mapping[str, float]], Mapping[str, Set[str]]],
    config: Optional[GraphAnalysisConfig] = None,
) -> Dict[str, float]:
    settings = config or GraphAnalysisConfig()
    count = len(outgoing)
    if not count:
        return {}
    weighted = {
        node_id: targets if isinstance(targets, Mapping) else {target: 1.0 for target in targets}
        for node_id, targets in outgoing.items()
    }
    totals = {node_id: sum(targets.values()) for node_id, targets in weighted.items()}
    scores = {node_id: 1.0 / count for node_id in outgoing}
    base = (1.0 - settings.damping) / count

    for _ in range(settings.max_iterations):
        dangling = sum(scores[node_id] for node_id, targets in weighted.items() if not targets)
        residual = 0.0
        for source, targets in weighted.items():
            if targets:
                residual += settings.damping * scores[source] * (1.0 - totals[source] / len(targets))
        updated = {node_id: base + (settings.damping * dangling + residual) / count for node_id in outgoing}
        for source, targets in weighted.items():
            if not targets:
                continue
            share = settings.damping * scores[source] / len(targets)
            for target, weight in targets.items():
                updated[target] += share * weight
        if sum(abs(updated[item] - scores[item]) for item in scores) <= settings.tolerance:
            scores = updated
            break
        scores = updated
    return scores


class GraphAnalyzer:
    def __init__(self, config: Optional[GraphAnalysisConfig] = None):
        self.config = config or GraphAnalysisConfig()

    def analyze(
        self,
        nodes: Sequence[Any],
        edges: Sequence[Any],
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        node_by_id = {node.id: node for node in nodes}
        outgoing = {node_id: set() for node_id in node_by_id}
        incoming = {node_id: set() for node_id in node_by_id}
        pair_weights: Dict[Tuple[str, str], float] = {}

        for edge in edges:
            source = self._edge_value(edge, "from_id", "from")
            projection = candidate_projection(edge)
            if str(edge_value(edge, "resolution", "exact")) != "ambiguous" and (
                    source not in node_by_id or any(target not in node_by_id for target, _ in projection)):
                continue
            for target, share in candidate_projection(edge, node_by_id):
                if source == target:
                    continue
                outgoing[source].add(target)
                incoming[target].add(source)
                weight = self._edge_weight(edge) * share
                pair = (source, target)
                pair_weights[pair] = max(pair_weights.get(pair, 0.0), weight)

        token_costs = {
            node_id: self._node_token_cost(node)
            for node_id, node in node_by_id.items()
        }
        effective_token_costs = {
            node_id: token_costs[node_id] * self._cost_multiplier(node)
            for node_id, node in node_by_id.items()
        }
        weighted_outgoing = {
            node_id: {target: pair_weights[(node_id, target)] for target in targets}
            for node_id, targets in outgoing.items()
        }
        pagerank = self._pagerank(weighted_outgoing)
        betweenness, betweenness_strategy, betweenness_sample_size = self._betweenness_for_graph(outgoing)
        undirected = {
            node_id: outgoing[node_id] | incoming[node_id]
            for node_id in node_by_id
        }
        tick_costs = {
            node_id: token_costs[node_id] * round(10 * self._cost_multiplier(node))
            for node_id, node in node_by_id.items()
        }
        neighborhood_costs, neighborhood_strategy = self._neighborhood_metrics(undirected, tick_costs)

        metrics: Dict[str, Dict[str, Any]] = {}
        for node_id, node in node_by_id.items():
            node_metrics = {
                "token_cost": token_costs[node_id],
                "effective_token_cost": effective_token_costs[node_id],
                "pagerank": pagerank[node_id],
                "betweenness_centrality": betweenness[node_id],
                "weighted_centrality_cost": pagerank[node_id] * effective_token_costs[node_id],
                "fan_in": len(incoming[node_id]),
                "fan_out": len(outgoing[node_id]),
                "weighted_fan_in": sum(pair_weights[(source, node_id)] for source in incoming[node_id]),
                "weighted_fan_out": sum(weighted_outgoing[node_id].values()),
                "hop_2_token_cost": neighborhood_costs[node_id],
            }
            metrics[node_id] = node_metrics
            metadata = getattr(node, "metadata", None)
            if isinstance(metadata, dict):
                metadata["analysis"] = node_metrics

        return {
            "ambiguity_policy": AMBIGUITY_POLICY,
            "edge_weights": {
                "confidence": dict(self.config.edge_weights.confidence),
                "resolution": dict(self.config.edge_weights.resolution),
            } if self.config.edge_weights is not None else {
                "confidence": {item.value: 1.0 for item in Confidence},
                "resolution": {item.value: 1.0 for item in Resolution},
            },
            "node_metrics": metrics,
            "top_pagerank": self._rank(metrics, node_by_id, "pagerank"),
            "top_betweenness": self._rank(metrics, node_by_id, "betweenness_centrality"),
            "top_weighted_cost": self._rank(metrics, node_by_id, "weighted_centrality_cost"),
            "top_hop_2_cost": self._rank(metrics, node_by_id, "hop_2_token_cost"),
            "total_token_cost": sum(token_costs.values()),
            "total_effective_token_cost": sum(effective_token_costs.values()),
            "cost_policy": {
                "vendored": 0.0,
                "generated": 0.1,
                "migration": 0.1,
                "default": 1.0,
            },
            "betweenness_strategy": betweenness_strategy,
            "betweenness_sample_size": betweenness_sample_size,
            "neighborhood_strategy": neighborhood_strategy,
        }

    def _betweenness_for_graph(self, outgoing: Mapping[str, Set[str]]):
        count = len(outgoing)
        if count <= self.config.exact_betweenness_threshold:
            return self._betweenness(outgoing), "exact", count
        requested = min(count, max(1, self.config.betweenness_sample_size))
        ordered = sorted(outgoing)
        if self.config.betweenness_sampler is not None:
            sampled = list(self.config.betweenness_sampler(ordered, requested))
        else:
            sampled = [ordered[index * count // requested] for index in range(requested)]
        sampled = list(dict.fromkeys(item for item in sampled if item in outgoing))
        return self._betweenness(outgoing, sampled), "deterministic_sampled", len(sampled)

    def _pagerank(self, outgoing: Mapping[str, Mapping[str, float]]) -> Dict[str, float]:
        return pagerank(outgoing, self.config)

    @staticmethod
    def _betweenness(
        outgoing: Mapping[str, Set[str]], sources: Optional[Sequence[str]] = None
    ) -> Dict[str, float]:
        scores = {node_id: 0.0 for node_id in outgoing}
        source_ids = list(sources) if sources is not None else list(outgoing)
        for source in source_ids:
            stack = []
            predecessors = {node_id: [] for node_id in outgoing}
            path_counts = {node_id: 0.0 for node_id in outgoing}
            path_counts[source] = 1.0
            distances = {node_id: -1 for node_id in outgoing}
            distances[source] = 0
            queue = deque([source])

            while queue:
                current = queue.popleft()
                stack.append(current)
                for target in sorted(outgoing[current]):
                    if distances[target] < 0:
                        queue.append(target)
                        distances[target] = distances[current] + 1
                    if distances[target] == distances[current] + 1:
                        path_counts[target] += path_counts[current]
                        predecessors[target].append(current)

            dependencies = {node_id: 0.0 for node_id in outgoing}
            while stack:
                target = stack.pop()
                if path_counts[target]:
                    coefficient = (1.0 + dependencies[target]) / path_counts[target]
                    for predecessor in predecessors[target]:
                        dependencies[predecessor] += path_counts[predecessor] * coefficient
                if target != source:
                    scores[target] += dependencies[target]

        count = len(outgoing)
        scale = (
            (count - 1) * (count - 2)
            if sources is None
            else len(source_ids) * max(1, count - 2)
        )
        if scale > 0:
            scores = {node_id: value / scale for node_id, value in scores.items()}
        return scores

    @staticmethod
    def _two_hop_neighborhood(start: str, adjacency: Mapping[str, Set[str]]) -> Set[str]:
        first = adjacency[start]
        reached = set(first)
        for node_id in first:
            reached |= adjacency[node_id]
        reached.discard(start)
        return reached

    def _neighborhood_metrics(
        self,
        adjacency: Mapping[str, Set[str]],
        tick_costs: Mapping[str, int],
    ) -> tuple[Dict[str, float], str]:
        metrics: Dict[str, float] = {}
        remaining = set(adjacency)
        used_bfs = False
        used_bitsets = False
        while remaining:
            start = remaining.pop()
            component = [start]
            queue = deque([start])
            while queue:
                for neighbor in adjacency[queue.popleft()]:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        component.append(neighbor)
                        queue.append(neighbor)

            count = len(component)
            degree_work = sum(len(adjacency[node_id]) ** 2 for node_id in component)
            budget = self.config.neighborhood_memory_budget_bytes
            use_bitsets = False
            if budget and count >= 64 and degree_work >= 64 * count:
                cost_bit_count = max(tick_costs[node_id] for node_id in component).bit_length()
                use_bitsets = self._estimate_neighborhood_bitset_bytes(count, cost_bit_count) <= budget
            if use_bitsets:
                metrics.update(self._bitset_component_metrics(component, adjacency, tick_costs, cost_bit_count))
                used_bitsets = True
            else:
                used_bfs = True
            del component, queue

        if used_bfs:
            for node_id in adjacency:
                if node_id in metrics:
                    continue
                metrics[node_id] = sum(tick_costs[target] for target in self._two_hop_neighborhood(node_id, adjacency)) / 10

        if used_bitsets:
            strategy = "exact_hybrid" if used_bfs else "exact_bitset"
        else:
            strategy = "single_bfs_to_2_hops"
        return metrics, strategy

    @staticmethod
    def _estimate_neighborhood_bitset_bytes(node_count: int, cost_bit_count: int) -> int:
        digit_bits = sys.int_info.bits_per_digit
        digit_bytes = sys.int_info.sizeof_digit

        def integer_bytes(bits: int) -> int:
            digits = max(1, (bits + digit_bits - 1) // digit_bits)
            return sys.getsizeof(0) + (digits - 1) * digit_bytes

        reference_bytes = sys.getsizeof([None]) - sys.getsizeof([])
        mask_bytes = integer_bytes(node_count)
        sum_bytes = integer_bytes(cost_bit_count + node_count.bit_length())
        # Reserve simultaneous OR/AND/shift temporaries and the wider integer cost sums.
        masks = (2 * node_count + cost_bit_count + 8) * mask_bytes + 8 * sum_bytes
        lists = 4 * sys.getsizeof([]) + (4 * node_count + cost_bit_count) * reference_bytes
        index = sys.getsizeof({}) + node_count * (
            sys.getsizeof({0: 0}) - sys.getsizeof({}) + integer_bytes(node_count.bit_length())
        )
        return masks + lists + index

    @staticmethod
    def _bitset_component_metrics(
        component: Sequence[str],
        adjacency: Mapping[str, Set[str]],
        tick_costs: Mapping[str, int],
        cost_bit_count: int,
    ) -> Dict[str, float]:
        indices = {node_id: index for index, node_id in enumerate(component)}
        closed_1 = [0] * len(component)
        closed_2 = [0] * len(component)
        cost_planes = [0] * cost_bit_count
        for index, node_id in enumerate(component):
            bit = 1 << index
            mask = bit
            for neighbor in adjacency[node_id]:
                mask |= 1 << indices[neighbor]
            closed_1[index] = mask
            ticks = tick_costs[node_id]
            while ticks:
                lowest = ticks & -ticks
                cost_planes[lowest.bit_length() - 1] |= bit
                ticks ^= lowest

        for index, node_id in enumerate(component):
            mask = closed_1[index]
            for neighbor in adjacency[node_id]:
                mask |= closed_1[indices[neighbor]]
            closed_2[index] = mask

        metrics: Dict[str, float] = {}
        for index, node_id in enumerate(component):
            hop_2 = closed_2[index] ^ (1 << index)
            hop_2_ticks = sum((hop_2 & plane).bit_count() << place for place, plane in enumerate(cost_planes))
            metrics[node_id] = hop_2_ticks / 10
        return metrics

    @staticmethod
    def _cost_multiplier(node: Any) -> float:
        flags = {str(flag).lower() for flag in (getattr(node, "flags", None) or [])}
        metadata = getattr(node, "metadata", {}) or {}
        flags.update(str(flag).lower() for flag in metadata.get("flags", []))
        path = str(metadata.get("file_path", "")).replace("\\", "/").lower()
        if "vendored" in flags or "/vendor/" in f"/{path}" or "/node_modules/" in f"/{path}":
            return 0.0
        if "generated" in flags or "migration" in flags or "/migrations/" in f"/{path}" or "/alembic/versions/" in f"/{path}":
            return 0.1
        return 1.0

    def _node_token_cost(self, node: Any) -> int:
        cost = getattr(node, "cost", None)
        token_estimate = getattr(cost, "token_estimate", None)
        metadata = getattr(node, "metadata", {}) or {}
        if isinstance(token_estimate, int) and (token_estimate > 0 or token_estimate == 0 and metadata.get("boundary")):
            return token_estimate
        fallback = json.dumps(
            {
                "label": _display_name(node, ""),
                "title": getattr(node, "title", ""),
                "metadata": metadata,
            },
            ensure_ascii=False,
            default=str,
        )
        return self._estimate_tokens(fallback)

    def _estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text, self.config.characters_per_token, self.config.digit_group_size)

    def _edge_weight(self, edge: Any) -> float:
        if self.config.edge_weights is None:
            return 1.0
        return self.config.edge_weights.weight_for(edge)

    @staticmethod
    def _edge_value(edge: Any, attribute: str, mapping_key: str) -> Any:
        if isinstance(edge, Mapping):
            return edge.get(mapping_key, edge.get(attribute))
        return getattr(edge, attribute, None)

    @staticmethod
    def _rank(
        metrics: Mapping[str, Mapping[str, Any]],
        nodes: Mapping[str, Any],
        metric_name: str,
        limit: int = 10,
    ) -> list[Dict[str, Any]]:
        ranked = sorted((item for item in metrics if not (getattr(nodes[item], "metadata", {}) or {}).get("boundary")), key=lambda node_id: metrics[node_id][metric_name], reverse=True)
        return [
            {
                "id": node_id,
                "label": _display_name(nodes[node_id], node_id),
                "value": metrics[node_id][metric_name],
            }
            for node_id in ranked[:limit]
        ]
