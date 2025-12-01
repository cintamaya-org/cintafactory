from django.db import migrations, models


def _blank_to_null_content(apps, schema_editor):
    NotificationMessage = apps.get_model("workflows", "NotificationMessage")
    NotificationMessage.objects.filter(content="").update(content=None)


class Migration(migrations.Migration):

    dependencies = [
        ("workflows", "0005_notificationmessage"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notificationmessage",
            name="content",
            field=models.TextField(blank=True, default=None, null=True, unique=True),
        ),
        migrations.RunPython(_blank_to_null_content, migrations.RunPython.noop),
    ]
