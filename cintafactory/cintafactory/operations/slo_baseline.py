from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from django.conf import settings

from .observability import inc_counter

logger = logging.getLogger("cintafactory.slo")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _path_group(path: str) -> str:
    if path.startswith("/diagrams/drawio/proxy/") or path.startswith("/diagrams/likec4/editor/"):
        return "proxy"
    if path.startswith("/api/"):
        return "api"
    return "web"


def _status_group(status_code: int) -> str:
    if status_code >= 500:
        return "5xx"
    if status_code >= 400:
        return "4xx"
    if status_code >= 300:
        return "3xx"
    if status_code >= 200:
        return "2xx"
    return "other"


def emit_baseline_metric(metric: str, *, duration_ms: float, success: bool, dimensions: Mapping[str, Any] | None = None) -> None:
    payload = {
        "metric": metric,
        "duration_ms": round(_as_float(duration_ms), 3),
        "success": bool(success),
    }
    if dimensions:
        payload.update({key: value for key, value in dimensions.items() if value is not None})
    inc_counter(
        "cinta_baseline_events_total",
        labels={
            "metric": metric,
            "success": str(bool(success)).lower(),
            "outcome": payload.get("outcome", "none"),
        },
    )
    logger.info("slo_baseline_metric", extra={"extra_data": payload})


def emit_web_request_baseline(
    request,
    *,
    duration_ms: float,
    status_code: int,
    success: bool,
    error_type: str | None = None,
) -> None:
    path = getattr(request, "path", "") or ""
    if getattr(settings, "SLO_BASELINE_IGNORE_STATIC", True):
        static_url = getattr(settings, "STATIC_URL", "") or ""
        media_url = getattr(settings, "MEDIA_URL", "") or ""
        if static_url and path.startswith(static_url):
            return
        if media_url and path.startswith(media_url):
            return
    path_group = _path_group(path)
    status_group = _status_group(_as_int(status_code))
    method = getattr(request, "method", None) or "UNKNOWN"
    emit_baseline_metric(
        "web.request",
        duration_ms=duration_ms,
        success=success,
        dimensions={
            "path_group": path_group,
            "status_code": _as_int(status_code),
            "status_group": status_group,
            "method": method,
            "error_type": error_type,
        },
    )
    inc_counter(
        "cinta_web_requests_total",
        labels={
            "path_group": path_group,
            "status_group": status_group,
            "method": str(method).upper(),
        },
    )
