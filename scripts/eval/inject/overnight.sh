#!/bin/sh
# usage: overnight.sh "CTFd flask-admin ghostfolio nowinandroid" [replicates] [negatives] ["extra run flags", e.g. "--fraction 3"]
# caffeinate keeps the Mac awake; tasks that failed for network reasons are not cached, so the second pass retries them.
# Repositories run one after another so test gates never compete for the CPU.
set -e
cd "$(dirname "$0")/../../.."
for REPO in ${1:-CTFd}; do
  W="$HOME/toy-projects/network-analysis-eval/inject/$REPO"
  for pass in 1 2; do
    caffeinate -i .venv/bin/python scripts/eval/inject/harness.py run "$REPO" --replicates "${2:-1}" --negatives "${3:-4}" --workers 3 ${4:-} >> "$W/overnight.log" 2>&1
  done
  .venv/bin/python scripts/eval/inject/harness.py score "$REPO" > "$W/score.txt"
done
