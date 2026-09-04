from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from django.conf import settings

from .conf_utils import ensure_conf_dir

DEFAULT_LIMIT_CONFIG: dict[str, Any] = {
    "app": {
        "limit_per_ip_per_minute": 500,
        "limit_per_user_per_minute": 50,
    },
    "api": {
        "limit_per_ip_per_minute": 1000,
    },
    "is_static_exluded": True,
    "is_admin_exluded": True,
}

_config_lock = threading.Lock()
_config_cache: dict[str, Any] | None = None
_config_mtime: float | None = None


def _config_path() -> Path:
    conf_dir = ensure_conf_dir()
    return conf_dir / "limit.json"


def ensure_limit_config_exists() -> None:
    path = _config_path()
    if path.exists():
        return
    path.write_text(json.dumps(DEFAULT_LIMIT_CONFIG, indent=2) + "\n")


def load_limit_config() -> dict[str, Any]:
    global _config_cache, _config_mtime

    path = _config_path()
    if not path.exists():
        ensure_limit_config_exists()

    try:
        stat = path.stat()
    except OSError:
        return DEFAULT_LIMIT_CONFIG.copy()

    with _config_lock:
        if _config_cache is None or _config_mtime != stat.st_mtime:
            try:
                raw = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                raw = {}
            _config_cache = _normalize_config(raw)
            _config_mtime = stat.st_mtime
        return _config_cache.copy()


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


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
    defaults = DEFAULT_LIMIT_CONFIG
    app_raw = raw.get("app", {}) if isinstance(raw.get("app"), dict) else {}
    api_raw = raw.get("api", {}) if isinstance(raw.get("api"), dict) else {}

    return {
        "app": {
            "limit_per_ip_per_minute": _coerce_int(
                app_raw.get("limit_per_ip_per_minute"),
                defaults["app"]["limit_per_ip_per_minute"],
            ),
            "limit_per_user_per_minute": _coerce_int(
                app_raw.get("limit_per_user_per_minute"),
                defaults["app"]["limit_per_user_per_minute"],
            ),
        },
        "api": {
            "limit_per_ip_per_minute": _coerce_int(
                api_raw.get("limit_per_ip_per_minute"),
                defaults["api"]["limit_per_ip_per_minute"],
            ),
        },
        "is_static_exluded": _coerce_bool(
            raw.get("is_static_exluded", raw.get("is_static_excluded")),
            defaults["is_static_exluded"],
        ),
        "is_admin_exluded": _coerce_bool(
            raw.get("is_admin_exluded", raw.get("is_admin_excluded")),
            defaults["is_admin_exluded"],
        ),
    }
