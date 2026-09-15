"""
Graph Builder for Android Architecture.
Converts extracted Compose/Hilt-Dagger/Room/Retrofit metadata into an interactive
network graph (nodes and edges) and computes architecture metrics via the
framework-neutral analysis layer.
"""

from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set

from analysis import GraphAnalyzer
from language_analyzers.core.annotate import annotate_nodes, mark_edges
from language_analyzers.core.enrichment import enrich_repository
from language_analyzers.core.report_schema import ColumnSpec, ReportCollection
from language_analyzers.core.graph_models import Confidence, RelationKind, Resolution, SourceSpan
from language_analyzers.kotlin import KotlinAnalyzer, KotlinParseCache

from .models import AndroidProjectArchitecture, GraphEdge, GraphNode


class AndroidArchitectureGraphBuilder:
    COLORS = {
        "composable": {
            "background": "#065F46", "border": "#10B981",
            "highlight": {"background": "#047857", "border": "#6EE7B7"},
            "hover": {"background": "#047857", "border": "#34D399"},
        },
        "viewmodel": {
            "background": "#1E40AF", "border": "#3B82F6",
            "highlight": {"background": "#1D4ED8", "border": "#93C5FD"},
            "hover": {"background": "#1D4ED8", "border": "#60A5FA"},
        },
        "di_module": {
            "background": "#7E22CE", "border": "#A855F7",
            "highlight": {"background": "#9333EA", "border": "#E9D5FF"},
            "hover": {"background": "#9333EA", "border": "#C084FC"},
        },
        "di_binding": {
            "background": "#0369A1", "border": "#38BDF8",
            "highlight": {"background": "#0284C7", "border": "#BAE6FD"},
            "hover": {"background": "#0284C7", "border": "#7DD3FC"},
        },
        "dagger_component": {
            "background": "#4338CA", "border": "#6366F1",
            "highlight": {"background": "#4F46E5", "border": "#A5B4FC"},
            "hover": {"background": "#4F46E5", "border": "#818CF8"},
        },
        "room_entity": {
            "background": "#86198F", "border": "#E879F9",
            "highlight": {"background": "#A21CAF", "border": "#F5D0FE"},
            "hover": {"background": "#A21CAF", "border": "#F0ABFC"},
        },
        "room_dao": {
            "background": "#92400E", "border": "#F59E0B",
            "highlight": {"background": "#B45309", "border": "#FDE68A"},
            "hover": {"background": "#B45309", "border": "#FBBF24"},
        },
        "room_query": {
            "background": "#115E59", "border": "#14B8A6",
            "highlight": {"background": "#0F766E", "border": "#99F6E4"},
            "hover": {"background": "#0F766E", "border": "#2DD4BF"},
        },
        "room_database": {
            "background": "#9F1239", "border": "#F43F5E",
            "highlight": {"background": "#BE123C", "border": "#FECDD3"},
            "hover": {"background": "#BE123C", "border": "#FB7185"},
        },
        "retrofit_api": {
            "background": "#7E22CE", "border": "#A855F7",
            "highlight": {"background": "#9333EA", "border": "#E9D5FF"},
            "hover": {"background": "#9333EA", "border": "#C084FC"},
        },
        "retrofit_endpoint": {
            "background": "#1E40AF", "border": "#3B82F6",
            "highlight": {"background": "#1D4ED8", "border": "#93C5FD"},
            "hover": {"background": "#1D4ED8", "border": "#60A5FA"},
        },
        "activity_fragment": {
            "background": "#374151", "border": "#9CA3AF",
            "highlight": {"background": "#4B5563", "border": "#E5E7EB"},
            "hover": {"background": "#4B5563", "border": "#D1D5DB"},
        },
    }

    def __init__(self, include_models: bool = True, include_dependencies: bool = True,
                 include_language_graph: bool = True, parse_cache: Optional[KotlinParseCache] = None):
        self.include_models = include_models
        self.include_dependencies = include_dependencies
        self.include_language_graph = include_language_graph
        self.parse_cache = parse_cache

    FRAMEWORK_RULE_SPECIFICITY = {
        "CALLS": "unique",
        "USES_VIEWMODEL": "unique",
        "PROVIDES": "unique",
        "BINDS": "unique",
        "INSTALLS_IN": "unique",
        "INJECTS": "unique",
        "CALLS_API": "unique",
        "ROUTES": "unique",
        "QUERIES": "unique",
        "CONTAINS": "unique",
        "DEFINES_ENTITY": "unique",
        "HOSTS": "unique",
    }

    def build_graph(self, arch: AndroidProjectArchitecture) -> AndroidProjectArchitecture:
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        node_ids: Set[str] = set()

        def add_node(node: GraphNode):
            nodes.append(node)
            node_ids.add(node.id)

        def by_name(items, attr="name") -> Dict[str, List[object]]:
            result: Dict[str, List[object]] = {}
            for item in items:
                result.setdefault(getattr(item, attr), []).append(item)
            return result

        def resolve(mapping, name, *, require_node=True, exclude_id=None, predicate=None):
            usable = [
                item for item in mapping.get(name) or []
                if item.id != exclude_id
                and (not require_node or item.id in node_ids)
                and (predicate is None or predicate(item))
            ]
            if not usable:
                return None, []
            return usable[0], [item.id for item in usable[1:]]

        def named_edge(from_id, target, others, relation, *, rule_id: str, evidence: SourceSpan,
                       confidence: str = Confidence.FRAMEWORK_INFERRED, **style) -> GraphEdge:
            return GraphEdge(
                from_id=from_id, to_id=target.id, relation=relation,
                confidence=confidence,
                resolution=Resolution.AMBIGUOUS if others else Resolution.UNIQUE_NAME,
                candidates=list(others),
                evidence=evidence,
                metadata={"framework_rule": {"id": rule_id, "specificity": "ambiguous" if others else "unique"}},
                **style,
            )

        composable_by_name = by_name(arch.composables)
        viewmodel_by_name = by_name(arch.viewmodels)
        entity_by_name = by_name(arch.room_entities)
        dao_by_name = by_name(arch.room_daos)
        api_by_name = by_name(arch.retrofit_apis)
        component_by_name = by_name(arch.dagger_components)
        binding_by_injected_type = {b.injected_type: b for b in arch.di_bindings if b.injected_type}
        binding_by_provided_type = {b.provided_type: b for b in arch.di_bindings if b.provided_type}

        for c in arch.composables:
            add_node(GraphNode(
                id=c.id, label=c.name, display_label=f"🧩 {c.name}", group="composable", category="composable",
                title=f"<b>Composable: {c.name}</b><br>Module: {c.module}<br>File: {c.file_path}:{c.line_number}",
                shape="box", size=24, color=self.COLORS["composable"],
                metadata={"name": c.name, "module": c.module, "file_path": c.file_path,
                          "line_number": c.line_number, "end_line_number": c.end_line_number,
                          "calls": c.calls, "uses_viewmodel": c.uses_viewmodel},
            ))
        for c in arch.composables:
            for call_name in c.calls:
                target, others = resolve(composable_by_name, call_name, exclude_id=c.id)
                if target:
                    edges.append(named_edge(
                        c.id, target, others, "CALLS",
                        rule_id="android.composable_calls",
                        evidence=SourceSpan(c.file_path, c.line_number, c.line_number),
                        color="#10B981",
                    ))
            if c.uses_viewmodel:
                target, others = resolve(viewmodel_by_name, c.uses_viewmodel, require_node=False)
                if target:
                    edges.append(named_edge(
                        c.id, target, others, "USES_VIEWMODEL",
                        rule_id="android.composable_uses_viewmodel",
                        evidence=SourceSpan(c.file_path, c.line_number, c.line_number),
                        label="uses", dashes=True, color="#3B82F6",
                    ))

        for v in arch.viewmodels:
            add_node(GraphNode(
                id=v.id, label=v.name, display_label=f"🧠 {v.name}", group="viewmodel", category="viewmodel",
                title=f"<b>ViewModel: {v.name}</b><br>Hilt: {v.is_hilt}<br>Module: {v.module}<br>File: {v.file_path}:{v.line_number}",
                shape="box", size=28, color=self.COLORS["viewmodel"],
                metadata={"name": v.name, "module": v.module, "file_path": v.file_path,
                          "line_number": v.line_number, "end_line_number": v.end_line_number,
                          "is_hilt": v.is_hilt, "injected_types": v.injected_types},
            ))

        if self.include_dependencies:
            for m in arch.di_modules:
                add_node(GraphNode(
                    id=m.id, label=m.name, display_label=f"📁 {m.name}", group="di_module", category="di_module",
                    title=f"<b>DI Module: {m.name}</b><br>Install In: {', '.join(m.install_in)}<br>File: {m.file_path}:{m.line_number}",
                    shape="box", size=30, color=self.COLORS["di_module"],
                    metadata={"name": m.name, "module": m.module, "file_path": m.file_path,
                              "line_number": m.line_number, "end_line_number": m.end_line_number,
                              "install_in": m.install_in},
                ))

            for comp in arch.dagger_components:
                add_node(GraphNode(
                    id=comp.id, label=comp.name, display_label=f"🚀 {comp.name}", group="dagger_component", category="dagger_component",
                    title=f"<b>Dagger Component: {comp.name}</b>{'<br>(synthesized)' if comp.synthesized else ''}",
                    shape="box", size=34, color=self.COLORS["dagger_component"],
                    metadata={"name": comp.name, "file_path": comp.file_path,
                              "line_number": comp.line_number, "end_line_number": comp.end_line_number,
                              "synthesized": comp.synthesized},
                ))

            for b in arch.di_bindings:
                add_node(GraphNode(
                    id=b.id, label=b.name, display_label=f"⚙️ {b.name}", group="di_binding", category="di_binding",
                    title=f"<b>DI Binding: {b.name}</b><br>Kind: {b.kind}<br>File: {b.file_path}:{b.line_number}",
                    shape="ellipse", size=20, color=self.COLORS["di_binding"],
                    symbol_path=f"{b.owner_class_name or ''}.{b.field_name or b.name}",
                    metadata={"name": b.name, "kind": b.kind, "module": b.module, "file_path": b.file_path,
                              "line_number": b.line_number, "end_line_number": b.end_line_number,
                              "provided_type": b.provided_type, "injected_type": b.injected_type,
                              "owner_class_name": b.owner_class_name, "field_name": b.field_name,
                              "symbol_search": f"{b.owner_class_name or ''}.{b.field_name or b.name}"},
                ))

            for m in arch.di_modules:
                for b in arch.di_bindings:
                    if b.owner_module_id == m.id and b.id in node_ids:
                        edges.append(GraphEdge(
                            from_id=m.id, to_id=b.id,
                            relation="PROVIDES" if b.kind == "provides" else "BINDS",
                            confidence=Confidence.FRAMEWORK_INFERRED, resolution=Resolution.UNIQUE_NAME,
                            evidence=SourceSpan(b.file_path, b.line_number, b.line_number),
                            metadata={"framework_rule": {
                                "id": "android.module_provides_binding", "specificity": "unique",
                            }},
                            dashes=True, color="#A855F7",
                        ))
                for target_name in m.install_in:
                    target, others = resolve(component_by_name, target_name)
                    if target:
                        edges.append(named_edge(
                            m.id, target, others, "INSTALLS_IN",
                            rule_id="android.di_module_installs_in",
                            evidence=SourceSpan(m.file_path, m.line_number, m.line_number),
                            color="#818CF8",
                        ))

            for v in arch.viewmodels:
                for injected_type in v.injected_types:
                    binding = binding_by_injected_type.get(injected_type) or binding_by_provided_type.get(injected_type)
                    if binding and binding.id in node_ids:
                        edges.append(GraphEdge(
                            from_id=v.id, to_id=binding.id, relation="INJECTS",
                            confidence=Confidence.FRAMEWORK_INFERRED, resolution=Resolution.UNIQUE_NAME,
                            evidence=SourceSpan(binding.file_path, binding.line_number, binding.line_number),
                            metadata={"framework_rule": {
                                "id": "android.viewmodel_injects_binding", "specificity": "unique",
                            }},
                            label="injects", dashes=True, color="#38BDF8",
                        ))
                    api, api_others = resolve(
                        api_by_name, injected_type, require_node=False,
                        predicate=lambda item: any(
                            call in {e.name for e in item.endpoints} for call in v.calls
                        ),
                    )
                    if api:
                        edges.append(named_edge(
                            v.id, api, api_others, "CALLS_API",
                            rule_id="android.viewmodel_calls_api",
                            evidence=SourceSpan(v.file_path, v.line_number, v.line_number),
                            label="calls", dashes=True, color="#A855F7",
                        ))

        if self.include_models:
            for e in arch.room_entities:
                add_node(GraphNode(
                    id=e.id, label=e.name, display_label=f"📦 {e.name}\n({len(e.fields)} fields)", group="room_entity", category="room_entity",
                    title=f"<b>Room Entity: {e.name}</b><br>Fields: {len(e.fields)}<br>File: {e.file_path}:{e.line_number}",
                    shape="box", size=20, color=self.COLORS["room_entity"],
                    metadata={"name": e.name, "module": e.module, "file_path": e.file_path,
                              "line_number": e.line_number, "end_line_number": e.end_line_number,
                              "fields": [f.__dict__ for f in e.fields]},
                ))

        for d in arch.room_daos:
            add_node(GraphNode(
                id=d.id, label=d.name, display_label=f"🗄️ {d.name}", group="room_dao", category="room_dao",
                title=f"<b>Room DAO: {d.name}</b><br>Methods: {len(d.methods)}<br>File: {d.file_path}:{d.line_number}",
                shape="box", size=28, color=self.COLORS["room_dao"],
                metadata={"name": d.name, "module": d.module, "file_path": d.file_path,
                          "line_number": d.line_number, "end_line_number": d.end_line_number},
            ))
            for method in d.methods:
                add_node(GraphNode(
                    id=method.id, label=method.name, display_label=f"{method.kind.upper()} {method.name}()", group="room_query", category="room_query",
                    title=f"<b>{method.kind}: {method.name}()</b><br>{method.query_text or ''}",
                    shape="box", size=18, color=self.COLORS["room_query"],
                    metadata={"name": method.name, "kind": method.kind, "query_text": method.query_text,
                              "return_type": method.return_type, "file_path": d.file_path,
                              "line_number": method.line_number, "end_line_number": method.end_line_number},
                ))
                edges.append(GraphEdge(from_id=d.id, to_id=method.id, relation="ROUTES", color="#F59E0B"))
                if self.include_models and method.return_type:
                    entity, others = resolve(entity_by_name, method.return_type)
                    if entity:
                        edges.append(named_edge(
                            method.id, entity, others, "QUERIES",
                            rule_id="android.dao_method_queries",
                            evidence=SourceSpan(d.file_path, method.line_number, method.line_number),
                            label="queries", dashes=True, color="#E879F9",
                        ))

        for db in arch.room_databases:
            add_node(GraphNode(
                id=db.id, label=db.name, display_label=f"🚀 {db.name}", group="room_database", category="room_database",
                title=f"<b>Room Database: {db.name}</b><br>Entities: {', '.join(db.entity_names)}",
                shape="box", size=34, color=self.COLORS["room_database"],
                metadata={"name": db.name, "module": db.module, "file_path": db.file_path,
                          "line_number": db.line_number, "end_line_number": db.end_line_number,
                          "entity_names": db.entity_names},
            ))
            for dao_type in db.dao_accessors:
                dao, others = resolve(dao_by_name, dao_type)
                if dao:
                    edges.append(named_edge(
                        db.id, dao, others, "CONTAINS",
                        rule_id="android.database_contains_dao",
                        evidence=SourceSpan(db.file_path, db.line_number, db.line_number),
                        color="#F43F5E",
                    ))
            if self.include_models:
                for entity_name in db.entity_names:
                    entity, others = resolve(entity_by_name, entity_name)
                    if entity:
                        edges.append(named_edge(
                            db.id, entity, others, "DEFINES_ENTITY",
                            rule_id="android.database_defines_entity",
                            evidence=SourceSpan(db.file_path, db.line_number, db.line_number),
                            color="#F43F5E",
                        ))

        for api in arch.retrofit_apis:
            add_node(GraphNode(
                id=api.id, label=api.name, display_label=f"📁 {api.name}", group="retrofit_api", category="retrofit_api",
                title=f"<b>Retrofit API: {api.name}</b><br>Endpoints: {len(api.endpoints)}<br>File: {api.file_path}:{api.line_number}",
                shape="box", size=30, color=self.COLORS["retrofit_api"],
                metadata={"name": api.name, "module": api.module, "file_path": api.file_path,
                          "line_number": api.line_number, "end_line_number": api.end_line_number},
            ))
            for ep in api.endpoints:
                add_node(GraphNode(
                    id=ep.id, label=ep.name, display_label=f"{ep.http_method} {ep.path}\n{ep.name}()", group="retrofit_endpoint", category="retrofit_endpoint",
                    title=f"<b>[{ep.http_method}] {ep.path}</b><br>Handler: {ep.name}()",
                    shape="box", size=20, color=self.COLORS["retrofit_endpoint"],
                    metadata={"name": ep.name, "http_method": ep.http_method, "path": ep.path,
                              "file_path": api.file_path,
                              "line_number": ep.line_number, "end_line_number": ep.end_line_number},
                ))
                edges.append(GraphEdge(from_id=api.id, to_id=ep.id, relation="ROUTES", color="#A855F7"))

        for af in arch.activities_fragments:
            add_node(GraphNode(
                id=af.id, label=af.name, display_label=f"📱 {af.name}", group="activity_fragment", category="activity_fragment",
                title=f"<b>{af.kind.title()}: {af.name}</b><br>Hilt Entry Point: {af.is_hilt_entry_point}<br>File: {af.file_path}:{af.line_number}",
                shape="box", size=32, color=self.COLORS["activity_fragment"],
                metadata={"name": af.name, "kind": af.kind, "module": af.module, "file_path": af.file_path,
                          "line_number": af.line_number, "end_line_number": af.end_line_number,
                          "is_hilt_entry_point": af.is_hilt_entry_point},
            ))
            for composable_name in af.hosted_composables:
                target, others = resolve(composable_by_name, composable_name)
                if target:
                    edges.append(named_edge(
                        af.id, target, others, "HOSTS",
                        rule_id="android.activity_hosts_composable",
                        evidence=SourceSpan(af.file_path, af.line_number, af.line_number),
                        color="#9CA3AF",
                    ))

        annotate_nodes(nodes, arch.project_path, "android", "kotlin")
        mark_edges(edges, nodes=nodes, rule_namespace="android",
                   rule_specificity=self.FRAMEWORK_RULE_SPECIFICITY)
        if self.include_language_graph:
            try:
                language_nodes, language_edges = KotlinAnalyzer(arch.project_path, parse_cache=self.parse_cache).build()
            except ImportError:
                language_nodes, language_edges = [], []
            known_ids = {node.id for node in nodes}
            nodes.extend(node for node in language_nodes if node.id not in known_ids)
            edges.extend(language_edges)
            if language_nodes:
                edges.extend(self._implementation_edges(arch, nodes))

        arch.nodes = nodes
        arch.edges = edges
        enrich_repository(arch)
        arch.stats = {
            "total_composables": len(arch.composables),
            "total_viewmodels": len(arch.viewmodels),
            "total_di_bindings": len(arch.di_bindings),
            "total_room_entities": len(arch.room_entities),
            "total_retrofit_apis": len(arch.retrofit_apis),
        }
        arch.stats["analysis"] = GraphAnalyzer().analyze(
            arch.nodes,
            arch.edges,
            project_path=arch.project_path,
        )
        arch.report_collections = self._build_report_collections(arch)

        return arch

    def _implementation_edges(self, arch: AndroidProjectArchitecture, nodes: List[GraphNode]) -> List[GraphEdge]:
        symbol_ids = {
            (Path(str(node.metadata.get("file_path", ""))).as_posix(), str(node.metadata.get("qualname", ""))): node.id
            for node in nodes if node.provenance == "kotlin-core" and node.metadata.get("qualname")
        }
        node_ids = {node.id for node in nodes}
        edges: List[GraphEdge] = []

        def add(source_id: str, file_path: str, qualname: str) -> bool:
            target_id = symbol_ids.get((Path(file_path).as_posix(), qualname))
            if not target_id or source_id not in node_ids:
                return False
            edges.append(GraphEdge(
                from_id=source_id, to_id=target_id, relation=RelationKind.IMPLEMENTED_BY,
                confidence=Confidence.FRAMEWORK_INFERRED, resolution=Resolution.UNIQUE_NAME,
                evidence=SourceSpan(Path(file_path).as_posix(), 1, 1),
                metadata={"framework_rule": {"id": "android.implemented_by", "specificity": "unique"}},
            ))
            return True

        for item in [*arch.composables, *arch.viewmodels, *arch.room_entities, *arch.room_daos,
                     *arch.room_databases, *arch.di_modules, *arch.dagger_components,
                     *arch.retrofit_apis, *arch.activities_fragments]:
            add(item.id, item.file_path, item.name)
        for dao in arch.room_daos:
            for method in dao.methods:
                add(method.id, dao.file_path, f"{dao.name}.{method.name}")
        for api in arch.retrofit_apis:
            for endpoint in api.endpoints:
                add(endpoint.id, api.file_path, f"{api.name}.{endpoint.name}")
        modules = {module.id: module for module in arch.di_modules}
        for binding in arch.di_bindings:
            if binding.kind in {"provides", "binds"}:
                owner = modules.get(binding.owner_module_id)
                if owner:
                    add(binding.id, binding.file_path, f"{owner.name}.{binding.name}")
            elif binding.kind == "inject_constructor":
                add(binding.id, binding.file_path, binding.injected_type or binding.name)
            elif binding.kind == "inject_field":
                owner = binding.owner_class_name or ""
                field = binding.field_name or binding.name
                add(binding.id, binding.file_path, f"{owner}.{field}")
        return edges

    @staticmethod
    def _build_report_collections(arch: AndroidProjectArchitecture) -> List[ReportCollection]:
        return [
            ReportCollection(
                key="composables", label="Composables", view="grid", node_category="composable",
                columns=[
                    ColumnSpec("module", "Module", "mono"),
                    ColumnSpec("uses_viewmodel", "ViewModel", "text"),
                    ColumnSpec("calls", "Calls", "list"),
                ],
                rows=[{"id": c.id, "name": c.name, "module": c.module,
                       "uses_viewmodel": c.uses_viewmodel, "calls": c.calls} for c in arch.composables],
            ),
            ReportCollection(
                key="viewmodels", label="ViewModels", view="grid", node_category="viewmodel",
                columns=[
                    ColumnSpec("is_hilt", "Hilt", "text"),
                    ColumnSpec("injected_types", "Injected Types", "list"),
                ],
                rows=[{"id": v.id, "name": v.name, "is_hilt": v.is_hilt,
                       "injected_types": v.injected_types} for v in arch.viewmodels],
            ),
            ReportCollection(
                key="di_bindings", label="DI Bindings", view="grid", node_category="di_binding",
                columns=[
                    ColumnSpec("kind", "Kind", "text"),
                    ColumnSpec("module", "Module", "mono"),
                ],
                rows=[{"id": b.id, "name": b.name, "kind": b.kind, "module": b.module} for b in arch.di_bindings],
            ),
            ReportCollection(
                key="room_entities", label="Room Entities", view="grid", node_category="room_entity",
                columns=[
                    ColumnSpec("fields", "Fields", "list"),
                ],
                rows=[{"id": e.id, "name": e.name,
                       "fields": [f"{f.name}: {f.type_annotation}" for f in e.fields]} for e in arch.room_entities],
            ),
            ReportCollection(
                key="retrofit_apis", label="Retrofit APIs", view="grid", node_category="retrofit_api",
                columns=[
                    ColumnSpec("endpoints", "Endpoints", "list"),
                ],
                rows=[{"id": a.id, "name": a.name,
                       "endpoints": [f"{ep.http_method} {ep.path}" for ep in a.endpoints]} for a in arch.retrofit_apis],
            ),
        ]

    def generate_mermaid(self, arch: AndroidProjectArchitecture) -> str:
        lines = ["graph TD", "  %% Android Architecture Diagram"]
        for edge in arch.edges:
            lbl = f"|{edge.label}|" if edge.label else ""
            arrow = "-.->" if edge.dashes else "-->"
            lines.append(f"  {edge.from_id} {arrow}{lbl} {edge.to_id}")
        return "\n".join(lines)
