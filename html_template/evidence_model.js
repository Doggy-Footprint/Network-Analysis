(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ReportEvidenceModel = api;
}(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  const compare = function (left, right) { return left < right ? -1 : left > right ? 1 : 0; };
  const build = function (data) {
    const items = [], byQuery = {};
    data.query_nodes.forEach(function (query) { byQuery[query.id] = query; });
    data.readable_nodes.forEach(function (value) { items.push({ type: "readable", title: value.label || value.id, subtitle: value.file_path, value: value }); });
    data.query_nodes.forEach(function (value) { items.push({ type: "query", title: value.term || value.id, subtitle: value.kind + " · " + value.visible_count + "/" + value.total_count + " visible", value: value }); });
    data.connections.forEach(function (value) { const framework = value.kind === "framework" || (byQuery[value.from_id] && byQuery[value.from_id].kind === "framework") || (byQuery[value.to_id] && byQuery[value.to_id].kind === "framework"); const shown = Object.assign({}, value); if (value.evidence.hint_id) shown.resolved_hint = data.hint_store[value.evidence.hint_id]; items.push({ type: framework ? "framework" : "connection", title: value.kind + " · " + value.specificity, subtitle: value.from_id + " → " + value.to_id, value: shown }); });
    items.sort(function (left, right) { return compare(left.type, right.type) || compare(left.title, right.title) || compare(left.subtitle, right.subtitle); });
    items.forEach(function (item) { item.search = (item.type + " " + item.title + " " + item.subtitle + " " + JSON.stringify(item.value)).toLocaleLowerCase(); });
    return items;
  };
  const search = function (items, term, limit) { const normalized = term.trim().toLocaleLowerCase(), matches = items.filter(function (item) { return !normalized || item.search.includes(normalized); }); return { total: matches.length, items: matches.slice(0, limit) }; };
  const boundaries = function (data) { return { excludedFiles: data.scan.excluded_files.slice(), entryDocuments: data.entry_documents.slice() }; };
  const loadQuery = async function (query, data, decodeBlock) { const byId = {}; data.occurrence_store.forEach(function (block) { byId[block.id] = block; }); const rows = []; for (const range of query.occurrence_ranges) { const blockRows = await decodeBlock(byId[range.block_id]); rows.push.apply(rows, blockRows.slice(range.start, range.start + range.count)); } return rows; };
  return { build: build, search: search, boundaries: boundaries, loadQuery: loadQuery };
}));
