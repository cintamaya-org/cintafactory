from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from django.conf import settings

from cintafactory.conf_utils import ensure_conf_dir


def _template_path() -> Path:
    return Path(__file__).with_name("section_blueprints.json")


def _conf_path() -> Path:
    conf_dir = ensure_conf_dir()
    return conf_dir / "section_blueprints.json"


def ensure_section_blueprints_file_exists() -> None:
    conf_path = _conf_path()
    if conf_path.exists():
        return
    template_path = _template_path()
    conf_path.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")


def _load_section_blueprints() -> Tuple[Dict[str, Any], ...]:
    conf_path = _conf_path()
    if not conf_path.exists():
        ensure_section_blueprints_file_exists()
    config_path = conf_path if conf_path.exists() else _template_path()
    try:
        with config_path.open(encoding="utf-8") as fp:
            data = json.load(fp)
    except json.JSONDecodeError:
        with _template_path().open(encoding="utf-8") as fp:
            data = json.load(fp)
    return tuple(data)


SECTION_BLUEPRINTS: Tuple[Dict[str, Any], ...] = _load_section_blueprints()

__all__ = ["SECTION_BLUEPRINTS", "ensure_section_blueprints_file_exists"]
