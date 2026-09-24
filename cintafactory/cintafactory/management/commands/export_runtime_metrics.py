# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from django.core.management.base import BaseCommand

from cintafactory.operations.metrics import render_prometheus_metrics


class Command(BaseCommand):
    help = "Print Prometheus-formatted runtime metrics."

    def handle(self, *args, **options):
        self.stdout.write(render_prometheus_metrics(), ending="")
