"""
Static AST Analysis Engine for FastAPI Codebases.
Parses Python files without executing code, extracting apps, routers,
endpoints, dependency injection chains, models, and middlewares.
"""

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from language_analyzers.python import PythonSourceAnalyzer

from .models import (
    AppInfo,
    DependencyInfo,
    EndpointInfo,
    ParameterInfo,
    ProjectArchitecture,
    RouterInclusion,
    RouterInfo,
    SchemaFieldInfo,
    SchemaInfo,
)


class PythonFileAST:
    def __init__(self, file_path: Path, module_name: str):
        self.file_path = file_path
        self.module_name = module_name
        self.tree: Optional[ast.AST] = None
        self.source_code: str = ""
        self.imports: Dict[str, str] = {}
        self.from_imports: Dict[str, Tuple[str, str]] = {}
        self.type_aliases: Dict[str, ast.AST] = {}
        self.security_schemes: Dict[str, Dict[str, Any]] = {}

        self.apps: Dict[str, AppInfo] = {}
        self.routers: Dict[str, RouterInfo] = {}
        self.endpoints: List[EndpointInfo] = []
        self.dependencies: Dict[str, DependencyInfo] = {}
        self.schemas: Dict[str, SchemaInfo] = {}


class FastAPIAnalyzer:
    HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head", "trace", "api_route"}

    def __init__(self, project_path: str, entrypoint: Optional[str] = None):
        self.project_path = Path(project_path).resolve()
        self.entrypoint = Path(entrypoint).resolve() if entrypoint else None
        self.file_asts: Dict[str, PythonFileAST] = {}
        self.path_to_module: Dict[Path, str] = {}

        self.apps: List[AppInfo] = []
        self.routers: List[RouterInfo] = []
        self.endpoints: List[EndpointInfo] = []
        self.dependencies: Dict[str, DependencyInfo] = {}
        self.schemas: Dict[str, SchemaInfo] = {}
        self.annotated_deps: Dict[str, str] = {}

    def analyze(self) -> ProjectArchitecture:
        self._discover_and_parse_files()
        self._extract_all_declarations()
        self._link_dependencies()
        self._resolve_router_hierarchy()

        unique_schemas = list({s.id: s for s in self.schemas.values()}.values())
        unique_deps = self._get_active_dependencies()

        arch = ProjectArchitecture(
            project_name=self.project_path.name,
            project_path=str(self.project_path),
            apps=self.apps,
            routers=self.routers,
            endpoints=self.endpoints,
            dependencies=unique_deps,
            schemas=unique_schemas,
        )

        return arch

    def _discover_and_parse_files(self):
        for source_file in PythonSourceAnalyzer(self.project_path).analyze():
            file_ast = PythonFileAST(
                file_path=source_file.file_path,
                module_name=source_file.module_name,
            )
            file_ast.tree = source_file.tree
            file_ast.source_code = source_file.source_code
            self.file_asts[source_file.module_name] = file_ast
            self.path_to_module[source_file.file_path] = source_file.module_name

        # Imports/aliases must be collected for every file before declarations
        # are extracted, since cross-file references are resolved by name.
        for mod_name, file_ast in self.file_asts.items():
            self._collect_imports_and_aliases(file_ast)

    def _collect_imports_and_aliases(self, file_ast: PythonFileAST):
        for node in file_ast.tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    file_ast.imports[local_name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if node.level > 0:
                    curr_parts = file_ast.module_name.split(".")
                    base_parts = curr_parts[:-node.level] if len(curr_parts) >= node.level else []
                    if mod:
                        mod = ".".join(base_parts + [mod])
                    else:
                        mod = ".".join(base_parts)
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    file_ast.from_imports[local_name] = (mod, alias.name)

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_name = target.id
                        file_ast.type_aliases[var_name] = node.value
                        dep_target = self._extract_depends_target(node.value, file_ast)
                        if dep_target:
                            qualified = f"{file_ast.module_name}.{var_name}"
                            self.annotated_deps[qualified] = dep_target
                            self.annotated_deps[var_name] = dep_target

                        if isinstance(node.value, ast.Call):
                            func_name = self._get_call_func_name(node.value.func)
                            if "OAuth2" in func_name or "Security" in func_name or "HTTPBearer" in func_name:
                                file_ast.security_schemes[var_name] = {
                                    "kind": func_name,
                                    "line": node.lineno
                                }
                                dep_info = DependencyInfo(
                                    id=f"sec_{file_ast.module_name}_{var_name}",
                                    name=var_name,
                                    kind="security_scheme",
                                    module=file_ast.module_name,
                                    file_path=str(file_ast.file_path),
                                    line_number=node.lineno,
                                    end_line_number=getattr(node, "end_lineno", node.lineno) or node.lineno,
                                    docstring=f"Security scheme: {func_name}"
                                )
                                self.dependencies[dep_info.id] = dep_info
                                self.dependencies[var_name] = dep_info
                                self.dependencies[f"{file_ast.module_name}.{var_name}"] = dep_info

    def _extract_all_declarations(self):
        for mod_name, file_ast in self.file_asts.items():
            for node in file_ast.tree.body:
                if isinstance(node, ast.Assign):
                    self._check_app_or_router_instantiation(node, file_ast)
                elif isinstance(node, ast.ClassDef):
                    self._check_schema_class(node, file_ast)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self._check_function_def(node, file_ast)
                elif isinstance(node, ast.Expr):
                    self._check_expr_calls(node.value, file_ast)
                elif isinstance(node, ast.If):
                    for sub_node in node.body:
                        if isinstance(sub_node, ast.Expr):
                            self._check_expr_calls(sub_node.value, file_ast)

    def _check_app_or_router_instantiation(self, node: ast.Assign, file_ast: PythonFileAST):
        if not isinstance(node.value, ast.Call):
            return
        call_name = self._get_call_func_name(node.value.func)

        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            var_name = target.id

            if call_name in ("FastAPI", "get_application") or "FastAPI" in call_name:
                title = "FastAPI App"
                version = "0.1.0"
                title_source = "default"
                version_source = "default"
                title_expr = None
                version_expr = None

                if "FastAPI" not in call_name:
                    title_source = version_source = "unresolved"
                    title_expr = version_expr = ast.unparse(node.value)
                else:
                    kwargs_expr = None
                    for kw in node.value.keywords:
                        if kw.arg is None:
                            kwargs_expr = f"**{ast.unparse(kw.value)}"
                        elif kw.arg == "title":
                            if isinstance(kw.value, ast.Constant):
                                title = str(kw.value.value)
                                title_source = "literal"
                                title_expr = None
                            else:
                                title_source = "unresolved"
                                title_expr = ast.unparse(kw.value)
                        elif kw.arg == "version":
                            if isinstance(kw.value, ast.Constant):
                                version = str(kw.value.value)
                                version_source = "literal"
                                version_expr = None
                            else:
                                version_source = "unresolved"
                                version_expr = ast.unparse(kw.value)
                    if kwargs_expr:
                        if title_source == "default":
                            title_source = "unresolved"
                            title_expr = kwargs_expr
                        if version_source == "default":
                            version_source = "unresolved"
                            version_expr = kwargs_expr

                app_info = AppInfo(
                    id=f"app_{file_ast.module_name}_{var_name}",
                    var_name=var_name,
                    title=title,
                    version=version,
                    module=file_ast.module_name,
                    file_path=str(file_ast.file_path),
                    line_number=node.lineno,
                    end_line_number=getattr(node, "end_lineno", node.lineno) or node.lineno,
                    title_source=title_source,
                    version_source=version_source,
                    title_expr=title_expr,
                    version_expr=version_expr,
                )
                file_ast.apps[var_name] = app_info
                self.apps.append(app_info)

            elif call_name in ("APIRouter", "router") or "APIRouter" in call_name:
                prefix = ""
                tags = []
                dependencies = []
                for kw in node.value.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        prefix = str(kw.value.value)
                    elif kw.arg == "tags" and isinstance(kw.value, ast.List):
                        tags = [self._eval_constant(elt) for elt in kw.value.elts if self._eval_constant(elt)]
                    elif kw.arg == "dependencies" and isinstance(kw.value, ast.List):
                        for elt in kw.value.elts:
                            dep = self._extract_depends_target(elt, file_ast)
                            if dep:
                                dependencies.append(dep)

                router_info = RouterInfo(
                    id=f"router_{file_ast.module_name}_{var_name}",
                    var_name=var_name,
                    module=file_ast.module_name,
                    file_path=str(file_ast.file_path),
                    line_number=node.lineno,
                    end_line_number=getattr(node, "end_lineno", node.lineno) or node.lineno,
                    prefix=prefix,
                    tags=tags,
                    dependencies=dependencies,
                )
                file_ast.routers[var_name] = router_info
                self.routers.append(router_info)

    def _check_schema_class(self, node: ast.ClassDef, file_ast: PythonFileAST):
        base_names = [self._get_ast_name(b) for b in node.bases]
        is_schema = any(
            b in ("BaseModel", "SQLModel", "Schema", "GenericModel") or "Schema" in b or "Model" in b
            for b in base_names
        )

        # Classes under a models/schemas/entities path are treated as schemas
        # even without a recognized base class, since plain dataclasses are common there.
        in_model_file = any(p in file_ast.file_path.parts for p in ("models", "schemas", "entities"))
        if is_schema or in_model_file:
            fields = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_name = item.target.id
                    type_str = self._get_ast_name(item.annotation)
                    default_str = self._get_ast_name(item.value) if item.value else None
                    fields.append(SchemaFieldInfo(
                        name=field_name,
                        type_annotation=type_str,
                        default_value=default_str,
                        is_required=(item.value is None or default_str == "...")
                    ))

            schema_info = SchemaInfo(
                id=f"schema_{file_ast.module_name}_{node.name}",
                name=node.name,
                module=file_ast.module_name,
                file_path=str(file_ast.file_path),
                line_number=node.lineno,
                end_line_number=getattr(node, "end_lineno", node.lineno) or node.lineno,
                docstring=ast.get_docstring(node),
                base_classes=base_names,
                fields=fields,
            )
            file_ast.schemas[node.name] = schema_info
            self.schemas[schema_info.id] = schema_info
            self.schemas[node.name] = schema_info
            self.schemas[f"{file_ast.module_name}.{node.name}"] = schema_info

    def _check_function_def(self, node: ast.AST, file_ast: PythonFileAST):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return

        route_decorator = self._find_route_decorator(node.decorator_list, file_ast)
        params, deps, req_schemas = self._analyze_function_params(node.args, file_ast)

        if route_decorator:
            router_var = route_decorator["router_var"]
            http_method = route_decorator["method"].upper()
            path = route_decorator["path"]
            tags = route_decorator.get("tags", [])
            response_model = route_decorator.get("response_model")
            status_code = route_decorator.get("status_code")
            summary = route_decorator.get("summary")
            decorator_deps = route_decorator.get("dependencies", [])

            all_deps = list(set(deps + decorator_deps))
            resp_schemas = [response_model] if response_model else []

            endpoint_id = f"ep_{file_ast.module_name}_{node.name}_{http_method}"
            endpoint_info = EndpointInfo(
                id=endpoint_id,
                http_method=http_method,
                path=path,
                full_path=path,  # placeholder; overwritten once router prefixes are resolved
                function_name=node.name,
                module=file_ast.module_name,
                file_path=str(file_ast.file_path),
                line_number=node.lineno,
                end_line_number=getattr(node, "end_lineno", node.lineno) or node.lineno,
                docstring=ast.get_docstring(node),
                summary=summary,
                tags=tags,
                response_model=response_model,
                status_code=status_code,
                parameters=params,
                dependencies=all_deps,
                request_schemas=req_schemas,
                response_schemas=resp_schemas,
                router_id=f"router_{file_ast.module_name}_{router_var}" if router_var else None,
            )
            file_ast.endpoints.append(endpoint_info)
            self.endpoints.append(endpoint_info)

            if router_var and router_var in file_ast.routers:
                file_ast.routers[router_var].endpoints.append(endpoint_id)
        else:
            dep_info = DependencyInfo(
                id=f"dep_{file_ast.module_name}_{node.name}",
                name=node.name,
                kind="function",
                module=file_ast.module_name,
                file_path=str(file_ast.file_path),
                line_number=node.lineno,
                end_line_number=getattr(node, "end_lineno", node.lineno) or node.lineno,
                docstring=ast.get_docstring(node),
                sub_dependencies=deps,
                parameters=params,
            )
            file_ast.dependencies[node.name] = dep_info
            self.dependencies[dep_info.id] = dep_info
            self.dependencies[node.name] = dep_info
            self.dependencies[f"{file_ast.module_name}.{node.name}"] = dep_info

    def _find_route_decorator(self, decorator_list: List[ast.AST], file_ast: PythonFileAST) -> Optional[Dict[str, Any]]:
        for dec in decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                method_name = dec.func.attr.lower()
                router_name = self._get_ast_name(dec.func.value)

                if method_name in self.HTTP_METHODS:
                    path = "/"
                    if dec.args:
                        path_val = self._eval_constant(dec.args[0])
                        if path_val is not None:
                            path = str(path_val)

                    tags = []
                    response_model = None
                    status_code = None
                    summary = None
                    dependencies = []

                    for kw in dec.keywords:
                        if kw.arg == "path" and isinstance(kw.value, ast.Constant):
                            path = str(kw.value.value)
                        elif kw.arg == "response_model":
                            response_model = self._get_ast_name(kw.value)
                        elif kw.arg == "status_code":
                            status_code = self._get_ast_name(kw.value)
                        elif kw.arg == "summary" and isinstance(kw.value, ast.Constant):
                            summary = str(kw.value.value)
                        elif kw.arg == "tags" and isinstance(kw.value, ast.List):
                            tags = [self._eval_constant(elt) for elt in kw.value.elts if self._eval_constant(elt)]
                        elif kw.arg == "dependencies" and isinstance(kw.value, ast.List):
                            for elt in kw.value.elts:
                                d = self._extract_depends_target(elt, file_ast)
                                if d:
                                    dependencies.append(d)

                    return {
                        "router_var": router_name,
                        "method": method_name,
                        "path": path,
                        "tags": tags,
                        "response_model": response_model,
                        "status_code": status_code,
                        "summary": summary,
                        "dependencies": dependencies,
                    }
        return None

    def _analyze_function_params(self, args_node: ast.arguments, file_ast: PythonFileAST) -> Tuple[List[ParameterInfo], List[str], List[str]]:
        params = []
        dependencies = []
        request_schemas = []

        all_args = args_node.args + args_node.kwonlyargs
        # ast.arguments.defaults only covers the trailing positional args;
        # this offset aligns index i in args_node.args with defaults[i - offset].
        defaults_offset = len(args_node.args) - len(args_node.defaults)

        for i, arg in enumerate(args_node.args):
            default_node = None
            if i >= defaults_offset:
                default_node = args_node.defaults[i - defaults_offset]

            p_info, dep, schema = self._parse_single_param(arg, default_node, file_ast)
            params.append(p_info)
            if dep:
                dependencies.append(dep)
            if schema:
                request_schemas.append(schema)

        for i, arg in enumerate(args_node.kwonlyargs):
            default_node = args_node.kw_defaults[i] if i < len(args_node.kw_defaults) else None
            p_info, dep, schema = self._parse_single_param(arg, default_node, file_ast)
            params.append(p_info)
            if dep:
                dependencies.append(dep)
            if schema:
                request_schemas.append(schema)

        return params, dependencies, request_schemas

    def _parse_single_param(self, arg: ast.arg, default_node: Optional[ast.AST], file_ast: PythonFileAST) -> Tuple[ParameterInfo, Optional[str], Optional[str]]:
        name = arg.arg
        type_str = self._get_ast_name(arg.annotation) if arg.annotation else None
        default_str = self._get_ast_name(default_node) if default_node else None
        kind = "query"
        dep_target = None
        schema_target = None

        if default_node:
            if isinstance(default_node, ast.Call):
                call_func = self._get_call_func_name(default_node.func)
                if call_func in ("Depends", "Security"):
                    kind = "dependency"
                    dep_target = self._extract_depends_target(default_node, file_ast)
                elif call_func in ("Body", "Query", "Path", "Header", "Cookie", "Form", "File"):
                    kind = call_func.lower()
            elif isinstance(default_node, ast.Name) and default_node.id in self.annotated_deps:
                kind = "dependency"
                dep_target = self.annotated_deps[default_node.id]

        if arg.annotation:
            ann_dep = self._extract_depends_target(arg.annotation, file_ast)
            if ann_dep:
                kind = "dependency"
                dep_target = ann_dep
            elif type_str in self.annotated_deps:
                kind = "dependency"
                dep_target = self.annotated_deps[type_str]

        if type_str and kind in ("body", "query"):
            clean_type = type_str.replace("Optional[", "").replace("List[", "").rstrip("]")
            if clean_type in self.schemas or any(s.endswith(f".{clean_type}") for s in self.schemas):
                schema_target = clean_type
                if kind != "query":
                    kind = "body"

        p_info = ParameterInfo(
            name=name,
            type_annotation=type_str,
            default_value=default_str,
            kind=kind,
            dependency_call=dep_target
        )
        return p_info, dep_target, schema_target

    def _extract_depends_target(self, node: Optional[ast.AST], file_ast: PythonFileAST) -> Optional[str]:
        if not node:
            return None

        if isinstance(node, ast.Call):
            call_func = self._get_call_func_name(node.func)
            if call_func in ("Depends", "Security"):
                if node.args:
                    target_arg = node.args[0]
                    return self._get_ast_name(target_arg)
                return call_func
            return self._get_ast_name(node)

        if isinstance(node, ast.Subscript):
            slice_node = node.slice
            # Python < 3.9 wraps the subscript slice in ast.Index; 3.9+ uses ast.Tuple directly.
            elts = []
            if isinstance(slice_node, ast.Tuple):
                elts = slice_node.elts
            elif isinstance(slice_node, ast.Index) and isinstance(slice_node.value, ast.Tuple):
                elts = slice_node.value.elts
            elif hasattr(slice_node, "elts"):
                elts = slice_node.elts

            for elt in elts:
                dep = self._extract_depends_target(elt, file_ast)
                if dep:
                    return dep

        if isinstance(node, ast.Name):
            if node.id in self.annotated_deps:
                return self.annotated_deps[node.id]
            if node.id in file_ast.type_aliases:
                return self._extract_depends_target(file_ast.type_aliases[node.id], file_ast)

        return None

    def _check_expr_calls(self, node: ast.AST, file_ast: PythonFileAST):
        if not isinstance(node, ast.Call):
            return

        func_name = self._get_call_func_name(node.func)
        caller_name = self._get_caller_var_name(node.func)

        if "include_router" in func_name:
            if not node.args:
                return
            target_router_expr = self._get_ast_name(node.args[0])
            prefix = ""
            tags = []
            dependencies = []

            for kw in node.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    prefix = str(kw.value.value)
                elif kw.arg == "tags" and isinstance(kw.value, ast.List):
                    tags = [self._eval_constant(elt) for elt in kw.value.elts if self._eval_constant(elt)]
                elif kw.arg == "dependencies" and isinstance(kw.value, ast.List):
                    for elt in kw.value.elts:
                        dep = self._extract_depends_target(elt, file_ast)
                        if dep:
                            dependencies.append(dep)

            target_module = self._resolve_target_router_module(target_router_expr, file_ast)

            inclusion = RouterInclusion(
                router_var=target_router_expr,
                module_or_source=target_module or file_ast.module_name,
                prefix=prefix,
                tags=tags,
                dependencies=dependencies
            )

            if caller_name in file_ast.apps:
                file_ast.apps[caller_name].inclusions.append(inclusion)
            elif caller_name in file_ast.routers:
                file_ast.routers[caller_name].inclusions.append(inclusion)
            else:
                for app in self.apps:
                    if app.var_name == caller_name and app.module == file_ast.module_name:
                        app.inclusions.append(inclusion)
                for r in self.routers:
                    if r.var_name == caller_name and r.module == file_ast.module_name:
                        r.inclusions.append(inclusion)

        elif "add_middleware" in func_name:
            if node.args:
                mw_name = self._get_ast_name(node.args[0])
                mw_info = {
                    "name": mw_name,
                    "module": file_ast.module_name,
                    "line": node.lineno,
                }
                if caller_name in file_ast.apps:
                    file_ast.apps[caller_name].middlewares.append(mw_info)
                elif self.apps:
                    self.apps[0].middlewares.append(mw_info)

    def _strip_root_package(self, module: str) -> str:
        root = self.project_path.name
        if module == root:
            return ""
        prefix = f"{root}."
        if module.startswith(prefix):
            return module[len(prefix):]
        return module

    def _resolve_target_router_module(self, target_expr: str, file_ast: PythonFileAST) -> Optional[str]:
        parts = target_expr.split(".")
        root_name = parts[0]

        if root_name in file_ast.from_imports:
            mod, orig = file_ast.from_imports[root_name]
            potential_submodule = f"{mod}.{orig}" if mod else orig
            # The stripped form is only accepted when it is a real module key, so
            # projects whose keys genuinely start with the root package name keep resolving.
            for candidate in (
                potential_submodule,
                self._strip_root_package(potential_submodule),
                mod,
                self._strip_root_package(mod),
            ):
                if candidate in self.file_asts:
                    return candidate
            return mod

        if root_name in file_ast.imports:
            raw = file_ast.imports[root_name]
            for candidate in (raw, self._strip_root_package(raw)):
                if candidate in self.file_asts:
                    return candidate
            return raw

        return file_ast.module_name

    def _link_dependencies(self):
        for dep_id, dep in list(self.dependencies.items()):
            resolved_subs = []
            for sub_name in dep.sub_dependencies:
                match = self.dependencies.get(sub_name)
                if not match:
                    for key, val in self.dependencies.items():
                        if key.endswith(f".{sub_name}") or val.name == sub_name:
                            match = val
                            break
                if match and match.id != dep.id:
                    resolved_subs.append(match.name)
                    if dep.name not in match.consumers:
                        match.consumers.append(dep.name)
            dep.sub_dependencies = list(set(resolved_subs))

    def _get_active_dependencies(self) -> List[DependencyInfo]:
        needed_names = set()

        for ep in self.endpoints:
            for d in ep.dependencies:
                clean = d.split("(")[0].split(".")[-1]
                needed_names.add(d)
                needed_names.add(clean)

        for r in self.routers:
            for d in r.dependencies:
                clean = d.split("(")[0].split(".")[-1]
                needed_names.add(d)
                needed_names.add(clean)

        active_deps_dict = {}
        for dep_id, dep in self.dependencies.items():
            if dep.kind == "security_scheme" or any(p in dep.module.lower() for p in ("dep", "security", "auth")):
                active_deps_dict[dep.id] = dep
                needed_names.add(dep.name)

        queue = list(needed_names)
        visited = set()

        while queue:
            name = queue.pop(0)
            if name in visited:
                continue
            visited.add(name)

            match = self.dependencies.get(name)
            if not match:
                for k, v in self.dependencies.items():
                    if v.name == name or k.endswith(f".{name}"):
                        match = v
                        break
            if match:
                active_deps_dict[match.id] = match
                for sub in match.sub_dependencies:
                    if sub not in visited:
                        queue.append(sub)

        return list(active_deps_dict.values())

    def _resolve_router_hierarchy(self):
        router_map: Dict[str, RouterInfo] = {}
        for r in self.routers:
            router_map[r.id] = r
            router_map[f"{r.module}.{r.var_name}"] = r
            router_map[r.module] = r

        def traverse_inclusions(parent_prefix: str, parent_tags: List[str], inclusions: List[RouterInclusion], visited: Set[str]):
            for inc in inclusions:
                target_mod = inc.module_or_source
                target_var = inc.router_var.split(".")[-1]
                target_key = f"{target_mod}.{target_var}"

                target_router = router_map.get(target_key) or router_map.get(target_mod)
                if not target_router:
                    for r in self.routers:
                        if r.module == target_mod or r.module.endswith(target_mod):
                            target_router = r
                            break

                if target_router and target_router.id not in visited:
                    visited.add(target_router.id)
                    inc.target_router_id = target_router.id

                    combined_prefix = self._join_paths(parent_prefix, inc.prefix)
                    combined_prefix = self._join_paths(combined_prefix, target_router.prefix)
                    combined_tags = list(set(parent_tags + inc.tags + target_router.tags))

                    for ep in self.endpoints:
                        if ep.module == target_router.module or ep.router_id == target_router.id:
                            ep.full_path = self._join_paths(combined_prefix, ep.path)
                            ep.tags = list(set(ep.tags + combined_tags))
                            ep.router_id = target_router.id

                    traverse_inclusions(combined_prefix, combined_tags, target_router.inclusions, visited)

        for app in self.apps:
            visited: Set[str] = set()
            traverse_inclusions("", [], app.inclusions, visited)

        # Routers never reached via an app's include_router() (e.g. included only
        # by other routers not rooted at an app) are still traversed independently.
        for r in self.routers:
            if r.inclusions:
                visited = {r.id}
                traverse_inclusions(r.prefix, r.tags, r.inclusions, visited)

        for ep in self.endpoints:
            if not ep.full_path:
                ep.full_path = ep.path
            ep.full_path = "/" + "/".join([p for p in ep.full_path.split("/") if p])

    @staticmethod
    def _join_paths(p1: str, p2: str) -> str:
        s1 = (p1 or "").strip("/")
        s2 = (p2 or "").strip("/")
        if s1 and s2:
            return f"/{s1}/{s2}"
        if s1:
            return f"/{s1}"
        if s2:
            return f"/{s2}"
        return "/"

    @classmethod
    def _get_call_func_name(cls, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        elif isinstance(node, ast.Call):
            return cls._get_call_func_name(node.func)
        return ""

    @classmethod
    def _get_caller_var_name(cls, node: ast.AST) -> str:
        if isinstance(node, ast.Attribute):
            return cls._get_ast_name(node.value)
        return ""

    @classmethod
    def _get_ast_name(cls, node: Optional[ast.AST]) -> str:
        if node is None:
            return ""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{cls._get_ast_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Call):
            func_name = cls._get_ast_name(node.func)
            args_str = ", ".join([cls._get_ast_name(a) for a in node.args])
            return f"{func_name}({args_str})"
        elif isinstance(node, ast.Subscript):
            val = cls._get_ast_name(node.value)
            sl = cls._get_ast_name(node.slice)
            return f"{val}[{sl}]"
        elif isinstance(node, ast.Tuple):
            return ", ".join([cls._get_ast_name(elt) for elt in node.elts])
        elif isinstance(node, ast.List):
            return f"[{', '.join([cls._get_ast_name(elt) for elt in node.elts])}]"
        elif isinstance(node, ast.Index):
            return cls._get_ast_name(node.value)
        return ""

    @staticmethod
    def _eval_constant(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        return None
