from __future__ import annotations

import uuid
from typing import Callable
from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.http.request import validate_host

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


class DynamicCsrfTrustedOriginsMiddleware:
    """
    Ensure CSRF trusted origins keep pace with allowed hosts at runtime.

    The middleware inspects the incoming Origin header and, when it points to
    a host already permitted by ALLOWED_HOSTS, automatically appends both the
    http and https variants to settings.CSRF_TRUSTED_ORIGINS. This allows
    deployments where hostnames change without requiring manual environment
    updates.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        origin = request.META.get("HTTP_ORIGIN")
        if origin:
            self._ensure_origin_allowed(origin)
        return self.get_response(request)

    def _ensure_origin_allowed(self, origin: str) -> None:
        try:
            parsed = urlsplit(origin)
        except ValueError:
            return
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return
        if not validate_host(parsed.hostname, settings.ALLOWED_HOSTS):
            return

        origins = set(settings.CSRF_TRUSTED_ORIGINS)
        netloc = parsed.netloc
        for scheme in ("http", "https"):
            candidate = f"{scheme}://{netloc}"
            origins.add(candidate)
        settings.CSRF_TRUSTED_ORIGINS = sorted(origins)
