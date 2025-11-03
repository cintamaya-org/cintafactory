from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0007_create_default_users"),
        ("dat", "0007_dathistory"),
    ]

    operations = [
        migrations.CreateModel(
            name="DATParticipant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
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
        migrations.AddConstraint(
            model_name="datparticipant",
            constraint=models.UniqueConstraint(
                fields=("dat", "role"),
                name="dat_participant_unique_role_per_dat",
            ),
        ),
        migrations.AddConstraint(
            model_name="datparticipant",
            constraint=models.UniqueConstraint(
                fields=("dat", "user"),
                name="dat_participant_unique_user_per_dat",
            ),
        ),
    ]
