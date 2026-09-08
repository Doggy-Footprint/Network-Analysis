from typing import Any


def render_report(payload: Any) -> str:
    from .generate import render_report as render

    return render(payload)

__all__ = ["render_report"]
