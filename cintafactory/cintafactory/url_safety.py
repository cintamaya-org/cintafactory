# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from urllib.parse import urlsplit

ALLOWED_SCHEMES = {"http", "https"}


def is_http_url(url: str) -> bool:
    if not url:
        return False
    try:
        parts = urlsplit(url)
    except Exception:
        return False
    if not parts.scheme or parts.scheme.lower() not in ALLOWED_SCHEMES:
        return False
    if not parts.netloc:
        return False
    return True
