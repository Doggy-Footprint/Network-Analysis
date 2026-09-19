"""
Optional Dynamic Runtime Introspection for FastAPI Applications.
Used when the project is importable in the current environment and the user supplies `--app module:app`.
"""

import importlib
import sys
from pathlib import Path
from typing import Any, List, Optional

from .models import (
    AppInfo,
    DependencyInfo,
    EndpointInfo,
    ParameterInfo,
    ProjectArchitecture,
    RouterInfo,
    SchemaInfo,
)


class DynamicFastAPIAnalyzer:
    def __init__(self, project_path: str, app_import_str: str):
        self.project_path = Path(project_path).resolve()
        self.app_import_str = app_import_str
        self.app_instance = None

    def analyze(self) -> Optional[ProjectArchitecture]:
        if str(self.project_path) not in sys.path:
            sys.path.insert(0, str(self.project_path))

        try:
            mod_name, app_name = self.app_import_str.split(":")
            module = importlib.import_module(mod_name)
            self.app_instance = getattr(module, app_name)
        except Exception as e:
            print(f"[!] Dynamic introspection failed: {e}")
            return None

        apps = []
        routers = []
        endpoints = []
        dependencies = {}
        schemas = {}

        app_info = AppInfo(
            id=f"app_{mod_name}_{app_name}",
            var_name=app_name,
            title=getattr(self.app_instance, "title", "FastAPI App"),
            version=getattr(self.app_instance, "version", "0.1.0"),
            title_source="literal",
            version_source="literal",
            module=mod_name,
            file_path="",
            line_number=0,
        )
        apps.append(app_info)

        for route in getattr(self.app_instance, "routes", []):
            methods = list(getattr(route, "methods", []))
            path = getattr(route, "path", "/")
            endpoint_fn = getattr(route, "endpoint", None)
            fn_name = endpoint_fn.__name__ if endpoint_fn else "unknown"
            fn_module = endpoint_fn.__module__ if endpoint_fn else ""
            docstring = endpoint_fn.__doc__ if endpoint_fn else ""
            tags = list(getattr(route, "tags", []))
            resp_model = getattr(route, "response_model", None)
            resp_model_name = getattr(resp_model, "__name__", str(resp_model)) if resp_model else None

            route_deps = []
            dependant = getattr(route, "dependant", None)
            if dependant:
                self._collect_dependant_deps(dependant, route_deps, dependencies)

            for method in methods:
                if method.upper() in ("HEAD", "OPTIONS") and len(methods) > 1:
                    continue
                ep_id = f"ep_dyn_{fn_module}_{fn_name}_{method}"
                ep = EndpointInfo(
                    id=ep_id,
                    http_method=method.upper(),
                    path=path,
                    full_path=path,
                    function_name=fn_name,
                    module=fn_module,
                    file_path="",
                    line_number=0,
                    docstring=docstring,
                    tags=tags,
                    response_model=resp_model_name,
                    dependencies=route_deps,
                    app_id=app_info.id,
                )
                endpoints.append(ep)

        return ProjectArchitecture(
            project_name=self.project_path.name,
            project_path=str(self.project_path),
            apps=apps,
            routers=routers,
            endpoints=endpoints,
            dependencies=list(dependencies.values()),
            schemas=list(schemas.values()),
        )

    def _collect_dependant_deps(self, dependant: Any, collected_names: List[str], dep_registry: dict):
        if not dependant:
            return
        call = getattr(dependant, "call", None)
        if call and callable(call):
            call_name = getattr(call, "__name__", str(call))
            call_mod = getattr(call, "__module__", "")
            if call_name not in collected_names:
                collected_names.append(call_name)
            
            if call_name not in dep_registry:
                dep_info = DependencyInfo(
                    id=f"dep_{call_mod}_{call_name}",
                    name=call_name,
                    kind="function",
                    module=call_mod,
                    file_path="",
                    docstring=getattr(call, "__doc__", None),
                )
                dep_registry[call_name] = dep_info
                
                for sub in getattr(dependant, "dependencies", []):
                    sub_call = getattr(sub, "call", None)
                    if sub_call:
                        sub_name = getattr(sub_call, "__name__", str(sub_call))
                        if sub_name not in dep_info.sub_dependencies:
                            dep_info.sub_dependencies.append(sub_name)
                        self._collect_dependant_deps(sub, dep_info.sub_dependencies, dep_registry)
