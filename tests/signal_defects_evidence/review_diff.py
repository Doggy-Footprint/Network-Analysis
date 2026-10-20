"""Review diff for spec e91abc221d7deb2a (V12/C22/Q1): compares base and HEAD architecture (--json) and bottleneck
outputs for one input and attributes every difference to an R id, or counts it as unexplained.
Usage: review_diff.py <base_dir> <head_dir> <name> <mode> <out.json>; files are <name>-<mode>.json / .b.json.
"""
import collections
import json
import sys

R1_META = {"external_call_count", "external_calls", "unresolved_reference_total", "unresolved_calls",
           "unresolved_references", "unresolved_reference_limit", "unresolved_reference_truncated"}
OWNERSHIP = {"CONTAINS", "DECLARES", "EXPORTS"}
R4_RELATIONS = {"CALLS", "INSTANTIATES", "READS", "WRITES"}
SAMPLE = 10


def load(directory, name, mode):
    return (json.load(open(f"{directory}/{name}-{mode}.json")), json.load(open(f"{directory}/{name}-{mode}.b.json")))


def key_paths(value, prefix="$"):
    paths = set()
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}" if not prefix.endswith("<map>") else prefix
            paths.add(child)
            paths |= key_paths(item, child)
    elif isinstance(value, list):
        for item in value:
            paths |= key_paths(item, prefix + "[]")
    return paths


def normalize(path):
    # dict keys that are data (node ids, names, kinds) collapse so the comparison sees only structure
    parts = path.split(".")
    for marker in ("node_metrics", "candidate_groups", "unresolved_calls", "external_calls", "nodes_by_kind",
                   "edges_by_relation", "edges_by_confidence", "rankings", "rankings_by_category", "package_metrics",
                   "layer_file_counts", "analysis_coverage", "files", "schemes", "confidence", "resolution",
                   "package_dependencies", "by_status", "by_language"):
        if marker in parts:
            index = parts.index(marker)
            return ".".join(parts[:index + 1] + ["<map>"] + parts[index + 2:])
    return path


def edge_key(edge):
    evidence = edge.get("evidence") or {}
    return (edge["from_id"], edge["to_id"], edge["relation"], edge.get("resolution"), edge.get("confidence"),
            evidence.get("start_line"), tuple(edge.get("candidates", ())))


def attribute_edges(base_arch, head_arch, member_of, report):
    base_edges = collections.Counter(edge_key(e) for e in base_arch["edges"])
    head_edges = collections.Counter(edge_key(e) for e in head_arch["edges"])
    removed, added = base_edges - head_edges, head_edges - base_edges
    head_pairs = {(e["from_id"], e["to_id"], e["relation"]) for e in head_arch["edges"]}
    head_any = {(e["from_id"], e["to_id"]) for e in head_arch["edges"] if e["relation"] != "TESTS"}
    base_by_pair = collections.defaultdict(set)
    for e in base_arch["edges"]:
        base_by_pair[(e["from_id"], e["to_id"])].add(e["relation"])
    candidates_of = {edge_key(e): e.get("candidates", ()) for e in base_arch["edges"]}
    edge_why, r4_file_pairs = collections.Counter(), set()

    def file_of(node_id):
        return node_id.split(":", 1)[1].split("#")[0] if ":" in node_id else node_id

    for key, count in removed.items():
        source, target, relation = key[:3]
        targets = [target, *candidates_of.get(key, ())]
        kotlin = source.startswith("kotlin:")
        if kotlin and relation in R4_RELATIONS and (
                any((m, target, relation) in head_pairs for m in {p[0] for p in head_pairs} if member_of(m, source))
                or any(member_of(t, source) for t in targets)):
            why = "R4"
        elif kotlin and relation == "TESTS" and (member_of(target, source) or (
                (source, target) not in head_any and base_by_pair[(source, target)] - {"TESTS"})):
            why = "R4"
        elif kotlin and relation in ("IMPORTS", "IMPORTS_SYMBOL", "TESTS") and (source, target, relation) in head_pairs:
            why = "R4/R9"
        else:
            why = "unexplained"
            report["unexplained"].append(f"edge removed {source} -{relation}-> {target}")
        if why.startswith("R4"):
            for t in targets:
                r4_file_pairs.add((file_of(source), file_of(t), relation))
                r4_file_pairs.add((file_of(source), file_of(t), "*"))
        edge_why[f"-{relation} ({why})"] += count
    for key, count in added.items():
        source, target, relation = key[:3]
        if source.startswith("kotlin:") and any(k[:3] == key[:3] for k in removed):
            why = "R4/R9"
        else:
            why = "unexplained"
            report["unexplained"].append(f"edge added {source} -{relation}-> {target}")
        edge_why[f"+{relation} ({why})"] += count
    return removed, added, edge_why, r4_file_pairs


def main():
    base_dir, head_dir, name, mode, out = sys.argv[1:6]
    (base_arch, base_b), (head_arch, head_b) = load(base_dir, name, mode), load(head_dir, name, mode)
    report = {"input": name, "mode": mode, "unexplained": []}
    bn = {node["id"]: node for node in base_arch["nodes"]}
    hn = {node["id"]: node for node in head_arch["nodes"]}
    report["nodes"] = {"base": len(bn), "head": len(hn), "added": sorted(set(hn) - set(bn))[:SAMPLE],
                       "removed": sorted(set(bn) - set(hn))[:SAMPLE]}
    if set(bn) != set(hn):
        report["unexplained"].append("node id set differs")

    head_edges = collections.Counter(edge_key(e) for e in head_arch["edges"])
    base_edges = collections.Counter(edge_key(e) for e in base_arch["edges"])
    parent = {}
    for edge in base_arch["edges"] + head_arch["edges"]:
        if edge["relation"] == "CONTAINS":
            parent[edge["to_id"]] = edge["from_id"]

    def member_of(node_id, owner):
        while node_id in parent:
            node_id = parent[node_id]
            if node_id == owner:
                return True
        return False

    # flags (R6 ambiguous_name; R4 Kotlin class dynamic flags now only on members)
    flag_changes = collections.Counter()
    for node_id in set(bn) & set(hn):
        before, after = set(bn[node_id].get("flags", [])), set(hn[node_id].get("flags", []))
        for flag in before - after:
            if flag == "ambiguous_name":
                why = "R6"
            elif flag.startswith("dynamic_") and node_id.startswith("kotlin:") and any(
                    flag in hn[m].get("flags", []) for m in hn if member_of(m, node_id)):
                why = "R4"
            else:
                why = "unexplained"
                report["unexplained"].append(f"flag {flag} removed from {node_id}")
            flag_changes[f"-{flag} ({why})"] += 1
        for flag in after - before:
            report["unexplained"].append(f"flag {flag} added to {node_id}")
            flag_changes[f"+{flag} (unexplained)"] += 1
    report["flag_changes"] = dict(flag_changes)

    # metadata keys and values
    meta_changes = collections.Counter()
    for node_id in set(bn) & set(hn):
        before, after = bn[node_id].get("metadata", {}) or {}, hn[node_id].get("metadata", {}) or {}
        for key in set(before) | set(after):
            if before.get(key) == after.get(key):
                continue
            if key in R1_META:
                why = "R1/R3" if not node_id.startswith("kotlin:") else "R1/R3/R4"
            elif key == "analysis":
                why = "R7/R4"
            else:
                why = "unexplained"
                report["unexplained"].append(f"metadata {key} changed on {node_id}")
            meta_changes[f"{key} ({why})"] += 1
    report["metadata_changes"] = dict(meta_changes)

    # edges
    removed, added, edge_why, r4_file_pairs = attribute_edges(base_arch, head_arch, member_of, report)
    if mode == "file":
        (sym_base, _), (sym_head, _) = load(base_dir, name, "symbol"), load(head_dir, name, "symbol")
        sym_parent = {}
        for edge in sym_base["edges"] + sym_head["edges"]:
            if edge["relation"] == "CONTAINS":
                sym_parent[edge["to_id"]] = edge["from_id"]

        def sym_member_of(node_id, owner):
            while node_id in sym_parent:
                node_id = sym_parent[node_id]
                if node_id == owner:
                    return True
            return False
        _, _, _, r4_file_pairs = attribute_edges(sym_base, sym_head, sym_member_of, {"unexplained": []})
        edge_why = collections.Counter()
        report["unexplained"] = [u for u in report["unexplained"] if not u.startswith("edge ")]
        for (source, target, relation, *_), count in removed.items():
            why = "R4" if (source[5:], target[5:], relation) in r4_file_pairs or (source[5:], target[5:], "*") in r4_file_pairs else "unexplained"
            if why == "unexplained":
                report["unexplained"].append(f"edge removed {source} -{relation}-> {target}")
            edge_why[f"-{relation} ({why})"] += count
        for (source, target, relation, *_), count in added.items():
            why = "R4/R9" if any(k[0] == source and k[1] == target and k[2] == relation for k in removed) else "unexplained"
            if why == "unexplained":
                report["unexplained"].append(f"edge added {source} -{relation}-> {target}")
            edge_why[f"+{relation} ({why})"] += count
    report["edges"] = {"base": sum(base_edges.values()), "head": sum(head_edges.values()), "changes": dict(edge_why)}

    # JSON structure (Q1): compare records present on both sides, so a record that disappeared (with its kind's keys) is
    # not mistaken for a schema change
    expected_new = ("large_node_token_threshold", "token_count", "token_threshold", "external_call_count",
                    "external_calls", "unresolved_reference_total")
    r1_keys = ("unresolved_calls", "unresolved_references", "unresolved_reference_")
    pairs = [("architecture top level", {k: v for k, v in base_arch.items() if k not in ("nodes", "edges")},
              {k: v for k, v in head_arch.items() if k not in ("nodes", "edges")}),
             ("bottlenecks top level", {k: v for k, v in base_b.items() if k != "candidates"},
              {k: v for k, v in head_b.items() if k != "candidates"})]
    pairs += [("node " + nid, bn[nid], hn[nid]) for nid in set(bn) & set(hn)]
    bc = {c["id"]: c for c in base_b["candidates"]}; hc = {c["id"]: c for c in head_b["candidates"]}
    pairs += [("candidate " + cid, bc[cid], hc[cid]) for cid in set(bc) & set(hc)]
    key_report = collections.Counter()
    for label, before, after in pairs:
        b_paths, h_paths = {normalize(p) for p in key_paths(before)}, {normalize(p) for p in key_paths(after)}
        for path in h_paths - b_paths:
            ok = any(path.endswith("." + e) or ("." + e + ".") in path or path.endswith(e) for e in expected_new)
            key_report[f"+{path} ({'R1/R3/R8' if ok else 'unexplained'})"] += 1
            if not ok:
                report["unexplained"].append(f"{label}: key added {path}")
        for path in b_paths - h_paths:
            ok = any(k in path for k in r1_keys) or (label.startswith("candidate ") and path.startswith("$.evidence[]")
                                                     and bc[label[10:]]["kind"] in ("unresolved_boundary", "evidence_spread"))
            key_report[f"-{path} ({'R1/R5' if ok else 'unexplained'})"] += 1
            if not ok:
                report["unexplained"].append(f"{label}: key removed {path}")
    report["key_paths"] = dict(key_report)
    if base_b["schema"] != head_b["schema"]:
        report["unexplained"].append("schema changed")
    report["schema"] = head_b["schema"]
    report["versions"] = [base_b["versions"], head_b["versions"]]

    # candidates
    def by_kind(payload):
        result = collections.defaultdict(dict)
        for candidate in payload["candidates"]:
            result[candidate["kind"]][candidate["id"]] = candidate
        return result

    bk, hk = by_kind(base_b), by_kind(head_b)
    bm, hm = base_b["dependency_network"]["node_metrics"], head_b["dependency_network"]["node_metrics"]
    node_file = {nid: (n.get("span") or {}).get("file_path") or (n.get("metadata") or {}).get("file_path") for nid, n in hn.items()}
    candidates = {}
    has_r4 = any("(R4" in key for key in edge_why)
    for kind in sorted(set(bk) | set(hk)):
        gone, new = sorted(set(bk[kind]) - set(hk[kind])), sorted(set(hk[kind]) - set(bk[kind]))
        changed = sorted(i for i in set(bk[kind]) & set(hk[kind]) if bk[kind][i] != hk[kind][i])
        samples = []
        for label, ids, source in (("removed", gone, bk), ("added", new, hk), ("changed", changed, hk)):
            for cid in ids[:SAMPLE]:
                candidate = source[kind][cid]
                target = candidate["target"]
                if kind == "unresolved_boundary":
                    meta = (hn.get(target) or {}).get("metadata", {}) if mode == "symbol" else {}
                    why = "R1/R3" + ("/R4" if target.startswith(("kotlin:", "file:")) else "")
                elif kind == "evidence_spread":
                    own = node_file.get(target) or (target[5:] if target.startswith("file:") else None)
                    records = candidate["evidence"]
                    paths = {r["path"] for r in records if isinstance(r, dict) and "path" in r}
                    why = "R5" if label != "added" else ("R5" if own not in paths else "unexplained")
                elif kind == "large_node":
                    why = "R8"
                elif kind == "untested_hub":
                    why = "R7" if bm.get(target, {}).get("pagerank") != hm.get(target, {}).get("pagerank") else "unexplained"
                else:
                    why = "unexplained"
                if why == "unexplained":
                    report["unexplained"].append(f"{kind} {label} {target}")
                samples.append({"change": label, "target": target, "why": why,
                                "metrics": [bk[kind].get(cid, {}).get("metrics"), hk[kind].get(cid, {}).get("metrics")]})
        if kind not in ("unresolved_boundary", "evidence_spread", "large_node", "untested_hub") and (gone or new or changed):
            if not gone and not new and has_r4:
                report["unexplained"] = [u for u in report["unexplained"] if not u.startswith(f"{kind} changed ")]
                for sample in samples:
                    sample["why"] = "R4"
            else:
                report["unexplained"].append(f"{kind}: {len(gone)} removed, {len(new)} added, {len(changed)} changed")
        candidates[kind] = {"base": len(bk[kind]), "head": len(hk[kind]), "removed": len(gone), "added": len(new),
                            "changed": len(changed), "samples": samples}
    report["candidates"] = candidates

    # structural metrics that R7 does not touch
    stable = ("fan_in", "fan_out", "token_cost", "betweenness_centrality", "hop_2_token_cost")
    metric_changes = collections.Counter(k for nid in set(bm) & set(hm) for k in stable if bm[nid][k] != hm[nid][k])
    report["structural_metric_changes"] = dict(metric_changes)
    if metric_changes and not name == "android":
        report["unexplained"].append(f"structural metrics changed: {dict(metric_changes)}")

    json.dump(report, open(out, "w"), indent=1, ensure_ascii=False)
    print(f"{name} {mode}: nodes {len(bn)}/{len(hn)} edges {report['edges']['base']}/{report['edges']['head']} "
          f"flags {report['flag_changes']} unexplained {len(report['unexplained'])}")


if __name__ == "__main__":
    main()
