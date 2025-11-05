from __future__ import annotations

from django.contrib.auth.hashers import make_password
from django.db import migrations


DEFAULT_PASSWORD = "123+Aze"


def create_default_users(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    User = apps.get_model("users", "User")

    password_hash = make_password(DEFAULT_PASSWORD)
    superuser_username = "super_admin"

    if not User.objects.filter(username=superuser_username).exists():
        User.objects.create(
            username=superuser_username,
            email="super_admin@example.com",
            is_active=True,
            is_staff=True,
            is_superuser=True,
            password=password_hash,
        )

    roles = list(Role.objects.all())
    slug_to_role = {role.slug: role for role in roles}

    def ensure_user_for_role(role: Role):
        existing_user = User.objects.filter(role=role).first()
        if existing_user:
            return existing_user

        base_username = f"{role.slug.replace('-', '_')}_user"
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user = User(
            username=username,
            email=f"{username}@example.com",
            role=role,
            is_active=True,
        )

        if role.slug == "architecte-technique":
            referent_role = slug_to_role.get("architecte-referent")
            if referent_role:
                referent_user = ensure_user_for_role(referent_role)
                if referent_user:
                    user.architect_referent_id = referent_user.id

        user.password = password_hash
        user.save()
        return user

    referent_role = slug_to_role.get("architecte-referent")
    if referent_role:
        ensure_user_for_role(referent_role)

    for role in roles:
        ensure_user_for_role(role)


def remove_default_users(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    User = apps.get_model("users", "User")

    User.objects.filter(
        username="super_admin",
        email="super_admin@example.com",
        is_superuser=True,
    ).delete()

    for role in Role.objects.all():
        base_username = f"{role.slug.replace('-', '_')}_user"
        User.objects.filter(
            role=role,
            username__startswith=base_username,
            email__endswith="@example.com",
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0006_add_infra_exploitation_role"),
    ]

    operations = [
        migrations.RunPython(create_default_users, reverse_code=remove_default_users),
    ]
