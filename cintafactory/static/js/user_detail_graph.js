(function () {
  var SVG_NS = "http://www.w3.org/2000/svg";
  var XLINK_NS = "http://www.w3.org/1999/xlink";
  var BOX = { width: 220, height: 86 };
  var DEFAULT_LAYOUT = {
    user: { x: 20, y: 70 },
    group: { x: 280, y: 70 },
    business_direction: { x: 560, y: 10 },
    technical_direction: { x: 560, y: 190 },
    responsible: { x: 280, y: 260 },
  };

  function createSvgElement(tag, attrs) {
    var el = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        if (attrs[key] === undefined || attrs[key] === null) {
          return;
        }
        if (key === "xlink:href") {
          el.setAttributeNS(XLINK_NS, "href", attrs[key]);
        } else {
          el.setAttribute(key, attrs[key]);
        }
      });
    }
    return el;
  }

  function normalizeNode(node) {
    var layout = DEFAULT_LAYOUT[node.id] || { x: 0, y: 0 };
    var overrides = (node.layout || {});
    node.x = typeof overrides.x === "number" ? overrides.x : layout.x;
    node.y = typeof overrides.y === "number" ? overrides.y : layout.y;
    node.width = typeof overrides.width === "number" ? overrides.width : layout.width || BOX.width;
    node.height = typeof overrides.height === "number" ? overrides.height : layout.height || BOX.height;
    node.value = typeof node.value === "string" ? node.value : (node.value == null ? "Non défini" : String(node.value));
    node.isMissing = !node.value || node.value === "Non défini";
    return node;
  }

  function computeCanvas(nodes) {
    return nodes.reduce(function (acc, node) {
      var maxX = node.x + node.width;
      var maxY = node.y + node.height;
      if (maxX > acc.width) {
        acc.width = maxX;
      }
      if (maxY > acc.height) {
        acc.height = maxY;
      }
      return acc;
    }, { width: 840, height: 360 });
  }

  function chunkText(text, maxChars) {
    var clean = text || "";
    var words = clean.split(/\s+/);
    var lines = [];
    var current = "";
    words.forEach(function (word) {
      if (!word) {
        return;
      }
      var candidate = current ? current + " " + word : word;
      if (candidate.length <= maxChars) {
        current = candidate;
      } else {
        if (current) {
          lines.push(current);
        }
        if (word.length > maxChars) {
          var chunk = word;
          while (chunk.length > maxChars) {
            lines.push(chunk.slice(0, maxChars));
            chunk = chunk.slice(maxChars);
          }
          current = chunk;
        } else {
          current = word;
        }
      }
    });
    if (current) {
      lines.push(current);
    }
    return lines;
  }

  function appendWrappedText(parent, text, width, opts) {
    opts = opts || {};
    var padding = opts.padding || 20;
    var maxChars = Math.max(12, Math.floor((width - padding) / 7));
    var lines = chunkText(text, maxChars);
    var maxLines = opts.maxLines || 3;
    var baseY = opts.y || 0;
    var truncated = lines.length > maxLines;
    lines.slice(0, maxLines).forEach(function (line, idx) {
      var content = line;
      if (truncated && idx === maxLines - 1) {
        content = content.slice(0, Math.max(3, maxChars - 1)).trim();
        content = content ? content + "…" : "…";
      }
      var tspan = createSvgElement("tspan", {
        x: opts.x,
        y: baseY + idx * (opts.lineHeight || 16),
      });
      tspan.textContent = content;
      parent.appendChild(tspan);
    });
  }

  function getEdgePoint(node, edge) {
    var x = node.x + node.width / 2;
    var y = node.y + node.height / 2;
    switch (edge) {
      case "left":
        return { x: node.x, y: y };
      case "right":
        return { x: node.x + node.width, y: y };
      case "top":
        return { x: x, y: node.y };
      case "bottom":
        return { x: x, y: node.y + node.height };
      default:
        return { x: x, y: y };
    }
  }

  function buildPath(fromNode, toNode, route) {
    var start;
    var end;
    var commands;
    switch (route) {
      case "horizontal":
        start = getEdgePoint(fromNode, fromNode.x <= toNode.x ? "right" : "left");
        end = getEdgePoint(toNode, fromNode.x <= toNode.x ? "left" : "right");
        commands = ["M", start.x, start.y, "L", end.x, end.y];
        break;
      case "up":
        start = getEdgePoint(fromNode, "top");
        end = getEdgePoint(toNode, "left");
        commands = [
          "M", start.x, start.y,
          "L", start.x, end.y,
          "L", end.x, end.y,
        ];
        break;
      case "down":
        start = getEdgePoint(fromNode, "bottom");
        end = getEdgePoint(toNode, "top");
        commands = ["M", start.x, start.y, "L", end.x, end.y];
        break;
      default:
        start = getEdgePoint(fromNode);
        end = getEdgePoint(toNode);
        commands = ["M", start.x, start.y, "L", end.x, end.y];
    }
    return commands.join(" ");
  }

  function ensureArrowMarker(svg, markerId) {
    var defs = svg.querySelector("defs");
    if (!defs) {
      defs = createSvgElement("defs");
      svg.appendChild(defs);
    }
    var marker = createSvgElement("marker", {
      id: markerId,
      orient: "auto",
      markerWidth: 12,
      markerHeight: 12,
      refX: 10,
      refY: 3.5,
    });
    var arrow = createSvgElement("path", {
      d: "M 0 0 L 10 3.5 L 0 7 z",
      class: "user-relationship-link__arrow",
    });
    marker.appendChild(arrow);
    defs.appendChild(marker);
  }

  function renderNodes(svg, nodes) {
    var nodeMap = {};
    nodes.forEach(function (node) {
      nodeMap[node.id] = node;
      var g = createSvgElement("g", {
        class: [
          "user-relationship-node",
          node.optional ? "user-relationship-node--optional" : "",
          node.isMissing ? "user-relationship-node--empty" : "",
          node.url ? "user-relationship-node--clickable" : "",
        ].filter(Boolean).join(" "),
        transform: "translate(" + node.x + " " + node.y + ")",
      });

      var rect = createSvgElement("rect", {
        width: node.width,
        height: node.height,
        rx: 18,
        ry: 18,
      });
      g.appendChild(rect);

      var title = createSvgElement("text", {
        x: 16,
        y: 24,
        class: "user-relationship-node__title",
      });
      title.textContent = node.title || "";
      g.appendChild(title);

      var value = createSvgElement("text", {
        x: 16,
        y: 46,
        class: "user-relationship-node__value",
      });
      appendWrappedText(value, node.value, node.width, {
        x: 16,
        y: 46,
        lineHeight: 18,
        maxLines: 3,
      });
      g.appendChild(value);

      if (node.url) {
        var link = createSvgElement("a", {
          href: node.url,
          "xlink:href": node.url,
        });
        link.appendChild(g);
        svg.appendChild(link);
      } else {
        svg.appendChild(g);
      }
    });
    return nodeMap;
  }

  function renderLinks(svg, nodes, links, markerId) {
    links.forEach(function (link) {
      var fromNode = nodes[link.from];
      var toNode = nodes[link.to];
      if (!fromNode || !toNode) {
        return;
      }
      var path = createSvgElement("path", {
        d: buildPath(fromNode, toNode, link.route),
        class: "user-relationship-link",
        "marker-end": "url(#" + markerId + ")",
      });
      svg.appendChild(path);
    });
  }

  function render(container, data) {
    if (!container || !data) {
      return;
    }
    var parsedNodes = (data.nodes || []).map(function (node) {
      return normalizeNode(node);
    });
    if (!parsedNodes.length) {
      container.textContent = "Aucune donnée à afficher.";
      return;
    }

    var canvas = computeCanvas(parsedNodes);
    var svg = createSvgElement("svg", {
      viewBox: "0 0 " + (canvas.width + 60) + " " + (canvas.height + 40),
      role: "img",
      "aria-label": "Relations utilisateur",
      class: "user-relationship-graph__svg",
      preserveAspectRatio: "xMinYMin meet",
    });

    var markerId = "user-relationship-arrow-" + Math.random().toString(36).slice(2, 8);
    ensureArrowMarker(svg, markerId);
    var nodeMap = renderNodes(svg, parsedNodes);
    renderLinks(svg, nodeMap, data.links || [], markerId);

    container.innerHTML = "";
    container.appendChild(svg);
  }

  function init() {
    var containers = document.querySelectorAll("[data-graph-source]");
    Array.prototype.forEach.call(containers, function (container) {
      if (container.__userGraphReady) {
        return;
      }
      var sourceId = container.getAttribute("data-graph-source");
      if (!sourceId) {
        return;
      }
      var sourceEl = document.getElementById(sourceId);
      if (!sourceEl) {
        return;
      }
      try {
        var payload = JSON.parse(sourceEl.textContent);
        render(container, payload);
        container.__userGraphReady = true;
      } catch (err) {
        console.error("Unable to render user dependency graph", err);
      }
    });
  }

  window.CintaUserGraph = {
    render: render,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  document.addEventListener("turbolinks:load", init);
})();
