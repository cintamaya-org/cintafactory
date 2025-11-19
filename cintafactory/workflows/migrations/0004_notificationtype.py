from django.db import migrations, models
import django.db.models.deletion


def forwards_create_types(apps, schema_editor):
    NotificationType = apps.get_model("workflows", "NotificationType")
    UserNotification = apps.get_model("workflows", "UserNotification")
    default_level = "info"
    for notification in UserNotification.objects.all().iterator():
        level = notification.level or default_level
        notification_type, _ = NotificationType.objects.get_or_create(
            title=notification.title,
            level=level,
        )
        notification.notification_type = notification_type
        notification.save(update_fields=["notification_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("workflows", "0003_alter_usernotification_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationType",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("title", models.CharField(max_length=255)),
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "workflow_notification_type",
                "ordering": ["title", "level", "pk"],
                "verbose_name": "Notification type",
                "verbose_name_plural": "Notification types",
                "unique_together": {("title", "level")},
            },
        ),
        migrations.AddField(
            model_name="usernotification",
            name="notification_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="user_notifications",
                to="workflows.notificationtype",
            ),
        ),
        migrations.RunPython(forwards_create_types, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="usernotification",
            name="level",
        ),
        migrations.RemoveField(
            model_name="usernotification",
            name="title",
        ),
        migrations.AlterField(
            model_name="usernotification",
            name="notification_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="user_notifications",
                to="workflows.notificationtype",
            ),
        ),
    ]
