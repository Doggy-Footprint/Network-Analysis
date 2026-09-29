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
      const nodeData = { id: node.id, label: model.label, full_label: model.full_label, size: size, weight: model.weight, default_visible: model.default_visible, always_label: model.always_label };
      if (parent) nodeData.parent = parent;
      elements.push({ group: "nodes", data: nodeData, classes: "readable" + (model.default_visible ? "" : " capped") });
    });
    data.query_nodes.forEach(function (query) {
      const model = nodes.find(function (candidate) { return candidate.id === query.id; });
      const size = Math.max(10, Math.min(50, Math.sqrt(Math.max(1, query.total_count + 1)) * 4));
      elements.push({ group: "nodes", data: { id: query.id, label: model.label, full_label: model.full_label, size: size, weight: model.weight, default_visible: model.default_visible, always_label: model.always_label }, classes: "query" + (model.default_visible ? "" : " capped") });
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

  const NEIGHBOR_LIMIT = 20;
  const MIN_GAP = 60;
  const MAX_RING = 12;

  const ringCandidates = function (startRing, endRing) {
    const candidates = [];
    for (let k = startRing; k <= endRing; k += 1) {
      const radius = MIN_GAP * k;
      const slots = Math.max(1, Math.floor((2 * Math.PI * radius) / MIN_GAP));
      for (let j = 0; j < slots; j += 1) {
        const angle = (2 * Math.PI * j) / slots;
        candidates.push({ dx: radius * Math.cos(angle), dy: radius * Math.sin(angle) });
      }
    }
    return candidates;
  };
  const TARGET_CANDIDATES = ringCandidates(0, MAX_RING);
  const NEIGHBOR_CANDIDATES = ringCandidates(2, MAX_RING);

  const distance = function (ax, ay, bx, by) { return Math.sqrt((ax - bx) * (ax - bx) + (ay - by) * (ay - by)); };
  const isClearOf = function (x, y, points) {
    return points.every(function (point) { return distance(x, y, point.x, point.y) >= MIN_GAP; });
  };
  const placeNear = function (centerX, centerY, candidates, blockingPoints) {
    for (let i = 0; i < candidates.length; i += 1) {
      const x = centerX + candidates[i].dx;
      const y = centerY + candidates[i].dy;
      if (isClearOf(x, y, blockingPoints)) return { x: x, y: y };
    }
    const fallback = candidates[candidates.length - 1];
    return { x: centerX + fallback.dx, y: centerY + fallback.dy };
  };

  const ancestorChain = function (elementByNodeId, nodeId) {
    const chain = [];
    let parentId = (elementByNodeId[nodeId] || {}).parent;
    while (parentId) {
      chain.unshift(parentId);
      parentId = (elementByNodeId[parentId] || {}).parent;
    }
    return chain;
  };

  const expand = function (built, present, targetId) {
    const nodeElementById = {};
    const edgesByNodeId = {};
    built.elements.forEach(function (element) {
      if (element.group === "nodes") {
        nodeElementById[element.data.id] = element.data;
      } else {
        (edgesByNodeId[element.data.source] = edgesByNodeId[element.data.source] || []).push(element);
        (edgesByNodeId[element.data.target] = edgesByNodeId[element.data.target] || []).push(element);
      }
    });

    const targetElement = nodeElementById[targetId];
    if (!targetElement || targetElement.is_directory) return null;
    if (present[targetId]) return { nodes: [], parents: [], edges: [], positions: {} };

    const connectionCount = {};
    built.elements.forEach(function (element) {
      if (element.group !== "edges") return;
      connectionCount[element.data.source] = (connectionCount[element.data.source] || 0) + 1;
      connectionCount[element.data.target] = (connectionCount[element.data.target] || 0) + 1;
    });

    const neighborIds = {};
    (edgesByNodeId[targetId] || []).forEach(function (edge) {
      const other = edge.data.source === targetId ? edge.data.target : edge.data.source;
      const otherElement = nodeElementById[other];
      if (other !== targetId && otherElement && !otherElement.is_directory) neighborIds[other] = true;
    });
    const rankedNeighbors = Object.keys(neighborIds).sort(function (a, b) {
      return ((connectionCount[b] || 0) - (connectionCount[a] || 0)) || compare(a, b);
    });
    const selectedNeighbors = rankedNeighbors.slice(0, NEIGHBOR_LIMIT);

    const focusSet = [targetId].concat(selectedNeighbors);

    const presentIds = {};
    Object.keys(present).forEach(function (id) { presentIds[id] = true; });

    const newNodeIds = focusSet.filter(function (id) { return !presentIds[id]; });

    const parents = [];
    const seenParent = {};
    newNodeIds.forEach(function (nodeId) {
      ancestorChain(nodeElementById, nodeId).forEach(function (ancestorId) {
        if (!presentIds[ancestorId] && !seenParent[ancestorId]) {
          seenParent[ancestorId] = true;
          parents.push(ancestorId);
        }
      });
    });

    const allPresentAfterIds = {};
    Object.keys(presentIds).forEach(function (id) { allPresentAfterIds[id] = true; });
    focusSet.forEach(function (id) { allPresentAfterIds[id] = true; });
    parents.forEach(function (id) { allPresentAfterIds[id] = true; });

    const edges = [];
    const seenEdge = {};
    focusSet.forEach(function (nodeId) {
      (edgesByNodeId[nodeId] || []).forEach(function (edge) {
        const eid = edge.data.id;
        if (seenEdge[eid]) return;
        const otherEnd = edge.data.source === nodeId ? edge.data.target : edge.data.source;
        if (!allPresentAfterIds[otherEnd]) return;
        if (presentIds[nodeId] && presentIds[otherEnd]) return;
        seenEdge[eid] = true;
        edges.push(eid);
      });
    });

    const positions = {};
    const anchor = (function () {
      const existingNeighborId = rankedNeighbors.find(function (id) { return presentIds[id]; });
      if (existingNeighborId) return present[existingNeighborId];
      const ancestors = ancestorChain(nodeElementById, targetId);
      for (let i = ancestors.length - 1; i >= 0; i -= 1) {
        if (presentIds[ancestors[i]]) return present[ancestors[i]];
      }
      return { x: 0, y: 0 };
    })();

    const placedPoints = Object.keys(present).map(function (id) { return present[id]; });

    if (newNodeIds.indexOf(targetId) !== -1) {
      const targetPosition = placeNear(anchor.x, anchor.y, TARGET_CANDIDATES, placedPoints);
      positions[targetId] = targetPosition;
      placedPoints.push(targetPosition);
    }

    const newOtherNeighbors = newNodeIds.filter(function (id) { return id !== targetId; });
    const neighborCenter = positions[targetId] || anchor;
    newOtherNeighbors.forEach(function (nodeId) {
      const neighborPosition = placeNear(neighborCenter.x, neighborCenter.y, NEIGHBOR_CANDIDATES, placedPoints);
      positions[nodeId] = neighborPosition;
      placedPoints.push(neighborPosition);
    });

    return { nodes: newNodeIds, parents: parents, edges: edges, positions: positions };
  };

  const labelFontSize = function (zoom) { return Math.max(9, 11 / zoom); };
  const focusZoom = function (fitZoom) { return Math.max(fitZoom, 1); };

  const boxesOverlap = function (a, b) {
    return a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2;
  };
  const visibleLabels = function (boxes) {
    const ordered = boxes.slice().sort(function (a, b) { return (b.weight - a.weight) || compare(a.id, b.id); });
    const accepted = [];
    ordered.forEach(function (box) {
      const overlapsAccepted = accepted.some(function (chosen) { return boxesOverlap(box, chosen); });
      if (!overlapsAccepted) accepted.push(box);
    });
    return accepted.map(function (box) { return box.id; });
  };

  return { build: build, focus: focus, expand: expand, visibleLabels: visibleLabels, labelFontSize: labelFontSize, focusZoom: focusZoom };
}));
