import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Union

import yaml

from agent_view.models import ProfileRef

from .models import PolicyError

_TOP_LEVEL_KEYS = (
    "id",
    "version",
    "phase_a",
    "phase_b",
    "hint_prior",
    "sampling",
    "tie_break",
    "provenance",
    "history",
)
_SAMPLING_INTS = (
    "min_samples",
    "max_samples",
    "batch",
    "bootstrap_resamples",
    "seed",
)


@dataclass(frozen=True)
class ExplorationPolicy:
    ref: ProfileRef
    root_list_query: bool
    repo_map_enabled: bool
    repo_map_rank: str
    repo_map_max_entries: int
    repo_map_token_budget: int
    phase_b_policy: str
    result_ordering: str
    revisit_probability: float
    role_weights: Dict[str, float]
    filename_exact_bonus: float
    min_samples: int
    max_samples: int
    batch: int
    convergence_metric: str
    relative_tolerance: float
    bootstrap_resamples: int
    bootstrap_interval: float
    seed: int
    tie_break_version: str
    provenance: Dict[str, str] = field(default_factory=dict)

    @property
    def version(self) -> int:
        return self.ref.version

    def output(self) -> Dict[str, Any]:
        result = asdict(self)
        result.update(asdict(self.ref))
        del result["ref"]
        return result


def default_policy_path() -> Path:
    return Path(__file__).resolve().parents[1] / "profiles" / "exploration_policy.v1.yaml"


def _mapping(document: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise PolicyError(f"policy {key} must be a mapping")
    return value


def _bool(raw: Dict[str, Any], key: str, label: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise PolicyError(f"policy {label} must be a boolean")
    return value


def _int(raw: Dict[str, Any], key: str, label: str, minimum: int = 1) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise PolicyError(f"policy {label} must be an int >= {minimum}")
    return value


def _number(raw: Dict[str, Any], key: str, label: str) -> float:
    value = raw.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PolicyError(f"policy {label} must be a number")
    return float(value)


def _choice(raw: Dict[str, Any], key: str, label: str, allowed: tuple) -> str:
    value = raw.get(key)
    if value not in allowed:
        raise PolicyError(f"policy {label} must be one of {sorted(allowed)}")
    return value


def load_exploration_policy(path: Union[str, Path]) -> ExplorationPolicy:
    try:
        raw_bytes = Path(path).read_bytes()
    except OSError as error:
        raise PolicyError(f"cannot read policy {path}: {error}") from error
    try:
        document = yaml.safe_load(raw_bytes.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise PolicyError(f"policy is not valid YAML: {error}") from error
    if not isinstance(document, dict):
        raise PolicyError("policy root must be a mapping")
    for key in _TOP_LEVEL_KEYS:
        if key not in document:
            raise PolicyError(f"policy is missing required key: {key}")
    unknown = sorted(set(document) - set(_TOP_LEVEL_KEYS))
    if unknown:
        raise PolicyError(f"unknown policy key: {unknown[0]}")
    if not isinstance(document["id"], str) or not document["id"]:
        raise PolicyError("policy id must be a non-empty string")
    if document["version"] != 1:
        raise PolicyError("policy version must be 1")

    phase_a = _mapping(document, "phase_a")
    repo_map = _mapping(phase_a, "structural_repo_map")
    phase_b = _mapping(document, "phase_b")
    hint_prior = _mapping(document, "hint_prior")
    sampling = _mapping(document, "sampling")
    tie_break = _mapping(document, "tie_break")
    provenance = _mapping(document, "provenance")

    if repo_map.get("rank") != "pagerank":
        raise PolicyError("policy phase_a.structural_repo_map.rank must be 'pagerank'")
    revisit_probability = _number(phase_b, "revisit_probability", "phase_b.revisit_probability")
    if revisit_probability != 0.0:
        # The axis(sample) <= axis(closure) invariant only holds while revisits are impossible;
        # ROADMAP requires the cost contract to be rewritten before this can be raised.
        raise PolicyError("policy phase_b.revisit_probability must be 0.0")

    role_weights_raw = _mapping(hint_prior, "role_weights")
    role_weights = {}
    for key, value in sorted(role_weights_raw.items()):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise PolicyError(f"policy hint_prior.role_weights.{key} must be a non-negative number")
        role_weights[str(key)] = float(value)

    integers = {key: _int(sampling, key, f"sampling.{key}") for key in _SAMPLING_INTS}
    if integers["min_samples"] < 2:
        raise PolicyError("policy sampling.min_samples must be an int >= 2")
    if integers["max_samples"] < integers["min_samples"]:
        raise PolicyError("policy sampling.max_samples must be >= sampling.min_samples")
    relative_tolerance = _number(sampling, "relative_tolerance", "sampling.relative_tolerance")
    if relative_tolerance <= 0:
        raise PolicyError("policy sampling.relative_tolerance must be > 0")
    bootstrap_interval = _number(sampling, "bootstrap_interval", "sampling.bootstrap_interval")
    if not 0 < bootstrap_interval < 1:
        raise PolicyError("policy sampling.bootstrap_interval must be between 0 and 1")
    if not isinstance(sampling.get("convergence_metric"), str) or not sampling["convergence_metric"]:
        raise PolicyError("policy sampling.convergence_metric must be a non-empty string")
    if not isinstance(tie_break.get("version"), str) or not tie_break["version"]:
        raise PolicyError("policy tie_break.version must be a non-empty string")
    for key, value in sorted(provenance.items()):
        if not isinstance(value, str) or not value:
            raise PolicyError(f"policy provenance.{key} must be a non-empty string")

    return ExplorationPolicy(
        ref=ProfileRef(
            id=document["id"],
            version=1,
            content_hash=hashlib.sha256(raw_bytes).hexdigest(),
        ),
        root_list_query=_bool(phase_a, "root_list_query", "phase_a.root_list_query"),
        repo_map_enabled=_bool(repo_map, "enabled", "phase_a.structural_repo_map.enabled"),
        repo_map_rank="pagerank",
        repo_map_max_entries=_int(repo_map, "max_entries", "phase_a.structural_repo_map.max_entries"),
        repo_map_token_budget=_int(repo_map, "token_budget", "phase_a.structural_repo_map.token_budget"),
        phase_b_policy=_choice(phase_b, "policy", "phase_b.policy", ("bfs-exhaust", "best-first-pivot")),
        result_ordering=_choice(phase_b, "result_ordering", "phase_b.result_ordering", ("hint-prior", "uniform")),
        revisit_probability=revisit_probability,
        role_weights=role_weights,
        filename_exact_bonus=_number(hint_prior, "filename_exact_bonus", "hint_prior.filename_exact_bonus"),
        convergence_metric=sampling["convergence_metric"],
        relative_tolerance=relative_tolerance,
        bootstrap_interval=bootstrap_interval,
        tie_break_version=tie_break["version"],
        provenance={str(key): value for key, value in sorted(provenance.items())},
        **integers,
    )
