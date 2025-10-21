from django.apps import AppConfig
from material.frontend.apps import ModuleMixin

class UsersConfig(ModuleMixin, AppConfig):
    name = "users"
    verbose_name = "Gestion des utilisateurs"
    icon = "<i class='material-icons'>supervisor_account</i>"
    default_auto_field = "django.db.models.BigAutoField"
