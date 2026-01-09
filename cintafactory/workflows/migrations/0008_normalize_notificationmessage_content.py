from django.db import migrations, models
from django.db.models import Q


def normalize_notification_messages(apps, schema_editor):
    NotificationMessage = apps.get_model("workflows", "NotificationMessage")
    UserNotification = apps.get_model("workflows", "UserNotification")

    empty_messages = list(
        NotificationMessage.objects.filter(
            Q(content__isnull=True) | Q(content="")
        ).order_by("pk")
    )
    if not empty_messages:
        return

    canonical = None
    for message in empty_messages:
        if message.content == "":
            canonical = message
            break
    if canonical is None:
        canonical = empty_messages[0]

    if canonical.content != "":
        NotificationMessage.objects.filter(pk=canonical.pk).update(content="")

    merge_ids = [message.pk for message in empty_messages if message.pk != canonical.pk]
    if merge_ids:
        UserNotification.objects.filter(notification_message_id__in=merge_ids).update(
            notification_message_id=canonical.pk
        )
        NotificationMessage.objects.filter(pk__in=merge_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("workflows", "0007_historynotificationseen"),
    ]

    operations = [
        migrations.RunPython(normalize_notification_messages, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="notificationmessage",
            name="content",
            field=models.TextField(blank=True, default="", unique=True),
        ),
    ]
