"""A mutation counts as killed only when a test of its expected obligation fails."""
import json
import subprocess
import sys

SYMBOL_DIRS = "directories = {posixpath.dirname(path) for path in paths} - ({posixpath.dirname(own)} if own is not None else set())"
MUTATIONS = [
    ("M1", "bottlenecks/core.py", "if len(directories) > 1 or (len(paths) == 1 and span > threshold): candidates.append(",
     "if len(paths) > 1 or (len(paths) == 1 and span > threshold): candidates.append(", "R11 file count kept as trigger (symbol)", "V1"),
    ("M2", "bottlenecks/core.py", SYMBOL_DIRS, "directories = {posixpath.dirname(path) for path in paths}",
     "R11 target directory not excluded (symbol)", "V1"),
    ("M3", "bottlenecks/core.py", "directories = {posixpath.dirname(path) for path in paths} - {posixpath.dirname(own)}",
     "directories = {posixpath.dirname(path) for path in paths}", "R11 target directory not excluded (file)", "V2"),
    ("M4", "bottlenecks/core.py", "            if len(directories) > 1 or (len(paths) == 1 and span > threshold):",
     "            if len(directories) > 1 or (len(paths) == 1 and span >= threshold):", "R11 single-file range boundary off by one (file)", "V2"),
    ("M5", "bottlenecks/core.py", '{"file_count": len(paths), "directory_count": len(directories), "line_span": span, "line_threshold": threshold}, [evidence_record',
     '{"file_count": len(paths), "directory_count": len(paths), "line_span": span, "line_threshold": threshold}, [evidence_record',
     "R11 directory_count reports files (symbol)", "V1"),
    ("M6", "report/bottlenecks/generate.py", '"evidence_spread": ("directory_count", 0),', '"evidence_spread": ("file_count", 0),',
     "R11r report ranks by file_count", "V3"),
    ("M7", "language_analyzers/kotlin/ast.py", '        if child.type == "ERROR":\n            members.extend(',
     '        if child.type == "ERROR" and False:\n            members.extend(', "R12 (A) ERROR-wrapped members ignored", "V4"),
    ("M8", "language_analyzers/kotlin/ast.py", "child.type in _MEMBER_TYPES or recovered_object_members(child) is not None)",
     "child.type in _MEMBER_TYPES)", "R12 (B) nested recovered object ignored", "V4"),
    ("M9", "language_analyzers/kotlin/analyzer.py", 'self._collect_field(key, field_name, f"{qualname}.{field_name}", parameter_node, symbol_id)',
     'self._collect_field(key, field_name, f"{qualname}.{field_name}", constructor, symbol_id)', "R13 field scans whole constructor", "V5"),
    ("M10", "bottlenecks/core.py", '{"analysis": "6"}', '{"analysis": "5"}', "R14 version not bumped", "V7"),
    ("M11", "bottlenecks/core.py", SYMBOL_DIRS, 'directories = {posixpath.dirname(path) for path in paths} - {posixpath.dirname(own or "")}',
     "R11 file-less target treated as root directory (verifier VF1-F1)", "V1"),
    ("T15", "bottlenecks/core.py", 'records, "static_analyzer_relation"))\n    return sorted(candidates, key=lambda item: (item["kind"], item["id"]))',
     'records, "static_analyzer_relation_x"))\n    return sorted(candidates, key=lambda item: (item["kind"], item["id"]))',
     "tool mutants 15/27 re-applied after correction batch 1 (file-mode candidate coverage label)", "V2"),
    ("T16", "language_analyzers/kotlin/analyzer.py", 'symbol.node.type == "infix_expression" else', 'symbol.node.type == "infix_expression_x" else',
     "tool mutant 16 re-applied after correction batch 1 (recovered object signature)", "V4"),
]

TEST = ["uv", "run", "-q", "--with-requirements", "requirements-dev.txt", "python", "-m", "pytest", "-q", "-rfE",
        "-p", "no:cacheprovider", "tests/test_signal_defects_round4.py"]


def main():
    results = []
    for mid, path, old, new, defect, obligation in [m for m in MUTATIONS if len(sys.argv) < 3 or m[0] in sys.argv[2].split(",")]:
        text = open(path).read()
        if text.count(old) != 1:
            results.append({"id": mid, "defect": defect, "result": "inconclusive", "reason": f"anchor count {text.count(old)}"})
            print(mid, "inconclusive anchor", flush=True)
            continue
        subprocess.run(["python3", ".harness/bin/seed.py", "backup", path], check=True)
        try:
            open(path, "w").write(text.replace(old, new))
            done = subprocess.run(TEST, capture_output=True, text=True, timeout=1800)
            failed = sorted({line.split(" ")[1].split("::")[1].split("[")[0] for line in done.stdout.splitlines() if line.startswith(("FAILED ", "ERROR "))})
            crashed = any(line.startswith("ERROR ") for line in done.stdout.splitlines())
            killed = any(name.startswith(f"test_{obligation}_") for name in failed)
            results.append({"id": mid, "file": path, "defect": defect, "obligation": obligation,
                            "result": "inconclusive" if crashed else "killed" if killed else ("inconclusive" if done.returncode not in (0, 1) else "survived"),
                            "failed_tests": failed})
        finally:
            subprocess.run(["python3", ".harness/bin/seed.py", "restore"], check=True)
        print(results[-1]["id"], results[-1]["result"], len(results[-1].get("failed_tests", [])), flush=True)
    json.dump(results, open(sys.argv[1], "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
