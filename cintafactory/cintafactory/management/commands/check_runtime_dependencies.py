from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from cintafactory.operations.health import overall_ready


class Command(BaseCommand):
    help = "Validate runtime dependency readiness for web/worker profiles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile",
            choices=["web", "worker"],
            default="web",
            help="Dependency profile to evaluate.",
        )
        parser.add_argument("--json-output", action="store_true", help="Print JSON payload.")

    def handle(self, *args, **options):
        profile = options["profile"]
        json_output = bool(options["json_output"])
        ready, checks = overall_ready(profile=profile)
        payload = {
            "ok": ready,
            "profile": profile,
            "checks": checks,
        }
        if json_output:
            self.stdout.write(json.dumps(payload, sort_keys=True))
        else:
            status = "OK" if ready else "FAIL"
            self.stdout.write(f"{status} runtime dependencies ({profile}): {checks}")
        if not ready:
            raise CommandError(f"Runtime dependencies are not ready for profile '{profile}'.")
