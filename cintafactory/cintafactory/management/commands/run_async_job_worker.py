from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from cintafactory.async_jobs import dispatch_async_job
from cintafactory.models import AsyncJob


class Command(BaseCommand):
    help = "Run async job worker loop for queued jobs."

    def add_arguments(self, parser):
        parser.add_argument("--poll-interval", type=float, default=1.0)
        parser.add_argument("--max-jobs", type=int, default=0)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        poll_interval = max(0.1, float(options["poll_interval"]))
        max_jobs = max(0, int(options["max_jobs"]))
        run_once = bool(options["once"])

        processed = 0
        while True:
            queued = (
                AsyncJob.objects.filter(status=AsyncJob.Status.QUEUED)
                .order_by("created_at")
                .values_list("id", flat=True)
                .first()
            )
            if not queued:
                if run_once:
                    break
                time.sleep(poll_interval)
                continue

            dispatch_async_job(queued)
            processed += 1
            if max_jobs and processed >= max_jobs:
                break
            if run_once:
                # Drain the current queue then exit.
                continue

        self.stdout.write(self.style.SUCCESS(f"Processed async jobs: {processed}"))
