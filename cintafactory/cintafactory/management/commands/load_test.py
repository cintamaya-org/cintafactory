from __future__ import annotations

import json
import os
import secrets

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from cintafactory.operations.load_testing import (
    LOAD_PROFILES,
    LoadTestError,
    SeedConfig,
    Thresholds,
    cleanup_run,
    ensure_load_test_allowed,
    public_config,
    resolve_profile,
    run_db_load,
    run_http_load,
    seed_database,
    validate_run_id,
)


SCENARIOS = ("web", "proxy", "drawio_export", "likec4_export")


class Command(BaseCommand):
    help = "Generate isolated synthetic data and run database or HTTP load tests."

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="action", required=True)

        seed_parser = subparsers.add_parser("seed", help="Generate an isolated synthetic dataset.")
        self._add_common(seed_parser)
        self._add_seed_options(seed_parser)

        db_parser = subparsers.add_parser("db", help="Run direct ORM database load.")
        self._add_common(db_parser)
        self._add_runtime_options(db_parser)
        self._add_threshold_options(db_parser)
        db_parser.add_argument("--mode", choices=("read", "write", "mixed"), default="mixed")
        db_parser.add_argument("--read-ratio", type=float, default=0.8)

        http_parser = subparsers.add_parser("http", help="Run HTTP GET load against a deployed stack.")
        self._add_common(http_parser)
        self._add_http_options(http_parser, exclusive_duration=True)
        self._add_threshold_options(http_parser)

        suite_parser = subparsers.add_parser("suite", help="Seed data, then run DB and HTTP load.")
        self._add_common(suite_parser)
        self._add_seed_options(suite_parser)
        self._add_runtime_options(suite_parser)
        self._add_threshold_options(suite_parser)
        suite_parser.add_argument("--read-ratio", type=float, default=0.8)
        suite_parser.add_argument("--base-url", default="http://127.0.0.1:8101")
        suite_parser.add_argument("--path", action="append", dest="paths")
        suite_parser.add_argument("--scenario", choices=SCENARIOS, default="web")
        suite_parser.add_argument("--requests", type=int)
        suite_parser.add_argument("--timeout", type=float, default=10.0)
        suite_parser.add_argument("--oauth-token-env")
        suite_parser.add_argument("--cleanup-after", action="store_true")

        cleanup_parser = subparsers.add_parser("cleanup", help="Delete only data tagged for one run.")
        self._add_common(cleanup_parser, profile=False, seed=False, allow_fail=False)
        cleanup_parser.add_argument("--batch-size", type=int, default=250)
        cleanup_parser.add_argument("--confirm", action="store_true")

    @staticmethod
    def _add_common(parser, *, profile: bool = True, seed: bool = True, allow_fail: bool = True) -> None:
        if profile:
            parser.add_argument("--profile", choices=tuple(LOAD_PROFILES), default="small")
        parser.add_argument("--run-id")
        if seed:
            parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--json-output", action="store_true")
        if allow_fail:
            parser.add_argument("--allow-fail", action="store_true")
        parser.add_argument("--allow-non-debug", action="store_true")

    @staticmethod
    def _add_seed_options(parser) -> None:
        parser.add_argument("--users", type=int)
        parser.add_argument("--applications", type=int)
        parser.add_argument("--dats", type=int)
        parser.add_argument("--fill-ratio", type=float)
        parser.add_argument("--batch-size", type=int, default=250)

    @staticmethod
    def _add_runtime_options(parser) -> None:
        parser.add_argument("--duration", type=float)
        parser.add_argument("--concurrency", type=int)

    @staticmethod
    def _add_threshold_options(parser) -> None:
        parser.add_argument("--max-p95-ms", type=float)
        parser.add_argument("--max-error-rate", type=float)
        parser.add_argument("--min-throughput", type=float)

    @staticmethod
    def _add_http_options(parser, *, exclusive_duration: bool) -> None:
        parser.add_argument("--base-url", default="http://127.0.0.1:8101")
        parser.add_argument("--path", action="append", dest="paths")
        parser.add_argument("--scenario", choices=SCENARIOS, default="web")
        if exclusive_duration:
            group = parser.add_mutually_exclusive_group()
            group.add_argument("--requests", type=int)
            group.add_argument("--duration", type=float)
        else:
            parser.add_argument("--requests", type=int)
            parser.add_argument("--duration", type=float)
        parser.add_argument("--concurrency", type=int)
        parser.add_argument("--timeout", type=float, default=10.0)
        parser.add_argument("--oauth-token-env")

    def handle(self, *args, **options):
        try:
            result = self._dispatch(options)
        except LoadTestError as exc:
            raise CommandError(str(exc)) from exc

        if options.get("json_output"):
            self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
        else:
            self._write_human(result)

        if not result.get("passed", True) and not options.get("allow_fail", False):
            raise CommandError("Load test failed checks or configured thresholds.")

    def _dispatch(self, options: dict[str, object]) -> dict[str, object]:
        action = str(options["action"])
        if action == "cleanup":
            return self._cleanup(options)

        resolved = resolve_profile(
            str(options["profile"]),
            users=options.get("users"),
            applications=options.get("applications"),
            dats=options.get("dats"),
            fill_ratio=options.get("fill_ratio"),
            duration=options.get("duration"),
            concurrency=options.get("concurrency"),
        )
        run_id = str(options.get("run_id") or self._new_run_id())
        validate_run_id(run_id)
        thresholds = self._thresholds(options)

        if action == "seed":
            config = self._seed_config(options, resolved, run_id)
            if options["dry_run"]:
                return {"action": "seed", "dry_run": True, "config": public_config(config), "passed": True}
            self._guard(options)
            return seed_database(config, progress=self._progress(options))

        if action == "db":
            payload = {
                "action": "db",
                "run_id": run_id,
                "mode": options["mode"],
                "duration": resolved["duration"],
                "concurrency": resolved["concurrency"],
                "read_ratio": options["read_ratio"],
                "thresholds": thresholds.__dict__,
            }
            if options["dry_run"]:
                return {**payload, "dry_run": True, "passed": True}
            if options["mode"] in {"write", "mixed"}:
                self._guard(options)
            return run_db_load(
                run_id,
                mode=str(options["mode"]),
                duration=float(resolved["duration"]),
                concurrency=int(resolved["concurrency"]),
                read_ratio=float(options["read_ratio"]),
                seed=int(options["seed"]),
                thresholds=thresholds,
            )

        if action == "http":
            return self._http(options, resolved, thresholds)

        if action == "suite":
            return self._suite(options, resolved, run_id, thresholds)
        raise LoadTestError(f"unsupported action: {action}")

    def _suite(
        self,
        options: dict[str, object],
        resolved: dict[str, int | float],
        run_id: str,
        thresholds: Thresholds,
    ) -> dict[str, object]:
        config = self._seed_config(options, resolved, run_id)
        oauth_token = self._oauth_token(options)
        paths = list(options.get("paths") or ["/accounts/login/"])
        if options["dry_run"]:
            return {
                "action": "suite",
                "dry_run": True,
                "run_id": run_id,
                "seed": public_config(config),
                "db": {
                    "mode": "mixed",
                    "duration": resolved["duration"],
                    "concurrency": resolved["concurrency"],
                    "read_ratio": options["read_ratio"],
                },
                "http": {
                    "base_url": options["base_url"],
                    "paths": paths,
                    "scenario": options["scenario"],
                    "requests": options.get("requests"),
                    "duration": None if options.get("requests") else resolved["duration"],
                    "oauth": bool(oauth_token),
                },
                "cleanup_after": bool(options["cleanup_after"]),
                "passed": True,
            }

        self._guard(options)
        seed_result = seed_database(config, progress=self._progress(options))
        if not seed_result["passed"]:
            return {"action": "suite", "run_id": run_id, "seed": seed_result, "passed": False}
        db_result = run_db_load(
            run_id,
            mode="mixed",
            duration=float(resolved["duration"]),
            concurrency=int(resolved["concurrency"]),
            read_ratio=float(options["read_ratio"]),
            seed=int(options["seed"]),
            thresholds=thresholds,
        )
        http_result = run_http_load(
            base_url=str(options["base_url"]),
            paths=paths,
            scenario=str(options["scenario"]),
            concurrency=int(resolved["concurrency"]),
            timeout=float(options["timeout"]),
            total_requests=int(options["requests"]) if options.get("requests") is not None else None,
            duration=None if options.get("requests") is not None else float(resolved["duration"]),
            oauth_token=oauth_token,
            thresholds=thresholds,
        )
        cleanup_result = None
        if options["cleanup_after"]:
            cleanup_result = cleanup_run(
                run_id,
                batch_size=int(options["batch_size"]),
                progress=self._progress(options),
            )
        passed = bool(seed_result["passed"] and db_result["passed"] and http_result["passed"])
        if cleanup_result is not None:
            passed = bool(passed and cleanup_result["passed"])
        return {
            "action": "suite",
            "run_id": run_id,
            "seed": seed_result,
            "db": db_result,
            "http": http_result,
            "cleanup": cleanup_result,
            "passed": passed,
        }

    def _http(
        self,
        options: dict[str, object],
        resolved: dict[str, int | float],
        thresholds: Thresholds,
    ) -> dict[str, object]:
        oauth_token = self._oauth_token(options)
        paths = list(options.get("paths") or ["/accounts/login/"])
        requests = int(options["requests"]) if options.get("requests") is not None else None
        duration = None if requests is not None else float(resolved["duration"])
        payload = {
            "action": "http",
            "base_url": options["base_url"],
            "paths": paths,
            "scenario": options["scenario"],
            "requests": requests,
            "duration": duration,
            "concurrency": resolved["concurrency"],
            "timeout": options["timeout"],
            "oauth": bool(oauth_token),
        }
        if options["dry_run"]:
            return {**payload, "dry_run": True, "passed": True}
        return run_http_load(
            base_url=str(options["base_url"]),
            paths=paths,
            scenario=str(options["scenario"]),
            concurrency=int(resolved["concurrency"]),
            timeout=float(options["timeout"]),
            total_requests=requests,
            duration=duration,
            oauth_token=oauth_token,
            thresholds=thresholds,
        )

    def _cleanup(self, options: dict[str, object]) -> dict[str, object]:
        run_id = str(options.get("run_id") or "")
        validate_run_id(run_id)
        if not options["dry_run"] and not options["confirm"]:
            raise LoadTestError("cleanup requires --confirm (or use --dry-run to preview)")
        if not options["dry_run"]:
            self._guard(options)
        return cleanup_run(
            run_id,
            batch_size=int(options["batch_size"]),
            dry_run=bool(options["dry_run"]),
            progress=self._progress(options),
        )

    @staticmethod
    def _seed_config(
        options: dict[str, object], resolved: dict[str, int | float], run_id: str
    ) -> SeedConfig:
        batch_size = int(options["batch_size"])
        if batch_size < 1:
            raise LoadTestError("batch-size must be >= 1")
        return SeedConfig(
            run_id=run_id,
            seed=int(options["seed"]),
            users=int(resolved["users"]),
            applications=int(resolved["applications"]),
            dats=int(resolved["dats"]),
            fill_ratio=float(resolved["fill_ratio"]),
            batch_size=batch_size,
        )

    @staticmethod
    def _thresholds(options: dict[str, object]) -> Thresholds:
        values = {
            "max_p95_ms": options.get("max_p95_ms"),
            "max_error_rate": options.get("max_error_rate"),
            "min_throughput": options.get("min_throughput"),
        }
        for name, value in values.items():
            if value is not None and float(value) < 0:
                raise LoadTestError(f"{name.replace('_', '-')} must be >= 0")
        if values["max_error_rate"] is not None and float(values["max_error_rate"]) > 1:
            raise LoadTestError("max-error-rate must be between 0 and 1")
        return Thresholds(**values)

    @staticmethod
    def _oauth_token(options: dict[str, object]) -> str | None:
        variable = options.get("oauth_token_env")
        if not variable:
            return None
        token = os.environ.get(str(variable), "")
        if not token:
            raise LoadTestError(f"OAuth token environment variable is empty or missing: {variable}")
        return token

    @staticmethod
    def _new_run_id() -> str:
        return f"{timezone.now():%Y%m%d%H%M%S}-{secrets.token_hex(2)}".lower()

    @staticmethod
    def _guard(options: dict[str, object]) -> None:
        ensure_load_test_allowed(allow_non_debug=bool(options["allow_non_debug"]))

    def _progress(self, options: dict[str, object]):
        if options.get("json_output"):
            return None
        return lambda message: self.stderr.write(f"[load-test] {message}")

    def _write_human(self, result: dict[str, object]) -> None:
        action = result.get("action", "load-test")
        status = "PASSED" if result.get("passed", True) else "FAILED"
        self.stdout.write(self.style.SUCCESS(f"[{action}] {status}"))
        if result.get("run_id"):
            self.stdout.write(f"run_id={result['run_id']}")
        if result.get("dry_run"):
            self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
            return
        counts = result.get("counts") or result.get("counts_before")
        if counts:
            self.stdout.write("counts=" + json.dumps(counts, sort_keys=True))
        metrics = result.get("metrics")
        if isinstance(metrics, dict):
            latency = metrics.get("latency_ms", {})
            self.stdout.write(
                f"ops={metrics.get('total_operations')} errors={metrics.get('error_count')} "
                f"throughput={metrics.get('throughput_per_second')}/s "
                f"p95={latency.get('p95')}ms p99={latency.get('p99')}ms"
            )
        if action == "suite":
            for child_name in ("seed", "db", "http", "cleanup"):
                child = result.get(child_name)
                if isinstance(child, dict):
                    self.stdout.write(
                        f"{child_name}={'PASSED' if child.get('passed', True) else 'FAILED'}"
                    )
