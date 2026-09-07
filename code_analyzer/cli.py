"""
Command-line interface for the FastAPI Visualizer.
"""

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from agent_view import build_agent_view, diff_agent_view, graph_to_json, load_profile
from agent_view.profile import default_profile_path
from analysis import GraphAnalyzer
from discovery import (
    CachedSeedQueryGenerator,
    GraphView,
    build_report,
    default_policy_path,
    default_weights_path,
    load_cost_weights,
    load_exploration_policy,
    load_scenarios,
    report_to_json,
    resolve_seed_queries,
    run_scenario,
)
from language_analyzers.core.serialization import architecture_to_dict

from framework_analyzers.android.analyzer import AndroidAnalyzer
from framework_analyzers.android.graph import AndroidArchitectureGraphBuilder
from framework_analyzers.fastapi.analyzer import FastAPIAnalyzer
from framework_analyzers.fastapi.dynamic_analyzer import DynamicFastAPIAnalyzer
from framework_analyzers.fastapi.graph import ArchitectureGraphBuilder
from language_analyzers.python.graph import PythonGraphAnalyzer
from language_analyzers.kotlin import KotlinAnalyzer
from language_analyzers.typescript import TypeScriptAnalyzer
from renderers.html import HTMLRenderer

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
    parser.add_argument(
        "--phase-b",
        default=None,
        metavar="SCENARIOS",
        help="Simulate phase A and phase B target discovery over the scenarios in the given file.",
    )
    parser.add_argument(
        "--phase-b-out",
        default="phase_b_cost.json",
        metavar="PATH",
        help="Output path for the phase-B cost report.",
    )
    parser.add_argument(
        "--exploration-policy",
        default=None,
        metavar="PATH",
        help="Override the exploration policy profile used by --phase-b.",
    )
    parser.add_argument(
        "--cost-weights",
        default=None,
        metavar="PATH",
        help="Override the cost weight profile used by --phase-b.",
    )
    parser.add_argument(
        "--seed-queries",
        default=None,
        metavar="PATH",
        help="Cached seed query fixture used by --phase-b scenarios without explicit seed queries.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=None,
        metavar="N",
        help="Fixed Monte Carlo sample count for --phase-b, overriding the adaptive loop.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="N",
        help="Random seed root for --phase-b, overriding the policy profile seed.",
    )
    args = parser.parse_args()
    if (args.language or args.framework != "fastapi") and (args.entrypoint or args.app):
        parser.error("--entrypoint and --app are only supported with --framework fastapi")
    if args.agent_view_profile and not args.agent_view:
        parser.error("--agent-view-profile requires --agent-view")
    if not args.phase_b:
        for flag, value in (
            ("--phase-b-out", args.phase_b_out if args.phase_b_out != "phase_b_cost.json" else None),
            ("--exploration-policy", args.exploration_policy),
            ("--cost-weights", args.cost_weights),
            ("--seed-queries", args.seed_queries),
            ("--samples", args.samples),
            ("--seed", args.seed),
        ):
            if value is not None:
                parser.error(f"{flag} requires --phase-b")
    if args.samples is not None and args.samples < 1:
        parser.error("--samples must be >= 1")
    return args


def main():
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
    if args.language == "python":
        arch = PythonGraphAnalyzer(project_path).analyze()
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
        analyzer = AndroidAnalyzer(str(project_path), entrypoint=args.entrypoint)
        arch = analyzer.analyze()
        builder = AndroidArchitectureGraphBuilder(
            include_models=not args.no_models,
            include_dependencies=not args.no_deps,
            include_language_graph=not args.no_language_graph,
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

    renderer = HTMLRenderer(title=args.title, framework_label=analyzer_label)
    output_html_path = renderer.render(arch, args.output)
    print(f"[✓] Generated interactive HTML dashboard: {output_html_path}")

    if args.json:
        json_output_path = output_html_path.with_suffix(".json")
        with open(json_output_path, "w", encoding="utf-8") as f:
            json.dump(architecture_to_dict(arch), f, indent=2, ensure_ascii=False, default=str)
        print(f"[✓] Exported architecture JSON: {json_output_path}")

    agent_view_graph = None
    agent_view_profile = None
    if args.agent_view or args.phase_b:
        agent_view_profile = load_profile(args.agent_view_profile or default_profile_path())
        agent_view_path = Path(args.agent_view) if args.agent_view else None
        dashboard_assets = output_html_path.with_name(f"{output_html_path.stem}_assets")
        excluded = [output_html_path, dashboard_assets]
        if agent_view_path is not None:
            excluded.append(agent_view_path)
        if args.phase_b:
            excluded.append(Path(args.phase_b_out))
        agent_view_graph = build_agent_view(
            arch,
            profile=agent_view_profile,
            excluded_paths=tuple(excluded),
        )
    if args.agent_view:
        agent_view_path = Path(args.agent_view)
        agent_view_path.write_text(graph_to_json(agent_view_graph), encoding="utf-8")
        print(f"[✓] Exported agent-view graph: {agent_view_path}")

    if args.phase_b:
        policy = load_exploration_policy(args.exploration_policy or default_policy_path())
        weights = load_cost_weights(args.cost_weights or default_weights_path())
        cached = CachedSeedQueryGenerator.from_path(
            args.seed_queries or Path("fixtures") / "seed_queries.v1.json"
        )
        view = GraphView(agent_view_graph)
        results = []
        seed_sets = {}
        for scenario in load_scenarios(args.phase_b, view):
            resolved, seed_set = resolve_seed_queries(scenario, cached)
            seed_sets[resolved.id] = seed_set
            results.append(
                run_scenario(
                    view, resolved, policy, weights, samples=args.samples, seed=args.seed
                )
            )
        payload = build_report(
            agent_view_graph, view, results, agent_view_profile, policy, weights, seed_sets
        )
        phase_b_path = Path(args.phase_b_out)
        phase_b_path.write_text(report_to_json(payload), encoding="utf-8")
        print(f"[✓] Exported phase-B cost report: {phase_b_path}")

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
