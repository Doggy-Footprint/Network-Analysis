from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Mapping
from functools import cached_property
from types import MappingProxyType


def split_source_lines(text):
    if not text:
        return ()
    pieces = text.split("\n")
    if pieces[-1] == "":
        pieces.pop()
        last = len(pieces)
    else:
        last = len(pieces) - 1
    return tuple(
        piece[:-1] if index < last and piece.endswith("\r") else piece
        for index, piece in enumerate(pieces)
    )


class SourceText(str):
    @cached_property
    def lines(self):
        return split_source_lines(self)

    @cached_property
    def ranges(self):
        return {}

    def span_text(self, start, end):
        key = (start, end)
        if key not in self.ranges:
            self.ranges[key] = "\n".join(self.lines[start:end])
        return self.ranges[key]


@dataclass(frozen=True)
class ScanPolicyRef:
    id: str
    version: int


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

    @cached_property
    def source_map(self) -> Mapping[str, str]:
        return MappingProxyType({path: SourceText(text) for path, text in self.contents})

    @cached_property
    def source_lines(self) -> Mapping[str, Tuple[str, ...]]:
        return MappingProxyType({path: text.lines for path, text in self.source_map.items()})

    def content_map(self) -> Dict[str, str]:
        return dict(self.contents)
