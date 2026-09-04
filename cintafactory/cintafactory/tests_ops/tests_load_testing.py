from __future__ import annotations

import json
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from ..operations.load_testing import (
    LoadTestError,
    SeedConfig,
    Thresholds,
    cleanup_run,
    ensure_load_test_allowed,
    evaluate_thresholds,
    resolve_profile,
    run_db_load,
    run_http_load,
    seed_database,
    validate_run_id,
)


class LoadTestingConfigurationTests(SimpleTestCase):
    def test_profile_defaults_and_overrides_are_resolved(self):
        resolved = resolve_profile("small", dats=12, fill_ratio=0.75, concurrency=2)

        self.assertEqual(resolved["users"], 100)
        self.assertEqual(resolved["dats"], 12)
        self.assertEqual(resolved["fill_ratio"], 0.75)
        self.assertEqual(resolved["concurrency"], 2)

    def test_profile_rejects_invalid_ratio(self):
        with self.assertRaisesMessage(LoadTestError, "fill-ratio"):
            resolve_profile("small", fill_ratio=1.1)

    def test_run_id_rejects_unsafe_value(self):
        with self.assertRaisesMessage(LoadTestError, "run-id"):
            validate_run_id("../../production")

    @override_settings(DEBUG=True)
    def test_mutating_guard_requires_environment_opt_in(self):
        with self.assertRaisesMessage(LoadTestError, "LOAD_TEST_ENABLED=1"):
            ensure_load_test_allowed(allow_non_debug=False, environ={})

    @override_settings(DEBUG=False)
    def test_mutating_guard_requires_non_debug_confirmation(self):
        with self.assertRaisesMessage(LoadTestError, "--allow-non-debug"):
            ensure_load_test_allowed(
                allow_non_debug=False,
                environ={"LOAD_TEST_ENABLED": "1"},
            )

    def test_threshold_evaluation_reports_each_failure(self):
        result = evaluate_thresholds(
            {
                "error_rate": 0.2,
                "throughput_per_second": 3.0,
                "latency_ms": {"p95": 900.0},
            },
            Thresholds(max_p95_ms=800.0, max_error_rate=0.1, min_throughput=5.0),
        )

        self.assertFalse(result["passed"])
        self.assertEqual(len(result["failures"]), 3)


class LoadTestingHttpTests(SimpleTestCase):
    @mock.patch("cintafactory.operations.load_testing._http_request")
    def test_http_runner_aggregates_status_latency_and_paths(self, request):
        request.side_effect = [
            (10.0, 200, None),
            (20.0, 200, None),
            (30.0, 503, None),
            (40.0, 200, None),
        ]

        result = run_http_load(
            base_url="http://example.test",
            paths=["/health/live", "/accounts/login/"],
            scenario="web",
            concurrency=1,
            timeout=1.0,
            total_requests=4,
        )

        self.assertEqual(result["metrics"]["total_operations"], 4)
        self.assertEqual(result["metrics"]["error_count"], 1)
        self.assertEqual(result["metrics"]["statuses"], {"200": 3, "503": 1})
        self.assertEqual(result["metrics"]["latency_ms"]["p50"], 25.0)
        self.assertFalse(result["passed"])

    def test_http_command_dry_run_never_prints_oauth_token(self):
        out = StringIO()
        with mock.patch.dict("os.environ", {"LOAD_TOKEN": "top-secret-token"}):
            call_command(
                "load_test",
                "http",
                "--dry-run",
                "--requests",
                "2",
                "--oauth-token-env",
                "LOAD_TOKEN",
                "--json-output",
                stdout=out,
            )

        payload = out.getvalue()
        self.assertNotIn("top-secret-token", payload)
        self.assertTrue(json.loads(payload)["oauth"])

    def test_http_command_requires_token_environment_variable(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(CommandError):
                call_command(
                    "load_test",
                    "http",
                    "--dry-run",
                    "--oauth-token-env",
                    "MISSING_LOAD_TOKEN",
                )


@override_settings(DEBUG=True)
class LoadTestingDatabaseTests(TransactionTestCase):
    def _seed(self, run_id: str, *, dats: int = 1):
        return seed_database(
            SeedConfig(
                run_id=run_id,
                seed=7,
                users=4,
                applications=2,
                dats=dats,
                fill_ratio=0.5,
                batch_size=1,
            )
        )

    def test_bulk_seed_builds_complete_coherent_graph(self):
        result = self._seed("graph-test", dats=2)

        self.assertTrue(result["passed"], result["integrity"]["failures"])
        self.assertEqual(result["counts"]["users"], 4)
        self.assertEqual(result["counts"]["applications"], 2)
        self.assertEqual(result["counts"]["dats"], 2)
        self.assertEqual(result["counts"]["sections"], 14)
        self.assertEqual(result["counts"]["sub_sections"], 52)
        self.assertEqual(result["counts"]["parts"], 116)
        self.assertGreater(result["counts"]["entries"], 0)

    def test_cleanup_removes_only_selected_run(self):
        self._seed("cleanup-one")
        self._seed("cleanup-two")

        result = cleanup_run("cleanup-one", batch_size=1)

        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["counts_after"]["dats"], 0)
        second_preview = cleanup_run("cleanup-two", dry_run=True)
        self.assertEqual(second_preview["counts"]["dats"], 1)

    def test_seed_rejects_duplicate_run(self):
        self._seed("duplicate-run")

        with self.assertRaisesMessage(LoadTestError, "run already exists"):
            self._seed("duplicate-run")

    def test_concurrent_db_workload_reports_successful_operations(self):
        self._seed("db-workload")

        result = run_db_load(
            "db-workload",
            mode="mixed",
            duration=0.1,
            concurrency=2,
            read_ratio=0.5,
            seed=11,
        )

        self.assertTrue(result["passed"], result["evaluation"]["failures"])
        self.assertGreater(result["metrics"]["total_operations"], 0)
        self.assertEqual(result["metrics"]["error_count"], 0)
