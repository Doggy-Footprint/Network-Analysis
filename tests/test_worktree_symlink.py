import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / ".githooks" / "link_worktree_shared.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("link_worktree_shared", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


link_worktree_shared = _load_module()

is_main_worktree = link_worktree_shared.is_main_worktree
main_worktree_root = link_worktree_shared.main_worktree_root
link_shared = link_worktree_shared.link_shared
LinkResult = link_worktree_shared.LinkResult


def test_ec_09_main_worktree_detected_when_git_dir_equals_git_common_dir(tmp_path: Path) -> None:
    git_dir = tmp_path / "repo" / ".git"
    assert is_main_worktree(git_dir, git_dir) is True


def test_ec_09_linked_worktree_detected_when_git_dir_differs_from_git_common_dir(tmp_path: Path) -> None:
    git_common_dir = tmp_path / "repo" / ".git"
    git_dir = git_common_dir / "worktrees" / "feature"
    assert is_main_worktree(git_dir, git_common_dir) is False


def test_main_worktree_root_is_parent_of_git_common_dir(tmp_path: Path) -> None:
    git_common_dir = tmp_path / "repo" / ".git"
    assert main_worktree_root(git_common_dir) == (tmp_path / "repo").resolve()


def test_ec_10_missing_targets_are_linked_as_symlinks_to_main_root(tmp_path: Path) -> None:
    main_root = tmp_path / "main"
    (main_root / ".venv").mkdir(parents=True)
    (main_root / ".fixtures").mkdir(parents=True)
    worktree_root = tmp_path / "worktree"
    worktree_root.mkdir()

    results = link_shared(worktree_root, main_root)

    assert results == [
        LinkResult(name=".fixtures", action="linked"),
        LinkResult(name=".venv", action="linked"),
    ]
    assert (worktree_root / ".fixtures").is_symlink()
    assert (worktree_root / ".fixtures").resolve() == (main_root / ".fixtures").resolve()
    assert (worktree_root / ".venv").is_symlink()
    assert (worktree_root / ".venv").resolve() == (main_root / ".venv").resolve()


def test_ec_11_already_linked_symlink_is_left_alone(tmp_path: Path) -> None:
    main_root = tmp_path / "main"
    (main_root / ".fixtures").mkdir(parents=True)
    worktree_root = tmp_path / "worktree"
    worktree_root.mkdir()
    (worktree_root / ".fixtures").symlink_to(main_root / ".fixtures", target_is_directory=True)
    before = (worktree_root / ".fixtures").lstat()

    results = link_shared(worktree_root, main_root, names=(".fixtures",))

    assert results == [LinkResult(name=".fixtures", action="already_linked")]
    after = (worktree_root / ".fixtures").lstat()
    assert before == after


def test_ec_12_existing_real_directory_is_left_untouched_with_warning(tmp_path: Path, capsys) -> None:
    main_root = tmp_path / "main"
    (main_root / ".venv").mkdir(parents=True)
    worktree_root = tmp_path / "worktree"
    (worktree_root / ".venv").mkdir(parents=True)
    marker = worktree_root / ".venv" / "marker.txt"
    marker.write_text("real venv, not a symlink")

    results = link_shared(worktree_root, main_root, names=(".venv",))

    assert results == [LinkResult(name=".venv", action="skipped_exists")]
    assert not (worktree_root / ".venv").is_symlink()
    assert marker.read_text() == "real venv, not a symlink"
    captured = capsys.readouterr()
    assert captured.err != ""


def test_ec_13_missing_source_is_skipped_without_warning_or_write(tmp_path: Path, capsys) -> None:
    main_root = tmp_path / "main"
    main_root.mkdir()
    worktree_root = tmp_path / "worktree"
    worktree_root.mkdir()

    results = link_shared(worktree_root, main_root, names=(".venv",))

    assert results == [LinkResult(name=".venv", action="skipped_source_missing")]
    assert not (worktree_root / ".venv").exists()
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


def test_ec_14_ordinary_checkout_inside_main_worktree_is_a_no_op(monkeypatch, tmp_path: Path) -> None:
    git_dir = tmp_path / "repo" / ".git"
    git_dir.mkdir(parents=True)

    responses = {
        ("rev-parse", "--git-dir"): str(git_dir),
        ("rev-parse", "--git-common-dir"): str(git_dir),
    }
    calls = []

    def fake_run(command, capture_output, text, check):
        calls.append(command)
        args = tuple(command[1:])
        return link_worktree_shared.subprocess.CompletedProcess(
            command, 0, responses[args] + "\n", ""
        )

    link_shared_calls = []
    original_link_shared = link_worktree_shared.link_shared

    def spy_link_shared(*args, **kwargs):
        link_shared_calls.append((args, kwargs))
        return original_link_shared(*args, **kwargs)

    monkeypatch.setattr(link_worktree_shared.subprocess, "run", fake_run)
    monkeypatch.setattr(link_worktree_shared, "link_shared", spy_link_shared)

    exit_code = link_worktree_shared.main([])

    assert exit_code == 0
    assert link_shared_calls == []
    assert calls == [("git", "rev-parse", "--git-dir"), ("git", "rev-parse", "--git-common-dir")]


def test_main_linked_worktree_actually_links_shared_dirs(monkeypatch, tmp_path: Path, capsys) -> None:
    main_root = tmp_path / "main"
    (main_root / ".venv").mkdir(parents=True)
    (main_root / ".fixtures").mkdir(parents=True)
    git_common_dir = main_root / ".git"
    git_common_dir.mkdir()

    worktree_root = tmp_path / "worktree"
    worktree_root.mkdir()
    git_dir = git_common_dir / "worktrees" / "feature"
    git_dir.mkdir(parents=True)

    responses = {
        ("rev-parse", "--git-dir"): str(git_dir),
        ("rev-parse", "--git-common-dir"): str(git_common_dir),
        ("rev-parse", "--show-toplevel"): str(worktree_root),
    }

    def fake_run(command, capture_output, text, check):
        args = tuple(command[1:])
        return link_worktree_shared.subprocess.CompletedProcess(
            command, 0, responses[args] + "\n", ""
        )

    monkeypatch.setattr(link_worktree_shared.subprocess, "run", fake_run)

    exit_code = link_worktree_shared.main([])

    assert exit_code == 0
    assert (worktree_root / ".venv").is_symlink()
    assert (worktree_root / ".venv").resolve() == (main_root / ".venv").resolve()
    assert (worktree_root / ".fixtures").is_symlink()
    assert (worktree_root / ".fixtures").resolve() == (main_root / ".fixtures").resolve()
    captured = capsys.readouterr()
    assert "linked .fixtures" in captured.out
    assert "linked .venv" in captured.out


def test_ec_15_link_shared_guards_worktree_root_equal_main_root_directly(tmp_path: Path) -> None:
    same_root = tmp_path / "repo"
    (same_root / ".venv").mkdir(parents=True)
    (same_root / ".fixtures").mkdir(parents=True)
    before_venv = (same_root / ".venv").lstat()
    before_fixtures = (same_root / ".fixtures").lstat()

    results = link_shared(same_root, same_root, names=(".fixtures", ".venv"))

    assert results == [
        LinkResult(name=".fixtures", action="skipped_main"),
        LinkResult(name=".venv", action="skipped_main"),
    ]
    assert (same_root / ".venv").lstat() == before_venv
    assert (same_root / ".fixtures").lstat() == before_fixtures
    assert not (same_root / ".venv").is_symlink()
    assert not (same_root / ".fixtures").is_symlink()


def test_worktree_root_equal_main_root_handles_nonexistent_paths_without_touching_filesystem() -> None:
    same_root = Path("/repo")
    results = link_shared(same_root, same_root, names=(".fixtures", ".venv"))
    assert results == [
        LinkResult(name=".fixtures", action="skipped_main"),
        LinkResult(name=".venv", action="skipped_main"),
    ]
