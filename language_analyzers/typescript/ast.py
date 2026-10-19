"""Thin helpers over the tree-sitter TypeScript/TSX/JavaScript grammars, mirroring
language_analyzers/kotlin/ast.py. Name resolution stays syntactic: the grammars give
structure, not types, so a call to an unimported name is matched by name alone."""

from typing import Any, Dict, Iterator, List, Optional

_PARSERS: Dict[str, Any] = {}

GRAMMAR_BY_SUFFIX = {
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
}

DEFINITION_TYPES = {
    "class_declaration",
    "abstract_class_declaration",
    "interface_declaration",
    "enum_declaration",
    "function_declaration",
    "generator_function_declaration",
    "function_expression",
    "arrow_function",
    "method_definition",
}


def get_parser(grammar: str):
    if grammar not in _PARSERS:
        try:
            from tree_sitter_language_pack import get_parser as _get
        except ImportError as exc:
            raise ImportError(
                "TypeScript analysis requires the 'tree-sitter' and 'tree-sitter-language-pack' "
                "packages. Install them with: pip install -r requirements.txt"
            ) from exc
        _PARSERS[grammar] = _get(grammar)
    return _PARSERS[grammar]


def parser_for_suffix(suffix: str):
    return get_parser(GRAMMAR_BY_SUFFIX.get(suffix, "typescript"))


def node_text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def start_line(node) -> int:
    return node.start_point[0] + 1


def end_line(node) -> int:
    return node.end_point[0] + 1


def child_of_type(node, *types) -> Optional[Any]:
    for child in node.named_children:
        if child.type in types:
            return child
    return None


def children_of_type(node, *types) -> List[Any]:
    return [child for child in node.named_children if child.type in types]


def descendants(node) -> Iterator[Any]:
    stack = list(node.named_children)
    while stack:
        current = stack.pop()
        yield current
        stack.extend(current.named_children)


def descendants_excluding_definitions(node) -> Iterator[Any]:
    """Walk a definition's own body, stopping at nested definitions because those are
    separate symbols and their calls must not be attributed to the enclosing one."""
    stack = list(node.named_children)
    while stack:
        current = stack.pop()
        yield current
        if current.type in DEFINITION_TYPES:
            continue
        stack.extend(current.named_children)


def call_argument(node, index: int) -> Optional[Any]:
    arguments = node.child_by_field_name("arguments")
    if arguments is None:
        return None
    values = [child for child in arguments.named_children if child.type != "comment"]
    return values[index] if index < len(values) else None


def is_literal_key(node) -> bool:
    if node is None:
        return False
    if node.type == "template_string":
        return child_of_type(node, "template_substitution") is None
    return node.type in ("string", "number")


def string_literal_value(source: bytes, node) -> Optional[str]:
    if node is None or node.type not in ("string", "template_string"):
        return None
    fragment = child_of_type(node, "string_fragment")
    if fragment is not None:
        return node_text(source, fragment)
    text = node_text(source, node)
    return text[1:-1] if len(text) >= 2 else None


def declared_name(source: bytes, node) -> Optional[str]:
    named = child_of_type(node, "identifier", "type_identifier", "property_identifier")
    return node_text(source, named) if named is not None else None


def callee_name(source: bytes, call_node) -> Optional[str]:
    function = call_node.child_by_field_name("function")
    if function is None:
        return None
    if function.type in ("identifier", "property_identifier"):
        return node_text(source, function)
    if function.type == "member_expression":
        prop = function.child_by_field_name("property")
        return node_text(source, prop) if prop is not None else None
    return None


def callee_receiver(source: bytes, call_node) -> Optional[str]:
    function = call_node.child_by_field_name("function")
    if function is None or function.type != "member_expression":
        return None
    obj = function.child_by_field_name("object")
    if obj is None:
        return None
    if obj.type in ("identifier", "this"):
        return node_text(source, obj)
    if obj.type == "member_expression":
        prop = obj.child_by_field_name("property")
        return node_text(source, prop) if prop is not None else None
    return None


def type_names(source: bytes, node) -> List[str]:
    if node is None:
        return []
    names = []
    for item in [node] + list(descendants(node)):
        if item.type in ("type_identifier", "identifier"):
            names.append(node_text(source, item))
    return names
