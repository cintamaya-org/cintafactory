from django.db import migrations, models
from django.db.models import Q


NEW_ROLES = (
    {"name": "Porteur de la demande", "slug": "porteur-demande"},
    {"name": "Architecte Référent", "slug": "architecte-referent"},
    {"name": "Architecte Technique", "slug": "architecte-technique"},
    {"name": "Urbaniste", "slug": "urbaniste"},
    {"name": "Analyste Sécu", "slug": "analyste-secu"},
    {"name": "RSSI", "slug": "rssi"},
    {"name": "Comité de validation", "slug": "comite-validation"},
)

OLD_ROLES = (
    {"name": "Carrier", "slug": "carrier"},
    {"name": "Reviewer", "slug": "reviewer"},
    {"name": "Validator", "slug": "validator"},
    {"name": "Admin", "slug": "admin"},
)


def seed_roles(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    User = apps.get_model("users", "User")

    new_slugs = {role["slug"] for role in NEW_ROLES}

    for data in NEW_ROLES:
        Role.objects.update_or_create(slug=data["slug"], defaults=data)

    obsolete_roles = Role.objects.exclude(slug__in=new_slugs)
    if obsolete_roles.exists():
        User.objects.filter(role__in=obsolete_roles).update(role=None)
        obsolete_roles.delete()


def unseed_roles(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    User = apps.get_model("users", "User")

    for data in OLD_ROLES:
        Role.objects.update_or_create(slug=data["slug"], defaults=data)

    fresh_roles = Role.objects.filter(slug__in=[role["slug"] for role in NEW_ROLES])
    if fresh_roles.exists():
        User.objects.filter(role__in=fresh_roles).update(role=None)
        fresh_roles.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_drop_role_level"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="architect_referent",
            field=models.ForeignKey(
                blank=True,
                help_text="Referent de rattachement pour les architectes techniques.",
                limit_choices_to={"role__slug": "architecte-referent"},
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="technical_architects",
                to="users.user",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                check=Q(role__slug="architecte-technique", architect_referent__isnull=False)
                | ~Q(role__slug="architecte-technique"),
                name="architecte_technique_requires_referent",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                check=~Q(role__slug="architecte-referent", architect_referent__isnull=False),
                name="architecte_referent_cannot_have_referent",
            ),
        ),
        migrations.RunPython(seed_roles, reverse_code=unseed_roles),
    ]
