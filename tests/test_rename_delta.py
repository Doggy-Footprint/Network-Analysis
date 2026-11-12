import json
from pathlib import Path

import pytest

from tests.delta_candidates_support import boundary_evidence, gen
from tests.delta_support import (DELTA_KEYS, LISTS, NOT_REQUESTED, SUMMARY, cycle, external_violation, internal_violation, payload,
                                 pdep, pmetrics, ref_delta, wire, without_renames)
from tests.rename_delta_support import (APP_FILES, MISSING_COMMIT, RENAMES_WARNING, analysis_args, block, empty_path_env, git,
                                        make_repo, move_a_to_a_impl, observations, oracle_pairs, run_cli, write_files)


def renames_api():
    import bottlenecks.renames as module
    return module


def delta_api():
    import bottlenecks.delta as module
    return module


def applied(*pairs, similarity=100):
    return {'status': 'applied', 'reason': None, 'pairs': [{'from': a, 'to': b, 'similarity': similarity} for a, b in pairs]}


def skipped(reason):
    return {'status': 'skipped', 'reason': reason, 'pairs': []}


def f(path):
    return f'file:{path}'


def compute(current, baseline, renames):
    result = wire(delta_api().compute_delta(current, baseline, renames))
    assert result == wire(ref_delta(current, baseline, renames))
    return result


def assert_quiet(result):
    assert all(result[name] == [] for name in LISTS)
    assert result['new_candidates'] == [] and result['strengthened_candidates'] == []
    assert result['resolved'] == {'cycles': 0, 'violations': 0, 'package_dependencies': 0, 'candidates': 0}



def commit_of(root):
    return git(root, 'rev-parse', 'HEAD').strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'repo'
    commit = make_repo(root, APP_FILES)
    return root, commit


def test_V01_EP1_clean_repo_records_head(repo):
    root, commit = repo
    assert len(commit) == 40
    assert renames_api().repository_commit(root) == (commit, None)


def test_V01_EP2_tracked_modification_is_dirty(repo):
    root, _ = repo
    (root / 'app' / 'a.py').write_text('changed = 1\n', encoding='utf-8')
    assert renames_api().repository_commit(root) == (None, 'dirty')


def test_V01_EP3_staged_change_is_dirty(repo):
    root, _ = repo
    (root / 'app' / 'a.py').write_text('changed = 1\n', encoding='utf-8')
    git(root, 'add', 'app/a.py')
    assert git(root, 'status', '--porcelain').startswith('M ')
    assert renames_api().repository_commit(root) == (None, 'dirty')


def test_V01_EP4_untracked_file_is_dirty(repo):
    root, _ = repo
    (root / 'app' / 'new.py').write_text('x = 1\n', encoding='utf-8')
    assert renames_api().repository_commit(root) == (None, 'dirty')


def test_V01_EP5_only_the_excluded_output_file_is_present(repo):
    root, commit = repo
    out = root / 'out.json'
    out.write_text('{}', encoding='utf-8')
    assert renames_api().repository_commit(root, exclude=[out]) == (commit, None)
    assert renames_api().repository_commit(root) == (None, 'dirty')
    (root / 'other.json').write_text('{}', encoding='utf-8')
    assert renames_api().repository_commit(root, exclude=[out]) == (None, 'dirty')


def test_V01_EP6_directory_that_is_not_a_repository(tmp_path):
    write_files(tmp_path / 'plain', APP_FILES)
    assert renames_api().repository_commit(tmp_path / 'plain') == (None, 'not_a_git_repository')


def test_V01_EP7_git_executable_missing(repo, tmp_path, monkeypatch):
    root, _ = repo
    monkeypatch.setenv('PATH', str(empty_path_env(tmp_path / 'nobin')['PATH']))
    assert renames_api().repository_commit(root) == (None, 'git_unavailable')


@pytest.fixture(scope='module')
def clean_cli_project(tmp_path_factory):
    base = tmp_path_factory.mktemp('clean-cli')
    root = base / 'repo'
    commit = make_repo(root, APP_FILES)
    done = run_cli(analysis_args(root, base / 'out'))
    assert done.returncode == 0, done.stderr[-1500:]
    return root, commit, base / 'out' / 'b.json'


def snapshot_of(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))['snapshot']


def test_V01_EP1_cli_clean_repo_snapshot(clean_cli_project):
    _, commit, bottlenecks = clean_cli_project
    snap = snapshot_of(bottlenecks)
    assert snap['git_commit'] == commit and snap['git_commit_reason'] is None
    assert set(snap) == {'file_count', 'ignore_source', 'git_commit', 'git_commit_reason'}


def cli_snapshot(tmp_path, state):
    root = tmp_path / 'repo'
    env = None
    out = tmp_path / 'out'
    if state == 'non-repo':
        write_files(root, APP_FILES)
    else:
        make_repo(root, APP_FILES)
    if state == 'tracked-modified':
        (root / 'app' / 'a.py').write_text('changed = 1\n', encoding='utf-8')
    elif state == 'untracked':
        (root / 'app' / 'new.py').write_text('x = 1\n', encoding='utf-8')
    elif state == 'no-git':
        env = empty_path_env(tmp_path / 'nobin')
    if state == 'outputs-only':
        args = [root, '-l', 'python', '--granularity', 'file', '-o', root / 'r.html', '--bottlenecks', root / 'b.json']
        out = root
    else:
        args = analysis_args(root, out)
    done = run_cli(args, env=env)
    assert done.returncode == 0, done.stderr[-1500:]
    assert 'Traceback' not in done.stderr
    return snapshot_of(out / 'b.json'), commit_of(root) if state != 'non-repo' and state != 'no-git' else None


@pytest.mark.parametrize('state, reason', [
    ('tracked-modified', 'dirty'), ('untracked', 'dirty'), ('non-repo', 'not_a_git_repository'), ('no-git', 'git_unavailable')])
def test_V01_C10_cli_snapshot_without_commit(tmp_path, state, reason):
    snap, _ = cli_snapshot(tmp_path, state)
    assert snap['git_commit'] is None and snap['git_commit_reason'] == reason


def test_V01_EP5_cli_output_files_inside_the_project_do_not_make_it_dirty(tmp_path):
    snap, head = cli_snapshot(tmp_path, 'outputs-only')
    assert snap['git_commit'] == head and snap['git_commit_reason'] is None



def detect(root, commit):
    result = renames_api().detect_renames(root, commit)
    assert set(result) == {'status', 'reason', 'pairs'}
    return result


def rename_repo(tmp_path, files):
    root = tmp_path / 'repo'
    return root, make_repo(root, files)


def test_V02_S1_git_mv_pure_rename(tmp_path):
    files = {'a.py': block('sa'), 'keep.py': block('keep')}
    root, commit = rename_repo(tmp_path, files)
    git(root, 'mv', 'a.py', 'a_impl.py')
    expected, _ = oracle_pairs(root, commit, tmp_path)
    assert expected == [{'from': 'a.py', 'to': 'a_impl.py', 'similarity': 100}]
    assert detect(root, commit) == {'status': 'applied', 'reason': None, 'pairs': expected}


def test_V02_S2_rename_with_edit(tmp_path):
    root, commit = rename_repo(tmp_path, {'src/m.py': block('s2'), 'keep.py': block('keep')})
    git(root, 'mv', 'src/m.py', 'src/m2.py')
    with open(root / 'src' / 'm2.py', 'a', encoding='utf-8') as handle:
        handle.write(block('added', 5))
    expected, _ = oracle_pairs(root, commit, tmp_path)
    assert len(expected) == 1 and expected[0]['from'] == 'src/m.py' and 50 <= expected[0]['similarity'] < 100
    assert detect(root, commit) == {'status': 'applied', 'reason': None, 'pairs': expected}


def test_V02_S3_untracked_new_file(tmp_path):
    root, commit = rename_repo(tmp_path, {'a.py': block('sa'), 'keep.py': block('keep')})
    (root / 'a.py').rename(root / 'a_impl.py')
    assert 'a_impl.py' in git(root, 'status', '--porcelain').split('?? ')[1]
    expected, _ = oracle_pairs(root, commit, tmp_path)
    assert expected == [{'from': 'a.py', 'to': 'a_impl.py', 'similarity': 100}]
    assert detect(root, commit) == {'status': 'applied', 'reason': None, 'pairs': expected}


def test_V02_S4_unrelated_delete_and_add_gives_no_pair(tmp_path):
    root, commit = rename_repo(tmp_path, {'a.py': block('sa'), 'keep.py': block('keep')})
    (root / 'a.py').unlink()
    (root / 'new.py').write_text(block('unrelated'), encoding='utf-8')
    expected, _ = oracle_pairs(root, commit, tmp_path)
    assert expected == []
    assert detect(root, commit) == {'status': 'applied', 'reason': None, 'pairs': []}


def test_V02_S5_two_renames_sorted_by_from(tmp_path):
    root, commit = rename_repo(tmp_path, {'a.py': block('sa'), 'b.py': block('sb'), 'keep.py': block('keep')})
    git(root, 'mv', 'a.py', 'z.py')
    (root / 'b.py').rename(root / 'c.py')
    expected, _ = oracle_pairs(root, commit, tmp_path)
    assert expected == [{'from': 'a.py', 'to': 'z.py', 'similarity': 100}, {'from': 'b.py', 'to': 'c.py', 'similarity': 100}]
    assert detect(root, commit) == {'status': 'applied', 'reason': None, 'pairs': expected}


def history_repo(tmp_path):
    root, base = rename_repo(tmp_path, {'a.py': block('sa'), 'b.py': block('sb'), 'keep.py': block('keep')})
    git(root, 'mv', 'a.py', 'a_impl.py')
    git(root, 'commit', '-q', '-m', 'rename a')
    assert git(root, 'rev-parse', 'HEAD').strip() != base and git(root, 'status', '--porcelain') == ''
    return root, base


def test_V02_S6_rename_committed_after_the_baseline_commit_on_a_clean_tree(tmp_path):
    root, base = history_repo(tmp_path)
    expected, _ = oracle_pairs(root, base, tmp_path)
    assert expected == [{'from': 'a.py', 'to': 'a_impl.py', 'similarity': 100}]
    assert detect(root, base) == {'status': 'applied', 'reason': None, 'pairs': expected}


def test_V02_S6_committed_rename_plus_one_uncommitted_rename(tmp_path):
    root, base = history_repo(tmp_path)
    (root / 'b.py').rename(root / 'b_impl.py')
    expected, _ = oracle_pairs(root, base, tmp_path)
    assert expected == [{'from': 'a.py', 'to': 'a_impl.py', 'similarity': 100}, {'from': 'b.py', 'to': 'b_impl.py', 'similarity': 100}]
    assert detect(root, base) == {'status': 'applied', 'reason': None, 'pairs': expected}


def boundary_repo(tmp_path, kept_lines):
    old = block('old', 100)
    root, commit = rename_repo(tmp_path, {'src/old.txt': old, 'keep.txt': block('keep')})
    git(root, 'mv', 'src/old.txt', 'src/new.txt')
    (root / 'src' / 'new.txt').write_text(old[:kept_lines * 20] + block('new', 100 - kept_lines), encoding='utf-8')
    return root, commit


def test_V03_B1_similarity_exactly_50_is_a_pair(tmp_path):
    root, commit = boundary_repo(tmp_path, 50)
    expected, listing = oracle_pairs(root, commit, tmp_path)
    assert listing.startswith('R050\t'), listing
    assert detect(root, commit) == {'status': 'applied', 'reason': None,
                                    'pairs': [{'from': 'src/old.txt', 'to': 'src/new.txt', 'similarity': 50}]}


def test_V03_B2_similarity_49_is_not_a_pair(tmp_path):
    root, commit = boundary_repo(tmp_path, 49)
    default_pairs, _ = oracle_pairs(root, commit, tmp_path)
    assert default_pairs == []
    lowered, listing = oracle_pairs(root, commit, tmp_path, threshold=40)
    assert listing.startswith('R049\t'), listing
    assert detect(root, commit) == {'status': 'applied', 'reason': None, 'pairs': []}



def test_V04_EP1_clean_repo_git_mv_leaves_state_unchanged(tmp_path):
    root, commit = rename_repo(tmp_path, {'a.py': block('sa'), 'keep.py': block('keep')})
    git(root, 'mv', 'a.py', 'a_impl.py')
    before = observations(root)
    result = detect(root, commit)
    assert result['pairs']
    assert observations(root) == before


def test_V04_EP2_untracked_new_file_leaves_state_unchanged(tmp_path):
    root, commit = rename_repo(tmp_path, {'a.py': block('sa'), 'keep.py': block('keep')})
    (root / 'a.py').rename(root / 'a_impl.py')
    (root / 'extra.txt').write_text(block('extra'), encoding='utf-8')
    before = observations(root)
    assert detect(root, commit)['pairs'] == [{'from': 'a.py', 'to': 'a_impl.py', 'similarity': 100}]
    assert observations(root) == before


def test_V04_EP3_commit_not_found_leaves_state_unchanged(tmp_path):
    root, _ = rename_repo(tmp_path, {'a.py': block('sa')})
    (root / 'a.py').rename(root / 'a_impl.py')
    before = observations(root)
    assert detect(root, MISSING_COMMIT) == skipped('commit_not_found')
    assert observations(root) == before



def mixed_pair():
    a, b, c = f('a.py'), f('b.py'), f('c.py')
    base = payload(candidates=[cycle([a, b]), internal_violation('b:v1', a, b),
                               gen('large_node', 'file:big.py', 'c1', {'line_count': 10, 'token_count': 5})],
                   package_dependencies={'language': [pdep('p', 'q')]}, package_metrics={'language': pmetrics({'pkg:x': 0.1})})
    cur = payload(candidates=[cycle([a, b, c]), internal_violation('b:v2', a, c),
                              gen('large_node', 'file:big.py', 'c1', {'line_count': 20, 'token_count': 5}),
                              gen('isolated_node', 'file:new.py', 'c2', {})],
                  package_dependencies={'language': [pdep('p', 'r')]}, package_metrics={'language': pmetrics({'pkg:x': 0.9})})
    return cur, base


def assert_skipped_delta(result, reason):
    assert result == skipped(reason)
    cur, base = mixed_pair()
    delta = compute(cur, base, result)
    assert delta['renames'] == skipped(reason)
    assert without_renames(delta) == without_renames(wire(ref_delta(cur, base)))


def test_V05_EP2_null_baseline_commit(repo):
    root, _ = repo
    assert_skipped_delta(detect(root, None), 'baseline_without_commit')


def test_V05_EP3_not_a_repository(tmp_path):
    write_files(tmp_path / 'plain', APP_FILES)
    assert_skipped_delta(detect(tmp_path / 'plain', MISSING_COMMIT), 'not_a_git_repository')


def test_V05_EP4_git_missing(repo, tmp_path, monkeypatch):
    root, commit = repo
    monkeypatch.setenv('PATH', empty_path_env(tmp_path / 'nobin')['PATH'])
    assert_skipped_delta(detect(root, commit), 'git_unavailable')


def test_V05_EP5_commit_absent_from_repository(repo, tmp_path):
    root, _ = repo
    assert_skipped_delta(detect(root, MISSING_COMMIT), 'commit_not_found')
    other = tmp_path / 'other'
    foreign = make_repo(other, {'z.py': block('zz')})
    assert_skipped_delta(detect(root, foreign), 'commit_not_found')


def test_V05_EP6_git_exits_non_zero_on_broken_repository_config(repo):
    root, commit = repo
    (root / '.git' / 'config').write_text('[core\n\tbare = = =\n', encoding='utf-8')
    assert_skipped_delta(detect(root, commit), 'git_failed')


@pytest.mark.parametrize('text', ['HEAD', 'BRANCH', '--output=x'], ids=['HEAD', 'branch-name', 'option-like'])
def test_V05_EP7_non_hex_commit_string_is_commit_not_found_and_creates_nothing(tmp_path, text):
    root, _ = rename_repo(tmp_path, {'a.py': block('sa'), 'keep.py': block('keep')})
    git(root, 'mv', 'a.py', 'a_impl.py')
    if text == 'BRANCH':
        text = git(root, 'branch', '--show-current').strip()
        assert text
    listing = lambda: (sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*') if '.git' not in p.relative_to(tmp_path).parts),
                       sorted(p.name for p in tmp_path.parent.iterdir()))
    before_files, before_state = listing(), observations(root)
    assert_skipped_delta(detect(root, text), 'commit_not_found')
    assert listing() == before_files and observations(root) == before_state


@pytest.fixture(params=['key-removed', 'dirty-baseline'])
def baseline_without_commit_case(request, tmp_path):
    root = tmp_path / 'repo'
    commit = make_repo(root, APP_FILES)
    if request.param == 'key-removed':
        done = run_cli(analysis_args(root, tmp_path / 'base'))
        assert done.returncode == 0, done.stderr[-1500:]
        path = tmp_path / 'base' / 'b.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        del data['snapshot']['git_commit'], data['snapshot']['git_commit_reason']
        path.write_text(json.dumps(data), encoding='utf-8')
    else:
        (root / 'app' / 'a.py').write_text(APP_FILES['app/a.py'] + '\n# edit\n', encoding='utf-8')
        done = run_cli(analysis_args(root, tmp_path / 'base'))
        assert done.returncode == 0, done.stderr[-1500:]
        assert snapshot_of(tmp_path / 'base' / 'b.json')['git_commit_reason'] == 'dirty'
        git(root, 'checkout', '--', 'app/a.py')
    return root, tmp_path / 'base' / 'b.json', commit


def test_V05_EP1_baseline_without_commit_key_or_null_through_the_cli(baseline_without_commit_case, tmp_path):
    root, baseline, _ = baseline_without_commit_case
    done = run_cli(analysis_args(root, tmp_path / 'out', '--baseline', baseline))
    assert done.returncode == 0, done.stderr[-1500:]
    delta = json.loads((tmp_path / 'out' / 'b.json').read_text(encoding='utf-8'))['delta']
    assert delta['renames'] == skipped('baseline_without_commit')



OLD, NEW, B, C = 'src/a.py', 'src/a_impl.py', 'src/b.py', 'src/c.py'
EV_OLD, EV_NEW = 'src/events/events.module.ts', 'src/events/events-impl.module.ts'
NEST_OLD, NEST_NEW = f'pkg:nestjs:{EV_OLD}#EventsModule', f'pkg:nestjs:{EV_NEW}#EventsModule'
RN = applied((OLD, NEW))
RN_EV = applied((EV_OLD, EV_NEW))


def sides(old_value, new_value, build):
    return build(new_value), build(old_value)


def test_V06_A1_B1_candidate_target_is_mapped():
    build = lambda path: payload([gen('large_node', f(path), 'b:1', {'line_count': 5, 'token_count': 9})])
    cur, base = sides(OLD, NEW, build)
    assert_quiet(compute(cur, base, RN))
    control = compute(cur, base, None)
    assert len(control['new_candidates']) == 1 and control['resolved']['candidates'] == 1


def test_V06_A1_B2_cycle_members_are_mapped():
    build = lambda path: payload([cycle([f(path), f(B), f(C)])])
    cur, base = sides(OLD, NEW, build)
    assert_quiet(compute(cur, base, RN))
    control = compute(cur, base, None)
    assert len(control['new_cycles']) + len(control['grown_cycles']) == 1


def test_V06_A1_B2_B3_growth_reports_only_pairs_not_already_in_the_mapped_baseline():
    base = payload([cycle([f(OLD), f(B)])])
    cur = payload([cycle([f(NEW), f(B), f(C)])])
    result = compute(cur, base, RN)
    assert result['new_cycles'] == []
    [grown] = result['grown_cycles']
    assert grown['added_members'] == [f(C)]
    assert grown['new_internal_pairs'] == [[f(B), f(C)], [f(C), f(NEW)]]


def boundary(node):
    return gen('unresolved_boundary', f(B), 'b:u', {'unresolved_count': 1}, evidence=boundary_evidence(node, names=['x']))


def test_V06_A1_B3_evidence_node_id_is_mapped():
    cur, base = payload([boundary(f(NEW))]), payload([boundary(f(OLD))])
    assert_quiet(compute(cur, base, RN))
    control = compute(cur, base, None)
    assert len(control['strengthened_candidates']) == 1


def test_V06_A1_B3_evidence_from_id_and_to_id_are_mapped():
    def build(path, other):
        item = gen('unresolved_boundary', f(B), 'b:u', {'unresolved_count': 1},
                   evidence=[{'from_id': f(path), 'to_id': f(other), 'relation': 'CALLS'}])
        return payload([item])
    assert_quiet(compute(build(NEW, C), build(OLD, C), RN))
    assert_quiet(compute(build(C, NEW), build(C, OLD), RN))
    assert len(compute(build(NEW, C), build(OLD, C), None)['strengthened_candidates']) == 1


def test_V06_A1_B4_package_dependency_ids_are_mapped():
    build = lambda path: payload(package_dependencies={'language': [pdep(f(path), f(B))]})
    cur, base = sides(OLD, NEW, build)
    assert_quiet(compute(cur, base, RN))
    control = compute(cur, base, None)
    assert len(control['new_package_dependencies']) == 1 and control['resolved']['package_dependencies'] == 1


def test_V06_A2_B4_framework_package_dependency_is_mapped():
    build = lambda ident: payload(package_dependencies={'framework': [pdep(ident, 'pkg:nestjs:src/app.module.ts#AppModule')]})
    cur, base = sides(NEST_OLD, NEST_NEW, build)
    assert_quiet(compute(cur, base, RN_EV))


def test_V06_A2_B5_package_metrics_key_is_mapped_so_an_instability_change_is_still_seen():
    cur = payload(package_metrics={'framework': pmetrics({NEST_NEW: 0.9})})
    base = payload(package_metrics={'framework': pmetrics({NEST_OLD: 0.1})})
    result = compute(cur, base, RN_EV)
    assert [(i['scheme'], i['package'], i['baseline'], i['current']) for i in result['instability_changes']] == [
        ('framework', NEST_NEW, 0.1, 0.9)]
    assert compute(cur, base, None)['instability_changes'] == []


@pytest.mark.parametrize('field', ['target', 'to_id'])
def test_V06_A1_B6_violation_target_and_evidence_are_mapped(field):
    if field == 'target':
        base = payload([internal_violation('b:v1', f(OLD), f(B))])
        cur = payload([internal_violation('b:v2', f(NEW), f(B))])
    else:
        base = payload([internal_violation('b:v1', f(B), f(OLD))])
        cur = payload([internal_violation('b:v2', f(B), f(NEW))])
    assert_quiet(compute(cur, base, RN))
    assert len(compute(cur, base, None)['new_violations']) == 1


def v9_cycle(file_ids, members, rows):
    data = payload([{'id': 'b:c', 'kind': 'dependency_cycle', 'structure': {'scheme': 'file', 'tier': 'all', 'members': sorted(members)},
                     'evidence': rows}])
    data['dependency_network']['file_ids'] = list(file_ids)
    return data


def test_V06_A1_B7_file_ids_are_mapped_for_index_pair_evidence():
    base = v9_cycle([f(OLD), f(B)], [f(OLD), f(B)], [[0, 1], [1, 0]])
    cur = v9_cycle([f(NEW), f(B), f(C)], [f(NEW), f(B), f(C)], [[0, 1], [1, 2], [2, 0]])
    result = compute(cur, base, RN)
    [grown] = result['grown_cycles']
    assert grown['new_internal_pairs'] == [[f(B), f(C)], [f(C), f(NEW)]]
    unmapped = compute(cur, base, None)
    assert unmapped['grown_cycles'][0]['new_internal_pairs'] != grown['new_internal_pairs']


def unstable(to_package):
    return gen('unstable_dependency', 'pkg:nestjs:src/x.module.ts#X', 'b:s', {'file_pair_count': 1},
               structure={'from_package': 'pkg:nestjs:src/x.module.ts#X', 'to_package': to_package, 'tier': 'all'})


def test_V06_A2_B8_general_candidate_structure_string_is_mapped():
    cur, base = payload([unstable(NEST_NEW)]), payload([unstable(NEST_OLD)])
    assert_quiet(compute(cur, base, RN_EV))
    assert len(compute(cur, base, None)['new_candidates']) == 1


@pytest.mark.parametrize('old_id, new_id', [
    ('file:x/src/a.py', 'file:x/src/a_impl.py'),
    ('file:src/a.py.bak', 'file:src/a_impl.py.bak'),
    ('file:y_src/a.py', 'file:y_src/a_impl.py'),
], ids=['inside-longer-path', 'longer-suffix', 'longer-prefix'])
def test_V06_A3_boundary_mismatch_is_not_mapped(old_id, new_id):
    build = lambda ident: payload([gen('large_node', ident, 'b:1', {'line_count': 5, 'token_count': 9})])
    result = compute(build(new_id), build(old_id), RN)
    assert len(result['new_candidates']) == 1 and result['new_candidates'][0]['target'] == new_id
    assert result['resolved']['candidates'] == 1


def py_boundary(node):
    return gen('unresolved_boundary', f(B), 'b:u', {'unresolved_count': 1},
               evidence=boundary_evidence(node, names=['x'], flags=['dynamic_attr']))


@pytest.mark.parametrize('pair, old_id, new_id', [
    (('pkg/users.py', 'pkg/users_impl.py'), 'py:pkg.users#listing', 'py:pkg.users_impl#listing'),
    (('pkg/users.py', 'pkg/users_impl.py'), 'py:pkg.users', 'py:pkg.users_impl'),
    (('pkg/__init__.py', 'pkg2/__init__.py'), 'py:pkg#create_app', 'py:pkg2#create_app'),
    (('pkg/__init__.py', 'pkg2/__init__.py'), 'py:pkg', 'py:pkg2'),
], ids=['qualname', 'bare-module', 'package-init-qualname', 'package-init-bare'])
def test_V06_A5_python_symbol_ids_follow_the_module_name_of_a_renamed_file(pair, old_id, new_id):
    cur, base = payload([py_boundary(new_id)]), payload([py_boundary(old_id)])
    assert_quiet(compute(cur, base, applied(pair)))
    control = compute(cur, base, None)
    assert len(control['strengthened_candidates']) == 1 and control['new_candidates'] == []


@pytest.mark.parametrize('old_id, wrong_new_id', [
    ('py:pkg.users_x#f', 'py:pkg.users_impl_x#f'),
    ('py:pkg.users.sub#f', 'py:pkg.users_impl.sub#f'),
    ('pyx:pkg.users#f', 'pyx:pkg.users_impl#f'),
], ids=['longer-module-name', 'submodule', 'other-prefix'])
def test_V06_A6_python_id_boundary_mismatch_is_not_mapped(old_id, wrong_new_id):
    cur, base = payload([py_boundary(wrong_new_id)]), payload([py_boundary(old_id)])
    result = compute(cur, base, applied(('pkg/users.py', 'pkg/users_impl.py')))
    assert len(result['strengthened_candidates']) == 1 and result['new_candidates'] == []
    assert result['strengthened_candidates'][0]['added_evidence']


def test_V06_A4_path_free_package_ids_are_not_mapped_when_a_file_changes_directory():
    moved = applied(('src/a.py', 'lib/a.py'))
    base = payload([gen('large_node', 'file:src/a.py', 'b:1', {'line_count': 5, 'token_count': 9})],
                   package_dependencies={'language': [pdep('pkg:dir:src', 'pkg:dir:core'), pdep('pkg:python:src', 'pkg:python:core')]})
    cur = payload([gen('large_node', 'file:lib/a.py', 'b:1', {'line_count': 5, 'token_count': 9})],
                  package_dependencies={'language': [pdep('pkg:dir:lib', 'pkg:dir:core'), pdep('pkg:python:lib', 'pkg:python:core')]})
    result = compute(cur, base, moved)
    assert result['new_candidates'] == [] and result['strengthened_candidates'] == []
    assert [(i['from_id'], i['to_id']) for i in result['new_package_dependencies']] == [
        ('pkg:dir:lib', 'pkg:dir:core'), ('pkg:python:lib', 'pkg:python:core')]
    assert result['resolved']['package_dependencies'] == 2


def test_V06_C05_nestjs_module_rename_leaves_dependencies_metrics_and_candidates_quiet():
    def build(ident):
        return payload([unstable(ident)], package_dependencies={'framework': [pdep(ident, 'pkg:nestjs:src/app.module.ts#AppModule')]},
                       package_metrics={'framework': pmetrics({ident: 0.5})})
    result = compute(build(NEST_NEW), build(NEST_OLD), RN_EV)
    assert_quiet(result)
    assert result['new_package_dependencies'] == [] and result['new_candidates'] == [] and result['instability_changes'] == []


def package_cycle(ident, other='pkg:nestjs:src/app.module.ts#AppModule', rows=False):
    members = sorted([ident, other])
    if rows:
        evidence = [[members[0], members[1], 'all'], [members[1], members[0], 'all']]
        return {'id': 'b:pc', 'kind': 'package_cycle', 'structure': {'scheme': 'framework', 'tier': 'all', 'members': members},
                'evidence': evidence}
    return cycle(members, kind='package_cycle', scheme='framework', ident='b:pc')


@pytest.mark.parametrize('rows', [False, True], ids=['evidence-records', 'evidence-rows'])
def test_V06_A2_B9_package_cycle_members_and_evidence_rows_are_mapped(rows):
    cur = payload([package_cycle(NEST_NEW, rows=rows)])
    base = payload([package_cycle(NEST_OLD, rows=rows)])
    if rows:
        for data in (cur, base):
            data['schema'] = 'bottlenecks.v9'
            data['dependency_network']['file_ids'] = [f(B), f(C)]
    result = compute(cur, base, RN_EV)
    assert result['new_cycles'] == [] and result['grown_cycles'] == [] and result['resolved']['cycles'] == 0
    assert_quiet(result)
    control = compute(cur, base, None)
    assert len(control['new_cycles']) + len(control['grown_cycles']) == 1



def test_V07_M1_no_renames_argument_equals_the_v2_reference_with_v3_policy():
    cur, base = mixed_pair()
    for result in (wire(delta_api().compute_delta(cur, base)), wire(delta_api().compute_delta(cur, base, None))):
        assert result == wire(ref_delta(cur, base))
        assert result['policy'] == 'delta.v5'
        assert result['renames'] == NOT_REQUESTED == {'status': 'skipped', 'reason': 'not_requested', 'pairs': []}
        assert set(result) == DELTA_KEYS
        assert result['counts'] == {'new_cycles': 0, 'grown_cycles': 1, 'new_violations': 1, 'new_package_dependencies': 1,
                                    'instability_changes': 1, 'new_candidates': 1, 'strengthened_candidates': 1,
                                    'changed_signatures': 0, 'removed_symbols': 0, 'untested_changes': 0, 'weakened_tests': 0, 'added_mocks': 0}


def test_V07_M2_applied_with_empty_pairs_changes_nothing_but_the_renames_object():
    cur, base = mixed_pair()
    renames = {'status': 'applied', 'reason': None, 'pairs': []}
    result = compute(cur, base, renames)
    assert result['renames'] == renames and result['policy'] == 'delta.v5'
    assert without_renames(result) == without_renames(compute(cur, base, None))


@pytest.mark.parametrize('reason', ['baseline_without_commit', 'not_a_git_repository', 'git_unavailable', 'commit_not_found',
                                    'git_failed'])
def test_V07_M3_skipped_renames_are_echoed_and_do_not_change_the_comparison(reason):
    cur, base = mixed_pair()
    result = compute(cur, base, skipped(reason))
    assert result['renames'] == skipped(reason) and result['policy'] == 'delta.v5'
    assert without_renames(result) == without_renames(compute(cur, base, None))



def test_V08_D1_same_five_fields_with_different_ids_is_not_new():
    base = payload([internal_violation('b:old', f(OLD), f(B))])
    cur = payload([internal_violation('b:new', f(OLD), f(B))])
    result = compute(cur, base, None)
    assert result['new_violations'] == [] and result['resolved']['violations'] == 0


def test_V08_D1_same_five_fields_after_the_rename_is_not_new():
    base = payload([internal_violation('b:old', f(OLD), f(B))])
    cur = payload([internal_violation('b:new', f(NEW), f(B))])
    result = compute(cur, base, RN)
    assert result['new_violations'] == [] and result['resolved']['violations'] == 0


def test_V08_D2_only_the_target_differs_with_the_same_id():
    base = payload([internal_violation('b:v1', f(OLD), f(B))])
    cur = payload([internal_violation('b:v1', f(C), f(B))])
    result = compute(cur, base, None)
    assert [(i['candidate_id'], i['target']) for i in result['new_violations']] == [('b:v1', f(C))]
    assert result['resolved']['violations'] == 1


def test_V08_D3_only_the_to_id_differs_with_the_same_id():
    base = payload([internal_violation('b:v1', f(OLD), f(B))])
    cur = payload([internal_violation('b:v1', f(OLD), f(C))])
    result = compute(cur, base, None)
    assert [(i['candidate_id'], i['to_id']) for i in result['new_violations']] == [('b:v1', f(C))]
    assert result['resolved']['violations'] == 1


def test_V08_D4_external_violation_equal_in_content_is_not_new():
    base = payload([external_violation('b:e-old', f(OLD), 'requests')])
    cur = payload([external_violation('b:e-new', f(OLD), 'requests')])
    result = compute(cur, base, None)
    assert result['new_violations'] == [] and result['resolved']['violations'] == 0


@pytest.mark.parametrize('name, base_kwargs, cur_kwargs', [
    ('D5-rule_type', {'rule_type': 'allow'}, {'rule_type': 'forbid'}),
    ('D6-from_layer', {'from_layer': 'db'}, {'from_layer': 'svc'}),
    ('D7-to_layer', {'to_layer': 'api'}, {'to_layer': 'web'}),
], ids=['D5-rule_type', 'D6-from_layer', 'D7-to_layer'])
def test_V08_D5_D6_D7_a_single_differing_structure_field_with_the_same_id_is_new(name, base_kwargs, cur_kwargs):
    base = payload([internal_violation('b:v1', f(OLD), f(B), **base_kwargs)])
    cur = payload([internal_violation('b:v1', f(OLD), f(B), **cur_kwargs)])
    result = compute(cur, base, None)
    assert [i['candidate_id'] for i in result['new_violations']] == ['b:v1']
    assert result['resolved']['violations'] == 1


def test_V08_D8_only_the_external_name_differs_with_the_same_id_and_target():
    base = payload([external_violation('b:e1', f(OLD), 'requests')])
    cur = payload([external_violation('b:e1', f(OLD), 'boto3')])
    result = compute(cur, base, None)
    assert [(i['candidate_id'], i['to_external']) for i in result['new_violations']] == [('b:e1', 'boto3')]
    assert result['resolved']['violations'] == 1



def out_json(directory):
    return json.loads((Path(directory) / 'b.json').read_text(encoding='utf-8'))


def renames_lines(done):
    return ([line for line in done.stdout.splitlines() if line.startswith('[Δ] Renames applied')],
            [line for line in done.stderr.splitlines() if 'renames not detected' in line])


def baseline_run(root, directory):
    done = run_cli(analysis_args(root, directory))
    assert done.returncode == 0, done.stderr[-1500:]
    return Path(directory) / 'b.json'


@pytest.mark.parametrize('moves', [['a'], ['a', 'd']], ids=['one-rename', 'two-renames'])
def test_V09_EP1_C18_rename_after_baseline_is_applied_and_reports_nothing(tmp_path, moves):
    root = tmp_path / 'repo'
    commit = make_repo(root, APP_FILES)
    baseline = baseline_run(root, tmp_path / 'base')
    assert snapshot_of(baseline)['git_commit'] == commit
    move_a_to_a_impl(root)
    if 'd' in moves:
        git(root, 'mv', 'app/d.py', 'app/d_impl.py')
    done = run_cli(analysis_args(root, tmp_path / 'out', '--baseline', baseline, '--fail-on-new', 'any'))
    assert done.returncode == 0, done.stderr[-1500:]
    delta = out_json(tmp_path / 'out')['delta']
    expected_pairs = [{'from': 'app/a.py', 'to': 'app/a_impl.py', 'similarity': 100}]
    if 'd' in moves:
        expected_pairs.append({'from': 'app/d.py', 'to': 'app/d_impl.py', 'similarity': 100})
    assert delta['renames'] == {'status': 'applied', 'reason': None, 'pairs': expected_pairs}
    assert_quiet(delta)
    assert all(count == 0 for count in delta['counts'].values())
    assert renames_lines(done) == ([f'[Δ] Renames applied: {len(moves)}'], [])
    assert SUMMARY.format(0, 0, 0, 0, 0, 0, 0) in done.stdout.splitlines()
    assert git(root, 'rev-parse', 'HEAD').strip() == commit


def test_V09_EP2_applied_without_pairs_prints_neither_line(clean_cli_project, tmp_path):
    root, _, baseline = clean_cli_project
    done = run_cli(analysis_args(root, tmp_path / 'out', '--baseline', baseline))
    assert done.returncode == 0, done.stderr[-1500:]
    assert out_json(tmp_path / 'out')['delta']['renames'] == {'status': 'applied', 'reason': None, 'pairs': []}
    assert renames_lines(done) == ([], [])


@pytest.mark.parametrize('extra, code', [([], 0), (['--fail-on-new', 'cycle'], 3)], ids=['no-regression', 'new-cycle'])
def test_V09_EP3_skipped_baseline_without_commit_warns_once_and_keeps_the_exit_code(baseline_without_commit_case, tmp_path, extra, code):
    root, baseline, _ = baseline_without_commit_case
    if extra:
        write_files(root, {'app/e.py': 'from app.f import ff\n\n\ndef fe():\n    return ff()\n',
                           'app/f.py': 'from app.e import fe\n\n\ndef ff():\n    return fe()\n'})
        git(root, 'add', '-A')
        git(root, 'commit', '-q', '-m', 'cycle')
    done = run_cli(analysis_args(root, tmp_path / 'out', '--baseline', baseline, *extra))
    assert done.returncode == code, done.stderr[-1500:]
    assert renames_lines(done) == ([], [RENAMES_WARNING.format('baseline_without_commit')])
    assert out_json(tmp_path / 'out')['delta']['renames'] == skipped('baseline_without_commit')


def test_V09_EP4_no_baseline_prints_neither_line(tmp_path):
    root = tmp_path / 'repo'
    make_repo(root, APP_FILES)
    done = run_cli(analysis_args(root, tmp_path / 'out'))
    assert done.returncode == 0, done.stderr[-1500:]
    assert renames_lines(done) == ([], [])
    assert 'delta' not in out_json(tmp_path / 'out')


def test_V05_C09_cli_without_git_on_path_reports_git_unavailable_and_exits_normally(clean_cli_project, tmp_path):
    root, _, baseline = clean_cli_project
    done = run_cli(analysis_args(root, tmp_path / 'out', '--baseline', baseline), env=empty_path_env(tmp_path / 'nobin'))
    assert done.returncode == 0, done.stderr[-1500:]
    assert 'Traceback' not in done.stderr
    assert out_json(tmp_path / 'out')['delta']['renames'] == skipped('git_unavailable')
    assert renames_lines(done) == ([], [RENAMES_WARNING.format('git_unavailable')])


def test_V05_C08_cli_baseline_commit_from_another_repository(clean_cli_project, tmp_path):
    root, _, baseline = clean_cli_project
    foreign = make_repo(tmp_path / 'other', {'z.py': block('zz')})
    data = json.loads(baseline.read_text(encoding='utf-8'))
    data['snapshot']['git_commit'] = foreign
    changed = tmp_path / 'foreign.json'
    changed.write_text(json.dumps(data), encoding='utf-8')
    done = run_cli(analysis_args(root, tmp_path / 'out', '--baseline', changed))
    assert done.returncode == 0, done.stderr[-1500:]
    assert out_json(tmp_path / 'out')['delta']['renames'] == skipped('commit_not_found')
    assert renames_lines(done) == ([], [RENAMES_WARNING.format('commit_not_found')])


def test_V02_S6_cli_rename_committed_after_the_baseline_is_applied(tmp_path):
    root = tmp_path / 'repo'
    base = make_repo(root, APP_FILES)
    baseline = baseline_run(root, tmp_path / 'base')
    assert snapshot_of(baseline)['git_commit'] == base
    move_a_to_a_impl(root)
    git(root, 'add', '-A')
    git(root, 'commit', '-q', '-m', 'rename')
    done = run_cli(analysis_args(root, tmp_path / 'out', '--baseline', baseline, '--fail-on-new', 'any'))
    assert done.returncode == 0, done.stderr[-1500:]
    delta = out_json(tmp_path / 'out')['delta']
    assert delta['renames'] == {'status': 'applied', 'reason': None,
                                'pairs': [{'from': 'app/a.py', 'to': 'app/a_impl.py', 'similarity': 100}]}
    assert_quiet(delta)
    assert all(count == 0 for count in delta['counts'].values())
    assert renames_lines(done) == (['[Δ] Renames applied: 1'], [])



def baseline_file(tmp_path, **snapshot):
    data = payload()
    data['snapshot'].update(snapshot)
    path = tmp_path / 'baseline.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return path


@pytest.mark.parametrize('case', ['string', 'null', 'absent'])
def test_V10_EP1_EP2_EP3_accepted_git_commit_values(tmp_path, case):
    values = {'string': {'git_commit': 'a' * 40}, 'null': {'git_commit': None}, 'absent': {}}[case]
    loaded = delta_api().load_baseline(baseline_file(tmp_path, **values))
    assert loaded['snapshot'].get('git_commit') == values.get('git_commit')


@pytest.mark.parametrize('value', [7, ['a' * 40]], ids=['EP4-integer', 'EP5-list'])
def test_V10_EP4_EP5_non_string_git_commit_is_a_baseline_error(tmp_path, value):
    path = baseline_file(tmp_path, git_commit=value)
    with pytest.raises(delta_api().BaselineError) as raised:
        delta_api().load_baseline(path)
    assert str(raised.value).startswith(f'baseline {path}: ') and '$.snapshot.git_commit' in str(raised.value)


def test_V10_C19_cli_exits_1_without_output_for_an_integer_git_commit(clean_cli_project, tmp_path):
    root, _, baseline = clean_cli_project
    data = json.loads(baseline.read_text(encoding='utf-8'))
    data['snapshot']['git_commit'] = 7
    changed = tmp_path / 'int.json'
    changed.write_text(json.dumps(data), encoding='utf-8')
    done = run_cli(analysis_args(root, tmp_path / 'out', '--baseline', changed))
    assert done.returncode == 1
    errors = [line for line in done.stderr.splitlines() if line.startswith('[!]')]
    assert len(errors) == 1 and '$.snapshot.git_commit' in errors[0]
    assert not (tmp_path / 'out' / 'b.json').exists() and not (tmp_path / 'out' / 'r.html').exists()
