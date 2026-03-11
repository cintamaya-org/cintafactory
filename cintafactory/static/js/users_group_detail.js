    (function () {
      function renderGroupGraph() {
        var container = document.getElementById("group-dependency-graph");
        var source = document.getElementById("group-dependency-graph-data");
        if (!container || !source || (container && container.__userGraphReady)) {
          return;
        }
        if (!window.CintaUserGraph || typeof window.CintaUserGraph.render !== "function") {
          window.setTimeout(renderGroupGraph, 80);
          return;
        }
        try {
          var payload = JSON.parse(source.textContent);
          window.CintaUserGraph.render(container, payload);
          container.__userGraphReady = true;
        } catch (err) {
          console.error("Unable to render group dependency graph", err);
        }
      }

      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", renderGroupGraph, { once: true });
      } else {
        renderGroupGraph();
      }
      document.addEventListener("turbolinks:load", renderGroupGraph);
    })();
  
