import re
from typing import Any

from analysis.candidate_projection import candidate_targets
from analysis.file_graph import _DECLARATION_KINDS, _LANGUAGE_PROVENANCE

_KINDS = frozenset({"function", "method", "class", "constant"})
_CONFIRMED = frozenset({"exact", "unique_name"})
_STATIC = frozenset({"static_certain", "static_inferred"})
_PRIVATE_WORDS = frozenset({"private", "protected", "internal"})
_WORD = re.compile(r"[^\s(<:=,{]+")
SYMBOL_COLUMNS = ["id", "file", "kind", "name", "signature", "visibility", "external_refs", "uncertain_external_refs"]
_EXCLUDED_NAMES = frozenset({"constructor", "main"})


def _ownership(edge: Any, nodes: dict) -> bool:
    # Mirrors analysis.file_graph.ownership_edge on serialized nodes.
    relation = edge["relation"]
    if relation == "IMPLEMENTED_BY":
        return True
    if relation not in {"CONTAINS", "DECLARES", "EXPORTS"}:
        return False
    source, target = nodes[edge["from_id"]], nodes[edge["to_id"]]
    return (source.get("provenance", "") in _LANGUAGE_PROVENANCE and target.get("provenance", "") in _LANGUAGE_PROVENANCE
            and (source.get("kind", "") or source.get("category", "")) in _DECLARATION_KINDS
            and (target.get("kind", "") or target.get("category", "")) in _DECLARATION_KINDS)


def incoming_index(architecture: Any) -> tuple[dict, set]:
    """(target id -> [confirmed source files, uncertain source files], ids implemented by a framework declaration).

    Presence in the first mapping means a non-ownership edge points at the node."""
    details = architecture.details
    node_files = details["node_files"]
    nodes = {node["id"]: node for node in details["nodes"]}
    index: dict = {}
    implemented: set = set()
    for edge in details["edges"]:
        if _ownership(edge, nodes):
            if edge["relation"] == "IMPLEMENTED_BY" and nodes[edge["from_id"]].get("provenance", "") not in _LANGUAGE_PROVENANCE:
                implemented.add(edge["to_id"])
            continue
        source = edge["from_id"]
        source_file = node_files[source]
        confirmed = edge.get("confidence") in _STATIC and edge.get("resolution") in _CONFIRMED
        for target in candidate_targets(edge):
            if target == source:
                continue
            files = index.setdefault(target, ([set(), set()]))
            if source_file is not None and source_file != node_files[target]:
                files[0 if confirmed else 1].add(source_file)
    return index, implemented


def _production_files(architecture: Any) -> set:
    from bottlenecks.core import _category
    file_nodes = architecture.details["file_nodes"]
    return {node.id for node in architecture.nodes if node.id in file_nodes and _category(node) == "production"}


def _name(node: dict) -> str:
    return node["metadata"].get("name") or node["label"]


def _modifiers(signature: str, name: str) -> set:
    found = set()
    for word in _WORD.findall(signature):
        if word == name or word.endswith("." + name):
            break
        found.add(word)
    return found


def symbol_table(architecture: Any, index: tuple | None = None) -> list[dict]:
    index = (incoming_index(architecture) if index is None else index)[0]
    production = _production_files(architecture)
    node_files = architecture.details["node_files"]
    table = []
    for node in architecture.details["nodes"]:
        kind = node["kind"]
        file = node_files[node["id"]]
        if kind not in _KINDS or file not in production:
            continue
        name = _name(node)
        signature = node.get("signature")
        signature = " ".join(signature.split()) if isinstance(signature, str) else None
        private = name[:1] in ("_", "#") or (signature is not None and not _PRIVATE_WORDS.isdisjoint(_modifiers(signature, name)))
        confirmed, uncertain = index.get(node["id"], (set(), set()))
        table.append({"id": node["id"], "file": file, "kind": kind, "name": name, "signature": signature,
                      "visibility": "private" if private else "public",
                      "external_refs": len(confirmed), "uncertain_external_refs": len(uncertain - confirmed)})
    return sorted(table, key=lambda item: item["id"])


def symbol_rows(table: list[dict], file_ids: list[str]) -> list[list]:
    position = {file_id: number for number, file_id in enumerate(file_ids)}
    return [[item["id"], position[item["file"]], *(item[name] for name in SYMBOL_COLUMNS[2:])] for item in table]


def unreferenced_candidates(architecture: Any, index: tuple | None = None) -> list[dict]:
    from bottlenecks.core import _candidate
    referenced, implemented = incoming_index(architecture) if index is None else index
    production = _production_files(architecture)
    node_files = architecture.details["node_files"]
    found: dict = {}
    for node in architecture.details["nodes"]:
        file = node_files[node["id"]]
        if node["kind"] not in ("function", "method") or file not in production or node["id"] in referenced or node["id"] in implemented:
            continue
        name = _name(node)
        if name in _EXCLUDED_NAMES or (len(name) > 4 and name.startswith("__") and name.endswith("__")):
            continue
        signature = node.get("signature")
        if isinstance(signature, str) and "override" in _modifiers(" ".join(signature.split()), name):
            continue
        span = node.get("span") or {}
        found.setdefault(file, []).append({"node_id": node["id"], "name": name, "kind": node["kind"], "start_line": span.get("start_line")})
    return [_candidate(file + "|unreferenced_symbol", "unreferenced_symbol", file, {"unreferenced_count": len(records)},
                       sorted(records, key=lambda item: item["node_id"]), "static_analyzer_relation")
            for file, records in sorted(found.items())]
