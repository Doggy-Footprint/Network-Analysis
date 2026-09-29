"""V9 (F1, F2, F3, F16, Q2, C13) for spec 8fd668e309160b58 v1; automates review evidence R1.

Technique: equivalence partitioning over {AST import scan of the active packages, retired
paths absent, archive paths present, agent_view-shaped files kept in the snapshot,
_is_agent_view_artifact absent}. The import detector is itself checked on synthetic sources
so an always-empty scan cannot pass.
"""
import ast
import configparser
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

import repository.scan
from repository import build_snapshot, default_scan_policy_path, load_scan_policy

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_PACKAGES = [
    "analysis", "bottlenecks", "code_analyzer", "framework_analyzers", "language_analyzers",
    "renderers", "report", "repository",
]
RETIRED_TESTS = [
    "test_agent_view_graph.py", "test_report_m1.py", "test_readability_m1.py", "test_readability_followup.py",
    "test_readability_bottlenecks.py", "test_bottlenecks_contract.py", "test_m3_futuramaapi_acceptance.py",
    "test_readability_finish.py",
]
FORBIDDEN_ROOTS = ("agent_view", "report.m1", "archive")


def is_forbidden(module):
    return any(module == name or module.startswith(name + ".") for name in FORBIDDEN_ROOTS)


def imported_modules(source, package_parts):
    """Absolute module names imported by `source`; `package_parts` is the importing file's package path."""
    modules = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = list(package_parts[: len(package_parts) - (node.level - 1)]) if node.level else []
            if node.module:
                base.extend(node.module.split("."))
            modules.append(".".join(base))
            modules.extend(".".join(base + [alias.name]) for alias in node.names)
    return modules


def forbidden_imports(source, package_parts=()):
    return sorted({module for module in imported_modules(source, package_parts) if is_forbidden(module)})


@pytest.mark.parametrize(
    ("source", "package_parts", "expected"),
    [
        ("import agent_view", (), ["agent_view"]),
        ("from agent_view.scan import build_snapshot", (), ["agent_view.scan", "agent_view.scan.build_snapshot"]),
        ("from report.m1.generate import generate_report", (), ["report.m1.generate", "report.m1.generate.generate_report"]),
        ("from report import m1", (), ["report.m1"]),
        ("from .m1 import generate", ("report",), ["report.m1", "report.m1.generate"]),
        ("import archive.tests.helper", (), ["archive.tests.helper"]),
        ("from archive import thing", (), ["archive", "archive.thing"]),
        ("import agent_viewer", (), []),
        ("from report.shared import document", (), []),
        ("from report.bottlenecks import render_report", (), []),
    ],
)
def test_V9_import_detector_flags_exactly_the_forbidden_modules(source, package_parts, expected):
    assert forbidden_imports(source, package_parts) == expected


@pytest.mark.parametrize("package", ACTIVE_PACKAGES)
def test_V9_C13_Q2_active_package_does_not_import_retired_code(package):
    sources = sorted((ROOT / package).rglob("*.py"))
    assert sources, package
    offenders = {}
    for path in sources:
        relative = path.relative_to(ROOT)
        found = forbidden_imports(path.read_text(encoding="utf-8"), relative.parts[:-1])
        if found:
            offenders[relative.as_posix()] = found
    assert offenders == {}


@pytest.mark.parametrize(
    "relative",
    ["agent_view", "report/m1", "framework_analyzers/fastapi/dynamic_analyzer.py",
     "profiles/agent_view.v3.yaml", "profiles/harness.fixed-baseline.v1.json"],
)
def test_V9_F1_F3_retired_paths_are_absent(relative):
    assert not (ROOT / relative).exists()


@pytest.mark.parametrize("name", RETIRED_TESTS)
def test_V9_F1_retired_tests_left_the_active_test_directory(name):
    assert not (ROOT / "tests" / name).exists()
    assert (ROOT / "archive" / "tests" / name).is_file()


def test_V9_F1_archive_holds_the_retired_code_and_profiles():
    archive = ROOT / "archive"
    assert archive.is_dir()
    directory_names = {path.name for path in archive.rglob("*") if path.is_dir()}
    assert any("agent_view" in name for name in directory_names)
    assert any("m1" in name for name in directory_names)
    assert list(archive.rglob("agent_view.v3.yaml"))
    assert list(archive.rglob("harness.fixed-baseline.v1.json"))


def test_V9_A4_archive_tests_are_outside_pytest_testpaths():
    parser = configparser.ConfigParser()
    parser.read(ROOT / "pytest.ini", encoding="utf-8")
    assert parser["pytest"]["testpaths"].split() == ["tests"]


def test_V9_F3_fastapi_package_no_longer_exports_the_dynamic_analyzer():
    package = importlib.import_module("framework_analyzers.fastapi")
    assert not hasattr(package, "DynamicFastAPIAnalyzer")
    assert "DynamicFastAPIAnalyzer" not in getattr(package, "__all__", [])
    assert importlib.util.find_spec("framework_analyzers.fastapi.dynamic_analyzer") is None


def test_V9_F16_agent_view_shaped_files_are_regular_snapshot_files():
    files = {
        "view.json": json.dumps({"schema_version": "3", "query_nodes": [], "occurrence_store": []}),
        "compact.json": json.dumps({"schema_version": "2", "query_nodes": []}),
        "payload.html": '<html><script id="agent-view-v3-payload"></script></html>',
        "data.html": '<html><script id="agent-view-data"></script></html>',
    }
    root = Path("/repo")
    snapshot = build_snapshot(
        root,
        sorted(files),
        policy=load_scan_policy(default_scan_policy_path()),
        reader=lambda path: files[path.relative_to(root).as_posix()],
        ignore_source="test",
    )
    assert snapshot.content_map() == files
    assert snapshot.excluded_files == ()


def test_V9_F16_agent_view_artifact_predicate_is_removed():
    assert not hasattr(repository.scan, "_is_agent_view_artifact")


RETIRED_IDENTIFIERS = {"HarnessProfile", "parse_harness_profile", "replay_probe", "Probe", "ProbeOutput"}
RETIRED_KINDS = {"output_truncation", "multiple_results", "read_limit"}


def test_V9_E5_bottlenecks_package_has_no_probe_or_harness_code():
    sources = sorted((ROOT / "bottlenecks").rglob("*.py"))
    assert sources
    identifiers, strings = set(), set()
    for path in sources:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Name):
                identifiers.add(node.id)
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                identifiers.add(node.name)
            elif isinstance(node, ast.alias):
                identifiers.update(part for part in node.name.split(".") + [node.asname or ""])
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                strings.add(node.value)
    assert identifiers & RETIRED_IDENTIFIERS == set()
    assert strings & RETIRED_KINDS == set()
