from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dat", "0006_update_statuses_v2"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DATHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("created", "Création"), ("updated", "Mise à jour"), ("status_changed", "Changement de statut"), ("owner_changed", "Changement de responsable"), ("deleted", "Suppression")], max_length=32)),
                ("status_before", models.CharField(blank=True, choices=[("demande_initiale", "Demande initiale"), ("validation_referent", "Validation du referent"), ("instruction_architecture", "Instruction architecture technique"), ("instruction_urbanisme", "Instruction urbanisme"), ("analyse_securite", "Analyse cyber securite"), ("generation_cartographie", "Generation cartographie et inventaire"), ("revue_infra_exploitation", "Revue infra / exploitation"), ("validation_finale", "Validation finale pluridisciplinaire"), ("validation_reserve", "Validation avec reserve"), ("dat_refuse", "DAT refuse"), ("dat_valide", "DAT valide")], max_length=64, null=True)),
                ("status_after", models.CharField(blank=True, choices=[("demande_initiale", "Demande initiale"), ("validation_referent", "Validation du referent"), ("instruction_architecture", "Instruction architecture technique"), ("instruction_urbanisme", "Instruction urbanisme"), ("analyse_securite", "Analyse cyber securite"), ("generation_cartographie", "Generation cartographie et inventaire"), ("revue_infra_exploitation", "Revue infra / exploitation"), ("validation_finale", "Validation finale pluridisciplinaire"), ("validation_reserve", "Validation avec reserve"), ("dat_refuse", "DAT refuse"), ("dat_valide", "DAT valide")], max_length=64, null=True)),
                ("performed_by_display", models.CharField(blank=True, max_length=255)),
                ("details", models.JSONField(blank=True, null=True)),
                ("performed_at", models.DateTimeField(auto_now_add=True)),
                ("dat", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="history_entries", to="dat.dat")),
                ("performed_by", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="dat_history_entries", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "dat_history",
                "ordering": ["-performed_at", "-id"],
            },
        ),
    ]
