from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from language_analyzers.core.graph_models import SourceSpan

from . import ast as ts

AXIOS_VERBS = ("get", "post", "put", "patch", "delete", "head", "options")
_ABSOLUTE_URL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


@dataclass(frozen=True)
class HttpCallSite:
    source_id: str
    http_method: Optional[str]
    path: Optional[str]
    evidence: SourceSpan


def _literal(source: bytes, node) -> Optional[str]:
    """Raw text of a string or template string; template interpolations stay verbatim
    because route normalization maps them to path parameters."""
    if node is None or node.type not in ("string", "template_string"):
        return None
    text = ts.node_text(source, node)
    return text[1:-1] if len(text) >= 2 else None


def _static_literal(source: bytes, node) -> Optional[str]:
    if node is None:
        return None
    if node.type == "template_string" and ts.children_of_type(node, "template_substitution"):
        return None
    return _literal(source, node)


def _arguments(call) -> List[Any]:
    arguments = call.child_by_field_name("arguments")
    if arguments is None:
        return []
    return [child for child in arguments.named_children if child.type != "comment"]


def _object_properties(source: bytes, node) -> Tuple[Dict[str, Any], bool]:
    properties: Dict[str, Any] = {}
    has_spread = False
    for child in node.named_children:
        if child.type == "pair":
            key = child.child_by_field_name("key")
            if key is None:
                continue
            name = ts.node_text(source, key)
            if key.type == "string":
                name = name[1:-1]
            properties[name] = child.child_by_field_name("value")
        elif child.type == "shorthand_property_identifier":
            properties[ts.node_text(source, child)] = None
        elif child.type == "spread_element":
            has_spread = True
    return properties, has_spread


def _instance_base(source: bytes, value) -> Optional[str]:
    if value is None or value.type != "call_expression":
        return None
    function = value.child_by_field_name("function")
    if function is None or ts.node_text(source, function) != "axios.create":
        return None
    arguments = _arguments(value)
    if not arguments or arguments[0].type != "object":
        return None
    properties, _spread = _object_properties(source, arguments[0])
    return _literal(source, properties.get("baseURL"))


def _module_instances(module) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Returns (module-scope instances, exported instances keyed by export name; the
    default export uses the key 'default')."""
    source = module.source
    local: Dict[str, str] = {}
    exported: Dict[str, str] = {}

    def declarations(statement):
        for declarator in ts.children_of_type(statement, "variable_declarator"):
            name_node = declarator.child_by_field_name("name")
            if name_node is None or name_node.type != "identifier":
                continue
            base = _instance_base(source, declarator.child_by_field_name("value"))
            if base is not None:
                yield ts.node_text(source, name_node), base

    for statement in module.tree.root_node.named_children:
        if statement.type in ("lexical_declaration", "variable_declaration"):
            local.update(declarations(statement))
    for statement in module.tree.root_node.named_children:
        if statement.type != "export_statement" or ts.child_of_type(statement, "string") is not None:
            continue
        declaration = ts.child_of_type(statement, "lexical_declaration", "variable_declaration")
        if declaration is not None:
            for name, base in declarations(declaration):
                local[name] = base
                exported[name] = base
            continue
        clause = ts.child_of_type(statement, "export_clause")
        if clause is not None:
            for entry in ts.children_of_type(clause, "export_specifier"):
                original = entry.child_by_field_name("name")
                alias = entry.child_by_field_name("alias")
                if original is None:
                    continue
                name = ts.node_text(source, original)
                if name in local:
                    exported[ts.node_text(source, alias) if alias is not None else name] = local[name]
            continue
        if ts.node_text(source, statement).lstrip().startswith("export default"):
            value = statement.child_by_field_name("value")
            if value is None:
                continue
            if value.type == "identifier" and ts.node_text(source, value) in local:
                exported["default"] = local[ts.node_text(source, value)]
            else:
                base = _instance_base(source, value)
                if base is not None:
                    exported["default"] = base
    return local, exported


def _join(base: str, url: str) -> str:
    if not base or _ABSOLUTE_URL.match(url):
        return url
    if not url:
        return base
    return base.rstrip("/") + "/" + url.lstrip("/")


def _config_call(source: bytes, arguments: List[Any]) -> Tuple[Optional[str], Optional[str]]:
    if not arguments or arguments[0].type != "object":
        return None, None
    properties, has_spread = _object_properties(source, arguments[0])
    url = _literal(source, properties.get("url"))
    if "method" in properties:
        method = _static_literal(source, properties["method"])
        method = method.upper() if method is not None else None
    else:
        method = None if has_spread else "GET"
    return method, url


def _fetch_call(source: bytes, arguments: List[Any]) -> Tuple[Optional[str], Optional[str]]:
    url = _literal(source, arguments[0]) if arguments else None
    if len(arguments) < 2:
        return "GET", url
    init = arguments[1]
    if init.type != "object":
        return None, url
    properties, has_spread = _object_properties(source, init)
    if "method" in properties:
        method = _static_literal(source, properties["method"])
        return (method.upper() if method is not None else None), url
    return (None if has_spread else "GET"), url


def collect_http_calls(
    modules: Mapping[str, Any],
    resolve_import: Callable[[Any, str], Optional[str]],
    function_ids: Mapping[str, Mapping[Tuple[int, int], str]],
) -> List[HttpCallSite]:
    """`modules` are analyzer modules exposing id, file_key, path, source, tree and imports;
    `function_ids` maps (start_byte, end_byte) of each function or method body to its graph node id."""
    instances = {key: _module_instances(module) for key, module in modules.items()}
    found: List[Tuple[str, int, HttpCallSite]] = []
    for file_key in sorted(modules):
        module = modules[file_key]
        local, _exported = instances[file_key]
        visible: Dict[str, str] = dict(local)
        for name, binding in module.imports.items():
            if binding.is_namespace or name in visible:
                continue
            target_key = resolve_import(module.path, binding.specifier)
            if target_key is None or target_key not in instances:
                continue
            base = instances[target_key][1].get(binding.imported_name or "default")
            if base is not None:
                visible[name] = base
        for call in ts.descendants(module.tree.root_node):
            if call.type != "call_expression":
                continue
            parsed = _parse_call(module.source, call, visible)
            if parsed is None:
                continue
            method, url, base = parsed
            path = _join(base, url) if url is not None else None
            span = SourceSpan(file_key, ts.start_line(call), ts.end_line(call))
            site = HttpCallSite(_enclosing(module, call, function_ids.get(file_key, {})), method, path, span)
            found.append((file_key, call.start_byte, site))
    found.sort(key=lambda item: (item[0], item[1]))
    return [site for _key, _offset, site in found]


def _parse_call(source: bytes, call, instances: Mapping[str, str]):
    function = call.child_by_field_name("function")
    if function is None:
        return None
    arguments = _arguments(call)
    if function.type == "identifier":
        name = ts.node_text(source, function)
        if name == "fetch":
            method, url = _fetch_call(source, arguments)
            return method, url, ""
        if name == "axios":
            method, url = _config_call(source, arguments)
            return method, url, ""
        if name in instances:
            method, url = _config_call(source, arguments)
            return method, url, instances[name]
        return None
    if function.type != "member_expression":
        return None
    receiver = function.child_by_field_name("object")
    prop = function.child_by_field_name("property")
    if receiver is None or prop is None or receiver.type != "identifier":
        return None
    receiver_name, member = ts.node_text(source, receiver), ts.node_text(source, prop)
    if receiver_name == "axios":
        base = ""
    elif receiver_name in instances:
        base = instances[receiver_name]
    else:
        return None
    if member in AXIOS_VERBS:
        url = _literal(source, arguments[0]) if arguments else None
        return member.upper(), url, base
    if member == "request":
        method, url = _config_call(source, arguments)
        return method, url, base
    return None


def _enclosing(module, call, function_ids: Mapping[Tuple[int, int], str]) -> str:
    node = call.parent
    while node is not None:
        found = function_ids.get((node.start_byte, node.end_byte))
        if found is not None:
            return found
        node = node.parent
    return module.id
