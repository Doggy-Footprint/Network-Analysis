(function () {
  "use strict";
  const ui = window.ReportUI;
  const data = ui.data;
  const model = window.ReportEvidenceModel;
  const items = model.build(data);
  const boundaries = model.boundaries(data);

  const search = document.getElementById("evidence-search");
  const list = document.getElementById("evidence-list");
  const count = document.getElementById("evidence-count");
  const detail = document.getElementById("evidence-detail");
  const render = function () {
    const result = model.search(items, search.value, 200);
    ui.clear(list);
    count.textContent = ui.format(result.total) + "개 일치 · 최대 200개 표시";
    result.items.forEach(function (item) {
      const button = ui.make("button", null, "evidence-item");
      button.type = "button";
      button.appendChild(ui.make("span", item.type, "badge " + item.type));
      const labels = ui.make("span");
      labels.appendChild(ui.make("strong", item.title));
      labels.appendChild(ui.make("small", item.subtitle));
      button.appendChild(labels);
      button.addEventListener("click", function () {
        detail.textContent = JSON.stringify(item.value, null, 2);
      });
      list.appendChild(button);
    });
    if (!result.total) list.appendChild(ui.make("p", "일치하는 근거가 없습니다.", "muted"));
  };
  search.addEventListener("input", render);
  render();

  const fillBoundary = function (elementId, values, describe) {
    const container = document.getElementById(elementId);
    if (!values.length) {
      container.appendChild(ui.make("p", "없음", "muted"));
      return;
    }
    values.forEach(function (value) {
      container.appendChild(ui.make("div", describe(value)));
    });
  };
  fillBoundary("excluded-files", boundaries.excludedFiles, function (value) {
    return value.file_path + " · " + value.reason;
  });
  fillBoundary("unknown-edges", boundaries.unknownFrameworkEdges, function (value) { return value; });
})();
