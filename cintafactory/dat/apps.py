# dat/apps.py
from django.apps import AppConfig
from material.frontend.apps import ModuleMixin
from material.frontend import Module  # <-- TODO FIX import error

class DatModule(Module):
    """
    Register the 'dat' section with Material Frontend so built-in
    list/detail/change templates know which base template to extend.
    """
    icon = "topic"  # material icon name (e.g. 'description', 'topic', 'assignment')
    order = 30
    base_template = "material/frontend/base_module.html"  # <-- critical

class DatConfig(ModuleMixin, AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dat"
    verbose_name = "DAT Management"
    icon = "<i class='material-icons'>topic</i>"

    # ModuleMixin will register these modules automatically
    modules = [DatModule]

