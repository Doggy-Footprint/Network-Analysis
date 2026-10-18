"""Reference implementations are written from the spec text (F02-F06, F09-F12) with algorithms unlike the product's
on purpose: root-aligned suffix enumeration for Python, regex for TypeScript names, brute force over
(file, name, entry) for external rule evaluation."""
import ast
import copy
import hashlib
import json
import re
from fnmatch import fnmatchcase
from pathlib import Path

from tests.architecture_rules_support import ref_layer_matches, ref_rule_evaluation, sha16
from tests.structure_support import architecture

EVIDENCE = Path(__file__).parent / 'external_rules_evidence'
MANIFEST_PATH = EVIDENCE / 'base_manifest.json'
FIXTURES = ('futuramaapi', 'fastapi-realworld', 'fastapi-official-template', 'android-nowinandroid', 'typescript-nestjs-realworld')
SYMBOL_FIXTURES = ('fastapi-realworld', 'typescript-nestjs-realworld')
RULE_KIND = 'rule_violation'
FORBID_EXT, ALLOW_EXT = 'forbid_external', 'allow_external'
INTERNAL_COVERAGE_KEYS = {'policy', 'version', 'layer_file_counts', 'unassigned_file_count', 'unassigned_files', 'empty_layers',
                          'violation_count'}
EXTERNAL_COVERAGE_KEYS = {'external_import_count', 'external_violation_count'}

EXAMPLE_EXT_SPEC = {
    'version': 1,
    'layers': {
        'api': {'paths': ['app/api/**']},
        'services': {'paths': ['app/services/**']},
        'db': {'paths': ['app/db/**']},
        'domain': {'packages': ['pkg:python:app.models.domain']},
        'schemas': {'packages': ['pkg:python:app.models.schemas']},
        'core': {'paths': ['app/core/**', 'app/resources/**']},
    },
    'external': {'web': ['fastapi*', 'starlette*'], 'db_driver': ['asyncpg*', 'sqlalchemy*', 'alembic*', 'pypika*', 'aiosql*']},
    'allow': {'domain': []},
    'forbid': [{'from': 'db', 'to': ['api'], 'to_external': ['group:web']}, {'from': 'services', 'to': ['api']},
               {'from': 'api', 'to_external': ['group:db_driver']}],
    'allow_external': {'domain': ['pydantic*', 'typing', 'datetime']},
}


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))


def canonical_text(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def strip_external_imports(value):
    if isinstance(value, dict):
        metadata = value.get('metadata')
        if isinstance(metadata, dict):
            metadata.pop('external_imports', None)
        for child in value.values():
            strip_external_imports(child)
    elif isinstance(value, list):
        for child in value:
            strip_external_imports(child)
    return value


def canonical_architecture_sha(payload):
    payload = strip_external_imports(copy.deepcopy(payload))
    payload.pop('project_path', None)
    return hashlib.sha256(canonical_text(payload).encode('utf-8')).hexdigest()


def keys_found(value, key, path=()):
    found = []
    if isinstance(value, dict):
        for name, child in value.items():
            if name == key:
                found.append(path + (name,))
            found += keys_found(child, key, path + (name,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found += keys_found(child, key, path + (index,))
    return found


def file_nodes(payload):
    return [n for n in payload['nodes'] if not (n.get('metadata') or {}).get('boundary')]


def records_by_file(payload):
    return {n['id'][len('file:'):]: n['metadata']['external_imports'] for n in file_nodes(payload)
            if n['id'].startswith('file:') and 'external_imports' in (n.get('metadata') or {})}


def names_by_file(payload):
    return {path: {r['name'] for r in records} for path, records in records_by_file(payload).items()}


def sort_key(record):
    return (record['name'], record['line'], record.get('specifier', ''), bool(record.get('dynamic', False)))


def ref_normalize(records):
    distinct = {json.dumps(dict(r), sort_keys=True) for r in records}
    return sorted((json.loads(item) for item in distinct), key=sort_key)


def ref_python_internal(modules, packages, name):
    packages = set(packages)
    target = name.split('.')
    for module in modules:
        segments = module.split('.')
        for start in range(len(segments)):
            if start and '.'.join(segments[:start]) in packages:
                continue
            if segments[start:start + len(target)] == target:
                return True
    return False


def ref_kotlin_internal(name, packages):
    return any(name == p or name.startswith(p + '.') or p.startswith(name + '.') for p in packages)


def ref_ts_package_name(specifier):
    pattern = r'[^/]*(?:/[^/]*)?' if specifier.startswith('@') else r'[^/]*'
    return re.match(pattern, specifier).group(0)


def ref_ts_alias(specifier, path_keys, base_url, source_files):
    for key in path_keys:
        if key == '*':
            continue
        if key.endswith('*') and specifier.startswith(key[:-1]):
            return True
        if not key.endswith('*') and specifier == key:
            return True
    if base_url is not None:
        head = specifier.split('/')[0]
        prefix = base_url + '/' if base_url else ''
        for path in source_files:
            if not path.startswith(prefix):
                continue
            relative = path[len(prefix):]
            first = relative.split('/')[0]
            if '/' not in relative:
                first = first.rsplit('.', 1)[0] if '.' in first else first
            if first == head:
                return True
    return False


def ref_entry_matches(groups, entry, name):
    if entry.startswith('group:'):
        return any(fnmatchcase(name, pattern) for pattern in groups[entry[len('group:'):]])
    return fnmatchcase(name, entry)


def to_rules_ext(spec):
    from analysis.architecture_rules import ArchitectureRules, LayerSelector
    layers = {name: LayerSelector(paths=tuple(spec['layers'][name].get('paths', ())),
                                  packages=tuple(spec['layers'][name].get('packages', ())))
              for name in sorted(spec['layers'])}
    forbid, forbid_external = {}, {}
    for item in spec.get('forbid', ()):
        if 'to' in item:
            forbid.setdefault(item['from'], set()).update(item['to'])
        if 'to_external' in item:
            forbid_external.setdefault(item['from'], set()).update(item['to_external'])
    return ArchitectureRules(
        version=spec.get('version', 1), layers=layers,
        allow={a: tuple(sorted(set(b))) for a, b in sorted(spec.get('allow', {}).items())},
        forbid={a: tuple(sorted(b)) for a, b in sorted(forbid.items())},
        external={g: tuple(sorted(set(p))) for g, p in sorted(spec.get('external', {}).items())},
        forbid_external={a: tuple(sorted(b)) for a, b in sorted(forbid_external.items())},
        allow_external={a: tuple(sorted(set(b))) for a, b in sorted(spec.get('allow_external', {}).items())})


def internal_spec(spec):
    return {'version': spec.get('version', 1), 'layers': spec['layers'], 'allow': spec.get('allow', {}),
            'forbid': [{'from': i['from'], 'to': i['to']} for i in spec.get('forbid', ()) if 'to' in i]}


def ext_arch(files, boundary=None, edges=()):
    arch = architecture(list(files), list(edges), boundary=list(boundary or ()))
    for node in arch.nodes:
        path = node.id[len('file:'):] if node.id.startswith('file:') else node.id
        source = (boundary or {}).get(path) if (node.metadata or {}).get('boundary') else files.get(path)
        if source is not None:
            node.metadata['external_imports'] = copy.deepcopy(source)
    return arch


def ref_external_evaluation(spec, arch):
    layer_of = {f: layers[0] for f, layers in ref_layer_matches(spec, arch).items() if layers}
    groups = spec.get('external', {})
    forbid = {}
    for item in spec.get('forbid', ()):
        forbid.setdefault(item['from'], set()).update(item.get('to_external', ()))
    allow = {a: set(b) for a, b in spec.get('allow_external', {}).items()}
    candidates, total = [], 0
    for node in sorted(arch.nodes, key=lambda n: n.id):
        if (node.metadata or {}).get('boundary'):
            continue
        records = (node.metadata or {}).get('external_imports', [])
        total += len(records)
        layer = layer_of.get(node.id)
        if layer is None:
            continue
        for name in sorted({r['name'] for r in records}):
            mine = [r for r in records if r['name'] == name]
            hits = sorted(e for e in forbid.get(layer, ()) if ref_entry_matches(groups, e, name))
            kinds = []
            if hits:
                kinds.append((FORBID_EXT, hits))
            if layer in allow and not any(ref_entry_matches(groups, e, name) for e in allow[layer]):
                kinds.append((ALLOW_EXT, []))
            for rule_type, matched in kinds:
                candidates.append({
                    'id': 'b:' + sha16(f'rule|{rule_type}|{layer}|{node.id}|{name}'), 'kind': RULE_KIND, 'target': node.id,
                    'metrics': {'evidence_count': len(mine)}, 'evidence': mine, 'coverage': 'static_analyzer_relation',
                    'status': 'static_candidate',
                    'structure': {'rule_type': rule_type, 'from_layer': layer, 'to_external': name, 'matched': matched,
                                  'tier': 'certain' if any(not r.get('dynamic') for r in mine) else 'resolved',
                                  'relations': ['IMPORTS']}})
    candidates.sort(key=lambda item: item['id'])
    return candidates, total


def ref_coverage(spec, arch, weights):
    _, internal, base = ref_rule_evaluation(internal_spec(spec), arch, weights)
    external, total = ref_external_evaluation(spec, arch)
    coverage = dict(base)
    has_external = bool(spec.get('allow_external')) or any('to_external' in i for i in spec.get('forbid', ()))
    if has_external:
        coverage['external_import_count'] = total
        coverage['external_violation_count'] = len(external)
        coverage['violation_count'] = len(internal) + len(external)
    return coverage


def external_violations(candidates):
    return sorted((c for c in candidates if c['kind'] == RULE_KIND and c['structure'].get('rule_type') in (FORBID_EXT, ALLOW_EXT)),
                  key=lambda c: c['id'])


def assert_external_equal(actual, expected):
    assert [c['id'] for c in actual] == [c['id'] for c in expected]
    for got, want in zip(actual, expected):
        assert set(got) == set(want), want['id']
        for key in ('kind', 'target', 'coverage', 'status', 'structure', 'metrics', 'evidence'):
            assert got[key] == want[key], (want['id'], key)
        assert set(got['structure']) == {'rule_type', 'from_layer', 'to_external', 'matched', 'tier', 'relations'}


def brief(candidates):
    return sorted((c['structure']['rule_type'], c['structure']['from_layer'], c['target'], c['structure']['to_external'])
                  for c in candidates)


def rec(name, line=1, specifier=None, dynamic=False):
    record = {'name': name, 'line': line}
    if specifier is not None:
        record['specifier'] = specifier
    if dynamic:
        record['dynamic'] = True
    return record


def own_result(coverage, path, ident):
    rows = [row for row in coverage['files'] if row['file_path'] == path]
    assert rows, path
    return [r for r in rows[0]['results'] if r['analyzer_id'] == ident]


def _statements(body):
    for stmt in body:
        yield stmt
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield from _statements(stmt.body)
        elif isinstance(stmt, ast.If):
            yield from _statements(stmt.body)
            yield from _statements(stmt.orelse)
        elif isinstance(stmt, ast.Try):
            for part in (stmt.body, stmt.orelse, stmt.finalbody, *(h.body for h in stmt.handlers)):
                yield from _statements(part)


def ref_python_names(source):
    names = []
    for stmt in _statements(ast.parse(source).body):
        if isinstance(stmt, ast.Import):
            names += [(a.name, stmt.lineno) for a in stmt.names]
        elif isinstance(stmt, ast.ImportFrom) and stmt.level == 0 and stmt.module and stmt.module != '__future__':
            names.append((stmt.module, stmt.lineno))
    return names


def python_repo_index(root):
    modules, packages = set(), set()
    for path in Path(root).rglob('*.py'):
        relative = path.relative_to(root).parts
        if any(part.startswith('.') or part == 'node_modules' for part in relative):
            continue
        parts = list(relative[:-1])
        if relative[-1] == '__init__.py':
            if parts:
                packages.add('.'.join(parts))
        else:
            modules.add('.'.join(parts + [relative[-1][:-3]]))
    return modules, packages


def ref_python_external_names(root, prefix):
    root = Path(root)
    modules, packages = python_repo_index(root)
    found = {}
    for path in sorted((root / prefix).rglob('*.py')):
        relative = path.relative_to(root).as_posix()
        try:
            names = ref_python_names(path.read_text(encoding='utf-8'))
        except SyntaxError:
            names = []
        found[relative] = {n for n, _ in names if not ref_python_internal(modules, packages, n)}
    return found


KOTLIN_IMPORT = re.compile(r'^\s*import\s+([\w.*]+)', re.M)
KOTLIN_PACKAGE = re.compile(r'^\s*package\s+([\w.]+)', re.M)


def ref_kotlin_external_names(root, paths):
    sources = {p: (Path(root) / p).read_text(encoding='utf-8') for p in paths}
    packages = {m.group(1) for text in sources.values() for m in KOTLIN_PACKAGE.finditer(text)}
    found = {}
    for path, text in sources.items():
        names = set()
        for match in KOTLIN_IMPORT.finditer(text):
            name = match.group(1)
            name = name[:-2] if name.endswith('.*') else name
            if not ref_kotlin_internal(name, packages):
                names.add(name)
        found[path] = names
    return found


_BLOCK = re.compile(r'/\*.*?\*/', re.S)
_LINE = re.compile(r'^\s*//.*$', re.M)
_FROM = re.compile(r'''\bfrom\s*['"]([^'"\n]+)['"]''')
_SIDE = re.compile(r'''\bimport\s*['"]([^'"\n]+)['"]''')
_CALL = re.compile(r'''\b(?:require|import)\s*\(\s*['"]([^'"\n]+)['"]\s*\)''')
_LITERAL = re.compile(r'''['"]([^'"\n]+)['"]''')


def ref_ts_scan(source):
    text = _LINE.sub('', _BLOCK.sub('', source))
    specifiers = {m.group(1) for pattern in (_FROM, _SIDE, _CALL) for m in pattern.finditer(text)}
    literals = {m.group(1) for m in _LITERAL.finditer(text)}
    external = lambda items: {ref_ts_package_name(s) for s in items if not s.startswith(('.', '/'))}
    return external(specifiers), external(literals)
