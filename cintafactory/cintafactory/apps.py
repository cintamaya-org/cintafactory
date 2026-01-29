from __future__ import annotations

from django.apps import AppConfig


class CintaFactoryConfig(AppConfig):
    name = "cintafactory"

    def ready(self) -> None:
        from .rate_limit import ensure_limit_config_exists
        from .theming import ensure_theme_structure_exists
        from .upload_limit import ensure_upload_config_exists

        ensure_limit_config_exists()
        ensure_theme_structure_exists()
        ensure_upload_config_exists()
