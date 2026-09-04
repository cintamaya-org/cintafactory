from django.apps import AppConfig


class DatViewflowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dat_viewflow"
    verbose_name = "DAT Viewflow"

    def ready(self):
        from .config import ensure_dat_viewflow_template_exists

        ensure_dat_viewflow_template_exists()
        from . import signals  # noqa: F401
