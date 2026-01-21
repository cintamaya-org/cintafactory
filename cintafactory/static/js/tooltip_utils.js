(function (global) {
  "use strict";

  var DEFAULT_TOOLTIP_TEXT =
    "Exmaple DEFAULT_TOOLTIP_TEXT" +
    "DEFAULT_TOOLTIP_TEXT" +
    "tra laoreeilisis bibendum elementum morbi. Semper risus condimentum porttitor netus pharetra congue nam, metus natoque maecenas tortor sapien praesent, turpis consequat\n\n";

  function buildDefaultText(target) {
    var tip = target.getAttribute("data-tooltip") || "Information";
    return DEFAULT_TOOLTIP_TEXT + tip;
  }

  function initWorkflowTooltip(options) {
    var opts = options || {};
    var tooltipId = opts.tooltipId || "wf-tooltip";
    var tooltip = document.getElementById(tooltipId);
    if (!tooltip) {
      return null;
    }

    var spinner = tooltip.querySelector(".wf-tooltip__spinner");
    var textNode = tooltip.querySelector(".wf-tooltip__text");
    if (!spinner || !textNode) {
      return null;
    }

    var delayMs = typeof opts.delayMs === "number" ? opts.delayMs : 2000;
    var offsetX = typeof opts.offsetX === "number" ? opts.offsetX : 24;
    var offsetY = typeof opts.offsetY === "number" ? opts.offsetY : 24;
    var nodeSelector = opts.nodeSelector || ".wf-node";
    var chipSelector = opts.chipSelector || ".wf-chip";
    var textBuilder = typeof opts.textBuilder === "function" ? opts.textBuilder : buildDefaultText;
    var fixedText = typeof opts.fixedText === "string" ? opts.fixedText : null;
    var dataFetcher = typeof opts.dataFetcher === "function" ? opts.dataFetcher : null;
    var errorText = typeof opts.errorText === "string" ? opts.errorText : "Information";
    var errorBuilder = typeof opts.errorBuilder === "function" ? opts.errorBuilder : null;
    var instantText = opts.instantText === true;

    var state = tooltip.__wfTooltipState;
    if (!state) {
      state = { showTimer: null, activeTarget: null, insideTrigger: false, requestId: 0 };
      tooltip.__wfTooltipState = state;
    }

    function getPoint(evt) {
      if (!evt) {
        return { x: 0, y: 0 };
      }
      if (evt.touches && evt.touches.length) {
        return { x: evt.touches[0].clientX, y: evt.touches[0].clientY };
      }
      return { x: evt.clientX, y: evt.clientY };
    }

    function setPosition(point) {
      if (!tooltip || tooltip.hidden) {
        return;
      }
      tooltip.style.left = point.x + offsetX + "px";
      tooltip.style.top = point.y - offsetY + "px";
    }

    function hideTooltip(target) {
      if (state.insideTrigger && target === state.activeTarget) {
        return;
      }
      state.activeTarget = null;
      state.requestId += 1;
      tooltip.classList.remove("wf-tooltip--visible");
      tooltip.classList.remove("wf-tooltip--text");
      tooltip.hidden = true;
      spinner.hidden = true;
      textNode.hidden = true;
      textNode.textContent = "";
      if (state.showTimer) {
        clearTimeout(state.showTimer);
        state.showTimer = null;
      }
    }

    function showText(text) {
      var content = text == null ? "" : String(text);
      spinner.hidden = true;
      textNode.textContent = content;
      textNode.hidden = false;
      tooltip.classList.add("wf-tooltip--text");
    }

    function showSpinner() {
      spinner.hidden = false;
      textNode.hidden = true;
      textNode.textContent = "";
      tooltip.classList.remove("wf-tooltip--text");
    }

    function showTooltip(target, point) {
      state.activeTarget = target;
      if (state.showTimer) {
        clearTimeout(state.showTimer);
        state.showTimer = null;
      }
      tooltip.hidden = false;
      requestAnimationFrame(function () {
        tooltip.classList.add("wf-tooltip--visible");
      });
      setPosition(point);

      if (dataFetcher) {
        var requestId = (state.requestId += 1);
        showSpinner();
        Promise.resolve()
          .then(function () {
            return dataFetcher(target);
          })
          .then(function (result) {
            if (state.activeTarget !== target || state.requestId !== requestId) {
              return;
            }
            showText(result == null ? "" : String(result));
          })
          .catch(function (err) {
            if (state.activeTarget !== target || state.requestId !== requestId) {
              return;
            }
            if (errorBuilder) {
              showText(errorBuilder(err, target));
            } else {
              showText(errorText);
            }
          });
        return;
      }

      if (fixedText !== null) {
        showText(fixedText);
        return;
      }

      if (instantText) {
        showText(textBuilder(target));
        return;
      }

      showSpinner();
      state.showTimer = setTimeout(function () {
        if (state.activeTarget !== target) {
          return;
        }
        showText(textBuilder(target));
      }, delayMs);
    }

    function attachHover(element, owner) {
      if (!element || !owner) {
        return;
      }
      if (element.__wfTooltipReady) {
        return;
      }
      element.__wfTooltipReady = true;
      element.addEventListener("mouseenter", function (evt) {
        state.insideTrigger = true;
        showTooltip(owner, getPoint(evt));
      });
      element.addEventListener("mousemove", function (evt) {
        setPosition(getPoint(evt));
      });
      element.addEventListener("mouseleave", function () {
        state.insideTrigger = false;
        hideTooltip(owner);
      });
      element.addEventListener("touchstart", function (evt) {
        state.insideTrigger = true;
        showTooltip(owner, getPoint(evt));
      });
      element.addEventListener("touchmove", function (evt) {
        setPosition(getPoint(evt));
      });
      element.addEventListener("touchend", function () {
        state.insideTrigger = false;
        hideTooltip(owner);
      });
      element.addEventListener("touchcancel", function () {
        state.insideTrigger = false;
        hideTooltip(owner);
      });
    }

    Array.prototype.forEach.call(document.querySelectorAll(nodeSelector), function (node) {
      var reference = node.querySelector(".wf-dot") || node.querySelector(".wf-node__badge") || node;
      attachHover(node, reference);
    });

    Array.prototype.forEach.call(document.querySelectorAll(chipSelector), function (chip) {
      attachHover(chip, chip);
    });

    if (!tooltip.__wfTooltipReady) {
      tooltip.__wfTooltipReady = true;
      tooltip.addEventListener("mouseenter", function () {
        state.insideTrigger = true;
      });
      tooltip.addEventListener("mouseleave", function () {
        state.insideTrigger = false;
        hideTooltip(state.activeTarget);
      });
    }

    return {
      hide: hideTooltip,
      show: showTooltip,
      updatePosition: setPosition
    };
  }

  global.CintaTooltip = global.CintaTooltip || {};
  global.CintaTooltip.initWorkflowTooltip = initWorkflowTooltip;
})(window);
