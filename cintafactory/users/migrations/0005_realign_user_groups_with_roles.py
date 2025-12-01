from django.db import migrations


def _get_default_group_responsible(apps):
    User = apps.get_model("users", "User")
    return User.objects.filter(is_superuser=True).order_by("id").first() or User.objects.order_by("id").first()


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
            if business_direction and not group.business_direction_id:
                group.business_direction = business_direction
                updates.append("business_direction")
            if responsible and group.responsible_id != responsible.id:
                group.responsible = responsible
                updates.append("responsible")
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


def _realign_users(apps):
    BusinessGroup = apps.get_model("users", "BusinessGroup")
    Role = apps.get_model("users", "Role")
    User = apps.get_model("users", "User")

    # Ensure default groups exist per direction before assignment.
    _ensure_default_groups(apps)

    roles_with_direction = Role.objects.filter(technical_direction__isnull=False).select_related("technical_direction")
    for role in roles_with_direction:
        default_group = (
            BusinessGroup.objects.filter(direction=role.technical_direction, is_default=True).order_by("id").first()
            or BusinessGroup.objects.filter(direction=role.technical_direction).order_by("id").first()
        )
        if not default_group:
            continue
        User.objects.filter(role=role).update(business_group=default_group)

    # Roles without direction must not have a group.
    User.objects.filter(role__technical_direction__isnull=True).update(business_group=None)


def forwards(apps, schema_editor):
    _realign_users(apps)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_directional_group_defaults"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
