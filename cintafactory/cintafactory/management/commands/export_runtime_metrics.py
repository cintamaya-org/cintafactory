from __future__ import annotations

from django.core.management.base import BaseCommand

from cintafactory.operations.metrics import render_prometheus_metrics


class Command(BaseCommand):
    help = "Print Prometheus-formatted runtime metrics."

    def handle(self, *args, **options):
        self.stdout.write(render_prometheus_metrics(), ending="")
