(function () {
  "use strict";
  window.ReportReady.then(function (data) {
    const make = function (tag, text, className) {
      const element = document.createElement(tag);
      if (text !== undefined && text !== null) element.textContent = String(text);
      if (className) element.className = className;
      return element;
    };
    const clear = function (element) { while (element.firstChild) element.removeChild(element.firstChild); };
    const format = function (value) { return new Intl.NumberFormat("ko-KR").format(value); };
    window.ReportUI = { data: data, make: make, clear: clear, format: format };
    const report = window.ReportCostModel.build(data);
    window.ReportUI.report = report;
    document.getElementById("report-title").textContent = report.projectName + " 대상 발견 비용";
    const strip = document.getElementById("profile-strip");
    [
      ["policy", report.profiles.exploration_policy.id + " · v" + report.profiles.exploration_policy.version],
      ["weights", report.profiles.cost_weights.id + " · v" + report.profiles.cost_weights.version],
      ["snapshot", report.snapshotDigest]
    ].forEach(function (entry) {
      const wrapper = make("div");
      wrapper.appendChild(make("dt", entry[0]));
      wrapper.appendChild(make("dd", entry[1]));
      strip.appendChild(wrapper);
    });
  });
}());
