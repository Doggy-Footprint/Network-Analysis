#!/usr/bin/env python3
"""Symlinks shared, gitignored directories (.fixtures, .venv) from the main
worktree into a newly created linked worktree, so `git worktree add` doesn't
force a fresh fixture clone / venv install per worktree.

Invoked by .githooks/post-checkout (via core.hooksPath) and by
scripts/link-worktree-shared.sh for worktrees created before the hook existed.
See contracts/fixture-unification.md.
"""
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

Action = Literal[
    "linked", "already_linked", "skipped_exists",
    "skipped_source_missing", "skipped_main",
]


@dataclass(frozen=True)
class LinkResult:
    name: str
    action: Action


def is_main_worktree(git_dir: Path, git_common_dir: Path) -> bool:
    return Path(git_dir).resolve() == Path(git_common_dir).resolve()


def main_worktree_root(git_common_dir: Path) -> Path:
    return Path(git_common_dir).resolve().parent


def link_shared(
    worktree_root: Path,
    main_root: Path,
    names: Sequence[str] = (".fixtures", ".venv"),
) -> list:
    worktree_root = Path(worktree_root)
    main_root = Path(main_root)

    if worktree_root.resolve() == main_root.resolve():
        return [LinkResult(name=name, action="skipped_main") for name in names]

    results = []
    for name in names:
        source = main_root / name
        target = worktree_root / name

        if not source.exists():
            results.append(LinkResult(name=name, action="skipped_source_missing"))
            continue

        if target.is_symlink():
            if target.resolve() == source.resolve():
                results.append(LinkResult(name=name, action="already_linked"))
            else:
                print(
                    f"link_worktree_shared: {target} is a symlink to something other than "
                    f"{source}, leaving untouched",
                    file=sys.stderr,
                )
                results.append(LinkResult(name=name, action="skipped_exists"))
            continue

        if target.exists():
            print(
                f"link_worktree_shared: {target} already exists and is not a symlink, "
                "leaving untouched",
                file=sys.stderr,
            )
            results.append(LinkResult(name=name, action="skipped_exists"))
            continue

        target.symlink_to(source, target_is_directory=source.is_dir())
        results.append(LinkResult(name=name, action="linked"))

    return results


def _git_output(*args: str) -> str:
    completed = subprocess.run(("git", *args), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise RuntimeError(detail)
    return completed.stdout.strip()


def main(argv: Sequence[str] = sys.argv[1:]) -> int:
    try:
        git_dir = Path(_git_output("rev-parse", "--git-dir")).resolve()
        git_common_dir = Path(_git_output("rev-parse", "--git-common-dir")).resolve()
        if is_main_worktree(git_dir, git_common_dir):
            return 0
        worktree_root = Path(_git_output("rev-parse", "--show-toplevel")).resolve()
        main_root = main_worktree_root(git_common_dir)
        for result in link_shared(worktree_root, main_root):
            if result.action == "linked":
                print(f"link_worktree_shared: linked {result.name} from {main_root}")
    except Exception as exc:
        print(f"link_worktree_shared: skipping ({exc})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
