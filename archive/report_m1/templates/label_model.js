(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ReportLabels = api;
}(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  const segments = function (path) {
    const parts = path.split("/").filter(function (part) { return part !== ""; });
    return parts.length ? parts : [path];
  };
  const suffix = function (parts, depth) {
    return parts.slice(Math.max(0, parts.length - depth)).join("/");
  };
  const shortLabels = function (paths) {
    const uniquePaths = [];
    const seen = {};
    paths.forEach(function (path) { if (!Object.prototype.hasOwnProperty.call(seen, path)) { seen[path] = true; uniquePaths.push(path); } });
    if (!uniquePaths.length) return {};
    const segmentsByPath = {};
    uniquePaths.forEach(function (path) { segmentsByPath[path] = segments(path); });
    const groups = {};
    uniquePaths.forEach(function (path) {
      const parts = segmentsByPath[path];
      const basename = parts[parts.length - 1];
      if (!groups[basename]) groups[basename] = [];
      groups[basename].push(path);
    });
    const labels = {};
    Object.keys(groups).forEach(function (basename) {
      const groupPaths = groups[basename];
      if (groupPaths.length === 1) {
        labels[groupPaths[0]] = basename;
        return;
      }
      const maxDepth = groupPaths.reduce(function (max, path) { return Math.max(max, segmentsByPath[path].length); }, 0);
      let depth = 2;
      while (true) {
        const candidates = {};
        groupPaths.forEach(function (path) { candidates[path] = suffix(segmentsByPath[path], depth); });
        const counts = {};
        Object.keys(candidates).forEach(function (path) { const label = candidates[path]; counts[label] = (counts[label] || 0) + 1; });
        const allUnique = Object.keys(candidates).every(function (path) { return counts[candidates[path]] === 1; });
        if (allUnique || depth >= maxDepth) {
          Object.keys(candidates).forEach(function (path) { labels[path] = candidates[path]; });
          break;
        }
        depth += 1;
      }
    });
    return labels;
  };
  return { shortLabels: shortLabels };
}));
