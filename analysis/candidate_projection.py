import math
from typing import Any, Mapping

AMBIGUITY_POLICY = "equal-symbol-share.v1"


def edge_value(edge: Any, name: str, default=None):
    if isinstance(edge, Mapping):
        return edge.get(name, edge.get({"from_id": "from", "to_id": "to"}.get(name, name), default))
    return getattr(edge, name, default)


def candidate_targets(edge: Any) -> tuple[str, ...]:
    target = edge_value(edge, "to_id")
    if str(edge_value(edge, "resolution", "exact")) != "ambiguous":
        return (target,)
    return tuple(sorted(set([target, *(edge_value(edge, "candidates", []) or [])])))


def candidate_relation_key(source, target, relation, resolution, candidates=None):
    if str(resolution) != "ambiguous":
        return (source, target, relation)
    targets = candidate_targets({"to_id": target, "resolution": resolution, "candidates": candidates})
    return (source, targets[0], relation, "ambiguous", targets)


def has_external_candidate(source, target, resolution, candidates=None):
    return any(item != source for item in candidate_targets(
        {"to_id": target, "resolution": resolution, "candidates": candidates}))


def candidate_projection(edge: Any, node_ids=None):
    source = edge_value(edge, "from_id")
    targets = candidate_targets(edge)
    if node_ids is not None and (source not in node_ids or any(target not in node_ids for target in targets)
                                or any(target not in node_ids for target in (edge_value(edge, "candidates", []) or []))):
        raise ValueError("edge reference is outside architecture")
    metadata = edge_value(edge, "metadata", {}) or {}
    if "candidate_share" in metadata:
        if len(targets) != 1:
            raise ValueError("candidate_share requires a single projected target")
        share = metadata["candidate_share"]
        if isinstance(share, bool) or not isinstance(share, (int, float)) or not math.isfinite(share) or not 0 < share <= 1:
            raise ValueError("candidate_share must be a finite number in (0, 1]")
        return ((edge_value(edge, "to_id"), float(share)),)
    share = 1.0 / len(targets)
    return tuple((target, share) for target in targets)
