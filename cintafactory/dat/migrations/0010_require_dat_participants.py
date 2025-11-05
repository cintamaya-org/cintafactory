from __future__ import annotations

from django.conf import settings
from django.db import migrations


REQUIRED_ROLE_SLUGS = (
    "porteur-demande",
    "architecte-referent",
    "architecte-technique",
    "urbaniste",
    "analyste-secu",
    "rssi",
    "comite-validation",
    "infra-exploitation",
)
PORTEUR_ROLE_SLUG = REQUIRED_ROLE_SLUGS[0]


def ensure_required_participants(apps, schema_editor):
    DAT = apps.get_model("dat", "DAT")
    DATParticipant = apps.get_model("dat", "DATParticipant")
    Role = apps.get_model("users", "Role")
    user_app_label, user_model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(user_app_label, user_model_name)

    roles = Role.objects.filter(slug__in=REQUIRED_ROLE_SLUGS)
    role_map = {role.slug: role for role in roles}

    for dat in DAT.objects.all():
        existing_participants = DATParticipant.objects.filter(
            dat=dat,
            role__slug__in=REQUIRED_ROLE_SLUGS,
        ).select_related("role")
        existing_map = {
            participant.role.slug: participant
            for participant in existing_participants
            if participant.role
        }

        for slug in REQUIRED_ROLE_SLUGS:
            role = role_map.get(slug)
            if role is None:
                continue

            participant = existing_map.get(slug)
            if participant:
                if slug == PORTEUR_ROLE_SLUG and dat.owner_id and participant.user_id != dat.owner_id:
                    participant.user_id = dat.owner_id
                    participant.save(update_fields=["user"])
                continue

            user_id = None
            if slug == PORTEUR_ROLE_SLUG and dat.owner_id:
                user_id = dat.owner_id
            else:
                user = (
                    User.objects.filter(role=role)
                    .order_by("id")
                    .first()
                )
                if user:
                    user_id = user.id

            if user_id:
                DATParticipant.objects.create(
                    dat_id=dat.id,
                    role_id=role.id,
                    user_id=user_id,
                )


class Migration(migrations.Migration):

    dependencies = [
        ("dat", "0009_seed_test_dat"),
    ]

    operations = [
        migrations.RunPython(ensure_required_participants, migrations.RunPython.noop),
    ]

