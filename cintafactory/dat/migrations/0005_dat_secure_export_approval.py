from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("dat", "0004_dat_section_participant_and_admin"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="dat",
            name="secure_export_requires_dual_admin_approval",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="DATExportAccessRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "En attente"), ("approved", "Approuvée"), ("expired", "Expirée")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("approve_deadline_at", models.DateTimeField()),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("access_valid_until", models.DateTimeField(blank=True, null=True)),
                ("required_approvals", models.PositiveSmallIntegerField(default=2)),
                (
                    "dat",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="export_access_requests",
                        to="dat.dat",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dat_export_access_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "dat_export_access_request",
                "ordering": ["-requested_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="DATExportAccessHistory",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("request_created", "Demande créée"),
                            ("approved", "Demande approuvée"),
                            ("access_granted", "Accès autorisé"),
                            ("download_pdf", "Téléchargement PDF"),
                            ("download_json", "Téléchargement JSON"),
                            ("request_expired", "Demande expirée"),
                            ("access_expired", "Accès expiré"),
                        ],
                        max_length=32,
                    ),
                ),
                ("details", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dat_export_access_history_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "dat",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="export_access_history_entries",
                        to="dat.dat",
                    ),
                ),
                (
                    "request",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="history_entries",
                        to="dat.datexportaccessrequest",
                    ),
                ),
            ],
            options={
                "db_table": "dat_export_access_history",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="DATExportAccessApproval",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("approved_at", models.DateTimeField(auto_now_add=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dat_export_access_approvals",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "dat",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="export_access_approvals",
                        to="dat.dat",
                    ),
                ),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="approvals",
                        to="dat.datexportaccessrequest",
                    ),
                ),
            ],
            options={
                "db_table": "dat_export_access_approval",
                "ordering": ["approved_at", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="datexportaccessapproval",
            constraint=models.UniqueConstraint(
                fields=("request", "approved_by"),
                name="dat_export_access_approval_unique_request_user",
            ),
        ),
    ]
