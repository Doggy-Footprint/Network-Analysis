import ast
import warnings
from pathlib import PurePosixPath
from typing import Any, Iterable, Iterator, Mapping, Optional

from analysis.candidate_projection import candidate_targets
from analysis.file_graph import _LANGUAGE_PROVENANCE

TEST_CASE_COLUMNS = ["id", "file", "name", "strong_assertions", "weak_assertions", "mocks", "skipped"]

_TS_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"})
_CASE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".kt"})
_FOLLOWED = frozenset({"CALLS", "INSTANTIATES", "CALLS_ROUTE", "IMPLEMENTED_BY", "DECORATES"})
_CONFIRMED_CONFIDENCE = frozenset({"static_certain", "static_inferred"})
_CONFIRMED_RESOLUTION = frozenset({"exact", "unique_name"})
_CONSTRUCTORS = frozenset({"__init__", "__post_init__", "constructor", "init"})
_REACH_KINDS = frozenset({"function", "method", "class", "constant"})


def _suffix(path: str) -> str:
    return PurePosixPath(path).suffix.lower()


def _python_tree(source: str) -> Optional[ast.AST]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def _tree_sitter(suffix: str, source: str) -> Optional[tuple]:
    data = source.encode("utf-8", "replace")
    if suffix == ".kt":
        from language_analyzers.kotlin.ast import get_kotlin_parser
        parser = get_kotlin_parser()
    else:
        from language_analyzers.typescript.ast import parser_for_suffix
        parser = parser_for_suffix(suffix)
    root = parser.parse(data).root_node
    return None if root.has_error else (data, root)


def _text(data: bytes, node: Any) -> str:
    return data[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _line(node: Any) -> int:
    return node.start_point[0] + 1


_PY_BRANCH_NODES = tuple(item for item in (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, getattr(ast, "match_case", None)) if item)
_PY_NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

_TS_BRANCH_TYPES = frozenset({"if_statement", "for_statement", "for_in_statement", "while_statement", "do_statement", "catch_clause", "ternary_expression", "switch_case"})
_TS_OPERATORS = frozenset({"&&", "||", "??"})
_TS_NESTED = frozenset({"function_declaration", "generator_function_declaration", "method_definition", "class_declaration", "abstract_class_declaration"})
_TS_FUNCTION_VALUES = frozenset({"arrow_function", "function_expression", "function"})

_KT_BRANCH_TYPES = frozenset({"if_expression", "for_statement", "while_statement", "do_while_statement", "catch_block", "elvis_expression", "conjunction_expression", "disjunction_expression"})
_KT_NESTED = frozenset({"function_declaration", "class_declaration", "object_declaration"})


def _python_branches(root: ast.AST) -> int:
    total = 0
    stack = list(ast.iter_child_nodes(root))
    while stack:
        node = stack.pop()
        if isinstance(node, _PY_NESTED):
            continue
        if isinstance(node, _PY_BRANCH_NODES):
            total += 1
        elif isinstance(node, ast.BoolOp):
            total += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            total += len(node.ifs)
        stack.extend(ast.iter_child_nodes(node))
    return total


def _ts_branches(root: Any) -> int:
    total = 0
    stack = list(root.named_children)
    while stack:
        node = stack.pop()
        kind = node.type
        if kind in _TS_NESTED:
            continue
        if kind in _TS_BRANCH_TYPES:
            total += 1
        elif kind == "binary_expression":
            operator = node.child_by_field_name("operator")
            if operator is not None and operator.type in _TS_OPERATORS:
                total += 1
        stack.extend(node.named_children)
    return total


def _kotlin_branches(root: Any) -> int:
    total = 0
    stack = list(root.named_children)
    while stack:
        node = stack.pop()
        kind = node.type
        if kind in _KT_NESTED:
            continue
        if kind in _KT_BRANCH_TYPES:
            total += 1
        elif kind == "when_entry" and not any(child.type == "else" for child in node.children):
            total += 1
        stack.extend(node.named_children)
    return total


def _python_declarations(tree: ast.AST) -> dict:
    found: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.setdefault((node.lineno, node.name), node)
            if node.decorator_list:
                found.setdefault((min(item.lineno for item in node.decorator_list), node.name), node)
    return found


def _ts_declarations(root: Any, data: bytes) -> dict:
    found: dict = {}

    def register(node: Any, name: str, anchors: Iterable[Any]) -> None:
        for anchor in anchors:
            found.setdefault((_line(anchor), name), node)
        first = node
        while first.prev_named_sibling is not None and first.prev_named_sibling.type == "decorator":
            first = first.prev_named_sibling
        if first is not node:
            found.setdefault((_line(first), name), node)

    stack = [root]
    while stack:
        node = stack.pop()
        kind = node.type
        parent = node.parent
        if kind in ("function_declaration", "generator_function_declaration", "method_definition"):
            name = node.child_by_field_name("name")
            if name is not None:
                anchors = [node] + ([parent] if parent is not None and parent.type == "export_statement" else [])
                register(node, _text(data, name), anchors + [name])
        elif kind in _TS_FUNCTION_VALUES and parent is not None:
            name, anchors = None, [node]
            if parent.type == "variable_declarator":
                name = parent.child_by_field_name("name")
                anchors += [parent]
                statement = parent.parent
                while statement is not None and statement.type in ("lexical_declaration", "variable_declaration", "export_statement"):
                    anchors.append(statement)
                    statement = statement.parent
            elif parent.type in ("public_field_definition", "field_definition"):
                name = parent.child_by_field_name("name")
                anchors += [parent]
            if name is not None:
                register(node, _text(data, name), anchors)
        stack.extend(node.named_children)
    return found


def _kotlin_declarations(root: Any, data: bytes) -> dict:
    found: dict = {}
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "function_declaration":
            name = next((child for child in node.children if child.type == "simple_identifier"), None)
            if name is not None:
                found.setdefault((_line(node), _text(data, name)), node)
                found.setdefault((_line(name), _text(data, name)), node)
        stack.extend(node.named_children)
    return found


class BranchCounter:
    """Parses each file once and reuses its declaration lookup across symbols."""

    def __init__(self) -> None:
        self._files: dict = {}

    def _load(self, path: str, source: str) -> Optional[tuple]:
        suffix = _suffix(path)
        if suffix == ".py":
            tree = _python_tree(source)
            return None if tree is None else (_python_branches, _python_declarations(tree))
        if suffix in _TS_SUFFIXES:
            parsed = _tree_sitter(suffix, source)
            return None if parsed is None else (_ts_branches, _ts_declarations(parsed[1], parsed[0]))
        if suffix == ".kt":
            parsed = _tree_sitter(suffix, source)
            return None if parsed is None else (_kotlin_branches, _kotlin_declarations(parsed[1], parsed[0]))
        return None

    def count(self, path: str, source: str, start_line: int, name: str) -> Optional[int]:
        if path not in self._files:
            self._files[path] = self._load(path, source)
        loaded = self._files[path]
        if loaded is None:
            return None
        counter, declarations = loaded
        node = declarations.get((start_line, name.rsplit(".", 1)[-1]))
        return None if node is None else counter(node)


def branch_count(path: str, source: str, start_line: int, name: str) -> Optional[int]:
    return BranchCounter().count(path, source, start_line, name)


_PY_STRONG = frozenset("""assertEqual assertEquals assertIs assertIsNone assertDictEqual assertListEqual assertCountEqual
assertSequenceEqual assertTupleEqual assertSetEqual assertMultiLineEqual assertAlmostEqual assertRaises assertRaisesRegex
assert_called_once_with assert_called_with assert_any_call assert_has_calls assert_not_called""".split())
_PY_WEAK = frozenset("""assertTrue assertFalse assertIsNotNone assertIn assertNotIn assertGreater assertGreaterEqual assertLess
assertLessEqual assertNotEqual assertIsInstance assertIsNot assertNotAlmostEqual assertRegex assert_called assert_called_once""".split())
_PY_PREFIXES = ("assert", "check", "verify", "expect")
_PY_MOCK_CLASSES = frozenset({"Mock", "MagicMock", "AsyncMock", "NonCallableMock", "PropertyMock", "create_autospec"})
_PY_PATCH = frozenset({"patch", "patch.object", "patch.dict", "patch.multiple"})
_PY_PATCH_PREFIXES = ("unittest.mock.", "mock.", "mocker.")
_PY_MONKEYPATCH = frozenset({"monkeypatch.setattr", "monkeypatch.setitem"})
_PY_SKIP_DECORATORS = frozenset(
    [f"pytest.mark.{name}" for name in ("skip", "skipif", "xfail")] + [f"mark.{name}" for name in ("skip", "skipif", "xfail")]
    + [prefix + name for name in ("skip", "skipIf", "skipUnless", "expectedFailure") for prefix in ("unittest.", "")])


def _py_dotted(node: Any) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _py_dotted(node.value)
        return None if base is None else base + "." + node.attr
    return None


def _py_last(node: Any) -> Optional[str]:
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None


def _py_patch_name(dotted: Optional[str]) -> bool:
    if dotted is None:
        return False
    for prefix in _PY_PATCH_PREFIXES:
        if dotted.startswith(prefix):
            dotted = dotted[len(prefix):]
            break
    return dotted in _PY_PATCH


def _py_is_mock_call(call: ast.Call) -> bool:
    dotted = _py_dotted(call.func)
    return _py_last(call.func) in _PY_MOCK_CLASSES or _py_patch_name(dotted) or dotted in _PY_MONKEYPATCH


def _py_decorator_target(decorator: ast.expr) -> ast.expr:
    return decorator.func if isinstance(decorator, ast.Call) else decorator


def _py_bare_mock_decorators(decorators: list) -> int:
    return sum(1 for item in decorators if not isinstance(item, ast.Call) and _py_patch_name(_py_dotted(item)))


def _py_mocks_in(nodes: Iterable[ast.AST]) -> int:
    return sum(1 for root in nodes for node in ast.walk(root) if isinstance(node, ast.Call) and _py_is_mock_call(node))


def _py_skips(decorators: list) -> bool:
    return any(_py_dotted(_py_decorator_target(item)) in _PY_SKIP_DECORATORS for item in decorators)


def _py_assertions(function: ast.AST) -> tuple[int, int]:
    strong = weak = 0
    stack = [function]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Assert):
            test = node.test
            if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], (ast.Eq, ast.Is)):
                strong += 1
            else:
                weak += 1
            continue
        stack.extend(ast.iter_child_nodes(node))
        if isinstance(node, ast.Call):
            last = _py_last(node.func)
            if last is None:
                continue
            if _py_dotted(node.func) in ("pytest.raises", "raises") or last in _PY_STRONG:
                strong += 1
            elif last in _PY_WEAK:
                weak += 1
            elif last.startswith(_PY_PREFIXES):
                strong += 1
    return strong, weak


def _py_calls_skip(function: ast.AST) -> bool:
    return any(isinstance(node, ast.Call) and (_py_dotted(node.func) == "pytest.skip" or _py_last(node.func) == "skipTest") for node in ast.walk(function))


def _py_module_mocks(tree: ast.Module) -> int:
    total = 0
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, _PY_NESTED):
            continue
        if isinstance(node, ast.Call) and _py_is_mock_call(node):
            total += 1
        stack.extend(ast.iter_child_nodes(node))
    return total


def _python_cases(source: str) -> Optional[list]:
    tree = _python_tree(source)
    if tree is None:
        return None
    module_mocks = _py_module_mocks(tree)
    cases: list = []

    def visit(body: list, classes: tuple) -> None:
        for statement in body:
            if isinstance(statement, ast.ClassDef):
                visit(statement.body, classes + (statement,))
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)) and statement.name.startswith("test"):
                strong, weak = _py_assertions(statement)
                class_decorators = [item for owner in classes for item in owner.decorator_list]
                mocks = (module_mocks + _py_mocks_in([statement]) + _py_bare_mock_decorators(statement.decorator_list)
                         + _py_mocks_in(class_decorators) + _py_bare_mock_decorators(class_decorators))
                skipped = _py_skips(statement.decorator_list) or _py_skips(class_decorators) or _py_calls_skip(statement)
                cases.append((".".join([owner.name for owner in classes] + [statement.name]), strong, weak, mocks, skipped))

    visit(tree.body, ())
    return cases


_TS_CASE_ROOTS = frozenset({"it", "test", "xit", "xtest", "fit"})
_TS_SUITE_ROOTS = frozenset({"describe", "xdescribe", "fdescribe"})
_TS_MODIFIERS = frozenset({"only", "skip", "todo", "each", "concurrent", "failing", "sequential", "fails"})
_TS_STRONG_MATCHERS = frozenset("""toBe toEqual toStrictEqual toBeNull toBeUndefined toBeNaN toBeCloseTo toHaveLength toHaveBeenCalledWith
toBeCalledWith toHaveBeenLastCalledWith toHaveBeenNthCalledWith toHaveBeenCalledTimes toHaveReturnedWith toMatchSnapshot
toMatchInlineSnapshot toThrowErrorMatchingSnapshot toContainEqual""".split())
_TS_WEAK_MATCHERS = frozenset("""toBeDefined toBeTruthy toBeFalsy toMatchObject toHaveBeenCalled toBeCalled toHaveReturned toContain
toBeGreaterThan toBeGreaterThanOrEqual toBeLessThan toBeLessThanOrEqual toBeInstanceOf toMatch""".split())
_TS_NEGATION_STRONG = frozenset({"toHaveBeenCalled", "toBeCalled"})
_TS_NODE_STRONG = frozenset({"strictEqual", "deepStrictEqual", "equal", "deepEqual", "throws", "rejects"})
_TS_NODE_WEAK = frozenset({"ok", "notEqual", "notStrictEqual", "notDeepEqual"})
_TS_MOCK_CALLS = frozenset({"jest.mock", "jest.fn", "jest.spyOn", "jest.doMock", "vi.mock", "vi.fn", "vi.spyOn"})


def _ts_parts(node: Any, data: bytes) -> Optional[list]:
    if node.type == "identifier":
        return [_text(data, node)]
    if node.type == "member_expression":
        base = node.child_by_field_name("object")
        prop = node.child_by_field_name("property")
        parts = _ts_parts(base, data) if base is not None else None
        return None if parts is None or prop is None else parts + [_text(data, prop)]
    return None


def _ts_classify(call: Any, data: bytes) -> Optional[tuple]:
    """Returns (kind, parts) for it/test/describe calls; the `.each(table)` binding call itself is not a test call."""
    function = call.child_by_field_name("function")
    if function is None:
        return None
    if function.type == "call_expression":
        inner = function.child_by_field_name("function")
        parts = _ts_parts(inner, data) if inner is not None else None
        if not parts or parts[-1] != "each":
            return None
        parts = parts[:-1]
    else:
        parts = _ts_parts(function, data)
        if parts and parts[-1] == "each":
            return None
    if not parts or any(item not in _TS_MODIFIERS for item in parts[1:]):
        return None
    kind = "case" if parts[0] in _TS_CASE_ROOTS else "suite" if parts[0] in _TS_SUITE_ROOTS else None
    arguments = call.child_by_field_name("arguments")
    if kind is None or arguments is None or arguments.type != "arguments" or not arguments.named_children:
        return None
    return kind, parts


def _ts_title(call: Any, data: bytes) -> str:
    first = call.child_by_field_name("arguments").named_children[0]
    return _text(data, first)[1:-1] if first.type in ("string", "template_string") else "<dynamic>"


def _ts_callback(call: Any) -> Optional[Any]:
    callbacks = [item for item in call.child_by_field_name("arguments").named_children if item.type in _TS_FUNCTION_VALUES]
    return callbacks[-1] if callbacks else None


def _ts_scan(root: Any, data: bytes, visit: Any) -> None:
    """Visits calls under root, skipping nested it/test/describe calls, which own their scope."""
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "call_expression":
            if node.id != root.id and _ts_classify(node, data) is not None:
                continue
            visit(node)
        stack.extend(node.named_children)


def _ts_matcher(call: Any, data: bytes) -> Optional[str]:
    function = call.child_by_field_name("function")
    if function is None or function.type != "member_expression":
        return None
    matcher = _text(data, function.child_by_field_name("property"))
    negated = False
    node = function.child_by_field_name("object")
    while node is not None and node.type == "member_expression":
        negated = negated or _text(data, node.child_by_field_name("property")) == "not"
        node = node.child_by_field_name("object")
    if node is None or node.type != "call_expression":
        return None
    root = node.child_by_field_name("function")
    if root is None or (_ts_parts(root, data) or [None])[0] != "expect":
        return None
    count = len(call.child_by_field_name("arguments").named_children) if call.child_by_field_name("arguments") is not None else 0
    if negated:
        return "strong" if matcher in _TS_NEGATION_STRONG else "weak"
    if matcher in ("toThrow", "toThrowError"):
        return "strong" if count else "weak"
    if matcher == "toHaveProperty":
        return "strong" if count >= 2 else "weak"
    return "weak" if matcher in _TS_WEAK_MATCHERS else "strong"


def _ts_assertion(call: Any, data: bytes) -> Optional[str]:
    function = call.child_by_field_name("function")
    if function is None:
        return None
    if function.type == "identifier" and _text(data, function) == "assert":
        return "weak"
    if function.type == "member_expression":
        base, prop = function.child_by_field_name("object"), function.child_by_field_name("property")
        if base is not None and base.type == "identifier" and _text(data, base) == "assert":
            name = _text(data, prop)
            return "strong" if name in _TS_NODE_STRONG else "weak" if name in _TS_NODE_WEAK else None
    return _ts_matcher(call, data)


def _typescript_cases(suffix: str, source: str) -> Optional[list]:
    parsed = _tree_sitter(suffix, source)
    if parsed is None:
        return None
    data, root = parsed

    def mock_total(scope: Any) -> int:
        found = [0]

        def visit(call: Any) -> None:
            function = call.child_by_field_name("function")
            if function is not None and ".".join(_ts_parts(function, data) or ()) in _TS_MOCK_CALLS:
                found[0] += 1
        _ts_scan(scope, data, visit)
        return found[0]

    top_mocks = mock_total(root)
    suite_mocks: dict = {}
    cases: list = []
    stack = [(child, ()) for child in reversed(root.named_children)]
    while stack:
        node, chain = stack.pop()
        if node.type == "call_expression":
            info = _ts_classify(node, data)
            if info is not None and info[0] == "suite":
                parts = info[1]
                callback = _ts_callback(node)
                mocks = 0
                if callback is not None:
                    mocks = suite_mocks.setdefault(callback.id, mock_total(callback))
                skipped = parts[0] == "xdescribe" or "skip" in parts[1:]
                chain = chain + ((_ts_title(node, data), skipped, mocks),)
            elif info is not None:
                counts = {"strong": 0, "weak": 0}

                def assertion(call: Any) -> None:
                    verdict = _ts_assertion(call, data)
                    if verdict:
                        counts[verdict] += 1
                _ts_scan(node, data, assertion)
                parts = info[1]
                skipped = parts[0] in ("xit", "xtest") or "skip" in parts[1:] or "todo" in parts[1:] or any(item[1] for item in chain)
                name = " > ".join([item[0] for item in chain] + [_ts_title(node, data)])
                cases.append((name, counts["strong"], counts["weak"], top_mocks + sum(item[2] for item in chain) + mock_total(node), skipped))
                continue
        stack.extend((child, chain) for child in reversed(node.named_children))
    return cases


_KT_STRONG = frozenset("assertEquals assertSame assertContentEquals assertArrayEquals assertNull assertFailsWith assertThrows verify coVerify verifyOrder verifySequence".split())
_KT_WEAK = frozenset("assertTrue assertFalse assertNotNull assertNotEquals assertNotSame assertIs assertIsNot assertContains assertFails".split())
_KT_CHAIN_WEAK = frozenset("isNotNull isTrue isFalse isNotEmpty contains isNotEqualTo isInstanceOf isGreaterThan isLessThan isAtLeast isAtMost".split())
_KT_PREFIXES = ("assert", "verify", "expect")
_KT_MOCKS = frozenset("mockk spyk mockkObject mockkStatic mockkConstructor every coEvery mock whenever".split())


def _kt_callee(call: Any, data: bytes) -> Optional[str]:
    callee = call.named_children[0] if call.named_children else None
    if callee is None:
        return None
    if callee.type == "simple_identifier":
        return _text(data, callee)
    if callee.type == "navigation_expression":
        suffix = callee.named_children[-1]
        name = next((child for child in suffix.named_children if child.type == "simple_identifier"), None)
        return None if name is None else _text(data, name)
    return None


def _kt_in_assert_that_chain(call: Any, data: bytes) -> bool:
    node = call.named_children[0] if call.named_children else None
    while node is not None:
        if node.type == "call_expression":
            if _kt_callee(node, data) == "assertThat":
                return True
        elif node.type != "navigation_expression":
            return False
        node = node.named_children[0] if node.named_children else None
    return False


def _kt_calls(root: Any) -> Iterator[Any]:
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "call_expression":
            yield node
        stack.extend(node.named_children)


def _kt_annotation_names(node: Any, data: bytes) -> set:
    from language_analyzers.kotlin.ast import annotations
    return {name.rsplit(".", 1)[-1] for name, _ in annotations(node, data)}


def _kotlin_cases(source: str) -> Optional[list]:
    parsed = _tree_sitter(".kt", source)
    if parsed is None:
        return None
    data, root = parsed
    from language_analyzers.kotlin.ast import declared_name
    setup_cache: dict = {}

    def class_setup(owner: Any) -> int:
        if owner.id not in setup_cache:
            total = 0
            body = next((child for child in owner.children if child.type == "class_body"), None)
            for member in body.named_children if body is not None else ():
                if member.type == "property_declaration" or (member.type == "function_declaration" and _kt_annotation_names(member, data) & {"Before", "BeforeEach"}):
                    total += sum(1 for call in _kt_calls(member) if _kt_callee(call, data) in _KT_MOCKS)
            setup_cache[owner.id] = total
        return setup_cache[owner.id]

    cases: list = []
    stack = [(root, ())]
    while stack:
        node, classes = stack.pop()
        for child in reversed(node.named_children):
            if child.type in ("class_declaration", "object_declaration"):
                body = next((item for item in child.children if item.type == "class_body"), None)
                if body is not None:
                    stack.append((body, classes + (child,)))
            elif child.type == "companion_object":
                stack.append((child, classes))
            elif child.type == "function_declaration" and "Test" in _kt_annotation_names(child, data):
                strong = weak = mocks = 0
                for call in _kt_calls(child):
                    name = _kt_callee(call, data)
                    if name in _KT_MOCKS:
                        mocks += 1
                    if name is None or name == "assertThat":
                        continue
                    if _kt_in_assert_that_chain(call, data):
                        parent = call.parent
                        if parent is not None and parent.type == "navigation_expression" and parent.named_children[0].id == call.id:
                            continue
                        weak, strong = (weak + 1, strong) if name in _KT_CHAIN_WEAK else (weak, strong + 1)
                    elif name in _KT_STRONG or (name not in _KT_WEAK and name.startswith(_KT_PREFIXES)):
                        strong += 1
                    elif name in _KT_WEAK:
                        weak += 1
                mocks += sum(class_setup(owner) for owner in classes)
                skipped = bool(_kt_annotation_names(child, data) & {"Ignore", "Disabled"}) or any(_kt_annotation_names(owner, data) & {"Ignore", "Disabled"} for owner in classes)
                names = [declared_name(owner, data) or "" for owner in classes] + [declared_name(child, data) or ""]
                cases.append((".".join(names), strong, weak, mocks, skipped))
    return cases


def _cases_in(path: str, source: str) -> Optional[list]:
    suffix = _suffix(path)
    if suffix not in _CASE_SUFFIXES:
        return None
    if suffix == ".py":
        return _python_cases(source)
    if suffix == ".kt":
        return _kotlin_cases(source)
    return _typescript_cases(suffix, source)


def test_case_table(contents: Mapping[str, str], test_paths: Iterable[str]) -> list[dict]:
    table = []
    for path in test_paths:
        source = contents.get(path)
        cases = _cases_in(path, source) if isinstance(source, str) else None
        seen: dict = {}
        for name, strong, weak, mocks, skipped in cases or ():
            base = f"file:{path}#{name}"
            seen[base] = seen.get(base, 0) + 1
            case_id = base if seen[base] == 1 else f"{base} [{seen[base]}]"
            table.append({"id": case_id, "file": "file:" + path, "name": name, "strong_assertions": strong,
                          "weak_assertions": weak, "mocks": mocks, "skipped": skipped})
    return sorted(table, key=lambda item: item["id"])


def _short_name(node: dict) -> str:
    return (node["metadata"].get("name") or node["label"]).rsplit(".", 1)[-1]


def _reach(starts: Iterable[str], adjacency: dict) -> set:
    seen = set(starts)
    queue = list(seen)
    while queue:
        for target in adjacency.get(queue.pop(), ()):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def test_reach(architecture: Any) -> dict[str, str]:
    from bottlenecks.core import _category
    details = architecture.details
    node_files = details["node_files"]
    nodes = {node["id"]: node for node in details["nodes"]}
    file_nodes = details["file_nodes"]
    categories = {node.id: _category(node) for node in architecture.nodes if node.id in file_nodes}
    constructors: dict = {}
    for edge in details["edges"]:
        if edge["relation"] in ("CONTAINS", "DECLARES"):
            child = nodes.get(edge["to_id"])
            if child is not None and _short_name(child) in _CONSTRUCTORS:
                constructors.setdefault(edge["from_id"], []).append(edge["to_id"])
    confirmed: dict = {}
    anywhere: dict = {}
    entrypoints: set = set()
    for edge in details["edges"]:
        source = edge["from_id"]
        targets = candidate_targets(edge)
        if nodes[source].get("provenance", "") not in _LANGUAGE_PROVENANCE:
            entrypoints.update(targets)
        if edge["relation"] not in _FOLLOWED:
            continue
        if edge["relation"] == "INSTANTIATES":
            targets = targets + tuple(item for target in targets for item in constructors.get(target, ()))
        anywhere.setdefault(source, []).extend(targets)
        if edge.get("confidence") in _CONFIRMED_CONFIDENCE and edge.get("resolution") in _CONFIRMED_RESOLUTION:
            confirmed.setdefault(source, []).extend(targets)
    seeds = [node_id for node_id in nodes if categories.get(node_files[node_id]) == "test"]
    tested = _reach(seeds, confirmed)
    possible = _reach(seeds + [item for item in entrypoints if item in nodes], anywhere)
    result = {}
    for node_id, node in nodes.items():
        file = node_files[node_id]
        if node["kind"] in _REACH_KINDS and categories.get(file) == "production":
            result[node_id] = "tested" if node_id in tested else "uncertain" if node_id in possible else "untested"
    return result
