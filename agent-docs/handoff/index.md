File: 5ee31efd06e4aecf-typescript-snapshot-imports.md
Summary: Resolve TypeScript relative imports from captured snapshot paths when a snapshot is supplied.
Related Files: code_analyzer/cli.py, language_analyzers/typescript/analyzer.py, tests/test_typescript_analyzer.py
Related Symbols: TypeScriptAnalyzer._resolve_import

---

File: 3a1c71a7afc82a15-framework-analysis-duplication.md
Summary: Remove the duplicated unweighted GraphAnalyzer run in fastapi/android builders that the CLI recomputes with edge weights.
Related Files: framework_analyzers/fastapi/graph.py, framework_analyzers/android/graph.py, code_analyzer/cli.py, bottlenecks/core.py
Related Symbols: ArchitectureGraphBuilder.build_graph, AndroidArchitectureGraphBuilder.build_graph, GraphAnalyzer, analyze_bottlenecks
