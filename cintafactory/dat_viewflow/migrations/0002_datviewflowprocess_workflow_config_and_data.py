from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dat_viewflow", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="datviewflowprocess",
            name="workflow_config",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="datviewflowprocess",
            name="workflow_data",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
