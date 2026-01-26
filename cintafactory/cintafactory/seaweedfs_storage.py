from __future__ import annotations

import logging
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils import timezone

logger = logging.getLogger(__name__)


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
        if not self.base_url:
            raise ValueError("SEAWEEDFS_FILER_URL must be configured to use SeaweedFS storage.")
        if not self.public_url:
            self.public_url = self.base_url

    def _build_path(self, name: str) -> str:
        clean_name = name.lstrip("/")
        if self.base_dir:
            return f"{self.base_dir}/{clean_name}"
        return clean_name

    def _build_url(self, base_url: str, name: str) -> str:
        path = self._build_path(name)
        return f"{base_url}/{quote(path, safe='/')}"

    def _open(self, name: str, mode: str = "rb"):
        url = self._build_url(self.base_url, name)
        try:
            response = urlopen(url, timeout=self.timeout)
        except HTTPError as exc:
            raise FileNotFoundError(name) from exc
        return File(response, name)

    def _save(self, name: str, content):
        url = self._build_url(self.base_url, name)
        data = content.read()
        request = Request(url, data=data, method="PUT")
        request.add_header("Content-Length", str(len(data)))
        content_type = getattr(content, "content_type", "") or "application/octet-stream"
        request.add_header("Content-Type", content_type)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                response.read()
        except (HTTPError, URLError) as exc:
            logger.warning("SeaweedFS upload failed for %s", name)
            raise
        return name

    def delete(self, name: str) -> None:
        url = self._build_url(self.base_url, name)
        request = Request(url, method="DELETE")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                response.read()
        except HTTPError as exc:
            if exc.code == 404:
                return
            raise

    def exists(self, name: str) -> bool:
        url = self._build_url(self.base_url, name)
        request = Request(url, method="HEAD")
        try:
            with urlopen(request, timeout=self.timeout):
                return True
        except HTTPError as exc:
            if exc.code == 404:
                return False
            raise

    def size(self, name: str) -> int:
        url = self._build_url(self.base_url, name)
        request = Request(url, method="HEAD")
        with urlopen(request, timeout=self.timeout) as response:
            length = response.headers.get("Content-Length", "0")
            try:
                return int(length)
            except (TypeError, ValueError):
                return 0

    def get_modified_time(self, name: str):
        url = self._build_url(self.base_url, name)
        request = Request(url, method="HEAD")
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
        return self._build_url(self.public_url, name)

    def get_available_name(self, name: str, max_length: int | None = None) -> str:
        return name

    def deconstruct(self):
        return ("cintafactory.seaweedfs_storage.SeaweedFSStorage", [], {})
