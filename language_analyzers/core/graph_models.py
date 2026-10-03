from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Confidence(str, Enum):
    STATIC_CERTAIN = "static_certain"
    STATIC_INFERRED = "static_inferred"
    FRAMEWORK_INFERRED = "framework_inferred"
    DYNAMIC_REQUIRED = "dynamic_required"

    def __str__(self) -> str:
        return self.value


class Resolution(str, Enum):
    EXACT = "exact"
    UNIQUE_NAME = "unique_name"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"

    def __str__(self) -> str:
        return self.value


class NodeKind:
    PACKAGE = "package"
    MODULE = "module"
    FILE = "file"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    FUNCTION = "function"
    METHOD = "method"
    FIELD = "field"
    CONSTANT = "constant"
    TYPE_ALIAS = "type_alias"
    CONFIGURATION = "configuration"


class RelationKind:
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    IMPORTS_SYMBOL = "IMPORTS_SYMBOL"
    RE_EXPORTS = "RE_EXPORTS"
    EXPORTS = "EXPORTS"
    DECLARES = "DECLARES"
    CALLS = "CALLS"
    INSTANTIATES = "INSTANTIATES"
    INHERITS = "INHERITS"
    IMPLEMENTS = "IMPLEMENTS"
    DECORATES = "DECORATES"
    TYPE_USES = "TYPE_USES"
    READS = "READS"
    WRITES = "WRITES"
    IMPLEMENTED_BY = "IMPLEMENTED_BY"
    TESTS = "TESTS"
    CONFIGURES = "CONFIGURES"
    CALLS_ROUTE = "CALLS_ROUTE"
    MIGRATES = "MIGRATES"


@dataclass(frozen=True)
class SourceSpan:
    file_path: str
    start_line: int
    end_line: int
    start_col: int = 0
    end_col: int = 0


@dataclass(frozen=True)
class NodeCost:
    token_estimate: int
    char_count: int
    line_count: int


@dataclass
class GraphNode:
    id: str
    label: str
    group: str
    category: str
    title: str = ""
    shape: str = "box"
    size: int = 25
    color: Optional[Dict[str, str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    kind: str = ""
    language: str = ""
    span: Optional[SourceSpan] = None
    cost: Optional[NodeCost] = None
    signature: Optional[str] = None
    docstring: Optional[str] = None
    exported: Optional[bool] = None
    symbol_path: str = ""
    display_label: str = ""
    flags: List[str] = field(default_factory=list)
    provenance: str = ""

    def __post_init__(self):
        # analysis/graph_metrics.py and the dashboard still read these conventional
        # metadata keys; mirroring keeps them working while span becomes the source of truth.
        if self.span is not None:
            self.metadata.setdefault("file_path", self.span.file_path)
            self.metadata.setdefault("line_number", self.span.start_line)
            self.metadata.setdefault("end_line_number", self.span.end_line)


@dataclass
class GraphEdge:
    from_id: str
    to_id: str
    relation: str
    label: str = ""
    dashes: bool = False
    arrows: str = "to"
    color: Optional[str] = None
    title: Optional[str] = None
    confidence: str = Confidence.STATIC_CERTAIN
    resolution: str = Resolution.EXACT
    evidence: Optional[SourceSpan] = None
    candidates: List[str] = field(default_factory=list)
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
