"""
Small helpers over the tree-sitter Kotlin grammar (via tree-sitter-language-pack).
Detection is heuristic name/annotation matching, not full type resolution — the same
tradeoff FastAPIAnalyzer already makes for Python (e.g. matching "FastAPI" in call_name)
since Kotlin wildcard imports make exact resolution impossible from syntax alone anyway.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PARSER = None


def get_kotlin_parser():
    global _PARSER
    if _PARSER is None:
        try:
            from tree_sitter_language_pack import get_parser
        except ImportError as exc:
            raise ImportError(
                "Android analysis requires the 'tree-sitter' and 'tree-sitter-language-pack' "
                "packages. Install them with: pip install -r requirements.txt"
            ) from exc
        _PARSER = get_parser("kotlin")
    return _PARSER


class KotlinParseCache:
    """Shared across AndroidAnalyzer/KotlinAnalyzer so files discovered by both are
    read and parsed at most once per cache instance."""

    def __init__(self) -> None:
        self._cache: Dict[Path, Tuple[bytes, Any]] = {}

    def read_and_parse(self, path: Path) -> Tuple[bytes, Any]:
        cached = self._cache.get(path)
        if cached is not None:
            return cached
        source = path.read_bytes()
        root = get_kotlin_parser().parse(source).root_node
        self._cache[path] = (source, root)
        return self._cache[path]

    def parse_snapshot(self, path: Path, source: bytes) -> Tuple[bytes, Any]:
        cached = self._cache.get(path)
        if cached is not None and cached[0] == source:
            return cached
        parsed = (source, get_kotlin_parser().parse(source).root_node)
        self._cache[path] = parsed
        return parsed


def node_text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def start_line(node) -> int:
    return node.start_point[0] + 1


def end_line(node) -> int:
    return node.end_point[0] + 1


def top_level_declarations(root) -> List[Any]:
    return [
        child for child in root.children
        if child.type in ("function_declaration", "class_declaration", "object_declaration")
    ]


def nested_declarations(node) -> List[Any]:
    """Declarations directly inside a class/object/interface body (one level, not recursive)."""
    body = class_body(node)
    if body is None:
        return []
    return [
        child for child in body.children
        if child.type in ("function_declaration", "class_declaration", "object_declaration")
    ]


def class_body(node) -> Optional[Any]:
    for child in node.children:
        if child.type == "class_body":
            return child
    return None


def modifiers_node(node) -> Optional[Any]:
    for child in node.children:
        if child.type == "modifiers":
            return child
    return None


def _annotation_type_node(annotation_node) -> Optional[Any]:
    for child in annotation_node.children:
        if child.type == "user_type":
            return child
        if child.type == "constructor_invocation":
            for grandchild in child.children:
                if grandchild.type == "user_type":
                    return grandchild
    return None


def annotations(node, source: bytes) -> List[Tuple[str, Any]]:
    """Return [(simple_name, annotation_node), ...] for a declaration's own modifiers."""
    mods = modifiers_node(node)
    if mods is None:
        return []
    result = []
    for child in mods.children:
        if child.type != "annotation":
            continue
        type_node = _annotation_type_node(child)
        if type_node is not None:
            result.append((node_text(source, type_node), child))
    return result


def has_annotation(node, source: bytes, name: str) -> bool:
    return any(n == name for n, _ in annotations(node, source))


def find_annotation(node, source: bytes, name: str) -> Optional[Any]:
    for n, ann_node in annotations(node, source):
        if n == name:
            return ann_node
    return None


def annotation_args_text(annotation_node, source: bytes) -> str:
    for child in annotation_node.children:
        if child.type == "constructor_invocation":
            for grandchild in child.children:
                if grandchild.type == "value_arguments":
                    return node_text(source, grandchild)
    return ""


def annotation_first_string_arg(annotation_node, source: bytes) -> Optional[str]:
    match = re.search(r'"([^"]*)"', annotation_args_text(annotation_node, source))
    return match.group(1) if match else None


def annotation_class_literal_args(annotation_node, source: bytes) -> List[str]:
    """Names referenced as `Foo::class` inside an annotation's arguments, e.g.
    @Database(entities = [GreetingEntity::class]) -> ["GreetingEntity"]."""
    return re.findall(r"(\w+)::class", annotation_args_text(annotation_node, source))


def declared_name(node, source: bytes) -> Optional[str]:
    for child in node.children:
        if child.type in ("type_identifier", "simple_identifier"):
            return node_text(source, child)
    return None


def is_interface(node) -> bool:
    return any(child.type == "interface" for child in node.children)


def supertype_names(node, source: bytes) -> List[str]:
    names = []
    for child in node.children:
        if child.type != "delegation_specifier":
            continue
        for grandchild in child.children:
            if grandchild.type == "constructor_invocation":
                for c in grandchild.children:
                    if c.type == "user_type":
                        names.append(node_text(source, c))
            elif grandchild.type == "user_type":
                names.append(node_text(source, grandchild))
    return names


def receiver_type_name(node, source: bytes) -> Optional[str]:
    for child in node.children:
        if child.type != "receiver_type":
            continue
        for grandchild in child.children:
            user_type = None
            if grandchild.type == "user_type":
                user_type = grandchild
            elif grandchild.type == "nullable_type":
                for c in grandchild.children:
                    if c.type == "user_type":
                        user_type = c
                        break
            if user_type is not None:
                for c in user_type.children:
                    if c.type == "type_identifier":
                        return node_text(source, c)
    return None


def primary_constructor(node) -> Optional[Any]:
    for child in node.children:
        if child.type == "primary_constructor":
            return child
    return None


def class_parameters(ctor_node, source: bytes) -> List[Dict[str, Any]]:
    params = []
    for child in ctor_node.children:
        if child.type != "class_parameter":
            continue
        name = None
        type_name = None
        for c in child.children:
            if c.type == "simple_identifier":
                name = node_text(source, c)
            elif c.type == "user_type":
                type_name = node_text(source, c)
        params.append({
            "name": name,
            "type": type_name,
            "annotations": [n for n, _ in annotations(child, source)],
        })
    return params


def function_params(func_node, source: bytes) -> List[Dict[str, Any]]:
    params = []
    for child in func_node.children:
        if child.type != "function_value_parameters":
            continue
        for c in child.children:
            if c.type != "parameter":
                continue
            name = None
            type_name = None
            for gc in c.children:
                if gc.type == "simple_identifier" and name is None:
                    name = node_text(source, gc)
                elif gc.type == "user_type":
                    type_name = node_text(source, gc)
            params.append({"name": name, "type": type_name})
    return params


def function_return_type(func_node, source: bytes) -> Optional[str]:
    return function_return_types(func_node, source)[0]


def function_return_types(func_node, source: bytes) -> Tuple[Optional[str], Optional[str]]:
    """(base_type, generic_inner_type). For `List<Foo>` this is ("List", "Foo");
    for `Foo` it is ("Foo", None)."""
    seen_params = False
    for child in func_node.children:
        if child.type == "function_value_parameters":
            seen_params = True
            continue
        if seen_params and child.type == "user_type":
            base = None
            inner = None
            for c in child.children:
                if c.type == "type_identifier":
                    base = node_text(source, c)
                elif c.type == "type_arguments":
                    for proj in c.children:
                        if proj.type == "type_projection":
                            for ut in proj.children:
                                if ut.type == "user_type":
                                    for ti in ut.children:
                                        if ti.type == "type_identifier":
                                            inner = node_text(source, ti)
            return base or node_text(source, child), inner
        if seen_params and child.type == "function_body":
            break
    return None, None


def call_expressions(node, source: bytes) -> List[Dict[str, Any]]:
    """Every call in a subtree, as [{"name": callee, "type_args": [...]}].
    Bare calls (`foo()`) and generic calls (`foo<Bar>()`) are named by their own identifier;
    method calls (`x.foo()`) are named by the method, not the receiver."""
    results: List[Dict[str, Any]] = []

    def walk(n):
        if n.type == "call_expression":
            callee_node = None
            for c in n.children:
                if c.type == "navigation_expression":
                    suffixes = [g for g in c.children if g.type == "navigation_suffix"]
                    if suffixes:
                        for g in suffixes[-1].children:
                            if g.type == "simple_identifier":
                                callee_node = g
                    break
                if c.type == "simple_identifier":
                    callee_node = c
                    break
            type_args = []
            for c in n.children:
                if c.type == "call_suffix":
                    for gc in c.children:
                        if gc.type == "type_arguments":
                            for proj in gc.children:
                                if proj.type == "type_projection":
                                    for ut in proj.children:
                                        if ut.type == "user_type":
                                            for ti in ut.children:
                                                if ti.type == "type_identifier":
                                                    type_args.append(node_text(source, ti))
            if callee_node is not None:
                results.append({"name": node_text(source, callee_node), "type_args": type_args})
        for c in n.children:
            walk(c)

    walk(node)
    return results
