"""
Command-line interface for the FastAPI Visualizer.
"""

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from typing import Callable, Mapping, Optional

from agent_view import (build_agent_view, build_snapshot, diff_agent_view, graph_to_json,
                        list_repository_files, load_profile, read_file)
from agent_view.profile import ProfileError, default_profile_path
from analysis import GraphAnalyzer
from language_analyzers.core.serialization import architecture_to_dict

from framework_analyzers.android.analyzer import AndroidAnalyzer
from framework_analyzers.android.graph import AndroidArchitectureGraphBuilder
from framework_analyzers.fastapi.analyzer import FastAPIAnalyzer
from framework_analyzers.fastapi.dynamic_analyzer import DynamicFastAPIAnalyzer
from framework_analyzers.fastapi.graph import ArchitectureGraphBuilder
from language_analyzers.python.graph import PythonGraphAnalyzer
from language_analyzers.kotlin import KotlinAnalyzer, KotlinParseCache
from language_analyzers.typescript import TypeScriptAnalyzer
from renderers.html import HTMLRenderer
from bottlenecks import (BottleneckInputError, HarnessProfileError, analyze_bottlenecks,
                         bottlenecks_to_json, parse_harness_profile)
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
        "--app",
        default=None,
        help="[fastapi only] Optional dynamic app import string (e.g. 'app.main:app') for runtime introspection if installed.",
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
    parser.add_argument(
        "--agent-view",
        default=None,
        metavar="PATH",
        help="Write the deterministic agent-view graph (readable nodes, query nodes, framework links) as JSON.",
    )
    parser.add_argument(
        "--agent-view-diff",
        nargs=2,
        default=None,
        metavar=("BEFORE", "AFTER"),
        help="Print the diff between two agent-view JSON files and exit.",
    )
    parser.add_argument(
        "--agent-view-profile",
        default=None,
        metavar="PATH",
        help="Override the derived-query rule profile used by --agent-view.",
    )
    parser.add_argument("--bottlenecks", metavar="PATH", help="Write bottlenecks.v2 JSON.")
    parser.add_argument("--harness-profile", metavar="PATH", help="Harness profile for --bottlenecks.")
    parser.add_argument("--bottlenecks-html", metavar="PATH", help="Write bottlenecks.v2 HTML.")
    args = parser.parse_args()
    if (args.language or args.framework != "fastapi") and (args.entrypoint or args.app):
        parser.error("--entrypoint and --app are only supported with --framework fastapi")
    if args.agent_view_profile and not (args.agent_view or args.bottlenecks):
        parser.error("--agent-view-profile requires --agent-view or --bottlenecks")
    if args.bottlenecks and not args.harness_profile:
        parser.error("--bottlenecks requires --harness-profile")
    if args.harness_profile and not args.bottlenecks:
        parser.error("--harness-profile requires --bottlenecks")
    if args.bottlenecks_html and not args.bottlenecks:
        parser.error("--bottlenecks-html requires --bottlenecks")
    if args.agent_view_diff and args.bottlenecks:
        parser.error("--agent-view-diff cannot be combined with --bottlenecks")
    if args.bottlenecks:
        output = Path(args.output).resolve()
        output_paths = [output, output.with_name(f"{output.stem}_assets"), Path(args.bottlenecks).resolve()]
        if args.bottlenecks_html:
            output_paths.append(Path(args.bottlenecks_html).resolve())
        if args.agent_view:
            output_paths.append(Path(args.agent_view).resolve())
        if args.json:
            output_paths.append(Path(args.output).resolve().with_suffix(".json"))
        if len(output_paths) != len(set(output_paths)):
            parser.error("analysis output paths must be distinct")
    return args


def _read_json(path: Path, reader: Callable[[Path], Optional[str]]):
    text = reader(path)
    if text is None:
        raise OSError(f"unable to read {path}")
    return json.loads(text)


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
    if args.agent_view:
        paths.append(Path(args.agent_view).resolve())
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

    if args.agent_view_diff:
        before_path, after_path = args.agent_view_diff
        with open(before_path, encoding="utf-8") as handle:
            before = json.load(handle)
        with open(after_path, encoding="utf-8") as handle:
            after = json.load(handle)
        print(json.dumps(diff_agent_view(before, after), indent=2, sort_keys=True))
        return

    project_path = Path(args.project_path).resolve()

    if not project_path.exists():
        print(f"[!] Error: Project path does not exist: {project_path}")
        sys.exit(1)

    analyzer_label = LANGUAGE_LABELS.get(args.language) or FRAMEWORK_LABELS[args.framework]
    print(f"[*] Analyzing {analyzer_label} project at: {project_path}")

    builder = None
    repository_snapshot = None
    bottleneck_report = None
    harness_profile = None
    snapshot_profile = None
    outputs = _output_paths(project_path, args)
    if args.bottlenecks:
        try:
            snapshot_profile = load_profile(args.agent_view_profile or default_profile_path())
            harness_profile = parse_harness_profile(
                _read_json(Path(args.harness_profile).resolve(), file_reader)
            )
        except (OSError, UnicodeError, json.JSONDecodeError, HarnessProfileError, ProfileError) as exc:
            print(f"[!] Error: {exc}", file=sys.stderr)
            raise SystemExit(1)
        if args.language != "python":
            try:
                ignore_source, paths = file_lister(
                    project_path, tracked_files_only=snapshot_profile.tracked_files_only
                )
                paths = _exclude_output_paths(project_path, paths, outputs)
                repository_snapshot = build_snapshot(
                    project_path, paths, profile=snapshot_profile, reader=file_reader,
                    ignore_source=ignore_source, excluded_paths=outputs,
                )
            except (OSError, UnicodeError, ValueError) as exc:
                print(f"[!] Error: {exc}", file=sys.stderr)
                raise SystemExit(1)
    if args.language == "python":
        if args.bottlenecks:
            try:
                ignore_source, paths = file_lister(
                    project_path, tracked_files_only=snapshot_profile.tracked_files_only
                )
                paths = _exclude_output_paths(project_path, paths, outputs)
                repository_snapshot = build_snapshot(
                    project_path,
                    paths,
                    profile=snapshot_profile,
                    reader=file_reader,
                    ignore_source=ignore_source,
                    excluded_paths=outputs,
                )
                arch = PythonGraphAnalyzer(project_path, repository_snapshot).analyze()
            except (OSError, UnicodeError, ValueError) as exc:
                print(f"[!] Error: {exc}", file=sys.stderr)
                raise SystemExit(1)
        else:
            arch = PythonGraphAnalyzer(project_path, repository_snapshot).analyze()
        if not args.bottlenecks:
            arch.stats["analysis"] = GraphAnalyzer().analyze(
                arch.nodes, arch.edges, project_path=arch.project_path
            )
    elif args.language == "typescript":
        arch = TypeScriptAnalyzer(project_path).analyze()
        arch.stats["analysis"] = GraphAnalyzer().analyze(
            arch.nodes, arch.edges, project_path=arch.project_path
        )
    elif args.language == "kotlin":
        arch = KotlinAnalyzer(project_path).analyze()
        arch.stats["analysis"] = GraphAnalyzer().analyze(
            arch.nodes, arch.edges, project_path=arch.project_path
        )
    elif args.framework == "android":
        parse_cache = KotlinParseCache()
        analyzer = AndroidAnalyzer(str(project_path), entrypoint=args.entrypoint, parse_cache=parse_cache)
        arch = analyzer.analyze()
        builder = AndroidArchitectureGraphBuilder(
            include_models=not args.no_models,
            include_dependencies=not args.no_deps,
            include_language_graph=not args.no_language_graph,
            parse_cache=parse_cache,
        )
        arch = builder.build_graph(arch)
    else:
        if args.app:
            print(f"[*] Attempting dynamic introspection with app import: {args.app}...")
            dyn_analyzer = DynamicFastAPIAnalyzer(str(project_path), args.app)
            arch = dyn_analyzer.analyze()
            if not arch:
                print("[!] Dynamic introspection failed. Falling back to static AST analysis...")
                analyzer = FastAPIAnalyzer(str(project_path), entrypoint=args.entrypoint)
                arch = analyzer.analyze()
        else:
            analyzer = FastAPIAnalyzer(str(project_path), entrypoint=args.entrypoint)
            arch = analyzer.analyze()

        builder = ArchitectureGraphBuilder(
            include_models=not args.no_models,
            include_dependencies=not args.no_deps,
            include_language_graph=not args.no_language_graph,
        )
        arch = builder.build_graph(arch)

    agent_view_graph = None
    agent_view_profile = None
    if args.agent_view or args.bottlenecks:
        agent_view_profile = snapshot_profile or load_profile(
            args.agent_view_profile or default_profile_path()
        )
        try:
            agent_view_graph = build_agent_view(
                arch,
                profile=agent_view_profile,
                snapshot=repository_snapshot,
                excluded_paths=outputs,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            if not args.bottlenecks:
                raise
            print(f"[!] Error: {exc}", file=sys.stderr)
            raise SystemExit(1)

    if args.bottlenecks:
        try:
            bottleneck_report = analyze_bottlenecks(
                repository_snapshot, arch, agent_view_graph, harness_profile
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

    if args.agent_view:
        agent_view_path = Path(args.agent_view).resolve()
        _write_text(agent_view_path, graph_to_json(agent_view_graph), file_writer)
        print(f"[✓] Exported agent-view graph: {agent_view_path}")

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
