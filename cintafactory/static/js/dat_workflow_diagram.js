"use strict";

(function () {
  function positionNodes(diagram) {
    var row = diagram.querySelector(".wf-node-row");
    if (!row) {
      return;
    }

    var layoutHeight = parseInt(diagram.getAttribute("data-layout-height") || "300", 10);
    if (!Number.isFinite(layoutHeight) || layoutHeight < 180) {
      layoutHeight = 300;
    }
    diagram.style.height = String(layoutHeight) + "px";
    row.style.height = String(layoutHeight) + "px";

    var nodes = Array.prototype.slice.call(row.querySelectorAll(".wf-node[data-node-id]"));
    if (!nodes.length) {
      return;
    }

    var host = diagram.getBoundingClientRect();
    var padding = parseInt(diagram.getAttribute("data-layout-padding") || "36", 10);
    if (!Number.isFinite(padding) || padding < 0) {
      padding = 36;
    }

    var rows = [];
    var cols = [];
    nodes.forEach(function (node) {
      var r = parseInt(node.getAttribute("data-row") || "0", 10);
      var c = parseInt(node.getAttribute("data-col") || "0", 10);
      if (!Number.isFinite(r) || r < 0) {
        r = 0;
      }
      if (!Number.isFinite(c) || c < 0) {
        c = 0;
      }
      rows.push(r);
      cols.push(c);
      node.setAttribute("data-row", String(r));
      node.setAttribute("data-col", String(c));
    });

    var minRow = Math.min.apply(Math, rows);
    var maxRow = Math.max.apply(Math, rows);
    var minCol = Math.min.apply(Math, cols);
    var maxCol = Math.max.apply(Math, cols);
    var width = Math.max(1, Math.round(host.width));
    var height = Math.max(1, Math.round(host.height));
    var rowSpan = Math.max(1, maxRow - minRow);
    var colSpan = Math.max(1, maxCol - minCol);

    nodes.forEach(function (node) {
      var r = parseInt(node.getAttribute("data-row") || "0", 10);
      var c = parseInt(node.getAttribute("data-col") || "0", 10);
      var x = padding + ((c - minCol) / colSpan) * (width - padding * 2);
      var y = padding + ((r - minRow) / rowSpan) * (height - padding * 2);
      node.style.left = String(x) + "px";
      node.style.top = String(y) + "px";
    });
  }

  function drawLinks(diagram) {
    var svg = diagram.querySelector("[data-wf-links]");
    if (!svg) {
      return;
    }

    positionNodes(diagram);
    var nodes = Array.prototype.slice.call(diagram.querySelectorAll(".wf-node[data-node-id]"));
    var byId = {};
    nodes.forEach(function (node) {
      byId[node.getAttribute("data-node-id")] = node;
    });

    var host = diagram.getBoundingClientRect();
    var width = Math.max(1, Math.round(host.width));
    var height = Math.max(1, Math.round(host.height));
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("width", String(width));
    svg.setAttribute("height", String(height));

    while (svg.firstChild) {
      svg.removeChild(svg.firstChild);
    }

    var defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    var marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
    marker.setAttribute("id", "wf-arrow-" + Math.random().toString(36).slice(2));
    marker.setAttribute("viewBox", "0 0 10 10");
    marker.setAttribute("refX", "9");
    marker.setAttribute("refY", "5");
    marker.setAttribute("markerWidth", "7");
    marker.setAttribute("markerHeight", "7");
    marker.setAttribute("orient", "auto-start-reverse");

    var tip = document.createElementNS("http://www.w3.org/2000/svg", "path");
    tip.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
    tip.setAttribute("fill", "#90a4ae");
    marker.appendChild(tip);
    defs.appendChild(marker);
    svg.appendChild(defs);

    var markerId = marker.getAttribute("id");
    nodes.forEach(function (node) {
      var linksRaw = node.getAttribute("data-links") || "";
      if (!linksRaw) {
        return;
      }
      var from = node.getBoundingClientRect();
      var x1 = from.left - host.left + from.width / 2;
      var y1 = from.top - host.top + from.height / 2;

      linksRaw
        .split(",")
        .map(function (x) {
          return x.trim();
        })
        .filter(Boolean)
        .forEach(function (targetId) {
          var target = byId[targetId];
          if (!target) {
            return;
          }
          var to = target.getBoundingClientRect();
          var x2 = to.left - host.left + to.width / 2;
          var y2 = to.top - host.top + to.height / 2;
          var dx = x2 - x1;
          var dy = y2 - y1;
          var dist = Math.sqrt(dx * dx + dy * dy);
          if (!dist) {
            return;
          }
          var startOffset = 14;
          var endOffset = 16;
          var sx = x1 + (dx / dist) * startOffset;
          var sy = y1 + (dy / dist) * startOffset;
          var ex = x2 - (dx / dist) * endOffset;
          var ey = y2 - (dy / dist) * endOffset;
          var line = document.createElementNS("http://www.w3.org/2000/svg", "line");
          line.setAttribute("x1", String(sx));
          line.setAttribute("y1", String(sy));
          line.setAttribute("x2", String(ex));
          line.setAttribute("y2", String(ey));
          line.setAttribute("stroke", "#90a4ae");
          line.setAttribute("stroke-width", "3");
          line.setAttribute("opacity", "0.95");
          line.setAttribute("stroke-linecap", "round");
          line.setAttribute("marker-end", "url(#" + markerId + ")");
          svg.appendChild(line);
        });
    });
  }

  function redrawAll() {
    document.querySelectorAll("[data-wf-diagram]").forEach(drawLinks);
  }

  function bindNodeToggle() {
    if (window.__datWorkflowNodesBound) {
      return;
    }
    window.__datWorkflowNodesBound = true;
    document.addEventListener("click", function (event) {
      var cap = event.target.closest(".wf-node__cap");
      if (cap) {
        var capNode = cap.closest(".wf-node");
        if (capNode) {
          capNode.classList.remove("wf-node--expanded");
          redrawAll();
        }
        return;
      }

      var node = event.target.closest(".wf-node");
      if (!node) {
        return;
      }
      node.classList.add("wf-node--expanded");
      redrawAll();
    });
  }

  function initWorkflowDiagrams() {
    window.__redrawDatWorkflowLinks = redrawAll;
    bindNodeToggle();
    redrawAll();
  }

  if (!window.__datWorkflowLinksResizeBound) {
    window.__datWorkflowLinksResizeBound = true;
    window.addEventListener("resize", redrawAll);
  }

  document.addEventListener("DOMContentLoaded", initWorkflowDiagrams);
  document.addEventListener("turbolinks:load", initWorkflowDiagrams);
})();
