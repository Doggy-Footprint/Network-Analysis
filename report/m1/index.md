File: base.html
Summary: 결정적 gzip v3 graph를 시작 시 해제하고 occurrence 블록은 지연 해제하는 오프라인 문서 골격
Related Files: report/m1/generate.py
Related Symbols: _build_document
---
File: header.html, header.js
Summary: 프로젝트와 profile 식별 정보를 표시하는 보고서 머리말
Related Files: report/m1/generate.py
Related Symbols: ReportUI
---
File: summary.html, summary.js
Summary: graph 규모와 scan 결과의 핵심 집계
Related Files: report/m1/generate.py, agent_view/models.py
Related Symbols: AgentViewGraph, ScanReport
---
File: summary_model.js
Summary: 요약과 분포를 계산하는 브라우저·테스트 공용 순수 모델
Related Files: summary.js, distributions.js, tests/test_report_m1.py
Related Symbols: createSummary, createDistributions
---
File: distributions.html, distributions.js
Summary: readable 및 query 종류와 token·결과 수 분포
Related Files: report/m1/generate.py, agent_view/models.py
Related Symbols: ReadableNode, QueryNode
---
File: graph.html, graph.js
Summary: 전체 readable·query node와 일반·framework connection을 vendored Cytoscape.js+fcose로 탐색하는 디렉터리 compound 시각화
Related Files: report/m1/generate.py, report/m1/vendor/, agent_view/models.py
Related Symbols: ReadableNode, QueryNode, Connection
---
File: graph_model.js
Summary: Cytoscape element(디렉터리 compound 포함)와 짧은 라벨을 구성하고 "먼저 볼 곳" 후보를 계산하는 순수 모델
Related Files: graph.js, label_model.js, focus.js, tests/test_report_m1.py
Related Symbols: build, focus
---
File: label_model.js
Summary: report/shared/labels.py의 short_labels와 동일한 규칙을 브라우저·Node에서 계산하는 UMD 모델
Related Files: report/shared/labels.py, graph_model.js
Related Symbols: shortLabels
---
File: focus.html, focus.js
Summary: token_estimate, 생략된 query 결과 수, connection 수 상위 항목을 요약 앞에 보여주는 "먼저 볼 곳" 섹션
Related Files: graph_model.js, report/m1/generate.py
Related Symbols: focus
---
File: vendor_register.js
Summary: 인라인된 cytoscape-fcose를 cytoscape에 등록하는 연결 스크립트
Related Files: report/m1/vendor/
Related Symbols: none
---
File: evidence.html, evidence.js
Summary: node·query·connection 근거와 지연 occurrence 조회 및 분석 경계 검색 화면
Related Files: report/m1/generate.py, agent_view/models.py
Related Symbols: OccurrenceBlock, Connection, ScanReport
---
File: evidence_model.js
Summary: 근거 항목 구성·검색과 query occurrence 블록 지연 해제를 담당하는 순수 모델
Related Files: evidence.js, tests/test_report_m1.py
Related Symbols: build, search, boundaries, loadQuery
---
File: glossary.html
Summary: 비전문가를 위한 M1 핵심 용어 설명
Related Files: profiles/agent_view.v3.yaml
Related Symbols: readable node, query node, framework link
---
File: common.css
Summary: 모든 보고서 컴포넌트가 공유하는 변경 가능한 시각 스타일
Related Files: report/m1/generate.py
Related Symbols: none
