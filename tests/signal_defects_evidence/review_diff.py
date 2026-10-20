"""Review diff for spec 3f70cc03aeae9c1a (rules RV1-RV9). Compares the base and head outputs of one input and attributes
every difference to an R id, or lists it under `unexplained`.

Usage: review_diff.py <base_dir> <head_dir> <name> <mode> <out.json> --stage a|b
Inputs are `<name>-<mode>.json` (architecture, --json) and `<name>-<mode>.b.json` (bottlenecks). A file-mode run also
reads the same input's symbol-mode files, because file-mode edge removals are attributed through symbol mode (RV3).
Stage a attributes R1-R10 (base cf0cf44, head 3b768a9); stage b attributes R11-R14 (base 3b768a9, head the new tree).
A missing input file aborts with a non-zero exit code before any output file is written.

Identifications that the JSON does not state directly (choices, not spec text):
- primary-constructor field: kind == "field", CONTAINS parent is a class node, and in BASE its signature starts
  with "(" or contains "constructor(" and its span lies inside the parent's span (3b768a9 gave every constructor field the
  whole constructor's span and signature text; body fields get their own declaration head, e.g. "val d").
- ownership edge (evidence_spread recomputation): relation in CONTAINS, DECLARES, EXPORTS, IMPLEMENTED_BY.
- structure-candidate constituents: every string anywhere inside the candidate, normalised to a file path (`file:`,
  `kotlin:`, `ts:`, `py:` prefixes and `#member` removed) or kept as a package id; edge endpoints are normalised the same
  way and also contribute their containing package id.
- stage b edge rules not spelled out in RV1-RV9 (R13 consequences): a removed edge leaving a constructor field with a scan
  relation is R13 only if its evidence line lies outside that field's HEAD span; a CONTAINS edge to a constructor field
  that differs only in evidence start_line is an R13 re-key; edges touching a node added in stage b are R12.
- RV3 "to is a member of C" also holds when an ambiguous edge lists a member of C among its candidates (the original
  ambiguous target and its alternatives are one relation; 3b768a9 android has such removals).
- RV3 treats Kotlin interface nodes like class nodes (R4 covers class/object/interface).
- RV8a details not spelled out: weighted_fan_* follow fan_*, effective_token_cost follows token_cost; in stage a pagerank and
  rankings may change without attributed edges (R7) while betweenness needs them; stage b hop_2 also counts constructor
  fields whose token_cost changed as changed nodes.
- ENRICHMENT_RELATIONS (RV9) is {CONFIGURES}.
"""
import collections
import json
import posixpath
import re
import sys

R1_META_PREFIXES = ("unresolved_", "external_")
OWNERSHIP = {"CONTAINS", "DECLARES", "EXPORTS", "IMPLEMENTED_BY"}
R4_RELATIONS = {"CALLS", "INSTANTIATES", "READS", "WRITES"}
IMPORT_RELATIONS = {"IMPORTS", "IMPORTS_SYMBOL"}
ENRICHMENT_RELATIONS = {"CONFIGURES"}
FIELD_SCAN_RELATIONS = {"CALLS", "INSTANTIATES", "READS", "WRITES", "TYPE_USES"}
CLASS_KINDS = {"class", "interface"}  # R4 names class/object/interface; objects carry kind "class"
STRUCTURE_KINDS = {"dependency_cycle", "package_cycle", "unstable_dependency"}
ENDPOINT_METRICS = ("fan_in", "fan_out", "weighted_fan_in", "weighted_fan_out")
COST_METRICS = ("token_cost", "effective_token_cost")
GLOBAL_METRICS = ("pagerank", "weighted_centrality_cost", "betweenness_centrality")
NODE_GEOMETRY = ("span", "cost", "signature", "size")
DATA_KEYED = {"unresolved_calls", "external_calls", "node_metrics", "candidate_groups", "nodes_by_kind",
              "edges_by_relation", "edges_by_confidence", "edges_by_resolution", "rankings_by_category",
              "package_metrics", "layer_file_counts", "analysis_coverage", "files", "schemes", "package_dependencies",
              "by_status", "by_language", "node_files", "node_owners", "file_nodes", "collections", "confidence",
              "resolution"}
SAMPLE = 10


# ------------------------------------------------------------------ small helpers

def file_of(node_id):
    """Path part of a node id: 'kotlin:a/B.kt#C.m' -> 'a/B.kt'; ids without a language prefix are returned unchanged."""
    if ":" not in node_id:
        return node_id
    return node_id.split(":", 1)[1].split("#")[0]


def normalise_entity(text):
    if text.startswith("pkg:kotlin:"):
        return "kotlin-package:" + text[len("pkg:kotlin:"):]
    if text.startswith("kotlin-package:"):
        return text
    if re.match(r"^(file|kotlin|ts|py|python|typescript):", text):
        return file_of(text)
    return text


def is_nontest(path):
    parts = path.split("/")
    if any(p in ("test", "tests", "spec") for p in parts[:-1]):
        return False
    name = parts[-1]
    if name.startswith("test_") or re.search(r"_test\.[^.]+$", name) or re.search(r"\.(spec|test)\.[^.]+$", name):
        return False
    return not (name.endswith("Test.kt") or name.endswith("Tests.kt"))


def edge_key(edge):
    evidence = edge.get("evidence") or {}
    return (edge["from_id"], edge["to_id"], edge["relation"], edge.get("resolution"), edge.get("confidence"),
            evidence.get("start_line"), tuple(edge.get("candidates", ())))


def reduced(key):
    """RV1 key without the evidence start_line."""
    return key[:5] + key[6:]


def node_span(node):
    return node.get("span") or {}


def key_paths(value, path=("$",)):
    """Set of tuple paths. Dict keys under data-keyed maps collapse to '<map>'; list items to '[]'."""
    paths = set()
    if isinstance(value, dict):
        collapse = len(path) > 1 and path[-1] in DATA_KEYED
        for key, item in value.items():
            child = path + ("<map>" if collapse else key,)
            paths.add(child)
            paths |= key_paths(item, child)
    elif isinstance(value, list):
        child = path[:-1] + (path[-1] + "[]",) if path else path
        for item in value:
            paths |= key_paths(item, child)
    return paths


def dotted(path):
    return ".".join(path)


def strings_in(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings_in(item)


# ------------------------------------------------------------------ evidence_spread recomputation (RV5)

def spread_expected(arch, threshold, mode, rule):
    """Candidate set recomputed from the architecture JSON alone. rule: 'pre3' | 'r5' | 'r11'.
    pre3: every evidence counts (own file and ownership edges included); r5: ownership edges and evidence in the target's
    own file are dropped; r11: as r5 for the evidence set, then directories other than the target's directory are counted."""
    nodes = {n["id"]: n for n in arch["nodes"]}
    if mode == "file":
        details = arch["details"]
        edges, node_files = details["edges"], details["node_files"]
        detail_nodes = {n["id"]: n for n in details["nodes"]}
    else:
        edges, node_files, detail_nodes = arch["edges"], {}, nodes

    def target_of(node_id):
        if mode == "file":
            file_node = node_files.get(node_id)
            return file_node if file_node else (node_id if node_id in nodes else None)
        return node_id if node_id in nodes else None

    def own_file(target):
        node = nodes[target]
        if mode == "file":
            return (node.get("metadata") or {}).get("file_path") or (target[5:] if target.startswith("file:") else None)
        return node_span(node).get("file_path")

    evidence = collections.defaultdict(list)
    for edge in edges:
        if edge["relation"] in OWNERSHIP:
            if rule != "pre3" or mode == "file":
                continue
        span = edge.get("evidence") or {}
        if not span.get("file_path"):
            continue
        ends = [edge["to_id"]] + (list(edge.get("candidates", ())) if edge.get("resolution") == "ambiguous" else [])
        for end in ends:
            target = target_of(end)
            if target is None:
                continue
            if rule != "pre3" and own_file(target) == span["file_path"]:
                continue
            evidence[target].append(span)
    expected = {}
    for target, spans in evidence.items():
        paths = {s["file_path"] for s in spans}
        extent = max(s["end_line"] for s in spans) - min(s["start_line"] for s in spans) + 1 if len(paths) == 1 else 0
        metrics = {"file_count": len(paths), "line_span": extent, "line_threshold": threshold}
        if rule == "r11":
            own = own_file(target)
            own_dir = posixpath.dirname(own) if own else None
            dirs = {posixpath.dirname(p) for p in paths}
            metrics["directory_count"] = len({d for d in dirs if d != own_dir})
            fires = metrics["directory_count"] >= 2 or (len(paths) == 1 and extent > threshold)
        else:
            fires = len(paths) >= 2 or (len(paths) == 1 and extent > threshold)
        if fires:
            expected[target] = metrics
    return expected


def spread_actual(bott):
    return {c["target"]: c["metrics"] for c in bott["candidates"] if c["kind"] == "evidence_spread"}


# ------------------------------------------------------------------ the review

class Side:
    def __init__(self, arch, bott):
        self.arch, self.bott = arch, bott
        self.nodes = {n["id"]: n for n in arch["nodes"]}
        self.edges = arch["edges"]
        self.metrics = bott["dependency_network"]["node_metrics"]
        self.candidates = {}
        for c in bott["candidates"]:
            self.candidates.setdefault(c["kind"], {})[c["id"]] = c


def parent_map(*sides):
    parent = {}
    for side in sides:
        for edge in side.edges:
            if edge["relation"] == "CONTAINS":
                parent[edge["to_id"]] = edge["from_id"]
    return parent


def descendants_of(parent, owner, node_id):
    while node_id in parent:
        node_id = parent[node_id]
        if node_id == owner:
            return True
    return False


def constructor_fields(base, head, parent):
    found = set()
    for node_id, node in base.nodes.items():
        if node.get("kind") != "field" or node_id not in head.nodes:
            continue
        owner = parent.get(node_id)
        if owner is None or (base.nodes.get(owner) or head.nodes.get(owner) or {}).get("kind") not in CLASS_KINDS:
            continue
        owner_node = base.nodes.get(owner) or head.nodes[owner]
        signature = (node.get("signature") or "").lstrip()
        inside = node_span(owner_node).get("start_line", 0) <= node_span(node).get("start_line", -1) <= node_span(owner_node).get("end_line", -1)
        if inside and (signature.startswith("(") or "constructor(" in signature.replace(" (", "(")):
            found.add(node_id)
    return found


def review(base_pair, head_pair, *, name, mode, stage, symbol_pairs=None):
    """base_pair/head_pair: (architecture dict, bottlenecks dict). symbol_pairs: (base, head) pairs of the same input in
    symbol mode, required for file mode. Returns the report dict."""
    base, head = Side(*base_pair), Side(*head_pair)
    report = {"input": name, "mode": mode, "stage": stage, "unexplained": []}
    bad = report["unexplained"]
    parent = parent_map(base, head)
    threshold = head.bott["edge_weights"]["large_node_line_threshold"]
    ctor = constructor_fields(base, head, parent)
    added_nodes = set(head.nodes) - set(base.nodes)

    # ---- node ids (RV7)
    report["nodes"] = {"base": len(base.nodes), "head": len(head.nodes), "added": sorted(added_nodes)[:SAMPLE],
                       "removed": sorted(set(base.nodes) - set(head.nodes))[:SAMPLE]}
    for node_id in sorted(set(base.nodes) - set(head.nodes)):
        bad.append(f"node removed {node_id}")
    for node_id in sorted(added_nodes):
        if stage == "a" or not node_id.startswith("kotlin:"):
            bad.append(f"node added {node_id}")
    common = sorted(set(base.nodes) & set(head.nodes))

    # ---- edges (RV1-RV3, RV9)
    removed = collections.Counter(edge_key(e) for e in base.edges) - collections.Counter(edge_key(e) for e in head.edges)
    added = collections.Counter(edge_key(e) for e in head.edges) - collections.Counter(edge_key(e) for e in base.edges)
    base_pairs = collections.defaultdict(set)
    for e in base.edges:
        base_pairs[(e["from_id"], e["to_id"])].add(e["relation"])
    head_triples = {(e["from_id"], e["to_id"], e["relation"]) for e in head.edges}
    head_nontests = collections.defaultdict(set)
    for e in head.edges:
        head_nontests[(e["from_id"], e["to_id"])].add(e["relation"])
    edge_why = collections.Counter()
    attributed = []  # removed edges attributed to R4 / R13: (from, to, relation)
    sym_attr, sym_changes = None, 0
    if mode == "file":
        sym_attr, ctor, sym_changes = symbol_attributed_files(symbol_pairs, name, stage)

    def take(key, counter, n=1):
        counter[key] -= n
        if counter[key] <= 0:
            del counter[key]

    def pair_up(rule_name, predicate, relation_label, added_ok=lambda akey: True):
        for rkey in list(removed):
            for akey in list(added):
                if rkey not in removed or akey not in added:
                    continue
                if reduced(rkey) == reduced(akey) and rkey[5] != akey[5] and predicate(rkey) and added_ok(akey):
                    n = min(removed[rkey], added[akey])
                    edge_why[f"{relation_label} re-key ({rule_name})"] += n
                    take(rkey, removed, n)
                    take(akey, added, n)

    is_kotlin = lambda key: key[0].startswith("kotlin:") or key[0].endswith(".kt")
    if stage == "a":
        pair_up("R9", lambda k: is_kotlin(k) and k[2] in IMPORT_RELATIONS, "imports")
        pair_up("R4", lambda k: is_kotlin(k) and k[2] not in IMPORT_RELATIONS, "other")
        for key, count in list(removed.items()):
            source, target, relation = key[:3]
            why = None
            if mode == "symbol":
                owner = base.nodes.get(source) or {}
                if is_kotlin(key) and owner.get("kind") in CLASS_KINDS:
                    if relation in R4_RELATIONS:
                        member_has = any((m, target, relation) in head_triples and descendants_of(parent, source, m)
                                         for m in head.nodes)
                        reached = [target] + (list(key[6]) if key[3] == "ambiguous" else [])
                        if member_has or any(descendants_of(parent, source, t) for t in reached):
                            why = "R4"
                    elif relation == "TESTS":
                        others = base_pairs[(source, target)] - {"TESTS"}
                        if descendants_of(parent, source, target) or (others and not (head_nontests[(source, target)] - {"TESTS"})):
                            why = "R4"
            else:
                if is_kotlin(key) and (relation, file_of(source), file_of(target)) in sym_attr:
                    why = "R4"
            if why:
                attributed.extend([(source, target, relation, tuple(key[6]))] * count)
                edge_why[f"-{relation} ({why})"] += count
                take(key, removed, count)
    else:
        # RV9: CONFIGURES-like edge re-targeted between constructor fields of one class
        for rkey in list(removed):
            for akey in list(added):
                if rkey not in removed or akey not in added:
                    continue
                if (rkey[2] in ENRICHMENT_RELATIONS and rkey[2] == akey[2] and rkey[0] == akey[0] and rkey[1] != akey[1]
                        and rkey[3:] == akey[3:] and rkey[1] in ctor and akey[1] in ctor
                        and parent.get(rkey[1]) == parent.get(akey[1])
                        and line_in_span(edge_evidence(base, head, rkey), head.nodes[akey[1]])):
                    n = min(removed[rkey], added[akey])
                    attributed.extend([(rkey[0], rkey[1], rkey[2], tuple(rkey[6]))] * n)
                    edge_why[f"-{rkey[2]} retarget (R13)"] += n
                    take(rkey, removed, n)
                    take(akey, added, n)
        pair_up("R13", lambda k: k[0] in ctor or k[1] in ctor, "constructor field")
        for key, count in list(removed.items()):
            source, target, relation = key[:3]
            why = None
            if mode == "symbol":
                if source in ctor and relation in FIELD_SCAN_RELATIONS and key[5] is not None and not line_in_span(
                        key[5], head.nodes[source]):
                    why = "R13"
            elif (relation, file_of(source), file_of(target)) in sym_attr:
                why = "R13"
            if why:
                attributed.extend([(source, target, relation, tuple(key[6]))] * count)
                edge_why[f"-{relation} ({why})"] += count
                take(key, removed, count)
        for key, count in list(added.items()):
            if key[0] in added_nodes or key[1] in added_nodes:
                edge_why[f"+{key[2]} (R12)"] += count
                take(key, added, count)
    for key, count in removed.items():
        bad.append(f"edge removed {key[0]} -{key[2]}-> {key[1]} (x{count})")
        edge_why[f"-{key[2]} (unexplained)"] += count
    for key, count in added.items():
        bad.append(f"edge added {key[0]} -{key[2]}-> {key[1]} (x{count})")
        edge_why[f"+{key[2]} (unexplained)"] += count
    report["edges"] = {"base": len(base.edges), "head": len(head.edges), "changes": dict(edge_why)}
    marker = ("R4",) if stage == "a" else ("R13", "R12")
    edge_changes = sum(v for k, v in edge_why.items() if any(m in k for m in marker) and "unexplained" not in k)
    edge_changes = max(edge_changes, sym_changes)
    report["attributed_edge_changes"] = edge_changes
    report["attributed_removed_edges"] = len(attributed)
    report["constructor_fields"] = sorted(ctor)
    report["attributed_file_pairs"] = sorted({(rel, file_of(s), file_of(t)) for s, t, rel, cands in attributed
                                              for t in (t, *cands)})

    # ---- flags (RV7)
    flag_changes = collections.Counter()
    for node_id in common:
        before, after = set(base.nodes[node_id].get("flags", [])), set(head.nodes[node_id].get("flags", []))
        for flag in sorted(before - after):
            if stage == "a" and flag == "ambiguous_name":
                why = "R6"
            elif stage == "a" and flag.startswith("dynamic_") and node_id.startswith("kotlin:") and any(
                    flag in head.nodes[m].get("flags", []) for m in head.nodes if descendants_of(parent, node_id, m)):
                why = "R4"
            elif stage == "b" and flag.startswith("dynamic_") and node_id in ctor:
                why = "R13"
            else:
                why = "unexplained"
                bad.append(f"flag {flag} removed from {node_id}")
            flag_changes[f"-{flag} ({why})"] += 1
        for flag in sorted(after - before):
            bad.append(f"flag {flag} added to {node_id}")
            flag_changes[f"+{flag} (unexplained)"] += 1
    report["flag_changes"] = dict(flag_changes)

    # ---- metadata values, node geometry, other node fields (RV7)
    meta_changes = collections.Counter()
    geometry = collections.Counter()
    for node_id in common:
        bn, hn = base.nodes[node_id], head.nodes[node_id]
        before, after = bn.get("metadata") or {}, hn.get("metadata") or {}
        for key in sorted(set(before) | set(after)):
            if before.get(key) == after.get(key):
                continue
            if key == "analysis":
                why = "R7" if stage == "a" else "R14"
            elif key.startswith(R1_META_PREFIXES) and (stage == "a" or r13_node(node_id, ctor)):
                why = "R1/R3/R4" if stage == "a" else "R13"
            elif (stage == "b" and node_id in ctor and key in ("line_number", "end_line_number")
                  and after.get(key) == node_span(hn).get("start_line" if key == "line_number" else "end_line")):
                why = "R13"
            else:
                why = "unexplained"
                bad.append(f"metadata {key} changed on {node_id}")
            meta_changes[f"{key} ({why})"] += 1
        for key in NODE_GEOMETRY:
            if bn.get(key) != hn.get(key):
                if stage == "b" and node_id in ctor:
                    geometry[f"{key} (R13)"] += 1
                else:
                    geometry[f"{key} (unexplained)"] += 1
                    bad.append(f"{key} changed on {node_id}")
        for key in sorted((set(bn) | set(hn)) - {"metadata", "flags", *NODE_GEOMETRY}):
            if bn.get(key) != hn.get(key):
                bad.append(f"node field {key} changed on {node_id}")
    report["metadata_changes"] = dict(meta_changes)
    report["geometry_changes"] = dict(geometry)

    # ---- key paths (RV6)
    key_report = collections.Counter()
    skip = ("nodes", "edges", "details")
    pairs = [("architecture top level", {k: v for k, v in base.arch.items() if k not in skip},
              {k: v for k, v in head.arch.items() if k not in skip}),
             ("bottlenecks top level", {k: v for k, v in base.bott.items() if k != "candidates"},
              {k: v for k, v in head.bott.items() if k != "candidates"})]
    pairs += [("node " + nid, base.nodes[nid], head.nodes[nid]) for nid in common]
    if mode == "file":
        bd = {n["id"]: n for n in base.arch["details"]["nodes"]}
        hd = {n["id"]: n for n in head.arch["details"]["nodes"]}
        pairs += [("node " + nid, bd[nid], hd[nid]) for nid in sorted(set(bd) & set(hd))]
    base_c = {c["id"]: c for c in base.bott["candidates"]}
    head_c = {c["id"]: c for c in head.bott["candidates"]}
    pairs += [("candidate " + cid, base_c[cid], head_c[cid]) for cid in sorted(set(base_c) & set(head_c))]
    for label, before, after in pairs:
        b_paths, h_paths = key_paths(before), key_paths(after)
        kind = (base_c.get(label[10:]) or {}).get("kind") if label.startswith("candidate ") else None
        for path in sorted(h_paths - b_paths):
            ok = key_added_allowed(stage, label, kind, path, ctor, mode)
            key_report[f"+{dotted(path)} ({'allowed' if ok else 'unexplained'})"] += 1
            if not ok:
                bad.append(f"{label}: key added {dotted(path)}")
        for path in sorted(b_paths - h_paths):
            ok = key_removed_allowed(stage, label, kind, path, ctor)
            key_report[f"-{dotted(path)} ({'allowed' if ok else 'unexplained'})"] += 1
            if not ok:
                bad.append(f"{label}: key removed {dotted(path)}")
    report["key_paths"] = dict(key_report)
    if base.bott["schema"] != head.bott["schema"]:
        bad.append("schema changed")
    report["schema"] = head.bott["schema"]
    report["versions"] = [base.bott["versions"], head.bott["versions"]]
    expected_analysis = {"a": "5", "b": "6"}[stage]
    if head.bott["versions"].get("analysis") != expected_analysis:
        bad.append(f"versions.analysis is {head.bott['versions'].get('analysis')!r}, expected {expected_analysis!r}")

    # ---- candidates (RV4, RV5)
    spread_rules = {"a": ("pre3", "r5"), "b": ("r5", "r11")}[stage]
    spread_report = {}
    for label, side, rule in (("base", base, spread_rules[0]), ("head", head, spread_rules[1])):
        want, have = spread_expected(side.arch, side.bott["edge_weights"]["large_node_line_threshold"], mode, rule), spread_actual(side.bott)
        wrong = sorted(t for t in set(want) | set(have) if want.get(t) != have.get(t))
        spread_report[label] = {"rule": rule, "expected": len(want), "actual": len(have), "mismatch": len(wrong)}
        for target in wrong[:SAMPLE]:
            bad.append(f"evidence_spread {label} ({rule}) mismatch at {target}: expected {want.get(target)}, actual {have.get(target)}")
        if len(wrong) > SAMPLE:
            bad.append(f"evidence_spread {label} ({rule}): {len(wrong) - SAMPLE} more mismatches")
    report["evidence_spread_recomputation"] = spread_report

    seeds = set()
    for source, target, _, cands in attributed:
        seeds.update((source, target, *cands))
    if mode == "file":
        seeds |= {"file:" + path for _, a, b in sym_attr for path in (a, b)}
    entities = {x for s in seeds for x in (normalise_entity(s), normalise_entity(parent.get(s, s)))}
    for s in seeds:
        p = parent.get(s)
        while p:
            if p.startswith("kotlin-package:"):
                entities.add(p)
            p = parent.get(p)
        if mode == "file":
            for side in (base, head):
                details = side.arch["details"]
                for member in details["file_nodes"].get(s, ()):
                    owner = details["node_owners"].get(member)
                    if owner and owner.startswith("kotlin-package:"):
                        entities.add(owner)
    candidates = {}
    kinds = sorted(set(base.candidates) | set(head.candidates))
    for kind in kinds:
        bk, hk = base.candidates.get(kind, {}), head.candidates.get(kind, {})
        gone, new = sorted(set(bk) - set(hk)), sorted(set(hk) - set(bk))
        changed = sorted(i for i in set(bk) & set(hk) if bk[i] != hk[i])
        samples = []
        for change, ids, src in (("removed", gone, bk), ("added", new, hk), ("changed", changed, hk)):
            for cid in ids:
                before, after = bk.get(cid), hk.get(cid)
                candidate = src[cid]
                why = candidate_why(stage, kind, change, before, after, base, head, ctor, entities, threshold, mode,
                                parent, edge_changes)
                if why == "unexplained":
                    bad.append(f"{kind} {change} {candidate['target']}")
                if len(samples) < 3 * SAMPLE and sum(1 for s in samples if s["change"] == change) < SAMPLE:
                    samples.append({"change": change, "target": candidate["target"], "why": why,
                                    "metrics": [(before or {}).get("metrics"), (after or {}).get("metrics")]})
        candidates[kind] = {"base": len(bk), "head": len(hk), "removed": len(gone), "added": len(new),
                            "changed": len(changed), "samples": samples}
    report["candidates"] = candidates

    # ---- structural metrics (RV8)
    neighbours = collections.defaultdict(set)
    for e in base.edges + head.edges:
        neighbours[e["from_id"]].add(e["to_id"])
        neighbours[e["to_id"]].add(e["from_id"])
        for alternative in e.get("candidates", ()):
            neighbours[e["from_id"]].add(alternative)
            neighbours[alternative].add(e["from_id"])
    def within_two(start):
        reached, frontier = set(start), set(start)
        for _ in range(2):
            frontier = {m for n in frontier for m in neighbours[n]} - reached
            reached |= frontier
        return reached

    changed_nodes = set(seeds)
    cost_changed = {n for n in ctor if n in head.metrics and n in base.metrics
                    and base.metrics[n].get("token_cost") != head.metrics[n].get("token_cost")}
    near = within_two(changed_nodes | (cost_changed if stage == "b" else set()))
    changes = collections.Counter()

    def judge(key, node_id, ok):
        changes[f"{key} ({'allowed' if ok else 'unexplained'})"] += 1
        if not ok:
            bad.append(f"{key} changed on {node_id}")

    for node_id in sorted(set(base.metrics) & set(head.metrics)):
        before, after = base.metrics[node_id], head.metrics[node_id]
        for key in ENDPOINT_METRICS:
            if before.get(key) != after.get(key):
                judge(key, node_id, node_id in seeds)
        for key in COST_METRICS:
            if before.get(key) != after.get(key):
                judge(key, node_id, stage == "b" and node_id in ctor)
        if before.get("hop_2_token_cost") != after.get("hop_2_token_cost"):
            judge("hop_2_token_cost", node_id, node_id in near)
        for key in GLOBAL_METRICS:
            if before.get(key) != after.get(key):
                judge(key, node_id, (stage == "a" and key != "betweenness_centrality") or bool(edge_changes))
    for ranking in ("rankings", "rankings_by_category"):
        if base.bott["dependency_network"].get(ranking) != head.bott["dependency_network"].get(ranking):
            ok = stage == "a" or bool(edge_changes)
            changes[f"{ranking} ({'allowed' if ok else 'unexplained'})"] += 1
            if not ok:
                bad.append(f"{ranking} changed without attributed edge changes")
    report["structural_metric_changes"] = dict(changes)

    report["nontest_share"] = {"base": nontest_share(base, mode), "head": nontest_share(head, mode)}
    return report


def edge_evidence(base, head, key):
    return key[5]


def line_in_span(line, node):
    span = node_span(node)
    return line is not None and span.get("start_line") is not None and span["start_line"] <= line <= span["end_line"]


def symbol_attributed_files(symbol_pairs, name, stage):
    base_pair, head_pair = symbol_pairs
    sym = review(base_pair, head_pair, name=name, mode="symbol", stage=stage)
    return {tuple(pair) for pair in sym["attributed_file_pairs"]}, set(sym["constructor_fields"]), sym["attributed_edge_changes"]


def r13_node(node_id, ctor):
    """A constructor field, or (file mode) a file node that holds one."""
    return node_id in ctor or (node_id.startswith("file:") and any(file_of(c) == node_id[5:] for c in ctor))


def key_added_allowed(stage, label, kind, path, ctor, mode="symbol"):
    p = dotted(path)
    if stage == "a":
        if label.startswith("node "):
            return p in ("$.metadata.external_call_count", "$.metadata.external_calls",
                         "$.metadata.external_calls.<map>", "$.metadata.unresolved_reference_total")
        if label == "bottlenecks top level":
            return p == "$.edge_weights.large_node_token_threshold"
        if label.startswith("candidate "):
            if kind == "unresolved_boundary" and mode == "file" and p == "$.evidence[].unresolved_reference_total":
                return True
            return kind == "large_node" and p in ("$.metrics.token_count", "$.metrics.token_threshold")
        return False
    if label.startswith("node ") and r13_node(label[5:], ctor):
        return len(path) >= 3 and path[1] == "metadata" and path[2].startswith(R1_META_PREFIXES)
    return label.startswith("candidate ") and kind == "evidence_spread" and p == "$.metrics.directory_count"


def key_removed_allowed(stage, label, kind, path, ctor):
    if stage != "a":
        return label.startswith("node ") and r13_node(label[5:], ctor) and len(path) >= 3 and path[1] == "metadata" \
            and path[2].startswith(R1_META_PREFIXES)
    if label.startswith("node "):
        return len(path) >= 3 and path[1] == "metadata" and path[2].startswith("unresolved_")
    if label.startswith("candidate ") and kind in ("unresolved_boundary", "evidence_spread"):
        return len(path) >= 3 and path[1] == "evidence[]"
    return False


def blank_indices(value):
    if isinstance(value, dict):
        return {k: (None if k in ("detail_edge_index", "detail_edge_indices") else blank_indices(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [blank_indices(v) for v in value]
    return value


def r3_count(side, target, mode):
    """R3 recomputation of unresolved_count from architecture metadata (RV5a)."""
    if mode == "file" and target.startswith("file:"):
        details = side.arch["details"]
        nodes = [n for n in details["nodes"] if details["node_files"].get(n["id"]) == target]
    else:
        nodes = [side.nodes[target]] if target in side.nodes else []
    total = 0
    for n in nodes:
        md = n.get("metadata") or {}
        total += md.get("unresolved_reference_total", len(md.get("unresolved_references") or []))
    return total


def holds_constructor_field(target, ctor, parent):
    if target in ctor:
        return True
    if target.startswith("file:"):
        return any(file_of(c) == target[5:] for c in ctor)
    return any(parent.get(c) == target for c in ctor)


def candidate_why(stage, kind, change, before, after, base, head, ctor, entities, threshold, mode, parent=None, edge_changes=0):
    parent = parent or {}
    target = (before or after)["target"]
    if (stage == "b" and change == "changed" and edge_changes and blank_indices(before) == blank_indices(after)):
        return "R12/R13 index"
    if kind in STRUCTURE_KINDS:
        if change != "changed":
            return "unexplained"
        found = {normalise_entity(s) for s in strings_in(after)} | {normalise_entity(s) for s in strings_in(before)}
        return ("R4" if stage == "a" else "R13") if found & entities else "unexplained"
    if kind == "large_node":
        if stage == "a":
            if change == "changed":
                bm, hm = before["metrics"], after["metrics"]
                rest_same = {k: v for k, v in before.items() if k != "metrics"} == {k: v for k, v in after.items() if k != "metrics"}
                if rest_same and set(hm) - set(bm) <= {"token_count", "token_threshold"} and all(hm.get(k) == v for k, v in bm.items()):
                    return "R8"
                return "unexplained"
            if change == "added":
                m = after["metrics"]
                return "R8" if "token_count" in m and m["token_count"] > m["token_threshold"] and m["line_count"] <= m["line_threshold"] else "unexplained"
            return "unexplained"
        if change == "removed" and target in ctor and node_span(base.nodes[target]) != node_span(head.nodes[target]):
            return "R13"
        return "unexplained"
    if kind == "unresolved_boundary":
        if stage == "b":
            if not holds_constructor_field(target, ctor, parent):
                return "unexplained"
            if change == "changed" and after["metrics"].get("unresolved_count") != r3_count(head, target, mode):
                return "unexplained"
            return "R13"
        if change == "removed":
            return "R1/R4" if boundary_moved(target, base, head, mode) else "unexplained"
        if change == "changed":
            only = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
            gone = constituent_names(base, target, mode, "unresolved_calls") - constituent_names(head, target, mode, "unresolved_calls")
            if (only <= {"metrics", "evidence"} and after["metrics"].get("unresolved_count") == r3_count(head, target, mode)
                    and boundary_moved(target, base, head, mode, gone)):
                return "R1/R3/R4"
        return "unexplained"
    if kind == "evidence_spread":
        return "R5" if stage == "a" else "R11"  # validity is established by the recomputation mismatch check
    if kind == "untested_hub":
        if stage == "a" and base.metrics.get(target, {}).get("pagerank") != head.metrics.get(target, {}).get("pagerank"):
            return "R7"
        return "unexplained"
    return "unexplained"


def constituent_names(side, target, mode, key):
    """Names under metadata[key] of a node; in file mode the union over the symbol records of that file."""
    if mode == "file" and target.startswith("file:"):
        details = side.arch["details"]
        nodes = [n for n in details["nodes"] if details["node_files"].get(n["id"]) == target]
    else:
        nodes = [side.nodes[target]] if target in side.nodes else []
    names = set()
    for n in nodes:
        names |= set((n.get("metadata") or {}).get(key) or {})
    return names


def boundary_moved(target, base, head, mode, names=None):
    if names is None:
        names = constituent_names(base, target, mode, "unresolved_calls")
        if not names:
            return False
    elif not names:
        return True
    external = constituent_names(head, target, mode, "external_calls")
    if names <= external:
        return True
    parent = parent_map(base, head)
    moved = set()
    for node_id, member in head.nodes.items():
        if descendants_of(parent, target, node_id):
            md = member.get("metadata") or {}
            moved |= set(md.get("unresolved_calls") or {}) | set(md.get("external_calls") or {})
    if mode == "file":
        moved = constituent_names(head, target, mode, "unresolved_calls") | external
    return (target.endswith(".kt") or target.startswith("kotlin:")) and names <= moved


def nontest_share(side, mode):
    """Share of non-test files that carry an unresolved_boundary / evidence_spread candidate (RV8)."""
    if mode == "file":
        files = {n["id"][5:] for n in side.arch["nodes"] if n["id"].startswith("file:") and not (n.get("metadata") or {}).get("boundary")}
        basis = "file nodes"

        def path_of(target):
            return target[5:] if target.startswith("file:") else None
    else:
        files = {node_span(n).get("file_path") for n in side.arch["nodes"] if node_span(n).get("file_path")}
        basis = "files with a span in symbol mode"
        node_by = side.nodes

        def path_of(target):
            return node_span(node_by.get(target) or {}).get("file_path")
    scope = {f for f in files if is_nontest(f)}
    result = {"basis": basis, "nontest_files": len(scope)}
    for kind in ("unresolved_boundary", "evidence_spread"):
        hit = {path_of(c["target"]) for c in side.bott["candidates"] if c["kind"] == kind} & scope
        result[kind] = {"files": len(hit), "share": round(len(hit) / len(scope), 4) if scope else None}
    return result


# ------------------------------------------------------------------ CLI

def load(directory, name, mode):
    with open(f"{directory}/{name}-{mode}.json") as a, open(f"{directory}/{name}-{mode}.b.json") as b:
        return json.load(a), json.load(b)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--stage" not in argv:
        sys.exit("usage: review_diff.py <base_dir> <head_dir> <name> <mode> <out.json> --stage a|b")
    at = argv.index("--stage")
    stage = argv[at + 1]
    del argv[at:at + 2]
    base_dir, head_dir, name, mode, out = argv
    if stage not in ("a", "b") or mode not in ("file", "symbol"):
        sys.exit("stage must be a|b and mode file|symbol")
    try:
        base_pair, head_pair = load(base_dir, name, mode), load(head_dir, name, mode)
        symbol_pairs = (load(base_dir, name, "symbol"), load(head_dir, name, "symbol")) if mode == "file" else None
    except OSError as error:
        sys.exit(f"review_diff: missing input: {error}")
    report = review(base_pair, head_pair, name=name, mode=mode, stage=stage, symbol_pairs=symbol_pairs)
    with open(out, "w") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False, sort_keys=True)
    print(f"{name} {mode} stage {stage}: nodes {report['nodes']['base']}/{report['nodes']['head']} edges "
          f"{report['edges']['base']}/{report['edges']['head']} unexplained {len(report['unexplained'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
