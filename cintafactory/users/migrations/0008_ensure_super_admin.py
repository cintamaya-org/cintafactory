from __future__ import annotations

from django.contrib.auth.hashers import make_password
from django.db import migrations

DEFAULT_PASSWORD = "123+Aze"
SUPERUSER_USERNAME = "super_admin"
SUPERUSER_EMAIL = "super_admin@example.com"


def create_super_admin(apps, schema_editor):
    User = apps.get_model("users", "User")

    if not User.objects.filter(username=SUPERUSER_USERNAME).exists():
        User.objects.create(
            username=SUPERUSER_USERNAME,
            email=SUPERUSER_EMAIL,
            is_active=True,
            is_staff=True,
            is_superuser=True,
            password=make_password(DEFAULT_PASSWORD),
        )


def remove_super_admin(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(
        username=SUPERUSER_USERNAME,
        email=SUPERUSER_EMAIL,
        is_superuser=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0007_create_default_users"),
    ]

    operations = [
        migrations.RunPython(create_super_admin, reverse_code=remove_super_admin),
    ]
