(function () {
  "use strict";
  if (typeof cytoscape === "function" && typeof cytoscapeFcose !== "undefined") {
    cytoscape.use(cytoscapeFcose);
  }
}());
