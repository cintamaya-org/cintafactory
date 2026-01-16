from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dat", "0009_dat_reserve_history_action"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DATSectionAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("storage_path", models.CharField(max_length=512, verbose_name="Chemin de stockage")),
                ("original_name", models.CharField(max_length=255, verbose_name="Nom d'origine")),
                ("display_name", models.CharField(max_length=255, verbose_name="Nom affiché")),
                ("extension", models.CharField(max_length=16, verbose_name="Extension")),
                ("size", models.PositiveIntegerField(verbose_name="Taille")),
                ("content_type", models.CharField(blank=True, max_length=100, verbose_name="Type de contenu")),
                ("uploaded_by_display", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Créé le")),
                (
                    "section",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="attachments",
                        to="dat.datsection",
                        verbose_name="Section",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="dat_section_attachments",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Déposé par",
                    ),
                ),
            ],
            options={
                "verbose_name": "Pièce jointe de section",
                "verbose_name_plural": "Pièces jointes de section",
                "db_table": "dat_section_attachment",
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
