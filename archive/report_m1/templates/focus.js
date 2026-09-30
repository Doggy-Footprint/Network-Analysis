(function () {
  "use strict";
  window.ReportReady.then(function (data) {
    const ui = window.ReportUI;
    const grid = document.getElementById("focus-grid");
    const items = window.ReportGraphModel.focus(data, 5);
    const groups = {};
    const order = [];
    items.forEach(function (item) {
      if (!groups[item.reason]) { groups[item.reason] = []; order.push(item.reason); }
      groups[item.reason].push(item);
    });
    if (!order.length) {
      grid.appendChild(ui.make("p", "표시할 항목이 없습니다.", "muted"));
      return;
    }
    order.forEach(function (reason) {
      const card = ui.make("article", null, "focus-card");
      card.appendChild(ui.make("h3", reason));
      const list = ui.make("ol");
      groups[reason].forEach(function (item) {
        const row = ui.make("li");
        const button = ui.make("button", item.label, "focus-link");
        button.type = "button";
        button.addEventListener("click", function () { window.dispatchEvent(new CustomEvent("focus-node-request", { detail: item.id })); });
        row.appendChild(button);
        row.appendChild(ui.make("span", ui.format(item.value), "focus-value"));
        if (item.duplicate_count > 1) row.appendChild(ui.make("span", "같은 항목 " + ui.format(item.duplicate_count) + "건", "muted"));
        list.appendChild(row);
      });
      card.appendChild(list);
      grid.appendChild(card);
    });
  });
}());
