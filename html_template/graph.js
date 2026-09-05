(function () {
  "use strict";
  const ui = window.ReportUI;
  const data = ui.data;
  const graph = window.ReportGraphModel;
  const model = graph.build(data);
  const canvas = document.getElementById("relationship-canvas");
  const context = canvas.getContext("2d");
  const inspector = document.getElementById("graph-inspector");
  const status = document.getElementById("graph-status");
  const empty = document.getElementById("graph-empty");
  const readableToggle = document.getElementById("filter-readable");
  const queryToggle = document.getElementById("filter-query");
  const frameworkToggle = document.getElementById("filter-framework");
  const queryKind = document.getElementById("filter-query-kind");
  const search = document.getElementById("graph-search");
  const palette = { readable: "#4f7cff", query: "#ef8f3c", regular: "#91a0b8", framework: "#8a63d2", unreachable: "#d74f68" };
  let view = { scale: 1, x: 0, y: 0 };
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  let startX = 0;
  let startY = 0;
  const filters = function () {
    return { readable: readableToggle.checked, query: queryToggle.checked, framework: frameworkToggle.checked, queryKind: queryKind.value };
  };
  const dimensions = function () {
    const ratio = window.devicePixelRatio || 1;
    return { ratio: ratio, width: canvas.width / ratio, height: canvas.height / ratio };
  };
  const drawArrow = function (from, to, colour, dashed) {
    context.beginPath();
    context.setLineDash(dashed ? [5, 5] : []);
    context.moveTo(from.x, from.y);
    context.lineTo(to.x, to.y);
    context.strokeStyle = colour;
    context.lineWidth = dashed ? 1.5 : 1;
    context.globalAlpha = 0.55;
    context.stroke();
    context.globalAlpha = 1;
    context.setLineDash([]);
    const angle = Math.atan2(to.y - from.y, to.x - from.x);
    context.beginPath();
    context.moveTo(to.x, to.y);
    context.lineTo(to.x - Math.cos(angle - 0.45) * 7, to.y - Math.sin(angle - 0.45) * 7);
    context.lineTo(to.x - Math.cos(angle + 0.45) * 7, to.y - Math.sin(angle + 0.45) * 7);
    context.closePath();
    context.fillStyle = colour;
    context.fill();
  };
  const draw = function () {
    const size = dimensions();
    context.clearRect(0, 0, size.width, size.height);
    const activeFilters = filters();
    const visible = graph.selectVisible(model, activeFilters, view, size.width, size.height);
    visible.edges.forEach(function (edge) {
      drawArrow(graph.screen(model.byKey[edge.from], view), graph.screen(model.byKey[edge.to], view), palette[edge.type], edge.type === "framework");
    });
    visible.nodes.forEach(function (node) {
      const point = graph.screen(node, view);
      context.beginPath();
      context.arc(point.x, point.y, node.type === "query" ? 5 : 6, 0, Math.PI * 2);
      const unreachable = node.type === "readable" && data.unreachable_node_ids.includes(node.value.id);
      context.fillStyle = unreachable ? palette.unreachable : palette[node.type];
      context.fill();
      if (view.scale >= 0.7) {
        context.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";
        context.fillStyle = "#3b4658";
        const label = node.label.length > 28 ? node.label.slice(0, 27) + "…" : node.label;
        context.fillText(label, point.x + 9, point.y + 4);
      }
    });
    empty.hidden = model.nodes.some(function (node) { return graph.visibleNode(node, activeFilters); });
    status.textContent = "현재 viewport: node " + ui.format(visible.nodes.length) + " · edge " + ui.format(visible.edges.length) + " · 전체 node " + ui.format(model.nodes.length) + " · 전체 edge " + ui.format(model.edges.length) + " · viewport culling 적용";
  };
  const resize = function () {
    const ratio = window.devicePixelRatio || 1;
    const rectangle = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.floor(rectangle.width * ratio));
    canvas.height = Math.max(1, Math.floor(rectangle.height * ratio));
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    draw();
  };
  const fit = function () {
    const size = dimensions();
    view = graph.fit(model, filters(), size.width, size.height);
    draw();
  };
  const focusNode = function (node) {
    const size = dimensions();
    view = graph.center(node, view, size.width, size.height);
    inspector.textContent = JSON.stringify({ type: node.type, data: node.value }, null, 2);
    draw();
  };
  Array.from(new Set(data.query_nodes.map(function (query) { return query.kind; }))).sort().forEach(function (kind) {
    const option = ui.make("option", kind);
    option.value = kind;
    queryKind.appendChild(option);
  });
  document.getElementById("graph-find").addEventListener("click", function () {
    const match = graph.find(model, search.value, filters());
    if (match) focusNode(match);
    else inspector.textContent = "일치하는 표시 가능 node가 없습니다.";
  });
  search.addEventListener("keydown", function (event) {
    if (event.key === "Enter") document.getElementById("graph-find").click();
  });
  document.getElementById("graph-fit").addEventListener("click", fit);
  [readableToggle, queryToggle, frameworkToggle, queryKind].forEach(function (control) { control.addEventListener("change", fit); });
  canvas.addEventListener("wheel", function (event) {
    event.preventDefault();
    const rectangle = canvas.getBoundingClientRect();
    view = graph.zoomAt(view, event.deltaY < 0 ? 1.12 : 0.89, { x: event.clientX - rectangle.left, y: event.clientY - rectangle.top });
    draw();
  }, { passive: false });
  canvas.addEventListener("pointerdown", function (event) {
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
    startX = event.clientX;
    startY = event.clientY;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", function (event) {
    if (!dragging) return;
    view = graph.pan(view, event.clientX - lastX, event.clientY - lastY);
    lastX = event.clientX;
    lastY = event.clientY;
    draw();
  });
  canvas.addEventListener("pointerup", function (event) {
    if (!dragging) return;
    dragging = false;
    if (Math.abs(event.clientX - startX) + Math.abs(event.clientY - startY) > 2) return;
    const rectangle = canvas.getBoundingClientRect();
    const result = graph.inspectAt(model, filters(), view, { x: event.clientX - rectangle.left, y: event.clientY - rectangle.top });
    if (result) inspector.textContent = JSON.stringify(result, null, 2);
  });
  window.addEventListener("resize", resize);
  resize();
  fit();
})();
