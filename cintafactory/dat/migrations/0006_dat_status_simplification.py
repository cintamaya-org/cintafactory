from django.db import migrations, models


NEW_STATUS_CHOICES = [
    ("nouvelle_demande", "Nouvelle demande"),
    ("en_cours", "En cours"),
    ("en_attente_de_revue", "En Attente de revue"),
    ("valider", "Valider"),
    ("refuse", "Refusé"),
    ("reserve", "Reserve"),
]

STATUS_MAPPING = {
    "demande_initiale": "nouvelle_demande",
    "validation_referent": "en_cours",
    "instruction_architecture": "en_cours",
    "instruction_urbanisme": "en_cours",
    "analyse_securite": "en_cours",
    "generation_cartographie": "en_cours",
    "revue_infra_exploitation": "en_cours",
    "validation_finale": "en_attente_de_revue",
    "validation_reserve": "reserve",
    "dat_refuse": "refuse",
    "dat_valide": "valider",
}


def forward_status_mapping(apps, schema_editor):
    dat_model = apps.get_model("dat", "DAT")
    history_model = apps.get_model("dat", "DATHistory")

    for dat in dat_model.objects.all():
        new_status = STATUS_MAPPING.get(dat.status)
        if new_status and new_status != dat.status:
            dat.status = new_status
            dat.save(update_fields=["status"])

    for entry in history_model.objects.all():
        changed = False
        if entry.status_before in STATUS_MAPPING:
            entry.status_before = STATUS_MAPPING[entry.status_before]
            changed = True
        if entry.status_after in STATUS_MAPPING:
            entry.status_after = STATUS_MAPPING[entry.status_after]
            changed = True
        if changed:
            entry.save(update_fields=["status_before", "status_after"])


class Migration(migrations.Migration):
    dependencies = [
        ("dat", "0005_application_business_direction_nullable"),
    ]

    operations = [
        migrations.RunPython(forward_status_mapping, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="dat",
            name="status",
            field=models.CharField(
                choices=NEW_STATUS_CHOICES,
                default="nouvelle_demande",
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="dathistory",
            name="status_before",
            field=models.CharField(
                blank=True,
                choices=NEW_STATUS_CHOICES,
                max_length=64,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="dathistory",
            name="status_after",
            field=models.CharField(
                blank=True,
                choices=NEW_STATUS_CHOICES,
                max_length=64,
                null=True,
            ),
        ),
    ]
