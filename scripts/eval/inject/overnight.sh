#!/bin/sh
# caffeinate keeps the Mac awake; tasks that failed for network reasons are not cached, so the second pass retries them.
set -e
cd "$(dirname "$0")/../../.."
REPO="${1:-CTFd}"
W="$HOME/toy-projects/network-analysis-eval/inject/$REPO"
for pass in 1 2; do
  caffeinate -i .venv/bin/python scripts/eval/inject/harness.py run "$REPO" --replicates "${2:-1}" --negatives "${3:-4}" --workers 3 >> "$W/overnight.log" 2>&1
done
.venv/bin/python scripts/eval/inject/harness.py score "$REPO" > "$W/score.txt"
