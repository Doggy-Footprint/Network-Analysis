#!/usr/bin/env python3
"""Compare two analysis JSON outputs (code-analyzer --json) of the same project: base commit vs HEAD.

Usage:
  review_diff.py BASE.json HEAD.json [--root PROJECT] [--seed 20261019] [--sample 10]
                 [--base-bottlenecks B.json --head-bottlenecks H.json]

Prints (1) the (relation, resolution) count diff, (2) added/removed edges grouped by (relation, resolution),
(3) nodes whose span end_line or cost.line_count changed, (4) candidate-kind count diff and top-level key diff when
bottleneck files are given, (5) a seeded sample of added edges with the source line they cite (needs --root).
Stdlib only. Exit code 0 always; the reviewer decides acceptance from the printed tables.
"""
import argparse
import json
import random
from collections import Counter
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def edge_key(edge):
    return (edge['from_id'], edge['to_id'], edge['relation'], edge['confidence'], edge['resolution'],
            tuple(edge.get('candidates') or ()))


def counts(edges):
    return Counter((e['relation'], e['resolution']) for e in edges)


def print_count_diff(base_edges, head_edges):
    base, head = counts(base_edges), counts(head_edges)
    print('== (relation, resolution) count diff: base -> head')
    print(f'{"relation":<16}{"resolution":<12}{"base":>8}{"head":>8}{"delta":>8}')
    for key in sorted(set(base) | set(head)):
        delta = head[key] - base[key]
        if delta:
            print(f'{key[0]:<16}{key[1]:<12}{base[key]:>8}{head[key]:>8}{delta:>+8}')
    print(f'total edges: base={len(base_edges)} head={len(head_edges)}')


def edge_sets(base_edges, head_edges):
    base, head = Counter(map(edge_key, base_edges)), Counter(map(edge_key, head_edges))
    return head - base, base - head


def print_edge_changes(added, removed):
    for title, bag in (('added', added), ('removed', removed)):
        grouped = Counter((k[2], k[4], k[3]) for k in bag.elements())
        print(f'== {title} edges by (relation, resolution, confidence): {sum(bag.values())}')
        for (relation, resolution, confidence), n in sorted(grouped.items()):
            print(f'  {relation:<16}{resolution:<12}{confidence:<20}{n:>6}')


def print_node_changes(base, head):
    base_nodes = {n['id']: n for n in base['nodes']}
    head_nodes = {n['id']: n for n in head['nodes']}
    print('== nodes with changed span end_line / cost.line_count (F8/F9)')
    changed = 0
    for node_id in sorted(set(base_nodes) & set(head_nodes)):
        a, b = base_nodes[node_id], head_nodes[node_id]
        span_a, span_b = (a.get('span') or {}), (b.get('span') or {})
        row_a = (span_a.get('end_line'), (a.get('cost') or {}).get('line_count'))
        row_b = (span_b.get('end_line'), (b.get('cost') or {}).get('line_count'))
        if row_a != row_b:
            changed += 1
            print(f'  {node_id}: (end_line, line_count) {row_a} -> {row_b}')
    print(f'  changed nodes: {changed}; only in base: {len(set(base_nodes) - set(head_nodes))}; '
          f'only in head: {len(set(head_nodes) - set(base_nodes))}')


def print_bottlenecks(base, head):
    print('== bottleneck payload')
    print(f'  schema: base={base.get("schema")} head={head.get("schema")}')
    for name in ('top-level', 'dependency_network', 'edge_weights', 'coverage'):
        a = set(base) if name == 'top-level' else set(base.get(name, {}))
        b = set(head) if name == 'top-level' else set(head.get(name, {}))
        print(f'  {name} keys only in base: {sorted(a - b)}; only in head: {sorted(b - a)}')
    kinds_a = Counter(c['kind'] for c in base['candidates'])
    kinds_b = Counter(c['kind'] for c in head['candidates'])
    print('  candidate kind counts (base -> head)')
    for kind in sorted(set(kinds_a) | set(kinds_b)):
        print(f'    {kind:<22}{kinds_a[kind]:>6}{kinds_b[kind]:>6}{kinds_b[kind] - kinds_a[kind]:>+6}')
    ids_a = {c['id']: c for c in base['candidates']}
    ids_b = {c['id']: c for c in head['candidates']}
    for title, ids in (('new candidates', sorted(set(ids_b) - set(ids_a))), ('gone candidates', sorted(set(ids_a) - set(ids_b)))):
        source = ids_b if title.startswith('new') else ids_a
        print(f'  {title}: {len(ids)}')
        for ident in ids:
            print(f'    {source[ident]["kind"]:<20}{source[ident]["target"]}')


def sample_edges(added, seed, size, root):
    pool = sorted(added.elements())
    rng = random.Random(seed)
    chosen = rng.sample(pool, min(size, len(pool)))
    print(f'== {len(chosen)} sampled added edges (seed={seed}); verify each against the cited source line')
    for index, key in enumerate(chosen, 1):
        print(f'[{index}] {key[0]} -{key[2]}-> {key[1]}  ({key[3]}, {key[4]}, candidates={list(key[5])})')
    return chosen


def print_source_lines(head_edges, chosen, root):
    by_key = {}
    for edge in head_edges:
        by_key.setdefault(edge_key(edge), edge)
    for index, key in enumerate(chosen, 1):
        evidence = by_key[key].get('evidence') or {}
        path, line = evidence.get('file_path'), evidence.get('start_line')
        text = '(no evidence location)'
        if root and path and line:
            file = Path(root) / path
            if file.is_file():
                lines = file.read_text(encoding='utf-8', errors='replace').split('\n')
                text = lines[line - 1] if 0 < line <= len(lines) else '(line out of range)'
            else:
                text = '(file missing)'
        print(f'[{index}] {path}:{line}: {text.strip()}')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('base')
    parser.add_argument('head')
    parser.add_argument('--root', help='analysed project directory, to print cited source lines')
    parser.add_argument('--seed', type=int, default=20261019)
    parser.add_argument('--sample', type=int, default=10)
    parser.add_argument('--base-bottlenecks')
    parser.add_argument('--head-bottlenecks')
    args = parser.parse_args()
    base, head = load(args.base), load(args.head)
    print_count_diff(base['edges'], head['edges'])
    added, removed = edge_sets(base['edges'], head['edges'])
    print_edge_changes(added, removed)
    print_node_changes(base, head)
    if args.base_bottlenecks and args.head_bottlenecks:
        print_bottlenecks(load(args.base_bottlenecks), load(args.head_bottlenecks))
    chosen = sample_edges(added, args.seed, args.sample, args.root)
    print_source_lines(head['edges'], chosen, args.root)


if __name__ == '__main__':
    main()
