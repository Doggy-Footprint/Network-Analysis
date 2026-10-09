import html
import json
from pathlib import Path
from typing import Any, Mapping, Optional

from language_analyzers.core.flags import path_flags
from analysis.candidate_projection import AMBIGUITY_POLICY, candidate_projection
from report.shared.document import ReportInputError


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
    payload = json.dumps({"architecture": architecture, "bottlenecks": bottlenecks, "categories": categories, "framework_label": framework_label}, ensure_ascii=False, default=str).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    document = (package / "templates" / "dashboard.html").read_text(encoding="utf-8")
    replacements = {
        "{{TITLE}}": html.escape(title or (architecture or {}).get("project_name") or "의존성 병목 보고서"),
        "{{CSS}}": (package / "static" / "styles.css").read_text(encoding="utf-8"),
        "{{DATA}}": payload,
        "{{VENDOR}}": (package / "vendor" / "cytoscape-3.30.2.min.js").read_text(encoding="utf-8"),
        "{{LICENSE}}": (package / "vendor" / "cytoscape-3.30.2.LICENSE").read_text(encoding="utf-8"),
        "{{JS}}": (package / "static" / "app.js").read_text(encoding="utf-8"),
    }
    import re

    return re.sub(r"\{\{(?:TITLE|CSS|DATA|VENDOR|LICENSE|JS)\}\}", lambda match: replacements[match.group()], document)
