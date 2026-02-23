from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase


class DashboardAssetsTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.dashboards_dir = cls.repo_root / "deploy" / "observability" / "grafana" / "dashboards"

    def _load_dashboard(self, filename: str) -> dict:
        path = self.dashboards_dir / filename
        self.assertTrue(path.exists(), f"Missing dashboard: {path}")
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def test_all_plan6_dashboards_exist_and_parse(self):
        expected = [
            "service-overview.json",
            "reliability-slo.json",
            "logs-and-traces.json",
            "capacity-and-scaling.json",
            "architecture-and-interactions.json",
        ]
        for filename in expected:
            payload = self._load_dashboard(filename)
            self.assertIn("title", payload)
            self.assertIn("panels", payload)
            self.assertGreater(len(payload["panels"]), 0)

    def test_dashboards_cover_required_observability_dimensions(self):
        overview = self._load_dashboard("service-overview.json")
        reliability = self._load_dashboard("reliability-slo.json")
        logs = self._load_dashboard("logs-and-traces.json")
        capacity = self._load_dashboard("capacity-and-scaling.json")
        architecture = self._load_dashboard("architecture-and-interactions.json")

        def dashboard_exprs(payload: dict) -> str:
            parts: list[str] = []
            for panel in payload.get("panels", []):
                for target in panel.get("targets", []):
                    expr = target.get("expr")
                    if expr:
                        parts.append(str(expr))
            return "\n".join(parts)

        overview_exprs = dashboard_exprs(overview)
        reliability_exprs = dashboard_exprs(reliability)
        logs_exprs = dashboard_exprs(logs)
        capacity_exprs = dashboard_exprs(capacity)
        architecture_exprs = dashboard_exprs(architecture)

        self.assertIn("cinta_dependency_up", overview_exprs)
        self.assertIn("cinta_baseline_events_total", reliability_exprs)
        self.assertIn("request_id", logs_exprs)
        self.assertIn("container_last_seen", capacity_exprs)
        self.assertIn("cinta_dependency_up", architecture_exprs)

    def test_provisioning_points_to_dashboard_folder_and_datasources(self):
        datasource_file = (
            self.repo_root
            / "deploy"
            / "observability"
            / "grafana"
            / "provisioning"
            / "datasources"
            / "datasources.yml"
        )
        dashboards_file = (
            self.repo_root
            / "deploy"
            / "observability"
            / "grafana"
            / "provisioning"
            / "dashboards"
            / "dashboards.yml"
        )
        self.assertTrue(datasource_file.exists())
        self.assertTrue(dashboards_file.exists())

        datasource_text = datasource_file.read_text(encoding="utf-8")
        dashboards_text = dashboards_file.read_text(encoding="utf-8")

        self.assertIn("name: Prometheus", datasource_text)
        self.assertIn("name: Loki", datasource_text)
        self.assertIn("path: /var/lib/grafana/dashboards", dashboards_text)

    def test_observability_compose_declares_required_services(self):
        compose_file = self.repo_root / "docker-compose.observability.dev.yml"
        self.assertTrue(compose_file.exists())
        compose_text = compose_file.read_text(encoding="utf-8")

        for required in ["prometheus:", "loki:", "promtail:", "cadvisor:", "grafana:"]:
            self.assertIn(required, compose_text)
