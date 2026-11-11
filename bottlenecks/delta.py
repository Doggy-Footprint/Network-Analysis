import copy
import json
import os
import re
from typing import Any, Callable, Iterable, Mapping

from analysis.structure import TIERS

DELTA_POLICY = "delta.v3"
INSTABILITY_THRESHOLD = 0.2
# Tolerates float error of differences such as 0.8 - 0.6 landing just below 0.2.
_EPSILON = 1e-12
_SCHEMAS = ("bottlenecks.v8", "bottlenecks.v9")
_CYCLE_KINDS = ("dependency_cycle", "package_cycle")
_LIST_NAMES = ("new_cycles", "grown_cycles", "new_violations", "new_package_dependencies", "instability_changes", "new_candidates", "strengthened_candidates")
_SPECIAL_KINDS = _CYCLE_KINDS + ("rule_violation",)
# Only these count as strengthening; line spans, thresholds and ranks change on formatting alone.
_STRENGTH_METRICS = {"large_node": ("line_count", "token_count"), "unresolved_boundary": ("unresolved_count",),
                     "evidence_spread": ("file_count", "directory_count"), "dangling_doc_reference": ("dangling_count",),
                     "unstable_dependency": ("file_pair_count",)}
_EVIDENCE_KINDS = ("unresolved_boundary", "dangling_doc_reference")


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
    schema = root.get("schema")
    if schema not in _SCHEMAS: _fail(path, "$.schema", 'one of "bottlenecks.v8", "bottlenecks.v9"')
    if root.get("granularity") != "file": _fail(path, "$.granularity", '"file"')
    snapshot = _object(_member(root, "snapshot", path, "$"), path, "$.snapshot")
    count = _member(snapshot, "file_count", path, "$.snapshot")
    if not isinstance(count, int) or isinstance(count, bool): _fail(path, "$.snapshot.file_count", "an integer")
    commit = snapshot.get("git_commit")
    if commit is not None and not isinstance(commit, str): _fail(path, "$.snapshot.git_commit", "a string or null")
    network = _object(_member(root, "dependency_network", path, "$"), path, "$.dependency_network")
    columns = _check_columns(network, path) if schema == "bottlenecks.v9" else None
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
        if candidate["kind"] in _CYCLE_KINDS: _check_cycle(candidate, path, where, columns)
        elif candidate["kind"] == "rule_violation": _check_violation(candidate, path, where)
        else: _check_general(candidate, path, where)
    coverage = root.get("coverage")
    if coverage is not None:
        _object(coverage, path, "$.coverage")
        rules = coverage.get("architecture_rules")
        if "architecture_rules" in coverage:
            _object(rules, path, "$.coverage.architecture_rules")
            if "rules_sha256" in rules: _string(rules["rules_sha256"], path, "$.coverage.architecture_rules.rules_sha256")


def _check_columns(network: Mapping[str, Any], path: str) -> dict:
    base = "$.dependency_network"
    ids = _member(network, "file_ids", path, base)
    if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids): _fail(path, base + ".file_ids", "a list of strings")
    columns = _object(_member(network, "evidence_columns", path, base), path, base + ".evidence_columns")
    for name in ("file_pair", "package_pair"):
        names = _member(columns, name, path, base + ".evidence_columns")
        if not isinstance(names, list) or not all(isinstance(item, str) for item in names): _fail(path, f"{base}.evidence_columns.{name}", "a list of strings")
    return {"count": len(ids), "file_pair": len(columns["file_pair"]), "package_pair": len(columns["package_pair"])}


def _check_cycle(candidate: Mapping[str, Any], path: str, where: str, columns: Mapping[str, int] | None = None) -> None:
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
        if columns is not None:
            _check_row(record, candidate["kind"], path, item, columns)
            continue
        _object(record, path, item)
        _string(record.get("from_id"), path, item + ".from_id")
        _string(record.get("to_id"), path, item + ".to_id")


def _check_row(row: Any, kind: str, path: str, where: str, columns: Mapping[str, int]) -> None:
    name = "file_pair" if kind == "dependency_cycle" else "package_pair"
    if not isinstance(row, list) or len(row) != columns[name]: _fail(path, where, f"a list of {columns[name]} values")
    def index(value: Any, at: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < columns["count"]: _fail(path, at, "an integer index within file_ids")
    if name == "file_pair":
        index(row[0], where + "[0]"); index(row[1], where + "[1]")
        return
    _string(row[0], path, where + "[0]"); _string(row[1], path, where + "[1]")
    pairs = row[6]
    if not isinstance(pairs, list): _fail(path, where + "[6]", "a list")
    for position, pair in enumerate(pairs):
        if not isinstance(pair, list) or len(pair) != 2: _fail(path, f"{where}[6][{position}]", "a pair of indices")
        index(pair[0], f"{where}[6][{position}][0]"); index(pair[1], f"{where}[6][{position}][1]")


def _check_violation(candidate: Mapping[str, Any], path: str, where: str) -> None:
    structure = _object(candidate.get("structure"), path, where + ".structure")
    _string(structure.get("rule_type"), path, where + ".structure.rule_type")
    _string(structure.get("from_layer"), path, where + ".structure.from_layer")
    if "to_layer" in structure: _string(structure["to_layer"], path, where + ".structure.to_layer")
    elif "to_external" in structure: _string(structure["to_external"], path, where + ".structure.to_external")
    else: _fail(path, where + ".structure", "an object with a string to_layer or to_external")


def _check_general(candidate: Mapping[str, Any], path: str, where: str) -> None:
    _string(candidate.get("target"), path, where + ".target")
    metrics = _object(candidate.get("metrics"), path, where + ".metrics")
    for name in _STRENGTH_METRICS.get(candidate["kind"], ()):
        if name in metrics and not _number(metrics[name]): _fail(path, f"{where}.metrics.{name}", "a number")
    if candidate["kind"] in _EVIDENCE_KINDS:
        evidence = candidate.get("evidence")
        if not isinstance(evidence, list): _fail(path, where + ".evidence", "a list")
        for index, record in enumerate(evidence): _object(record, path, f"{where}.evidence[{index}]")


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


def _pairs(candidate: Mapping[str, Any], file_ids: list | None = None) -> set[tuple[str, str]]:
    if file_ids is None: return {(record["from_id"], record["to_id"]) for record in candidate["evidence"]}
    if candidate["kind"] == "package_cycle": return {(row[0], row[1]) for row in candidate["evidence"]}
    return {(file_ids[row[0]], file_ids[row[1]]) for row in candidate["evidence"]}


def _cycle_delta(current: list, baseline: list, current_ids: list | None = None, baseline_ids: list | None = None) -> tuple[list, list, int]:
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
            known_pairs = set().union(*(_pairs(base_cycles[index], baseline_ids) for index in overlap)) if overlap else set()
            item = {"candidate_id": cycle["id"], "kind": key[0], "scheme": key[1], "tier": key[2], "members": sorted(members),
                    "baseline_candidate_ids": sorted(base_cycles[index]["id"] for index in overlap), "added_members": sorted(added),
                    "new_internal_pairs": [list(pair) for pair in sorted(_pairs(cycle, current_ids) - known_pairs)]}
            (grown if overlap else new).append(item)
    current_members = {key: {member for cycle in cycles for member in cycle["structure"]["members"]} for key, cycles in current_by_key.items()}
    for key, cycles in base_by_key.items():
        present = current_members.get(key, set())
        resolved += sum(1 for cycle in cycles if present.isdisjoint(cycle["structure"]["members"]))
    order = lambda item: (item["kind"], item["scheme"], item["tier"], item["candidate_id"])
    return sorted(new, key=order), sorted(grown, key=order), resolved


def _violation_key(candidate: Mapping[str, Any]) -> tuple:
    structure, evidence = candidate["structure"], candidate.get("evidence")
    first = evidence[0].get("to_id") if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict) else None
    return (structure["rule_type"], structure["from_layer"], structure.get("to_layer"), structure.get("to_external"), candidate["target"], first)


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


def _signatures(candidate: Mapping[str, Any]) -> set[tuple[str, ...]]:
    kind, found = candidate["kind"], set()
    evidence = candidate.get("evidence")
    if kind not in _EVIDENCE_KINDS or not isinstance(evidence, list): return found
    for record in evidence:
        if not isinstance(record, dict): continue
        if kind == "dangling_doc_reference":
            if isinstance(record.get("notation"), str) and isinstance(record.get("text"), str): found.add(("doc", record["notation"], record["text"]))
            continue
        node = record["node_id"] if isinstance(record.get("node_id"), str) else candidate.get("target")
        references, flags = record.get("unresolved_references"), record.get("flags")
        if isinstance(references, list):
            found.update(("reference", node, item["name"]) for item in references if isinstance(item, dict) and isinstance(item.get("name"), str))
        if isinstance(flags, list): found.update(("flag", node, flag) for flag in flags if isinstance(flag, str))
        if isinstance(record.get("from_id"), str) and isinstance(record.get("to_id"), str):
            relation = record.get("relation")
            found.add(("edge", record["from_id"], record["to_id"], relation if isinstance(relation, str) else ""))
    return found


def _general(candidates: Iterable[Mapping[str, Any]]) -> dict[tuple, Mapping[str, Any]]:
    keys = []
    seen: dict[tuple, int] = {}
    chosen = [candidate for candidate in candidates if candidate.get("kind") not in _SPECIAL_KINDS]
    for candidate in chosen:
        structure = candidate.get("structure")
        if isinstance(structure, dict): structure = json.dumps({k: v for k, v in structure.items() if k != "tier"}, sort_keys=True)
        else: structure = "" if structure is None else json.dumps(structure, sort_keys=True)
        key = (candidate.get("kind"), candidate.get("target"), structure)
        keys.append(key)
        seen[key] = seen.get(key, 0) + 1
    return {(key + (candidate.get("id"),) if seen[key] > 1 else key): candidate for key, candidate in zip(keys, chosen)}


def _general_delta(current: Iterable[Mapping[str, Any]], baseline: Iterable[Mapping[str, Any]]) -> tuple[list, list, int]:
    now, then = _general(current), _general(baseline)
    new, strengthened = [], []
    for key, candidate in now.items():
        before = then.get(key)
        if before is None:
            new.append({"candidate_id": candidate.get("id"), "kind": candidate["kind"], "target": candidate.get("target"), "metrics": candidate.get("metrics")})
            continue
        increased = {}
        now_metrics, then_metrics = candidate.get("metrics"), before.get("metrics")
        if isinstance(now_metrics, dict) and isinstance(then_metrics, dict):
            for name in _STRENGTH_METRICS.get(candidate["kind"], ()):
                if _number(now_metrics.get(name)) and _number(then_metrics.get(name)) and now_metrics[name] > then_metrics[name]:
                    increased[name] = {"baseline": then_metrics[name], "current": now_metrics[name]}
        added = sorted(_signatures(candidate) - _signatures(before))
        if increased or added:
            strengthened.append({"candidate_id": candidate.get("id"), "baseline_candidate_id": before.get("id"), "kind": candidate["kind"], "target": candidate.get("target"),
                                 "increased": increased, "added_evidence": [list(item) for item in added]})
    order = lambda item: (item["kind"], item["target"], item["candidate_id"])
    return sorted(new, key=order), sorted(strengthened, key=order), len(then.keys() - now.keys())


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


_NOT_REQUESTED = {"status": "skipped", "reason": "not_requested", "pairs": []}


def _remap(value: Any, substitute: Callable[[str], str]) -> Any:
    if isinstance(value, str): return substitute(value)
    if isinstance(value, list): return [_remap(item, substitute) for item in value]
    if isinstance(value, dict): return {key: _remap(item, substitute) for key, item in value.items()}
    return value


def _module_name(path: str) -> str:
    module = path[:-len(".py")]
    if module.endswith("/__init__"): module = module[:-len("/__init__")]
    return module.replace("/", ".")


def _substituter(mapping: Mapping[str, str]) -> Callable[[str], str]:
    # A path only counts when it is a whole path segment of the id: at the start or after ":", and at the end or before "#".
    paths = re.compile(r"(?<![^:])(?:" + "|".join(re.escape(old) for old in sorted(mapping, key=len, reverse=True)) + r")(?![^#])")
    modules = {_module_name(old): _module_name(new) for old, new in mapping.items() if old.endswith(".py") and new.endswith(".py")}
    modules = {old: new for old, new in modules.items() if old != new}
    symbols = re.compile(r"py:(" + "|".join(re.escape(old) for old in sorted(modules, key=len, reverse=True)) + r")(?![^#])") if modules else None
    def substitute(value: str) -> str:
        value = paths.sub(lambda found: mapping[found.group(0)], value)
        return symbols.sub(lambda found: "py:" + modules[found.group(1)], value) if symbols and value.startswith("py:") else value
    return substitute


def _remap_baseline(baseline: Mapping[str, Any], mapping: Mapping[str, str]) -> dict:
    result = copy.deepcopy(dict(baseline))
    substitute = _substituter(mapping)
    def fix(value: Any) -> Any: return _remap(value, substitute)
    network = result.get("dependency_network") or {}
    if "file_ids" in network: network["file_ids"] = fix(network["file_ids"])
    for pairs in (network.get("package_dependencies") or {}).values():
        for pair in pairs:
            pair["from_id"], pair["to_id"] = fix(pair["from_id"]), fix(pair["to_id"])
    metrics = network.get("package_metrics") or {}
    for scheme, packages in metrics.items(): metrics[scheme] = {fix(package): record for package, record in packages.items()}
    for candidate in result.get("candidates", []):
        if "target" in candidate: candidate["target"] = fix(candidate["target"])
        structure = candidate.get("structure")
        if candidate.get("kind") == "rule_violation": pass
        elif candidate.get("kind") in _CYCLE_KINDS: structure["members"] = fix(structure["members"])
        elif structure is not None: candidate["structure"] = fix(structure)
        evidence = candidate.get("evidence")
        for record in evidence if isinstance(evidence, list) else [evidence]:
            if isinstance(record, dict):
                for key in ("from_id", "to_id", "node_id"):
                    if key in record: record[key] = fix(record[key])
            elif isinstance(record, list):
                for position in (0, 1):
                    if isinstance(record[position], str): record[position] = fix(record[position])
    return result


def compute_delta(current: Mapping[str, Any], baseline: Mapping[str, Any], renames: Mapping[str, Any] | None = None) -> dict:
    renames = dict(_NOT_REQUESTED) if renames is None else renames
    mapping = {pair["from"]: pair["to"] for pair in renames["pairs"] if pair["from"] != pair["to"]}
    if mapping: baseline = _remap_baseline(baseline, mapping)
    current_network, baseline_network = current.get("dependency_network") or {}, baseline.get("dependency_network") or {}
    if current_network.get("structure_policy") != baseline_network.get("structure_policy"):
        raise BaselineError(f"baseline: structure_policy {baseline_network.get('structure_policy')!r} differs from current {current_network.get('structure_policy')!r}")
    current_rules = (current.get("coverage") or {}).get("architecture_rules")
    baseline_rules = (baseline.get("coverage") or {}).get("architecture_rules")
    if (current_rules is None) != (baseline_rules is None):
        raise BaselineError("baseline: architecture rules were used by only one of the baseline and the current run")
    digest = None if baseline_rules is None else baseline_rules.get("rules_sha256")
    rules_changed = current_rules is not None and (digest is None or current_rules.get("rules_sha256") != digest)

    new_cycles, grown_cycles, resolved_cycles = _cycle_delta(current["candidates"], baseline["candidates"], current_network.get("file_ids"), baseline_network.get("file_ids"))
    current_violations, baseline_violations = _violations(current["candidates"]), _violations(baseline["candidates"])
    current_keys = {_violation_key(candidate) for candidate in current_violations.values()}
    baseline_keys = {_violation_key(candidate) for candidate in baseline_violations.values()}
    new_violations = [_violation_item(current_violations[found]) for found in sorted(current_violations) if _violation_key(current_violations[found]) not in baseline_keys]
    resolved_violations = sum(1 for candidate in baseline_violations.values() if _violation_key(candidate) not in current_keys)
    current_pairs, baseline_pairs = _dependency_map(current_network), _dependency_map(baseline_network)
    new_pairs = [{"scheme": key[0], "from_id": key[1], "to_id": key[2], "tier": current_pairs[key]} for key in sorted(set(current_pairs) - set(baseline_pairs))]
    changes = _instability_changes(current_network, baseline_network)
    new_candidates, strengthened, resolved_candidates = _general_delta(current["candidates"], baseline["candidates"])
    delta = {"policy": DELTA_POLICY, "renames": {"status": renames["status"], "reason": renames["reason"], "pairs": [dict(pair) for pair in renames["pairs"]]}, "baseline": {"file_count": baseline["snapshot"]["file_count"], "rules_sha256": digest}, "rules_changed": rules_changed,
             "new_cycles": new_cycles, "grown_cycles": grown_cycles, "new_violations": new_violations,
             "new_package_dependencies": new_pairs, "instability_changes": changes,
             "new_candidates": new_candidates, "strengthened_candidates": strengthened,
             "resolved": {"cycles": resolved_cycles, "violations": resolved_violations,
                          "package_dependencies": len(set(baseline_pairs) - set(current_pairs)), "candidates": resolved_candidates}}
    delta["counts"] = {name: len(delta[name]) for name in _LIST_NAMES}
    return delta


def regressions(delta: Mapping[str, Any], fail_on: Iterable[str]) -> list[str]:
    selected = set(fail_on)
    if "any" in selected: selected |= {"cycle", "violation"}
    result = []
    if "cycle" in selected and (delta["new_cycles"] or delta["grown_cycles"]): result.append("cycle")
    if "violation" in selected and delta["new_violations"]: result.append("violation")
    return result
