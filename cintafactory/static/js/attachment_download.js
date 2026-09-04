"use strict";

(function () {
  function triggerAttachmentDownload(url) {
    if (!url) {
      return;
    }

    var win = window.open(url, "_blank");
    if (win) {
      setTimeout(function () {
        try {
          win.close();
        } catch (err) {
          // Ignore close failures from browser policies.
        }
      }, 1500);
      return;
    }

    var iframe = document.createElement("iframe");
    iframe.style.display = "none";
    iframe.src = url;
    document.body.appendChild(iframe);
    setTimeout(function () {
      if (iframe.parentNode) {
        iframe.parentNode.removeChild(iframe);
      }
    }, 60000);
  }

  if (window.__cintaAttachmentDownloadBound) {
    return;
  }
  window.__cintaAttachmentDownloadBound = true;

  document.addEventListener("click", function (event) {
    var link = event.target.closest("[data-attachment-download]");
    if (!link) {
      return;
    }
    if (link.dataset.attachmentDownloading === "1") {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    link.dataset.attachmentDownloading = "1";
    setTimeout(function () {
      link.removeAttribute("data-attachment-downloading");
    }, 2000);
    triggerAttachmentDownload(link.getAttribute("href"));
  });
})();
