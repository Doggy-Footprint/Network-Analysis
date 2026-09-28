(function () {
  "use strict";

  const splitElements = function (elements) {
    const nodeById = {};
    elements.forEach(function (element) { if (element.group === "nodes") nodeById[element.data.id] = element; });
    const initialIds = {};
    elements.forEach(function (element) {
      if (element.group !== "nodes" || element.classes.indexOf("directory") !== -1) return;
      if (element.data.default_visible === false) return;
      let current = element;
      while (current) {
        initialIds[current.data.id] = true;
        const parentId = current.data.parent;
        current = parentId ? nodeById[parentId] : null;
      }
    });
    const initial = [];
    const rest = [];
    elements.forEach(function (element) {
      if (element.group === "nodes") {
        (initialIds[element.data.id] ? initial : rest).push(element);
      } else {
        const bothVisible = initialIds[element.data.source] && initialIds[element.data.target];
        (bothVisible ? initial : rest).push(element);
      }
    });
    return { initial: initial, rest: rest };
  };

  window.ReportReady.then(function (data) {
    const ui = window.ReportUI;
    const built = window.ReportGraphModel.build(data);
    const parts = splitElements(built.elements);
    const container = document.getElementById("cy");
    const inspector = document.getElementById("graph-inspector");
    const status = document.getElementById("graph-status");
    const empty = document.getElementById("graph-empty");
    const readableToggle = document.getElementById("filter-readable");
    const queryToggle = document.getElementById("filter-query");
    const frameworkToggle = document.getElementById("filter-framework");
    const queryKind = document.getElementById("filter-query-kind");
    const search = document.getElementById("graph-search");

    const byId = {};
    built.nodes.forEach(function (node) { byId[node.id] = node; });

    const elementByNodeId = {};
    const edgesByEdgeId = {};
    built.elements.forEach(function (element) {
      if (element.group === "nodes") elementByNodeId[element.data.id] = element;
      else edgesByEdgeId[element.data.id] = element;
    });

    const DIRECTORY_LABEL_MIN_PX = 12;
    const ZOOM_LABEL_THRESHOLD = 1;

    const cy = cytoscape({
      container: container,
      elements: parts.initial,
      style: [
        { selector: "node.directory", style: { "background-color": "#e7ebf3", "background-opacity": 0.4, shape: "round-rectangle", "border-width": 1, "border-color": "#c3cbdd", label: "data(label)", "font-size": DIRECTORY_LABEL_MIN_PX, "text-valign": "top", "text-margin-y": -4, padding: "10px" } },
        { selector: "node.readable", style: { "background-color": "#4f7cff", width: "data(size)", height: "data(size)", "font-size": 9, color: "#1f2733", "text-valign": "bottom", "text-margin-y": 4 } },
        { selector: "node.query", style: { "background-color": "#ef8f3c", shape: "diamond", width: "data(size)", height: "data(size)", "font-size": 9, color: "#1f2733", "text-valign": "bottom", "text-margin-y": 4 } },
        { selector: "node.readable.label-always, node.query.label-always, node.readable.label-zoomed, node.query.label-zoomed, node.readable.label-hover, node.query.label-hover", style: { label: "data(label)" } },
        { selector: "edge", style: { width: 1.4, "line-color": "#91a0b8", "target-arrow-color": "#91a0b8", "target-arrow-shape": "triangle", "curve-style": "bezier", opacity: 0.65 } },
        { selector: "edge.framework", style: { "line-color": "#8a63d2", "target-arrow-color": "#8a63d2", "line-style": "dashed" } },
        { selector: ".dimmed", style: { opacity: 0.12 } },
        { selector: ".highlighted", style: { opacity: 1, "border-width": 2, "border-color": "#f43f5e", "line-color": "#f43f5e", "target-arrow-color": "#f43f5e" } }
      ]
    });

    const applyAlwaysLabelClass = function (collection) {
      collection.filter(function (element) { return element.isNode() && element.data("always_label"); }).addClass("label-always");
    };

    const updateDirectoryLabelSize = function () {
      cy.style().selector("node.directory").style("font-size", DIRECTORY_LABEL_MIN_PX / cy.zoom()).update();
    };

    const updateLabelFontSize = function () {
      const size = window.ReportGraphModel.labelFontSize(cy.zoom());
      cy.style().selector("node.readable, node.query").style("font-size", size).update();
    };

    const updateZoomLabels = function () {
      const showZoomed = cy.zoom() >= ZOOM_LABEL_THRESHOLD;
      cy.nodes("node.readable, node.query").toggleClass("label-zoomed", showZoomed);
    };

    cy.on("zoom", function () { updateDirectoryLabelSize(); updateLabelFontSize(); updateZoomLabels(); });
    cy.on("mouseover", "node.readable, node.query", function (event) { event.target.addClass("label-hover"); });
    cy.on("mouseout", "node.readable, node.query", function (event) { event.target.removeClass("label-hover"); });

    applyAlwaysLabelClass(cy.nodes());
    updateDirectoryLabelSize();
    updateLabelFontSize();
    updateZoomLabels();

    cy.on("layoutstop", function () {
      cy.resize();
      cy.fit(cy.elements(":visible"), 40);
      updateDirectoryLabelSize();
      updateLabelFontSize();
      updateZoomLabels();
    });

    cy.layout({ name: "fcose", quality: "default", animate: false, nodeDimensionsIncludeLabels: true }).run();

    const addMissingNode = function (id) {
      if (cy.getElementById(id).length) return true;

      const present = {};
      cy.nodes().forEach(function (node) { present[node.id()] = node.position(); });

      const result = window.ReportGraphModel.expand(built, present, id);
      if (!result) return false;

      const elementsToAdd = result.parents
        .concat(result.nodes)
        .map(function (nodeId) { return elementByNodeId[nodeId]; })
        .concat(result.edges.map(function (edgeId) { return edgesByEdgeId[edgeId]; }));
      const added = cy.add(elementsToAdd);

      Object.keys(result.positions).forEach(function (nodeId) {
        cy.getElementById(nodeId).position(result.positions[nodeId]);
      });

      applyAlwaysLabelClass(added);
      updateZoomLabels();
      return true;
    };

    const applyFilters = function () {
      const kind = queryKind.value;
      cy.nodes(".readable").forEach(function (node) { node.data("filtered", !readableToggle.checked); });
      cy.nodes(".query").forEach(function (node) {
        const value = byId[node.id()] ? byId[node.id()].value : null;
        const kindMatches = kind === "all" || (value && value.kind === kind);
        node.data("filtered", !queryToggle.checked || !kindMatches);
      });
      cy.nodes("[?filtered]").addClass("dimmed");
      cy.nodes().not("[?filtered]").removeClass("dimmed");
      cy.edges(".framework").forEach(function (edge) { edge.data("filtered", !frameworkToggle.checked); });
      cy.edges("[?filtered]").style("display", "none");
      cy.edges().not("[?filtered]").style("display", "element");
      const visibleCount = cy.nodes().filter(function (node) { return node.visible() && !node.hasClass("directory") && !node.data("filtered"); }).length;
      const visibleEdges = cy.edges().filter(function (edge) { return edge.visible() && !edge.data("filtered"); }).length;
      empty.hidden = visibleCount > 0;
      status.textContent = "표시 node " + ui.format(visibleCount) + " · 표시 connection " + ui.format(visibleEdges) + " · 전체 node " + ui.format(built.total) + " · 전체 connection " + ui.format(data.connections.length) + " · viewport culling 적용";
    };

    Array.from(new Set(data.query_nodes.map(function (query) { return query.kind; }))).sort().forEach(function (kind) {
      const option = ui.make("option", kind);
      option.value = kind;
      queryKind.appendChild(option);
    });

    const showInspector = function (kind, value, extra) {
      const rows = [];
      if (kind === "readable") {
        rows.push(["종류", "readable node"]);
        rows.push(["경로", value.file_path]);
        rows.push(["read-unit token", ui.format(value.read_cost.token_estimate)]);
        rows.push(["줄 수", ui.format(value.read_cost.line_count)]);
        rows.push(["kind", value.kind]);
      } else if (kind === "query") {
        rows.push(["종류", "query node"]);
        rows.push(["term", value.term]);
        rows.push(["query 전체 결과 수", ui.format(value.total_count)]);
        rows.push(["노출 결과 수", ui.format(value.visible_count)]);
        rows.push(["truncated", value.truncated ? "예" : "아니오"]);
      } else {
        rows.push(["종류", "connection"]);
        rows.push(["kind", value.kind]);
        rows.push(["connection specificity", value.specificity]);
        if (extra) { rows.push(["from", extra.from]); rows.push(["to", extra.to]); }
      }
      const table = ui.make("table", null, "inspector-table");
      rows.forEach(function (pair) {
        const row = ui.make("tr");
        row.appendChild(ui.make("th", pair[0]));
        row.appendChild(ui.make("td", pair[1]));
        table.appendChild(row);
      });
      ui.clear(inspector);
      inspector.appendChild(table);
      const details = ui.make("details");
      details.appendChild(ui.make("summary", "원본 JSON"));
      const pre = ui.make("pre");
      pre.textContent = JSON.stringify(value, null, 2);
      details.appendChild(pre);
      inspector.appendChild(details);
    };

    const clearHighlight = function () { cy.elements().removeClass("highlighted dimmed"); };

    cy.on("tap", "node.readable, node.query", function (event) {
      const node = event.target;
      clearHighlight();
      const neighborhood = node.closedNeighborhood();
      cy.elements().difference(neighborhood).addClass("dimmed");
      neighborhood.addClass("highlighted");
      const model = byId[node.id()];
      showInspector(model.type, model.value);
    });

    cy.on("tap", "edge", function (event) {
      const edge = event.target;
      clearHighlight();
      edge.addClass("highlighted");
      edge.connectedNodes().addClass("highlighted");
      showInspector("connection", edge.data("value"), { from: edge.data("source"), to: edge.data("target") });
    });

    cy.on("tap", function (event) { if (event.target === cy) clearHighlight(); });

    const computeFitZoom = function (eles, padding) {
      const bb = eles.boundingBox();
      if (bb.w <= 0 || bb.h <= 0) return cy.zoom();
      return Math.min((cy.width() - 2 * padding) / bb.w, (cy.height() - 2 * padding) / bb.h);
    };

    const focusOnNode = function (id) {
      if (!cy.getElementById(id).length) addMissingNode(id);
      const node = cy.getElementById(id);
      if (!node.length) return;
      applyFilters();
      const neighborhood = node.closedNeighborhood().filter(function (ele) { return ele.visible(); });
      const fitZoom = computeFitZoom(neighborhood, 40);
      cy.animate({ center: { eles: node }, zoom: window.ReportGraphModel.focusZoom(fitZoom) }, { duration: 200 });
      clearHighlight();
      cy.elements().unselect();
      node.select();
      node.closedNeighborhood().addClass("highlighted");
      const model = byId[id];
      if (model) showInspector(model.type, model.value);
    };

    document.getElementById("graph-find").addEventListener("click", function () {
      const term = search.value.trim().toLocaleLowerCase();
      if (!term) return;
      const match = built.nodes.find(function (node) { return node.label.toLocaleLowerCase().includes(term) || node.full_label.toLocaleLowerCase().includes(term) || node.id.toLocaleLowerCase().includes(term); });
      if (match) focusOnNode(match.id);
      else { ui.clear(inspector); inspector.appendChild(ui.make("p", "일치하는 표시 가능 node가 없습니다.", "muted")); }
    });
    document.getElementById("graph-fit").addEventListener("click", function () { cy.fit(undefined, 40); });
    [readableToggle, queryToggle, frameworkToggle, queryKind].forEach(function (control) { control.addEventListener("change", applyFilters); });
    window.addEventListener("focus-node-request", function (event) { focusOnNode(event.detail); });

    applyFilters();
    cy.fit(undefined, 40);
  });
}());
