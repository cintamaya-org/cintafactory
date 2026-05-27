import json
import shutil
import tempfile
from unittest.mock import patch
from urllib.error import HTTPError

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import DrawIODiagram
from .validation import sanitize_diagram_title


class DiagramTitleValidationTest(SimpleTestCase):
    def test_normalizes_whitespace(self):
        self.assertEqual(sanitize_diagram_title("  Mon   diagramme  "), "Mon diagramme")

    def test_rejects_html_like_characters(self):
        with self.assertRaises(ValidationError):
            sanitize_diagram_title("<schema>")

    def test_rejects_control_characters(self):
        with self.assertRaises(ValidationError):
            sanitize_diagram_title("Schema\x08Name")


class DiagramImportViewTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._media_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self._media_dir, ignore_errors=True))
        self._media_override = self.settings(MEDIA_ROOT=self._media_dir)
        self._media_override.enable()
        self.user = get_user_model().objects.create_user(username="importer", password="pwd")
        self.diagram = DrawIODiagram.objects.create(title="Test diagram", owner=self.user)
        self.url = reverse("diagrams:import_xml", args=[self.diagram.pk])

    def tearDown(self) -> None:
        self._media_override.disable()
        super().tearDown()

    def test_rejects_invalid_payload_type(self):
        self.client.force_login(self.user)
        payload = SimpleUploadedFile("diagram.svg", b"<svg></svg>", content_type="image/svg+xml")
        response = self.client.post(self.url, {"file": payload})
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data.get("error"), "invalid_diagram")

    @patch("diagrams.views.enqueue_drawio_export_job")
    def test_imports_valid_drawio_file(self, mock_enqueue_job):
        mock_enqueue_job.return_value = type("Job", (), {"id": "33333333-3333-3333-3333-333333333333", "status": "queued"})()
        self.client.force_login(self.user)
        xml = "<mxGraphModel><root><mxCell id=\"0\" /></root></mxGraphModel>"
        payload = SimpleUploadedFile("schema.drawio", xml.encode("utf-8"), content_type="application/xml")
        response = self.client.post(self.url, {"file": payload})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("thumbnail_url", data.get("diagram", {}))
        self.assertIsNone(data["diagram"]["thumbnail_url"])
        self.assertIn("job", data)
        self.assertEqual(data["job"]["status"], "queued")
        mock_enqueue_job.assert_called_once()
        self.diagram.refresh_from_db()
        self.assertEqual(self.diagram.read_xml(), xml)


class DiagramViewerContextTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._media_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self._media_dir, ignore_errors=True))
        self._media_override = self.settings(MEDIA_ROOT=self._media_dir)
        self._media_override.enable()
        self.user = get_user_model().objects.create_user(username="viewer", password="pwd")
        self.diagram = DrawIODiagram.objects.create(title="Diag", owner=self.user)
        self.diagram.write_xml("<mxGraphModel/>")
        self.url = reverse("diagrams:viewer_context", args=[self.diagram.pk])

    def tearDown(self) -> None:
        self._media_override.disable()
        super().tearDown()

    @patch("diagrams.views.enqueue_drawio_export_job")
    def test_enqueues_missing_thumbnail_on_view(self, mock_enqueue_job):
        self.client.force_login(self.user)
        mock_enqueue_job.return_value = type("Job", (), {"id": "44444444-4444-4444-4444-444444444444", "status": "queued"})()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["diagram"]["thumbnail_url"])
        self.assertIn("job", data)
        self.assertEqual(data["job"]["status"], "queued")
        mock_enqueue_job.assert_called_once_with(
            self.diagram.pk,
            xml_payload="<mxGraphModel/>",
            requested_by=self.user,
            source="viewer_context",
        )


class DiagramSaveXmlAsyncTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = get_user_model().objects.create_user(username="save-xml-user", password="pwd")
        self.diagram = DrawIODiagram.objects.create(title="Save xml diagram", owner=self.user)
        self.url = reverse("diagrams:save_xml", args=[self.diagram.pk])

    @patch("diagrams.views.enqueue_drawio_export_job")
    def test_save_xml_enqueues_drawio_job(self, mock_enqueue_job):
        mock_enqueue_job.return_value = type("Job", (), {"id": "66666666-6666-6666-6666-666666666666", "status": "queued"})()
        self.client.force_login(self.user)
        xml = "<mxGraphModel><root><mxCell id=\"1\" /></root></mxGraphModel>"
        response = self.client.post(
            self.url,
            data=json.dumps({"xml": xml}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("job", payload)
        self.assertEqual(payload["job"]["status"], "queued")
        mock_enqueue_job.assert_called_once_with(
            self.diagram.pk,
            xml_payload=xml,
            requested_by=self.user,
            source="save_xml",
        )


class LikeC4MetadataAuthTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("diagrams:likec4_metadata")
        self.payload = {
            "path": "diagrams/123/likec4.c4",
            "size": 10,
            "content_type": "text/plain",
        }

    @patch("diagrams.views.emit_baseline_metric")
    def test_requires_auth_or_token(self, emit_metric):
        with self.settings(LIKEC4_METADATA_TOKEN="secret-token"):
            response = self.client.post(
                self.url,
                data=json.dumps(self.payload),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data.get("error"), "unauthorized")
        emit_metric.assert_called_once()
        _, kwargs = emit_metric.call_args
        self.assertEqual(kwargs["dimensions"]["surface"], "likec4_metadata")
        self.assertEqual(kwargs["dimensions"]["outcome"], "unauthorized")
        self.assertFalse(kwargs["success"])

    @patch("diagrams.views.enqueue_likec4_export_job")
    def test_allows_valid_token(self, mock_enqueue):
        mock_enqueue.return_value = type("Job", (), {"id": "11111111-1111-1111-1111-111111111111", "status": "queued"})()
        payload = dict(self.payload, token="secret-token")
        with self.settings(LIKEC4_METADATA_TOKEN="secret-token"):
            response = self.client.post(
                self.url,
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("job", data)
        self.assertEqual(data["job"]["status"], "queued")
        mock_enqueue.assert_called_once()

    @patch("diagrams.views.enqueue_likec4_export_job")
    def test_allows_authenticated_user(self, mock_enqueue):
        mock_enqueue.return_value = type("Job", (), {"id": "22222222-2222-2222-2222-222222222222", "status": "queued"})()
        user = get_user_model().objects.create_user(username="meta-auth", password="pwd")
        self.client.force_login(user)
        with self.settings(LIKEC4_METADATA_TOKEN="secret-token"):
            response = self.client.post(
                self.url,
                data=json.dumps(self.payload),
                content_type="application/json",
                HTTP_ORIGIN="http://testserver",
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("job", data)
        self.assertEqual(data["job"]["status"], "queued")
        mock_enqueue.assert_called_once()

    @patch("diagrams.views.enqueue_likec4_export_job")
    def test_authenticated_user_requires_same_origin(self, mock_enqueue):
        mock_enqueue.return_value = type("Job", (), {"id": "33333333-3333-3333-3333-333333333333", "status": "queued"})()
        user = get_user_model().objects.create_user(username="meta-cross-site", password="pwd")
        self.client.force_login(user)
        with self.settings(LIKEC4_METADATA_TOKEN="secret-token"):
            response = self.client.post(
                self.url,
                data=json.dumps(self.payload),
                content_type="application/json",
                HTTP_ORIGIN="http://evil.example",
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get("error"), "csrf_failed")
        mock_enqueue.assert_not_called()


class LikeC4ExportBaselineTests(SimpleTestCase):
    @patch("diagrams.likec4_exports.emit_baseline_metric")
    def test_enqueue_emits_success_metric(self, emit_metric):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with self.settings(
            LIKEC4_EXPORT_ENABLED=True,
            LIKEC4_EXPORT_URL="https://example.local/export",
            LIKEC4_EXPORT_TIMEOUT=1,
            LIKEC4_API_TOKEN="",
        ):
            with patch("diagrams.likec4_exports.urlopen", return_value=Response()):
                from .likec4_exports import enqueue_likec4_export

                result = enqueue_likec4_export("diagrams/1/likec4.c4", source="test")

        self.assertTrue(result)
        emit_metric.assert_called_once()
        _, kwargs = emit_metric.call_args
        self.assertEqual(kwargs["dimensions"]["outcome"], "ok")

    @patch("diagrams.likec4_exports.emit_baseline_metric")
    def test_enqueue_emits_failure_metric(self, emit_metric):
        with self.settings(
            LIKEC4_EXPORT_ENABLED=True,
            LIKEC4_EXPORT_URL="https://example.local/export",
            LIKEC4_EXPORT_TIMEOUT=1,
            LIKEC4_API_TOKEN="",
        ):
            with patch(
                "diagrams.likec4_exports.urlopen",
                side_effect=HTTPError(
                    url="https://example.local/export",
                    code=503,
                    msg="Service Unavailable",
                    hdrs=None,
                    fp=None,
                ),
            ):
                from .likec4_exports import enqueue_likec4_export

                result = enqueue_likec4_export("diagrams/1/likec4.c4", source="test")

        self.assertFalse(result)
        emit_metric.assert_called_once()
        _, kwargs = emit_metric.call_args
        self.assertEqual(kwargs["dimensions"]["outcome"], "http_error")


class ProxySecurityTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = get_user_model().objects.create_user(username="proxy-user", password="pwd")

    def test_drawio_proxy_blocks_absolute_url_path(self):
        with self.settings(DRAWIO_BASE_URL="https://drawio.example.test"):
            with patch("diagrams.views.urlopen") as mock_urlopen:
                response = self.client.get("/diagrams/drawio/proxy/http://evil.example/")
        self.assertEqual(response.status_code, 404)
        mock_urlopen.assert_not_called()

    def test_drawio_proxy_blocks_non_allowlisted_upstream_host(self):
        with self.settings(
            DRAWIO_BASE_URL="https://drawio.example.test",
            DRAWIO_PROXY_ALLOWED_UPSTREAM_HOSTS="allowed.internal",
        ):
            with patch("diagrams.views.urlopen") as mock_urlopen:
                response = self.client.get(reverse("diagrams:drawio_proxy_root"))
        self.assertEqual(response.status_code, 404)
        mock_urlopen.assert_not_called()

    def test_likec4_proxy_blocks_path_traversal(self):
        self.client.force_login(self.user)
        with self.settings(LIKEC4_EDITOR_URL="https://likec4.example.test"):
            with patch("diagrams.views.urlopen") as mock_urlopen:
                response = self.client.get("/diagrams/likec4/editor/..%2fsecrets")
        self.assertEqual(response.status_code, 404)
        mock_urlopen.assert_not_called()

    def test_likec4_proxy_blocks_oversized_post_payload(self):
        self.client.force_login(self.user)
        with self.settings(
            LIKEC4_EDITOR_URL="https://likec4.example.test",
            LIKEC4_PROXY_MAX_BODY_BYTES=4,
        ):
            with patch("diagrams.views.urlopen") as mock_urlopen:
                response = self.client.post(
                    reverse("diagrams:likec4_proxy_root"),
                    data=b"abcdef",
                    content_type="application/json",
                    HTTP_ORIGIN="http://testserver",
                )
        self.assertEqual(response.status_code, 413)
        mock_urlopen.assert_not_called()

    def test_likec4_proxy_uses_editor_csp(self):
        class Response:
            status = 200
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b"<html></html>"

        self.client.force_login(self.user)
        with self.settings(LIKEC4_EDITOR_URL="https://likec4.example.test"):
            with patch("diagrams.views.urlopen", return_value=Response()):
                response = self.client.get(reverse("diagrams:likec4_proxy_root"))

        self.assertEqual(response.status_code, 200)
        csp = response["Content-Security-Policy"]
        self.assertIn("'unsafe-inline'", csp)
        self.assertIn("'unsafe-eval'", csp)
        self.assertIn("https://cdn.jsdelivr.net", csp)

    def test_likec4_proxy_post_adds_api_token(self):
        class Response:
            status = 200
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"ok": true}'

        self.client.force_login(self.user)
        with self.settings(LIKEC4_EDITOR_URL="https://likec4.example.test", LIKEC4_API_TOKEN="proxy-token"):
            with patch("diagrams.views.urlopen", return_value=Response()) as mock_urlopen:
                response = self.client.post(
                    reverse("diagrams:likec4_proxy", args=["save"]),
                    data=b'{"content": ""}',
                    content_type="application/json",
                    HTTP_ORIGIN="http://testserver",
                )

        self.assertEqual(response.status_code, 200)
        forwarded_request = mock_urlopen.call_args.args[0]
        self.assertEqual(forwarded_request.get_header("X-likec4-token"), "proxy-token")

    def test_likec4_proxy_blocks_cross_origin_post(self):
        self.client.force_login(self.user)
        with self.settings(LIKEC4_EDITOR_URL="https://likec4.example.test"):
            with patch("diagrams.views.urlopen") as mock_urlopen:
                response = self.client.post(
                    reverse("diagrams:likec4_proxy", args=["save"]),
                    data=b'{"content": ""}',
                    content_type="application/json",
                    HTTP_ORIGIN="http://evil.example",
                )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get("error"), "csrf_failed")
        mock_urlopen.assert_not_called()
