"""
FastAPI Architecture & Dependency Visualizer.
"""

from .analyzer import FastAPIAnalyzer
from .graph import ArchitectureGraphBuilder
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

__version__ = "0.1.0"
__all__ = [
    "FastAPIAnalyzer",
    "ArchitectureGraphBuilder",
    "ProjectArchitecture",
    "AppInfo",
    "RouterInfo",
    "EndpointInfo",
    "DependencyInfo",
    "SchemaInfo",
    "GraphNode",
    "GraphEdge",
]
