import json, random, re, sys
from collections import Counter, defaultdict
from pathlib import Path

out, roots, seed = Path(sys.argv[1]), {"nestjs": Path(sys.argv[2]), "android": Path(sys.argv[3])}, int(sys.argv[4])
IMPORTISH = {"IMPORTS", "IMPORTS_SYMBOL", "RE_EXPORTS"}


def resolve_evidence(payload):
    details = payload.get("details") or {}
    detail_edges = details.get("edges") or []
    detail_nodes = {n["id"]: n for n in details.get("nodes") or []}
    for e in payload["edges"]:
        if e.get("evidence") is None and (e.get("metadata") or {}).get("detail_edge_indices"):
            first = detail_edges[e["metadata"]["detail_edge_indices"][0]]
            e["evidence"] = first.get("evidence")
            e["detail_target"] = detail_nodes.get(first["to_id"])
    return payload


def key(e):
    return (e["from_id"], e["to_id"], e["relation"], e["resolution"], e["confidence"], tuple(e.get("candidates") or []),
            (e.get("evidence") or {}).get("start_line"))


def names_by_file(symbol_nodes):
    names = defaultdict(set)
    for n in symbol_nodes:
        span = n.get("span") or {}
        if span.get("file_path") and n.get("label"):
            names[span["file_path"]].add(n["label"])
    return names


def node_file(node):
    return ((node or {}).get("span") or {}).get("file_path")


def plausible(edge, nodes, line, names):
    target = edge.get("detail_target") or nodes.get(edge["to_id"])
    if edge["relation"] == "TESTS":
        return True, "TESTS derives from an underlying edge; counterpart checked separately"
    if edge["relation"] in IMPORTISH:
        stem = Path(node_file(target) or "").stem
        label = (target or {}).get("label", "")
        ok = "import" in line or "export" in line
        ok = ok and (stem.split(".")[0] in line or label.rsplit("/", 1)[-1].split(".")[0] in line or Path(stem).stem in line)
        return ok, "import/export line names the target"
    if target and target.get("kind") in ("file", "module"):
        candidates = names.get(node_file(target), set())
    else:
        candidates = {(target or {}).get("label", "")}
    hit = [n for n in candidates if n and re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", line)]
    return bool(hit), f"line names {hit[:3]}"


report = []
for fixture in ("nestjs", "android"):
    symbol_nodes = json.load(open(out / f"head-{fixture}-symbol.json"))["nodes"]
    names = names_by_file(symbol_nodes)
    for granularity in ("file", "symbol"):
        base = resolve_evidence(json.load(open(out / f"base-{fixture}-{granularity}.json")))
        head = resolve_evidence(json.load(open(out / f"head-{fixture}-{granularity}.json")))
        nodes = {n["id"]: n for n in head["nodes"]}
        b, h = Counter(map(key, base["edges"])), Counter(map(key, head["edges"]))
        added_keys, removed_keys = h - b, b - h
        added = [e for e in head["edges"] if key(e) in added_keys]
        removed = [e for e in base["edges"] if key(e) in removed_keys]
        report.append(f"## {fixture} {granularity}: added {sum(added_keys.values())}, removed {sum(removed_keys.values())}")
        groups = Counter((e["relation"], e["resolution"]) for e in added)
        report.append("added groups: " + ", ".join(f"{r}/{s}={c}" for (r, s), c in sorted(groups.items())))
        groups = Counter((e["relation"], e["resolution"]) for e in removed)
        report.append("removed groups: " + ", ".join(f"{r}/{s}={c}" for (r, s), c in sorted(groups.items())))
        by_site = defaultdict(list)
        for e in added:
            ev = e.get("evidence") or {}
            by_site[(e["from_id"], e["relation"], ev.get("file_path"), ev.get("start_line"))].append(e)
        unmatched = []
        for e in removed:
            ev = e.get("evidence") or {}
            site = (e["from_id"], e["relation"], ev.get("file_path"), ev.get("start_line"))
            if not by_site.get(site):
                unmatched.append(e)
        report.append(f"removed edges without an added edge at the same (source, relation, evidence line): {len(unmatched)}")
        for e in unmatched[:15]:
            report.append(f"  UNMATCHED {e['from_id']} -{e['relation']}/{e['resolution']}-> {e['to_id']} line {(e.get('evidence') or {}).get('start_line')} candidates={e.get('candidates')}")
        rng = random.Random(seed)
        sample = rng.sample(added, min(10, len(added)))
        bad = 0
        for i, e in enumerate(sample, 1):
            ev = e.get("evidence") or {}
            path, line_no = ev.get("file_path"), ev.get("start_line")
            text = (roots[fixture] / path).read_text(encoding="utf-8").split("\n") if path else []
            line = text[line_no - 1].strip() if path and line_no and line_no <= len(text) else ""
            ok, why = plausible(e, nodes, line, names)
            bad += not ok
            report.append(f"  [{i}] {'yes' if ok else 'NO '} {e['from_id'].rsplit('/', 1)[-1]} -{e['relation']}/{e['resolution']}-> {e['to_id'].rsplit('/', 1)[-1]} @ {path}:{line_no} `{line[:110]}` ({why})")
        report.append(f"sample mismatches: {bad}/{len(sample)}")
print("\n".join(report))
