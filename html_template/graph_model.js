(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ReportGraphModel = api;
}(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  const compare = function (left, right) { return left < right ? -1 : left > right ? 1 : 0; };
  const build = function (data) {
    const nodes = [], byKey = {};
    const addNode = function (type, value) { const node = { key: value.id, type: type, value: value, label: type === "readable" ? (value.label || value.file_path) : (value.term || value.id), searchable: JSON.stringify(value).toLocaleLowerCase(), x: 0, y: 0 }; nodes.push(node); byKey[node.key] = node; };
    data.readable_nodes.slice().sort(function (a, b) { return compare(a.id, b.id); }).forEach(function (node) { addNode("readable", node); });
    data.query_nodes.slice().sort(function (a, b) { return compare(a.id, b.id); }).forEach(function (node) { addNode("query", node); });
    const readable = nodes.filter(function (node) { return node.type === "readable"; }), queries = nodes.filter(function (node) { return node.type === "query"; });
    const place = function (items, startX, columns) { items.forEach(function (node, index) { node.x = startX + (index % columns) * 150; node.y = 80 + Math.floor(index / columns) * 70; }); };
    const readableColumns = Math.max(1, Math.ceil(Math.sqrt(Math.max(1, readable.length) * 1.5)));
    place(readable, 80, readableColumns); place(queries, 180 + readableColumns * 150, Math.max(1, Math.ceil(Math.sqrt(Math.max(1, queries.length) * 1.5))));
    const frameworkQueries = new Set(data.query_nodes.filter(function (query) { return query.kind === "framework"; }).map(function (query) { return query.id; }));
    const edges = data.connections.filter(function (connection) { return byKey[connection.from_id] && byKey[connection.to_id]; }).map(function (connection) { return { from: connection.from_id, to: connection.to_id, type: connection.kind === "framework" || frameworkQueries.has(connection.from_id) || frameworkQueries.has(connection.to_id) ? "framework" : "regular", value: connection, label: connection.kind + " · " + connection.specificity }; });
    return { nodes: nodes, byKey: byKey, edges: edges };
  };
  const visibleNode = function (node, filters) { return node.type === "readable" ? filters.readable : filters.query && (filters.queryKind === "all" || node.value.kind === filters.queryKind); };
  const screen = function (node, view) { return { x: node.x * view.scale + view.x, y: node.y * view.scale + view.y }; };
  const inViewport = function (point, width, height, margin) { return point.x >= -margin && point.y >= -margin && point.x <= width + margin && point.y <= height + margin; };
  const selectVisible = function (model, filters, view, width, height) { const nodes = model.nodes.filter(function (node) { return visibleNode(node, filters) && inViewport(screen(node, view), width, height, 24); }); const edges = model.edges.filter(function (edge) { const from = model.byKey[edge.from], to = model.byKey[edge.to]; return visibleNode(from, filters) && visibleNode(to, filters) && (edge.type !== "framework" || filters.framework) && (inViewport(screen(from, view), width, height, 80) || inViewport(screen(to, view), width, height, 80)); }); return { nodes: nodes, edges: edges }; };
  const fit = function (model, filters, width, height) { const active = model.nodes.filter(function (node) { return visibleNode(node, filters); }); if (!active.length) return { scale: 1, x: 0, y: 0 }; const xs = active.map(function (node) { return node.x; }), ys = active.map(function (node) { return node.y; }); const minX = Math.min.apply(null, xs) - 40, maxX = Math.max.apply(null, xs) + 120, minY = Math.min.apply(null, ys) - 40, maxY = Math.max.apply(null, ys) + 40; const scale = Math.max(0.03, Math.min(2, Math.min(width / Math.max(1, maxX - minX), height / Math.max(1, maxY - minY)))); return { scale: scale, x: (width - (minX + maxX) * scale) / 2, y: (height - (minY + maxY) * scale) / 2 }; };
  const pan = function (view, dx, dy) { return { scale: view.scale, x: view.x + dx, y: view.y + dy }; };
  const zoomAt = function (view, factor, point) { const scale = Math.max(0.03, Math.min(5, view.scale * factor)); const worldX = (point.x - view.x) / view.scale, worldY = (point.y - view.y) / view.scale; return { scale: scale, x: point.x - worldX * scale, y: point.y - worldY * scale }; };
  const find = function (model, term, filters) { const normalized = term.trim().toLocaleLowerCase(); return normalized ? model.nodes.find(function (node) { return visibleNode(node, filters) && node.searchable.includes(normalized); }) || null : null; };
  const center = function (node, view, width, height) { const scale = Math.max(view.scale, 1); return { scale: scale, x: width / 2 - node.x * scale, y: height / 2 - node.y * scale }; };
  const segmentDistance = function (point, start, end) { const dx = end.x - start.x, dy = end.y - start.y; if (dx === 0 && dy === 0) return Math.hypot(point.x - start.x, point.y - start.y); const ratio = Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy))); return Math.hypot(point.x - (start.x + ratio * dx), point.y - (start.y + ratio * dy)); };
  const inspectAt = function (model, filters, view, point) { let nearest = null, distance = 14; model.nodes.forEach(function (node) { if (!visibleNode(node, filters)) return; const candidate = screen(node, view), measured = Math.hypot(candidate.x - point.x, candidate.y - point.y); if (measured < distance) { nearest = node; distance = measured; } }); if (nearest) return { type: nearest.type, data: nearest.value }; const edge = model.edges.find(function (candidate) { const from = model.byKey[candidate.from], to = model.byKey[candidate.to]; return visibleNode(from, filters) && visibleNode(to, filters) && (candidate.type !== "framework" || filters.framework) && segmentDistance(point, screen(from, view), screen(to, view)) <= 6; }); return edge ? { type: edge.type + " connection", relation: edge.label, data: edge.value } : null; };
  return { build: build, visibleNode: visibleNode, screen: screen, selectVisible: selectVisible, fit: fit, pan: pan, zoomAt: zoomAt, find: find, center: center, inspectAt: inspectAt };
}));
