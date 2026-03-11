from __future__ import annotations

from unittest import mock

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from .attachments import scan_file_with_clamav


class ClamAVBaselineTests(SimpleTestCase):
    @override_settings(CLAMAV_HOST="clamav", CLAMAV_PORT=3310, CLAMAV_TIMEOUT=1, CLAMAV_RETRY_COUNT=0)
    @mock.patch("dat.attachments.emit_baseline_metric")
    @mock.patch("dat.attachments._probe_clamav")
    @mock.patch("dat.attachments._scan_file_with_scan_command")
    def test_scan_emits_ok_metric(self, scan_command, _probe, emit_metric):
        scan_command.return_value = b"/tmp/upload: OK\n"
        uploaded = SimpleUploadedFile("safe.txt", b"safe payload", content_type="text/plain")

        scan_file_with_clamav(uploaded)

        emit_metric.assert_called_once()
        _, kwargs = emit_metric.call_args
        self.assertEqual(kwargs["dimensions"]["outcome"], "ok")
        self.assertTrue(kwargs["success"])

    @override_settings(CLAMAV_HOST="clamav", CLAMAV_PORT=3310, CLAMAV_TIMEOUT=1, CLAMAV_RETRY_COUNT=0)
    @mock.patch("dat.attachments.emit_baseline_metric")
    @mock.patch("dat.attachments._probe_clamav")
    @mock.patch("dat.attachments._scan_file_with_scan_command")
    def test_scan_emits_infected_metric(self, scan_command, _probe, emit_metric):
        scan_command.return_value = b"/tmp/upload: Eicar-Test-Signature FOUND\n"
        uploaded = SimpleUploadedFile("bad.txt", b"infected", content_type="text/plain")

        with self.assertRaises(ValidationError):
            scan_file_with_clamav(uploaded)

        emit_metric.assert_called_once()
        _, kwargs = emit_metric.call_args
        self.assertEqual(kwargs["dimensions"]["outcome"], "infected")
        self.assertFalse(kwargs["success"])
