from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("diagrams", "0005_merge_20260115_1535"),
    ]

    operations = [
        migrations.AddField(
            model_name="likec4file",
            name="png_paths",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
