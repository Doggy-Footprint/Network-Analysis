(function () {
  "use strict";
  window.ReportReady.then(function () {
    const ui = window.ReportUI;
    const grid = document.getElementById("distribution-grid");
    window.ReportSummaryModel.createDistributions(ui.data).forEach(function (distribution) {
      const card = ui.make("article", null, "distribution-card"); card.appendChild(ui.make("h3", distribution[0]));
      const entries = Object.entries(distribution[1]).sort(function (left, right) { return right[1] - left[1] || left[0].localeCompare(right[0]); });
      const maximum = Math.max.apply(null, entries.map(function (entry) { return entry[1]; }).concat([1]));
      entries.forEach(function (entry) { const row = ui.make("div", null, "bar-row"); const track = ui.make("span", null, "bar-track"); const fill = ui.make("i", null, "bar-fill"); fill.style.width = String((entry[1] / maximum) * 100) + "%"; track.appendChild(fill); row.appendChild(ui.make("span", entry[0])); row.appendChild(track); row.appendChild(ui.make("strong", ui.format(entry[1]))); card.appendChild(row); });
      grid.appendChild(card);
    });
  });
}());
