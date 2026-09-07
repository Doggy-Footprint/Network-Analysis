(function () {
  "use strict";
  const AXES = [
    "exploration_turns", "search_tool_calls", "read_tool_calls",
    "query_result_tokens", "readable_node_tokens", "zero_result_queries",
    "revisits", "exposed_non_target_candidates", "duplicate_occurrences"
  ];
  const PERCENTILES = ["p5", "p50", "p95"];

  const timeline = function (scenario, name) {
    const percentile = scenario.percentiles[name];
    const unitOf = {};
    scenario.targets.forEach(function (target) { unitOf[target.read_unit_id] = target; });
    return percentile.execution_sequence.map(function (step) {
      const target = step.action === "read" ? unitOf[step.id] : undefined;
      return {
        step: step.step,
        phase: step.phase,
        action: step.action,
        id: step.id,
        turn: step.turn,
        costDelta: step.cost_delta,
        targetLabel: target ? target.file_path + "#" + target.label : null
      };
    });
  };

  const axisDistribution = function (scenario) {
    return AXES.map(function (axis) {
      const statistics = scenario.axis_statistics[axis];
      const closure = scenario.closure.axes[axis];
      const values = {};
      PERCENTILES.forEach(function (name) { values[name] = scenario.percentiles[name].axes[axis]; });
      return {
        axis: axis,
        mean: statistics.mean,
        stdev: statistics.stdev,
        percentiles: values,
        closure: closure,
        // The closure is the structural upper bound for every axis, so a share above 1 would
        // mean the axis<=closure invariant was violated rather than that the axis is expensive.
        closureShare: closure > 0 ? values.p95 / closure : 0
      };
    });
  };

  const weightedBars = function (scenario) {
    const closure = scenario.closure.weighted_cost;
    const largest = Math.max(closure, scenario.percentiles.p95.weighted_cost, 1);
    const bars = PERCENTILES.map(function (name) {
      return {
        label: name,
        value: scenario.percentiles[name].weighted_cost,
        share: scenario.percentiles[name].weighted_cost / largest,
        bootstrap: scenario.percentiles[name].bootstrap_ci
      };
    });
    bars.push({ label: "closure", value: closure, share: closure / largest, bootstrap: null });
    return bars;
  };

  const build = function (data) {
    return {
      projectName: data.project_name,
      snapshotDigest: data.snapshot_digest,
      profiles: data.profiles,
      seedQueryGenerator: data.seed_query_generator,
      versions: data.versions,
      scenarios: data.scenarios.map(function (scenario) {
        return {
          id: scenario.id,
          task: scenario.task,
          targets: scenario.targets,
          seedQueries: scenario.seed_queries,
          phaseA: scenario.phase_a,
          sampleCount: scenario.sample_count,
          converged: scenario.converged,
          seed: scenario.seed,
          percentileMethod: scenario.percentile_method,
          weightedBars: weightedBars(scenario),
          axes: axisDistribution(scenario),
          timelines: PERCENTILES.map(function (name) {
            return { percentile: name, steps: timeline(scenario, name) };
          }),
          observations: PERCENTILES.map(function (name) {
            return { percentile: name, value: scenario.percentiles[name].observations };
          }),
          invariants: scenario.invariants,
          reachability: scenario.reachability,
          closure: scenario.closure
        };
      })
    };
  };

  const api = { AXES: AXES, PERCENTILES: PERCENTILES, build: build };
  if (typeof module === "object" && module.exports) module.exports = api;
  if (typeof window === "object") window.ReportCostModel = api;
}());
