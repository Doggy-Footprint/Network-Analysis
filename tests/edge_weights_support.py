"""Shared builders for the dependency-bottleneck-refocus tests (spec 8fd668e309160b58)."""
import copy
from pathlib import Path

import yaml

from analysis.edge_weights import load_edge_weights
from language_analyzers.core.graph_models import Confidence, GraphEdge, GraphNode, Resolution

ROOT = Path(__file__).resolve().parents[1]

CONFIDENCE_KEYS = [member.value for member in Confidence]
RESOLUTION_KEYS = [member.value for member in Resolution]

DEFAULT_WEIGHTS = {
    "id": "edge_weights",
    "version": 1,
    "confidence": {"static_certain": 1.0, "static_inferred": 0.3, "framework_inferred": 0.3, "dynamic_required": 0.3},
    "resolution": {"exact": 1.0, "unique_name": 1.0, "ambiguous": 0.3, "unresolved": 0.3},
    "large_node_line_threshold": 2000,
}


def weights_data(confidence=None, resolution=None, **top_level):
    data = copy.deepcopy(DEFAULT_WEIGHTS)
    data["confidence"].update(confidence or {})
    data["resolution"].update(resolution or {})
    data.update(top_level)
    return data


def uniform_weights_data(**top_level):
    return weights_data(
        confidence={key: 1.0 for key in CONFIDENCE_KEYS},
        resolution={key: 1.0 for key in RESOLUTION_KEYS},
        **top_level,
    )


def write_weights(directory, data, name="weights.yaml"):
    path = Path(directory) / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def load_weights(directory, data, name="weights.yaml"):
    return load_edge_weights(write_weights(directory, data, name))


def edge(source, target, confidence=Confidence.STATIC_CERTAIN, resolution=Resolution.EXACT, relation="CALLS", **extra):
    return GraphEdge(source, target, relation, confidence=confidence, resolution=resolution, **extra)


def symbol_nodes(*ids):
    return [GraphNode(item, item, "symbol", "symbol") for item in ids]
