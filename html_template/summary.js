(function () {
  "use strict";
  const ui = window.ReportUI;
  const summary = window.ReportSummaryModel.createSummary(ui.data);
  const metrics = [
    ["readable nodes", summary.metrics.readableNodes, "읽을 수 있는 대상"],
    ["query nodes", summary.metrics.queryNodes, "검색 행동과 결과 묶음"],
    ["framework links", summary.metrics.frameworkLinks, "프레임워크 규칙 연결"],
    ["unreachable", summary.metrics.unreachable, "현재 근거로 도달 불가"],
    ["read tokens", summary.metrics.readTokens, "모든 읽기 비용 합계"],
    ["output tokens", summary.metrics.outputTokens, "모든 검색 출력 합계"]
  ];
  const container = document.getElementById("summary-metrics");
  metrics.forEach(function (metric) {
    const card = ui.make("article", null, "metric-card");
    card.appendChild(ui.make("span", metric[0], "metric-label"));
    card.appendChild(ui.make("strong", ui.format(metric[1]), "metric-value"));
    card.appendChild(ui.make("small", metric[2], "metric-note"));
    container.appendChild(card);
  });

  const scanItems = [
    ["파일 목록 근거", summary.scan.ignoreSource],
    ["scan 파일", ui.format(summary.scan.scannedFiles)],
    ["generated 파일", ui.format(summary.scan.generatedFiles)],
    ["generated node", ui.format(summary.scan.generatedNodes)],
    ["제외 파일", ui.format(summary.scan.excludedFiles)],
    ["unknown framework edge", ui.format(summary.scan.unknownFrameworkEdges)]
  ];
  const scanContainer = document.getElementById("scan-summary");
  scanItems.forEach(function (item) {
    const pair = ui.make("div");
    pair.appendChild(ui.make("span", item[0]));
    pair.appendChild(ui.make("strong", item[1]));
    scanContainer.appendChild(pair);
  });
})();
