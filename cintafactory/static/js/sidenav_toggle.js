/* global document */
(function () {
  "use strict";

  var collapsedClass = "is-collapsed";
  var initFlag = "sidenavToggleBound";

  function resolveSidenav(toggle) {
    var targetId = toggle.getAttribute("aria-controls");
    if (targetId) {
      var target = document.getElementById(targetId);
      if (target) {
        var rootFromTarget = target.closest("dmc-sidenav");
        if (rootFromTarget) {
          return rootFromTarget;
        }
      }
    }

    return toggle.closest("dmc-sidenav") || document.querySelector("dmc-sidenav");
  }

  function initSidenavToggle(source) {
    var toggle = document.querySelector("[data-sidenav-width-toggle]");
    if (!toggle) {
      console.warn("[sidenav-toggle] toggle button not found", source);
      return;
    }

    var sidenav = resolveSidenav(toggle);
    if (!sidenav) {
      console.warn("[sidenav-toggle] dmc-sidenav not found", {
        source: source,
        ariaControls: toggle.getAttribute("aria-controls"),
      });
      return;
    }

    var label = toggle.querySelector("span");
    var icon = toggle.querySelector(".material-icons");

    function sync() {
      var collapsed = sidenav.classList.contains(collapsedClass);
      toggle.setAttribute("aria-expanded", String(!collapsed));
      if (icon) {
        icon.textContent = collapsed
          ? "keyboard_double_arrow_right"
          : "keyboard_double_arrow_left";
      }
      if (label) {
        label.textContent = collapsed ? "Etendre le menu" : "Reduire le menu";
      }
      console.debug("[sidenav-toggle] sync", {
        collapsed: collapsed,
        expanded: !collapsed,
        source: source,
      });
    }

    if (toggle.dataset[initFlag] !== "1") {
      toggle.addEventListener("click", function () {
        sidenav.classList.toggle(collapsedClass);
        console.info("[sidenav-toggle] click", {
          collapsed: sidenav.classList.contains(collapsedClass),
        });
        sync();
      });
      toggle.dataset[initFlag] = "1";
      console.info("[sidenav-toggle] listener attached", source);
    }

    sync();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initSidenavToggle("DOMContentLoaded");
    });
  } else {
    initSidenavToggle("immediate");
  }

  document.addEventListener("turbolinks:load", function () {
    initSidenavToggle("turbolinks:load");
  });
})();
