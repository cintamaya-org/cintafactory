(function () {
  var MIN_QUERY_LENGTH = 3;
  var DEBOUNCE_MS = 220;

  function debounce(fn, wait) {
    var timeoutId = null;
    return function () {
      var args = arguments;
      var context = this;
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(function () {
        fn.apply(context, args);
      }, wait);
    };
  }

  function renderMessage(container, message) {
    container.innerHTML = '<p class="topbar-search__results-empty"></p>';
    var messageNode = container.querySelector(".topbar-search__results-empty");
    messageNode.textContent = message;
    container.hidden = false;
  }

  function renderResults(container, results) {
    if (!results.length) {
      renderMessage(container, "Aucun résultat.");
      return;
    }
    var html = '<ul class="topbar-search__results-list">';
    results.forEach(function (result) {
      var typeLabel = result.type === "application" ? "Application" : "DAT";
      html += '<li class="topbar-search__result-item">';
      html += '<a class="topbar-search__result-link" href="' + result.url + '">';
      html += '<span class="topbar-search__result-main">';
      html += '<span class="topbar-search__result-label"></span>';
      html += '<span class="topbar-search__result-subtitle"></span>';
      html += "</span>";
      html += '<span class="topbar-search__result-badge">' + typeLabel + "</span>";
      html += "</a>";
      html += "</li>";
    });
    html += "</ul>";
    container.innerHTML = html;
    var labelNodes = container.querySelectorAll(".topbar-search__result-label");
    var subtitleNodes = container.querySelectorAll(".topbar-search__result-subtitle");
    results.forEach(function (result, index) {
      if (labelNodes[index]) {
        labelNodes[index].textContent = result.label || "";
      }
      if (subtitleNodes[index]) {
        subtitleNodes[index].textContent = result.subtitle || "";
      }
    });
    container.hidden = false;
  }

  function initTopbarSearch() {
    var input = document.getElementById("topbar-search");
    var resultContainer = document.getElementById("topbar-search-results");
    var applicationFilter = document.getElementById("topbar-search-filter-applications");
    var datFilter = document.getElementById("topbar-search-filter-dats");
    if (!input || !resultContainer || !applicationFilter || !datFilter) {
      return;
    }
    if (input.dataset.topbarSearchInitialized === "1") {
      return;
    }
    input.dataset.topbarSearchInitialized = "1";

    var endpoint = input.dataset.searchUrl || "";
    var abortController = null;

    function closeResults() {
      resultContainer.hidden = true;
      resultContainer.innerHTML = "";
    }

    function currentFilters() {
      return {
        applications: applicationFilter.checked,
        dats: datFilter.checked,
      };
    }

    function fetchResults() {
      var query = (input.value || "").trim();
      var filters = currentFilters();

      if (!query.length) {
        closeResults();
        return;
      }
      if (!filters.applications && !filters.dats) {
        renderMessage(resultContainer, "Sélectionnez au moins un filtre.");
        return;
      }
      if (query.length < MIN_QUERY_LENGTH) {
        renderMessage(resultContainer, "Saisissez au moins 3 caractères.");
        return;
      }
      if (!endpoint) {
        closeResults();
        return;
      }

      if (abortController) {
        abortController.abort();
      }
      abortController = new AbortController();

      var params = new URLSearchParams();
      params.set("q", query);
      params.set("applications", filters.applications ? "1" : "0");
      params.set("dats", filters.dats ? "1" : "0");

      fetch(endpoint + "?" + params.toString(), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal: abortController.signal,
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("search-request-failed");
          }
          return response.json();
        })
        .then(function (payload) {
          renderResults(resultContainer, payload.results || []);
        })
        .catch(function (error) {
          if (error && error.name === "AbortError") {
            return;
          }
          renderMessage(resultContainer, "Impossible de charger les résultats.");
        });
    }

    var debouncedFetch = debounce(fetchResults, DEBOUNCE_MS);
    function onInputChanged() {
      var query = (input.value || "").trim();
      var filters = currentFilters();
      if (!query.length) {
        closeResults();
        return;
      }
      if (!filters.applications && !filters.dats) {
        renderMessage(resultContainer, "Sélectionnez au moins un filtre.");
        return;
      }
      if (query.length < MIN_QUERY_LENGTH) {
        renderMessage(resultContainer, "Saisissez au moins 3 caractères.");
        return;
      }
      renderMessage(resultContainer, "Recherche en cours...");
      debouncedFetch();
    }

    input.addEventListener("input", onInputChanged);
    input.addEventListener("focus", function () {
      if ((input.value || "").trim().length) {
        onInputChanged();
      }
    });
    applicationFilter.addEventListener("change", onInputChanged);
    datFilter.addEventListener("change", onInputChanged);
    document.addEventListener("click", function (event) {
      if (event.target.closest(".topbar-search")) {
        return;
      }
      closeResults();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeResults();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", initTopbarSearch);
  document.addEventListener("turbolinks:load", initTopbarSearch);
})();
