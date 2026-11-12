"""Hand mutations (spec fda1b3f71e2390f3).
pytest -x under xdist exits 2 (Interrupted) after a failure, so 1 and 2 both count when a FAILED line exists.
usage: python run_mutations.py <repo root>"""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(sys.argv[1])
TESTS = ["tests/test_test_signals.py", "tests/test_test_changes_delta.py"]
DELTA, SIGNALS = "bottlenecks/delta.py", "bottlenecks/test_signals.py"
MUTATIONS = [
    ("M01 uncertain reach treated as tested", DELTA, 'or after["test_reach"] == "tested": continue', 'or after["test_reach"] != "untested": continue'),
    ("M02 equal branch count reported", DELTA, 'and after["branches"] > before["branches"])', 'and after["branches"] >= before["branches"])'),
    ("M03 existing-case mock increase threshold 1", DELTA, 'if after["mocks"] - before["mocks"] >= 2:', 'if after["mocks"] - before["mocks"] >= 1:'),
    ("M04 test case ids not rename-mapped", DELTA, "for row in network[\"test_cases\"]: row[position] = fix(row[position])", "for row in network[\"test_cases\"]: pass"),
    ("M05 skipped reason priority swapped", DELTA,
     '    if not _has_test_data(baseline): return {"status": "skipped", "reason": "baseline_without_test_data"}, [], [], []\n    if not _has_test_data(current): return {"status": "skipped", "reason": "current_without_test_data"}, [], [], []',
     '    if not _has_test_data(current): return {"status": "skipped", "reason": "current_without_test_data"}, [], [], []\n    if not _has_test_data(baseline): return {"status": "skipped", "reason": "baseline_without_test_data"}, [], [], []'),
    ("M06 python >= counted strong", SIGNALS, "isinstance(test.ops[0], (ast.Eq, ast.Is))", "isinstance(test.ops[0], (ast.Eq, ast.Is, ast.GtE))"),
    ("M07 jest .not ignored", SIGNALS, "    if negated:\n        return", "    if False:\n        return"),
    ("M08 bool operator counts every operand", SIGNALS, "total += len(node.values) - 1", "total += len(node.values)"),
    ("M09 nested named declarations counted", SIGNALS, "        if kind in _TS_NESTED:\n            continue\n", ""),
    ("M10 resolution ignored for confirmed edges", SIGNALS, 'if edge.get("confidence") in _CONFIRMED_CONFIDENCE and edge.get("resolution") in _CONFIRMED_RESOLUTION:',
     'if edge.get("confidence") in _CONFIRMED_CONFIDENCE:'),
    ("M11 INSTANTIATES does not reach constructors", SIGNALS, "targets = targets + tuple(item for target in targets for item in constructors.get(target, ()))", "pass"),
    ("M12 framework entrypoints ignored", SIGNALS, "            entrypoints.update(targets)\n", "            pass\n"),
    ("M13 jest file-level mocks not counted", SIGNALS, "    top_mocks = mock_total(root)\n", "    top_mocks = 0\n"),
    ("M14 Kotlin class-level skip not inherited", SIGNALS, ' or any(_kt_annotation_names(owner, data) & {"Ignore", "Disabled"} for owner in classes)', ""),
    ("M15 Kotlin check prefix counted strong", SIGNALS, '_KT_PREFIXES = ("assert", "verify", "expect")', '_KT_PREFIXES = ("assert", "verify", "expect", "check")'),
    ("M16 Kotlin object scope not entered", SIGNALS, 'if child.type in ("class_declaration", "object_declaration"):', 'if child.type in ("class_declaration",):'),
    ("M17 Python decorator line does not match", SIGNALS, "            if node.decorator_list:\n                found.setdefault", "            if False:\n                found.setdefault"),
]


def main():
    results = []
    for name, rel, old, new in MUTATIONS:
        path = ROOT / rel
        original = path.read_text()
        if original.count(old) != 1:
            results.append({"mutation": name, "status": "inconclusive: snippet not unique"}); print(json.dumps(results[-1]), flush=True); continue
        path.write_text(original.replace(old, new))
        try:
            proc = subprocess.run(["uv", "run", "-q", "--with-requirements", "requirements-dev.txt", "python", "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *TESTS],
                                  cwd=ROOT, capture_output=True, text=True, timeout=1800)
        finally:
            path.write_text(original)
        failed = [line.split(" ")[1] for line in proc.stdout.splitlines() if line.startswith("FAILED ")]
        summary = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        errors = " error" in summary
        status = "killed" if proc.returncode in (1, 2) and failed and not errors else ("survived" if proc.returncode == 0 else "inconclusive: " + summary)
        results.append({"mutation": name, "status": status, "failed": failed[:3]})
        print(json.dumps(results[-1]), flush=True)
    (Path(__file__).parent / "results.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
