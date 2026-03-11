from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from ..operations.scaling_validation import LoadSummary, evaluate_slo, percentile_ms


class ScalingValidationMathTests(SimpleTestCase):
    def test_percentile_ms_interpolates_values(self):
        samples = [10.0, 20.0, 30.0, 40.0, 50.0]
        self.assertAlmostEqual(percentile_ms(samples, 95), 48.0)
        self.assertEqual(percentile_ms(samples, 0), 10.0)
        self.assertEqual(percentile_ms(samples, 100), 50.0)

    def test_evaluate_slo_reports_failure_for_web_latency(self):
        summary = LoadSummary(scenario="web", total_requests=100, error_count=0, p95_ms=1200.0, p99_ms=1400.0)
        evaluation = evaluate_slo(summary)
        self.assertFalse(evaluation["passed"])
        self.assertIn("web p95 >= 800ms", evaluation["failures"])

    def test_evaluate_slo_reports_failure_for_proxy_error_rate(self):
        summary = LoadSummary(scenario="proxy", total_requests=100, error_count=5, p95_ms=300.0, p99_ms=500.0)
        evaluation = evaluate_slo(summary)
        self.assertFalse(evaluation["passed"])
        self.assertIn("proxy 5xx rate >= 0.5%", evaluation["failures"])


class ScalingValidationCommandTests(SimpleTestCase):
    def test_command_dry_run_outputs_payload(self):
        out = StringIO()
        call_command(
            "run_scaling_load_validation",
            "--dry-run",
            "--scenario",
            "web",
            "--requests",
            "20",
            "--concurrency",
            "4",
            stdout=out,
        )
        payload = out.getvalue()
        self.assertIn('"dry_run": true', payload)
        self.assertIn('"scenario": "web"', payload)

    def test_command_fails_when_endpoint_unreachable_and_allow_fail_false(self):
        with self.assertRaises(CommandError):
            call_command(
                "run_scaling_load_validation",
                "--base-url",
                "http://127.0.0.1:65500",
                "--requests",
                "2",
                "--concurrency",
                "1",
                "--timeout",
                "0.2",
            )
