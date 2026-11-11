"""Run inside a worktree (cwd, PYTHONPATH=cwd). Prints the Q04 canonical size of android-nowinandroid as test_V13_Q04_size_ratio computes it, with snapshot git keys removed."""
import json, tempfile
from pathlib import Path
from fixtures.registry import fixture_root
import tests.test_delta_integration as t
from tests.android_build_support import without_build_parts
d = Path(tempfile.mkdtemp())
t.run_bottlenecks(fixture_root('android-nowinandroid').resolve(), d, name='android-nowinandroid', rules=None, extra=[])
data = json.loads(t.legacy_bottlenecks_canonical(d / 'b.json', d / 'r.json'))
for k in ('git_commit', 'git_commit_reason'): data.get('snapshot', {}).pop(k, None)
print(len(json.dumps(without_build_parts(data), **t.CANON).encode('utf-8') + b'\n'))
