import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Tuple, Union

import yaml

from agent_view.models import ProfileRef

from .models import AXES, CostVector, Sample, WeightsError

_TOP_LEVEL_KEYS = ("id", "version", "weights", "axis_priority", "provenance", "history")


@dataclass(frozen=True)
class CostWeights:
    ref: ProfileRef
    weights: Dict[str, float]
    axis_priority: Tuple[str, ...]
    provenance: Dict[str, str]

    @property
    def version(self) -> int:
        return self.ref.version

    def weighted_cost(self, cost: CostVector) -> float:
        values = cost.values()
        return sum(self.weights[axis] * values[axis] for axis in AXES)

    def tie_break_key(self, sample: Sample) -> tuple:
        values = sample.cost.values()
        return (
            tuple(values[axis] for axis in self.axis_priority),
            len(sample.sequence),
            tuple(item.replace("\\", "/").encode("utf-8") for item in sample.id_sequence),
        )

    def sort_key(self, sample: Sample) -> tuple:
        return (self.weighted_cost(sample.cost),) + self.tie_break_key(sample)

    def output(self) -> Dict[str, Any]:
        result = asdict(self)
        result.update(asdict(self.ref))
        del result["ref"]
        result["axis_priority"] = list(self.axis_priority)
        return result


def default_weights_path() -> Path:
    return Path(__file__).resolve().parents[1] / "profiles" / "cost_weights.v1.yaml"


def _mapping(document: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise WeightsError(f"cost weights {key} must be a mapping")
    return value


def load_cost_weights(path: Union[str, Path]) -> CostWeights:
    try:
        raw_bytes = Path(path).read_bytes()
    except OSError as error:
        raise WeightsError(f"cannot read cost weights {path}: {error}") from error
    try:
        document = yaml.safe_load(raw_bytes.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise WeightsError(f"cost weights is not valid YAML: {error}") from error
    if not isinstance(document, dict):
        raise WeightsError("cost weights root must be a mapping")
    for key in _TOP_LEVEL_KEYS:
        if key not in document:
            raise WeightsError(f"cost weights is missing required key: {key}")
    unknown = sorted(set(document) - set(_TOP_LEVEL_KEYS))
    if unknown:
        raise WeightsError(f"unknown cost weights key: {unknown[0]}")
    if not isinstance(document["id"], str) or not document["id"]:
        raise WeightsError("cost weights id must be a non-empty string")
    if document["version"] != 1:
        raise WeightsError("cost weights version must be 1")

    raw_weights = _mapping(document, "weights")
    if set(raw_weights) != set(AXES):
        missing = sorted(set(AXES) - set(raw_weights))
        extra = sorted(set(raw_weights) - set(AXES))
        offender = (missing + extra)[0]
        raise WeightsError(f"cost weights weights must cover exactly the cost axes: {offender}")
    weights = {}
    for axis in AXES:
        value = raw_weights[axis]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise WeightsError(f"cost weights weights.{axis} must be a non-negative number")
        weights[axis] = float(value)

    priority = document["axis_priority"]
    if not isinstance(priority, list) or sorted(priority) != sorted(AXES):
        raise WeightsError("cost weights axis_priority must be a permutation of the cost axes")

    raw_provenance = _mapping(document, "provenance")
    for axis in AXES:
        if not isinstance(raw_provenance.get(axis), str) or not raw_provenance[axis]:
            raise WeightsError(f"cost weights provenance.{axis} must be a non-empty string")

    return CostWeights(
        ref=ProfileRef(
            id=document["id"],
            version=1,
            content_hash=hashlib.sha256(raw_bytes).hexdigest(),
        ),
        weights=weights,
        axis_priority=tuple(priority),
        provenance={str(key): value for key, value in sorted(raw_provenance.items())},
    )
