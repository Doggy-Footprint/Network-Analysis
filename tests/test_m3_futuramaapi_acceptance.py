import json
import re
from pathlib import Path
from typing import Callable, Optional

from agent_view import build_agent_view, load_profile
from agent_view.scan import build_snapshot, read_file
from bottlenecks import analyze_bottlenecks, bottlenecks_to_json, parse_harness_profile
from fixtures.registry import fixture_root
from language_analyzers.python.graph import PythonGraphAnalyzer
from report.bottlenecks.generate import render_report


ROOT = Path(__file__).resolve().parents[1]


def _source_paths(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    )


def _analyze_futuramaapi(
    root: Path,
    *,
    path_lister: Callable[[Path], list[str]] = _source_paths,
    snapshot_builder: Callable[..., object] = build_snapshot,
    snapshot_reader: Callable[[Path], Optional[str]] = read_file,
    profile_loader: Callable[[Path], object] = load_profile,
    harness_reader: Callable[[Path], str] = lambda path: path.read_text(),
) -> str:
    agent_profile = profile_loader(ROOT / "profiles/agent_view.v3.yaml")
    snapshot = snapshot_builder(
        root,
        path_lister(root),
        profile=agent_profile,
        reader=snapshot_reader,
        ignore_source="futuramaapi-commit",
    )
    architecture = PythonGraphAnalyzer(root, snapshot).analyze()
    graph = build_agent_view(architecture, profile=agent_profile, snapshot=snapshot)
    harness = parse_harness_profile(json.loads(harness_reader(ROOT / "profiles/harness.fixed-baseline.v1.json")))
    return bottlenecks_to_json(analyze_bottlenecks(snapshot, architecture, graph, harness))


def test_external_source_analysis_accepts_injected_filesystem_access() -> None:
    agent_profile = load_profile(ROOT / "profiles/agent_view.v3.yaml")
    harness_text = (ROOT / "profiles/harness.fixed-baseline.v1.json").read_text()
    calls = []

    def path_lister(root: Path) -> list[str]:
        calls.append(("paths", root))
        return ["app.py"]

    def snapshot_reader(path: Path) -> Optional[str]:
        calls.append(("snapshot", path))
        return "def value():\n    return 1\n"

    def profile_loader(path: Path) -> object:
        calls.append(("profile", path))
        return agent_profile

    def harness_reader(path: Path) -> str:
        calls.append(("harness", path))
        return harness_text

    payload = json.loads(
        _analyze_futuramaapi(
            Path("/virtual/futuramaapi"),
            path_lister=path_lister,
            snapshot_reader=snapshot_reader,
            profile_loader=profile_loader,
            harness_reader=harness_reader,
        )
    )
    assert payload["snapshot"]["file_count"] == 1
    assert calls == [
        ("profile", ROOT / "profiles/agent_view.v3.yaml"),
        ("paths", Path("/virtual/futuramaapi")),
        ("snapshot", Path("/virtual/futuramaapi/app.py")),
        ("harness", ROOT / "profiles/harness.fixed-baseline.v1.json"),
    ]


def test_m3_ec_06_futuramaapi_analysis_is_deterministic_and_embeds_unchanged_json() -> None:
    source = fixture_root("futuramaapi")
    first = _analyze_futuramaapi(source)
    second = _analyze_futuramaapi(source)
    assert first == second
    payload = json.loads(first)
    for candidate in payload["candidates"]:
        assert candidate["status"] == "static_candidate"
    document = render_report(payload)
    match = re.search(r"<script id='bottlenecks-data' type='application/json'>(.*?)</script>", document, re.DOTALL)
    assert match
    assert json.loads(match.group(1)) == payload
