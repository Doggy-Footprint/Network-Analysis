#!/bin/sh
# usage: verify.sh <repo> <pid>  — independent gate rerun, measurement, comparison and verdict for one point
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY="$ROOT/eval/.venv/bin/python"
git -C "$ROOT/eval/repos/$1" switch -q "eval/$2"
"$PY" "$ROOT/scripts/eval/gate.py" "$1" --label "$2-eval" > /dev/null
"$PY" "$ROOT/scripts/eval/measure.py" "$1" "$2" --rev "eval/$2" > "$ROOT/eval/results/$1/measure-$2.log" 2>&1
"$PY" "$ROOT/scripts/eval/compare.py" "$1" "$2" > /dev/null
"$PY" "$ROOT/scripts/eval/judge.py" "$1" "$2"
