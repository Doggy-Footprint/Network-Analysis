from dataclasses import asdict, is_dataclass
from copy import deepcopy
from analysis.candidate_projection import AMBIGUITY_POLICY
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "5"


def _structure(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return None


def node_to_dict(node: Any) -> Dict[str, Any]:
    """Nodes reaching this point may be duck-typed stand-ins from adapters or tests, so every
    field beyond the original vis.js set is read defensively."""
    return {
        "id": node.id,
        "label": node.label,
        "group": getattr(node, "group", ""),
        "category": getattr(node, "category", ""),
        "title": getattr(node, "title", ""),
        "shape": getattr(node, "shape", "box"),
        "size": getattr(node, "size", 25),
        "color": getattr(node, "color", None),
        "kind": getattr(node, "kind", "") or getattr(node, "category", ""),
        "language": getattr(node, "language", ""),
        "span": _structure(getattr(node, "span", None)),
        "cost": _structure(getattr(node, "cost", None)),
        "signature": getattr(node, "signature", None),
        "docstring": getattr(node, "docstring", None),
        "exported": getattr(node, "exported", None),
        "symbol_path": getattr(node, "symbol_path", ""),
        "display_label": getattr(node, "display_label", "") or "",
        "flags": list(getattr(node, "flags", []) or []),
        "provenance": getattr(node, "provenance", ""),
        "metadata": getattr(node, "metadata", {}) or {},
    }


def edge_to_dict(edge: Any) -> Dict[str, Any]:
    if isinstance(edge, dict):
        source = edge.get("from_id", edge.get("from"))
        target = edge.get("to_id", edge.get("to"))
        base = dict(edge)
        base.update({"from_id": source, "to_id": target})
        base.pop("from", None)
        base.pop("to", None)
        return base
    return {
        "from_id": edge.from_id,
        "to_id": edge.to_id,
        "relation": edge.relation,
        "label": getattr(edge, "label", ""),
        "dashes": getattr(edge, "dashes", False),
        "arrows": getattr(edge, "arrows", "to"),
        "color": getattr(edge, "color", None),
        "title": getattr(edge, "title", None),
        "confidence": str(getattr(edge, "confidence", "static_certain")),
        "resolution": str(getattr(edge, "resolution", "exact")),
        "evidence": _structure(getattr(edge, "evidence", None)),
        "candidates": list(getattr(edge, "candidates", []) or []),
        "weight": getattr(edge, "weight", 1.0),
        "metadata": getattr(edge, "metadata", {}) or {},
    }


def collection_to_dict(collection: Any) -> Dict[str, Any]:
    return {
        "label": collection.label,
        "icon": getattr(collection, "icon", "box"),
        "view": getattr(collection, "view", "grid"),
        "node_category": getattr(collection, "node_category", None),
        "columns": [asdict(column) for column in collection.columns],
        "rows": collection.rows,
    }


def architecture_to_dict(architecture: Any) -> Dict[str, Any]:
    result = {
        "schema_version": "6" if getattr(architecture, "granularity", None) == "file" else SCHEMA_VERSION,
        "project_name": architecture.project_name,
        "project_path": architecture.project_path,
        "stats": getattr(architecture, "stats", {}) or {},
        "nodes": [node_to_dict(node) for node in architecture.nodes],
        "edges": [edge_to_dict(edge) for edge in architecture.edges],
        "collections": {
            collection.key: collection_to_dict(collection)
            for collection in getattr(architecture, "report_collections", []) or []
        },
    }
    analysis = result["stats"].get("analysis")
    if not analysis and not any(node["metadata"].get("analysis") for node in result["nodes"]):
        result["stats"] = deepcopy(result["stats"])
        result["stats"]["analysis"] = {"ambiguity_policy": AMBIGUITY_POLICY}
    if getattr(architecture, "granularity", None) == "file":
        result.update(granularity="file", details=architecture.details)
    return result
