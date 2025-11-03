from __future__ import annotations

import uuid
from typing import Callable

from django.http import HttpRequest, HttpResponse

from .logging_utils import bind_request_context, clear_request_context


class LoggingContextMiddleware:
    """
    Populate thread-local logging context for each request.

    Extracts correlation identifiers from headers when provided and falls
    back to a generated UUID. The context is cleared once the response cycle
    has completed to avoid leaking data between requests.
    """

    header_names = ("X-Request-ID", "X-Correlation-ID")

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = self._extract_request_id(request)
        user = getattr(request, "user", None)
        bind_request_context(
            request_id=request_id,
            path=request.path,
            method=request.method,
            user_id=getattr(user, "pk", None) if getattr(user, "is_authenticated", False) else None,
            username=getattr(user, "username", None) if getattr(user, "is_authenticated", False) else None,
        )
        request.request_id = request_id  # type: ignore[attr-defined]
        try:
            response = self.get_response(request)
            status_code = getattr(response, "status_code", None)
            if status_code is not None:
                bind_request_context(status_code=status_code)
            return response
        finally:
            clear_request_context()

    def _extract_request_id(self, request: HttpRequest) -> str:
        for header in self.header_names:
            if header in request.headers:
                value = request.headers.get(header)
                if value:
                    return value
        return uuid.uuid4().hex

