# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from pathlib import Path

from django.conf import settings


def ensure_conf_dir() -> Path:
    conf_dir = Path(settings.BASE_DIR) / "conf"
    conf_dir.mkdir(parents=True, exist_ok=True)
    return conf_dir
