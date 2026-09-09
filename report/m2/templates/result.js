(function () {
  "use strict";
  window.ReportReady.then(function () {
    const ui = window.ReportUI, data = ui.data, make = ui.make, format = ui.format;
    const row = function (body, values) { const tr = make("tr"); values.forEach(function (value) { tr.appendChild(make("td", value)); }); body.appendChild(tr); };
    if (data.schema === "harness_run_evaluation.v1") {
      document.getElementById("evaluation-panel").hidden = false;
      const grid = document.getElementById("burden-grid");
      Object.keys(data.burden).forEach(function (axis) { const card = make("article", undefined, "metric-card"); card.appendChild(make("span", axis, "metric-label")); card.appendChild(make("strong", format(data.burden[axis]), "metric-value")); grid.appendChild(card); });
      [["confirmations-table", data.confirmations], ["outcomes-table", data.outcomes]].forEach(function (entry) { const body = document.getElementById(entry[0]).querySelector("tbody"); entry[1].forEach(function (item) { row(body, [item.id, item.event_ids.join(", ") || "—", item.status]); }); });
      return;
    }
    document.getElementById("comparison-panel").hidden = false;
    document.getElementById("comparison-summary").textContent = "status: " + data.status + " · factor: " + data.factor;
    const body = document.getElementById("comparison-table").querySelector("tbody");
    Object.keys(data.burden_delta).forEach(function (axis) { const value = data.burden_delta[axis]; row(body, [axis, (value > 0 ? "+" : "") + format(value)]); });
  });
}());
