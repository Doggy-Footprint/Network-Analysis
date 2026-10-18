import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

STRUCTURE_POLICY = "structure.v1"
TIERS = ("certain", "resolved", "all")
_RANK = {tier: index for index, tier in enumerate(TIERS)}
_CUT_LIMIT = 10


@dataclass(frozen=True)
class StructureResult:
    candidates: tuple
    package_metrics: Mapping[str, Mapping[str, Mapping]]
    coverage: Mapping[str, Mapping]


def _field(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, Mapping) else getattr(item, name, default)


def edge_tier(edge: Any) -> str:
    confidence, resolution = str(_field(edge, "confidence")), str(_field(edge, "resolution"))
    if resolution == "exact": return "certain" if confidence == "static_certain" else "resolved"
    return "resolved" if resolution == "unique_name" else "all"


def strongly_connected_components(nodes: Iterable[str], adjacency: Mapping[str, Iterable[str]]) -> list[list[str]]:
    order = sorted(set(nodes)); known = set(order)
    successors = {node: sorted(set(adjacency.get(node, ())) & known) for node in order}
    index, low, on_stack, stack, result, counter = {}, {}, set(), [], [], 0
    for root in order:
        if root in index: continue
        index[root] = low[root] = counter; counter += 1; stack.append(root); on_stack.add(root)
        work = [(root, iter(successors[root]))]
        while work:
            node, children = work[-1]
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter; counter += 1; stack.append(child); on_stack.add(child)
                    work.append((child, iter(successors[child])))
                    break
                if child in on_stack: low[node] = min(low[node], index[child])
            else:
                work.pop()
                if work: low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    component = []
                    while True:
                        member = stack.pop(); on_stack.discard(member); component.append(member)
                        if member == node: break
                    if len(component) > 1: result.append(sorted(component))
    return sorted(result)


def _file_ids(architecture: Any) -> list[str]:
    return sorted(node.id for node in architecture.nodes if not (getattr(node, "metadata", {}) or {}).get("boundary"))


def _details(architecture: Any) -> Mapping[str, Any]:
    return getattr(architecture, "details", None) or {}


def _file_path(file_id: str) -> str:
    return file_id[5:] if file_id.startswith("file:") else file_id


def _language_packages(files: list[str], details: Mapping[str, Any]) -> dict[str, list[str]]:
    node_files = details.get("node_files") or {}
    nodes = {node["id"]: node for node in details.get("nodes") or []}
    modules = {}
    for node_id in sorted(nodes):
        node = nodes[node_id]
        if node.get("provenance") == "python-core" and node.get("kind") == "module" and node_files.get(node_id):
            modules.setdefault(node_files[node_id], node)
    kotlin = {}
    for edge in details.get("edges") or []:
        source, target = edge["from_id"], edge["to_id"]
        if edge.get("relation") == "CONTAINS" and source.startswith("kotlin-package:") and nodes.get(target, {}).get("provenance") == "kotlin-core" and nodes[target].get("kind") == "file" and node_files.get(target):
            kotlin.setdefault(node_files[target], source[len("kotlin-package:"):])
    result = {}
    for file_id in files:
        path = _file_path(file_id)
        if file_id in modules:
            module = modules[file_id]; dotted = module.get("symbol_path") or module["id"].removeprefix("py:")
            package = dotted if path.rsplit("/", 1)[-1] == "__init__.py" else dotted.rpartition(".")[0] or "(root)"
            result[file_id] = ["pkg:python:" + package]
        elif file_id in kotlin: result[file_id] = ["pkg:kotlin:" + kotlin[file_id]]
        else: result[file_id] = ["pkg:dir:" + (path.rpartition("/")[0] or ".")]
    return result


def _framework_packages(files: list[str], details: Mapping[str, Any]) -> dict[str, list[str]] | None:
    node_files = details.get("node_files") or {}
    modules = sorted(node["id"] for node in details.get("nodes") or [] if node.get("provenance") == "nestjs" and node.get("kind") == "module")
    if not modules: return None
    members = {module: {node_files.get(module)} for module in modules}
    for edge in details.get("edges") or []:
        if edge.get("relation") in {"DECLARES", "PROVIDES"} and edge["from_id"] in members: members[edge["from_id"]].add(node_files.get(edge["to_id"]))
    result = {file_id: [] for file_id in files}
    for module in modules:
        package = "pkg:nestjs:" + module.removeprefix("nestjs:module:")
        for file_id in sorted(item for item in members[module] if item in result):
            if package not in result[file_id]: result[file_id].append(package)
    return {file_id: sorted(packages) for file_id, packages in result.items() if packages}


def _assignments(architecture: Any) -> tuple[list[str], dict[str, dict[str, list[str]]]]:
    files, details = _file_ids(architecture), _details(architecture)
    schemes = {"language": _language_packages(files, details)}
    framework = _framework_packages(files, details)
    if framework is not None: schemes["framework"] = framework
    return files, schemes


def package_assignments(architecture: Any) -> dict[str, dict[str, list[str]]]:
    return _assignments(architecture)[1]


def _file_pairs(architecture: Any, weights: Any, files: set[str]) -> dict[str, dict[tuple[str, str], dict]]:
    edges = []
    for edge in architecture.edges:
        if _field(edge, "relation") == "TESTS" or _field(edge, "from_id") not in files or _field(edge, "to_id") not in files: continue
        metadata = _field(edge, "metadata") or {}
        edges.append((_RANK[edge_tier(edge)], edge, weights.weight_for(edge) * metadata.get("candidate_share", 1), metadata))
    result = {}
    for tier in TIERS:
        pairs = {}
        for rank, edge, weight, metadata in edges:
            if rank > _RANK[tier]: continue
            key = (_field(edge, "from_id"), _field(edge, "to_id"))
            record = pairs.get(key)
            if record is None:
                record = pairs[key] = {"from_id": key[0], "to_id": key[1], "relations": set(), "max_weight": weight, "evidence_count": 0, "detail_edge_indices": set(), "rank": rank}
            record["relations"].add(_field(edge, "relation")); record["max_weight"] = max(record["max_weight"], weight)
            record["evidence_count"] += metadata.get("evidence_count", 1); record["detail_edge_indices"].update(metadata.get("detail_edge_indices", ())); record["rank"] = min(record["rank"], rank)
        for record in pairs.values():
            record["relations"] = sorted(record["relations"]); record["detail_edge_indices"] = sorted(record["detail_edge_indices"]); record["tier"] = TIERS[record.pop("rank")]
        result[tier] = dict(sorted(pairs.items()))
    return result


def _package_pairs(file_pairs: Mapping[tuple[str, str], dict], assignment: Mapping[str, list[str]]) -> dict[tuple[str, str], dict]:
    pairs = {}
    for (source, target), record in file_pairs.items():
        for left in assignment.get(source, ()):
            for right in assignment.get(target, ()):
                if left == right: continue
                item = pairs.get((left, right))
                if item is None:
                    item = pairs[(left, right)] = {"from_id": left, "to_id": right, "relations": set(), "max_weight": record["max_weight"], "evidence_count": 0, "file_pairs": [], "rank": _RANK[record["tier"]]}
                item["relations"].update(record["relations"]); item["max_weight"] = max(item["max_weight"], record["max_weight"])
                item["evidence_count"] += record["evidence_count"]; item["file_pairs"].append([source, target]); item["rank"] = min(item["rank"], _RANK[record["tier"]])
    for item in pairs.values():
        item["relations"] = sorted(item["relations"]); item["file_pairs"].sort(); item["tier"] = TIERS[item.pop("rank")]
    return dict(sorted(pairs.items()))


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _cycle_candidates(scheme: str, pairs_by_tier: Mapping[str, Mapping[tuple[str, str], dict]], nodes: Iterable[str], kind: str) -> list[dict]:
    from bottlenecks.core import _candidate
    nodes, candidates, ids_by_tier = sorted(set(nodes)), [], {}
    for tier in TIERS:
        pairs = pairs_by_tier[tier]
        adjacency = {}
        for source, target in pairs: adjacency.setdefault(source, []).append(target)
        components = strongly_connected_components(nodes, adjacency)
        component_of = {member: index for index, members in enumerate(components) for member in members}
        internal_pairs = [[] for _ in components]
        for (source, target), record in pairs.items():
            if source in component_of and component_of[source] == component_of.get(target): internal_pairs[component_of[source]].append(record)
        ids_by_tier[tier] = [(set(members), "b:" + _digest("cycle|%s|%s|%s" % (scheme, tier, "\n".join(members)))) for members in components]
        for members, internal in zip(components, internal_pairs):
            identifier = "cycle|%s|%s|%s" % (scheme, tier, "\n".join(members))
            cuts = sorted(internal, key=lambda record: (record["max_weight"], record["evidence_count"], record["from_id"], record["to_id"]))[:_CUT_LIMIT]
            candidate = _candidate(identifier, kind, "cycle:%s:%s:%s" % (scheme, tier, _digest(identifier)),
                {"member_count": len(members), "internal_pair_count": len(internal), "internal_evidence_count": sum(record["evidence_count"] for record in internal), "min_pair_weight": min(record["max_weight"] for record in internal)},
                internal, "static_analyzer_relation")
            candidate["structure"] = {"scheme": scheme, "tier": tier, "members": members, "parent_id": None,
                "cut_candidates": [{key: record[key] for key in ("from_id", "to_id", "relations", "max_weight", "evidence_count")} for record in cuts]}
            candidates.append(candidate)
    for candidate in candidates:
        tier = candidate["structure"]["tier"]
        if tier == "all": continue
        members = set(candidate["structure"]["members"])
        candidate["structure"]["parent_id"] = next((cid for parent, cid in ids_by_tier[TIERS[_RANK[tier] + 1]] if members <= parent), None)
    return candidates


def _instability(ca: int, ce: int, weighted_ca: float, weighted_ce: float) -> tuple:
    return (ce / (ca + ce) if ca + ce else None, weighted_ce / (weighted_ca + weighted_ce) if weighted_ca + weighted_ce else None)


def _package_metrics(assignment: Mapping[str, list[str]], pairs: Mapping[tuple[str, str], dict]) -> dict[str, dict]:
    metrics = {}
    for packages in assignment.values():
        for package in packages:
            metrics.setdefault(package, {"file_count": 0, "ca": 0, "ce": 0, "weighted_ca": 0, "weighted_ce": 0})["file_count"] += 1
    for (source, target), record in pairs.items():
        metrics[source]["ce"] += 1; metrics[source]["weighted_ce"] += record["max_weight"]
        metrics[target]["ca"] += 1; metrics[target]["weighted_ca"] += record["max_weight"]
    for item in metrics.values():
        item["instability"], item["weighted_instability"] = _instability(item["ca"], item["ce"], item["weighted_ca"], item["weighted_ce"])
    return {package: metrics[package] for package in sorted(metrics)}


def _unstable_candidates(scheme: str, pairs: Mapping[tuple[str, str], dict], metrics: Mapping[str, dict], file_pairs: Mapping[tuple[str, str], dict]) -> list[dict]:
    from bottlenecks.core import _candidate
    candidates = []
    for (source, target), record in pairs.items():
        left, right = metrics[source], metrics[target]
        if left["instability"] is None or right["instability"] is None or not right["instability"] > left["instability"]: continue
        values = {"instability_from": left["instability"], "instability_to": right["instability"], "instability_delta": right["instability"] - left["instability"],
            "evidence_count": record["evidence_count"], "file_pair_count": len(record["file_pairs"])}
        if left["weighted_instability"] is not None: values["weighted_instability_from"] = left["weighted_instability"]
        if right["weighted_instability"] is not None: values["weighted_instability_to"] = right["weighted_instability"]
        candidate = _candidate("unstable|%s|%s|%s" % (scheme, source, target), "unstable_dependency", source, values,
            [file_pairs[tuple(pair)] for pair in record["file_pairs"]], "static_analyzer_relation")
        candidate["structure"] = {"scheme": scheme, "tier": record["tier"], "from_package": source, "to_package": target}
        candidates.append(candidate)
    return candidates


def _external_violations(rules: Any, layers: Mapping[str, str], records_by_file: Mapping[str, list]) -> list[dict]:
    from analysis.architecture_rules import external_entries_matcher, external_entry_matches
    from bottlenecks.core import _candidate
    matchers = {}
    decisions: dict[tuple[str, str], tuple[tuple[str, ...], bool]] = {}

    def decide(layer: str, name: str) -> tuple[tuple[str, ...], bool]:
        found = decisions.get((layer, name))
        if found is None:
            if layer not in matchers:
                matchers[layer] = (external_entries_matcher(rules, rules.forbid_external.get(layer, ())),
                                   external_entries_matcher(rules, rules.allow_external.get(layer, ())) if layer in rules.allow_external else None)
            forbidden, allowed = matchers[layer]
            matched = tuple(entry for entry in rules.forbid_external.get(layer, ()) if external_entry_matches(rules, entry, name)) if forbidden(name) else ()
            found = decisions[(layer, name)] = (matched, allowed is not None and not allowed(name))
        return found

    candidates = []
    for file_id, layer in layers.items():
        by_name: dict[str, list] = {}
        for record in records_by_file.get(file_id, ()): by_name.setdefault(record["name"], []).append(record)
        for name in sorted(by_name):
            matched, outside = decide(layer, name)
            records = by_name[name]
            tier = "certain" if any(not record.get("dynamic") for record in records) else "resolved"
            for rule_type, violated, entries in (("forbid_external", bool(matched), matched), ("allow_external", outside, ())):
                if not violated: continue
                candidate = _candidate("rule|%s|%s|%s|%s" % (rule_type, layer, file_id, name), "rule_violation", file_id,
                    {"evidence_count": len(records)}, records, "static_analyzer_relation")
                candidate["structure"] = {"rule_type": rule_type, "from_layer": layer, "to_external": name, "matched": list(entries), "tier": tier, "relations": ["IMPORTS"]}
                candidates.append(candidate)
    return candidates


def _rule_violations(rules: Any, files: list[str], assignments: Mapping[str, Mapping[str, list[str]]], pairs: Mapping[tuple[str, str], dict], records_by_file: Mapping[str, list] | None = None) -> tuple[list[dict], dict]:
    from analysis.architecture_rules import RULES_POLICY, layer_assignments
    from bottlenecks.core import _candidate
    layers = layer_assignments(rules, files, assignments)
    candidates = []
    for (source, target), record in pairs.items():
        left, right = layers.get(source), layers.get(target)
        if left is None or right is None or left == right: continue
        for rule_type, violated in (("allow", left in rules.allow and right not in rules.allow[left]), ("forbid", right in rules.forbid.get(left, ()))):
            if not violated: continue
            candidate = _candidate("rule|%s|%s|%s|%s|%s" % (rule_type, left, right, source, target), "rule_violation", source,
                {"evidence_count": record["evidence_count"], "max_weight": record["max_weight"]}, [record], "static_analyzer_relation")
            candidate["structure"] = {"rule_type": rule_type, "from_layer": left, "to_layer": right, "tier": record["tier"], "relations": record["relations"]}
            candidates.append(candidate)
    counts = {name: 0 for name in rules.layers}
    for name in layers.values(): counts[name] += 1
    unassigned = [file_id for file_id in files if file_id not in layers]
    coverage = {"policy": RULES_POLICY, "version": rules.version, "layer_file_counts": dict(sorted(counts.items())), "unassigned_file_count": len(unassigned),
        "unassigned_files": unassigned, "empty_layers": sorted(name for name, count in counts.items() if not count)}
    if rules.forbid_external or rules.allow_external:
        external = _external_violations(rules, layers, records_by_file or {})
        candidates += external
        coverage["external_import_count"] = sum(len(records) for records in (records_by_file or {}).values())
        coverage["external_violation_count"] = len(external)
    coverage["violation_count"] = len(candidates)
    return candidates, coverage


def analyze_structure(architecture: Any, weights: Any, rules: Any = None) -> StructureResult:
    files, assignments = _assignments(architecture)
    file_pairs = _file_pairs(architecture, weights, set(files))
    candidates = _cycle_candidates("file", file_pairs, files, "dependency_cycle")
    package_metrics, schemes = {}, {}
    for scheme, assignment in assignments.items():
        pairs_by_tier = {tier: _package_pairs(file_pairs[tier], assignment) for tier in TIERS}
        packages = {package for packages in assignment.values() for package in packages}
        package_metrics[scheme] = _package_metrics(assignment, pairs_by_tier["all"])
        candidates += _cycle_candidates(scheme, pairs_by_tier, packages, "package_cycle")
        candidates += _unstable_candidates(scheme, pairs_by_tier["all"], package_metrics[scheme], file_pairs["all"])
        unassigned = [file_id for file_id in files if file_id not in assignment]
        shared = [file_id for file_id in files if len(assignment.get(file_id, ())) > 1]
        schemes[scheme] = {"assigned_file_count": len(files) - len(unassigned), "unassigned_file_count": len(unassigned), "unassigned_files": unassigned, "shared_file_count": len(shared), "shared_files": shared}
    coverage = {"structure": {"policy": STRUCTURE_POLICY, "schemes": schemes}}
    if rules is not None:
        records_by_file = {node.id: node.metadata["external_imports"] for node in architecture.nodes
                           if not (getattr(node, "metadata", None) or {}).get("boundary") and (getattr(node, "metadata", None) or {}).get("external_imports")}
        violations, coverage["architecture_rules"] = _rule_violations(rules, files, assignments, file_pairs["all"], records_by_file)
        candidates += violations
    return StructureResult(tuple(sorted(candidates, key=lambda item: (item["kind"], item["id"]))), package_metrics, coverage)
