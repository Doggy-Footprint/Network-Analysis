import copy, json, random, sys, tempfile, traceback
from pathlib import Path
from bottlenecks.delta import BaselineError, compute_delta, load_baseline
from analysis.structure import TIERS

SEED, N = 20261018, 20000
rng = random.Random(SEED)
out = {"seed": SEED}

def paths(node, prefix=()):
    yield prefix
    if len(prefix) > 40: return
    if isinstance(node, dict):
        for k, v in node.items(): yield from paths(v, prefix + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node[:6]): yield from paths(v, prefix + (i,))

def junk():
    return rng.choice([None, 0, -1, 1.5, True, "", "x", "bottlenecks.v8", "file", "all", [], {}, ["a"], {"id": "x"}, [{"from_id": 1}], 10**30])

def mutate(doc):
    doc = copy.deepcopy(doc)
    for _ in range(rng.randint(1, 3)):
        all_paths = list(paths(doc))
        p = rng.choice(all_paths)
        if not p: return junk()
        parent = doc
        for k in p[:-1]: parent = parent[k]
        k = p[-1]; op = rng.randrange(5)
        if op == 0:
            del parent[k]
        elif op == 1: parent[k] = junk()
        elif op == 2 and isinstance(parent[k], list) and parent[k]:
            parent[k].append(copy.deepcopy(rng.choice(parent[k])))
        elif op == 3:
            v = parent[k]
            for _ in range(rng.choice([1, 5, 200])): v = [v]
            parent[k] = v
        else:
            parent[k] = rng.choice([str(parent[k]), [parent[k]], {"v": parent[k]}])
    return doc

# (a) crash oracle
valid = json.loads(Path(sys.argv[1]).read_text())
for key in ("node_metrics", "rankings", "rankings_by_category"): valid["dependency_network"].pop(key, None)
current = copy.deepcopy(valid)
RAW = json.dumps(valid).encode()
tmp = Path(tempfile.mkdtemp()); target = tmp / "b.json"
crashes, accepted = [], 0
for i in range(N):
    r = rng.random()
    if r < 0.02:
        data = b"[" * rng.choice([1000, 100000]) + b"]" * rng.choice([0, 1000, 100000])
    elif r < 0.1:
        raw = RAW
        cut = rng.randrange(len(raw)); data = raw[:cut] if rng.random() < 0.5 else raw[:cut] + bytes([rng.randrange(256)]) + raw[cut+1:]
    else:
        data = json.dumps(mutate(valid)).encode()
    target.write_bytes(data)
    try:
        compute_delta(current, load_baseline(target)); accepted += 1
    except BaselineError:
        pass
    except Exception as exc:
        crashes.append({"i": i, "error": repr(exc)[:300], "trace": traceback.format_exc()[-600:]})
out["a"] = {"execs": N, "accepted": accepted, "crashes": len(crashes), "first": crashes[:3]}
print(json.dumps(out["a"])[:2000], flush=True)

# (b) property oracle
def payload(rng):
    files = [f"file:f{i}.py" for i in range(rng.randint(2, 30))]
    pkgs = [f"pkg:dir:p{i}" for i in range(rng.randint(1, 8))]
    cands = []
    for kind, scheme, nodes in (("dependency_cycle", "file", files), ("package_cycle", "language", pkgs)):
        for tier in TIERS:
            pool = nodes[:]; rng.shuffle(pool)
            while len(pool) >= 2 and rng.random() < 0.6:
                size = rng.randint(2, min(5, len(pool))); members = sorted(pool[:size]); pool = pool[size:]
                ev = [{"from_id": rng.choice(members), "to_id": rng.choice(members)} for _ in range(rng.randint(1, 4))]
                cands.append({"id": f"b:{kind}{tier}{'|'.join(members)}", "kind": kind, "structure": {"scheme": scheme, "tier": tier, "members": members}, "evidence": ev})
    for j in rng.sample(range(40), rng.randint(0, 15)):
        st = {"rule_type": "forbid", "from_layer": "a"}
        if j % 2: st["to_layer"] = "b"
        else: st["to_external"] = "x"
        cands.append({"id": f"b:v{j}", "kind": "rule_violation", "target": rng.choice(files), "structure": st, "evidence": [{"from_id": files[0], "to_id": files[-1]}]})
    pairs = sorted({(rng.choice(pkgs), rng.choice(pkgs)) for _ in range(rng.randint(0, 20))})
    deps = {"language": [{"from_id": a, "to_id": b, "tier": rng.choice(TIERS)} for a, b in pairs if a != b]}
    metrics = {"language": {p: {"instability": rng.choice([None, rng.random(), 0.0, 1.0])} for p in pkgs}}
    return {"schema": "bottlenecks.v8", "granularity": "file", "snapshot": {"file_count": len(files)}, "coverage": {"architecture_rules": {"rules_sha256": "x"}},
            "dependency_network": {"structure_policy": "structure.v1", "package_dependencies": deps, "package_metrics": metrics}, "candidates": cands}
violations = []
for i in range(N):
    a, b = payload(rng), payload(rng)
    try:
        s = compute_delta(a, copy.deepcopy(a))
        if any(s[k] for k in ("new_cycles", "grown_cycles", "new_violations", "new_package_dependencies", "instability_changes")) or s["rules_changed"] or any(s["resolved"].values()):
            violations.append({"i": i, "prop": "self"})
        ab, ba = compute_delta(a, b), compute_delta(b, a)
        if ab["counts"]["new_violations"] != ba["resolved"]["violations"]: violations.append({"i": i, "prop": "violation symmetry"})
        if ab["counts"]["new_package_dependencies"] != ba["resolved"]["package_dependencies"]: violations.append({"i": i, "prop": "package symmetry"})
    except Exception as exc:
        violations.append({"i": i, "prop": "exception", "error": repr(exc)[:300]})
out["b"] = {"execs": N, "violations": len(violations), "first": violations[:5]}
print(json.dumps(out["b"]), flush=True)
Path(sys.argv[2]).write_text(json.dumps(out, indent=2) + "\n")
