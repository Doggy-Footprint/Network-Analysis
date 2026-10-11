# Review — spec 0c3bcfad9643613b v3

## Screenshot review (main, 2026-10-11)
Procedure: regenerate tag-manager report (`fastapi_visualizer.py ~/toy-projects/tag-manager -f android`), open in Chromium 1440x900 with CDN routed to tests/fixtures/vis-network-9.1.9, wait graphReady, capture top / 02 graph / modal (first representative card). Script: scratchpad shot.py (inputs: HTML, vis copy). pageerrors: [].
- review-top.png: KPI pills (파일 296, 연결 11,363, 후보 499 by kind, 분석 범위 284/6/0), 01 cards; no lead paragraphs. Pass.
- review-graph.png: tabs, toolbar, legend with layers ui/composable/data/room_dao/services/... and 후보 marker; graph rendered. Pass. Observation: dense core; candidate borders dominate colour (advisory, not a spec violation).
- review-modal.png: dialog over page, short label + path + layer/category badges, 6 metrics + 줄 수/토큰 수, candidate lines with key numbers, incoming/outgoing top lists with totals. Pass.

## Glossary review (A16)
Input: glossary.json. Checklist against A05: metric definitions = prior description + unit (15/15); 할인, 가중, 배분 몫, 가중 기여도, hop, layer, 대상 밖, 제외 match A05 meanings; status/category terms present. Pass.
