"""Pinned external fixture acquisition (shallow-clone-and-verify), shared across tests.

Generalizes the `futuramaapi_root` pattern that used to live in
tests/test_m3_futuramaapi_acceptance.py so multiple fixtures can reuse the same
acquire/verify/cache logic. See contracts/fixture-unification.md.
"""
import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]


class FixtureAcquisitionError(RuntimeError):
    """Raised when the clone/fetch/checkout subprocess sequence fails."""


class FixtureIntegrityError(RuntimeError):
    """Raised when the acquired fixture's commit or content hash doesn't match its spec."""


@dataclass(frozen=True)
class FixtureSpec:
    name: str
    remote: str
    commit: str
    content_sha256: str
    subpaths: Optional[Mapping[str, str]] = None


FIXTURES: Mapping[str, FixtureSpec] = {
    "futuramaapi": FixtureSpec(
        name="futuramaapi",
        remote="https://github.com/koldakov/futuramaapi",
        commit="db2603ce931b4b42846afcb3681d021d57618876",
        content_sha256="9fe2403f78985ad5502272088b53ed034db4f9e32f834e361b5ca2ba8aef69d5",
    ),
}


def compute_content_sha256(root: Path) -> str:
    relative_paths = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    )
    hasher = hashlib.sha256()
    for relative_path in relative_paths:
        hasher.update((root / relative_path).read_bytes())
    return hasher.hexdigest()


def _run_git(
    run: Callable[[Sequence[str], Optional[Path]], "subprocess.CompletedProcess[str]"],
    command: Sequence[str],
    cwd: Optional[Path],
    fixture_name: str,
) -> str:
    try:
        completed = run(tuple(command), cwd)
    except OSError as exc:
        raise FixtureAcquisitionError(f"cannot acquire fixture {fixture_name!r}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise FixtureAcquisitionError(f"cannot acquire fixture {fixture_name!r}: {detail}")
    return completed.stdout.strip()


def _clone(
    spec: FixtureSpec,
    path: Path,
    run: Callable[[Sequence[str], Optional[Path]], "subprocess.CompletedProcess[str]"],
) -> None:
    _run_git(run, ("git", "init", "--quiet", str(path)), None, spec.name)
    _run_git(run, ("git", "-C", str(path), "fetch", "--depth=1", spec.remote, spec.commit), None, spec.name)
    _run_git(run, ("git", "-C", str(path), "checkout", "--quiet", "--detach", "FETCH_HEAD"), None, spec.name)


def _head(
    path: Path,
    run: Callable[[Sequence[str], Optional[Path]], "subprocess.CompletedProcess[str]"],
    fixture_name: str,
) -> str:
    return _run_git(run, ("git", "rev-parse", "HEAD"), path, fixture_name)


def _matches(
    spec: FixtureSpec,
    path: Path,
    run: Callable[[Sequence[str], Optional[Path]], "subprocess.CompletedProcess[str]"],
) -> bool:
    if _head(path, run, spec.name) != spec.commit:
        return False
    return compute_content_sha256(path) == spec.content_sha256


def _require_match(
    spec: FixtureSpec,
    path: Path,
    run: Callable[[Sequence[str], Optional[Path]], "subprocess.CompletedProcess[str]"],
) -> None:
    if not _matches(spec, path, run):
        raise FixtureIntegrityError(
            f"fixture {spec.name!r} at {path} does not match pinned commit {spec.commit} "
            f"or content_sha256 {spec.content_sha256}"
        )


def _default_run(command: Sequence[str], cwd: Optional[Path]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True)


def fixture_root(
    name: str,
    *,
    environment: Mapping[str, str] = os.environ,
    run: Callable[[Sequence[str], Optional[Path]], "subprocess.CompletedProcess[str]"] = _default_run,
    fixtures_dir: Optional[Path] = None,
) -> Path:
    spec = FIXTURES[name]

    env_key = f"{name.upper().replace('-', '_')}_FIXTURE_ROOT"
    override = environment.get(env_key)
    if override:
        override_path = Path(override)
        _require_match(spec, override_path, run)
        return override_path

    base = fixtures_dir if fixtures_dir is not None else (REPO_ROOT / ".fixtures")
    path = base / name

    if path.exists():
        if _matches(spec, path, run):
            return path
        shutil.rmtree(path)
        _clone(spec, path, run)
        _require_match(spec, path, run)
        return path

    _clone(spec, path, run)
    _require_match(spec, path, run)
    return path
