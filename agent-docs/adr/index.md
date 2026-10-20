---
File: 31d2dee6912427d5-consolidate-overlapping-metrics.md
Summary: 순위 정보가 겹치는 노드 지표(HITS, degree_centrality, hop_3, hop_2/3 node_count)를 제거해 16개 지표를 10개로 통합
Related Files: analysis/graph_metrics.py, bottlenecks/core.py, report/bottlenecks/generate.py, renderers/html/static/app.js
Related Symbols: GraphAnalyzer, RANKING_KEYS, METRIC_DEFINITIONS
---
File: 58424b9754efe9a2-package-grouping-schemes.md
Summary: package 단위를 language 체계(Python/Kotlin package, 그 외 디렉터리)와 framework 체계(NestJS @Module)로 따로 계산하고 우선순위 병합은 기각
Related Files: analysis/structure.py, bottlenecks/core.py, language_analyzers/kotlin/analyzer.py, language_analyzers/python/graph.py, framework_analyzers/nestjs/analyzer.py
Related Symbols: package_metrics, package_cycle, unstable_dependency
---
File: 07e12b7114048d41-json-baseline-ratchet.md
Summary: 구조 회귀 비교(--baseline, --fail-on-new)는 이전 bottleneck JSON을 baseline으로 쓰고 git ref checkout 방식은 기각
Related Files: bottlenecks/delta.py, code_analyzer/cli.py, analysis/structure.py, bottlenecks/core.py
Related Symbols: load_baseline, compute_delta, regressions, package_dependencies, rules_digest
---
File: b8a976686050faf6-evidence-spread-by-directory.md
Summary: evidence_spread는 대상 디렉터리 밖 디렉터리 2개 이상(또는 단일 파일 줄 범위 초과)으로 발동하고, 파일 수 임계 노출과 file 모드 제거는 기각
Related Files: bottlenecks/core.py, report/bottlenecks/generate.py, renderers/html/static/app.js
Related Symbols: _candidates, _file_candidates, evidence_spread, directory_count
