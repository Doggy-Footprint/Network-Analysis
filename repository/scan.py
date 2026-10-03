import fnmatch
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Set, Tuple

from .models import ExcludedFile, RepositorySnapshot, ScanPolicy

STATIC_EXCLUDED_DIRECTORIES = {
    ".git",
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "venv",
}
AGENT_DOC_NAMES = {"AGENTS.md", "CLAUDE.md", "README.md"}
_BINARY_SNIFF_CHARS = 8192


def read_file(path: Path) -> Optional[str]:
    try:
        return path.read_bytes().decode("utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None


def list_repository_files(
    root: Path,
    *,
    tracked_files_only: bool = True,
) -> Tuple[str, List[str]]:
    if tracked_files_only:
        tracked = _git_tracked_files(root)
        if tracked is not None:
            return "git-tracked", sorted(tracked)
    return "static_fallback", sorted(_walk_files(root))


def _git_tracked_files(root: Path) -> Optional[List[str]]:
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, ValueError):
        return None
    if completed.returncode != 0:
        return None
    entries = [
        entry
        for entry in completed.stdout.decode("utf-8", errors="replace").split("\0")
        if entry
    ]
    return [Path(entry).as_posix() for entry in entries] if entries else None


def _walk_files(root: Path) -> List[str]:
    output = []
    for current, directories, names in os.walk(root):
        directories[:] = [
            directory
            for directory in directories
            if not directory.startswith(".")
            and directory not in STATIC_EXCLUDED_DIRECTORIES
        ]
        output.extend(
            Path(current, name).relative_to(root).as_posix()
            for name in names
        )
    return output


def _matches_output(path: str, explicit_outputs: Set[str]) -> bool:
    return any(
        path == output or path.startswith(output.rstrip("/") + "/")
        for output in explicit_outputs
    )


def _exclusion_reason(
    path: str,
    text: Optional[str],
    policy: ScanPolicy,
    explicit_outputs: Set[str],
) -> Optional[str]:
    if _matches_output(path, explicit_outputs):
        return "explicit_output"
    if Path(path).name in policy.lockfile_names:
        return "lockfile"
    if any(fnmatch.fnmatch(path, pattern) for pattern in policy.vendor_globs):
        return "vendored"
    if any(fnmatch.fnmatch(path, pattern) for pattern in policy.generated_globs):
        return "generated_path"
    if text is None:
        return "unreadable"
    if len(text.encode("utf-8", errors="replace")) > policy.max_file_bytes:
        return "too_large"
    if "\0" in text[:_BINARY_SNIFF_CHARS]:
        return "binary"
    head = "\n".join(text.splitlines()[:policy.generated_marker_lines])
    if any(re.search(pattern, head, re.IGNORECASE) for pattern in policy.generated_markers):
        return "generated_marker"
    if not policy.include_agent_docs and Path(path).name in AGENT_DOC_NAMES:
        return "agent_document_disabled"
    return None


def _relative_outputs(root: Path, excluded_paths: Sequence[str]) -> Set[str]:
    outputs = set()
    for value in excluded_paths:
        path = Path(value)
        try:
            relative = path.relative_to(root) if path.is_absolute() else path
        except ValueError:
            continue
        outputs.add(relative.as_posix().lstrip("./"))
    return outputs


def build_snapshot(
    root: Path,
    relative_paths: Sequence[str],
    *,
    policy: ScanPolicy,
    reader: Callable[[Path], Optional[str]] = read_file,
    ignore_source: str = "provided",
    excluded_paths: Sequence[str] = (),
) -> RepositorySnapshot:
    explicit_outputs = _relative_outputs(root, excluded_paths)
    contents = []
    excluded = []
    normalized_paths = sorted(
        {Path(path).as_posix().lstrip("./") for path in relative_paths}
    )
    for relative in normalized_paths:
        try:
            text = reader(root / relative)
        except (OSError, UnicodeError):
            text = None
        reason = _exclusion_reason(relative, text, policy, explicit_outputs)
        if reason is None:
            contents.append((relative, text or ""))
        else:
            excluded.append(ExcludedFile(relative, reason))

    return RepositorySnapshot(
        root=str(root),
        ignore_source=ignore_source,
        contents=tuple(contents),
        excluded_files=tuple(excluded),
    )
