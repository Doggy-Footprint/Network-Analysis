"""Expected hashes and byte counts come from tests/external_rules_evidence/base_manifest.json, produced at the pre-feature
commit. Size and time checks are deliberately not benchmark-marked so they run in the default selection."""
import fnmatch
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

import pytest

from analysis.structure import analyze_structure
from fixtures.registry import fixture_root
from tests.architecture_rules_support import (EXAMPLE_SPEC, assert_candidates_equal, cli, mini_project, ref_rule_evaluation,
                                              violations_of, weights, write_rules)
from tests.external_rules_support import (KOTLIN_PACKAGE, ALLOW_EXT, EXAMPLE_EXT_SPEC, EXTERNAL_COVERAGE_KEYS, FIXTURES, FORBID_EXT,
                                          INTERNAL_COVERAGE_KEYS, RULE_KIND, SYMBOL_FIXTURES, assert_external_equal,
                                          canonical_architecture_sha, ext_arch, external_violations, file_nodes, keys_found, load_manifest,
                                          names_by_file, rec, records_by_file, ref_coverage, ref_external_evaluation,
                                          ref_kotlin_external_names, ref_normalize, ref_python_external_names, ref_ts_scan,
                                          to_rules_ext)

MANIFEST = load_manifest()
EXAMPLE_PROFILE = Path(__file__).resolve().parents[1] / 'profiles' / 'architecture_rules.example.yaml'


def fixture_args(name):
    return MANIFEST['fixtures'][name]['args']


def run_cli(name, directory, granularity='file', rules=None, seed='0', root=None):
    directory.mkdir(parents=True, exist_ok=True)
    args = [root or fixture_root(name).resolve(), *fixture_args(name), '--granularity', granularity, '--json', '-o', directory / 'r.html']
    if granularity == 'file':
        args += ['--bottlenecks', directory / 'b.json']
    if rules is not None:
        args += ['--architecture-rules', rules]
    done = cli(args, seed=seed)
    assert done.returncode == 0, done.stderr[-2000:]
    return {'arch': (directory / 'r.json').read_bytes(), 'bn': (directory / 'b.json').read_bytes() if granularity == 'file' else None}


@pytest.fixture(scope='module', params=SYMBOL_FIXTURES)
def symbol(request, tmp_path_factory):
    name = request.param
    run = run_cli(name, tmp_path_factory.mktemp('symbol-' + name), granularity='symbol')
    return name, run, json.loads(run['arch'])


@pytest.fixture(scope='module')
def by_name(tmp_path_factory):
    cache = {}

    def get(name):
        if name not in cache:
            run = run_cli(name, tmp_path_factory.mktemp('shared-' + name))
            cache[name] = (run, json.loads(run['arch']))
        return cache[name]
    return get


@pytest.fixture(scope='module', params=FIXTURES)
def plain(request, by_name):
    run, payload = by_name(request.param)
    return request.param, run, payload


@pytest.fixture(scope='module')
def realworld_rules_run(tmp_path_factory):
    return run_cli('fastapi-realworld', tmp_path_factory.mktemp('rw-rules'), rules=EXAMPLE_PROFILE)


@pytest.fixture(scope='module')
def realworld_rules(realworld_rules_run):
    return json.loads(realworld_rules_run['bn'])


@pytest.fixture(scope='module')
def realworld_2a_rules(tmp_path_factory):
    directory = tmp_path_factory.mktemp('rw-2a')
    rules = write_rules(directory, EXAMPLE_SPEC, 'rules2a.yaml')
    return json.loads(run_cli('fastapi-realworld', directory / 'run', rules=rules)['bn'])


@pytest.fixture(scope='module')
def realworld_arch(tmp_path_factory):
    import code_analyzer.cli as cli_module
    seen = {}
    original = cli_module.analyze_bottlenecks

    def spy(snapshot, arch, weights_, *args, **kwargs):
        seen['arch'] = arch
        return original(snapshot, arch, weights_, *args, **kwargs)

    directory = tmp_path_factory.mktemp('rw-inproc')
    argv = ['code-analyzer', str(fixture_root('fastapi-realworld').resolve()), *fixture_args('fastapi-realworld'), '--granularity',
            'file', '-o', str(directory / 'r.html'), '--bottlenecks', str(directory / 'b.json')]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cli_module, 'analyze_bottlenecks', spy)
        patch.setattr(sys, 'argv', argv)
        cli_module.main()
    assert seen
    return seen['arch']


def test_V11_bottleneck_json_byte_equal_to_base(plain):
    name, run, _ = plain
    expected = MANIFEST['fixtures'][name]['file']
    assert len(run['bn']) == expected['bottleneck_bytes']
    assert hashlib.sha256(run['bn']).hexdigest() == expected['bottleneck_sha256']
    assert json.loads(run['bn'])['schema'] == 'bottlenecks.v8'


def test_V11_architecture_file_canonical_equal_to_base(plain):
    name, _, payload = plain
    assert canonical_architecture_sha(payload) == MANIFEST['fixtures'][name]['file']['architecture_canonical_sha256']


def test_V11_architecture_symbol_canonical_equal_to_base(symbol):
    name, _, payload = symbol
    assert canonical_architecture_sha(payload) == MANIFEST['fixtures'][name]['symbol']['architecture_canonical_sha256']


def test_V11_file_nodes_carry_external_imports_with_the_f01_f02_shape(plain):
    name, _, payload = plain
    records = records_by_file(payload)
    assert records, name
    allowed = {'name', 'line', 'specifier', 'dynamic'}
    for path, items in records.items():
        assert items and items == ref_normalize(items), path
        for item in items:
            assert set(item) <= allowed and isinstance(item['name'], str) and item['name']
            assert isinstance(item['line'], int) and item['line'] >= 1
            assert item.get('dynamic', True) is True and item.get('specifier') != item['name']
            if not name.startswith('typescript'):
                assert set(item) == {'name', 'line'}


def test_V07_details_keep_the_key_boundary_and_bottleneck_json_do_not(plain):
    _, run, payload = plain
    assert all('external_imports' not in n['metadata'] for n in payload['nodes'] if n['metadata'].get('boundary'))
    node_files = payload['details']['node_files']
    held = {}
    for detail in payload['details']['nodes']:
        records = detail['metadata'].get('external_imports')
        if records:
            held.setdefault(node_files.get(detail['id']), []).extend(records)
    assert held
    for path, records in records_by_file(payload).items():
        assert ref_normalize(held.get('file:' + path, [])) == records, path
    assert b'external_imports' not in run['bn'] and b'external_import_count' not in run['bn']
    top = [n for n in payload['nodes'] if 'external_imports' in n['metadata']]
    assert top and all(n['id'].startswith('file:') for n in top)


def test_V07_symbol_mode_keeps_the_key_on_analyzer_nodes(symbol):
    name, _, payload = symbol
    found = keys_found(payload, 'external_imports')
    assert any(path[0] == 'nodes' and path[2:] == ('metadata', 'external_imports') for path in found), name


@pytest.mark.parametrize('seed', ['1', '2'])
def test_V11_C28_determinism_hashseed_with_rules(tmp_path, realworld_rules_run, seed):
    again = run_cli('fastapi-realworld', tmp_path, rules=EXAMPLE_PROFILE, seed=seed)
    assert again['bn'] == realworld_rules_run['bn']
    assert again['arch'] == realworld_rules_run['arch']


def test_V11_C30_2a_rules_file_gives_the_2a_result(realworld_2a_rules, realworld_arch, plain_realworld_candidates):
    _, expected, coverage = ref_rule_evaluation(EXAMPLE_SPEC, realworld_arch, weights())
    assert_candidates_equal(violations_of(realworld_2a_rules['candidates']), expected)
    assert realworld_2a_rules['coverage']['architecture_rules'] == coverage
    assert set(coverage) == INTERNAL_COVERAGE_KEYS
    assert external_violations(realworld_2a_rules['candidates']) == []
    others = [c for c in realworld_2a_rules['candidates'] if c['kind'] != RULE_KIND]
    assert others == plain_realworld_candidates


@pytest.fixture(scope='module')
def plain_realworld_candidates(by_name):
    return json.loads(by_name('fastapi-realworld')[0]['bn'])['candidates']


def forbid_pairs(candidates):
    return {(c['target'][len('file:'):], c['structure']['to_external']) for c in candidates
            if c['structure']['rule_type'] == FORBID_EXT}


def test_V12_C22_realworld_example_violations(realworld_rules, realworld_2a_rules, realworld_arch):
    external = external_violations(realworld_rules['candidates'])
    assert forbid_pairs(external) == {('app/api/dependencies/database.py', 'asyncpg.connection'),
                                      ('app/api/dependencies/database.py', 'asyncpg.pool'), ('app/db/events.py', 'fastapi')}
    assert len(external) == 3
    assert not [c for c in external if c['structure']['rule_type'] == ALLOW_EXT]
    internal = [c for c in realworld_rules['candidates'] if c['kind'] == RULE_KIND and c['id'] not in {e['id'] for e in external}]
    assert internal == [c for c in realworld_2a_rules['candidates'] if c['kind'] == RULE_KIND]
    expected, total = ref_external_evaluation(EXAMPLE_EXT_SPEC, realworld_arch)
    assert_external_equal(external, expected)
    coverage = realworld_rules['coverage']['architecture_rules']
    assert coverage == ref_coverage(EXAMPLE_EXT_SPEC, realworld_arch, weights())
    assert coverage['external_import_count'] == total and coverage['external_violation_count'] == 3
    assert coverage['violation_count'] == len(internal) + 3


def test_V12_C22_independent_ast_reading_of_the_fixture_sources(realworld_rules):
    root = fixture_root('fastapi-realworld')
    names = ref_python_external_names(root, 'app')
    web, driver = EXAMPLE_EXT_SPEC['external']['web'], EXAMPLE_EXT_SPEC['external']['db_driver']
    expected = set()
    for path, found in names.items():
        if path.startswith('app/db/'):
            expected |= {(path, n) for n in found if any(fnmatch.fnmatchcase(n, p) for p in web)}
        if path.startswith('app/api/'):
            expected |= {(path, n) for n in found if any(fnmatch.fnmatchcase(n, p) for p in driver)}
    assert expected == forbid_pairs(external_violations(realworld_rules['candidates']))


def test_V12_C22_example_profile_loaded_through_cli_has_the_f15_coverage(realworld_rules):
    coverage = realworld_rules['coverage']['architecture_rules']
    assert set(coverage) == INTERNAL_COVERAGE_KEYS | EXTERNAL_COVERAGE_KEYS
    assert realworld_rules['schema'] == 'bottlenecks.v8'


def test_V12_C23_official_template_backend_root(by_name):
    _, payload = by_name('fastapi-official-template')
    found = names_by_file(payload)
    app_files = {p: n for p, n in found.items() if p.startswith('backend/app/')}
    assert app_files
    flat = set().union(*app_files.values())
    assert {'fastapi', 'sqlmodel'} <= flat
    assert not {n for n in flat if n == 'app' or n.startswith('app.')}
    expected = ref_python_external_names(fixture_root('fastapi-official-template'), 'backend/app')
    assert {p: found.get(p, set()) for p in expected} == expected


def test_V12_C24_nestjs_records(by_name):
    _, payload = by_name('typescript-nestjs-realworld')
    records = records_by_file(payload)
    src = {p: r for p, r in records.items() if p.startswith('src/')}
    flat = [r for items in src.values() for r in items]
    assert {'@nestjs/common', 'typeorm'} <= {r['name'] for r in flat}
    assert not [r for r in flat if r['name'].startswith(('.', '/')) or r.get('specifier', '').startswith(('.', '/'))]
    assert any(r.get('specifier') for r in flat)
    root = fixture_root('typescript-nestjs-realworld')
    checked = 0
    for node in file_nodes(payload):
        path = node['id'][len('file:'):]
        if not (path.startswith('src/') and path.endswith('.ts')):
            continue
        scanned, literals = ref_ts_scan((root / path).read_text(encoding='utf-8'))
        recorded = {r['name'] for r in records.get(path, ())}
        assert scanned <= recorded <= literals, (path, scanned - recorded, recorded - literals)
        checked += 1
    assert checked > 20


def test_V12_C25_nowinandroid_records(by_name):
    _, payload = by_name('android-nowinandroid')
    found = names_by_file(payload)
    flat = set().union(*found.values())
    assert any(n.startswith('androidx.') for n in flat)
    root = fixture_root('android-nowinandroid')
    paths = [p for p in (n['id'][len('file:'):] for n in file_nodes(payload) if n['id'].endswith('.kt')) if (root / p).is_file()]
    assert paths
    declared = {m.group(1) for p in paths for m in KOTLIN_PACKAGE.finditer((root / p).read_text(encoding='utf-8'))}
    assert not [n for n in flat if any(n == d or n.startswith(d + '.') for d in declared)]
    expected = ref_kotlin_external_names(root, paths)
    assert {p: found.get(p, set()) for p in paths} == expected


def test_V14_architecture_size_ratio(plain):
    name, run, _ = plain
    ratio = len(run['arch']) / MANIFEST['fixtures'][name]['file']['architecture_bytes']
    assert 1.0 < ratio <= 1.05, ratio


def test_V14_bottleneck_size_ratio_realworld(realworld_rules_run, by_name):
    plain_bytes = by_name('fastapi-realworld')[0]['bn']
    ratio = len(realworld_rules_run['bn']) / len(plain_bytes)
    assert 1.0 <= ratio <= 1.25, ratio
    assert len(plain_bytes) == MANIFEST['fixtures']['fastapi-realworld']['file']['bottleneck_bytes']


MINI_PY = {'app/__init__.py': '', 'app/x.py': 'import os\nfrom app import y\n', 'app/y.py': 'Y = 1\n'}


def mini_arch(tmp_path, files, language='python', granularity='file', extra=(), rules=None):
    project = mini_project(tmp_path / 'p', files)
    out = tmp_path / 'out'
    out.mkdir()
    args = [project, '-l', language, '--granularity', granularity, '-o', out / 'report.html', '--json', *extra]
    if rules is not None:
        args += ['--architecture-rules', rules]
    done = cli(args)
    return done, out


def test_V07_cli_file_mode_projects_to_file_nodes_and_details_keep_key(tmp_path):
    done, out = mini_arch(tmp_path, MINI_PY)
    assert done.returncode == 0, done.stderr
    payload = json.loads((out / 'report.json').read_text(encoding='utf-8'))
    assert records_by_file(payload) == {'app/x.py': [rec('os', 1)]}
    held = {d['id']: d['metadata']['external_imports'] for d in payload['details']['nodes'] if 'external_imports' in d['metadata']}
    assert held == {'py:app.x': [rec('os', 1)]}


def test_V07_cli_symbol_mode_keeps_module_node_key(tmp_path):
    done, out = mini_arch(tmp_path, MINI_PY, granularity='symbol')
    assert done.returncode == 0, done.stderr
    payload = json.loads((out / 'report.json').read_text(encoding='utf-8'))
    holders = {n['id']: n['metadata']['external_imports'] for n in payload['nodes'] if 'external_imports' in n['metadata']}
    assert holders == {'py:app.x': [rec('os', 1)]}


@pytest.mark.parametrize('case', ['external-list', 'allow-external-undefined-layer', 'undefined-group'])
def test_V08_cli_bad_external_rules_exit1_no_output(tmp_path, case):
    layers = 'version: 1\nlayers:\n  la:\n    paths: [app/x.py]\n'
    text = {'external-list': layers + 'external: [libs]\n',
            'allow-external-undefined-layer': layers + 'allow_external:\n  zzz_undefined: [os]\n',
            'undefined-group': layers + 'forbid:\n  - from: la\n    to_external: ["group:missing"]\n'}[case]
    needle = {'external-list': 'external', 'allow-external-undefined-layer': 'zzz_undefined', 'undefined-group': 'missing'}[case]
    project = mini_project(tmp_path / 'p', MINI_PY)
    out = tmp_path / 'out'
    out.mkdir()
    done = cli([project, '-l', 'python', '--granularity', 'file', '-o', out / 'report.html', '--json', '--bottlenecks', out / 'b.json',
                '--architecture-rules', write_rules(tmp_path, text)])
    assert done.returncode == 1 and done.stderr.startswith('[!] Error:') and needle in done.stderr, done.stderr
    assert list(out.iterdir()) == []


def test_V12_cli_external_rule_violation_exits_zero_and_reports(tmp_path):
    text = ('version: 1\nlayers:\n  la:\n    paths: [app/x.py]\nforbid:\n  - from: la\n    to_external: [os]\n'
            'allow_external:\n  la: [json]\n')
    done, out = mini_arch(tmp_path, MINI_PY, extra=['--bottlenecks', tmp_path / 'out' / 'b.json'], rules=write_rules(tmp_path, text))
    assert done.returncode == 0, done.stderr
    payload = json.loads((tmp_path / 'out' / 'b.json').read_text(encoding='utf-8'))
    found = sorted((c['structure']['rule_type'], c['structure']['to_external']) for c in external_violations(payload['candidates']))
    assert found == [(ALLOW_EXT, 'os'), (FORBID_EXT, 'os')]
    assert payload['coverage']['architecture_rules']['external_violation_count'] == 2


def test_V05_cli_invalid_tsconfig_exit0_and_coverage_recorded(tmp_path):
    files = {'tsconfig.json': '{"compilerOptions": [', 'src/a.ts': "import {x} from '@/lib'\nexport const a = 1\n"}
    done, out = mini_arch(tmp_path, files, language='typescript')
    assert done.returncode == 0, done.stderr
    payload = json.loads((out / 'report.json').read_text(encoding='utf-8'))
    rows = [r for r in payload['stats']['analysis_coverage']['files'] if r['file_path'] == 'tsconfig.json']
    codes = [(x['analyzer_id'], x['status'], [r['code'] for r in x['reasons']]) for r in rows for x in r['results']]
    assert codes == [('typescript-core', 'partial', ['tsconfig_invalid'])]
    assert records_by_file(payload) == {'src/a.ts': [rec('@/lib', 1)]}


def test_V05_cli_valid_tsconfig_alias_excluded_and_nothing_recorded(tmp_path):
    files = {'tsconfig.json': '{"compilerOptions": {"paths": {"@/*": ["src/*"]}}} // jsonc', 'src/a.ts':
             "import {x} from '@/lib'\nimport l from 'lodash'\nexport const a = 1\n"}
    done, out = mini_arch(tmp_path, files, language='typescript')
    assert done.returncode == 0, done.stderr
    payload = json.loads((out / 'report.json').read_text(encoding='utf-8'))
    assert 'tsconfig_invalid' not in json.dumps(payload['stats']['analysis_coverage'])
    assert records_by_file(payload) == {'src/a.ts': [rec('lodash', 2)]}


def synthetic_external_input(files=20000, names_per_file=20, seed=20261018):
    import random
    rnd = random.Random(seed)
    pool = [f'lib{a}.mod{b}' for a in range(20) for b in range(10)]
    layer_files = {}
    for index in range(files):
        picked = sorted(rnd.sample(pool, names_per_file))
        layer_files[f'L{index % 10}/f{index}.py'] = [rec(name, 1 + position) for position, name in enumerate(picked)]
    groups = {f'g{i}': [f'lib{10 + i}.mod0'] + [f'zz{i}{j}*' for j in range(4)] for i in range(5)}
    spec = {'version': 1, 'layers': {f'layer{k}': {'paths': [f'L{k}/**']} for k in range(10)}, 'external': groups,
            'forbid': [{'from': f'layer{k}', 'to_external': [f'group:g{i}' for i in range(5)] +
                        [f'lib{(k + i) % 20}.mod{i + 5}' for i in range(5)]} for k in range(10)],
            'allow_external': {f'layer{k}': [f'lib{a}*' for a in range(1, 10)] + ['lib0.mod[0-4]'] for k in range(10)}}
    return layer_files, spec


def median_time(function):
    samples = []
    for _ in range(3):
        started = time.perf_counter()
        function()
        samples.append(time.perf_counter() - started)
    return statistics.median(samples)


def test_V14_C29_synthetic_time_and_correctness():
    files, spec = synthetic_external_input()
    assert len(files) == 20000 and all(len(r) == 20 for r in files.values()) and len(spec['layers']) == 10
    assert all(len(set(i['to_external'])) == 10 for i in spec['forbid']) and all(len(v) == 10 for v in spec['allow_external'].values())
    assert len(spec['external']) == 5 and all(len(v) == 5 for v in spec['external'].values())
    arch = ext_arch(files)
    rules = to_rules_ext(spec)
    plain_rules = to_rules_ext({'version': 1, 'layers': spec['layers']})
    result = analyze_structure(arch, weights(), rules)
    actual = external_violations(result.candidates)
    sample = {path: records for index, (path, records) in enumerate(files.items()) if index % 10 == 0}
    expected, _ = ref_external_evaluation(spec, ext_arch(sample))
    targets = {f'file:{p}' for p in sample}
    assert_external_equal([c for c in actual if c['target'] in targets], expected)
    assert 1000 < len(actual) <= 40000 and result.coverage['architecture_rules']['external_violation_count'] == len(actual)
    assert result.coverage['architecture_rules']['external_import_count'] == 20000 * 20
    with_external = median_time(lambda: analyze_structure(arch, weights(), rules))
    without = median_time(lambda: analyze_structure(arch, weights(), plain_rules))
    assert with_external - without <= 5.0, (with_external, without)
