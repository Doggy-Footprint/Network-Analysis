(function () {
  "use strict";
  const ui = window.ReportUI;
  const distributions = window.ReportSummaryModel.createDistributions(ui.data);

  const grid = document.getElementById("distribution-grid");
  distributions.forEach(function (distribution) {
    const card = ui.make("article", null, "distribution-card");
    card.appendChild(ui.make("h3", distribution[0]));
    const entries = Object.entries(distribution[1]).sort(function (left, right) {
      return right[1] - left[1] || left[0].localeCompare(right[0]);
    });
    const maximum = Math.max.apply(null, entries.map(function (entry) { return entry[1]; }).concat([1]));
    if (!entries.length) card.appendChild(ui.make("p", "데이터 없음", "muted"));
    entries.forEach(function (entry) {
      const row = ui.make("div", null, "bar-row");
      const label = ui.make("span", entry[0]);
      const track = ui.make("span", null, "bar-track");
      const fill = ui.make("i", null, "bar-fill");
      fill.style.width = String((entry[1] / maximum) * 100) + "%";
      track.appendChild(fill);
      row.appendChild(label);
      row.appendChild(track);
      row.appendChild(ui.make("strong", ui.format(entry[1])));
      card.appendChild(row);
    });
    grid.appendChild(card);
  });
})();
