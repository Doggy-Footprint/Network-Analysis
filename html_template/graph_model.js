(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ReportGraphModel = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  const compare = function (left, right) { return left < right ? -1 : left > right ? 1 : 0; };
  const build = function (data) {
    const nodes = [];
    const byKey = {};
    const addNode = function (type, value) {
      const key = type.charAt(0) + ":" + value.id;
      const searchable = type === "readable"
        ? [value.id, value.label, value.file_path, value.kind].join(" ")
        : [value.id, value.term, value.kind, value.rule_id || ""].join(" ");
      const node = { key: key, type: type, value: value, label: type === "readable" ? value.label : value.term, searchable: searchable.toLocaleLowerCase(), x: 0, y: 0 };
      nodes.push(node);
      byKey[key] = node;
    };
    data.readable_nodes.slice().sort(function (a, b) { return compare(a.id, b.id); }).forEach(function (node) { addNode("readable", node); });
    data.query_nodes.slice().sort(function (a, b) { return compare(a.id, b.id); }).forEach(function (node) { addNode("query", node); });
    const readable = nodes.filter(function (node) { return node.type === "readable"; });
    const queries = nodes.filter(function (node) { return node.type === "query"; });
    const place = function (items, startX, columns) {
      items.forEach(function (node, index) {
        node.x = startX + (index % columns) * 150;
        node.y = 80 + Math.floor(index / columns) * 70;
      });
    };
    const readableColumns = Math.max(1, Math.ceil(Math.sqrt(Math.max(1, readable.length) * 1.5)));
    const queryColumns = Math.max(1, Math.ceil(Math.sqrt(Math.max(1, queries.length) * 1.5)));
    place(readable, 80, readableColumns);
    place(queries, 180 + readableColumns * 150, queryColumns);
    const edges = [];
    const addEdge = function (from, to, type, value, label) {
      if (byKey[from] && byKey[to]) edges.push({ from: from, to: to, type: type, value: value, label: label });
    };
    data.query_nodes.forEach(function (query) {
      query.origin_node_ids.forEach(function (origin) { addEdge("r:" + origin, "q:" + query.id, "regular", query, "origin→query"); });
      query.arrival_node_ids.forEach(function (arrival) { addEdge("q:" + query.id, "r:" + arrival, "regular", query, "query→arrival"); });
    });
    data.framework_links.forEach(function (link) {
      if (link.query_id) {
        addEdge("r:" + link.from_node_id, "q:" + link.query_id, "framework", link, link.rule_id);
        link.to_node_ids.forEach(function (target) { addEdge("q:" + link.query_id, "r:" + target, "framework", link, link.rule_id); });
      } else {
        link.to_node_ids.forEach(function (target) { addEdge("r:" + link.from_node_id, "r:" + target, "framework", link, link.rule_id); });
      }
    });
    return { nodes: nodes, byKey: byKey, edges: edges };
  };
  const visibleNode = function (node, filters) {
    if (node.type === "readable") return filters.readable;
    return filters.query && (filters.queryKind === "all" || node.value.kind === filters.queryKind);
  };
  const screen = function (node, view) {
    return { x: node.x * view.scale + view.x, y: node.y * view.scale + view.y };
  };
  const inViewport = function (point, width, height, margin) {
    return point.x >= -margin && point.y >= -margin && point.x <= width + margin && point.y <= height + margin;
  };
  const selectVisible = function (model, filters, view, width, height) {
    const nodes = model.nodes.filter(function (node) {
      return visibleNode(node, filters) && inViewport(screen(node, view), width, height, 24);
    });
    const edges = model.edges.filter(function (edge) {
      const from = model.byKey[edge.from];
      const to = model.byKey[edge.to];
      if (!visibleNode(from, filters) || !visibleNode(to, filters) || (edge.type === "framework" && !filters.framework)) return false;
      return inViewport(screen(from, view), width, height, 80) || inViewport(screen(to, view), width, height, 80);
    });
    return { nodes: nodes, edges: edges };
  };
  const fit = function (model, filters, width, height) {
    const active = model.nodes.filter(function (node) { return visibleNode(node, filters); });
    if (!active.length) return { scale: 1, x: 0, y: 0 };
    const xs = active.map(function (node) { return node.x; });
    const ys = active.map(function (node) { return node.y; });
    const minX = Math.min.apply(null, xs) - 40;
    const maxX = Math.max.apply(null, xs) + 120;
    const minY = Math.min.apply(null, ys) - 40;
    const maxY = Math.max.apply(null, ys) + 40;
    const scale = Math.max(0.03, Math.min(2, Math.min(width / Math.max(1, maxX - minX), height / Math.max(1, maxY - minY))));
    return { scale: scale, x: (width - (minX + maxX) * scale) / 2, y: (height - (minY + maxY) * scale) / 2 };
  };
  const pan = function (view, dx, dy) { return { scale: view.scale, x: view.x + dx, y: view.y + dy }; };
  const zoomAt = function (view, factor, point) {
    const scale = Math.max(0.03, Math.min(5, view.scale * factor));
    const worldX = (point.x - view.x) / view.scale;
    const worldY = (point.y - view.y) / view.scale;
    return { scale: scale, x: point.x - worldX * scale, y: point.y - worldY * scale };
  };
  const find = function (model, term, filters) {
    const normalized = term.trim().toLocaleLowerCase();
    return normalized ? model.nodes.find(function (node) { return visibleNode(node, filters) && node.searchable.includes(normalized); }) || null : null;
  };
  const center = function (node, view, width, height) {
    const scale = Math.max(view.scale, 1);
    return { scale: scale, x: width / 2 - node.x * scale, y: height / 2 - node.y * scale };
  };
  const segmentDistance = function (point, start, end) {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    if (dx === 0 && dy === 0) return Math.hypot(point.x - start.x, point.y - start.y);
    const ratio = Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy)));
    return Math.hypot(point.x - (start.x + ratio * dx), point.y - (start.y + ratio * dy));
  };
  const inspectAt = function (model, filters, view, point) {
    let nearest = null;
    let distance = 14;
    model.nodes.forEach(function (node) {
      if (!visibleNode(node, filters)) return;
      const candidate = screen(node, view);
      const measured = Math.hypot(candidate.x - point.x, candidate.y - point.y);
      if (measured < distance) { nearest = node; distance = measured; }
    });
    if (nearest) return { type: nearest.type, data: nearest.value };
    const edge = model.edges.find(function (candidate) {
      const from = model.byKey[candidate.from];
      const to = model.byKey[candidate.to];
      if (!visibleNode(from, filters) || !visibleNode(to, filters) || (candidate.type === "framework" && !filters.framework)) return false;
      return segmentDistance(point, screen(from, view), screen(to, view)) <= 6;
    });
    return edge ? { type: edge.type + " edge", relation: edge.label, data: edge.value } : null;
  };
  return { build: build, visibleNode: visibleNode, screen: screen, selectVisible: selectVisible, fit: fit, pan: pan, zoomAt: zoomAt, find: find, center: center, inspectAt: inspectAt };
});
