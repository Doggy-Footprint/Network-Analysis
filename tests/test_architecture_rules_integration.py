"""Expected CLI hashes come from tests/architecture_rules_evidence/base_manifest.json, produced at the pre-feature commit.
Size checks are deliberately not benchmark-marked so they run in the default selection; the 20k-node time budget runs with -m benchmark."""
import hashlib
import json
import statistics
import sys
import time

import pytest

from analysis.architecture_rules import layer_assignments
from analysis.structure import analyze_structure, package_assignments
from fixtures.registry import fixture_root
from tests.delta_support import base_form_bytes, without_digest
from tests.architecture_rules_support import (EXAMPLE_PROFILE, EXAMPLE_SPEC, FIXTURES, REPO, RULE_KIND, assert_candidates_equal, cli,
                                              copy_fixture, init_git, load_manifest, mini_project, ref_rule_evaluation, synthetic_input,
                                              to_rules, violations_of, weights, write_rules)

from tests.android_build_support import NAME as ANDROID, assert_architecture_changes_are_build_only, assert_file_changes_are_build_only, assert_symbol_changes_are_build_only, without_build_parts

MANIFEST = load_manifest()


def fixture_args(name):
    return MANIFEST['fixtures'][name]['args']


class Output(bytes):
    """The bottlenecks.json bytes; `.legacy` is the same report in the base-commit (v8) layout, rebuilt with its details file."""


def run_cli(name, directory, rules=None, seed='0', root=None):
    directory.mkdir(parents=True, exist_ok=True)
    args = [root or fixture_root(name).resolve(), *fixture_args(name), '--granularity', 'file', '-o', directory / 'r.html',
            '--bottlenecks', directory / 'b.json', '--json']
    if rules is not None:
        args += ['--architecture-rules', rules]
    done = cli(args, seed=seed)
    assert done.returncode == 0, done.stderr[-2000:]
    from tests.report_size_support import legacy_bottlenecks_canonical
    out = Output((directory / 'b.json').read_bytes())
    out.legacy = legacy_bottlenecks_canonical(directory / 'b.json', directory / 'r.json')
    return out


@pytest.fixture(scope='module', params=FIXTURES)
def plain(request, tmp_path_factory):
    name = request.param
    return name, run_cli(name, tmp_path_factory.mktemp('plain-' + name))


def test_V07_no_rules_byte_equal_to_base(plain):
    name, data = plain
    if name == ANDROID:
        assert_file_changes_are_build_only(json.loads(data))
        return
    expected = MANIFEST['fixtures'][name]
    base_form = base_form_bytes(data.legacy)
    assert len(base_form) == expected['bytes']
    assert hashlib.sha256(base_form).hexdigest() == expected['sha256']
    assert json.loads(data)['schema'] == 'bottlenecks.v9'


@pytest.fixture(scope='module')
def realworld_plain(tmp_path_factory):
    return json.loads(run_cli('fastapi-realworld', tmp_path_factory.mktemp('rw-plain')))


@pytest.fixture(scope='module')
def realworld_rules_bytes(tmp_path_factory):
    return run_cli('fastapi-realworld', tmp_path_factory.mktemp('rw-rules'), rules=EXAMPLE_PROFILE)


@pytest.fixture(scope='module')
def realworld_rules(realworld_rules_bytes):
    return json.loads(realworld_rules_bytes)


@pytest.fixture(scope='module')
def realworld_arch(tmp_path_factory):
    import code_analyzer.cli as cli_module
    seen = {}
    original = cli_module.analyze_bottlenecks

    def spy(snapshot, arch, weights_, *args, **kwargs):
        seen['arch'] = arch
        return original(snapshot, arch, weights_, *args, **kwargs)

    directory = tmp_path_factory.mktemp('rw-inproc')
    argv = ['code-analyzer', str(fixture_root('fastapi-realworld').resolve()), *fixture_args('fastapi-realworld'), '--granularity', 'file',
            '-o', str(directory / 'r.html'), '--bottlenecks', str(directory / 'b.json')]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cli_module, 'analyze_bottlenecks', spy)
        patch.setattr(sys, 'argv', argv)
        cli_module.main()
    assert seen
    return seen['arch']


@pytest.mark.parametrize('seed', ['1', '2', '0'])
def test_V07_determinism_hashseed_with_rules(tmp_path, realworld_rules_bytes, seed):
    assert run_cli('fastapi-realworld', tmp_path / seed, rules=EXAMPLE_PROFILE, seed=seed) == realworld_rules_bytes


def test_V07_rules_change_only_the_rule_parts(realworld_plain, realworld_rules):
    plain_candidates = realworld_plain['candidates']
    others = [c for c in realworld_rules['candidates'] if c['kind'] != RULE_KIND]
    assert others == plain_candidates
    keys = [(c['kind'], c['id']) for c in realworld_rules['candidates']]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    assert {k: v for k, v in realworld_rules['coverage'].items() if k != 'architecture_rules'} == realworld_plain['coverage']
    assert realworld_rules['schema'] == 'bottlenecks.v9' and 'architecture_rules' not in realworld_plain['coverage']


def internal_only(candidates):
    return [c for c in candidates if c['kind'] == RULE_KIND and c['structure']['rule_type'] in ('allow', 'forbid')]


def test_V08_example_realworld_against_reference(realworld_rules, realworld_arch):
    _, expected, coverage = ref_rule_evaluation(EXAMPLE_SPEC, realworld_arch, weights())
    actual = violations_of(internal_only(realworld_rules['candidates']))
    assert_candidates_equal(actual, expected)
    got = dict(without_digest(realworld_rules['coverage']['architecture_rules']))
    external_keys = {'external_import_count', 'external_violation_count'}
    assert external_keys <= set(got)
    total = got.pop('violation_count')
    assert {k: v for k, v in got.items() if k not in external_keys} == {k: v for k, v in coverage.items() if k != 'violation_count'}
    assert total == len(actual) + got['external_violation_count']
    assert coverage['violation_count'] == len(actual) > 0


def test_V08_example_realworld_expected_violations_exist(realworld_rules):
    found = {(c['structure']['rule_type'], c['structure']['from_layer'], c['structure']['to_layer'])
             for c in internal_only(realworld_rules['candidates'])}
    assert ('allow', 'domain', 'services') in found
    assert ('forbid', 'db', 'api') in found
    assert {rule for rule, source, _ in found if rule == 'allow'} and all(s == 'domain' for r, s, _ in found if r == 'allow')
    assert all((s, t) in {('db', 'api'), ('services', 'api')} for r, s, t in found if r == 'forbid')
    coverage = without_digest(realworld_rules['coverage']['architecture_rules'])
    assert coverage['policy'] == 'architecture_rules.v1' and coverage['version'] == 1
    assert set(coverage['layer_file_counts']) == set(EXAMPLE_SPEC['layers'])
    assert coverage['violation_count'] == sum(1 for c in realworld_rules['candidates'] if c['kind'] == RULE_KIND)


def output_state(directory):
    return {name: (directory / name).exists() for name in ('report.html', 'report.json', 'report_assets', 'b.json')}


MINI = {'src/a.py': 'x = 1\n', 'src/b.py': 'import src.a\n'}


def mini_run(tmp_path, project, rules_path, extra=()):
    out = tmp_path / 'out'
    out.mkdir()
    args = [project, '-l', 'python', '--granularity', 'file', '-o', out / 'report.html', '--json', '--bottlenecks', out / 'b.json', *extra]
    if rules_path is not None:
        args += ['--architecture-rules', rules_path]
    return cli(args), out


def test_V08_positive_control_outputs_exist_without_rules(tmp_path):
    project = mini_project(tmp_path / 'p', MINI)
    done, out = mini_run(tmp_path, project, None)
    assert done.returncode == 0, done.stderr
    state = output_state(out)
    assert state['report.html'] and state['report.json'] and state['b.json']


GOOD_LAYERS = 'version: 1\nlayers:\n  la:\n    paths: [src/a.py]\n  lb:\n    paths: [src/b.py]\n'
BAD_RULES = {
    'unknown-key': ('version: 1\nlayers:\n  la:\n    paths: [src/a.py]\nnonsense_key: 1\n', 'nonsense_key'),
    'external': (GOOD_LAYERS + 'external: [libs]\n', 'external'),
    'syntax': ('version: [1\n', None),
    'missing-file': (None, 'no_such_rules.yaml'),
}


@pytest.mark.parametrize('case', sorted(BAD_RULES))
def test_V08_bad_rules_exit1_no_output(tmp_path, case):
    project = mini_project(tmp_path / 'p', MINI)
    text, needle = BAD_RULES[case]
    rules = tmp_path / 'no_such_rules.yaml' if text is None else write_rules(tmp_path, text)
    done, out = mini_run(tmp_path, project, rules)
    assert done.returncode == 1
    assert done.stderr.startswith('[!] Error:'), done.stderr
    if needle:
        assert needle in done.stderr
    if case == 'syntax':
        assert str(rules) in done.stderr
    assert not any(output_state(out).values()), output_state(out)


def test_V08_multi_match_exit1_no_output(tmp_path):
    files = {f'shared/f{i:02}.py': 'x = 1\n' for i in range(12)}
    files['solo/s.py'] = 'y = 1\n'
    project = mini_project(tmp_path / 'p', files)
    rules = write_rules(tmp_path, 'version: 1\nlayers:\n  alpha:\n    paths: ["shared/**"]\n  beta:\n    paths: ["shared/*.py"]\n')
    done, out = mini_run(tmp_path, project, rules)
    assert done.returncode == 1
    assert done.stderr.startswith('[!] Error:'), done.stderr
    for token in ('12', 'alpha', 'beta', 'shared/f00.py', 'shared/f09.py'):
        assert token in done.stderr
    assert 'shared/f10.py' not in done.stderr and 'shared/f11.py' not in done.stderr
    assert not any(output_state(out).values()), output_state(out)


@pytest.mark.parametrize('rules_kind', ['valid', 'missing'])
def test_V08_symbol_granularity_exit2_no_output(tmp_path, rules_kind):
    project = mini_project(tmp_path / 'p', MINI)
    rules = write_rules(tmp_path, GOOD_LAYERS) if rules_kind == 'valid' else tmp_path / 'absent.yaml'
    out = tmp_path / 'out'
    out.mkdir()
    done = cli([project, '-l', 'python', '--granularity', 'symbol', '-o', out / 'report.html', '--json', '--bottlenecks', out / 'b.json',
                '--architecture-rules', rules])
    assert done.returncode == 2
    assert list(out.iterdir()) == []


def test_V08_empty_layer_and_violation_keep_exit_0(tmp_path):
    project = mini_project(tmp_path / 'p', MINI)
    rules = write_rules(tmp_path, GOOD_LAYERS + '  ghost:\n    paths: ["nothing/**"]\nallow:\n  lb: []\n')
    done, out = mini_run(tmp_path, project, rules)
    assert done.returncode == 0, done.stderr
    payload = json.loads((out / 'b.json').read_text(encoding='utf-8'))
    coverage = without_digest(payload['coverage']['architecture_rules'])
    assert coverage['empty_layers'] == ['ghost'] and coverage['violation_count'] >= 1
    assert [c['structure']['rule_type'] for c in payload['candidates'] if c['kind'] == RULE_KIND][0] == 'allow'


def allow_violations(payload):
    return [c for c in payload['candidates'] if c['kind'] == RULE_KIND and c['structure']['rule_type'] == 'allow']


def test_V08_reverse_import_copy_adds_allow_violation(tmp_path, realworld_rules):
    copy = copy_fixture('fastapi-realworld', tmp_path / 'copy')
    target = copy / 'app' / 'models' / 'domain' / 'rwmodel.py'
    target.write_text(target.read_text(encoding='utf-8') + '\nimport app.api.routes.api\n', encoding='utf-8')
    init_git(copy)
    after = json.loads(run_cli('fastapi-realworld', tmp_path / 'run', rules=EXAMPLE_PROFILE, root=copy))
    new_pair = ('file:app/models/domain/rwmodel.py', 'file:app/api/routes/api.py')

    def pairs(payload):
        return {(c['target'], c['evidence'][0]['to_id']) for c in allow_violations(payload)}

    assert new_pair not in pairs(realworld_rules)
    assert new_pair in pairs(after)
    assert len(allow_violations(after)) > len(allow_violations(realworld_rules))
    added = [c for c in allow_violations(after) if (c['target'], c['evidence'][0]['to_id']) == new_pair][0]
    assert added['structure']['from_layer'] == 'domain' and added['structure']['to_layer'] == 'api'


def test_V11_size_ratio_realworld(realworld_rules_bytes):
    ratio = len(realworld_rules_bytes.legacy) / MANIFEST['fixtures']['fastapi-realworld']['bytes']
    assert ratio <= 1.25, ratio
    assert len(realworld_rules_bytes.legacy) >= MANIFEST['fixtures']['fastapi-realworld']['bytes']


TIME_LIMIT = 5.0


def median_time(function):
    samples = []
    for _ in range(3):
        started = time.perf_counter()
        function()
        samples.append(time.perf_counter() - started)
    return statistics.median(samples)


def test_V11_synthetic_time():
    arch, spec = synthetic_input()
    assert len(arch.nodes) == 20000 and len(arch.edges) == 100000 and len(spec['layers']) == 10
    assert all(len(v['paths']) == 5 and len(v['packages']) == 5 for v in spec['layers'].values())
    rules = to_rules(spec)
    result = analyze_structure(arch, weights(), rules)
    _, expected, coverage = ref_rule_evaluation(spec, arch, weights())
    assert without_digest(result.coverage['architecture_rules'])['violation_count'] == coverage['violation_count'] == len(expected) > 1000


@pytest.mark.benchmark
def test_V11_synthetic_time_budget():
    arch, spec = synthetic_input()
    rules = to_rules(spec)
    ids = [node.id for node in arch.nodes]
    packages = package_assignments(arch)
    assert median_time(lambda: layer_assignments(rules, ids, packages)) <= TIME_LIMIT
    with_rules = median_time(lambda: analyze_structure(arch, weights(), rules))
    without = median_time(lambda: analyze_structure(arch, weights()))
    assert with_rules - without <= TIME_LIMIT, (with_rules, without)
