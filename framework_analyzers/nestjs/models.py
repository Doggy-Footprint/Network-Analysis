from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from language_analyzers.core.graph_models import GraphEdge, GraphNode, SourceSpan
from language_analyzers.core.report_schema import ReportCollection


@dataclass
class NestJSDeclaration:
    id: str
    kind: str
    name: str
    file_path: str
    span: SourceSpan
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    ast_node: Any = field(default=None, repr=False)


@dataclass
class NestJSReference:
    from_id: str
    to_id: str
    relation: str
    evidence: SourceSpan


@dataclass
class NestJSDiagnostic:
    code: str
    span: SourceSpan
    expression: str
    reason: str

    def as_dict(self):
        return {"code": self.code, "span": self.span.__dict__, "expression": self.expression,
                "reason": self.reason}


@dataclass
class NestJSProjectArchitecture:
    project_name: str
    project_path: str
    declarations: List[NestJSDeclaration] = field(default_factory=list)
    references: List[NestJSReference] = field(default_factory=list)
    diagnostics: List[NestJSDiagnostic] = field(default_factory=list)
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    report_collections: List[ReportCollection] = field(default_factory=list)
    http_calls: List[Any] = field(default_factory=list)
    pending_implementation_edges: List[GraphEdge] = field(default_factory=list)
