from django.db import migrations, models
import django.db.models.deletion


ROLE_DIRECTION_MAP = {
    "porteur-demande": "besoins",
    "architecte-referent": "architecture-technique",
    "architecte-technique": "architecture-technique",
    "urbaniste": "urbanisme",
    "analyste-secu": "cybersecurite",
    "rssi": "cybersecurite",
    "infra-exploitation": "exploitations",
    "comite-validation": "architecture-technique",
}

ADMIN_ROLE_SLUGS = ("admin",)


def assign_role_directions(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    TechnicalDirection = apps.get_model("users", "TechnicalDirection")

    directions = {
        slug: TechnicalDirection.objects.filter(slug=slug).only("id").first()
        for slug in set(ROLE_DIRECTION_MAP.values())
    }

    for role_slug, direction_slug in ROLE_DIRECTION_MAP.items():
        role = Role.objects.filter(slug=role_slug, technical_direction__isnull=True).only("id").first()
        direction = directions.get(direction_slug)
        if not role or not direction:
            continue
        Role.objects.filter(pk=role.pk).update(technical_direction=direction)


def mark_admin_roles(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    Role.objects.filter(slug__in=ADMIN_ROLE_SLUGS).update(is_admin_role=True)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_rename_projectdirection_to_technicaldirection"),
    ]

    operations = [
        migrations.AddField(
            model_name="role",
            name="is_admin_role",
            field=models.BooleanField(
                default=False,
                help_text="Les rôles administrateurs ne sont pas rattachés à une direction technique.",
            ),
        ),
        migrations.AddField(
            model_name="role",
            name="technical_direction",
            field=models.ForeignKey(
                blank=True,
                help_text="Direction technique associée à ce rôle.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="roles",
                to="users.technicaldirection",
            ),
        ),
        migrations.RunPython(assign_role_directions, migrations.RunPython.noop),
        migrations.RunPython(mark_admin_roles, migrations.RunPython.noop),
    ]
