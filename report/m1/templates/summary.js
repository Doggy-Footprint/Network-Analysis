(function () {
  "use strict";
  window.ReportReady.then(function () {
    const ui = window.ReportUI;
    const summary = window.ReportSummaryModel.createSummary(ui.data);
    const metrics = [["read units", summary.metrics.readUnits, "독립 읽기 단위"], ["readable nodes", summary.metrics.readableNodes, "읽을 수 있는 대상"], ["query nodes", summary.metrics.queryNodes, "검색 행동과 결과 묶음"], ["connections", summary.metrics.connections, "근거가 있는 관계"], ["read tokens", summary.metrics.readTokens, "읽기 비용 합계"], ["output tokens", summary.metrics.outputTokens, "검색 노출 비용 합계"]];
    const container = document.getElementById("summary-metrics");
    metrics.forEach(function (metric) { const card = ui.make("article", null, "metric-card"); card.appendChild(ui.make("span", metric[0], "metric-label")); card.appendChild(ui.make("strong", ui.format(metric[1]), "metric-value")); card.appendChild(ui.make("small", metric[2], "metric-note")); container.appendChild(card); });
    const scanItems = [["파일 목록 근거", summary.scan.ignoreSource], ["scan 파일", ui.format(summary.scan.scannedFiles)], ["제외 파일", ui.format(summary.scan.excludedFiles)], ["framework 관계", ui.format(summary.metrics.frameworkConnections)], ["snapshot digest", summary.scan.snapshotDigest], ["occurrence block", ui.format(ui.data.occurrence_store.length)]];
    const scanContainer = document.getElementById("scan-summary");
    scanItems.forEach(function (item) { const pair = ui.make("div"); pair.appendChild(ui.make("span", item[0])); pair.appendChild(ui.make("strong", item[1])); scanContainer.appendChild(pair); });
  });
}());
