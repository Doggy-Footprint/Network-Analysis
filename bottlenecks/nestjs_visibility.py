from typing import Any


def _exported(root: str, exports: dict, modules: set) -> set:
    providers, visited, pending = set(), set(), [root]
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        visited.add(module)
        for target in exports.get(module, ()):
            if target in modules:
                pending.append(target)
            else:
                providers.add(target)
    return providers


def unprovided_candidates(architecture: Any) -> list[dict]:
    from bottlenecks.core import _candidate
    details = architecture.details
    nestjs = {node["id"]: node for node in details["nodes"] if node.get("provenance") == "nestjs"}
    modules = {node_id for node_id, node in nestjs.items() if node["kind"] == "module"}
    imports, provides, exports, homes, dependencies = {}, {}, {}, {}, []
    for edge in details["edges"]:
        source, target, relation = edge["from_id"], edge["to_id"], edge["relation"]
        if source not in nestjs or target not in nestjs:
            continue
        if relation == "INCLUDES":
            imports.setdefault(source, set()).add(target)
        elif relation == "PROVIDES":
            provides.setdefault(source, set()).add(target)
            homes.setdefault(target, set()).add(source)
        elif relation == "DECLARES":
            homes.setdefault(target, set()).add(source)
        elif relation == "EXPORTS":
            exports.setdefault(source, set()).add(target)
        elif relation == "DEPENDS_ON":
            dependencies.append(edge)
    if not dependencies:
        return []
    global_exports = set()
    for module in sorted(modules):
        if nestjs[module]["metadata"].get("global"):
            global_exports |= _exported(module, exports, modules)
    cache: dict = {}

    def visible(module: str) -> set:
        if module not in cache:
            seen = set(provides.get(module, ())) | global_exports
            for imported in imports.get(module, ()):
                seen |= _exported(imported, exports, modules)
            cache[module] = seen
        return cache[module]

    node_files = details["node_files"]
    found: dict = {}
    for edge in sorted(dependencies, key=lambda item: (item["from_id"], item["to_id"])):
        consumer, provider = edge["from_id"], edge["to_id"]
        file = node_files[consumer]
        homes_of = sorted(homes.get(consumer, set()) | ({consumer} if consumer in modules else set()))
        if not homes_of:
            missing, certain = [], False
        else:
            missing = [module for module in homes_of if provider not in visible(module)]
            if not missing:
                continue
            certain = not any(nestjs[module]["metadata"].get("unsupported_fields") for module in missing)
        found.setdefault(file, []).append({"consumer_id": consumer, "provider_id": provider, "module_ids": missing,
                                           "certainty": "certain" if certain else "uncertain", "line": (edge.get("evidence") or {}).get("start_line")})
    candidates = []
    for file, records in sorted(found.items()):
        certain = sum(1 for record in records if record["certainty"] == "certain")
        candidates.append(_candidate(file + "|unprovided_injection", "unprovided_injection", file,
                                     {"unprovided_count": certain, "uncertain_count": len(records) - certain}, records, "static_analyzer_relation"))
    return candidates
