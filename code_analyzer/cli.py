"""
Command-line interface for the FastAPI Visualizer.
"""

import argparse
import json
import sys
import time
import webbrowser
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional

from language_analyzers.core.analysis_coverage import attach_coverage
from analysis import (EdgeWeightsError, GraphAnalysisConfig, GraphAnalyzer,
                      default_edge_weights_path, load_edge_weights)
from repository import (ScanPolicyError, build_snapshot, default_scan_policy_path,
                        list_repository_files, load_scan_policy, read_file)
from language_analyzers.core.graph_models import GraphEdge, GraphNode
from language_analyzers.core.report_schema import ReportCollection
from language_analyzers.core.serialization import architecture_to_dict
from analysis.file_graph import to_file_architecture
from analysis.candidate_projection import AMBIGUITY_POLICY
from bottlenecks.core import _snapshot, _validate

from framework_analyzers.android.analyzer import AndroidAnalyzer
from framework_analyzers.android.graph import AndroidArchitectureGraphBuilder
from framework_analyzers.fastapi.analyzer import FastAPIAnalyzer
from framework_analyzers.fastapi.graph import ArchitectureGraphBuilder
from framework_analyzers.nestjs.analyzer import NestJSAnalyzer
from framework_analyzers.nestjs.graph import NestJSGraphBuilder
from framework_analyzers.route_matching import match_routes
from framework_analyzers.sqlalchemy.analyzer import SQLAlchemyAnalyzer
from framework_analyzers.sqlalchemy.graph import SQLAlchemyGraphBuilder
from language_analyzers.python.graph import PythonGraphAnalyzer
from language_analyzers.kotlin import KotlinAnalyzer, KotlinParseCache
from language_analyzers.typescript import TypeScriptAnalyzer
from renderers.html import HTMLRenderer
from bottlenecks import BottleneckInputError, analyze_bottlenecks, bottlenecks_to_json

FRAMEWORK_LABELS = {"fastapi": "FastAPI", "android": "Android", "sqlalchemy": "SQLAlchemy", "nestjs": "NestJS"}
LANGUAGE_LABELS = {"kotlin": "Kotlin", "python": "Python", "typescript": "TypeScript/JavaScript"}


@dataclass
class MergedArchitecture:
    project_name: str
    project_path: str
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    report_collections: List[ReportCollection] = field(default_factory=list)


class _AnalyzerSelection(argparse.Action):
    """-f and -l share one destination so argv order across both flags is preserved."""

    def __call__(self, parser, namespace, values, option_string=None):
        selections = list(getattr(namespace, self.dest, None) or [])
        selections.append((self.const, values))
        setattr(namespace, self.dest, selections)


def parse_args():
    parser = argparse.ArgumentParser(
        prog="code-analyzer",
        description="Statically analyze a project and generate an interactive HTML dependency bottleneck report.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        default=".",
        help="Path to the project directory.",
    )
    parser.add_argument(
        "-f",
        "--framework",
        choices=sorted(FRAMEWORK_LABELS),
        action=_AnalyzerSelection,
        dest="analyzers",
        const="framework",
        default=None,
        help="Framework adapter to analyze the project with (default: fastapi). "
             "Repeatable and mixable with -l; analyzers run in argv order.",
    )
    parser.add_argument(
        "-l",
        "--language",
        choices=sorted(LANGUAGE_LABELS),
        action=_AnalyzerSelection,
        dest="analyzers",
        const="language",
        default=None,
        help="Analyze a language directly without framework semantics. Repeatable and mixable with -f.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="architecture.html",
        help="Output path for the generated interactive HTML report.",
    )
    parser.add_argument(
        "-e",
        "--entrypoint",
        default=None,
        help="[fastapi only] Optional entrypoint Python file (e.g. main.py or app/main.py).",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Custom title for the report.",
    )
    parser.add_argument(
        "--no-models",
        action="store_true",
        help="Exclude schema-shaped nodes from the graph (Pydantic/SQLModel schemas for fastapi, Room entities for android).",
    )
    parser.add_argument(
        "--no-deps",
        action="store_true",
        help="Exclude dependency-injection-shaped nodes from the graph (FastAPI dependencies for fastapi, Hilt/Dagger modules and bindings for android).",
    )
    parser.add_argument(
        "--no-language-graph",
        action="store_true",
        help="Exclude the underlying language symbol graph (modules, classes, functions, "
             "imports and calls) and show framework components only.",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Automatically open the generated HTML report in the default web browser.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also export architecture graph metadata as a JSON file.",
    )
    parser.add_argument("--granularity", choices=("file", "symbol"), default="file", help="Unit for network metrics and candidates.")
    parser.add_argument("--bottlenecks", metavar="PATH", help="Write bottleneck JSON for the selected granularity.")
    parser.add_argument(
        "--edge-weights",
        default=str(default_edge_weights_path()),
        metavar="PATH",
        help="Edge weight profile applied to PageRank, HITS and weighted fan metrics.",
    )
    args = parser.parse_args()
    if not args.analyzers:
        args.analyzers = [("framework", "fastapi")]
    args.framework = next((value for kind, value in args.analyzers if kind == "framework"), "fastapi")
    args.language = next((value for kind, value in args.analyzers if kind == "language"), None)
    if len(args.analyzers) != len(set(args.analyzers)):
        parser.error("the same -f/-l value may not be repeated")
    if args.entrypoint and ("framework", "fastapi") not in args.analyzers:
        parser.error("--entrypoint is only supported with --framework fastapi")
    output = Path(args.output).resolve()
    output_paths = [output, output.with_name(f"{output.stem}_assets")]
    if args.bottlenecks:
        output_paths.append(Path(args.bottlenecks).resolve())
    if args.json:
        output_paths.append(output.with_suffix(".json"))
    if len(output_paths) != len(set(output_paths)):
        parser.error("analysis output paths must be distinct")
    return args


def _write_text(path: Path, text: str, writer: Callable[[Path, str], object]):
    try:
        return writer(path, text)
    except (OSError, UnicodeError) as exc:
        print(f"[!] Error: {exc}", file=sys.stderr)
        raise SystemExit(1)


def _output_paths(project_path: Path, args) -> tuple[Path, ...]:
    output = Path(args.output).resolve()
    paths = [output, output.with_name(f"{output.stem}_assets")]
    if args.json:
        paths.append(output.with_suffix(".json"))
    if args.bottlenecks:
        paths.append(Path(args.bottlenecks).resolve())
    return tuple(paths)


def _exclude_output_paths(
    project_path: Path, paths: list[str], outputs: tuple[Path, ...]
) -> list[str]:
    excluded = []
    for output in outputs:
        try:
            excluded.append(output.relative_to(project_path))
        except ValueError:
            pass
    return [
        path for path in paths
        if not any(Path(path) == item or item in Path(path).parents for item in excluded)
    ]


def _run_analyzer(kind, value, args, project_path, repository_snapshot, analysis_config, single):
    builder = None
    http_calls = []
    if kind == "language" and value == "python":
        arch = PythonGraphAnalyzer(project_path, snapshot=repository_snapshot).analyze()
        if args.granularity == "symbol" and single and not args.bottlenecks:
            arch.stats["analysis"] = GraphAnalyzer(analysis_config).analyze(
                arch.nodes, arch.edges, project_path=arch.project_path
            )
    elif kind == "language" and value == "typescript":
        arch = TypeScriptAnalyzer(project_path, snapshot=repository_snapshot).analyze()
        http_calls = arch.http_calls
        if args.granularity == "symbol" and single:
            arch.stats["analysis"] = GraphAnalyzer(analysis_config).analyze(
                arch.nodes, arch.edges, project_path=arch.project_path
            )
    elif kind == "language":
        arch = KotlinAnalyzer(project_path, snapshot=repository_snapshot).analyze()
        if args.granularity == "symbol" and single:
            arch.stats["analysis"] = GraphAnalyzer(analysis_config).analyze(
                arch.nodes, arch.edges, project_path=arch.project_path
            )
    elif value == "android":
        parse_cache = KotlinParseCache()
        analyzer = AndroidAnalyzer(str(project_path), entrypoint=None, parse_cache=parse_cache,
                                   snapshot=repository_snapshot)
        arch = analyzer.analyze()
        builder = AndroidArchitectureGraphBuilder(
            include_models=not args.no_models,
            include_dependencies=not args.no_deps,
            include_language_graph=not args.no_language_graph,
            parse_cache=parse_cache,
            snapshot=repository_snapshot,
            analysis_config=analysis_config,
            compute_metrics=args.granularity == "symbol",
        )
        arch = builder.build_graph(arch)
    elif value == "nestjs":
        arch = NestJSAnalyzer(str(project_path), snapshot=repository_snapshot).analyze()
        explicit_ts = ("language", "typescript") in args.analyzers
        builder = NestJSGraphBuilder(
            include_dependencies=not args.no_deps,
            include_language_graph=not args.no_language_graph,
            emit_language_graph=not explicit_ts and not args.no_language_graph,
            snapshot=repository_snapshot,
            analysis_config=analysis_config,
            compute_metrics=args.granularity == "symbol",
        )
        arch = builder.build_graph(arch)
        if builder.emit_language_graph:
            http_calls = arch.http_calls
    elif value == "sqlalchemy":
        analyzer = SQLAlchemyAnalyzer(str(project_path), snapshot=repository_snapshot)
        arch = analyzer.analyze()
        # A selected python-core emitter (FastAPI's language graph or -l python) already owns
        # those node ids, so the duplicate-id check in _run_merged stays in force.
        python_core_emitted = (
            ("framework", "fastapi") in args.analyzers or ("language", "python") in args.analyzers
        ) and not args.no_language_graph
        builder = SQLAlchemyGraphBuilder(
            include_models=not args.no_models,
            include_language_graph=not args.no_language_graph,
            emit_language_graph=not python_core_emitted,
            snapshot=repository_snapshot,
            analysis_config=analysis_config,
            compute_metrics=args.granularity == "symbol",
        )
        arch = builder.build_graph(arch)
    else:
        analyzer = FastAPIAnalyzer(str(project_path), entrypoint=args.entrypoint,
                                   snapshot=repository_snapshot)
        arch = analyzer.analyze()

        builder = ArchitectureGraphBuilder(
            include_models=not args.no_models,
            include_dependencies=not args.no_deps,
            include_language_graph=not args.no_language_graph,
            snapshot=repository_snapshot,
            analysis_config=analysis_config,
            compute_metrics=args.granularity == "symbol",
        )
        arch = builder.build_graph(arch)
    return arch, builder, http_calls


def _run_merged(args, project_path, repository_snapshot, analysis_config, results=None) -> MergedArchitecture:
    results = results if results is not None else [
        _run_analyzer(kind, value, args, project_path, repository_snapshot, analysis_config, single=False)
        for kind, value in args.analyzers
    ]
    merged = MergedArchitecture(
        project_name=results[0][0].project_name,
        project_path=results[0][0].project_path,
    )
    http_calls = []
    seen = set()
    for arch, _builder, calls in results:
        for node in arch.nodes:
            if node.id in seen:
                print(f"[!] Error: duplicate node id across analyzers: {node.id}", file=sys.stderr)
                raise SystemExit(1)
            seen.add(node.id)
        merged.nodes.extend(arch.nodes)
        merged.edges.extend(arch.edges)
        merged.report_collections.extend(arch.report_collections)
        http_calls.extend(calls)
        for key, item in arch.stats.items():
            if key != "analysis":
                merged.stats.setdefault(key, item)
    attach_coverage(merged, repository_snapshot, *(arch.stats.get("analysis_coverage") for arch, _, _ in results))
    for arch, _builder, _calls in results:
        merged.edges.extend(edge for edge in getattr(arch, "pending_implementation_edges", ())
                            if edge.from_id in seen and edge.to_id in seen)
    route_edges, route_stats = match_routes(merged.nodes, http_calls)
    merged.edges.extend(route_edges)
    merged.stats["nodes_by_kind"] = dict(Counter(node.kind or node.category for node in merged.nodes))
    merged.stats["edges_by_relation"] = dict(Counter(edge.relation for edge in merged.edges))
    merged.stats["edges_by_confidence"] = dict(Counter(str(edge.confidence) for edge in merged.edges))
    merged.stats["route_matching"] = route_stats
    if args.granularity == "symbol":
        merged.stats["analysis"] = GraphAnalyzer(analysis_config).analyze(
            merged.nodes, merged.edges, project_path=merged.project_path
        )
    return merged


def main(
    *,
    file_lister: Callable = list_repository_files,
    file_reader: Callable[[Path], Optional[str]] = read_file,
    file_writer: Callable[[Path, str], object] = lambda path, text: path.write_text(
        text, encoding="utf-8"
    ),
    renderer_factory: Callable[..., HTMLRenderer] = HTMLRenderer,
):
    args = parse_args()

    project_path = Path(args.project_path).resolve()

    if not project_path.exists():
        print(f"[!] Error: Project path does not exist: {project_path}", file=sys.stderr)
        sys.exit(1)
    if not project_path.is_dir():
        print(f"[!] Error: Project path is not a directory: {project_path}", file=sys.stderr)
        raise SystemExit(1)

    labels = [
        (FRAMEWORK_LABELS if kind == "framework" else LANGUAGE_LABELS)[value]
        for kind, value in args.analyzers
    ]
    analyzer_label = " + ".join(labels)
    print(f"[*] Analyzing {analyzer_label} project at: {project_path}")

    repository_snapshot = None
    bottleneck_report = None
    outputs = _output_paths(project_path, args)
    analysis_config = None
    try:
        edge_weights = load_edge_weights(args.edge_weights)
        analysis_config = GraphAnalysisConfig(edge_weights=edge_weights)
        scan_policy = load_scan_policy(default_scan_policy_path())
        inventory = file_lister(
            project_path, tracked_files_only=scan_policy.tracked_files_only
        )
        if isinstance(inventory, tuple) and len(inventory) == 2:
            ignore_source, paths = inventory
        else:
            ignore_source, paths = "", inventory
        timing = {}
        overall_started = time.perf_counter()
        stage_started = overall_started
        repository_snapshot = build_snapshot(
            project_path, paths, policy=scan_policy, reader=file_reader,
            ignore_source=ignore_source, excluded_paths=outputs,
        )
        _snapshot(repository_snapshot)
        timing["snapshot"] = time.perf_counter() - stage_started
    except (OSError, UnicodeError, ValueError, EdgeWeightsError, ScanPolicyError) as exc:
        print(f"[!] Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    try:
        stage_started = time.perf_counter()
        results = [
            _run_analyzer(kind, value, args, project_path, repository_snapshot, analysis_config, single=len(args.analyzers) == 1)
            for kind, value in args.analyzers
        ]
        timing["extraction"] = time.perf_counter() - stage_started
        stage_started = time.perf_counter()
        if len(results) == 1:
            arch, _builder, _http_calls = results[0]
        else:
            arch = _run_merged(args, project_path, repository_snapshot, analysis_config, results=results)
        timing["integration"] = time.perf_counter() - stage_started
        stage_started = time.perf_counter()
        _validate(repository_snapshot, arch)
        if args.granularity == "file":
            arch = to_file_architecture(arch, repository_snapshot)
        timing["conversion"] = time.perf_counter() - stage_started
        stage_started = time.perf_counter()
        final_analysis = GraphAnalyzer(analysis_config).analyze(arch.nodes, arch.edges, project_path=arch.project_path)
        if args.granularity == "file":
            arch.stats["analysis"] = deepcopy(final_analysis)
        elif "analysis" not in arch.stats:
            arch.stats["analysis"] = {
                "ambiguity_policy": final_analysis["ambiguity_policy"],
                "edge_weights": deepcopy(final_analysis["edge_weights"]),
            }
        elif not isinstance(arch.stats["analysis"], Mapping) or arch.stats["analysis"].get("ambiguity_policy") != AMBIGUITY_POLICY:
            raise BottleneckInputError("missing or unsupported analysis ambiguity_policy")
        bottleneck_report = analyze_bottlenecks(repository_snapshot, arch, edge_weights, analysis=final_analysis)
        timing["metrics_candidates"] = time.perf_counter() - stage_started
    except (OSError, UnicodeError, ValueError, BottleneckInputError) as exc:
        print(f"[!] Error: {exc}", file=sys.stderr)
        raise SystemExit(1)

    stage_started = time.perf_counter()
    try:
        renderer = renderer_factory(title=args.title, framework_label=analyzer_label)
        output_html_path = Path(renderer.render(arch, str(outputs[0]), bottleneck_report=json.loads(bottlenecks_to_json(bottleneck_report)))).resolve()
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"[!] Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    timing["output"] = time.perf_counter() - stage_started
    timing["total"] = time.perf_counter() - overall_started
    main.last_timing = timing
    print(f"[✓] Generated unified dependency bottleneck report: {output_html_path}")

    if args.json:
        json_output_path = output_html_path.with_suffix(".json")
        _write_text(
            json_output_path,
            json.dumps(architecture_to_dict(arch), indent=2, ensure_ascii=False, default=str),
            file_writer,
        )
        print(f"[✓] Exported architecture JSON: {json_output_path}")

    if args.bottlenecks:
        bottleneck_path = Path(args.bottlenecks).resolve()
        _write_text(bottleneck_path, bottlenecks_to_json(bottleneck_report), file_writer)
        print(f"[✓] Exported bottleneck report: {bottleneck_path}")

    stats = arch.stats
    print(f"\n📊 Summary Statistics:")
    if "total_apps" in stats:
        print(f"  • Applications: {stats.get('total_apps', 0)}")
    for collection in arch.report_collections:
        print(f"  • {collection.label:<14}{len(collection.rows)}")
    if stats.get("methods_breakdown"):
        print(f"  • Methods:      {stats['methods_breakdown']}")
    top_cost = stats.get("analysis", {}).get("top_weighted_cost", [])
    if top_cost:
        print(f"  • Highest PageRank × effective token cost: {top_cost[0]['label']} ({top_cost[0]['value']:.4f})")

    if args.open:
        print(f"[*] Opening {output_html_path} in default browser...")
        webbrowser.open(f"file://{output_html_path}")


if __name__ == "__main__":
    main()
