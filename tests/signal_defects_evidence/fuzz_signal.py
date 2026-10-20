"""Property fuzz for spec e91abc221d7deb2a. Surface A: random temp projects per language whose call
forms each have a known R1 class (boundary or external), counted per node independently of the
analyzers; each project gets a broken extra file with probability 0.1. Surface B: random weighted
graphs checked against R7 properties and the pre-change definition for all-1.0 weights.
Usage: fuzz_signal.py [--seed 20261020] [--budget 1000] [--graphs 2000] [--lang python,typescript,kotlin]
Spec 3f70cc03aeae9c1a adds `--round4 [--budget 1000]`: surface C (R11) builds Python projects whose files sit in
random directories and import-and-call one target function, so the expected evidence files and directories are known
by construction; surface D (R12, R13) builds Kotlin files mixing one-line and multi-line object/class bodies and
primary constructors whose default values call known project functions.
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


def _cli_payload(root, granularity, out):
    import code_analyzer.cli as cli
    argv = ["code-analyzer", str(root), "-l", root.lang, "--granularity", granularity, "-o", str(out / f"{granularity}.html"),
            "--bottlenecks", str(out / f"{granularity}.b.json"), "--json"]
    saved = sys.argv
    sys.argv = argv
    try:
        cli.main()
    finally:
        sys.argv = saved
    import json
    return (json.loads((out / f"{granularity}.b.json").read_text()), json.loads((out / f"{granularity}.json").read_text()))


class _Root(type(Path())):
    lang = "python"


def spread_case(rng):
    dirs = rng.sample(["", "a", "b", "c", "a/d", "e"], rng.randint(1, 5))
    count = rng.randint(2, 12)
    paths = []
    for index in range(count):
        directory = rng.choice(dirs)
        paths.append(f"{directory}/m{index}.py" if directory else f"m{index}.py")
    target = paths[0]
    module = target[:-3].replace("/", ".")
    files = {target: "def tgt(x):\n    return x\n"}
    callers = set()
    for path in paths[1:]:
        calls = rng.randint(0, 3)
        if calls:
            callers.add(path)
            files[path] = f"from {module} import tgt\n\n\ndef use(x):\n" + "".join("    tgt(x)\n" for _ in range(calls))
        else:
            files[path] = "def idle(x):\n    return x\n"
    for path in list(files):
        parts = path.split("/")[:-1]
        for depth in range(1, len(parts) + 1):
            files.setdefault("/".join(parts[:depth]) + "/__init__.py", "")
    own = posix_dir(target)
    directories = {posix_dir(path) for path in callers} - {own}
    return files, {"target": target, "files": len(callers), "dirs": len(directories)}


def posix_dir(path):
    return path.rsplit("/", 1)[0] if "/" in path else ""


def spread_check(root, expected):
    problems = []
    with tempfile.TemporaryDirectory() as out:
        for granularity in ("symbol", "file"):
            payload, _arch = _cli_payload(_Root(root), granularity, Path(out))
            # Python symbol ids use the dotted module name, file ids the path
            wanted = "py:" + expected["target"][:-3].replace("/", ".") + "#tgt" if granularity == "symbol" else None
            found = [c for c in payload["candidates"] if c["kind"] == "evidence_spread"
                     and (c["target"] == wanted if wanted else c["target"].endswith(":" + expected["target"]))]
            fire = expected["dirs"] >= 2
            if fire != bool(found):
                problems.append((granularity, "fire", fire, [c["metrics"] for c in found]))
            for candidate in found:
                metrics = candidate["metrics"]
                if (metrics.get("file_count"), metrics.get("directory_count")) != (expected["files"], expected["dirs"]):
                    problems.append((granularity, "metrics", expected, metrics))
                if metrics.get("directory_count", 0) > metrics.get("file_count", 0):
                    problems.append((granularity, "directory_count > file_count", metrics))
    return problems


def kotlin_case(rng):
    lines, expected = ["package p", ""], {"names": set(), "field_calls": {}, "member_calls": {}}
    functions = [f"g{i}" for i in range(4)]
    counter = [0]

    def fresh(prefix):
        counter[0] += 1
        return f"{prefix}{counter[0]}"

    for _ in range(rng.randint(1, 4)):
        shape = rng.choice(["one_object", "one_class", "multi_object", "ctor"])
        name = fresh("T")
        expected["names"].add(name)
        members = []
        for _ in range(rng.randint(0, 3)):
            if rng.random() < 0.5:
                member = fresh("v")
                members.append((f"val {member} = 1", member, None))
            else:
                member, callee = fresh("f"), rng.choice(functions)
                members.append((f"fun {member}() = {callee}()", member, callee))
        for _text, member, callee in members:
            expected["names"].add(f"{name}.{member}")
            if callee:
                expected["member_calls"][f"{name}.{member}"] = callee
        body = "; ".join(text for text, _m, _c in members)
        if shape == "one_object":
            lines.append(f"{rng.choice(['', 'data '])}object {name} {{ {body} }}" if members else f"object {name} {{ }}")
        elif shape == "one_class":
            lines.append(f"class {name} {{ {body} }}")
        elif shape == "multi_object":
            nested = fresh("N")
            expected["names"].add(f"{name}.{nested}")
            expected["names"].add(f"{name}.{nested}.w")
            lines += [f"object {name} {{"] + [f"    {text}" for text, _m, _c in members] + [f"    object {nested} {{ val w = 1 }}", "}"]
        else:
            params = []
            for _ in range(rng.randint(0, 4)):
                param, binding = fresh("p"), rng.choice(["val ", "var ", ""])
                callees = rng.sample(functions, rng.randint(0, 2))
                default = " + ".join(f"{c}()" for c in callees) if callees else "0"
                params.append(f"{binding}{param}: Int = {default}")
                if binding:
                    expected["names"].add(f"{name}.{param}")
                    expected["field_calls"][f"{name}.{param}"] = set(callees)
            for text, member, callee in members:
                expected["names"].discard(f"{name}.{member}")
                expected["member_calls"].pop(f"{name}.{member}", None)
            split = rng.random() < 0.5
            lines.append(f"class {name}(" + (",\n    ".join(params) if split else ", ".join(params)) + ")")
        lines.append("")
    lines += [f"fun {f}() = 1" for f in functions]
    return {"src/A.kt": "\n".join(lines) + "\n"}, expected


def kotlin_shape_check(root, expected):
    arch = KotlinAnalyzer(str(root)).analyze()
    ids = {n.id for n in arch.nodes}
    prefix = "kotlin:src/A.kt#"
    problems = [("missing", name) for name in sorted(expected["names"]) if prefix + name not in ids]
    calls = {}
    for edge in arch.edges:
        if edge.relation == "CALLS" and edge.from_id.startswith(prefix):
            calls.setdefault(edge.from_id[len(prefix):], set()).add(edge.to_id[len(prefix):])
    for field, callees in expected["field_calls"].items():
        if calls.get(field, set()) != callees:
            problems.append(("field calls", field, callees, calls.get(field, set())))
    for member, callee in expected["member_calls"].items():
        owner = member.rsplit(".", 1)[0]
        if calls.get(member, set()) != {callee}:
            problems.append(("member calls", member, callee, calls.get(member, set())))
        if callee in calls.get(owner, set()) and not any(c == callee for m, c in expected["member_calls"].items()
                                                          if m.rsplit(".", 1)[0] != owner):
            problems.append(("owner calls member callee", owner, callee))
    return problems


def round4(args):
    violations = executions = 0
    surfaces = (("C", spread_case, spread_check, None),
                ("D", kotlin_case, kotlin_shape_check, ("src/B.kt", "package p\nclass Broken( {\n  fun x( = \n")))
    for label, case, check, broken in surfaces:
        rng = random.Random(f"{args.seed}:round4:{label}")
        for index in range(args.budget):
            files, expected = case(rng)
            if broken and rng.random() < 0.1:
                files[broken[0]] = broken[1]
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
                print(f"VIOLATION {label} #{index}: {problems}\n--- files ---\n{files}", flush=True)
        print(f"surface {label}: {args.budget} projects done", flush=True)
    print(f"executions={executions} violations={violations}")
    return 1 if violations else 0


if __name__ == "__main__":
    if "--round4" in sys.argv:
        sys.argv.remove("--round4")
        parser = argparse.ArgumentParser()
        parser.add_argument("--seed", type=int, default=20261020)
        parser.add_argument("--budget", type=int, default=1000)
        sys.exit(round4(parser.parse_args()))
    sys.exit(main())
