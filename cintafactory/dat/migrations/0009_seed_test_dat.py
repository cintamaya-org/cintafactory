from __future__ import annotations

from django.conf import settings
from django.db import migrations


TEST_REFERENCE = "DAT-TEST"
TEST_APPLICATION_CODE = "test-app"
TEST_APPLICATION_DEFAULTS = {
    "name": "Application Test",
    "description": (
        "Application de démonstration pour le DAT de test initial."
    ),
}
PARTICIPANT_MAPPINGS = (
    ("porteur_demande_user", "porteur-demande"),
    ("architecte_referent_user", "architecte-referent"),
    ("architecte_technique_user", "architecte-technique"),
    ("urbaniste_user", "urbaniste"),
    ("analyste_secu_user", "analyste-secu"),
    ("rssi_user", "rssi"),
    ("comite_validation_user", "comite-validation"),
    ("infra_exploitation_user", "infra-exploitation"),
)


def create_dat_with_participants(apps, schema_editor):
    Application = apps.get_model("dat", "Application")
    DAT = apps.get_model("dat", "DAT")
    DATParticipant = apps.get_model("dat", "DATParticipant")
    Role = apps.get_model("users", "Role")
    user_app_label, user_model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(user_app_label, user_model_name)

    application, _ = Application.objects.get_or_create(
        code=TEST_APPLICATION_CODE,
        defaults=TEST_APPLICATION_DEFAULTS,
    )

    usernames = [username for username, _ in PARTICIPANT_MAPPINGS]
    users = User.objects.filter(username__in=usernames)
    user_map = {user.username: user for user in users}

    role_slugs = [role_slug for _, role_slug in PARTICIPANT_MAPPINGS]
    roles = Role.objects.filter(slug__in=role_slugs)
    role_map = {role.slug: role for role in roles}

    owner_user = user_map.get("porteur_demande_user")

    dat, created = DAT.objects.get_or_create(
        reference=TEST_REFERENCE,
        defaults={
            "title": "Test",
            "description": (
                "DAT de démonstration liant les principaux acteurs de validation."
            ),
            "application": application,
            "status": "demande_initiale",
            "owner": owner_user,
        },
    )
    fields_to_update: list[str] = []
    if not created:
        if dat.application_id != application.id:
            dat.application = application
            fields_to_update.append("application")
        if dat.status != "demande_initiale":
            dat.status = "demande_initiale"
            fields_to_update.append("status")
        if owner_user and dat.owner_id != owner_user.id:
            dat.owner = owner_user
            fields_to_update.append("owner")
        if dat.title != "Test":
            dat.title = "Test"
            fields_to_update.append("title")
        if not dat.description:
            dat.description = (
                "DAT de démonstration liant les principaux acteurs de validation."
            )
            fields_to_update.append("description")
        if fields_to_update:
            dat.save(update_fields=fields_to_update)

    for username, role_slug in PARTICIPANT_MAPPINGS:
        user = user_map.get(username)
        role = role_map.get(role_slug)
        if not user or not role:
            continue
        participant, created = DATParticipant.objects.get_or_create(
            dat=dat,
            role=role,
            defaults={"user": user},
        )
        if not created and participant.user_id != user.id:
            participant.user = user
            participant.save(update_fields=["user"])


def delete_dat_with_participants(apps, schema_editor):
    Application = apps.get_model("dat", "Application")
    DAT = apps.get_model("dat", "DAT")
    DATParticipant = apps.get_model("dat", "DATParticipant")

    try:
        dat = DAT.objects.get(reference=TEST_REFERENCE)
    except DAT.DoesNotExist:
        dat = None

    if dat:
        DATParticipant.objects.filter(dat=dat).delete()
        application = dat.application
        dat.delete()
        if application and not DAT.objects.filter(application=application).exists():
            application.delete()

    # Clean up application if it still exists without any DAT
    try:
        application = Application.objects.get(code=TEST_APPLICATION_CODE)
    except Application.DoesNotExist:
        return
    if not DAT.objects.filter(application=application).exists():
        application.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("dat", "0008_datparticipant"),
    ]

    operations = [
        migrations.RunPython(create_dat_with_participants, delete_dat_with_participants),
    ]
