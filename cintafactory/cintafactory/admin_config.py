from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .conf_utils import ensure_conf_dir


DEFAULT_ADMIN_CONFIG: dict[str, Any] = {
    "cipher_url": "khtijgdryi",
}

_config_lock = threading.Lock()
_config_cache: dict[str, Any] | None = None
_config_mtime: float | None = None


def _config_path() -> Path:
    conf_dir = ensure_conf_dir()
    return conf_dir / "admin.json"


def ensure_admin_config_exists() -> None:
    path = _config_path()
    if path.exists():
        return
    path.write_text(json.dumps(DEFAULT_ADMIN_CONFIG, indent=2) + "\n")


def load_admin_config() -> dict[str, Any]:
    global _config_cache, _config_mtime

    path = _config_path()
    if not path.exists():
        ensure_admin_config_exists()

    try:
        stat = path.stat()
    except OSError:
        return DEFAULT_ADMIN_CONFIG.copy()

    with _config_lock:
        if _config_cache is None or _config_mtime != stat.st_mtime:
            try:
                raw = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                raw = {}
            _config_cache = _normalize_config(raw)
            _config_mtime = stat.st_mtime
        return _config_cache.copy()


def _normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    cipher = raw.get("cipher_url", DEFAULT_ADMIN_CONFIG["cipher_url"])
    cipher = str(cipher).strip().strip("/")
    cleaned = "".join(ch for ch in cipher if ch.isalnum() or ch in {"-", "_"})
    if not cleaned:
        cleaned = DEFAULT_ADMIN_CONFIG["cipher_url"]
    return {"cipher_url": cleaned}
