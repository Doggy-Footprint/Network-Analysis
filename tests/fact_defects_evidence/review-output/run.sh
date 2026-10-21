set -e
REPO=/home/user/Network-Analysis
S=/tmp/claude-0/-home-user-Network-Analysis/78de8046-135c-5ea8-a78c-b69b67d2d488/scratchpad
BASE=$S/review-base; OUT=$S/review-out
rm -rf $BASE $OUT; mkdir -p $OUT
git -C $REPO worktree add -q --detach $BASE b590d5461c59d93db7800f9be451392f367b8db0
NEST=$(cd $REPO && python3 -c "from fixtures.registry import fixture_root; print(fixture_root('typescript-nestjs-realworld').resolve())")
ANDROID=$(cd $REPO && python3 -c "from fixtures.registry import fixture_root; print(fixture_root('android-nowinandroid').resolve())")
run() { wt=$1; tag=$2; name=$3; path=$4; shift 4
  for g in file symbol; do
    (cd $wt && PYTHONHASHSEED=0 python3 -c 'from code_analyzer.cli import main; main()' "$path" "$@" --granularity $g --json -o $OUT/$tag-$name-$g.html --bottlenecks $OUT/$tag-$name-$g.bottlenecks.json >/dev/null)
  done; }
for tag_wt in "base:$BASE" "head:$REPO"; do
  run ${tag_wt#*:} ${tag_wt%%:*} nestjs "$NEST" -l typescript -f nestjs
  run ${tag_wt#*:} ${tag_wt%%:*} android "$ANDROID" -l kotlin
done
for name in nestjs android; do for g in file symbol; do
  echo "######## $name $g"
  python3 $REPO/tests/fact_defects_evidence/review_diff.py $OUT/base-$name-$g.json $OUT/head-$name-$g.json --root $( [ $name = nestjs ] && echo $NEST || echo $ANDROID ) --base-bottlenecks $OUT/base-$name-$g.bottlenecks.json --head-bottlenecks $OUT/head-$name-$g.bottlenecks.json --seed 20261019 --sample 10 > $OUT/review-$name-$g.txt 2>&1 || echo "review_diff rc=$?"
done; done
python3 $REPO/tests/fact_defects_evidence/review-output/sample_check.py $OUT $NEST $ANDROID 20261019 > $OUT/sample-check.txt
git -C $REPO worktree remove --force $BASE
echo DONE
