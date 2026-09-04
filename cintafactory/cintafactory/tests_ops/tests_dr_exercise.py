from __future__ import annotations

import json
from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from ..operations.alerting import AlertEvent
from ..operations.dr_exercise import run_dr_game_day_exercise


class DrExerciseTests(SimpleTestCase):
    @mock.patch("cintafactory.operations.dr_exercise.evaluate_runtime_alerts", return_value=[])
    @mock.patch("cintafactory.operations.dr_exercise.run_backup_dr_validation", return_value={"ok": True, "checks": {}, "errors": []})
    def test_dr_exercise_passes_when_objectives_met(self, _run_validation, _alerts):
        report = run_dr_game_day_exercise(
            postgres_restore_seconds=300,
            seaweedfs_restore_seconds=240,
            data_loss_minutes=2,
            target_rto_seconds=600,
            target_rpo_minutes=5,
        )
        self.assertTrue(report["ok"])
        self.assertEqual(report["gaps"], [])

    @mock.patch(
        "cintafactory.operations.dr_exercise.evaluate_runtime_alerts",
        return_value=[
            AlertEvent(
                code="seaweedfs_errors",
                severity="warning",
                summary="SeaweedFS operation errors exceeded thresholds.",
                route="slack:ops",
                runbook="params_dev/PLAN5_ALERTING_RUNBOOK.md#seaweedfs-errors",
                details={},
            )
        ],
    )
    @mock.patch("cintafactory.operations.dr_exercise.run_backup_dr_validation", return_value={"ok": False, "checks": {}, "errors": ["bad"]})
    def test_dr_exercise_reports_gaps_on_failure(self, _run_validation, _alerts):
        report = run_dr_game_day_exercise(
            postgres_restore_seconds=1800,
            seaweedfs_restore_seconds=1500,
            data_loss_minutes=20,
            target_rto_seconds=900,
            target_rpo_minutes=15,
        )
        self.assertFalse(report["ok"])
        self.assertGreaterEqual(len(report["gaps"]), 2)
        self.assertIn("seaweedfs_errors", report["alerts_referenced"])

    @mock.patch("cintafactory.operations.dr_exercise.evaluate_runtime_alerts", side_effect=RuntimeError("missing table"))
    @mock.patch("cintafactory.operations.dr_exercise.run_backup_dr_validation", return_value={"ok": True, "checks": {}, "errors": []})
    def test_dr_exercise_handles_alert_evaluation_error(self, _run_validation, _alerts):
        report = run_dr_game_day_exercise(
            postgres_restore_seconds=200,
            seaweedfs_restore_seconds=200,
            data_loss_minutes=1,
            target_rto_seconds=600,
            target_rpo_minutes=5,
        )
        self.assertFalse(report["ok"])
        self.assertIn("alert_evaluation_error", report)
        self.assertTrue(report["alert_evaluation_error"].startswith("RuntimeError:"))


class DrGameDayCommandTests(SimpleTestCase):
    @mock.patch("cintafactory.management.commands.run_dr_game_day.run_dr_game_day_exercise")
    def test_command_outputs_json(self, run_exercise):
        run_exercise.return_value = {
            "ok": True,
            "objectives": {
                "rto_seconds": {"actual": 100.0, "target": 600.0, "ok": True},
                "rpo_minutes": {"actual": 1.0, "target": 5.0, "ok": True},
            },
            "gaps": [],
            "recommendations": [],
        }
        out = StringIO()
        call_command("run_dr_game_day", "--json-output", stdout=out)
        payload = json.loads(out.getvalue().strip())
        self.assertTrue(payload["ok"])

    @mock.patch("cintafactory.management.commands.run_dr_game_day.run_dr_game_day_exercise")
    def test_command_fails_without_allow_fail(self, run_exercise):
        run_exercise.return_value = {
            "ok": False,
            "objectives": {
                "rto_seconds": {"actual": 1000.0, "target": 600.0, "ok": False},
                "rpo_minutes": {"actual": 20.0, "target": 5.0, "ok": False},
            },
            "gaps": ["RTO gap"],
            "recommendations": [],
        }
        with self.assertRaises(CommandError):
            call_command("run_dr_game_day")
