from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


DAT_STATUS_CHOICES = [
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

HISTORY_ACTION_CHOICES = [
    ("created", "Création"),
    ("updated", "Mise à jour"),
    ("status_changed", "Changement de statut"),
    ("owner_changed", "Changement de responsable"),
    ("section_updated", "Section mise à jour"),
    ("deleted", "Suppression"),
]

DAT_PART_TYPE_CHOICES = [
    ("text", "Texte"),
    ("long_text", "Texte long"),
    ("integer", "Nombre entier"),
    ("decimal", "Nombre décimal"),
    ("date", "Date"),
    ("boolean", "Booléen"),
    ("json", "JSON"),
    ("url", "Lien"),
    ("repeater", "Tableau dynamique"),
]


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("users", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Application",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=64, unique=True, verbose_name="Code")),
                ("name", models.CharField(max_length=200, verbose_name="Nom")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")),
                (
                    "business_direction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="applications",
                        to="users.businessdirection",
                        verbose_name="Direction métier",
                    ),
                ),
            ],
            options={
                "db_table": "dat_application",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="DAT",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference", models.CharField(max_length=64, unique=True)),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=DAT_STATUS_CHOICES,
                        default="demande_initiale",
                        max_length=64,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("pdf_export_in_progress", models.BooleanField(default=False)),
                ("pdf_export_requested_at", models.DateTimeField(blank=True, null=True)),
                ("pdf_export_requested_by_display", models.CharField(blank=True, max_length=255)),
                (
                    "application",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dats",
                        to="dat.application",
                    ),
                ),
                (
                    "business_direction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dats",
                        to="users.businessdirection",
                        verbose_name="Direction métier",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dats",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "pdf_export_requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "dat_dat",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DATSection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Titre")),
                ("slug", models.SlugField(max_length=100, verbose_name="Identifiant")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="Ordre")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")),
                (
                    "dat",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sections",
                        to="dat.dat",
                        verbose_name="DAT",
                    ),
                ),
                (
                    "allowed_roles",
                    models.ManyToManyField(
                        blank=True,
                        related_name="editable_dat_sections",
                        to="users.role",
                        verbose_name="Rôles autorisés",
                    ),
                ),
            ],
            options={
                "db_table": "dat_section",
                "ordering": ["order", "id"],
                "unique_together": {("dat", "slug")},
                "verbose_name": "Section de DAT",
                "verbose_name_plural": "Sections de DAT",
            },
        ),
        migrations.CreateModel(
            name="DATSubSection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Titre")),
                ("slug", models.SlugField(max_length=100, verbose_name="Identifiant")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="Ordre")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")),
                (
                    "allowed_roles",
                    models.ManyToManyField(
                        blank=True,
                        related_name="editable_dat_sub_sections",
                        to="users.role",
                        verbose_name="Rôles autorisés",
                    ),
                ),
                (
                    "section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sub_sections",
                        to="dat.datsection",
                        verbose_name="Section",
                    ),
                ),
            ],
            options={
                "db_table": "dat_sub_section",
                "ordering": ["order", "id"],
                "unique_together": {("section", "slug")},
                "verbose_name": "Sous-section de DAT",
                "verbose_name_plural": "Sous-sections de DAT",
            },
        ),
        migrations.CreateModel(
            name="DATParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "dat",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participants",
                        to="dat.dat",
                        verbose_name="DAT",
                    ),
                ),
                (
                    "role",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dat_participants",
                        to="users.role",
                        verbose_name="Rôle",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dat_participations",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Utilisateur",
                    ),
                ),
            ],
            options={
                "db_table": "dat_participant",
                "ordering": ["dat_id", "role__name", "user__username"],
                "verbose_name": "Participant du DAT",
                "verbose_name_plural": "Participants du DAT",
            },
        ),
        migrations.CreateModel(
            name="DATHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=HISTORY_ACTION_CHOICES, max_length=32)),
                (
                    "status_before",
                    models.CharField(
                        blank=True,
                        choices=DAT_STATUS_CHOICES,
                        max_length=64,
                        null=True,
                    ),
                ),
                (
                    "status_after",
                    models.CharField(
                        blank=True,
                        choices=DAT_STATUS_CHOICES,
                        max_length=64,
                        null=True,
                    ),
                ),
                ("performed_by_display", models.CharField(blank=True, max_length=255)),
                ("details", models.JSONField(blank=True, null=True)),
                ("performed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "dat",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="history_entries",
                        to="dat.dat",
                    ),
                ),
                (
                    "performed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dat_history_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "dat_history",
                "ordering": ["-performed_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="DATPart",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(max_length=100, verbose_name="Clé")),
                ("label", models.CharField(max_length=200, verbose_name="Libellé")),
                (
                    "data_type",
                    models.CharField(
                        choices=DAT_PART_TYPE_CHOICES,
                        default="text",
                        max_length=20,
                        verbose_name="Type de donnée",
                    ),
                ),
                ("required", models.BooleanField(default=False, verbose_name="Obligatoire")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="Ordre")),
                ("config", models.JSONField(blank=True, null=True, verbose_name="Configuration")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")),
                (
                    "sub_section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="parts",
                        to="dat.datsubsection",
                        verbose_name="Sous-section",
                    ),
                ),
            ],
            options={
                "db_table": "dat_part",
                "ordering": ["order", "id"],
                "unique_together": {("sub_section", "key")},
                "verbose_name": "Partie de DAT",
                "verbose_name_plural": "Parties de DAT",
            },
        ),
        migrations.CreateModel(
            name="DATPartEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("value", models.JSONField(blank=True, null=True, verbose_name="Valeur")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")),
                (
                    "part",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="dat.datpart",
                        verbose_name="Partie",
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
        migrations.AddConstraint(
            model_name="datparticipant",
            constraint=models.UniqueConstraint(fields=("dat", "role"), name="dat_participant_unique_role_per_dat"),
        ),
        migrations.AddConstraint(
            model_name="datparticipant",
            constraint=models.UniqueConstraint(fields=("dat", "user"), name="dat_participant_unique_user_per_dat"),
        ),
    ]
