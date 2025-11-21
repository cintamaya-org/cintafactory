(function () {
  function applyRoleFilter(form) {
    var directionField = form.querySelector('[data-direction-selector]');
    var roleField = form.querySelector('[data-role-selector]');
    if (!directionField || !roleField) {
      return;
    }

    function runFilter() {
      var selectedDirection = directionField.value || "";
      var options = roleField.options;
      var hasVisible = false;
      Array.prototype.forEach.call(options, function (option) {
        if (!option.value) {
          option.hidden = false;
          option.disabled = false;
          return;
        }
        var isAdminRole = option.getAttribute("data-role-admin") === "1";
        var optionDirection = option.getAttribute("data-direction");
        var matches;
        if (!selectedDirection) {
          matches = isAdminRole;
        } else {
          matches = isAdminRole || optionDirection === selectedDirection;
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

    directionField.addEventListener("change", runFilter);
    runFilter();
  }

  function initAll() {
    var forms = document.querySelectorAll("form");
    Array.prototype.forEach.call(forms, function (form) {
      if (form.__cintaRoleFilterReady) {
        return;
      }
      if (!form.querySelector('[data-direction-selector]') || !form.querySelector('[data-role-selector]')) {
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
