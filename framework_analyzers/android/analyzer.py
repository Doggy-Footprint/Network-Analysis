from __future__ import annotations

"""
Kotlin/Android AST entry point.
Walks .kt files with tree-sitter, extracts Compose/Hilt-Dagger/Room/Retrofit/ViewModel
declarations, and links them into an AndroidProjectArchitecture.
"""

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from repository.models import RepositorySnapshot

from framework_analyzers.migration_tables import normalize_table_name, sql_table_refs
from language_analyzers.kotlin import ast as ka
from .models import (
    ActivityFragmentInfo,
    AndroidProjectArchitecture,
    ComposableInfo,
    DaggerComponentInfo,
    DiBindingInfo,
    DiModuleInfo,
    RetrofitApiInfo,
    RetrofitEndpointInfo,
    RoomDaoInfo,
    RoomDatabaseInfo,
    RoomEntityInfo,
    RoomFieldInfo,
    RoomMigrationInfo,
    RoomQueryMethodInfo,
    ViewModelInfo,
)

EXCLUDED_DIRS = {"build", ".gradle", ".idea", ".git", "generated"}
HTTP_METHOD_ANNOTATIONS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
QUERY_METHOD_ANNOTATIONS = {
    "Query": "query",
    "Insert": "insert",
    "Update": "update",
    "Delete": "delete",
    "Transaction": "transaction",
}
VIEWMODEL_SUPERTYPES = {"ViewModel", "AndroidViewModel"}
ACTIVITY_SUPERTYPES = {"Activity", "AppCompatActivity", "ComponentActivity", "FragmentActivity"}
FRAGMENT_SUPERTYPES = {"Fragment", "DialogFragment"}


def _descendants(node):
    for child in node.children:
        yield child
        yield from _descendants(child)


class AndroidAnalyzer:
    def __init__(
        self,
        project_path: Union[str, Path],
        entrypoint: Optional[str] = None,
        parse_cache: Optional[ka.KotlinParseCache] = None,
        snapshot: Optional[RepositorySnapshot] = None,
    ):
        self.snapshot = snapshot
        if snapshot is None:
            self.project_path = Path(project_path).resolve()
        else:
            supplied = Path(project_path)
            snapshot_root = Path(snapshot.root)
            if not supplied.is_absolute() or not snapshot_root.is_absolute() or supplied != snapshot_root:
                raise ValueError("project path and snapshot root must be absolute and match")
            self.project_path = snapshot_root
        self.entrypoint = entrypoint  # unused; kept for CLI symmetry with FastAPIAnalyzer
        self._parse_cache = parse_cache if parse_cache is not None else ka.KotlinParseCache()

    def analyze(self) -> AndroidProjectArchitecture:
        arch = AndroidProjectArchitecture(
            project_name=self.project_path.name,
            project_path=str(self.project_path),
        )

        for file_path in self._discover_files():
            try:
                if self.snapshot is None:
                    source, root = self._parse_cache.read_and_parse(file_path)
                else:
                    source = self.snapshot.content_map()[file_path.relative_to(self.project_path).as_posix()].encode("utf-8")
                    source, root = self._parse_cache.parse_snapshot(file_path, source)
            except OSError:
                continue
            module = self._module_for(file_path)
            for decl in ka.top_level_declarations(root):
                self._extract_declaration(decl, source, module, arch)
            self._extract_migration_properties(root, source, module, arch)

        self._link(arch)

        return arch

    def _discover_files(self) -> List[Path]:
        if self.snapshot is not None:
            return sorted(self.project_path / relative for relative, _source in self.snapshot.contents
                          if relative.endswith(".kt")
                          and not any(part in EXCLUDED_DIRS for part in Path(relative).parts))
        files = []
        for dirpath, dirnames, filenames in os.walk(self.project_path):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
            for filename in filenames:
                if filename.endswith(".kt"):
                    files.append(Path(dirpath) / filename)
        return sorted(files)

    def _module_for(self, file_path: Path) -> str:
        try:
            return str(file_path.relative_to(self.project_path))
        except ValueError:
            return str(file_path)

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def _extract_declaration(self, decl, source: bytes, module: str, arch: AndroidProjectArchitecture):
        if decl.type == "function_declaration":
            anns = dict(ka.annotations(decl, source))
            if "Composable" in anns:
                self._extract_composable(decl, source, module, arch)
            return

        if decl.type not in ("class_declaration", "object_declaration"):
            return

        anns = dict(ka.annotations(decl, source))
        name = ka.declared_name(decl, source) or "?"
        supertypes = set(ka.supertype_names(decl, source))
        is_iface = ka.is_interface(decl)
        is_viewmodel = "HiltViewModel" in anns or bool(supertypes & VIEWMODEL_SUPERTYPES)

        if "Entity" in anns:
            self._extract_room_entity(decl, source, module, name, anns["Entity"], arch)
        if self._is_migration(decl, source):
            arch.room_migrations.append(self._migration_info(decl, decl, source, module, name, True))
        if "Dao" in anns:
            self._extract_room_dao(decl, source, module, name, arch)
        if "Database" in anns:
            self._extract_room_database(decl, source, module, name, anns, arch)
        if "Module" in anns:
            self._extract_di_module(decl, source, module, name, anns, arch)
        if "Component" in anns or "Subcomponent" in anns:
            arch.dagger_components.append(DaggerComponentInfo(
                id=f"component_{module}_{name}",
                name=name,
                module=module,
                file_path=module,
                line_number=ka.start_line(decl),
                end_line_number=ka.end_line(decl),
            ))

        if is_viewmodel:
            self._extract_viewmodel(decl, source, module, name, arch)
        else:
            ctor = ka.primary_constructor(decl)
            if ctor is not None and ka.has_annotation(ctor, source, "Inject"):
                arch.di_bindings.append(DiBindingInfo(
                    id=f"dibind_ctor_{module}_{name}",
                    name=name,
                    kind="inject_constructor",
                    module=module,
                    file_path=module,
                    line_number=ka.start_line(ctor),
                    end_line_number=ka.end_line(decl),
                    injected_type=name,
                ))

        self._extract_inject_fields(decl, source, module, name, arch)

        if is_iface and "Dao" not in anns:
            endpoints = self._retrofit_endpoints(decl, source)
            if endpoints:
                arch.retrofit_apis.append(RetrofitApiInfo(
                    id=f"api_{module}_{name}",
                    name=name,
                    module=module,
                    file_path=module,
                    line_number=ka.start_line(decl),
                    end_line_number=ka.end_line(decl),
                    endpoints=endpoints,
                ))

        if supertypes & ACTIVITY_SUPERTYPES:
            self._extract_activity_fragment(decl, source, module, name, anns, "activity", arch)
        elif supertypes & FRAGMENT_SUPERTYPES:
            self._extract_activity_fragment(decl, source, module, name, anns, "fragment", arch)

    def _extract_composable(self, decl, source: bytes, module: str, arch: AndroidProjectArchitecture):
        name = ka.declared_name(decl, source) or "?"
        params = ka.function_params(decl, source)
        calls = [c["name"] for c in ka.call_expressions(decl, source)]

        uses_viewmodel = None
        for param in params:
            if param["type"] and param["type"].endswith("ViewModel"):
                uses_viewmodel = param["type"]
        if uses_viewmodel is None:
            for call in ka.call_expressions(decl, source):
                if call["name"] in ("hiltViewModel", "viewModel") and call["type_args"]:
                    uses_viewmodel = call["type_args"][0]

        arch.composables.append(ComposableInfo(
            id=f"composable_{module}_{name}_{ka.start_line(decl)}",
            name=name,
            module=module,
            file_path=module,
            line_number=ka.start_line(decl),
            end_line_number=ka.end_line(decl),
            calls=calls,
            uses_viewmodel=uses_viewmodel,
        ))

    def _extract_room_entity(self, decl, source: bytes, module: str, name: str, entity_annotation,
                             arch: AndroidProjectArchitecture):
        fields = []
        ctor = ka.primary_constructor(decl)
        if ctor is not None:
            for param in ka.class_parameters(ctor, source):
                if not param["name"]:
                    continue
                fields.append(RoomFieldInfo(
                    name=param["name"],
                    type_annotation=param["type"] or "",
                    is_primary_key="PrimaryKey" in param["annotations"],
                ))
        table_match = re.search(r'\btableName\s*=\s*"([^"]*)"', ka.annotation_args_text(entity_annotation, source))
        arch.room_entities.append(RoomEntityInfo(
            id=f"entity_{module}_{name}",
            name=name,
            module=module,
            file_path=module,
            line_number=ka.start_line(decl),
            end_line_number=ka.end_line(decl),
            fields=fields,
            table_name=normalize_table_name(table_match.group(1) if table_match else name) or "",
        ))

    @staticmethod
    def _is_migration(node, source: bytes) -> bool:
        """True for a declaration or object literal with a `Migration(...)` supertype call."""
        for child in node.children:
            if child.type != "delegation_specifier":
                continue
            for invocation in child.children:
                if invocation.type != "constructor_invocation":
                    continue
                for user_type in invocation.children:
                    if user_type.type == "user_type" and ka.node_text(source, user_type).split(".")[-1].strip() == "Migration":
                        return True
        return False

    def _extract_migration_properties(self, container, source: bytes, module: str, arch: AndroidProjectArchitecture):
        for child in container.children:
            if child.type == "property_declaration":
                literal = next((c for c in child.children if c.type == "object_literal"), None)
                if literal is None or not self._is_migration(literal, source):
                    continue
                variable = next((c for c in child.children if c.type == "variable_declaration"), None)
                name = ka.declared_name(variable, source) if variable is not None else None
                if name:
                    arch.room_migrations.append(self._migration_info(child, literal, source, module, name, False))
            elif child.type in ("class_declaration", "object_declaration", "companion_object"):
                body = ka.class_body(child)
                if body is not None:
                    self._extract_migration_properties(body, source, module, arch)

    def _migration_info(self, span_node, body_node, source: bytes, module: str, name: str,
                        is_declaration: bool) -> RoomMigrationInfo:
        return RoomMigrationInfo(
            id=f"room_migration_{module}_{name}",
            name=name,
            module=module,
            file_path=module,
            line_number=ka.start_line(span_node),
            end_line_number=ka.end_line(span_node),
            is_declaration=is_declaration,
            table_refs=self._exec_sql_refs(body_node, source),
        )

    @staticmethod
    def _exec_sql_refs(node, source: bytes) -> List[Optional[str]]:
        refs: List[Optional[str]] = []

        def first_argument(call):
            for suffix in call.children:
                if suffix.type != "call_suffix":
                    continue
                for arguments in suffix.children:
                    if arguments.type == "value_arguments":
                        return next((a for a in arguments.children if a.type == "value_argument"), None)
            return None

        def callee(call) -> Optional[str]:
            for child in call.children:
                if child.type == "navigation_expression":
                    suffixes = [g for g in child.children if g.type == "navigation_suffix"]
                    identifiers = [g for g in suffixes[-1].children if g.type == "simple_identifier"] if suffixes else []
                    return ka.node_text(source, identifiers[-1]) if identifiers else None
                if child.type == "simple_identifier":
                    return ka.node_text(source, child)
            return None

        def literal_value(argument) -> Optional[str]:
            value = argument.children[-1] if argument.children else None
            if value is None or value.type != "string_literal" or len(argument.children) not in (1, 3):
                return None
            if any(c.type in ("interpolation", "interpolated_identifier", "interpolated_expression")
                   for c in _descendants(value)):
                return None
            text = ka.node_text(source, value)
            if text.startswith('"""') and text.endswith('"""') and len(text) >= 6:
                return text[3:-3]
            return re.sub(r'\\(.)', lambda m: {"n": " ", "t": " "}.get(m.group(1), m.group(1)), text[1:-1])

        def walk(current):
            if current.type == "call_expression" and callee(current) == "execSQL":
                argument = first_argument(current)
                if argument is not None:
                    text = literal_value(argument)
                    if text is None:
                        refs.append(None)
                    else:
                        refs.extend(sql_table_refs(text))
            for child in current.children:
                walk(child)

        walk(node)
        return refs

    def _extract_room_dao(self, decl, source: bytes, module: str, name: str, arch: AndroidProjectArchitecture):
        methods = []
        for method in ka.nested_declarations(decl):
            if method.type != "function_declaration":
                continue
            method_anns = dict(ka.annotations(method, source))
            kind = next((v for k, v in QUERY_METHOD_ANNOTATIONS.items() if k in method_anns), None)
            if kind is None:
                continue
            method_name = ka.declared_name(method, source) or "?"
            query_text = None
            if "Query" in method_anns:
                query_text = ka.annotation_first_string_arg(method_anns["Query"], source)
            base_type, inner_type = ka.function_return_types(method, source)
            methods.append(RoomQueryMethodInfo(
                id=f"query_{module}_{name}_{method_name}_{ka.start_line(method)}",
                name=method_name,
                kind=kind,
                query_text=query_text,
                return_type=inner_type or base_type,
                line_number=ka.start_line(method),
                end_line_number=ka.end_line(method),
            ))
        arch.room_daos.append(RoomDaoInfo(
            id=f"dao_{module}_{name}",
            name=name,
            module=module,
            file_path=module,
            line_number=ka.start_line(decl),
            end_line_number=ka.end_line(decl),
            methods=methods,
        ))

    def _extract_room_database(self, decl, source: bytes, module: str, name: str, anns: Dict[str, Any], arch: AndroidProjectArchitecture):
        entity_names = ka.annotation_class_literal_args(anns["Database"], source)
        dao_accessors = []
        for method in ka.nested_declarations(decl):
            if method.type != "function_declaration":
                continue
            base_type, _ = ka.function_return_types(method, source)
            if base_type:
                dao_accessors.append(base_type)
        arch.room_databases.append(RoomDatabaseInfo(
            id=f"database_{module}_{name}",
            name=name,
            module=module,
            file_path=module,
            line_number=ka.start_line(decl),
            end_line_number=ka.end_line(decl),
            entity_names=entity_names,
            dao_accessors=dao_accessors,
        ))

    def _extract_di_module(self, decl, source: bytes, module: str, name: str, anns: Dict[str, Any], arch: AndroidProjectArchitecture):
        install_in = []
        if "InstallIn" in anns:
            install_in = ka.annotation_class_literal_args(anns["InstallIn"], source)
        module_id = f"dimodule_{module}_{name}"
        arch.di_modules.append(DiModuleInfo(
            id=module_id,
            name=name,
            module=module,
            file_path=module,
            line_number=ka.start_line(decl),
            end_line_number=ka.end_line(decl),
            install_in=install_in,
        ))

        for method in ka.nested_declarations(decl):
            if method.type != "function_declaration":
                continue
            method_anns = dict(ka.annotations(method, source))
            kind = "provides" if "Provides" in method_anns else ("binds" if "Binds" in method_anns else None)
            if kind is None:
                continue
            method_name = ka.declared_name(method, source) or "?"
            base_type, _ = ka.function_return_types(method, source)
            arch.di_bindings.append(DiBindingInfo(
                id=f"dibind_{module}_{name}_{method_name}",
                name=method_name,
                kind=kind,
                module=module,
                file_path=module,
                line_number=ka.start_line(method),
                end_line_number=ka.end_line(method),
                owner_module_id=module_id,
                provided_type=base_type,
            ))

    def _extract_viewmodel(self, decl, source: bytes, module: str, name: str, arch: AndroidProjectArchitecture):
        is_hilt = ka.has_annotation(decl, source, "HiltViewModel")
        injected_types = []
        ctor = ka.primary_constructor(decl)
        if ctor is not None:
            injected_types = [p["type"] for p in ka.class_parameters(ctor, source) if p["type"]]

        calls: List[str] = []
        for method in ka.nested_declarations(decl):
            if method.type == "function_declaration":
                calls.extend(c["name"] for c in ka.call_expressions(method, source))

        arch.viewmodels.append(ViewModelInfo(
            id=f"viewmodel_{module}_{name}",
            name=name,
            module=module,
            file_path=module,
            line_number=ka.start_line(decl),
            end_line_number=ka.end_line(decl),
            is_hilt=is_hilt,
            injected_types=injected_types,
            calls=calls,
        ))

    def _extract_inject_fields(self, decl, source: bytes, module: str, name: str, arch: AndroidProjectArchitecture):
        body = ka.class_body(decl)
        if body is None:
            return
        for child in body.children:
            if child.type != "property_declaration":
                continue
            if not ka.has_annotation(child, source, "Inject"):
                continue
            prop_name = None
            prop_type = None
            for c in child.children:
                if c.type == "variable_declaration":
                    for gc in c.children:
                        if gc.type == "simple_identifier" and prop_name is None:
                            prop_name = ka.node_text(source, gc)
                        elif gc.type == "user_type":
                            prop_type = ka.node_text(source, gc)
            if prop_name is None:
                continue
            arch.di_bindings.append(DiBindingInfo(
                id=f"dibind_field_{module}_{name}_{prop_name}",
                name=prop_name,
                kind="inject_field",
                module=module,
                file_path=module,
                line_number=ka.start_line(child),
                end_line_number=ka.end_line(child),
                injected_type=prop_type,
                owner_class_name=name,
                field_name=prop_name,
            ))

    def _retrofit_endpoints(self, decl, source: bytes) -> List[RetrofitEndpointInfo]:
        endpoints = []
        module_placeholder = ""
        name_placeholder = ka.declared_name(decl, source) or "?"
        for method in ka.nested_declarations(decl):
            if method.type != "function_declaration":
                continue
            method_anns = dict(ka.annotations(method, source))
            http_method = next((m for m in HTTP_METHOD_ANNOTATIONS if m in method_anns), None)
            if http_method is None:
                continue
            method_name = ka.declared_name(method, source) or "?"
            path = ka.annotation_first_string_arg(method_anns[http_method], source) or ""
            endpoints.append(RetrofitEndpointInfo(
                id=f"retrofit_{name_placeholder}_{method_name}",
                name=method_name,
                http_method=http_method,
                path=path,
                line_number=ka.start_line(method),
                end_line_number=ka.end_line(method),
            ))
        return endpoints

    def _extract_activity_fragment(self, decl, source: bytes, module: str, name: str, anns: Dict[str, Any], kind: str, arch: AndroidProjectArchitecture):
        is_hilt_entry_point = "AndroidEntryPoint" in anns
        hosted_composables: List[str] = []
        for method in ka.nested_declarations(decl):
            if method.type != "function_declaration":
                continue
            calls = ka.call_expressions(method, source)
            if any(c["name"] == "setContent" for c in calls):
                hosted_composables.extend(c["name"] for c in calls if c["name"] != "setContent")

        arch.activities_fragments.append(ActivityFragmentInfo(
            id=f"{kind}_{module}_{name}",
            name=name,
            kind=kind,
            module=module,
            file_path=module,
            line_number=ka.start_line(decl),
            end_line_number=ka.end_line(decl),
            is_hilt_entry_point=is_hilt_entry_point,
            hosted_composables=hosted_composables,
        ))

    # ------------------------------------------------------------------
    # Linking (cross-declaration resolution once every file has been parsed)
    # ------------------------------------------------------------------

    def _link(self, arch: AndroidProjectArchitecture):
        component_names = {c.name for c in arch.dagger_components}
        for dimodule in arch.di_modules:
            for target in dimodule.install_in:
                if target not in component_names:
                    arch.dagger_components.append(DaggerComponentInfo(
                        id=f"component_synth_{target}",
                        name=target,
                        synthesized=True,
                    ))
                    component_names.add(target)
