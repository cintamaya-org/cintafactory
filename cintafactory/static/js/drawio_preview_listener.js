"use strict";

(function () {
  if (window.CintaDrawioPreview) {
    return;
  }

  function withCacheBuster(url) {
    if (!url) {
      return url;
    }
    var separator = url.includes("?") ? "&" : "?";
    return url + separator + "_=" + Date.now();
  }

  function updateElements(diagramId, thumbnailUrl) {
    if (!diagramId || !thumbnailUrl) {
      return;
    }
    var selector = '[data-diagram-preview-id="' + diagramId + '"]';
    var targets = document.querySelectorAll(selector);
    if (!targets.length) {
      return;
    }
    var refreshedUrl = withCacheBuster(thumbnailUrl);
    targets.forEach(function (element) {
      if (element.tagName === "IMG") {
        element.src = refreshedUrl;
      } else {
        element.style.backgroundImage = 'url("' + refreshedUrl + '")';
      }
      element.dataset.previewRefreshedAt = String(Date.now());
    });
  }

  function handleDiagramImported(event) {
    var detail = (event && event.detail) || {};
    var diagramId = detail.diagramId || detail.diagram_id;
    var thumbnailUrl = detail.thumbnailUrl || detail.thumbnail_url;
    updateElements(diagramId, thumbnailUrl);
  }

  window.CintaDrawioPreview = {
    withCacheBuster: withCacheBuster,
    updateElements: updateElements,
  };

  document.addEventListener("dat:diagram-imported", handleDiagramImported);
})();
