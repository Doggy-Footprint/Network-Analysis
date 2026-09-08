import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from language_analyzers.core import flags as flag_names
from language_analyzers.core.graph_models import NodeKind

from .source import PythonSourceFile


def module_id(module: str) -> str:
    return f"py:{module}"


def symbol_id(module: str, qualname: str) -> str:
    return f"py:{module}#{qualname}"


def resolve_relative_module(package: str, module: Optional[str], level: int) -> str:
    """Resolve `from ..pkg import x`. `package` is the importer's `__package__`, not its
    `__name__`: for `pkg/__init__.py` both are "pkg", so a one-level import must not climb."""
    if not level:
        return module or ""
    parts = (package or "").split(".") if package else []
    if level > 1:
        parts = parts[: max(0, len(parts) - (level - 1))]
    return ".".join(parts + [module]) if module else ".".join(parts)


@dataclass
class ImportBinding:
    local_name: str
    module: str
    symbol: Optional[str]
    line: int
    level: int = 0


@dataclass
class SymbolEntry:
    id: str
    name: str
    qualname: str
    kind: str
    module: str
    file_path: str
    start_line: int
    end_line: int
    parent_id: Optional[str] = None
    signature: Optional[str] = None
    docstring: Optional[str] = None
    exported: bool = True
    bases: List[Tuple[str, int]] = field(default_factory=list)
    decorators: List[Tuple[str, int]] = field(default_factory=list)
    annotations: List[Tuple[str, int]] = field(default_factory=list)
    node: Optional[ast.AST] = None


@dataclass
class ModuleEntry:
    id: str
    module: str
    file_path: str
    source: str
    tree: ast.AST
    end_line: int
    docstring: Optional[str] = None
    package: Optional[str] = None
    is_package_init: bool = False
    bindings: Dict[str, ImportBinding] = field(default_factory=dict)
    defines: Dict[str, str] = field(default_factory=dict)
    exported_names: Optional[List[str]] = None
    imported_modules: List[Tuple[str, int]] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)


@dataclass
class SymbolTable:
    modules: Dict[str, ModuleEntry] = field(default_factory=dict)
    by_id: Dict[str, SymbolEntry] = field(default_factory=dict)
    by_simple_name: Dict[str, List[str]] = field(default_factory=dict)
    packages: Dict[str, List[str]] = field(default_factory=dict)

    def resolve_in_module(self, module: str, name: str) -> Optional[str]:
        entry = self.modules.get(module)
        if entry is None:
            return None
        if name in entry.defines:
            return entry.defines[name]
        binding = entry.bindings.get(name)
        if binding is None:
            return None
        return self.resolve_binding(binding)

    def resolve_binding(self, binding: ImportBinding) -> Optional[str]:
        if binding.symbol is None:
            return module_id(binding.module) if binding.module in self.modules else None
        target = self.modules.get(binding.module)
        if target is None:
            return None
        if binding.symbol in target.defines:
            return target.defines[binding.symbol]
        chained = target.bindings.get(binding.symbol)
        if chained is not None and chained.module != binding.module:
            return self.resolve_binding(chained)
        submodule = f"{binding.module}.{binding.symbol}"
        return module_id(submodule) if submodule in self.modules else None

    def collisions(self, name: str) -> int:
        return len({self.by_id[item].module for item in self.by_simple_name.get(name, [])})


def _name_of(node: Optional[ast.AST]) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_of(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    if isinstance(node, ast.Subscript):
        return _name_of(node.value)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def annotation_names(node: Optional[ast.AST]) -> List[str]:
    if node is None:
        return []
    names: List[str] = []
    for item in ast.walk(node):
        if isinstance(item, ast.Name):
            names.append(item.id)
        elif isinstance(item, ast.Attribute):
            names.append(item.attr)
        elif isinstance(item, ast.Constant) and isinstance(item.value, str):
            names.append(item.value)
    return names


def signature_of(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
        try:
            args = ast.unparse(node.args)
        except Exception:
            args = ""
        returns = ""
        if node.returns is not None:
            try:
                returns = f" -> {ast.unparse(node.returns)}"
            except Exception:
                returns = ""
        return f"{prefix}{node.name}({args}){returns}"
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(_name_of(base) for base in node.bases if _name_of(base))
        return f"class {node.name}({bases})" if bases else f"class {node.name}"
    return ""


_REEXPORT_ONLY = (ast.Import, ast.ImportFrom, ast.Pass)


def _is_reexport_module(tree: ast.AST, is_package_init: bool) -> bool:
    if not is_package_init:
        return False
    saw_import = False
    for node in tree.body:
        if isinstance(node, _REEXPORT_ONLY):
            saw_import = saw_import or isinstance(node, (ast.Import, ast.ImportFrom))
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if all(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                continue
        return False
    return saw_import


def _dunder_all(tree: ast.AST) -> Optional[List[str]]:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            continue
        if isinstance(node.value, (ast.List, ast.Tuple)):
            return [
                element.value for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
    return None


class _ModuleCollector:
    def __init__(self, table: SymbolTable, entry: ModuleEntry):
        self.table = table
        self.entry = entry

    def run(self):
        self._visit_body(self.entry.tree.body, scope=[], parent_id=None, in_class=False)

    def _register(self, symbol: SymbolEntry, local_name: Optional[str]):
        self.table.by_id[symbol.id] = symbol
        self.table.by_simple_name.setdefault(symbol.name, []).append(symbol.id)
        if local_name is not None:
            self.entry.defines[local_name] = symbol.id

    def _qualname(self, scope: Sequence[str], name: str) -> str:
        return ".".join(list(scope) + [name])

    def _exported(self, name: str) -> bool:
        if self.entry.exported_names is not None:
            return name in self.entry.exported_names
        return not name.startswith("_")

    def _visit_body(self, body, scope: List[str], parent_id: Optional[str], in_class: bool):
        top_level = not scope
        for node in body:
            if isinstance(node, ast.Import):
                self._import(node)
            elif isinstance(node, ast.ImportFrom):
                self._import_from(node)
            elif isinstance(node, ast.ClassDef):
                self._class(node, scope, parent_id, top_level)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._function(node, scope, parent_id, in_class, top_level)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                self._assign(node, scope, parent_id, in_class, top_level)
            elif isinstance(node, (ast.If, ast.Try)):
                for attribute in ("body", "orelse", "finalbody", "handlers"):
                    branch = getattr(node, attribute, None) or []
                    if attribute == "handlers":
                        for handler in branch:
                            self._visit_body(handler.body, scope, parent_id, in_class)
                    else:
                        self._visit_body(branch, scope, parent_id, in_class)

    def _import(self, node: ast.Import):
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            self.entry.bindings[local] = ImportBinding(local, alias.name, None, node.lineno)
            self.entry.imported_modules.append((alias.name, node.lineno))

    def _import_from(self, node: ast.ImportFrom):
        module = resolve_relative_module(self.entry.package or "", node.module, node.level)
        if module:
            self.entry.imported_modules.append((module, node.lineno))
        for alias in node.names:
            if alias.name == "*":
                continue
            local = alias.asname or alias.name
            self.entry.bindings[local] = ImportBinding(local, module, alias.name, node.lineno, node.level)

    def _class(self, node: ast.ClassDef, scope: List[str], parent_id: Optional[str], top_level: bool):
        qualname = self._qualname(scope, node.name)
        symbol = SymbolEntry(
            id=symbol_id(self.entry.module, qualname),
            name=node.name,
            qualname=qualname,
            kind=NodeKind.CLASS,
            module=self.entry.module,
            file_path=self.entry.file_path,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
            parent_id=parent_id or self.entry.id,
            signature=signature_of(node),
            docstring=ast.get_docstring(node),
            exported=self._exported(node.name) if top_level else False,
            bases=[(_name_of(base), base.lineno) for base in node.bases if _name_of(base)],
            decorators=[(_name_of(d), d.lineno) for d in node.decorator_list if _name_of(d)],
            node=node,
        )
        self._register(symbol, node.name if top_level else None)
        self._visit_body(node.body, scope + [node.name], symbol.id, in_class=True)

    def _function(self, node, scope: List[str], parent_id: Optional[str], in_class: bool, top_level: bool):
        qualname = self._qualname(scope, node.name)
        annotations: List[Tuple[str, int]] = []
        arguments = node.args
        for arg in list(arguments.posonlyargs) + list(arguments.args) + list(arguments.kwonlyargs):
            for name in annotation_names(arg.annotation):
                annotations.append((name, arg.lineno))
        for extra in (arguments.vararg, arguments.kwarg):
            if extra is not None:
                for name in annotation_names(extra.annotation):
                    annotations.append((name, extra.lineno))
        for name in annotation_names(node.returns):
            annotations.append((name, node.returns.lineno))

        symbol = SymbolEntry(
            id=symbol_id(self.entry.module, qualname),
            name=node.name,
            qualname=qualname,
            kind=NodeKind.METHOD if in_class else NodeKind.FUNCTION,
            module=self.entry.module,
            file_path=self.entry.file_path,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
            parent_id=parent_id or self.entry.id,
            signature=signature_of(node),
            docstring=ast.get_docstring(node),
            exported=self._exported(node.name) if top_level else False,
            decorators=[(_name_of(d), d.lineno) for d in node.decorator_list if _name_of(d)],
            annotations=annotations,
            node=node,
        )
        self._register(symbol, node.name if top_level else None)
        self._visit_body(node.body, scope + [node.name, "<locals>"], symbol.id, in_class=False)

    def _assign(self, node, scope: List[str], parent_id: Optional[str], in_class: bool, top_level: bool):
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
            annotations = [(name, node.annotation.lineno) for name in annotation_names(node.annotation)]
        else:
            targets = node.targets
            annotations = []
        if not (top_level or in_class):
            return
        for target in targets:
            if not isinstance(target, ast.Name) or target.id == "__all__":
                continue
            qualname = self._qualname(scope, target.id)
            kind = NodeKind.FIELD if in_class else NodeKind.CONSTANT
            symbol = SymbolEntry(
                id=symbol_id(self.entry.module, qualname),
                name=target.id,
                qualname=qualname,
                kind=kind,
                module=self.entry.module,
                file_path=self.entry.file_path,
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                parent_id=parent_id or self.entry.id,
                exported=self._exported(target.id) if top_level else False,
                annotations=annotations,
                node=node,
            )
            self._register(symbol, target.id if top_level else None)


def build_symbol_table(sources: Sequence[PythonSourceFile], project_path: Path, *, resolve_root: bool = True) -> SymbolTable:
    project_path = Path(project_path)
    if resolve_root:
        project_path = project_path.resolve()
    elif not project_path.is_absolute():
        raise ValueError("project path must be absolute when resolve_root is false")
    table = SymbolTable()
    for source in sources:
        relative = source.file_path.relative_to(project_path).as_posix()
        is_init = source.file_path.name == "__init__.py"
        package = source.module_name if is_init else (
            source.module_name.rsplit(".", 1)[0] if "." in source.module_name else None
        )
        entry = ModuleEntry(
            id=module_id(source.module_name),
            module=source.module_name,
            file_path=relative,
            source=source.source_code,
            tree=source.tree,
            end_line=max(1, source.source_code.count("\n") + 1),
            docstring=ast.get_docstring(source.tree) if isinstance(source.tree, ast.Module) else None,
            package=package,
            is_package_init=is_init,
            exported_names=_dunder_all(source.tree),
            flags=flag_names.path_flags(relative),
        )
        if _is_reexport_module(source.tree, is_init):
            entry.flags.append(flag_names.REEXPORT)
        table.modules[source.module_name] = entry
        if package:
            table.packages.setdefault(package, []).append(source.module_name)

    for entry in table.modules.values():
        _ModuleCollector(table, entry).run()
    return table
