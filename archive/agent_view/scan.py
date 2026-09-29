from pathlib import Path
from typing import Callable, Optional, Sequence

from repository.scan import (
    AGENT_DOC_NAMES,
    STATIC_EXCLUDED_DIRECTORIES,
    build_snapshot,
    list_repository_files,
    read_file,
)

from .models import ProfileRef
from .profile import Profile

__all__ = [
    "AGENT_DOC_NAMES",
    "STATIC_EXCLUDED_DIRECTORIES",
    "build_snapshot",
    "list_repository_files",
    "read_file",
    "scan_files",
]


def scan_files(
    root: Path,
    relative_paths: Sequence[str],
    *,
    max_file_bytes: int,
    reader: Callable[[Path], Optional[str]],
    include_agent_docs: bool = True,
):
    profile = Profile(
        ref=ProfileRef("compat", 3, ""),
        min_term_length=3,
        max_file_bytes=max_file_bytes,
        transforms=[],
        include_agent_docs=include_agent_docs,
        vendor_globs=[],
        generated_globs=[],
    )
    snapshot = build_snapshot(root, relative_paths, policy=profile.scan_policy(), reader=reader)
    contents = snapshot.content_map()
    excluded = [
        item
        for item in snapshot.excluded_files
        if item.reason != "agent_document_disabled"
    ]
    return list(contents), excluded, contents
