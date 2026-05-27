from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from cintafactory.operations.alerting import evaluate_runtime_alerts


class Command(BaseCommand):
    help = "Evaluate reliability alert rules from current runtime signals."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json-output",
            action="store_true",
            help="Emit structured JSON output.",
        )
        parser.add_argument(
            "--fail-on",
            choices=["none", "warning", "critical"],
            default="critical",
            help="Exit non-zero when alerts at or above this severity are firing.",
        )

    def handle(self, *args, **options):
        alerts = evaluate_runtime_alerts()
        alert_payload = [
            {
                "code": item.code,
                "severity": item.severity,
                "summary": item.summary,
                "route": item.route,
                "runbook": item.runbook,
                "details": item.details,
            }
            for item in alerts
        ]
        result = {
            "ok": len(alert_payload) == 0,
            "alert_count": len(alert_payload),
            "alerts": alert_payload,
        }
        if options["json_output"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
        else:
            if not alert_payload:
                self.stdout.write("No runtime alerts firing.")
            for alert in alert_payload:
                self.stdout.write(
                    f"[{alert['severity'].upper()}] {alert['code']} route={alert['route']} runbook={alert['runbook']}"
                )

        fail_on = options["fail_on"]
        if fail_on == "none":
            return
        if fail_on == "warning":
            failing = [item for item in alerts if item.severity in {"warning", "critical"}]
        else:
            failing = [item for item in alerts if item.severity == "critical"]
        if failing:
            raise CommandError(f"Runtime alerts firing: {len(failing)} (threshold={fail_on})")
