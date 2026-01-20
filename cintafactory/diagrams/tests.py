import json
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import DrawIODiagram
from .validation import sanitize_diagram_title, validate_drawio_xml


class DiagramTitleValidationTest(SimpleTestCase):
    def test_normalizes_whitespace(self):
        self.assertEqual(sanitize_diagram_title("  Mon   diagramme  "), "Mon diagramme")

    def test_rejects_html_like_characters(self):
        with self.assertRaises(ValidationError):
            sanitize_diagram_title("<schema>")

    def test_rejects_control_characters(self):
        with self.assertRaises(ValidationError):
            sanitize_diagram_title("Schema\x08Name")


class DrawioXmlValidationTest(SimpleTestCase):
    def test_accepts_mxfile_payload(self):
        xml = "<mxfile><diagram id=\"test\"></diagram></mxfile>"
        self.assertEqual(validate_drawio_xml(xml), xml)

    def test_rejects_non_drawio_root(self):
        with self.assertRaises(ValidationError):
            validate_drawio_xml("<svg></svg>")

    def test_rejects_doctype(self):
        with self.assertRaises(ValidationError):
            validate_drawio_xml("<!DOCTYPE html><mxfile></mxfile>")


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

    @patch("diagrams.views._regenerate_drawio_thumbnail")
    def test_imports_valid_drawio_file(self, mock_regenerate):
        def fake_regen(diagram, xml_payload):
            diagram.thumbnail.save("thumb.png", ContentFile(b"fake image"), save=False)
            diagram.save(update_fields=["thumbnail"])
            return True

        mock_regenerate.side_effect = fake_regen
        self.client.force_login(self.user)
        xml = "<mxGraphModel><root><mxCell id=\"0\" /></root></mxGraphModel>"
        payload = SimpleUploadedFile("schema.drawio", xml.encode("utf-8"), content_type="application/xml")
        response = self.client.post(self.url, {"file": payload})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("thumbnail_url", data.get("diagram", {}))
        self.assertTrue(data["diagram"]["thumbnail_url"].endswith("/views/thumb.png"))
        mock_regenerate.assert_called_once()
        args, _ = mock_regenerate.call_args
        self.assertEqual(args[1], xml)
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

    @patch("diagrams.views._regenerate_drawio_thumbnail")
    def test_regenerates_missing_thumbnail_on_view(self, mock_regenerate):
        self.client.force_login(self.user)
        self.diagram.thumbnail.save("thumb.png", ContentFile(b"stale"), save=True)
        try:
            self.diagram.thumbnail.storage.delete(self.diagram.thumbnail.name)
        except Exception:
            pass

        def fake_regen(diagram, xml_payload):
            diagram.thumbnail.save("thumb.png", ContentFile(b"fresh"), save=False)
            diagram.save(update_fields=["thumbnail"])
            return True

        mock_regenerate.side_effect = fake_regen
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["diagram"]["thumbnail_url"].endswith("/views/thumb.png"))
        mock_regenerate.assert_called_once_with(self.diagram, "<mxGraphModel/>")


class LikeC4MetadataAuthTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("diagrams:likec4_metadata")
        self.payload = {
            "path": "diagrams/123/likec4.c4",
            "size": 10,
            "content_type": "text/plain",
        }

    def test_requires_auth_or_token(self):
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

    @patch("diagrams.views.enqueue_likec4_export")
    def test_allows_valid_token(self, mock_enqueue):
        mock_enqueue.return_value = False
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
        mock_enqueue.assert_called_once_with(self.payload["path"], source="metadata")

    @patch("diagrams.views.enqueue_likec4_export")
    def test_allows_authenticated_user(self, mock_enqueue):
        mock_enqueue.return_value = False
        user = get_user_model().objects.create_user(username="meta-auth", password="pwd")
        self.client.force_login(user)
        with self.settings(LIKEC4_METADATA_TOKEN="secret-token"):
            response = self.client.post(
                self.url,
                data=json.dumps(self.payload),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))
        mock_enqueue.assert_called_once_with(self.payload["path"], source="metadata")
