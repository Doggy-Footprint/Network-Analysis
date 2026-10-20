#!/bin/bash
# usage: review_run.sh <code_tree> <outdir>; analyses the base tree's own sources for "self" so input is identical
CODE=$1; OUT=$2; mkdir -p $OUT
FX=/home/user/Network-Analysis/.fixtures
SELF=${SELF:?set SELF to the base worktree path}
targets=("self python $SELF" "nestjs typescript $FX/typescript-nestjs-realworld" "android kotlin $FX/android-nowinandroid" "futurama python $FX/futuramaapi" "fastapirw python $FX/fastapi-realworld")
cd $CODE
for t in "${targets[@]}"; do set -- $t
  for g in file symbol; do
    PYTHONHASHSEED=0 python3 -m code_analyzer -l $2 $3 --granularity $g --json --bottlenecks $OUT/$1-$g.b.json -o $OUT/$1-$g.html >/dev/null 2>$OUT/$1-$g.err || echo "FAIL $1 $g"
  done
done
