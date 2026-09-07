import ast
import json
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Set

from language_analyzers.core.cost import CHARACTERS_PER_TOKEN, DIGIT_GROUP_SIZE, estimate_tokens


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


def pagerank(
    outgoing: Mapping[str, Set[str]],
    config: Optional[GraphAnalysisConfig] = None,
) -> Dict[str, float]:
    settings = config or GraphAnalysisConfig()
    count = len(outgoing)
    if not count:
        return {}
    scores = {node_id: 1.0 / count for node_id in outgoing}
    base = (1.0 - settings.damping) / count

    for _ in range(settings.max_iterations):
        dangling = sum(scores[node_id] for node_id, targets in outgoing.items() if not targets)
        updated = {node_id: base + settings.damping * dangling / count for node_id in outgoing}
        for source, targets in outgoing.items():
            if not targets:
                continue
            contribution = settings.damping * scores[source] / len(targets)
            for target in targets:
                updated[target] += contribution
        if sum(abs(updated[item] - scores[item]) for item in scores) <= settings.tolerance:
            scores = updated
            break
        scores = updated
    return scores


class GraphAnalyzer:
    def __init__(self, config: Optional[GraphAnalysisConfig] = None):
        self.config = config or GraphAnalysisConfig()
        self._source_cache: Dict[Path, str] = {}
        self._tree_cache: Dict[Path, Optional[ast.AST]] = {}

    def analyze(
        self,
        nodes: Sequence[Any],
        edges: Sequence[Any],
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        node_by_id = {node.id: node for node in nodes}
        outgoing = {node_id: set() for node_id in node_by_id}
        incoming = {node_id: set() for node_id in node_by_id}

        for edge in edges:
            source = self._edge_value(edge, "from_id", "from")
            target = self._edge_value(edge, "to_id", "to")
            if source not in node_by_id or target not in node_by_id or source == target:
                continue
            outgoing[source].add(target)
            incoming[target].add(source)

        token_costs = {
            node_id: self._node_token_cost(node, project_path)
            for node_id, node in node_by_id.items()
        }
        effective_token_costs = {
            node_id: token_costs[node_id] * self._cost_multiplier(node)
            for node_id, node in node_by_id.items()
        }
        pagerank = self._pagerank(outgoing)
        hub_scores, authority_scores = self._hits(outgoing, incoming)
        betweenness, betweenness_strategy, betweenness_sample_size = self._betweenness_for_graph(outgoing)
        undirected = {
            node_id: outgoing[node_id] | incoming[node_id]
            for node_id in node_by_id
        }
        denominator = max(1, 2 * (len(node_by_id) - 1))

        metrics: Dict[str, Dict[str, Any]] = {}
        for node_id, node in node_by_id.items():
            hop_2_nodes, hop_3_nodes = self._neighborhoods(node_id, undirected)
            node_metrics = {
                "token_cost": token_costs[node_id],
                "effective_token_cost": effective_token_costs[node_id],
                "pagerank": pagerank[node_id],
                "hub_score": hub_scores[node_id],
                "authority_score": authority_scores[node_id],
                "degree_centrality": (len(outgoing[node_id]) + len(incoming[node_id])) / denominator,
                "betweenness_centrality": betweenness[node_id],
                "weighted_centrality_cost": pagerank[node_id] * effective_token_costs[node_id],
                "fan_in": len(incoming[node_id]),
                "fan_out": len(outgoing[node_id]),
                "hop_2_node_count": len(hop_2_nodes),
                "hop_2_token_cost": sum(effective_token_costs[item] for item in hop_2_nodes),
                "hop_3_node_count": len(hop_3_nodes),
                "hop_3_token_cost": sum(effective_token_costs[item] for item in hop_3_nodes),
            }
            metrics[node_id] = node_metrics
            metadata = getattr(node, "metadata", None)
            if isinstance(metadata, dict):
                metadata["analysis"] = node_metrics

        return {
            "node_metrics": metrics,
            "top_pagerank": self._rank(metrics, node_by_id, "pagerank"),
            "top_hubs": self._rank(metrics, node_by_id, "hub_score"),
            "top_betweenness": self._rank(metrics, node_by_id, "betweenness_centrality"),
            "top_weighted_cost": self._rank(metrics, node_by_id, "weighted_centrality_cost"),
            "top_hop_2_cost": self._rank(metrics, node_by_id, "hop_2_token_cost"),
            "top_hop_3_cost": self._rank(metrics, node_by_id, "hop_3_token_cost"),
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
            "neighborhood_strategy": "single_bfs_to_3_hops",
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

    def _pagerank(self, outgoing: Mapping[str, Set[str]]) -> Dict[str, float]:
        return pagerank(outgoing, self.config)

    def _hits(
        self,
        outgoing: Mapping[str, Set[str]],
        incoming: Mapping[str, Set[str]],
    ) -> tuple[Dict[str, float], Dict[str, float]]:
        if not outgoing:
            return {}, {}
        hubs = {node_id: 1.0 for node_id in outgoing}
        authorities = {node_id: 1.0 for node_id in outgoing}

        for _ in range(self.config.max_iterations):
            next_authorities = {
                node_id: sum(hubs[source] for source in incoming[node_id])
                for node_id in outgoing
            }
            self._normalize(next_authorities)
            next_hubs = {
                node_id: sum(next_authorities[target] for target in outgoing[node_id])
                for node_id in outgoing
            }
            self._normalize(next_hubs)
            delta = sum(abs(next_hubs[item] - hubs[item]) for item in hubs)
            delta += sum(abs(next_authorities[item] - authorities[item]) for item in authorities)
            hubs, authorities = next_hubs, next_authorities
            if delta <= self.config.tolerance:
                break
        return hubs, authorities

    @staticmethod
    def _normalize(values: Dict[str, float]) -> None:
        norm = math.sqrt(sum(value * value for value in values.values()))
        if norm:
            for key in values:
                values[key] /= norm

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
    def _neighborhoods(
        start: str,
        adjacency: Mapping[str, Set[str]],
    ) -> tuple[Set[str], Set[str]]:
        visited = {start}
        frontier = {start}
        hop_2: Set[str] = set()
        for depth in range(1, 4):
            frontier = {
                neighbor
                for node_id in frontier
                for neighbor in adjacency[node_id]
                if neighbor not in visited
            }
            visited.update(frontier)
            if depth == 2:
                hop_2 = visited - {start}
            if not frontier:
                break
        if not hop_2:
            hop_2 = visited - {start}
        return hop_2, visited - {start}

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

    def _node_token_cost(self, node: Any, project_path: Optional[str]) -> int:
        cost = getattr(node, "cost", None)
        token_estimate = getattr(cost, "token_estimate", None)
        if isinstance(token_estimate, int) and token_estimate > 0:
            return token_estimate
        metadata = getattr(node, "metadata", {}) or {}
        file_value = metadata.get("file_path")
        line_number = metadata.get("line_number")
        end_line_number = metadata.get("end_line_number")
        if file_value:
            file_path = Path(file_value)
            if not file_path.is_absolute() and project_path:
                file_path = Path(project_path) / file_path
            source = self._source_for_line(file_path, line_number, end_line_number)
            if source:
                return self._estimate_tokens(source)
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

    def _source_for_line(self, path: Path, line_number: Any, end_line_number: Any = None) -> str:
        if path not in self._source_cache:
            try:
                self._source_cache[path] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                return ""
        source = self._source_cache[path]
        try:
            line = int(line_number)
        except (TypeError, ValueError):
            return source
        if end_line_number is not None:
            try:
                end_line = int(end_line_number)
            except (TypeError, ValueError):
                end_line = None
            if end_line is not None and end_line >= line:
                lines = source.splitlines()
                return "\n".join(lines[max(0, line - 1):end_line])
        tree = self._tree_cache.get(path)
        if path not in self._tree_cache:
            try:
                tree = ast.parse(source)
            except SyntaxError:
                tree = None
            self._tree_cache[path] = tree
        if tree is None:
            return source
        candidates = [
            item
            for item in ast.walk(tree)
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign, ast.Expr))
            and getattr(item, "lineno", 0) <= line <= getattr(item, "end_lineno", getattr(item, "lineno", 0))
        ]
        if not candidates:
            return source
        target = min(candidates, key=lambda item: item.end_lineno - item.lineno)
        return ast.get_source_segment(source, target) or source

    def _estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text, self.config.characters_per_token, self.config.digit_group_size)

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
        ranked = sorted(metrics, key=lambda node_id: metrics[node_id][metric_name], reverse=True)
        return [
            {
                "id": node_id,
                "label": _display_name(nodes[node_id], node_id),
                "value": metrics[node_id][metric_name],
            }
            for node_id in ranked[:limit]
        ]
