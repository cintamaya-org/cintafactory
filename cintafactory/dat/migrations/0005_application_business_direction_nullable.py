from django.db import migrations, models
import django.db.models.deletion


DEFAULT_BUSINESS_DIRECTION_SLUG = "direction-metier-defaut"


def set_missing_business_directions(apps, schema_editor):
    Application = apps.get_model("dat", "Application")
    BusinessDirection = apps.get_model("users", "BusinessDirection")

    default_direction = (
        BusinessDirection.objects.filter(slug=DEFAULT_BUSINESS_DIRECTION_SLUG).order_by("id").first()
        or BusinessDirection.objects.order_by("id").first()
    )
    if default_direction is None:
        return

    Application.objects.filter(business_direction__isnull=True).update(business_direction=default_direction)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_realign_user_groups_with_roles"),
        ("dat", "0004_alter_datpartpayload_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="application",
            name="business_direction",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="applications",
                to="users.businessdirection",
                verbose_name="Direction métier",
            ),
        ),
        migrations.RunPython(set_missing_business_directions, migrations.RunPython.noop),
    ]
