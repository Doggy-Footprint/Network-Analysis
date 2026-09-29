(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ReportSummaryModel = api;
}(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  const countBy = function (items, key) { return items.reduce(function (result, item) { const value = key(item) || "(없음)"; result[value] = (result[value] || 0) + 1; return result; }, {}); };
  const bucket = function (value, ranges) { for (let index = 0; index < ranges.length; index += 1) if (value <= ranges[index][0]) return ranges[index][1]; };
  const createSummary = function (data) {
    const frameworkQueries = new Set(data.query_nodes.filter(function (query) { return query.kind === "framework"; }).map(function (query) { return query.id; }));
    const framework = data.connections.filter(function (connection) { return connection.kind === "framework" || frameworkQueries.has(connection.from_id) || frameworkQueries.has(connection.to_id); }).length;
    return { projectName: data.project_name || "Repository", schemaVersion: data.schema_version, profile: { id: data.profile.id, version: data.profile.version, contentHash: data.profile.content_hash }, metrics: { readUnits: data.read_units.length, readableNodes: data.readable_nodes.length, queryNodes: data.query_nodes.length, connections: data.connections.length, frameworkConnections: framework, readTokens: data.read_units.reduce(function (sum, unit) { return sum + unit.read_cost.token_estimate; }, 0), outputTokens: data.query_nodes.reduce(function (sum, query) { return sum + query.output_tokens; }, 0) }, scan: { ignoreSource: data.scan.ignore_source, scannedFiles: data.scan.scanned_file_count, excludedFiles: data.scan.excluded_files.length, snapshotDigest: data.scan.snapshot_digest } };
  };
  const createDistributions = function (data) {
    const tokens = [[0, "0"], [100, "1–100"], [500, "101–500"], [2000, "501–2,000"], [Infinity, "2,001+"]];
    const results = [[0, "0"], [1, "1"], [5, "2–5"], [20, "6–20"], [Infinity, "21+"]];
    return [["readable 종류", countBy(data.readable_nodes, function (node) { return node.kind; })], ["read-unit token", countBy(data.read_units, function (unit) { return bucket(unit.read_cost.token_estimate, tokens); })], ["query 종류", countBy(data.query_nodes, function (query) { return query.kind; })], ["query 전체 결과 수", countBy(data.query_nodes, function (query) { return bucket(query.total_count, results); })], ["query 노출 결과 수", countBy(data.query_nodes, function (query) { return bucket(query.visible_count, results); })], ["query output token", countBy(data.query_nodes, function (query) { return bucket(query.output_tokens, tokens); })], ["connection 종류", countBy(data.connections, function (connection) { return connection.kind; })], ["connection specificity", countBy(data.connections, function (connection) { return connection.specificity; })]];
  };
  return { createSummary: createSummary, createDistributions: createDistributions };
}));
