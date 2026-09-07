import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from .graph_view import GraphView
from .models import Scenario, ScenarioError, SeedTerm

SCHEMA = "scenarios.v1"


def _resolve_symbol(view: GraphView, path: str, symbol: str) -> Tuple[str, ...]:
    matches = [
        node_id
        for node_id in view.nodes_by_path.get(path, ())
        if view.readable[node_id].label == symbol
    ]
    if not matches:
        raise ScenarioError(f"target does not resolve: {path}#{symbol}")
    if len(matches) > 1:
        raise ScenarioError(f"target is ambiguous: {path}#{symbol}")
    return (matches[0],)


def _resolve_path(view: GraphView, path: str) -> Tuple[str, ...]:
    node_ids = view.nodes_by_path.get(path, ())
    if not node_ids:
        raise ScenarioError(f"target does not resolve: {path}")
    whole_file = [node_id for node_id in node_ids if view.readable[node_id].kind == "file"]
    if whole_file:
        return (whole_file[0],)
    by_unit: Dict[str, List[str]] = defaultdict(list)
    for node_id in node_ids:
        by_unit[view.unit_of_node[node_id]].append(node_id)
    return tuple(sorted(min(members) for members in by_unit.values()))


def _seed_terms(raw: Any, scenario_id: str) -> Tuple[SeedTerm, ...]:
    if not isinstance(raw, list):
        raise ScenarioError(f"scenario {scenario_id} seed_queries must be a list")
    terms = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ScenarioError(f"scenario {scenario_id} seed query must be an object")
        term = entry.get("term")
        surface = entry.get("surface")
        if not isinstance(term, str) or not term:
            raise ScenarioError(f"scenario {scenario_id} seed query term must be a non-empty string")
        if surface not in ("content", "path"):
            raise ScenarioError(f"scenario {scenario_id} seed query surface must be content or path")
        terms.append(SeedTerm(term=term, surface=surface))
    return tuple(terms)


def load_scenarios(path: Union[str, Path], view: GraphView) -> List[Scenario]:
    try:
        raw_text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise ScenarioError(f"cannot read scenarios {path}: {error}") from error
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise ScenarioError(f"scenarios is not valid JSON: {error}") from error
    if not isinstance(document, dict):
        raise ScenarioError("scenarios root must be an object")
    if document.get("schema") != SCHEMA:
        raise ScenarioError(f"scenarios schema must be {SCHEMA}")
    entries = document.get("scenarios")
    if not isinstance(entries, list):
        raise ScenarioError("scenarios must be a list")

    scenarios = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ScenarioError("scenario must be an object")
        scenario_id = entry.get("id")
        task = entry.get("task")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ScenarioError("scenario id must be a non-empty string")
        if scenario_id in seen:
            raise ScenarioError(f"duplicate scenario id: {scenario_id}")
        seen.add(scenario_id)
        if not isinstance(task, str) or not task:
            raise ScenarioError(f"scenario {scenario_id} task must be a non-empty string")
        targets = entry.get("targets")
        if not isinstance(targets, list) or not targets:
            raise ScenarioError(f"scenario {scenario_id} targets must be a non-empty list")
        node_ids: List[str] = []
        for target in targets:
            if not isinstance(target, str) or not target:
                raise ScenarioError(f"scenario {scenario_id} target must be a non-empty string")
            if "#" in target:
                path_part, _, symbol = target.partition("#")
                resolved = _resolve_symbol(view, path_part, symbol)
            else:
                resolved = _resolve_path(view, target)
            for node_id in resolved:
                if node_id not in node_ids:
                    node_ids.append(node_id)
        scenarios.append(
            Scenario(
                id=scenario_id,
                task=task,
                target_node_ids=tuple(node_ids),
                seed_terms=_seed_terms(entry["seed_queries"], scenario_id)
                if "seed_queries" in entry
                else (),
            )
        )
    return scenarios
