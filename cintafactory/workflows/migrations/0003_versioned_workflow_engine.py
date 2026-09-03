# Generated manually for versioned workflow subsystem.

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("workflows", "0002_alter_notificationmessage_content"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkflowDefinitionVersion",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("version", models.PositiveIntegerField()),
                ("checksum", models.CharField(max_length=64)),
                ("specification", models.JSONField()),
                ("published_at", models.DateTimeField(auto_now_add=True)),
                (
                    "workflow",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="workflows.workflow",
                    ),
                ),
            ],
            options={
                "db_table": "workflow_definition_version",
                "ordering": ["workflow", "-version"],
            },
        ),
        migrations.AddConstraint(
            model_name="workflowdefinitionversion",
            constraint=models.UniqueConstraint(
                fields=("workflow", "version"),
                name="workflow_definition_version_unique_number",
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowdefinitionversion",
            constraint=models.UniqueConstraint(
                fields=("workflow", "checksum"),
                name="workflow_definition_version_unique_checksum",
            ),
        ),
        migrations.AddField(
            model_name="workflow",
            name="active_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="active_for_workflows",
                to="workflows.workflowdefinitionversion",
            ),
        ),
        migrations.CreateModel(
            name="WorkflowInstance",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("object_id", models.CharField(max_length=64)),
                ("current_state", models.CharField(max_length=64)),
                ("data", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workflow_instances",
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "definition_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="instances",
                        to="workflows.workflowdefinitionversion",
                    ),
                ),
                (
                    "workflow",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="instances",
                        to="workflows.workflow",
                    ),
                ),
            ],
            options={
                "db_table": "workflow_instance",
                "ordering": ["-updated_at", "-pk"],
                "indexes": [
                    models.Index(
                        fields=["workflow", "current_state"],
                        name="workflow_instance_state_idx",
                    )
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="workflowinstance",
            constraint=models.UniqueConstraint(
                fields=("workflow", "content_type", "object_id"),
                name="workflow_instance_unique_object",
            ),
        ),
        migrations.CreateModel(
            name="WorkflowTransitionEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("event", models.SlugField(max_length=64)),
                ("from_state", models.CharField(max_length=64)),
                ("to_state", models.CharField(max_length=64)),
                ("actor_display", models.CharField(blank=True, max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="workflow_transition_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "instance",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transition_events",
                        to="workflows.workflowinstance",
                    ),
                ),
            ],
            options={
                "db_table": "workflow_transition_event",
                "ordering": ["-occurred_at", "-pk"],
                "indexes": [
                    models.Index(
                        fields=["instance", "occurred_at"],
                        name="workflow_transition_time_idx",
                    )
                ],
            },
        ),
    ]
