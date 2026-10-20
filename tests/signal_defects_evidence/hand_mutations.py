"""Hand mutations for spec e91abc221d7deb2a: each injects one strongest defect class, runs the new tests,
and records which tests failed. A mutation counts as killed only when an expected obligation test fails.
Files are backed up and restored with .harness/bin/seed.py. Usage: hand_mutations.py <out.json>
"""
import json
import subprocess
import sys

MUTATIONS = [
    ("M1", "analysis/graph_metrics.py", "share = settings.damping * scores[source] / len(targets)",
     "share = settings.damping * scores[source] / totals[source]", "R7 relative normalization (pre-change)", "V9"),
    ("M2", "analysis/graph_metrics.py", "base + (settings.damping * dangling + residual) / count",
     "base + (settings.damping * dangling) / count", "R7 undelivered mass dropped", "V9"),
    ("M3", "bottlenecks/core.py", "edges = [edge for edge in edges if edge.evidence.file_path != own]",
     "edges = list(edges)", "R5 own-file evidence kept (symbol)", "V7"),
    ("M4", "bottlenecks/core.py", "if record[\"evidence\"][\"file_path\"] != own]",
     "]", "R5 own-file evidence kept (file)", "V7"),
    ("M5", "bottlenecks/core.py", "and not ownership_edge(edge, nodes_by_id)", "", "R5 ownership edges kept", "V7"),
    ("M6", "bottlenecks/core.py", "return total if _valid_int(total) else len(",
     "return len(", "R3 truncated list counted", "V5"),
    ("M7", "bottlenecks/core.py", "if count > threshold or tokens > token_threshold:",
     "if count > threshold or tokens >= token_threshold:", "R8 token boundary off by one (file)", "V10"),
    ("M8", "language_analyzers/python/graph.py", "                    if base is None or base.kind != NodeKind.CLASS:\n                        closed = False\n                        break",
     "                    if base is None or base.kind != NodeKind.CLASS:\n                        continue", "R1 Python open ancestry ignored", "V1"),
    ("M9", "language_analyzers/typescript/analyzer.py", "            return owner is not None and owner.kind == NodeKind.CLASS and self._closed_class(owner)\n        if receiver in locals_:",
     "            return owner is not None and owner.kind == NodeKind.CLASS\n        if receiver in locals_:", "R1 TS this ancestry ignored", "V2"),
    ("M10", "language_analyzers/kotlin/analyzer.py", "for call in ka.call_expressions(symbol.node, source, members):",
     "for call in ka.call_expressions(symbol.node, source, ()):", "R4 Kotlin class scans member calls", "V6"),
    ("M11", "language_analyzers/kotlin/analyzer.py", 'self._imports[key] = [\n            (match.group(1), text.count("\\n", 0, match.start()) + 1)\n            for match in re.finditer(r"^[^\\S\\n]*import',
     'self._imports[key] = [\n            (match.group(1), text.count("\\n", 0, match.start()) + 1)\n            for match in re.finditer(r"^\\s*import', "R9 import line includes blank lines", "V11"),
]

TEST = ["uv", "run", "-q", "--with-requirements", "requirements-dev.txt", "python", "-m", "pytest", "-q",
        "-p", "no:cacheprovider", "tests/test_signal_defects.py"]


def main():
    results = []
    for mid, path, old, new, defect, obligation in [m for m in MUTATIONS if len(sys.argv) < 3 or m[0] in sys.argv[2].split(",")]:
        text = open(path).read()
        if text.count(old) != 1:
            results.append({"id": mid, "defect": defect, "result": "inconclusive", "reason": f"anchor count {text.count(old)}"})
            continue
        subprocess.run(["python3", ".harness/bin/seed.py", "backup", path], check=True)
        try:
            open(path, "w").write(text.replace(old, new))
            done = subprocess.run(TEST, capture_output=True, text=True, timeout=900)
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
