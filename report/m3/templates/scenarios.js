(function () {
  "use strict";
  window.ReportReady.then(function () {
    const ui = window.ReportUI;
    const make = ui.make, clear = ui.clear, format = ui.format;
    const report = ui.report;

    const versionsBody = document.getElementById("versions-table").querySelector("tbody");
    clear(versionsBody);
    report.versions.forEach(function (stamp) {
      const row = make("tr");
      row.appendChild(make("td", stamp.id));
      row.appendChild(make("td", stamp.version));
      versionsBody.appendChild(row);
    });

    const bar = function (entry) {
      const wrapper = make("div", undefined, "bar-row");
      wrapper.appendChild(make("span", entry.label, "bar-label"));
      const track = make("div", undefined, "bar-track");
      const fill = make("div", undefined, entry.label === "closure" ? "bar-fill closure" : "bar-fill");
      fill.style.width = (entry.share * 100).toFixed(2) + "%";
      track.appendChild(fill);
      wrapper.appendChild(track);
      const text = entry.bootstrap
        ? format(Math.round(entry.value)) + " (CI " + format(Math.round(entry.bootstrap.low)) + "–" + format(Math.round(entry.bootstrap.high)) + ")"
        : format(Math.round(entry.value));
      wrapper.appendChild(make("span", text, "bar-value"));
      return wrapper;
    };

    const axisTable = function (scenario) {
      const table = make("table", undefined, "data-table");
      const head = make("thead");
      const headRow = make("tr");
      ["axis", "p5", "p50", "p95", "mean", "stdev", "closure"].forEach(function (name) {
        headRow.appendChild(make("th", name));
      });
      head.appendChild(headRow);
      table.appendChild(head);
      const body = make("tbody");
      scenario.axes.forEach(function (entry) {
        const row = make("tr");
        row.appendChild(make("td", entry.axis));
        row.appendChild(make("td", format(entry.percentiles.p5)));
        row.appendChild(make("td", format(entry.percentiles.p50)));
        row.appendChild(make("td", format(entry.percentiles.p95)));
        row.appendChild(make("td", entry.mean.toFixed(2)));
        row.appendChild(make("td", entry.stdev.toFixed(2)));
        row.appendChild(make("td", format(entry.closure)));
        body.appendChild(row);
      });
      table.appendChild(body);
      return table;
    };

    const timelineList = function (scenario) {
      const wrapper = make("div", undefined, "timeline-group");
      scenario.timelines.forEach(function (entry) {
        const block = make("div", undefined, "timeline");
        block.appendChild(make("h4", entry.percentile + " discovery timeline"));
        const list = make("ol", undefined, "timeline-steps");
        entry.steps.forEach(function (step) {
          const item = make("li", undefined, "timeline-step " + step.action);
          const label = "turn " + step.turn + " · " + step.phase + " · " + step.action + " · " + step.id;
          item.appendChild(make("span", label, "timeline-label"));
          if (step.targetLabel) item.appendChild(make("span", "target: " + step.targetLabel, "timeline-target"));
          list.appendChild(item);
        });
        block.appendChild(list);
        wrapper.appendChild(block);
      });
      return wrapper;
    };

    const container = document.getElementById("scenario-list");
    clear(container);
    report.scenarios.forEach(function (scenario) {
      const card = make("article", undefined, "scenario-card");
      card.appendChild(make("h3", scenario.id));
      card.appendChild(make("p", scenario.task, "scenario-task"));

      const meta = make("dl", undefined, "profile-strip");
      [
        ["samples", format(scenario.sampleCount)],
        ["converged", scenario.converged === null ? "고정 표본 수" : String(scenario.converged)],
        ["seed", String(scenario.seed)],
        ["percentile", scenario.percentileMethod],
        ["reachability", scenario.reachability.status],
        ["seed queries", scenario.seedQueries.source]
      ].forEach(function (entry) {
        const item = make("div");
        item.appendChild(make("dt", entry[0]));
        item.appendChild(make("dd", entry[1]));
        meta.appendChild(item);
      });
      card.appendChild(meta);

      card.appendChild(make("h4", "weighted cost · closure 대비"));
      const bars = make("div", undefined, "bar-chart");
      scenario.weightedBars.forEach(function (entry) { bars.appendChild(bar(entry)); });
      card.appendChild(bars);

      card.appendChild(make("h4", "축별 분포"));
      card.appendChild(axisTable(scenario));

      card.appendChild(timelineList(scenario));

      const invariants = make("p", undefined, "invariants");
      const violations = scenario.invariants.violations.length;
      invariants.textContent =
        "invariants — weighted monotone: " + scenario.invariants.weighted_monotone +
        " · axis within closure: " + scenario.invariants.axis_within_closure +
        " · violations: " + violations;
      card.appendChild(invariants);

      if (scenario.reachability.unreached_targets.length) {
        card.appendChild(make("p", "unreached: " + scenario.reachability.unreached_targets.join(", "), "hint"));
      }
      container.appendChild(card);
    });
  });
}());
