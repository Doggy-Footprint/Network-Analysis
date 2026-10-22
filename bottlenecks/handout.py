import json
from typing import Any, Mapping

_TOP = 10
_CUTS = 5
_EVIDENCE = 3
_TIER_ORDER = {"all": 0, "resolved": 1, "certain": 2}
_SORTS = {
    "evidence_spread": lambda c: (-_metric(c, "directory_count"), -_metric(c, "file_count")),
    "dependency_cycle": lambda c: (-_metric(c, "member_count"), _TIER_ORDER.get((c.get("structure") or {}).get("tier"), 3)),
    "package_cycle": lambda c: (-_metric(c, "member_count"), _TIER_ORDER.get((c.get("structure") or {}).get("tier"), 3)),
    "unstable_dependency": lambda c: (-_metric(c, "evidence_count"), -_metric(c, "instability_delta")),
    "large_node": lambda c: (-_metric(c, "token_count"),),
    "unresolved_boundary": lambda c: (-_metric(c, "unresolved_count"),),
    "isolated_node": lambda c: (-_metric(c, "line_count"),),
    "untested_hub": lambda c: (_metric(c, "pagerank_rank"),),
    "rule_violation": lambda c: (-_metric(c, "evidence_count"),),
}
_EDGE_ITEM_KEYS = ("uncertain_test_edges", "edges")


def _metric(candidate: Mapping[str, Any], name: str) -> float:
    value = (candidate.get("metrics") or {}).get(name)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _path(file_id: str) -> str:
    return file_id[5:] if file_id.startswith("file:") else file_id


def _value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _items(candidate: Mapping[str, Any]) -> list:
    evidence = candidate.get("evidence")
    if isinstance(evidence, dict):
        for key in _EDGE_ITEM_KEYS:
            if isinstance(evidence.get(key), list) and evidence[key]:
                return evidence[key]
        return [evidence]
    return list(evidence) if isinstance(evidence, list) else []


def _describe(candidate: Mapping[str, Any], item: Any, file_ids: list, edges: list) -> str:
    kind = candidate["kind"]
    if isinstance(item, int) and not isinstance(item, bool):
        edge = edges[item] if 0 <= item < len(edges) else None
        if edge is None:
            return f"detail edge #{item}"
        where = edge.get("evidence") or {}
        return f"`{edge.get('from_id')}` → `{edge.get('to_id')}` ({edge.get('relation')}) at `{where.get('file_path')}:{where.get('start_line')}`"
    if isinstance(item, list):
        if kind == "package_cycle":
            return f"`{item[0]}` → `{item[1]}` ({', '.join(item[2])})"
        source, target = (file_ids[item[0]], file_ids[item[1]]) if file_ids else (item[0], item[1])
        return f"`{_path(source)}` → `{_path(target)}` ({', '.join(item[2])})"
    if isinstance(item, Mapping):
        if kind in ("dependency_cycle", "package_cycle", "unstable_dependency") and "from_id" in item:
            return f"`{_path(item['from_id'])}` → `{_path(item['to_id'])}` ({', '.join(item.get('relations') or [])})"
        where = item.get("evidence") or {}
        path = item.get("path") or where.get("file_path")
        line = item.get("start_line", where.get("start_line"))
        if path:
            return f"`{path}:{line}`" if line is not None else f"`{path}`"
        return f"`{item.get('to_id') or item.get('node_id') or _value(item)}`"
    return f"`{item}`"


def _candidate_lines(candidate: Mapping[str, Any], file_ids: list, edges: list) -> list[str]:
    lines = [f"- `{candidate['id']}` target `{candidate['target']}`"]
    metrics = candidate.get("metrics") or {}
    lines.append("  - metrics: " + (", ".join(f"{key}={_value(metrics[key])}" for key in sorted(metrics)) or "none"))
    structure = candidate.get("structure")
    if structure and "members" in structure:
        lines.append(f"  - structure: scheme {structure.get('scheme')}, tier {structure.get('tier')}, {len(structure['members'])} members")
        for cut in (structure.get("cut_candidates") or [])[:_CUTS]:
            lines.append(f"    - cut `{_path(cut['from_id'])}` → `{_path(cut['to_id'])}` ({', '.join(cut['relations'])}), max_weight {_value(cut['max_weight'])}")
    elif structure:
        lines.append(f"  - structure: {', '.join(f'{key}={_value(structure[key])}' for key in sorted(structure))}")
    items = _items(candidate)
    lines.append(f"  - evidence: {len(items)} items")
    for item in items[:_EVIDENCE]:
        lines.append("    - " + _describe(candidate, item, file_ids, edges))
    return lines


def _instability_key(item: tuple) -> tuple:
    value = item[1].get("instability")
    return (value is None, -(value or 0), item[0])


def render_handout(report: Mapping, architecture: Mapping) -> str:
    network = report.get("dependency_network") or {}
    file_ids = network.get("file_ids") or []
    edges = (architecture.get("details") or {}).get("edges") or []
    candidates = report.get("candidates") or []
    out = ["# Dependency bottleneck handout", "",
           f"- Project: {architecture.get('project_name')}",
           f"- Files: {(report.get('snapshot') or {}).get('file_count')}",
           f"- Dependency edges: {network.get('edge_count')}", "",
           "## How to read", "",
           "- Relation: the kind of dependency between two files (IMPORTS, CALLS, ...). Edge columns list every relation found for the pair.",
           "- Confidence: how the analyzer found the relation (static_certain, framework_inferred, dynamic_required, ...).",
           "- Resolution: how precisely the target was identified (exact, unique_name, ambiguous, unresolved).",
           "- Weight: the configured discount for the edge's confidence and resolution; max_weight is the largest weight among a pair's edges. Uncertain relations are kept, with lower weight.",
           "- Tier: certain (exact and static_certain), resolved (exact or unique_name), all (everything). Each tier includes the stronger tiers.",
           "- Candidates are structural facts to review, not verdicts.",
           f"- bottlenecks.json holds every candidate. The details file ({report.get('details_file') or 'not recorded'}) holds the full edge list.",
           "- evidence_spread evidence in bottlenecks.json is a list of indices into `edges` of the details file (0-based).",
           "- Cycle and unstable_dependency evidence rows are `[from, to, relations, max_weight, evidence_count, tier]`; from and to index `dependency_network.file_ids`. package_cycle rows end with `file_pairs`, pairs of `file_ids` indices.",
           "", "## Candidate counts", ""]
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate["kind"]] = counts.get(candidate["kind"], 0) + 1
    out += ["| kind | count |", "| --- | --- |"] + [f"| {kind} | {counts[kind]} |" for kind in sorted(counts)]
    out += ["", "## Production rankings", ""]
    for key, rows in sorted(((report.get("dependency_network") or {}).get("rankings_by_category") or {}).get("production", {}).items()):
        out += [f"### {key}", ""] + [f"{rank}. `{row['node_id']}` {_value(row['value'])}" for rank, row in enumerate(rows[:_TOP], 1)] + [""]
    out += ["## Packages", ""]
    for scheme, packages in sorted((network.get("package_metrics") or {}).items()):
        out += [f"### {scheme}", ""]
        for package, record in sorted(packages.items(), key=_instability_key)[:_TOP]:
            out.append(f"- `{package}` instability {_value(record.get('instability'))}, file_count {record.get('file_count')}, ca {record.get('ca')}, ce {record.get('ce')}")
        out.append("")
    out += ["## Candidates", ""]
    if not candidates:
        out += ["No candidates.", ""]
    for kind in sorted(counts):
        ranked = sorted((c for c in candidates if c["kind"] == kind), key=lambda c: (*_SORTS.get(kind, lambda _c: ())(c), c["id"]))
        out += [f"### {kind}", ""]
        for candidate in ranked[:_TOP]:
            out += _candidate_lines(candidate, file_ids, edges)
        if len(ranked) > _TOP:
            out.append(f"… {len(ranked) - _TOP} more {kind} candidates in bottlenecks.json")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"
