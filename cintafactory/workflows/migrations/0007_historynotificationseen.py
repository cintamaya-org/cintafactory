from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("dat", "0009_dat_reserve_history_action"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("workflows", "0006_alter_notificationmessage_content"),
    ]

    operations = [
        migrations.CreateModel(
            name="HistoryNotificationSeen",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("seen_at", models.DateTimeField(auto_now_add=True)),
                (
                    "history",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workflow_seen_by",
                        to="dat.dathistory",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workflow_history_notifications_seen",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "workflow_history_notification_seen",
                "ordering": ["-seen_at", "-pk"],
                "unique_together": {("user", "history")},
                "verbose_name": "Workflow history seen",
                "verbose_name_plural": "Workflow history seen",
            },
        ),
    ]
