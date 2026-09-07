(function () {
  "use strict";
  window.ReportReady.then(function () {
    const ui = window.ReportUI, data = ui.data, model = window.ReportEvidenceModel, items = model.build(data), boundaries = model.boundaries(data);
    const search = document.getElementById("evidence-search"), list = document.getElementById("evidence-list"), count = document.getElementById("evidence-count"), detail = document.getElementById("evidence-detail");
    const render = function () { const result = model.search(items, search.value, 200); ui.clear(list); count.textContent = ui.format(result.total) + "개 일치 · 최대 200개 표시"; result.items.forEach(function (item) { const button = ui.make("button", null, "evidence-item"); button.type = "button"; button.appendChild(ui.make("span", item.type, "badge " + item.type)); const labels = ui.make("span"); labels.appendChild(ui.make("strong", item.title)); labels.appendChild(ui.make("small", item.subtitle)); button.appendChild(labels); button.addEventListener("click", async function () { if (item.type !== "query") { detail.textContent = JSON.stringify(item.value, null, 2); return; } detail.textContent = "압축 occurrence 근거를 여는 중…"; try { const occurrences = await model.loadQuery(item.value, data, window.ReportPayload.decodeOccurrenceBlock); detail.textContent = JSON.stringify({ query: item.value, occurrences: occurrences }, null, 2); } catch (error) { detail.textContent = error.name + ": " + error.message; } }); list.appendChild(button); }); if (!result.total) list.appendChild(ui.make("p", "일치하는 근거가 없습니다.", "muted")); };
    search.addEventListener("input", render); render();
    const fill = function (elementId, values, describe) { const container = document.getElementById(elementId); if (!values.length) { container.appendChild(ui.make("p", "없음", "muted")); return; } values.forEach(function (value) { container.appendChild(ui.make("div", describe(value))); }); };
    fill("excluded-files", boundaries.excludedFiles, function (value) { return value.file_path + " · " + value.reason; });
    fill("entry-documents", boundaries.entryDocuments, function (value) { return value.file_path + (value.injected ? " · 자동 주입" : " · 일반 진입 문서"); });
  });
}());
