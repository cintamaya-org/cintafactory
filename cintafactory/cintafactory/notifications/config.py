from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Iterable

from cintafactory.conf_utils import ensure_conf_dir

DEFAULT_EXTERNAL_NOTIFICATION_CONFIG: list[Any] = []

_config_lock = threading.Lock()
_config_cache: list[Any] | None = None
_config_mtime: float | None = None


def _config_path() -> Path:
    conf_dir = ensure_conf_dir()
    return conf_dir / "external_notifications.json"


def ensure_external_notifications_config_exists() -> None:
    path = _config_path()
    if path.exists():
        return
    path.write_text(json.dumps(DEFAULT_EXTERNAL_NOTIFICATION_CONFIG, indent=2) + "\n")


def load_external_notifications_config() -> list[Any]:
    global _config_cache, _config_mtime

    path = _config_path()
    if not path.exists():
        ensure_external_notifications_config_exists()

    try:
        stat = path.stat()
    except OSError:
        return DEFAULT_EXTERNAL_NOTIFICATION_CONFIG.copy()

    with _config_lock:
        if _config_cache is None or _config_mtime != stat.st_mtime:
            try:
                raw = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                raw = []
            _config_cache = _normalize_config(raw)
            _config_mtime = stat.st_mtime
        return list(_config_cache)


def _normalize_config(raw: Any) -> list[Any]:
    if not isinstance(raw, list):
        return []
    cleaned: list[Any] = []
    for entry in raw:
        if isinstance(entry, str):
            cleaned.append(entry)
        elif isinstance(entry, dict):
            cleaned.append(entry)
    return cleaned
