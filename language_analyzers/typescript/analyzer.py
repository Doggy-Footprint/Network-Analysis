from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from language_analyzers.core import flags as flag_names
from language_analyzers.core.cost import cost_for_span
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

from . import ast as ts

SOURCE_EXTENSIONS = tuple(ts.GRAMMAR_BY_SUFFIX)
IGNORED_DIRECTORIES = {".git", "node_modules", "dist", "build", "coverage", ".next"}
PROVENANCE = "typescript-core"
LANGUAGE = "typescript"

_KIND_BY_TYPE = {
    "class_declaration": NodeKind.CLASS,
    "abstract_class_declaration": NodeKind.CLASS,
    "interface_declaration": NodeKind.INTERFACE,
    "enum_declaration": NodeKind.ENUM,
    "type_alias_declaration": NodeKind.TYPE_ALIAS,
    "function_declaration": NodeKind.FUNCTION,
    "generator_function_declaration": NodeKind.FUNCTION,
}
_FUNCTION_VALUE_TYPES = ("arrow_function", "function_expression", "generator_function")


@dataclass
class TypeScriptProjectArchitecture:
    project_name: str
    project_path: str
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    stats: Dict[str, object] = field(default_factory=dict)
    report_collections: List[ReportCollection] = field(default_factory=list)


@dataclass
class _Symbol:
    id: str
    name: str
    qualname: str
    kind: str
    file_key: str
    start_line: int
    end_line: int
    exported: bool = False
    parent: Optional[str] = None
    signature: Optional[str] = None
    heritage: List[Tuple[str, str, int]] = field(default_factory=list)
    annotations: List[Tuple[str, int]] = field(default_factory=list)
    type_parameter_constraints: List[Tuple[str, int]] = field(default_factory=list)
    body: Any = None
    parameters: List[str] = field(default_factory=list)


@dataclass
class _Import:
    local_name: str
    specifier: str
    imported_name: Optional[str]
    line: int
    is_namespace: bool = False


@dataclass
class _Module:
    id: str
    file_key: str
    path: Path
    source: bytes
    text: str
    tree: Any
    end_line: int
    imports: Dict[str, _Import] = field(default_factory=dict)
    module_specifiers: List[Tuple[str, int]] = field(default_factory=list)
    reexport_specifiers: List[Tuple[Optional[str], str, int]] = field(default_factory=list)
    dynamic_specifiers: List[Tuple[str, int]] = field(default_factory=list)
    defines: Dict[str, str] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)


class TypeScriptAnalyzer:
    def __init__(self, project_path: Union[str, Path]):
        self.project_path = Path(project_path).resolve()

    def analyze(self) -> TypeScriptProjectArchitecture:
        modules = [self._parse(path) for path in self._discover_files()]
        modules = [module for module in modules if module is not None]
        self._modules: Dict[str, _Module] = {module.file_key: module for module in modules}
        self._symbols: Dict[str, _Symbol] = {}
        self._by_simple_name: Dict[str, List[str]] = {}
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: Dict[Tuple[str, str, str], GraphEdge] = {}

        for module in modules:
            self._collect_module(module)
        for module in modules:
            self._module_node(module)
        for symbol in self._symbols.values():
            self._symbol_node(symbol)
        for module in modules:
            self._module_edges(module)
        for symbol in self._symbols.values():
            self._symbol_edges(symbol)
        for module in modules:
            self._scan_bodies(module)

        nodes = list(self._nodes.values())
        edges = list(self._edges.values())
        architecture = TypeScriptProjectArchitecture(
            project_name=self.project_path.name,
            project_path=str(self.project_path),
            nodes=nodes,
            edges=edges,
            stats={
                "total_files": len(modules),
                "total_symbols": len(self._symbols),
                "symbols_by_kind": dict(Counter(symbol.kind for symbol in self._symbols.values())),
                "nodes_by_kind": dict(Counter(node.kind for node in nodes)),
                "edges_by_relation": dict(Counter(edge.relation for edge in edges)),
                "edges_by_confidence": dict(Counter(str(edge.confidence) for edge in edges)),
            },
            report_collections=[self._symbol_collection(nodes)],
        )
        enrich_repository(architecture)
        architecture.stats["nodes_by_kind"] = dict(Counter(node.kind for node in architecture.nodes))
        architecture.stats["edges_by_relation"] = dict(Counter(edge.relation for edge in architecture.edges))
        return architecture

    # ---- discovery & parsing ----

    def _discover_files(self) -> List[Path]:
        result = []
        for path in self.project_path.rglob("*"):
            if not path.is_file() or path.suffix not in SOURCE_EXTENSIONS:
                continue
            parts = path.relative_to(self.project_path).parts
            if any(part in IGNORED_DIRECTORIES or part.startswith(".") for part in parts):
                continue
            result.append(path)
        return sorted(result)

    def _parse(self, path: Path) -> Optional[_Module]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        source = text.encode("utf-8")
        tree = ts.parser_for_suffix(path.suffix).parse(source)
        file_key = path.relative_to(self.project_path).as_posix()
        return _Module(
            id=self._file_id(file_key),
            file_key=file_key,
            path=path,
            source=source,
            text=text,
            tree=tree,
            end_line=max(1, text.count("\n") + 1),
            flags=flag_names.path_flags(file_key),
        )

    @staticmethod
    def _file_id(file_key: str) -> str:
        return f"ts:{file_key}"

    @staticmethod
    def _symbol_id(file_key: str, qualname: str) -> str:
        return f"ts:{file_key}#{qualname}"

    # ---- collection ----

    def _collect_module(self, module: _Module):
        for child in module.tree.root_node.named_children:
            self._collect_statement(module, child, exported=False, scope=[], parent=None)
        if self._is_barrel(module):
            module.flags.append(flag_names.REEXPORT)
        for node in ts.descendants(module.tree.root_node):
            if node.type != "call_expression":
                continue
            function = node.child_by_field_name("function")
            if function is None:
                continue
            head = ts.node_text(module.source, function)
            if head in ("import", "require"):
                arguments = node.child_by_field_name("arguments")
                literal = ts.child_of_type(arguments, "string", "template_string") if arguments else None
                value = ts.string_literal_value(module.source, literal) if literal is not None else None
                if value:
                    module.dynamic_specifiers.append((value, ts.start_line(node)))

    @staticmethod
    def _is_barrel(module: _Module) -> bool:
        statements = [
            child for child in module.tree.root_node.named_children
            if child.type not in ("comment",)
        ]
        if not statements:
            return False
        interesting = [
            child for child in statements
            if child.type not in ("import_statement",)
        ]
        if not interesting:
            return False
        return all(
            child.type == "export_statement" and ts.child_of_type(child, "string") is not None
            for child in interesting
        )

    def _collect_statement(self, module: _Module, node, exported: bool, scope: List[str], parent):
        if node.type == "import_statement":
            self._collect_import(module, node)
            return
        if node.type == "export_statement":
            self._collect_export(module, node, scope, parent)
            return
        if node.type in _KIND_BY_TYPE:
            self._collect_declaration(module, node, exported, scope, parent)
            return
        if node.type == "type_alias_declaration":
            self._collect_declaration(module, node, exported, scope, parent)
            return
        if node.type in ("lexical_declaration", "variable_declaration"):
            for declarator in ts.children_of_type(node, "variable_declarator"):
                self._collect_variable(module, node, declarator, exported, scope, parent)

    def _collect_import(self, module: _Module, node):
        specifier_node = ts.child_of_type(node, "string")
        specifier = ts.string_literal_value(module.source, specifier_node)
        if not specifier:
            return
        line = ts.start_line(node)
        module.module_specifiers.append((specifier, line))
        clause = ts.child_of_type(node, "import_clause")
        if clause is None:
            return
        for child in clause.named_children:
            if child.type == "identifier":
                module.imports[ts.node_text(module.source, child)] = _Import(
                    ts.node_text(module.source, child), specifier, "default", line
                )
            elif child.type == "namespace_import":
                alias = ts.child_of_type(child, "identifier")
                if alias is not None:
                    name = ts.node_text(module.source, alias)
                    module.imports[name] = _Import(name, specifier, None, line, is_namespace=True)
            elif child.type == "named_imports":
                for entry in ts.children_of_type(child, "import_specifier"):
                    original = entry.child_by_field_name("name")
                    alias = entry.child_by_field_name("alias")
                    if original is None:
                        continue
                    imported = ts.node_text(module.source, original)
                    local = ts.node_text(module.source, alias) if alias is not None else imported
                    module.imports[local] = _Import(local, specifier, imported, line)

    def _collect_export(self, module: _Module, node, scope: List[str], parent):
        specifier_node = ts.child_of_type(node, "string")
        specifier = ts.string_literal_value(module.source, specifier_node) if specifier_node else None
        line = ts.start_line(node)
        if specifier:
            module.module_specifiers.append((specifier, line))
            clause = ts.child_of_type(node, "export_clause")
            if clause is None:
                module.reexport_specifiers.append((None, specifier, line))
            else:
                for entry in ts.children_of_type(clause, "export_specifier"):
                    original = entry.child_by_field_name("name")
                    if original is not None:
                        module.reexport_specifiers.append(
                            (ts.node_text(module.source, original), specifier, line)
                        )
            return
        for child in node.named_children:
            self._collect_statement(module, child, exported=True, scope=scope, parent=parent)

    def _collect_declaration(self, module: _Module, node, exported: bool, scope: List[str], parent):
        name = ts.declared_name(module.source, node)
        if not name:
            return
        kind = _KIND_BY_TYPE.get(node.type, NodeKind.TYPE_ALIAS)
        symbol = self._make_symbol(module, node, name, kind, exported, scope, parent)
        symbol.heritage = self._heritage(module, node)
        symbol.signature = self._signature(module, node, name, kind)
        symbol.type_parameter_constraints = self._type_parameter_constraint_names(module, node)
        if kind == NodeKind.CLASS:
            body = ts.child_of_type(node, "class_body")
            if body is not None:
                self._collect_class_members(module, body, symbol, scope + [name])
        elif kind == NodeKind.FUNCTION:
            symbol.body = ts.child_of_type(node, "statement_block")
            symbol.parameters = self._parameters(module, node)
            symbol.annotations = self._annotations(module, node)
            symbol.type_parameter_constraints = self._type_parameter_constraint_names(module, node)

    def _collect_class_members(self, module: _Module, body, owner: _Symbol, scope: List[str]):
        for member in body.named_children:
            if member.type == "method_definition":
                name = ts.declared_name(module.source, member)
                if not name:
                    continue
                symbol = self._make_symbol(module, member, name, NodeKind.METHOD, False, scope, owner)
                symbol.body = ts.child_of_type(member, "statement_block")
                symbol.parameters = self._parameters(module, member)
                symbol.annotations = self._annotations(module, member)
                symbol.type_parameter_constraints = self._type_parameter_constraint_names(module, member)
                symbol.signature = f"{name}({', '.join(symbol.parameters)})"
            elif member.type == "public_field_definition":
                name = ts.declared_name(module.source, member)
                if not name:
                    continue
                symbol = self._make_symbol(module, member, name, NodeKind.FIELD, False, scope, owner)
                symbol.annotations = self._annotations(module, member)
                symbol.type_parameter_constraints = self._type_parameter_constraint_names(module, member)
                symbol.body = member

    def _collect_variable(self, module: _Module, statement, declarator, exported, scope, parent):
        name_node = declarator.child_by_field_name("name")
        if name_node is None or name_node.type != "identifier":
            return
        name = ts.node_text(module.source, name_node)
        value = declarator.child_by_field_name("value")
        is_function = value is not None and value.type in _FUNCTION_VALUE_TYPES
        kind = NodeKind.FUNCTION if is_function else NodeKind.CONSTANT
        symbol = self._make_symbol(module, statement, name, kind, exported, scope, parent)
        symbol.annotations = self._annotations(module, declarator)
        symbol.type_parameter_constraints = self._type_parameter_constraint_names(module, declarator)
        if is_function:
            symbol.body = value
            symbol.parameters = self._parameters(module, value)
            symbol.signature = f"{name}({', '.join(symbol.parameters)})"
        else:
            symbol.body = declarator

    def _make_symbol(self, module: _Module, node, name, kind, exported, scope, parent) -> _Symbol:
        qualname = ".".join(list(scope) + [name])
        symbol = _Symbol(
            id=self._symbol_id(module.file_key, qualname),
            name=name,
            qualname=qualname,
            kind=kind,
            file_key=module.file_key,
            start_line=ts.start_line(node),
            end_line=ts.end_line(node),
            exported=exported,
            parent=parent.id if isinstance(parent, _Symbol) else None,
        )
        self._symbols[symbol.id] = symbol
        self._by_simple_name.setdefault(name, []).append(symbol.id)
        if not scope:
            module.defines[name] = symbol.id
        return symbol

    @staticmethod
    def _parameters(module: _Module, node) -> List[str]:
        parameters = ts.child_of_type(node, "formal_parameters")
        if parameters is None:
            return []
        return [
            ts.node_text(module.source, child).strip()
            for child in parameters.named_children
            if child.type != "comment"
        ]

    @staticmethod
    def _annotations(module: _Module, node) -> List[Tuple[str, int]]:
        found: List[Tuple[str, int]] = []
        for item in ts.descendants(node):
            if item.type == "type_annotation":
                for name in ts.type_names(module.source, item):
                    found.append((name, ts.start_line(item)))
        return found

    @staticmethod
    def _type_parameter_constraint_names(module: _Module, node) -> List[Tuple[str, int]]:
        found: List[Tuple[str, int]] = []
        type_parameters = ts.child_of_type(node, "type_parameters")
        if type_parameters is None:
            return found
        for parameter in ts.children_of_type(type_parameters, "type_parameter"):
            constraint = ts.child_of_type(parameter, "constraint")
            if constraint is None:
                continue
            for name in ts.type_names(module.source, constraint):
                found.append((name, ts.start_line(constraint)))
        return found

    @staticmethod
    def _heritage(module: _Module, node) -> List[Tuple[str, str, int]]:
        result: List[Tuple[str, str, int]] = []
        heritage = ts.child_of_type(node, "class_heritage")
        clauses = heritage.named_children if heritage is not None else []
        clauses = list(clauses) + ts.children_of_type(node, "extends_type_clause", "extends_clause")
        for clause in clauses:
            relation = (
                RelationKind.IMPLEMENTS
                if clause.type == "implements_clause"
                else RelationKind.INHERITS
            )
            for name in ts.type_names(module.source, clause):
                result.append((name, relation, ts.start_line(clause)))
        return result

    @staticmethod
    def _signature(module: _Module, node, name: str, kind: str) -> str:
        if kind == NodeKind.FUNCTION:
            parameters = ts.child_of_type(node, "formal_parameters")
            text = ts.node_text(module.source, parameters) if parameters is not None else "()"
            return f"function {name}{text}"
        first_line = ts.node_text(module.source, node).splitlines()[0]
        return first_line.split("{")[0].strip()

    # ---- nodes ----

    def _module_node(self, module: _Module):
        span = SourceSpan(module.file_key, 1, module.end_line)
        self._nodes[module.id] = GraphNode(
            id=module.id,
            label=module.file_key,
            group=NodeKind.FILE,
            category=NodeKind.FILE,
            kind=NodeKind.FILE,
            language=LANGUAGE,
            span=span,
            cost=cost_for_span(module.text, span),
            symbol_path=module.file_key,
            flags=list(module.flags),
            provenance=PROVENANCE,
            metadata={"file_path": module.file_key},
        )

    def _symbol_node(self, symbol: _Symbol):
        module = self._modules[symbol.file_key]
        span = SourceSpan(symbol.file_key, symbol.start_line, symbol.end_line)
        flags = list(module.flags)
        collisions = len({
            self._symbols[item].file_key for item in self._by_simple_name.get(symbol.name, [])
        })
        metadata: Dict[str, Any] = {"kind": symbol.kind, "name": symbol.name}
        if collisions > 1:
            flags.append(flag_names.AMBIGUOUS_NAME)
            metadata["name_collision_count"] = collisions
        self._nodes[symbol.id] = GraphNode(
            id=symbol.id,
            label=symbol.name,
            group=symbol.kind,
            category=symbol.kind,
            kind=symbol.kind,
            language=LANGUAGE,
            span=span,
            cost=cost_for_span(module.text, span),
            signature=symbol.signature,
            exported=symbol.exported,
            symbol_path=f"{symbol.file_key}:{symbol.qualname}",
            flags=flags,
            provenance=PROVENANCE,
            metadata=metadata,
        )

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

    def _module_edges(self, module: _Module):
        for name, symbol_id in module.defines.items():
            relation = (
                RelationKind.EXPORTS
                if self._symbols[symbol_id].exported
                else RelationKind.DECLARES
            )
            self._add_edge(module.id, symbol_id, relation)

        for specifier, line in module.module_specifiers:
            target = self._resolve_import(module.path, specifier)
            if target:
                self._add_edge(
                    module.id, self._file_id(target), RelationKind.IMPORTS,
                    evidence=SourceSpan(module.file_key, line, line),
                )

        for binding in module.imports.values():
            if binding.imported_name in (None, "default"):
                continue
            target_id = self._resolve_binding(module, binding)
            if target_id:
                self._add_edge(
                    module.id, target_id, RelationKind.IMPORTS_SYMBOL,
                    evidence=SourceSpan(module.file_key, binding.line, binding.line),
                )

        for name, specifier, line in module.reexport_specifiers:
            target = self._resolve_import(module.path, specifier)
            if not target:
                continue
            target_module = self._modules.get(target)
            evidence = SourceSpan(module.file_key, line, line)
            if name is None:
                for symbol_id in target_module.defines.values():
                    if self._symbols[symbol_id].exported:
                        self._add_edge(module.id, symbol_id, RelationKind.RE_EXPORTS, evidence=evidence)
            elif name in target_module.defines:
                self._add_edge(
                    module.id, target_module.defines[name], RelationKind.RE_EXPORTS, evidence=evidence
                )

        for specifier, line in module.dynamic_specifiers:
            target = self._resolve_import(module.path, specifier)
            if target:
                self._add_edge(
                    module.id, self._file_id(target), RelationKind.IMPORTS,
                    Confidence.DYNAMIC_REQUIRED, Resolution.EXACT,
                    SourceSpan(module.file_key, line, line),
                )
        if module.dynamic_specifiers:
            node = self._nodes[module.id]
            if flag_names.DYNAMIC_IMPORT not in node.flags:
                node.flags.append(flag_names.DYNAMIC_IMPORT)

    def _symbol_edges(self, symbol: _Symbol):
        module = self._modules[symbol.file_key]
        if symbol.parent:
            self._add_edge(symbol.parent, symbol.id, RelationKind.CONTAINS)
        for name, relation, line in symbol.heritage:
            target, resolution, confidence, candidates = self._resolve_name(module, name)
            if target:
                self._add_edge(
                    symbol.id, target, relation, confidence, resolution,
                    SourceSpan(symbol.file_key, line, line), candidates,
                )
        for name, line in symbol.annotations:
            target, resolution, confidence, candidates = self._resolve_name(module, name)
            if target and self._symbols.get(target) and self._symbols[target].kind in (
                NodeKind.CLASS, NodeKind.INTERFACE, NodeKind.ENUM, NodeKind.TYPE_ALIAS
            ):
                self._add_edge(
                    symbol.id, target, RelationKind.TYPE_USES, confidence, resolution,
                    SourceSpan(symbol.file_key, line, line), candidates,
                )
        for name, line in symbol.type_parameter_constraints:
            target, resolution, confidence, candidates = self._resolve_name(module, name)
            if target and self._symbols.get(target) and self._symbols[target].kind in (
                NodeKind.CLASS, NodeKind.INTERFACE, NodeKind.ENUM, NodeKind.TYPE_ALIAS
            ):
                self._add_edge(
                    symbol.id, target, RelationKind.TYPE_USES, confidence, resolution,
                    SourceSpan(symbol.file_key, line, line), candidates,
                )

    def _scan_bodies(self, module: _Module):
        for symbol in self._symbols.values():
            if symbol.file_key != module.file_key or symbol.body is None:
                continue
            self._scan_body(module, symbol.id, symbol, symbol.body, set(symbol.parameters))

    def _scan_body(self, module: _Module, source_id: str, symbol: Optional[_Symbol], body, parameters: Set[str]):
        locals_: Set[str] = {
            parameter.split(":")[0].strip().lstrip("...").strip() for parameter in parameters
        }
        nodes = sorted(
            ts.descendants_excluding_definitions(body),
            key=lambda item: (item.start_point[0], item.start_point[1]),
        )
        for node in nodes:
            if node.type == "variable_declarator":
                name_node = node.child_by_field_name("name")
                if name_node is not None and name_node.type == "identifier":
                    locals_.add(ts.node_text(module.source, name_node))

        unresolved: Counter = Counter()
        unresolved_evidence: List[Dict[str, Any]] = []
        for node in nodes:
            if node.type not in ("call_expression", "new_expression"):
                continue
            type_arguments = node.child_by_field_name("type_arguments")
            if type_arguments is not None:
                for type_name in ts.type_names(module.source, type_arguments):
                    type_target, type_resolution, type_confidence, type_candidates = self._resolve_name(
                        module, type_name
                    )
                    if type_target and self._symbols.get(type_target) and self._symbols[type_target].kind in (
                        NodeKind.CLASS, NodeKind.INTERFACE, NodeKind.ENUM, NodeKind.TYPE_ALIAS
                    ):
                        self._add_edge(
                            source_id, type_target, RelationKind.TYPE_USES, type_confidence, type_resolution,
                            SourceSpan(module.file_key, ts.start_line(type_arguments), ts.start_line(type_arguments)),
                            type_candidates,
                        )
            if node.type == "new_expression":
                constructor = node.child_by_field_name("constructor")
                name = ts.node_text(module.source, constructor) if constructor is not None else None
                receiver = None
            else:
                name = ts.callee_name(module.source, node)
                receiver = ts.callee_receiver(module.source, node)
            if not name or name in ("import", "require"):
                continue
            if receiver is None and name in locals_:
                continue
            target, resolution, confidence, candidates = self._resolve_reference(
                module, symbol, name, receiver
            )
            if target is None:
                unresolved[name] += 1
                unresolved_evidence.append({
                    "name": name,
                    "resolution": str(Resolution.UNRESOLVED),
                    "confidence": str(Confidence.DYNAMIC_REQUIRED),
                    "evidence": {"file_path": module.file_key, "start_line": ts.start_line(node), "end_line": ts.start_line(node)},
                })
                continue
            relation = (
                RelationKind.INSTANTIATES
                if node.type == "new_expression" or self._symbols[target].kind == NodeKind.CLASS
                else RelationKind.CALLS
            )
            self._add_edge(
                source_id, target, relation, confidence, resolution,
                SourceSpan(module.file_key, ts.start_line(node), ts.start_line(node)), candidates,
            )
        if unresolved:
            self._nodes[source_id].metadata["unresolved_calls"] = dict(unresolved.most_common(20))
            self._nodes[source_id].metadata["unresolved_references"] = unresolved_evidence[:20]

        write_nodes: Set[Tuple[int, int]] = set()
        for node in nodes:
            if node.type in ("assignment_expression", "augmented_assignment_expression"):
                left = node.child_by_field_name("left")
                if left is not None:
                    write_nodes.update((item.start_byte, item.end_byte) for item in [left] + list(ts.descendants(left)))
            elif node.type == "update_expression":
                argument = node.child_by_field_name("argument") or ts.child_of_type(node, "identifier", "member_expression")
                if argument is not None:
                    write_nodes.update((item.start_byte, item.end_byte) for item in [argument] + list(ts.descendants(argument)))

        for node in nodes:
            if node.type not in ("identifier", "property_identifier"):
                continue
            parent = node.parent
            if parent is not None and parent.type in ("variable_declarator", "formal_parameter", "required_parameter", "optional_parameter") and parent.child_by_field_name("name") == node:
                continue
            name = ts.node_text(module.source, node)
            if name in locals_ or name in ("this", "undefined"):
                continue
            target, resolution, confidence, candidates = self._resolve_name(module, name)
            if target is None:
                continue
            relation = RelationKind.WRITES if (node.start_byte, node.end_byte) in write_nodes else RelationKind.READS
            self._add_edge(
                source_id, target, relation, confidence, resolution,
                SourceSpan(module.file_key, ts.start_line(node), ts.start_line(node)), candidates,
            )

    # ---- resolution ----

    def _resolve_reference(self, module: _Module, symbol: Optional[_Symbol], name: str, receiver: Optional[str]):
        if receiver == "this" and symbol is not None and symbol.parent:
            owner = self._symbols.get(symbol.parent)
            if owner is not None:
                member = self._symbol_id(owner.file_key, f"{owner.qualname}.{name}")
                if member in self._symbols:
                    return member, Resolution.EXACT, Confidence.STATIC_CERTAIN, []
                for base_name, relation, _line in owner.heritage:
                    base_id, _r, _c, _cand = self._resolve_name(module, base_name)
                    base = self._symbols.get(base_id) if base_id else None
                    if base is not None:
                        inherited = self._symbol_id(base.file_key, f"{base.qualname}.{name}")
                        if inherited in self._symbols:
                            return inherited, Resolution.EXACT, Confidence.STATIC_CERTAIN, []
            return self._by_simple_name_lookup(name)
        if receiver:
            binding = module.imports.get(receiver)
            if binding is not None and binding.is_namespace:
                target_key = self._resolve_import(module.path, binding.specifier)
                target_module = self._modules.get(target_key) if target_key else None
                if target_module is not None and name in target_module.defines:
                    return target_module.defines[name], Resolution.EXACT, Confidence.STATIC_CERTAIN, []
                return None, Resolution.UNRESOLVED, Confidence.DYNAMIC_REQUIRED, []
            return self._by_simple_name_lookup(name)
        return self._resolve_name(module, name)

    def _resolve_name(self, module: _Module, name: str):
        if not name:
            return None, Resolution.UNRESOLVED, Confidence.DYNAMIC_REQUIRED, []
        if name in module.defines:
            return module.defines[name], Resolution.EXACT, Confidence.STATIC_CERTAIN, []
        binding = module.imports.get(name)
        if binding is not None:
            resolved = self._resolve_binding(module, binding)
            if resolved:
                return resolved, Resolution.EXACT, Confidence.STATIC_CERTAIN, []
        return self._by_simple_name_lookup(name)

    def _resolve_binding(self, module: _Module, binding: _Import) -> Optional[str]:
        target_key = self._resolve_import(module.path, binding.specifier)
        target_module = self._modules.get(target_key) if target_key else None
        if target_module is None:
            return None
        if binding.imported_name and binding.imported_name in target_module.defines:
            return target_module.defines[binding.imported_name]
        if binding.imported_name == "default":
            exported = [
                symbol_id for symbol_id in target_module.defines.values()
                if self._symbols[symbol_id].exported
            ]
            if len(exported) == 1:
                return exported[0]
        for name, specifier, _line in target_module.reexport_specifiers:
            if name and name == binding.imported_name:
                nested = self._resolve_import(target_module.path, specifier)
                nested_module = self._modules.get(nested) if nested else None
                if nested_module and name in nested_module.defines:
                    return nested_module.defines[name]
        return None

    def _by_simple_name_lookup(self, name: str):
        candidates = self._by_simple_name.get(name, [])
        if len(candidates) == 1:
            return candidates[0], Resolution.UNIQUE_NAME, Confidence.STATIC_INFERRED, []
        if len(candidates) > 1:
            return candidates[0], Resolution.AMBIGUOUS, Confidence.STATIC_INFERRED, list(candidates[1:])
        return None, Resolution.UNRESOLVED, Confidence.DYNAMIC_REQUIRED, []

    def _resolve_import(self, file_path: Path, specifier: str) -> Optional[str]:
        if not specifier.startswith("."):
            return None
        base = (file_path.parent / specifier).resolve()
        candidates = [base] if base.suffix in SOURCE_EXTENSIONS else []
        candidates += [base.with_suffix(extension) for extension in SOURCE_EXTENSIONS]
        candidates += [base / f"index{extension}" for extension in SOURCE_EXTENSIONS]
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                key = candidate.relative_to(self.project_path).as_posix()
            except ValueError:
                continue
            if key in self._modules:
                return key
        return None

    @staticmethod
    def _symbol_collection(nodes: Sequence[GraphNode]) -> ReportCollection:
        return ReportCollection(
            key="symbols",
            label="Symbols",
            view="table",
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
