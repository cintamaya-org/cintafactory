# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

from django.apps import AppConfig
from material.frontend.apps import ModuleMixin


class DiagramsConfig(ModuleMixin, AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "diagrams"
    verbose_name = "Diagrammes"
    icon = "<i class='material-icons'>schema</i>"
    order = 50
    base_template = "material/frontend/base_module.html"
