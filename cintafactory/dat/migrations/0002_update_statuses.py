from __future__ import annotations

from django.db import migrations, models


NEW_CHOICES = [
    ("besoin_dal", "Nouveau besoin (DAL)"),
    ("nouveau_dat", "Nouveau dossier (DAT)"),
    ("validation_referent", "Validation du referent"),
    ("instruction_urbanisme", "Instruction urbanisme"),
    ("documentation_technique", "Documentation architecture technique"),
    ("analyse_risque", "Analyse de risque"),
    ("preconisation_securite", "Preconisation securite"),
    ("derogation_pssi", "Derogation PSSI"),
    ("architecture_prete", "Architecture prete"),
    ("inscription_offres_service", "Inscription offres de service"),
    ("validation_capacitaire", "Validation capacitaire"),
    ("cartographie_flux", "Cartographie des flux"),
    ("validation_infrastructure", "Validation infrastructure / exploitation"),
    ("dat_valide", "DAT valide"),
    ("presentation_comite", "Presentation en comite"),
    ("levee_reserve", "Levee de reserve"),
    ("dat_publie", "DAT publie"),
]


def migrate_status_forward(apps, schema_editor):
    DAT = apps.get_model("dat", "DAT")
    status_map = {
        "draft": "besoin_dal",
        "review": "validation_referent",
        "validated": "dat_valide",
        "archived": "dat_publie",
    }
    for old, new in status_map.items():
        DAT.objects.filter(status=old).update(status=new)


def migrate_status_backward(apps, schema_editor):
    DAT = apps.get_model("dat", "DAT")
    status_map = {
        "besoin_dal": "draft",
        "nouveau_dat": "draft",
        "validation_referent": "review",
        "instruction_urbanisme": "review",
        "documentation_technique": "review",
        "analyse_risque": "review",
        "preconisation_securite": "review",
        "derogation_pssi": "review",
        "architecture_prete": "validated",
        "inscription_offres_service": "validated",
        "validation_capacitaire": "validated",
        "cartographie_flux": "validated",
        "validation_infrastructure": "validated",
        "dat_valide": "validated",
        "presentation_comite": "validated",
        "levee_reserve": "review",
        "dat_publie": "archived",
    }
    for new, old in status_map.items():
        DAT.objects.filter(status=new).update(status=old)


class Migration(migrations.Migration):

    dependencies = [
        ("dat", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dat",
            name="status",
            field=models.CharField(
                choices=NEW_CHOICES,
                default="besoin_dal",
                max_length=64,
            ),
        ),
        migrations.RunPython(migrate_status_forward, migrate_status_backward),
    ]
