from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="ProjectDirection",
            new_name="TechnicalDirection",
        ),
        migrations.AlterModelTable(
            name="technicaldirection",
            table="TECHNICAL_DIRECTION",
        ),
        migrations.RemoveConstraint(
            model_name="businessgroup",
            name="unique_business_direction_group_per_project_direction",
        ),
        migrations.AddConstraint(
            model_name="businessgroup",
            constraint=models.UniqueConstraint(
                fields=("business_direction", "direction"),
                condition=models.Q(("business_direction__isnull", False)),
                name="unique_business_direction_group_per_technical_direction",
            ),
        ),
    ]
