from __future__ import annotations

from django.core.exceptions import RequestDataTooBig
from django.core.files.uploadhandler import FileUploadHandler

from .upload_limit import load_upload_config


class PerFileSizeLimitUploadHandler(FileUploadHandler):
    """
    Enforce a maximum size per uploaded file for all incoming requests.
    """

    def __init__(self, request=None) -> None:
        super().__init__(request)
        config = load_upload_config()
        max_mb = config.get("max_file_size_mb", 200)
        try:
            max_mb_int = int(max_mb)
        except (TypeError, ValueError):
            max_mb_int = 200
        self.max_size_bytes = max_mb_int * 1024 * 1024
        self._current_size = 0

    def new_file(
        self,
        field_name,
        file_name,
        content_type,
        content_length,
        charset=None,
        content_type_extra=None,
    ) -> None:
        super().new_file(
            field_name,
            file_name,
            content_type,
            content_length,
            charset=charset,
            content_type_extra=content_type_extra,
        )
        self._current_size = 0
        if content_length and self.max_size_bytes and content_length > self.max_size_bytes:
            raise RequestDataTooBig("Uploaded file exceeds the maximum allowed size.")

    def receive_data_chunk(self, raw_data, start) -> bytes | None:
        self._current_size += len(raw_data)
        if self.max_size_bytes and self._current_size > self.max_size_bytes:
            raise RequestDataTooBig("Uploaded file exceeds the maximum allowed size.")
        return raw_data
