from django.db import migrations, models
import django.db.models.deletion


def forwards_create_messages(apps, schema_editor):
    NotificationMessage = apps.get_model("workflows", "NotificationMessage")
    UserNotification = apps.get_model("workflows", "UserNotification")
    for notification in UserNotification.objects.all().iterator():
        content = getattr(notification, "message", "") or ""
        message_obj, _ = NotificationMessage.objects.get_or_create(
            content=content,
        )
        notification.notification_message = message_obj
        notification.save(update_fields=["notification_message"])


class Migration(migrations.Migration):

    dependencies = [
        ("workflows", "0004_notificationtype"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationMessage",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("content", models.TextField(blank=True, default="", unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "workflow_notification_message",
                "ordering": ["pk"],
                "verbose_name": "Notification message",
                "verbose_name_plural": "Notification messages",
            },
        ),
        migrations.AddField(
            model_name="usernotification",
            name="notification_message",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="user_notifications",
                to="workflows.notificationmessage",
            ),
        ),
        migrations.RunPython(forwards_create_messages, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="usernotification",
            name="message",
        ),
        migrations.AlterField(
            model_name="usernotification",
            name="notification_message",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="user_notifications",
                to="workflows.notificationmessage",
            ),
        ),
    ]
