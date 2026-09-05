(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ReportSummaryModel = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  const countBy = function (items, key) {
    return items.reduce(function (result, item) {
      const value = key(item) || "(없음)";
      result[value] = (result[value] || 0) + 1;
      return result;
    }, {});
  };
  const bucket = function (value, ranges) {
    for (let index = 0; index < ranges.length; index += 1) {
      if (value <= ranges[index][0]) return ranges[index][1];
    }
    return ranges[ranges.length - 1][1];
  };
  const createSummary = function (data) {
    const scan = data.scan;
    return {
      projectName: data.project_name,
      schemaVersion: data.schema_version,
      profile: { id: data.profile.id, version: data.profile.version, contentHash: data.profile.content_hash },
      metrics: {
        readableNodes: data.readable_nodes.length,
        queryNodes: data.query_nodes.length,
        frameworkLinks: data.framework_links.length,
        unreachable: data.unreachable_node_ids.length,
        readTokens: data.readable_nodes.reduce(function (sum, node) { return sum + node.read_cost.token_estimate; }, 0),
        outputTokens: data.query_nodes.reduce(function (sum, query) { return sum + query.output_tokens; }, 0)
      },
      scan: {
        ignoreSource: scan.ignore_source,
        scannedFiles: scan.scanned_file_count,
        generatedFiles: scan.generated_file_count,
        generatedNodes: scan.generated_node_count,
        excludedFiles: scan.excluded_files.length,
        unknownFrameworkEdges: scan.unknown_framework_edges.length
      }
    };
  };
  const createDistributions = function (data) {
    const tokens = [[0, "0"], [100, "1–100"], [500, "101–500"], [2000, "501–2,000"], [Infinity, "2,001+"]];
    const results = [[0, "0"], [1, "1"], [5, "2–5"], [20, "6–20"], [Infinity, "21+"]];
    return [
      ["readable 종류", countBy(data.readable_nodes, function (node) { return node.kind; })],
      ["read token", countBy(data.readable_nodes, function (node) { return bucket(node.read_cost.token_estimate, tokens); })],
      ["query 종류", countBy(data.query_nodes, function (query) { return query.kind; })],
      ["query 결과 수", countBy(data.query_nodes, function (query) { return bucket(query.occurrences.length, results); })],
      ["query output token", countBy(data.query_nodes, function (query) { return bucket(query.output_tokens, tokens); })]
    ];
  };
  return { createSummary: createSummary, createDistributions: createDistributions };
});
