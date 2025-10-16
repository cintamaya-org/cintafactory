from django.apps import AppConfig
from material.frontend.apps import ModuleMixin

class DatConfig(ModuleMixin, AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dat"  # or "cintafactory.dat" if inside project package
    verbose_name = "DAT Management"

    icon = "<i class='material-icons'>topic</i>"
    order = 30
    base_template = "material/frontend/base_module.html"
