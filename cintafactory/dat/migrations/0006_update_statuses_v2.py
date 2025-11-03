from __future__ import annotations

from django.db import migrations, models


NEW_CHOICES = [
    ("demande_initiale", "Demande initiale"),
    ("validation_referent", "Validation du referent"),
    ("instruction_architecture", "Instruction architecture technique"),
    ("instruction_urbanisme", "Instruction urbanisme"),
    ("analyse_securite", "Analyse cyber securite"),
    ("generation_cartographie", "Generation cartographie et inventaire"),
    ("revue_infra_exploitation", "Revue infra / exploitation"),
    ("validation_finale", "Validation finale pluridisciplinaire"),
    ("validation_reserve", "Validation avec reserve"),
    ("dat_refuse", "DAT refuse"),
    ("dat_valide", "DAT valide"),
]


STATUS_FORWARD_MAP = {
    "besoin_dal": "demande_initiale",
    "nouveau_dat": "demande_initiale",
    "validation_referent": "validation_referent",
    "documentation_technique": "instruction_architecture",
    "architecture_prete": "instruction_architecture",
    "instruction_urbanisme": "instruction_urbanisme",
    "analyse_risque": "analyse_securite",
    "preconisation_securite": "analyse_securite",
    "derogation_pssi": "analyse_securite",
    "cartographie_flux": "generation_cartographie",
    "inscription_offres_service": "revue_infra_exploitation",
    "validation_capacitaire": "revue_infra_exploitation",
    "validation_infrastructure": "revue_infra_exploitation",
    "presentation_comite": "validation_finale",
    "levee_reserve": "validation_reserve",
    "dat_publie": "dat_valide",
    "dat_valide": "dat_valide",
}


STATUS_BACKWARD_MAP = {
    "demande_initiale": "besoin_dal",
    "validation_referent": "validation_referent",
    "instruction_architecture": "documentation_technique",
    "instruction_urbanisme": "instruction_urbanisme",
    "analyse_securite": "analyse_risque",
    "generation_cartographie": "cartographie_flux",
    "revue_infra_exploitation": "validation_infrastructure",
    "validation_finale": "presentation_comite",
    "validation_reserve": "levee_reserve",
    "dat_refuse": "presentation_comite",
    "dat_valide": "dat_valide",
}


def migrate_status_forward(apps, schema_editor):
    DAT = apps.get_model("dat", "DAT")
    for old, new in STATUS_FORWARD_MAP.items():
        DAT.objects.filter(status=old).update(status=new)


def migrate_status_backward(apps, schema_editor):
    DAT = apps.get_model("dat", "DAT")
    for new, old in STATUS_BACKWARD_MAP.items():
        DAT.objects.filter(status=new).update(status=old)


class Migration(migrations.Migration):

    dependencies = [
        ("dat", "0005_alter_application_code_alter_application_created_at_and_more"),
    ]

    operations = [
        migrations.RunPython(migrate_status_forward, migrate_status_backward),
        migrations.AlterField(
            model_name="dat",
            name="status",
            field=models.CharField(
                choices=NEW_CHOICES,
                default="demande_initiale",
                max_length=64,
            ),
        ),
    ]
