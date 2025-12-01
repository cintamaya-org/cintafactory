from __future__ import annotations

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("dat", "0001_initial"),
        ("workflows", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserNotification",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("message", models.TextField(blank=True)),
                (
                    "level",
                    models.CharField(
                        choices=[
                            ("info", "Information"),
                            ("success", "Succès"),
                            ("warning", "Avertissement"),
                            ("error", "Erreur"),
                        ],
                        default="info",
                        max_length=16,
                    ),
                ),
                ("target_url", models.CharField(blank=True, max_length=500)),
                ("created_by_display", models.CharField(blank=True, max_length=255)),
                ("extra_data", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("viewed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "dat",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.CASCADE,
                        related_name="user_notifications",
                        to="dat.dat",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="workflow_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "workflow_user_notification",
                "ordering": ["-created_at", "-pk"],
            },
        ),
    ]
