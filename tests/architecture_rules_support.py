"""Reference implementations are written from the spec text (F04, F05, F08, F09, F10) with algorithms unlike the
product's on purpose: a recursive segment/character matcher instead of a regex translation, brute-force pair
evaluation instead of indexed lookups."""
import ast
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from fnmatch import fnmatchcase
from pathlib import Path

from language_analyzers.core.graph_models import GraphEdge
from tests.structure_support import (EXACT, REPO, SC, SI, UNIQUE, AMBIGUOUS, architecture, default_weights, fedge,
                                     file_pair_view, fid, python_modules, ref_file_ids, ref_framework, ref_language,
                                     ref_pairs, sha16)

EVIDENCE = Path(__file__).parent / 'architecture_rules_evidence'
MANIFEST_PATH = EVIDENCE / 'base_manifest.json'
EXAMPLE_PROFILE = REPO / 'profiles' / 'architecture_rules.example.yaml'
RULES_POLICY = 'architecture_rules.v1'
MAIN = 'from code_analyzer.cli import main; main()'
FIXTURES = ('futuramaapi', 'fastapi-realworld', 'android-nowinandroid', 'typescript-nestjs-realworld')
RULE_KIND = 'rule_violation'

EXAMPLE_SPEC = {
    'version': 1,
    'layers': {
        'api': {'paths': ['app/api/**']},
        'services': {'paths': ['app/services/**']},
        'db': {'paths': ['app/db/**']},
        'domain': {'packages': ['pkg:python:app.models.domain']},
        'schemas': {'packages': ['pkg:python:app.models.schemas']},
        'core': {'paths': ['app/core/**', 'app/resources/**']},
    },
    'allow': {'domain': []},
    'forbid': [{'from': 'db', 'to': ['api']}, {'from': 'services', 'to': ['api']}],
}


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))


def ref_match(pattern, path):
    """F04 (spec v2): a final `**` consumes one or more segments, any other `**` zero or more, and consecutive
    `**` segments count as one."""
    collapsed = []
    for segment in pattern.split('/'):
        if not (segment == '**' and collapsed and collapsed[-1] == '**'):
            collapsed.append(segment)
    return _segments(collapsed, path.split('/'))


def _segments(patterns, parts):
    if not patterns:
        return not parts
    head, rest = patterns[0], patterns[1:]
    if head == '**':
        low = 0 if rest else 1
        return any(_segments(rest, parts[i:]) for i in range(low, len(parts) + 1))
    if not parts:
        return False
    return _chars(head, parts[0]) and _segments(rest, parts[1:])


def _chars(pattern, text):
    if not pattern:
        return not text
    if pattern[0] == '*':
        return any(_chars(pattern[1:], text[i:]) for i in range(len(text) + 1))
    if not text:
        return False
    return (pattern[0] == '?' or pattern[0] == text[0]) and _chars(pattern[1:], text[1:])


def path_of(file_id):
    return file_id[len('file:'):] if file_id.startswith('file:') else file_id


def to_rules(spec):
    from analysis.architecture_rules import ArchitectureRules, LayerSelector
    layers = {name: LayerSelector(paths=tuple(spec['layers'][name].get('paths', ())),
                                  packages=tuple(spec['layers'][name].get('packages', ())))
              for name in sorted(spec['layers'])}
    allow = {a: tuple(sorted(set(b))) for a, b in sorted(spec.get('allow', {}).items())}
    forbid = {}
    for item in spec.get('forbid', ()):
        forbid.setdefault(item['from'], set()).update(item['to'])
    return ArchitectureRules(version=spec.get('version', 1), layers=layers, allow=allow,
                             forbid={a: tuple(sorted(b)) for a, b in sorted(forbid.items())})


def package_schemes(arch):
    """The `packages` argument of layer_assignments: package_assignments format built from the Phase 1 reference."""
    schemes = {'language': ref_language(arch)}
    framework = ref_framework(arch)
    if framework is not None:
        schemes['framework'] = framework
    return schemes


def ref_layer_matches(spec, arch):
    schemes = package_schemes(arch)
    found = {}
    for file_id in sorted(ref_file_ids(arch)):
        every_package = [pkg for scheme in schemes.values() for pkg in scheme.get(file_id, ())]
        matched = []
        for name, selector in sorted(spec['layers'].items()):
            by_path = any(ref_match(pattern, path_of(file_id)) for pattern in selector.get('paths', ()))
            by_package = any(fnmatchcase(pkg, pattern) for pattern in selector.get('packages', ()) for pkg in every_package)
            if by_path or by_package:
                matched.append(name)
        found[file_id] = matched
    return found


def violation_identifier(rule_type, a, b, source, target):
    return f'rule|{rule_type}|{a}|{b}|{source}|{target}'


def ref_rule_evaluation(spec, arch, weights):
    """Returns (assignments, candidates, coverage) per F05, F08, F09, F10; multi-matched files must not occur."""
    matches = ref_layer_matches(spec, arch)
    assert all(len(layers) <= 1 for layers in matches.values()), 'oracle input has a multi-matched file'
    layer_of = {f: layers[0] for f, layers in matches.items() if layers}
    allow = {a: set(b) for a, b in spec.get('allow', {}).items()}
    forbid = {}
    for item in spec.get('forbid', ()):
        forbid.setdefault(item['from'], set()).update(item['to'])
    candidates = []
    for (source, target), record in sorted(ref_pairs(arch, weights, 'all').items()):
        if source == target or source not in layer_of or target not in layer_of:
            continue
        a, b = layer_of[source], layer_of[target]
        if a == b:
            continue
        kinds = []
        if a in allow and b not in allow[a]:
            kinds.append('allow')
        if b in forbid.get(a, ()):
            kinds.append('forbid')
        for rule_type in kinds:
            candidates.append({
                'id': 'b:' + sha16(violation_identifier(rule_type, a, b, source, target)),
                'kind': RULE_KIND, 'target': source,
                'metrics': {'evidence_count': record['evidence_count'], 'max_weight': record['max_weight']},
                'evidence': [file_pair_view({'from_id': source, 'to_id': target, **record})],
                'coverage': 'static_analyzer_relation', 'status': 'static_candidate',
                'structure': {'rule_type': rule_type, 'from_layer': a, 'to_layer': b, 'tier': record['tier'],
                              'relations': record['relations']},
            })
    candidates.sort(key=lambda item: item['id'])
    files = sorted(ref_file_ids(arch))
    counts = {name: sum(1 for f in files if layer_of.get(f) == name) for name in sorted(spec['layers'])}
    coverage = {
        'policy': RULES_POLICY, 'version': spec.get('version', 1), 'layer_file_counts': counts,
        'unassigned_file_count': sum(1 for f in files if f not in layer_of),
        'unassigned_files': [f for f in files if f not in layer_of],
        'empty_layers': [name for name, count in counts.items() if count == 0],
        'violation_count': len(candidates),
    }
    return layer_of, candidates, coverage


def violations_of(candidates):
    return sorted((c for c in candidates if c['kind'] == RULE_KIND), key=lambda item: item['id'])


def assert_candidates_equal(actual, expected):
    assert [c['id'] for c in actual] == [c['id'] for c in expected]
    for got, want in zip(actual, expected):
        assert set(got) == set(want)
        for key in ('kind', 'target', 'coverage', 'status', 'structure'):
            assert got[key] == want[key], (want['id'], key)
        assert set(got['metrics']) == {'evidence_count', 'max_weight'}
        assert got['metrics']['evidence_count'] == want['metrics']['evidence_count']
        assert abs(got['metrics']['max_weight'] - want['metrics']['max_weight']) < 1e-9
        assert len(got['evidence']) == 1
        for key in ('from_id', 'to_id', 'relations', 'evidence_count', 'detail_edge_indices', 'tier'):
            assert got['evidence'][0][key] == want['evidence'][0][key], (want['id'], key)
        assert abs(got['evidence'][0]['max_weight'] - want['evidence'][0]['max_weight']) < 1e-9
        assert set(got['evidence'][0]) == set(want['evidence'][0])


def raw_edge(source, target, relation='IMPORTS', confidence=SC, resolution=EXACT, share=None, indices=(), evidence=1):
    """Like structure_support.fedge but ids are used verbatim, so a boundary id without 'file:' can be an endpoint."""
    metadata = {'detail_edge_indices': list(indices), 'evidence_count': evidence}
    if share is not None:
        metadata['candidate_share'] = share
    return GraphEdge(source, target, relation, confidence=confidence, resolution=resolution, metadata=metadata)


def edge_counter():
    state = {'n': 0}

    def make(source, target, **kwargs):
        index = state['n']
        state['n'] += 1
        kwargs.setdefault('indices', [index])
        return fedge(source, target, **kwargs)
    return make


def write_rules(directory, spec_or_text, name='rules.yaml'):
    target = Path(directory) / name
    if isinstance(spec_or_text, bytes):
        target.write_bytes(spec_or_text)
    else:
        text = spec_or_text if isinstance(spec_or_text, str) else json.dumps(spec_or_text)
        target.write_text(text, encoding='utf-8')
    return target


def weights():
    return default_weights()


def random_graph(seed):
    """Layered random graph with TESTS edges, mixed tiers, parallel edges, boundary endpoints and unassigned files."""
    rnd = random.Random(seed)
    dirs = ['src/a', 'src/b', 'src/c', 'src/d', 'other']
    paths = [f'{rnd.choice(dirs)}/f{i}.py' for i in range(14)]
    paths = sorted(set(paths))
    boundary = ['src/b/ext.py', 'lib/x.py']
    tiers = [(SC, EXACT), (SI, EXACT), (SI, UNIQUE), (SI, AMBIGUOUS), (SC, AMBIGUOUS)]
    make = edge_counter()
    edges = []
    for _ in range(40):
        source = fid(rnd.choice(paths))
        target = rnd.choice(boundary) if rnd.random() < .1 else fid(rnd.choice(paths))
        confidence, resolution = rnd.choice(tiers)
        edges.append(raw_edge(source, target, rnd.choice(['IMPORTS', 'IMPORTS', 'CALLS', 'TESTS']), confidence, resolution,
                              share=rnd.choice([None, None, .5]), indices=[len(edges)], evidence=rnd.randint(1, 4)))
    spec = {'version': 1,
            'layers': {'la': {'paths': ['src/a/**']}, 'lb': {'paths': ['src/b/*.py']}, 'lc': {'paths': ['src/c/**']},
                       'ld': {'paths': ['src/d/**', 'nothing/**']}, 'le': {'paths': ['empty/**']}},
            'allow': {'la': rnd.sample(['lb', 'lc'], rnd.randint(0, 2)), 'lb': ['la']},
            'forbid': [{'from': 'lc', 'to': ['la', 'lb']}, {'from': 'lc', 'to': ['ld']}, {'from': 'lb', 'to': ['lc']},
                       {'from': 'la', 'to': ['lb']}]}
    return architecture(paths, edges, boundary=boundary), spec


def synthetic_input(files=20000, pairs=100000, seed=20261018):
    """Ten layers, each with five path patterns and five package patterns; every file matches exactly one layer."""
    mapping = {}
    for i in range(files):
        layer, slot = i % 10, (i // 10) % 5
        if (i // 50) % 2 == 0:
            mapping[f'mod{layer}/p{slot}/f{i}.py'] = f'mod{layer}.p{slot}.f{i}'
        else:
            mapping[f'mod{layer}/q{slot}/f{i}.py'] = f'mod{layer}.q{slot}.f{i}'
    paths = list(mapping)
    rnd = random.Random(seed)
    chosen = set()
    while len(chosen) < pairs:
        a, b = rnd.randrange(files), rnd.randrange(files)
        if a < b:
            chosen.add((a, b))
    edges = [fedge(paths[a], paths[b], indices=[n]) for n, (a, b) in enumerate(sorted(chosen))]
    dnodes, node_files = python_modules(mapping)
    spec = {'version': 1, 'layers': {
        f'layer{k}': {'paths': [f'mod{k}/p{j}/**' for j in range(5)], 'packages': [f'pkg:python:mod{k}.q{j}' for j in range(5)]}
        for k in range(10)},
        'allow': {'layer0': ['layer1', 'layer2'], 'layer3': []},
        'forbid': [{'from': 'layer1', 'to': ['layer4', 'layer5']}, {'from': 'layer6', 'to': ['layer7']}]}
    return architecture(paths, edges, dnodes=dnodes, node_files=node_files), spec


def imported_modules(source, package='analysis'):
    modules = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:
                parts = package.split('.')[:len(package.split('.')) - node.level + 1]
                base = '.'.join(parts + ([base] if base else []))
            modules.append(base)
            modules += [f'{base}.{alias.name}' for alias in node.names]
        elif isinstance(node, ast.Call):
            name = getattr(node.func, 'attr', getattr(node.func, 'id', ''))
            if name in {'import_module', '__import__'} and node.args and isinstance(node.args[0], ast.Constant):
                modules.append(str(node.args[0].value))
    return modules


def framework_imports(modules):
    return [m for m in modules if m.split('.')[0] == 'framework_analyzers']


def language_imports(modules):
    return [m for m in modules if m.split('.')[0] == 'language_analyzers' and len(m.split('.')) > 1
            and m.split('.')[1] in ('python', 'kotlin', 'typescript')]


def cli(args, cwd=REPO, seed='0'):
    return subprocess.run([sys.executable, '-c', MAIN, *map(str, args)], cwd=cwd, env=dict(os.environ, PYTHONHASHSEED=seed),
                          capture_output=True, text=True)


def init_git(root):
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)


def mini_project(root, files):
    for path, text in files.items():
        target = Path(root) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    init_git(root)
    return Path(root)


def copy_fixture(name, destination):
    from fixtures.registry import fixture_root
    shutil.copytree(fixture_root(name), destination, symlinks=True)
    return Path(destination)

