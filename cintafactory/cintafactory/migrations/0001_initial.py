from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AsyncJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("job_type", models.CharField(max_length=100)),
                ("queue_name", models.CharField(default="default", max_length=100)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("dead_lettered", "Dead lettered"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="queued",
                        max_length=20,
                    ),
                ),
                ("resource_ref", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(default=1)),
                ("last_error", models.TextField(blank=True, default="")),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("result_payload", models.JSONField(blank=True, default=dict)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=255)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="async_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "async_jobs",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="asyncjob",
            index=models.Index(fields=["status", "job_type"], name="async_jobs_status_d4f95f_idx"),
        ),
        migrations.AddIndex(
            model_name="asyncjob",
            index=models.Index(fields=["resource_ref"], name="async_jobs_resourc_f85fed_idx"),
        ),
        migrations.AddIndex(
            model_name="asyncjob",
            index=models.Index(fields=["idempotency_key"], name="async_jobs_idempot_e23e04_idx"),
        ),
        migrations.AddIndex(
            model_name="asyncjob",
            index=models.Index(fields=["created_at"], name="async_jobs_created_1101da_idx"),
        ),
    ]
