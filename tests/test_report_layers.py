"""V01: report.unified.file_layers decision table (F04, C01, C02, C03). Expected layers are hand-derived from A03/A04."""
import pytest

from report.unified import file_layers
from tests.report_redesign_support import build_report, file_id, make_file

FW, PK = 'framework', 'package'

# Each case: (framework, {path: [roles in input order]}, {path: (layer, source)}, details mode)
# Package layer = path minus everything through the first matching source root, minus the longest common
# directory prefix of all (operating) files, first remaining directory, '(root)' when none remains.
CASES = {
    'android-multi-single-none': ('android', {
        'app/src/main/java/com/shop/ui/CartScreen.kt': ['composable', 'viewmodel'],
        'app/src/main/java/com/shop/ui/ListScreen.kt': ['composable'],
        'app/src/main/java/com/shop/data/Db.kt': ['composable', 'room_dao', 'room_entity'],
        'app/src/main/java/com/shop/net/Util.kt': [],
    }, {
        'app/src/main/java/com/shop/ui/CartScreen.kt': ('viewmodel', FW),
        'app/src/main/java/com/shop/ui/ListScreen.kt': ('composable', FW),
        'app/src/main/java/com/shop/data/Db.kt': ('room_dao', FW),
        'app/src/main/java/com/shop/net/Util.kt': ('net', PK),
    }, 'full'),
    'fastapi-multi-single-none': ('fastapi', {
        'src/app/routers/users.py': ['schema', 'router', 'dependency'],
        'src/app/routers/items.py': ['endpoint'],
        'src/app/models/base.py': [],
    }, {
        'src/app/routers/users.py': ('router', FW),
        'src/app/routers/items.py': ('endpoint', FW),
        'src/app/models/base.py': ('models', PK),
    }, 'full'),
    'sqlalchemy-multi-single-none': ('sqlalchemy', {
        'db/models/user.py': ['sqlalchemy_model', 'alembic_migration'],
        'db/models/order.py': ['alembic_migration', 'sqlalchemy_model'],
        'db/models/item.py': ['sqlalchemy_model'],
        'db/scripts/init.py': [],
    }, {
        'db/models/user.py': ('alembic_migration', FW),
        'db/models/order.py': ('alembic_migration', FW),
        'db/models/item.py': ('sqlalchemy_model', FW),
        'db/scripts/init.py': ('db', PK),
    }, 'full'),
    'nestjs-multi-single-none': ('nestjs', {
        'src/users/users.module.ts': ['controller', 'provider', 'module'],
        'src/users/users.service.ts': ['provider'],
        'src/common/util.ts': [],
    }, {
        'src/users/users.module.ts': ('module', FW),
        'src/users/users.service.ts': ('provider', FW),
        'src/common/util.ts': ('common', PK),
    }, 'full'),
    'A10-outside-source-root-first-repo-directory-or-root': ('fastapi', {
        'pkg/ui/a.py': [], 'pkg/ui/b.py': [], 'pkg/c.py': [], 'top.py': [],
    }, {
        'pkg/ui/a.py': ('pkg', PK), 'pkg/ui/b.py': ('pkg', PK), 'pkg/c.py': ('pkg', PK), 'top.py': ('(root)', PK),
    }, 'full'),
    'A10-mixed-rooted-and-unrooted-and-test-file': ('android', {
        'src/main/java/com/app/ui/A.java': [],
        'src/main/java/com/app/data/B.java': [],
        'src/test/java/com/other/T.java': [],
        'scripts/build.py': [],
        'setup.py': [],
    }, {
        'src/main/java/com/app/ui/A.java': ('ui', PK),
        'src/main/java/com/app/data/B.java': ('data', PK),
        'scripts/build.py': ('scripts', PK),
        'setup.py': ('(root)', PK),
    }, 'full'),
    'C03-directly-under-source-root': ('android', {
        'src/main/java/Main.java': [],
        'src/main/java/com/app/ui/A.java': [],
        'src/main/java/com/app/data/B.java': [],
    }, {
        'src/main/java/Main.java': ('(root)', PK),
        'src/main/java/com/app/ui/A.java': ('com', PK),
        'src/main/java/com/app/data/B.java': ('com', PK),
    }, 'full'),
    'C03-single-operating-file': ('android', {
        'src/main/java/com/app/ui/A.java': [],
    }, {
        'src/main/java/com/app/ui/A.java': ('(root)', PK),
    }, 'full'),
    'no-node-files-key': ('fastapi', {
        'app/ui/a.py': [], 'app/data/b.py': [],
    }, {
        'app/ui/a.py': ('app', PK), 'app/data/b.py': ('app', PK),
    }, 'absent'),
    'empty-node-files-mapping-with-role-symbols': ('fastapi', {
        'app/ui/a.py': ['router'], 'app/data/b.py': ['schema'],
    }, {
        'app/ui/a.py': ('app', PK), 'app/data/b.py': ('app', PK),
    }, 'empty-mapping'),
}

CASES['E01-core-provenance-module-node-is-not-a-framework-role'] = ('fastapi', {
    'src/app/routers/users.py': ['router'], 'src/app/models/base.py': [],
}, {
    'src/app/routers/users.py': ('router', FW), 'src/app/models/base.py': ('models', PK),
}, 'full')
GENERIC = {'E01-core-provenance-module-node-is-not-a-framework-role': {'src/app/models/base.py': ['module', 'class']}}
# A04 strips by source-root list order (src/main/java before src), not by position or shortest match; A10 then takes the prefix over rooted files.
CASES['E01-list-order-source-root'] = ('android', {
    'src/main/java/com/A.java': [], 'src/lib/B.java': [],
}, {
    'src/main/java/com/A.java': ('com', PK), 'src/lib/B.java': ('lib', PK),
}, 'full')


@pytest.mark.parametrize('case', CASES, ids=str)
def test_V01_file_layers_decision_table(case):
    framework, roles, expected, details = CASES[case]
    generic = GENERIC.get(case)
    files = [make_file(path) for path in roles]
    arch, _ = build_report(files, roles=roles, framework=framework, details=details, generic=generic)
    observed = file_layers(arch)
    observed = {k: v for k, v in observed.items() if k in {file_id(p) for p in expected}}
    assert observed == {file_id(path): {'layer': layer, 'source': source} for path, (layer, source) in expected.items()}
