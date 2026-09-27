(function (root, factory) {
  "use strict";
  const labels = (typeof module === "object" && module.exports) ? require("./label_model.js") : root.ReportLabels;
  const api = factory(labels);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ReportGraphModel = api;
}(typeof globalThis === "object" ? globalThis : this, function (ReportLabels) {
  "use strict";
  const DEFAULT_LIMIT = 300;
  const compare = function (left, right) { return left < right ? -1 : left > right ? 1 : 0; };

  const directoryChain = function (filePath) {
    const parts = filePath.split("/");
    parts.pop();
    return parts;
  };

  const hasSymbolLabel = function (node) { return Boolean(node.label) && node.label !== node.file_path; };
  const readableLabel = function (node, shortLabelByPath) {
    const fileLabel = shortLabelByPath[node.file_path] || node.file_path;
    return hasSymbolLabel(node) ? fileLabel + ":" + node.label : fileLabel;
  };
  const readableFullLabel = function (node) {
    return hasSymbolLabel(node) ? node.file_path + ":" + node.label : node.file_path;
  };

  const groupBy = function (items, keyOf) {
    const groups = {};
    items.forEach(function (item) {
      const key = keyOf(item);
      if (!groups[key]) groups[key] = [];
      groups[key].push(item);
    });
    return groups;
  };

  const build = function (data, options) {
    const opts = options || {};
    const limit = opts.limit || DEFAULT_LIMIT;
    const filePaths = data.readable_nodes.map(function (node) { return node.file_path; });
    const shortLabelByPath = ReportLabels.shortLabels(filePaths);

    const connectionCount = {};
    data.connections.forEach(function (connection) {
      connectionCount[connection.from_id] = (connectionCount[connection.from_id] || 0) + 1;
      connectionCount[connection.to_id] = (connectionCount[connection.to_id] || 0) + 1;
    });

    const nodes = [];
    data.readable_nodes.forEach(function (node) {
      const label = readableLabel(node, shortLabelByPath);
      const fullLabel = readableFullLabel(node);
      const weight = (node.read_cost ? node.read_cost.token_estimate : 0) + (connectionCount[node.id] || 0);
      nodes.push({ id: node.id, label: label, full_label: fullLabel, type: "readable", weight: weight, value: node });
    });
    data.query_nodes.forEach(function (query) {
      const label = query.term || query.id;
      const weight = (query.total_count || 0) + (connectionCount[query.id] || 0);
      nodes.push({ id: query.id, label: label, full_label: query.term || query.id, type: "query", weight: weight, value: query });
    });

    const ranked = nodes.slice().sort(function (a, b) { return (b.weight - a.weight) || compare(a.id, b.id); });
    const defaultVisible = {};
    ranked.slice(0, limit).forEach(function (node) { defaultVisible[node.id] = true; });
    const capped = nodes.length > limit;
    nodes.forEach(function (node) { node.default_visible = !capped || Boolean(defaultVisible[node.id]); });
    const alwaysLabelIds = {};
    ranked.slice(0, 20).forEach(function (node) { alwaysLabelIds[node.id] = true; });
    nodes.forEach(function (node) { node.always_label = Boolean(alwaysLabelIds[node.id]); });

    const nodeIds = {};
    nodes.forEach(function (node) { nodeIds[node.id] = true; });

    const elements = [];
    const directoryIds = {};
    const ensureDirectory = function (filePath) {
      const parts = directoryChain(filePath);
      let prefix = "";
      let parentId = null;
      parts.forEach(function (part) {
        prefix = prefix ? prefix + "/" + part : part;
        const directoryId = "dir:" + prefix;
        if (!directoryIds[directoryId]) {
          directoryIds[directoryId] = true;
          const directoryData = { id: directoryId, label: part, full_label: prefix, is_directory: true };
          if (parentId) directoryData.parent = parentId;
          elements.push({ group: "nodes", data: directoryData, classes: "directory" });
        }
        parentId = directoryId;
      });
      return parentId;
    };

    data.readable_nodes.forEach(function (node) {
      const model = nodes.find(function (candidate) { return candidate.id === node.id; });
      const parent = ensureDirectory(node.file_path);
      const size = Math.max(10, Math.min(70, Math.sqrt(Math.max(1, node.read_cost.token_estimate)) * 2.5));
      const nodeData = { id: node.id, label: model.label, full_label: model.full_label, size: size, default_visible: model.default_visible, always_label: model.always_label };
      if (parent) nodeData.parent = parent;
      elements.push({ group: "nodes", data: nodeData, classes: "readable" + (model.default_visible ? "" : " capped") });
    });
    data.query_nodes.forEach(function (query) {
      const model = nodes.find(function (candidate) { return candidate.id === query.id; });
      const size = Math.max(10, Math.min(50, Math.sqrt(Math.max(1, query.total_count + 1)) * 4));
      elements.push({ group: "nodes", data: { id: query.id, label: model.label, full_label: model.full_label, size: size, default_visible: model.default_visible, always_label: model.always_label }, classes: "query" + (model.default_visible ? "" : " capped") });
    });

    data.connections.forEach(function (connection) {
      if (!nodeIds[connection.from_id] || !nodeIds[connection.to_id]) return;
      elements.push({
        group: "edges",
        data: {
          id: "edge:" + connection.id,
          source: connection.from_id,
          target: connection.to_id,
          kind: connection.kind,
          specificity: connection.specificity,
          value: connection
        },
        classes: connection.kind === "framework" ? "framework" : "regular"
      });
    });

    return { nodes: nodes, elements: elements, capped: capped, limit: limit, total: nodes.length };
  };

  const topByValue = function (items, valueOf, reason, labelOf, count) {
    return items
      .slice()
      .sort(function (a, b) { return (valueOf(b) - valueOf(a)) || compare(a.id, b.id); })
      .slice(0, count)
      .map(function (item) { return { id: item.id, label: labelOf(item), reason: reason, value: valueOf(item) }; });
  };

  const focus = function (data, n) {
    const count = n || 5;
    const filePaths = data.readable_nodes.map(function (node) { return node.file_path; });
    const shortLabelByPath = ReportLabels.shortLabels(filePaths);
    const connectionCount = {};
    data.connections.forEach(function (connection) {
      connectionCount[connection.from_id] = (connectionCount[connection.from_id] || 0) + 1;
      connectionCount[connection.to_id] = (connectionCount[connection.to_id] || 0) + 1;
    });

    const readUnitGroups = groupBy(data.readable_nodes, function (node) { return node.read_unit_id; });
    const tokenRepresentatives = Object.keys(readUnitGroups).map(function (key) {
      const group = readUnitGroups[key].slice().sort(function (a, b) { return compare(a.id, b.id); });
      return { node: group[0], duplicate_count: group.length };
    });
    const tokenTop = tokenRepresentatives
      .slice()
      .sort(function (a, b) { return (b.node.read_cost.token_estimate - a.node.read_cost.token_estimate) || compare(a.node.id, b.node.id); })
      .slice(0, count)
      .map(function (entry) {
        return {
          id: entry.node.id,
          label: readableLabel(entry.node, shortLabelByPath),
          reason: "read-unit token 상위",
          value: entry.node.read_cost.token_estimate,
          duplicate_count: entry.duplicate_count
        };
      });

    const truncated = data.query_nodes.filter(function (query) { return query.truncated; });
    const termGroups = groupBy(truncated, function (query) { return query.term; });
    const omittedValue = function (query) { return query.total_count - query.visible_count; };
    const omittedRepresentatives = Object.keys(termGroups).map(function (key) {
      const group = termGroups[key].slice().sort(function (a, b) { return (omittedValue(b) - omittedValue(a)) || compare(a.id, b.id); });
      return { node: group[0], duplicate_count: group.length };
    });
    const omittedTop = omittedRepresentatives
      .slice()
      .sort(function (a, b) { return (omittedValue(b.node) - omittedValue(a.node)) || compare(a.node.id, b.node.id); })
      .slice(0, count)
      .map(function (entry) {
        return {
          id: entry.node.id,
          label: entry.node.term || entry.node.id,
          reason: "생략된 query 결과 수 상위",
          value: omittedValue(entry.node),
          duplicate_count: entry.duplicate_count
        };
      });

    const allNodes = data.readable_nodes.map(function (node) {
      return { id: node.id, label: readableLabel(node, shortLabelByPath) };
    }).concat(data.query_nodes.map(function (query) {
      return { id: query.id, label: query.term || query.id };
    }));
    const connectionTop = topByValue(
      allNodes,
      function (node) { return connectionCount[node.id] || 0; },
      "연결 수 상위",
      function (node) { return node.label; },
      count
    ).map(function (item) { item.duplicate_count = 1; return item; });

    return tokenTop.concat(omittedTop).concat(connectionTop);
  };

  return { build: build, focus: focus };
}));
