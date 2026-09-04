from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from django.conf import settings

from ..conf_utils import ensure_conf_dir

DEFAULT_UPLOAD_CONFIG: dict[str, Any] = {
    "max_file_size_mb": 200,
}

_config_lock = threading.Lock()
_config_cache: dict[str, Any] | None = None
_config_mtime: float | None = None


def _config_path() -> Path:
    conf_dir = ensure_conf_dir()
    return conf_dir / "upload.json"


def ensure_upload_config_exists() -> None:
    path = _config_path()
    if path.exists():
        return
    path.write_text(json.dumps(DEFAULT_UPLOAD_CONFIG, indent=2) + "\n")


def load_upload_config() -> dict[str, Any]:
    global _config_cache, _config_mtime

    path = _config_path()
    if not path.exists():
        ensure_upload_config_exists()

    try:
        stat = path.stat()
    except OSError:
        return DEFAULT_UPLOAD_CONFIG.copy()

    with _config_lock:
        if _config_cache is None or _config_mtime != stat.st_mtime:
            try:
                raw = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                raw = {}
            _config_cache = _normalize_config(raw)
            _config_mtime = stat.st_mtime
        return _config_cache.copy()


def _coerce_int(value: Any, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            try:
                return int(digits)
            except ValueError:
                return default
    return default


def _normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    defaults = DEFAULT_UPLOAD_CONFIG
    return {
        "max_file_size_mb": _coerce_int(
            raw.get("max_file_size_mb"),
            defaults["max_file_size_mb"],
        ),
    }
