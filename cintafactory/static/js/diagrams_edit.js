"use strict";

(function () {
  var iframeEl = document.getElementById("dio");
  var loaderEl = document.getElementById("drawio-loading");
  var saveButton = document.getElementById("btnSave");
  var configEl = document.getElementById("diagram-editor-config");

  if (!iframeEl || !saveButton || !configEl) {
    return;
  }

  var iframeWin = iframeEl.contentWindow;
  var DRAWIO_ORIGIN = configEl.getAttribute("data-drawio-origin") || "";
  var DIAGRAM_XML = configEl.getAttribute("data-diagram-xml") || "";
  var SAVE_XML_URL = configEl.getAttribute("data-save-xml-url") || "";
  var SAVE_THUMB_URL = configEl.getAttribute("data-save-thumb-url") || "";

  function hideLoader() {
    if (loaderEl) {
      loaderEl.style.opacity = "0";
      loaderEl.style.pointerEvents = "none";
      window.setTimeout(function () {
        loaderEl.remove();
      }, 200);
    }
  }

  function getCSRF() {
    var input = document.querySelector('#csrfForm input[name=csrfmiddlewaretoken]');
    return input ? input.value : "";
  }

  function sendToDrawio(payload) {
    if (!iframeWin || !DRAWIO_ORIGIN) {
      return;
    }
    iframeWin.postMessage(JSON.stringify(payload), DRAWIO_ORIGIN);
  }

  async function handleSave(xml) {
    try {
      await fetch(SAVE_XML_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRF(),
        },
        body: JSON.stringify({ xml: xml }),
      });

      sendToDrawio({ action: "export", format: "png", scale: 1, grid: 0 });
    } catch (e) {
      console.error(e);
    }
  }

  window.addEventListener("message", function (evt) {
    if (evt.origin !== DRAWIO_ORIGIN) {
      return;
    }

    var msg = evt.data;
    if (!msg) {
      return;
    }

    if (typeof msg === "string") {
      try {
        msg = JSON.parse(msg);
      } catch (_error) {
        return;
      }
    }

    if (typeof msg !== "object") {
      return;
    }

    if (msg.event === "init") {
      sendToDrawio({ action: "configure", config: { autosave: 1 } });
      sendToDrawio({ action: "load", xml: DIAGRAM_XML || "<mxGraphModel/>" });
      hideLoader();
    }

    if (msg.event === "save") {
      handleSave(msg.xml);
    }

    if (msg.event === "export" && msg.data) {
      fetch(SAVE_THUMB_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRF(),
        },
        body: JSON.stringify({ data_uri: msg.data }),
      }).catch(console.error);
    }
  });

  saveButton.addEventListener("click", function () {
    sendToDrawio({ action: "save" });
  });

  iframeEl.addEventListener("load", function () {
    window.setTimeout(hideLoader, 5000);
  });
})();
