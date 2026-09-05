(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ReportEvidenceModel = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  const compare = function (left, right) { return left < right ? -1 : left > right ? 1 : 0; };
  const build = function (data) {
    const items = [];
    data.readable_nodes.forEach(function (value) {
      items.push({ type: "readable", title: value.label || value.id, subtitle: value.file_path, value: value });
    });
    data.query_nodes.forEach(function (value) {
      items.push({ type: "query", title: value.term || value.id, subtitle: value.kind + " · " + value.occurrences.length + " occurrence", value: value });
    });
    data.framework_links.forEach(function (value) {
      items.push({ type: "framework", title: value.rule_id, subtitle: value.evidence_file + ":" + value.evidence_line, value: value });
    });
    items.sort(function (left, right) {
      return compare(left.type, right.type) || compare(left.title, right.title) || compare(left.subtitle, right.subtitle);
    });
    items.forEach(function (item) {
      item.search = (item.type + " " + item.title + " " + item.subtitle + " " + JSON.stringify(item.value)).toLocaleLowerCase();
    });
    return items;
  };
  const search = function (items, term, limit) {
    const normalized = term.trim().toLocaleLowerCase();
    const matches = items.filter(function (item) { return !normalized || item.search.includes(normalized); });
    return { total: matches.length, items: matches.slice(0, limit) };
  };
  const boundaries = function (data) {
    return { excludedFiles: data.scan.excluded_files.slice(), unknownFrameworkEdges: data.scan.unknown_framework_edges.slice() };
  };
  return { build: build, search: search, boundaries: boundaries };
});
