(function () {
  if (window.__cintaDevFrontendLoggerInitialized) {
    return;
  }
  window.__cintaDevFrontendLoggerInitialized = true;

  var prefix = "[cinta-dev]";
  var originalLog = console.log.bind(console);
  var originalWarn = console.warn.bind(console);
  var originalError = console.error.bind(console);

  function nowIso() {
    return new Date().toISOString();
  }

  function write(method, label, payload) {
    method(prefix, nowIso(), label, payload);
  }

  function log(label, payload) {
    write(originalLog, label, payload);
  }

  function warn(label, payload) {
    write(originalWarn, label, payload);
  }

  function error(label, payload) {
    write(originalError, label, payload);
  }

  console.log = function () {
    originalLog.apply(console, [prefix, "[log]"].concat(Array.prototype.slice.call(arguments)));
  };
  console.warn = function () {
    originalWarn.apply(console, [prefix, "[warn]"].concat(Array.prototype.slice.call(arguments)));
  };
  console.error = function () {
    originalError.apply(console, [prefix, "[error]"].concat(Array.prototype.slice.call(arguments)));
  };

  log("frontend logger enabled", { href: window.location.href });
  document.addEventListener("DOMContentLoaded", function () {
    log("DOMContentLoaded", { title: document.title });
  });
  document.addEventListener("turbolinks:load", function () {
    log("turbolinks:load", { href: window.location.href });
  });

  window.addEventListener("error", function (event) {
    error("runtime-error", {
      message: event.message,
      source: event.filename,
      line: event.lineno,
      column: event.colno,
      stack: event.error && event.error.stack ? event.error.stack : null,
    });
  });

  window.addEventListener("unhandledrejection", function (event) {
    var reason = event.reason;
    error("unhandled-promise-rejection", {
      reason: reason && reason.message ? reason.message : String(reason),
      stack: reason && reason.stack ? reason.stack : null,
    });
  });

  function snapshotMessages() {
    var container = document.querySelector("dmc-snackbar");
    var items = container ? Array.prototype.slice.call(container.querySelectorAll("p")) : [];
    var texts = items.map(function (el) {
      return (el.textContent || "").trim();
    });
    var counts = texts.reduce(function (acc, text) {
      acc[text] = (acc[text] || 0) + 1;
      return acc;
    }, {});
    var duplicates = Object.keys(counts)
      .filter(function (key) {
        return counts[key] > 1;
      })
      .map(function (key) {
        return { text: key, count: counts[key] };
      });

    log("messages-snapshot", {
      total: items.length,
      unique: texts.length ? Object.keys(counts).length : 0,
      duplicates: duplicates,
    });
  }

  document.addEventListener("DOMContentLoaded", snapshotMessages);
  document.addEventListener("turbolinks:load", snapshotMessages);

  var messageContainer = document.querySelector("dmc-snackbar");
  if (messageContainer && window.MutationObserver) {
    var observer = new MutationObserver(function (mutations) {
      var added = [];
      Array.prototype.forEach.call(mutations, function (mutation) {
        Array.prototype.forEach.call(mutation.addedNodes || [], function (node) {
          if (node.nodeType === 1 && node.matches("p")) {
            added.push((node.textContent || "").trim());
          }
        });
      });

      if (added.length) {
        log("messages-added", { added: added });
      }
    });
    observer.observe(messageContainer, { childList: true });
  }

  if (window.M && typeof window.M.toast === "function" && !window.M.toast.__cintaDevPatched) {
    var originalToast = window.M.toast;
    var seenToasts = {};
    var duplicateWindowMs = 2000;
    window.M.toast = function () {
      var args = Array.prototype.slice.call(arguments);
      var content = args[0] && args[0].html ? args[0].html : args[0];
      var now = Date.now();
      var previous = seenToasts[content];
      var isDuplicate = previous && now - previous < duplicateWindowMs;
      seenToasts[content] = now;
      log("materialize-toast", {
        content: content,
        duplicate: !!isDuplicate,
        sinceLastMs: previous ? now - previous : null,
      });
      return originalToast.apply(this, arguments);
    };
    window.M.toast.__cintaDevPatched = true;
  }
})();
