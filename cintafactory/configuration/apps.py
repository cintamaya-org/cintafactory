from django.apps import AppConfig
from material.frontend.apps import ModuleMixin


class ConfigurationConfig(ModuleMixin, AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "configuration"
    verbose_name = "Configuration"
    icon = "<i class='material-icons'>settings</i>"
    order = 60
    base_template = "material/frontend/base_module.html"

    def has_perm(self, user):
        """Expose the module only to Django superusers."""
        return bool(user and user.is_authenticated and getattr(user, "is_superuser", False))
