import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.file_analysis_support import CHARACTERIZATION_FILES, characterization, snapshot

calls = Counter()
texts = {}
original = re.finditer


def observe(pattern, string, *args, **kwargs):
    expression = getattr(pattern, "pattern", pattern)
    if isinstance(string, str) and (expression == r"\w+" or str(expression).startswith(r"\b")):
        digest = hashlib.sha256(string.encode()).hexdigest()
        texts[digest] = [path for path, text in CHARACTERIZATION_FILES.items()
                         if string in (text, "\n".join(text.splitlines()))]
        calls[(expression, digest)] += 1
    return original(pattern, string, *args, **kwargs)


re.finditer = observe
try:
    actual = characterization()
finally:
    re.finditer = original

directory = Path(__file__).parent
baseline = json.loads((directory / "baseline-small-relations.json").read_text())
assert actual == baseline, "Small raw relation characterization changed"
known_calls = [(pattern, digest, count) for (pattern, digest), count in calls.items() if texts[digest]]
assert known_calls and all(count == 1 for _, _, count in known_calls), "Repeated whole-file name scan"
snap = snapshot(CHARACTERIZATION_FILES)
mutable = snap.content_map()
mutable.clear()
assert snap.content_map() == CHARACTERIZATION_FILES
assert snap.source_map is snap.source_map and snap.source_lines is snap.source_lines
text = next(iter(snap.source_map.values()))
assert text.span_text(0, 2) == "\n".join(str(text).splitlines()[:2])
before = len(text.ranges)
assert text.span_text(0, 2) == "\n".join(str(text).splitlines()[:2])
assert len(text.ranges) == before
try:
    snap.source_map["injected"] = "bad"
except TypeError:
    pass
else:
    raise AssertionError("Internal snapshot lookup is mutable")

paths = ["repository/models.py", "language_analyzers/core/positions.py", "language_analyzers/core/enrichment.py",
         "language_analyzers/kotlin/analyzer.py", "language_analyzers/core/cost.py", "code_analyzer/cli.py",
         "analysis/file_graph.py", "analysis/graph_metrics.py", "bottlenecks/core.py", "README.md"]
result = {
    "spec_version": 2,
    "small_raw_relations_equal": True,
    "scan_rows": [{"pattern": pattern, "text_sha256": digest, "input_paths": texts[digest], "whole_text_scans": count}
                  for pattern, digest, count in sorted(known_calls)],
    "whole_text_scan_max": max(count for _, _, count in known_calls),
    "public_content_map_independent": True,
    "source_lookup_readonly_reused": True,
    "source_lines_reused": True,
    "source_range_reused": True,
    "reviewed_revision_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths},
    "procedure": ".venv/bin/python tests/file_analysis_evidence/scan-cache-review.py",
}
(directory / "scan-cache-review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"small_equal": True, "scan_rows": len(known_calls), "max_scans": result["whole_text_scan_max"]}))
