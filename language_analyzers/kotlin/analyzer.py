from __future__ import annotations

import re
import bisect
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from analysis.candidate_projection import candidate_relation_key, candidate_targets, has_external_candidate
from language_analyzers.core.analysis_coverage import CoverageRecorder, attach_coverage

if TYPE_CHECKING:
    from repository.models import RepositorySnapshot

from language_analyzers.core import flags as flag_names
from language_analyzers.core.cost import cost_for_span, cost_for_text, module_end_line
from language_analyzers.core.positions import NamePositions
from language_analyzers.core.enrichment import enrich_repository
from language_analyzers.core.external_imports import kotlin_is_internal, normalize_external_imports
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
from repository.models import SourceText


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
            contents = self.snapshot.source_map
            enrich_repository(architecture, file_inventory=tuple(contents),
                              file_reader=lambda path: contents[path.relative_to(self.project_path).as_posix()])
        architecture.stats = {
            "total_files": len(self._files),
            "total_symbols": len(self._symbols),
            "nodes_by_kind": dict(Counter(node.kind for node in architecture.nodes)),
            "edges_by_relation": dict(Counter(edge.relation for edge in architecture.edges)),
            "edges_by_confidence": dict(Counter(str(edge.confidence) for edge in architecture.edges)),
        }
        attach_coverage(architecture, self.snapshot, self.analysis_coverage)
        architecture.report_collections = [self._symbol_collection(architecture.nodes)]
        return architecture

    def build(self) -> tuple[List[GraphNode], List[GraphEdge]]:
        self._files: Dict[str, Tuple[bytes, str, Any]] = {}
        self._symbols: Dict[str, _KotlinSymbol] = {}
        self._by_name: Dict[str, List[str]] = {}
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: Dict[Tuple[Any, ...], GraphEdge] = {}
        self._imports: Dict[str, List[Tuple[str, int]]] = {}
        self._import_statements: Dict[str, List[Tuple[str, int]]] = {}
        self._file_package: Dict[str, str] = {}
        self._exact_imports: Dict[str, Dict[str, str]] = {}
        self._positions = {}
        self._byte_starts = {}
        self._valid_utf8 = {}
        self._symbol_offsets = {}
        self._fqn_index: Optional[Dict[str, List[str]]] = None
        self._member_nodes: Dict[str, List[Any]] = {}
        self._project_imports: Dict[str, Set[str]] = {}

        paths = self._discover_files()
        recorder = CoverageRecorder(self.snapshot, "kotlin-core", paths, {".kt"})
        for path in paths:
            try:
                if self.snapshot is None:
                    source, root = self._parse_cache.read_and_parse(path)
                else:
                    source = self.snapshot.source_map[path.relative_to(self.project_path).as_posix()].encode("utf-8")
                    source, root = self._parse_cache.parse_snapshot(path, source)
            except OSError as exc:
                recorder.record(path.relative_to(self.project_path).as_posix(), "failed", [{"code": "unreadable", "message": str(exc)}])
                continue
            key = path.relative_to(self.project_path).as_posix()
            recorder.parsed(key, root.has_error)
            text = self.snapshot.source_map[key] if self.snapshot is not None else SourceText(source.decode("utf-8", "replace"))
            self._files[key] = (source, text, root)
            self._positions[key] = NamePositions(text)
            byte_starts = [0]
            for character in text:
                byte_starts.append(byte_starts[-1] + len(character.encode("utf-8")))
            self._byte_starts[key] = byte_starts
            self._valid_utf8[key] = source == text.encode("utf-8")
            self._collect_file(key, source, text, root)

        self._record_external_imports()
        self._name_order = {name: index for index, name in enumerate(self._by_name)}
        for symbol in self._symbols.values():
            self._add_symbol_node(symbol)
        for key in self._files:
            self._add_import_edges(key)
        for symbol in self._symbols.values():
            self._add_symbol_edges(symbol)

        self.analysis_coverage = recorder.coverage()
        return list(self._nodes.values()), list(self._edges.values())

    def _record_external_imports(self) -> None:
        packages = tuple(sorted(node.symbol_path for node_id, node in self._nodes.items()
                                if node_id.startswith("kotlin-package:") and node.symbol_path != "<default>"))
        for key, imports in self._import_statements.items():
            self._project_imports[key] = {raw.rsplit(".", 1)[-1] for raw, _line in imports if not raw.endswith("*") and kotlin_is_internal(raw, packages)}
            external = normalize_external_imports(
                {"name": name, "line": line} for name, line in ((raw[:-2] if raw.endswith(".*") else raw, line) for raw, line in imports)
                if name and not kotlin_is_internal(name, packages))
            if external:
                self._nodes[f"kotlin:{key}"].metadata["external_imports"] = external

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
        file_span = SourceSpan(key, 1, module_end_line(text))
        self._nodes[file_id] = GraphNode(
            id=file_id, label=key, group=NodeKind.FILE, category=NodeKind.FILE,
            kind=NodeKind.FILE, language="kotlin", span=file_span,
            cost=cost_for_span(text, file_span), symbol_path=key, flags=flags,
            provenance="kotlin-core", metadata={"file_path": key},
        )
        package_match = re.search(r"^\s*package\s+([\w.]+)", text, re.M)
        package_name = package_match.group(1) if package_match else "<default>"
        if package_match:
            self._file_package[key] = package_name
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
            for match in re.finditer(r"^[^\S\n]*import\s+([\w.*]+)", text, re.M)
        ]
        self._import_statements[key] = [
            (match.group(1), text.count("\n", 0, match.start()) + 1)
            for match in re.finditer(r"^[^\S\n]*import\s+([\w.*]+)", text, re.M)
        ]
        for declaration in root.children:
            if declaration.type not in ("function_declaration", "class_declaration", "object_declaration") and ka.recovered_object_members(declaration) is None:
                continue
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
        recovered = ka.recovered_object_members(node)
        if node.type in ("class_declaration", "object_declaration") or recovered is not None:
            constructor = ka.primary_constructor(node)
            if constructor is not None:
                constructor_text = ka.node_text(source, constructor)
                for parameter, parameter_node in zip(ka.class_parameters(constructor, source), ka.class_parameter_nodes(constructor)):
                    field_name = parameter.get("name")
                    if field_name and re.search(rf"\b(?:val|var)\s+{re.escape(field_name)}\b", constructor_text):
                        self._collect_field(key, field_name, f"{qualname}.{field_name}", parameter_node, symbol_id)
            for child in (recovered if recovered is not None else ka.body_members(node)):
                if child.type != "property_declaration":
                    if ka.declared_name(child, source):
                        self._member_nodes.setdefault(symbol_id, []).append(child)
                    self._collect_declaration(key, source, child, symbol_id, scope + [name])
                else:
                    field_match = re.search(r"\b(?:val|var)\s+([A-Za-z_]\w*)", ka.node_text(source, child))
                    field_name = field_match.group(1) if field_match else None
                    if field_name and self._collect_field(key, field_name, f"{qualname}.{field_name}", child, symbol_id):
                        self._member_nodes.setdefault(symbol_id, []).append(child)

    def _collect_field(self, key: str, name: str, qualname: str, node: Any, parent: str) -> bool:
        field_id = self._symbol_id(key, qualname)
        if field_id in self._symbols:
            return False
        field = _KotlinSymbol(field_id, name, NodeKind.FIELD, key, qualname, node, parent)
        self._symbols[field_id] = field
        self._by_name.setdefault(name, []).append(field_id)
        self._add_edge(parent, field_id, RelationKind.CONTAINS,
                       SourceSpan(key, ka.start_line(node), ka.start_line(node)))
        return True

    @staticmethod
    def _symbol_id(key: str, qualname: str) -> str:
        return f"kotlin:{key}#{qualname}"

    def _add_symbol_node(self, symbol: _KotlinSymbol) -> None:
        source, text, _root = self._files[symbol.file_key]
        span = SourceSpan(symbol.file_key, ka.start_line(symbol.node), ka.end_line(symbol.node))
        flags = flag_names.path_flags(symbol.file_key)
        self._nodes[symbol.id] = GraphNode(
            id=symbol.id, label=symbol.name, group=symbol.kind, category=symbol.kind,
            kind=symbol.kind, language="kotlin", span=span, cost=cost_for_span(text, span),
            signature=f"object {symbol.name}" if symbol.node.type == "infix_expression" else ka.node_text(source, symbol.node).split("{")[0].split("=")[0].strip(),
            symbol_path=f"{symbol.file_key}:{symbol.qualname}", flags=flags,
            provenance="kotlin-core", metadata={"name": symbol.name, "file_path": symbol.file_key,
                                                  "qualname": symbol.qualname},
        )

    def _symbols_by_fqn(self) -> Dict[str, List[str]]:
        if self._fqn_index is None:
            index: Dict[str, List[str]] = {}
            for symbol in self._symbols.values():
                package = self._file_package.get(symbol.file_key)
                fqn = f"{package}.{symbol.qualname}" if package else symbol.qualname
                index.setdefault(fqn, []).append(symbol.id)
            self._fqn_index = {fqn: sorted(ids) for fqn, ids in index.items()}
        return self._fqn_index

    def _add_import_edges(self, key: str) -> None:
        file_id = f"kotlin:{key}"
        for imported, line in self._imports[key]:
            simple = imported.rsplit(".", 1)[-1]
            if simple == "*":
                continue
            matches = self._symbols_by_fqn().get(imported, [])
            if len(matches) == 1:
                self._exact_imports.setdefault(key, {})[simple] = matches[0]
                target, resolution, confidence, candidates = (
                    matches[0], Resolution.EXACT, Confidence.STATIC_CERTAIN, [])
            elif matches:
                target, resolution, confidence, candidates = (
                    matches[0], Resolution.AMBIGUOUS, Confidence.STATIC_INFERRED, matches[1:])
            else:
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
        positions = self._positions[symbol.file_key]
        if symbol.id not in self._symbol_offsets:
            offset = bisect.bisect_left(self._byte_starts[symbol.file_key], symbol.node.start_byte)
            if not self._valid_utf8[symbol.file_key]:
                offset = len(source[:symbol.node.start_byte].decode("utf-8", "replace"))
            self._symbol_offsets[symbol.id] = offset
        offset = self._symbol_offsets[symbol.id]
        end_offset = offset + len(node_text)
        members = self._member_nodes.get(symbol.id, ()) if symbol.kind in (NodeKind.CLASS, NodeKind.INTERFACE) else ()
        excluded = sorted((self._char_offset(symbol.file_key, member.start_byte), self._char_offset(symbol.file_key, member.end_byte)) for member in members)
        starts = [start for start, _end in excluded]
        def in_member(position):
            index = bisect.bisect_right(starts, position) - 1
            return index >= 0 and position < excluded[index][1]
        def occurrences(name, header_only=False):
            found = positions.matches(name, offset, offset + len(header) if header_only else end_offset)
            return [item for item in found if not in_member(item[0])] if excluded and not header_only else found
        if symbol.kind in (NodeKind.CLASS, NodeKind.INTERFACE):
            for name in ka.supertype_names(symbol.node, source):
                target, resolution, confidence, candidates = self._resolve(name.rsplit(".", 1)[-1], symbol.file_key)
                if target:
                    relation = RelationKind.IMPLEMENTS if symbol.kind == NodeKind.CLASS and self._symbols[target].kind == NodeKind.INTERFACE else RelationKind.INHERITS
                    self._add_edge(symbol.id, target, relation, SourceSpan(symbol.file_key, ka.start_line(symbol.node), ka.start_line(symbol.node)), confidence, resolution, candidates)
        if symbol.is_extension:
            target, resolution, confidence, candidates = self._resolve(symbol.receiver_type, symbol.file_key)
            if target:
                self._add_edge(symbol.id, target, RelationKind.TYPE_USES,
                               SourceSpan(symbol.file_key, ka.start_line(symbol.node), ka.start_line(symbol.node)), confidence, resolution, candidates)
        for name in positions.candidate_names(self._name_order, offset, offset + len(header)):
            if name == symbol.name or not occurrences(name, header_only=True):
                continue
            target, resolution, confidence, candidates = self._resolve(name, symbol.file_key)
            if target and self._symbols[target].kind in (NodeKind.CLASS, NodeKind.INTERFACE):
                self._add_edge(symbol.id, target, RelationKind.TYPE_USES,
                               SourceSpan(symbol.file_key, ka.start_line(symbol.node), ka.start_line(symbol.node)), confidence, resolution, candidates)
        for flag in sorted(ka.dynamic_call_flags(symbol.node, source, members)):
            if flag not in self._nodes[symbol.id].flags:
                self._nodes[symbol.id].flags.append(flag)
        unresolved: List[Dict[str, Any]] = []
        external: Counter = Counter()
        for call in ka.call_expressions(symbol.node, source, members):
            name = call["name"]
            target, resolution, confidence, candidates = self._resolve(name, symbol.file_key)
            matches = occurrences(name)
            line = ka.start_line(symbol.node) + positions.line(matches[0][0]) - positions.line(offset) if matches else ka.start_line(symbol.node)
            if target is None and name not in self._project_imports.get(symbol.file_key, ()):
                external[name] += 1
                continue
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
            self._nodes[symbol.id].metadata["unresolved_reference_total"] = len(unresolved)
        if external:
            self._nodes[symbol.id].metadata["external_call_count"] = sum(external.values())
            self._nodes[symbol.id].metadata["external_calls"] = dict(external.most_common(20))
        for name in positions.candidate_names(self._name_order, offset, end_offset):
            if name == symbol.name:
                continue
            for absolute_start, absolute_end in occurrences(name):
                match_start, match_end = absolute_start - offset, absolute_end - offset
                prefix = node_text[max(0, match_start - 12):match_start]
                if re.search(r"(class|fun|val|var)\s+$", prefix):
                    continue
                target, resolution, confidence, candidates = self._resolve(name, symbol.file_key)
                if target is None:
                    continue
                tail = node_text[match_end:match_end + 8]
                relation = RelationKind.WRITES if re.match(r"\s*(?:[+\-*/]?=|\+\+|--)", tail) else RelationKind.READS
                line = positions.line(absolute_start) - positions.line(offset) + ka.start_line(symbol.node)
                self._add_edge(symbol.id, target, relation, SourceSpan(symbol.file_key, line, line), confidence, resolution, candidates)

    def _char_offset(self, key: str, byte: int) -> int:
        if self._valid_utf8[key]:
            return bisect.bisect_left(self._byte_starts[key], byte)
        return len(self._files[key][0][:byte].decode("utf-8", "replace"))

    def _resolve(self, name: str, file_key: Optional[str] = None):
        imported = self._exact_imports.get(file_key, {}).get(name) if file_key else None
        if imported:
            return imported, Resolution.EXACT, Confidence.STATIC_CERTAIN, []
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
        if not has_external_candidate(source, target, resolution, candidates):
            return
        key = candidate_relation_key(source, target, relation, resolution, candidates)
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
