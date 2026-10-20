#!/bin/bash
# run.sh <worktree> <tag> <outdir>
REPO=/home/user/Network-Analysis; wt=$1; tag=$2; OUT=$3; mkdir -p $OUT
fr() { (cd $REPO && uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; print(fixture_root('$1').resolve())"); }
for spec in "nestjs:typescript-nestjs-realworld:-l typescript -f nestjs" "android:android-nowinandroid:-l kotlin" "futurama:futuramaapi:-l python" "realworld:fastapi-realworld:-l python" "template:fastapi-official-template:-l python"; do
  name=${spec%%:*}; rest=${spec#*:}; fx=${rest%%:*}; flags=${rest#*:}; path=$(fr $fx)
  for g in file symbol; do
    (cd $wt && PYTHONHASHSEED=0 uv run -q --with-requirements $REPO/requirements-dev.txt python -c 'from code_analyzer.cli import main; main()' "$path" $flags --granularity $g --json -o $OUT/$tag-$name-$g.html --bottlenecks $OUT/$tag-$name-$g.bottlenecks.json >/dev/null) || echo FAIL $name $g
  done
done
