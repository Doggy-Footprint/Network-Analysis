"""
Data models representing the extracted architecture of a FastAPI project.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from language_analyzers.core.graph_models import GraphEdge, GraphNode
from language_analyzers.core.report_schema import ColumnSpec, ReportCollection

__all__ = [
    "ParameterInfo",
    "EndpointInfo",
    "RouterInclusion",
    "RouterInfo",
    "AppInfo",
    "DependencyInfo",
    "SchemaFieldInfo",
    "SchemaInfo",
    "GraphNode",
    "GraphEdge",
    "ColumnSpec",
    "ReportCollection",
    "ProjectArchitecture",
]


@dataclass
class ParameterInfo:
    name: str
    type_annotation: Optional[str] = None
    default_value: Optional[str] = None
    kind: str = "query"  # query, path, body, header, cookie, dependency, security
    dependency_call: Optional[str] = None


@dataclass
class EndpointInfo:
    id: str
    http_method: str  # GET, POST, PUT, DELETE, PATCH, etc.
    path: str  # Path declared on decorator (e.g. "/items/{id}")
    full_path: str = ""  # Full resolved path with router prefixes
    function_name: str = ""
    module: str = ""
    file_path: str = ""
    line_number: int = 0
    end_line_number: int = 0
    docstring: Optional[str] = None
    summary: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    response_model: Optional[str] = None
    status_code: Optional[str] = None
    parameters: List[ParameterInfo] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    request_schemas: List[str] = field(default_factory=list)
    response_schemas: List[str] = field(default_factory=list)
    router_id: Optional[str] = None
    app_id: Optional[str] = None


@dataclass
class RouterInclusion:
    router_var: str
    module_or_source: str
    prefix: str = ""
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    target_router_id: Optional[str] = None


@dataclass
class RouterInfo:
    id: str
    var_name: str
    module: str
    file_path: str
    line_number: int
    end_line_number: int = 0
    prefix: str = ""
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    inclusions: List[RouterInclusion] = field(default_factory=list)
    endpoints: List[str] = field(default_factory=list)


@dataclass
class AppInfo:
    id: str
    var_name: str
    title: str = "FastAPI App"
    version: str = "0.1.0"
    module: str = ""
    file_path: str = ""
    line_number: int = 0
    end_line_number: int = 0
    middlewares: List[Dict[str, Any]] = field(default_factory=list)
    event_handlers: List[Dict[str, Any]] = field(default_factory=list)
    inclusions: List[RouterInclusion] = field(default_factory=list)
    endpoints: List[str] = field(default_factory=list)
    title_source: str = "default"
    version_source: str = "default"
    title_expr: Optional[str] = None
    version_expr: Optional[str] = None


@dataclass
class DependencyInfo:
    id: str
    name: str
    kind: str  # function, class, security_scheme, annotated_alias
    module: str
    file_path: str
    line_number: int = 0
    end_line_number: int = 0
    docstring: Optional[str] = None
    sub_dependencies: List[str] = field(default_factory=list)
    parameters: List[ParameterInfo] = field(default_factory=list)
    consumers: List[str] = field(default_factory=list)


@dataclass
class SchemaFieldInfo:
    name: str
    type_annotation: str
    default_value: Optional[str] = None
    description: Optional[str] = None
    is_required: bool = True


@dataclass
class SchemaInfo:
    id: str
    name: str
    module: str
    file_path: str
    line_number: int = 0
    end_line_number: int = 0
    docstring: Optional[str] = None
    base_classes: List[str] = field(default_factory=list)
    fields: List[SchemaFieldInfo] = field(default_factory=list)
    used_by_endpoints: List[str] = field(default_factory=list)


@dataclass
class ProjectArchitecture:
    project_name: str
    project_path: str
    apps: List[AppInfo] = field(default_factory=list)
    routers: List[RouterInfo] = field(default_factory=list)
    endpoints: List[EndpointInfo] = field(default_factory=list)
    dependencies: List[DependencyInfo] = field(default_factory=list)
    schemas: List[SchemaInfo] = field(default_factory=list)
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    report_collections: List[ReportCollection] = field(default_factory=list)
