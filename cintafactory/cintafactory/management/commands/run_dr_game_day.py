from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from cintafactory.operations.dr_exercise import run_dr_game_day_exercise


class Command(BaseCommand):
    help = "Run Plan 5 game-day DR exercise and evaluate RTO/RPO closure criteria."

    def add_arguments(self, parser):
        parser.add_argument("--json-output", action="store_true", help="Emit JSON output.")
        parser.add_argument(
            "--postgres-restore-seconds",
            type=float,
            default=600.0,
            help="Measured PostgreSQL restore time in seconds.",
        )
        parser.add_argument(
            "--seaweedfs-restore-seconds",
            type=float,
            default=480.0,
            help="Measured SeaweedFS restore time in seconds.",
        )
        parser.add_argument(
            "--data-loss-minutes",
            type=float,
            default=5.0,
            help="Measured data loss window during drill, in minutes.",
        )
        parser.add_argument(
            "--target-rto-seconds",
            type=float,
            default=None,
            help="Override RTO target in seconds.",
        )
        parser.add_argument(
            "--target-rpo-minutes",
            type=float,
            default=None,
            help="Override RPO target in minutes.",
        )
        parser.add_argument(
            "--skip-validation",
            action="store_true",
            help="Skip backup/restore validation probes during exercise.",
        )
        parser.add_argument("--allow-fail", action="store_true", help="Always exit with status 0.")

    def handle(self, *args, **options):
        report = run_dr_game_day_exercise(
            postgres_restore_seconds=float(options["postgres_restore_seconds"]),
            seaweedfs_restore_seconds=float(options["seaweedfs_restore_seconds"]),
            data_loss_minutes=float(options["data_loss_minutes"]),
            run_dependency_validation=not bool(options["skip_validation"]),
            target_rto_seconds=options["target_rto_seconds"],
            target_rpo_minutes=options["target_rpo_minutes"],
        )
        if options["json_output"]:
            self.stdout.write(json.dumps(report, sort_keys=True))
        else:
            status = "OK" if report.get("ok", False) else "FAILED"
            self.stdout.write(f"DR game-day exercise status: {status}")
            objectives = report.get("objectives", {})
            rto = objectives.get("rto_seconds", {})
            rpo = objectives.get("rpo_minutes", {})
            self.stdout.write(
                "RTO actual={:.3f}s target={:.3f}s ok={}".format(
                    float(rto.get("actual", 0.0)),
                    float(rto.get("target", 0.0)),
                    bool(rto.get("ok", False)),
                )
            )
            self.stdout.write(
                "RPO actual={:.3f}m target={:.3f}m ok={}".format(
                    float(rpo.get("actual", 0.0)),
                    float(rpo.get("target", 0.0)),
                    bool(rpo.get("ok", False)),
                )
            )
            for gap in report.get("gaps", []):
                self.stdout.write(f"gap: {gap}")
            for rec in report.get("recommendations", []):
                self.stdout.write(f"recommendation: {rec}")

        if not report.get("ok", False) and not options["allow_fail"]:
            raise CommandError("DR game-day exercise did not meet closure criteria.")
