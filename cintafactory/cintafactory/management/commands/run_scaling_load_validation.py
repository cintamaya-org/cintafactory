from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError

from cintafactory.operations.scaling_validation import LoadSummary, evaluate_slo, percentile_ms


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

        latencies_ms: list[float] = []
        error_count = 0

        def _fire_once() -> tuple[float, int]:
            started = time.perf_counter()
            request = Request(url, method="GET")
            try:
                with urlopen(request, timeout=timeout) as response:
                    status = int(getattr(response, "status", 200) or 200)
                    response.read(1)
            except HTTPError as exc:
                status = int(exc.code or 500)
            except URLError:
                status = 599
            except Exception:
                status = 599
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return elapsed_ms, status

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(_fire_once) for _ in range(total_requests)]
            for future in as_completed(futures):
                elapsed_ms, status = future.result()
                latencies_ms.append(elapsed_ms)
                if status >= 500:
                    error_count += 1

        summary = LoadSummary(
            scenario=scenario,
            total_requests=total_requests,
            error_count=error_count,
            p95_ms=percentile_ms(latencies_ms, 95),
            p99_ms=percentile_ms(latencies_ms, 99),
        )
        evaluation = evaluate_slo(summary)

        if options["json_output"]:
            self.stdout.write(json.dumps(evaluation, indent=2))
        else:
            self.stdout.write(
                self.style.NOTICE(
                    f"[{scenario}] req={total_requests} errors={error_count} "
                    f"p95={summary.p95_ms:.2f}ms p99={summary.p99_ms:.2f}ms"
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
