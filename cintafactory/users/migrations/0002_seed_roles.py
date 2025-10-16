from django.db import migrations

def seed_roles(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    data = [
        {"name": "Carrier",  "slug": "carrier",  "level": 10},
        {"name": "Reviewer", "slug": "reviewer", "level": 20},
        {"name": "Validator","slug": "validator","level": 30},
        {"name": "Admin",    "slug": "admin",    "level": 40},
    ]
    for r in data:
        Role.objects.update_or_create(slug=r["slug"], defaults=r)

def unseed_roles(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    Role.objects.filter(slug__in=["carrier","reviewer","validator","admin"]).delete()

class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(seed_roles, reverse_code=unseed_roles),
    ]
