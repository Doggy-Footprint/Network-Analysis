"""Measure one repository revision for the OSS refactoring evaluation.

Run with eval/.venv/bin/python (lizard, grimp). The analyzer under evaluation runs in
the project .venv as a subprocess, so its metrics never feed the independent ones.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import lizard

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / 'eval'
MANIFEST = json.loads((Path(__file__).parent / 'repos.json').read_text())
SKIP_DIRS = {'.git', '__pycache__', 'build', 'dist', 'env', 'node_modules', 'venv', '.gradle'}
EXTENSIONS = {'python': ('.py',), 'typescript': ('.ts', '.tsx'), 'kotlin': ('.kt',)}
IMPORT_RELATIONS = {'IMPORTS', 'IMPORTS_SYMBOL', 'RE_EXPORTS'}
HIGH_CCN, LONG_FUNCTION = 15, 60


def export(repo, rev, snap):
    if snap.exists():
        shutil.rmtree(snap)
    snap.mkdir(parents=True)
    archive = subprocess.run(['git', '-C', str(EVAL / 'repos' / repo), 'archive', rev], check=True, capture_output=True).stdout
    subprocess.run(['tar', '-x', '-C', str(snap)], input=archive, check=True)


def source_files(snap, language):
    exts = EXTENSIONS[language]
    for path in sorted(snap.rglob('*')):
        rel = path.relative_to(snap)
        if path.is_file() and path.suffix in exts and not SKIP_DIRS & set(rel.parts[:-1]) and not rel.name.endswith('.d.ts'):
            yield rel.as_posix()


def is_test(path):
    parts = path.lower().split('/')
    return any(p in ('test', 'tests', 'testing', 'androidtest', 'testfixtures') or p.startswith('test_') for p in parts) or re.search(r'(\.spec\.tsx?$|_test\.py$|Test\.kt$)', path) is not None


def run_analyzer(repo, snap, out):
    cmd = [str(ROOT / '.venv/bin/python'), '-m', 'code_analyzer', str(snap), *MANIFEST[repo]['analyzers'],
           '-o', str(out / 'report.html'), '--json', '--bottlenecks', str(out / 'bottlenecks.json'), '--title', repo]
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    seconds = time.perf_counter() - start
    (out / 'analyzer.log').write_text(proc.stdout + proc.stderr)
    result = {'command': cmd, 'seconds': round(seconds, 2), 'returncode': proc.returncode}
    if proc.returncode != 0:
        return result, None
    arch = json.loads((out / 'report.json').read_text())
    bottlenecks = json.loads((out / 'bottlenecks.json').read_text())
    network = bottlenecks['dependency_network']
    result.update(node_count=len(arch['nodes']), edge_count=len(arch['edges']),
                  relations=dict(Counter(e['relation'] for e in arch['edges'])),
                  confidence=dict(Counter(e['confidence'] for e in arch['edges'])),
                  resolution=dict(Counter(e['resolution'] for e in arch['edges'])),
                  candidates=dict(Counter(c['kind'] for c in bottlenecks['candidates'])),
                  coverage=bottlenecks.get('coverage'), limitations=bottlenecks.get('limitations'),
                  top_production={key: [r['node_id'] for r in rows[:10]] for key, rows in network['rankings_by_category']['production'].items()})
    return result, arch


def measure_lizard(snap, files):
    per_file, failed = {}, []
    for rel in files:
        try:
            info = lizard.analyze_file(str(snap / rel))
        except Exception as error:
            failed.append(f'{rel}: {type(error).__name__}')
            continue
        ccns = [f.cyclomatic_complexity for f in info.function_list]
        per_file[rel] = {'nloc': info.nloc, 'functions': len(ccns), 'ccn_sum': sum(ccns), 'ccn_max': max(ccns, default=0),
                         'high_ccn': sum(c > HIGH_CCN for c in ccns),
                         'long_functions': sum(f.nloc > LONG_FUNCTION for f in info.function_list), 'test': is_test(rel)}
    return per_file, failed


def lizard_totals(per_file, production_only=True):
    rows = [v for v in per_file.values() if not (production_only and v['test'])]
    functions = sum(r['functions'] for r in rows)
    return {'files': len(rows), 'nloc': sum(r['nloc'] for r in rows), 'functions': functions,
            'ccn_avg': round(sum(r['ccn_sum'] for r in rows) / functions, 3) if functions else 0,
            'ccn_max': max((r['ccn_max'] for r in rows), default=0),
            'high_ccn_functions': sum(r['high_ccn'] for r in rows), 'long_functions': sum(r['long_functions'] for r in rows)}


def python_imports(snap, packages):
    import grimp
    sys.path.insert(0, str(snap))
    try:
        graph = grimp.build_graph(*packages, cache_dir=None)
    finally:
        sys.path.remove(str(snap))
    def file_of(module):
        base = snap / module.replace('.', '/')
        for candidate in (base.with_suffix('.py'), base / '__init__.py'):
            if candidate.is_file():
                return candidate.relative_to(snap).as_posix()
    edges, scope = set(), {file_of(m) for m in graph.modules} - {None}
    for module in graph.modules:
        source = file_of(module)
        for imported in graph.find_modules_directly_imported_by(module):
            target = file_of(imported)
            if source and target and source != target:
                edges.add((source, target))
    return edges, 'grimp (static, package-scoped: %s)' % ', '.join(packages), scope


def typescript_imports(snap, spec):
    cmd = [str(EVAL / 'node/node_modules/.bin/depcruise'), '--no-config', '--output-type', 'json', '--do-not-follow', 'node_modules',
           '--exclude', 'node_modules|\\.d\\.ts$', '--ts-pre-compilation-deps', *spec['roots']]
    if spec.get('ts_config'):
        cmd[1:1] = ['--ts-config', spec['ts_config']]
    proc = subprocess.run(cmd, cwd=snap, capture_output=True, text=True)
    if proc.returncode not in (0, 1) or not proc.stdout.strip():
        raise RuntimeError(proc.stderr[-2000:])
    modules = json.loads(proc.stdout)['modules']
    edges, unresolved = set(), 0
    scope = {m['source'] for m in modules if (snap / m['source']).is_file()}
    for module in modules:
        for dep in module.get('dependencies', []):
            if dep.get('couldNotResolve'):
                unresolved += 1
                continue
            target = dep.get('resolved', '')
            if target != module['source'] and (snap / target).is_file() and 'node_modules' not in target:
                edges.add((module['source'], target))
    return edges, f'dependency-cruiser 18.7.0 (unresolved specifiers: {unresolved})', scope


KT_DECL = re.compile(r'^(?:(?:public|internal|private|protected|data|sealed|abstract|open|enum|annotation|inline|value|const|expect|actual|suspend|operator|infix|tailrec|external|fun\s+interface)\s+)*'
                     r'(?:class|interface|object|fun|val|var|typealias)\s+(?:<[^>]*>\s*)?(?:[\w.]+(?:<[^>]*>)?\??\.)?(\w+)', re.M)


def kotlin_imports(snap, files):
    package_of, declared, by_fqn, by_package = {}, {}, defaultdict(set), defaultdict(lambda: defaultdict(set))
    texts = {}
    for rel in files:
        text = (snap / rel).read_text(errors='replace')
        texts[rel] = text
        match = re.search(r'^\s*package\s+([\w.]+)', text, re.M)
        package = match.group(1) if match else ''
        package_of[rel] = package
        names = set(KT_DECL.findall(text))
        declared[rel] = names
        for name in names:
            by_fqn[f'{package}.{name}' if package else name].add(rel)
            by_package[package][name].add(rel)
    edges = set()
    for rel, text in texts.items():
        tokens = set(re.findall(r'\b[A-Za-z_]\w*\b', re.sub(r'^\s*(package|import)\s.*$', '', text, flags=re.M)))
        visible = [package_of[rel]]
        for fqn, star in re.findall(r'^\s*import\s+([\w.`]+?)(\.\*)?(?:\s+as\s+\w+)?\s*$', text, re.M):
            fqn = fqn.replace('`', '')
            if star:
                visible.append(fqn)
                continue
            parts = fqn.split('.')
            for cut in range(len(parts), 0, -1):
                targets = by_fqn.get('.'.join(parts[:cut]))
                if targets:
                    edges.update((rel, t) for t in targets if t != rel)
                    break
        for package in visible:
            for name, targets in by_package.get(package, {}).items():
                if name in tokens:
                    edges.update((rel, t) for t in targets if t != rel)
    return edges, 'regex package/import resolver (explicit + star imports + same-package identifier references)', set(files)


def graph_metrics(nodes, edges):
    adjacency = defaultdict(set)
    for a, b in edges:
        adjacency[a].add(b)
    index, low, on_stack, stack, sccs, counter = {}, {}, set(), [], [], [0]
    for root in sorted(nodes):
        if root in index:
            continue
        work = [(root, iter(sorted(adjacency[root])))]
        index[root] = low[root] = counter[0]; counter[0] += 1; stack.append(root); on_stack.add(root)
        while work:
            node, children = work[-1]
            child = next(children, None)
            if child is not None:
                if child not in index:
                    index[child] = low[child] = counter[0]; counter[0] += 1; stack.append(child); on_stack.add(child)
                    work.append((child, iter(sorted(adjacency[child]))))
                elif child in on_stack:
                    low[node] = min(low[node], index[child])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    item = stack.pop(); on_stack.discard(item); component.append(item)
                    if item == node:
                        break
                if len(component) > 1:
                    sccs.append(sorted(component))
    fan_in, fan_out = Counter(b for _, b in edges), Counter(a for a, _ in edges)
    return {'nodes': len(nodes), 'edges': len(edges), 'cycle_count': len(sccs), 'largest_cycle': max(map(len, sccs), default=0),
            'files_in_cycles': sum(map(len, sccs)), 'max_fan_in': max(fan_in.values(), default=0), 'max_fan_out': max(fan_out.values(), default=0)}, sccs


def agreement(arch, independent, scope):
    file_set = set(scope)
    ours_import, ours_any = set(), set()
    for e in arch['edges']:
        a, b = e['from_id'].removeprefix('file:'), e['to_id'].removeprefix('file:')
        if a in file_set and b in file_set and a != b:
            ours_any.add((a, b))
            if e['relation'] in IMPORT_RELATIONS:
                ours_import.add((a, b))
    known = {n['id'].removeprefix('file:') for n in arch['nodes']} & file_set
    reference = {(a, b) for a, b in independent if a in known and b in known}
    def ratio(x, y):
        return round(x / y, 4) if y else None
    return {'reference_edges': len(reference), 'our_import_edges': len(ours_import), 'our_any_edges': len(ours_any),
            'import_recall': ratio(len(reference & ours_import), len(reference)),
            'import_precision': ratio(len(reference & ours_import), len(ours_import)),
            'any_relation_recall': ratio(len(reference & ours_any), len(reference)),
            'files_known_to_both': len(known), 'reference_scope_files': len(file_set),
            'missed_sample': sorted(reference - ours_any)[:25], 'extra_import_sample': sorted(ours_import - reference)[:25]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('repo', choices=sorted(MANIFEST))
    parser.add_argument('label')
    parser.add_argument('--rev', default='HEAD')
    parser.add_argument('--skip-analyzer', action='store_true')
    args = parser.parse_args()
    spec = MANIFEST[args.repo]
    snap, out = EVAL / 'snap' / args.repo / args.label, EVAL / 'results' / args.repo / args.label
    out.mkdir(parents=True, exist_ok=True)
    rev = subprocess.run(['git', '-C', str(EVAL / 'repos' / args.repo), 'rev-parse', args.rev], check=True, capture_output=True, text=True).stdout.strip()
    export(args.repo, rev, snap)
    files = list(source_files(snap, spec['language']))
    summary = {'repo': args.repo, 'cell': spec['cell'], 'label': args.label, 'rev': rev}
    arch = None
    if not args.skip_analyzer:
        summary['analyzer'], arch = run_analyzer(args.repo, snap, out)
    elif (out / 'report.json').exists() and (out / 'summary.json').exists():
        summary['analyzer'] = json.loads((out / 'summary.json').read_text()).get('analyzer')
        arch = json.loads((out / 'report.json').read_text())
    per_file, lizard_failed = measure_lizard(snap, files)
    (out / 'lizard.json').write_text(json.dumps(per_file, indent=1, sort_keys=True))
    summary['lizard'] = {'production': lizard_totals(per_file), 'all': lizard_totals(per_file, production_only=False), 'parse_failures': lizard_failed}
    if spec['language'] == 'python':
        edges, method, scope = python_imports(snap, spec['packages'])
    elif spec['language'] == 'typescript':
        edges, method, scope = typescript_imports(snap, spec)
    else:
        edges, method, scope = kotlin_imports(snap, files)
    metrics, sccs = graph_metrics(set(files) | {x for e in edges for x in e}, edges)
    (out / 'imports.json').write_text(json.dumps({'method': method, 'edges': sorted(edges), 'cycles': sccs}, indent=0))
    summary['imports'] = {'method': method, **metrics}
    if arch is not None:
        summary['agreement'] = agreement(arch, edges, scope)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != 'agreement'} | {'agreement': {k: v for k, v in summary.get('agreement', {}).items() if 'sample' not in k}}, indent=1))


if __name__ == '__main__':
    main()
