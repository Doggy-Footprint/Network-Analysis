# Stale Index Archive
<!-- harness:stale-index-archive -->

File: 2a5f8873bb660577-nowinandroid-bottlenecks.md
Summary: Resume generation of the Now in Android bottleneck report from the existing depth-1 clone.
Related Files: nowinandroid-analysis.html, profiles/harness.fixed-baseline.v1.json, code_analyzer/cli.py
Related Symbols: code_analyzer.cli.main, bottlenecks.core.analyze_bottlenecks
---

File: 9c41d27e5ab03f86-report-readability.md
Summary: 세 HTML 보고서 가독성 개선 workflow 중단 지점과 남은 수정.
Related Files: report/m1/generate.py, report/bottlenecks/generate.py, renderers/html/static/app.js, report/shared/labels.py
Related Symbols: short_labels, prioritize_candidates, buildOverview, ReportGraphModel.build

---

File: 5e5f4c6a7336658f-repository-scan-test-advisories.md
Summary: Run the unexecuted boundary/normalization mutations and verifier advisories for the repository snapshot layer tests.
Related Files: repository/scan.py, repository/policy.py, tests/test_repository_scan.py
Related Symbols: build_snapshot, list_repository_files, load_scan_policy

---

File: 36233e8bd84b6f88-exploration-candidate-rules.md
Summary: Add a selected repository-grounded rule for generating a possible next exploration candidate.
Related Files: agent_view/exact_query.py, agent_view/derived_query.py, agent_view/__init__.py, profiles/agent_view.v3.yaml
Related Symbols: extract_clues, derive_terms, _build_search_specs

---

File: 3a1c71a7afc82a15-framework-analysis-duplication.md
Summary: Remove the duplicated unweighted GraphAnalyzer run in fastapi/android builders that the CLI recomputes with edge weights.
Related Files: framework_analyzers/fastapi/graph.py, framework_analyzers/android/graph.py, code_analyzer/cli.py, bottlenecks/core.py
Related Symbols: ArchitectureGraphBuilder.build_graph, AndroidArchitectureGraphBuilder.build_graph, GraphAnalyzer, analyze_bottlenecks

---

File: ef204f17ee13850a-category-rankings-v6-evidence.md
Summary: Close the V6 HTML metric-panel evidence gap for rankings_by_category.
Related Files: report/bottlenecks/generate.py, tests/test_category_rankings_v3.py, bottlenecks/core.py
Related Symbols: render_report, _ranking_panels, CATEGORY_KEYS

---

File: 5ee31efd06e4aecf-typescript-snapshot-imports.md
Summary: Resolve TypeScript relative imports from captured snapshot paths when a snapshot is supplied.
Related Files: code_analyzer/cli.py, language_analyzers/typescript/analyzer.py, tests/test_typescript_analyzer.py
Related Symbols: TypeScriptAnalyzer._resolve_import
---
File: db77d50f78afc60d-route-client-call-edges.md
Summary: Add route string to client call edges.
Related Files: framework_analyzers/, language_analyzers/core/graph_models.py, analysis/graph_metrics.py
Related Symbols: GraphEdge, RelationKind, GraphAnalyzer
---
File: 93580783d647f789-event-signal-edges.md
Summary: Add event/signal publish-subscribe edges.
Related Files: framework_analyzers/, language_analyzers/core/graph_models.py, analysis/graph_metrics.py
Related Symbols: GraphEdge, RelationKind, GraphAnalyzer
---
File: 981eafd0004ac48b-orm-migration-edges.md
Summary: Add ORM model to migration edges.
Related Files: framework_analyzers/, language_analyzers/core/graph_models.py, analysis/graph_metrics.py
Related Symbols: GraphEdge, RelationKind, GraphAnalyzer
