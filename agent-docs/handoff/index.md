---
File: 0c3bcfad9643613b-report-graph-modal-redesign.md
Summary: 보고서 그래프·modal·용어 tooltip 개편, verifier 한도 도달(E07 미해결)
Related Files: report/unified.py, renderers/html/static/app.js, renderers/html/templates/dashboard.html, tests/test_report_modal.py
Related Symbols: file_layers, openModal, contribution
---
File: b6db876d7191e86d-gradle-module-package-scheme.md
Summary: Phase 1에서 제외한 Android Gradle module(및 npm workspace)을 framework package 체계에 추가하는 후속 작업
Related Files: language_analyzers/core/enrichment.py, analysis/structure.py, agent-docs/adr/58424b9754efe9a2-package-grouping-schemes.md
Related Symbols: package_metrics, enrich_repository
---
File: fa00b92fe9819b57-agent-context-candidates.md
Summary: AI agent 친화 코드 조사에서 도출한 후보 C(시그니처 기준 맥락 비용)와 D(문서→코드 참조, dangling 참조)를 인계
Related Files: analysis/graph_metrics.py, language_analyzers/core/cost.py, repository/scan.py, repository/policy.py, language_analyzers/core/graph_models.py
Related Symbols: hop_2_token_cost, GraphNode.signature, RelationKind
---
File: dad85e4830f21190-existing-signal-defects.md
Summary: 기존 후보 신호 결함 F1–F12 수정 인계; 3회차까지 구현 완료, V12 review evidence(review_diff 귀속 규칙) 정정만 남음(verifier limit)
Related Files: tests/signal_defects_evidence/review_diff.py, language_analyzers/typescript/analyzer.py, language_analyzers/kotlin/analyzer.py, language_analyzers/python/graph.py, bottlenecks/core.py, analysis/graph_metrics.py, analysis/file_graph.py
Related Symbols: unresolved_boundary, evidence_spread, large_node, ambiguous_name, pagerank
