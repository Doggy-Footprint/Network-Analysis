#!/bin/sh
# caffeinate keeps the Mac awake; the run is resumable, so rerunning skips finished tasks.
set -e
cd "$(dirname "$0")/../../.."
W="$HOME/toy-projects/network-analysis-eval/inject/${1:-CTFd}"
caffeinate -i .venv/bin/python scripts/eval/inject/harness.py run "${1:-CTFd}" --replicates "${2:-1}" --negatives "${3:-4}" --workers 3 >> "$W/overnight.log" 2>&1
.venv/bin/python scripts/eval/inject/harness.py score "${1:-CTFd}" > "$W/score.txt"
