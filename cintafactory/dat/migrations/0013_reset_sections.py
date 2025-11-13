from django.db import migrations

from ..sections import ensure_default_sections


def reset_sections(apps, schema_editor):
    DATPartEntry = apps.get_model("dat", "DATPartEntry")
    DATSectionPart = apps.get_model("dat", "DATSectionPart")
    DATSection = apps.get_model("dat", "DATSection")
    DAT = apps.get_model("dat", "DAT")

    db_alias = schema_editor.connection.alias

    DATPartEntry.objects.using(db_alias).all().delete()
    DATSectionPart.objects.using(db_alias).all().delete()
    DATSection.objects.using(db_alias).all().delete()

    for dat in DAT.objects.using(db_alias).all():
        ensure_default_sections(dat, apps=apps)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("dat", "0012_populate_default_sections"),
    ]

    operations = [
        migrations.RunPython(reset_sections, noop),
    ]
