from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, Union

if TYPE_CHECKING:
    from agent_view.models import RepositorySnapshot

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

from . import ast as ka


@dataclass
class KotlinProjectArchitecture:
    project_name: str
    project_path: str
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    report_collections: List[ReportCollection] = field(default_factory=list)


@dataclass
class _KotlinSymbol:
    id: str
    name: str
    kind: str
    file_key: str
    qualname: str
    node: Any
    parent: Optional[str]
    is_extension: bool = False
    receiver_type: Optional[str] = None


class KotlinAnalyzer:
    def __init__(self, project_path: Union[str, Path], parse_cache: Optional[ka.KotlinParseCache] = None,
                 snapshot: Optional[RepositorySnapshot] = None):
        self.snapshot = snapshot
        if snapshot is None:
            self.project_path = Path(project_path).resolve()
        else:
            supplied = Path(project_path)
            snapshot_root = Path(snapshot.root)
            if not supplied.is_absolute() or not snapshot_root.is_absolute() or supplied != snapshot_root:
                raise ValueError("project path and snapshot root must be absolute and match")
            self.project_path = snapshot_root
        self._parse_cache = parse_cache if parse_cache is not None else ka.KotlinParseCache()

    def analyze(self) -> KotlinProjectArchitecture:
        nodes, edges = self.build()
        architecture = KotlinProjectArchitecture(
            project_name=self.project_path.name,
            project_path=str(self.project_path),
            nodes=nodes,
            edges=edges,
        )
        if self.snapshot is None:
            enrich_repository(architecture)
        else:
            contents = self.snapshot.content_map()
            enrich_repository(architecture, file_inventory=tuple(contents),
                              file_reader=lambda path: contents[path.relative_to(self.project_path).as_posix()])
        architecture.stats = {
            "total_files": len(self._files),
            "total_symbols": len(self._symbols),
            "nodes_by_kind": dict(Counter(node.kind for node in architecture.nodes)),
            "edges_by_relation": dict(Counter(edge.relation for edge in architecture.edges)),
            "edges_by_confidence": dict(Counter(str(edge.confidence) for edge in architecture.edges)),
        }
        architecture.report_collections = [self._symbol_collection(architecture.nodes)]
        return architecture

    def build(self) -> tuple[List[GraphNode], List[GraphEdge]]:
        self._files: Dict[str, Tuple[bytes, str, Any]] = {}
        self._symbols: Dict[str, _KotlinSymbol] = {}
        self._by_name: Dict[str, List[str]] = {}
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: Dict[Tuple[str, str, str], GraphEdge] = {}
        self._imports: Dict[str, List[Tuple[str, int]]] = {}

        for path in self._discover_files():
            try:
                if self.snapshot is None:
                    source, root = self._parse_cache.read_and_parse(path)
                else:
                    source = self.snapshot.content_map()[path.relative_to(self.project_path).as_posix()].encode("utf-8")
                    source, root = self._parse_cache.parse_snapshot(path, source)
            except OSError:
                continue
            key = path.relative_to(self.project_path).as_posix()
            text = source.decode("utf-8", "replace")
            self._files[key] = (source, text, root)
            self._collect_file(key, source, text, root)

        for symbol in self._symbols.values():
            self._add_symbol_node(symbol)
        for key in self._files:
            self._add_import_edges(key)
        for symbol in self._symbols.values():
            self._add_symbol_edges(symbol)

        return list(self._nodes.values()), list(self._edges.values())

    def _discover_files(self) -> List[Path]:
        if self.snapshot is not None:
            return sorted(self.project_path / relative for relative, _source in self.snapshot.contents
                          if relative.endswith(".kt")
                          and not any(part in {".git", ".gradle", ".idea", "build"}
                                      for part in Path(relative).parts))
        ignored = {".git", ".gradle", ".idea", "build"}
        return sorted(
            path for path in self.project_path.rglob("*.kt")
            if path.is_file() and not any(part in ignored for part in path.relative_to(self.project_path).parts)
        )

    def _collect_file(self, key: str, source: bytes, text: str, root: Any) -> None:
        flags = flag_names.path_flags(key)
        file_id = f"kotlin:{key}"
        file_span = SourceSpan(key, 1, max(1, text.count("\n") + 1))
        self._nodes[file_id] = GraphNode(
            id=file_id, label=key, group=NodeKind.FILE, category=NodeKind.FILE,
            kind=NodeKind.FILE, language="kotlin", span=file_span,
            cost=cost_for_span(text, file_span), symbol_path=key, flags=flags,
            provenance="kotlin-core", metadata={"file_path": key},
        )
        package_match = re.search(r"^\s*package\s+([\w.]+)", text, re.M)
        package_name = package_match.group(1) if package_match else "<default>"
        package_id = f"kotlin-package:{package_name}"
        if package_id not in self._nodes:
            self._nodes[package_id] = GraphNode(
                id=package_id, label=package_name, group=NodeKind.MODULE, category=NodeKind.MODULE,
                kind=NodeKind.MODULE, language="kotlin", cost=cost_for_text(package_name),
                symbol_path=package_name, provenance="kotlin-core",
            )
        self._add_edge(package_id, file_id, RelationKind.CONTAINS, SourceSpan(key, 1, 1))
        self._imports[key] = [
            (match.group(1), text.count("\n", 0, match.start()) + 1)
            for match in re.finditer(r"^\s*import\s+([\w.*]+)", text, re.M)
        ]
        for declaration in ka.top_level_declarations(root):
            self._collect_declaration(key, source, declaration, None, [])
            name = ka.declared_name(declaration, source)
            if name:
                self._add_edge(file_id, self._symbol_id(key, name), RelationKind.DECLARES,
                               SourceSpan(key, ka.start_line(declaration), ka.start_line(declaration)))

    def _collect_declaration(
        self, key: str, source: bytes, node: Any, parent: Optional[str], scope: List[str]
    ) -> None:
        name = ka.declared_name(node, source)
        if not name:
            return
        if node.type == "function_declaration":
            kind = NodeKind.METHOD if parent else NodeKind.FUNCTION
        elif ka.is_interface(node):
            kind = NodeKind.INTERFACE
        else:
            kind = NodeKind.CLASS
        qualname = ".".join(scope + [name])
        symbol_id = self._symbol_id(key, qualname)
        symbol = _KotlinSymbol(symbol_id, name, kind, key, qualname, node, parent)
        if node.type == "function_declaration":
            receiver_type = ka.receiver_type_name(node, source)
            if receiver_type is not None:
                symbol.is_extension = True
                symbol.receiver_type = receiver_type
        self._symbols[symbol_id] = symbol
        self._by_name.setdefault(name, []).append(symbol_id)
        if parent:
            self._add_edge(parent, symbol_id, RelationKind.CONTAINS,
                           SourceSpan(key, ka.start_line(node), ka.start_line(node)))
        if node.type in ("class_declaration", "object_declaration"):
            constructor = ka.primary_constructor(node)
            if constructor is not None:
                constructor_text = ka.node_text(source, constructor)
                for parameter in ka.class_parameters(constructor, source):
                    field_name = parameter.get("name")
                    if field_name and re.search(rf"\b(?:val|var)\s+{re.escape(field_name)}\b", constructor_text):
                        self._collect_field(key, field_name, f"{qualname}.{field_name}", constructor, symbol_id)
            body = ka.class_body(node)
            if body is not None:
                for child in body.children:
                    if child.type in ("function_declaration", "class_declaration", "object_declaration"):
                        self._collect_declaration(key, source, child, symbol_id, scope + [name])
                    elif child.type == "property_declaration":
                        field_match = re.search(r"\b(?:val|var)\s+([A-Za-z_]\w*)", ka.node_text(source, child))
                        field_name = field_match.group(1) if field_match else None
                        if field_name:
                            self._collect_field(key, field_name, f"{qualname}.{field_name}", child, symbol_id)

    def _collect_field(self, key: str, name: str, qualname: str, node: Any, parent: str) -> None:
        field_id = self._symbol_id(key, qualname)
        if field_id in self._symbols:
            return
        field = _KotlinSymbol(field_id, name, NodeKind.FIELD, key, qualname, node, parent)
        self._symbols[field_id] = field
        self._by_name.setdefault(name, []).append(field_id)
        self._add_edge(parent, field_id, RelationKind.CONTAINS,
                       SourceSpan(key, ka.start_line(node), ka.start_line(node)))

    @staticmethod
    def _symbol_id(key: str, qualname: str) -> str:
        return f"kotlin:{key}#{qualname}"

    def _add_symbol_node(self, symbol: _KotlinSymbol) -> None:
        source, text, _root = self._files[symbol.file_key]
        span = SourceSpan(symbol.file_key, ka.start_line(symbol.node), ka.end_line(symbol.node))
        flags = flag_names.path_flags(symbol.file_key)
        if len(self._by_name.get(symbol.name, [])) > 1:
            flags.append(flag_names.AMBIGUOUS_NAME)
        self._nodes[symbol.id] = GraphNode(
            id=symbol.id, label=symbol.name, group=symbol.kind, category=symbol.kind,
            kind=symbol.kind, language="kotlin", span=span, cost=cost_for_span(text, span),
            signature=ka.node_text(source, symbol.node).split("{")[0].split("=")[0].strip(),
            symbol_path=f"{symbol.file_key}:{symbol.qualname}", flags=flags,
            provenance="kotlin-core", metadata={"name": symbol.name, "file_path": symbol.file_key,
                                                  "qualname": symbol.qualname},
        )

    def _add_import_edges(self, key: str) -> None:
        file_id = f"kotlin:{key}"
        for imported, line in self._imports[key]:
            simple = imported.rsplit(".", 1)[-1]
            if simple == "*":
                continue
            target, resolution, confidence, candidates = self._resolve(simple)
            if target:
                self._add_edge(file_id, target, RelationKind.IMPORTS_SYMBOL, SourceSpan(key, line, line),
                               confidence, resolution, candidates)
                target_file = f"kotlin:{self._symbols[target].file_key}"
                self._add_edge(file_id, target_file, RelationKind.IMPORTS, SourceSpan(key, line, line),
                               confidence, resolution, candidates)

    def _add_symbol_edges(self, symbol: _KotlinSymbol) -> None:
        source, _text, _root = self._files[symbol.file_key]
        node_text = ka.node_text(source, symbol.node)
        header = node_text.split("{", 1)[0]
        if symbol.kind in (NodeKind.CLASS, NodeKind.INTERFACE):
            for name in ka.supertype_names(symbol.node, source):
                target, resolution, confidence, candidates = self._resolve(name.rsplit(".", 1)[-1])
                if target:
                    relation = RelationKind.IMPLEMENTS if symbol.kind == NodeKind.CLASS and self._symbols[target].kind == NodeKind.INTERFACE else RelationKind.INHERITS
                    self._add_edge(symbol.id, target, relation, SourceSpan(symbol.file_key, ka.start_line(symbol.node), ka.start_line(symbol.node)), confidence, resolution, candidates)
        if symbol.is_extension:
            target, resolution, confidence, candidates = self._resolve(symbol.receiver_type)
            if target:
                self._add_edge(symbol.id, target, RelationKind.TYPE_USES,
                               SourceSpan(symbol.file_key, ka.start_line(symbol.node), ka.start_line(symbol.node)), confidence, resolution, candidates)
        for name, targets in self._by_name.items():
            if name == symbol.name or not re.search(rf"\b{re.escape(name)}\b", header):
                continue
            target, resolution, confidence, candidates = self._resolve(name)
            if target and self._symbols[target].kind in (NodeKind.CLASS, NodeKind.INTERFACE):
                self._add_edge(symbol.id, target, RelationKind.TYPE_USES,
                               SourceSpan(symbol.file_key, ka.start_line(symbol.node), ka.start_line(symbol.node)), confidence, resolution, candidates)
        unresolved: List[Dict[str, Any]] = []
        for call in ka.call_expressions(symbol.node, source):
            name = call["name"]
            target, resolution, confidence, candidates = self._resolve(name)
            line = self._line_of(node_text, name, ka.start_line(symbol.node))
            if target is None:
                unresolved.append({
                    "name": name, "resolution": str(Resolution.UNRESOLVED),
                    "confidence": str(Confidence.DYNAMIC_REQUIRED),
                    "evidence": {"file_path": symbol.file_key, "start_line": line, "end_line": line},
                })
                continue
            relation = RelationKind.INSTANTIATES if self._symbols[target].kind == NodeKind.CLASS else RelationKind.CALLS
            self._add_edge(symbol.id, target, relation, SourceSpan(symbol.file_key, line, line), confidence, resolution, candidates)
        if unresolved:
            self._nodes[symbol.id].metadata["unresolved_calls"] = dict(Counter(item["name"] for item in unresolved))
            self._nodes[symbol.id].metadata["unresolved_references"] = unresolved[:20]
        for name in self._by_name:
            if name == symbol.name:
                continue
            for match in re.finditer(rf"\b{re.escape(name)}\b", node_text):
                prefix = node_text[max(0, match.start() - 12):match.start()]
                if re.search(r"(class|fun|val|var)\s+$", prefix):
                    continue
                target, resolution, confidence, candidates = self._resolve(name)
                if target is None:
                    continue
                tail = node_text[match.end():match.end() + 8]
                relation = RelationKind.WRITES if re.match(r"\s*(?:[+\-*/]?=|\+\+|--)", tail) else RelationKind.READS
                line = node_text.count("\n", 0, match.start()) + ka.start_line(symbol.node)
                self._add_edge(symbol.id, target, relation, SourceSpan(symbol.file_key, line, line), confidence, resolution, candidates)

    def _resolve(self, name: str):
        candidates = self._by_name.get(name, [])
        if len(candidates) == 1:
            return candidates[0], Resolution.UNIQUE_NAME, Confidence.STATIC_INFERRED, []
        if len(candidates) > 1:
            return candidates[0], Resolution.AMBIGUOUS, Confidence.STATIC_INFERRED, candidates[1:]
        return None, Resolution.UNRESOLVED, Confidence.DYNAMIC_REQUIRED, []

    def _add_edge(
        self, source: str, target: str, relation: str, evidence: SourceSpan,
        confidence: str = Confidence.STATIC_CERTAIN, resolution: str = Resolution.EXACT,
        candidates: Optional[List[str]] = None,
    ) -> None:
        if source == target:
            return
        key = (source, target, relation)
        if key in self._edges:
            self._edges[key].weight += 1.0
            return
        self._edges[key] = GraphEdge(
            from_id=source, to_id=target, relation=relation, evidence=evidence,
            confidence=confidence, resolution=resolution, candidates=candidates or [],
        )

    @staticmethod
    def _line_of(text: str, name: str, base: int) -> int:
        match = re.search(rf"\b{re.escape(name)}\b", text)
        return base + text.count("\n", 0, match.start()) if match else base

    @staticmethod
    def _symbol_collection(nodes: Sequence[GraphNode]) -> ReportCollection:
        return ReportCollection(
            key="symbols", label="Symbols", view="table",
            columns=[ColumnSpec("symbol_path", "Symbol", "mono"), ColumnSpec("kind", "Kind")],
            rows=[{"id": node.id, "symbol_path": node.symbol_path or node.label, "kind": node.kind} for node in nodes],
        )
