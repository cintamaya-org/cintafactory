from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from cintafactory.operations.load_testing import LoadTestError, run_http_load


class Command(BaseCommand):
    help = "Run lightweight load validation against a deployed stack and evaluate Plan 3 SLO targets."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default="http://127.0.0.1:8101")
        parser.add_argument("--path", default="/accounts/login/")
        parser.add_argument("--scenario", choices=["web", "proxy", "drawio_export", "likec4_export"], default="web")
        parser.add_argument("--requests", type=int, default=100)
        parser.add_argument("--concurrency", type=int, default=10)
        parser.add_argument("--timeout", type=float, default=10.0)
        parser.add_argument("--allow-fail", action="store_true")
        parser.add_argument("--json-output", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        total_requests = max(1, int(options["requests"]))
        concurrency = max(1, int(options["concurrency"]))
        timeout = max(0.1, float(options["timeout"]))
        url = f"{str(options['base_url']).rstrip('/')}/{str(options['path']).lstrip('/')}"
        scenario = str(options["scenario"])
        dry_run = bool(options["dry_run"])

        if dry_run:
            payload = {
                "scenario": scenario,
                "url": url,
                "requests": total_requests,
                "concurrency": concurrency,
                "timeout": timeout,
                "dry_run": True,
            }
            self.stdout.write(json.dumps(payload, indent=2))
            return

        try:
            result = run_http_load(
                base_url=str(options["base_url"]),
                paths=[str(options["path"])],
                scenario=scenario,
                concurrency=concurrency,
                timeout=timeout,
                total_requests=total_requests,
                error_status_min=500,
            )
        except LoadTestError as exc:
            raise CommandError(str(exc)) from exc
        evaluation = result["scenario_slo"]
        metrics = result["metrics"]

        if options["json_output"]:
            self.stdout.write(json.dumps(evaluation, indent=2))
        else:
            self.stdout.write(
                self.style.NOTICE(
                    f"[{scenario}] req={total_requests} errors={metrics['error_count']} "
                    f"p95={float(metrics['latency_ms']['p95']):.2f}ms "
                    f"p99={float(metrics['latency_ms']['p99']):.2f}ms"
                )
            )
            if evaluation["failures"]:
                self.stdout.write(self.style.WARNING("Failures: " + ", ".join(evaluation["failures"])))
            if evaluation["suggestions"]:
                self.stdout.write("Suggestions:")
                for suggestion in evaluation["suggestions"]:
                    self.stdout.write(f"- {suggestion}")

        if (not evaluation["passed"]) and (not options["allow_fail"]):
            raise CommandError("Load validation failed SLO checks.")
