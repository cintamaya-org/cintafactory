from django.db import migrations

from ..sections import ensure_default_sections


def create_sections(apps, schema_editor):
    DAT = apps.get_model("dat", "DAT")
    db_alias = schema_editor.connection.alias
    for dat in DAT.objects.using(db_alias).all():
        ensure_default_sections(dat, apps=apps)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("dat", "0011_dat_sections"),
    ]

    operations = [
        migrations.RunPython(create_sections, noop),
    ]
