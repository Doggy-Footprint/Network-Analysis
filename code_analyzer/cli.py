"""
Command-line interface for the FastAPI Visualizer.
"""

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from typing import Callable, Mapping, Optional

from analysis import (EdgeWeightsError, GraphAnalysisConfig, GraphAnalyzer,
                      default_edge_weights_path, load_edge_weights)
from repository import (ScanPolicyError, build_snapshot, default_scan_policy_path,
                        list_repository_files, load_scan_policy, read_file)
from language_analyzers.core.serialization import architecture_to_dict

from framework_analyzers.android.analyzer import AndroidAnalyzer
from framework_analyzers.android.graph import AndroidArchitectureGraphBuilder
from framework_analyzers.fastapi.analyzer import FastAPIAnalyzer
from framework_analyzers.fastapi.graph import ArchitectureGraphBuilder
from language_analyzers.python.graph import PythonGraphAnalyzer
from language_analyzers.kotlin import KotlinAnalyzer, KotlinParseCache
from language_analyzers.typescript import TypeScriptAnalyzer
from renderers.html import HTMLRenderer
from bottlenecks import BottleneckInputError, analyze_bottlenecks, bottlenecks_to_json
from report.bottlenecks import render_report as render_bottlenecks_report

FRAMEWORK_LABELS = {"fastapi": "FastAPI", "android": "Android"}
LANGUAGE_LABELS = {"kotlin": "Kotlin", "python": "Python", "typescript": "TypeScript/JavaScript"}


def parse_args():
    parser = argparse.ArgumentParser(
        prog="code-analyzer",
        description="Statically analyze a project and generate an interactive HTML architecture & dependency dashboard.",
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
        default="fastapi",
        help="Which framework adapter to analyze the project with.",
    )
    parser.add_argument(
        "-l",
        "--language",
        choices=sorted(LANGUAGE_LABELS),
        help="Analyze a language directly without framework semantics.",
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
        help="Custom title for the dashboard.",
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
    parser.add_argument(
        "--mermaid",
        action="store_true",
        help="Print Mermaid diagram markdown to stdout.",
    )
    parser.add_argument("--bottlenecks", metavar="PATH", help="Write bottlenecks.v3 JSON.")
    parser.add_argument("--bottlenecks-html", metavar="PATH", help="Write bottlenecks.v3 HTML.")
    parser.add_argument(
        "--edge-weights",
        default=str(default_edge_weights_path()),
        metavar="PATH",
        help="Edge weight profile applied to PageRank, HITS and weighted fan metrics.",
    )
    args = parser.parse_args()
    if (args.language or args.framework != "fastapi") and args.entrypoint:
        parser.error("--entrypoint is only supported with --framework fastapi")
    if args.bottlenecks_html and not args.bottlenecks:
        parser.error("--bottlenecks-html requires --bottlenecks")
    if args.bottlenecks:
        output = Path(args.output).resolve()
        output_paths = [output, output.with_name(f"{output.stem}_assets"), Path(args.bottlenecks).resolve()]
        if args.bottlenecks_html:
            output_paths.append(Path(args.bottlenecks_html).resolve())
        if args.json:
            output_paths.append(Path(args.output).resolve().with_suffix(".json"))
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
    if args.bottlenecks_html:
        paths.append(Path(args.bottlenecks_html).resolve())
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
        print(f"[!] Error: Project path does not exist: {project_path}")
        sys.exit(1)

    analyzer_label = LANGUAGE_LABELS.get(args.language) or FRAMEWORK_LABELS[args.framework]
    print(f"[*] Analyzing {analyzer_label} project at: {project_path}")

    builder = None
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
        paths = _exclude_output_paths(project_path, paths, outputs)
        repository_snapshot = build_snapshot(
            project_path, paths, policy=scan_policy, reader=file_reader,
            ignore_source=ignore_source, excluded_paths=outputs,
        )
    except (OSError, UnicodeError, ValueError, EdgeWeightsError, ScanPolicyError) as exc:
        print(f"[!] Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    if args.language == "python":
        arch = PythonGraphAnalyzer(project_path, snapshot=repository_snapshot).analyze()
        if not args.bottlenecks:
            arch.stats["analysis"] = GraphAnalyzer(analysis_config).analyze(
                arch.nodes, arch.edges, project_path=arch.project_path
            )
    elif args.language == "typescript":
        arch = TypeScriptAnalyzer(project_path, snapshot=repository_snapshot).analyze()
        arch.stats["analysis"] = GraphAnalyzer(analysis_config).analyze(
            arch.nodes, arch.edges, project_path=arch.project_path
        )
    elif args.language == "kotlin":
        arch = KotlinAnalyzer(project_path, snapshot=repository_snapshot).analyze()
        arch.stats["analysis"] = GraphAnalyzer(analysis_config).analyze(
            arch.nodes, arch.edges, project_path=arch.project_path
        )
    elif args.framework == "android":
        parse_cache = KotlinParseCache()
        analyzer = AndroidAnalyzer(str(project_path), entrypoint=args.entrypoint, parse_cache=parse_cache,
                                   snapshot=repository_snapshot)
        arch = analyzer.analyze()
        builder = AndroidArchitectureGraphBuilder(
            include_models=not args.no_models,
            include_dependencies=not args.no_deps,
            include_language_graph=not args.no_language_graph,
            parse_cache=parse_cache,
            snapshot=repository_snapshot,
            analysis_config=analysis_config,
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
        )
        arch = builder.build_graph(arch)

    if args.bottlenecks:
        try:
            bottleneck_report = analyze_bottlenecks(
                repository_snapshot, arch, edge_weights
            )
        except BottleneckInputError as exc:
            print(f"[!] Error: {exc}", file=sys.stderr)
            raise SystemExit(1)

    try:
        renderer = renderer_factory(title=args.title, framework_label=analyzer_label)
        output_html_path = Path(renderer.render(arch, str(outputs[0]))).resolve()
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"[!] Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"[✓] Generated interactive HTML dashboard: {output_html_path}")

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
        if args.bottlenecks_html:
            html_path = Path(args.bottlenecks_html).resolve()
            _write_text(html_path, render_bottlenecks_report(json.loads(bottlenecks_to_json(bottleneck_report))), file_writer)
            print(f"[✓] Exported bottleneck HTML: {html_path}")

    if args.mermaid:
        if builder is None:
            print("[!] Mermaid output is currently available for framework analyzers only.")
            return
        mermaid_code = builder.generate_mermaid(arch)
        print("\n--- Mermaid Architecture Diagram ---")
        print(mermaid_code)
        print("------------------------------------\n")

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
        print(f"  • Highest agent context cost: {top_cost[0]['label']} ({top_cost[0]['value']:.4f})")

    if args.open:
        print(f"[*] Opening {output_html_path} in default browser...")
        webbrowser.open(f"file://{output_html_path}")


if __name__ == "__main__":
    main()
