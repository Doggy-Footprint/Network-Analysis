import json
import os
from typing import Any, Iterable, Mapping

from analysis.structure import TIERS

DELTA_POLICY = "delta.v1"
INSTABILITY_THRESHOLD = 0.2
# Tolerates float error of differences such as 0.8 - 0.6 landing just below 0.2.
_EPSILON = 1e-12
_CYCLE_KINDS = ("dependency_cycle", "package_cycle")
_LIST_NAMES = ("new_cycles", "grown_cycles", "new_violations", "new_package_dependencies", "instability_changes")


class BaselineError(ValueError):
    pass


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _fail(path: str, where: str, expected: str) -> None:
    raise BaselineError(f"baseline {path}: {where} must be {expected}")


def _object(value: Any, path: str, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict): _fail(path, where, "an object")
    return value


def _member(owner: Mapping[str, Any], key: str, path: str, where: str) -> Any:
    if key not in owner: _fail(path, f"{where}.{key}", "present")
    return owner[key]


def _string(value: Any, path: str, where: str) -> None:
    if not isinstance(value, str): _fail(path, where, "a string")


def _check_tier(value: Any, path: str, where: str) -> None:
    if value not in TIERS: _fail(path, where, "one of " + ", ".join(TIERS))


def _check_baseline(document: Any, path: str) -> None:
    root = _object(document, path, "$")
    if root.get("schema") != "bottlenecks.v8": _fail(path, "$.schema", '"bottlenecks.v8"')
    if root.get("granularity") != "file": _fail(path, "$.granularity", '"file"')
    snapshot = _object(_member(root, "snapshot", path, "$"), path, "$.snapshot")
    count = _member(snapshot, "file_count", path, "$.snapshot")
    if not isinstance(count, int) or isinstance(count, bool): _fail(path, "$.snapshot.file_count", "an integer")
    network = _object(_member(root, "dependency_network", path, "$"), path, "$.dependency_network")
    _string(_member(network, "structure_policy", path, "$.dependency_network"), path, "$.dependency_network.structure_policy")
    dependencies = _object(_member(network, "package_dependencies", path, "$.dependency_network"), path, "$.dependency_network.package_dependencies")
    for scheme, pairs in dependencies.items():
        where = f"$.dependency_network.package_dependencies.{scheme}"
        if not isinstance(pairs, list): _fail(path, where, "a list")
        for index, pair in enumerate(pairs):
            item = f"{where}[{index}]"
            _object(pair, path, item)
            _string(pair.get("from_id"), path, item + ".from_id")
            _string(pair.get("to_id"), path, item + ".to_id")
            _check_tier(pair.get("tier"), path, item + ".tier")
    metrics = _object(_member(network, "package_metrics", path, "$.dependency_network"), path, "$.dependency_network.package_metrics")
    for scheme, packages in metrics.items():
        where = f"$.dependency_network.package_metrics.{scheme}"
        _object(packages, path, where)
        for package, record in packages.items():
            item = f"{where}.{package}"
            _object(record, path, item)
            if "instability" not in record or not (record["instability"] is None or _number(record["instability"])):
                _fail(path, item + ".instability", "a number or null")
    candidates = _member(root, "candidates", path, "$")
    if not isinstance(candidates, list): _fail(path, "$.candidates", "a list")
    for index, candidate in enumerate(candidates):
        where = f"$.candidates[{index}]"
        _object(candidate, path, where)
        _string(candidate.get("id"), path, where + ".id")
        _string(candidate.get("kind"), path, where + ".kind")
        if candidate["kind"] in _CYCLE_KINDS: _check_cycle(candidate, path, where)
        elif candidate["kind"] == "rule_violation": _check_violation(candidate, path, where)
    coverage = root.get("coverage")
    if coverage is not None:
        _object(coverage, path, "$.coverage")
        rules = coverage.get("architecture_rules")
        if "architecture_rules" in coverage:
            _object(rules, path, "$.coverage.architecture_rules")
            if "rules_sha256" in rules: _string(rules["rules_sha256"], path, "$.coverage.architecture_rules.rules_sha256")


def _check_cycle(candidate: Mapping[str, Any], path: str, where: str) -> None:
    structure = _object(candidate.get("structure"), path, where + ".structure")
    _string(structure.get("scheme"), path, where + ".structure.scheme")
    _check_tier(structure.get("tier"), path, where + ".structure.tier")
    members = structure.get("members")
    if not isinstance(members, list) or not all(isinstance(item, str) for item in members):
        _fail(path, where + ".structure.members", "a list of strings")
    evidence = candidate.get("evidence")
    if not isinstance(evidence, list): _fail(path, where + ".evidence", "a list")
    for index, record in enumerate(evidence):
        item = f"{where}.evidence[{index}]"
        _object(record, path, item)
        _string(record.get("from_id"), path, item + ".from_id")
        _string(record.get("to_id"), path, item + ".to_id")


def _check_violation(candidate: Mapping[str, Any], path: str, where: str) -> None:
    structure = _object(candidate.get("structure"), path, where + ".structure")
    _string(structure.get("rule_type"), path, where + ".structure.rule_type")
    _string(structure.get("from_layer"), path, where + ".structure.from_layer")
    if "to_layer" in structure: _string(structure["to_layer"], path, where + ".structure.to_layer")
    elif "to_external" in structure: _string(structure["to_external"], path, where + ".structure.to_external")
    else: _fail(path, where + ".structure", "an object with a string to_layer or to_external")


def load_baseline(path: "str | os.PathLike") -> dict:
    name = os.fspath(path)
    try:
        with open(name, "rb") as handle: raw = handle.read()
        document = json.loads(raw.decode("utf-8"))
    except OSError as error:
        raise BaselineError(f"baseline {name}: cannot read: {error}") from error
    except UnicodeDecodeError as error:
        raise BaselineError(f"baseline {name}: is not valid UTF-8: {error}") from error
    except RecursionError as error:
        raise BaselineError(f"baseline {name}: JSON nesting is too deep") from error
    except ValueError as error:
        raise BaselineError(f"baseline {name}: is not valid JSON: {error}") from error
    try:
        _check_baseline(document, name)
    except RecursionError as error:
        raise BaselineError(f"baseline {name}: JSON nesting is too deep") from error
    return document


def _structure_cycles(candidates: Iterable[Mapping[str, Any]]) -> dict[tuple, list[Mapping[str, Any]]]:
    grouped: dict[tuple, list] = {}
    for candidate in candidates:
        if candidate.get("kind") in _CYCLE_KINDS:
            structure = candidate["structure"]
            grouped.setdefault((candidate["kind"], structure["scheme"], structure["tier"]), []).append(candidate)
    return grouped


def _pairs(candidate: Mapping[str, Any]) -> set[tuple[str, str]]:
    return {(record["from_id"], record["to_id"]) for record in candidate["evidence"]}


def _cycle_delta(current: list, baseline: list) -> tuple[list, list, int]:
    base_by_key = _structure_cycles(baseline)
    current_by_key = _structure_cycles(current)
    new, grown, resolved = [], [], 0
    for key, cycles in current_by_key.items():
        owners: dict[str, list[int]] = {}
        base_cycles = base_by_key.get(key, [])
        for index, cycle in enumerate(base_cycles):
            for member in cycle["structure"]["members"]: owners.setdefault(member, []).append(index)
        for cycle in cycles:
            members = set(cycle["structure"]["members"])
            overlap = sorted({index for member in members for index in owners.get(member, ())})
            union = set().union(*(base_cycles[index]["structure"]["members"] for index in overlap)) if overlap else set()
            added = members - union
            if overlap and not added and len(overlap) < 2: continue
            known_pairs = set().union(*(_pairs(base_cycles[index]) for index in overlap)) if overlap else set()
            item = {"candidate_id": cycle["id"], "kind": key[0], "scheme": key[1], "tier": key[2], "members": sorted(members),
                    "baseline_candidate_ids": sorted(base_cycles[index]["id"] for index in overlap), "added_members": sorted(added),
                    "new_internal_pairs": [list(pair) for pair in sorted(_pairs(cycle) - known_pairs)]}
            (grown if overlap else new).append(item)
    current_members = {key: {member for cycle in cycles for member in cycle["structure"]["members"]} for key, cycles in current_by_key.items()}
    for key, cycles in base_by_key.items():
        present = current_members.get(key, set())
        resolved += sum(1 for cycle in cycles if present.isdisjoint(cycle["structure"]["members"]))
    order = lambda item: (item["kind"], item["scheme"], item["tier"], item["candidate_id"])
    return sorted(new, key=order), sorted(grown, key=order), resolved


def _violations(candidates: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    found: dict[str, Mapping[str, Any]] = {}
    for candidate in candidates:
        if candidate.get("kind") == "rule_violation": found.setdefault(candidate["id"], candidate)
    return found


def _violation_item(candidate: Mapping[str, Any]) -> dict:
    structure = candidate["structure"]
    item = {"candidate_id": candidate["id"], "rule_type": structure["rule_type"], "from_layer": structure["from_layer"], "target": candidate["target"]}
    if "to_external" in structure: item["to_external"] = structure["to_external"]
    else: item.update(to_layer=structure["to_layer"], to_id=candidate["evidence"][0]["to_id"])
    return item


def _dependency_map(network: Mapping[str, Any]) -> dict[tuple[str, str, str], str]:
    found: dict[tuple[str, str, str], str] = {}
    for scheme, pairs in (network.get("package_dependencies") or {}).items():
        for pair in pairs: found.setdefault((scheme, pair["from_id"], pair["to_id"]), pair["tier"])
    return found


def _instability_changes(current: Mapping[str, Any], baseline: Mapping[str, Any]) -> list[dict]:
    changes = []
    base_metrics = baseline.get("package_metrics") or {}
    for scheme, packages in (current.get("package_metrics") or {}).items():
        before = base_metrics.get(scheme) or {}
        for package, record in packages.items():
            if package not in before: continue
            now, then = record.get("instability"), before[package].get("instability")
            if not _number(now) or not _number(then): continue
            if abs(now - then) >= INSTABILITY_THRESHOLD - _EPSILON:
                changes.append({"scheme": scheme, "package": package, "baseline": then, "current": now, "delta": now - then})
    return sorted(changes, key=lambda item: (-abs(item["delta"]), item["scheme"], item["package"]))


def compute_delta(current: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict:
    current_network, baseline_network = current.get("dependency_network") or {}, baseline.get("dependency_network") or {}
    if current_network.get("structure_policy") != baseline_network.get("structure_policy"):
        raise BaselineError(f"baseline: structure_policy {baseline_network.get('structure_policy')!r} differs from current {current_network.get('structure_policy')!r}")
    current_rules = (current.get("coverage") or {}).get("architecture_rules")
    baseline_rules = (baseline.get("coverage") or {}).get("architecture_rules")
    if (current_rules is None) != (baseline_rules is None):
        raise BaselineError("baseline: architecture rules were used by only one of the baseline and the current run")
    digest = None if baseline_rules is None else baseline_rules.get("rules_sha256")
    rules_changed = current_rules is not None and (digest is None or current_rules.get("rules_sha256") != digest)

    new_cycles, grown_cycles, resolved_cycles = _cycle_delta(current["candidates"], baseline["candidates"])
    current_violations, baseline_violations = _violations(current["candidates"]), _violations(baseline["candidates"])
    new_violations = [_violation_item(current_violations[key]) for key in sorted(set(current_violations) - set(baseline_violations))]
    current_pairs, baseline_pairs = _dependency_map(current_network), _dependency_map(baseline_network)
    new_pairs = [{"scheme": key[0], "from_id": key[1], "to_id": key[2], "tier": current_pairs[key]} for key in sorted(set(current_pairs) - set(baseline_pairs))]
    changes = _instability_changes(current_network, baseline_network)
    delta = {"policy": DELTA_POLICY, "baseline": {"file_count": baseline["snapshot"]["file_count"], "rules_sha256": digest}, "rules_changed": rules_changed,
             "new_cycles": new_cycles, "grown_cycles": grown_cycles, "new_violations": new_violations,
             "new_package_dependencies": new_pairs, "instability_changes": changes,
             "resolved": {"cycles": resolved_cycles, "violations": len(set(baseline_violations) - set(current_violations)),
                          "package_dependencies": len(set(baseline_pairs) - set(current_pairs))}}
    delta["counts"] = {name: len(delta[name]) for name in _LIST_NAMES}
    return delta


def regressions(delta: Mapping[str, Any], fail_on: Iterable[str]) -> list[str]:
    selected = set(fail_on)
    if "any" in selected: selected |= {"cycle", "violation"}
    result = []
    if "cycle" in selected and (delta["new_cycles"] or delta["grown_cycles"]): result.append("cycle")
    if "violation" in selected and delta["new_violations"]: result.append("violation")
    return result
