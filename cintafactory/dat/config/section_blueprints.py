from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple


def _load_section_blueprints() -> Tuple[Dict[str, Any], ...]:
    config_path = Path(__file__).with_name("section_blueprints.json")
    with config_path.open(encoding="utf-8") as fp:
        data = json.load(fp)
    return tuple(data)


SECTION_BLUEPRINTS: Tuple[Dict[str, Any], ...] = _load_section_blueprints()

__all__ = ["SECTION_BLUEPRINTS"]
