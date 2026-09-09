(function () {
  "use strict";
  window.ReportReady.then(function (data) {
    const make = function (tag, text, className) { const element = document.createElement(tag); if (text !== undefined) element.textContent = String(text); if (className) element.className = className; return element; };
    const strip = document.getElementById("result-strip");
    const add = function (key, value) { const row = make("div"); row.appendChild(make("dt", key)); row.appendChild(make("dd", value)); strip.appendChild(row); };
    const evaluation = data.schema === "harness_run_evaluation.v1";
    document.getElementById("report-title").textContent = evaluation ? data.case_id + " 실행 평가" : data.case_id + " 실행 비교";
    document.getElementById("report-lede").textContent = evaluation ? "관측 결합과 확인·결과 충족을 보존한 실행 부담입니다." : "확인과 결과 충족을 보존하는 조건에서 한 요인만 바꾼 부담 차이입니다.";
    add("schema", data.schema); add("case", data.case_id);
    if (evaluation) { add("run", data.run_id); add("binding", data.binding_status); add("eligible", data.eligible); }
    else { add("factor", data.factor); add("status", data.status); add("before → after", data.before_run_id + " → " + data.after_run_id); }
    window.ReportUI = { data: data, make: make, format: function (value) { return new Intl.NumberFormat("ko-KR").format(value); } };
  });
}());
