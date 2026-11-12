"""Hand mutations (spec 338f748639b68776). Each mutation replaces one unique snippet, runs the new test files, and restores the file.
pytest -x under xdist exits 2 (Interrupted) after a failure, so 1 and 2 both count when a FAILED line exists.
usage: python run_mutations.py <repo root>"""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(sys.argv[1])
TESTS = ["tests/test_symbol_changes.py", "tests/test_unreferenced_symbol.py", "tests/test_unprovided_injection.py", "tests/test_delta.py", "tests/test_rename_delta.py"]
MUTATIONS = [
    ("M01 report rule or->and", "bottlenecks/delta.py", 'return symbol.get("visibility") != "private" or refs', 'return symbol.get("visibility") != "private" and refs'),
    ("M02 changed uses current refs", "bottlenecks/delta.py", "and _reported(after, before):", "and _reported(after, after):"),
    ("M03 skipped reason priority swapped", "bottlenecks/delta.py",
     '    if "symbols" not in baseline: return {"status": "skipped", "reason": "baseline_without_symbols"}, [], []\n    if "symbols" not in current: return {"status": "skipped", "reason": "current_without_symbols"}, [], []',
     '    if "symbols" not in current: return {"status": "skipped", "reason": "current_without_symbols"}, [], []\n    if "symbols" not in baseline: return {"status": "skipped", "reason": "baseline_without_symbols"}, [], []'),
    ("M04 symbol ids not rename-mapped", "bottlenecks/delta.py", "for row in network[\"symbols\"]: row[position] = fix(row[position])", "for row in network[\"symbols\"]: pass"),
    ("M05 self edge counts as reference", "bottlenecks/symbols.py", "            if target == source:\n                continue\n", ""),
    ("M06 framework IMPLEMENTED_BY ignored", "bottlenecks/symbols.py", ' or node["id"] in implemented:', ":"),
    ("M07 modifier after name counts", "bottlenecks/symbols.py", "        if word == name or word.endswith(\".\" + name):\n            break\n", ""),
    ("M08 same-file source counted external", "bottlenecks/symbols.py", "if source_file is not None and source_file != node_files[target]:", "if source_file is not None:"),
    ("M09 global modules ignored", "bottlenecks/nestjs_visibility.py", 'if nestjs[module]["metadata"].get("global"):', "if False:"),
    ("M10 re-export not followed", "bottlenecks/nestjs_visibility.py", "                pending.append(target)\n", "                pass\n"),
    ("M11 unsupported fields ignored", "bottlenecks/nestjs_visibility.py", 'certain = not any(nestjs[module]["metadata"].get("unsupported_fields") for module in missing)', "certain = True"),
    ("M12 consumer/provider ids not rename-mapped", "bottlenecks/delta.py", 'for key in ("from_id", "to_id", "node_id", "consumer_id", "provider_id"):', 'for key in ("from_id", "to_id", "node_id"):'),
    ("M13 uncertain_count not a strength metric", "bottlenecks/delta.py", '"unprovided_injection": ("unprovided_count", "uncertain_count")}', '"unprovided_injection": ("unprovided_count",)}'),
    ("M14 recorded only when invisible in every module", "bottlenecks/nestjs_visibility.py", "            if not missing:\n", "            if len(missing) != len(homes_of):\n"),
    ("M15 certainty from all consumer modules", "bottlenecks/nestjs_visibility.py", 'for module in missing)', 'for module in homes_of)'),
]


def main():
    results = []
    for name, rel, old, new in MUTATIONS:
        path = ROOT / rel
        original = path.read_text()
        if original.count(old) != 1:
            results.append({"mutation": name, "status": "inconclusive: snippet not unique"}); continue
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
