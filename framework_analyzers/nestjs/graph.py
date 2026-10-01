from __future__ import annotations

from collections import Counter
from pathlib import Path

from analysis import GraphAnalyzer
from language_analyzers.core.cost import cost_for_span
from language_analyzers.core.graph_models import Confidence, GraphEdge, GraphNode, Resolution
from language_analyzers.core.report_schema import ColumnSpec, ReportCollection
from language_analyzers.typescript import TypeScriptAnalyzer


class NestJSGraphBuilder:
    def __init__(self, include_dependencies=True, include_language_graph=True, emit_language_graph=True,
                 snapshot=None, analysis_config=None):
        self.include_dependencies = include_dependencies
        self.include_language_graph = include_language_graph
        self.emit_language_graph = emit_language_graph
        self.snapshot = snapshot
        self.analysis_config = analysis_config

    def build_graph(self, arch):
        if self.snapshot is not None:
            root = Path(arch.project_path)
            snapshot_root = Path(self.snapshot.root)
            if not root.is_absolute() or not snapshot_root.is_absolute() or root != snapshot_root:
                raise ValueError("project path and snapshot root must be absolute and match")
        declarations = [d for d in arch.declarations if self.include_dependencies or d.kind != "provider"]
        nodes = []
        arch.report_collections = []
        for d in declarations:
            metadata = dict(d.metadata)
            metadata.update({"type": d.kind, "name": d.name, "file_path": d.file_path,
                             "line_number": d.span.start_line, "end_line_number": d.span.end_line})
            nodes.append(GraphNode(
                id=d.id, label=d.name, display_label=d.name, group=d.kind, category=d.kind,
                kind=d.kind, language="typescript", provenance="nestjs", span=d.span,
                cost=cost_for_span(d.source, d.span), symbol_path=f"{d.file_path}#{d.name}",
                metadata=metadata,
            ))
        node_ids = {n.id for n in nodes}
        edges = []
        for ref in arch.references:
            if ref.from_id in node_ids and ref.to_id in node_ids:
                edges.append(self._edge(ref.from_id, ref.to_id, ref.relation, ref.evidence))
        arch.http_calls = []
        arch.pending_implementation_edges = []
        if self.include_language_graph:
            language = TypeScriptAnalyzer(arch.project_path, snapshot=self.snapshot).analyze()
            language_ids = {node.id for node in language.nodes}
            for d in declarations:
                if d.kind == "application":
                    function = d.metadata.get("bootstrap_function")
                    symbol_id = f"ts:{d.file_path}#{function}" if function else None
                else:
                    name = d.name.split(".")[0] if d.kind == "endpoint" else d.name
                    symbol_id = f"ts:{d.file_path}#{name}"
                if d.kind == "endpoint":
                    method = d.metadata.get("function_name")
                    symbol_id = f"ts:{d.file_path}#{name}.{method}"
                if symbol_id in language_ids:
                    link = self._edge(d.id, symbol_id, "IMPLEMENTED_BY", d.span)
                    if self.emit_language_graph:
                        edges.append(link)
                    else:
                        arch.pending_implementation_edges.append(link)
            if self.emit_language_graph:
                nodes.extend(language.nodes)
                edges.extend(language.edges)
                arch.http_calls = language.http_calls
                arch.report_collections = list(language.report_collections)
        ids = {n.id for n in nodes}
        edges = [e for e in edges if e.from_id in ids and e.to_id in ids]
        nodes.sort(key=lambda n: n.id)
        edges.sort(key=lambda e: (e.from_id, e.to_id, e.relation, e.evidence.file_path if e.evidence else "", e.evidence.start_line if e.evidence else 0))
        arch.nodes = nodes
        arch.edges = edges
        arch.report_collections.extend(self._collections(arch, declarations))
        counts = Counter(d.kind for d in declarations)
        arch.stats = {
            "nestjs": {**{kind: counts.get(kind, 0) for kind in ("application", "module", "controller", "provider", "endpoint")},
                       "diagnostics": [d.as_dict() for d in arch.diagnostics]},
            "nodes_by_kind": dict(Counter(node.kind or node.category for node in nodes)),
            "edges_by_relation": dict(Counter(edge.relation for edge in edges)),
            "edges_by_confidence": dict(Counter(str(edge.confidence) for edge in edges)),
        }
        arch.stats["analysis"] = GraphAnalyzer(self.analysis_config).analyze(nodes, edges, project_path=arch.project_path)
        return arch

    @staticmethod
    def _edge(from_id, to_id, relation, evidence):
        return GraphEdge(from_id, to_id, relation, confidence=Confidence.FRAMEWORK_INFERRED,
                         resolution=Resolution.EXACT, evidence=evidence,
                         metadata={"framework_rule": {"id": f"nestjs.{relation.lower()}", "specificity": "unique"}})

    @staticmethod
    def _collections(arch, declarations):
        result = []
        for kind, label in (("module", "Modules"), ("controller", "Controllers"),
                            ("provider", "Providers"), ("endpoint", "Endpoints")):
            rows = [{"id": d.id, "name": d.name, "file_path": d.file_path,
                     "line_number": d.span.start_line, **{k: v for k, v in d.metadata.items() if k != "decorator"}}
                    for d in declarations if d.kind == kind]
            result.append(ReportCollection(key=f"nestjs_{kind}s", label=label, view="table",
                                           node_category=kind,
                                           columns=[ColumnSpec("name", "Name"), ColumnSpec("file_path", "File", "mono"),
                                                    ColumnSpec("line_number", "Line")], rows=rows))
        result.append(ReportCollection(key="nestjs_diagnostics", label="Diagnostics", view="table",
                                       columns=[ColumnSpec("code", "Code"), ColumnSpec("file_path", "File", "mono"),
                                                ColumnSpec("line_number", "Line"), ColumnSpec("expression", "Expression", "mono"),
                                                ColumnSpec("reason", "Reason")],
                                       rows=[{**d.as_dict(), "file_path": d.span.file_path, "line_number": d.span.start_line}
                                             for d in arch.diagnostics]))
        return result

    @staticmethod
    def generate_mermaid(arch):
        framework = [node for node in arch.nodes if node.provenance == "nestjs"]
        ids = {node.id for node in framework}
        aliases = {node.id: f"n{i}" for i, node in enumerate(framework)}
        lines = ["graph TD"]
        for node in framework:
            lines.append(f'  {aliases[node.id]}["{node.label.replace(chr(34), chr(39))}"]')
        for edge in arch.edges:
            if edge.from_id in ids and edge.to_id in ids:
                lines.append(f"  {aliases[edge.from_id]} -->|{edge.relation}| {aliases[edge.to_id]}")
        return "\n".join(lines)
