import html
import json
from pathlib import Path
from typing import Any, Mapping, Optional

from language_analyzers.core.flags import path_flags
from analysis.candidate_projection import AMBIGUITY_POLICY, candidate_projection
from report.shared.document import ReportInputError


FRAMEWORK_LAYER_PRIORITY = {
    "android": ("viewmodel", "activity_fragment", "room_database", "room_dao", "room_entity", "room_migration", "dagger_component", "di_module", "di_binding", "retrofit_api", "composable"),
    "fastapi": ("app", "router", "endpoint", "dependency", "middleware", "schema"),
    "sqlalchemy": ("alembic_migration", "sqlalchemy_model"),
    "nestjs": ("application", "module", "controller", "endpoint", "provider"),
}
SOURCE_ROOTS = ("src/main/java", "src/main/kotlin", "src/test/java", "src/test/kotlin", "src/androidTest/java", "src/androidTest/kotlin", "src")
# Language analyzers emit generic kinds such as "module" that collide with framework role names.
LANGUAGE_PROVENANCE = {"python-core", "typescript-core", "kotlin-core", "file-aggregation"}


def _strip_source_root(parts: list) -> tuple:
    for root in SOURCE_ROOTS:
        root_parts = root.split("/")
        for start in range(len(parts) - len(root_parts) + 1):
            if parts[start:start + len(root_parts)] == root_parts:
                return parts[start + len(root_parts):], True
    return parts, False


def file_layers(architecture: Mapping[str, Any]) -> dict:
    architecture = architecture or {}
    details = architecture.get("details") or {}
    node_files = details.get("node_files") or {}
    best = {}
    for node in details.get("nodes") or []:
        file_id = node_files.get(node.get("id"))
        kind = node.get("kind") or node.get("category")
        if not file_id or node.get("provenance") in LANGUAGE_PROVENANCE:
            continue
        for ranks in FRAMEWORK_LAYER_PRIORITY.values():
            if kind in ranks and (file_id not in best or ranks.index(kind) < best[file_id][0]):
                best[file_id] = (ranks.index(kind), kind)
    files = {}
    for node in architecture.get("nodes") or []:
        node_id = node.get("id")
        if (node.get("kind") or node.get("category")) != "file" or not isinstance(node_id, str) or (node.get("metadata") or {}).get("boundary"):
            continue
        path = ((node.get("span") or {}).get("file_path") or (node.get("metadata") or {}).get("file_path") or node_id.removeprefix("file:")).replace("\\", "/")
        parts = path.split("/")
        rest, rooted = _strip_source_root(parts)
        files[node_id] = (path, rest[:-1] if rooted else parts[:-1][:1], rooted)
    production = [dirs for path, dirs, rooted in files.values() if rooted and not path_flags(path)]
    common = list(production[0]) if production else []
    for dirs in production[1:]:
        size = 0
        while size < min(len(common), len(dirs)) and common[size] == dirs[size]:
            size += 1
        del common[size:]
    layers = {}
    for node_id, (_, dirs, rooted) in files.items():
        if node_id in best:
            layers[node_id] = {"layer": best[node_id][1], "source": "framework"}
            continue
        rest = dirs[len(common):] if rooted and dirs[:len(common)] == common else dirs
        layers[node_id] = {"layer": rest[0] if rest else "(root)", "source": "package"}
    return layers


def render_unified_report(architecture: Optional[Mapping[str, Any]], bottlenecks: Optional[Mapping[str, Any]] = None, *, title: Optional[str] = None, framework_label: str = "") -> str:
    for component, analysis in ((architecture, (architecture or {}).get("stats", {}).get("analysis", {})),
                                (bottlenecks, (bottlenecks or {}).get("dependency_network", {}))):
        if component is not None and analysis.get("ambiguity_policy") != AMBIGUITY_POLICY:
            raise ReportInputError("missing or unsupported ambiguity_policy")
    if bottlenecks is not None:
        groups = bottlenecks.get("dependency_network", {}).get("candidate_groups", {})
        if not isinstance(groups, Mapping):
            raise ReportInputError("candidate_groups must be a mapping")
        for group_id, group in groups.items():
            if (not isinstance(group_id, str) or not group_id or not isinstance(group, Mapping)
                    or not isinstance(group.get("to_id"), str) or not group["to_id"]
                    or not isinstance(group.get("candidates"), list)
                    or any(not isinstance(item, str) or not item for item in group["candidates"])):
                raise ReportInputError("candidate_groups contains an invalid group")
        for candidate in bottlenecks.get("candidates", []):
            evidence = candidate.get("evidence")
            for record in evidence if isinstance(evidence, list) else [evidence]:
                if not isinstance(record, Mapping) or "candidate_group_id" not in record:
                    continue
                group_id = record["candidate_group_id"]
                if (not isinstance(group_id, str) or not group_id or group_id not in groups
                        or record.get("to_id") != groups[group_id]["to_id"]):
                    raise ReportInputError("candidate_group_id is invalid or does not match its representative")
    if architecture is not None:
        from bottlenecks.core import BottleneckInputError
        try:
            for graph in (architecture, architecture.get("details", {})):
                node_ids = {node["id"] for node in graph.get("nodes", [])}
                for edge in graph.get("edges", []):
                    candidate_projection(edge, node_ids)
        except (TypeError, KeyError, ValueError) as error:
            raise BottleneckInputError("architecture edge reference or candidate_share is invalid") from error
    package = Path(__file__).resolve().parents[1] / "renderers" / "html"
    categories = {}
    file_mode = (architecture or {}).get("granularity") == "file"
    for node in (architecture or {}).get("nodes", []):
        span = node.get("span")
        file_path = span["file_path"] if span else None
        if file_mode and not file_path:
            file_path = (node.get("metadata") or {}).get("file_path")
        flags = path_flags(file_path) if file_path else []
        categories[node["id"]] = next((kind for kind in ("vendored", "generated", "test") if kind in flags), "production" if file_path else "unknown")
    layers = file_layers(architecture) if architecture is not None else {}
    embedded = {key: value for key, value in architecture.items() if key != "details"} if architecture is not None else None
    payload = json.dumps({"architecture": embedded, "bottlenecks": bottlenecks, "categories": categories, "layers": layers, "framework_label": framework_label}, ensure_ascii=False, default=str).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    document = (package / "templates" / "dashboard.html").read_text(encoding="utf-8")
    replacements = {
        "{{TITLE}}": html.escape(title or (architecture or {}).get("project_name") or "의존성 병목 보고서"),
        "{{CSS}}": (package / "static" / "styles.css").read_text(encoding="utf-8"),
        "{{DATA}}": payload,
        "{{JS}}": (package / "static" / "app.js").read_text(encoding="utf-8"),
    }
    import re

    return re.sub(r"\{\{(?:TITLE|CSS|DATA|JS)\}\}", lambda match: replacements[match.group()], document)
