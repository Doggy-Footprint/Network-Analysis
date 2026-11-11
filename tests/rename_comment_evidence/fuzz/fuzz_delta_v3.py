"""Fuzz compute_delta (spec 73bd5aa508fa3e88 V13). argv: repo root, base_delta.py path.
P1 metamorphic: one abstract model rendered with old and renamed paths, delta(b, a, renames) is empty.
P2 differential: renames=None equals base_commit delta.v2 apart from policy/renames.
P3: applied with empty pairs equals renames=None apart from renames."""
import copy, hashlib, importlib.util, json, random, sys

sys.path.insert(0, sys.argv[1])
from bottlenecks.delta import compute_delta  # noqa: E402

spec = importlib.util.spec_from_file_location("base_delta", sys.argv[2])
base_delta = importlib.util.module_from_spec(spec); spec.loader.exec_module(base_delta)

SEED, N = 20261111, 5000
GENERAL = ("large_node", "unresolved_boundary", "evidence_spread", "dangling_doc_reference", "unstable_dependency",
           "untested_hub", "isolated_node", "duplicate_code")
DIRS = ("", "src/", "src/a/", "b/", "src/a/b/")
BASES = ("a.py", "m1.py", "xm1.py", "events.module.ts", "app.module.ts", "util.ts", "a.module.ts")
EMPTY = {"status": "applied", "reason": None, "pairs": []}


def h(*parts):
    return "b:" + hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16]


def model(rnd, paths=None):
    paths = paths or sorted(set(rnd.choice(DIRS) + rnd.choice(BASES) for _ in range(rnd.randint(2, 8))))
    n = len(paths)
    m = {"paths": paths, "general": [], "dcycles": [], "pcycles": [], "viol": [], "pdeps": [], "pmet": [], "fc": rnd.randint(1, 50)}
    seen = set()
    for _ in range(rnd.randint(0, 14)):
        kind = rnd.choice(GENERAL); t = rnd.randrange(n)
        pk = (rnd.choice(("nest", "dir")), rnd.randrange(n), rnd.choice(("nest", "dir")), rnd.randrange(n)) if kind == "unstable_dependency" else None
        key = (kind, t, pk)
        if key in seen: continue
        seen.add(key)
        m["general"].append({"kind": kind, "t": t, "pk": pk, "metric": rnd.randint(0, 5),
                             "refs": [rnd.choice("abcd") for _ in range(rnd.randint(0, 2))],
                             "edge": (rnd.randrange(n), rnd.randrange(n)) if rnd.random() < 0.5 else None})
    for _ in range(rnd.randint(0, 2)):
        if n < 2: break
        mem = sorted(rnd.sample(range(n), rnd.randint(2, n)))
        m["dcycles"].append({"mem": mem, "tier": rnd.choice(("all", "certain"))})
    for _ in range(rnd.randint(0, 2)):
        if n < 2: break
        mem = sorted(rnd.sample(range(n), 2))
        m["pcycles"].append({"mem": mem, "sch": rnd.choice(("nest", "dir"))})
    for _ in range(rnd.randint(0, 3)):
        m["viol"].append({"t": rnd.randrange(n), "to": rnd.randrange(n), "ext": rnd.random() < 0.3,
                          "rule": rnd.choice(("forbid", "allow_only")), "fl": rnd.choice(("db", "api")), "tl": rnd.choice(("api", "ui"))})
    for _ in range(rnd.randint(0, 6)):
        m["pdeps"].append((rnd.choice(("nest", "dir")), rnd.randrange(n), rnd.randrange(n), rnd.choice(("all", "certain"))))
    for i in range(n):
        if rnd.random() < 0.6: m["pmet"].append((rnd.choice(("nest", "dir")), i, round(rnd.random(), 2)))
    return m


def render(m, paths):
    fid = lambda i: "file:" + paths[i]
    def pkg(kind, i):
        if kind == "nest": return "pkg:nestjs:%s#M%d" % (paths[i], i)
        d = paths[i].rsplit("/", 1)[0] if "/" in paths[i] else "."
        return "pkg:dir:" + d
    scheme = {"nest": "framework", "dir": "language"}
    file_ids = sorted(fid(i) for i in range(len(paths)))
    index = {f: k for k, f in enumerate(file_ids)}
    cands = []
    for g in m["general"]:
        kind, target = g["kind"], fid(g["t"])
        c = {"id": h(kind, target), "kind": kind, "target": target, "metrics": {}, "evidence": [], "structure": None}
        if kind == "large_node": c["metrics"] = {"line_count": g["metric"], "token_count": g["metric"]}
        elif kind == "evidence_spread": c["metrics"] = {"file_count": g["metric"], "directory_count": 1}
        elif kind == "dangling_doc_reference":
            c["metrics"] = {"dangling_count": g["metric"]}; c["evidence"] = [{"line": 1, "notation": "code", "text": r} for r in g["refs"]]
        elif kind == "unresolved_boundary":
            c["metrics"] = {"unresolved_count": g["metric"]}
            rec = {"node_id": target, "unresolved_references": [{"name": r, "line": 1} for r in g["refs"]], "flags": []}
            if g["edge"]: rec.update(from_id=fid(g["edge"][0]), to_id=fid(g["edge"][1]), relation="CALLS")
            c["evidence"] = [rec]
        elif kind == "unstable_dependency":
            fk, fi, tk, ti = g["pk"]
            c["target"] = pkg(fk, fi); c["id"] = h(kind, c["target"], pkg(tk, ti))
            c["structure"] = {"scheme": scheme[fk], "tier": "all", "from_package": pkg(fk, fi), "to_package": pkg(tk, ti)}
            c["metrics"] = {"file_pair_count": g["metric"]}
        cands.append(c)
    # pkg:dir targets of unstable_dependency may collide after rendering; keep the first like a unique analyzer output
    uniq, keys = [], set()
    for c in cands:
        k = (c["kind"], c["target"], json.dumps(c["structure"], sort_keys=True))
        if k not in keys: keys.add(k); uniq.append(c)
    cands = uniq
    taken = {}
    for cy in m["dcycles"]:
        mem = sorted(fid(i) for i in cy["mem"])
        # analyzer cycles are disjoint SCCs per (kind, scheme, tier)
        if taken.setdefault(("dc", cy["tier"]), set()) & set(mem): continue
        taken[("dc", cy["tier"])] |= set(mem)
        rows = [[index[mem[k]], index[mem[(k + 1) % len(mem)]], ["IMPORTS"], 1.0, 1, cy["tier"]] for k in range(len(mem))]
        cands.append({"id": h("dc", *mem), "kind": "dependency_cycle", "target": h("cyc", *mem),
                      "structure": {"scheme": "file", "tier": cy["tier"], "members": mem}, "evidence": rows})
    for cy in m["pcycles"]:
        mem = sorted({pkg(cy["sch"], i) for i in cy["mem"]})
        if len(mem) < 2 or taken.setdefault(("pc", cy["sch"]), set()) & set(mem): continue
        taken[("pc", cy["sch"])] |= set(mem)
        rows = [[mem[0], mem[1], ["IMPORTS"], 1.0, 1, "all", []], [mem[1], mem[0], ["IMPORTS"], 1.0, 1, "all", []]]
        cands.append({"id": h("pc", *mem), "kind": "package_cycle", "target": h("pcyc", *mem),
                      "structure": {"scheme": scheme[cy["sch"]], "tier": "all", "members": mem}, "evidence": rows})
    vseen = set()
    for v in m["viol"]:
        target, to = fid(v["t"]), fid(v["to"])
        if v["ext"]:
            key = ("forbid_external", v["fl"], "requests", target)
            c = {"kind": "rule_violation", "target": target, "structure": {"rule_type": "forbid_external", "from_layer": v["fl"], "to_external": "requests"},
                 "evidence": [{"name": "requests", "line": 1}]}
        else:
            key = (v["rule"], v["fl"], v["tl"], target, to)
            c = {"kind": "rule_violation", "target": target, "structure": {"rule_type": v["rule"], "from_layer": v["fl"], "to_layer": v["tl"], "tier": "all"},
                 "evidence": [{"from_id": target, "to_id": to, "tier": "all"}]}
        if key in vseen: continue
        vseen.add(key); c["id"] = h(*key); cands.append(c)
    deps = {}
    for k, a, b, tier in m["pdeps"]:
        deps.setdefault(scheme[k], []).append({"from_id": pkg(k, a), "to_id": pkg(k, b), "tier": tier})
    met = {}
    for k, i, value in m["pmet"]:
        met.setdefault(scheme[k], {})[pkg(k, i)] = {"instability": value}
    net = {"structure_policy": "structure.v2", "package_dependencies": deps, "package_metrics": met, "file_ids": file_ids,
           "evidence_columns": {"file_pair": ["from", "to", "relations", "max_weight", "evidence_count", "tier"],
                                "package_pair": ["from_id", "to_id", "relations", "max_weight", "evidence_count", "tier", "file_pairs"]}}
    return {"schema": "bottlenecks.v9", "granularity": "file", "snapshot": {"file_count": m["fc"]}, "dependency_network": net,
            "candidates": cands, "coverage": {}}


def renamed(rnd, paths):
    out, pairs = list(paths), []
    for i, p in enumerate(paths):
        if rnd.random() < 0.5:
            d, base = (p.rsplit("/", 1)[0] + "/", p.rsplit("/", 1)[1]) if "/" in p else ("", p)
            stem, ext = base.split(".", 1)
            new = d + stem + "_r." + ext
            if new in paths or new in out: continue
            out[i] = new; pairs.append({"from": p, "to": new, "similarity": 100})
    return out, sorted(pairs, key=lambda x: x["from"])


LISTS = ("new_cycles", "grown_cycles", "new_violations", "new_package_dependencies", "instability_changes", "new_candidates", "strengthened_candidates")


def strip(d):
    d = dict(d); d.pop("policy", None); d.pop("renames", None); return d


def main():
    rnd = random.Random(SEED)
    fails = {"P1": 0, "P2": 0, "P3": 0, "exceptions": 0}
    examples, pairs_total = [], 0
    for _ in range(N):
        m = model(rnd)
        try:
            a = render(m, m["paths"])
            new_paths, pairs = renamed(rnd, m["paths"])
            pairs_total += len(pairs)
            b = render(m, new_paths)
            ren = {"status": "applied", "reason": None, "pairs": pairs}
            d1 = compute_delta(b, copy.deepcopy(a), ren)
            if any(d1[k] for k in LISTS) or any(d1["resolved"].values()):
                fails["P1"] += 1; examples.append(("P1", pairs, {k: d1[k] for k in LISTS if d1[k]}, d1["resolved"]))
            c = render(model(rnd, m["paths"]), m["paths"])
            got, want = compute_delta(c, copy.deepcopy(a)), base_delta.compute_delta(c, copy.deepcopy(a))
            if strip(got) != strip(want) or got.get("policy") != "delta.v3" or got.get("renames", {}).get("reason") != "not_requested":
                fails["P2"] += 1; examples.append(("P2", {k: (got.get(k), want.get(k)) for k in set(got) | set(want) if got.get(k) != want.get(k) and k not in ("policy",)}))
            got3 = compute_delta(c, copy.deepcopy(a), EMPTY)
            if strip(got3) != strip(got) or got3["renames"] != EMPTY:
                fails["P3"] += 1; examples.append(("P3",))
        except Exception as exc:  # noqa: BLE001
            fails["exceptions"] += 1; examples.append(("exc", f"{type(exc).__name__}: {exc}"))
    print(json.dumps({"seed": SEED, "inputs": N, "rename_pairs": pairs_total, "failures": fails,
                      "examples": [json.dumps(e, default=str)[:900] for e in examples[:5]]}, indent=1))


if __name__ == "__main__":
    main()
