import json
import logging
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from cintafactory.operations.slo_baseline import emit_baseline_metric
from cintafactory.url_safety import is_http_url

logger = logging.getLogger(__name__)


def enqueue_likec4_export(storage_path: str, *, source: str | None = None) -> bool:
    started_at = perf_counter()

    def _emit(success: bool, outcome: str) -> None:
        emit_baseline_metric(
            "export.likec4.enqueue",
            duration_ms=(perf_counter() - started_at) * 1000.0,
            success=success,
            dimensions={
                "outcome": outcome,
                "source": source or "",
            },
        )

    if not storage_path:
        _emit(False, "invalid_storage_path")
        return False
    if not getattr(settings, "LIKEC4_EXPORT_ENABLED", False):
        _emit(False, "disabled")
        return False
    export_url = getattr(settings, "LIKEC4_EXPORT_URL", "").strip()
    if not export_url:
        logger.warning("LikeC4 export skipped: LIKEC4_EXPORT_URL is not configured.")
        _emit(False, "missing_url")
        return False
    if not is_http_url(export_url):
        logger.warning("LikeC4 export skipped: LIKEC4_EXPORT_URL must be http(s).")
        _emit(False, "invalid_url")
        return False

    payload = {
        "storage_path": storage_path,
        "source": source or "",
        "requested_at": timezone.now().isoformat(),
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    api_token = getattr(settings, "LIKEC4_API_TOKEN", "")
    if api_token:
        headers["X-LikeC4-Token"] = api_token
    timeout = int(getattr(settings, "LIKEC4_EXPORT_TIMEOUT", 60))
    try:
        request = Request(export_url, data=body, headers=headers, method="POST")
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status < 200 or status >= 300:
                resp_body = response.read().decode("utf-8", errors="ignore")
                logger.warning(
                    "LikeC4 export request failed for %s: status=%s body=%s",
                    storage_path,
                    status,
                    resp_body[:200],
                )
                _emit(False, "http_status")
                return False
        _emit(True, "ok")
        return True
    except HTTPError as exc:  # pragma: no cover - best effort export
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body_text = ""
        logger.warning(
            "LikeC4 export request failed for %s: status=%s body=%s",
            storage_path,
            exc.code,
            body_text[:200],
        )
        _emit(False, "http_error")
        return False
    except Exception as exc:  # pragma: no cover - best effort enqueue
        logger.warning("LikeC4 export request failed for %s: %s", storage_path, exc)
        _emit(False, "exception")
        return False
