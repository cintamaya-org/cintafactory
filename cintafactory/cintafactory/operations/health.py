from __future__ import annotations

import socket
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import connections

from ..models import AsyncJob


def _http_reachable(url: str, timeout: int = 3) -> bool:
    target = (url or "").strip()
    if not target:
        return False
    request = Request(target, method="HEAD")
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 0) or 0)
            return 200 <= status < 500
    except HTTPError as exc:
        # Some internal health probes intentionally return 4xx for incomplete
        # requests (for example HEAD /export). Treat any non-5xx as reachable.
        return 200 <= int(getattr(exc, "code", 0) or 0) < 500
    except Exception:
        return False


def _db_ready() -> bool:
    try:
        connection = connections["default"]
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("select 1")
            cursor.fetchone()
        return True
    except Exception:
        return False


def _queue_ready() -> bool:
    try:
        AsyncJob.objects.order_by("-created_at").values_list("id", flat=True).first()
        return True
    except Exception:
        return False


def _clamav_ready(timeout: int = 2) -> bool:
    host = str(getattr(settings, "CLAMAV_HOST", "clamav") or "clamav")
    port = int(getattr(settings, "CLAMAV_PORT", 3310) or 3310)
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(b"PING\n")
            response = sock.recv(256).decode("utf-8", errors="replace")
            return "PONG" in response
    except Exception:
        return False


def _seaweedfs_ready() -> bool:
    base = str(getattr(settings, "SEAWEEDFS_FILER_URL", "") or "").rstrip("/")
    if not base:
        return False
    # Use root endpoint because it is lightweight and always available on a healthy filer.
    return _http_reachable(f"{base}/", timeout=3)


def _drawio_exporter_ready() -> bool:
    drawio_export_url = str(getattr(settings, "DRAWIO_EXPORT_URL", "") or "").strip()
    if drawio_export_url:
        parts = urlsplit(drawio_export_url)
        if parts.scheme and parts.netloc:
            return _http_reachable(drawio_export_url, timeout=3)
    drawio_base = str(getattr(settings, "DRAWIO_BASE_URL", "") or "").rstrip("/")
    if not drawio_base:
        return False
    return _http_reachable(f"{drawio_base}/", timeout=3)


def _likec4_exporter_ready() -> bool:
    enabled = bool(getattr(settings, "LIKEC4_EXPORT_ENABLED", False))
    if not enabled:
        return True
    export_url = str(getattr(settings, "LIKEC4_EXPORT_URL", "") or "").strip()
    if not export_url:
        return False
    return _http_reachable(export_url, timeout=3)


def collect_readiness(profile: str = "web") -> dict[str, bool]:
    checks = {
        "database": _db_ready(),
        "queue": _queue_ready(),
    }
    if profile in {"web", "worker"}:
        checks["seaweedfs"] = _seaweedfs_ready()
        checks["clamav"] = _clamav_ready()
        checks["drawio_exporter"] = _drawio_exporter_ready()
        checks["likec4_exporter"] = _likec4_exporter_ready()
    return checks


def overall_ready(profile: str = "web") -> tuple[bool, dict[str, bool]]:
    checks = collect_readiness(profile=profile)
    return all(checks.values()), checks
