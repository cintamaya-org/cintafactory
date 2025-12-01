from django.db import migrations, models
import django.db.models.deletion


TECHNICAL_DIRECTIONS = {
    "architecture-technique": "Architecture technique",
    "besoins": "Besoins",
    "cybersecurite": "Cybersécurité",
    "exploitations": "Exploitations",
    "urbanisme": "Urbanisme",
}

ROLE_DEFINITIONS = (
    {"slug": "porteur-demande", "name": "Porteur de la demande"},
    {"slug": "architecte-referent", "name": "Architecte Référent"},
    {"slug": "architecte-technique", "name": "Architecte Technique"},
    {"slug": "urbaniste", "name": "Urbaniste"},
    {"slug": "analyste-secu", "name": "Analyste Sécu"},
    {"slug": "rssi", "name": "RSSI"},
    {"slug": "infra-exploitation", "name": "Infra / Exploitation"},
    {"slug": "comite-validation", "name": "Comité de validation"},
)

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


def _get_default_group_responsible(apps):
    User = apps.get_model("users", "User")
    return User.objects.filter(is_superuser=True).order_by("id").first() or User.objects.order_by("id").first()


def _seed_directions_and_roles(apps):
    TechnicalDirection = apps.get_model("users", "TechnicalDirection")
    Role = apps.get_model("users", "Role")

    directions = {}
    for slug, name in TECHNICAL_DIRECTIONS.items():
        direction, created = TechnicalDirection.objects.get_or_create(slug=slug, defaults={"name": name})
        if not created and direction.name != name:
            direction.name = name
            direction.save(update_fields=["name"])
        directions[slug] = direction

    roles = {}
    for data in ROLE_DEFINITIONS:
        role, _ = Role.objects.get_or_create(slug=data["slug"], defaults={"name": data["name"]})
        if role.name != data["name"]:
            role.name = data["name"]
            role.save(update_fields=["name"])
        roles[role.slug] = role

    for role_slug, direction_slug in ROLE_DIRECTION_MAP.items():
        role = roles.get(role_slug)
        direction = directions.get(direction_slug)
        if not role or not direction:
            continue
        if role.technical_direction_id != direction.id:
            role.technical_direction = direction
            role.save(update_fields=["technical_direction"])


def _ensure_default_groups(apps):
    TechnicalDirection = apps.get_model("users", "TechnicalDirection")
    BusinessGroup = apps.get_model("users", "BusinessGroup")
    BusinessDirection = apps.get_model("users", "BusinessDirection")

    responsible = _get_default_group_responsible(apps)
    business_direction = BusinessDirection.objects.order_by("id").first()
    for direction in TechnicalDirection.objects.all():
        group = (
            BusinessGroup.objects.filter(direction=direction, is_default=True).order_by("id").first()
            or BusinessGroup.objects.filter(direction=direction).order_by("id").first()
        )
        if group:
            updates = []
            if group.responsible_id is None and responsible:
                group.responsible = responsible
                updates.append("responsible")
            elif responsible and group.responsible_id != responsible.id:
                group.responsible = responsible
                updates.append("responsible")
            if business_direction and not group.business_direction_id:
                group.business_direction = business_direction
                updates.append("business_direction")
            if not group.is_default:
                group.is_default = True
                updates.append("is_default")
            if updates:
                group.save(update_fields=updates)
            continue
        if not responsible:
            continue
        base_name = f"{direction.name} - Groupe par défaut"
        name = base_name
        counter = 2
        while BusinessGroup.objects.filter(name=name).exists():
            name = f"{base_name} {counter}"
            counter += 1
        BusinessGroup.objects.create(
            name=name,
            direction=direction,
            responsible=responsible,
            is_default=True,
            business_direction=business_direction,
        )


def _align_users_with_roles(apps):
    BusinessGroup = apps.get_model("users", "BusinessGroup")
    Role = apps.get_model("users", "Role")
    User = apps.get_model("users", "User")

    # Assign groups to users whose role targets a direction.
    roles = Role.objects.filter(technical_direction__isnull=False).select_related("technical_direction")
    for role in roles:
        default_group = (
            BusinessGroup.objects.filter(direction=role.technical_direction, is_default=True).order_by("id").first()
            or BusinessGroup.objects.filter(direction=role.technical_direction).order_by("id").first()
        )
        if default_group:
            User.objects.filter(role=role, business_group__isnull=True).update(business_group=default_group)

    # Remove groups from users whose role is directionless.
    User.objects.filter(role__technical_direction__isnull=True).update(business_group=None)


def forwards(apps, schema_editor):
    _seed_directions_and_roles(apps)
    _ensure_default_groups(apps)
    _align_users_with_roles(apps)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_role_direction_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="business_group",
            field=models.ForeignKey(
                blank=True,
                help_text="Groupe métier auquel appartient l'utilisateur.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="users.businessgroup",
            ),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
