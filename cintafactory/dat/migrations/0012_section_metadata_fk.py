from django.db import migrations, models


def forward_link_metadata(apps, schema_editor):
    DATSection = apps.get_model("dat", "DATSection")
    DATSectionMetadata = apps.get_model("dat", "DATSectionMetadata")
    for section in DATSection.objects.all():
        existing = None
        try:
            existing = DATSectionMetadata.objects.filter(section_id=section.pk).first()
        except Exception:
            existing = None
        if existing is None:
            existing = DATSectionMetadata.objects.create(
                title=section.title,
                slug=section.slug,
                description=section.description,
            )
        section.metadata_id = existing.pk
        section.save(update_fields=["metadata"])


def reverse_unlink_metadata(apps, schema_editor):
    DATSection = apps.get_model("dat", "DATSection")
    DATSectionMetadata = apps.get_model("dat", "DATSectionMetadata")
    for section in DATSection.objects.exclude(metadata_id=None):
        metadata = DATSectionMetadata.objects.filter(pk=section.metadata_id).first()
        if metadata is None:
            continue
        try:
            metadata.section_id = section.pk
            metadata.save(update_fields=["section"])
        except Exception:
            pass


class Migration(migrations.Migration):
    dependencies = [
        ("dat", "0011_dat_section_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="datsection",
            name="metadata",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="section",
                to="dat.datsectionmetadata",
                verbose_name="Metadata",
            ),
        ),
        migrations.RunPython(forward_link_metadata, reverse_unlink_metadata),
        migrations.RemoveField(
            model_name="datsectionmetadata",
            name="section",
        ),
        migrations.AlterField(
            model_name="datsection",
            name="metadata",
            field=models.OneToOneField(
                on_delete=models.deletion.PROTECT,
                related_name="section",
                to="dat.datsectionmetadata",
                verbose_name="Metadata",
            ),
        ),
    ]
