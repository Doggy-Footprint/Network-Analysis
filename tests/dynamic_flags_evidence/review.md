# Review: dynamic flags (spec f3972ebd2386454f, V10 / Q1)

## Procedure
1. `git worktree add --detach <BASE> 963d70018442629e55c0b7415882357e77e152ae`.
2. `review-output/run.sh <BASE> base <OUT>` and `review-output/run.sh <repo> head <OUT>`: analyzes
   typescript-nestjs-realworld (`-l typescript -f nestjs`), android-nowinandroid (`-l kotlin`), futuramaapi,
   fastapi-realworld, fastapi-official-template (`-l python`) at file and symbol granularity with `--json --bottlenecks`.
3. `python3 review-output/flagdiff.py <OUT>`: per node, flag additions/removals and any non-flag field change;
   multiset edge diff; candidate counts by kind; bottleneck top-level key set and schema.
4. Source scan of each fixture for every R1–R9 construct
   (`require(`, `import(`, `eval(`, `new Function`, `Reflect.`, `Object.defineProperty`, `forName(`, `ServiceLoader`,
   `loadClass`, `getMethod(`/`getField(`/`getDeclared*`, attribute hooks, `__dict__[`, `import_module`, `builtins`).

## Results (`review-output/flagdiff.txt`)
- All 10 runs: 0 node changes, 0 edge changes, identical candidate counts, identical bottleneck key sets and schema.
- Source scan hits: only `src/user/user.service.ts:6 require('jsonwebtoken')` and
  `src/article/article.service.ts:11 require('slug')` in nestjs. Both are literal `require`, which already carried
  `dynamic_import` at base (D1), so R1 adds nothing. No other fixture contains an R1–R9 construct.
- Unexplained changes: 0. Flags at locations without a matching construct: 0.

## Limitation
The real fixtures exercise R1 only through already-flagged literals; positive behaviour of R1–R9 is covered by
`tests/test_dynamic_flags.py` and `fuzz_dynamic.py` (`fuzz-run.log`), not by this review.
