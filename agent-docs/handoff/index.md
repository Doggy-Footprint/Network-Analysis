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
File: e16d433ef30afd87-oss-report-refactoring-eval.md
Summary: OSS 7개 저장소에서 리포트 유무(sonnet-medium, 단일 에이전트, headless 격리 병렬 run)에 따른 리팩토링 개선 비교 실험 인계 — 리포트 경량화·다른 handoff 선행, `./eval` 전부 폐기(환경·기준선 재구축 필요), run 격리 스크립트 초안
Related Files: scripts/eval/prepare_runs.py, scripts/eval/run_hook.py, scripts/eval/TASK_PROMPT.md, scripts/eval/measure.py, scripts/eval/compare.py, scripts/eval/gate.py, scripts/eval/judge.py, scripts/eval/verify.sh, scripts/eval/collect_agents.py, scripts/eval/repos.json, language_analyzers/typescript/analyzer.py
Related Symbols: measure.main, gate.main, judge.main, kotlin_imports, typescript_imports, agreement
