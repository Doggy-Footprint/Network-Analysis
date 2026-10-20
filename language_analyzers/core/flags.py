import re
from pathlib import Path
from typing import Iterable

DYNAMIC_IMPORT = "dynamic_import"
DYNAMIC_ATTR = "dynamic_attr"
DYNAMIC_EVAL = "dynamic_eval"
REEXPORT = "reexport"
GENERATED = "generated"
VENDORED = "vendored"
TEST = "test"

_GENERATED_DIR_PARTS = ("migrations", "versions", "__generated__", "generated")
_GENERATED_NAME_RE = re.compile(r"(_pb2(_grpc)?\.pyi?|\.g\.(dart|kt)|\.freezed\.dart|_generated\.[a-z]+)$")
# Room exports one JSON per database version into the room.schemaLocation directory,
# named by that integer version. Matching the number-only name keeps hand-written
# JSON that happens to live under a "schemas" directory out of the rule.
_ROOM_SCHEMA_NAME_RE = re.compile(r"^\d+\.json$")
_VENDORED_PARTS = ("vendor", "vendored", "third_party", "thirdparty", "node_modules", "site-packages")
_TEST_PARTS = ("test", "tests", "__tests__", "spec")
_TEST_NAME_RE = re.compile(r"(^test_.*\.py$|.+_test\.py$|.+\.(test|spec)\.(ts|tsx|js|jsx|mjs|cjs)$|.+Test\.kt$)")


def _parts(relative_path: str) -> Iterable[str]:
    return Path(relative_path.replace("\\", "/")).parts


def is_generated_path(relative_path: str) -> bool:
    parts = list(_parts(relative_path))
    if not parts:
        return False
    if _GENERATED_NAME_RE.search(parts[-1]):
        return True
    lowered = [part.lower() for part in parts[:-1]]
    # "versions" alone is too common; alembic's layout is migrations/versions or alembic/versions.
    for index, part in enumerate(lowered):
        if part in ("migrations", "__generated__", "generated"):
            return True
        if part == "versions" and index > 0 and lowered[index - 1] in ("alembic", "migrations"):
            return True
    if "schemas" in lowered and _ROOM_SCHEMA_NAME_RE.match(parts[-1]):
        return True
    return False


def is_vendored_path(relative_path: str) -> bool:
    return any(part.lower() in _VENDORED_PARTS for part in _parts(relative_path))


def is_test_path(relative_path: str) -> bool:
    parts = list(_parts(relative_path))
    if not parts:
        return False
    if _TEST_NAME_RE.fullmatch(parts[-1]):
        return True
    return any(part.lower() in _TEST_PARTS for part in parts[:-1])


def path_flags(relative_path: str) -> list:
    flags = []
    if is_generated_path(relative_path):
        flags.append(GENERATED)
    if is_vendored_path(relative_path):
        flags.append(VENDORED)
    if is_test_path(relative_path):
        flags.append(TEST)
    return flags
