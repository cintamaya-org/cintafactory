from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .conf_utils import ensure_conf_dir


DEFAULT_ACTIVE_THEME: dict[str, Any] = {"active": "base"}

DEFAULT_THEME_TOKENS: dict[str, Any] = {
    "name": "cinta-classic",
    "palette": {
        "primary": "#1e88e5",
        "secondary": "#ff6f00",
        "surface": "#f7f8fa",
        "text": "#1f2937",
        "muted": "#6b7280",
        "success": "#2e7d32",
        "warning": "#ed6c02",
        "danger": "#d32f2f",
    },
    "typography": {
        "font_family": "IBM Plex Sans",
        "base_size_px": 14,
        "heading_weight": 600,
    },
    "radius": {"sm": 4, "md": 8, "lg": 12},
}


def ensure_theme_structure_exists() -> None:
    conf_dir = ensure_conf_dir()
    theme_dir = conf_dir / "theming"
    theme_dir.mkdir(parents=True, exist_ok=True)

    active_path = theme_dir / "active.json"
    if not active_path.exists():
        active_path.write_text(json.dumps(DEFAULT_ACTIVE_THEME, indent=2) + "\n")

    base_dir = theme_dir / "base"
    base_dir.mkdir(parents=True, exist_ok=True)
    tokens_path = base_dir / "tokens.json"
    if not tokens_path.exists():
        tokens_path.write_text(json.dumps(DEFAULT_THEME_TOKENS, indent=2) + "\n")
