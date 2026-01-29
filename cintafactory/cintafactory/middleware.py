from __future__ import annotations

import uuid
from typing import Callable
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.http.request import validate_host

from .logging_utils import bind_request_context, clear_request_context
from .rate_limit import load_limit_config


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


class RateLimitMiddleware:
    """
    Simple request throttling for both app pages and API endpoints.

    Uses the Django cache backend to track per-minute counters. The limits and
    exclusions are loaded from conf/limit.json.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        config = load_limit_config()
        if self._is_excluded(request, config):
            return self.get_response(request)

        is_api = request.path.startswith("/api/")
        window_seconds = 60
        client_ip = self._get_client_ip(request)

        if is_api:
            api_limit = config["api"]["limit_per_ip_per_minute"]
            if self._is_over_limit("api", "ip", client_ip, api_limit, window_seconds):
                return self._rate_limited_response(is_api=True)
            return self.get_response(request)

        app_ip_limit = config["app"]["limit_per_ip_per_minute"]
        if self._is_over_limit("app", "ip", client_ip, app_ip_limit, window_seconds):
            return self._rate_limited_response(is_api=False)

        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            app_user_limit = config["app"]["limit_per_user_per_minute"]
            user_key = f"{user.pk}"
            if self._is_over_limit("app", "user", user_key, app_user_limit, window_seconds):
                return self._rate_limited_response(is_api=False)

        return self.get_response(request)

    def _is_excluded(self, request: HttpRequest, config: dict) -> bool:
        path = request.path
        if config.get("is_static_exluded") and settings.STATIC_URL:
            if path.startswith(settings.STATIC_URL):
                return True
        if config.get("is_admin_exluded"):
            if path.startswith("/admin/"):
                return True
        return False

    def _get_client_ip(self, request: HttpRequest) -> str:
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")

    def _is_over_limit(
        self,
        scope: str,
        bucket: str,
        key_part: str,
        limit: int,
        window_seconds: int,
    ) -> bool:
        if not limit or limit <= 0:
            return False
        cache_key = f"rate:{scope}:{bucket}:{key_part}"
        count = self._increment(cache_key, window_seconds)
        return count > limit

    def _increment(self, cache_key: str, window_seconds: int) -> int:
        try:
            added = cache.add(cache_key, 1, timeout=window_seconds)
            if added:
                return 1
            return cache.incr(cache_key)
        except Exception:
            current = cache.get(cache_key) or 0
            try:
                current = int(current) + 1
            except (TypeError, ValueError):
                current = 1
            cache.set(cache_key, current, timeout=window_seconds)
            return current

    def _rate_limited_response(self, is_api: bool) -> HttpResponse:
        if is_api:
            return JsonResponse({"detail": "Rate limit exceeded."}, status=429)
        return HttpResponse("Rate limit exceeded.", status=429)
