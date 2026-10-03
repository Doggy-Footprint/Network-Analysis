"""
Data models representing the SQLAlchemy/SQLModel models and Alembic revisions of a Python project.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from language_analyzers.core.graph_models import GraphEdge, GraphNode
from language_analyzers.core.report_schema import ColumnSpec, ReportCollection

__all__ = [
    "SQLAlchemyModelInfo",
    "AlembicMigrationInfo",
    "GraphNode",
    "GraphEdge",
    "ColumnSpec",
    "ReportCollection",
    "SQLAlchemyProjectArchitecture",
]


@dataclass
class SQLAlchemyModelInfo:
    id: str
    name: str
    qualname: str
    module: str
    file_path: str
    table_name: str
    line_number: int = 0
    end_line_number: int = 0


@dataclass
class AlembicMigrationInfo:
    id: str
    module: str
    file_path: str
    line_number: int = 0
    end_line_number: int = 0
    table_refs: List[Optional[str]] = field(default_factory=list)  # None marks a non-literal table argument


@dataclass
class SQLAlchemyProjectArchitecture:
    project_name: str
    project_path: str
    models: List[SQLAlchemyModelInfo] = field(default_factory=list)
    migrations: List[AlembicMigrationInfo] = field(default_factory=list)
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    report_collections: List[ReportCollection] = field(default_factory=list)
