import ast
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from language_analyzers.core import flags as flag_names
from language_analyzers.core.cost import cost_for_span, cost_for_text
from language_analyzers.core.enrichment import enrich_repository
from language_analyzers.core.graph_models import (
    Confidence,
    GraphEdge,
    GraphNode,
    NodeKind,
    RelationKind,
    Resolution,
    SourceSpan,
)
from language_analyzers.core.report_schema import ColumnSpec, ReportCollection

from .source import PythonSourceAnalyzer, PythonSourceFile
from agent_view.models import RepositorySnapshot
from .symbols import (
    ModuleEntry,
    SymbolEntry,
    SymbolTable,
    build_symbol_table,
    module_id,
)

PROVENANCE = "python-core"

_DYNAMIC_IMPORT_NAMES = {"import_module", "__import__", "importlib.import_module"}
_DYNAMIC_ATTR_NAMES = {"getattr", "setattr", "hasattr", "delattr"}
_DYNAMIC_EVAL_NAMES = {"eval", "exec", "globals", "locals", "vars", "compile"}


@dataclass
class PythonProjectArchitecture:
    project_name: str
    project_path: str
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    report_collections: List[ReportCollection] = field(default_factory=list)
    snapshot_digest: Optional[str] = None
    snapshot_coverage: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _Reference:
    name: str
    receiver: Optional[str]
    line: int
    is_call: bool


def _walk_excluding_defs(nodes):
    stack = [node for node in nodes]
    while stack:
        current = stack.pop()
        yield current
        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            stack.append(child)


def _receiver_and_name(func: ast.AST) -> Tuple[Optional[str], str]:
    if isinstance(func, ast.Name):
        return None, func.id
    if isinstance(func, ast.Attribute):
        value = func.value
        if isinstance(value, ast.Name):
            return value.id, func.attr
        if isinstance(value, ast.Attribute):
            return value.attr, func.attr
        return None, func.attr
    return None, ""


class _BodyScanner:
    """Collects references and dynamic markers from one symbol's own statements,
    stopping at nested definitions because those are separate symbols."""

    def __init__(self, statements: Sequence[ast.AST], parameters: Sequence[str] = ()):
        self.locals: Set[str] = set(parameters)
        self.references: List[_Reference] = []
        self.stores: List[Tuple[str, int]] = []
        self.dynamic: Set[str] = set()
        self.dynamic_imports: List[Tuple[str, int]] = []
        self._scan([
            statement for statement in statements
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ])

    def _scan(self, statements: Sequence[ast.AST]):
        # _walk_excluding_defs is stack-based, so restore source order to keep the first
        # occurrence of a repeated reference as the recorded evidence.
        nodes = sorted(
            _walk_excluding_defs(statements),
            key=lambda item: (getattr(item, "lineno", 0), getattr(item, "col_offset", 0)),
        )
        for node in nodes:
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                self.locals.add(node.id)
                self.stores.append((node.id, node.lineno))
            elif isinstance(node, (ast.comprehension,)):
                for item in ast.walk(node.target):
                    if isinstance(item, ast.Name):
                        self.locals.add(item.id)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                self.locals.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    self.locals.add(alias.asname or alias.name.split(".")[0])

        for node in nodes:
            if isinstance(node, ast.Call):
                receiver, name = _receiver_and_name(node.func)
                if name:
                    self.references.append(_Reference(name, receiver, node.lineno, True))
                self._mark_dynamic(node, receiver, name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                self.references.append(_Reference(node.id, None, node.lineno, False))

    def _mark_dynamic(self, node: ast.Call, receiver: Optional[str], name: str):
        qualified = f"{receiver}.{name}" if receiver else name
        if name in _DYNAMIC_IMPORT_NAMES or qualified in _DYNAMIC_IMPORT_NAMES:
            self.dynamic.add(flag_names.DYNAMIC_IMPORT)
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                self.dynamic_imports.append((node.args[0].value, node.lineno))
        elif name in _DYNAMIC_ATTR_NAMES and receiver is None:
            constant_attribute = (
                len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            )
            if not constant_attribute:
                self.dynamic.add(flag_names.DYNAMIC_ATTR)
        elif name in _DYNAMIC_EVAL_NAMES and receiver is None:
            self.dynamic.add(flag_names.DYNAMIC_EVAL)


class PythonGraphAnalyzer:
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

    def analyze(self) -> PythonProjectArchitecture:
        source_analyzer = PythonSourceAnalyzer(self.project_path, self.snapshot)
        sources = source_analyzer.analyze()
        nodes, edges = self.build(sources)
        architecture = PythonProjectArchitecture(
            project_name=self.project_path.name,
            project_path=str(self.project_path),
            nodes=nodes,
            edges=edges,
            snapshot_digest=self.snapshot.digest if self.snapshot is not None else None,
            snapshot_coverage=dict(source_analyzer.coverage) if self.snapshot is not None else {},
        )
        if self.snapshot is None:
            enrich_repository(architecture)
        else:
            contents = self.snapshot.content_map()
            enrich_repository(
                architecture,
                file_inventory=tuple(contents),
                file_reader=lambda path: contents[path.relative_to(self.project_path).as_posix()],
            )
        nodes, edges = architecture.nodes, architecture.edges
        architecture.stats = {
            "total_modules": sum(node.kind == NodeKind.MODULE for node in nodes),
            "total_symbols": sum(node.kind not in (NodeKind.MODULE, NodeKind.PACKAGE) for node in nodes),
            "nodes_by_kind": dict(Counter(node.kind for node in nodes)),
            "edges_by_relation": dict(Counter(edge.relation for edge in edges)),
            "edges_by_confidence": dict(Counter(str(edge.confidence) for edge in edges)),
        }
        architecture.report_collections = [self._symbol_collection(nodes)]
        return architecture

    def build(self, sources: Sequence[PythonSourceFile]) -> Tuple[List[GraphNode], List[GraphEdge]]:
        table = build_symbol_table(sources, self.project_path, resolve_root=self.snapshot is None)
        self._table = table
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: Dict[Tuple[str, str, str], GraphEdge] = {}

        self._build_package_nodes(table)
        for entry in table.modules.values():
            self._build_module_node(entry)
        for symbol in table.by_id.values():
            self._build_symbol_node(symbol, table)

        for entry in table.modules.values():
            self._module_edges(entry, table)
        for symbol in table.by_id.values():
            self._symbol_edges(symbol, table)
        self._scan_bodies(table)

        return list(self._nodes.values()), list(self._edges.values())

    # ---- nodes ----

    def _build_package_nodes(self, table: SymbolTable):
        for package in table.packages:
            if package in table.modules:
                continue
            self._add_node(GraphNode(
                id=module_id(package),
                label=package,
                group=NodeKind.PACKAGE,
                category=NodeKind.PACKAGE,
                kind=NodeKind.PACKAGE,
                language="python",
                symbol_path=package,
                provenance=PROVENANCE,
                cost=cost_for_text(package),
            ))

    def _build_module_node(self, entry: ModuleEntry):
        span = SourceSpan(entry.file_path, 1, entry.end_line)
        self._add_node(GraphNode(
            id=entry.id,
            label=entry.file_path,
            group=NodeKind.MODULE,
            category=NodeKind.MODULE,
            kind=NodeKind.MODULE,
            language="python",
            span=span,
            cost=cost_for_span(entry.source, span),
            docstring=(entry.docstring or "").strip().splitlines()[0] if entry.docstring else None,
            symbol_path=entry.module,
            flags=list(entry.flags),
            provenance=PROVENANCE,
            metadata={"module": entry.module, "is_package_init": entry.is_package_init},
        ))

    def _build_symbol_node(self, symbol: SymbolEntry, table: SymbolTable):
        entry = table.modules[symbol.module]
        span = SourceSpan(symbol.file_path, symbol.start_line, symbol.end_line)
        flags = list(entry.flags)
        collisions = table.collisions(symbol.name)
        metadata: Dict[str, Any] = {"module": symbol.module, "name": symbol.name}
        if collisions > 1:
            flags.append(flag_names.AMBIGUOUS_NAME)
            metadata["name_collision_count"] = collisions
        self._add_node(GraphNode(
            id=symbol.id,
            label=symbol.name,
            group=symbol.kind,
            category=symbol.kind,
            kind=symbol.kind,
            language="python",
            span=span,
            cost=cost_for_span(entry.source, span),
            signature=symbol.signature,
            docstring=(symbol.docstring or "").strip().splitlines()[0] if symbol.docstring else None,
            exported=symbol.exported,
            symbol_path=f"{symbol.module}.{symbol.qualname}",
            flags=flags,
            provenance=PROVENANCE,
            metadata=metadata,
        ))

    def _add_node(self, node: GraphNode):
        self._nodes.setdefault(node.id, node)

    def _add_edge(
        self,
        from_id: str,
        to_id: str,
        relation: str,
        confidence: str = Confidence.STATIC_CERTAIN,
        resolution: str = Resolution.EXACT,
        evidence: Optional[SourceSpan] = None,
        candidates: Optional[List[str]] = None,
    ):
        if from_id == to_id or from_id not in self._nodes or to_id not in self._nodes:
            return
        key = (from_id, to_id, relation)
        existing = self._edges.get(key)
        if existing is not None:
            existing.weight += 1.0
            return
        if evidence is None:
            evidence_node = self._nodes[from_id] if self._nodes[from_id].span else self._nodes[to_id]
            if evidence_node.span is not None:
                evidence = SourceSpan(
                    evidence_node.span.file_path,
                    evidence_node.span.start_line,
                    evidence_node.span.start_line,
                )
        self._edges[key] = GraphEdge(
            from_id=from_id,
            to_id=to_id,
            relation=relation,
            confidence=confidence,
            resolution=resolution,
            evidence=evidence,
            candidates=candidates or [],
        )

    # ---- edges ----

    def _module_edges(self, entry: ModuleEntry, table: SymbolTable):
        if entry.package and entry.package != entry.module:
            self._add_edge(module_id(entry.package), entry.id, RelationKind.CONTAINS)
        for name, target_id in entry.defines.items():
            self._add_edge(entry.id, target_id, RelationKind.CONTAINS)
        for module_name, line in entry.imported_modules:
            target = module_id(module_name)
            if target in self._nodes:
                self._add_edge(
                    entry.id, target, RelationKind.IMPORTS,
                    evidence=SourceSpan(entry.file_path, line, line),
                )
        reexport = flag_names.REEXPORT in entry.flags
        for binding in entry.bindings.values():
            if binding.symbol is None:
                continue
            resolved = table.resolve_binding(binding)
            if not resolved or resolved not in self._nodes:
                continue
            relation = RelationKind.RE_EXPORTS if reexport else RelationKind.IMPORTS_SYMBOL
            self._add_edge(
                entry.id, resolved, relation,
                evidence=SourceSpan(entry.file_path, binding.line, binding.line),
            )

    def _symbol_edges(self, symbol: SymbolEntry, table: SymbolTable):
        if symbol.parent_id:
            self._add_edge(symbol.parent_id, symbol.id, RelationKind.CONTAINS)
        evidence_file = symbol.file_path
        for base_name, line in symbol.bases:
            target, resolution, confidence, candidates = self._resolve_name(
                base_name.rsplit(".", 1)[-1], symbol.module, table
            )
            if target:
                self._add_edge(
                    symbol.id, target, RelationKind.INHERITS, confidence, resolution,
                    SourceSpan(evidence_file, line, line), candidates,
                )
        for decorator_name, line in symbol.decorators:
            target, resolution, confidence, candidates = self._resolve_name(
                decorator_name.rsplit(".", 1)[-1], symbol.module, table
            )
            if target:
                self._add_edge(
                    target, symbol.id, RelationKind.DECORATES, confidence, resolution,
                    SourceSpan(evidence_file, line, line), candidates,
                )
        for annotation_name, line in symbol.annotations:
            target, resolution, confidence, candidates = self._resolve_name(
                annotation_name, symbol.module, table
            )
            if target and table.by_id.get(target) and table.by_id[target].kind == NodeKind.CLASS:
                self._add_edge(
                    symbol.id, target, RelationKind.TYPE_USES, confidence, resolution,
                    SourceSpan(evidence_file, line, line), candidates,
                )

    def _scan_bodies(self, table: SymbolTable):
        for symbol in list(table.by_id.values()):
            node = symbol.node
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                arguments = node.args
                parameters = [
                    arg.arg for arg in
                    list(arguments.posonlyargs) + list(arguments.args) + list(arguments.kwonlyargs)
                ]
                for extra in (arguments.vararg, arguments.kwarg):
                    if extra is not None:
                        parameters.append(extra.arg)
                scanner = _BodyScanner(node.body, parameters)
            elif isinstance(node, ast.ClassDef):
                scanner = _BodyScanner(node.body)
            else:
                continue
            self._apply_scan(symbol.id, symbol, scanner, table)

        for entry in table.modules.values():
            scanner = _BodyScanner(entry.tree.body)
            self._apply_scan(entry.id, None, scanner, table)

    def _apply_scan(
        self,
        source_id: str,
        symbol: Optional[SymbolEntry],
        scanner: _BodyScanner,
        table: SymbolTable,
    ):
        node = self._nodes.get(source_id)
        if node is None:
            return
        for flag in sorted(scanner.dynamic):
            if flag not in node.flags:
                node.flags.append(flag)
        module = symbol.module if symbol else node.metadata.get("module", "")
        file_path = symbol.file_path if symbol else node.span.file_path
        unresolved: Counter = Counter()
        unresolved_evidence: List[Dict[str, Any]] = []

        for target_module, line in scanner.dynamic_imports:
            self._add_edge(
                source_id, module_id(target_module), RelationKind.IMPORTS,
                Confidence.DYNAMIC_REQUIRED, Resolution.EXACT,
                SourceSpan(file_path, line, line),
            )

        for reference in scanner.references:
            if reference.receiver is None and reference.name in scanner.locals:
                continue
            target, resolution, confidence, candidates = self._resolve_reference(
                reference, symbol, module, table
            )
            if target is None:
                if reference.is_call:
                    unresolved[reference.name] += 1
                    unresolved_evidence.append({
                        "name": reference.name,
                        "resolution": str(Resolution.UNRESOLVED),
                        "confidence": str(Confidence.DYNAMIC_REQUIRED),
                        "evidence": {
                            "file_path": file_path,
                            "start_line": reference.line,
                            "end_line": reference.line,
                        },
                    })
                continue
            target_symbol = table.by_id.get(target)
            if reference.is_call:
                relation = (
                    RelationKind.INSTANTIATES
                    if target_symbol is not None and target_symbol.kind == NodeKind.CLASS
                    else RelationKind.CALLS
                )
            elif target_symbol is not None and target_symbol.kind in (NodeKind.CONSTANT, NodeKind.FIELD):
                relation = RelationKind.READS
            else:
                continue
            self._add_edge(
                source_id, target, relation, confidence, resolution,
                SourceSpan(file_path, reference.line, reference.line), candidates,
            )

        if symbol is not None:
            for name, line in scanner.stores:
                target = table.resolve_in_module(module, name)
                if target and table.by_id.get(target) and table.by_id[target].kind == NodeKind.CONSTANT:
                    self._add_edge(
                        source_id, target, RelationKind.WRITES,
                        evidence=SourceSpan(file_path, line, line),
                    )
        if unresolved:
            node.metadata["unresolved_calls"] = dict(unresolved.most_common(20))
            node.metadata["unresolved_references"] = unresolved_evidence[:20]
            if len(unresolved_evidence) > 20:
                node.metadata["unresolved_reference_total"] = len(unresolved_evidence)
                node.metadata["unresolved_reference_limit"] = 20
                node.metadata["unresolved_reference_truncated"] = True

    # ---- resolution ----

    def _resolve_reference(
        self,
        reference: _Reference,
        symbol: Optional[SymbolEntry],
        module: str,
        table: SymbolTable,
    ) -> Tuple[Optional[str], str, str, List[str]]:
        receiver = reference.receiver
        if receiver in ("self", "cls") and symbol is not None:
            owner = self._owning_class(symbol, table)
            if owner is not None:
                found = self._lookup_member(owner, reference.name, table)
                if found:
                    return found, Resolution.EXACT, Confidence.STATIC_CERTAIN, []
            return self._resolve_name(reference.name, module, table)
        if receiver:
            entry = table.modules.get(module)
            binding = entry.bindings.get(receiver) if entry else None
            if binding is not None and binding.symbol is None:
                target_module = table.modules.get(binding.module)
                if target_module and reference.name in target_module.defines:
                    return target_module.defines[reference.name], Resolution.EXACT, Confidence.STATIC_CERTAIN, []
                if target_module:
                    return None, Resolution.UNRESOLVED, Confidence.DYNAMIC_REQUIRED, []
            if binding is not None and binding.symbol is not None:
                owner_id = table.resolve_binding(binding)
                owner = table.by_id.get(owner_id) if owner_id else None
                if owner is not None and owner.kind == NodeKind.CLASS:
                    found = self._lookup_member(owner, reference.name, table)
                    if found:
                        return found, Resolution.EXACT, Confidence.STATIC_CERTAIN, []
            if entry and receiver in entry.defines:
                owner = table.by_id.get(entry.defines[receiver])
                if owner is not None and owner.kind == NodeKind.CLASS:
                    found = self._lookup_member(owner, reference.name, table)
                    if found:
                        return found, Resolution.EXACT, Confidence.STATIC_CERTAIN, []
            return self._by_simple_name(reference.name, table)
        return self._resolve_name(reference.name, module, table)

    def _resolve_name(
        self, name: str, module: str, table: SymbolTable
    ) -> Tuple[Optional[str], str, str, List[str]]:
        if not name:
            return None, Resolution.UNRESOLVED, Confidence.DYNAMIC_REQUIRED, []
        resolved = table.resolve_in_module(module, name)
        if resolved:
            return resolved, Resolution.EXACT, Confidence.STATIC_CERTAIN, []
        return self._by_simple_name(name, table)

    @staticmethod
    def _by_simple_name(name: str, table: SymbolTable) -> Tuple[Optional[str], str, str, List[str]]:
        candidates = table.by_simple_name.get(name, [])
        if len(candidates) == 1:
            return candidates[0], Resolution.UNIQUE_NAME, Confidence.STATIC_INFERRED, []
        if len(candidates) > 1:
            return candidates[0], Resolution.AMBIGUOUS, Confidence.STATIC_INFERRED, list(candidates[1:])
        return None, Resolution.UNRESOLVED, Confidence.DYNAMIC_REQUIRED, []

    @staticmethod
    def _owning_class(symbol: SymbolEntry, table: SymbolTable) -> Optional[SymbolEntry]:
        parent = table.by_id.get(symbol.parent_id) if symbol.parent_id else None
        return parent if parent is not None and parent.kind == NodeKind.CLASS else None

    def _lookup_member(
        self, owner: SymbolEntry, name: str, table: SymbolTable, seen: Optional[Set[str]] = None
    ) -> Optional[str]:
        seen = seen or set()
        if owner.id in seen:
            return None
        seen.add(owner.id)
        direct = f"py:{owner.module}#{owner.qualname}.{name}"
        if direct in table.by_id:
            return direct
        for base_name, _ in owner.bases:
            base_id, _resolution, _confidence, _candidates = self._resolve_name(
                base_name.rsplit(".", 1)[-1], owner.module, table
            )
            base = table.by_id.get(base_id) if base_id else None
            if base is not None and base.kind == NodeKind.CLASS:
                found = self._lookup_member(base, name, table, seen)
                if found:
                    return found
        return None

    @staticmethod
    def _symbol_collection(nodes: Sequence[GraphNode]) -> ReportCollection:
        return ReportCollection(
            key="symbols",
            label="Symbols",
            view="table",
            node_category=None,
            columns=[
                ColumnSpec("symbol_path", "Symbol", "mono"),
                ColumnSpec("kind", "Kind"),
                ColumnSpec("file_path", "File", "mono"),
                ColumnSpec("line_number", "Line"),
                ColumnSpec("token_cost", "Tokens"),
                ColumnSpec("flags", "Flags", "list"),
            ],
            rows=[{
                "id": node.id,
                "symbol_path": node.symbol_path or node.label,
                "kind": node.kind,
                "file_path": node.span.file_path if node.span else "",
                "line_number": node.span.start_line if node.span else "",
                "token_cost": node.cost.token_estimate if node.cost else "",
                "flags": node.flags,
            } for node in nodes],
        )
