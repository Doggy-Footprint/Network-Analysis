from pathlib import Path
from typing import Any, Mapping, Optional

from language_analyzers.core.serialization import architecture_to_dict
from report.unified import render_unified_report


class HTMLRenderer:
    def __init__(self, title: Optional[str] = None, framework_label: str = ""):
        self.title = title
        self.framework_label = framework_label

    def render(self, arch: Any, output_path: str, *, bottleneck_report: Optional[Mapping[str, Any]] = None) -> Path:
        output = Path(output_path).resolve()
        document = render_unified_report(architecture_to_dict(arch), bottleneck_report, title=self.title, framework_label=self.framework_label)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document, encoding="utf-8")
        return output
