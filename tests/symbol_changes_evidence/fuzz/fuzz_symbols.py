"""Fuzz compute_delta symbol lists (spec 338f748639b68776 V11). argv: repo root, base_commit delta.py path.
P1 metamorphic: one symbol model rendered with old and renamed paths plus the renames gives empty symbol lists.
P2 differential: apart from the delta.v4 keys, the result equals base_commit delta.v3 on the payloads without symbols.
P3: with independent baseline and current symbol models (and renames), both lists equal a reference computed on model keys.
Signatures are drawn as shapes, each rendered through a random formatter variant (v6 F04: whitespace, separators before a
closing bracket and quote style are not changes), so the reference compares shapes and never canonicalizes strings itself."""
import copy, importlib.util, json, random, sys
from pathlib import Path

prev_spec = importlib.util.spec_from_file_location("fuzz_v3", Path(__file__).resolve().parents[2] / "rename_comment_evidence/fuzz/fuzz_delta_v3.py")
prev = importlib.util.module_from_spec(prev_spec); prev_spec.loader.exec_module(prev)
compute_delta, base_delta = prev.compute_delta, prev.base_delta

SEED, N = 20261112, 5000
KINDS = ("function", "method", "class", "constant")
NAMES = ("f", "g", "_h", "#p", "Cls", "Cls.run", "Cls._run", "MAX", "main")
SHAPES = (None, ("def f(x, y)", "def f( x, y )", "def f(x,y)"), ("def f(y, x)", "def f(\n    y,\n    x,\n)"),
          ("get({ a, b }: T)", "get({ a, b, }: T)", "get({a,b}:T)"), ("get(x: T['a'])", 'get(x: T["a"])', "get( x: T['a'], )"),
          ("run(a: { p: string; q: number; })", "run(a: { p: string; q: number })"), ("fun g(a: Int)", "fun g(\n    a: Int,\n)"),
          ("fun g(a: Int, b: Int)",), ("run(b)", "run( b )"), ("x: Map<K, V>", "x: Map<K, V,>"), ("private fun g()",), ("MAX = 1",))
NEW_KEYS = ("symbol_changes", "changed_signatures", "removed_symbols")


def symbol_model(rnd, n):
    out = {}
    for _ in range(rnd.randint(0, 20)):
        key = (rnd.randrange(n), rnd.choice(NAMES))
        out[key] = {"kind": rnd.choice(KINDS), "shape": rnd.randrange(len(SHAPES)), "visibility": rnd.choice(("public", "private")),
                    "external_refs": rnd.choice((0, 0, 1, 3)), "uncertain_external_refs": rnd.choice((0, 0, 2))}
    return out


def symbol_id(path, name):
    if path.endswith(".py"): return "py:%s#%s" % (prev.module(path), name)
    return ("kotlin:" if path.endswith(".kt") else "ts:") + path + "#" + name


def render_symbols(symbols, paths, rnd):
    rows = []
    for (i, name), record in symbols.items():
        shape = SHAPES[record["shape"]]
        record["signature"] = None if shape is None else rnd.choice(shape)
        rows.append(dict(record, id=symbol_id(paths[i], name), file="file:" + paths[i], name=name))
    return sorted(rows, key=lambda row: row["id"])


COLUMNS = ["id", "file", "kind", "name", "signature", "visibility", "external_refs", "uncertain_external_refs"]


def with_symbols(payload, symbols, paths, rnd):
    """Renders `symbols` in place: each record's `signature` becomes the variant drawn for this payload."""
    payload = copy.deepcopy(payload)
    network = payload["dependency_network"]
    index = {f: k for k, f in enumerate(network["file_ids"])}
    rows = render_symbols(symbols, paths, rnd)
    network["symbol_columns"] = list(COLUMNS)
    network["symbols"] = [[index[row["file"]] if c == "file" else row[c] for c in COLUMNS] for row in rows]
    return payload


def reference(base, cur, paths):
    changed, removed = [], []
    for key, b in base.items():
        i, name = key
        common = {"id": symbol_id(paths[i], name), "file": "file:" + paths[i], "name": name,
                  "external_refs": b["external_refs"], "uncertain_external_refs": b["uncertain_external_refs"]}
        refs = b["external_refs"] + b["uncertain_external_refs"]
        if key in cur:
            c = cur[key]
            if isinstance(b["signature"], str) and isinstance(c["signature"], str) and b["shape"] != c["shape"] and (c["visibility"] == "public" or refs > 0):
                changed.append(dict(common, kind=c["kind"], baseline_signature=b["signature"], current_signature=c["signature"], visibility=c["visibility"]))
        elif b["visibility"] == "public" or refs > 0:
            removed.append(dict(common, kind=b["kind"], baseline_signature=b["signature"], visibility=b["visibility"]))
    return sorted(changed, key=lambda r: r["id"]), sorted(removed, key=lambda r: r["id"])


def strip(d):
    d = prev.strip(d); counts = dict(d.get("counts") or {})
    for key in NEW_KEYS: d.pop(key, None); counts.pop(key, None)
    d["counts"] = counts; return d


def main():
    rnd = random.Random(SEED)
    fails = {"P1": 0, "P2": 0, "P3": 0, "exceptions": 0}
    examples, stats = [], {"executed": 0, "rename_pairs": 0, "changed": 0, "removed": 0}
    bases = prev.BASES + ("Main.kt", "ui/Screen.kt")
    while stats["executed"] < N:
        try:
            paths = prev.python_paths(sorted(set(rnd.choice(prev.DIRS) + rnd.choice(bases) for _ in range(rnd.randint(2, 8)))))
            if len(paths) < 2: continue
            stats["executed"] += 1
            m = prev.model(rnd, paths)
            new_paths, pairs = prev.renamed(rnd, paths)
            new_paths_ok = len({prev.module(p) for p in new_paths if p.endswith(".py")}) == sum(p.endswith(".py") for p in new_paths)
            if not new_paths_ok: new_paths, pairs = paths, []
            stats["rename_pairs"] += len(pairs)
            ren = {"status": "applied", "reason": None, "pairs": pairs}
            syms = symbol_model(rnd, len(paths))
            a = with_symbols(prev.render(m, paths), syms, paths, rnd)
            b = with_symbols(prev.render(m, new_paths), copy.deepcopy(syms), new_paths, rnd)
            d1 = compute_delta(b, copy.deepcopy(a), ren)
            if d1["changed_signatures"] or d1["removed_symbols"] or d1["symbol_changes"] != {"status": "applied", "reason": None}:
                fails["P1"] += 1; examples.append(("P1", pairs, d1["changed_signatures"][:2], d1["removed_symbols"][:2]))
            c_model = prev.model(rnd, paths)
            c_syms = symbol_model(rnd, len(paths))
            plain_a, plain_c = prev.render(m, paths), prev.render(c_model, new_paths)
            want = base_delta.compute_delta(copy.deepcopy(plain_c), copy.deepcopy(plain_a), ren)
            for case, (cur, base_payload, reason) in {
                    "none": (plain_c, plain_a, "baseline_without_symbols"),
                    "cur_only": (with_symbols(plain_c, c_syms, new_paths, rnd), plain_a, "baseline_without_symbols"),
                    "base_only": (plain_c, with_symbols(plain_a, syms, paths, rnd), "current_without_symbols"),
                    "both": (with_symbols(plain_c, c_syms, new_paths, rnd), with_symbols(plain_a, syms, paths, rnd), None)}.items():
                got = compute_delta(cur, copy.deepcopy(base_payload), ren)
                status = {"status": "skipped" if reason else "applied", "reason": reason}
                counts_ok = got["counts"].get("changed_signatures") == len(got["changed_signatures"]) and got["counts"].get("removed_symbols") == len(got["removed_symbols"])
                if strip(got) != strip(want) or got["policy"] != "delta.v4" or got["symbol_changes"] != status or not counts_ok or (reason and (got["changed_signatures"] or got["removed_symbols"])):
                    fails["P2"] += 1; examples.append(("P2", case, {k: (got.get(k), want.get(k)) for k in set(got) | set(want) if got.get(k) != want.get(k)}))
                if case == "both":
                    changed, removed = reference(syms, c_syms, new_paths)
                    stats["changed"] += len(changed); stats["removed"] += len(removed)
                    if got["changed_signatures"] != changed or got["removed_symbols"] != removed:
                        fails["P3"] += 1; examples.append(("P3", pairs, got["changed_signatures"], changed, got["removed_symbols"], removed))
        except Exception as exc:  # noqa: BLE001
            fails["exceptions"] += 1; examples.append(("exc", f"{type(exc).__name__}: {exc}"))
    print(json.dumps({"seed": SEED, "inputs": N, **stats, "failures": fails,
                      "examples": [json.dumps(e, default=str)[:1200] for e in examples[:5]]}, indent=1))


if __name__ == "__main__":
    main()
