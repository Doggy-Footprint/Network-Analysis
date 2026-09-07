File: generate.py
Summary: phase_b_cost.v1 JSON만 입력받아 단일 오프라인 HTML 보고서를 만드는 M3 생성기와 스키마 검증
Related Files: report/shared/document.py, discovery/report.py, tests/test_report_m3.py
Related Symbols: generate_report, _validate_payload, _scenario, _percentile
---
File: templates/header.html, templates/header.js
Summary: 프로젝트와 policy·weights profile 식별 정보를 표시하는 보고서 머리말
Related Files: report/m3/generate.py
Related Symbols: ReportUI, ReportCostModel
---
File: templates/cost_model.js
Summary: 타임라인·축 분포·closure 대비 막대를 계산하는 브라우저·테스트 공용 순수 모델
Related Files: report/m3/templates/scenarios.js, tests/test_report_m3.py
Related Symbols: build, axisDistribution, weightedBars, timeline
---
File: templates/scenarios.html, templates/scenarios.js
Summary: 시나리오별 p5·p50·p95 타임라인, 축별 평균·표준편차, p95 옆 closure 막대, 불변식과 flat versions 표
Related Files: report/m3/templates/cost_model.js
Related Symbols: ReportCostModel
---
File: templates/glossary.html
Summary: exploration turn·weighted cost·closure cost·discovery turn index 용어 안내
Related Files: ROADMAP.md
Related Symbols: 
