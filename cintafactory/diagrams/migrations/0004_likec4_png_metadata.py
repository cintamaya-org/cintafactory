from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("diagrams", "0003_remove_diagram_xml"),
    ]

    operations = [
        migrations.AddField(
            model_name="likec4file",
            name="png_path",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="likec4file",
            name="png_content_type",
            field=models.CharField(blank=True, default="image/png", max_length=200),
        ),
        migrations.AddField(
            model_name="likec4file",
            name="png_size",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="likec4file",
            name="png_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
