from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from cintafactory.operations.backup_dr import run_backup_dr_validation


class Command(BaseCommand):
    help = "Validate Postgres PITR and SeaweedFS backup/restore readiness."

    def add_arguments(self, parser):
        parser.add_argument("--json-output", action="store_true", help="Emit JSON output.")
        parser.add_argument("--sample-size", type=int, default=50, help="SeaweedFS consistency sample size.")
        parser.add_argument("--skip-postgres", action="store_true", help="Skip PostgreSQL PITR checks.")
        parser.add_argument("--skip-seaweedfs", action="store_true", help="Skip SeaweedFS checks.")
        parser.add_argument(
            "--write-storage-probe",
            action="store_true",
            help="Write/read/delete a probe object in SeaweedFS as part of validation.",
        )
        parser.add_argument(
            "--attempt-restore-point",
            action="store_true",
            help="Attempt pg_create_restore_point() verification for PITR.",
        )
        parser.add_argument(
            "--require-restore-point",
            action="store_true",
            help="Fail validation if restore-point probe does not succeed.",
        )
        parser.add_argument("--allow-fail", action="store_true", help="Always exit with success status.")

    def handle(self, *args, **options):
        result = run_backup_dr_validation(
            sample_size=max(int(options["sample_size"]), 1),
            validate_postgres=not bool(options["skip_postgres"]),
            validate_seaweedfs=not bool(options["skip_seaweedfs"]),
            write_storage_probe=bool(options["write_storage_probe"]),
            attempt_restore_point=bool(options["attempt_restore_point"]),
            require_restore_point=bool(options["require_restore_point"]),
        )

        if options["json_output"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
        else:
            status = "OK" if result.get("ok", False) else "FAILED"
            self.stdout.write(f"Backup/DR validation status: {status}")
            for scope, payload in result.get("checks", {}).items():
                scope_ok = bool(payload.get("ok", False))
                self.stdout.write(f"- {scope}: {'ok' if scope_ok else 'failed'}")
            for err in result.get("errors", []):
                self.stdout.write(f"  error: {err}")

        if not result.get("ok", False) and not options["allow_fail"]:
            raise CommandError("Backup/DR validation failed.")
