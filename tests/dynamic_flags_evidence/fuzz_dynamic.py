"""Expected dynamic_* flag sets come from the snippet catalogue below, never from analyzer output."""
import argparse
import os
import random
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, os.getcwd())
from language_analyzers.kotlin.analyzer import KotlinAnalyzer  # noqa: E402
from language_analyzers.python.graph import PythonGraphAnalyzer  # noqa: E402
from language_analyzers.typescript.analyzer import TypeScriptAnalyzer  # noqa: E402

I, A, E = "dynamic_import", "dynamic_attr", "dynamic_eval"

PY_SNIPPETS = [
    ("import_module(n)", {I}, None), ("__import__(n)", {I}, None), ("importlib.import_module(n)", {I}, None),
    ("im(n)", {I}, "im"), ("il.import_module(n)", {I}, None), ("il.reload(n)", set(), None),
    ("getattr(o, n)", {A}, None), ("getattr(o, 'x')", set(), None), ("setattr(o, n, v)", {A}, None),
    ("hasattr(o, 'x')", set(), None), ("delattr(o, n)", {A}, None),
    ("builtins.getattr(o, n)", {A}, None), ("builtins.getattr(o, 'x')", set(), None),
    ("builtins.eval(c)", {E}, None), ("builtins.exec(c)", {E}, None),
    ("bi.exec(c)", {E}, "bi"), ("bi.getattr(o, n)", {A}, "bi"), ("bi.getattr(o, 'x')", set(), "bi"),
    ("ev(c)", {E}, "ev"), ("ga(o, n)", {A}, "ga"),
    ("eval(c)", {E}, None), ("o.eval(c)", set(), None), ("vars(o)", {E}, None), ("o.compile(c)", set(), None),
    ("o.__dict__[n]", {A}, None), ("o.__dict__['x']", set(), None), ("o.__dict__[n] = v", {A}, None),
    ("del o.__dict__[n]", {A}, None), ("o.__dict__[1]", {A}, None), ("o.mapping[n]", set(), None),
    ("o.__dict__[f'{n}']", {A}, None), ("x = len(o)", set(), None),
    ("from builtins import eval as e2\n    e2(c)", {E}, None),
    ("from importlib import import_module as m2\n    m2(n)", {I}, None),
]
PY_ALIASES = {
    "im": "from importlib import import_module as im",
    "il": "import importlib as il",
    "bi": "import builtins as bi",
    "ev": "from builtins import eval as ev",
    "ga": "from builtins import getattr as ga",
}
PY_HOOKS = ["__getattr__", "__getattribute__", "__setattr__", "__delattr__"]

TS_SNIPPETS = [
    ("import(n)", {I}), ("require(n)", {I}), ("require('fs')", {I}), ("require('')", {I}), ("require()", {I}),
    ("import(`./x${n}`)", {I}), ("require.resolve(n)", set()), ("o.require(n)", set()),
    ("eval(c)", {E}), ("Function('a', c)", {E}), ("new Function(c)", {E}), ("window.eval(c)", set()),
    ("o.Function()", set()), ("new o.Function()", set()), ("evaluate(c)", set()),
    ("Reflect.get(o, n)", {A}), ("Reflect.get(o, 'a')", set()), ("Reflect.get(o, 0)", set()),
    ("Reflect.get(o, `a`)", set()), ("Reflect.get(o, `a${n}`)", {A}), ("Reflect.get(o)", {A}),
    ("Reflect.set(o, n, v)", {A}), ("Reflect.set(o, 'a', v)", set()), ("Reflect.has(o, n)", {A}),
    ("Reflect.has(o, \"a\")", set()), ("Reflect.deleteProperty(o, n)", {A}),
    ("Reflect.defineProperty(o, n, {})", {A}), ("Object.defineProperty(o, n, {})", {A}),
    ("Object.defineProperty(o, 'x', {})", set()), ("Reflect.apply(f, null, [])", {A}),
    ("Reflect.apply(f, null, [n])", {A}), ("Reflect.ownKeys(o)", set()), ("o[n]", set()), ("Object.keys(o)", set()),
    ("const z = n + 1", set()),
]

KT_SNIPPETS = [
    ("Class.forName(n)", {I}), ("java.lang.Class.forName(\"a.B\")", {I}), ("ServiceLoader.load(Svc::class.java)", {I}),
    ("java.util.ServiceLoader.load(Svc::class.java)", {I}), ("loader.loadClass(n)", {I}),
    ("forName(n)", set()), ("Foo.forName(n)", set()), ("x.load()", set()), ("loadClass(n)", set()),
    ("cls.getMethod(n)", {A}), ("cls.getMethod(\"run\")", set()), ("cls.getDeclaredField(\"$n\")", {A}),
    ("cls.getDeclaredField(\"${n}x\")", {A}), ("cls.getField()", {A}), ("cls.getField(\"x\")", set()),
    ("cls.getDeclaredMethod(\"a\", String::class.java)", set()), ("cls.getDeclaredMethod(n, String::class.java)", {A}),
    ("getMethod(n)", set()), ("println(n)", set()),
]


def dyn(node):
    values = [f for f in node.flags if f.startswith("dynamic_")]
    # A repeated flag makes the set differ from every expectation (R10: flags change only by value).
    return set(values) | ({"DUPLICATE"} if len(values) != len(set(values)) else set())


def py_case(rng):
    aliases = sorted(a for a in PY_ALIASES if rng.random() < 0.5)
    lines = []
    guarded = rng.random() < 0.3
    for alias in aliases:
        if guarded:
            lines += ["try:", f"    {PY_ALIASES[alias]}", "except ImportError:", "    pass"]
        else:
            lines.append(PY_ALIASES[alias])
    lines.append("import builtins, importlib")
    expected = {}
    module_flags = set()
    if rng.random() < 0.3:
        lines += ["def __getattr__(name):", "    return name"]
        module_flags.add(A)
        expected["__getattr__"] = set()
    for i in range(rng.randint(1, 3)):
        name = f"f{i}"
        chosen = [rng.choice(PY_SNIPPETS) for _ in range(rng.randint(0, 3))]
        flags = set()
        body = []
        for snippet, snippet_flags, alias in chosen:
            body.append("    " + snippet)
            if alias is None or alias in aliases:
                flags |= snippet_flags
        lines += [f"def {name}(o, n, c, v):"] + (body or ["    pass"])
        expected[name] = flags
    for i in range(rng.randint(0, 2)):
        cname = f"K{i}"
        hook = rng.choice(PY_HOOKS + [None, None])
        is_async = rng.random() < 0.3
        lines.append(f"class {cname}:")
        lines.append("    attr = 1")
        if hook:
            lines += [f"    {'async ' if is_async else ''}def {hook}(self, *a):", "        return 1"]
            expected[hook] = set()
        lines += ["    def plain(self):", "        return 2"]
        expected[cname] = {A} if hook else set()
    return {"m.py": "\n".join(lines) + "\n"}, expected, module_flags


def py_check(root, files, expected, module_flags):
    arch = PythonGraphAnalyzer(str(root)).analyze()
    problems = []
    modules = [n for n in arch.nodes if n.kind == "module" and n.label == "m.py"]
    if len(modules) != 1 or dyn(modules[0]) != module_flags:
        problems.append(("module", module_flags, [dyn(m) for m in modules]))
    for name, flags in expected.items():
        nodes = [n for n in arch.nodes if n.label == name and n.kind != "module"]
        got = set().union(*(dyn(n) for n in nodes)) if nodes else None
        if got != flags:
            problems.append((name, flags, got))
    return problems


def ts_case(rng):
    files, expected = {}, {}
    for f in range(rng.randint(1, 3)):
        flags, body = set(), []
        for i in range(rng.randint(1, 3)):
            chosen = [rng.choice(TS_SNIPPETS) for _ in range(rng.randint(0, 3))]
            for snippet, snippet_flags in chosen:
                flags |= snippet_flags
            stmts = "".join(f"  {s};\n" for s, _ in chosen)
            body.append(f"export function f{i}(o: any, n: any, c: any, v: any, f: any) {{\n{stmts}}}\n")
        if rng.random() < 0.3:
            snippet, snippet_flags = rng.choice(TS_SNIPPETS)
            body.append(f"declare const o: any, n: any, c: any, v: any, f: any;\n{snippet};\n")
            flags |= snippet_flags
        files[f"m{f}.ts"] = "".join(body)
        expected[f"m{f}.ts"] = flags
    return files, expected, None


def ts_check(root, files, expected, _):
    arch = TypeScriptAnalyzer(str(root)).analyze()
    problems = []
    for key, flags in expected.items():
        nodes = [n for n in arch.nodes if n.id == f"ts:{key}"]
        got = dyn(nodes[0]) if nodes else None
        if got != flags:
            problems.append((key, flags, got))
        for n in arch.nodes:
            if n.id.startswith(f"ts:{key}#") and dyn(n):
                problems.append((n.id, set(), dyn(n)))
    return problems


def kt_case(rng):
    lines = ["package p", "", "interface Svc", ""]
    expected = {}
    params = "(n: String, cls: Class<*>, loader: ClassLoader, x: Any)"
    for i in range(rng.randint(1, 3)):
        chosen = [rng.choice(KT_SNIPPETS) for _ in range(rng.randint(0, 3))]
        flags = set().union(*(f for _, f in chosen)) if chosen else set()
        stmts = "".join(f"        {s}\n" for s, _ in chosen)
        if rng.random() < 0.5:
            lines.append(f"fun t{i}{params} {{\n{stmts}}}\n")
            expected[f"t{i}"] = flags
        else:
            lines.append(f"class C{i} {{\n    fun m{i}{params} {{\n{stmts}    }}\n}}\n")
            expected[f"m{i}"] = flags
            expected[f"C{i}"] = flags
    return {"p/M.kt": "\n".join(lines)}, expected, None


def kt_check(root, files, expected, _):
    arch = KotlinAnalyzer(str(root)).analyze()
    problems = []
    for name, flags in expected.items():
        nodes = [n for n in arch.nodes if n.label == name]
        got = set().union(*(dyn(n) for n in nodes)) if nodes else None
        if got != flags:
            problems.append((name, flags, got))
    return problems


BROKEN = {
    "python": ("broken.py", "def (:\n    eval(c\n"),
    "typescript": ("zz.ts", "require(n); const = ;\nReflect.get(o, ;\n"),
    "kotlin": ("p/B.kt", "package p\nfun ( {\n    Class.forName(n)\n    x.loadClass { }\n"),
}

LANGS = {"python": (py_case, py_check), "typescript": (ts_case, ts_check), "kotlin": (kt_case, kt_check)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20261019)
    parser.add_argument("--budget", type=int, default=1000)
    parser.add_argument("--lang", default="python,typescript,kotlin")
    args = parser.parse_args()
    total_violations = 0
    for lang in args.lang.split(","):
        rng = random.Random(f"{args.seed}:{lang}")
        make, check = LANGS[lang]
        crashes = violations = 0
        for run in range(args.budget):
            files, expected, extra = make(rng)
            if rng.random() < 0.1:
                broken_path, broken_text = BROKEN[lang]
                files[broken_path] = broken_text
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for rel, text in files.items():
                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
                    (root / rel).write_text(text, encoding="utf-8")
                try:
                    problems = check(root, files, expected, extra)
                except Exception:
                    crashes += 1
                    print(f"{lang} CRASH run={run}\n{files}\n{traceback.format_exc()}")
                    continue
            if problems:
                violations += 1
                if violations <= 5:
                    print(f"{lang} VIOLATION run={run} {problems}\n{files}")
        print(f"{lang}: execs={args.budget} crashes={crashes} violations={violations}")
        total_violations += crashes + violations
    print(f"TOTAL violations+crashes={total_violations}")
    return 1 if total_violations else 0


if __name__ == "__main__":
    sys.exit(main())
