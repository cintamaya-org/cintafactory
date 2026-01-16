from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("diagrams", "0002_diagram_storage_migration"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="diagram",
            name="xml",
        ),
    ]
