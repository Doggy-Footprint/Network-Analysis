import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Optional, Sequence

import pytest

from fixtures import registry
from fixtures.registry import (
    FixtureAcquisitionError,
    FixtureIntegrityError,
    FixtureSpec,
    compute_content_sha256,
    fixture_root,
)


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess((), returncode, stdout, stderr)


def _write_tree(root: Path, files: Dict[str, bytes]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for relative_path, content in files.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def _hand_computed_hash(files: Dict[str, bytes]) -> str:
    # Independent restatement of the contract's algorithm (sorted relative
    # posix paths, concatenated raw bytes, sha256 hexdigest) -- not a call
    # into the module under test.
    hasher = hashlib.sha256()
    for relative_path in sorted(files):
        hasher.update(files[relative_path])
    return hasher.hexdigest()


GOOD_FILES = {"a.txt": b"hello", "sub/b.txt": b"world"}
GOOD_COMMIT = "1111111111111111111111111111111111abcd"
GOOD_HASH = _hand_computed_hash(GOOD_FILES)

OTHER_FILES = {"a.txt": b"different content"}
OTHER_HASH = _hand_computed_hash(OTHER_FILES)
OTHER_COMMIT = "2222222222222222222222222222222222dcba"

SPEC = FixtureSpec(
    name="widget",
    remote="https://example.invalid/widget.git",
    commit=GOOD_COMMIT,
    content_sha256=GOOD_HASH,
)


def test_compute_content_sha256_matches_independent_hand_calculation(tmp_path: Path) -> None:
    _write_tree(tmp_path, GOOD_FILES)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_bytes(b"ref: refs/heads/main\n")
    assert compute_content_sha256(tmp_path) == GOOD_HASH


def test_default_run_captures_text_output_and_passes_cwd_as_keyword(tmp_path: Path, monkeypatch) -> None:
    # Proves the real (non-test) call path -- fixture_root(name) with no `run=`
    # override -- no longer crashes now that the default is `_default_run`
    # instead of bare `subprocess.run` (contract v2, EC unchanged, default fixed).
    monkeypatch.setitem(registry.FIXTURES, "widget", SPEC)
    target = tmp_path / "widget"
    _write_tree(target, GOOD_FILES)
    received = {}

    def fake_subprocess_run(command, cwd=None, capture_output=None, text=None):
        received["command"] = command
        received["cwd"] = cwd
        received["capture_output"] = capture_output
        received["text"] = text
        return subprocess.CompletedProcess(command, 0, f"{GOOD_COMMIT}\n", "")

    monkeypatch.setattr(registry.subprocess, "run", fake_subprocess_run)

    root = fixture_root("widget", environment={}, fixtures_dir=tmp_path)

    assert root == target
    assert received["command"] == ("git", "rev-parse", "HEAD")
    assert received["cwd"] == target
    assert received["capture_output"] is True
    assert received["text"] is True


def test_ec_01_fresh_acquisition_runs_init_fetch_checkout_and_verifies(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget", SPEC)
    target = tmp_path / "widget"
    calls = []

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(command), cwd))
        if command[:2] == ("git", "init"):
            target.mkdir(parents=True, exist_ok=True)
            return _completed()
        if command[:4] == ("git", "-C", str(target), "fetch"):
            return _completed()
        if command == ("git", "-C", str(target), "checkout", "--quiet", "--detach", "FETCH_HEAD"):
            _write_tree(target, GOOD_FILES)
            return _completed()
        if command == ("git", "rev-parse", "HEAD"):
            return _completed(f"{GOOD_COMMIT}\n")
        raise AssertionError(f"unexpected command {command!r}")

    root = fixture_root("widget", environment={}, run=run, fixtures_dir=tmp_path)

    assert root == target
    assert calls[0][0] == ("git", "init", "--quiet", str(target))
    assert calls[0][1] is None
    assert calls[1][0] == ("git", "-C", str(target), "fetch", "--depth=1", SPEC.remote, SPEC.commit)
    assert calls[1][1] is None
    assert calls[2][0] == ("git", "-C", str(target), "checkout", "--quiet", "--detach", "FETCH_HEAD")
    assert calls[2][1] is None
    assert calls[3] == (("git", "rev-parse", "HEAD"), target)


def test_ec_01_fresh_clone_wrong_content_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget", SPEC)
    target = tmp_path / "widget"

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        if command[:2] == ("git", "init"):
            target.mkdir(parents=True, exist_ok=True)
            return _completed()
        if command[:4] == ("git", "-C", str(target), "fetch"):
            return _completed()
        if command == ("git", "-C", str(target), "checkout", "--quiet", "--detach", "FETCH_HEAD"):
            _write_tree(target, OTHER_FILES)  # right commit, wrong content
            return _completed()
        if command == ("git", "rev-parse", "HEAD"):
            return _completed(f"{GOOD_COMMIT}\n")
        raise AssertionError(f"unexpected command {command!r}")

    with pytest.raises(FixtureIntegrityError):
        fixture_root("widget", environment={}, run=run, fixtures_dir=tmp_path)


def test_ec_01_fresh_clone_wrong_commit_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget", SPEC)
    target = tmp_path / "widget"

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        if command[:2] == ("git", "init"):
            target.mkdir(parents=True, exist_ok=True)
            return _completed()
        if command[:4] == ("git", "-C", str(target), "fetch"):
            return _completed()
        if command == ("git", "-C", str(target), "checkout", "--quiet", "--detach", "FETCH_HEAD"):
            _write_tree(target, GOOD_FILES)  # right content, wrong commit
            return _completed()
        if command == ("git", "rev-parse", "HEAD"):
            return _completed(f"{OTHER_COMMIT}\n")
        raise AssertionError(f"unexpected command {command!r}")

    with pytest.raises(FixtureIntegrityError):
        fixture_root("widget", environment={}, run=run, fixtures_dir=tmp_path)


def test_ec_02_cache_hit_returns_path_with_single_rev_parse_call(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget", SPEC)
    target = tmp_path / "widget"
    _write_tree(target, GOOD_FILES)
    calls = []

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(command), cwd))
        return _completed(f"{GOOD_COMMIT}\n")

    root = fixture_root("widget", environment={}, run=run, fixtures_dir=tmp_path)

    assert root == target
    assert calls == [(("git", "rev-parse", "HEAD"), target)]


def test_ec_03_cache_hash_mismatch_reclones_once_then_succeeds(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget", SPEC)
    target = tmp_path / "widget"
    _write_tree(target, OTHER_FILES)  # right commit, wrong content
    stale_file = target / "stale.txt"  # present in the old tree, absent from the fresh clone's file set
    stale_file.write_text("leftover from a previous acquisition")
    calls = []

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(command), cwd))
        if command[:2] == ("git", "init"):
            target.mkdir(parents=True, exist_ok=True)
            return _completed()
        if command[:4] == ("git", "-C", str(target), "fetch"):
            return _completed()
        if command == ("git", "-C", str(target), "checkout", "--quiet", "--detach", "FETCH_HEAD"):
            _write_tree(target, GOOD_FILES)
            return _completed()
        if command == ("git", "rev-parse", "HEAD"):
            return _completed(f"{GOOD_COMMIT}\n")
        raise AssertionError(f"unexpected command {command!r}")

    root = fixture_root("widget", environment={}, run=run, fixtures_dir=tmp_path)

    assert root == target
    assert compute_content_sha256(target) == GOOD_HASH
    assert not stale_file.exists()  # proves the stale dir was deleted, not overwritten in place
    # first rev-parse (cache probe) + reclone (init/fetch/checkout) + final rev-parse
    assert [c[0] for c in calls].count(("git", "rev-parse", "HEAD")) == 2


def test_ec_03_cache_hash_mismatch_still_mismatched_after_retry_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget", SPEC)
    target = tmp_path / "widget"
    _write_tree(target, OTHER_FILES)

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        if command[:2] == ("git", "init"):
            target.mkdir(parents=True, exist_ok=True)
            return _completed()
        if command[:4] == ("git", "-C", str(target), "fetch"):
            return _completed()
        if command == ("git", "-C", str(target), "checkout", "--quiet", "--detach", "FETCH_HEAD"):
            _write_tree(target, OTHER_FILES)  # still wrong content after "reclone"
            return _completed()
        if command == ("git", "rev-parse", "HEAD"):
            return _completed(f"{GOOD_COMMIT}\n")
        raise AssertionError(f"unexpected command {command!r}")

    with pytest.raises(FixtureIntegrityError):
        fixture_root("widget", environment={}, run=run, fixtures_dir=tmp_path)


def test_ec_04_cache_wrong_head_reclones_once_then_succeeds(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget", SPEC)
    target = tmp_path / "widget"
    _write_tree(target, GOOD_FILES)  # right content, but rev-parse will report wrong HEAD until reclone
    stale_file = target / "stale.txt"  # present in the old tree, absent from the fresh clone's file set
    stale_file.write_text("leftover from a previous acquisition")
    heads = iter([OTHER_COMMIT, GOOD_COMMIT])
    calls = []

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(command), cwd))
        if command[:2] == ("git", "init"):
            target.mkdir(parents=True, exist_ok=True)
            return _completed()
        if command[:4] == ("git", "-C", str(target), "fetch"):
            return _completed()
        if command == ("git", "-C", str(target), "checkout", "--quiet", "--detach", "FETCH_HEAD"):
            _write_tree(target, GOOD_FILES)
            return _completed()
        if command == ("git", "rev-parse", "HEAD"):
            return _completed(f"{next(heads)}\n")
        raise AssertionError(f"unexpected command {command!r}")

    root = fixture_root("widget", environment={}, run=run, fixtures_dir=tmp_path)

    assert root == target
    assert not stale_file.exists()  # proves the stale dir was deleted, not overwritten in place
    assert [c[0] for c in calls].count(("git", "rev-parse", "HEAD")) == 2


def test_ec_05_env_override_matching_returns_path_and_leaves_cache_untouched(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget", SPEC)
    override_dir = tmp_path / "supplied"
    _write_tree(override_dir, GOOD_FILES)
    cache_dir = tmp_path / "cache"
    calls = []

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(command), cwd))
        return _completed(f"{GOOD_COMMIT}\n")

    root = fixture_root(
        "widget",
        environment={"WIDGET_FIXTURE_ROOT": str(override_dir)},
        run=run,
        fixtures_dir=cache_dir,
    )

    assert root == override_dir
    assert calls == [(("git", "rev-parse", "HEAD"), override_dir)]
    assert not (cache_dir / "widget").exists()


def test_ec_06_env_override_wrong_commit_or_hash_raises_without_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget", SPEC)
    override_dir = tmp_path / "supplied"
    _write_tree(override_dir, OTHER_FILES)
    cache_dir = tmp_path / "cache"
    calls = []

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(command), cwd))
        return _completed(f"{GOOD_COMMIT}\n")

    with pytest.raises(FixtureIntegrityError):
        fixture_root(
            "widget",
            environment={"WIDGET_FIXTURE_ROOT": str(override_dir)},
            run=run,
            fixtures_dir=cache_dir,
        )

    assert calls == [(("git", "rev-parse", "HEAD"), override_dir)]
    assert not (cache_dir / "widget").exists()


def test_ec_07_unknown_fixture_name_raises_key_error_before_any_subprocess_call(tmp_path: Path) -> None:
    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        raise AssertionError("run must not be called for an unknown fixture name")

    with pytest.raises(KeyError):
        fixture_root("does-not-exist", environment={}, run=run, fixtures_dir=tmp_path)


def test_ec_08_clone_subprocess_os_error_raises_fixture_acquisition_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget", SPEC)

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        raise OSError("git is unavailable")

    with pytest.raises(FixtureAcquisitionError):
        fixture_root("widget", environment={}, run=run, fixtures_dir=tmp_path)


def test_ec_08_clone_subprocess_nonzero_exit_raises_with_stderr_in_message(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget", SPEC)

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        return _completed(stderr="fatal: fetch failed", returncode=1)

    with pytest.raises(FixtureAcquisitionError, match="fatal: fetch failed"):
        fixture_root("widget", environment={}, run=run, fixtures_dir=tmp_path)


# --- subpaths (EC-16/EC-17/EC-18) ---------------------------------------

UPSTREAM_SUBPATH_FILES = {
    "keep/a.txt": b"keep-a",
    "keep/sub/b.txt": b"keep-b",
    "drop/c.txt": b"drop-c",
    "top_level.txt": b"top-level",
}
PRUNED_SUBPATH_FILES = {"kept/a.txt": b"keep-a", "kept/sub/b.txt": b"keep-b"}
PRUNED_SUBPATH_HASH = _hand_computed_hash(PRUNED_SUBPATH_FILES)

SUBPATH_SPEC = FixtureSpec(
    name="widget-sub",
    remote="https://example.invalid/widget-sub.git",
    commit=GOOD_COMMIT,
    content_sha256=PRUNED_SUBPATH_HASH,
    subpaths={"keep": "kept"},
)


def _fake_checkout_run(target: Path, files_after_checkout: Dict[str, bytes], head: str):
    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        if command[:2] == ("git", "init"):
            target.mkdir(parents=True, exist_ok=True)
            (target / ".git").mkdir(exist_ok=True)
            return _completed()
        if command[:4] == ("git", "-C", str(target), "fetch"):
            return _completed()
        if command == ("git", "-C", str(target), "checkout", "--quiet", "--detach", "FETCH_HEAD"):
            _write_tree(target, files_after_checkout)
            return _completed()
        if command == ("git", "rev-parse", "HEAD"):
            return _completed(f"{head}\n")
        raise AssertionError(f"unexpected command {command!r}")

    return run


def test_ec_16_fresh_clone_prunes_and_renames_subpaths_before_hashing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget-sub", SUBPATH_SPEC)
    target = tmp_path / "widget-sub"
    run = _fake_checkout_run(target, UPSTREAM_SUBPATH_FILES, GOOD_COMMIT)

    root = fixture_root("widget-sub", environment={}, run=run, fixtures_dir=tmp_path)

    assert root == target
    assert (target / ".git").is_dir()  # preserved
    assert not (target / "drop").exists()  # pruned
    assert not (target / "top_level.txt").exists()  # pruned
    assert not (target / "keep").exists()  # renamed away, not left behind
    assert (target / "kept" / "a.txt").read_bytes() == b"keep-a"
    assert (target / "kept" / "sub" / "b.txt").read_bytes() == b"keep-b"
    assert compute_content_sha256(target) == PRUNED_SUBPATH_HASH


def test_ec_17_cache_hit_rehashes_pruned_tree_without_repruning(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget-sub", SUBPATH_SPEC)
    target = tmp_path / "widget-sub"
    # Already pruned from a prior EC-16 run: only the renamed destination + .git remain,
    # the original "keep"/"drop" source_prefix locations no longer exist.
    _write_tree(target, PRUNED_SUBPATH_FILES)
    (target / ".git").mkdir(exist_ok=True)
    calls = []

    def run(command: Sequence[str], cwd: Optional[Path]) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(command), cwd))
        return _completed(f"{GOOD_COMMIT}\n")

    root = fixture_root("widget-sub", environment={}, run=run, fixtures_dir=tmp_path)

    assert root == target
    assert calls == [(("git", "rev-parse", "HEAD"), target)]  # no fetch/checkout: no re-prune attempted
    assert (target / "kept" / "a.txt").exists()


def test_ec_18_fresh_clone_missing_source_prefix_raises_acquisition_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry.FIXTURES, "widget-sub", SUBPATH_SPEC)
    target = tmp_path / "widget-sub"
    files_without_keep = {"drop/c.txt": b"drop-c", "top_level.txt": b"top-level"}
    run = _fake_checkout_run(target, files_without_keep, GOOD_COMMIT)

    with pytest.raises(FixtureAcquisitionError):
        fixture_root("widget-sub", environment={}, run=run, fixtures_dir=tmp_path)
