from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from language_analyzers.core.graph_models import NodeCost

SCHEMA_VERSION = "3"

@dataclass(frozen=True)
class ProfileRef:
    id: str
    version: int
    content_hash: str

@dataclass(frozen=True)
class ReadUnit:
    id: str
    file_path: str
    start_line: int
    end_line: int
    symbol_ids: List[str]
    read_cost: NodeCost
    oversized_symbol: bool = False

@dataclass(frozen=True)
class ReadableNode:
    id: str
    file_path: str
    symbol_id: Optional[str]
    label: str
    kind: str
    start_line: Optional[int]
    end_line: Optional[int]
    read_cost: NodeCost
    flags: List[str] = field(default_factory=list)
    read_unit_id: str = ""

@dataclass(frozen=True)
class Occurrence:
    file_path: str
    line: int
    col: int
    matched_text: str
    context: str
    enclosing_node_id: str
    surface: str = "content"

@dataclass(frozen=True)
class OccurrenceRange:
    block_id: str
    start: int
    count: int

@dataclass(frozen=True)
class OccurrenceBlock:
    id: str
    start: int
    end: int
    count: int
    sha256: str
    encoding: str
    data: str

@dataclass(frozen=True)
class QueryNode:
    id: str
    term: str
    kind: str
    surface: str
    scope: str
    clue_kinds: List[str]
    origin_node_ids: List[str]
    rule_id: Optional[str]
    source_terms: List[str]
    occurrence_ranges: List[OccurrenceRange]
    occurrence_digest: str
    arrival_node_ids: List[str]
    total_count: int
    visible_count: int
    truncated: bool
    output_tokens: int
    duplicate_suppressed_count: int = 0
    candidate_filtered_count: int = 0
    candidate_cap_truncated: bool = False
    refinement_depth: int = 0

@dataclass(frozen=True)
class Connection:
    id: str
    from_id: str
    to_id: str
    kind: str
    specificity: str
    evidence: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class EntryDocument:
    node_id: str
    file_path: str
    injected: bool

@dataclass(frozen=True)
class ExcludedFile:
    file_path: str
    reason: str

@dataclass(frozen=True)
class ScanReport:
    ignore_source: str
    scanned_file_count: int
    excluded_files: List[ExcludedFile]
    exclusion_counts: Dict[str, int]
    snapshot_digest: str

@dataclass(frozen=True)
class AgentViewGraph:
    schema_version: str
    project_name: str
    project_path: str
    profile: Dict[str, Any]
    scan: ScanReport
    read_units: List[ReadUnit]
    readable_nodes: List[ReadableNode]
    query_nodes: List[QueryNode]
    connections: List[Connection]
    entry_documents: List[EntryDocument]
    hint_store: Dict[str, Dict[str, Any]]
    occurrence_store: List[OccurrenceBlock]
    scale_warning: Optional[str] = None

@dataclass(frozen=True)
class RepositorySnapshot:
    root: str
    ignore_source: str
    contents: Tuple[Tuple[str, str], ...]
    excluded_files: Tuple[ExcludedFile, ...]
    digest: str

    def content_map(self) -> Dict[str, str]:
        return dict(self.contents)
