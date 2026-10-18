import dataclasses
import itertools
import json
import random
from pathlib import Path

import pytest

from language_analyzers.core.external_imports import (PythonModuleIndex, TsconfigAliases, is_typescript_alias, kotlin_is_internal,
                                                       normalize_external_imports, parse_tsconfig_aliases, typescript_package_name)
from language_analyzers.kotlin import KotlinAnalyzer
from language_analyzers.python.graph import PythonGraphAnalyzer
from language_analyzers.typescript import TypeScriptAnalyzer
from repository import RepositorySnapshot
from tests.external_rules_support import (own_result, rec, ref_kotlin_internal, ref_normalize, ref_python_internal, ref_ts_alias,
                                          ref_ts_package_name)


def write_files(root, files):
    for path, text in files.items():
        target = Path(root) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    return Path(root)


def file_records(arch, kind):
    return {n.metadata['file_path']: n.metadata.get('external_imports') for n in arch.nodes
            if str(getattr(n.kind, 'value', n.kind)) == kind and (n.metadata or {}).get('file_path')}


def python_records(tmp_path, files):
    return file_records(PythonGraphAnalyzer(write_files(tmp_path, files)).analyze(), 'module')


def kotlin_records(tmp_path, files):
    return file_records(KotlinAnalyzer(write_files(tmp_path, files)).analyze(), 'file')


def typescript_arch(tmp_path, files, snapshot=False):
    if snapshot:
        snap = RepositorySnapshot(str(Path(tmp_path).resolve()), 'snapshot.v1', tuple(sorted(files.items())), ())
        return TypeScriptAnalyzer(str(tmp_path), snapshot=snap).analyze()
    return TypeScriptAnalyzer(str(write_files(tmp_path, files))).analyze()


def typescript_records(tmp_path, files, snapshot=False):
    return file_records(typescript_arch(tmp_path, files, snapshot), 'file')


def names(records):
    return [r['name'] for r in records or []]


C01_SOURCE = ('from __future__ import annotations\n'
              'import os\n'
              'import a.b as c\n'
              'from fastapi import FastAPI\n'
              'from app import x\n'
              'from . import y\n')


def test_V01_C01_import_forms(tmp_path):
    found = python_records(tmp_path, {'app/__init__.py': '', 'app/x.py': C01_SOURCE})
    assert found['app/x.py'] == [rec('a.b', 3), rec('fastapi', 4), rec('os', 2)]


def test_V01_import_plain_and_dotted_alias_names_and_multiple_aliases(tmp_path):
    source = 'import os\nimport a.b.c as d\nimport x.y, z as zz\n'
    assert python_records(tmp_path, {'m.py': source})['m.py'] == [rec('a.b.c', 2), rec('os', 1), rec('x.y', 3), rec('z', 3)]


def test_V01_from_absolute_records_module_not_imported_symbol(tmp_path):
    found = python_records(tmp_path, {'m.py': 'from a.b import c, d\nfrom fastapi import *\n'})
    assert found['m.py'] == [rec('a.b', 1), rec('fastapi', 2)]


def test_V01_from_internal_package_and_module_are_not_recorded(tmp_path):
    files = {'app/__init__.py': '', 'app/core/__init__.py': '', 'app/core/config.py': '', 'app/x.py':
             'from app import core\nimport app.core.config\nfrom app.core import config\nfrom app.core.config import X\n'}
    assert python_records(tmp_path, files)['app/x.py'] is None


def test_V01_from_relative_never_recorded(tmp_path):
    files = {'pkg/__init__.py': '', 'pkg/a.py': 'from . import b\nfrom .b import c\nfrom .missing import z\nfrom ..nowhere import q\n'
             'from . import nothing\n', 'pkg/b.py': ''}
    assert python_records(tmp_path, files)['pkg/a.py'] is None


def test_V01_future_import_never_recorded(tmp_path):
    assert python_records(tmp_path, {'m.py': 'from __future__ import annotations, division\n'})['m.py'] is None


C02_SOURCE = ('from typing import TYPE_CHECKING\n'
              'if TYPE_CHECKING:\n'
              '    import sqlalchemy\n'
              'try:\n'
              '    import ujson\n'
              'except ImportError:\n'
              '    import json\n'
              'def f():\n'
              '    import requests\n')


def test_V01_C02_branches_and_function_body(tmp_path):
    found = python_records(tmp_path, {'m.py': C02_SOURCE})['m.py']
    assert found == [rec('json', 7), rec('requests', 9), rec('sqlalchemy', 3), rec('typing', 1), rec('ujson', 5)]


def test_V01_class_body_recorded(tmp_path):
    source = 'class A:\n    import yaml\n    def m(self):\n        import toml\n'
    assert python_records(tmp_path, {'m.py': source})['m.py'] == [rec('toml', 4), rec('yaml', 2)]


def test_V01_nested_branch_in_function(tmp_path):
    source = ('def f():\n    if cond:\n        import a1\n    else:\n        import a2\n    try:\n        import b1\n'
              '    except ImportError:\n        import b2\n')
    assert python_records(tmp_path, {'m.py': source})['m.py'] == [rec('a1', 3), rec('a2', 5), rec('b1', 7), rec('b2', 9)]


def test_V01_with_or_loop_block_not_recorded(tmp_path):
    source = ('with ctx:\n    import w1\nfor i in x:\n    import f1\nwhile c:\n    import l1\n'
              'match v:\n    case 1:\n        import m1\nimport kept\n')
    assert python_records(tmp_path, {'m.py': source})['m.py'] == [rec('kept', 10)]


def test_V01_type_checking_branch_else_arm(tmp_path):
    source = 'import sys\nif sys.version_info >= (3, 9):\n    import tomllib\nelse:\n    import tomli\n'
    assert python_records(tmp_path, {'m.py': source})['m.py'] == [rec('sys', 1), rec('tomli', 5), rec('tomllib', 3)]


def test_V01_module_without_external_imports_has_no_key(tmp_path):
    found = python_records(tmp_path, {'m.py': 'x = 1\n', 'n.py': 'import m\n'})
    assert found == {'m.py': None, 'n.py': None}


def test_V01_same_name_twice_keeps_one_record_per_line(tmp_path):
    found = python_records(tmp_path, {'m.py': 'import os\nimport os\nimport os as o\n'})['m.py']
    assert found == [rec('os', 1), rec('os', 2), rec('os', 3)]


C03_MODULES = ['backend.app', 'backend.app.core', 'backend.app.core.config', 'backend.app.main', 'scripts.tool']
C03_PACKAGES = ['backend.app', 'backend.app.core']
C03_TABLE = [('app', True), ('app.core', True), ('app.core.config', True), ('app.missing', False), ('core', False),
             ('config', False), ('backend', True), ('backend.app', True), ('backend.x', False), ('scripts', True),
             ('tool', True), ('fastapi', False)]


@pytest.mark.parametrize('name,internal', C03_TABLE, ids=[f'C03-{n}' for n, _ in C03_TABLE])
def test_V02_C03_table(name, internal):
    index = PythonModuleIndex(C03_MODULES, C03_PACKAGES)
    assert index.is_internal(name) is internal
    assert ref_python_internal(C03_MODULES, C03_PACKAGES, name) is internal


def test_V02_accepts_one_shot_iterables():
    index = PythonModuleIndex(iter(C03_MODULES), (p for p in C03_PACKAGES))
    assert index.is_internal('app.core') is True and index.is_internal('core') is False


def test_V02_agrees_with_reference_on_random_layouts():
    rnd = random.Random(20261018)
    alphabet = ['a', 'b', 'c']
    for _ in range(300):
        modules = sorted({'.'.join(rnd.choice(alphabet) for _ in range(rnd.randint(1, 4))) for _ in range(rnd.randint(1, 5))})
        packages = sorted({'.'.join(m.split('.')[:rnd.randint(1, len(m.split('.')))]) for m in modules if rnd.random() < .6})
        index = PythonModuleIndex(modules, packages)
        for size in (1, 2, 3):
            for combo in itertools.product(alphabet, repeat=size):
                name = '.'.join(combo)
                assert index.is_internal(name) is ref_python_internal(modules, packages, name), (modules, packages, name)


KOTLIN_PACKAGES = ['com.ex.app', 'com.ex.core.data']
KOTLIN_APP = ('package com.ex.app\n\n'
              'import androidx.room.Dao\n'
              'import com.ex.core.data.Repo\n'
              'import com.ex.app.ui.*\n'
              'import kotlinx.coroutines.*\n'
              'import com.ex.Shared\n'
              'import com.ex.*\n')


def test_V03_C04_kotlin_analyzer_records(tmp_path):
    found = kotlin_records(tmp_path, {'App.kt': KOTLIN_APP, 'Data.kt': 'package com.ex.core.data\nclass Repo\n'})
    assert found['App.kt'] == [rec('androidx.room.Dao', 3), rec('com.ex.Shared', 7), rec('kotlinx.coroutines', 6)]
    assert found['Data.kt'] is None


C04_TABLE = [('androidx.room.Dao', False), ('com.ex.core.data.Repo', True), ('com.ex.app.ui', True),
             ('kotlinx.coroutines', False), ('com.ex.Shared', False), ('com.ex', True)]


@pytest.mark.parametrize('name,internal', C04_TABLE, ids=['external-fqn', 'internal-fqn', 'internal-star', 'external-star',
                                                          'prefix-mismatch', 'parent-of-repo-package'])
def test_V03_kotlin_is_internal_partitions(name, internal):
    assert kotlin_is_internal(name, KOTLIN_PACKAGES) is internal
    assert ref_kotlin_internal(name, KOTLIN_PACKAGES) is internal


def test_V03_kotlin_is_internal_equal_package_and_sibling_segment_boundary():
    assert kotlin_is_internal('com.ex.app', KOTLIN_PACKAGES) is True
    assert kotlin_is_internal('com.ex.application.X', KOTLIN_PACKAGES) is False
    assert kotlin_is_internal('com.e', KOTLIN_PACKAGES) is False


def test_V03_kotlin_is_internal_agrees_with_reference():
    parts = ['a', 'b', 'c']
    packages_pool = ['.'.join(c) for n in (1, 2, 3) for c in itertools.product(parts, repeat=n)]
    rnd = random.Random(7)
    for _ in range(200):
        packages = rnd.sample(packages_pool, rnd.randint(1, 3))
        for name in packages_pool:
            assert kotlin_is_internal(name, packages) is ref_kotlin_internal(name, packages)


def test_V03_kotlin_default_package_file_does_not_make_everything_internal(tmp_path):
    found = kotlin_records(tmp_path, {'Root.kt': 'import androidx.room.Dao\nclass R\n', 'A.kt': 'package com.ex.app\nclass A\n'})
    assert names(found['Root.kt']) == ['androidx.room.Dao']


C05_SOURCE = ("import {A} from '@nestjs/common'\n"
              "import type {B} from 'typeorm/common/DeepPartial'\n"
              "export * from 'rxjs'\n"
              "const f = require('node:fs/promises')\n"
              "import('lodash')\n"
              "import x from './y'\n"
              "import z from '/abs'\n")


def test_V04_C05_records(tmp_path):
    found = typescript_records(tmp_path, {'src/a.ts': C05_SOURCE, 'src/y.ts': 'export default 1\n'})
    assert found['src/a.ts'] == [rec('@nestjs/common', 1), rec('lodash', 5, dynamic=True),
                                 rec('node:fs', 4, 'node:fs/promises', dynamic=True), rec('rxjs', 3),
                                 rec('typeorm', 2, 'typeorm/common/DeepPartial')]
    assert found['src/y.ts'] is None


@pytest.mark.parametrize('source,expected', [
    ("import {A} from '@nestjs/common'\n", [rec('@nestjs/common', 1)]),
    ("import type {B} from 'typeorm/common/DeepPartial'\n", [rec('typeorm', 1, 'typeorm/common/DeepPartial')]),
    ("export * from 'rxjs'\n", [rec('rxjs', 1)]),
    ("export {a} from 'rxjs/operators'\n", [rec('rxjs', 1, 'rxjs/operators')]),
    ("const f = require('node:fs/promises')\n", [rec('node:fs', 1, 'node:fs/promises', dynamic=True)]),
    ("import('lodash')\n", [rec('lodash', 1, dynamic=True)]),
    ("import x from './y'\n", None), ("import z from '/abs'\n", None), ("import w from '../up/z'\n", None),
], ids=['static-scoped', 'type-only', 'export-from', 'export-from-subpath', 'require-node', 'dynamic-import', 'relative',
        'absolute', 'relative-parent'])
def test_V04_one_import_form_at_a_time(tmp_path, source, expected):
    assert typescript_records(tmp_path, {'src/a.ts': source})['src/a.ts'] == expected


def test_V04_static_and_dynamic_of_same_package_stay_separate_records(tmp_path):
    source = "import a from 'lodash'\nconst b = require('lodash')\n"
    assert typescript_records(tmp_path, {'a.ts': source})['a.ts'] == [rec('lodash', 1), rec('lodash', 2, dynamic=True)]


C06_TABLE = [('@a/b/c', '@a/b'), ('@a', '@a'), ('@a/b', '@a/b'), ('node:fs', 'node:fs'), ('node:fs/x', 'node:fs'),
             ('a/b/c', 'a'), ('a', 'a')]


@pytest.mark.parametrize('specifier,expected', C06_TABLE, ids=[f'C06-{s}' for s, _ in C06_TABLE])
def test_V04_C06_package_name_table(specifier, expected):
    assert typescript_package_name(specifier) == expected
    assert ref_ts_package_name(specifier) == expected


@pytest.mark.parametrize('specifier,expected', [
    ('@nestjs/common/exceptions/http.exception', '@nestjs/common'), ('typeorm/common/DeepPartial', 'typeorm'),
    ('node:fs/promises', 'node:fs'), ('lodash', 'lodash'), ('@scope', '@scope'),
], ids=['f05-scoped-deep', 'f05-unscoped-deep', 'f05-node-subpath', 'f05-plain', 'f05-scope-only'])
def test_V04_F05_examples(specifier, expected):
    assert typescript_package_name(specifier) == expected


def test_V04_package_name_agrees_with_regex_reference_on_exhaustive_grammar():
    tokens = ['@', 'a', 'node:', '/', 'b.c', '@s']
    for size in range(1, 5):
        for combo in itertools.product(tokens, repeat=size):
            specifier = ''.join(combo)
            assert typescript_package_name(specifier) == ref_ts_package_name(specifier), specifier


C07_TSCONFIG = '{"compilerOptions": {"paths": {"@/*": ["src/*"], "@core": ["src/core/index.ts"], "*": ["types/*"]}}}'
C07_TABLE = [('@/x', True), ('@/', True), ('@core', True), ('@core/x', False), ('@nestjs/common', False), ('lodash', False)]


@pytest.mark.parametrize('specifier,expected', C07_TABLE, ids=[f'C07-{s}' for s, _ in C07_TABLE])
def test_V05_C07_paths_table(specifier, expected):
    aliases = parse_tsconfig_aliases(C07_TSCONFIG)
    assert is_typescript_alias(specifier, aliases, []) is expected
    assert ref_ts_alias(specifier, ['@/*', '@core', '*'], None, []) is expected


def test_V05_C07_parse_result_shape():
    aliases = parse_tsconfig_aliases(C07_TSCONFIG)
    assert isinstance(aliases, TsconfigAliases) and dataclasses.is_dataclass(aliases)
    assert tuple(aliases.path_keys) == ('@/*', '@core', '*')
    assert aliases.base_url is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        aliases.base_url = 'x'


def test_V05_path_keys_keep_input_order():
    aliases = parse_tsconfig_aliases('{"compilerOptions": {"paths": {"zz": [], "@a/*": [], "b": []}}}')
    assert tuple(aliases.path_keys) == ('zz', '@a/*', 'b')


C08_TSCONFIG = '{"compilerOptions": {"baseUrl": "./src"}}'
C08_FILES = ['src/app/x.ts', 'src/utils.ts', 'lib/z.ts']
C08_TABLE = [('app/x', True), ('utils', True), ('lib/z', False), ('lodash', False)]


@pytest.mark.parametrize('specifier,expected', C08_TABLE, ids=[f'C08-{s}' for s, _ in C08_TABLE])
def test_V05_C08_base_url_table(specifier, expected):
    aliases = parse_tsconfig_aliases(C08_TSCONFIG)
    assert is_typescript_alias(specifier, aliases, C08_FILES) is expected
    assert ref_ts_alias(specifier, [], 'src', C08_FILES) is expected


@pytest.mark.parametrize('base,expected', [('./src', 'src'), ('src', 'src'), ('.', ''), ('./', '')],
                         ids=['dot-slash-dir', 'plain-dir', 'dot-root', 'dot-slash-root'])
def test_V05_base_url_is_normalised_repo_relative(base, expected):
    assert parse_tsconfig_aliases(json.dumps({'compilerOptions': {'baseUrl': base}})).base_url == expected


def test_V05_base_url_root_makes_top_level_directories_aliases():
    aliases = parse_tsconfig_aliases('{"compilerOptions": {"baseUrl": "."}}')
    assert is_typescript_alias('lib/z', aliases, ['lib/z.ts', 'src/a.ts']) is True
    assert is_typescript_alias('lodash', aliases, ['lib/z.ts', 'src/a.ts']) is False


def test_V05_source_files_may_be_a_one_shot_iterable():
    aliases = parse_tsconfig_aliases(C08_TSCONFIG)
    assert is_typescript_alias('app/x', aliases, iter(C08_FILES)) is True


JSONC_ROWS = {
    'jsonc-line-comment': ('{\n // top comment\n "compilerOptions": {"baseUrl": "./src"} // tail\n}', 'src', ()),
    'jsonc-block-comment': ('{"compilerOptions": /* a */ {"paths": /* multi\n line */ {"@a/*": ["x"]}}}', None, ('@a/*',)),
    'slash-in-string': ('{"compilerOptions": {"paths": {"http://x/*": ["a"], "a/*b*/c": ["x"], "q\\"//z": ["y"]}}}', None,
                        ('http://x/*', 'a/*b*/c', 'q"//z')),
    'jsonc-empty-block-comment': ('{"compilerOptions": {/**/"baseUrl": "./src", "paths": {"@/*": ["src/*"]}}}', 'src', ('@/*',)),
    'jsonc-triple-star-block-comment': ('{"compilerOptions": {/***/"baseUrl": "./src", "paths": {"@/*": ["src/*"]}}}', 'src', ('@/*',)),
    'trailing-comma': ('{"compilerOptions": {"paths": {"@a": ["x",],},}, "include": ["src",],}', None, ('@a',)),
    'trailing-comma-then-comment': ('{"compilerOptions": {"baseUrl": "src", // c\n /* d */ },\n}', 'src', ()),
    'comma-brace-inside-string': ('{"compilerOptions": {"paths": {"a,}": ["x"], "b,]": ["y"]}}}', None, ('a,}', 'b,]')),
}


@pytest.mark.parametrize('row', sorted(JSONC_ROWS))
def test_V05_C09_jsonc_syntax(row):
    text, base_url, keys = JSONC_ROWS[row]
    aliases = parse_tsconfig_aliases(text)
    assert aliases.base_url == base_url
    assert tuple(aliases.path_keys) == keys


C10_ROWS = {
    'invalid-json': '{bad', 'top-level-list': '[]', 'compilerOptions-string': '{"compilerOptions": "x"}',
    'paths-list': '{"compilerOptions": {"paths": []}}', 'baseUrl-number': '{"compilerOptions": {"baseUrl": 5}}',
}


@pytest.mark.parametrize('row', sorted(C10_ROWS))
def test_V05_C10_invalid_input_raises_value_error(row):
    with pytest.raises(ValueError):
        parse_tsconfig_aliases(C10_ROWS[row])


@pytest.mark.parametrize('text', ['{}', '{"compilerOptions": {}}', '{"compilerOptions": {"paths": {}}}', '{"extends": "./base.json"}'],
                         ids=['empty-object', 'no-paths-no-baseUrl', 'empty-paths', 'extends-only'])
def test_V05_C11_missing_keys_are_not_errors(text):
    aliases = parse_tsconfig_aliases(text)
    assert aliases.base_url is None and tuple(aliases.path_keys) == ()
    assert is_typescript_alias('@a/x', aliases, ['src/a.ts']) is False


def tsconfig_files(tsconfig, extra=None):
    files = {'tsconfig.json': tsconfig, 'src/app/x.ts': 'export const x = 1\n',
             'src/main.ts': "import {a} from '@/lib'\nimport {b} from 'app/x'\nimport _ from 'lodash'\nimport {c} from '@nestjs/common'\n"}
    files.update(extra or {})
    return files


@pytest.mark.parametrize('snapshot', [False, True], ids=['filesystem', 'snapshot'])
def test_V05_analyzer_excludes_paths_and_base_url_aliases(tmp_path, snapshot):
    config = '{"compilerOptions": {"baseUrl": "./src", "paths": {"@/*": ["src/*"]}}}'
    found = typescript_records(tmp_path, tsconfig_files(config), snapshot)
    assert names(found['src/main.ts']) == ['@nestjs/common', 'lodash']


@pytest.mark.parametrize('snapshot', [False, True], ids=['filesystem', 'snapshot'])
def test_V05_analyzer_paths_only_keeps_base_url_specifiers_external(tmp_path, snapshot):
    config = '{"compilerOptions": {"paths": {"@/*": ["src/*"]}}}'
    found = typescript_records(tmp_path, tsconfig_files(config), snapshot)
    assert names(found['src/main.ts']) == ['@nestjs/common', 'app', 'lodash']


def test_V05_invalid_tsconfig_filesystem_mode_proceeds_without_aliases(tmp_path):
    arch = typescript_arch(tmp_path, tsconfig_files('{"compilerOptions": {"paths": [}'))
    assert names(file_records(arch, 'file')['src/main.ts']) == ['@/lib', '@nestjs/common', 'app', 'lodash']


def test_V05_invalid_coverage_record(tmp_path):
    arch = typescript_arch(tmp_path, tsconfig_files('{"compilerOptions": {"paths": [}'), True)
    results = own_result(arch.stats['analysis_coverage'], 'tsconfig.json', 'typescript-core')
    assert len(results) == 1 and results[0]['status'] == 'partial'
    assert [r['code'] for r in results[0]['reasons']] == ['tsconfig_invalid']
    assert all(r['message'] for r in results[0]['reasons'])
    assert names(file_records(arch, 'file')['src/main.ts']) == ['@/lib', '@nestjs/common', 'app', 'lodash']


@pytest.mark.parametrize('variant', ['valid-paths', 'missing-file', 'missing-compilerOptions'])
def test_V05_valid_or_absent_tsconfig_records_nothing(tmp_path, variant):
    files = tsconfig_files({'valid-paths': '{"compilerOptions": {"paths": {"@/*": ["src/*"]}}}', 'missing-file': None,
                            'missing-compilerOptions': '{"include": ["src"]}'}[variant])
    if variant == 'missing-file':
        del files['tsconfig.json']
    arch = typescript_arch(tmp_path, files, snapshot=True)
    coverage = arch.stats['analysis_coverage']
    assert 'tsconfig_invalid' not in json.dumps(coverage)
    rows = [r for r in coverage['files'] if r['file_path'] == 'tsconfig.json']
    assert all(not [x for x in r['results'] if x['analyzer_id'] == 'typescript-core'] for r in rows)


def test_V05_only_the_root_tsconfig_is_read(tmp_path):
    files = tsconfig_files('{"compilerOptions": {}}', {'sub/tsconfig.json': '{"compilerOptions": {"paths": {"lodash": ["x"]}}}',
                                                       'sub/a.ts': "import _ from 'lodash'\n"})
    assert names(typescript_records(tmp_path, files, True)['sub/a.ts']) == ['lodash']


def test_V06_duplicate_records_merge():
    records = [rec('a', 3), rec('a', 3), rec('b', 1, 'b/x', dynamic=True), rec('b', 1, 'b/x', dynamic=True)]
    assert normalize_external_imports(records) == [rec('a', 3), rec('b', 1, 'b/x', dynamic=True)]


def test_V06_same_name_different_lines_are_distinct():
    assert normalize_external_imports([rec('a', 9), rec('a', 2)]) == [rec('a', 2), rec('a', 9)]


def test_V06_ordering_by_name_then_line():
    records = [rec('b', 1), rec('a', 9), rec('B', 1), rec('a', 2), rec('@s/x', 5)]
    assert normalize_external_imports(records) == [rec('@s/x', 5), rec('B', 1), rec('a', 2), rec('a', 9), rec('b', 1)]


def test_V06_specifier_order_empty_first():
    records = [rec('x', 1, 'x/b'), rec('x', 1, 'x/a'), rec('x', 1)]
    assert normalize_external_imports(records) == [rec('x', 1), rec('x', 1, 'x/a'), rec('x', 1, 'x/b')]


def test_V06_dynamic_after_static():
    records = [rec('x', 1, dynamic=True), rec('x', 1)]
    assert normalize_external_imports(records) == [rec('x', 1), rec('x', 1, dynamic=True)]


def test_V06_line_outranks_specifier_and_specifier_outranks_dynamic():
    records = [rec('x', 2), rec('x', 1, 'x/z', dynamic=True), rec('x', 1, 'x/a', dynamic=True), rec('x', 1, 'x/a')]
    assert normalize_external_imports(records) == [rec('x', 1, 'x/a'), rec('x', 1, 'x/a', dynamic=True),
                                                   rec('x', 1, 'x/z', dynamic=True), rec('x', 2)]


def test_V06_empty_input_gives_empty_list_and_input_is_not_mutated():
    assert normalize_external_imports([]) == []
    records = [rec('b', 2), rec('a', 1), rec('a', 1)]
    snapshot = json.dumps(records)
    normalize_external_imports(records)
    assert json.dumps(records) == snapshot


def test_V06_accepts_iterators():
    assert normalize_external_imports(iter([rec('b', 1), rec('a', 1)])) == [rec('a', 1), rec('b', 1)]


def test_V06_agrees_with_reference_on_random_lists():
    rnd = random.Random(20261018)
    for _ in range(200):
        records = [rec(rnd.choice(['a', 'b', '@s/c']), rnd.randint(1, 3), rnd.choice([None, 'x', 'y']), rnd.random() < .5)
                   for _ in range(rnd.randint(0, 12))]
        assert normalize_external_imports(records) == ref_normalize(records)


def test_V16_star_key_swallows_all_bare_specifiers():
    aliases = parse_tsconfig_aliases('{"compilerOptions": {"paths": {"*": ["types/*"]}}}')
    for specifier in ('lodash', '@nestjs/common', 'fastapi', 'a/b'):
        assert is_typescript_alias(specifier, aliases, ['src/a.ts']) is False


def test_V16_star_key_in_analyzer_keeps_packages_external(tmp_path):
    files = tsconfig_files('{"compilerOptions": {"paths": {"*": ["types/*"]}}}')
    assert names(typescript_records(tmp_path, files, True)['src/main.ts']) == ['@/lib', '@nestjs/common', 'app', 'lodash']


def test_V16_relative_import_recorded_as_external(tmp_path):
    files = {'pkg/__init__.py': '', 'pkg/a.py': 'from .gone import x\nfrom . import gone2\nfrom ... import deep\n'}
    assert python_records(tmp_path, files)['pkg/a.py'] is None


def test_V16_namespace_root_misclassified(tmp_path):
    files = {'backend/app/__init__.py': '', 'backend/app/core/__init__.py': '', 'backend/app/core/config.py': 'X = 1\n',
             'backend/app/main.py': 'from app.core import config\nimport app.core.config\nfrom app import core\nimport fastapi\n'
             'from backend.x import y\nfrom core import z\n'}
    assert python_records(tmp_path, files)['backend/app/main.py'] == [rec('backend.x', 5), rec('core', 6), rec('fastapi', 4)]


def test_V01_F01_multi_line_python_imports_use_the_statement_line(tmp_path):
    source = ('import os, \\\n    sys\n'
              'from fastapi import (\n    A,\n    B)\n'
              'import json\n')
    assert python_records(tmp_path, {'m.py': source})['m.py'] == [rec('fastapi', 3), rec('json', 6), rec('os', 1), rec('sys', 1)]


def test_V04_F01_multi_line_typescript_imports_use_the_statement_line(tmp_path):
    source = ("import {\n  A,\n  B\n} from '@nestjs/common'\n"
              "export {\n  C\n} from 'rxjs'\n"
              "const f = require(\n  'node:fs'\n)\n")
    assert typescript_records(tmp_path, {'src/a.ts': source})['src/a.ts'] == [
        rec('@nestjs/common', 1), rec('node:fs', 8, dynamic=True), rec('rxjs', 5)]


def test_V01_F02_unparseable_module_still_counts_as_internal(tmp_path):
    files = {'app/__init__.py': '', 'app/broken.py': 'def f(:\n', 'app/m.py': 'from app.broken import x\nimport app.broken\nimport fastapi\n'}
    found = python_records(tmp_path, files)
    assert found['app/m.py'] == [rec('fastapi', 3)]
    assert found.get('app/broken.py') is None


def test_V01_F02_unparseable_package_init_still_defines_the_import_root(tmp_path):
    files = {'outer/pkg/__init__.py': 'def f(:\n', 'outer/pkg/core.py': 'X = 1\n',
             'other/y.py': 'import core\nimport pkg.core\nimport pkg\n'}
    assert python_records(tmp_path, files)['other/y.py'] == [rec('core', 1)]


def test_V05_C08_F06b_base_url_rows_are_segment_aware_and_stem_based():
    aliases = parse_tsconfig_aliases(C08_TSCONFIG)
    files = C08_FILES + ['src2/x.ts']
    for specifier, expected in [('app/other', True), ('utils/foo', True), ('src2/x', False), ('app', True), ('lib/z', False)]:
        assert is_typescript_alias(specifier, aliases, files) is expected, specifier
        assert ref_ts_alias(specifier, [], 'src', files) is expected


def test_V05_C08_F06b_root_base_url_top_level_directory_is_alias():
    aliases = parse_tsconfig_aliases('{"compilerOptions": {"baseUrl": "."}}')
    files = ['src2/x.ts', 'lib/z.ts', 'main.ts']
    for specifier, expected in [('src2/x', True), ('lib/anything', True), ('main', True), ('lodash', False)]:
        assert is_typescript_alias(specifier, aliases, files) is expected, specifier


@pytest.mark.parametrize('row', sorted(C10_ROWS))
def test_V05_C10_analyzer_proceeds_without_aliases_and_records_coverage(tmp_path, row):
    arch = typescript_arch(tmp_path, tsconfig_files(C10_ROWS[row]), True)
    results = own_result(arch.stats['analysis_coverage'], 'tsconfig.json', 'typescript-core')
    assert len(results) == 1 and results[0]['status'] == 'partial'
    assert [r['code'] for r in results[0]['reasons']] == ['tsconfig_invalid']
    assert names(file_records(arch, 'file')['src/main.ts']) == ['@/lib', '@nestjs/common', 'app', 'lodash']


def test_V04_F06_alias_exclusion_applies_to_non_static_forms(tmp_path):
    source = ("const a = require('@/lib')\nimport('@/x')\nexport * from '@/y'\nexport {a2} from '@/z'\n"
              "import l from 'lodash'\n")
    files = {'tsconfig.json': '{"compilerOptions": {"paths": {"@/*": ["src/*"]}}}', 'src/a.ts': source}
    assert typescript_records(tmp_path, files, True)['src/a.ts'] == [rec('lodash', 5)]
