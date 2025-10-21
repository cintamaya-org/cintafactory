from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("users", "0004_drop_role_level"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Workflow",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("code", models.SlugField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workflows",
                        to="contenttypes.contenttype",
                    ),
                ),
            ],
            options={
                "verbose_name": "Workflow",
                "verbose_name_plural": "Workflows",
                "ordering": ["name"],
                "db_table": "workflow_definition",
            },
        ),
        migrations.CreateModel(
            name="WorkflowStep",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("key", models.SlugField(max_length=64)),
                ("name", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True)),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "state",
                    models.CharField(
                        help_text="Code stored on the target object to represent this step",
                        max_length=64,
                    ),
                ),
                (
                    "is_initial",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this step is the default/start of the workflow.",
                    ),
                ),
                (
                    "workflow",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="steps",
                        to="workflows.workflow",
                    ),
                ),
            ],
            options={
                "verbose_name": "Workflow step",
                "verbose_name_plural": "Workflow steps",
                "ordering": ["order", "pk"],
                "db_table": "workflow_step",
                "unique_together": {("workflow", "key"), ("workflow", "state")},
            },
        ),
        migrations.CreateModel(
            name="WorkflowStepPermission",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                (
                    "permission_type",
                    models.CharField(
                        choices=[("read", "Read"), ("write", "Write")],
                        max_length=5,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "role",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workflow_step_permissions",
                        to="users.role",
                    ),
                ),
                (
                    "step",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="permissions",
                        to="workflows.workflowstep",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workflow_step_permissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Workflow step permission",
                "verbose_name_plural": "Workflow step permissions",
                "ordering": ["step", "permission_type", "role__name", "user__username"],
                "db_table": "workflow_step_permission",
            },
        ),
        migrations.AddConstraint(
            model_name="workflowsteppermission",
            constraint=models.CheckConstraint(
                check=models.Q(("role__isnull", False)) | models.Q(("user__isnull", False)),
                name="workflow_step_permission_role_or_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowsteppermission",
            constraint=models.UniqueConstraint(
                condition=models.Q(("role__isnull", False)),
                fields=("step", "permission_type", "role"),
                name="workflow_step_permission_unique_role",
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowsteppermission",
            constraint=models.UniqueConstraint(
                condition=models.Q(("user__isnull", False)),
                fields=("step", "permission_type", "user"),
                name="workflow_step_permission_unique_user",
            ),
        ),
    ]
