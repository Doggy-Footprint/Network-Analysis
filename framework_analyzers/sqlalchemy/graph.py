from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set

if TYPE_CHECKING:
    from repository.models import RepositorySnapshot

from analysis import GraphAnalysisConfig, GraphAnalyzer
from framework_analyzers.migration_tables import match_migration_tables
from language_analyzers.core.annotate import annotate_nodes
from language_analyzers.core.enrichment import enrich_repository
from language_analyzers.core.graph_models import Confidence, RelationKind, Resolution, SourceSpan
from language_analyzers.core.report_schema import ColumnSpec, ReportCollection
from language_analyzers.python.graph import PythonGraphAnalyzer
from language_analyzers.python.source import PythonSourceAnalyzer
from language_analyzers.python.symbols import module_id, symbol_id

from .models import GraphEdge, GraphNode, SQLAlchemyProjectArchitecture


class SQLAlchemyGraphBuilder:
    COLORS = {
        "sqlalchemy_model": {
            "background": "#86198F", "border": "#E879F9",
            "highlight": {"background": "#A21CAF", "border": "#F5D0FE"},
            "hover": {"background": "#A21CAF", "border": "#F0ABFC"},
        },
        "alembic_migration": {
            "background": "#334155", "border": "#94A3B8",
            "highlight": {"background": "#475569", "border": "#E2E8F0"},
            "hover": {"background": "#475569", "border": "#CBD5E1"},
        },
    }

    PROVENANCE = "sqlalchemy"

    def __init__(
        self,
        include_models: bool = True,
        include_language_graph: bool = True,
        emit_language_graph: bool = True,
        snapshot: Optional[RepositorySnapshot] = None,
        analysis_config: Optional[GraphAnalysisConfig] = None,
    ):
        self.include_models = include_models
        self.include_language_graph = include_language_graph
        self.emit_language_graph = emit_language_graph
        self.snapshot = snapshot
        self.analysis_config = analysis_config

    def build_graph(self, arch: SQLAlchemyProjectArchitecture) -> SQLAlchemyProjectArchitecture:
        self._validate_snapshot(arch.project_path)
        nodes: List[GraphNode] = []

        if self.include_models:
            for model in arch.models:
                nodes.append(GraphNode(
                    id=model.id,
                    label=model.name,
                    display_label=f"📦 {model.name}\n({model.table_name})",
                    group="sqlalchemy_model",
                    category="sqlalchemy_model",
                    title=f"<b>SQLAlchemy Model: {model.name}</b><br>Table: {model.table_name}<br>Module: {model.module}<br>File: {model.file_path}:{model.line_number}",
                    shape="box",
                    size=20,
                    color=self.COLORS["sqlalchemy_model"],
                    metadata={
                        "type": "sqlalchemy_model",
                        "name": model.name,
                        "module": model.module,
                        "table_name": model.table_name,
                        "file_path": model.file_path,
                        "line_number": model.line_number,
                        "end_line_number": model.end_line_number,
                    },
                ))
        for migration in arch.migrations:
            nodes.append(GraphNode(
                id=migration.id,
                label=migration.file_path,
                display_label=f"🧱 {Path(migration.file_path).name}",
                group="alembic_migration",
                category="alembic_migration",
                title=f"<b>Alembic Migration</b><br>File: {migration.file_path}",
                shape="box",
                size=22,
                color=self.COLORS["alembic_migration"],
                flags=["migration"],
                metadata={
                    "type": "alembic_migration",
                    "module": migration.module,
                    "file_path": migration.file_path,
                    "line_number": migration.line_number,
                    "end_line_number": migration.end_line_number,
                },
            ))
        annotate_nodes(nodes, arch.project_path, self.PROVENANCE, "python", snapshot=self.snapshot)

        node_ids: Set[str] = {node.id for node in nodes}
        edges: List[GraphEdge] = []

        language_nodes, language_edges = [], []
        if self.include_language_graph:
            language_nodes, language_edges = self._language_graph(arch)
            language_ids = {node.id for node in language_nodes}
            edges.extend(self._implementation_edges(arch, node_ids, language_ids))
            if self.emit_language_graph:
                nodes.extend(node for node in language_nodes if node.id not in node_ids)
                edges.extend(language_edges)

        models_by_table: Dict[str, List[str]] = {}
        if self.include_models:
            for model in arch.models:
                models_by_table.setdefault(model.table_name, []).append(model.id)
        spans = {node.id: node.span for node in nodes if node.span is not None}
        migrate_edges, matching_stats = match_migration_tables(
            models_by_table,
            [(m.id, m.table_refs, spans[m.id]) for m in arch.migrations],
        )
        edges.extend(migrate_edges)

        arch.nodes = nodes
        arch.edges = edges
        if self.include_language_graph and self.emit_language_graph:
            # Another analyzer owning the python-core graph also enriches it; repeating
            # enrichment here would emit its configuration nodes a second time.
            if self.snapshot is None:
                enrich_repository(arch)
            else:
                contents = self.snapshot.content_map()
                enrich_repository(arch, file_inventory=tuple(contents),
                                  file_reader=lambda path: contents[path.relative_to(Path(arch.project_path)).as_posix()])
        arch.stats = {
            "total_models": len(arch.models) if self.include_models else 0,
            "total_migrations": len(arch.migrations),
            "nodes_by_kind": dict(Counter(node.kind or node.category for node in arch.nodes)),
            "edges_by_relation": dict(Counter(edge.relation for edge in arch.edges)),
            "edges_by_confidence": dict(Counter(str(edge.confidence) for edge in arch.edges)),
            "migration_matching": matching_stats,
        }
        arch.stats["analysis"] = GraphAnalyzer(self.analysis_config).analyze(
            arch.nodes,
            arch.edges,
            project_path=arch.project_path,
        )
        arch.report_collections = self._build_report_collections(arch)
        return arch

    def _validate_snapshot(self, project_path: str) -> None:
        if self.snapshot is None:
            return
        supplied = Path(project_path)
        snapshot_root = Path(self.snapshot.root)
        if not supplied.is_absolute() or not snapshot_root.is_absolute() or supplied != snapshot_root:
            raise ValueError("project path and snapshot root must be absolute and match")

    def _language_graph(self, arch: SQLAlchemyProjectArchitecture):
        analyzer = PythonGraphAnalyzer(arch.project_path, self.snapshot)
        return analyzer.build(PythonSourceAnalyzer(arch.project_path, self.snapshot).analyze())

    def _implementation_edges(
        self, arch: SQLAlchemyProjectArchitecture, node_ids: Set[str], language_ids: Set[str]
    ) -> List[GraphEdge]:
        pairs = []
        if self.include_models:
            pairs += [(m.id, symbol_id(m.module, m.qualname), m.file_path, m.line_number) for m in arch.models]
        pairs += [(m.id, module_id(m.module), m.file_path, m.line_number) for m in arch.migrations]
        edges: List[GraphEdge] = []
        for source_id, target_id, file_path, line in pairs:
            if source_id not in node_ids or target_id not in language_ids:
                continue
            edges.append(GraphEdge(
                from_id=source_id,
                to_id=target_id,
                relation=RelationKind.IMPLEMENTED_BY,
                label="implemented by",
                dashes=True,
                color="#94A3B8",
                confidence=Confidence.FRAMEWORK_INFERRED,
                resolution=Resolution.EXACT,
                evidence=SourceSpan(file_path, line, line),
                metadata={"framework_rule": {"id": "sqlalchemy.implemented_by", "specificity": "unique"}},
            ))
        return edges

    @staticmethod
    def _build_report_collections(arch: SQLAlchemyProjectArchitecture) -> List[ReportCollection]:
        return [
            ReportCollection(
                key="sqlalchemy_models",
                label="SQLAlchemy Models",
                view="grid",
                node_category="sqlalchemy_model",
                columns=[
                    ColumnSpec("table_name", "Table", "mono"),
                    ColumnSpec("module", "Module", "mono"),
                ],
                rows=[
                    {"id": m.id, "name": m.name, "table_name": m.table_name,
                     "module": f"{m.module}:{m.line_number}"}
                    for m in arch.models
                ],
            ),
            ReportCollection(
                key="alembic_migrations",
                label="Alembic Migrations",
                view="grid",
                node_category="alembic_migration",
                columns=[
                    ColumnSpec("tables", "Tables", "list"),
                ],
                rows=[
                    {"id": m.id, "name": m.file_path,
                     "tables": sorted({ref for ref in m.table_refs if ref is not None})}
                    for m in arch.migrations
                ],
            ),
        ]

    def generate_mermaid(self, arch: SQLAlchemyProjectArchitecture) -> str:
        lines = ["graph TD", "  %% SQLAlchemy/Alembic Architecture Diagram"]
        framework_ids = {
            node.id for node in arch.nodes
            if (node.provenance or self.PROVENANCE) == self.PROVENANCE
        }
        for edge in arch.edges:
            if edge.from_id not in framework_ids or edge.to_id not in framework_ids:
                continue
            lbl = f"|{edge.label}|" if edge.label else ""
            arrow = "-.->" if edge.dashes else "-->"
            lines.append(f"  {edge.from_id} {arrow}{lbl} {edge.to_id}")
        return "\n".join(lines)
