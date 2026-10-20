"""Property fuzz for spec e91abc221d7deb2a. Surface A: random temp projects per language whose call
forms each have a known R1 class (boundary or external), counted per node independently of the
analyzers; each project gets a broken extra file with probability 0.1. Surface B: random weighted
graphs checked against R7 properties and the pre-change definition for all-1.0 weights.
Usage: fuzz_signal.py [--seed 20261020] [--budget 1000] [--graphs 2000] [--lang python,typescript,kotlin]
"""
import argparse
import os
import random
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, os.getcwd())
from analysis.graph_metrics import GraphAnalysisConfig, pagerank  # noqa: E402
from language_analyzers.kotlin.analyzer import KotlinAnalyzer  # noqa: E402
from language_analyzers.python.graph import PythonGraphAnalyzer  # noqa: E402
from language_analyzers.typescript.analyzer import TypeScriptAnalyzer  # noqa: E402

B, X = "boundary", "external"

# Snippet templates; {u} is replaced with a fresh name no project symbol uses.
PY_FORMS = [("len(x)", X, False), ("requests.u{u}()", X, False), ("x.u{u}()", X, False),
            ("os.path.u{u}(x)", X, False), ("mb.u{u}()", B, False), ("gone()", B, False),
            ("Closed.u{u}()", B, False), ("Open.u{u}()", X, False)]
PY_SELF = {"closed": ("self.u{u}()", B), "open": ("self.u{u}()", X)}

TS_FORMS = [("parseInt(x)", X), ("axios.u{u}()", X), ("x.u{u}()", X), ("mb.u{u}()", B), ("gone()", B),
            ("new Ext()", X), ("console.log(x)", X)]
TS_THIS = {"closed": ("this.u{u}()", B), "open": ("this.u{u}()", X)}

KT_FORMS = [("println(x)", X), ("listOf(1)", X), ("x.u{u}()", X), ("gone()", B), ("Thing.u{u}()", X)]


def counts(node):
    meta = node.metadata or {}
    boundary = meta.get("unresolved_reference_total", len(meta.get("unresolved_references", [])))
    return boundary, meta.get("external_call_count", 0)


def body(rng, forms, counter, indent):
    lines, tally = [], {B: 0, X: 0}
    for _ in range(rng.randint(0, 4)):
        form = rng.choice(forms)
        counter[0] += 1
        lines.append(indent + form[0].format(u=counter[0]))
        tally[form[1]] += 1
    return lines, (tally[B], tally[X])


def py_case(rng):
    counter, expected = [0], {}
    lines = ["import os", "import requests", "import pkg.b as mb", "from pkg.b import Closed, Open, gone", ""]
    for i in range(rng.randint(1, 3)):
        stmts, tally = body(rng, PY_FORMS, counter, "    ")
        lines += [f"def f{i}(x):"] + (stmts or ["    pass"]) + [""]
        expected[f"f{i}"] = tally
    for i, kind in enumerate(rng.sample(["closed", "open"], rng.randint(0, 2))):
        base = "Closed" if kind == "closed" else "Open"
        stmts, tally = body(rng, [(PY_SELF[kind][0], PY_SELF[kind][1], False)], counter, "        ")
        lines += [f"class K{i}({base}):", f"    def g{i}(self, x):"] + (stmts or ["        pass"]) + [""]
        expected[f"g{i}"] = tally
    files = {
        "pkg/__init__.py": "",
        "pkg/b.py": "from extlib import ExtBase\n\n\nclass Closed:\n    def keep(self):\n        return 1\n\n\nclass Open(ExtBase):\n    pass\n",
        "pkg/a.py": "\n".join(lines) + "\n",
    }
    return files, expected


def py_check(root, expected):
    arch = PythonGraphAnalyzer(str(root)).analyze()
    problems = []
    for name, want in expected.items():
        nodes = [n for n in arch.nodes if n.label == name and n.kind != "module"]
        got = counts(nodes[0]) if len(nodes) == 1 else None
        if got != want:
            problems.append((name, want, got))
    return problems


def ts_case(rng):
    counter, expected = [0], {}
    lines = ["import * as mb from './b';", "import { Closed, Open, gone } from './b';",
             "import axios from 'axios';", "import { Ext } from 'extlib';", ""]
    for i in range(rng.randint(1, 3)):
        stmts, tally = body(rng, TS_FORMS, counter, "  ")
        lines += [f"export function f{i}(x: any) {{"] + [s + ";" for s in stmts] + ["}", ""]
        expected[f"f{i}"] = tally
    for i, kind in enumerate(rng.sample(["closed", "open"], rng.randint(0, 2))):
        base = "Closed" if kind == "closed" else "Open"
        stmts, tally = body(rng, [TS_THIS[kind]], counter, "    ")
        lines += [f"export class K{i} extends {base} {{", f"  g{i}(x: any) {{"] + [s + ";" for s in stmts] + ["  }", "}", ""]
        expected[f"g{i}"] = tally
    files = {
        "src/b.ts": "import { ExtBase } from 'extlib';\nexport class Closed {\n  keep() { return 1; }\n}\nexport class Open extends ExtBase {}\n",
        "src/a.ts": "\n".join(lines) + "\n",
    }
    return files, expected


def ts_check(root, expected):
    arch = TypeScriptAnalyzer(str(root)).analyze()
    problems = []
    for name, want in expected.items():
        nodes = [n for n in arch.nodes if n.label == name or n.id.endswith(f".{name}") or n.id.endswith(f"#{name}")]
        nodes = [n for n in nodes if "src/a.ts" in n.id]
        got = counts(nodes[0]) if len(nodes) == 1 else None
        if got != want:
            problems.append((name, want, got, [n.id for n in nodes]))
    return problems


def kt_case(rng):
    counter, expected = [0], {}
    lines = ["package com.proj.a", "", "import com.proj.b.gone", "import org.ext.Thing", ""]
    for i in range(rng.randint(1, 3)):
        stmts, tally = body(rng, KT_FORMS, counter, "    ")
        lines += [f"fun f{i}(x: Any) {{"] + stmts + ["}", ""]
        expected[f"f{i}"] = tally
    files = {"com/proj/b/B.kt": "package com.proj.b\n\nfun helper() {}\n",
             "com/proj/a/A.kt": "\n".join(lines) + "\n"}
    return files, expected


def kt_check(root, expected):
    arch = KotlinAnalyzer(str(root)).analyze()
    problems = []
    for name, want in expected.items():
        nodes = [n for n in arch.nodes if n.label == name]
        got = counts(nodes[0]) if len(nodes) == 1 else None
        if got != want:
            problems.append((name, want, got))
    return problems


BROKEN = {
    "python": ("pkg/broken.py", "def (:\n    len(x\n"),
    "typescript": ("src/zz.ts", "const = ;\nmb.u0(;\n"),
    "kotlin": ("com/proj/a/Z.kt", "package com.proj.a\nfun ( {\n    gone()\n"),
}
LANGS = {"python": (py_case, py_check), "typescript": (ts_case, ts_check), "kotlin": (kt_case, kt_check)}


def old_pagerank(outgoing, settings):
    count = len(outgoing)
    totals = {n: sum(t.values()) for n, t in outgoing.items()}
    scores = {n: 1.0 / count for n in outgoing}
    base = (1.0 - settings.damping) / count
    for _ in range(settings.max_iterations):
        dangling = sum(scores[n] for n, t in outgoing.items() if not t)
        updated = {n: base + settings.damping * dangling / count for n in outgoing}
        for s, t in outgoing.items():
            for d, w in t.items():
                updated[d] += settings.damping * scores[s] * w / totals[s]
        done = sum(abs(updated[i] - scores[i]) for i in scores) <= settings.tolerance
        scores = updated
        if done:
            break
    return scores


def graph_case(rng):
    nodes = [f"n{i}" for i in range(rng.randint(1, 30))]
    graph = {n: {} for n in nodes}
    for n in nodes:
        for t in rng.sample(nodes, rng.randint(0, min(4, len(nodes)))):
            if t != n:
                graph[n][t] = rng.choice([1.0, 0.3, rng.uniform(0.01, 1.0)])
    return graph


def graph_check(rng, graph):
    problems = []
    settings = GraphAnalysisConfig(tolerance=1e-14, max_iterations=1000)
    scores = pagerank(graph, settings)
    if abs(sum(scores.values()) - 1.0) > 1e-9:
        problems.append(("sum", sum(scores.values())))
    if any(v <= 0 for v in scores.values()):
        problems.append(("nonpositive", scores))
    ones = {n: {t: 1.0 for t in ts} for n, ts in graph.items()}
    new_ones, old_ones = pagerank(ones, settings), old_pagerank(ones, settings)
    sets = pagerank({n: set(ts) for n, ts in graph.items()}, settings)
    if any(abs(new_ones[n] - old_ones[n]) > 1e-12 or abs(sets[n] - old_ones[n]) > 1e-12 for n in graph):
        problems.append(("all-ones differs from previous definition",))
    edges = [(s, t) for s, ts in graph.items() for t in ts]
    if edges:
        s, t = rng.choice(edges)
        lowered = {n: dict(ts) for n, ts in graph.items()}
        lowered[s][t] = graph[s][t] * rng.uniform(0.01, 0.99)
        if pagerank(lowered, settings)[t] > scores[t] + 1e-12:
            problems.append(("lowered weight raised target", s, t))
    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--budget", type=int, default=1000)
    parser.add_argument("--graphs", type=int, default=2000)
    parser.add_argument("--lang", default="python,typescript,kotlin")
    args = parser.parse_args()
    violations = executions = 0
    for lang in args.lang.split(","):
        rng = random.Random(f"{args.seed}:{lang}")
        case, check = LANGS[lang]
        for index in range(args.budget):
            files, expected = case(rng)
            if rng.random() < 0.1:
                files[BROKEN[lang][0]] = BROKEN[lang][1]
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for rel, text in files.items():
                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
                    (root / rel).write_text(text)
                try:
                    problems = check(root, expected)
                except Exception:
                    problems = [("exception", traceback.format_exc())]
            executions += 1
            if problems:
                violations += 1
                print(f"VIOLATION {lang} #{index}: {problems}\n--- files ---\n{files}", flush=True)
        print(f"{lang}: {args.budget} projects done", flush=True)
    rng = random.Random(f"{args.seed}:pagerank")
    for index in range(args.graphs):
        graph = graph_case(rng)
        try:
            problems = graph_check(rng, graph)
        except Exception:
            problems = [("exception", traceback.format_exc())]
        executions += 1
        if problems:
            violations += 1
            print(f"VIOLATION pagerank #{index}: {problems}\n{graph}", flush=True)
    print(f"executions={executions} violations={violations}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
