from __future__ import annotations

from pathlib import Path

from django.conf import settings


def ensure_conf_dir() -> Path:
    conf_dir = Path(settings.BASE_DIR) / "conf"
    conf_dir.mkdir(parents=True, exist_ok=True)
    return conf_dir
