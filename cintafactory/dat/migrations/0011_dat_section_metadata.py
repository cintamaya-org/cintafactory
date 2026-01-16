from django.db import migrations, models


def create_section_metadata(apps, schema_editor):
    DATSection = apps.get_model("dat", "DATSection")
    DATSectionMetadata = apps.get_model("dat", "DATSectionMetadata")
    for section in DATSection.objects.all():
        DATSectionMetadata.objects.update_or_create(
            section=section,
            defaults={
                "title": section.title,
                "slug": section.slug,
                "description": section.description,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("dat", "0010_dat_section_attachment"),
    ]

    operations = [
        migrations.CreateModel(
            name="DATSectionMetadata",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Titre")),
                ("slug", models.SlugField(max_length=100, verbose_name="Identifiant")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                (
                    "section",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="metadata",
                        to="dat.datsection",
                        verbose_name="Section",
                    ),
                ),
            ],
            options={
                "verbose_name": "Metadata de section",
                "verbose_name_plural": "Metadata de sections",
                "db_table": "dat_section_metada",
            },
        ),
        migrations.RunPython(create_section_metadata, migrations.RunPython.noop),
    ]
