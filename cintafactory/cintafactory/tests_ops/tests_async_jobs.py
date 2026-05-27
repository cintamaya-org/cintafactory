from __future__ import annotations

from django.contrib.auth import get_user_model
from unittest import mock
from django.test import TestCase, override_settings
from django.urls import reverse

from ..async_jobs import enqueue_likec4_export_job
from ..logging.logging_utils import bind_request_context, clear_request_context
from ..models import AsyncJob

User = get_user_model()


class AsyncJobServiceTests(TestCase):
    def tearDown(self) -> None:
        clear_request_context()
        super().tearDown()

    @override_settings(ASYNC_JOBS_RUNNER_MODE="inline", ASYNC_JOBS_LIKEC4_BACKOFF_SECONDS=[0.0])
    def test_enqueue_uses_existing_active_job_for_same_idempotency_key(self):
        user = User.objects.create_user(username="job-owner", password="pwd")
        existing = AsyncJob.objects.create(
            job_type="exports.likec4",
            queue_name="exports.likec4",
            status=AsyncJob.Status.QUEUED,
            resource_ref="diagrams/abc/likec4.c4",
            requested_by=user,
            max_attempts=2,
            idempotency_key="likec4_export:diagrams/abc/likec4.c4",
            payload={"storage_path": "diagrams/abc/likec4.c4", "source": "test", "backoff_seconds": [0.0]},
        )

        job = enqueue_likec4_export_job("diagrams/abc/likec4.c4", requested_by=user, source="test")

        self.assertEqual(job.id, existing.id)
        self.assertEqual(AsyncJob.objects.filter(idempotency_key=existing.idempotency_key).count(), 1)

    @mock.patch("cintafactory.async_jobs.dispatch_async_job")
    @override_settings(ASYNC_JOBS_RUNNER_MODE="external")
    def test_enqueue_does_not_start_inline_or_thread_runner_in_external_mode(self, dispatch_job):
        user = User.objects.create_user(username="job-owner-2", password="pwd")

        job = enqueue_likec4_export_job("diagrams/def/likec4.c4", requested_by=user, source="test")

        self.assertEqual(job.status, AsyncJob.Status.QUEUED)
        dispatch_job.assert_not_called()

    @override_settings(ASYNC_JOBS_RUNNER_MODE="external")
    def test_enqueue_persists_request_trace_id_in_payload(self):
        user = User.objects.create_user(username="job-owner-trace", password="pwd")
        bind_request_context(request_id="req-trace-123")
        job = enqueue_likec4_export_job("diagrams/trace/likec4.c4", requested_by=user, source="test")
        self.assertEqual(job.payload.get("trace_id"), "req-trace-123")


class AsyncJobApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="jobs-user", password="pwd")
        self.other = User.objects.create_user(username="jobs-other", password="pwd")
        self.staff = User.objects.create_user(username="jobs-staff", password="pwd", is_staff=True)

        self.user_job = AsyncJob.objects.create(
            job_type="exports.likec4",
            queue_name="exports.likec4",
            status=AsyncJob.Status.QUEUED,
            resource_ref="diagrams/user/likec4.c4",
            requested_by=self.user,
            max_attempts=2,
            idempotency_key="likec4_export:diagrams/user/likec4.c4",
            payload={"storage_path": "diagrams/user/likec4.c4"},
        )
        self.other_job = AsyncJob.objects.create(
            job_type="exports.likec4",
            queue_name="exports.likec4",
            status=AsyncJob.Status.QUEUED,
            resource_ref="diagrams/other/likec4.c4",
            requested_by=self.other,
            max_attempts=2,
            idempotency_key="likec4_export:diagrams/other/likec4.c4",
            payload={"storage_path": "diagrams/other/likec4.c4"},
        )

    def test_jobs_list_requires_authentication(self):
        response = self.client.get(reverse("api:async-job-list"))
        self.assertIn(response.status_code, {401, 403})

    def test_jobs_list_returns_only_requester_jobs(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("api:async-job-list"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["job_id"], str(self.user_job.id))

    def test_jobs_list_allows_staff_to_see_all_jobs(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("api:async-job-list"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 2)

    def test_jobs_list_supports_resource_ref_filter(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("api:async-job-list"), {"resource_ref": "diagrams/user/likec4.c4"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["resource_ref"], "diagrams/user/likec4.c4")

    def test_job_detail_hides_other_users_job(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("api:async-job-detail", args=[self.user_job.id]))
        self.assertEqual(response.status_code, 200)
        response_other = self.client.get(
            reverse("api:async-job-detail", args=[self.other_job.id])
        )
        self.assertEqual(response_other.status_code, 404)

    def test_cancel_requires_staff(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("api:async-job-cancel", args=[self.user_job.id]))
        self.assertEqual(response.status_code, 403)

    def test_cancel_updates_status(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("api:async-job-cancel", args=[self.user_job.id]))
        self.assertEqual(response.status_code, 200)
        self.user_job.refresh_from_db()
        self.assertEqual(self.user_job.status, AsyncJob.Status.CANCELLED)

    @mock.patch("cintafactory.api.jobs.dispatch_async_job")
    def test_requeue_resets_job_and_dispatches(self, dispatch_job):
        self.user_job.status = AsyncJob.Status.DEAD_LETTERED
        self.user_job.attempt_count = 2
        self.user_job.last_error = "boom"
        self.user_job.save(update_fields=["status", "attempt_count", "last_error", "updated_at"])
        self.client.force_login(self.staff)
        response = self.client.post(reverse("api:async-job-requeue", args=[self.user_job.id]))
        self.assertEqual(response.status_code, 200)
        self.user_job.refresh_from_db()
        self.assertEqual(self.user_job.status, AsyncJob.Status.QUEUED)
        self.assertEqual(self.user_job.attempt_count, 0)
        self.assertEqual(self.user_job.last_error, "")
        dispatch_job.assert_called_once_with(self.user_job.id)

    def test_ignore_sets_cancelled_with_reason(self):
        self.user_job.status = AsyncJob.Status.DEAD_LETTERED
        self.user_job.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("api:async-job-ignore", args=[self.user_job.id]),
            data={"reason": "known issue"},
        )
        self.assertEqual(response.status_code, 200)
        self.user_job.refresh_from_db()
        self.assertEqual(self.user_job.status, AsyncJob.Status.CANCELLED)
        self.assertIn("known issue", self.user_job.last_error)
