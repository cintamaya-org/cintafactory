from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dat", "0010_require_dat_participants"),
        ("users", "0008_ensure_super_admin"),
    ]

    operations = [
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
            ],
            options={
                "db_table": "dat_section",
                "ordering": ["order", "id"],
                "verbose_name": "Section de DAT",
                "verbose_name_plural": "Sections de DAT",
                "unique_together": {("dat", "slug")},
            },
        ),
        migrations.CreateModel(
            name="DATSectionPart",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Titre")),
                ("slug", models.SlugField(max_length=100, verbose_name="Identifiant")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="Ordre")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")),
                (
                    "section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="parts",
                        to="dat.datsection",
                        verbose_name="Section",
                    ),
                ),
            ],
            options={
                "db_table": "dat_section_part",
                "ordering": ["order", "id"],
                "verbose_name": "Partie de section de DAT",
                "verbose_name_plural": "Parties de section de DAT",
                "unique_together": {("section", "slug")},
            },
        ),
        migrations.CreateModel(
            name="DATPartEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(max_length=100, verbose_name="Clé")),
                ("label", models.CharField(max_length=200, verbose_name="Libellé")),
                (
                    "data_type",
                    models.CharField(
                        choices=[
                            ("text", "Texte"),
                            ("long_text", "Texte long"),
                            ("integer", "Nombre entier"),
                            ("decimal", "Nombre décimal"),
                            ("date", "Date"),
                            ("boolean", "Booléen"),
                            ("json", "JSON"),
                            ("url", "Lien"),
                        ],
                        default="text",
                        max_length=20,
                        verbose_name="Type de donnée",
                    ),
                ),
                ("value", models.JSONField(blank=True, null=True, verbose_name="Valeur")),
                ("required", models.BooleanField(default=False, verbose_name="Obligatoire")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="Ordre")),
                ("config", models.JSONField(blank=True, null=True, verbose_name="Configuration")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")),
                (
                    "part",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="dat.datsectionpart",
                        verbose_name="Partie",
                    ),
                ),
            ],
            options={
                "db_table": "dat_part_entry",
                "ordering": ["order", "id"],
                "verbose_name": "Donnée de partie de DAT",
                "verbose_name_plural": "Données de partie de DAT",
                "unique_together": {("part", "key")},
            },
        ),
        migrations.AddField(
            model_name="datsection",
            name="allowed_roles",
            field=models.ManyToManyField(
                blank=True,
                related_name="editable_dat_sections",
                to="users.role",
                verbose_name="Rôles autorisés",
            ),
        ),
    ]
