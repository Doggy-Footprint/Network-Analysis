import os, random, sys, tempfile, json
from pathlib import Path
sys.path.insert(0, os.getcwd())
from repository.models import SourceText
from language_analyzers.typescript.analyzer import TypeScriptAnalyzer, SOURCE_EXTENSIONS
from language_analyzers.python.graph import PythonGraphAnalyzer

def ref_L(t):
    return t.count("\n") + (1 if t and not t.endswith("\n") else 0)
def ref_lines(t):
    if not t: return ()
    parts = t.split("\n")
    if t.endswith("\n"): parts = parts[:-1]
    out = []
    for i, p in enumerate(parts):
        followed = i < len(t.split("\n")) - 1
        out.append(p[:-1] if followed and p.endswith("\r") else p)
    return tuple(out)

ALPH = ["\n", "\r\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " ", "a", "b", " ", "�", "", "\n\n"]
def surface_a(rng, n):
    bad = 0
    for _ in range(n):
        t = "".join(rng.choice(ALPH) for _ in range(rng.randint(0, 12)))
        try:
            st = SourceText(t); lines = st.lines
            if len(lines) != ref_L(t) or lines != ref_lines(t):
                bad += 1; print("A-VIOLATION", repr(t), lines, ref_lines(t)); 
        except Exception as e:
            bad += 1; print("A-CRASH", repr(t), e)
    return bad

def ref_resolve(files, importer, spec):
    if not spec.startswith("."): return None
    base = os.path.normpath(os.path.join(os.path.dirname(importer), spec))
    if base.startswith(".."): return None
    suf = os.path.splitext(base)[1]
    c = ([base] if suf in SOURCE_EXTENSIONS else []) + [base + e for e in SOURCE_EXTENSIONS]
    if suf in SOURCE_EXTENSIONS: c += [base[:-len(suf)] + e for e in SOURCE_EXTENSIONS]
    c += [base + "/index" + e for e in SOURCE_EXTENSIONS]
    for x in c:
        if x in files: return x
    return None

def surface_b(rng, n):
    bad = 0
    words = ["tag", "user", "entity", "service", "spec", "dto", "index", "foo"]
    exts = [".ts", ".tsx", ".js"]
    for i in range(n):
        with tempfile.TemporaryDirectory() as d:
            files = set()
            for _ in range(rng.randint(2, 6)):
                name = ".".join(rng.choice(words) for _ in range(rng.randint(1, 4)))
                sub = rng.choice(["", "a/", "a/b/"])
                files.add(sub + name + rng.choice(exts))
            files = sorted(files)
            expected = {}
            for f in files:
                specs = []
                for _ in range(rng.randint(0, 3)):
                    tgt = rng.choice(files)
                    rel = os.path.relpath(tgt, os.path.dirname(f) or ".")
                    if not rel.startswith("."): rel = "./" + rel
                    form = rng.randint(0, 3)
                    if form == 0: rel = os.path.splitext(rel)[0]
                    elif form == 1 and rel.endswith(".ts"): rel = rel[:-3] + ".js"
                    elif form == 2: rel = os.path.splitext(rel)[0] + ".missing"
                    specs.append(rel)
                body = "".join(f"import {{ X{j} }} from '{s}';\n" for j, s in enumerate(specs))
                body += rng.choice(["", "\n", "\x0c\n", "\r\n", "export const v = 1;"])
                p = Path(d, f); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(body)
                for s in specs:
                    r = ref_resolve(set(files), f, s)
                    if r and r != f: expected.setdefault(f, set()).add(r)
            try:
                arch = TypeScriptAnalyzer(d).analyze()
                got = {}
                for e in arch.edges:
                    if e.relation == "IMPORTS":
                        got.setdefault(e.from_id[3:], set()).add(e.to_id[3:])
                nodes = {n.id: n for n in arch.nodes}
                for f in files:
                    t = Path(d, f).read_text()
                    n = nodes.get("ts:" + f)
                    if n is None or n.span.end_line != max(1, ref_L(t)):
                        bad += 1; print("B-ENDLINE", f, repr(t), n and n.span.end_line); 
                if {k: v for k, v in got.items()} != expected:
                    bad += 1; print("B-VIOLATION", files, expected, got)
            except Exception as e:
                bad += 1; print("B-CRASH", files, repr(e))
    return bad

if __name__ == "__main__":
    rng = random.Random(20261019)
    a = surface_a(rng, 20000)
    b = surface_b(rng, 500)
    print(json.dumps({"a_execs": 20000, "a_violations": a, "b_execs": 500, "b_violations": b}))
