"""
Graph Builder and Topology Solver for FastAPI Architecture.
Converts extracted architecture metadata into an interactive network graph (nodes and edges)
and computes architecture metrics.
"""

import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from analysis import GraphAnalyzer
from language_analyzers.core.annotate import annotate_nodes, mark_edges, relative_repo_path
from language_analyzers.core.enrichment import enrich_repository
from language_analyzers.core.graph_models import Confidence, RelationKind, Resolution, SourceSpan
from language_analyzers.core.report_schema import ColumnSpec, ReportCollection
from language_analyzers.python.graph import PythonGraphAnalyzer
from language_analyzers.python.source import PythonSourceAnalyzer
from language_analyzers.python.symbols import symbol_id

from .models import (
    AppInfo,
    DependencyInfo,
    EndpointInfo,
    GraphEdge,
    GraphNode,
    ProjectArchitecture,
    RouterInfo,
    SchemaInfo,
)


class ArchitectureGraphBuilder:
    COLORS = {
        "app": {
            "background": "#4338CA",
            "border": "#6366F1",
            "highlight": {"background": "#4F46E5", "border": "#A5B4FC"},
            "hover": {"background": "#4F46E5", "border": "#818CF8"},
        },
        "router": {
            "background": "#7E22CE",
            "border": "#A855F7",
            "highlight": {"background": "#9333EA", "border": "#E9D5FF"},
            "hover": {"background": "#9333EA", "border": "#C084FC"},
        },
        "endpoint_get": {
            "background": "#065F46",
            "border": "#10B981",
            "highlight": {"background": "#047857", "border": "#6EE7B7"},
            "hover": {"background": "#047857", "border": "#34D399"},
        },
        "endpoint_post": {
            "background": "#1E40AF",
            "border": "#3B82F6",
            "highlight": {"background": "#1D4ED8", "border": "#93C5FD"},
            "hover": {"background": "#1D4ED8", "border": "#60A5FA"},
        },
        "endpoint_put": {
            "background": "#92400E",
            "border": "#F59E0B",
            "highlight": {"background": "#B45309", "border": "#FDE68A"},
            "hover": {"background": "#B45309", "border": "#FBBF24"},
        },
        "endpoint_delete": {
            "background": "#9F1239",
            "border": "#F43F5E",
            "highlight": {"background": "#BE123C", "border": "#FECDD3"},
            "hover": {"background": "#BE123C", "border": "#FB7185"},
        },
        "endpoint_patch": {
            "background": "#115E59",
            "border": "#14B8A6",
            "highlight": {"background": "#0F766E", "border": "#99F6E4"},
            "hover": {"background": "#0F766E", "border": "#2DD4BF"},
        },
        "endpoint_other": {
            "background": "#374151",
            "border": "#9CA3AF",
            "highlight": {"background": "#4B5563", "border": "#E5E7EB"},
            "hover": {"background": "#4B5563", "border": "#D1D5DB"},
        },
        "dependency": {
            "background": "#0369A1",
            "border": "#38BDF8",
            "highlight": {"background": "#0284C7", "border": "#BAE6FD"},
            "hover": {"background": "#0284C7", "border": "#7DD3FC"},
        },
        "schema": {
            "background": "#86198F",
            "border": "#E879F9",
            "highlight": {"background": "#A21CAF", "border": "#F5D0FE"},
            "hover": {"background": "#A21CAF", "border": "#F0ABFC"},
        },
        "middleware": {
            "background": "#334155",
            "border": "#94A3B8",
            "highlight": {"background": "#475569", "border": "#E2E8F0"},
            "hover": {"background": "#475569", "border": "#CBD5E1"},
        },
    }

    PROVENANCE = "fastapi"

    def __init__(
        self,
        include_models: bool = True,
        include_dependencies: bool = True,
        include_language_graph: bool = True,
    ):
        self.include_models = include_models
        self.include_dependencies = include_dependencies
        self.include_language_graph = include_language_graph

    FRAMEWORK_RULE_SPECIFICITY = {
        "MIDDLEWARE_OF": "unique",
        "INCLUDES": "unique",
        "ROUTES": "unique",
        "DEPENDS_ON": "unique",
        "SUB_DEPENDENCY": "unique",
        "REQUEST_BODY": "unique",
        "RESPONSE_MODEL": "unique",
    }

    def build_graph(self, arch: ProjectArchitecture) -> ProjectArchitecture:
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        node_ids: Set[str] = set()
        root = Path(arch.project_path)

        for app in arch.apps:
            node = GraphNode(
                id=app.id,
                label=app.var_name,
                display_label=f"🚀 {app.title}\napp: {app.var_name}",
                group="app",
                category="app",
                title=f"<b>FastAPI Application: {app.title if app.title_source != 'unresolved' else app.title_expr}</b><br>Version: {app.version}<br>Module: {app.module}<br>File: {app.file_path}:{app.line_number}",
                shape="box",
                size=38,
                color=self.COLORS["app"],
                metadata={
                    "type": "app",
                    "title": app.title,
                    "title_source": app.title_source,
                    "title_expr": app.title_expr,
                    "version": app.version,
                    "module": app.module,
                    "file_path": app.file_path,
                    "line_number": app.line_number,
                    "end_line_number": app.end_line_number,
                    "middlewares": app.middlewares,
                }
            )
            nodes.append(node)
            node_ids.add(node.id)

            for mw in app.middlewares:
                mw_id = f"mw_{app.id}_{mw['name']}"
                if mw_id not in node_ids:
                    mw_node = GraphNode(
                        id=mw_id,
                        label=mw["name"],
                        display_label=f"🛡️ {mw['name']}",
                        group="middleware",
                        category="middleware",
                        title=f"<b>Middleware: {mw['name']}</b><br>Registered on: {app.title}",
                        shape="ellipse",
                        size=22,
                        color=self.COLORS["middleware"],
                        metadata={"name": mw["name"], "app": app.title}
                    )
                    nodes.append(mw_node)
                    node_ids.add(mw_id)
                    edges.append(GraphEdge(
                        from_id=app.id,
                        to_id=mw_id,
                        relation="MIDDLEWARE_OF",
                        label="middleware",
                        dashes=True,
                        color="#94A3B8",
                        confidence=Confidence.FRAMEWORK_INFERRED,
                        resolution=Resolution.UNIQUE_NAME,
                        evidence=SourceSpan(
                            relative_repo_path(app.file_path, root), app.line_number, app.line_number,
                        ),
                    ))

        for router in arch.routers:
            prefix_label = f"\nprefix: {router.prefix}" if router.prefix else "\nprefix: /"
            node = GraphNode(
                id=router.id,
                label=router.var_name,
                display_label=f"📁 {router.var_name}{prefix_label}",
                group="router",
                category="router",
                title=f"<b>Router: {router.var_name}</b><br>Prefix: {router.prefix or '/'}<br>Tags: {', '.join(router.tags)}<br>Module: {router.module}<br>File: {router.file_path}:{router.line_number}",
                shape="box",
                size=32,
                color=self.COLORS["router"],
                metadata={
                    "type": "router",
                    "var_name": router.var_name,
                    "prefix": router.prefix,
                    "tags": router.tags,
                    "module": router.module,
                    "file_path": router.file_path,
                    "line_number": router.line_number,
                    "end_line_number": router.end_line_number,
                    "dependencies": router.dependencies,
                }
            )
            nodes.append(node)
            node_ids.add(node.id)

        for app in arch.apps:
            for inc in app.inclusions:
                target_id = inc.target_router_id or self._find_router_id(inc.module_or_source, inc.router_var, arch.routers)
                if target_id and target_id in node_ids:
                    lbl = f"include {inc.prefix}" if inc.prefix else "include"
                    edges.append(GraphEdge(
                        from_id=app.id,
                        to_id=target_id,
                        relation="INCLUDES",
                        label=lbl,
                        color="#818CF8",
                        confidence=Confidence.FRAMEWORK_INFERRED,
                        resolution=Resolution.UNIQUE_NAME,
                        evidence=SourceSpan(
                            relative_repo_path(app.file_path, root), app.line_number, app.line_number,
                        ),
                    ))

        for router in arch.routers:
            for inc in router.inclusions:
                target_id = inc.target_router_id or self._find_router_id(inc.module_or_source, inc.router_var, arch.routers)
                if target_id and target_id in node_ids and target_id != router.id:
                    lbl = f"include {inc.prefix}" if inc.prefix else "include"
                    edges.append(GraphEdge(
                        from_id=router.id,
                        to_id=target_id,
                        relation="INCLUDES",
                        label=lbl,
                        color="#C084FC",
                        confidence=Confidence.FRAMEWORK_INFERRED,
                        resolution=Resolution.UNIQUE_NAME,
                        evidence=SourceSpan(
                            relative_repo_path(router.file_path, root), router.line_number, router.line_number,
                        ),
                    ))

        for ep in arch.endpoints:
            method = ep.http_method.lower()
            group_name = f"endpoint_{method}" if f"endpoint_{method}" in self.COLORS else "endpoint_other"
            badge = self._get_method_badge(ep.http_method)
            
            node = GraphNode(
                id=ep.id,
                label=ep.function_name,
                display_label=f"{badge} {ep.full_path or ep.path}\n{ep.function_name}()",
                group=group_name,
                category="endpoint",
                title=f"<b>[{ep.http_method}] {ep.full_path or ep.path}</b><br>Handler: <code>{ep.function_name}()</code><br>Module: {ep.module}<br>Tags: {', '.join(ep.tags)}<br>Status: {ep.status_code or '200'}<br>Response: {ep.response_model or 'default'}",
                shape="box",
                size=26,
                color=self.COLORS[group_name],
                metadata={
                    "type": "endpoint",
                    "http_method": ep.http_method,
                    "path": ep.path,
                    "full_path": ep.full_path or ep.path,
                    "function_name": ep.function_name,
                    "module": ep.module,
                    "file_path": ep.file_path,
                    "line_number": ep.line_number,
                    "end_line_number": ep.end_line_number,
                    "docstring": ep.docstring,
                    "summary": ep.summary,
                    "tags": ep.tags,
                    "response_model": ep.response_model,
                    "status_code": ep.status_code,
                    "parameters": [p.__dict__ for p in ep.parameters],
                    "dependencies": ep.dependencies,
                    "request_schemas": ep.request_schemas,
                    "response_schemas": ep.response_schemas,
                }
            )
            nodes.append(node)
            node_ids.add(node.id)

            ep_evidence = SourceSpan(relative_repo_path(ep.file_path, root), ep.line_number, ep.line_number)
            if ep.router_id and ep.router_id in node_ids:
                edges.append(GraphEdge(
                    from_id=ep.router_id,
                    to_id=ep.id,
                    relation="ROUTES",
                    color="#A855F7",
                    confidence=Confidence.FRAMEWORK_INFERRED,
                    resolution=Resolution.UNIQUE_NAME,
                    evidence=ep_evidence,
                ))
            else:
                matching_router = next((r for r in arch.routers if r.module == ep.module), None)
                if matching_router and matching_router.id in node_ids:
                    edges.append(GraphEdge(
                        from_id=matching_router.id,
                        to_id=ep.id,
                        relation="ROUTES",
                        color="#A855F7",
                        confidence=Confidence.FRAMEWORK_INFERRED,
                        resolution=Resolution.UNIQUE_NAME,
                        evidence=ep_evidence,
                    ))
                elif arch.apps and arch.apps[0].id in node_ids:
                    edges.append(GraphEdge(
                        from_id=arch.apps[0].id,
                        to_id=ep.id,
                        relation="ROUTES",
                        color="#818CF8",
                        confidence=Confidence.FRAMEWORK_INFERRED,
                        resolution=Resolution.UNIQUE_NAME,
                        evidence=ep_evidence,
                    ))

        if self.include_dependencies:
            for dep in arch.dependencies:
                dep_label = f"⚙️ {dep.name}"
                dep_node = GraphNode(
                    id=dep.id,
                    label=dep.name,
                    display_label=dep_label,
                    group="dependency",
                    category="dependency",
                    title=f"<b>Dependency: {dep.name}</b><br>Kind: {dep.kind}<br>Module: {dep.module}<br>File: {dep.file_path}:{dep.line_number}",
                    shape="ellipse",
                    size=22,
                    color=self.COLORS["dependency"],
                    metadata={
                        "type": "dependency",
                        "name": dep.name,
                        "kind": dep.kind,
                        "module": dep.module,
                        "file_path": dep.file_path,
                        "line_number": dep.line_number,
                        "end_line_number": dep.end_line_number,
                        "docstring": dep.docstring,
                        "sub_dependencies": dep.sub_dependencies,
                        "consumers": dep.consumers,
                    }
                )
                nodes.append(dep_node)
                node_ids.add(dep.id)

            for ep in arch.endpoints:
                for d_name in ep.dependencies:
                    targets = [
                        d for d in self._find_deps_by_name(d_name, arch.dependencies)
                        if d.id in node_ids
                    ]
                    if targets:
                        edges.append(self._named_edge(
                            ep.id, targets, "DEPENDS_ON",
                            label="depends", dashes=True, color="#38BDF8",
                        ))

            for dep in arch.dependencies:
                for sub_name in dep.sub_dependencies:
                    targets = [
                        d for d in self._find_deps_by_name(sub_name, arch.dependencies)
                        if d.id in node_ids and d.id != dep.id
                    ]
                    if targets:
                        edges.append(self._named_edge(
                            dep.id, targets, "SUB_DEPENDENCY",
                            label="calls", dashes=True, color="#38BDF8",
                        ))

        if self.include_models:
            for schema in arch.schemas:
                schema_node = GraphNode(
                    id=schema.id,
                    label=schema.name,
                    display_label=f"📦 {schema.name}\n({len(schema.fields)} fields)",
                    group="schema",
                    category="schema",
                    title=f"<b>Schema Model: {schema.name}</b><br>Fields: {len(schema.fields)}<br>Module: {schema.module}",
                    shape="box",
                    size=20,
                    color=self.COLORS["schema"],
                    metadata={
                        "type": "schema",
                        "name": schema.name,
                        "module": schema.module,
                        "file_path": schema.file_path,
                        "line_number": schema.line_number,
                        "end_line_number": schema.end_line_number,
                        "docstring": schema.docstring,
                        "base_classes": schema.base_classes,
                        "fields": [f.__dict__ for f in schema.fields],
                    }
                )
                nodes.append(schema_node)
                node_ids.add(schema.id)

            for ep in arch.endpoints:
                for req_s in ep.request_schemas:
                    targets = [
                        s for s in self._find_schemas_by_name(req_s, arch.schemas)
                        if s.id in node_ids
                    ]
                    if targets:
                        edges.append(self._named_edge(
                            ep.id, targets, "REQUEST_BODY",
                            label="body", dashes=True, color="#E879F9",
                        ))
                for resp_s in ep.response_schemas:
                    targets = [
                        s for s in self._find_schemas_by_name(resp_s, arch.schemas)
                        if s.id in node_ids
                    ]
                    if targets:
                        edges.append(self._named_edge(
                            ep.id, targets, "RESPONSE_MODEL",
                            label="returns", dashes=True, color="#E879F9"
                        ))

        methods_counter = Counter([ep.http_method for ep in arch.endpoints])
        deps_counter = Counter([d for ep in arch.endpoints for d in ep.dependencies])

        annotate_nodes(nodes, arch.project_path, self.PROVENANCE, "python")
        mark_edges(edges, nodes=nodes, rule_namespace="fastapi",
                   rule_specificity=self.FRAMEWORK_RULE_SPECIFICITY)
        # mark_edges unconditionally sets confidence=FRAMEWORK_INFERRED on every edge it
        # sees, so the model-field TYPE_USES edges (which must stay STATIC_CERTAIN, per
        # contract Section E) are built after that call, mirroring how _implementation_edges
        # is appended post-mark_edges below.
        if self.include_models:
            edges.extend(self._schema_field_type_uses_edges(arch, node_ids))
        if self.include_language_graph:
            language_nodes, language_edges = self._language_graph(arch)
            known = {node.id for node in nodes}
            nodes.extend(node for node in language_nodes if node.id not in known)
            edges.extend(language_edges)
            edges.extend(self._implementation_edges(arch, {node.id for node in nodes}))

        arch.nodes = nodes
        arch.edges = edges
        enrich_repository(arch)
        arch.stats = {
            "total_apps": len(arch.apps),
            "total_routers": len(arch.routers),
            "total_endpoints": len(arch.endpoints),
            "total_dependencies": len(arch.dependencies),
            "total_schemas": len(arch.schemas),
            "methods_breakdown": dict(methods_counter),
            "top_reused_dependencies": deps_counter.most_common(5),
            "unique_tags": list(set([t for ep in arch.endpoints for t in ep.tags if t])),
            "nodes_by_kind": dict(Counter(node.kind or node.category for node in arch.nodes)),
            "edges_by_relation": dict(Counter(edge.relation for edge in arch.edges)),
            "edges_by_confidence": dict(Counter(str(edge.confidence) for edge in arch.edges)),
        }
        arch.stats["analysis"] = GraphAnalyzer().analyze(
            arch.nodes,
            arch.edges,
            project_path=arch.project_path,
        )
        arch.report_collections = self._build_report_collections(arch)

        return arch

    @staticmethod
    def _language_graph(arch: ProjectArchitecture):
        analyzer = PythonGraphAnalyzer(arch.project_path)
        return analyzer.build(PythonSourceAnalyzer(arch.project_path).analyze())

    @staticmethod
    def _implementation_edges(arch: ProjectArchitecture, known_ids: Set[str]) -> List[GraphEdge]:
        edges: List[GraphEdge] = []
        root = Path(arch.project_path)
        pairs = [(ep.id, ep.module, ep.function_name, ep.file_path, ep.line_number) for ep in arch.endpoints]
        pairs += [(dep.id, dep.module, dep.name, dep.file_path, dep.line_number) for dep in arch.dependencies]
        pairs += [(schema.id, schema.module, schema.name, schema.file_path, schema.line_number) for schema in arch.schemas]
        for source_id, module, name, file_path, line in pairs:
            if source_id not in known_ids or not module or not name:
                continue
            target = symbol_id(module, name)
            if target not in known_ids:
                continue
            edges.append(GraphEdge(
                from_id=source_id,
                to_id=target,
                relation=RelationKind.IMPLEMENTED_BY,
                label="implemented by",
                dashes=True,
                color="#94A3B8",
                confidence=Confidence.FRAMEWORK_INFERRED,
                resolution=Resolution.EXACT,
                evidence=SourceSpan(relative_repo_path(file_path, root), line, line),
                metadata={"framework_rule": {"id": "fastapi.implemented_by", "specificity": "unique"}},
            ))
        return edges

    def _schema_field_type_uses_edges(self, arch: ProjectArchitecture, node_ids: Set[str]) -> List[GraphEdge]:
        schema_by_name: Dict[str, List[SchemaInfo]] = {}
        for schema in arch.schemas:
            schema_by_name.setdefault(schema.name, []).append(schema)

        edges: List[GraphEdge] = []
        for schema in arch.schemas:
            if schema.id not in node_ids:
                continue
            for schema_field in schema.fields:
                target_name = self._unwrap_field_type(schema_field.type_annotation)
                matches = [s for s in schema_by_name.get(target_name, []) if s.id in node_ids]
                if not matches:
                    continue
                others = matches[1:]
                edges.append(GraphEdge(
                    from_id=schema.id,
                    to_id=matches[0].id,
                    relation=RelationKind.TYPE_USES,
                    label="uses",
                    dashes=True,
                    color="#E879F9",
                    confidence=Confidence.STATIC_CERTAIN,
                    resolution=Resolution.AMBIGUOUS if others else Resolution.UNIQUE_NAME,
                    candidates=[s.id for s in others],
                    evidence=SourceSpan(schema.file_path, schema.line_number, schema.line_number),
                    metadata={"framework_rule": {
                        "id": "fastapi.model_field_type_uses",
                        "specificity": "ambiguous" if others else "unique",
                    }},
                ))
        return edges

    @staticmethod
    def _build_report_collections(arch: ProjectArchitecture) -> List[ReportCollection]:
        return [
            ReportCollection(
                key="endpoints",
                label="Endpoints",
                view="table",
                node_category="endpoint",
                columns=[
                    ColumnSpec("http_method", "Method", "mono"),
                    ColumnSpec("path", "Path", "mono"),
                    ColumnSpec("function_name", "Handler", "mono"),
                    ColumnSpec("tags", "Tags", "list"),
                    ColumnSpec("dependencies", "Dependencies", "list"),
                    ColumnSpec("response_model", "Response Model", "mono"),
                ],
                rows=[
                    {
                        "id": ep.id,
                        "http_method": ep.http_method,
                        "path": ep.full_path or ep.path,
                        "function_name": f"{ep.function_name}()",
                        "tags": ep.tags,
                        "dependencies": ep.dependencies,
                        "response_model": ep.response_model,
                    }
                    for ep in arch.endpoints
                ],
            ),
            ReportCollection(
                key="routers",
                label="Routers",
                view="grid",
                node_category="router",
                columns=[
                    ColumnSpec("prefix", "Prefix", "mono"),
                    ColumnSpec("tags", "Tags", "list"),
                    ColumnSpec("dependencies", "Dependencies", "list"),
                ],
                rows=[
                    {
                        "id": r.id,
                        "name": r.var_name,
                        "prefix": r.prefix or "/",
                        "tags": r.tags,
                        "dependencies": r.dependencies,
                    }
                    for r in arch.routers
                ],
            ),
            ReportCollection(
                key="dependencies",
                label="Dependencies",
                view="grid",
                node_category="dependency",
                columns=[
                    ColumnSpec("kind", "Kind", "text"),
                    ColumnSpec("module", "Module", "mono"),
                    ColumnSpec("sub_dependencies", "Sub-Dependencies", "list"),
                ],
                rows=[
                    {
                        "id": d.id,
                        "name": d.name,
                        "kind": d.kind,
                        "module": f"{d.module}:{d.line_number}",
                        "sub_dependencies": d.sub_dependencies,
                    }
                    for d in arch.dependencies
                ],
            ),
            ReportCollection(
                key="schemas",
                label="Schemas",
                view="grid",
                node_category="schema",
                columns=[
                    ColumnSpec("base", "Base", "text"),
                    ColumnSpec("fields", "Fields", "list"),
                ],
                rows=[
                    {
                        "id": s.id,
                        "name": s.name,
                        "base": (s.base_classes[0] if s.base_classes else "BaseModel"),
                        "fields": [f"{f.name}: {f.type_annotation}" for f in s.fields],
                    }
                    for s in arch.schemas
                ],
            ),
        ]

    @staticmethod
    def _find_router_id(module_or_source: str, var_name: str, routers: List[RouterInfo]) -> Optional[str]:
        clean_var = var_name.split(".")[-1]
        for r in routers:
            if r.var_name == clean_var and (r.module == module_or_source or r.module.endswith(module_or_source)):
                return r.id
        for r in routers:
            if r.var_name == clean_var or r.module == module_or_source:
                return r.id
        return None

    @staticmethod
    def _find_deps_by_name(name: str, dependencies: List[DependencyInfo]) -> List[DependencyInfo]:
        clean_name = name.split("(")[0].split(".")[-1]
        return [
            d for d in dependencies
            if d.name == clean_name or d.name == name or d.id.endswith(f"_{clean_name}")
        ]

    @staticmethod
    def _unwrap_field_type(type_annotation: str) -> str:
        match = re.match(r"^\w+\[(.*)\]$", type_annotation.strip())
        if not match:
            return type_annotation.strip()
        inner = match.group(1)
        if "," in inner:
            inner = inner.rsplit(",", 1)[-1]
        return inner.strip()

    @staticmethod
    def _find_schemas_by_name(name: str, schemas: List[SchemaInfo]) -> List[SchemaInfo]:
        clean_name = name.split(".")[-1]
        return [s for s in schemas if s.name == clean_name or s.name == name]

    @staticmethod
    def _named_edge(from_id, targets, relation, **style) -> GraphEdge:
        return GraphEdge(
            from_id=from_id, to_id=targets[0].id, relation=relation,
            resolution=Resolution.AMBIGUOUS if targets[1:] else Resolution.UNIQUE_NAME,
            candidates=[item.id for item in targets[1:]],
            **style,
        )

    @staticmethod
    def _get_method_badge(method: str) -> str:
        icons = {
            "GET": "GET",
            "POST": "POST",
            "PUT": "PUT",
            "DELETE": "DEL",
            "PATCH": "PATCH",
            "OPTIONS": "OPT",
            "HEAD": "HEAD",
        }
        return icons.get(method.upper(), method.upper())

    def generate_mermaid(self, arch: ProjectArchitecture) -> str:
        lines = ["graph TD", "  %% FastAPI Architecture Diagram"]
        
        for app in arch.apps:
            lines.append(f'  subgraph App_{app.var_name} ["App: {app.title}"]')
            lines.append(f'    {app.id}["🚀 {app.title}"]')
            lines.append("  end")

        for router in arch.routers:
            lines.append(f'  subgraph Router_{router.var_name} ["Router: {router.var_name} ({router.prefix or "/"})"]')
            lines.append(f'    {router.id}["📁 {router.var_name}"]')
            lines.append("  end")

        framework_ids = {
            node.id for node in arch.nodes
            if (node.provenance or self.PROVENANCE) == self.PROVENANCE
        }
        for edge in arch.edges:
            if edge.from_id not in framework_ids or edge.to_id not in framework_ids:
                continue
            lbl = f"|{edge.label}|" if edge.label else ""
            arrow = "-.->" if edge.dashes else "-->"
            lines.append(f"  {edge.from_id} {arrow}{lbl} {edge.to_id}")

        return "\n".join(lines)
