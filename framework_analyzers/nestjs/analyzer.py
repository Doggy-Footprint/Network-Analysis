from __future__ import annotations

import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from language_analyzers.core.graph_models import SourceSpan
from language_analyzers.typescript import ast as ts
from language_analyzers.typescript.analyzer import IGNORED_DIRECTORIES, SOURCE_EXTENSIONS

from .models import NestJSDeclaration, NestJSDiagnostic, NestJSProjectArchitecture, NestJSReference

_HTTP = {name: name.upper() for name in ("Get", "Post", "Put", "Delete", "Patch", "Options", "Head")}
_KINDS = {"Module": "module", "Controller": "controller", "Injectable": "provider"}
_CLASS_TYPES = {"class_declaration", "abstract_class_declaration"}


@dataclass
class _Binding:
    package: str
    imported: str
    namespace: bool = False


@dataclass
class _File:
    key: str
    source: bytes
    tree: Any
    imports: Dict[str, List[_Binding]] = field(default_factory=lambda: defaultdict(list))
    classes: Dict[str, List[Any]] = field(default_factory=lambda: defaultdict(list))
    other_names: set[str] = field(default_factory=set)
    defaults: List[str] = field(default_factory=list)
    exported: set[str] = field(default_factory=set)
    decorators: Dict[int, List[Any]] = field(default_factory=dict)


def _text(file: _File, node: Any) -> str:
    return ts.node_text(file.source, node)


def _span(file: _File, node: Any) -> SourceSpan:
    return SourceSpan(file.key, ts.start_line(node), ts.end_line(node), node.start_point.column, node.end_point.column)


def _children(node: Any, *types: str) -> List[Any]:
    return [child for child in node.named_children if child.type in types]


def _normalize(*parts: str) -> str:
    return "/" + "/".join(seg for part in parts for seg in part.split("/") if seg)


def _literal(file: _File, node: Any) -> Optional[str]:
    if node is None or node.type not in ("string", "template_string"):
        return None
    if node.type == "template_string" and any(c.type == "template_substitution" for c in node.named_children):
        return None
    return ts.string_literal_value(file.source, node)


class NestJSAnalyzer:
    def __init__(self, project_path, snapshot=None):
        self.snapshot = snapshot
        if snapshot is None:
            self.project_path = Path(project_path).resolve()
        else:
            supplied = Path(project_path)
            root = Path(snapshot.root)
            if not supplied.is_absolute() or not root.is_absolute() or supplied != root:
                raise ValueError("project path and snapshot root must be absolute and match")
            self.project_path = root

    def analyze(self) -> NestJSProjectArchitecture:
        arch = NestJSProjectArchitecture(self.project_path.name, str(self.project_path))
        self.arch = arch
        self.files: Dict[str, _File] = {}
        contents = self.snapshot.content_map() if self.snapshot is not None else None
        if contents is None:
            paths = sorted(p for p in self.project_path.rglob("*") if p.is_file())
            keys = [p.relative_to(self.project_path).as_posix() for p in paths]
        else:
            keys = sorted(contents)
        for key in keys:
            path = Path(key)
            if path.suffix not in SOURCE_EXTENSIONS or any(p in IGNORED_DIRECTORIES or p.startswith(".") for p in path.parts):
                continue
            if contents is None:
                try:
                    content = (self.project_path / key).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
            else:
                content = contents[key]
            source = content.encode("utf-8")
            tree = ts.parser_for_suffix(path.suffix).parse(source)
            if tree.root_node.has_error:
                self._diagnostic_raw("syntax_error", SourceSpan(key, 1, max(1, content.count("\n") + 1)), "", "file contains a syntax error")
                continue
            self.files[key] = _File(key, source, tree)
        for file in self.files.values():
            self._index(file)
        self.by_class: Dict[tuple[str, str], NestJSDeclaration] = {}
        for file in self.files.values():
            for name, nodes in sorted(file.classes.items()):
                for node in nodes:
                    decorators = file.decorators.get(node.start_byte, [])
                    recognized = [(self._decorator_name(file, dec), dec) for dec in decorators]
                    for dec_name, decorator in recognized:
                        kind = _KINDS.get(dec_name)
                        if not kind:
                            continue
                        declaration = self._declare(kind, file, node, name, {"decorator": _text(file, decorator)})
                        self.by_class[(file.key, name)] = declaration
                        if kind == "controller":
                            args = self._arguments(decorator)
                            path = "" if not args else _literal(file, args[0]) if len(args) == 1 else None
                            if path is None or "*" in path:
                                self._diagnostic("unsupported_expression", file, args[0] if args else decorator, "unsupported controller path")
                                declaration.metadata["controller_path"] = None
                            else:
                                declaration.metadata["controller_path"] = _normalize(path)
                        if kind == "module":
                            declaration.metadata["module_decorator"] = decorator
                        break
        for file in self.files.values():
            self._modules(file, only_providers=True)
        for file in self.files.values():
            self._modules(file, only_providers=False)
            self._routes(file)
        for file in self.files.values():
            self._bootstrap(file)
        for declaration in self.arch.declarations:
            declaration.metadata.pop("module_decorator", None)
        self._constructor_dependencies()
        self._finalize_routes()
        arch.declarations.sort(key=lambda d: d.id)
        arch.references.sort(key=lambda r: (r.from_id, r.to_id, r.relation, r.evidence.file_path, r.evidence.start_line))
        arch.diagnostics.sort(key=lambda d: (d.span.file_path, d.span.start_line, d.span.start_col, d.code, d.expression))
        return arch

    def _diagnostic_raw(self, code, span, expression, reason):
        self.arch.diagnostics.append(NestJSDiagnostic(code, span, expression, reason))

    def _diagnostic(self, code, file, node, reason):
        self._diagnostic_raw(code, _span(file, node), _text(file, node), reason)

    def _index(self, file):
        root = file.tree.root_node
        outer_pending = []
        for statement in root.named_children:
            if statement.type == "decorator":
                outer_pending.append(statement)
                continue
            if statement.type == "import_statement":
                spec = ts.child_of_type(statement, "string")
                package = _literal(file, spec)
                clause = ts.child_of_type(statement, "import_clause")
                if not package or clause is None:
                    continue
                for child in clause.named_children:
                    if child.type == "identifier":
                        file.imports[_text(file, child)].append(_Binding(package, "default"))
                    elif child.type == "namespace_import":
                        ident = ts.child_of_type(child, "identifier")
                        if ident:
                            file.imports[_text(file, ident)].append(_Binding(package, "*", True))
                    elif child.type == "named_imports":
                        for item in _children(child, "import_specifier"):
                            original = item.child_by_field_name("name")
                            alias = item.child_by_field_name("alias")
                            if original:
                                file.imports[_text(file, alias or original)].append(_Binding(package, _text(file, original)))
                continue
            wrapped = statement.type == "export_statement"
            if wrapped and ts.child_of_type(statement, "string") is None:
                clause = ts.child_of_type(statement, "export_clause")
                if clause:
                    for entry in _children(clause, "export_specifier"):
                        original = entry.child_by_field_name("name")
                        if original:
                            file.exported.add(_text(file, original))
                elif not any(child.type in _CLASS_TYPES for child in statement.named_children):
                    identifiers = _children(statement, "identifier")
                    if identifiers and "default" in _text(file, statement):
                        file.defaults.append(_text(file, identifiers[0]))
                        file.exported.add(_text(file, identifiers[0]))
            targets = statement.named_children if wrapped else [statement]
            pending = outer_pending
            outer_pending = []
            for target in targets:
                if target.type == "decorator":
                    pending.append(target)
                elif target.type in _CLASS_TYPES:
                    self._index_class(file, target, pending, wrapped and "default" in _text(file, statement)[:target.start_byte-statement.start_byte], wrapped)
                    pending = []
                elif target.type in ("interface_declaration", "type_alias_declaration", "function_declaration", "lexical_declaration", "variable_declaration"):
                    name = ts.declared_name(file.source, target)
                    if name:
                        file.other_names.add(name)
                    if target.type in ("lexical_declaration", "variable_declaration"):
                        for variable in _children(target, "variable_declarator"):
                            identifier = variable.child_by_field_name("name")
                            if identifier:
                                file.other_names.add(_text(file, identifier))
        for node in ts.descendants(root):
            if node.type in ("interface_declaration", "type_alias_declaration"):
                name = ts.declared_name(file.source, node)
                if name:
                    file.other_names.add(name)

    def _index_class(self, file, node, outer_decorators, default, exported):
        name = ts.declared_name(file.source, node)
        if not name:
            return
        file.classes[name].append(node)
        if exported:
            file.exported.add(name)
        if default:
            file.defaults.append(name)
        file.decorators[node.start_byte] = list(outer_decorators) + _children(node, "decorator")
        body = ts.child_of_type(node, "class_body")
        if body:
            pending = []
            for child in body.named_children:
                if child.type == "decorator":
                    pending.append(child)
                elif child.type == "method_definition":
                    file.decorators[child.start_byte] = pending + _children(child, "decorator")
                    pending = []
                else:
                    pending = []

    def _decorator_name(self, file, decorator):
        expression = decorator.named_children[0] if decorator.named_children else None
        target = expression.child_by_field_name("function") if expression and expression.type == "call_expression" else expression
        if target is None:
            return None
        binding = self._binding(file, target, "@nestjs/common")
        return binding

    def _lexical_binding(self, file, node, name):
        current = node
        while current is not None:
            if current.type in ("function_declaration", "method_definition", "arrow_function", "function_expression"):
                params = ts.child_of_type(current, "formal_parameters")
                if params:
                    for parameter in params.named_children:
                        identifiers = [part for part in ts.descendants(parameter) if part.type == "identifier"]
                        if identifiers and _text(file, identifiers[0]) == name:
                            return ("parameter", parameter.start_byte)
            if current.type in ("statement_block", "program"):
                for statement in current.named_children:
                    if statement.type not in ("lexical_declaration", "variable_declaration"):
                        continue
                    for declaration in _children(statement, "variable_declarator"):
                        identifier = declaration.child_by_field_name("name")
                        if identifier and _text(file, identifier) == name:
                            return ("variable", declaration.start_byte)
            current = current.parent
        return None

    def _binding(self, file, node, package):
        if node.type in ("identifier", "type_identifier"):
            name = _text(file, node)
            if name in file.classes or name in file.other_names or self._lexical_binding(file, node, name) is not None:
                return None
            bindings = file.imports.get(name, [])
            if len(bindings) == 1 and bindings[0].package == package and not bindings[0].namespace:
                return bindings[0].imported
        if node.type in ("member_expression", "nested_type_identifier"):
            obj = node.child_by_field_name("object") or node.child_by_field_name("module")
            prop = node.child_by_field_name("property") or node.child_by_field_name("name")
            if obj and prop:
                name = _text(file, obj)
                bindings = file.imports.get(name, [])
                if name not in file.classes and name not in file.other_names and self._lexical_binding(file, obj, name) is None and len(bindings) == 1 and bindings[0].package == package and bindings[0].namespace:
                    return _text(file, prop)
        return None

    @staticmethod
    def _arguments(decorator):
        expression = decorator.named_children[0] if decorator.named_children else None
        args = expression.child_by_field_name("arguments") if expression and expression.type == "call_expression" else None
        return list(args.named_children) if args else []

    def _declare(self, kind, file, node, name, metadata=None):
        identity = f"nestjs:{kind}:{file.key}#{name}"
        previous = next((d for d in self.arch.declarations if d.id == identity), None)
        if previous:
            return previous
        declaration = NestJSDeclaration(identity, kind, name, file.key, _span(file, node), file.source.decode("utf-8"), metadata or {}, node)
        self.arch.declarations.append(declaration)
        return declaration

    def _resolve(self, file, expression, expected=None, diagnose=True, register_provider=False):
        text = _text(file, expression)
        parts = text.split(".")
        if self._lexical_binding(file, expression, parts[0]) is not None:
            if diagnose:
                self._diagnostic("unresolved_reference", file, expression, "name is shadowed by a local binding")
            return None
        candidates = []
        if len(parts) == 1 and re.fullmatch(r"[A-Za-z_$][\w$]*", parts[0]):
            name = parts[0]
            for node in file.classes.get(name, []):
                candidates.append((file.key, name, node.start_byte))
            if name not in file.other_names:
                for binding in file.imports.get(name, []):
                    if not binding.namespace:
                        for target in self._relative_candidates(file, binding.package):
                            selected = self.files[target].defaults if binding.imported == "default" else [binding.imported]
                            candidates.extend((target, item, node.start_byte) for item in selected for node in self.files[target].classes.get(item, []) if item in self.files[target].exported)
        elif len(parts) == 2:
            alias, name = parts
            if alias not in file.classes and alias not in file.other_names:
                for binding in file.imports.get(alias, []):
                    if binding.namespace:
                        for target in self._relative_candidates(file, binding.package):
                            candidates.extend((target, name, node.start_byte) for node in self.files[target].classes.get(name, []) if name in self.files[target].exported)
        candidates = list(dict.fromkeys(candidates))
        if len(candidates) != 1:
            if diagnose:
                self._diagnostic("ambiguous_reference" if len(candidates) > 1 else "unresolved_reference", file, expression,
                                 "multiple class targets" if len(candidates) > 1 else "no directly imported local class target")
            return None
        target_file, target_name, _ = candidates[0]
        declaration = self.by_class.get((target_file, target_name))
        if expected == "provider" and declaration is None and register_provider:
            node = self.files[target_file].classes[target_name][0]
            declaration = self._declare("provider", self.files[target_file], node, target_name)
            self.by_class[(target_file, target_name)] = declaration
        if declaration is None or (expected and declaration.kind != expected):
            if diagnose:
                self._diagnostic("unresolved_reference", file, expression, "class has no expected NestJS declaration")
            return None
        return declaration

    def _relative_candidates(self, file, package):
        if not package.startswith("."):
            return []
        base = posixpath.normpath(posixpath.join(posixpath.dirname(file.key), package))
        candidates = [base] if Path(base).suffix in SOURCE_EXTENSIONS else []
        candidates += [base + suffix for suffix in SOURCE_EXTENSIONS]
        candidates += [base + "/index" + suffix for suffix in SOURCE_EXTENSIONS]
        return [candidate for candidate in dict.fromkeys(candidates) if candidate in self.files]

    def _reference(self, source, target, relation, file, evidence):
        if source and target:
            ref = NestJSReference(source.id, target.id, relation, _span(file, evidence))
            if not any((r.from_id, r.to_id, r.relation) == (ref.from_id, ref.to_id, ref.relation) for r in self.arch.references):
                self.arch.references.append(ref)

    def _modules(self, file, only_providers=False):
        for declaration in list(self.arch.declarations):
            if declaration.file_path != file.key or declaration.kind != "module":
                continue
            decorator = declaration.metadata.get("module_decorator")
            args = self._arguments(decorator) if decorator else []
            obj = args[0] if len(args) == 1 and args[0].type == "object" else None
            if obj is None:
                self._diagnostic("unsupported_expression", file, decorator or declaration.ast_node, "module metadata must be an object")
                continue
            for pair in _children(obj, "pair"):
                key = pair.child_by_field_name("key")
                value = pair.child_by_field_name("value")
                field = _text(file, key) if key else ""
                if field not in {"imports", "controllers", "providers", "exports"}:
                    continue
                if (field == "providers") != only_providers:
                    continue
                if value is None or value.type != "array":
                    self._diagnostic("unsupported_expression", file, value or pair, "module field must be an array")
                    continue
                for item in value.named_children:
                    if item.type not in ("identifier", "member_expression"):
                        self._diagnostic("unsupported_expression", file, item, "dynamic module item is unsupported")
                        continue
                    expected = {"imports": "module", "controllers": "controller", "providers": "provider", "exports": None}[field]
                    target = self._resolve(file, item, expected, register_provider=(field == "providers"))
                    if target and field == "exports" and target.kind not in {"module", "provider"}:
                        self._diagnostic("unresolved_reference", file, item, "export is not a module or provider")
                        continue
                    relation = {"imports": "INCLUDES", "controllers": "DECLARES", "providers": "PROVIDES", "exports": "EXPORTS"}[field]
                    self._reference(declaration, target, relation, file, item)

    def _routes(self, file):
        for controller in [d for d in self.arch.declarations if d.file_path == file.key and d.kind == "controller"]:
            body = ts.child_of_type(controller.ast_node, "class_body")
            if not body:
                continue
            for member in _children(body, "method_definition"):
                name = ts.declared_name(file.source, member)
                if not name:
                    continue
                for decorator in file.decorators.get(member.start_byte, []):
                    http = self._decorator_name(file, decorator)
                    if http not in _HTTP:
                        continue
                    args = self._arguments(decorator)
                    route = "" if not args else _literal(file, args[0]) if len(args) == 1 else None
                    if route is None or "*" in route:
                        self._diagnostic("unsupported_expression", file, args[0] if args else decorator, "unsupported route path")
                    relative = _normalize(controller.metadata.get("controller_path") or "", route) if route is not None and controller.metadata.get("controller_path") is not None and "*" not in route else None
                    identity = f"{controller.name}.{name}@{ts.start_line(decorator)}:{decorator.start_point.column}"
                    endpoint = self._declare("endpoint", file, decorator, identity, {
                        "http_method": _HTTP[http], "path": _normalize(route) if route is not None and "*" not in route else None,
                        "controller_path": controller.metadata.get("controller_path"),
                        "relative_path": relative, "full_path": None,
                        "function_name": name, "controller_id": controller.id,
                    })
                    self._reference(controller, endpoint, "ROUTES", file, decorator)

    def _bootstrap(self, file):
        for node in ts.descendants(file.tree.root_node):
            if node.type != "call_expression":
                continue
            function = node.child_by_field_name("function")
            if function is None or function.type != "member_expression":
                continue
            obj = function.child_by_field_name("object")
            prop = function.child_by_field_name("property")
            if not obj or not prop or _text(file, prop) != "create" or self._binding(file, obj, "@nestjs/core") != "NestFactory":
                continue
            args = node.child_by_field_name("arguments")
            items = args.named_children if args else []
            target = self._resolve(file, items[0], "module") if items else None
            app = self._declare("application", file, node, f"NestFactory.create@{ts.start_line(node)}:{node.start_point.column}",
                                {"root_module": target.id if target else None, "prefix": None})
            self._reference(app, target, "INCLUDES", file, items[0] if items else node)
            if not target:
                self._diagnostic("bootstrap_unresolved", file, node, "root module is unresolved")
            parent = node.parent
            while parent and parent.type not in ("function_declaration", "method_definition", "arrow_function", "function_expression"):
                parent = parent.parent
            if parent:
                function_name = ts.declared_name(file.source, parent) if parent.type in ("function_declaration", "method_definition") else None
                if not function_name and parent.type in ("arrow_function", "function_expression") and parent.parent and parent.parent.type == "variable_declarator":
                    function_node = parent.parent.child_by_field_name("name")
                    function_name = _text(file, function_node) if function_node else None
                if function_name:
                    app.metadata["bootstrap_function"] = function_name
            variable = None
            if node.parent and node.parent.type == "await_expression" and node.parent.parent and node.parent.parent.type == "variable_declarator":
                variable = node.parent.parent.child_by_field_name("name")
            elif node.parent and node.parent.type == "variable_declarator":
                variable = node.parent.child_by_field_name("name")
            prefix_calls = []
            if parent and variable:
                for child in ts.descendants(parent):
                    if child.type != "call_expression":
                        continue
                    enclosing = child.parent
                    while enclosing and enclosing.type not in ("function_declaration", "method_definition", "arrow_function", "function_expression"):
                        enclosing = enclosing.parent
                    if enclosing is None or (enclosing.type, enclosing.start_byte, enclosing.end_byte) != (parent.type, parent.start_byte, parent.end_byte):
                        continue
                    callee = child.child_by_field_name("function")
                    if callee and callee.type == "member_expression":
                        receiver = callee.child_by_field_name("object")
                        method = callee.child_by_field_name("property")
                        if receiver and method and _text(file, receiver) == _text(file, variable) and _text(file, method) == "setGlobalPrefix":
                            binding = self._lexical_binding(file, receiver, _text(file, variable))
                            if binding == ("variable", variable.parent.start_byte):
                                prefix_calls.append(child)
            if not prefix_calls:
                app.metadata["prefix"] = ""
            elif len(prefix_calls) == 1:
                call = prefix_calls[0]
                call_args = call.child_by_field_name("arguments")
                arguments = call_args.named_children if call_args else []
                prefix = _literal(file, arguments[0]) if len(arguments) == 1 else None
                if prefix is None:
                    self._diagnostic("bootstrap_unresolved", file, call, "global prefix is not a single literal")
                else:
                    app.metadata["prefix"] = prefix
            else:
                self._diagnostic("bootstrap_unresolved", file, prefix_calls[0], "multiple global prefix calls")

    def _constructor_dependencies(self):
        for consumer in list(self.arch.declarations):
            if consumer.kind not in {"module", "controller", "provider"}:
                continue
            file = self.files[consumer.file_path]
            body = ts.child_of_type(consumer.ast_node, "class_body")
            if not body:
                continue
            constructors = [m for m in _children(body, "method_definition") if ts.declared_name(file.source, m) == "constructor"]
            for constructor in constructors:
                params = ts.child_of_type(constructor, "formal_parameters")
                if not params:
                    continue
                for parameter in params.named_children:
                    annotations = [n for n in ts.descendants(parameter) if n.type == "decorator"]
                    if annotations:
                        self._diagnostic("unsupported_expression", file, parameter, "explicit injection decorator is unsupported")
                        continue
                    type_node = ts.child_of_type(parameter, "type_annotation")
                    if type_node is None:
                        continue
                    type_children = type_node.named_children
                    type_expr = type_children[0] if len(type_children) == 1 else None
                    if type_expr is None or type_expr.type not in ("type_identifier", "nested_type_identifier"):
                        self._diagnostic("unsupported_expression", file, type_node, "only simple class types are supported")
                        continue
                    target = self._resolve(file, type_expr, "provider")
                    self._reference(consumer, target, "DEPENDS_ON", file, type_expr)

    def _finalize_routes(self):
        apps = [d for d in self.arch.declarations if d.kind == "application"]
        if len(apps) != 1:
            if apps:
                self._diagnostic_raw("bootstrap_unresolved", apps[0].span, "NestFactory.create", "multiple bootstraps")
            else:
                endpoints = sorted((d for d in self.arch.declarations if d.kind == "endpoint"), key=lambda d: d.id)
                if endpoints:
                    self._diagnostic_raw("bootstrap_unresolved", endpoints[0].span, "", "no recognized bootstrap")
            return
        app = apps[0]
        root = app.metadata.get("root_module")
        prefix = app.metadata.get("prefix")
        if not root or prefix is None:
            return
        reachable = {root}
        changed = True
        while changed:
            before = len(reachable)
            reachable.update(ref.to_id for ref in self.arch.references if ref.relation == "INCLUDES" and ref.from_id in reachable)
            changed = len(reachable) != before
        controllers = {ref.to_id for ref in self.arch.references if ref.relation == "DECLARES" and ref.from_id in reachable}
        for endpoint in self.arch.declarations:
            if endpoint.kind == "endpoint" and endpoint.metadata.get("controller_id") in controllers and endpoint.metadata.get("relative_path") is not None:
                endpoint.metadata["full_path"] = _normalize(prefix, endpoint.metadata["relative_path"])
