from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Union

if TYPE_CHECKING:
    from repository.models import RepositorySnapshot

from framework_analyzers.migration_tables import normalize_table_name, sql_table_refs
from language_analyzers.python import PythonSourceAnalyzer
from language_analyzers.python.source import PythonSourceFile

from .models import AlembicMigrationInfo, SQLAlchemyModelInfo, SQLAlchemyProjectArchitecture

MIGRATION_DIRECTORIES = ("/alembic/versions/", "/migrations/versions/")

# op method -> ((positional index, keyword name), ...) of the table arguments it touches.
# drop_index takes its table only through the optional table_name argument.
_OP_TABLE_ARGS = {
    "create_table": ((0, "table_name"),),
    "drop_table": ((0, "table_name"),),
    "rename_table": ((0, "old_table_name"), (1, "new_table_name")),
    "add_column": ((0, "table_name"),),
    "drop_column": ((0, "table_name"),),
    "alter_column": ((0, "table_name"),),
    "create_index": ((1, "table_name"),),
    "drop_index": ((1, "table_name"),),
    "create_foreign_key": ((1, "source_table"), (2, "referent_table")),
    "create_unique_constraint": ((1, "table_name"),),
    "drop_constraint": ((1, "table_name"),),
    "batch_alter_table": ((0, "table_name"),),
}


class SQLAlchemyAnalyzer:
    def __init__(self, project_path: Union[str, Path], snapshot: Optional[RepositorySnapshot] = None):
        self.snapshot = snapshot
        if snapshot is None:
            self.project_path = Path(project_path).resolve()
        else:
            supplied = Path(project_path)
            snapshot_root = Path(snapshot.root)
            if not supplied.is_absolute() or not snapshot_root.is_absolute() or supplied != snapshot_root:
                raise ValueError("project path and snapshot root must be absolute and match")
            self.project_path = snapshot_root

    def analyze(self) -> SQLAlchemyProjectArchitecture:
        arch = SQLAlchemyProjectArchitecture(
            project_name=self.project_path.name,
            project_path=str(self.project_path),
        )
        sources = sorted(
            PythonSourceAnalyzer(self.project_path, self.snapshot).analyze(),
            key=lambda source: self._relative(source),
        )
        for source in sources:
            relative = self._relative(source)
            self._extract_models(source, relative, arch)
            self._extract_migration(source, relative, arch)
        return arch

    def _relative(self, source: PythonSourceFile) -> str:
        return source.file_path.relative_to(self.project_path).as_posix()

    def _extract_models(self, source: PythonSourceFile, relative: str, arch: SQLAlchemyProjectArchitecture):
        def visit(body: List[ast.stmt], scope: List[str]):
            for node in body:
                if not isinstance(node, ast.ClassDef):
                    continue
                qualname = ".".join(scope + [node.name])
                table = self._model_table(node)
                if table is not None:
                    arch.models.append(SQLAlchemyModelInfo(
                        id=f"sqlalchemy_model_{source.module_name}_{qualname}",
                        name=node.name,
                        qualname=qualname,
                        module=source.module_name,
                        file_path=relative,
                        table_name=table,
                        line_number=node.lineno,
                        end_line_number=node.end_lineno or node.lineno,
                    ))
                visit(node.body, scope + [node.name])

        visit(source.tree.body, [])

    @staticmethod
    def _model_table(node: ast.ClassDef) -> Optional[str]:
        for statement in node.body:
            if isinstance(statement, ast.Assign):
                targets, value = statement.targets, statement.value
            elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
                targets, value = [statement.target], statement.value
            else:
                continue
            if any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in targets):
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    return normalize_table_name(value.value)
                return None
        is_table = any(
            keyword.arg == "table" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
            for keyword in node.keywords
        )
        return normalize_table_name(node.name) if is_table else None

    def _extract_migration(self, source: PythonSourceFile, relative: str, arch: SQLAlchemyProjectArchitecture):
        if not any(directory in f"/{relative}" for directory in MIGRATION_DIRECTORIES):
            return
        functions = {
            node.name: node for node in source.tree.body if isinstance(node, ast.FunctionDef)
        }
        if "upgrade" not in functions:
            return
        refs: List[Optional[str]] = []
        for name in ("upgrade", "downgrade"):
            if name in functions:
                refs.extend(self._function_refs(functions[name]))
        arch.migrations.append(AlembicMigrationInfo(
            id=f"alembic_migration_{relative}",
            module=source.module_name,
            file_path=relative,
            line_number=1,
            end_line_number=max(1, len(source.source_code.splitlines())),
            table_refs=refs,
        ))

    def _function_refs(self, function: ast.FunctionDef) -> List[Optional[str]]:
        calls = [
            node for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "op"
        ]
        calls.sort(key=lambda call: (call.lineno, call.col_offset))
        refs: List[Optional[str]] = []
        for call in calls:
            method = call.func.attr
            if method == "execute":
                argument = self._argument(call, 0, "sqltext")
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    refs.extend(sql_table_refs(argument.value))
                continue
            for position, keyword in _OP_TABLE_ARGS.get(method, ()):
                argument = self._argument(call, position, keyword)
                if argument is None:
                    continue
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    refs.append(normalize_table_name(argument.value))
                else:
                    refs.append(None)
        return refs

    @staticmethod
    def _argument(call: ast.Call, position: int, keyword: str) -> Optional[ast.expr]:
        if position < len(call.args) and not any(isinstance(a, ast.Starred) for a in call.args[:position + 1]):
            return call.args[position]
        for item in call.keywords:
            if item.arg == keyword:
                return item.value
        return None
