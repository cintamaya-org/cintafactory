(function () {
  function refreshSelect(select) {
    if (!window.M || !M.FormSelect) {
      return;
    }
    var instance = M.FormSelect.getInstance(select);
    if (instance) {
      instance.destroy();
    }
    M.FormSelect.init(select);
  }

  function getSelectedDirection(select) {
    var selectedOption = select.options[select.selectedIndex];
    if (!selectedOption) {
      return "";
    }
    return selectedOption.getAttribute("data-direction") || "";
  }

  function cloneOptions(select) {
    return Array.prototype.map.call(select.options, function (option) {
      return option.cloneNode(true);
    });
  }

  function getDirectionForValue(options, value) {
    var direction = "";
    Array.prototype.some.call(options, function (option) {
      if (option.value === value) {
        direction = option.getAttribute("data-direction") || "";
        return true;
      }
      return false;
    });
    return direction;
  }

  function rebuildOptions(select, sourceOptions, shouldShow) {
    var selectedValue = select.value;
    while (select.options.length) {
      select.remove(0);
    }

    Array.prototype.forEach.call(sourceOptions, function (option) {
      if (!option.value || shouldShow(option)) {
        select.add(option.cloneNode(true));
      }
    });

    select.value = selectedValue;
    if (select.value !== selectedValue) {
      select.value = "";
    }
    select.disabled = false;
    refreshSelect(select);
  }

  function applyRoleFilter(form) {
    var groupField = form.querySelector('[data-group-selector]');
    var roleField = form.querySelector('[data-role-selector]');
    if (!groupField || !roleField) {
      return;
    }

    var groupOptions = cloneOptions(groupField);
    var roleOptions = cloneOptions(roleField);

    function runFilter() {
      var selectedRoleDirection = getDirectionForValue(roleOptions, roleField.value);

      rebuildOptions(groupField, groupOptions, function (option) {
        if (!roleField.value) {
          return true;
        }
        var optionDirection = option.getAttribute("data-direction") || "";
        if (selectedRoleDirection) {
          return optionDirection === selectedRoleDirection;
        }
        return optionDirection === "";
      });

      var selectedGroupDirection = getSelectedDirection(groupField);

      rebuildOptions(roleField, roleOptions, function (option) {
        var optionDirection = option.getAttribute("data-direction") || "";
        if (selectedGroupDirection) {
          return optionDirection === selectedGroupDirection;
        }
        return true;
      });
    }

    groupField.addEventListener("change", runFilter);
    roleField.addEventListener("change", runFilter);
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
