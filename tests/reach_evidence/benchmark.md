# V10 benchmark (Q2)

Command: `uv run -q --with-requirements requirements-dev.txt python -m pytest -q -p no:cacheprovider -m benchmark -s tests/test_reach_candidates.py`
Measure: end-to-end CLI wall-clock, file granularity, median of 3 after a warm-up; base is a temporary worktree at 6444895.

| fixture | base median (s) | new median (s) | ratio | threshold |
| --- | --- | --- | --- | --- |
| fastapi-realworld | 0.677 | 0.644 | 0.950 | ≤ 1.10 |
| typescript-nestjs-realworld | 0.778 | 0.751 | 0.965 | ≤ 1.10 |

Result: pass.
