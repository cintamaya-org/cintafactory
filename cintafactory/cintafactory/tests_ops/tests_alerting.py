from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from ..operations.alerting import AlertEvent, evaluate_runtime_alerts
from ..models import AsyncJob


class RuntimeAlertingRuleTests(TestCase):
    @override_settings(
        ALERT_EXPORT_QUEUE_OLDEST_WARNING_SECONDS=60,
        ALERT_EXPORT_QUEUE_OLDEST_CRITICAL_SECONDS=120,
    )
    @mock.patch("cintafactory.operations.alerting.collect_readiness", return_value={"seaweedfs": True})
    @mock.patch("cintafactory.operations.alerting._db_saturation_ratio", return_value=None)
    def test_export_queue_backlog_alert_fires(self, _db_ratio, _collect_readiness):
        job = AsyncJob.objects.create(job_type="exports.likec4", status=AsyncJob.Status.QUEUED, payload={"storage_path": "x"})
        old_time = timezone.now() - timedelta(seconds=240)
        AsyncJob.objects.filter(id=job.id).update(created_at=old_time)
        alerts = evaluate_runtime_alerts(now=timezone.now())
        export_alerts = [item for item in alerts if item.code == "export_queue_backlog"]
        self.assertEqual(len(export_alerts), 1)
        self.assertEqual(export_alerts[0].severity, "critical")

    @override_settings(
        ALERT_SCAN_MIN_SAMPLES=10,
        ALERT_SCAN_FAILURE_WARNING_RATE=0.03,
        ALERT_SCAN_FAILURE_CRITICAL_RATE=0.50,
        ALERT_SCAN_TIMEOUT_WARNING_COUNT=3,
        ALERT_SCAN_TIMEOUT_CRITICAL_COUNT=99,
    )
    @mock.patch("cintafactory.operations.alerting.collect_readiness", return_value={"seaweedfs": True})
    @mock.patch("cintafactory.operations.alerting._db_saturation_ratio", return_value=None)
    def test_scan_failures_alert_fires_from_counter_rates(self, _db_ratio, _collect_readiness):
        def counter_side_effect(name: str, **labels: str) -> float:
            if name != "cinta_baseline_events_total":
                return 0.0
            if labels == {"metric": "upload.clamav.scan"}:
                return 100.0
            if labels == {"metric": "upload.clamav.scan", "success": "false"}:
                return 5.0
            if labels == {"metric": "upload.clamav.scan", "outcome": "scanner_timeout"}:
                return 2.0
            if labels == {"metric": "upload.clamav.scan", "outcome": "scanner_unavailable"}:
                return 1.0
            return 0.0

        with mock.patch("cintafactory.operations.alerting._counter_sum", side_effect=counter_side_effect):
            alerts = evaluate_runtime_alerts(now=timezone.now())
        scan_alerts = [item for item in alerts if item.code == "scan_failures_timeouts"]
        self.assertEqual(len(scan_alerts), 1)
        self.assertEqual(scan_alerts[0].severity, "warning")

    @mock.patch("cintafactory.operations.alerting.collect_readiness", return_value={"seaweedfs": False})
    @mock.patch("cintafactory.operations.alerting._db_saturation_ratio", return_value=None)
    @mock.patch("cintafactory.operations.alerting._counter_sum", return_value=0.0)
    def test_seaweedfs_unavailable_alert_fires_critical(self, _counter_sum, _db_ratio, _collect_readiness):
        alerts = evaluate_runtime_alerts(now=timezone.now())
        seaweed_alerts = [item for item in alerts if item.code == "seaweedfs_unavailable"]
        self.assertEqual(len(seaweed_alerts), 1)
        self.assertEqual(seaweed_alerts[0].severity, "critical")


class RuntimeAlertCommandTests(SimpleTestCase):
    @mock.patch("cintafactory.management.commands.check_runtime_alerts.evaluate_runtime_alerts")
    def test_command_outputs_json(self, evaluate_alerts):
        evaluate_alerts.return_value = [
            AlertEvent(
                code="export_queue_backlog",
                severity="warning",
                summary="Export queue oldest job age breached threshold.",
                route="slack:ops",
                runbook="params_dev/PLAN5_ALERTING_RUNBOOK.md#export-queue-backlog",
                details={"queued_exports": 5},
            )
        ]
        out = StringIO()
        call_command("check_runtime_alerts", "--json-output", "--fail-on", "none", stdout=out)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual(payload["alert_count"], 1)
        self.assertEqual(payload["alerts"][0]["code"], "export_queue_backlog")

    @mock.patch("cintafactory.management.commands.check_runtime_alerts.evaluate_runtime_alerts")
    def test_command_fails_on_critical_alerts(self, evaluate_alerts):
        evaluate_alerts.return_value = [
            AlertEvent(
                code="db_saturation",
                severity="critical",
                summary="Database connection saturation is above threshold.",
                route="pagerduty:oncall",
                runbook="params_dev/PLAN5_ALERTING_RUNBOOK.md#database-saturation",
                details={"saturation_ratio": 0.99},
            )
        ]
        with self.assertRaises(CommandError):
            call_command("check_runtime_alerts", "--fail-on", "critical")
