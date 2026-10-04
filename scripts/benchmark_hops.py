import gc
import json
import math
import random
import statistics
import sys
import time
import tracemalloc
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis import GraphAnalyzer


REPEATS = 3
ARTIFACT = Path("/private/tmp/network-analysis-exact-hop-benchmark.json")


def build_graph(size, pairs):
    adjacency = {f"n{i}": set() for i in range(size)}
    for a, b in pairs:
        if a != b:
            adjacency[f"n{a}"].add(f"n{b}")
            adjacency[f"n{b}"].add(f"n{a}")
    return adjacency


def datasets():
    rng = random.Random(1729)
    return [
        ("chain1500", build_graph(1500, ((i, i + 1) for i in range(1499))), {"shape": "chain", "nodes": 1500}),
        ("tree1500", build_graph(1500, (((i - 1) // 2, i) for i in range(1, 1500))), {"shape": "binary_tree", "nodes": 1500}),
        ("hub1500", build_graph(1500, ((0, i) for i in range(1, 1500))), {"shape": "hub", "nodes": 1500}),
        ("dense300", build_graph(300, ((i, j) for i in range(300) for j in range(i))), {"shape": "complete", "nodes": 300}),
        ("random800", build_graph(800, ((rng.randrange(800), rng.randrange(800)) for _ in range(8 * 800))), {"shape": "random_pairs", "nodes": 800, "seed": 1729, "pairs": 8 * 800}),
    ]


def original_bfs_with_sums(adjacency, ticks):
    costs = {node: tick / 10 for node, tick in ticks.items()}
    result = {}
    for start in adjacency:
        visited = {start}
        pending = deque([(start, 0)])
        h2, h3 = set(), set()
        while pending:
            node, depth = pending.popleft()
            if depth == 3:
                continue
            next_depth = depth + 1
            for target in adjacency[node]:
                if target in visited:
                    continue
                visited.add(target)
                pending.append((target, next_depth))
                h3.add(target)
                if next_depth <= 2:
                    h2.add(target)
        result[start] = (len(h2), sum(costs[target] for target in h2), len(h3), sum(costs[target] for target in h3))
    return result


def legacy_neighborhoods_with_sums(analyzer, adjacency, ticks):
    costs = {node: tick / 10 for node, tick in ticks.items()}
    result = {}
    for start in adjacency:
        h2, h3 = analyzer._neighborhoods(start, adjacency)
        result[start] = (len(h2), sum(costs[target] for target in h2),
                         len(h3), sum(costs[target] for target in h3))
    return result


def assert_equivalent(actual, expected):
    assert actual.keys() == expected.keys()
    for node in expected:
        for index in (0, 2):
            assert actual[node][index] == expected[node][index], (node, index)
        for index in (1, 3):
            assert math.isclose(actual[node][index], expected[node][index], rel_tol=1e-12, abs_tol=1e-9), (node, index)


def measure_seconds(call):
    samples = []
    for _ in range(REPEATS):
        gc.collect()
        started = time.perf_counter()
        result = call()
        samples.append(time.perf_counter() - started)
        del result
    return {"samples_seconds": samples, "median_seconds": statistics.median(samples)}


def measure_peak(call):
    gc.collect()
    tracemalloc.start()
    try:
        result = call()
        _, peak = tracemalloc.get_traced_memory()
        del result
        return peak
    finally:
        tracemalloc.stop()


def main():
    records = []
    for name, adjacency, parameters in datasets():
        ticks = {node: (index * 37) % 10031 for index, node in enumerate(adjacency)}
        analyzer = GraphAnalyzer()
        optimized = lambda: analyzer._neighborhood_metrics(adjacency, ticks)
        baseline = lambda: legacy_neighborhoods_with_sums(analyzer, adjacency, ticks)
        actual, strategy = optimized()
        expected = original_bfs_with_sums(adjacency, ticks)
        legacy = baseline()
        assert_equivalent(actual, expected)
        assert_equivalent(legacy, expected)
        del actual, expected, legacy
        parameters["undirected_edges"] = sum(map(len, adjacency.values())) // 2
        record = {
            "dataset": name,
            "parameters": parameters,
            "strategy": strategy,
            "exact_oracle_equivalence": True,
            "baseline": measure_seconds(baseline),
            "optimized": measure_seconds(optimized),
        }
        record["baseline"]["tracemalloc_peak_bytes"] = measure_peak(baseline)
        record["optimized"]["tracemalloc_peak_bytes"] = measure_peak(optimized)
        records.append(record)
        print(json.dumps(record), flush=True)
    artifact = {
        "spec": "6c2e9b03f7a841d5", "version": 2,
        "python": sys.version, "repeats": REPEATS,
        "correctness_oracle": "Independent deque BFS with separate sums",
        "baseline": "Retained GraphAnalyzer._neighborhoods with legacy separate float-cost sums",
        "measurement_context": "Hop phase includes component discovery, index/mask/cost-plane preparation and aggregation; input adjacency and ticks are prebuilt. Timing and allocation tracing are separate runs.",
        "acceptance": "Exact equivalence only; timing and peak ratios are report-only.",
        "datasets": records,
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"Artifact: {ARTIFACT}", flush=True)


if __name__ == "__main__":
    main()
