from django.apps import AppConfig
from material.frontend.apps import ModuleMixin


class AccountConfig(ModuleMixin, AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "account"
    verbose_name = "My Account"

    icon = "<i class='material-icons'>person</i>"
    order = 20
    base_template = "material/frontend/base_module.html"

    @property
    def installed(self):
        """Always expose the account module without requiring DB toggle."""
        return True

    def has_perm(self, user):
        """Hide the module from side menus while keeping URLs reachable."""
        return False
