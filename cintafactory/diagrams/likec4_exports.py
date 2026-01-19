import json
import logging
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def enqueue_likec4_export(storage_path: str, *, source: str | None = None) -> bool:
    if not storage_path:
        return False
    if not getattr(settings, "LIKEC4_EXPORT_ENABLED", False):
        return False
    export_url = getattr(settings, "LIKEC4_EXPORT_URL", "").strip()
    if not export_url:
        logger.warning("LikeC4 export skipped: LIKEC4_EXPORT_URL is not configured.")
        return False

    payload = {
        "storage_path": storage_path,
        "source": source or "",
        "requested_at": timezone.now().isoformat(),
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
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
                return False
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
        return False
    except Exception as exc:  # pragma: no cover - best effort enqueue
        logger.warning("LikeC4 export request failed for %s: %s", storage_path, exc)
        return False
