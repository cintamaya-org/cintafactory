    (function () {
      function init() {
        if (window.CintaTooltip && window.CintaTooltip.initWorkflowTooltip) {
          window.CintaTooltip.initWorkflowTooltip({
            nodeSelector: ".wf-tooltip-trigger",
            chipSelector: ".wf-tooltip-trigger",
            textBuilder: function (target) {
              return target.getAttribute("data-tooltip") || "Information";
            },
            instantText: true
          });
        }
      }

      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
      } else {
        init();
      }
      document.addEventListener("turbolinks:load", init);
    })();
  
