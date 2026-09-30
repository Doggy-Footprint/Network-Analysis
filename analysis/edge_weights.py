import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Union

import yaml

from language_analyzers.core.graph_models import Confidence, Resolution


class EdgeWeightsError(ValueError):
    pass


_KEYS = {"id", "version", "confidence", "resolution", "large_node_line_threshold"}


@dataclass(frozen=True)
class EdgeWeights:
    id: str
    version: int
    content_hash: str
    confidence: Mapping[str, float]
    resolution: Mapping[str, float]
    large_node_line_threshold: int

    def weight_for(self, edge: Any) -> float:
        if isinstance(edge, Mapping):
            confidence, resolution = edge.get("confidence"), edge.get("resolution")
        else:
            confidence, resolution = getattr(edge, "confidence", None), getattr(edge, "resolution", None)
        return min(self.confidence[str(confidence)], self.resolution[str(resolution)])


def default_edge_weights_path() -> Path:
    return Path(__file__).resolve().parents[1] / "profiles" / "edge_weights.v1.yaml"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _weight_table(document: Dict[str, Any], key: str, members: type) -> Dict[str, float]:
    table = document[key]
    expected = {member.value for member in members}
    if not isinstance(table, dict) or set(table) != expected:
        raise EdgeWeightsError(f"edge weights {key} must have exactly the keys {sorted(expected)}")
    for name, value in table.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
            raise EdgeWeightsError(f"edge weights {key}.{name} must be a number in (0, 1]")
    return {name: float(table[name]) for name in sorted(table)}


def load_edge_weights(path: Union[str, Path]) -> EdgeWeights:
    try:
        raw_bytes = Path(path).read_bytes()
    except OSError as error:
        raise EdgeWeightsError(f"cannot read edge weights {path}: {error}") from error
    try:
        document = yaml.safe_load(raw_bytes.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise EdgeWeightsError(f"edge weights is not valid YAML: {error}") from error
    if not isinstance(document, dict) or set(document) != _KEYS:
        raise EdgeWeightsError(f"edge weights must be a mapping with exactly the keys {sorted(_KEYS)}")
    if not isinstance(document["id"], str) or not document["id"]:
        raise EdgeWeightsError("edge weights id must be a non-empty string")
    if not _is_int(document["version"]) or document["version"] < 1:
        raise EdgeWeightsError("edge weights version must be an int >= 1")
    threshold = document["large_node_line_threshold"]
    if not _is_int(threshold) or threshold < 1:
        raise EdgeWeightsError("edge weights large_node_line_threshold must be an int >= 1")
    return EdgeWeights(
        id=document["id"],
        version=document["version"],
        content_hash=hashlib.sha256(raw_bytes).hexdigest(),
        confidence=_weight_table(document, "confidence", Confidence),
        resolution=_weight_table(document, "resolution", Resolution),
        large_node_line_threshold=threshold,
    )
