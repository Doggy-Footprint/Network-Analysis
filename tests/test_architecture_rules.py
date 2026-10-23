import json
import random

import pytest

from analysis.structure import analyze_structure
from tests.delta_support import without_digest
from tests.architecture_rules_support import (EXAMPLE_PROFILE, EXAMPLE_SPEC, REPO, RULE_KIND, RULES_POLICY, assert_candidates_equal,
                                              edge_counter, framework_imports, imported_modules, language_imports, package_schemes,
                                              path_of, random_graph, raw_edge, ref_match, ref_rule_evaluation, to_rules,
                                              violations_of, weights, write_rules)
from tests.structure_support import AMBIGUOUS, EXACT, SC, SI, UNIQUE, architecture, dedge, dnode, fedge, fid, python_modules

LAYERS_AB = {'alpha': {'paths': ['src/a/**']}, 'beta': {'paths': ['src/b/**']}}
BASE = 'version: 1\nlayers:\n  alpha:\n    paths: [src/a/**]\n  beta:\n    paths: [src/b/**]\n'


def load(path):
    from analysis.architecture_rules import load_architecture_rules
    return load_architecture_rules(path)


def error_type():
    from analysis.architecture_rules import ArchitectureRulesError
    return ArchitectureRulesError


def rejected(directory, content, name='my_rules.txt'):
    path = write_rules(directory, content, name)
    with pytest.raises(error_type()) as raised:
        load(path)
    return str(raised.value)


def mentions(message, needles):
    lowered = message.lower()
    return any(needle.lower() in lowered for needle in needles)


def test_V01_error_type_is_a_value_error():
    assert issubclass(error_type(), ValueError)


def test_V01_C12_file_not_found(tmp_path):
    with pytest.raises(error_type()) as raised:
        load(tmp_path / 'missing_rules.txt')
    assert 'missing_rules.txt' in str(raised.value)


def test_V01_C12_non_utf8(tmp_path):
    path = write_rules(tmp_path, b'version: 1\nlayers: \xff\xfe\x80\n', 'my_rules.txt')
    with pytest.raises(error_type()) as raised:
        load(path)
    assert str(path) in str(raised.value)


def test_V01_C12_yaml_syntax_error(tmp_path):
    path = write_rules(tmp_path, 'version: [1\nlayers: {a: ', 'my_rules.txt')
    with pytest.raises(error_type()) as raised:
        load(path)
    assert str(path) in str(raised.value)


def test_V01_C12_top_level_list(tmp_path):
    assert 'mapping' in rejected(tmp_path, '- version\n- layers\n')


def test_V01_C12_top_level_scalar_is_not_a_mapping(tmp_path):
    assert 'mapping' in rejected(tmp_path, 'just text\n')


def test_V01_C12_empty_document(tmp_path):
    assert 'mapping' in rejected(tmp_path, '')


ROWS = {
    'unknown-top-key': (BASE + 'bogus_key: 1\n', ['bogus_key']),
    'version-missing': ('layers:\n  alpha:\n    paths: [src/a/**]\n', ['version']),
    'version-0': ('version: 0\n' + BASE[len('version: 1\n'):], ['version']),
    'version-2': ('version: 2\n' + BASE[len('version: 1\n'):], ['version']),
    'version-string-1': ('version: "1"\n' + BASE[len('version: 1\n'):], ['version']),
    'version-true': ('version: true\n' + BASE[len('version: 1\n'):], ['version']),
    'layers-missing': ('version: 1\n', ['layers']),
    'layers-empty-mapping': ('version: 1\nlayers: {}\n', ['layers']),
    'layers-list': ('version: 1\nlayers: [alpha]\n', ['layers']),
    'layer-name-1a': ('version: 1\nlayers:\n  1a:\n    paths: [x]\n', ['1a']),
    'layer-name-with-space': ('version: 1\nlayers:\n  "a b":\n    paths: [x]\n', ['a b']),
    'layer-name-number': ('version: 1\nlayers:\n  123:\n    paths: [x]\n', ['123']),
    'selector-empty-mapping': ('version: 1\nlayers:\n  alpha: {}\n', ['alpha', 'paths', 'packages']),
    'selector-unknown-key': ('version: 1\nlayers:\n  alpha:\n    globs: [x]\n', ['globs']),
    'selector-empty-list': ('version: 1\nlayers:\n  alpha:\n    paths: []\n', ['paths']),
    'selector-non-list': ('version: 1\nlayers:\n  alpha:\n    paths: src/a\n', ['paths']),
    'selector-non-string': ('version: 1\nlayers:\n  alpha:\n    paths: [4242]\n', ['paths', '4242']),
    'selector-empty-string': ('version: 1\nlayers:\n  alpha:\n    packages: [""]\n', ['packages']),
    'path-absolute': ('version: 1\nlayers:\n  alpha:\n    paths: ["/abs/dir/**"]\n', ['/abs/dir/**']),
    'path-a-double-star': ('version: 1\nlayers:\n  alpha:\n    paths: ["src/a**"]\n', ['src/a**']),
    'path-double-star-b': ('version: 1\nlayers:\n  alpha:\n    paths: ["**b/x"]\n', ['**b/x']),
    'allow-non-mapping': (BASE + 'allow: [alpha]\n', ['allow']),
    'allow-undefined-layer-value': (BASE + 'allow:\n  alpha: [zzz_undefined]\n', ['zzz_undefined']),
    'allow-undefined-layer-key': (BASE + 'allow:\n  zzz_undefined: [alpha]\n', ['zzz_undefined']),
    'allow-self-reference': (BASE + 'allow:\n  alpha: [beta, alpha]\n', ['alpha']),
    'allow-non-list': (BASE + 'allow:\n  alpha: beta\n', ['allow', 'beta']),
    'forbid-non-list': (BASE + 'forbid:\n  from: alpha\n  to: [beta]\n', ['forbid']),
    'forbid-item-key-missing-to': (BASE + 'forbid:\n  - from: alpha\n', ['to']),
    'forbid-item-key-missing-from': (BASE + 'forbid:\n  - to: [beta]\n', ['from']),
    'forbid-item-extra-key': (BASE + 'forbid:\n  - from: alpha\n    to: [beta]\n    reason_extra: x\n', ['reason_extra']),
    'forbid-to-empty-list': (BASE + 'forbid:\n  - from: alpha\n    to: []\n', ['to']),
    'forbid-to-undefined': (BASE + 'forbid:\n  - from: alpha\n    to: [zzz_undefined]\n', ['zzz_undefined']),
    'forbid-to-self': (BASE + 'forbid:\n  - from: alpha\n    to: [alpha]\n', ['alpha']),
    'forbid-from-undefined': (BASE + 'forbid:\n  - from: zzz_undefined\n    to: [alpha]\n', ['zzz_undefined']),
}


@pytest.mark.parametrize('row', sorted(ROWS))
def test_V01_C12_table_row(tmp_path, row):
    text, needles = ROWS[row]
    message = rejected(tmp_path, text)
    assert message.strip()
    assert mentions(message, needles), (row, message)


@pytest.mark.parametrize('value', ['{}', '{db: [api]}', '5', 'true', 'null', '"abc"'],
                         ids=['empty-mapping', 'non-empty-mapping', 'int', 'bool', 'null', 'string'])
def test_V01_C12_forbid_not_a_list(tmp_path, value):
    message = rejected(tmp_path, BASE + f'forbid: {value}\n')
    assert 'forbid' in message


def test_V01_C12_valid_base_document_loads(tmp_path):
    assert load(write_rules(tmp_path, BASE)).version == 1


def test_V01_C13_external_group_definition_loads(tmp_path):
    rules = load(write_rules(tmp_path, BASE + 'external:\n  libs: [requests]\n'))
    assert dict(rules.external) == {'libs': ('requests',)}


@pytest.mark.parametrize('text', ['external: []\n', 'external: {}\n'], ids=['external-top-list', 'external-top-empty-mapping'])
def test_V01_C13_external_top_level_must_be_a_non_empty_mapping(tmp_path, text):
    message = rejected(tmp_path, BASE + text)
    assert 'external' in message and 'not supported' not in message


def test_V01_C13_to_external(tmp_path):
    rules = load(write_rules(tmp_path, BASE + 'forbid:\n  - from: alpha\n    to_external: [requests]\n'))
    assert dict(rules.forbid_external) == {'alpha': ('requests',)}


def test_V01_C13_to_external_next_to_to(tmp_path):
    rules = load(write_rules(tmp_path, BASE + 'forbid:\n  - from: alpha\n    to: [beta]\n    to_external: [requests]\n'))
    assert dict(rules.forbid)['alpha'] == ('beta',) and dict(rules.forbid_external) == {'alpha': ('requests',)}


@pytest.mark.parametrize('where', ['layers-value', 'nested-path', 'top-level-value'])
def test_V01_Q08_python_object_tag_is_rejected_without_side_effect(tmp_path, where):
    sentinel = tmp_path / 'sentinel.txt'
    payload = f'!!python/object/apply:os.system ["touch {sentinel}"]'
    text = {
        'layers-value': f'version: 1\nlayers: {payload}\n',
        'nested-path': f'version: 1\nlayers:\n  alpha:\n    paths: [{payload}]\n',
        'top-level-value': f'version: 1\nlayers:\n  alpha:\n    paths: [src/a/**]\nallow: {payload}\n',
    }[where]
    rejected(tmp_path, text)
    assert not sentinel.exists()


def test_V02_minimal_paths(tmp_path):
    rules = load(write_rules(tmp_path, 'version: 1\nlayers:\n  alpha:\n    paths: [src/a/**]\n'))
    assert rules.version == 1 and list(rules.layers) == ['alpha']
    assert tuple(rules.layers['alpha'].paths) == ('src/a/**',) and tuple(rules.layers['alpha'].packages) == ()
    assert dict(rules.allow) == {} and dict(rules.forbid) == {}


def test_V02_minimal_packages(tmp_path):
    rules = load(str(write_rules(tmp_path, 'version: 1\nlayers:\n  alpha:\n    packages: [pkg:python:app.x]\n')))
    assert tuple(rules.layers['alpha'].paths) == () and tuple(rules.layers['alpha'].packages) == ('pkg:python:app.x',)


def test_V02_both_selectors_and_layer_order_and_package_order(tmp_path):
    text = ('version: 1\nlayers:\n  zeta:\n    packages: [pkg:dir:z]\n  alpha:\n    paths: [a/**, b/*.py]\n'
            '    packages: [pkg:python:z.z, pkg:python:a.a, "pkg:nestjs:Feed*"]\n')
    rules = load(write_rules(tmp_path, text))
    assert list(rules.layers) == ['alpha', 'zeta']
    assert sorted(rules.layers['alpha'].paths) == ['a/**', 'b/*.py']
    assert tuple(rules.layers['alpha'].packages) == ('pkg:python:z.z', 'pkg:python:a.a', 'pkg:nestjs:Feed*')
    assert tuple(rules.layers['zeta'].paths) == () and tuple(rules.layers['zeta'].packages) == ('pkg:dir:z',)


def test_V02_layer_name_hyphen_underscore_upper(tmp_path):
    rules = load(write_rules(tmp_path, 'version: 1\nlayers:\n  Core-Layer_2:\n    paths: [src/**]\n  x_Y-z9:\n    paths: [lib/**]\n'))
    assert list(rules.layers) == sorted(['Core-Layer_2', 'x_Y-z9'])
    assert tuple(rules.layers['Core-Layer_2'].paths) == ('src/**',)


def test_V02_allow_empty_list(tmp_path):
    rules = load(write_rules(tmp_path, BASE + 'allow:\n  alpha: []\n'))
    assert dict(rules.allow) == {'alpha': ()}


def test_V02_allow_dup_sorted_and_deduplicated(tmp_path):
    text = ('version: 1\nlayers:\n  a1: {paths: [x]}\n  b1: {paths: [y]}\n  c1: {paths: [z]}\n'
            'allow:\n  a1: [c1, b1, c1, b1]\n')
    assert dict(load(write_rules(tmp_path, text)).allow) == {'a1': ('b1', 'c1')}


def test_V02_forbid_dup_sorted_and_deduplicated(tmp_path):
    text = ('version: 1\nlayers:\n  a1: {paths: [x]}\n  b1: {paths: [y]}\n  c1: {paths: [z]}\n'
            'forbid:\n  - from: a1\n    to: [c1, b1, c1]\n')
    assert dict(load(write_rules(tmp_path, text)).forbid) == {'a1': ('b1', 'c1')}


def test_V02_forbid_merge_same_from_is_union(tmp_path):
    text = ('version: 1\nlayers:\n  a1: {paths: [x]}\n  b1: {paths: [y]}\n  c1: {paths: [z]}\n  d1: {paths: [w]}\n'
            'forbid:\n  - from: a1\n    to: [d1, b1]\n  - from: c1\n    to: [a1]\n  - from: a1\n    to: [b1, c1]\n')
    assert dict(load(write_rules(tmp_path, text)).forbid) == {'a1': ('b1', 'c1', 'd1'), 'c1': ('a1',)}


def test_V02_example_profile_loads_to_the_f07_content():
    rules = load(EXAMPLE_PROFILE)
    assert rules.version == 1
    assert list(rules.layers) == sorted(EXAMPLE_SPEC['layers'])
    for name, selector in EXAMPLE_SPEC['layers'].items():
        assert sorted(rules.layers[name].paths) == sorted(selector.get('paths', ()))
        assert list(rules.layers[name].packages) == selector.get('packages', [])
    assert dict(rules.allow) == {'domain': ()}
    assert dict(rules.forbid) == {'db': ('api',), 'services': ('api',)}


C09 = [
    ('app/**', 'app/a.py', True), ('app/**', 'app/x/y.py', True), ('app/**', 'app', False), ('app/**', 'apps/a.py', False),
    ('app/*.py', 'app/a.py', True), ('app/*.py', 'app/x/a.py', False), ('app/*.py', 'app/.py', True),
    ('**/m.py', 'm.py', True), ('**/m.py', 'a/b/m.py', True), ('**/m.py', 'am.py', False),
    ('a/**/b', 'a/b', True), ('a/**/b', 'a/x/y/b', True),
    ('a?c', 'abc', True), ('a?c', 'a/c', False), ('a?c', 'ac', False),
    ('a.b[1]', 'a.b[1]', True), ('a.b[1]', 'axb1', False),
    ('App/x', 'app/x', False),
]


@pytest.mark.parametrize('pattern,path,expected', C09, ids=[f'C09-{i:02}' for i in range(len(C09))])
def test_V03_C09_table(pattern, path, expected):
    from analysis.architecture_rules import match_path
    assert match_path(pattern, path) is expected


@pytest.mark.parametrize('pattern,path,expected', C09, ids=[f'C09-{i:02}' for i in range(len(C09))])
def test_V03_reference_matcher_reproduces_the_table(pattern, path, expected):
    assert ref_match(pattern, path) is expected


def test_V03_product_agrees_with_reference_on_small_exhaustive_space():
    from analysis.architecture_rules import match_path
    segments = ['a', 'b', 'ab', '*', '**', '?', 'a*', '*b', 'a?', '.x']
    names = ['a', 'b', 'ab', 'aab', '.x', 'abb']
    patterns = [[]]
    for _ in range(3):
        patterns += [p + [s] for p in patterns if len(p) < 3 for s in segments]
    patterns = sorted({'/'.join(p) for p in patterns if p})
    paths = sorted({'/'.join(p) for n in range(1, 4) for p in _product(names, n)})
    mismatches = [(p, x) for p in patterns for x in paths if match_path(p, x) != ref_match(p, x)]
    assert mismatches == []


@pytest.mark.parametrize('pattern,path,expected', [
    ('**', 'a', True), ('**', 'a/b/c', True), ('a/**/**', 'a', False), ('a/**/**', 'a/b', True), ('a/**/**/b', 'a/b', True),
    ('**/**', 'x', True), ('**/a/**', 'a', False), ('**/a/**', 'q/a/z', True),
], ids=['v2-lone-star', 'v2-lone-deep', 'v2-consecutive-final-0', 'v2-consecutive-final-1', 'v2-consecutive-mid',
        'v2-consecutive-only', 'v2-lead-and-final-0', 'v2-lead-and-final-1'])
def test_V03_v2_double_star_rules(pattern, path, expected):
    from analysis.architecture_rules import match_path
    assert match_path(pattern, path) is expected and ref_match(pattern, path) is expected


def _product(items, n):
    if n == 0:
        return [[]]
    return [[i] + rest for i in items for rest in _product(items, n - 1)]


def build_arch(spec_paths, **kwargs):
    return architecture(spec_paths, **kwargs)


def assign(spec, arch, files=None):
    from analysis.architecture_rules import layer_assignments
    ids = files if files is not None else [n.id for n in arch.nodes if not (n.metadata or {}).get('boundary')]
    return layer_assignments(to_rules(spec), ids, package_schemes(arch))


def test_V04_path_only():
    paths = ['src/a/x.py', 'src/a/deep/z.py', 'src/b/y.py', 'src/b/deep/w.py', 'docs/z.md']
    spec = {'layers': {'a': {'paths': ['src/a/**']}, 'b': {'paths': ['src/b/*.py']}}}
    assert assign(spec, architecture(paths)) == {fid('src/a/x.py'): 'a', fid('src/a/deep/z.py'): 'a', fid('src/b/y.py'): 'b'}


def test_V04_package_language():
    modules = {'app/models/domain/users.py': 'app.models.domain.users', 'app/models/domain/sub/y.py': 'app.models.domain.sub.y',
               'app/models/schemas/x.py': 'app.models.schemas.x', 'app/Models/domain/q.py': 'App.models.domain.q'}
    dnodes, files = python_modules(modules)
    arch = architecture(list(modules) + ['docs/a.md', 'Docs/a.md'], dnodes=dnodes, node_files=files)
    spec = {'layers': {'domain': {'packages': ['pkg:python:app.models.domain']}, 'schemas': {'packages': ['pkg:python:app.models.sch*']},
                       'docs': {'packages': ['pkg:dir:do?s']}}}
    assert assign(spec, arch) == {fid('app/models/domain/users.py'): 'domain', fid('app/models/schemas/x.py'): 'schemas',
                                  fid('docs/a.md'): 'docs'}


def nest_arch(extra_member=None):
    modules = {'FeedA': 'src/feed/a.module.ts', 'FeedB': 'src/feed/b.module.ts', 'Other': 'src/other/o.module.ts'}
    dnodes, dedges, files = [], [], {}
    for name, path in modules.items():
        node = dnode(f'nestjs:module:{name}', 'module', 'nestjs')
        dnodes.append(node)
        files[node['id']] = path
    members = [('FeedA', 'DECLARES', 'src/feed/c.ts'), ('FeedA', 'PROVIDES', 'src/shared/s.ts'), ('FeedB', 'PROVIDES', 'src/shared/s.ts'),
               ('Other', 'PROVIDES', 'src/other/p.ts')]
    if extra_member:
        members.append(extra_member)
    for owner, relation, path in members:
        ident = f'nestjs:provider:{path}#P'
        if ident not in files:
            dnodes.append(dnode(ident, 'provider', 'nestjs'))
            files[ident] = path
        dedges.append(dedge(f'nestjs:module:{owner}', ident, relation))
    paths = sorted({*modules.values(), *(m[2] for m in members), 'src/loose.ts'})
    return architecture(paths, dnodes=dnodes, dedges=dedges, node_files=files)


def test_V04_package_framework_shared():
    arch = nest_arch()
    spec = {'layers': {'feed': {'packages': ['pkg:nestjs:Feed*']}, 'other': {'packages': ['pkg:nestjs:Other']}}}
    assert assign(spec, arch) == {fid('src/feed/a.module.ts'): 'feed', fid('src/feed/b.module.ts'): 'feed', fid('src/feed/c.ts'): 'feed',
                                  fid('src/shared/s.ts'): 'feed', fid('src/other/o.module.ts'): 'other', fid('src/other/p.ts'): 'other'}


def test_V04_package_framework_shared_between_layers_is_multi_match():
    arch = nest_arch(('Other', 'PROVIDES', 'src/shared/s.ts'))
    spec = {'layers': {'feed': {'packages': ['pkg:nestjs:Feed*']}, 'other': {'packages': ['pkg:nestjs:Other']}}}
    with pytest.raises(error_type()) as raised:
        assign(spec, arch)
    message = str(raised.value)
    assert 'src/shared/s.ts' in message and 'feed' in message and 'other' in message and '1' in message


def test_V04_path_or_package():
    modules = {'app/core/c.py': 'app.core.c', 'lib/y.py': 'app.core.y', 'lib/z.py': 'zzz.z', 'plain/p.py': 'plain.p'}
    dnodes, files = python_modules(modules)
    arch = architecture(list(modules), dnodes=dnodes, node_files=files)
    spec = {'layers': {'mixed': {'paths': ['lib/**'], 'packages': ['pkg:python:app.core']}}}
    assert assign(spec, arch) == {fid('app/core/c.py'): 'mixed', fid('lib/y.py'): 'mixed', fid('lib/z.py'): 'mixed'}


def test_V04_unmatched_files_are_absent():
    arch = architecture(['x/a.py', 'y/b.py'])
    spec = {'layers': {'only': {'paths': ['x/**']}, 'nothing': {'paths': ['q/**'], 'packages': ['pkg:dir:q']}}}
    assert assign(spec, arch) == {fid('x/a.py'): 'only'}
    assert assign(spec, architecture([])) == {}


def multi_arch(count, extra=()):
    names = [f'shared/f{i:02}.py' for i in range(count)]
    names += list(extra)
    random.Random(7).shuffle(names)
    return names


def window(message, path, listed):
    lines = [line for line in message.splitlines() if path in line and not any(o in line for o in listed if o != path)]
    if lines:
        return ' '.join(lines)
    start = message.index(path)
    ends = [message.index(o, start + 1) for o in listed if o != path and message.find(o, start + 1) != -1]
    return message[start:min(ends)] if ends else message[start:]


def test_V04_multi_match_error_12():
    names = multi_arch(12, extra=['solo/a.py', 'alpha_only/x.py'])
    spec = {'layers': {'alpha': {'paths': ['shared/**', 'alpha_only/**']}, 'beta': {'paths': ['shared/f0?.py']},
                       'gamma': {'paths': ['shared/f1?.py']}}}
    arch = architecture(names)
    with pytest.raises(error_type()) as raised:
        assign(spec, arch)
    message = str(raised.value)
    listed = [f'shared/f{i:02}.py' for i in range(10)]
    assert '12' in message
    for path in listed:
        assert path in message
    for path in ('shared/f10.py', 'shared/f11.py'):
        assert path not in message
    assert 'solo/a.py' not in message and 'alpha_only/x.py' not in message
    positions = [message.index(p) for p in listed]
    assert positions == sorted(positions)
    for path in listed:
        near = window(message, path, listed)
        assert 'alpha' in near and 'beta' in near and 'gamma' not in near, (path, near)


def test_V04_multi_match_error_12_names_second_layer_pair():
    names = [f'shared/f{i:02}.py' for i in range(12)]
    spec = {'layers': {'alpha': {'paths': ['shared/**']}, 'gamma': {'paths': ['shared/*.py']}}}
    with pytest.raises(error_type()) as raised:
        assign(spec, architecture(names))
    assert 'alpha' in str(raised.value) and 'gamma' in str(raised.value) and '12' in str(raised.value)


def test_V04_multi_match_error_1():
    spec = {'layers': {'alpha': {'paths': ['src/**']}, 'beta': {'paths': ['src/a/**']}, 'gamma': {'paths': ['docs/**']}}}
    with pytest.raises(error_type()) as raised:
        assign(spec, architecture(['src/a/x.py', 'src/b/y.py', 'docs/d.md']))
    message = str(raised.value)
    assert 'src/a/x.py' in message and 'alpha' in message and 'beta' in message
    assert 'src/b/y.py' not in message and 'docs/d.md' not in message and 'gamma' not in message
    assert '1' in message


def verdict(spec, paths, edges, **kwargs):
    arch = architecture(paths, edges, **kwargs)
    result = analyze_structure(arch, weights(), to_rules(spec))
    _, expected, coverage = ref_rule_evaluation(spec, arch, weights())
    actual = violations_of(result.candidates)
    assert_candidates_equal(actual, expected)
    return result, actual, coverage


def summary(candidates):
    return sorted((c['structure']['rule_type'], c['structure']['from_layer'], c['structure']['to_layer'], c['target'],
                   c['evidence'][0]['to_id']) for c in candidates)


SPEC3 = {'version': 1, 'layers': {'a': {'paths': ['src/a/**']}, 'b': {'paths': ['src/b/**']}, 'c': {'paths': ['src/c/**']}}}


def spec3(allow=None, forbid=None):
    return {**SPEC3, 'allow': allow or {}, 'forbid': forbid or []}


AX, BY, CZ = 'src/a/x.py', 'src/b/y.py', 'src/c/z.py'


def test_V05_allow_violation_candidate_fields_C01():
    make = edge_counter()
    result, actual, _ = verdict(spec3(allow={'a': []}), [AX, BY], [make(AX, BY, evidence=2)])
    assert summary(actual) == [('allow', 'a', 'b', fid(AX), fid(BY))]
    item = actual[0]
    expected_id = 'b:' + __import__('hashlib').sha256(f'rule|allow|a|b|{fid(AX)}|{fid(BY)}'.encode()).hexdigest()[:16]
    assert item['id'] == expected_id
    assert set(item) == {'id', 'kind', 'target', 'metrics', 'evidence', 'coverage', 'status', 'structure'}
    assert item['kind'] == RULE_KIND and item['target'] == fid(AX)
    assert item['coverage'] == 'static_analyzer_relation' and item['status'] == 'static_candidate'
    assert item['metrics']['evidence_count'] == 2 and set(item['metrics']) == {'evidence_count', 'max_weight'}
    assert item['metrics']['max_weight'] == item['evidence'][0]['max_weight'] > 0
    assert set(item['structure']) == {'rule_type', 'from_layer', 'to_layer', 'tier', 'relations'}
    assert item['structure'] == {'rule_type': 'allow', 'from_layer': 'a', 'to_layer': 'b', 'tier': 'certain', 'relations': ['IMPORTS']}
    record = item['evidence'][0]
    assert (record['from_id'], record['to_id'], record['relations'], record['evidence_count']) == (fid(AX), fid(BY), ['IMPORTS'], 2)
    assert record['detail_edge_indices'] == [0] and record['tier'] == 'certain'


def test_V05_forbid_only_direction_matters_C02():
    make = edge_counter()
    _, actual, _ = verdict(spec3(forbid=[{'from': 'a', 'to': ['b']}]), [AX, BY], [make(AX, BY), make(BY, AX)])
    assert summary(actual) == [('forbid', 'a', 'b', fid(AX), fid(BY))]


def test_V05_allow_and_forbid_both_C03():
    make = edge_counter()
    _, actual, _ = verdict(spec3(allow={'a': ['c']}, forbid=[{'from': 'a', 'to': ['b']}]), [AX, BY, CZ], [make(AX, BY)])
    assert summary(actual) == [('allow', 'a', 'b', fid(AX), fid(BY)), ('forbid', 'a', 'b', fid(AX), fid(BY))]
    assert len({c['id'] for c in actual}) == 2


def test_V05_row_allowed_target_in_allow_list_and_forbidden_gives_forbid_only():
    make = edge_counter()
    _, actual, _ = verdict(spec3(allow={'a': ['b']}, forbid=[{'from': 'a', 'to': ['b']}]), [AX, BY], [make(AX, BY)])
    assert summary(actual) == [('forbid', 'a', 'b', fid(AX), fid(BY))]


def test_V05_row_allowed_target_in_allow_list_not_forbidden_gives_none():
    make = edge_counter()
    _, actual, _ = verdict(spec3(allow={'a': ['b']}, forbid=[{'from': 'a', 'to': ['c']}]), [AX, BY, CZ], [make(AX, BY)])
    assert actual == []


def test_V05_row_allow_key_absent_forbid_hit():
    make = edge_counter()
    _, actual, _ = verdict(spec3(allow={'c': []}, forbid=[{'from': 'a', 'to': ['b', 'c']}]), [AX, BY, CZ], [make(AX, BY), make(AX, CZ)])
    assert summary(actual) == [('forbid', 'a', 'b', fid(AX), fid(BY)), ('forbid', 'a', 'c', fid(AX), fid(CZ))]


def test_V05_row_allow_key_absent_no_forbid_C05():
    make = edge_counter()
    _, actual, _ = verdict(spec3(allow={'a': []}), [AX, BY], [make(BY, AX)])
    assert actual == []


def test_V05_same_layer_C04():
    make = edge_counter()
    _, actual, _ = verdict(spec3(allow={'a': []}, forbid=[{'from': 'b', 'to': ['c']}]), [AX, 'src/a/z.py', BY, 'src/b/q.py'],
                           [make(AX, 'src/a/z.py'), make(BY, 'src/b/q.py'), make(AX, AX)])
    assert actual == []


def test_V05_unassigned_end_C04():
    make = edge_counter()
    _, actual, _ = verdict(spec3(allow={'a': [], 'b': []}, forbid=[{'from': 'a', 'to': ['b']}]), [AX, BY, 'other/u.py'],
                           [make(AX, 'other/u.py'), make('other/u.py', AX), make('other/u.py', BY)])
    assert actual == []


def test_V05_tests_only_C06():
    make = edge_counter()
    _, actual, _ = verdict(spec3(allow={'a': []}), [AX, BY], [make(AX, BY, relation='TESTS')])
    assert actual == []


def test_V05_tests_edge_next_to_real_edge_adds_nothing():
    make = edge_counter()
    _, actual, _ = verdict(spec3(allow={'a': []}), [AX, BY], [make(AX, BY, relation='TESTS', evidence=9), make(AX, BY, evidence=2)])
    assert len(actual) == 1
    assert actual[0]['metrics']['evidence_count'] == 2 and actual[0]['structure']['relations'] == ['IMPORTS']


@pytest.mark.parametrize('direction', ['to-boundary', 'from-boundary'])
def test_V05_boundary_end_C06(direction):
    boundary = 'src/b/ext.py'
    edge = raw_edge(fid(AX), boundary) if direction == 'to-boundary' else raw_edge(boundary, fid(AX))
    _, actual, coverage = verdict(spec3(allow={'a': [], 'b': []}, forbid=[{'from': 'a', 'to': ['b']}]), [AX, BY], [edge], boundary=[boundary])
    assert actual == []
    assert boundary not in ' '.join(coverage['unassigned_files']) and coverage['layer_file_counts']['b'] == 1


def test_V05_mixed_tier_C07():
    make = edge_counter()
    spec = spec3(allow={'a': []})
    arch_edges = [make(AX, BY, evidence=2, indices=[0, 1]),
                  make(AX, BY, relation='CALLS', confidence=SI, resolution=AMBIGUOUS, share=.5, evidence=3, indices=[2])]
    result, actual, _ = verdict(spec, [AX, BY], arch_edges)
    assert len(actual) == 1
    item = actual[0]
    assert item['structure']['tier'] == 'certain' and item['evidence'][0]['tier'] == 'certain'
    assert item['metrics']['evidence_count'] == 5
    w = weights()
    assert item['metrics']['max_weight'] == pytest.approx(max(w.weight_for(arch_edges[0]), w.weight_for(arch_edges[1]) * .5))
    assert item['structure']['relations'] == ['CALLS', 'IMPORTS'] and item['evidence'][0]['detail_edge_indices'] == [0, 1, 2]


def test_V05_mixed_tier_resolved_beats_all():
    make = edge_counter()
    edges = [make(AX, BY, confidence=SI, resolution=EXACT), make(AX, BY, confidence=SI, resolution=AMBIGUOUS)]
    _, actual, _ = verdict(spec3(allow={'a': []}), [AX, BY], edges)
    assert [c['structure']['tier'] for c in actual] == ['resolved'] and actual[0]['metrics']['evidence_count'] == 2


def test_V05_ambiguous_only_C08():
    make = edge_counter()
    _, actual, _ = verdict(spec3(allow={'a': []}), [AX, BY], [make(AX, BY, confidence=SI, resolution=AMBIGUOUS, share=.25)])
    assert len(actual) == 1 and actual[0]['structure']['tier'] == 'all' and actual[0]['evidence'][0]['tier'] == 'all'


def test_V05_candidate_per_file_pair_and_sorted_by_id():
    make = edge_counter()
    a1, a2, b1, b2 = 'src/a/1.py', 'src/a/2.py', 'src/b/1.py', 'src/b/2.py'
    edges = [make(a1, b1), make(a1, b2), make(a2, b1), make(a2, b2), make(b1, a1)]
    result, actual, _ = verdict(spec3(allow={'a': []}, forbid=[{'from': 'b', 'to': ['a']}]), [a1, a2, b1, b2], edges)
    assert len(actual) == 5
    assert [c['id'] for c in actual] == sorted(c['id'] for c in actual)
    kinds = [c['kind'] for c in result.candidates]
    ids = [c['id'] for c in result.candidates if c['kind'] == RULE_KIND]
    assert ids == sorted(ids) and len(set(ids)) == 5 and kinds.count(RULE_KIND) == 5


def test_V05_tiers_below_all_are_not_dropped_for_unresolved_edges():
    make = edge_counter()
    edges = [make(AX, BY, confidence=SI, resolution=UNIQUE)]
    _, actual, _ = verdict(spec3(allow={'a': []}), [AX, BY], edges)
    assert len(actual) == 1 and actual[0]['structure']['tier'] == 'resolved'


@pytest.mark.parametrize('seed', range(24))
def test_V05_random_graphs_match_reference(seed):
    arch, spec = random_graph(seed)
    result = analyze_structure(arch, weights(), to_rules(spec))
    _, expected, coverage = ref_rule_evaluation(spec, arch, weights())
    assert_candidates_equal(violations_of(result.candidates), expected)
    assert without_digest(result.coverage['architecture_rules']) == coverage


def test_V05_random_graph_family_is_not_vacuous():
    rule_types, tiers, relations = set(), set(), set()
    for seed in range(24):
        arch, spec = random_graph(seed)
        _, expected, _ = ref_rule_evaluation(spec, arch, weights())
        for item in expected:
            rule_types.add(item['structure']['rule_type'])
            tiers.add(item['structure']['tier'])
            relations.update(item['structure']['relations'])
    assert rule_types == {'allow', 'forbid'} and tiers == {'certain', 'resolved', 'all'} and 'TESTS' not in relations


def test_V06_counts_all_layers_and_policy_fields():
    make = edge_counter()
    spec = {'version': 1, 'layers': {'zz': {'paths': ['nowhere/**']}, 'b': {'paths': ['src/b/**']}, 'a': {'paths': ['src/a/**']}},
            'allow': {'a': []}}
    paths = [AX, 'src/a/x2.py', BY]
    result, _, _ = verdict(spec, paths, [make(AX, BY)])
    coverage = without_digest(result.coverage['architecture_rules'])
    assert coverage['policy'] == RULES_POLICY == 'architecture_rules.v1' and coverage['version'] == 1
    assert coverage['layer_file_counts'] == {'a': 2, 'b': 1, 'zz': 0}
    assert list(coverage['layer_file_counts']) == ['a', 'b', 'zz']
    assert set(coverage) == {'policy', 'version', 'layer_file_counts', 'unassigned_file_count', 'unassigned_files', 'empty_layers',
                             'violation_count'}


def test_V06_zero_layer_listed_and_empty_layers_sorted():
    spec = {'version': 1, 'layers': {'qq': {'paths': ['q/**']}, 'pp': {'paths': ['p/**']}, 'a': {'paths': ['src/a/**']}}}
    result, _, _ = verdict(spec, [AX], [])
    coverage = without_digest(result.coverage['architecture_rules'])
    assert coverage['layer_file_counts'] == {'a': 1, 'pp': 0, 'qq': 0}
    assert coverage['empty_layers'] == ['pp', 'qq']


def test_V06_unassigned_list_sorted_and_excludes_boundary():
    spec = {'version': 1, 'layers': {'a': {'paths': ['src/a/**']}}}
    result, _, _ = verdict(spec, [AX, 'other/u2.py', 'other/u1.py', 'z.py'], [], boundary=['lib/boundary.py'])
    coverage = without_digest(result.coverage['architecture_rules'])
    assert coverage['unassigned_file_count'] == 3
    assert coverage['unassigned_files'] == [fid('other/u1.py'), fid('other/u2.py'), fid('z.py')]
    assert coverage['empty_layers'] == []


def test_V06_violation_count_counts_candidates_not_pairs():
    make = edge_counter()
    spec = spec3(allow={'a': []}, forbid=[{'from': 'a', 'to': ['b']}])
    result, actual, _ = verdict(spec, [AX, BY, CZ], [make(AX, BY), make(AX, CZ), make(BY, AX)])
    assert len(actual) == 3
    assert without_digest(result.coverage['architecture_rules'])['violation_count'] == 3


@pytest.mark.parametrize('details', [True, False], ids=['details', 'no-details'])
def test_V06_empty_graph(details):
    spec = spec3(allow={'a': []})
    arch = architecture([], [], details=details)
    result = analyze_structure(arch, weights(), to_rules(spec))
    assert result.candidates == ()
    assert without_digest(result.coverage['architecture_rules']) == {
        'policy': RULES_POLICY, 'version': 1, 'layer_file_counts': {'a': 0, 'b': 0, 'c': 0}, 'unassigned_file_count': 0,
        'unassigned_files': [], 'empty_layers': ['a', 'b', 'c'], 'violation_count': 0}


def test_V13_rules_none_equals_phase1_result():
    arch, spec = random_graph(3)
    base = analyze_structure(arch, weights())
    assert analyze_structure(arch, weights(), None) == base
    assert 'architecture_rules' not in base.coverage
    assert all(c['kind'] != RULE_KIND for c in base.candidates)
    with_rules = analyze_structure(arch, weights(), to_rules(spec))
    assert [c for c in with_rules.candidates if c['kind'] != RULE_KIND] == list(base.candidates)
    assert with_rules.package_metrics == base.package_metrics
    assert {k: v for k, v in with_rules.coverage.items() if k != 'architecture_rules'} == base.coverage


def test_V13_empty_graph_with_rules_matches_empty_phase1():
    arch = architecture([], [])
    base = analyze_structure(arch, weights())
    result = analyze_structure(arch, weights(), to_rules(spec3()))
    assert result.candidates == base.candidates == ()
    assert result.package_metrics == base.package_metrics


def test_V13_layer_pattern_matching_nothing_is_not_an_error():
    make = edge_counter()
    spec = {'version': 1, 'layers': {'ghost': {'paths': ['no/such/**'], 'packages': ['pkg:dir:no/such']}, 'a': {'paths': ['src/a/**']},
                                     'b': {'paths': ['src/b/**']}}, 'forbid': [{'from': 'a', 'to': ['ghost']}]}
    result, actual, _ = verdict(spec, [AX, BY], [make(AX, BY)])
    coverage = without_digest(result.coverage['architecture_rules'])
    assert actual == [] and coverage['empty_layers'] == ['ghost'] and coverage['layer_file_counts']['ghost'] == 0


def test_V13_file_id_without_prefix_uses_the_id_as_path():
    from analysis.architecture_rules import layer_assignments
    rules = to_rules({'layers': {'a': {'paths': ['src/a/**']}, 'b': {'paths': ['src/b/**']}}})
    result = layer_assignments(rules, ['src/a/x.py', 'file:src/b/y.py'], {'language': {}})
    assert result == {'src/a/x.py': 'a', 'file:src/b/y.py': 'b'}


def test_V13_file_prefix_is_not_part_of_the_matched_path():
    from analysis.architecture_rules import layer_assignments
    rules = to_rules({'layers': {'a': {'paths': ['file:src/**']}, 'b': {'paths': ['**']}}})
    assert layer_assignments(rules, ['file:src/x.py'], {'language': {}}) == {'file:src/x.py': 'b'}
    assert path_of('file:src/x.py') == 'src/x.py'


def v8_payload():
    from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
    from tests.edge_weights_support import edge
    from tests.file_analysis_support import converted, node
    files = {AX: 'x = 1\n', BY: 'y = 1\n', CZ: 'z = 1\n'}
    nodes = [node('x', AX), node('y', BY), node('z', CZ)]
    snap, arch = converted(files, nodes, [edge('x', 'y'), edge('z', 'x')])
    spec = spec3(allow={'a': []}, forbid=[{'from': 'c', 'to': ['a']}])
    report = analyze_bottlenecks(snap, arch, weights(), rules=to_rules(spec))
    return json.loads(bottlenecks_to_json(report)), arch, spec


def render(payload):
    from pathlib import Path
    from report.bottlenecks import render_report
    from report.bottlenecks.generate import generate
    writes = []
    generate(Path('in.json'), Path('out.html'), read_text=lambda path: json.dumps(payload), write_text=lambda path, text: writes.append(text))
    assert len(writes) == 1
    return render_report(payload), writes[0]


def test_V09_v8_with_rule_violation_ok_and_label():
    from report.bottlenecks.generate import KIND_DESCRIPTIONS, KIND_LABELS
    payload, arch, _ = v8_payload()
    assert payload['schema'] == 'bottlenecks.v9'
    assert {c['kind'] for c in payload['candidates']} >= {RULE_KIND}
    assert KIND_LABELS[RULE_KIND] == '경계 규칙 위반'
    assert isinstance(KIND_DESCRIPTIONS[RULE_KIND], str) and KIND_DESCRIPTIONS[RULE_KIND].strip()
    from tests.report_size_support import legacy_v8
    for text in render(legacy_v8(payload, arch)):
        assert '<html' in text.lower() and '경계 규칙 위반' in text


def test_V09_coverage_architecture_rules_accepted_and_matches_reference():
    payload, arch, spec = v8_payload()
    assert 'architecture_rules' in payload['coverage']
    assert without_digest(payload['coverage']['architecture_rules'])['policy'] == RULES_POLICY
    assert without_digest(payload['coverage']['architecture_rules'])['violation_count'] == 2
    assert without_digest(payload['coverage']['architecture_rules'])['layer_file_counts'] == {'a': 1, 'b': 1, 'c': 1}
    from tests.report_size_support import legacy_v8
    for text in render(legacy_v8(payload, arch)):
        assert '<html' in text.lower()


def test_V09_payload_candidates_are_sorted_by_kind_then_id():
    payload, arch, spec = v8_payload()
    keys = [(c['kind'], c['id']) for c in payload['candidates']]
    assert keys == sorted(keys)


def test_V09_rules_absent_payload_has_no_architecture_rules_coverage():
    from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
    from tests.edge_weights_support import edge
    from tests.file_analysis_support import converted, node
    snap, arch = converted({AX: 'x = 1\n', BY: 'y = 1\n'}, [node('x', AX), node('y', BY)], [edge('x', 'y')])
    payload = json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, weights())))
    assert 'architecture_rules' not in payload['coverage'] and all(c['kind'] != RULE_KIND for c in payload['candidates'])
    assert payload['schema'] == 'bottlenecks.v9'


def test_V08_F12_multi_match_error_keeps_its_message_through_analyze_bottlenecks():
    from bottlenecks import BottleneckInputError, analyze_bottlenecks
    from tests.file_analysis_support import converted, node
    snap, arch = converted({AX: 'x = 1\n'}, [node('x', AX)], [])
    spec = {'layers': {'alpha': {'paths': ['src/**']}, 'beta': {'paths': ['src/a/**']}}}
    with pytest.raises(error_type()) as raised:
        analyze_bottlenecks(snap, arch, weights(), rules=to_rules(spec))
    assert not isinstance(raised.value, BottleneckInputError)
    assert 'alpha' in str(raised.value) and 'beta' in str(raised.value) and AX in str(raised.value)


ARCH_RULES_SOURCE = REPO / 'analysis' / 'architecture_rules.py'


@pytest.mark.parametrize('source,framework,language', [
    ('import framework_analyzers.nestjs', ['framework_analyzers.nestjs'], []),
    ('from framework_analyzers import fastapi', ['framework_analyzers', 'framework_analyzers.fastapi'], []),
    ('from language_analyzers.python.graph import X', [], ['language_analyzers.python.graph', 'language_analyzers.python.graph.X']),
    ('def f():\n    from language_analyzers.kotlin import K', [], ['language_analyzers.kotlin', 'language_analyzers.kotlin.K']),
    ('import importlib\nimportlib.import_module("language_analyzers.typescript")', [], ['language_analyzers.typescript']),
    ('from ..framework_analyzers.android import A', ['framework_analyzers.android', 'framework_analyzers.android.A'], []),
    ('from language_analyzers.core.graph_models import GraphEdge', [], []),
    ('import fnmatch, re, yaml', [], []),
])
def test_V12_checker_detects_and_allows_expected_forms(source, framework, language):
    modules = imported_modules(source)
    assert framework_imports(modules) == framework and language_imports(modules) == language


def test_V12_no_framework_import():
    modules = imported_modules(ARCH_RULES_SOURCE.read_text(encoding='utf-8'))
    assert modules
    assert framework_imports(modules) == []


def test_V12_no_lang_specific_import():
    modules = imported_modules(ARCH_RULES_SOURCE.read_text(encoding='utf-8'))
    assert language_imports(modules) == []
