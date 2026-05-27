from __future__ import annotations

import json
from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase


class HealthViewsTests(SimpleTestCase):
    def test_health_live_returns_alive(self):
        response = self.client.get("/health/live")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "alive")

    @mock.patch("cintafactory.operations.views_health.overall_ready", return_value=(True, {"database": True}))
    def test_health_ready_returns_200_when_ready(self, _overall_ready):
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ready")

    @mock.patch("cintafactory.operations.views_health.overall_ready", return_value=(False, {"database": False}))
    def test_health_ready_returns_503_when_not_ready(self, _overall_ready):
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "not_ready")

    @mock.patch("cintafactory.operations.views_health.render_prometheus_metrics", return_value="cinta_web_requests_total 1\n")
    def test_metrics_endpoint_returns_prometheus_text(self, _render_metrics):
        response = self.client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response["Content-Type"])
        self.assertIn("cinta_web_requests_total", response.content.decode("utf-8"))


class CheckRuntimeDependenciesCommandTests(SimpleTestCase):
    @mock.patch("cintafactory.management.commands.check_runtime_dependencies.overall_ready")
    def test_command_passes_when_ready(self, overall_ready):
        overall_ready.return_value = (True, {"database": True, "queue": True})
        out = StringIO()
        call_command("check_runtime_dependencies", "--profile", "web", "--json-output", stdout=out)
        payload = json.loads(out.getvalue().strip())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["profile"], "web")

    @mock.patch("cintafactory.management.commands.check_runtime_dependencies.overall_ready")
    def test_command_fails_when_not_ready(self, overall_ready):
        overall_ready.return_value = (False, {"database": False, "queue": True})
        with self.assertRaises(CommandError):
            call_command("check_runtime_dependencies", "--profile", "worker")

    @mock.patch("cintafactory.management.commands.export_runtime_metrics.render_prometheus_metrics")
    def test_export_runtime_metrics_command_outputs_metrics(self, render_metrics):
        render_metrics.return_value = "cinta_dependency_up{dependency=\"database\"} 1\n"
        out = StringIO()
        call_command("export_runtime_metrics", stdout=out)
        self.assertIn("cinta_dependency_up", out.getvalue())
