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
    const summary = window.ReportSummaryModel.createSummary(data);
    document.getElementById("report-title").textContent = summary.projectName + " 탐색 구조";
    const strip = document.getElementById("profile-strip");
    [["schema", summary.schemaVersion], ["profile", summary.profile.id + " · v" + summary.profile.version], ["content hash", summary.profile.contentHash]].forEach(function (entry) {
      const wrapper = make("div");
      wrapper.appendChild(make("dt", entry[0]));
      wrapper.appendChild(make("dd", entry[1]));
      strip.appendChild(wrapper);
    });
  });
}());
