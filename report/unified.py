import html
import json
from pathlib import Path
from typing import Any, Mapping, Optional

from language_analyzers.core.flags import path_flags


def render_unified_report(architecture: Optional[Mapping[str, Any]], bottlenecks: Optional[Mapping[str, Any]], *, title: Optional[str] = None, framework_label: str = "") -> str:
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
