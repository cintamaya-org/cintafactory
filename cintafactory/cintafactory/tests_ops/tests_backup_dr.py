from __future__ import annotations

import json
from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from ..operations.backup_dr import collect_postgres_pitr_validation, collect_seaweedfs_backup_validation


class PostgresBackupValidationTests(SimpleTestCase):
    @mock.patch("cintafactory.operations.backup_dr.emit_baseline_metric")
    @mock.patch("cintafactory.operations.backup_dr._read_pg_setting")
    @mock.patch("cintafactory.operations.backup_dr.connection")
    def test_postgres_pitr_validation_passes_with_required_settings(self, connection_mock, read_setting, _emit):
        connection_mock.vendor = "postgresql"
        read_setting.side_effect = lambda key: {
            "archive_mode": "on",
            "archive_command": "test ! -f /archive/%f && cp %p /archive/%f",
            "wal_level": "replica",
        }[key]
        payload = collect_postgres_pitr_validation()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["errors"], [])

    @mock.patch("cintafactory.operations.backup_dr.emit_baseline_metric")
    @mock.patch("cintafactory.operations.backup_dr._read_pg_setting")
    @mock.patch("cintafactory.operations.backup_dr.connection")
    def test_postgres_pitr_validation_fails_when_archive_not_enabled(self, connection_mock, read_setting, _emit):
        connection_mock.vendor = "postgresql"
        read_setting.side_effect = lambda key: {
            "archive_mode": "off",
            "archive_command": "",
            "wal_level": "minimal",
        }[key]
        payload = collect_postgres_pitr_validation()
        self.assertFalse(payload["ok"])
        self.assertGreaterEqual(len(payload["errors"]), 2)

    @mock.patch("cintafactory.operations.backup_dr.emit_baseline_metric")
    @mock.patch("cintafactory.operations.backup_dr._create_restore_point", side_effect=RuntimeError("permission denied"))
    @mock.patch("cintafactory.operations.backup_dr._read_pg_setting")
    @mock.patch("cintafactory.operations.backup_dr.connection")
    def test_postgres_restore_point_required_fails_on_exception(
        self,
        connection_mock,
        read_setting,
        _create_restore_point,
        _emit,
    ):
        connection_mock.vendor = "postgresql"
        read_setting.side_effect = lambda key: {
            "archive_mode": "on",
            "archive_command": "cp %p /archive/%f",
            "wal_level": "replica",
        }[key]
        payload = collect_postgres_pitr_validation(attempt_restore_point=True, require_restore_point=True)
        self.assertFalse(payload["ok"])
        self.assertIn("Restore point verification failed.", payload["errors"])


class SeaweedBackupValidationTests(SimpleTestCase):
    @mock.patch("cintafactory.operations.backup_dr.emit_baseline_metric")
    @mock.patch("cintafactory.operations.backup_dr._collect_storage_references", return_value=["a.txt", "b.txt"])
    @mock.patch("cintafactory.operations.backup_dr.SeaweedFSStorage")
    def test_seaweed_backup_validation_detects_missing_paths(
        self,
        storage_class,
        _collect_refs,
        _emit,
    ):
        storage = storage_class.return_value
        storage.exists.side_effect = [True, False]
        payload = collect_seaweedfs_backup_validation(sample_size=2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["checks"]["missing_count"], 1)

    @mock.patch("cintafactory.operations.backup_dr.emit_baseline_metric")
    @mock.patch("cintafactory.operations.backup_dr._collect_storage_references", return_value=["a.txt"])
    @mock.patch("cintafactory.operations.backup_dr.SeaweedFSStorage")
    def test_seaweed_backup_validation_probe_succeeds(
        self,
        storage_class,
        _collect_refs,
        _emit,
    ):
        storage = storage_class.return_value
        storage.exists.return_value = True
        payload = collect_seaweedfs_backup_validation(sample_size=1, write_probe=True)
        self.assertTrue(payload["ok"])
        self.assertIn("write_probe", payload["checks"])
        storage.save.assert_called()
        storage.delete.assert_called()


class RunBackupDrValidationCommandTests(SimpleTestCase):
    @mock.patch("cintafactory.management.commands.run_backup_dr_validation.run_backup_dr_validation")
    def test_command_outputs_json(self, run_validation):
        run_validation.return_value = {"ok": True, "checks": {"postgres": {"ok": True}}, "errors": []}
        out = StringIO()
        call_command("run_backup_dr_validation", "--json-output", stdout=out)
        payload = json.loads(out.getvalue().strip())
        self.assertTrue(payload["ok"])
        self.assertIn("postgres", payload["checks"])

    @mock.patch("cintafactory.management.commands.run_backup_dr_validation.run_backup_dr_validation")
    def test_command_raises_when_failed_without_allow_fail(self, run_validation):
        run_validation.return_value = {"ok": False, "checks": {}, "errors": ["postgres: bad"]}
        with self.assertRaises(CommandError):
            call_command("run_backup_dr_validation")
