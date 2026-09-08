import ast
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from agent_view.models import RepositorySnapshot


@dataclass
class PythonSourceFile:
    file_path: Path
    module_name: str
    source_code: str
    tree: ast.AST


class PythonSourceAnalyzer:
    def __init__(self, project_path: Union[str, Path], snapshot: Optional[RepositorySnapshot] = None):
        self.snapshot = snapshot
        if snapshot is None:
            self.project_path = Path(project_path).resolve()
        else:
            supplied = Path(project_path)
            snapshot_root = Path(snapshot.root)
            if not supplied.is_absolute() or not snapshot_root.is_absolute():
                raise ValueError("snapshot root and project path must be absolute")
            if supplied != snapshot_root:
                raise ValueError("project path and snapshot root do not match")
            self.project_path = snapshot_root
        self.coverage = {"python_file_count": 0, "parsed_python_file_count": 0, "invalid_python_files": []}

    def analyze(self) -> List[PythonSourceFile]:
        if self.snapshot is not None:
            return self._analyze_snapshot()
        files = []
        for root, directories, filenames in os.walk(self.project_path):
            directories[:] = [
                directory for directory in directories
                if not directory.startswith(".")
                and directory not in {"venv", "env", "node_modules", "__pycache__", "build", "dist"}
            ]
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                file_path = Path(root) / filename
                try:
                    source_code = file_path.read_text(encoding="utf-8", errors="replace")
                    tree = ast.parse(source_code, filename=str(file_path))
                except (OSError, SyntaxError, UnicodeError):
                    continue
                files.append(PythonSourceFile(
                    file_path=file_path,
                    module_name=self._module_name(file_path),
                    source_code=source_code,
                    tree=tree,
                ))
        return files

    def _analyze_snapshot(self) -> List[PythonSourceFile]:
        self.coverage = {"python_file_count": 0, "parsed_python_file_count": 0, "invalid_python_files": []}
        files = []
        for relative, source_code in self.snapshot.contents:
            if not relative.endswith(".py"):
                continue
            self.coverage["python_file_count"] += 1
            file_path = self.project_path / relative
            try:
                tree = ast.parse(source_code, filename=str(file_path))
            except (SyntaxError, ValueError):
                self.coverage["invalid_python_files"].append(relative)
                continue
            files.append(PythonSourceFile(file_path, self._module_name(file_path), source_code, tree))
            self.coverage["parsed_python_file_count"] += 1
        return files

    def _module_name(self, file_path: Path) -> str:
        parts = list(file_path.relative_to(self.project_path).parts)
        if parts[-1] == "__init__.py":
            parts.pop()
        else:
            parts[-1] = parts[-1][:-3]
        return ".".join(parts) if parts else "__init__"
