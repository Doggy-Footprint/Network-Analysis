"""
Data models representing the extracted architecture of an Android/Kotlin project.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from language_analyzers.core.graph_models import GraphEdge, GraphNode
from language_analyzers.core.report_schema import ColumnSpec, ReportCollection

__all__ = [
    "ComposableInfo",
    "ViewModelInfo",
    "DiModuleInfo",
    "DiBindingInfo",
    "DaggerComponentInfo",
    "RoomFieldInfo",
    "RoomEntityInfo",
    "RoomMigrationInfo",
    "RoomQueryMethodInfo",
    "RoomDaoInfo",
    "RoomDatabaseInfo",
    "RetrofitEndpointInfo",
    "RetrofitApiInfo",
    "ActivityFragmentInfo",
    "GraphNode",
    "GraphEdge",
    "ColumnSpec",
    "ReportCollection",
    "AndroidProjectArchitecture",
]


@dataclass
class ComposableInfo:
    id: str
    name: str
    module: str
    file_path: str
    line_number: int = 0
    end_line_number: int = 0
    calls: List[str] = field(default_factory=list)  # simple names of composables/functions called in the body
    uses_viewmodel: Optional[str] = None  # simple name of the ViewModel type used, if any


@dataclass
class ViewModelInfo:
    id: str
    name: str
    module: str
    file_path: str
    line_number: int = 0
    end_line_number: int = 0
    is_hilt: bool = False
    injected_types: List[str] = field(default_factory=list)  # constructor-injected parameter types
    calls: List[str] = field(default_factory=list)  # simple names of members called in the body


@dataclass
class DiModuleInfo:
    id: str
    name: str
    module: str
    file_path: str
    line_number: int = 0
    end_line_number: int = 0
    install_in: List[str] = field(default_factory=list)  # Dagger/Hilt component simple names


@dataclass
class DiBindingInfo:
    id: str
    name: str
    kind: str  # provides | binds | inject_constructor | inject_field
    module: str
    file_path: str
    line_number: int = 0
    end_line_number: int = 0
    owner_module_id: Optional[str] = None  # the DiModuleInfo.id this binding belongs to (provides/binds only)
    provided_type: Optional[str] = None
    injected_type: Optional[str] = None  # the class this binding is attached to (inject_constructor/inject_field)
    owner_class_name: Optional[str] = None
    field_name: Optional[str] = None


@dataclass
class DaggerComponentInfo:
    id: str
    name: str
    module: str = ""
    file_path: str = ""
    line_number: int = 0
    end_line_number: int = 0
    synthesized: bool = False  # true when no explicit @Component/@Subcomponent declaration was found


@dataclass
class RoomFieldInfo:
    name: str
    type_annotation: str
    is_primary_key: bool = False


@dataclass
class RoomEntityInfo:
    id: str
    name: str
    module: str
    file_path: str
    line_number: int = 0
    end_line_number: int = 0
    fields: List[RoomFieldInfo] = field(default_factory=list)
    table_name: str = ""  # normalized @Entity(tableName=...) or class name; kept out of node metadata


@dataclass
class RoomMigrationInfo:
    id: str
    name: str
    module: str
    file_path: str
    line_number: int = 0
    end_line_number: int = 0
    is_declaration: bool = False  # class/object form, which has a Kotlin language node; false for `object : Migration` properties
    table_refs: List[Optional[str]] = field(default_factory=list)  # None marks a non-literal execSQL argument


@dataclass
class RoomQueryMethodInfo:
    id: str
    name: str
    kind: str  # query | insert | update | delete | transaction
    query_text: Optional[str] = None
    return_type: Optional[str] = None
    line_number: int = 0
    end_line_number: int = 0


@dataclass
class RoomDaoInfo:
    id: str
    name: str
    module: str
    file_path: str
    line_number: int = 0
    end_line_number: int = 0
    methods: List[RoomQueryMethodInfo] = field(default_factory=list)


@dataclass
class RoomDatabaseInfo:
    id: str
    name: str
    module: str
    file_path: str
    line_number: int = 0
    end_line_number: int = 0
    entity_names: List[str] = field(default_factory=list)  # from @Database(entities = [...])
    dao_accessors: List[str] = field(default_factory=list)  # return-type simple names of abstract dao-returning methods


@dataclass
class RetrofitEndpointInfo:
    id: str
    name: str
    http_method: str
    path: str
    line_number: int = 0
    end_line_number: int = 0


@dataclass
class RetrofitApiInfo:
    id: str
    name: str
    module: str
    file_path: str
    line_number: int = 0
    end_line_number: int = 0
    endpoints: List[RetrofitEndpointInfo] = field(default_factory=list)


@dataclass
class ActivityFragmentInfo:
    id: str
    name: str
    kind: str  # activity | fragment
    module: str
    file_path: str
    line_number: int = 0
    end_line_number: int = 0
    is_hilt_entry_point: bool = False
    hosted_composables: List[str] = field(default_factory=list)  # simple names referenced inside setContent {}


@dataclass
class AndroidProjectArchitecture:
    project_name: str
    project_path: str
    composables: List[ComposableInfo] = field(default_factory=list)
    viewmodels: List[ViewModelInfo] = field(default_factory=list)
    di_modules: List[DiModuleInfo] = field(default_factory=list)
    di_bindings: List[DiBindingInfo] = field(default_factory=list)
    dagger_components: List[DaggerComponentInfo] = field(default_factory=list)
    room_entities: List[RoomEntityInfo] = field(default_factory=list)
    room_migrations: List[RoomMigrationInfo] = field(default_factory=list)
    room_daos: List[RoomDaoInfo] = field(default_factory=list)
    room_databases: List[RoomDatabaseInfo] = field(default_factory=list)
    retrofit_apis: List[RetrofitApiInfo] = field(default_factory=list)
    activities_fragments: List[ActivityFragmentInfo] = field(default_factory=list)
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    report_collections: List[ReportCollection] = field(default_factory=list)
