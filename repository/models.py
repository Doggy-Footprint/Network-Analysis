from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ScanPolicyRef:
    id: str
    version: int
    content_hash: str


@dataclass(frozen=True)
class ScanPolicy:
    ref: ScanPolicyRef
    max_file_bytes: int
    generated_marker_lines: int = 8
    include_agent_docs: bool = True
    tracked_files_only: bool = True
    vendor_globs: List[str] = field(default_factory=list)
    generated_globs: List[str] = field(default_factory=list)
    generated_markers: List[str] = field(default_factory=list)
    lockfile_names: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExcludedFile:
    file_path: str
    reason: str


@dataclass(frozen=True)
class RepositorySnapshot:
    root: str
    ignore_source: str
    contents: Tuple[Tuple[str, str], ...]
    excluded_files: Tuple[ExcludedFile, ...]
    digest: str

    def content_map(self) -> Dict[str, str]:
        return dict(self.contents)
