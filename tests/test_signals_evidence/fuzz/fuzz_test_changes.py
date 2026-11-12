"""Fuzz compute_delta test-change lists (spec fda1b3f71e2390f3 V13). argv: repo root, base_commit delta.py path.
P1 metamorphic: one symbol and test case model rendered with old and renamed paths plus the renames gives empty new lists.
P2 differential: apart from the delta.v5 keys, the result equals base_commit delta.v4 on the payloads without the new columns and tables.
P3: with independent baseline and current models (and renames), the three lists equal a reference computed on model keys."""
import copy, importlib.util, json, random
from pathlib import Path

sym_spec = importlib.util.spec_from_file_location("fuzz_symbols", Path(__file__).resolve().parents[2] / "symbol_changes_evidence/fuzz/fuzz_symbols.py")
sym = importlib.util.module_from_spec(sym_spec); sym_spec.loader.exec_module(sym)
prev, compute_delta, base_delta = sym.prev, sym.compute_delta, sym.base_delta

SEED, N = 20261113, 5000
REACH = ("tested", "uncertain", "untested")
CASE_NAMES = ("test_a", "test_b", "Cls.test_a", "Cls.Inner.test_c", "D > t", "D > t [2]", "D > E > it works", "<dynamic>", "Repo.loadsItems")
NEW_KEYS = ("test_changes", "untested_changes", "weakened_tests", "added_mocks")
SYMBOL_COLUMNS = sym.COLUMNS + ["branches", "test_reach"]
CASE_COLUMNS = ["id", "file", "name", "strong_assertions", "weak_assertions", "mocks", "skipped"]
COUNT_KEYS = ("strong_assertions", "weak_assertions", "mocks", "skipped")


def symbol_model(rnd, n):
    out = sym.symbol_model(rnd, n)
    for record in out.values():
        callable_kind = record["kind"] in ("function", "method")
        record["branches"] = rnd.choice((None, 0, 1, 2, 3, 5)) if callable_kind else None
        record["test_reach"] = rnd.choice(REACH)
    return out


def case_model(rnd, n):
    out = {}
    for _ in range(rnd.randint(0, 20)):
        out[(rnd.randrange(n), rnd.choice(CASE_NAMES))] = {"strong_assertions": rnd.choice((0, 0, 1, 2, 4)), "weak_assertions": rnd.choice((0, 1, 3)),
                                                          "mocks": rnd.choice((0, 0, 1, 2, 3, 4, 7)), "skipped": rnd.random() < 0.2}
    return out


def mutate_cases(rnd, cases):
    """Current-side cases derived from the baseline so that same-id comparisons are frequent."""
    out = {}
    for key, record in cases.items():
        if rnd.random() < 0.15: continue
        record = dict(record)
        for name in ("strong_assertions", "weak_assertions", "mocks"):
            if rnd.random() < 0.3: record[name] = max(0, record[name] + rnd.choice((-2, -1, 1, 2, 3)))
        if rnd.random() < 0.15: record["skipped"] = not record["skipped"]
        out[key] = record
    return out


def mutate_symbols(rnd, symbols):
    out = {}
    for key, record in symbols.items():
        if rnd.random() < 0.15: continue
        record = dict(record)
        if record["branches"] is not None and rnd.random() < 0.4: record["branches"] = max(0, record["branches"] + rnd.choice((-1, 1, 2)))
        if rnd.random() < 0.2: record["test_reach"] = rnd.choice(REACH)
        out[key] = record
    return out


def with_data(payload, symbols, cases, paths, rnd, *, test_data=True):
    """Renders `symbols` in place (signature variant per payload); `test_data=False` gives the base_commit shape."""
    payload = copy.deepcopy(payload)
    network = payload["dependency_network"]
    index = {f: k for k, f in enumerate(network["file_ids"])}
    rows = sym.render_symbols(symbols, paths, rnd)
    columns = SYMBOL_COLUMNS if test_data else sym.COLUMNS
    network["symbol_columns"] = list(columns)
    network["symbols"] = [[index[row["file"]] if c == "file" else row[c] for c in columns] for row in rows]
    if test_data:
        case_rows = sorted(([case_id(paths[i], name), index["file:" + paths[i]], name, *(record[k] for k in COUNT_KEYS)]
                            for (i, name), record in cases.items()), key=lambda row: row[0])
        network["test_case_columns"] = list(CASE_COLUMNS)
        network["test_cases"] = case_rows
    return payload


def project(payload):
    """The same payload in the base_commit shape (eight symbol columns, no test case table)."""
    payload = copy.deepcopy(payload)
    network = payload["dependency_network"]
    network.pop("test_cases", None); network.pop("test_case_columns", None)
    if "symbol_columns" in network:
        keep = [network["symbol_columns"].index(c) for c in sym.COLUMNS]
        network["symbols"] = [[row[k] for k in keep] for row in network["symbols"]]
        network["symbol_columns"] = list(sym.COLUMNS)
    return payload


def case_id(path, name):
    return "file:" + path + "#" + name


def counts(record):
    return {k: record[k] for k in COUNT_KEYS}


def reference(base_syms, cur_syms, base_cases, cur_cases, paths):
    untested, weakened, mocks = [], [], []
    for key, c in cur_syms.items():
        i, name = key
        if c["kind"] not in ("function", "method") or c["test_reach"] == "tested":
            continue
        b = base_syms.get(key)
        grew = b is not None and isinstance(b["branches"], int) and isinstance(c["branches"], int) and c["branches"] > b["branches"]
        if b is None or grew:
            untested.append({"id": sym.symbol_id(paths[i], name), "file": "file:" + paths[i], "kind": c["kind"], "name": name,
                             "baseline_branches": None if b is None else b["branches"], "current_branches": c["branches"], "test_reach": c["test_reach"]})
    for key in set(base_cases) | set(cur_cases):
        i, name = key
        b, c = base_cases.get(key), cur_cases.get(key)
        common = {"id": case_id(paths[i], name), "file": "file:" + paths[i], "name": name}
        reasons = []
        if b and c:
            if c["strong_assertions"] < b["strong_assertions"]: reasons.append("fewer_strong_assertions")
            if not b["skipped"] and c["skipped"]: reasons.append("newly_skipped")
        elif b:
            reasons.append("removed")
        elif c["strong_assertions"] == 0:
            reasons.append("new_without_strong_assertions")
        if reasons:
            weakened.append(dict(common, reasons=sorted(reasons), baseline=counts(b) if b else None, current=counts(c) if c else None))
        if c and ((b is None and c["mocks"] >= 3) or (b is not None and c["mocks"] - b["mocks"] >= 2)):
            mocks.append(dict(common, baseline_mocks=b["mocks"] if b else None, current_mocks=c["mocks"]))
    key = lambda r: r["id"]
    return sorted(untested, key=key), sorted(weakened, key=key), sorted(mocks, key=key)


def strip(d):
    d = dict(d); d.pop("policy", None); counts_ = dict(d.get("counts") or {})
    for key in NEW_KEYS: d.pop(key, None); counts_.pop(key, None)
    d["counts"] = counts_; return d


def lists_empty(d):
    return not (d["untested_changes"] or d["weakened_tests"] or d["added_mocks"])


def main():
    rnd = random.Random(SEED)
    fails = {"P1": 0, "P2": 0, "P3": 0, "exceptions": 0}
    examples, stats = [], {"executed": 0, "rename_pairs": 0, "untested": 0, "weakened": 0, "mocks": 0}
    bases = prev.BASES + ("Main.kt", "ui/Screen.kt", "test_a.py", "a_test.py", "a.spec.ts", "util.test.js", "RepoTest.kt")
    while stats["executed"] < N:
        try:
            paths = prev.python_paths(sorted(set(rnd.choice(prev.DIRS) + rnd.choice(bases) for _ in range(rnd.randint(2, 8)))))
            if len(paths) < 2: continue
            stats["executed"] += 1
            m = prev.model(rnd, paths)
            new_paths, pairs = prev.renamed(rnd, paths)
            if len({prev.module(p) for p in new_paths if p.endswith(".py")}) != sum(p.endswith(".py") for p in new_paths):
                new_paths, pairs = paths, []
            stats["rename_pairs"] += len(pairs)
            ren = {"status": "applied", "reason": None, "pairs": pairs}
            syms, cases = symbol_model(rnd, len(paths)), case_model(rnd, len(paths))
            a = with_data(prev.render(m, paths), syms, cases, paths, rnd)
            b = with_data(prev.render(m, new_paths), copy.deepcopy(syms), copy.deepcopy(cases), new_paths, rnd)
            d1 = compute_delta(b, copy.deepcopy(a), ren)
            if not lists_empty(d1) or d1["test_changes"] != {"status": "applied", "reason": None}:
                fails["P1"] += 1; examples.append(("P1", pairs, d1["untested_changes"][:2], d1["weakened_tests"][:2], d1["added_mocks"][:2]))
            c_model = prev.model(rnd, paths)
            c_syms = mutate_symbols(rnd, syms) if rnd.random() < 0.7 else symbol_model(rnd, len(paths))
            c_syms.update({k: v for k, v in symbol_model(rnd, len(paths)).items() if k not in c_syms and rnd.random() < 0.3})
            c_cases = mutate_cases(rnd, cases) if rnd.random() < 0.7 else case_model(rnd, len(paths))
            c_cases.update({k: v for k, v in case_model(rnd, len(paths)).items() if k not in c_cases and rnd.random() < 0.3})
            plain_a, plain_c = prev.render(m, paths), prev.render(c_model, new_paths)
            full_a = with_data(plain_a, syms, cases, paths, rnd)
            full_c = with_data(plain_c, c_syms, c_cases, new_paths, rnd)
            old_a = with_data(plain_a, syms, cases, paths, rnd, test_data=False)
            old_c = with_data(plain_c, c_syms, c_cases, new_paths, rnd, test_data=False)
            for case, (cur, base_payload, reason) in {
                    "none": (plain_c, plain_a, "baseline_without_test_data"),
                    "old_both": (old_c, old_a, "baseline_without_test_data"),
                    "cur_only": (full_c, old_a, "baseline_without_test_data"),
                    "base_only": (old_c, full_a, "current_without_test_data"),
                    "base_only_plain": (plain_c, full_a, "current_without_test_data"),
                    "both": (full_c, full_a, None)}.items():
                got = compute_delta(copy.deepcopy(cur), copy.deepcopy(base_payload), ren)
                want = base_delta.compute_delta(project(cur), project(base_payload), ren)
                status = {"status": "skipped" if reason else "applied", "reason": reason}
                counts_ok = all(got["counts"].get(k) == len(got[k]) for k in NEW_KEYS[1:])
                if strip(got) != strip(want) or got["policy"] != "delta.v5" or got["test_changes"] != status or not counts_ok or (reason and not lists_empty(got)):
                    fails["P2"] += 1; examples.append(("P2", case, {k: (got.get(k), want.get(k)) for k in set(got) | set(want) if got.get(k) != want.get(k)}))
                if case == "both":
                    untested, weakened, mocks = reference(syms, c_syms, cases, c_cases, new_paths)
                    stats["untested"] += len(untested); stats["weakened"] += len(weakened); stats["mocks"] += len(mocks)
                    if (got["untested_changes"], got["weakened_tests"], got["added_mocks"]) != (untested, weakened, mocks):
                        fails["P3"] += 1
                        examples.append(("P3", pairs, [(n, g, w) for n, g, w in (("untested", got["untested_changes"], untested),
                                                                                 ("weakened", got["weakened_tests"], weakened),
                                                                                 ("mocks", got["added_mocks"], mocks)) if g != w]))
        except Exception as exc:  # noqa: BLE001
            fails["exceptions"] += 1; examples.append(("exc", f"{type(exc).__name__}: {exc}"))
    print(json.dumps({"seed": SEED, "inputs": N, **stats, "failures": fails,
                      "examples": [json.dumps(e, default=str)[:1500] for e in examples[:5]]}, indent=1))


if __name__ == "__main__":
    main()
