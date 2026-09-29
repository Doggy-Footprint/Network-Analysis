import json
import sys
from dataclasses import asdict
from typing import Any, Dict

from .models import AgentViewGraph

SIZE_WARNING_BYTES = 10 * 1024 * 1024


def graph_to_dict(graph: AgentViewGraph) -> Dict[str, Any]:
    result = asdict(graph)
    result.pop("project_path", None)
    if result.get("scale_warning") is None:
        result.pop("scale_warning", None)
    return result


def graph_to_json(graph: AgentViewGraph) -> str:
    payload = graph_to_dict(graph)
    text = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ) + "\n"
    size = len(text.encode("utf-8"))
    if size > SIZE_WARNING_BYTES:
        payload["scale_warning"] = {
            "artifact": "json",
            "bytes": size,
            "threshold_bytes": SIZE_WARNING_BYTES,
        }
        text = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ) + "\n"
        print(
            f"warning: agent-view JSON is {size} bytes "
            f"(threshold {SIZE_WARNING_BYTES})",
            file=sys.stderr,
        )
    return text
