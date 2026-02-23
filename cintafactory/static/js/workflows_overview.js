  (function () {
    function init() {
      if (window.CintaTooltip && window.CintaTooltip.initWorkflowTooltip) {
        window.CintaTooltip.initWorkflowTooltip();
      }
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
    document.addEventListener("turbolinks:load", init);
  })();
