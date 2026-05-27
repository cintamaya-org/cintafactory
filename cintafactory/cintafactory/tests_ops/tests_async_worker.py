from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from ..models import AsyncJob


class AsyncJobWorkerCommandTests(TestCase):
    @mock.patch("cintafactory.management.commands.run_async_job_worker.dispatch_async_job")
    def test_worker_dispatches_queued_jobs_once(self, dispatch_job):
        job = AsyncJob.objects.create(
            job_type="exports.likec4",
            queue_name="exports.likec4",
            status=AsyncJob.Status.QUEUED,
            resource_ref="diagrams/1/likec4.c4",
            max_attempts=2,
            idempotency_key="likec4_export:diagrams/1/likec4.c4",
            payload={"storage_path": "diagrams/1/likec4.c4"},
        )
        out = StringIO()
        dispatch_job.side_effect = lambda job_id: AsyncJob.objects.filter(id=job_id).update(status=AsyncJob.Status.SUCCEEDED)

        call_command("run_async_job_worker", "--once", stdout=out)

        dispatch_job.assert_called_once_with(job.id)
        self.assertIn("Processed async jobs: 1", out.getvalue())

    @mock.patch("cintafactory.management.commands.run_async_job_worker.dispatch_async_job")
    def test_worker_respects_max_jobs(self, dispatch_job):
        for idx in range(3):
            AsyncJob.objects.create(
                job_type="exports.likec4",
                queue_name="exports.likec4",
                status=AsyncJob.Status.QUEUED,
                resource_ref=f"diagrams/{idx}/likec4.c4",
                max_attempts=2,
                idempotency_key=f"likec4_export:diagrams/{idx}/likec4.c4",
                payload={"storage_path": f"diagrams/{idx}/likec4.c4"},
            )
        out = StringIO()
        dispatch_job.side_effect = lambda job_id: AsyncJob.objects.filter(id=job_id).update(status=AsyncJob.Status.SUCCEEDED)

        call_command("run_async_job_worker", "--once", "--max-jobs", "2", stdout=out)

        self.assertEqual(dispatch_job.call_count, 2)
        self.assertIn("Processed async jobs: 2", out.getvalue())
