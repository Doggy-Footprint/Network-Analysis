import json
import shutil

import pytest
from fixtures.registry import fixture_root

from tests.delta_support import (EXAMPLE_PROFILE, LISTS, RULES_WARNING, SUMMARY, append_file, cli, copy_fixture, outputs, ref_delta,
                                 retrack, run_bottlenecks, wire)

NAME = 'fastapi-realworld'
CYCLE_FILES = [('app/zz/__init__.py', ''),
               ('app/zz/a.py', 'from app.zz.b import fb\n\n\ndef fa():\n    return fb()\n'),
               ('app/zz/b.py', 'from app.zz.a import fa\n\n\ndef fb():\n    return fa()\n')]
VIOLATION_EDIT = [('app/models/domain/rwmodel.py', '\nfrom app.services.security import get_password_hash\n')]
PACKAGE_FILES = [('app/zz2/__init__.py', ''),
                 ('app/zz2/c.py', 'from app.core.config import get_app_settings\n\n\ndef c():\n    return get_app_settings\n')]
ALL_OUTPUTS = {'r.html': True, 'r.json': True, 'r_assets': False, 'b.json': True}
NO_OUTPUTS = {'r.html': False, 'r.json': False, 'r_assets': False, 'b.json': False}


@pytest.fixture(scope='module')
def pristine():
    return fixture_root(NAME).resolve()


@pytest.fixture(scope='module')
def baselines(tmp_path_factory, pristine):
    directory = tmp_path_factory.mktemp('baselines')
    plain = directory / 'plain'
    ruled = directory / 'ruled'
    run_bottlenecks(pristine, plain)
    run_bottlenecks(pristine, ruled, rules=EXAMPLE_PROFILE)
    return {'plain': plain / 'b.json', 'ruled': ruled / 'b.json'}


def edited(tmp_path, *edits, name='copy'):
    root = copy_fixture(NAME, tmp_path / name)
    for group in edits:
        for relative, text in group:
            append_file(root, relative, text)
    retrack(root)
    return root


def go(root, tmp_path, baseline, *flags, rules=None, directory='out', bottlenecks='b.json'):
    return run_bottlenecks(root, tmp_path / directory, rules=rules, extra=['--baseline', baseline, *flags], check=False,
                           bottlenecks=bottlenecks)


def written(tmp_path, directory='out'):
    return json.loads((tmp_path / directory / 'b.json').read_text(encoding='utf-8'))


def error_lines(done):
    return [line for line in done.stderr.splitlines() if line.startswith('[!]')]


def summary_for(delta):
    return SUMMARY.format(*(len(delta[name]) for name in LISTS))


def stdout_summary(done):
    return [line for line in done.stdout.splitlines() if line.startswith('[Δ]')]


def regression_line(delta, names):
    return (f"[!] Structural regression (--fail-on-new {names}): new cycles {len(delta['new_cycles'])}, "
            f"grown cycles {len(delta['grown_cycles'])}, new violations {len(delta['new_violations'])}")


def assert_matches_reference(after, baseline_path):
    base = json.loads(baseline_path.read_text(encoding='utf-8'))
    body = {k: v for k, v in after.items() if k != 'delta'}
    assert after['delta'] == wire(ref_delta(body, base))
    return after['delta']


def test_V07_C01_rerun_on_same_commit_reports_nothing(tmp_path, pristine, baselines):
    done = go(pristine, tmp_path, baselines['ruled'], '--fail-on-new', 'any', rules=EXAMPLE_PROFILE)
    assert done.returncode == 0, done.stderr[-1500:]
    delta = assert_matches_reference(written(tmp_path), baselines['ruled'])
    assert all(delta[name] == [] for name in LISTS)
    assert delta['resolved'] == {'cycles': 0, 'violations': 0, 'package_dependencies': 0}
    assert delta['rules_changed'] is False
    assert stdout_summary(done) == [summary_for(delta)] == [SUMMARY.format(0, 0, 0, 0, 0)]
    assert error_lines(done) == []
    assert outputs(tmp_path / 'out') == ALL_OUTPUTS


def test_V07_C01_rerun_without_rules(tmp_path, pristine, baselines):
    done = go(pristine, tmp_path, baselines['plain'], '--fail-on-new', 'any')
    assert done.returncode == 0, done.stderr[-1500:]
    delta = written(tmp_path)['delta']
    assert all(delta[name] == [] for name in LISTS) and delta['baseline']['rules_sha256'] is None
    assert delta['baseline']['file_count'] == json.loads(baselines['plain'].read_text())['snapshot']['file_count']
    assert error_lines(done) == []


def test_V07_no_baseline_means_no_delta_and_no_summary(tmp_path, pristine):
    done = run_bottlenecks(pristine, tmp_path / 'out')
    assert 'delta' not in written(tmp_path)
    assert stdout_summary(done) == []


@pytest.mark.parametrize('flags, names, expected_code', [
    (['--fail-on-new', 'cycle'], 'cycle', 3),
    (['--fail-on-new', 'any'], 'cycle', 3),
    (['--fail-on-new', 'violation'], None, 0),
    ([], None, 0),
])
def test_V07_C02_new_cycle(tmp_path, baselines, flags, names, expected_code):
    root = edited(tmp_path, CYCLE_FILES)
    done = go(root, tmp_path, baselines['plain'], *flags)
    after = written(tmp_path)
    delta = assert_matches_reference(after, baselines['plain'])
    members = {m for item in delta['new_cycles'] + delta['grown_cycles'] for m in item['members'] if item['scheme'] == 'file'}
    assert {'file:app/zz/a.py', 'file:app/zz/b.py'} <= members
    assert done.returncode == expected_code, done.stderr[-1500:]
    assert outputs(tmp_path / 'out') == ALL_OUTPUTS
    assert stdout_summary(done) == [summary_for(delta)]
    if names:
        assert error_lines(done) == [regression_line(delta, names)]
    else:
        assert error_lines(done) == []


def test_V07_C02_every_tier_is_reported(tmp_path, baselines):
    root = edited(tmp_path, CYCLE_FILES)
    go(root, tmp_path, baselines['plain'])
    delta = written(tmp_path)['delta']
    tiers = {item['tier'] for item in delta['new_cycles'] + delta['grown_cycles']
             if item['scheme'] == 'file' and 'file:app/zz/a.py' in item['members']}
    assert tiers == {'certain', 'resolved', 'all'}


def test_V07_C03_new_boundary_violation(tmp_path, baselines):
    root = edited(tmp_path, VIOLATION_EDIT)
    done = go(root, tmp_path, baselines['ruled'], '--fail-on-new', 'violation', rules=EXAMPLE_PROFILE)
    delta = assert_matches_reference(written(tmp_path), baselines['ruled'])
    assert [(i['rule_type'], i['from_layer'], i['to_layer'], i['target'], i['to_id']) for i in delta['new_violations']] == [
        ('allow', 'domain', 'services', 'file:app/models/domain/rwmodel.py', 'file:app/services/security.py')]
    assert delta['new_cycles'] == [] and delta['grown_cycles'] == []
    assert done.returncode == 3
    assert error_lines(done) == [regression_line(delta, 'violation')]
    assert outputs(tmp_path / 'out') == ALL_OUTPUTS
    assert stdout_summary(done) == [summary_for(delta)]


def test_V07_C03_cycle_flag_does_not_fail_on_a_violation_only_change(tmp_path, baselines):
    root = edited(tmp_path, VIOLATION_EDIT)
    done = go(root, tmp_path, baselines['ruled'], '--fail-on-new', 'cycle', rules=EXAMPLE_PROFILE)
    assert done.returncode == 0, done.stderr[-1500:]
    assert len(written(tmp_path)['delta']['new_violations']) == 1
    assert error_lines(done) == []


def test_V07_C04_new_package_dependency_never_fails(tmp_path, baselines):
    root = edited(tmp_path, PACKAGE_FILES)
    done = go(root, tmp_path, baselines['plain'], '--fail-on-new', 'any')
    delta = assert_matches_reference(written(tmp_path), baselines['plain'])
    assert delta['new_package_dependencies'] == [{'scheme': 'language', 'from_id': 'pkg:python:app.zz2',
                                                  'to_id': 'pkg:python:app.core', 'tier': 'certain'}]
    assert delta['new_cycles'] == [] and delta['grown_cycles'] == [] and delta['new_violations'] == []
    assert done.returncode == 0, done.stderr[-1500:]
    assert stdout_summary(done) == [SUMMARY.format(0, 0, 0, 1, 0)]
    assert error_lines(done) == []


def test_V07_C15_baseline_and_bottlenecks_share_a_path(tmp_path, baselines):
    root = edited(tmp_path, PACKAGE_FILES)
    shared = tmp_path / 'out' / 'b.json'
    shared.parent.mkdir()
    shutil.copy(baselines['plain'], shared)
    original = shared.read_bytes()
    done = run_bottlenecks(root, tmp_path / 'out', extra=['--baseline', shared], check=False)
    assert done.returncode == 0, done.stderr[-1500:]
    after = written(tmp_path)
    assert shared.read_bytes() != original
    assert after['delta']['counts']['new_package_dependencies'] == 1
    assert after['delta'] == wire(ref_delta({k: v for k, v in after.items() if k != 'delta'}, json.loads(original)))


def test_V07_C22_both_regressions_name_both(tmp_path, baselines):
    root = edited(tmp_path, CYCLE_FILES, VIOLATION_EDIT)
    done = go(root, tmp_path, baselines['ruled'], '--fail-on-new', 'cycle', '--fail-on-new', 'violation', rules=EXAMPLE_PROFILE)
    delta = assert_matches_reference(written(tmp_path), baselines['ruled'])
    assert delta['new_cycles'] and delta['new_violations']
    assert done.returncode == 3
    assert error_lines(done) == [regression_line(delta, 'cycle,violation')]
    assert outputs(tmp_path / 'out') == ALL_OUTPUTS


def test_V07_C22_any_names_only_what_triggered(tmp_path, baselines):
    root = edited(tmp_path, CYCLE_FILES, VIOLATION_EDIT)
    done = go(root, tmp_path, baselines['ruled'], '--fail-on-new', 'any', rules=EXAMPLE_PROFILE)
    assert done.returncode == 3
    assert error_lines(done) == [regression_line(written(tmp_path)['delta'], 'cycle,violation')]


def test_V07_C19_baseline_with_symbol_granularity_is_a_usage_error(tmp_path, pristine, baselines):
    done = cli([pristine, '-l', 'python', '--granularity', 'symbol', '--baseline', baselines['plain'], '--json',
                '-o', tmp_path / 'out' / 'r.html'])
    assert done.returncode == 2
    assert 'usage' in done.stderr.lower() and 'error' in done.stderr.lower()
    assert not (tmp_path / 'out').exists()


def test_V07_C19_fail_on_new_without_baseline_is_a_usage_error(tmp_path, pristine):
    done = cli([pristine, '-l', 'python', '--granularity', 'file', '--fail-on-new', 'any', '--json', '-o', tmp_path / 'out' / 'r.html',
                '--bottlenecks', tmp_path / 'out' / 'b.json'])
    assert done.returncode == 2
    assert 'usage' in done.stderr.lower() and 'error' in done.stderr.lower()
    assert not (tmp_path / 'out').exists()


def test_V07_fail_on_new_rejects_unknown_choice(tmp_path, pristine, baselines):
    done = go(pristine, tmp_path, baselines['plain'], '--fail-on-new', 'package')
    assert done.returncode == 2 and not (tmp_path / 'out' / 'b.json').exists()


def ruled_variant(tmp_path, text, name):
    target = tmp_path / name
    target.write_text(text, encoding='utf-8')
    return target


def test_V07_C14_changed_rules_warn_once_and_continue(tmp_path, pristine, baselines):
    text = EXAMPLE_PROFILE.read_text(encoding='utf-8')
    changed = ruled_variant(tmp_path, text.replace('  core:\n', '  extra:\n    paths: ["app/main.py"]\n  core:\n'), 'changed.yaml')
    assert changed.read_text() != text
    done = go(pristine, tmp_path, baselines['ruled'], rules=changed)
    assert done.returncode == 0, done.stderr[-1500:]
    after = written(tmp_path)
    delta = assert_matches_reference(after, baselines['ruled'])
    assert delta['rules_changed'] is True
    old = json.loads(baselines['ruled'].read_text())['coverage']['architecture_rules']['rules_sha256']
    assert after['coverage']['architecture_rules']['rules_sha256'] != old
    assert delta['baseline']['rules_sha256'] == old
    assert done.stderr.splitlines().count(RULES_WARNING) == 1
    assert error_lines(done) == [RULES_WARNING]
    assert stdout_summary(done) == [summary_for(delta)]


def test_V07_C13_reordered_commented_rules_do_not_warn(tmp_path, pristine, baselines):
    text = EXAMPLE_PROFILE.read_text(encoding='utf-8')
    reshuffled = '# reviewed\n' + text.replace('  api:\n    paths: ["app/api/**"]\n', '  api:  # edge layer\n    paths: ["app/api/**", "app/api/**"]\n')
    reshuffled = reshuffled.replace('forbid:\n', '# order of rules is irrelevant\nforbid:\n')
    assert reshuffled != text
    variant = ruled_variant(tmp_path, reshuffled, 'same.yaml')
    done = go(pristine, tmp_path, baselines['ruled'], rules=variant)
    assert done.returncode == 0, done.stderr[-1500:]
    delta = written(tmp_path)['delta']
    assert delta['rules_changed'] is False
    assert error_lines(done) == []


# V08 and C16-C18 ------------------------------------------------------------------------------------------------------

def broken_baseline(tmp_path, baselines, kind):
    data = json.loads(baselines['ruled'].read_text(encoding='utf-8'))
    target = tmp_path / 'broken.json'
    if kind == 'missing':
        return tmp_path / 'absent.json'
    if kind == 'directory':
        target.mkdir()
    elif kind == 'utf8':
        target.write_bytes(b'{"schema": "\xff"}')
    elif kind == 'truncated':
        text = json.dumps(data)
        target.write_text(text[:len(text) // 2], encoding='utf-8')
    elif kind == 'deep':
        target.write_text('[' * 100000 + ']' * 100000, encoding='utf-8')
    else:
        kind(data)
        target.write_text(json.dumps(data), encoding='utf-8')
    return target


def first(data, kind):
    return next(c for c in data['candidates'] if c['kind'] == kind)


def v7(data):
    data['schema'] = 'bottlenecks.v7'


def no_granularity(data):
    del data['granularity']


def no_package_dependencies(data):
    del data['dependency_network']['package_dependencies']


def bad_members(data):
    first(data, 'dependency_cycle')['structure']['members'] = 'a'


def no_violation_target(data):
    del next(c for c in data['candidates'] if c['kind'] == 'rule_violation' and 'to_layer' in c['structure'])['structure']['to_layer']


@pytest.mark.parametrize('kind', ['missing', 'directory', 'utf8', 'truncated', 'deep'])
def test_V08_C16_unreadable_baseline_stops_before_any_output(tmp_path, pristine, baselines, kind):
    path = broken_baseline(tmp_path, baselines, kind)
    done = go(pristine, tmp_path, path, '--fail-on-new', 'any')
    assert done.returncode == 1
    lines = error_lines(done)
    assert len(lines) == 1 and lines[0].startswith(f'[!] Error: baseline {path}: ')
    assert 'Traceback' not in done.stderr
    assert outputs(tmp_path / 'out') == NO_OUTPUTS


@pytest.mark.parametrize('mutate, needle', [
    (v7, 'schema'), (no_granularity, 'granularity'), (no_package_dependencies, 'package_dependencies'), (bad_members, 'members'),
    (no_violation_target, 'to_layer'),
], ids=['schema-v7', 'granularity-missing', 'package_dependencies-missing', 'members-type', 'violation-target-missing'])
def test_V08_C17_malformed_baseline_names_the_json_path(tmp_path, pristine, baselines, mutate, needle):
    path = broken_baseline(tmp_path, baselines, mutate)
    done = go(pristine, tmp_path, path, rules=EXAMPLE_PROFILE)
    assert done.returncode == 1
    [line] = error_lines(done)
    assert line.startswith(f'[!] Error: baseline {path}: ') and needle in line
    assert outputs(tmp_path / 'out') == NO_OUTPUTS


def test_V08_C17_structure_policy_difference_is_incompatible(tmp_path, pristine, baselines):
    def other_policy(data):
        data['dependency_network']['structure_policy'] = 'structure.v0'
    path = broken_baseline(tmp_path, baselines, other_policy)
    done = go(pristine, tmp_path, path, rules=EXAMPLE_PROFILE)
    assert done.returncode == 1
    [line] = error_lines(done)
    assert line.startswith('[!] Error: baseline: ') and 'structure_policy' in line
    assert outputs(tmp_path / 'out') == NO_OUTPUTS


def test_V08_C18_current_with_rules_against_baseline_without(tmp_path, pristine, baselines):
    done = go(pristine, tmp_path, baselines['plain'], rules=EXAMPLE_PROFILE)
    assert done.returncode == 1
    [line] = error_lines(done)
    assert line.startswith('[!] Error: baseline: ')
    assert outputs(tmp_path / 'out') == NO_OUTPUTS


def test_V08_C18_current_without_rules_against_baseline_with(tmp_path, pristine, baselines):
    done = go(pristine, tmp_path, baselines['ruled'])
    assert done.returncode == 1
    [line] = error_lines(done)
    assert line.startswith('[!] Error: baseline: ')
    assert outputs(tmp_path / 'out') == NO_OUTPUTS


def test_V08_incompatibility_does_not_overwrite_an_existing_bottleneck_file(tmp_path, pristine, baselines):
    target = tmp_path / 'out'
    target.mkdir()
    marker = b'previous run'
    (target / 'b.json').write_bytes(marker)
    done = go(pristine, tmp_path, baselines['plain'], rules=EXAMPLE_PROFILE)
    assert done.returncode == 1 and (target / 'b.json').read_bytes() == marker


# F13 / D8: a baseline inside the analyzed root is not part of the snapshot ---------------------------------------------

def file_count_of(path):
    return json.loads(path.read_text(encoding='utf-8'))['snapshot']['file_count']


def test_V07_D8_baseline_inside_the_project_root_is_excluded_from_the_snapshot(tmp_path, baselines):
    original = file_count_of(baselines['plain'])
    root = copy_fixture(NAME, tmp_path / 'inside')
    shutil.copy(baselines['plain'], root / 'prev.json')
    retrack(root)
    done = go(root, tmp_path, root / 'prev.json', directory='excluded')
    assert done.returncode == 0, done.stderr[-1500:]
    after = written(tmp_path, 'excluded')
    assert after['snapshot']['file_count'] == original
    assert 'prev.json' not in json.dumps(after['dependency_network']['node_metrics'])
    assert all(after['delta'][name] == [] for name in LISTS)


def test_V07_D8_same_file_in_the_root_but_not_passed_as_baseline_is_scanned(tmp_path, baselines):
    original = file_count_of(baselines['plain'])
    root = copy_fixture(NAME, tmp_path / 'inside')
    shutil.copy(baselines['plain'], root / 'prev.json')
    retrack(root)
    outside = tmp_path / 'outside.json'
    shutil.copy(baselines['plain'], outside)
    done = go(root, tmp_path, outside, directory='included')
    assert done.returncode == 0, done.stderr[-1500:]
    assert written(tmp_path, 'included')['snapshot']['file_count'] == original + 1


def test_V07_D8_baseline_and_bottlenecks_share_a_path_inside_the_root(tmp_path, baselines):
    original = file_count_of(baselines['plain'])
    root = copy_fixture(NAME, tmp_path / 'inside')
    shutil.copy(baselines['plain'], root / 'prev.json')
    retrack(root)
    out = tmp_path / 'out'
    out.mkdir()
    done = cli([root, *['-l', 'python'], '--granularity', 'file', '--json', '-o', out / 'r.html', '--baseline', root / 'prev.json',
                '--bottlenecks', root / 'prev.json'])
    assert done.returncode == 0, done.stderr[-1500:]
    after = json.loads((root / 'prev.json').read_text(encoding='utf-8'))
    assert 'delta' in after and after['snapshot']['file_count'] == original
    assert all(after['delta'][name] == [] for name in LISTS)
