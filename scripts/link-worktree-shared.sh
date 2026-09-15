#!/usr/bin/env bash
# Manual repair: symlinks shared, gitignored directories (.fixtures, .venv)
# from the main worktree into the current worktree. Use this for worktrees
# created before the post-checkout hook was installed, or when
# core.hooksPath isn't configured yet.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"

python3 "$repo_root/.githooks/link_worktree_shared.py"
