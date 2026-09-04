from __future__ import annotations

from django.conf import settings


def frontend_dev_logger(_request):
    return {
        "frontend_dev_logger_enabled": bool(settings.DEBUG),
    }
