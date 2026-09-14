import json
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Mapping, Optional, Sequence

import pytest

from agent_view import build_agent_view, load_profile
from agent_view.scan import build_snapshot, read_file
from bottlenecks import analyze_bottlenecks, bottlenecks_to_json, parse_harness_profile
from language_analyzers.python.graph import PythonGraphAnalyzer
from report.bottlenecks.generate import render_report


ROOT = Path(__file__).resolve().parents[1]
FUTURAMAAPI_REVISION = "db2603c"
FUTURAMAAPI_COMMIT = "db2603ce931b4b42846afcb3681d021d57618876"
FUTURAMAAPI_REMOTE = "https://github.com/koldakov/futuramaapi"


def _run_subprocess(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)


def _run_git(
    run: Callable[[Sequence[str], Optional[Path]], subprocess.CompletedProcess[str]],
    command: Sequence[str],
    cwd: Optional[Path],
) -> str:
    try:
        completed = run(command, cwd)
    except OSError as exc:
        raise RuntimeError(f"cannot acquire FuturamaAPI: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise RuntimeError(f"cannot acquire FuturamaAPI: {detail}")
    return completed.stdout.strip()


def _require_futuramaapi_revision(
    root: Path,
    run: Callable[[Sequence[str], Optional[Path]], subprocess.CompletedProcess[str]],
) -> None:
    revision = _run_git(run, ("git", "rev-parse", "HEAD"), root)
    if not revision.startswith(FUTURAMAAPI_REVISION):
        raise RuntimeError(
            f"FuturamaAPI HEAD must begin with {FUTURAMAAPI_REVISION}, got {revision or 'no revision'}"
        )


@contextmanager
def futuramaapi_root(
    *,
    environment: Mapping[str, str],
    run: Callable[[Sequence[str], Optional[Path]], subprocess.CompletedProcess[str]] = _run_subprocess,
    temporary_directory: Callable[[], tempfile.TemporaryDirectory[str]] = tempfile.TemporaryDirectory,
) -> Iterator[Path]:
    supplied = environment.get("FUTURAMAAPI_ROOT")
    if supplied:
        root = Path(supplied)
        _require_futuramaapi_revision(root, run)
        yield root
        return
    with temporary_directory() as directory:
        root = Path(directory) / "futuramaapi"
        _run_git(run, ("git", "init", "--quiet", str(root)), None)
        _run_git(run, ("git", "-C", str(root), "fetch", "--depth=1", FUTURAMAAPI_REMOTE, FUTURAMAAPI_COMMIT), None)
        _run_git(run, ("git", "-C", str(root), "checkout", "--quiet", "--detach", "FETCH_HEAD"), None)
        _require_futuramaapi_revision(root, run)
        yield root


def _source_paths(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    )


def _analyze_futuramaapi(
    root: Path,
    *,
    path_lister: Callable[[Path], list[str]] = _source_paths,
    snapshot_builder: Callable[..., object] = build_snapshot,
    snapshot_reader: Callable[[Path], Optional[str]] = read_file,
    profile_loader: Callable[[Path], object] = load_profile,
    harness_reader: Callable[[Path], str] = lambda path: path.read_text(),
) -> str:
    agent_profile = profile_loader(ROOT / "profiles/agent_view.v3.yaml")
    snapshot = snapshot_builder(
        root,
        path_lister(root),
        profile=agent_profile,
        reader=snapshot_reader,
        ignore_source="futuramaapi-commit",
    )
    architecture = PythonGraphAnalyzer(root, snapshot).analyze()
    graph = build_agent_view(architecture, profile=agent_profile, snapshot=snapshot)
    harness = parse_harness_profile(json.loads(harness_reader(ROOT / "profiles/harness.fixed-baseline.v1.json")))
    return bottlenecks_to_json(analyze_bottlenecks(snapshot, architecture, graph, harness))


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess((), returncode, stdout, stderr)


def test_m3_ec_04_supplied_root_requires_futuramaapi_revision_prefix() -> None:
    calls = []

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(command), cwd))
        return _completed("db2603c123456789\n")

    with futuramaapi_root(environment={"FUTURAMAAPI_ROOT": "/provided"}, run=run) as root:
        assert root == Path("/provided")
    assert calls == [(("git", "rev-parse", "HEAD"), Path("/provided"))]

    with pytest.raises(RuntimeError, match="must begin with db2603c"):
        with futuramaapi_root(
            environment={"FUTURAMAAPI_ROOT": "/wrong"},
            run=lambda _command, _cwd: _completed("abcdef0123456789\n"),
        ):
            pass


def test_m3_ec_05_missing_root_fetches_only_futuramaapi_revision_in_temporary_directory() -> None:
    calls = []

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(command), cwd))
        if command == ("git", "rev-parse", "HEAD"):
            return _completed("db2603c123456789\n")
        return _completed()

    with futuramaapi_root(environment={}, run=run) as root:
        assert root.name == "futuramaapi"
        assert not root.is_relative_to(ROOT)
    assert calls[0][0][:3] == ("git", "init", "--quiet")
    assert calls[1][0][:-1] == ("git", "-C", str(root), "fetch", "--depth=1", FUTURAMAAPI_REMOTE)
    assert calls[1][0][-1] == FUTURAMAAPI_COMMIT
    assert calls[2][0] == ("git", "-C", str(root), "checkout", "--quiet", "--detach", "FETCH_HEAD")
    assert calls[3] == (("git", "rev-parse", "HEAD"), root)


@pytest.mark.parametrize(
    "run",
    [
        lambda _command, _cwd: (_ for _ in ()).throw(OSError("git is unavailable")),
        lambda _command, _cwd: _completed(stderr="git failed", returncode=1),
    ],
)
def test_m3_ec_05_git_acquisition_failures_raise_runtime_error(run) -> None:
    with pytest.raises(RuntimeError, match="cannot acquire FuturamaAPI"):
        with futuramaapi_root(environment={}, run=run):
            pass


def test_external_source_analysis_accepts_injected_filesystem_access() -> None:
    agent_profile = load_profile(ROOT / "profiles/agent_view.v3.yaml")
    harness_text = (ROOT / "profiles/harness.fixed-baseline.v1.json").read_text()
    calls = []

    def path_lister(root: Path) -> list[str]:
        calls.append(("paths", root))
        return ["app.py"]

    def snapshot_reader(path: Path) -> Optional[str]:
        calls.append(("snapshot", path))
        return "def value():\n    return 1\n"

    def profile_loader(path: Path) -> object:
        calls.append(("profile", path))
        return agent_profile

    def harness_reader(path: Path) -> str:
        calls.append(("harness", path))
        return harness_text

    payload = json.loads(
        _analyze_futuramaapi(
            Path("/virtual/futuramaapi"),
            path_lister=path_lister,
            snapshot_reader=snapshot_reader,
            profile_loader=profile_loader,
            harness_reader=harness_reader,
        )
    )
    assert payload["snapshot"]["file_count"] == 1
    assert calls == [
        ("profile", ROOT / "profiles/agent_view.v3.yaml"),
        ("paths", Path("/virtual/futuramaapi")),
        ("snapshot", Path("/virtual/futuramaapi/app.py")),
        ("harness", ROOT / "profiles/harness.fixed-baseline.v1.json"),
    ]


def test_m3_ec_06_futuramaapi_analysis_is_deterministic_and_embeds_unchanged_json() -> None:
    with futuramaapi_root(environment=os.environ) as source:
        first = _analyze_futuramaapi(source)
        second = _analyze_futuramaapi(source)
    assert first == second
    payload = json.loads(first)
    for candidate in payload["candidates"]:
        assert candidate["status"] == "static_candidate"
    document = render_report(payload)
    match = re.search(r"<script id='bottlenecks-data' type='application/json'>(.*?)</script>", document, re.DOTALL)
    assert match
    assert json.loads(match.group(1)) == payload
