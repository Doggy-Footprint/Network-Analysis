"""Expected module ids, package ids and edge tuples are written out by hand from the spec Signatures and the synthetic
repositories below. V10 compares against goldens produced by the base commit (see build_modules_evidence/README-free
generation procedure in the V10 test docstring)."""
import json

import pytest

from tests.build_modules_support import (BASE_COMMIT, EVIDENCE, by_kind, declared_edges, edge_view, enriched, file_architecture, gid,
                                         gpkg, module_ids, module_nodes, nid, node_by_id, npkg, pairs_of, run_cli, value,
                                         write_repo)
from tests.structure_support import cycle_id, default_weights, unstable_id

BUILD = 'plugins {}\n'
EXTRA_SPAN_KEYS = ('line_number', 'end_line_number')   # added to every spanned node by enrichment; the spec metadata lists neither
ROOT_G = gid(':')


def pj(name=None, **extra):
    data = dict(extra)
    if name is not None:
        data = {'name': name, **data}
    return json.dumps(data)


def span_of(node):
    return None if node.span is None else (node.span.file_path, node.span.start_line, node.span.end_line)


def gradle_ids(files):
    return module_ids(enriched(files), 'gradle')


def npm_ids(files):
    return module_ids(enriched(files), 'npm')


V1_CASES = {
    'kts-single-arg': ({'settings.gradle.kts': 'include(":app")\n'}, {':', ':app'}),
    'kts-multi-arg': ({'settings.gradle.kts': 'include(":core:data", ":core:model")\n'}, {':', ':core:data', ':core:model'}),
    'groovy-space-call': ({'settings.gradle': "include ':a', ':b'\n"}, {':', ':a', ':b'}),
    'no-leading-colon': ({'settings.gradle.kts': 'include("a:b")\n'}, {':', ':a:b'}),
    'line-comment': ({'settings.gradle.kts': '// include(":x")\ninclude(":y")\n'}, {':', ':y'}),
    'block-comment': ({'settings.gradle.kts': '/* include(":x") */\ninclude(":y")\n/*\ninclude(":z")\n*/\n'}, {':', ':y'}),
}


@pytest.mark.parametrize('files, expected', V1_CASES.values(), ids=V1_CASES.keys())
def test_V1_settings_syntax_partitions_give_exact_module_set(files, expected):
    assert gradle_ids(files) == {gid(path) for path in expected}


def test_V1_module_dir_replaces_colons_with_slashes():
    arch = enriched({'settings.gradle.kts': 'include(":core:data", ":app")\n'})
    dirs = {node.id: node.metadata['module_dir'] for node in module_nodes(arch)}
    assert dirs == {gid(':'): '', gid(':app'): 'app', gid(':core:data'): 'core/data'}


N1_FILES = {
    'settings.gradle.kts': 'include(":app")\ninclude(":core:data", ":core:model")\n',
    'app/build.gradle.kts': 'plugins {}\ndependencies {\n    // note\n    implementation(project(":core:data"))\n}\n',
    'core/data/build.gradle.kts': 'plugins {}\ndependencies {\n    // note\n    implementation(projects.core.model)\n}\n',
    'core/model/build.gradle.kts': BUILD,
    'app/src/A.kt': 'class A\n',
    'core/data/src/D.kt': 'class D\n',
    'core/model/src/M.kt': 'class M\n',
}


def test_N1_modules_and_declared_edges_are_exact():
    arch = enriched(N1_FILES)
    assert module_ids(arch) == {gid(p) for p in (':', ':app', ':core:data', ':core:model')}
    assert edge_view(arch) == {
        (gid(':app'), gid(':core:data'), 'exact', 'implementation', 'app/build.gradle.kts', 4, 4),
        (gid(':core:data'), gid(':core:model'), 'exact', 'implementation', 'core/data/build.gradle.kts', 4, 4)}
    for edge in declared_edges(arch):
        assert value(edge.confidence) == 'static_certain'


def test_Signature_gradle_module_node_fields():
    arch = enriched(N1_FILES)
    node = node_by_id(arch, gid(':core:data'))
    assert (node.kind, node.category, node.group, node.language, node.provenance) == (
        'module', 'configuration', 'configuration', 'configuration', 'gradle')
    assert {k: v for k, v in node.metadata.items() if k not in EXTRA_SPAN_KEYS} == {
        'build_system': 'gradle', 'module_path': ':core:data', 'module_dir': 'core/data', 'file_path': 'core/data/build.gradle.kts'}
    assert span_of(node) == ('core/data/build.gradle.kts', 1, 1)
    assert node.cost is not None
    root = node_by_id(arch, ROOT_G)
    assert span_of(root) is None and root.metadata['module_dir'] == '' and root.metadata['module_path'] == ':'
    assert 'file_path' not in root.metadata


def test_Signature_kts_preferred_over_groovy_build_file():
    arch = enriched({'settings.gradle.kts': 'include(":a")\n', 'a/build.gradle': BUILD, 'a/build.gradle.kts': BUILD})
    node = node_by_id(arch, gid(':a'))
    assert span_of(node) == ('a/build.gradle.kts', 1, 1) and node.metadata['file_path'] == 'a/build.gradle.kts'


def test_N2_groovy_settings_and_api_project_edge():
    files = {'settings.gradle': "include ':a', ':b'\n", 'a/build.gradle': "dependencies {\n    api project(':b')\n}\n",
             'b/build.gradle': 'apply plugin: "java"\n'}
    arch = enriched(files)
    assert module_ids(arch, 'gradle') == {gid(':'), gid(':a'), gid(':b')}
    assert edge_view(arch) == {(gid(':a'), gid(':b'), 'exact', 'api', 'a/build.gradle', 2, 2)}


V2_ROWS = {
    'settings+root-build': ({'settings.gradle.kts': 'include(":a")\n', 'build.gradle.kts': BUILD, 'a/build.gradle.kts': BUILD,
                             'b/build.gradle.kts': BUILD}, {':', ':a'}),
    'settings-only': ({'settings.gradle.kts': 'include(":a")\n', 'a/build.gradle.kts': BUILD, 'b/build.gradle.kts': BUILD},
                      {':', ':a'}),
    'root-build-only': ({'build.gradle.kts': BUILD, 'core/data/build.gradle.kts': BUILD}, {':', ':core:data'}),
    'neither-N3': ({'core/data/build.gradle.kts': BUILD, 'feature/topic/impl/build.gradle.kts': BUILD, 'docs/x.md': 'x\n'},
                   {':core:data', ':feature:topic:impl'}),
}


@pytest.mark.parametrize('files, expected', V2_ROWS.values(), ids=V2_ROWS.keys())
def test_V2_settings_by_root_build_decision_table(files, expected):
    assert gradle_ids(files) == {gid(path) for path in expected}


def test_V2_fallback_other_directories_are_unassigned_and_no_root_module():
    files = {'core/data/build.gradle.kts': BUILD, 'feature/topic/impl/build.gradle.kts': BUILD,
             'core/data/D.kt': 'class D\n', 'docs/Other.kt': 'class O\n'}
    _snap, arch = file_architecture(files, ['core/data/D.kt', 'docs/Other.kt'])
    from analysis.structure import analyze_structure, package_assignments
    assigned = {f: v for f, v in package_assignments(arch)['build'].items() if v}
    assert assigned == {'file:core/data/build.gradle.kts': [gpkg(':core:data')], 'file:core/data/D.kt': [gpkg(':core:data')],
                        'file:feature/topic/impl/build.gradle.kts': [gpkg(':feature:topic:impl')]}
    build = analyze_structure(arch, default_weights()).coverage['structure']['schemes']['build']
    assert build['unassigned_files'] == ['file:docs/Other.kt'] and build['unassigned_file_count'] == 1


@pytest.fixture(scope='module')
def nowinandroid():
    from fixtures.registry import fixture_root
    root = fixture_root('android-nowinandroid').resolve()
    files = {}
    for path in root.rglob('*'):
        if path.is_file() and '.git' not in path.relative_to(root).parts and path.name in (
                'build.gradle.kts', 'build.gradle', 'settings.gradle.kts', 'settings.gradle', 'package.json'):
            files[path.relative_to(root).as_posix()] = path.read_text(encoding='utf-8')
    return root, files


NOWINANDROID_MODULES = {':core:data', ':core:database', ':feature:topic:api', ':feature:topic:impl'}


def test_V2_G3_nowinandroid_fixture_fallback_modules_and_declared_edges(nowinandroid):
    _root, files = nowinandroid
    assert set(files) == {'core/data/build.gradle.kts', 'core/database/build.gradle.kts', 'feature/topic/api/build.gradle.kts',
                          'feature/topic/impl/build.gradle.kts'}
    arch = enriched(files)
    assert module_ids(arch, 'gradle') - {n.id for n in arch.nodes if 'module_dir' not in n.metadata} == {
        gid(path) for path in NOWINANDROID_MODULES}
    unresolved = lambda accessor: gid(accessor)
    impl, data, database = 'feature/topic/impl/build.gradle.kts', 'core/data/build.gradle.kts', 'core/database/build.gradle.kts'
    # expected tuples are read off the fixture build files (grep -n 'project'): line, configuration, accessor
    assert edge_view(arch) == {
        (gid(':feature:topic:impl'), gid(':core:data'), 'exact', 'implementation', impl, 28, 28),
        (gid(':feature:topic:impl'), gid(':feature:topic:api'), 'exact', 'implementation', impl, 29, 29),
        (gid(':feature:topic:impl'), unresolved('projects.core.testing'), 'unresolved', 'testImplementation', impl, 33, 33),
        (gid(':feature:topic:impl'), unresolved('projects.core.testing'), 'unresolved', 'androidTestImplementation', impl, 37, 37),
        (gid(':core:data'), unresolved('projects.core.common'), 'unresolved', 'api', data, 29, 29),
        (gid(':core:data'), gid(':core:database'), 'exact', 'api', data, 30, 30),
        (gid(':core:data'), unresolved('projects.core.datastore'), 'unresolved', 'api', data, 31, 31),
        (gid(':core:data'), unresolved('projects.core.network'), 'unresolved', 'api', data, 32, 32),
        (gid(':core:data'), unresolved('projects.core.analytics'), 'unresolved', 'implementation', data, 34, 34),
        (gid(':core:data'), unresolved('projects.core.notifications'), 'unresolved', 'implementation', data, 35, 35),
        (gid(':core:data'), unresolved('projects.core.datastoreTest'), 'unresolved', 'testImplementation', data, 39, 39),
        (gid(':core:data'), unresolved('projects.core.testing'), 'unresolved', 'testImplementation', data, 40, 40),
        (gid(':core:database'), unresolved('projects.core.model'), 'unresolved', 'api', database, 29, 29)}


def test_V2_G3_nowinandroid_fixture_cli_computes_build_scheme(nowinandroid, tmp_path):
    root, _files = nowinandroid
    _done, payload, _report = run_cli(root, tmp_path, '-l', 'kotlin')
    metrics = payload['dependency_network']['package_metrics']['build']
    assert set(metrics) == {gpkg(path) for path in NOWINANDROID_MODULES}
    build = payload['coverage']['structure']['schemes']['build']
    assert not any(path.startswith(('file:core/data/', 'file:core/database/', 'file:feature/topic/')) for path in build['unassigned_files'])
    assert build['assigned_file_count'] > 0 and build['shared_file_count'] == 0


def pkg_json(name=None, **extra):
    return pj(name, **extra)


def workspace_files(workspaces, packages, root_extra=None):
    files = {'package.json': json.dumps({**(root_extra or {}), 'workspaces': workspaces}) if workspaces is not None else '{}'}
    files.update(packages)
    return files


V3_CASES = {
    'format-array': (workspace_files(['packages/*'], {'packages/a/package.json': pj('a'), 'packages/b/package.json': pj('b')}),
                     {'(root)', 'a', 'b'}),
    'format-object': (workspace_files({'packages': ['packages/*']}, {'packages/a/package.json': pj('a'), 'packages/b/package.json': pj('b')}),
                      {'(root)', 'a', 'b'}),
    'format-broken-json': ({'package.json': '{"workspaces": [', 'packages/a/package.json': pj('a')}, set()),
    'format-unsupported-type': ({'package.json': '{"workspaces": "packages/*"}', 'packages/a/package.json': pj('a')}, set()),
    'glob-single-star': (workspace_files(['packages/*'], {'packages/a/package.json': pj('a'), 'packages/a/deep/package.json': pj('deep'),
                                                          'other/c/package.json': pj('c')}), {'(root)', 'a'}),
    'glob-double-star': (workspace_files(['libs/**'], {'libs/x/y/package.json': pj('y'), 'libs/x/package.json': pj('x'),
                                                       'libs/package.json': pj('libs-root'), 'other/z/package.json': pj('z')}),
                         {'(root)', 'y', 'x', 'libs-root'}),
    'glob-negation': (workspace_files(['packages/*', '!packages/b'], {'packages/a/package.json': pj('a'), 'packages/b/package.json': pj('b'),
                                                                    'packages/c/package.json': pj('c')}), {'(root)', 'a', 'c'}),
    'name-present': (workspace_files(['packages/*'], {'packages/a/package.json': pj('@x/a')}), {'(root)', '@x/a'}),
    'name-absent': (workspace_files(['packages/*'], {'packages/c/package.json': '{}'}), {'(root)', 'packages/c'}),
    'name-duplicate': (workspace_files(['packages/*'], {'packages/a/package.json': pj('dup'), 'packages/b/package.json': pj('dup')}),
                       {'(root)', 'dup', 'packages/b'}),
}


@pytest.mark.parametrize('files, expected', V3_CASES.values(), ids=V3_CASES.keys())
def test_V3_workspace_partitions_give_exact_npm_module_set(files, expected):
    assert npm_ids(files) == {nid(name) for name in expected}


def test_V3_N5_double_star_nested_directory_is_a_module():
    files = workspace_files({'packages': ['libs/**']}, {'libs/x/y/package.json': pj()})
    assert npm_ids(files) == {nid('(root)'), nid('libs/x/y')}


def test_V3_root_with_name_uses_its_name():
    assert npm_ids(workspace_files(['p/*'], {'p/a/package.json': pj('a')}, root_extra={'name': 'mono'})) == {nid('mono'), nid('a')}


def test_V3_E5_duplicate_name_goes_to_lexicographically_first_directory_regardless_of_input_order():
    files = workspace_files(['packages/*'], {'packages/z/package.json': pj('dup'), 'packages/b/package.json': pj('dup'),
                                             'packages/m/package.json': pj('dup')})
    arch = enriched(files)
    assert module_ids(arch, 'npm') == {nid('(root)'), nid('dup'), nid('packages/m'), nid('packages/z')}
    assert node_by_id(arch, nid('dup')).metadata['module_dir'] == 'packages/b'


def test_Signature_npm_module_node_fields():
    files = workspace_files(['packages/*'], {'packages/a/package.json': pj('@x/a')})
    arch = enriched(files)
    node = node_by_id(arch, nid('@x/a'))
    assert (node.kind, node.category, node.group, node.language, node.provenance) == (
        'module', 'configuration', 'configuration', 'configuration', 'npm-workspace')
    assert {k: v for k, v in node.metadata.items() if k not in EXTRA_SPAN_KEYS} == {
        'build_system': 'npm', 'module_path': '@x/a', 'module_dir': 'packages/a', 'file_path': 'packages/a/package.json'}
    assert span_of(node) == ('packages/a/package.json', 1, 1) and node.cost is not None
    root = node_by_id(arch, nid('(root)'))
    assert root.metadata['module_dir'] == '' and span_of(root) == ('package.json', 1, 1)


V4_BUILD = '\n'.join([
    'dependencies {',                                       # 1
    '    implementation(project(":lib"))',                  # 2  project(":x")
    '    api(project(path = ":core:model"))',               # 3  project(path = ":x")
    '    implementation(projects.util)',                    # 4  accessor simple
    '    implementation(projects.core.dataTest)',           # 5  accessor kebab -> camel
    '    implementation(projects.feature.myMod)',           # 6  accessor snake -> camel
    '    implementation(project(":missing"))',             # 7  unresolved project
    '    implementation(projects.nope)',                    # 8  unresolved accessor
    '    // implementation(project(":ignored1"))',          # 9  comment
    '    testImplementation(project(":lib"))',              # 10 other configuration
    '    implementation(project(":lib"))',                  # 11 repeated configuration
    '    /* project(":ignored2") */',                       # 12 block comment
    '    implementation(project(":ghost"))',                # 13 included, directory absent
    '}', ''])
V4_FILES = {
    'settings.gradle.kts': 'include(":app", ":lib", ":util", ":core:model", ":core:data-test", ":feature:my_mod", ":ghost")\n',
    'app/build.gradle.kts': V4_BUILD, 'lib/build.gradle.kts': BUILD, 'util/build.gradle.kts': BUILD, 'core/model/build.gradle.kts': BUILD,
    'core/data-test/build.gradle.kts': BUILD, 'feature/my_mod/build.gradle.kts': BUILD,
}


def test_V4_B5_reference_forms_and_configuration_split_give_exact_edges():
    app, f = gid(':app'), 'app/build.gradle.kts'
    assert edge_view(enriched(V4_FILES)) == {
        (app, gid(':lib'), 'exact', 'implementation', f, 2, 2),
        (app, gid(':core:model'), 'exact', 'api', f, 3, 3),
        (app, gid(':util'), 'exact', 'implementation', f, 4, 4),
        (app, gid(':core:data-test'), 'exact', 'implementation', f, 5, 5),
        (app, gid(':feature:my_mod'), 'exact', 'implementation', f, 6, 6),
        (app, gid(':missing'), 'unresolved', 'implementation', f, 7, 7),
        (app, gid('projects.nope'), 'unresolved', 'implementation', f, 8, 8),
        (app, gid(':lib'), 'exact', 'testImplementation', f, 10, 10),
        (app, gid(':ghost'), 'exact', 'implementation', f, 13, 13)}


def test_V4_A10_wrapper_calls_use_the_outer_configuration_name():
    files = {'settings.gradle.kts': 'include(":app", ":x", ":y")\n',
             'app/build.gradle.kts': 'dependencies {\n    implementation(platform(project(":x")))\n    api(enforcedPlatform(projects.y))\n}\n',
             'x/build.gradle.kts': BUILD, 'y/build.gradle.kts': BUILD}
    f = 'app/build.gradle.kts'
    assert edge_view(enriched(files)) == {(gid(':app'), gid(':x'), 'exact', 'implementation', f, 2, 2),
                                          (gid(':app'), gid(':y'), 'exact', 'api', f, 3, 3)}


def test_V4_A12_self_reference_and_call_less_reference_make_no_edge():
    files = {'settings.gradle.kts': 'include(":app", ":x")\n',
             'app/build.gradle.kts': 'val p = project(":x")\ndependencies {\n    implementation(project(":app"))\n}\n',
             'x/build.gradle.kts': BUILD}
    assert declared_edges(enriched(files)) == []


def test_V4_A11_empty_build_file_gives_span_less_node_with_module_dir():
    node = node_by_id(enriched({'settings.gradle.kts': 'include(":a")\n', 'a/build.gradle.kts': ''}), gid(':a'))
    assert node.span is None and 'file_path' not in node.metadata and node.metadata['module_dir'] == 'a'


def test_V4_edge_count_collapses_only_repeats_of_same_configuration():
    edges = declared_edges(enriched(V4_FILES))
    assert len(edges) == 9
    lib = [e for e in edges if e.to_id == gid(':lib')]
    assert sorted(e.metadata['configuration'] for e in lib) == ['implementation', 'testImplementation']


def test_V4_unresolved_targets_become_span_less_nodes_without_module_dir():
    arch = enriched(V4_FILES)
    for ident in (gid(':missing'), gid('projects.nope')):
        node = node_by_id(arch, ident)
        assert node.span is None and 'module_dir' not in node.metadata
    ghost = node_by_id(arch, gid(':ghost'))
    assert ghost.span is None and ghost.metadata['module_dir'] == 'ghost'
    assert {n.id for n in arch.nodes if 'module_dir' in n.metadata and n.id.startswith('build-module:gradle:')} == {
        gid(p) for p in (':', ':app', ':lib', ':util', ':core:model', ':core:data-test', ':feature:my_mod', ':ghost')}


NPM_A = '\n'.join([
    '{',                                   # 1
    '  "name": "@x/a",',                   # 2
    '  "dependencies": {',                 # 3
    '    "@x/b": "*",',                    # 4
    '    "lodash": "^4"',                  # 5
    '  },',                                # 6
    '  "devDependencies": {',              # 7
    '    "@x/c": "workspace:*"',           # 8
    '  },',                                # 9
    '  "peerDependencies": {',             # 10
    '    "@x/d": "^1"',                    # 11
    '  },',                                # 12
    '  "optionalDependencies": {',         # 13
    '    "@x/e": "1.0.0"',                 # 14
    '  }',                                 # 15
    '}', ''])
V5_FILES = {'package.json': '{"workspaces": ["packages/*"]}', 'packages/a/package.json': NPM_A,
            **{f'packages/{k}/package.json': pj(f'@x/{k}') for k in 'bcde'}}


def test_V5_N4_four_dependency_fields_workspace_only_with_key_line_evidence():
    f = 'packages/a/package.json'
    a = nid('@x/a')
    assert edge_view(enriched(V5_FILES)) == {
        (a, nid('@x/b'), 'exact', 'dependencies', f, 4, 4),
        (a, nid('@x/c'), 'exact', 'devDependencies', f, 8, 8),
        (a, nid('@x/d'), 'exact', 'peerDependencies', f, 11, 11),
        (a, nid('@x/e'), 'exact', 'optionalDependencies', f, 14, 14)}


def test_V5_external_name_makes_no_edge_or_node():
    arch = enriched(V5_FILES)
    assert not any('lodash' in i for i in module_ids(arch)) and not any('lodash' in e.to_id for e in declared_edges(arch))


def assignment(files, sources=()):
    from analysis.structure import package_assignments
    _snap, arch = file_architecture(files, sources)
    return {f: sorted(v) for f, v in package_assignments(arch)['build'].items() if v}, arch


def test_V6_B1_B2_boundaries_exact_subdir_sibling_prefix_and_root():
    files = {'settings.gradle.kts': 'include(":core", ":core:data", ":core-ui")\n', 'build.gradle.kts': BUILD,
             'core/build.gradle.kts': BUILD, 'core/data/build.gradle.kts': BUILD, 'core-ui/build.gradle.kts': BUILD,
             'core/B.kt': 'class B\n', 'core/data/src/A.kt': 'class A\n', 'core-ui/X.kt': 'class X\n', 'top/Y.kt': 'class Y\n',
             'Z.kt': 'class Z\n'}
    got, _arch = assignment(files, ['core/B.kt', 'core/data/src/A.kt', 'core-ui/X.kt', 'top/Y.kt', 'Z.kt'])
    assert got == {
        'file:build.gradle.kts': [gpkg(':')], 'file:Z.kt': [gpkg(':')], 'file:top/Y.kt': [gpkg(':')],
        'file:core/build.gradle.kts': [gpkg(':core')], 'file:core/B.kt': [gpkg(':core')],
        'file:core/data/build.gradle.kts': [gpkg(':core:data')], 'file:core/data/src/A.kt': [gpkg(':core:data')],
        'file:core-ui/build.gradle.kts': [gpkg(':core-ui')], 'file:core-ui/X.kt': [gpkg(':core-ui')]}


def test_V6_B2_sibling_with_common_prefix_is_unassigned_when_no_root_module():
    from analysis.structure import analyze_structure
    files = {'core/build.gradle.kts': BUILD, 'core/B.kt': 'class B\n', 'core-ui/X.kt': 'class X\n', 'corex/Z.kt': 'class Z\n',
             'W.kt': 'class W\n'}
    sources = ['core/B.kt', 'core-ui/X.kt', 'corex/Z.kt', 'W.kt']
    got, arch = assignment(files, sources)
    assert got == {'file:core/build.gradle.kts': [gpkg(':core')], 'file:core/B.kt': [gpkg(':core')]}
    build = analyze_structure(arch, default_weights()).coverage['structure']['schemes']['build']
    assert sorted(build['unassigned_files']) == ['file:W.kt', 'file:core-ui/X.kt', 'file:corex/Z.kt']
    assert (build['assigned_file_count'], build['unassigned_file_count'], build['shared_file_count']) == (2, 3, 0)


def test_V6_B3_root_only_module_takes_every_file():
    from analysis.structure import analyze_structure
    files = {'settings.gradle.kts': '', 'build.gradle.kts': BUILD, 'a/B.kt': 'class B\n', 'a/b/C.kt': 'class C\n'}
    got, arch = assignment(files, ['a/B.kt', 'a/b/C.kt'])
    assert got == {'file:build.gradle.kts': [gpkg(':')], 'file:a/B.kt': [gpkg(':')], 'file:a/b/C.kt': [gpkg(':')]}
    result = analyze_structure(arch, default_weights())
    assert set(result.package_metrics['build']) == {gpkg(':')}
    assert result.coverage['structure']['schemes']['build']['unassigned_file_count'] == 0


def test_V6_B4_gradle_and_npm_coexist_file_has_one_package_per_build_system():
    from analysis.structure import analyze_structure
    files = {'settings.gradle.kts': 'include(":app")\n', 'build.gradle.kts': BUILD, 'app/build.gradle.kts': BUILD,
             'package.json': '{"workspaces": ["app"]}', 'app/package.json': pj('web'), 'app/Main.kt': 'class M\n', 'README.kt': 'class R\n'}
    got, arch = assignment(files, ['app/Main.kt', 'README.kt'])
    both_root = sorted([gpkg(':'), npkg('(root)')])
    both_app = sorted([gpkg(':app'), npkg('web')])
    assert got == {'file:build.gradle.kts': both_root, 'file:package.json': both_root, 'file:README.kt': both_root,
                   'file:app/build.gradle.kts': both_app, 'file:app/package.json': both_app, 'file:app/Main.kt': both_app}
    build = analyze_structure(arch, default_weights()).coverage['structure']['schemes']['build']
    assert sorted(build['shared_files']) == sorted(got) and build['shared_file_count'] == 6
    assert build['unassigned_file_count'] == 0


V7_FILES = {
    'settings.gradle.kts': 'include(":s", ":u1", ":u2", ":v", ":w1", ":w2", ":p", ":q")\n',
    'build.gradle.kts': BUILD,
    'u1/build.gradle.kts': 'dependencies {\n    implementation(project(":s"))\n}\n',
    'u2/build.gradle.kts': 'dependencies {\n    implementation(projects.s)\n}\n',
    's/build.gradle.kts': 'dependencies {\n    implementation(project(":v"))\n}\n',
    'v/build.gradle.kts': 'dependencies {\n    implementation(projects.w1)\n    implementation(project(":w2"))\n}\n',
    'w1/build.gradle.kts': BUILD, 'w2/build.gradle.kts': BUILD,
    'p/build.gradle.kts': BUILD, 'q/build.gradle.kts': BUILD,
    'p/src/P.kt': 'package com.p\n\nimport com.q.Q\n\nclass P {\n    fun f() = Q()\n}\n',
    'q/src/Q.kt': 'package com.q\n\nimport com.p.P\n\nclass Q {\n    fun g() = P()\n}\n',
}


@pytest.fixture(scope='module')
def v7(tmp_path_factory):
    root = write_repo(tmp_path_factory.mktemp('v7repo'), V7_FILES)
    _done, payload, report = run_cli(root, tmp_path_factory.mktemp('v7out'), '-l', 'kotlin')
    return root, payload, report


def metric(payload, path):
    return payload['dependency_network']['package_metrics']['build'][gpkg(path)]


def test_V7_package_metrics_for_build_scheme(v7):
    _root, payload, _report = v7
    metrics = payload['dependency_network']['package_metrics']['build']
    assert set(metrics) == {gpkg(p) for p in (':', ':s', ':u1', ':u2', ':v', ':w1', ':w2', ':p', ':q')}
    got = {p: (metric(payload, p)['ca'], metric(payload, p)['ce']) for p in (':s', ':u1', ':u2', ':v', ':w1', ':w2', ':p', ':q')}
    assert got == {':s': (2, 1), ':u1': (0, 1), ':u2': (0, 1), ':v': (1, 2), ':w1': (1, 0), ':w2': (1, 0), ':p': (1, 1), ':q': (1, 1)}
    assert metric(payload, ':s')['instability'] == pytest.approx(1 / 3)
    assert metric(payload, ':v')['instability'] == pytest.approx(2 / 3)
    assert metric(payload, ':w1')['instability'] == 0 and metric(payload, ':u1')['instability'] == 1
    assert metric(payload, ':p')['instability'] == 0.5
    assert metric(payload, ':p')['file_count'] == 2 and metric(payload, ':s')['file_count'] == 1


def test_V7_package_dependencies_for_build_scheme(v7):
    _root, payload, _report = v7
    expected = {(':u1', ':s'), (':u2', ':s'), (':s', ':v'), (':v', ':w1'), (':v', ':w2'), (':p', ':q'), (':q', ':p')}
    assert pairs_of(payload, 'build') == {(gpkg(a), gpkg(b)) for a, b in expected}
    assert {item['tier'] for item in payload['dependency_network']['package_dependencies']['build']} == {'certain'}


def test_V7_package_cycle_between_modules_referencing_each_other_in_code(v7):
    _root, payload, _report = v7
    members = sorted([gpkg(':p'), gpkg(':q')])
    cycles = by_kind(payload, 'package_cycle', 'build')
    assert {(c['structure']['tier'], tuple(c['structure']['members']), c['id']) for c in cycles} == {
        (tier, tuple(members), cycle_id('build', tier, members)) for tier in ('certain', 'resolved', 'all')}


def test_V7_unstable_dependency_for_build_scheme(v7):
    _root, payload, _report = v7
    (item,) = by_kind(payload, 'unstable_dependency', 'build')
    assert item['id'] == unstable_id('build', gpkg(':s'), gpkg(':v'))
    assert item['metrics']['instability_from'] == pytest.approx(1 / 3) and item['metrics']['instability_to'] == pytest.approx(2 / 3)


def test_V7_coverage_build_scheme(v7):
    _root, payload, _report = v7
    schemes = payload['coverage']['structure']['schemes']
    build = schemes['build']
    assert build['unassigned_file_count'] == 0 and build['unassigned_files'] == []
    assert build['shared_file_count'] == 0 and build['shared_files'] == []
    assert build['assigned_file_count'] == schemes['language']['assigned_file_count'] > 0


def test_V7_N4_npm_workspace_scenario(tmp_path):
    files = {'package.json': '{"workspaces": ["packages/*"]}',
             'packages/a/package.json': '{\n  "name": "@x/a",\n  "dependencies": {\n    "@x/b": "*"\n  }\n}\n',
             'packages/b/package.json': pj('@x/b'),
             'packages/a/index.ts': 'export const a = 1;\n', 'packages/b/index.ts': 'export const b = 1;\n'}
    root = write_repo(tmp_path / 'repo', files)
    _done, payload, _report = run_cli(root, tmp_path / 'out', '-l', 'typescript')
    network = payload['dependency_network']
    assert set(network['package_metrics']['build']) == {npkg('(root)'), npkg('@x/a'), npkg('@x/b')}
    assert pairs_of(payload, 'build') == {(npkg('@x/a'), npkg('@x/b'))}
    a, b = network['package_metrics']['build'][npkg('@x/a')], network['package_metrics']['build'][npkg('@x/b')]
    assert (a['ca'], a['ce'], a['instability']) == (0, 1, 1) and (b['ca'], b['ce'], b['instability']) == (1, 0, 0)
    schemes = payload['coverage']['structure']['schemes']
    assert schemes['build']['unassigned_file_count'] == 0 and schemes['build']['shared_file_count'] == 0
    assert schemes['build']['assigned_file_count'] == schemes['language']['assigned_file_count']


def test_V8_policy_constant_is_v2():
    from analysis.structure import STRUCTURE_POLICY
    assert STRUCTURE_POLICY == 'structure.v2'


def test_V8_v1_baseline_delta_is_rejected_as_policy_mismatch():
    import bottlenecks.delta as delta
    from tests.delta_support import payload
    with pytest.raises(delta.BaselineError) as raised:
        delta.compute_delta(payload(policy='structure.v2'), payload(policy='structure.v1'))
    assert str(raised.value).startswith('baseline: ') and 'structure_policy' in str(raised.value)


def test_V8_cli_current_report_is_v2_and_v1_baseline_exits_with_baseline_error(v7, tmp_path):
    root, payload, _report = v7
    assert payload['dependency_network']['structure_policy'] == 'structure.v2'
    old = json.loads(json.dumps(payload))
    old['dependency_network']['structure_policy'] = 'structure.v1'
    baseline = tmp_path / 'old.json'
    baseline.write_text(json.dumps(old), encoding='utf-8')
    done, _p, _r = run_cli(root, tmp_path / 'out', '-l', 'kotlin', extra=['--baseline', str(baseline)], check=False)
    assert done.returncode == 1
    lines = [line for line in done.stderr.splitlines() if line.startswith('[!]')]
    assert len(lines) == 1 and lines[0].startswith('[!] Error: baseline: ') and 'structure_policy' in lines[0]


V9_FILES = {
    'settings.gradle.kts': 'include(":app", ":lib")\n', 'build.gradle.kts': BUILD,
    'app/build.gradle.kts': 'dependencies {\n    implementation(project(":lib"))\n}\n',
    'lib/build.gradle.kts': 'dependencies {\n    implementation(project(":gone"))\n}\n',
    'app/src/main/kotlin/com/example/app/A.kt': 'package com.example.app\n\nclass A\n',
    'lib/src/main/kotlin/com/example/lib/L.kt': 'package com.example.lib\n\nclass L\n',
    'main.py': 'def main():\n    return 1\n',
    'package.json': '{"workspaces": ["web/*"]}',
    'web/a/package.json': '{\n  "name": "@w/a",\n  "dependencies": {\n    "@w/b": "*"\n  }\n}\n',
    'web/b/package.json': pj('@w/b'),
    'web/a/index.ts': 'export const a = 1;\n',
}


def test_V9a_merged_analyzers_keep_one_node_and_one_edge_per_key(tmp_path):
    root = write_repo(tmp_path / 'repo', V9_FILES)
    _done, _payload, report = run_cli(root, tmp_path / 'out', '-l', 'python', '-l', 'typescript', granularity='symbol')
    ids = [n['id'] for n in report['nodes']]
    assert len(ids) == len(set(ids))
    assert sorted(i for i in ids if i.startswith('build-module:')) == sorted(
        [gid(':'), gid(':app'), gid(':lib'), gid(':gone'), nid('(root)'), nid('@w/a'), nid('@w/b')])
    declared = [(e['from_id'], e['to_id'], e['relation']) for e in report['edges'] if e['relation'] == 'DECLARES_DEPENDENCY']
    assert len(declared) == len(set(declared))
    assert sorted(declared) == sorted([(gid(':app'), gid(':lib'), 'DECLARES_DEPENDENCY'),
                                       (gid(':lib'), gid(':gone'), 'DECLARES_DEPENDENCY'),
                                       (nid('@w/a'), nid('@w/b'), 'DECLARES_DEPENDENCY')])


V9B_FILES = {'config.yaml': 'port: 8080\n', 'main.py': "def consume():\n    return 'port'\n",
             'client.ts': 'export function consume() {\n  return "port";\n}\n'}


def test_V9b_yaml_config_used_by_python_and_typescript_merges_without_duplicates(tmp_path):
    root = write_repo(tmp_path / 'repo', V9B_FILES)
    _done, _payload, report = run_cli(root, tmp_path / 'out', '-l', 'python', '-l', 'typescript', granularity='symbol')
    ids = [n['id'] for n in report['nodes']]
    assert len(ids) == len(set(ids))
    assert ids.count('config:config.yaml:port') == 1
    keys = [(e['from_id'], e['to_id'], e['relation']) for e in report['edges']]
    configures = [k for k in keys if k[0] == 'config:config.yaml:port']
    assert len(configures) == len(set(configures)) == 2


def test_V9c_same_id_from_non_enrichment_nodes_still_fails_with_exit_1(tmp_path):
    files = {'settings.gradle.kts': 'include(":app")\n', 'app/build.gradle.kts': BUILD,
             'app/src/main/kotlin/com/example/A.kt': 'package com.example\n\nclass A\n'}
    root = write_repo(tmp_path / 'repo', files)
    ids = {}
    for label, flags in (('android', ['-f', 'android']), ('kotlin', ['-l', 'kotlin'])):
        _d, _p, report = run_cli(root, tmp_path / label, *flags, granularity='symbol')
        ids[label] = [n['id'] for n in report['nodes']]
    first = next(i for i in ids['kotlin'] if i in set(ids['android']) and not i.startswith('build-module:'))
    done, _p, _r = run_cli(root, tmp_path / 'merged', '-f', 'android', '-l', 'kotlin', granularity='symbol', check=False)
    assert done.returncode == 1
    assert done.stderr.strip().splitlines()[-1] == f'[!] Error: duplicate node id across analyzers: {first}'


FIXTURE_FLAGS = {'fastapi-realworld': ['-l', 'python'], 'typescript-nestjs-realworld': ['-l', 'typescript', '-f', 'nestjs']}
NORMALIZED = ('candidates', 'coverage', 'package_metrics', 'package_dependencies')


def normalized(payload):
    """Same four parts as the golden; both policy strings are replaced so only the policy value itself may differ."""
    from tests.doc_references_support import without_doc_references
    data = without_doc_references(payload)
    network = data['dependency_network']
    result = {'candidates': data['candidates'], 'coverage': data['coverage'],
              'package_metrics': network['package_metrics'], 'package_dependencies': network['package_dependencies']}
    result['coverage']['structure']['policy'] = '<policy>'
    return result, network['structure_policy']


@pytest.mark.parametrize('name', sorted(FIXTURE_FLAGS))
def test_V10_G1_build_file_free_fixture_matches_base_commit_golden(name, tmp_path):
    """Golden: tests/build_modules_evidence/base_<fixture>.json, produced by running this CLI at base commit a8a3012 in a
    temporary `git worktree` with the flags below, `--granularity file --json --bottlenecks`, PYTHONHASHSEED=0, keeping
    candidates, coverage, package_metrics and package_dependencies (worktree removed afterwards)."""
    from fixtures.registry import fixture_root
    root = fixture_root(name).resolve()
    assert not [p for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts and p.name in (
        'settings.gradle', 'settings.gradle.kts', 'build.gradle', 'build.gradle.kts')]
    golden = json.loads((EVIDENCE / f'base_{name}.json').read_text(encoding='utf-8'))
    assert golden['base_commit'] == BASE_COMMIT and golden['structure_policy'] == 'structure.v1'
    _done, payload, _report = run_cli(root, tmp_path, *FIXTURE_FLAGS[name])
    current, policy = normalized(payload)
    expected = {key: golden[key] for key in NORMALIZED}
    expected['coverage']['structure']['policy'] = '<policy>'
    assert policy == 'structure.v2'
    assert 'build' not in payload['coverage']['structure']['schemes']
    assert 'build' not in payload['dependency_network']['package_metrics']
    assert 'build' not in payload['dependency_network']['package_dependencies']
    for key in NORMALIZED:
        assert current[key] == expected[key], key


def test_V11_E1_included_module_without_directory_is_span_less_and_edge_is_exact():
    files = {'settings.gradle.kts': 'include(":app", ":ghost")\n',
             'app/build.gradle.kts': 'dependencies {\n    implementation(project(":ghost"))\n}\n'}
    arch = enriched(files)
    ghost = node_by_id(arch, gid(':ghost'))
    assert ghost.span is None and ghost.metadata['module_dir'] == 'ghost' and 'file_path' not in ghost.metadata
    assert edge_view(arch) == {(gid(':app'), gid(':ghost'), 'exact', 'implementation', 'app/build.gradle.kts', 2, 2)}


def test_V11_E2_unresolved_project_and_accessor_targets():
    files = {'settings.gradle.kts': 'include(":app")\n',
             'app/build.gradle.kts': 'dependencies {\n    implementation(project(":missing"))\n    implementation(projects.nope)\n}\n'}
    f = 'app/build.gradle.kts'
    assert edge_view(enriched(files)) == {(gid(':app'), gid(':missing'), 'unresolved', 'implementation', f, 2, 2),
                                          (gid(':app'), gid('projects.nope'), 'unresolved', 'implementation', f, 3, 3)}


def test_V11_E3_broken_root_package_json_keeps_gradle_detection_and_cli_succeeds(tmp_path):
    files = {'package.json': '{"workspaces": [', 'packages/a/package.json': pj('a'), 'settings.gradle.kts': 'include(":app")\n',
             'app/build.gradle.kts': BUILD, 'app/src/A.kt': 'package a\n\nclass A\n'}
    arch = enriched(files)
    assert module_ids(arch, 'npm') == set() and module_ids(arch, 'gradle') == {gid(':'), gid(':app')}
    root = write_repo(tmp_path / 'repo', files)
    _done, payload, _report = run_cli(root, tmp_path / 'out', '-l', 'kotlin')
    packages = set(payload['dependency_network']['package_metrics']['build'])
    assert gpkg(':app') in packages and all(p.startswith('pkg:gradle:') for p in packages)


def test_V11_E4_commented_include_and_project_make_no_module_or_edge():
    files = {'settings.gradle.kts': '// include(":x")\n/* include(":y") */\ninclude(":app")\n',
             'app/build.gradle.kts': 'dependencies {\n    // implementation(project(":x"))\n    /* project(":y") */\n}\n'}
    arch = enriched(files)
    assert module_ids(arch, 'gradle') == {gid(':'), gid(':app')} and declared_edges(arch) == []


def test_V11_workspaces_number_makes_no_npm_module_and_gradle_still_works():
    files = {'package.json': '{"workspaces": 3}', 'packages/a/package.json': pj('a'), 'settings.gradle.kts': 'include(":app")\n'}
    arch = enriched(files)
    assert module_ids(arch, 'npm') == set() and module_ids(arch, 'gradle') == {gid(':'), gid(':app')}


def test_V11_name_number_falls_back_to_directory_id():
    files = workspace_files(['packages/*'], {'packages/a/package.json': '{"name": 5}', 'packages/b/package.json': pj('b')})
    assert npm_ids(files) == {nid('(root)'), nid('packages/a'), nid('b')}


def test_V11_broken_workspace_package_json_is_directory_id_without_edges_and_siblings_stay_normal():
    files = workspace_files(['packages/*'], {
        'packages/a/package.json': pj('@x/a', dependencies={'@x/b': '*'}),
        'packages/b/package.json': '{ not json',
        'packages/c/package.json': pj('@x/c', dependencies={'@x/a': '*'})})
    arch = enriched(files)
    assert module_ids(arch, 'npm') == {nid('(root)'), nid('@x/a'), nid('packages/b'), nid('@x/c')}
    assert {(e[0], e[1]) for e in edge_view(arch)} == {(nid('@x/c'), nid('@x/a'))}


def test_V11_garbled_settings_and_build_files_use_only_the_matching_parts():
    files = {'settings.gradle.kts': 'include(foo)\ninclude(\ninclude(":ok", ":other")\n',
             'ok/build.gradle.kts': 'dependencies {\n    implementation(project(\n    implementation(project(":other"))\n}\n',
             'other/build.gradle.kts': BUILD}
    arch = enriched(files)
    assert module_ids(arch, 'gradle') == {gid(':'), gid(':ok'), gid(':other')}
    assert edge_view(arch) == {(gid(':ok'), gid(':other'), 'exact', 'implementation', 'ok/build.gradle.kts', 3, 3)}



V9F_FILES = {
    'settings.gradle.kts': 'include(":app", ":lib")\n',
    'app/build.gradle.kts': 'dependencies {\n    implementation(project(":lib"))\n    testImplementation(project(":lib"))\n}\n',
    'lib/build.gradle.kts': BUILD,
    'main.py': 'def main():\n    return 1\n',
    'client.ts': 'export const a = 1;\n',
}


def test_V9f_edges_differing_only_in_configuration_survive_the_merge(tmp_path):
    root = write_repo(tmp_path / 'repo', V9F_FILES)
    _done, _payload, report = run_cli(root, tmp_path / 'out', '-l', 'python', '-l', 'typescript', granularity='symbol')
    declared = [e for e in report['edges'] if e['relation'] == 'DECLARES_DEPENDENCY' and e['from_id'] == gid(':app') and e['to_id'] == gid(':lib')]
    assert sorted(e['metadata']['configuration'] for e in declared) == ['implementation', 'testImplementation']
    keys = [json.dumps([e.get(k) for k in ('from_id', 'to_id', 'relation', 'confidence', 'resolution', 'candidates', 'evidence', 'metadata')],
                       sort_keys=True) for e in report['edges']]
    assert len(keys) == len(set(keys))


def test_V6_F2_span_less_module_still_owns_its_files():
    files = {'settings.gradle.kts': 'include(":x")\n', 'build.gradle.kts': BUILD, 'x/src/A.kt': 'class A\n'}
    got, _arch = assignment(files, ['x/src/A.kt'])
    assert got == {'file:build.gradle.kts': [gpkg(':')], 'file:x/src/A.kt': [gpkg(':x')]}


def test_V11_E1_file_graph_span_less_module_is_a_node_only_when_an_edge_reaches_it():
    untouched = {'settings.gradle.kts': 'include(":app", ":ghost")\n', 'app/build.gradle.kts': BUILD, 'app/A.kt': 'class A\n'}
    _snap, arch = file_architecture(untouched, ['app/A.kt'])
    assert gid(':ghost') not in {n.id for n in arch.nodes}
    touched = dict(untouched, **{'app/build.gradle.kts': 'dependencies {\n    implementation(project(":ghost"))\n}\n'})
    _snap, arch = file_architecture(touched, ['app/A.kt'])
    (ghost,) = [n for n in arch.nodes if n.id == gid(':ghost')]
    assert ghost.metadata.get('boundary') is True


ROOT_PATH = '/bm-oracle'


def module_node(provenance, module_dir):
    from language_analyzers.core.graph_models import GraphNode, NodeCost
    return GraphNode(gid(':dup'), ':dup', 'configuration', 'configuration', kind='module', language='configuration',
                     cost=NodeCost(1, 1, 1), provenance=provenance,
                     metadata={'build_system': 'gradle', 'module_path': ':dup', 'module_dir': module_dir})


@pytest.mark.parametrize('first, second', [
    (('gradle', 'a'), ('gradle', 'b')),
    (('gradle', 'a'), ('repository-enrichment', 'a')),
], ids=['V9d-same-provenance-different-content', 'V9e-different-provenance'])
def test_V9de_conflicting_duplicate_ids_across_analyzers_exit_1(first, second, capsys):
    from types import SimpleNamespace
    import code_analyzer.cli as cli
    results = []
    for provenance, module_dir in (first, second):
        arch = SimpleNamespace(project_name='bm', project_path=ROOT_PATH, nodes=[module_node(provenance, module_dir)], edges=[],
                               report_collections=[], stats={})
        results.append((arch, None, []))
    with pytest.raises(SystemExit) as raised:
        cli._run_merged(SimpleNamespace(granularity='file'), ROOT_PATH, None, None, results=results)
    assert raised.value.code == 1
    assert f'[!] Error: duplicate node id across analyzers: {gid(":dup")}' in capsys.readouterr().err


def _merge_with_edges(first, second):
    from types import SimpleNamespace as NS
    from code_analyzer.cli import _run_merged
    from language_analyzers.core.graph_models import GraphNode

    def node(ident):
        return GraphNode(id=ident, label=ident, group='configuration', category='configuration', kind='module', provenance='gradle')

    def arch(edges):
        return NS(project_name='p', project_path='/p', nodes=[node('a'), node('b')], edges=edges, report_collections=[], stats={})
    return _run_merged(NS(granularity='file'), '/p', None, None, results=[(arch(first), None, []), (arch(second), None, [])])


def _declares(configuration, line=None):
    from language_analyzers.core.graph_models import GraphEdge, SourceSpan
    return GraphEdge(from_id='a', to_id='b', relation='DECLARES_DEPENDENCY', confidence='static_certain', resolution='exact',
                     evidence=None if line is None else SourceSpan('build.gradle.kts', line, line),
                     metadata={'configuration': configuration})


def test_V9g_merge_keeps_one_node_each_and_edges_that_differ_only_in_metadata():
    merged = _merge_with_edges([_declares('implementation')], [_declares('implementation'), _declares('api')])
    assert sorted(n.id for n in merged.nodes) == ['a', 'b']
    assert sorted(e.metadata['configuration'] for e in merged.edges) == ['api', 'implementation']
    assert [(e.from_id, e.to_id, value(e.relation)) for e in merged.edges] == [('a', 'b', 'DECLARES_DEPENDENCY')] * 2


def test_V9g_merge_keeps_edges_that_differ_only_in_evidence():
    merged = _merge_with_edges([_declares('implementation', 2)], [_declares('implementation', 2), _declares('implementation', 5)])
    assert sorted(e.evidence.start_line for e in merged.edges) == [2, 5]
    assert len(merged.edges) == 2


def test_V1_line_comment_after_an_empty_literal_hides_the_commented_include():
    assert gradle_ids({'settings.gradle.kts': 'include(":a", "")  // include(":ghost")\n'}) == {gid(':'), gid(':a')}


def test_V1_empty_block_comment_does_not_swallow_the_next_line():
    assert gradle_ids({'settings.gradle.kts': '/**/\ninclude(":a")\n'}) == {gid(':'), gid(':a')}


def test_V4_line_comment_after_an_empty_literal_makes_no_edge_and_module_costs_are_zero():
    files = {'settings.gradle.kts': 'include(":app", ":y")\n',
             'app/build.gradle.kts': 'dependencies {\n    implementation("")  // project(":y")\n}\n', 'y/build.gradle.kts': BUILD}
    arch = enriched(files)
    assert declared_edges(arch) == []
    npm = enriched(workspace_files(['packages/*'], {'packages/a/package.json': pj('a')}))
    for node in (node_by_id(arch, gid(':app')), node_by_id(npm, nid('a'))):
        assert (node.cost.token_estimate, node.cost.char_count, node.cost.line_count) == (0, 0, 0)


def test_V3_directory_shallower_than_the_pattern_is_not_a_module():
    files = workspace_files(['packages/*'], {'packages/package.json': pj('p'), 'packages/a/package.json': pj('@x/a')})
    assert npm_ids(files) == {nid('(root)'), nid('@x/a')}


def test_V3_positive_pattern_after_star_still_matches_by_star():
    files = workspace_files(['*', 'ab'], {'b/package.json': pj('b')})
    assert npm_ids(files) == {nid('(root)'), nid('b')}
