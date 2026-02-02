from __future__ import annotations

import json
import os
import tempfile
from unittest import mock
from urllib.error import HTTPError

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from . import admin_config, rate_limit, upload_limit, url_safety
from .middleware import (
    DynamicCsrfTrustedOriginsMiddleware,
    LoggingContextMiddleware,
    RateLimitMiddleware,
)
from .seaweedfs_storage import SeaweedFSStorage


class ConfigFileTests(SimpleTestCase):
    def setUp(self) -> None:
        upload_limit._config_cache = None
        upload_limit._config_mtime = None
        admin_config._config_cache = None
        admin_config._config_mtime = None
        rate_limit._config_cache = None
        rate_limit._config_mtime = None

    def test_load_upload_config_defaults_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with override_settings(BASE_DIR=tmp_dir):
                conf_dir = os.path.join(tmp_dir, "conf")
                os.makedirs(conf_dir, exist_ok=True)
                path = os.path.join(conf_dir, "upload.json")
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("{invalid json")
                config = upload_limit.load_upload_config()
        self.assertEqual(config["max_file_size_mb"], upload_limit.DEFAULT_UPLOAD_CONFIG["max_file_size_mb"])

    def test_load_upload_config_coerces_int(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with override_settings(BASE_DIR=tmp_dir):
                conf_dir = os.path.join(tmp_dir, "conf")
                os.makedirs(conf_dir, exist_ok=True)
                path = os.path.join(conf_dir, "upload.json")
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps({"max_file_size_mb": "123MB"}))
                config = upload_limit.load_upload_config()
        self.assertEqual(config["max_file_size_mb"], 123)

    def test_load_admin_config_sanitizes_cipher_url(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with override_settings(BASE_DIR=tmp_dir):
                conf_dir = os.path.join(tmp_dir, "conf")
                os.makedirs(conf_dir, exist_ok=True)
                path = os.path.join(conf_dir, "admin.json")
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps({"cipher_url": " /bad//path/ "}))
                config = admin_config.load_admin_config()
        self.assertEqual(config["cipher_url"], "badpath")

    def test_load_rate_limit_supports_alt_keys(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with override_settings(BASE_DIR=tmp_dir):
                conf_dir = os.path.join(tmp_dir, "conf")
                os.makedirs(conf_dir, exist_ok=True)
                path = os.path.join(conf_dir, "limit.json")
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "app": {"limit_per_ip_per_minute": "42"},
                                "api": {"limit_per_ip_per_minute": "84"},
                                "is_static_excluded": "false",
                                "is_admin_excluded": "true",
                            }
                        )
                    )
                config = rate_limit.load_limit_config()
        self.assertEqual(config["app"]["limit_per_ip_per_minute"], 42)
        self.assertEqual(config["api"]["limit_per_ip_per_minute"], 84)
        self.assertFalse(config["is_static_exluded"])
        self.assertTrue(config["is_admin_exluded"])


class UrlSafetyTests(SimpleTestCase):
    def test_is_http_url_accepts_http_https(self):
        self.assertTrue(url_safety.is_http_url("http://example.com"))
        self.assertTrue(url_safety.is_http_url("https://example.com/path"))

    def test_is_http_url_rejects_invalid(self):
        self.assertFalse(url_safety.is_http_url(""))
        self.assertFalse(url_safety.is_http_url("ftp://example.com"))
        self.assertFalse(url_safety.is_http_url("/relative/path"))


class SeaweedFSStorageTests(SimpleTestCase):
    @override_settings(
        SEAWEEDFS_FILER_URL="http://files.example.com",
        SEAWEEDFS_PUBLIC_URL="https://cdn.example.com",
        SEAWEEDFS_BASE_DIR="root",
        SEAWEEDFS_TIMEOUT=5,
    )
    def test_build_url_uses_base_dir_and_public_url(self):
        storage = SeaweedFSStorage()
        self.assertEqual(
            storage.url("docs/plan.pdf"),
            "https://cdn.example.com/root/docs/plan.pdf",
        )

    def test_init_rejects_invalid_url(self):
        with self.assertRaises(ValueError):
            SeaweedFSStorage(base_url="ftp://bad.example.com")

    @override_settings(SEAWEEDFS_FILER_URL="http://files.example.com")
    @mock.patch("cintafactory.seaweedfs_storage.urlopen")
    def test_exists_returns_false_on_404(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="http://files.example.com/missing",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
        storage = SeaweedFSStorage()
        self.assertFalse(storage.exists("missing"))

    @override_settings(SEAWEEDFS_FILER_URL="http://files.example.com")
    @mock.patch("cintafactory.seaweedfs_storage.urlopen")
    def test_delete_ignores_404(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="http://files.example.com/missing",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
        storage = SeaweedFSStorage()
        storage.delete("missing")

    @override_settings(SEAWEEDFS_FILER_URL="http://files.example.com")
    @mock.patch("cintafactory.seaweedfs_storage.urlopen")
    def test_get_modified_time_requires_header(self, mock_urlopen):
        class Response:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        mock_urlopen.return_value = Response()
        storage = SeaweedFSStorage()
        with self.assertRaises(NotImplementedError):
            storage.get_modified_time("file.txt")


class MiddlewareTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_logging_context_uses_request_id_header(self):
        def get_response(request):
            return HttpResponse("ok", status=201)

        middleware = LoggingContextMiddleware(get_response)
        request = self.factory.get(
            "/",
            HTTP_X_REQUEST_ID="req-123",
            HTTP_X_CORRELATION_ID="corr-456",
        )
        with mock.patch("cintafactory.middleware.bind_request_context") as bind_ctx, mock.patch(
            "cintafactory.middleware.clear_request_context"
        ) as clear_ctx:
            response = middleware(request)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(request.request_id, "req-123")
        self.assertTrue(bind_ctx.called)
        clear_ctx.assert_called_once()

    @override_settings(ALLOWED_HOSTS=["example.com"], CSRF_TRUSTED_ORIGINS=[])
    def test_dynamic_csrf_trusted_origins_updates_allowed_hosts(self):
        def get_response(request):
            return HttpResponse("ok")

        middleware = DynamicCsrfTrustedOriginsMiddleware(get_response)
        request = self.factory.get("/", HTTP_ORIGIN="https://example.com")
        middleware(request)
        self.assertIn("https://example.com", set(settings.CSRF_TRUSTED_ORIGINS))
        self.assertIn("http://example.com", set(settings.CSRF_TRUSTED_ORIGINS))

    @override_settings(STATIC_URL="/static/")
    def test_rate_limit_excludes_static(self):
        def get_response(request):
            return HttpResponse("ok")

        middleware = RateLimitMiddleware(get_response)
        request = self.factory.get("/static/app.css")
        with mock.patch("cintafactory.middleware.load_limit_config") as load_config:
            load_config.return_value = {"is_static_exluded": True, "is_admin_exluded": True, "api": {}, "app": {}}
            response = middleware(request)
        self.assertEqual(response.status_code, 200)

    @override_settings(STATIC_URL="/static/")
    def test_rate_limit_blocks_api_requests(self):
        cache.clear()

        def get_response(request):
            return HttpResponse("ok")

        middleware = RateLimitMiddleware(get_response)
        request = self.factory.get("/api/items", REMOTE_ADDR="10.0.0.1")
        with mock.patch("cintafactory.middleware.load_limit_config") as load_config:
            load_config.return_value = {
                "is_static_exluded": True,
                "is_admin_exluded": True,
                "api": {"limit_per_ip_per_minute": 1},
                "app": {"limit_per_ip_per_minute": 100, "limit_per_user_per_minute": 100},
            }
            first = middleware(request)
            second = middleware(request)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
