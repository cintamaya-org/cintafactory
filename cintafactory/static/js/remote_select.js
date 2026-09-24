(function () {
  var DEBOUNCE_MS = 250;
  var DEFAULT_MAX_RESULTS = 30;

  function debounce(callback, delay) {
    var timeoutId = null;
    return function () {
      var args = arguments;
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(function () {
        callback.apply(null, args);
      }, delay);
    };
  }

  function initRemoteSelect(select) {
    if (select.dataset.remoteSelectInitialized === "1") {
      return;
    }
    select.dataset.remoteSelectInitialized = "1";
    select.classList.add("browser-default", "remote-select__control");

    var endpoint = select.dataset.remoteSelectUrl || "";
    if (!endpoint) {
      return;
    }
    var configuredLimit = Number.parseInt(select.dataset.remoteSelectLimit || "", 10);
    var maxResults = Number.isFinite(configuredLimit) && configuredLimit > 0
      ? Math.min(configuredLimit, DEFAULT_MAX_RESULTS)
      : DEFAULT_MAX_RESULTS;
    var emptyOption = Array.from(select.options).find(function (option) {
      return option.value === "";
    });
    var emptyLabel = emptyOption ? emptyOption.text : "---------";

    var search = document.createElement("input");
    search.type = "search";
    search.autocomplete = "off";
    search.className = "remote-select__search";
    search.placeholder = select.dataset.remoteSelectPlaceholder || "Rechercher...";
    search.setAttribute("aria-label", search.placeholder);

    var status = document.createElement("small");
    status.className = "remote-select__status text-muted";
    status.setAttribute("aria-live", "polite");

    select.parentNode.insertBefore(search, select);
    select.insertAdjacentElement("afterend", status);

    var abortController = null;

    function replaceOptions(options, hasMore) {
      var selectedValue = select.value;
      var selectedOption = Array.from(select.options).find(function (option) {
        return option.value === selectedValue;
      });
      var selectedLabel = selectedOption ? selectedOption.text : "";
      var normalized = Array.isArray(options) ? options.slice(0, maxResults) : [];

      select.replaceChildren();
      select.add(new Option(emptyLabel, ""));

      var insertedValues = new Set();
      if (selectedValue) {
        select.add(new Option(selectedLabel || selectedValue, selectedValue, true, true));
        insertedValues.add(selectedValue);
      }
      normalized.forEach(function (item) {
        if (insertedValues.size >= maxResults) {
          return;
        }
        var value = String(item.value !== undefined ? item.value : item.id || "");
        if (!value || insertedValues.has(value)) {
          return;
        }
        var label = String(item.label !== undefined ? item.label : item.name || value);
        select.add(new Option(label, value));
        insertedValues.add(value);
      });
      select.value = selectedValue || "";
      status.textContent = insertedValues.size + " résultat" + (insertedValues.size > 1 ? "s" : "")
        + (hasMore ? " — affinez la recherche" : "");
      select.dispatchEvent(new Event("remote-options-loaded", { bubbles: true }));
    }

    function fetchOptions() {
      if (abortController) {
        abortController.abort();
      }
      abortController = new AbortController();
      status.textContent = "Recherche en cours...";
      var params = new URLSearchParams();
      params.set("q", (search.value || "").trim());

      fetch(endpoint + "?" + params.toString(), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal: abortController.signal,
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("remote-select-request-failed");
          }
          return response.json();
        })
        .then(function (payload) {
          replaceOptions(payload.options || [], Boolean(payload.has_more));
        })
        .catch(function (error) {
          if (error && error.name === "AbortError") {
            return;
          }
          status.textContent = "Chargement impossible.";
        });
    }

    var debouncedFetch = debounce(fetchOptions, DEBOUNCE_MS);
    search.addEventListener("input", debouncedFetch);
    fetchOptions();
  }

  function initRemoteSelects() {
    document.querySelectorAll("select[data-remote-select-url]").forEach(initRemoteSelect);
  }

  document.addEventListener("DOMContentLoaded", initRemoteSelects);
  document.addEventListener("turbolinks:load", initRemoteSelects);
})();
