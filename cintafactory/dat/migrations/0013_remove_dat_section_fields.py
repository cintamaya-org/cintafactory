from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("dat", "0012_section_metadata_fk"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="datsection",
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name="datsection",
            name="description",
        ),
        migrations.RemoveField(
            model_name="datsection",
            name="slug",
        ),
        migrations.RemoveField(
            model_name="datsection",
            name="title",
        ),
    ]
