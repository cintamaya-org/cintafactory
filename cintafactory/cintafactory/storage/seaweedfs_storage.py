from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils import timezone

from ..operations.slo_baseline import emit_baseline_metric
from ..url_safety import is_http_url

logger = logging.getLogger(__name__)


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def build_filer_jwt(key: str, path: str, method: str, ttl_seconds: int) -> str:
    if not key:
        return ""
    now = int(time.time())
    header = _base64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _base64url(
        json.dumps(
            {
                "allowed_prefixes": [f"/{path.lstrip('/')}"],
                "allowed_methods": [method.upper()],
                "iat": now,
                "exp": now + max(1, int(ttl_seconds)),
            },
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = _base64url(hmac.new(key.encode(), signing_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def _emit_storage_metric(operation: str, started_at: float, *, success: bool, outcome: str) -> None:
    emit_baseline_metric(
        "storage.seaweedfs.request",
        duration_ms=(time.perf_counter() - started_at) * 1000.0,
        success=success,
        dimensions={
            "operation": operation,
            "outcome": outcome,
        },
    )


class SeaweedFSStorage(Storage):
    def __init__(
        self,
        *,
        base_url: str | None = None,
        public_url: str | None = None,
        base_dir: str | None = None,
        timeout: int | None = None,
    ):
        self.base_url = (base_url or getattr(settings, "SEAWEEDFS_FILER_URL", "")).rstrip("/")
        self.public_url = (public_url or getattr(settings, "SEAWEEDFS_PUBLIC_URL", "")).rstrip("/")
        self.base_dir = (base_dir or getattr(settings, "SEAWEEDFS_BASE_DIR", "")).strip("/")
        self.timeout = int(timeout or getattr(settings, "SEAWEEDFS_TIMEOUT", 30))
        self.write_key = str(getattr(settings, "SEAWEEDFS_JWT_WRITE_KEY", "") or "")
        self.read_key = str(getattr(settings, "SEAWEEDFS_JWT_READ_KEY", "") or "")
        self.jwt_ttl = int(getattr(settings, "SEAWEEDFS_JWT_TTL_SECONDS", 60))
        self.public_jwt_ttl = int(getattr(settings, "SEAWEEDFS_PUBLIC_JWT_TTL_SECONDS", 300))
        if not self.base_url:
            raise ValueError("SEAWEEDFS_FILER_URL must be configured to use SeaweedFS storage.")
        if not is_http_url(self.base_url):
            raise ValueError("SEAWEEDFS_FILER_URL must be an http(s) URL.")
        if not self.public_url:
            self.public_url = self.base_url
        if self.public_url and not is_http_url(self.public_url):
            raise ValueError("SEAWEEDFS_PUBLIC_URL must be an http(s) URL.")

    def _build_path(self, name: str) -> str:
        clean_name = name.lstrip("/")
        if self.base_dir:
            return f"{self.base_dir}/{clean_name}"
        return clean_name

    def _build_url(self, base_url: str, name: str) -> str:
        path = self._build_path(name)
        return f"{base_url}/{quote(path, safe='/')}"

    def _request(self, url: str, name: str, method: str, *, data=None) -> Request:
        request = Request(url, data=data, method=method)
        key = self.write_key if method in {"PUT", "POST", "DELETE"} else self.read_key
        token = build_filer_jwt(key, self._build_path(name), method, self.jwt_ttl)
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        return request

    def _open(self, name: str, mode: str = "rb"):
        started_at = time.perf_counter()
        url = self._build_url(self.base_url, name)
        try:
            response = urlopen(self._request(url, name, "GET"), timeout=self.timeout)
            _emit_storage_metric("open", started_at, success=True, outcome="ok")
        except HTTPError as exc:
            outcome = "not_found" if exc.code == 404 else "http_error"
            _emit_storage_metric("open", started_at, success=False, outcome=outcome)
            raise FileNotFoundError(name) from exc
        except URLError:
            _emit_storage_metric("open", started_at, success=False, outcome="url_error")
            raise
        return File(response, name)

    def _save(self, name: str, content):
        started_at = time.perf_counter()
        url = self._build_url(self.base_url, name)
        data = content.read()
        request = self._request(url, name, "PUT", data=data)
        request.add_header("Content-Length", str(len(data)))
        content_type = getattr(content, "content_type", "") or "application/octet-stream"
        request.add_header("Content-Type", content_type)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                response.read()
            _emit_storage_metric("save", started_at, success=True, outcome="ok")
        except (HTTPError, URLError) as exc:
            logger.warning("SeaweedFS upload failed for %s", name)
            _emit_storage_metric("save", started_at, success=False, outcome=type(exc).__name__)
            raise
        return name

    def delete(self, name: str) -> None:
        started_at = time.perf_counter()
        url = self._build_url(self.base_url, name)
        request = self._request(url, name, "DELETE")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                response.read()
            _emit_storage_metric("delete", started_at, success=True, outcome="ok")
        except HTTPError as exc:
            if exc.code == 404:
                _emit_storage_metric("delete", started_at, success=True, outcome="not_found")
                return
            _emit_storage_metric("delete", started_at, success=False, outcome="http_error")
            raise
        except URLError:
            _emit_storage_metric("delete", started_at, success=False, outcome="url_error")
            raise

    def exists(self, name: str) -> bool:
        started_at = time.perf_counter()
        url = self._build_url(self.base_url, name)
        request = self._request(url, name, "HEAD")
        try:
            with urlopen(request, timeout=self.timeout):
                _emit_storage_metric("exists", started_at, success=True, outcome="ok")
                return True
        except HTTPError as exc:
            if exc.code == 404:
                _emit_storage_metric("exists", started_at, success=True, outcome="not_found")
                return False
            _emit_storage_metric("exists", started_at, success=False, outcome="http_error")
            raise
        except URLError:
            _emit_storage_metric("exists", started_at, success=False, outcome="url_error")
            raise

    def size(self, name: str) -> int:
        url = self._build_url(self.base_url, name)
        request = self._request(url, name, "HEAD")
        with urlopen(request, timeout=self.timeout) as response:
            length = response.headers.get("Content-Length", "0")
            try:
                return int(length)
            except (TypeError, ValueError):
                return 0

    def get_modified_time(self, name: str):
        url = self._build_url(self.base_url, name)
        request = self._request(url, name, "HEAD")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                header = response.headers.get("Last-Modified")
        except HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(name) from exc
            raise
        if not header:
            raise NotImplementedError("SeaweedFS response did not include Last-Modified.")
        parsed = parsedate_to_datetime(header)
        if not parsed:
            raise NotImplementedError("SeaweedFS Last-Modified header could not be parsed.")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.utc)
        return parsed

    def url(self, name: str) -> str:
        url = self._build_url(self.public_url, name)
        token = build_filer_jwt(self.read_key, self._build_path(name), "GET", self.public_jwt_ttl)
        if not token:
            return url
        return f"{url}?jwt={quote(token, safe='')}"

    def get_available_name(self, name: str, max_length: int | None = None) -> str:
        return name

    def deconstruct(self):
        return ("cintafactory.storage.seaweedfs_storage.SeaweedFSStorage", [], {})
