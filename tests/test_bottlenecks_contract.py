import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agent_view import build_agent_view, build_snapshot, default_profile_path, load_profile
from bottlenecks import BottleneckInputError, analyze_bottlenecks, bottlenecks_to_json, parse_harness_profile
from language_analyzers.core.graph_models import GraphEdge, GraphNode, NodeCost, SourceSpan
from language_analyzers.python.graph import PythonGraphAnalyzer

RANKINGS = {"pagerank", "hub_score", "authority_score", "degree_centrality", "betweenness_centrality", "weighted_centrality_cost", "fan_in", "fan_out", "hop_2_token_cost", "hop_3_token_cost"}


def harness(visible=2, maximum=2):
    return parse_harness_profile({"schema":"harness_profile.v1","id":"fixed","version":1,"provenance_status":"unverified_baseline","content_search":{"matching":"fixed_string_case_sensitive","order":"path_lexical_then_numeric_line","visible_lines":visible,"cap_unit":"matching_lines","same_line_occurrences":"preserved"},"path_search":{"matching":"fixed_string_case_sensitive","order":"path_lexical_then_numeric_line","visible_lines":visible,"cap_unit":"matching_paths"},"read":{"bounds":"one_based_inclusive","max_lines":maximum,"eof":"clamp","truncation":"actual_omitted_lines"},"features":{"fixed_string_search":"supported","line_range_read":"supported","semantic_search":"unsupported","index":"unsupported","context_compaction":"observation_only","parallelism":"observation_only","subagents":"observation_only"},"assumptions":{"automatic_injection":"unverified_baseline","list_depth":2}})


def subject(files=None):
    files = {"a.py":"def one():\n return 1\n", "b.py":"from a import one\none()\n"} if files is None else files
    root, profile = Path("/repo"), load_profile(default_profile_path())
    snapshot = build_snapshot(root, sorted(files), profile=profile, reader=lambda path: files[path.relative_to(root).as_posix()], ignore_source="test")
    architecture = PythonGraphAnalyzer(root, snapshot).analyze()
    return snapshot, architecture, build_agent_view(architecture, profile=profile, snapshot=snapshot)


def network_subject(ids, edges=(), flags=None):
    snapshot, architecture, graph = subject({"a.py":"line\n"})
    flags = flags or {}
    nodes = [GraphNode(item, item, "g", "c", span=SourceSpan("a.py", 1, 1), cost=NodeCost(10, 10, 1), flags=flags.get(item, [])) for item in ids]
    return snapshot, replace(architecture, nodes=nodes, edges=list(edges)), replace(graph, readable_nodes=[], query_nodes=[], connections=[])


def test_NA_01_empty_snapshot_has_all_required_empty_rankings():
    snapshot, architecture, graph = subject({})
    report = analyze_bottlenecks(snapshot, architecture, graph, harness())
    assert report.schema == "bottlenecks.v2"
    assert report.dependency_network["node_count"] == report.dependency_network["edge_count"] == 0
    assert report.dependency_network["node_metrics"] == {}
    assert report.dependency_network["rankings"] == {key: [] for key in RANKINGS}
    assert report.candidates == ()


def test_NA_02_isolated_node_has_zero_connectivity_and_is_ranked():
    snapshot, architecture, graph = network_subject(["solo"])
    report = analyze_bottlenecks(snapshot, architecture, graph, harness())
    metrics = report.dependency_network["node_metrics"]["solo"]
    assert {key:metrics[key] for key in ("fan_in", "fan_out", "degree_centrality", "betweenness_centrality", "hub_score", "authority_score")} == {"fan_in":0,"fan_out":0,"degree_centrality":0,"betweenness_centrality":0,"hub_score":0.0,"authority_score":0.0}
    assert metrics["token_cost"] == 10
    assert report.dependency_network["rankings"]["fan_in"] == [{"node_id":"solo", "value":0}]


def test_NA_03_directed_chain_cycle_and_dangling_metrics_are_finite():
    snapshot, architecture, graph = network_subject(["a", "b", "c", "dangling"], [GraphEdge("a", "b", "x"), GraphEdge("b", "c", "x"), GraphEdge("c", "b", "x")])
    metrics = analyze_bottlenecks(snapshot, architecture, graph, harness()).dependency_network["node_metrics"]
    assert metrics["a"]["hub_score"] > metrics["a"]["authority_score"] and metrics["b"]["betweenness_centrality"] > 0
    assert all(math.isfinite(value) for row in metrics.values() for value in (row["pagerank"], row["hub_score"], row["authority_score"], row["betweenness_centrality"]))


def test_NA_04_duplicate_and_self_edges_are_ignored():
    edge = GraphEdge("a", "b", "x")
    snapshot, architecture, graph = network_subject(["a", "b"], [edge, edge, GraphEdge("a", "a", "self")])
    report = analyze_bottlenecks(snapshot, architecture, graph, harness())
    assert report.dependency_network["edge_count"] == 1
    assert report.dependency_network["node_metrics"]["a"]["fan_out"] == report.dependency_network["node_metrics"]["b"]["fan_in"] == 1


def assert_invalid_cli_has_no_writes(transform, monkeypatch, tmp_path):
    import code_analyzer.cli as cli
    snapshot, architecture, graph = subject({"a.py":"x\n"})
    writes = []
    monkeypatch.setattr(sys, "argv", ["code-analyzer", str(tmp_path), "-l", "python", "-o", str(tmp_path / "architecture.html"), "--bottlenecks", str(tmp_path / "b.json"), "--harness-profile", str(tmp_path / "h.json")])
    monkeypatch.setattr(cli, "build_snapshot", lambda *args, **kwargs: snapshot)
    monkeypatch.setattr(cli, "build_agent_view", lambda *args, **kwargs: graph)
    monkeypatch.setattr(cli, "PythonGraphAnalyzer", lambda *args: type("Analyzer", (), {"analyze":lambda self:transform(architecture)})())
    monkeypatch.setattr(cli, "_read_json", lambda *args: json.loads(json.dumps(harness(), default=lambda value:value.__dict__)))
    with pytest.raises(SystemExit) as error:
        cli.main(file_lister=lambda *args, **kwargs:("test", ["a.py"]), file_writer=lambda path, text:writes.append(path))
    assert error.value.code == 1 and writes == []


def test_NA_05_outside_edge_raises_before_cli_writes(monkeypatch, tmp_path):
    assert_invalid_cli_has_no_writes(lambda architecture: replace(architecture, edges=[GraphEdge("outside", "a", "x")]), monkeypatch, tmp_path)


def test_NA_06_outside_span_raises_before_cli_writes(monkeypatch, tmp_path):
    assert_invalid_cli_has_no_writes(lambda architecture: replace(architecture, nodes=[replace(architecture.nodes[0], span=SourceSpan("outside.py", 1, 1))]), monkeypatch, tmp_path)


def test_NA_07_missing_span_and_cost_uses_recorded_fallback():
    snapshot, architecture, graph = network_subject(["a"])
    report = analyze_bottlenecks(snapshot, replace(architecture, nodes=[replace(architecture.nodes[0], span=None, cost=None)]), graph, harness())
    assert report.coverage["limitations"] == ["Token cost fallback applies to nodes without a source span or explicit cost."]
    assert report.dependency_network["node_metrics"]["a"]["token_cost"] > 0


@pytest.mark.parametrize(("flag", "expected"), [("generated", 1.0), ("migration", 1.0), ("vendored", 0.0)])
def test_NA_08_cost_multipliers_are_serialized(flag, expected):
    snapshot, architecture, graph = network_subject(["a"], flags={"a":[flag]})
    assert analyze_bottlenecks(snapshot, architecture, graph, harness()).dependency_network["node_metrics"]["a"]["effective_token_cost"] == expected


def test_NA_09_threshold_crossing_uses_deterministic_sample():
    ids = [f"n{number:03}" for number in range(501)]
    snapshot, architecture, graph = network_subject(ids, [GraphEdge(ids[index], ids[index + 1], "x") for index in range(500)])
    network = analyze_bottlenecks(snapshot, architecture, graph, harness()).dependency_network
    assert (network["betweenness_strategy"], network["betweenness_sample_size"]) == ("deterministic_sampled", 100)


def test_NA_10_tied_rankings_are_node_sorted_and_capped_at_ten():
    ids = [f"n{number:02}" for number in range(12)]
    edges = [
        GraphEdge("n00", "n01", "x"), GraphEdge("n00", "n02", "x"), GraphEdge("n00", "n03", "x"),
        GraphEdge("n01", "n02", "x"), GraphEdge("n01", "n03", "x"),
        GraphEdge("n02", "n04", "x"), GraphEdge("n03", "n04", "x"),
    ]
    snapshot, architecture, graph = network_subject(ids, edges)
    rankings = analyze_bottlenecks(snapshot, architecture, graph, harness()).dependency_network["rankings"]
    assert set(rankings) == RANKINGS
    assert rankings["fan_out"] == [
        {"node_id":"n00", "value":3}, {"node_id":"n01", "value":2},
        {"node_id":"n02", "value":1}, {"node_id":"n03", "value":1},
        {"node_id":"n04", "value":0}, {"node_id":"n05", "value":0},
        {"node_id":"n06", "value":0}, {"node_id":"n07", "value":0},
        {"node_id":"n08", "value":0}, {"node_id":"n09", "value":0},
    ]


def test_NA_11_search_cap_emits_truncation_with_distinct_counts():
    snapshot, architecture, graph = subject({"a.py":"needle\nneedle\nneedle\n"})
    query = replace(graph.query_nodes[0], kind="exact", surface="content", term="needle", scope="repository")
    report = analyze_bottlenecks(snapshot, architecture, replace(graph, query_nodes=[query], connections=[]), harness(1, 2))
    assert next(item for item in report.candidates if item["kind"] == "output_truncation")["metrics"] == {"total_count":3,"visible_count":1,"omitted_count":2}


def test_NA_12_read_and_evidence_spread_candidates_have_concrete_evidence():
    snapshot, architecture, graph = subject()
    graph = replace(graph, readable_nodes=[replace(graph.readable_nodes[0], start_line=1, end_line=3), *graph.readable_nodes[1:]])
    edge = replace(architecture.edges[0], evidence=SourceSpan("a.py", 1, 3))
    report = analyze_bottlenecks(snapshot, replace(architecture, edges=[edge, replace(edge, evidence=SourceSpan("b.py", 1, 1))]), graph, harness(10, 1))
    assert next(item for item in report.candidates if item["kind"] == "read_limit")["evidence"] == {"path":graph.readable_nodes[0].file_path,"start_line":1,"end_line":3}
    assert next(item for item in report.candidates if item["kind"] == "evidence_spread")["metrics"]["file_count"] == 2


def test_NA_13_dynamic_relation_emits_analyzer_neutral_boundary():
    snapshot, architecture, graph = subject()
    report = analyze_bottlenecks(snapshot, replace(architecture, edges=[replace(architecture.edges[0], confidence="dynamic_required")]), graph, harness())
    assert any(item["kind"] == "unresolved_boundary" and item["coverage"] == "static_analyzer_relation" for item in report.candidates)


def test_NA_14_all_modes_write_architecture_agent_view_json_and_html(monkeypatch, tmp_path):
    import code_analyzer.cli as cli
    snapshot, architecture, graph = subject({"a.py":"x\n"})
    report, profile_data, writes, rendered = analyze_bottlenecks(snapshot, architecture, graph, harness()), json.loads(json.dumps(harness(), default=lambda value:value.__dict__)), [], []
    class Renderer:
        def __init__(self, **kwargs): pass
        def render(self, arch, path): rendered.append(Path(path)); return path
    class Analyzer:
        def __init__(self, *args, **kwargs): pass
        def analyze(self): return architecture
    class Builder:
        def __init__(self, *args, **kwargs): pass
        def build_graph(self, value): return value
    monkeypatch.setattr(cli, "build_snapshot", lambda *args, **kwargs:snapshot); monkeypatch.setattr(cli, "build_agent_view", lambda *args, **kwargs:graph); monkeypatch.setattr(cli, "analyze_bottlenecks", lambda *args:report); monkeypatch.setattr(cli, "_read_json", lambda *args:profile_data)
    for name in ("PythonGraphAnalyzer", "TypeScriptAnalyzer", "KotlinAnalyzer", "FastAPIAnalyzer", "AndroidAnalyzer"): monkeypatch.setattr(cli, name, Analyzer)
    monkeypatch.setattr(cli, "ArchitectureGraphBuilder", Builder); monkeypatch.setattr(cli, "AndroidArchitectureGraphBuilder", Builder)
    for option, mode in (("-l", "python"), ("-l", "typescript"), ("-l", "kotlin"), ("-f", "fastapi"), ("-f", "android")):
        rendered.clear(); writes.clear(); monkeypatch.setattr(sys, "argv", ["code-analyzer", str(tmp_path), option, mode, "-o", str(tmp_path / "architecture.html"), "--agent-view", str(tmp_path / "agent.json"), "--bottlenecks", str(tmp_path / "b.json"), "--bottlenecks-html", str(tmp_path / "b.html"), "--harness-profile", str(tmp_path / "h.json")])
        cli.main(file_lister=lambda *args, **kwargs:("test", ["a.py"]), file_writer=lambda path, text:writes.append(path), renderer_factory=Renderer)
        assert rendered == [(tmp_path / "architecture.html").resolve()] and {path.name for path in writes} == {"agent.json", "b.json", "b.html"}


@pytest.mark.parametrize("arguments", [("--bottlenecks-html", "b.html"), ("--bottlenecks", "b.json")])
def test_NA_15_cli_rejects_missing_bottleneck_dependencies(arguments, monkeypatch):
    import code_analyzer.cli as cli
    monkeypatch.setattr(sys, "argv", ["code-analyzer", ".", *arguments])
    with pytest.raises(SystemExit) as error: cli.parse_args()
    assert error.value.code == 2


def test_NA_16_cli_rejects_output_and_asset_directory_collisions(monkeypatch):
    import code_analyzer.cli as cli
    monkeypatch.setattr(sys, "argv", ["code-analyzer", ".", "-l", "python", "-o", "same.html", "--bottlenecks", "same_assets", "--harness-profile", "h.json"])
    with pytest.raises(SystemExit) as error: cli.parse_args()
    assert error.value.code == 2


def test_NA_17_removed_observation_api_and_cli_option_are_absent(monkeypatch):
    import bottlenecks
    import code_analyzer.cli as cli
    assert not hasattr(bottlenecks, "parse_observation_trace")
    monkeypatch.setattr(sys, "argv", ["code-analyzer", ".", "--observation-trace", "x"])
    with pytest.raises(SystemExit) as error: cli.parse_args()
    assert error.value.code == 2


def test_NA_18_v1_renderer_input_raises_report_input_error():
    from report.bottlenecks import render_report
    from report.shared.document import ReportInputError
    with pytest.raises(ReportInputError): render_report({"schema":"bottlenecks.v1"})


def test_NA_19_equivalent_inputs_have_byte_identical_compact_json():
    first, second = bottlenecks_to_json(analyze_bottlenecks(*subject(), harness())), bottlenecks_to_json(analyze_bottlenecks(*subject(), harness()))
    assert first == second and first.endswith("\n") and "\n" not in first[:-1]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True])
def test_NA_20_nonfinite_boolean_duplicate_and_invalid_ranges_raise_typed_errors(bad):
    from report.bottlenecks import render_report
    from report.shared.document import ReportInputError
    snapshot, architecture, graph = subject()
    query = replace(graph.query_nodes[0], occurrence_ranges=[replace(graph.query_nodes[0].occurrence_ranges[0], start=-1)])
    with pytest.raises(BottleneckInputError): analyze_bottlenecks(snapshot, architecture, replace(graph, query_nodes=[query], connections=[]), harness())
    with pytest.raises(BottleneckInputError): analyze_bottlenecks(snapshot, replace(architecture, nodes=[replace(architecture.nodes[0], cost=NodeCost(bad, 1, 1)), *architecture.nodes[1:]]), graph, harness())
    payload = {"schema":"bottlenecks.v2","snapshot":{},"profile":{},"versions":{},"coverage":{},"dependency_network":{},"exploration_network":{},"probes":[{"probe":{"id":"p"},"output":{"total_count":0,"visible_count":0,"omitted_count":0}},{"probe":{"id":"p"},"output":{"total_count":0,"visible_count":0,"omitted_count":0}}],"candidates":[],"limitations":[]}
    with pytest.raises(ReportInputError): render_report(payload)
