File: base.html
Summary: 단일 오프라인 M1 보고서의 문서 골격과 asset 삽입 위치
Related Files: generate_html.py
Related Symbols: _build_document
---
File: header.html, header.js
Summary: 프로젝트와 profile 식별 정보를 표시하는 보고서 머리말
Related Files: generate_html.py
Related Symbols: ReportUI
---
File: summary.html, summary.js
Summary: graph 규모와 scan 결과의 핵심 집계
Related Files: generate_html.py, agent_view/models.py
Related Symbols: AgentViewGraph, ScanReport
---
File: summary_model.js
Summary: 요약과 분포를 계산하는 브라우저·테스트 공용 순수 모델
Related Files: summary.js, distributions.js, tests/test_generate_html.py
Related Symbols: createSummary, createDistributions
---
File: distributions.html, distributions.js
Summary: readable 및 query 종류와 token·결과 수 분포
Related Files: generate_html.py, agent_view/models.py
Related Symbols: ReadableNode, QueryNode
---
File: graph.html, graph.js
Summary: 전체 agent-view 관계를 탐색하는 Canvas 시각화
Related Files: generate_html.py, agent_view/models.py
Related Symbols: ReadableNode, QueryNode, FrameworkLink
---
File: graph_model.js
Summary: 관계 구성·배치와 Canvas 상호작용을 계산하는 순수 모델
Related Files: graph.js, tests/test_generate_html.py
Related Symbols: build, selectVisible, fit, pan, zoomAt, find, center, inspectAt
---
File: evidence.html, evidence.js
Summary: node·query·framework 근거와 분석 경계 검색 화면
Related Files: generate_html.py, agent_view/models.py
Related Symbols: Occurrence, FrameworkLink, ScanReport
---
File: evidence_model.js
Summary: 근거 항목 구성과 검색을 담당하는 순수 모델
Related Files: evidence.js, tests/test_generate_html.py
Related Symbols: build, search, boundaries
---
File: glossary.html
Summary: 비전문가를 위한 M1 핵심 용어 설명
Related Files: ROADMAP.md
Related Symbols: readable node, query node, framework link
---
File: common.css
Summary: 모든 보고서 컴포넌트가 공유하는 변경 가능한 시각 스타일
Related Files: generate_html.py
Related Symbols: none
