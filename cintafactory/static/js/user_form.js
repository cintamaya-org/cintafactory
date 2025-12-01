(function () {
  function applyRoleFilter(form) {
    var groupField = form.querySelector('[data-group-selector]');
    var roleField = form.querySelector('[data-role-selector]');
    if (!groupField || !roleField) {
      return;
    }

    function runFilter() {
      var selectedDirection = "";
      var selectedOption = groupField.options[groupField.selectedIndex];
      if (selectedOption) {
        selectedDirection = selectedOption.getAttribute("data-direction") || "";
      }
      var options = roleField.options;
      var hasVisible = false;
      Array.prototype.forEach.call(options, function (option) {
        if (!option.value) {
          option.hidden = false;
          option.disabled = false;
          return;
        }
        var optionDirection = option.getAttribute("data-direction") || "";
        var matches;
        if (!selectedDirection) {
          matches = optionDirection === "";
        } else {
          matches = optionDirection === selectedDirection;
        }
        option.hidden = !matches;
        option.disabled = !matches;
        if (matches) {
          hasVisible = true;
        }
      });

      if (roleField.value) {
        var currentOption = roleField.options[roleField.selectedIndex];
        if (currentOption && currentOption.disabled) {
          roleField.value = "";
        }
      }

      roleField.disabled = !hasVisible;
    }

    groupField.addEventListener("change", runFilter);
    runFilter();
  }

  function initAll() {
    var forms = document.querySelectorAll("form");
    Array.prototype.forEach.call(forms, function (form) {
      if (form.__cintaRoleFilterReady) {
        return;
      }
      if (!form.querySelector('[data-group-selector]') || !form.querySelector('[data-role-selector]')) {
        return;
      }
      form.__cintaRoleFilterReady = true;
      applyRoleFilter(form);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
  document.addEventListener("turbolinks:load", initAll);
})();
