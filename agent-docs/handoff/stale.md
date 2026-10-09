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
---
File: fdec87dc8ce208aa-additional-framework-analyzers.md
Summary: Add analyzers for additional frameworks.
Related Files: framework_analyzers/, language_analyzers/core/graph_models.py, analysis/graph_metrics.py
Related Symbols: GraphEdge, RelationKind, GraphAnalyzer
---
File: ed8784db945e193f-identifier-ambiguity-metric.md
Summary: Add identifier occurrence ambiguity as a node attribute.
Related Files: framework_analyzers/, language_analyzers/core/graph_models.py, analysis/graph_metrics.py
Related Symbols: GraphEdge, RelationKind, GraphAnalyzer
---
File: 8c21d77542561b51-drop-traceability-constraint.md
Summary: Remove snapshot digest, profile hash, and digest-consistency mechanisms that existed only for the dropped result-traceability constraint.
Related Files: repository/scan.py, repository/policy.py, analysis/edge_weights.py, bottlenecks/core.py, language_analyzers/python/graph.py, README.md
Related Symbols: build_snapshot, RepositorySnapshot.digest, ScanPolicy.content_hash, EdgeWeights.content_hash, analyze_bottlenecks, _validate

---

File: df8e06a5dda281c8-file-granularity-project-refactor.md
Summary: 파일 기본·심볼 선택 분석 전환의 프로젝트 전반 변경 계획, 호환성 경계, 성능 근거와 미확정 세부 정책을 인계한다.
Related Files: code_analyzer/cli.py, repository/models.py, language_analyzers/core/serialization.py, language_analyzers/core/enrichment.py, language_analyzers/kotlin/analyzer.py, framework_analyzers/fastapi/graph.py, framework_analyzers/android/graph.py, framework_analyzers/sqlalchemy/graph.py, framework_analyzers/nestjs/graph.py, analysis/graph_metrics.py, bottlenecks/core.py, report/bottlenecks/generate.py, report/unified.py, renderers/html/static/app.js, README.md
Related Symbols: RepositorySnapshot.content_map, GraphAnalyzer.analyze, analyze_bottlenecks, architecture_to_dict, render_unified_report, _run_analyzer, _run_merged, _add_symbol_edges

---

File: 0fc789ad2164e35b-file-analysis-paused.md
Summary: 73.879초 중앙값·원본 관계 등가를 확보했고 사용자가 승인한 file-only single-pass 및 symbol 기존값 보존 v2의 구현·전체 검증을 진행한다.
Related Files: agent-docs/specs/0fc789ad2164e35b-file-analysis-symbol-details.md, agent-docs/specs/0fc789ad2164e35b-frontend-staging.json, scripts/benchmark_file_analysis.py, tests/file_analysis_evidence/coverage.json, tests/file_analysis_evidence/baseline-timing.json
Related Symbols: to_file_architecture, analyze_bottlenecks, architecture_to_dict, RepositorySnapshot.content_map

---
File: fce458d3be4db333-analysis-coverage-reporting.md
Summary: 분석하지 못한 부분을 결과에 함께 보여주기; 현재 한계와 재개 시 결정할 정책·검증 항목.
Related Files: repository/scan.py, repository/models.py, language_analyzers/python/source.py, language_analyzers/python/graph.py, code_analyzer/cli.py, bottlenecks/core.py, report/unified.py, renderers/html/static/app.js
Related Symbols: build_snapshot, RepositorySnapshot, PythonSourceAnalyzer, analyze_bottlenecks

---

File: e6f962102cb7de1a-ambiguous-route-candidates.md
Summary: 구현/전체1258개+하위200개 통과; 독립 감사2/2 후 심볼 UI 기여도 증거 V3-F5가 남아 추가 감사 승인 필요.
Related Files: framework_analyzers/route_matching.py, language_analyzers/core/graph_models.py, analysis/file_graph.py, analysis/graph_metrics.py, analysis/edge_weights.py, renderers/html/static/app.js, tests/test_route_client_call_edges.py
Related Symbols: match_routes, GraphEdge, to_file_architecture, GraphAnalyzer.analyze
