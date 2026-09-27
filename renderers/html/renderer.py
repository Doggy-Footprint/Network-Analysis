import html
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from language_analyzers.core.serialization import architecture_to_dict
from report.shared.labels import short_labels

FILE_LIKE_CATEGORIES = {"file", "module", "package"}

# vis.js line styling per edge confidence. Confidence is a semantic field the analyzers
# produce; turning it into a dash pattern belongs here so no analyzer carries presentation.
CONFIDENCE_STYLES: Dict[str, Dict[str, Any]] = {
    "static_certain": {"dashes": False, "color": "#64748B"},
    "framework_inferred": {"dashes": False, "color": "#818CF8"},
    "static_inferred": {"dashes": [8, 6], "color": "#38BDF8"},
    "dynamic_required": {"dashes": [2, 4], "color": "#F59E0B"},
}
DEFAULT_STYLE = CONFIDENCE_STYLES["static_certain"]


class HTMLRenderer:
    def __init__(self, title: Optional[str] = None, framework_label: str = ""):
        self.title = title
        self.framework_label = framework_label
        self.package_dir = Path(__file__).resolve().parent

    def render(self, arch: Any, output_path: str) -> Path:
        output = Path(output_path).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        asset_dir = output.parent / f"{output.stem}_assets"
        asset_dir.mkdir(parents=True, exist_ok=True)

        for asset_name in ("styles.css", "tailwind-config.js", "app.js"):
            shutil.copyfile(
                self.package_dir / "static" / asset_name,
                asset_dir / asset_name,
            )

        raw_data = architecture_to_dict(arch)
        short_label_by_id = self._short_label_map(raw_data["nodes"])
        raw_data["nodes"] = [self._vis_node(node, short_label_by_id) for node in raw_data["nodes"]]
        raw_data["edges"] = [self._vis_edge(edge) for edge in raw_data["edges"]]
        raw_data["confidence_styles"] = CONFIDENCE_STYLES

        document = (self.package_dir / "templates" / "dashboard.html").read_text(encoding="utf-8")
        replacements = {
            "{{DOC_TITLE}}": html.escape(self.title or f"Architecture - {arch.project_name}"),
            "{{PROJECT_PATH}}": html.escape(arch.project_path),
            "{{FRAMEWORK_LABEL}}": html.escape(self.framework_label or "Analyzer"),
            "{{ASSET_DIR}}": asset_dir.name,
            "{{ARCH_DATA}}": json.dumps(raw_data, ensure_ascii=False, default=str).replace("<", "\\u003c"),
        }
        for placeholder, value in replacements.items():
            document = document.replace(placeholder, value)

        output.write_text(document, encoding="utf-8")
        return output

    @staticmethod
    def _short_label_map(nodes: List[Dict[str, Any]]) -> Dict[str, str]:
        eligible: Dict[str, str] = {}
        for node in nodes:
            if node.get("display_label"):
                continue
            if node.get("category") not in FILE_LIKE_CATEGORIES:
                continue
            span = node.get("span") or {}
            path = span.get("file_path") or node.get("label", "")
            if "/" not in path:
                continue
            eligible[node["id"]] = path
        if not eligible:
            return {}
        labels = short_labels(eligible.values())
        return {node_id: labels[path] for node_id, path in eligible.items()}

    @staticmethod
    def _vis_node(node: Dict[str, Any], short_label_by_id: Dict[str, str]) -> Dict[str, Any]:
        vis = dict(node)
        display_label = node.get("display_label")
        if display_label:
            vis["label"] = display_label
            return vis
        vis["label"] = short_label_by_id.get(node["id"]) or node.get("label", "")
        span = node.get("span") or {}
        file_path = span.get("file_path")
        if file_path:
            title_parts = [node["title"]] if node.get("title") else []
            title_parts.append(html.escape(file_path))
            vis["title"] = "<br>".join(title_parts)
        return vis

    @staticmethod
    def _vis_edge(edge: Dict[str, Any]) -> Dict[str, Any]:
        confidence = edge.get("confidence") or "static_certain"
        style = CONFIDENCE_STYLES.get(confidence, DEFAULT_STYLE)
        relation = edge.get("relation", "")
        evidence = edge.get("evidence")
        tooltip_lines = [f"<b>{relation}</b>" if relation else "<b>edge</b>"]
        if edge.get("label"):
            tooltip_lines.append(edge["label"])
        tooltip_lines.append(f"confidence: {confidence}")
        tooltip_lines.append(f"resolution: {edge.get('resolution', 'exact')}")
        if evidence:
            tooltip_lines.append(f"evidence: {evidence['file_path']}:{evidence['start_line']}")
        if edge.get("candidates"):
            tooltip_lines.append(f"other candidates: {len(edge['candidates'])}")
        if edge.get("weight", 1.0) > 1:
            tooltip_lines.append(f"occurrences: {int(edge['weight'])}")

        colour = edge.get("color") or style["color"]
        vis = dict(edge)
        vis["from"] = edge["from_id"]
        vis["to"] = edge["to_id"]
        vis["dashes"] = edge.get("dashes") or style["dashes"]
        vis["color"] = {"color": colour, "highlight": "#38BDF8", "hover": "#38BDF8"}
        vis["title"] = edge.get("title") or "<br>".join(tooltip_lines)
        return vis
