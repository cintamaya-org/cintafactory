from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("diagrams", "0006_likec4_png_paths"),
    ]

    operations = [
        migrations.AddField(
            model_name="diagram",
            name="png_paths",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
