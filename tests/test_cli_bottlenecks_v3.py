"""V7 (F14, F4, F3, C8, C9, C12, Q1) for spec 8fd668e309160b58 v1: code_analyzer.cli.main() integration.

Technique: scenario. A scratch git repository in tmp_path is analyzed through main() with
sys.argv patched; observations are exit codes, stderr, output files and their bytes.
Scenario list: success run, three removed options, invalid weight files, two-run
determinism, snapshot policy (snapshot.v1 exclusion rules + tracked_files_only).
"""
import json
import subprocess
import sys

import pytest

import code_analyzer.cli as cli
from tests.edge_weights_support import uniform_weights_data, weights_data, write_weights

TRACKED = {
    "loader.py": "import importlib\n\ndef load():\n    return importlib.import_module('plugins.alpha')\n",
    "plugins/__init__.py": "",
    "plugins/alpha.py": "def run():\n    return 1\n",
    "main.py": "from loader import load\nfrom plugins.alpha import run\n\ndef main():\n    return load(), run()\n",
    "vendor/vendored_zz.py": "def vendored():\n    return 1\n",
    "third_party/thirdparty_zz.py": "def third():\n    return 1\n",
}
UNTRACKED = {"untracked_zz.py": "def loose():\n    return 1\n"}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    for relative, text in {**TRACKED, **UNTRACKED}.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", *TRACKED], cwd=root, check=True)
    return root


@pytest.fixture
def out(tmp_path):
    directory = tmp_path / "out"
    directory.mkdir()
    return directory


def run_cli(monkeypatch, *arguments):
    monkeypatch.setattr(sys, "argv", ["code-analyzer", *arguments])
    try:
        cli.main()
    except SystemExit as exit_request:
        return exit_request.code
    return 0


def bottleneck_arguments(project, out, *extra):
    return [
        str(project), "-l", "python", "-o", str(out / "architecture.html"),
        "--bottlenecks", str(out / "b.json"), "--bottlenecks-html", str(out / "b.html"), *extra,
    ]


def read_payload(out):
    return json.loads((out / "b.json").read_text(encoding="utf-8"))


def test_V7_C12_success_writes_v3_json_and_html_without_a_harness_profile(monkeypatch, project, out):
    assert run_cli(monkeypatch, *bottleneck_arguments(project, out)) in (0, None)
    payload = read_payload(out)
    assert payload["schema"] == "bottlenecks.v4"
    assert (out / "b.html").stat().st_size > 0
    assert (out / "architecture.html").is_file()


def test_V7_Q1_C12_two_runs_produce_byte_identical_json(monkeypatch, project, out):
    arguments = bottleneck_arguments(project, out)
    assert run_cli(monkeypatch, *arguments) in (0, None)
    first = (out / "b.json").read_bytes()
    for leftover in out.iterdir():
        if leftover.is_file():
            leftover.unlink()
    assert run_cli(monkeypatch, *arguments) in (0, None)
    second = (out / "b.json").read_bytes()
    assert first and first == second


def test_V7_F4_snapshot_policy_excludes_vendor_paths_and_untracked_files(monkeypatch, project, out):
    assert run_cli(monkeypatch, *bottleneck_arguments(project, out)) in (0, None)
    network = json.dumps(read_payload(out)["dependency_network"])
    assert "loader" in network and "alpha" in network
    for excluded in ("vendored_zz", "thirdparty_zz", "untracked_zz"):
        assert excluded not in network, excluded


def test_V7_F14_edge_weights_option_replaces_the_default_file(monkeypatch, project, out, tmp_path):
    assert run_cli(monkeypatch, *bottleneck_arguments(project, out)) in (0, None)
    default_payload = read_payload(out)
    assert default_payload["edge_weights"]["large_node_line_threshold"] == 2000
    assert [item for item in default_payload["candidates"] if item["kind"] == "large_node"] == []

    custom = write_weights(tmp_path, uniform_weights_data(large_node_line_threshold=1), "custom.yaml")
    assert run_cli(monkeypatch, *bottleneck_arguments(project, out, "--edge-weights", str(custom))) in (0, None)
    custom_payload = read_payload(out)
    assert custom_payload["edge_weights"]["large_node_line_threshold"] == 1
    assert [item for item in custom_payload["candidates"] if item["kind"] == "large_node"]


def test_V7_F14_edge_weights_reach_the_python_graph_analysis(monkeypatch, project, out, tmp_path):
    """loader#load -> plugins.alpha is a dynamic_required edge: 0.3 under the default file, 1.0 under a uniform file."""
    assert run_cli(monkeypatch, *bottleneck_arguments(project, out)) in (0, None)
    discounted = read_payload(out)["dependency_network"]["node_metrics"]
    custom = write_weights(tmp_path, uniform_weights_data(), "uniform.yaml")
    assert run_cli(monkeypatch, *bottleneck_arguments(project, out, "--edge-weights", str(custom))) in (0, None)
    uniform = read_payload(out)["dependency_network"]["node_metrics"]
    assert discounted != uniform
    for node_id, row in discounted.items():
        assert row["fan_in"] == uniform[node_id]["fan_in"], node_id
        assert row["weighted_fan_in"] <= uniform[node_id]["weighted_fan_in"] + 1e-12, node_id


@pytest.mark.parametrize(
    "option",
    [["--agent-view", "x"], ["--app", "x"], ["--harness-profile", "x"]],
    ids=["agent-view", "app", "harness-profile"],
)
def test_V7_C9_removed_options_are_rejected_by_argparse(monkeypatch, capsys, option):
    assert run_cli(monkeypatch, ".", *option) == 2
    assert option[0] in capsys.readouterr().err


@pytest.mark.parametrize("variant", ["missing-file", "invalid-yaml", "schema-violation"])
def test_V7_C8_invalid_weight_file_exits_one_and_writes_nothing(monkeypatch, capsys, project, out, tmp_path, variant):
    if variant == "missing-file":
        weights_path = tmp_path / "absent.yaml"
    elif variant == "invalid-yaml":
        weights_path = tmp_path / "broken.yaml"
        weights_path.write_text("id: [unclosed\nconfidence: {a: : :\n", encoding="utf-8")
    else:
        weights_path = write_weights(tmp_path, weights_data(confidence={"static_inferred": 0.0}), "bad.yaml")
    code = run_cli(monkeypatch, *bottleneck_arguments(project, out, "--edge-weights", str(weights_path)))
    assert code == 1
    assert "[!] Error:" in capsys.readouterr().err
    assert list(out.iterdir()) == []


def test_V7_F3_dynamic_fastapi_analyzer_is_gone_from_the_cli():
    assert not hasattr(cli, "DynamicFastAPIAnalyzer")


ALL_DISCOUNTED = weights_data(
    confidence={"static_certain": 0.5},
    resolution={"exact": 0.5},
)

ANDROID_TOPIC_DIR = "feature_topic/src/main/kotlin/com/example/feature/topic"
PATH_SCENARIOS = {
    "python": (["-l", "python"], TRACKED),
    "typescript": (
        ["-l", "typescript"],
        {
            "a.ts": "export function f() { return 1; }\n",
            "b.ts": "import { f } from './a';\nexport function g() { return f(); }\n",
        },
    ),
    "kotlin": (
        ["-l", "kotlin"],
        {"main.kt": "package demo\nclass Item\nfun create() = Item()\nfun twice() = create()\n"},
    ),
    "fastapi": (
        ["-f", "fastapi"],
        {
            "main.py": (
                "from fastapi import FastAPI, Depends\napp = FastAPI()\n\n"
                "def get_db():\n    return {}\n\n"
                "@app.get('/')\ndef route(db=Depends(get_db)):\n    return {'ok': True}\n"
            )
        },
    ),
    "android": (
        ["-f", "android"],
        {
            f"{ANDROID_TOPIC_DIR}/TopicScreen.kt": (
                "package com.example.feature.topic\n\n"
                "import androidx.compose.runtime.Composable\n\n"
                "@Composable\nfun TopicRoute() {\n    TopicScreen()\n}\n\n"
                "@Composable\nfun TopicScreen() {\n    TopicDetail()\n}\n\n"
                "@Composable\nfun TopicDetail() {\n}\n"
            )
        },
    ),
}


@pytest.mark.parametrize("mode", list(PATH_SCENARIOS))
def test_V7_F14_edge_weights_reach_every_cli_analysis_path(monkeypatch, tmp_path, mode):
    """Every certain/exact edge is discounted to 0.5 by the custom file, so some node must have
    weighted_fan_in < fan_in in the bottlenecks JSON; no node may exceed its count."""
    flags, files = PATH_SCENARIOS[mode]
    root = tmp_path / "repo"
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", *files], cwd=root, check=True)
    out = tmp_path / "out"
    out.mkdir()
    weights = write_weights(tmp_path, ALL_DISCOUNTED, "discount.yaml")
    arguments = [
        str(root), *flags, "-o", str(out / "architecture.html"),
        "--bottlenecks", str(out / "b.json"), "--edge-weights", str(weights),
    ]
    assert run_cli(monkeypatch, *arguments) in (0, None)
    payload = read_payload(out)
    metrics = payload["dependency_network"]["node_metrics"]
    assert any(row["fan_in"] > 0 for row in metrics.values()), "scratch repo produced no edge"
    assert all(row["weighted_fan_in"] <= row["fan_in"] + 1e-12 for row in metrics.values())
    assert any(row["weighted_fan_in"] < row["fan_in"] - 1e-12 for row in metrics.values())


def exported_node_metrics(directory):
    """stats.analysis.node_metrics of the architecture JSON that --json wrote next to the HTML report."""
    exports = [path for path in directory.glob("*.json") if path.name != "b.json"]
    assert len(exports) == 1, sorted(path.name for path in directory.iterdir())
    exported = json.loads(exports[0].read_text(encoding="utf-8"))
    analysis = exported.get("stats", {}).get("analysis")
    assert isinstance(analysis, dict), sorted(exported)
    return analysis["node_metrics"]


@pytest.mark.parametrize("mode", list(PATH_SCENARIOS))
def test_V7_F14_edge_weights_reach_the_architecture_analysis_export(monkeypatch, tmp_path, mode):
    """Same discounting file, observed on the --json architecture export (run without --bottlenecks,
    which may omit stats.analysis)."""
    flags, files = PATH_SCENARIOS[mode]
    root = tmp_path / "repo"
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", *files], cwd=root, check=True)
    out = tmp_path / "out"
    out.mkdir()
    weights = write_weights(tmp_path, ALL_DISCOUNTED, "discount.yaml")
    arguments = [str(root), *flags, "-o", str(out / "architecture.html"), "--json", "--edge-weights", str(weights)]
    assert run_cli(monkeypatch, *arguments) in (0, None)
    metrics = exported_node_metrics(out)
    assert any(row["fan_in"] > 0 for row in metrics.values()), "scratch repo produced no edge"
    assert all(row["weighted_fan_in"] <= row["fan_in"] + 1e-12 for row in metrics.values())
    assert any(row["weighted_fan_in"] < row["fan_in"] - 1e-12 for row in metrics.values())
