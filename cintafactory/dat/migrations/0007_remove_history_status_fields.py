from django.db import migrations

STATUS_LABELS = {
    "nouvelle_demande": "Nouvelle demande",
    "en_cours": "En cours",
    "en_attente_de_revue": "En Attente de revue",
    "valider": "Valider",
    "refuse": "Refusé",
    "reserve": "Reserve",
}


def migrate_status_details(apps, schema_editor):
    History = apps.get_model("dat", "DATHistory")
    for entry in History.objects.filter(action="status_changed"):
        details = entry.details or {}
        if not isinstance(details, dict):
            details = {}
        changed = False
        if not details.get("from") and entry.status_before:
            details["from"] = STATUS_LABELS.get(entry.status_before, entry.status_before)
            changed = True
        if not details.get("to") and entry.status_after:
            details["to"] = STATUS_LABELS.get(entry.status_after, entry.status_after)
            changed = True
        if changed:
            entry.details = details
            entry.save(update_fields=["details"])


class Migration(migrations.Migration):
    dependencies = [
        ("dat", "0006_dat_status_simplification"),
    ]

    operations = [
        migrations.RunPython(migrate_status_details, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="dathistory",
            name="status_before",
        ),
        migrations.RemoveField(
            model_name="dathistory",
            name="status_after",
        ),
    ]
