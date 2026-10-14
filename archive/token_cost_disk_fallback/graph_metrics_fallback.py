import ast
import json
from pathlib import Path
from typing import Any, Dict, Optional

from analysis.graph_metrics import _display_name
from language_analyzers.core.cost import estimate_tokens


class GraphAnalyzerDiskFallback:
    """Archived snapshot of the token-cost disk/ast fallback removed from GraphAnalyzer (spec f7564b09cf80bdd9)."""

    def __init__(self, config: Any):
        self.config = config
        self._source_cache: Dict[Path, str] = {}
        self._tree_cache: Dict[Path, Optional[ast.AST]] = {}

    def _node_token_cost(self, node: Any, project_path: Optional[str]) -> int:
        cost = getattr(node, "cost", None)
        token_estimate = getattr(cost, "token_estimate", None)
        if isinstance(token_estimate, int) and (token_estimate > 0 or token_estimate == 0 and (getattr(node, "metadata", {}) or {}).get("boundary")):
            return token_estimate
        metadata = getattr(node, "metadata", {}) or {}
        file_value = metadata.get("file_path")
        line_number = metadata.get("line_number")
        end_line_number = metadata.get("end_line_number")
        if file_value:
            file_path = Path(file_value)
            if not file_path.is_absolute() and project_path:
                file_path = Path(project_path) / file_path
            source = self._source_for_line(file_path, line_number, end_line_number)
            if source:
                return self._estimate_tokens(source)
        fallback = json.dumps(
            {
                "label": _display_name(node, ""),
                "title": getattr(node, "title", ""),
                "metadata": metadata,
            },
            ensure_ascii=False,
            default=str,
        )
        return self._estimate_tokens(fallback)

    def _source_for_line(self, path: Path, line_number: Any, end_line_number: Any = None) -> str:
        if path not in self._source_cache:
            try:
                self._source_cache[path] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                return ""
        source = self._source_cache[path]
        try:
            line = int(line_number)
        except (TypeError, ValueError):
            return source
        if end_line_number is not None:
            try:
                end_line = int(end_line_number)
            except (TypeError, ValueError):
                end_line = None
            if end_line is not None and end_line >= line:
                lines = source.splitlines()
                return "\n".join(lines[max(0, line - 1):end_line])
        tree = self._tree_cache.get(path)
        if path not in self._tree_cache:
            try:
                tree = ast.parse(source)
            except SyntaxError:
                tree = None
            self._tree_cache[path] = tree
        if tree is None:
            return source
        candidates = [
            item
            for item in ast.walk(tree)
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign, ast.Expr))
            and getattr(item, "lineno", 0) <= line <= getattr(item, "end_lineno", getattr(item, "lineno", 0))
        ]
        if not candidates:
            return source
        target = min(candidates, key=lambda item: item.end_lineno - item.lineno)
        return ast.get_source_segment(source, target) or source

    def _estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text, self.config.characters_per_token, self.config.digit_group_size)
