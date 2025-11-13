from django.db import migrations, models


def forwards_copy_values(apps, schema_editor):
    DATPart = apps.get_model("dat", "DATPart")
    DATPartEntry = apps.get_model("dat", "DATPartEntry")
    db_alias = schema_editor.connection.alias
    entries_to_create = []
    for part in DATPart.objects.using(db_alias).all():
        value = getattr(part, "value", None)
        if value in (None, ""):
            continue
        entries_to_create.append(
            DATPartEntry(
                part_id=part.pk,
                value=value,
                created_at=part.created_at,
                updated_at=part.updated_at,
            )
        )
    if entries_to_create:
        DATPartEntry.objects.using(db_alias).bulk_create(entries_to_create)


def backwards_copy_values(apps, schema_editor):
    DATPart = apps.get_model("dat", "DATPart")
    DATPartEntry = apps.get_model("dat", "DATPartEntry")
    db_alias = schema_editor.connection.alias
    for part in DATPart.objects.using(db_alias).all():
        entry = (
            DATPartEntry.objects.using(db_alias)
            .filter(part_id=part.pk)
            .order_by("-updated_at", "-id")
            .first()
        )
        value = entry.value if entry else None
        setattr(part, "value", value)
        part.save(update_fields=["value"])


class Migration(migrations.Migration):

    dependencies = [
        ("dat", "0014_alter_dathistory_action_alter_datpartentry_data_type"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="DATSectionPart",
            new_name="DATSubSection",
        ),
        migrations.AlterModelOptions(
            name="datsubsection",
            options={
                "ordering": ["order", "id"],
                "verbose_name": "Sous-section de DAT",
                "verbose_name_plural": "Sous-sections de DAT",
            },
        ),
        migrations.AlterModelTable(
            name="datsubsection",
            table="dat_sub_section",
        ),
        migrations.AlterField(
            model_name="datsubsection",
            name="section",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="sub_sections",
                to="dat.datsection",
                verbose_name="Section",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="datsubsection",
            unique_together={("section", "slug")},
        ),
        migrations.RenameModel(
            old_name="DATPartEntry",
            new_name="DATPart",
        ),
        migrations.AlterModelOptions(
            name="datpart",
            options={
                "ordering": ["order", "id"],
                "verbose_name": "Partie de DAT",
                "verbose_name_plural": "Parties de DAT",
            },
        ),
        migrations.AlterModelTable(
            name="datpart",
            table="dat_part",
        ),
        migrations.RenameField(
            model_name="datpart",
            old_name="part",
            new_name="sub_section",
        ),
        migrations.AlterField(
            model_name="datpart",
            name="sub_section",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="parts",
                to="dat.datsubsection",
                verbose_name="Sous-section",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="datpart",
            unique_together={("sub_section", "key")},
        ),
        migrations.RunSQL(
            sql="ALTER TABLE dat_part DROP CONSTRAINT IF EXISTS dat_part_entry_part_id_c6265e3a;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DROP INDEX IF EXISTS dat_part_entry_part_id_c6265e3a;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.CreateModel(
            name="DATPartEntry",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("value", models.JSONField(blank=True, null=True, verbose_name="Valeur")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")),
                (
                    "part",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="entries",
                        to="dat.datpart",
                        verbose_name="Partie",
                        db_index=False,
                    ),
                ),
            ],
            options={
                "db_table": "dat_part_entry",
                "ordering": ["-updated_at", "-id"],
                "verbose_name": "Valeur de partie de DAT",
                "verbose_name_plural": "Valeurs de parties de DAT",
                "indexes": [
                    models.Index(fields=["part"], name="dat_part_entry_part_idx"),
                ],
            },
        ),
        migrations.RunPython(forwards_copy_values, backwards_copy_values),
        migrations.RemoveField(
            model_name="datpart",
            name="value",
        ),
    ]
