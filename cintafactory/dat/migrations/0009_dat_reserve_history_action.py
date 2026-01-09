from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dat", "0008_dat_reserve_history"),
    ]

    operations = [
        migrations.AddField(
            model_name="datreservehistory",
            name="action",
            field=models.CharField(
                choices=[("set", "Mise en réserve"), ("cleared", "Réserve levée")],
                default="set",
                max_length=20,
            ),
        ),
    ]
