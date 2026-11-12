import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

_TIMEOUT_SECONDS = 120
_COMMIT = re.compile(r"[0-9a-fA-F]{4,64}")


class _GitFailure(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _git(root: Path, args: Sequence[str], env: dict | None = None) -> bytes:
    # fsmonitor would start a daemon inside the analysed repository; locks are skipped so that
    # read-only calls never rewrite .git/index.
    command = ["git", "-c", "core.fsmonitor=false", *args]
    environment = dict(os.environ if env is None else env)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        done = subprocess.run(command, cwd=root, env=environment, capture_output=True, timeout=_TIMEOUT_SECONDS, check=False)
    except FileNotFoundError as error:
        raise _GitFailure("git_unavailable") from error
    except (OSError, subprocess.SubprocessError) as error:
        raise _GitFailure("git_failed") from error
    if done.returncode != 0:
        raise _GitFailure("git_failed")
    return done.stdout


def _toplevel(root: Path) -> Path:
    try:
        return Path(os.fsdecode(_git(root, ["rev-parse", "--show-toplevel"])).strip()).resolve()
    except _GitFailure as failure:
        # A corrupted .git also makes rev-parse report "not a git repository"; only a missing .git means no repository.
        if failure.reason == "git_failed" and not any((parent / ".git").exists() for parent in (root.resolve(), *root.resolve().parents)):
            raise _GitFailure("not_a_git_repository") from failure
        raise


def _status_paths(output: bytes) -> list[str]:
    fields = output.split(b"\0")
    paths, index = [], 0
    while index < len(fields) and fields[index]:
        entry = fields[index]
        paths.append(os.fsdecode(entry[3:]))
        index += 2 if entry[:1] in (b"R", b"C") else 1
    return paths


def _is_excluded(path: Path, excluded: Sequence[Path]) -> bool:
    return any(path == item or item in path.parents for item in excluded)


def _repository_commit(root: Path, exclude: Sequence[Path]) -> str:
    top = _toplevel(root)
    excluded = [Path(item).resolve() for item in exclude]
    status = _git(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "."])
    if any(not _is_excluded(top / path, excluded) for path in _status_paths(status)):
        raise _GitFailure("dirty")
    return os.fsdecode(_git(root, ["rev-parse", "HEAD"])).strip()


def repository_commit(project_root: Path, *, exclude: Sequence[Path] = ()) -> tuple[str | None, str | None]:
    try:
        return _repository_commit(Path(project_root), exclude), None
    except _GitFailure as failure:
        return None, failure.reason


def _rename_pairs(root: Path, commit: str, exclude: Sequence[Path]) -> list[dict]:
    if not _COMMIT.fullmatch(commit):
        raise _GitFailure("commit_not_found")
    _toplevel(root)
    try:
        _git(root, ["cat-file", "-e", commit + "^{commit}"])
    except _GitFailure as failure:
        if failure.reason == "git_failed":
            raise _GitFailure("commit_not_found") from failure
        raise
    objects = Path(os.fsdecode(_git(root, ["rev-parse", "--path-format=absolute", "--git-path", "objects"])).strip())
    index = Path(os.fsdecode(_git(root, ["rev-parse", "--path-format=absolute", "--git-path", "index"])).strip())
    scratch = tempfile.mkdtemp(prefix="rename-detect-")
    try:
        temp_index = Path(scratch) / "index"
        if index.is_file():
            # Keeping the mtime preserves git's racy-entry check; a newer index would make same-second rewrites look unchanged.
            shutil.copy2(index, temp_index)
        (Path(scratch) / "objects").mkdir()
        # Scratch index and object directory keep untracked files out of the real repository;
        # the real objects stay readable through the alternate.
        env = dict(os.environ, GIT_INDEX_FILE=str(temp_index), GIT_OBJECT_DIRECTORY=str(Path(scratch) / "objects"),
                   GIT_ALTERNATE_OBJECT_DIRECTORIES=str(objects))
        _git(root, ["add", "-A", "--", "."], env)
        output = _git(root, ["diff", "--cached", "-M", "--name-status", "-z", "--relative", "--no-ext-diff", "--no-textconv", commit, "--", "."], env)
    except OSError as error:
        raise _GitFailure("git_failed") from error
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    fields = output.split(b"\0")
    pairs, index_at = [], 0
    while index_at < len(fields) and fields[index_at]:
        status = fields[index_at].decode("ascii", "replace")
        if status.startswith("R"):
            pairs.append({"from": os.fsdecode(fields[index_at + 1]), "to": os.fsdecode(fields[index_at + 2]), "similarity": int(status[1:])})
            index_at += 3
        else:
            index_at += 2
    excluded = [Path(item).resolve() for item in exclude]
    return sorted((pair for pair in pairs if not _is_excluded(root.resolve() / pair["to"], excluded)), key=lambda pair: (pair["from"], pair["to"]))


def detect_renames(project_root: Path, baseline_commit: str | None, *, exclude: Sequence[Path] = ()) -> dict:
    if baseline_commit is None:
        return {"status": "skipped", "reason": "baseline_without_commit", "pairs": []}
    try:
        return {"status": "applied", "reason": None, "pairs": _rename_pairs(Path(project_root), baseline_commit, exclude)}
    except _GitFailure as failure:
        return {"status": "skipped", "reason": failure.reason, "pairs": []}
