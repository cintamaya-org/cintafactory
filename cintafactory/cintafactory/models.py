from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class AsyncJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        DEAD_LETTERED = "dead_lettered", "Dead lettered"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_type = models.CharField(max_length=100)
    queue_name = models.CharField(max_length=100, default="default")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    resource_ref = models.CharField(max_length=255, blank=True, default="")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="async_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=1)
    last_error = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    result_payload = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "async_jobs"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "job_type"]),
            models.Index(fields=["resource_ref"]),
            models.Index(fields=["idempotency_key"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.job_type}:{self.id} ({self.status})"
