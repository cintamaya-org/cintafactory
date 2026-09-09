# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

from django.apps import AppConfig
from material.frontend.apps import ModuleMixin

class UsersConfig(ModuleMixin, AppConfig):
    name = "users"
    verbose_name = "Gestion des utilisateurs"
    icon = "<i class='material-icons'>supervisor_account</i>"
    default_auto_field = "django.db.models.BigAutoField"
    order = 10
    base_template = "material/frontend/base_module.html"

    def has_perm(self, user):
        """Expose the module only to Django superusers."""
        return bool(user and user.is_authenticated and getattr(user, "is_superuser", False))
